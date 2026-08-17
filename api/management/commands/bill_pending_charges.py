"""Bill any additional charges that aren't reflected on an invoice yet.

Historical charges (added before charges billed on creation) can be stranded —
added after their period's invoice was generated, or dated into an
opening-balance-covered period. This sweeps them onto the right invoice
(topping up the monthly invoice, or a charges-only settlement invoice for
covered periods). Idempotent — safe to re-run.

    python manage.py bill_pending_charges
    python manage.py bill_pending_charges --dry-run
"""
from django.core.management.base import BaseCommand

from api.billing import BillingService
from api.models import AdditionalCharge


class Command(BaseCommand):
    help = "Bill additional charges not yet reflected on an invoice (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Report how many charges would be (re)billed without writing.",
        )

    def handle(self, *args, **options):
        charges = AdditionalCharge.objects.select_related("admission").all()
        total = charges.count()

        if options["dry_run"]:
            self.stdout.write(
                self.style.WARNING(f"Would (re)bill {total} charge(s).")
            )
            return

        for charge in charges:
            BillingService.bill_charge(charge)
        self.stdout.write(self.style.SUCCESS(f"Billed {total} charge(s)."))
