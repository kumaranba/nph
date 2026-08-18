"""Tests for the import_patients management command."""
from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import call_command

from api.models import (
    Admission,
    AdmissionStatus,
    Bed,
    BedStatus,
    Invoice,
    Patient,
    Room,
)

HEADER = (
    "name,diagnosis,admitting_doctor,room,bed,"
    "admission_date,monthly_fee,guardian_name,guardian_phone"
)


@pytest.fixture
def ward(db):
    room = Room.objects.create(name="Ward A", capacity=3)
    for label in ("A1", "A2", "A3"):
        Bed.objects.create(room=room, label=label, status=BedStatus.VACANT)
    return room


def _write_csv(tmp_path, *rows):
    path = tmp_path / "patients.csv"
    path.write_text(HEADER + "\n" + "\n".join(rows) + "\n")
    return str(path)


def _run(path, **kwargs):
    out = StringIO()
    call_command("import_patients", path, stdout=out, **kwargs)
    return out.getvalue()


def test_valid_row_creates_patient_admission_invoice(tmp_path, ward):
    path = _write_csv(
        tmp_path,
        "Jane Doe,Pneumonia,Dr. Smith,Ward A,A1,2026-01-15,25000.00,John Doe,98765",
    )
    output = _run(path)

    assert "Imported 1 patient" in output
    patient = Patient.objects.get(name="Jane Doe")
    assert patient.patient_id.startswith("NPH-")
    admission = Admission.objects.get(patient=patient)
    assert admission.status == AdmissionStatus.ACTIVE
    assert admission.monthly_fee == Decimal("25000.00")
    # Bed flipped and a first invoice generated.
    admission.bed.refresh_from_db()
    assert admission.bed.status == BedStatus.OCCUPIED
    assert Invoice.objects.filter(admission=admission).count() == 1


def test_optional_guardian_fields_may_be_blank(tmp_path, ward):
    path = _write_csv(
        tmp_path,
        "Ravi Kumar,Post-op,Dr. Rao,Ward A,A2,2026-01-16,25000.00,,",
    )
    _run(path)
    p = Patient.objects.get(name="Ravi Kumar")
    assert p.guardian_name == ""
    assert p.guardian_phone == ""


@pytest.mark.parametrize(
    "row, expected_error",
    [
        # missing name
        (",Pneumonia,Dr. S,Ward A,A1,2026-01-15,25000,,", "name is required"),
        # bad fee
        ("A,Pneumonia,Dr. S,Ward A,A1,2026-01-15,abc,,", "monthly_fee must be a number"),
        # bad date
        ("A,Pneumonia,Dr. S,Ward A,A1,15-01-2026,25000,,", "admission_date must be YYYY-MM-DD"),
        # unknown bed
        ("A,Pneumonia,Dr. S,Ward A,Z9,2026-01-15,25000,,", "not found"),
    ],
)
def test_invalid_row_is_reported_and_skipped(tmp_path, ward, row, expected_error):
    path = _write_csv(tmp_path, row)
    output = _run(path)
    assert expected_error in output
    assert "Imported 0 patient" in output
    assert Patient.objects.count() == 0


def test_occupied_bed_rejected(tmp_path, ward):
    # First row takes A1; second row targeting A1 must be rejected.
    path = _write_csv(
        tmp_path,
        "First,Dx,Dr. S,Ward A,A1,2026-01-15,25000,,",
        "Second,Dx,Dr. S,Ward A,A1,2026-01-16,25000,,",
    )
    output = _run(path)
    assert "Imported 1 patient" in output
    assert "already occupied" in output
    assert Patient.objects.count() == 1


def test_partial_import_creates_valid_skips_invalid(tmp_path, ward):
    path = _write_csv(
        tmp_path,
        "Good One,Dx,Dr. S,Ward A,A1,2026-01-15,25000,,",
        ",60,Dx,Dr. S,Ward A,A2,2026-01-16,25000,,",  # missing name
        "Good Two,Dx,Dr. S,Ward A,A3,2026-01-17,25000,,",
    )
    output = _run(path)
    assert "Imported 2 patient(s); 1 row(s) skipped" in output
    assert Patient.objects.count() == 2


def test_dry_run_creates_nothing(tmp_path, ward):
    path = _write_csv(
        tmp_path,
        "Jane Doe,Pneumonia,Dr. Smith,Ward A,A1,2026-01-15,25000,,",
    )
    output = _run(path, dry_run=True)
    assert "Would import 1 patient" in output
    assert Patient.objects.count() == 0
    assert Admission.objects.count() == 0
    assert Invoice.objects.count() == 0
