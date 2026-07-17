from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0004_profile_color_daily_quests_shop"),
    ]

    operations = [
        migrations.CreateModel(
            name="UserQuestSlot",
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
                ("slot", models.PositiveSmallIntegerField()),
                ("quest_code", models.CharField(db_index=True, max_length=64)),
                ("progress", models.PositiveSmallIntegerField(default=0)),
                ("extra_data", models.JSONField(blank=True, default=dict)),
                ("assigned_at", models.DateTimeField(auto_now_add=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="quest_slots",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ("slot",),
            },
        ),
        migrations.AddConstraint(
            model_name="userquestslot",
            constraint=models.UniqueConstraint(
                fields=("user", "slot"), name="uniq_user_quest_slot"
            ),
        ),
    ]
