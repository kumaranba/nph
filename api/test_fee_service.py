"""Tests for FeeService — every rule in the CLAUDE.md Fee invariant."""
import threading
from datetime import date
from decimal import Decimal

import pytest

from api.billing import BillingService
from api.fees import FeeError, FeeService
from api.models import (
    Admission,
    AdmissionStatus,
    Bed,
    BedStatus,
    Fee,
    Patient,
    Room,
    User,
    UserRole,
)


@pytest.fixture
def finance(db):
    return User.objects.create_user(
        email="fin@fee.test", password="secret123", role=UserRole.FINANCE
    )


def _make_admission(admission_date=date(2026, 1, 15), fee=Decimal("15000.00")):
    room = Room.objects.create(name="Ward", capacity=2)
    bed = Bed.objects.create(room=room, label="A1", status=BedStatus.OCCUPIED)
    patient = Patient.objects.create(
        name="Jane Doe", diagnosis="dx", admitting_doctor="Dr. X"
    )
    admission = Admission.objects.create(
        patient=patient, bed=bed, admission_date=admission_date,
        monthly_fee=fee, status=AdmissionStatus.ACTIVE,
    )
    Fee.objects.create(
        admission=admission, amount=fee, effective_from=admission_date,
        is_active=True, reason="Initial fee",
    )
    return admission


@pytest.fixture
def admission(db):
    return _make_admission()


# ---------------------------------------------------- effective_from + override
def test_default_effective_from_is_next_uninvoiced_cycle(admission, finance):
    BillingService.generate_invoice_for_admission(admission.id, as_of=date(2026, 1, 15))
    fee = FeeService.change_fee(admission.id, Decimal("18000"), "raise", finance)
    # Jan invoice exists (Jan 15 - Feb 14) -> default is the next cycle, Feb 15.
    assert fee.effective_from == date(2026, 2, 15)
    assert fee.is_active is True


def test_explicit_effective_from_differing_without_override_is_rejected(admission, finance):
    BillingService.generate_invoice_for_admission(admission.id, as_of=date(2026, 1, 15))
    with pytest.raises(FeeError, match="override"):
        FeeService.change_fee(
            admission.id, Decimal("18000"), "r", finance,
            effective_from=date(2026, 3, 1), override=False,
        )


def test_explicit_effective_from_equal_to_default_is_allowed(admission, finance):
    BillingService.generate_invoice_for_admission(admission.id, as_of=date(2026, 1, 15))
    fee = FeeService.change_fee(
        admission.id, Decimal("18000"), "r", finance,
        effective_from=date(2026, 2, 15), override=False,
    )
    assert fee.effective_from == date(2026, 2, 15)


def test_override_allows_explicit_effective_from(admission, finance):
    BillingService.generate_invoice_for_admission(admission.id, as_of=date(2026, 1, 15))
    fee = FeeService.change_fee(
        admission.id, Decimal("18000"), "r", finance,
        effective_from=date(2026, 3, 1), override=True,
    )
    assert fee.effective_from == date(2026, 3, 1)


# --------------------------------------------------------------------- rules
def test_change_fee_on_discharged_admission_is_rejected(admission, finance):
    admission.status = AdmissionStatus.DISCHARGED
    admission.save(update_fields=["status"])
    with pytest.raises(FeeError, match="discharged"):
        FeeService.change_fee(admission.id, Decimal("18000"), "r", finance)


def test_only_one_active_fee_after_multiple_changes(admission, finance):
    for amt in ("16000", "17000", "18000", "19000"):
        FeeService.change_fee(admission.id, Decimal(amt), "r", finance)
    assert admission.fees.filter(is_active=True).count() == 1
    # The active fee is the latest amount.
    assert admission.active_fee.amount == Decimal("19000.00")


def test_old_fees_are_deactivated_not_deleted(admission, finance):
    before = admission.fees.count()  # 1 initial
    FeeService.change_fee(admission.id, Decimal("16000"), "r", finance)
    FeeService.change_fee(admission.id, Decimal("17000"), "r", finance)
    # Two changes add two fees; none removed.
    assert admission.fees.count() == before + 2
    inactive = admission.fees.filter(is_active=False)
    assert inactive.count() == before + 1
    assert all(f.deactivated_at is not None for f in inactive)


def test_finance_only(admission, db):
    admin = User.objects.create_user(
        email="adm@fee.test", password="x", role=UserRole.ADMIN
    )
    with pytest.raises(FeeError, match="Finance"):
        FeeService.change_fee(admission.id, Decimal("18000"), "r", admin)


def test_amount_must_be_positive(admission, finance):
    with pytest.raises(FeeError, match="positive"):
        FeeService.change_fee(admission.id, Decimal("0"), "r", finance)


def test_discharge_deactivates_active_fee(admission, finance):
    assert admission.active_fee is not None
    FeeService.deactivate_fee_on_discharge(admission.id)
    admission.refresh_from_db()
    assert admission.active_fee is None
    assert admission.fees.filter(is_active=False).count() == 1


def test_readmission_has_independent_fee_history(db, finance):
    first = _make_admission()
    FeeService.change_fee(first.id, Decimal("16000"), "r", finance)
    FeeService.deactivate_fee_on_discharge(first.id)
    first.status = AdmissionStatus.DISCHARGED
    first.save(update_fields=["status"])

    # Same patient re-admitted -> brand new Admission with its own fee.
    second = Admission.objects.create(
        patient=first.patient, bed=first.bed, admission_date=date(2026, 6, 1),
        monthly_fee=Decimal("20000"), status=AdmissionStatus.ACTIVE,
    )
    Fee.objects.create(
        admission=second, amount=Decimal("20000"), effective_from=date(2026, 6, 1),
        is_active=True, reason="Initial fee",
    )
    # Second admission has exactly one active fee, unrelated to the first's fees.
    assert second.fees.filter(is_active=True).count() == 1
    assert second.active_fee.amount == Decimal("20000.00")
    assert first.fees.filter(is_active=True).count() == 0


def test_fee_history_across_admissions_newest_first(db, finance):
    adm = _make_admission()
    FeeService.change_fee(adm.id, Decimal("16000"), "r", finance)
    history = list(FeeService.get_fee_history(adm.patient_id))
    # Newest first: the 16000 change, then the initial 15000.
    assert history[0].amount == Decimal("16000.00")
    assert history[-1].amount == Decimal("15000.00")


# ------------------------------------------------------------- race condition
@pytest.mark.django_db(transaction=True)
def test_concurrent_change_fee_cannot_create_two_active_fees():
    admission = _make_admission()
    finance = User.objects.create_user(
        email="fin-race@fee.test", password="x", role=UserRole.FINANCE
    )
    barrier = threading.Barrier(2)
    errors = []

    def worker(amount):
        from django.db import connection
        try:
            barrier.wait(timeout=5)
            FeeService.change_fee(admission.id, Decimal(amount), "concurrent", finance)
        except Exception as exc:  # noqa: BLE001 — recorded for assertion
            errors.append(exc)
        finally:
            connection.close()

    t1 = threading.Thread(target=worker, args=("21000",))
    t2 = threading.Thread(target=worker, args=("22000",))
    t1.start(); t2.start(); t1.join(); t2.join()

    # The row lock serializes them, so the invariant holds: exactly one active
    # fee, never two.
    assert admission.fees.filter(is_active=True).count() == 1
    # Clean up the transaction=True rows.
    Fee.objects.filter(admission=admission).delete()
    admission.delete()
    admission.patient.delete()
    admission.bed.delete()
    admission.bed.room.delete()
    finance.delete()
