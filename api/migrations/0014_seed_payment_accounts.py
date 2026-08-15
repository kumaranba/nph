from django.db import migrations

# Initial set of payment accounts (extendable later as config data).
ACCOUNTS = ["Nila", "Vaigari", "Bank AC"]


def seed_accounts(apps, schema_editor):
    PaymentAccount = apps.get_model("api", "PaymentAccount")
    for name in ACCOUNTS:
        PaymentAccount.objects.get_or_create(name=name)


def unseed_accounts(apps, schema_editor):
    PaymentAccount = apps.get_model("api", "PaymentAccount")
    PaymentAccount.objects.filter(name__in=ACCOUNTS).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0013_paymentaccount_paymentreceipt_payment_receipt"),
    ]

    operations = [
        migrations.RunPython(seed_accounts, unseed_accounts),
    ]
