import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    """Make Invoice.fee non-nullable now that migration 0007 has populated it
    for every existing invoice."""

    dependencies = [("api", "0007_populate_fees")]

    operations = [
        migrations.AlterField(
            model_name="invoice",
            name="fee",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="invoices",
                to="api.fee",
            ),
        ),
    ]
