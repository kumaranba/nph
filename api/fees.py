"""Fee lifecycle service.

Fee invariant (see CLAUDE.md):
- An ACTIVE admission has exactly one active Fee.
- A DISCHARGED admission has zero active Fees.
- Fee rows are never deleted; a change deactivates the current active Fee
  (is_active=False, deactivated_at=now) and creates a new active one.
- Only FINANCE may change a fee (ADMIN is view-only).
- change_fee's effective_from defaults to the admission's next
  not-yet-invoiced billing cycle date; an explicit effective_from that
  differs from that default requires override=True.
- A re-admission (new Admission row) has its own independent Fee history.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from .billing import BillingService
from .models import Admission, AdmissionStatus, Fee, UserRole


class FeeError(Exception):
    """Domain error for fee-rule violations (surfaced to the API layer)."""


class FeeService:
    @staticmethod
    def next_uninvoiced_cycle(admission) -> date:
        """The billing cycle date of the first period that has not been
        invoiced yet — the default effective date for a fee change."""
        latest = admission.invoices.order_by("-billing_period_end").first()
        if latest is not None:
            return latest.billing_period_end + timedelta(days=1)
        # No invoices yet: the current period start (never before admission).
        as_of = max(date.today(), admission.admission_date)
        start, _ = BillingService._period_for(admission.admission_date, as_of)
        return start

    @classmethod
    @transaction.atomic
    def change_fee(
        cls,
        admission_id,
        amount: Decimal,
        reason: str,
        user,
        effective_from: date = None,
        override: bool = False,
    ) -> Fee:
        # FINANCE only.
        if user is None or getattr(user, "role", None) != UserRole.FINANCE:
            raise FeeError("Only Finance can change fees.")
        if amount is None or amount <= 0:
            raise FeeError("Fee amount must be positive.")

        # Lock the admission row so concurrent change_fee calls serialize.
        admission = Admission.objects.select_for_update().get(pk=admission_id)
        if admission.status == AdmissionStatus.DISCHARGED:
            raise FeeError("Cannot change the fee of a discharged admission.")

        default_from = cls.next_uninvoiced_cycle(admission)
        if effective_from is None:
            effective_from = default_from
        elif effective_from != default_from and not override:
            raise FeeError(
                "effective_from differs from the default next billing cycle "
                "date; pass override=True to confirm."
            )

        # Defensive: at most one active fee should exist going in.
        active = list(admission.fees.filter(is_active=True))
        if len(active) > 1:
            raise FeeError("Data integrity error: multiple active fees exist.")

        now = timezone.now()
        for fee in active:
            fee.is_active = False
            fee.deactivated_at = now
            fee.save(update_fields=["is_active", "deactivated_at"])

        new_fee = Fee.objects.create(
            admission=admission,
            amount=amount,
            effective_from=effective_from,
            is_active=True,
            reason=reason or "",
            created_by=user,
        )

        # Post-condition: exactly one active fee.
        if admission.fees.filter(is_active=True).count() != 1:
            raise FeeError("Invariant violation: expected exactly one active fee.")
        return new_fee

    @classmethod
    @transaction.atomic
    def deactivate_fee_on_discharge(cls, admission_id):
        """Deactivate the admission's active fee(s) — called at discharge so a
        discharged admission holds zero active fees."""
        admission = Admission.objects.select_for_update().get(pk=admission_id)
        now = timezone.now()
        for fee in admission.fees.filter(is_active=True):
            fee.is_active = False
            fee.deactivated_at = now
            fee.save(update_fields=["is_active", "deactivated_at"])

    @staticmethod
    def get_fee_history(patient_id):
        """Every Fee across all of a patient's admissions, newest first."""
        return (
            Fee.objects.filter(admission__patient_id=patient_id)
            .select_related("admission", "created_by")
            .order_by("-created_at", "-id")
        )
