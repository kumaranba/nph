"""Billing logic for monthly admission invoices.

An admission is billed monthly on its "cycle date" — the same day-of-month as
the admission date, clamped to the last day for short months (so a patient
admitted on the 31st is billed on Feb 28/29, Apr 30, etc.). A billing period
runs from one cycle date up to the day before the next.
"""
import calendar
from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum

from .models import (
    AdditionalCharge,
    Admission,
    AdmissionStatus,
    Invoice,
    InvoiceStatus,
)


class BillingService:
    # ------------------------------------------------------------------ dates
    @staticmethod
    def get_billing_cycle_date(admission_date: date, month: int, year: int) -> date:
        """Billing cycle date for ``month``/``year``, anchored on the admission
        day-of-month and clamped to the last day of short months.

        e.g. an admission on the 31st bills on Feb 28 (or Feb 29 in a leap year).
        """
        last_day = calendar.monthrange(year, month)[1]
        return date(year, month, min(admission_date.day, last_day))

    @classmethod
    def next_billing_cycle_date(cls, admission_date: date, as_of: date) -> date:
        """The next billing cycle date on or after ``as_of``.

        If ``as_of`` is itself a cycle date, it is returned (billing is due
        that day). Otherwise the next monthly cycle date is returned.
        """
        candidate = cls.get_billing_cycle_date(admission_date, as_of.month, as_of.year)
        if candidate >= as_of:
            return candidate
        next_year = as_of.year + 1 if as_of.month == 12 else as_of.year
        next_month = 1 if as_of.month == 12 else as_of.month + 1
        return cls.get_billing_cycle_date(admission_date, next_month, next_year)

    @classmethod
    def _period_for(cls, admission_date: date, as_of: date):
        """Return ``(start, end)`` of the billing period containing ``as_of``."""
        start = cls.get_billing_cycle_date(admission_date, as_of.month, as_of.year)
        if start > as_of:
            # Before this month's cycle date — the period started last month.
            year = as_of.year - 1 if as_of.month == 1 else as_of.year
            month = 12 if as_of.month == 1 else as_of.month - 1
            start = cls.get_billing_cycle_date(admission_date, month, year)

        next_year = start.year + 1 if start.month == 12 else start.year
        next_month = 1 if start.month == 12 else start.month + 1
        next_start = cls.get_billing_cycle_date(admission_date, next_month, next_year)
        return start, next_start - timedelta(days=1)

    # --------------------------------------------------------------- invoices
    @classmethod
    @transaction.atomic
    def generate_invoice_for_admission(cls, admission_id, as_of: date = None):
        """Create (or return the existing) invoice for the billing period that
        contains ``as_of``. Idempotent: never duplicates a period's invoice.

        The invoice's line items are the admission's monthly fee plus every
        AdditionalCharge dated within the period; ``total_due`` is their sum.
        """
        as_of = as_of or date.today()
        admission = Admission.objects.select_for_update().get(pk=admission_id)

        # Nothing to bill before the patient is admitted.
        if as_of < admission.admission_date:
            return None

        start, end = cls._period_for(admission.admission_date, as_of)

        existing = Invoice.objects.filter(
            admission=admission,
            billing_period_start=start,
            billing_period_end=end,
        ).first()
        if existing is not None:
            return existing

        charges_total = (
            AdditionalCharge.objects.filter(
                admission=admission,
                charge_date__gte=start,
                charge_date__lte=end,
            ).aggregate(total=Sum("amount"))["total"]
            or Decimal("0")
        )
        base_fee = admission.monthly_fee
        return Invoice.objects.create(
            admission=admission,
            billing_period_start=start,
            billing_period_end=end,
            base_fee=base_fee,
            total_due=base_fee + charges_total,
            status=InvoiceStatus.UNPAID,
        )

    @classmethod
    def generate_all_due_invoices(cls, as_of: date = None):
        """Generate any missing invoices for the current period of every active
        admission. Returns the list of newly created invoices. Idempotent.
        """
        as_of = as_of or date.today()
        created = []
        for admission in Admission.objects.filter(status=AdmissionStatus.ACTIVE):
            if as_of < admission.admission_date:
                continue
            start, end = cls._period_for(admission.admission_date, as_of)
            already = Invoice.objects.filter(
                admission=admission,
                billing_period_start=start,
                billing_period_end=end,
            ).exists()
            if already:
                continue
            invoice = cls.generate_invoice_for_admission(admission.id, as_of=as_of)
            if invoice is not None:
                created.append(invoice)
        return created

    # ---------------------------------------------------------------- status
    @staticmethod
    def amount_paid(invoice: Invoice) -> Decimal:
        return invoice.payments.aggregate(total=Sum("amount"))["total"] or Decimal("0")

    @classmethod
    def recompute_status(cls, invoice: Invoice) -> Invoice:
        """Recompute and persist an invoice's status from payments + refunds."""
        settled = cls.amount_paid(invoice) + (invoice.refund_amount or Decimal("0"))
        if settled <= 0:
            invoice.status = InvoiceStatus.UNPAID
        elif settled < invoice.total_due:
            invoice.status = InvoiceStatus.PARTIAL
        else:
            invoice.status = InvoiceStatus.PAID
        invoice.save(update_fields=["status"])
        return invoice
