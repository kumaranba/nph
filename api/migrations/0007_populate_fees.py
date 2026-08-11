from django.db import migrations
from django.utils import timezone

SYSTEM_EMAIL = "system@nph.local"


def forwards(apps, schema_editor):
    User = apps.get_model("api", "User")
    Admission = apps.get_model("api", "Admission")
    Fee = apps.get_model("api", "Fee")
    Invoice = apps.get_model("api", "Invoice")

    # A non-login system user to own migration-created fees.
    system_user, _ = User.objects.get_or_create(
        email=SYSTEM_EMAIL,
        defaults={
            "role": "ADMIN",
            "is_active": False,
            "is_staff": False,
            "is_superuser": False,
            "password": "",  # unusable — this account cannot log in
        },
    )

    now = timezone.now()
    fee_by_admission = {}
    for admission in Admission.objects.all():
        is_active = admission.status == "ACTIVE"
        fee = Fee.objects.create(
            admission=admission,
            amount=admission.monthly_fee,
            effective_from=admission.admission_date,
            is_active=is_active,
            reason="Initial fee (data migration)",
            created_by=system_user,
            deactivated_at=None if is_active else now,
        )
        fee_by_admission[admission.id] = fee

    for invoice in Invoice.objects.all():
        fee = fee_by_admission.get(invoice.admission_id)
        if fee is not None:
            invoice.fee = fee
            invoice.save(update_fields=["fee"])


def backwards(apps, schema_editor):
    User = apps.get_model("api", "User")
    Fee = apps.get_model("api", "Fee")
    Invoice = apps.get_model("api", "Invoice")

    Invoice.objects.update(fee=None)
    Fee.objects.all().delete()
    User.objects.filter(email=SYSTEM_EMAIL).delete()


class Migration(migrations.Migration):
    dependencies = [("api", "0006_fee_and_invoice_fee")]
    operations = [migrations.RunPython(forwards, backwards)]
