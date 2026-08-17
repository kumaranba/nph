"""Backfill PaymentReceipts for human-recorded payments that predate receipts
(e.g. invoice-level "Log payment"). Each such Payment gets its own receipt so
it appears in payments history and counts on the account statement.

Credit-funded auto-payments (recorded_by is null) are left receiptless — they
re-apply already-received money and must not be counted again.
"""
from django.db import migrations


def backfill(apps, schema_editor):
    Payment = apps.get_model("api", "Payment")
    PaymentReceipt = apps.get_model("api", "PaymentReceipt")

    orphans = Payment.objects.filter(
        receipt__isnull=True, recorded_by__isnull=False
    ).select_related("invoice__admission")
    for payment in orphans:
        receipt = PaymentReceipt.objects.create(
            admission=payment.invoice.admission,
            paid_on=payment.paid_on,
            amount=payment.amount,
            fees_amount=payment.amount,
            charges_amount=0,
            account=None,
            recorded_by_id=payment.recorded_by_id,
        )
        payment.receipt = receipt
        payment.save(update_fields=["receipt"])


def unbackfill(apps, schema_editor):
    # Best-effort reverse: drop receipts that have no account and a single
    # payment (the shape this migration creates). Detaches then deletes.
    PaymentReceipt = apps.get_model("api", "PaymentReceipt")
    for receipt in PaymentReceipt.objects.filter(account__isnull=True):
        payments = list(receipt.payments.all())
        if len(payments) == 1:
            payments[0].receipt = None
            payments[0].save(update_fields=["receipt"])
            receipt.delete()


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0015_alter_patient_age"),
    ]

    operations = [
        migrations.RunPython(backfill, unbackfill),
    ]
