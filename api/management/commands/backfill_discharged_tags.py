"""Tag every currently-discharged patient with 'Discharged'.

A patient counts as discharged when they have at least one admission but none
that is ACTIVE. New discharges are tagged automatically by ``dischargePatient``;
this backfills patients discharged before that behaviour existed. Idempotent.

Usage:
    python manage.py backfill_discharged_tags
    python manage.py backfill_discharged_tags --dry-run
"""
from django.core.management.base import BaseCommand

from api.models import AdmissionStatus, Patient, Tag, TagCategory


class Command(BaseCommand):
    help = "Add the 'Discharged' tag to patients with no active admission."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Report what would change without writing anything.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        tag, _ = Tag.get_or_create_normalized(
            "Discharged", category=TagCategory.OTHER
        )

        added = 0
        for patient in Patient.objects.prefetch_related("admissions", "tags"):
            admissions = list(patient.admissions.all())
            if not admissions:
                continue                      # never admitted — not discharged
            if any(a.status == AdmissionStatus.ACTIVE for a in admissions):
                continue                      # currently admitted
            if patient.tags.filter(pk=tag.pk).exists():
                continue                      # already tagged
            if not dry_run:
                patient.tags.add(tag)
            added += 1

        verb = "Would tag" if dry_run else "Tagged"
        self.stdout.write(self.style.SUCCESS(
            f"{verb} {added} discharged patient(s) with 'Discharged'."
        ))
