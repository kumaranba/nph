"""Verify the Fee invariants against the live database.

Checks (see CLAUDE.md Fee invariant):
- every Invoice has a fee,
- every ACTIVE admission has exactly one active Fee,
- every DISCHARGED admission has zero active Fees.

Exits non-zero (CommandError) if any invariant is violated, so it can gate CI
or a post-migration check.
"""
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count, Q

from api.models import Admission, AdmissionStatus, Invoice


class Command(BaseCommand):
    help = "Verify Fee invariants (invoices have fees; active-fee counts)."

    def handle(self, *args, **options):
        errors = []

        missing = Invoice.objects.filter(fee__isnull=True).count()
        if missing:
            errors.append(f"{missing} invoice(s) have no fee")

        active_qs = Admission.objects.filter(
            status=AdmissionStatus.ACTIVE
        ).annotate(n=Count("fees", filter=Q(fees__is_active=True)))
        for admission in active_qs.exclude(n=1):
            errors.append(
                f"ACTIVE admission #{admission.id} has {admission.n} active "
                f"fee(s), expected exactly 1"
            )

        discharged_qs = Admission.objects.filter(
            status=AdmissionStatus.DISCHARGED
        ).annotate(n=Count("fees", filter=Q(fees__is_active=True)))
        for admission in discharged_qs.exclude(n=0):
            errors.append(
                f"DISCHARGED admission #{admission.id} has {admission.n} active "
                f"fee(s), expected 0"
            )

        if errors:
            for line in errors[:100]:
                self.stderr.write(self.style.ERROR(line))
            raise CommandError(f"{len(errors)} Fee invariant violation(s) found.")

        self.stdout.write(
            self.style.SUCCESS("Fee migration verified: all invariants hold.")
        )
