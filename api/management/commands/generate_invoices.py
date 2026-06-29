"""Daily invoice generation.

Run from cron / a scheduler once a day:

    python manage.py generate_invoices

Generates any invoices that have become due for active admissions. Idempotent
— re-running on the same day creates nothing new.
"""
from django.core.management.base import BaseCommand

from api.billing import BillingService


class Command(BaseCommand):
    help = "Generate due billing invoices for all active admissions."

    def handle(self, *args, **options):
        created = BillingService.generate_all_due_invoices()
        self.stdout.write(
            self.style.SUCCESS(f"Generated {len(created)} invoice(s).")
        )
