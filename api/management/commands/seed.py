"""
Idempotent seed command for reference data: rooms, beds, and the default
vitals thresholds that drive the `has_flag` logic on VitalReading.

Run it as often as you like — it uses get_or_create / update_or_create, so
re-running never duplicates rows. It does NOT touch patients, admissions,
invoices, payments, or users (those are operational data, not reference data).

    python manage.py seed
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from api.models import (
    Bed,
    BedStatus,
    Room,
    VitalsThreshold,
    VitalType,
)

# --- Rooms & their beds -----------------------------------------------------
# name -> list of bed labels. Capacity is derived from the number of beds so
# the two can never drift out of sync.
ROOMS = {
    "General Ward A": ["A1", "A2", "A3", "A4", "A5", "A6"],
    "General Ward B": ["B1", "B2", "B3", "B4", "B5", "B6"],
    "Semi-Private 1": ["SP1-1", "SP1-2"],
    "Semi-Private 2": ["SP2-1", "SP2-2"],
    "Private 1": ["P1"],
    "Private 2": ["P2"],
    "ICU": ["ICU-1", "ICU-2", "ICU-3", "ICU-4"],
}

# --- Default vitals thresholds ----------------------------------------------
# (below_threshold, above_threshold). None means "no bound on that side".
# A reading flags when value < below_threshold or value > above_threshold.
VITALS_THRESHOLDS = {
    VitalType.BP_SYSTOLIC:  (90, 180),
    VitalType.BP_DIASTOLIC: (60, 110),
    VitalType.PULSE:        (50, 120),
    VitalType.TEMPERATURE:  (95.0, 100.4),   # degrees F
    VitalType.SPO2:         (90, None),       # only a lower bound matters
    VitalType.WEIGHT:       (None, None),     # tracked, not auto-flagged
}


class Command(BaseCommand):
    help = "Seed reference data: rooms, beds, and default vitals thresholds."

    @transaction.atomic
    def handle(self, *args, **options):
        rooms_created = beds_created = 0

        for room_name, bed_labels in ROOMS.items():
            room, created = Room.objects.get_or_create(
                name=room_name,
                defaults={"capacity": len(bed_labels)},
            )
            if created:
                rooms_created += 1
            elif room.capacity != len(bed_labels):
                # Keep capacity aligned with the configured bed count.
                room.capacity = len(bed_labels)
                room.save(update_fields=["capacity"])

            for label in bed_labels:
                _, bed_created = Bed.objects.get_or_create(
                    room=room,
                    label=label,
                    defaults={"status": BedStatus.VACANT},
                )
                if bed_created:
                    beds_created += 1

        thresholds_written = 0
        for vital_type, (below, above) in VITALS_THRESHOLDS.items():
            VitalsThreshold.objects.update_or_create(
                vital_type=vital_type,
                defaults={"below_threshold": below, "above_threshold": above},
            )
            thresholds_written += 1

        self.stdout.write(
            self.style.SUCCESS(
                "Seed complete: "
                f"{rooms_created} new room(s), "
                f"{beds_created} new bed(s), "
                f"{thresholds_written} vitals threshold(s) ensured."
            )
        )
