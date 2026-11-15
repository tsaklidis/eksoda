"""Parse a receipt URL or saved page and print the canonical result. Never touches the database.

python manage.py parse_receipt <url | path/to/page.html> [--json] [--url URL]

For a saved page the receipt URL comes from --url, else from a ``<page>.meta.json``
file next to it (fixtures), else from the first link on the page that a registered
provider recognizes.
"""

import json
import re
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.receipts.canonical import CanonicalReceipt
from apps.receipts.conf import default_fetcher
from apps.receipts.errors import ReceiptError
from apps.receipts.fetching import FetchedDocument
from apps.receipts.providers import registry
from apps.receipts.providers.base import mask_url
from apps.receipts.validation import validate

_LINK_RE = re.compile(r"https://[^\s\"'<>]+")


class Command(BaseCommand):
    help = "Fetch (or read) and parse a receipt; print canonical data and validation warnings."
    requires_system_checks: list = []

    def add_arguments(self, parser):
        parser.add_argument("source", help="Receipt URL, or path to a saved receipt page")
        parser.add_argument("--json", action="store_true", help="Print canonical JSON")
        parser.add_argument(
            "--url", help="Receipt URL of a saved page (default: the URL printed on the page)"
        )

    def handle(self, *args, source: str, url: str | None, **options):
        try:
            if source.startswith(("http://", "https://")):
                provider, identity = registry.resolve_url(source)
                document = provider.fetch(identity, default_fetcher())
            else:
                path = Path(source)
                html = self._read(path)
                page_url = url or _meta_url(path) or _page_url(html)
                provider, identity = registry.resolve_url(page_url)
                document = FetchedDocument(html.encode("utf-8"))
            receipt = provider.parse(document, identity)
        except ReceiptError as exc:
            detail = f" ({exc.detail})" if exc.detail else ""
            raise CommandError(f"{exc.code}: {exc.public_message}{detail}") from exc

        issues = [issue.to_dict() for issue in validate(receipt)]
        if options["json"]:  # not a parameter: it would hide the json module
            payload = receipt.to_json()
            payload["source_url"] = mask_url(receipt.source_url)
            output = {"receipt": payload, "validation": issues}
            self.stdout.write(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            self._summary(receipt, issues)

    @staticmethod
    def _read(path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8")
        except OSError as exc:
            raise CommandError(f"cannot read {path}: {exc.strerror}") from exc

    def _summary(self, receipt: CanonicalReceipt, issues: list[dict]) -> None:
        d, t = receipt.document, receipt.totals
        write = self.stdout.write
        write(
            f"Provider:  {receipt.provider_code} ({receipt.parser_version}, culture {receipt.culture})"
        )
        write(f"Source:    {mask_url(receipt.source_url)}")
        write(f"Merchant:  {receipt.issuer.legal_name} (VAT {receipt.issuer.vat_number})")
        if receipt.branch:
            city = receipt.branch.address.city if receipt.branch.address else None
            write(f"Store:     branch {receipt.branch.number or '-'} {city or ''}".rstrip())
        write(
            f"Document:  {d.type_code or '-'} {d.kind} {d.type_label or ''} "
            f"{d.formatted_number or ''}".rstrip()
        )
        write(f"Issued:    {d.issued_at.isoformat()} ({receipt.coverage.issue_time})")
        identity = receipt.identity
        key = identity.mark or identity.source_key or identity.uid or "-"
        write(f"Identity:  {key}  cancelled: {bool(identity.cancellation_mark)}")
        discount = f"  discount {t.discount}" if t.discount is not None else ""
        write(f"Totals:    net {t.net}  VAT {t.vat}  gross {t.gross} {d.currency}{discount}")
        c = receipt.coverage
        write(
            f"Coverage:  lines={c.line_items} line_tax={c.line_tax_amounts} "
            f"official_codes={c.official_codes} cross_checked={c.cross_checked}"
        )
        write(f"Lines ({len(receipt.lines)}):")
        for line in receipt.lines:
            line_discount = f" − {line.discount}" if line.discount else ""
            write(
                f"  {line.line_number:>3} {line.merchant_product_code or '':>8}  "
                f"{line.description[:40]:<40} {line.quantity} {line.unit_label or ''} "
                f"× {line.unit_price}{line_discount} = {line.gross}  (VAT {line.vat_rate}%)"
            )
        for entry in receipt.vat_breakdown:
            write(f"VAT:       {entry.rate}%  net {entry.net}  VAT {entry.vat}")
        for payment in receipt.payments:
            label = payment.method_label or payment.method_code or payment.method
            write(f"Payment:   {label} {payment.amount}{' (derived)' if payment.derived else ''}")
        if receipt.unknown_fields:
            write(f"Unknown fields (format drift): {', '.join(sorted(receipt.unknown_fields))}")
        if issues:
            write(self.style.WARNING("Validation warnings:"))
            for issue in issues:
                write(f"  - {issue['code']}: {issue['message']}")
        else:
            write(self.style.SUCCESS("Validation: no warnings"))


def _meta_url(path: Path) -> str | None:
    meta = path.with_name(f"{path.stem}.meta.json")
    if not meta.exists():
        return None
    return json.loads(meta.read_text(encoding="utf-8")).get("url")


def _page_url(html: str) -> str:
    for candidate in _LINK_RE.findall(html):
        candidate = candidate.replace("&amp;", "&")  # links inside HTML attributes
        try:
            registry.resolve_url(candidate)
        except ReceiptError:
            continue
        return candidate
    raise CommandError("no receipt URL found on the page: pass --url")
