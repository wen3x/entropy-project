# Generated manually for Entropy v2.1 / shop v1.0

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0003_notification"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="profile_color",
            field=models.CharField(
                blank=True,
                choices=[
                    ("", "По умолчанию"),
                    ("red", "Красный"),
                    ("blue", "Синий"),
                    ("green", "Зелёный"),
                    ("gold", "Золотой"),
                ],
                default="",
                max_length=16,
            ),
        ),
        migrations.CreateModel(
            name="ShopItem",
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
                ("code", models.SlugField(max_length=64, unique=True)),
                ("title", models.CharField(max_length=128)),
                ("description", models.TextField()),
                ("price_tokens", models.PositiveIntegerField()),
                (
                    "item_type",
                    models.CharField(
                        choices=[
                            ("extend_vitality", "Продление жизни аккаунта"),
                            ("profile_color_basic", "Базовый цвет профиля"),
                            ("profile_color_gold", "Золотой цвет профиля"),
                        ],
                        max_length=32,
                    ),
                ),
                (
                    "visible_in_shop",
                    models.BooleanField(db_index=True, default=False),
                ),
                ("sort_order", models.PositiveSmallIntegerField(default=0)),
            ],
            options={
                "ordering": ("sort_order", "id"),
            },
        ),
        migrations.CreateModel(
            name="UserDailyQuestCycle",
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
                ("cycle_started_at", models.DateTimeField(auto_now_add=True)),
                ("cycle_completed_at", models.DateTimeField(blank=True, null=True)),
                ("golden_likes_done", models.BooleanField(default=False)),
                ("golden_approval_done", models.BooleanField(default=False)),
                ("dying_extensions_done", models.BooleanField(default=False)),
                ("golden_liked_post_ids", models.JSONField(blank=True, default=list)),
                ("dying_extended_post_ids", models.JSONField(blank=True, default=list)),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="daily_quest_cycle",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
    ]
