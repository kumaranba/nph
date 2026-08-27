"""Tests for duplicate-inquiry detection and merge."""
from datetime import date, timedelta

import pytest

from api.dedup import MergeError, find_duplicate_groups, merge_inquiries
from api.models import (
    Activity, ActivityKind, ConsentStatus, FollowUp, Inquiry,
    InquiryStatus, LostReason, Patient,
)


def _inq(name, phone="", source="PHONE", status=InquiryStatus.NEW, **kw):
    return Inquiry.objects.create(
        name=name, phone=phone, source=source, status=status, **kw
    )


# --- detection ------------------------------------------------------------

def test_groups_by_normalized_phone(db):
    a = _inq("Ravi", "9876543210")
    b = _inq("Ravi K", "+91 98765 43210")   # same number, different formatting
    _inq("Someone", "9000000000")            # unique → not grouped
    groups = find_duplicate_groups()
    assert len(groups) == 1
    key, items = groups[0]
    assert key == "phone:+919876543210"
    assert {i.id for i in items} == {a.id, b.id}


def test_groups_by_name_when_no_phone(db):
    a = _inq("  Meena  Devi ")
    b = _inq("meena devi")
    groups = find_duplicate_groups()
    assert len(groups) == 1
    assert {i.id for i in groups[0][1]} == {a.id, b.id}


def test_singletons_are_not_groups(db):
    _inq("Solo", "9876500000")
    assert find_duplicate_groups() == []


def test_group_members_sorted_oldest_first(db):
    old = _inq("A", "9876543210")
    new = _inq("A2", "9876543210")
    # Force created_at ordering (auto_now_add sets both ~now; nudge old back).
    Inquiry.objects.filter(pk=old.pk).update(
        created_at=new.created_at - timedelta(days=1)
    )
    groups = find_duplicate_groups()
    ids = [i.id for i in groups[0][1]]
    assert ids == [old.id, new.id]


# --- merge ----------------------------------------------------------------

def test_merge_reparents_activities_and_follow_ups(db):
    primary = _inq("Ravi", "9876543210")
    dup = _inq("Ravi", "9876543210")
    Activity.objects.create(inquiry=dup, type=ActivityKind.NOTE, body="called")
    FollowUp.objects.create(inquiry=dup, follow_up_date=date.today())

    merge_inquiries(primary, dup)

    assert not Inquiry.objects.filter(pk=dup.pk).exists()   # duplicate gone
    # The note moved to primary; a SYSTEM provenance activity was added.
    assert Activity.objects.filter(inquiry=primary, type=ActivityKind.NOTE).count() == 1
    assert Activity.objects.filter(inquiry=primary, type=ActivityKind.SYSTEM).count() == 1
    assert FollowUp.objects.filter(inquiry=primary).count() == 1


def test_merge_backfills_blank_primary_fields(db):
    primary = _inq("Ravi", "")               # no phone
    dup = _inq("Ravi", "9876543210", consulted_on=date(2026, 1, 5))
    merge_inquiries(primary, dup)
    primary.refresh_from_db()
    assert primary.phone == "9876543210"
    assert primary.consulted_on == date(2026, 1, 5)


def test_merge_keeps_furthest_stage(db):
    primary = _inq("Ravi", "9876543210", status=InquiryStatus.NEW)
    dup = _inq("Ravi", "9876543210", status=InquiryStatus.CONSULTED)
    merge_inquiries(primary, dup)
    primary.refresh_from_db()
    assert primary.status == InquiryStatus.CONSULTED


def test_active_duplicate_supersedes_lost_primary(db):
    primary = _inq("Ravi", "9876543210", status=InquiryStatus.LOST,
                   lost_reason=LostReason.UNREACHABLE)
    dup = _inq("Ravi", "9876543210", status=InquiryStatus.CONTACTED)
    merge_inquiries(primary, dup)
    primary.refresh_from_db()
    assert primary.status == InquiryStatus.CONTACTED
    assert primary.lost_reason == ""          # cleared on re-engagement


