from django.db import migrations

# Payment account for post-discharge take-home medication (billed and paid at
# discharge). Seeded like the other accounts so it appears in pickers and lets
# pharmacy receipts be tracked separately.
ACCOUNT = "Pharmacy"


def seed_pharmacy(apps, schema_editor):
    PaymentAccount = apps.get_model("api", "PaymentAccount")
    PaymentAccount.objects.get_or_create(name=ACCOUNT)


def unseed_pharmacy(apps, schema_editor):
    PaymentAccount = apps.get_model("api", "PaymentAccount")
    PaymentAccount.objects.filter(name=ACCOUNT).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0030_referrer_inquiry_referrer"),
    ]

    operations = [
        migrations.RunPython(seed_pharmacy, unseed_pharmacy),
    ]
