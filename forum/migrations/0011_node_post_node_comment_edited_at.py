from django.db import migrations, models
import django.db.models.deletion


def create_global_node(apps, schema_editor):
    Node = apps.get_model("forum", "Node")
    global_node = Node.objects.create(
        slug="global",
        name="Глобальный",
        description="Посты без определенной темы",
    )
    Post = apps.get_model("forum", "Post")
    Post.objects.all().update(node=global_node)


class Migration(migrations.Migration):

    dependencies = [
        ("forum", "0010_remove_uniq_top_level_comment_per_user_post"),
    ]

    operations = [
        migrations.CreateModel(
            name="Node",
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
                (
                    "slug",
                    models.SlugField(db_index=True, max_length=32, unique=True),
                ),
                ("name", models.CharField(max_length=64)),
                ("description", models.TextField(blank=True, default="")),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="created_nodes",
                        to="accounts.user",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("is_active", models.BooleanField(default=True)),
            ],
            options={
                "ordering": ("name",),
            },
        ),
        migrations.AddField(
            model_name="post",
            name="node",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="posts",
                to="forum.node",
            ),
        ),
        migrations.AddField(
            model_name="comment",
            name="edited_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RunPython(create_global_node, migrations.RunPython.noop),
    ]
