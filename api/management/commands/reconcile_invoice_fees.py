"""Reconcile generated invoices to the fee in force at their period start.

Fixes patients whose fee was changed (with an effective date covering an
already-generated cycle) before invoices were re-priced automatically. For each
monthly invoice it finds the Fee whose ``effective_from`` is the latest on or
before the invoice's ``billing_period_start`` and, if the invoice's snapshot
differs, re-prices it (recomputes total_due + status; any resulting overpayment
is released to advance credit). Opening-balance and settlement invoices are
skipped. Idempotent.

Usage:
    python manage.py reconcile_invoice_fees
    python manage.py reconcile_invoice_fees --dry-run
"""
from django.core.management.base import BaseCommand

from api.billing import BillingService
from api.models import Admission, Invoice


class Command(BaseCommand):
    help = "Re-price generated invoices to match the fee in force at their period start."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Report what would change without writing anything.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        repriced = 0
        checked = 0

        for admission in Admission.objects.prefetch_related("fees"):
            fees = sorted(
                admission.fees.all(), key=lambda f: (f.effective_from, f.id)
            )
            if not fees:
                continue
            invoices = admission.invoices.filter(
                is_opening_balance=False, is_settlement=False
            )
            for inv in invoices:
                checked += 1
                # Latest fee effective on or before the period start.
                applicable = None
                for f in fees:
                    if f.effective_from <= inv.billing_period_start:
                        applicable = f
                    else:
                        break
                if applicable is None:
                    continue
                if inv.fee_id == applicable.id and inv.base_fee == applicable.amount:
                    continue
                self.stdout.write(
                    f"  {admission.patient.patient_id} "
                    f"{inv.billing_period_start:%d-%m-%Y}: "
                    f"{inv.base_fee} -> {applicable.amount}"
                )
                if not dry_run:
                    BillingService.reprice_invoice(inv, applicable)
                repriced += 1

        verb = "Would re-price" if dry_run else "Re-priced"
        self.stdout.write(self.style.SUCCESS(
            f"{verb} {repriced} of {checked} invoice(s)."
        ))
