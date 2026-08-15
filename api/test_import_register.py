"""Tests for the import_register management command (register CSV → patients).

Covers the Gender column, the Ward column with auto-created wards and
auto-generated beds (capped at 20/ward), and the warnings the importer emits
for blank/over-capacity wards, gender/ward mismatches, and bad gender values.
"""
from datetime import date
from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import call_command

from api.billing import BillingService
from api.models import (
    Admission,
    AdmissionStatus,
    Bed,
    BedStatus,
    Gender,
    Invoice,
    Patient,
    Room,
)

# Register export header (subset of columns the importer reads).
HEADER = "S.No,Name,Gender,D.O.A,Fees,Ward,Contact"

# Header including the "Fees Status" (opening balance) column.
HEADER_OB = "S.No,Name,Gender,D.O.A,Fees,Fees Status,Ward,Contact"


def _write_csv(tmp_path, *rows):
    path = tmp_path / "register.csv"
    path.write_text(HEADER + "\n" + "\n".join(rows) + "\n")
    return str(path)


def _write_csv_ob(tmp_path, *rows):
    path = tmp_path / "register_ob.csv"
    path.write_text(HEADER_OB + "\n" + "\n".join(rows) + "\n")
    return str(path)


def _run(path, **kwargs):
    out = StringIO()
    call_command("import_register", path, stdout=out, **kwargs)
    return out.getvalue()


def test_place_column_is_imported(tmp_path, db):
    header = "S.No,Name,Gender,D.O.A,Fees,Ward,Contact,Place"
    path = tmp_path / "with_place.csv"
    path.write_text(header + "\n1,Ravi,M,15-01-2026,9500,MW1,999,Trichy\n")
    _run(str(path))
    assert Patient.objects.get(name="Ravi").place == "Trichy"


def test_valid_row_creates_patient_admission_invoice_and_bed(tmp_path, db):
    path = _write_csv(
        tmp_path,
        "1,Jane Doe,F,15-01-2026,25000,FW1,98765",
    )
    output = _run(path)

    assert "Imported 1 patient" in output
    patient = Patient.objects.get(name="Jane Doe")
    assert patient.gender == Gender.FEMALE
    admission = Admission.objects.get(patient=patient)
    assert admission.status == AdmissionStatus.ACTIVE
    assert admission.monthly_fee == Decimal("25000")

    # Ward auto-created; bed auto-generated as B1 and flipped to OCCUPIED.
    room = Room.objects.get(name="FW1")
    assert admission.bed.room == room
    assert admission.bed.label == "B1"
    assert admission.bed.status == BedStatus.OCCUPIED
    # No "Fees Status" column here → zero opening balance → no invoice seeded.
    assert admission.opening_balance == Decimal("0")
    assert Invoice.objects.filter(admission=admission).count() == 0


def test_register_slash_date_with_two_digit_year(tmp_path, db):
    # The real register export is day-first with a 2-digit year (30/08/25).
    path = _write_csv(
        tmp_path,
        "1,Prabakaran,M,30/08/23,15500,MW3,",
    )
    output = _run(path)
    assert "Imported 1 patient" in output
    admission = Admission.objects.get(patient__name="Prabakaran")
    assert admission.admission_date.isoformat() == "2023-08-30"


def test_beds_auto_number_within_a_ward(tmp_path, db):
    path = _write_csv(
        tmp_path,
        "1,Amma,F,15-01-2026,25000,FW1,",
        "2,Beena,F,16-01-2026,25000,FW1,",
        "3,Chitra,F,17-01-2026,25000,FW1,",
    )
    _run(path)
    labels = sorted(Bed.objects.filter(room__name="FW1").values_list("label", flat=True))
    assert labels == ["B1", "B2", "B3"]
    assert Bed.objects.filter(room__name="FW1", status=BedStatus.OCCUPIED).count() == 3


def test_full_name_gender_values_are_accepted(tmp_path, db):
    path = _write_csv(
        tmp_path,
        "1,Ravi,Male,15-01-2026,25000,MW1,",
    )
    _run(path)
    assert Patient.objects.get(name="Ravi").gender == Gender.MALE


def test_ward_bed_cap_of_20_imports_bedless_with_warning(tmp_path, db):
    # Pre-fill FW1 to the cap so the imported patient can't get a bed.
    room = Room.objects.create(name="FW1", capacity=20)
    for i in range(1, 21):
        Bed.objects.create(room=room, label=f"B{i}", status=BedStatus.OCCUPIED)

    path = _write_csv(
        tmp_path,
        "1,Latecomer,F,15-01-2026,25000,FW1,",
    )
    output = _run(path)

    assert "Imported 1 patient" in output
    assert "full" in output
    admission = Admission.objects.get(patient__name="Latecomer")
    assert admission.bed is None
    # No 21st bed created.
    assert Bed.objects.filter(room=room).count() == 20


def test_blank_ward_imports_bedless(tmp_path, db):
    path = _write_csv(
        tmp_path,
        "1,No Ward,F,15-01-2026,25000,,",
    )
    output = _run(path)
    assert "Imported 1 patient" in output
    admission = Admission.objects.get(patient__name="No Ward")
    assert admission.bed is None


