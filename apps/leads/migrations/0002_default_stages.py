from django.db import migrations

STAGES = [
    # (order, name_de, name_en, is_final, is_archive)
    (1, "Neu", "New", False, False),
    (2, "Recherche", "Research", False, False),
    (3, "Kontaktiert", "Contacted", False, False),
    (4, "In Gespräch", "In Conversation", False, False),
    (5, "Angebot", "Proposal", False, False),
    (6, "Angebot abgelehnt", "Proposal rejected", False, True),
    (7, "Disqualifiziert", "Disqualified", False, True),
    (8, "Kunde", "Customer", True, False),
]


def create_stages(apps, schema_editor):
    Stage = apps.get_model("leads", "Stage")
    for order, name_de, name_en, is_final, is_archive in STAGES:
        Stage.objects.get_or_create(
            name_de=name_de,
            defaults={
                "name_en": name_en,
                "order": order,
                "is_final": is_final,
                "is_archive": is_archive,
            },
        )


def delete_stages(apps, schema_editor):
    Stage = apps.get_model("leads", "Stage")
    Stage.objects.filter(name_de__in=[s[1] for s in STAGES]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("leads", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_stages, delete_stages),
    ]
