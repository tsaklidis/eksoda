"""Write a personal-data-free copy of a saved receipt page (for test fixtures).

    python manage.py sanitize_fixture <provider> raw.html tests/fixtures/<provider>/name.html

Each provider ships its own sanitizer. The output is verified: if any original
personal value survives, nothing is written.
"""

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.receipts.errors import ReceiptError
from apps.receipts.providers import registry
from apps.receipts.providers.sanitizing import SanitizeError


class Command(BaseCommand):
    help = "Sanitize a saved receipt page with its provider's sanitizer, verify it, write it."
    requires_system_checks: list = []

    def add_arguments(self, parser):
        parser.add_argument("provider", help=f"Provider code: {', '.join(registry.codes)}")
        parser.add_argument("source", type=Path)
        parser.add_argument("target", type=Path)
        parser.add_argument("--force", action="store_true", help="Overwrite the target")

    def handle(self, *args, provider: str, source: Path, target: Path, force: bool, **options):
        try:
            sanitizer = registry.get(provider)
        except ReceiptError as exc:
            raise CommandError(
                f"unknown provider {provider!r} ({', '.join(registry.codes)})"
            ) from exc
        if target.exists() and not force:
            raise CommandError(f"{target} exists (use --force to overwrite)")
        try:
            raw = source.read_text(encoding="utf-8")
        except OSError as exc:
            raise CommandError(f"cannot read {source}: {exc.strerror}") from exc
        try:
            result = sanitizer.sanitize(raw)
        except SanitizeError as exc:
            raise CommandError(f"refusing to write: {exc}") from exc
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(result.html, encoding="utf-8")
        summary = ", ".join(f"{name}={count}" for name, count in sorted(result.replaced.items()))
        self.stdout.write(self.style.SUCCESS(f"Wrote {target} (replaced: {summary or 'nothing'})"))
        self.stdout.write(
            f"Next: add {target.with_suffix('').name}.meta.json with the sanitized URL, "
            "then run the fixture tests with --update-golden and review the golden file."
        )
