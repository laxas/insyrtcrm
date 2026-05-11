from django.apps import apps as global_apps
from django.contrib.auth.management import create_permissions
from django.db import migrations

# Permissions granted to PR-Rep: add/change/view on operational models.
PR_REP_CODENAMES = [
    # leads
    "view_company",
    "add_company",
    "change_company",
    "view_contact",
    "add_contact",
    "change_contact",
    "delete_contact",
    "view_prbriefing",
    "add_prbriefing",
    "change_prbriefing",
    "view_stagetransition",
    "add_stagetransition",
    "view_stage",
    # activities
    "view_activity",
    "add_activity",
    "change_activity",
    # imports
    "view_importbatch",
]

# Read-only: view_* on everything operational.
READ_ONLY_CODENAMES = [
    "view_company",
    "view_contact",
    "view_prbriefing",
    "view_stagetransition",
    "view_stage",
    "view_activity",
    "view_importbatch",
    "view_auditentry",
]


def create_groups(apps, schema_editor):
    # Permissions are created by post_migrate signal normally, but data migrations
    # run before that signal fires. Force-create them now so we can assign them.
    for app_config in global_apps.get_app_configs():
        create_permissions(app_config, apps=apps, verbosity=0)

    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")

    admin_group, _ = Group.objects.get_or_create(name="Admin")
    pr_rep_group, _ = Group.objects.get_or_create(name="PR-Rep")
    readonly_group, _ = Group.objects.get_or_create(name="Read-only")

    pr_rep_perms = Permission.objects.filter(codename__in=PR_REP_CODENAMES)
    pr_rep_group.permissions.set(pr_rep_perms)

    readonly_perms = Permission.objects.filter(codename__in=READ_ONLY_CODENAMES)
    readonly_group.permissions.set(readonly_perms)

    # Admin group gets all permissions — managed via is_superuser in practice,
    # but the group exists for explicit role checks.
    all_perms = Permission.objects.all()
    admin_group.permissions.set(all_perms)


def delete_groups(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name__in=["Admin", "PR-Rep", "Read-only"]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0001_initial"),
        ("leads", "0001_initial"),
        ("activities", "0001_initial"),
        ("imports", "0001_initial"),
        # auth permissions exist after contenttypes migrations
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        migrations.RunPython(create_groups, delete_groups),
    ]
