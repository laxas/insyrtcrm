from django.apps import apps as global_apps
from django.contrib.auth.management import create_permissions
from django.db import migrations

# Permissions a Prompt-Manager holds: full control over prompt templates.
PROMPT_MANAGER_CODENAMES = [
    "manage_prompttemplate",
    "view_prompttemplate",
    "add_prompttemplate",
    "change_prompttemplate",
    "delete_prompttemplate",
]


def create_prompt_manager_group(apps, schema_editor):
    # Data migrations run before the post_migrate signal that normally creates
    # permissions, so force-create them here (mirrors accounts.0002_default_groups).
    for app_config in global_apps.get_app_configs():
        create_permissions(app_config, apps=apps, verbosity=0)

    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")

    perms = Permission.objects.filter(codename__in=PROMPT_MANAGER_CODENAMES)

    prompt_manager_group, _ = Group.objects.get_or_create(name="Prompt-Manager")
    prompt_manager_group.permissions.add(*perms)

    # Admins manage everything, including prompt templates.
    admin_group = Group.objects.filter(name="Admin").first()
    if admin_group:
        admin_group.permissions.add(*perms)


def delete_prompt_manager_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name="Prompt-Manager").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("leads", "0010_prompttemplate"),
        ("accounts", "0002_default_groups"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        migrations.RunPython(create_prompt_manager_group, delete_prompt_manager_group),
    ]
