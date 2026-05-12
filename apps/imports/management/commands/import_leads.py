"""Management command: import_leads

Usage
-----
  uv run python manage.py import_leads <file> [--mapping google_sheet_v1] [--on-duplicate skip]

Useful for ops and automated tests.
"""

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError

from apps.imports.services import DuplicateAbortError, LeadImporter


class Command(BaseCommand):
    help = "Import leads from an xlsx or csv file."

    def add_arguments(self, parser):
        parser.add_argument("file", help="Path to the xlsx or csv file to import")
        parser.add_argument(
            "--mapping",
            default="google_sheet_v1",
            help="Column mapping name (default: google_sheet_v1)",
        )
        parser.add_argument(
            "--on-duplicate",
            default="skip",
            choices=["skip", "update", "abort"],
            dest="on_duplicate",
            help="What to do with duplicate companies (default: skip)",
        )
        parser.add_argument(
            "--user",
            default=None,
            help="Username to record on the ImportBatch (defaults to first superuser)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            dest="dry_run",
            help="Preview only — do not write to the database",
        )

    def handle(self, *args, **options):
        filepath = options["file"]
        on_duplicate = options["on_duplicate"]
        dry_run = options["dry_run"]

        user = self._resolve_user(options["user"])

        try:
            fh = open(filepath, "rb")  # noqa: SIM115
        except OSError as exc:
            raise CommandError(f"Cannot open {filepath!r}: {exc}") from exc

        with fh:
            importer = LeadImporter(fh, on_duplicate=on_duplicate)

            if dry_run:
                result = importer.preview()
                self.stdout.write(
                    f"Preview: {result.new_count} new, "
                    f"{result.update_count} update, "
                    f"{result.skip_count} skip, "
                    f"{result.error_count} error(s)"
                )
                for row in result.rows:
                    if row.issues:
                        msg = (
                            f"  Row {row.row_number} [{row.status}]"
                            f" {row.company_name}: {'; '.join(row.issues)}"
                        )
                        self.stderr.write(msg)
                return

            try:
                batch = importer.commit(user)
            except DuplicateAbortError as exc:
                raise CommandError(str(exc)) from exc

        self.stdout.write(
            self.style.SUCCESS(
                f"Import complete: {batch.rows_created} created, "
                f"{batch.rows_updated} updated, "
                f"{batch.rows_skipped} skipped."
            )
        )
        if batch.errors_json:
            self.stderr.write(f"{len(batch.errors_json)} row error(s):")
            for err in batch.errors_json:
                issues = "; ".join(err["issues"])
                self.stderr.write(f"  Row {err['row']} {err['company']}: {issues}")

    def _resolve_user(self, username: str | None) -> User:
        if username:
            try:
                return User.objects.get(username=username)
            except User.DoesNotExist as exc:
                raise CommandError(f"User {username!r} not found") from exc
        user = User.objects.filter(is_superuser=True).first()
        if user is None:
            raise CommandError("No superuser found — pass --user <username>")
        return user
