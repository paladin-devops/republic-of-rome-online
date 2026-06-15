import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("rorapp", "0053_assassination_fields"),
    ]

    operations = [
        migrations.CreateModel(
            name="Province",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(max_length=30)),
                ("developed", models.BooleanField(default=False)),
                ("term", models.PositiveSmallIntegerField(default=0)),
                (
                    "game",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="provinces",
                        to="rorapp.game",
                    ),
                ),
                (
                    "governor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="governorships",
                        to="rorapp.senator",
                    ),
                ),
            ],
        ),
        migrations.AddField(
            model_name="senator",
            name="corrupt",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="senator",
            name="rebel",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="legion",
            name="province",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="legions",
                to="rorapp.province",
            ),
        ),
    ]
