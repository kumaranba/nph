"""Billing logic for monthly admission invoices.

An admission is billed monthly on its "cycle date" — the same day-of-month as
the admission date, clamped to the last day for short months (so a patient
admitted on the 31st is billed on Feb 28/29, Apr 30, etc.). A billing period
runs from one cycle date up to the day before the next.
"""
import calendar
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.db.models import Sum

from .models import (
    AdditionalCharge,
    Admission,
    AdmissionStatus,
    Invoice,
    InvoiceStatus,
)

_CENT = Decimal("0.01")


def _money(value) -> Decimal:
    return Decimal(value).quantize(_CENT, rounding=ROUND_HALF_UP)


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

    @staticmethod
    def _ensure_active_fee(admission):
        """Return the admission's active Fee, creating an initial one from
        ``monthly_fee`` if the admission has none yet (system-owned)."""
        from .models import Fee

        fee = admission.fees.filter(is_active=True).first()
        if fee is None:
            fee = Fee.objects.create(
                admission=admission,
                amount=admission.monthly_fee,
                effective_from=admission.admission_date,
                is_active=True,
                reason="Initial fee",
                created_by=None,
            )
        return fee

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

        # For imported admissions, every period up to and including the one that
        # was in progress when the opening balance was captured is already
        # covered by that opening balance. Billing resumes at the first period
        # starting AFTER the capture date, so we never bill a covered period
        # twice.
        if (
            admission.opening_balance_as_of is not None
            and start <= admission.opening_balance_as_of
        ):
            return None

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
        # Snapshot the admission's active fee onto the invoice. If none exists
        # yet (e.g. a legacy admission), create the initial fee from monthly_fee.
        fee = cls._ensure_active_fee(admission)
        base_fee = fee.amount
        invoice = Invoice.objects.create(
            admission=admission,
            fee=fee,
            billing_period_start=start,
            billing_period_end=end,
            base_fee=base_fee,
            total_due=base_fee + charges_total,
            status=InvoiceStatus.UNPAID,
        )
        # Draw down any advance credit against the fresh invoice.
        cls.apply_credit(admission)
        invoice.refresh_from_db()
        return invoice

    @classmethod
    @transaction.atomic
    def create_opening_balance_invoice(cls, admission_id, amount, as_of: date = None):
        """Seed a carried-forward opening balance for an imported admission.

        Creates a single ``is_opening_balance`` invoice for ``amount`` with a
        sentinel period (the day before admission) so it sorts oldest and never
        collides with a real monthly period. Idempotent: returns the existing
        opening-balance invoice if one is already present. ``amount`` <= 0 is a
        no-op.
        """
        from .models import Fee  # noqa: F401  (kept parallel to _ensure_active_fee)

        amount = Decimal(amount)
        admission = Admission.objects.select_for_update().get(pk=admission_id)

        existing = admission.invoices.filter(is_opening_balance=True).first()
        if existing is not None:
            return existing
        if amount <= 0:
            return None

        fee = cls._ensure_active_fee(admission)
        sentinel = admission.admission_date - timedelta(days=1)
        invoice = Invoice.objects.create(
            admission=admission,
            fee=fee,
            billing_period_start=sentinel,
            billing_period_end=sentinel,
            base_fee=Decimal("0"),
            total_due=amount,
            status=InvoiceStatus.UNPAID,
            is_opening_balance=True,
        )
        # Draw down any advance credit against it (none at import time, but keep
        # the invariant that credit is applied whenever a new invoice appears).
        cls.apply_credit(admission)
        invoice.refresh_from_db()
        return invoice

    @classmethod
    def generate_all_due_for_admission(cls, admission_id, as_of: date = None):
        """Generate invoices for **every** billing period of one admission from
        its admission date through ``as_of`` (default today), not just the
        current one. Used when an admission is created (possibly back-dated) so
        all periods already due are billed immediately. Idempotent.

        Returns the list of invoices created.
        """
        as_of = as_of or date.today()
        admission = Admission.objects.get(pk=admission_id)
        if as_of < admission.admission_date:
            return []

        created = []
        # Walk each cycle start from the admission date up to as_of.
        cursor = admission.admission_date
        while cursor <= as_of:
            start, end = cls._period_for(admission.admission_date, cursor)
            already = Invoice.objects.filter(
                admission=admission,
                billing_period_start=start,
                billing_period_end=end,
            ).exists()
            if not already:
                invoice = cls.generate_invoice_for_admission(admission_id, as_of=cursor)
                if invoice is not None:
                    created.append(invoice)
            cursor = cls.next_billing_cycle_date(
                admission.admission_date, cursor + timedelta(days=1)
            )
        return created

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

    @classmethod
    def balance_due(cls, invoice: Invoice) -> Decimal:
        return (
            invoice.total_due
            - (invoice.refund_amount or Decimal("0"))
            - cls.amount_paid(invoice)
        )

    # -------------------------------------------------------- additional charges
    @classmethod
    def recompute_invoice_total(cls, invoice: Invoice) -> Invoice:
        """Recompute an invoice's ``total_due`` from its fee plus the charges in
        its period, then its status. Used when a charge is added/removed after
        the invoice already exists. The opening-balance invoice is fixed and is
        never recomputed."""
        if invoice.is_opening_balance:
            return invoice
        charges = (
            AdditionalCharge.objects.filter(
                admission=invoice.admission,
                charge_date__gte=invoice.billing_period_start,
                charge_date__lte=invoice.billing_period_end,
            ).aggregate(total=Sum("amount"))["total"]
            or Decimal("0")
        )
        invoice.total_due = invoice.base_fee + charges
        invoice.save(update_fields=["total_due"])
        cls.recompute_status(invoice)
        return invoice

    @classmethod
    @transaction.atomic
    def bill_charge(cls, charge) -> Invoice:
        """Ensure ``charge`` is reflected on an invoice, immediately.

        - A billable monthly period: top up (or generate) that period's invoice.
        - A period already covered by the opening balance (imported patients):
          bill it on a charges-only ``is_settlement`` invoice for that period.

        Idempotent — safe to re-run for the same charge (recompute is a no-op if
        nothing changed).
        """
        admission = charge.admission
        start, end = cls._period_for(admission.admission_date, charge.charge_date)
        covered = (
            admission.opening_balance_as_of is not None
            and start <= admission.opening_balance_as_of
        )

        if not covered:
            invoice = admission.invoices.filter(
                billing_period_start=start, billing_period_end=end,
                is_settlement=False,
            ).first()
            if invoice is not None:
                return cls.recompute_invoice_total(invoice)
            # No invoice yet for this (billable) period — generate it; the new
            # invoice's total already includes this charge.
            return cls.generate_invoice_for_admission(
                admission.id, as_of=charge.charge_date
            )

        # Covered period: charges-only settlement invoice for that period.
        settlement = admission.invoices.filter(
            billing_period_start=start, billing_period_end=end,
            is_settlement=True,
        ).first()
        if settlement is not None:
            return cls.recompute_invoice_total(settlement)

        fee = cls._ensure_active_fee(admission)
        charges = (
            AdditionalCharge.objects.filter(
                admission=admission,
                charge_date__gte=start, charge_date__lte=end,
            ).aggregate(total=Sum("amount"))["total"]
            or Decimal("0")
        )
        settlement = Invoice.objects.create(
            admission=admission,
            fee=fee,
            billing_period_start=start,
            billing_period_end=end,
            base_fee=Decimal("0"),
            total_due=charges,
            status=InvoiceStatus.UNPAID,
            is_settlement=True,
        )
        cls.apply_credit(admission)
        settlement.refresh_from_db()
        return settlement

    @classmethod
    def sweep_unbilled_charges(cls, admission) -> None:
        """Ensure every one of the admission's additional charges is reflected
        on an invoice. Idempotent; used at discharge as a safety net."""
        charges = AdditionalCharge.objects.filter(admission=admission)
        for charge in charges:
            cls.bill_charge(charge)

    # ------------------------------------------------------ pending-dues report
    @classmethod
    def total_pending_dues(cls, admission) -> Decimal:
        """The admission's full current outstanding: the sum of the balance due
        across every unpaid/partial invoice (opening balance, overdue months,
        and the current cycle alike)."""
        total = Decimal("0")
        for inv in admission.invoices.filter(
            status__in=[InvoiceStatus.UNPAID, InvoiceStatus.PARTIAL]
        ).prefetch_related("payments"):
            total += cls.balance_due(inv)
        return total

    @classmethod
    def current_cycle_charge(cls, admission, as_of: date = None) -> Decimal:
        """The charge for the billing cycle in progress on ``as_of``: the
        monthly fee plus any additional charges dated within that period."""
        as_of = as_of or date.today()
        start, end = cls._period_for(admission.admission_date, as_of)
        charges = (
            AdditionalCharge.objects.filter(
                admission=admission,
                charge_date__gte=start,
                charge_date__lte=end,
            ).aggregate(total=Sum("amount"))["total"]
            or Decimal("0")
        )
        return admission.monthly_fee + charges

    # -------------------------------------------------------- credit + payments
    @classmethod
    def apply_credit(cls, admission):
        """Draw down the admission's credit balance against its unpaid invoices,
        oldest-first. Credit-funded payments have no recorder. Returns the list
        of ``(invoice, amount_applied)`` allocations made."""
        from .models import Payment

        allocations = []
        credit = admission.credit_balance or Decimal("0")
        if credit <= 0:
            return allocations

        unpaid = admission.invoices.filter(
            status__in=[InvoiceStatus.UNPAID, InvoiceStatus.PARTIAL]
        ).order_by("billing_period_start")
        for invoice in unpaid:
            if credit <= 0:
                break
            due = cls.balance_due(invoice)
            if due <= 0:
                continue
            applied = min(credit, due)
            Payment.objects.create(
                invoice=invoice,
                amount=applied,
                paid_on=date.today(),
                recorded_by=None,  # applied from advance credit
            )
            cls.recompute_status(invoice)
            credit -= applied
            allocations.append((invoice, applied))

        if allocations:
            admission.credit_balance = credit
            admission.save(update_fields=["credit_balance"])
        return allocations

    @classmethod
    @transaction.atomic
    def record_payment_for_admission(
        cls, admission, fees_amount, charges_amount, paid_on, recorded_by,
        account=None,
    ):
        """Record a payment for an admission. Clears outstanding invoices
        oldest-first; any surplus is held as advance credit on the admission
        (applied automatically as future monthly invoices come due).

        ``fees_amount`` + ``charges_amount`` is the total paid; the split and
        the receiving ``account`` are captured on a PaymentReceipt for the
        receipt/bill (informational — allocation is on the combined total).

        Returns ``(receipt, allocations, credit_added)`` where each allocation
        is ``(invoice, amount_applied)``.
        """
        from .models import Payment, PaymentReceipt

        fees_amount = Decimal(fees_amount)
        charges_amount = Decimal(charges_amount)
        total = fees_amount + charges_amount

        receipt = PaymentReceipt.objects.create(
            admission=admission,
            paid_on=paid_on,
            amount=total,
            fees_amount=fees_amount,
            charges_amount=charges_amount,
            account=account,
            recorded_by=recorded_by,
        )

        remaining = total
        allocations = []

        outstanding = admission.invoices.filter(
            status__in=[InvoiceStatus.UNPAID, InvoiceStatus.PARTIAL]
        ).order_by("billing_period_start")
        for invoice in outstanding:
            if remaining <= 0:
                break
            due = cls.balance_due(invoice)
            if due <= 0:
                continue
            applied = min(remaining, due)
            Payment.objects.create(
                invoice=invoice,
                amount=applied,
                paid_on=paid_on,
                recorded_by=recorded_by,
                receipt=receipt,
            )
            cls.recompute_status(invoice)
            remaining -= applied
            allocations.append((invoice, applied))

        credit_added = remaining
        if credit_added > 0:
            admission.credit_balance = (admission.credit_balance or Decimal("0")) + credit_added
            admission.save(update_fields=["credit_balance"])

        return receipt, allocations, credit_added

    # --------------------------------------------------- discharge pro-ration
    @classmethod
    def current_cycle_invoice(cls, admission, on_date: date):
        """The monthly invoice for the billing period containing ``on_date``
        (excludes opening-balance and settlement invoices). None if not billed
        yet."""
        start, end = cls._period_for(admission.admission_date, on_date)
        return admission.invoices.filter(
            billing_period_start=start, billing_period_end=end,
            is_opening_balance=False, is_settlement=False,
        ).first()

    @staticmethod
    def prorate(full_fee: Decimal, period_start: date, period_end: date,
                discharge_date: date):
        """Pro-rate ``full_fee`` for a stay ending on ``discharge_date`` within
        a billing period. The stay is counted from the period start through the
        discharge day, **both inclusive**. Returns
        ``(days_in_period, days_stayed, prorated_fee, cancelled)``."""
        days_in_period = (period_end - period_start).days + 1
        days_stayed = (discharge_date - period_start).days + 1     # inclusive
        days_stayed = max(0, min(days_stayed, days_in_period))
        prorated = _money(Decimal(full_fee) * days_stayed / days_in_period)
        return days_in_period, days_stayed, prorated, _money(Decimal(full_fee) - prorated)

    @classmethod
    def _period_charges(cls, admission, start, end) -> Decimal:
        return (
            AdditionalCharge.objects.filter(
                admission=admission, charge_date__gte=start, charge_date__lte=end,
            ).aggregate(total=Sum("amount"))["total"]
            or Decimal("0")
        )

    @classmethod
    @transaction.atomic
    def apply_discharge_proration(cls, admission, discharge_date: date) -> Decimal:
        """Reduce the in-progress cycle's invoice to the days actually stayed.

        Generates the current-period invoice first if Celery hasn't yet, then
        rewrites its fee line to the pro-rated amount (charges are untouched).
        Only an invoice that already exists for the in-progress cycle is
        adjusted — if billing hasn't raised one yet, there is nothing to
        pro-rate. Idempotent: the pro-ration is computed from the immutable fee
        snapshot, so re-running yields the same result. Returns the cancelled
        amount.
        """
        inv = cls.current_cycle_invoice(admission, discharge_date)
        if inv is None:      # not billed for this cycle — nothing to pro-rate
            return Decimal("0")

        _, _, prorated, cancelled = cls.prorate(
            inv.fee.amount, inv.billing_period_start, inv.billing_period_end,
            discharge_date,
        )
        if cancelled <= 0:
            return Decimal("0")
        charges = cls._period_charges(
            admission, inv.billing_period_start, inv.billing_period_end
        )
        inv.base_fee = prorated
        inv.total_due = prorated + charges
        inv.save(update_fields=["base_fee", "total_due"])
        cls.recompute_status(inv)
        return cancelled