def test_gender_ward_mismatch_warns_but_imports(tmp_path, db):
    # Male patient placed in a female ward (FW) → warn, still import.
    path = _write_csv(
        tmp_path,
        "1,Mismatch,M,15-01-2026,25000,FW1,",
    )
    output = _run(path)
    assert "Imported 1 patient" in output
    assert "female ward" in output
    admission = Admission.objects.get(patient__name="Mismatch")
    assert admission.bed.room.name == "FW1"


def test_unrecognized_gender_warns_and_leaves_blank(tmp_path, db):
    path = _write_csv(
        tmp_path,
        "1,Odd,X,15-01-2026,25000,MW1,",
    )
    output = _run(path)
    assert "Imported 1 patient" in output
    assert "unrecognized Gender" in output
    assert Patient.objects.get(name="Odd").gender == ""


@pytest.mark.parametrize(
    "row, expected_error",
    [
        ("1,,F,15-01-2026,25000,FW1,", "Name is required"),
        ("1,Bad Date,F,2026/01/15,25000,FW1,", "must be a day-first date"),
        ("1,Bad Fee,F,15-01-2026,abc,FW1,", "not a valid number"),
    ],
)
def test_invalid_rows_are_skipped(tmp_path, db, row, expected_error):
    path = _write_csv(tmp_path, row)
    output = _run(path)
    assert expected_error in output
    assert Patient.objects.count() == 0


def test_dry_run_creates_nothing(tmp_path, db):
    path = _write_csv(
        tmp_path,
        "1,Jane Doe,F,15-01-2026,25000,FW1,98765",
    )
    output = _run(path, dry_run=True)
    assert "Would import 1 patient" in output
    assert Patient.objects.count() == 0
    assert Admission.objects.count() == 0
    assert Room.objects.count() == 0


# --- Opening balance (Fees Status column) ----------------------------------

def test_opening_balance_seeds_carried_invoice_only(tmp_path, db):
    # Manikandan-style: monthly 9500, current outstanding 13500, admitted long
    # ago. Import captures the outstanding as an opening balance and seeds ONE
    # carried-forward invoice — no current-cycle invoice (would double-count).
    path = _write_csv_ob(
        tmp_path,
        "1,Manikandan,M,03/03/25,9500,13500,MW1,",
    )
    _run(path, as_of="2026-08-12")

    admission = Admission.objects.get(patient__name="Manikandan")
    assert admission.opening_balance == Decimal("13500")
    assert admission.opening_balance_as_of.isoformat() == "2026-08-12"

    invoices = Invoice.objects.filter(admission=admission)
    assert invoices.count() == 1
    opening = invoices.get()
    assert opening.is_opening_balance is True
    assert opening.total_due == Decimal("13500")
    assert opening.base_fee == Decimal("0")
    # Sentinel period is the day before admission, so it sorts oldest.
    assert opening.billing_period_start.isoformat() == "2025-03-02"


def test_nil_status_seeds_no_opening_balance(tmp_path, db):
    path = _write_csv_ob(
        tmp_path,
        "1,PaidUp,M,03/03/25,9500,NIL,MW1,",
    )
    _run(path, as_of="2026-08-12")
    admission = Admission.objects.get(patient__name="PaidUp")
    assert admission.opening_balance == Decimal("0")
    assert Invoice.objects.filter(admission=admission).count() == 0
    # Invariant: an ACTIVE admission always has exactly one active Fee, even a
    # paid-up (NIL) patient with no invoice.
    assert admission.fees.filter(is_active=True).count() == 1


def test_forward_billing_resumes_next_cycle_without_double_count(tmp_path, db):
    # After import, the current (covered) monthly period must NOT be billed
    # again; the next cycle bills normally and stacks on the opening balance.
    path = _write_csv_ob(
        tmp_path,
        "1,Manikandan,M,03/03/25,9500,13500,MW1,",
    )
    _run(path, as_of="2026-08-12")
    admission = Admission.objects.get(patient__name="Manikandan")

    # Current period (03 Aug–02 Sep) is covered by the opening balance.
    BillingService.generate_all_due_invoices(as_of=date(2026, 8, 12))
    assert Invoice.objects.filter(admission=admission).count() == 1  # still just opening

    # Next cycle on 03 Sep generates a normal 9500 invoice → outstanding 23000.
    BillingService.generate_invoice_for_admission(admission.id, as_of=date(2026, 9, 3))
    outstanding = sum(
        BillingService.balance_due(inv)
        for inv in Invoice.objects.filter(admission=admission)
    )
    assert outstanding == Decimal("23000")


def test_payment_clears_opening_balance_first(tmp_path, db):
    from api.models import User, UserRole

    user = User.objects.create_user(
        email="fin@nph.test", password="secret123", role=UserRole.FINANCE
    )
    path = _write_csv_ob(
        tmp_path,
        "1,Manikandan,M,03/03/25,9500,13500,MW1,",
    )
    _run(path, as_of="2026-08-12")
    admission = Admission.objects.get(patient__name="Manikandan")

    # A 4000 payment lands on the oldest debt: the opening balance.
    BillingService.record_payment_for_admission(
        admission, Decimal("4000"), Decimal("0"), date(2026, 8, 12), user
    )
    opening = Invoice.objects.get(admission=admission, is_opening_balance=True)
    assert BillingService.balance_due(opening) == Decimal("9500")
