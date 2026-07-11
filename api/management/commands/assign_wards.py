"""Create wards W1/W2/W3 (male) and W5/W6 (female), each with beds B1-B25,
then randomly distribute the 100 imported patients (all currently without a
bed) across the appropriate ward set.

Female patients  → W5, W6  (50 beds for 37 patients)
Male   patients  → W1, W2, W3  (75 beds for 63 patients)

Gender is inferred from import order: the first 37 patients by patient_id
are female (CSV rows 1-37), the remaining 63 are male (CSV rows 38-100).

Usage:
    python manage.py assign_wards
    python manage.py assign_wards --dry-run
"""
import random

from django.core.management.base import BaseCommand
from django.db import transaction

from api.models import Admission, Bed, BedStatus, Room

MALE_WARDS   = ["W1", "W2", "W3"]
FEMALE_WARDS = ["W5", "W6"]
BEDS_PER_WARD = 25
BED_LABELS = [f"B{i}" for i in range(1, BEDS_PER_WARD + 1)]

FEMALE_COUNT = 37   # first N patients by patient_id are female


class Command(BaseCommand):
    help = "Create wards W1-W3 (male) and W5-W6 (female) and assign imported patients to beds."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true",
                            help="Show what would happen without making changes.")
        parser.add_argument("--seed", type=int, default=None,
                            help="Random seed for reproducible assignment.")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        seed = options["seed"]
        if seed is not None:
            random.seed(seed)
        else:
            random.seed()

        # All admissions without a bed, ordered by patient_id for stable gender split.
        admissions = list(
            Admission.objects.filter(bed__isnull=True)
            .select_related("patient")
            .order_by("patient__patient_id")
        )

        if not admissions:
            self.stdout.write(self.style.WARNING("No unassigned admissions found."))
            return

        female_admissions = admissions[:FEMALE_COUNT]
        male_admissions   = admissions[FEMALE_COUNT:]

        self.stdout.write(
            f"Found {len(female_admissions)} female and {len(male_admissions)} male admissions."
        )

        if dry_run:
            self._report(female_admissions, FEMALE_WARDS)
            self._report(male_admissions, MALE_WARDS)
            return

        with transaction.atomic():
            female_beds = self._create_wards_and_get_beds(FEMALE_WARDS)
            male_beds   = self._create_wards_and_get_beds(MALE_WARDS)

            self._assign(female_admissions, female_beds, "female")
            self._assign(male_admissions,   male_beds,   "male")

        self.stdout.write(self.style.SUCCESS("Ward assignment complete."))

    def _create_wards_and_get_beds(self, ward_names):
        beds = []
        for ward_name in ward_names:
            room, created = Room.objects.get_or_create(
                name=ward_name,
                defaults={"capacity": BEDS_PER_WARD},
            )
            if created:
                self.stdout.write(f"  Created room {ward_name}")
            for label in BED_LABELS:
                bed, _ = Bed.objects.get_or_create(
                    room=room,
                    label=label,
                    defaults={"status": BedStatus.VACANT},
                )
                if bed.status == BedStatus.VACANT:
                    beds.append(bed)
        return beds

    def _assign(self, admissions, available_beds, gender_label):
        if len(admissions) > len(available_beds):
            self.stdout.write(self.style.ERROR(
                f"Not enough beds for {gender_label} patients "
                f"({len(admissions)} patients, {len(available_beds)} beds)."
            ))
            return

        chosen_beds = random.sample(available_beds, len(admissions))
        for admission, bed in zip(admissions, chosen_beds):
            admission.bed = bed
            admission.save(update_fields=["bed"])
            bed.status = BedStatus.OCCUPIED
            bed.save(update_fields=["status"])
            self.stdout.write(
                f"  {admission.patient.patient_id} {admission.patient.name} "
                f"→ {bed.room.name}/{bed.label}"
            )

    def _report(self, admissions, ward_names):
        self.stdout.write(
            f"  Would assign {len(admissions)} patients across {ward_names}"
        )