# ------------------------------------------------------- discharge preview
@dataclass
class DischargeLine:
    label: str
    kind: str            # 'fee' | 'charge' | 'opening' | 'settlement'
    amount: Decimal      # balance still due on this line


@dataclass
class DischargePreview:
    discharge_date: date
    # Current in-progress cycle (None if there isn't one to pro-rate).
    has_current_cycle: bool = False
    cycle_start: date = None
    cycle_end: date = None
    full_fee: Decimal = Decimal("0")
    days_in_period: int = 0
    days_stayed: int = 0
    prorated_fee: Decimal = Decimal("0")
    cancelled_fee: Decimal = Decimal("0")
    lines: list = field(default_factory=list)
    fees_due: Decimal = Decimal("0")
    charges_due: Decimal = Decimal("0")
    total_due_now: Decimal = Decimal("0")


def build_discharge_preview(admission, discharge_date: date) -> DischargePreview:
    """Compute — without mutating anything — what the patient owes if discharged
    on ``discharge_date``, with the current cycle's fee pro-rated to the days
    stayed. Itemises every outstanding line (fees + each additional charge)."""
    pv = DischargePreview(discharge_date=discharge_date)
    cur = BillingService.current_cycle_invoice(admission, discharge_date)
    cur_start, cur_end = BillingService._period_for(
        admission.admission_date, discharge_date
    )
    covered = (
        admission.opening_balance_as_of is not None
        and cur_start <= admission.opening_balance_as_of
    )

    # --- current in-progress cycle: pro-rated fee for the days stayed --------
    # Only when the cycle has actually been billed — no invoice, nothing owed.
    if cur is not None and not covered and discharge_date >= admission.admission_date:
        full_fee = cur.fee.amount
        days_in, stayed, prorated, cancelled = BillingService.prorate(
            full_fee, cur_start, cur_end, discharge_date
        )
        pv.has_current_cycle = True
        pv.cycle_start, pv.cycle_end = cur_start, cur_end
        pv.full_fee, pv.days_in_period, pv.days_stayed = full_fee, days_in, stayed
        pv.prorated_fee, pv.cancelled_fee = prorated, cancelled

        cur_paid = (
            BillingService.amount_paid(cur) + (cur.refund_amount or Decimal("0"))
            if cur is not None else Decimal("0")
        )
        cur_charges = BillingService._period_charges(admission, cur_start, cur_end)
        # Fee still owed for this period after any payment already applied.
        fee_bal = max(Decimal("0"), prorated - max(Decimal("0"), cur_paid - cur_charges))
        if prorated > 0:
            pv.lines.append(DischargeLine(
                f"Fee {cur_start:%d-%m-%Y} → {discharge_date:%d-%m-%Y} "
                f"({stayed}/{days_in} days, pro-rated)", "fee", fee_bal))
        pv.fees_due += fee_bal
        for ch in AdditionalCharge.objects.filter(
            admission=admission, charge_date__gte=cur_start, charge_date__lte=cur_end,
        ).order_by("charge_date"):
            pv.lines.append(DischargeLine(
                f"{ch.get_category_display()} {ch.charge_date:%d-%m-%Y}",
                "charge", ch.amount))
        # Charges owed for this period after payment (charges settle first).
        pv.charges_due += min(cur_charges, max(Decimal("0"), cur_charges + prorated - cur_paid))

    # --- all other outstanding invoices (older months, opening balance) -----
    for inv in admission.invoices.filter(
        status__in=[InvoiceStatus.UNPAID, InvoiceStatus.PARTIAL]
    ).order_by("billing_period_start"):
        if (inv.billing_period_start == cur_start
                and inv.billing_period_end == cur_end
                and not inv.is_opening_balance and not inv.is_settlement):
            continue  # already handled above as the current cycle
        bal = BillingService.balance_due(inv)
        if bal <= 0:
            continue
        if inv.is_opening_balance:
            pv.lines.append(DischargeLine("Opening balance", "opening", bal))
            pv.fees_due += bal
            continue
        charges = BillingService._period_charges(
            admission, inv.billing_period_start, inv.billing_period_end)
        charge_bal = min(bal, charges)
        fee_bal = bal - charge_bal
        period = f"{inv.billing_period_start:%d-%m-%Y}"
        if fee_bal > 0:
            pv.lines.append(DischargeLine(f"Fee {period}", "fee", fee_bal))
        for ch in AdditionalCharge.objects.filter(
            admission=admission,
            charge_date__gte=inv.billing_period_start,
            charge_date__lte=inv.billing_period_end,
        ).order_by("charge_date"):
            pv.lines.append(DischargeLine(
                f"{ch.get_category_display()} {ch.charge_date:%d-%m-%Y}",
                "charge", ch.amount))
        pv.fees_due += fee_bal
        pv.charges_due += charge_bal

    pv.total_due_now = pv.fees_due + pv.charges_due
    return pv
