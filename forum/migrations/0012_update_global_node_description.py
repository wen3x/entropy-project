from django.db import migrations


def update_global_node(apps, schema_editor):
    Node = apps.get_model("forum", "Node")
    Node.objects.filter(slug="global").update(
        name="Глобальный",
        description="Посты без определенной темы",
    )


class Migration(migrations.Migration):

    dependencies = [
        ("forum", "0011_node_post_node_comment_edited_at"),
    ]

    operations = [
        migrations.RunPython(
            update_global_node, migrations.RunPython.noop
        ),
    ]
