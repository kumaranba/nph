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

# Public {vital_type_value: reading_field} map, e.g. {"BP_SYSTOLIC": "bp_systolic"}.
VITAL_FIELD_BY_TYPE = {vital_type.value: field for vital_type, field in _VITAL_FIELDS}


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


# Friendly labels for the vital types.
VITAL_LABELS = {
    VitalType.BP_SYSTOLIC: "BP systolic",
    VitalType.BP_DIASTOLIC: "BP diastolic",
    VitalType.PULSE: "Pulse",
    VitalType.TEMPERATURE: "Temperature",
    VitalType.SPO2: "SpO₂",
    VitalType.WEIGHT: "Weight",
}


def _severity(value, below, above) -> str:
    """Heuristic: a breach is "critical" once the value is more than 10% beyond
    the breached bound, otherwise "warning"."""
    if below is not None and value < below and below > 0:
        margin = (float(below) - float(value)) / float(below)
    elif above is not None and value > above and above > 0:
        margin = (float(value) - float(above)) / float(above)
    else:
        return "warning"
    return "critical" if margin >= 0.10 else "warning"


def breach_details(reading) -> list[dict]:
    """Per-breach detail for a reading: one dict per out-of-range vital with
    its label, value, direction ("high"/"low") and severity."""
    thresholds = {t.vital_type: t for t in VitalsThreshold.objects.all()}
    details: list[dict] = []
    for vital_type, field in _VITAL_FIELDS:
        value = getattr(reading, field)
        if value is None:
            continue
        threshold = thresholds.get(vital_type)
        if threshold is None:
            continue
        below, above = threshold.below_threshold, threshold.above_threshold
        low = below is not None and value < below
        high = above is not None and value > above
        if not (low or high):
            continue
        details.append(
            {
                "vital_type": vital_type,
                "label": VITAL_LABELS.get(vital_type, vital_type),
                "value": float(value),
                "direction": "low" if low else "high",
                "severity": _severity(value, below, above),
            }
        )
    return details
