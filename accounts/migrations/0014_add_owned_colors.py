from django.db import migrations, models


def populate_owned_colors(apps, schema_editor):
    User = apps.get_model('accounts', 'User')
    for user in User.objects.iterator():
        colors = list(user.owned_colors or [])
        changed = False
        if user.has_basic_colors:
            for c in ("ice", "matrix", "sunset"):
                if c not in colors:
                    colors.append(c)
                    changed = True
        if user.has_gold_color and "gold" not in colors:
            colors.append("gold")
            changed = True
        if changed:
            User.objects.filter(pk=user.pk).update(owned_colors=colors)


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0013_alter_notification_kind'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='owned_colors',
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.RunPython(populate_owned_colors, migrations.RunPython.noop),
    ]