def test_merge_adopts_patient_from_admitted_duplicate(db):
    patient = Patient.objects.create(name="Ravi", diagnosis="d", admitting_doctor="Dr")
    primary = _inq("Ravi", "9876543210", status=InquiryStatus.NEW)
    dup = _inq("Ravi", "9876543210", status=InquiryStatus.ADMITTED, patient=patient)
    merge_inquiries(primary, dup)
    primary.refresh_from_db()
    assert primary.status == InquiryStatus.ADMITTED
    assert primary.patient_id == patient.id


def test_merge_strictest_contact_preferences_win(db):
    primary = _inq("Ravi", "9876543210", contact_consent=ConsentStatus.GRANTED)
    dup = _inq("Ravi", "9876543210", contact_consent=ConsentStatus.DECLINED,
               do_not_contact=True)
    merge_inquiries(primary, dup)
    primary.refresh_from_db()
    assert primary.contact_consent == ConsentStatus.DECLINED
    assert primary.do_not_contact is True


def test_merge_appends_notes(db):
    primary = _inq("Ravi", "9876543210", notes="first")
    dup = _inq("Ravi", "9876543210", notes="second")
    merge_inquiries(primary, dup)
    primary.refresh_from_db()
    assert "first" in primary.notes and "second" in primary.notes


def test_merge_self_raises(db):
    a = _inq("Ravi", "9876543210")
    with pytest.raises(MergeError):
        merge_inquiries(a, a)


def test_merge_different_patients_raises(db):
    p1 = Patient.objects.create(name="A", diagnosis="d", admitting_doctor="Dr")
    p2 = Patient.objects.create(name="B", diagnosis="d", admitting_doctor="Dr")
    primary = _inq("A", "9876543210", status=InquiryStatus.ADMITTED, patient=p1)
    dup = _inq("A", "9876543210", status=InquiryStatus.ADMITTED, patient=p2)
    with pytest.raises(MergeError):
        merge_inquiries(primary, dup)


# --- GraphQL + RBAC -------------------------------------------------------

GROUPS = """
query { duplicateInquiryGroups { key inquiries { id name } } }
"""

MERGE = """
mutation($p: ID!, $d: ID!) {
  mergeInquiries(primaryId: $p, duplicateId: $d) { id phone }
}
"""


def test_groups_query_for_pro(pro_client, db):
    _inq("Ravi", "9876543210")
    _inq("Ravi", "9876543210")
    result = pro_client.execute(GROUPS)
    assert result.get("errors") is None
    assert len(result["data"]["duplicateInquiryGroups"]) == 1


def test_pro_merges_via_graphql(pro_client, db):
    primary = _inq("Ravi", "")
    dup = _inq("Ravi", "9876543210")
    result = pro_client.execute(MERGE, {"p": str(primary.id), "d": str(dup.id)})
    assert result.get("errors") is None
    assert result["data"]["mergeInquiries"]["phone"] == "9876543210"
    assert not Inquiry.objects.filter(pk=dup.pk).exists()


@pytest.mark.parametrize("client_name", ["admin_client", "finance_client", "nurse_client"])
def test_merge_forbidden_for_non_pro(request, client_name, db):
    primary = _inq("Ravi", "9876543210")
    dup = _inq("Ravi", "9876543210")
    client = request.getfixturevalue(client_name)
    result = client.execute(MERGE, {"p": str(primary.id), "d": str(dup.id)})
    assert result["errors"]
    assert Inquiry.objects.filter(pk=dup.pk).exists()   # untouched


def test_admin_can_view_groups(admin_client, db):
    _inq("Ravi", "9876543210")
    _inq("Ravi", "9876543210")
    result = admin_client.execute(GROUPS)
    assert result.get("errors") is None
    assert len(result["data"]["duplicateInquiryGroups"]) == 1
