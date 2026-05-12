"""Management command: create (or update) the daily stats cache warm-up schedule."""

from __future__ import annotations

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Create or update the Django-Q2 schedule for daily stats cache warm-up."

    def handle(self, *args, **options):
        from django_q.models import Schedule

        name = "warm_stats_cache"
        func = "apps.stats.tasks.warm_stats_cache"

        obj, created = Schedule.objects.update_or_create(
            name=name,
            defaults={
                "func": func,
                "schedule_type": Schedule.DAILY,
                "repeats": -1,  # run indefinitely
            },
        )
        verb = "Created" if created else "Updated"
        self.stdout.write(self.style.SUCCESS(f"{verb} schedule '{name}' (pk={obj.pk})."))
