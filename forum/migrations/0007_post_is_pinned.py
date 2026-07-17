from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("forum", "0006_remove_globalevent"),
    ]

    operations = [
        migrations.AddField(
            model_name="post",
            name="is_pinned",
            field=models.BooleanField(db_index=True, default=False),
        ),
    ]
