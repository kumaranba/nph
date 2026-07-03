"""Vitals flagging: compare a VitalReading against the VitalsThreshold table.

A vital is flagged when its value is below the configured ``below_threshold``
or above the ``above_threshold`` for its VitalType. A threshold side left as
None means that side is unbounded (e.g. SpO2 only has a lower bound).
"""
from .models import VitalsThreshold, VitalType

# Maps each VitalType to the corresponding field on a VitalReading.
_VITAL_FIELDS = [
    (VitalType.BP_SYSTOLIC, "bp_systolic"),
    (VitalType.BP_DIASTOLIC, "bp_diastolic"),
    (VitalType.PULSE, "pulse"),
    (VitalType.TEMPERATURE, "temperature"),
    (VitalType.SPO2, "spo2"),
    (VitalType.WEIGHT, "weight"),
]


def breached_vitals(reading) -> list[str]:
    """Return the VitalType values (e.g. ['SPO2', 'PULSE']) that breach a
    threshold for this reading. Works on unsaved readings too."""
    thresholds = {t.vital_type: t for t in VitalsThreshold.objects.all()}
    flagged: list[str] = []
    for vital_type, field in _VITAL_FIELDS:
        value = getattr(reading, field)
        if value is None:
            continue
        threshold = thresholds.get(vital_type)
        if threshold is None:
            continue
        below, above = threshold.below_threshold, threshold.above_threshold
        if (below is not None and value < below) or (
            above is not None and value > above
        ):
            flagged.append(vital_type)
    return flagged


def has_flag(reading) -> bool:
    """True if any vital on the reading breaches its threshold."""
    return bool(breached_vitals(reading))
