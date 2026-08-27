"""Duplicate-inquiry detection.

The same prospective patient often turns up as several ``Inquiry`` rows — a
WhatsApp ping, a phone call, a web-form submission, an OP-list import. This
groups likely duplicates so a PRO can merge them.

Signal: a normalized phone number (strongest), falling back to a normalized
name when no phone is present. Merged-away and already-linked-to-a-patient rows
are still surfaced (merging a fresh lead into an admitted one is valid), but a
group needs at least two rows to be worth showing.
"""
import re

from django.db import transaction

from .models import (
    Activity, ActivityKind, ConsentStatus, FollowUp, Inquiry, InquirySource,
    InquiryStatus,
)
from .phones import normalize_phone


class MergeError(Exception):
    """A merge that can't proceed (same row, or two different real patients)."""


def _name_key(name: str) -> str:
    """Lowercased, whitespace-collapsed name for coarse matching."""
    return re.sub(r'\s+', ' ', (name or '').strip().lower())


def _group_key(inquiry) -> str:
    """The dedup key for one inquiry: its normalized phone if present, else a
    ``name:`` fallback. Returns '' when there is nothing to match on."""
    phone = normalize_phone(inquiry.phone or '')
    if phone:
        return f'phone:{phone}'
    name = _name_key(inquiry.name)
    return f'name:{name}' if name else ''


def find_duplicate_groups(queryset=None):
    """Return groups of inquiries that share a dedup key, as a list of
    ``(key, [inquiries])`` tuples — only groups with two or more members.

    Groups are ordered by descending size then key; within a group inquiries
    are oldest-first (a stable default primary for the UI). ``key`` is the
    human-facing value (a phone number, or ``name:<name>``)."""
    qs = queryset if queryset is not None else Inquiry.objects.all()
    qs = qs.select_related('patient', 'referrer', 'assigned_to', 'created_by')

    buckets = {}
    for inq in qs:
        key = _group_key(inq)
        if not key:
            continue
        buckets.setdefault(key, []).append(inq)

    groups = [
        (key, sorted(items, key=lambda i: (i.created_at, i.id)))
        for key, items in buckets.items()
        if len(items) >= 2
    ]
    groups.sort(key=lambda g: (-len(g[1]), g[0]))
    return groups


# Pipeline progress rank; LOST sits below NEW so any active re-engagement wins.
_STAGE_RANK = {
    InquiryStatus.LOST: -1,
    InquiryStatus.NEW: 0,
    InquiryStatus.CONTACTED: 1,
    InquiryStatus.CONSULTED: 2,
    InquiryStatus.ADMITTED: 3,
}


@transaction.atomic
def merge_inquiries(primary, duplicate, user=None):
    """Merge ``duplicate`` into ``primary`` (the survivor) and delete it.

    Blanks on the primary are backfilled from the duplicate, the furthest
    pipeline stage is kept, the strictest contact preferences win, and the
    duplicate's activities and follow-ups are re-parented onto the primary. A
    system activity records the provenance. Returns the refreshed primary.

    Raises ``MergeError`` if the two are the same row or point at two different
    real patients (that's two admissions, not one lead)."""
    if primary.pk == duplicate.pk:
        raise MergeError('Cannot merge an inquiry into itself.')
    if (
        primary.patient_id and duplicate.patient_id
        and primary.patient_id != duplicate.patient_id
    ):
        raise MergeError(
            'These inquiries are linked to different patients and cannot be merged.'
        )

    # Backfill blank primary fields from the duplicate.
    if not primary.phone:
        primary.phone = duplicate.phone
    if not primary.referrer_id:
        primary.referrer_id = duplicate.referrer_id
    if not primary.assigned_to_id:
        primary.assigned_to_id = duplicate.assigned_to_id
    if primary.consulted_on is None:
        primary.consulted_on = duplicate.consulted_on

    # Contact preferences: strictest wins (do-not-contact sticks; a DECLINED or
    # GRANTED answer supersedes UNKNOWN, and DECLINED beats GRANTED).
    primary.do_not_contact = primary.do_not_contact or duplicate.do_not_contact
    if duplicate.contact_consent == ConsentStatus.DECLINED:
        primary.contact_consent = ConsentStatus.DECLINED
    elif (
        primary.contact_consent == ConsentStatus.UNKNOWN
        and duplicate.contact_consent != ConsentStatus.UNKNOWN
    ):
        primary.contact_consent = duplicate.contact_consent

    # Append the duplicate's notes so nothing written about the lead is lost.
    if duplicate.notes.strip():
        primary.notes = (
            f'{primary.notes}\n\n{duplicate.notes}'.strip()
            if primary.notes.strip() else duplicate.notes
        )

    # Keep the furthest pipeline stage. Adopting an ADMITTED duplicate carries
    # its patient link; landing on any non-LOST stage clears the lost reason.
    if _STAGE_RANK[duplicate.status] > _STAGE_RANK[primary.status]:
        primary.status = duplicate.status
        if duplicate.status == InquiryStatus.ADMITTED and not primary.patient_id:
            primary.patient_id = duplicate.patient_id
        primary.lost_reason = duplicate.lost_reason
        primary.lost_reason_note = duplicate.lost_reason_note
    if primary.status != InquiryStatus.LOST:
        primary.lost_reason = ''
        primary.lost_reason_note = ''

    primary.save()

    # Re-parent the duplicate's timeline and follow-ups onto the survivor
    # (their FKs cascade-delete, so this must happen before the delete).
    Activity.objects.filter(inquiry=duplicate).update(inquiry=primary)
    FollowUp.objects.filter(inquiry=duplicate).update(inquiry=primary)

    src = InquirySource(duplicate.source).label
    Activity.objects.create(
        inquiry=primary, type=ActivityKind.SYSTEM,
        body=(
            f'Merged duplicate inquiry "{duplicate.name}" '
            f'({src}, added {duplicate.created_at:%d-%m-%Y}) into this record'
        ),
        created_by=user,
    )
    duplicate.delete()
    primary.refresh_from_db()
    return primary
