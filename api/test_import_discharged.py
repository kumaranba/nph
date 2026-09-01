"""Tests for the import_discharged management command (past-discharge list →
discharged admissions, for PRO follow-up).

Covers record creation, dry-run, re-admission safety, idempotency, phone-first
matching with a name fallback, ambiguous-match skipping, and row validation.
"""
from datetime import date
from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import call_command

from api.models import (
    Admission, AdmissionStatus, Bed, BedStatus, Patient, Room,
)

HEADER = "Patient Name,D.O.A,D.O.D,FEES,CONTACT,PLACE"


def _write(tmp_path, *rows, name="discharges.csv"):
    path = tmp_path / name
    path.write_text(HEADER + "\n" + "\n".join(rows) + "\n")
    return str(path)


def _run(path, **kwargs):
    out = StringIO()
    call_command("import_discharged", path, stdout=out, **kwargs)
    return out.getvalue()


# --- basic import ---------------------------------------------------------

def test_creates_patient_and_discharged_admission(tmp_path, db):
    path = _write(tmp_path, "Ravi Kumar,15/01/2026,10/02/2026,9500,9876543210,Trichy")
    _run(path)
    p = Patient.objects.get(name="Ravi Kumar")
    assert p.place == "Trichy"
    assert p.guardian_phone == "9876543210"
    adm = Admission.objects.get(patient=p)
    assert adm.status == AdmissionStatus.DISCHARGED
    assert adm.admission_date == date(2026, 1, 15)
    assert adm.discharge_date == date(2026, 2, 10)
    assert adm.monthly_fee == Decimal("9500")
    assert adm.bed is None                       # follow-up record, no bed


def test_blank_and_nil_fees_default_zero(tmp_path, db):
    path = _write(
        tmp_path,
        "A,01/01/2026,02/01/2026,,900,X",
        "B,01/01/2026,02/01/2026,NIL,901,Y",
        "C,01/01/2026,02/01/2026,\"12,500\",902,Z",
    )
    _run(path)
    assert Admission.objects.get(patient__name="A").monthly_fee == Decimal("0")
    assert Admission.objects.get(patient__name="B").monthly_fee == Decimal("0")
    assert Admission.objects.get(patient__name="C").monthly_fee == Decimal("12500")


# --- dry run --------------------------------------------------------------

def test_dry_run_writes_nothing(tmp_path, db):
    path = _write(tmp_path, "Ravi,15/01/2026,10/02/2026,9500,9876543210,Trichy")
    out = _run(path, dry_run=True)
    assert Patient.objects.count() == 0
    assert Admission.objects.count() == 0
    assert "Would create" in out


# --- re-admission safety --------------------------------------------------

def test_matches_existing_patient_and_leaves_active_admission_untouched(tmp_path, db):
    # An existing, currently-admitted patient (re-admitted since the discharge).
    room = Room.objects.create(name="MW1", capacity=1)
    bed = Bed.objects.create(room=room, label="B1", status=BedStatus.OCCUPIED)
    p = Patient.objects.create(
        name="Ravi", guardian_phone="9876543210",
        diagnosis="d", admitting_doctor="Dr",
    )
    active = Admission.objects.create(
        patient=p, bed=bed, admission_date=date(2026, 8, 20),
        monthly_fee=Decimal("10000"), status=AdmissionStatus.ACTIVE,
    )
    # Import a historical discharge for the same phone.
    path = _write(tmp_path, "Ravi K,15/01/2026,10/02/2026,9500,9876543210,Trichy")
    _run(path)

    assert Patient.objects.count() == 1          # matched, not duplicated
    active.refresh_from_db()
    assert active.status == AdmissionStatus.ACTIVE
    assert active.bed_id == bed.id               # active stay untouched
    hist = Admission.objects.get(patient=p, status=AdmissionStatus.DISCHARGED)
    assert hist.discharge_date == date(2026, 2, 10)


def test_idempotent_rerun_does_not_duplicate(tmp_path, db):
    path = _write(tmp_path, "Ravi,15/01/2026,10/02/2026,9500,9876543210,Trichy")
    _run(path)
    _run(path)
    assert Patient.objects.count() == 1
    assert Admission.objects.filter(status=AdmissionStatus.DISCHARGED).count() == 1


def test_same_person_readmitted_within_file(tmp_path, db):
    # Discharged, re-admitted, discharged again — two stays, one patient.
    path = _write(
        tmp_path,
        "Ravi,15/01/2026,10/02/2026,9500,9876543210,Trichy",
        "Ravi,01/05/2026,20/05/2026,9500,9876543210,Trichy",
    )
    _run(path)
    assert Patient.objects.count() == 1
    assert Admission.objects.filter(status=AdmissionStatus.DISCHARGED).count() == 2


# --- matching -------------------------------------------------------------

def test_phone_match_ignores_formatting(tmp_path, db):
    Patient.objects.create(
        name="Ravi", guardian_phone="+91 98765 43210",
        diagnosis="d", admitting_doctor="Dr",
    )
    path = _write(tmp_path, "Ravi K,15/01/2026,10/02/2026,9500,9876543210,X")
    _run(path)
    assert Patient.objects.count() == 1          # matched despite +91/spacing


def test_name_fallback_when_no_phone(tmp_path, db):
    Patient.objects.create(name="Meena Devi", diagnosis="d", admitting_doctor="Dr")
    path = _write(tmp_path, "meena devi,15/01/2026,10/02/2026,9500,,X")
    _run(path)
    assert Patient.objects.count() == 1


def test_ambiguous_name_is_skipped(tmp_path, db):
    Patient.objects.create(name="Kumar", diagnosis="d", admitting_doctor="Dr")
    Patient.objects.create(name="Kumar", diagnosis="d", admitting_doctor="Dr")
    path = _write(tmp_path, "Kumar,15/01/2026,10/02/2026,9500,,X")
    out = _run(path)
    assert Admission.objects.filter(status=AdmissionStatus.DISCHARGED).count() == 0
    assert "ambiguous" in out.lower()


# --- validation -----------------------------------------------------------

def test_bad_rows_are_skipped(tmp_path, db):
    path = _write(
        tmp_path,
        ",15/01/2026,10/02/2026,9500,9,X",           # no name
        "NoDates,,,,9,X",                             # missing dates
        "Backwards,10/02/2026,15/01/2026,9500,9,X",   # D.O.D before D.O.A
        "Good,15/01/2026,10/02/2026,9500,9000000000,X",
    )
    out = _run(path)
    assert Patient.objects.count() == 1
    assert Patient.objects.get().name == "Good"
    assert "skipped on error" in out
