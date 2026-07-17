import secrets
import string

from django.db import migrations, models

ALPHABET = string.ascii_letters + string.digits + "_"


def _gen_slug(existing):
    length = secrets.randbelow(4) + 8
    while True:
        slug = "".join(secrets.choice(ALPHABET) for _ in range(length))
        if slug not in existing:
            existing.add(slug)
            return slug


def fill_slugs(apps, schema_editor):
    Post = apps.get_model("forum", "Post")
    existing = set(Post.objects.exclude(slug="").values_list("slug", flat=True))
    for post in Post.objects.all():
        if post.slug:
            continue
        post.slug = _gen_slug(existing)
        post.save(update_fields=["slug"])


class Migration(migrations.Migration):

    dependencies = [
        ("forum", "0003_like_granted_time_extension_like_is_active"),
    ]

    operations = [
        # 1. Создаем поле СРАЗУ уникальным, без промежуточных шагов
        migrations.AddField(
            model_name="post",
            name="slug",
            field=models.CharField(blank=True, max_length=11, unique=True, default=""),
            preserve_default=False,
        ),
        # 2. Заполняем слагами, если нужно (на пустой БД эта функция просто пролетит мимо)
        migrations.RunPython(fill_slugs, migrations.RunPython.noop),
        
        # 3. Твои остальные изменения (комментарии и лайки)
        migrations.AlterField(
            model_name="comment",
            name="is_active",
            field=models.BooleanField(
                db_index=True,
                default=True,
                help_text="Ложь — комментарий скрыт после очистки.",
            ),
        ),
        migrations.AlterField(
            model_name="like",
            name="granted_time_extension",
            field=models.BooleanField(
                default=False,
                help_text="Посту уже начислены +4ч за лайк этого пользователя.",
            ),
        ),
        migrations.AlterField(
            model_name="post",
            name="is_active",
            field=models.BooleanField(
                db_index=True,
                default=True,
                help_text="Ложь — пост в архиве (Кладбище).",
            ),
        ),
    ]