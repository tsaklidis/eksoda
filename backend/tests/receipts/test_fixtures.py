"""Every saved receipt page is a test: tests/fixtures/<provider>/<name>.html + .meta.json.

Meta file: {"url": <sanitized receipt URL>, "description": ..., "expect": {...}} where
"expect" is either {"warnings": [codes]} (parse, compare with the golden file in
expected/<name>.json, check validation warnings) or {"error": <error code>}.

Adding a new real receipt therefore needs no test code: sanitize it, add the meta
file, run `make test ARGS="tests/receipts/test_fixtures.py --update-golden"` and
review the golden file.
"""

import json
from pathlib import Path

import pytest

from apps.receipts.errors import ReceiptError
from apps.receipts.fetching import FetchedDocument
from apps.receipts.providers import registry
from apps.receipts.validation import validate

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
META_FILES = sorted(FIXTURES.glob("*/*.meta.json"))


def load(meta_path: Path):
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    page = meta_path.with_name(meta_path.name.removesuffix(".meta.json") + ".html")
    provider, identity = registry.resolve_url(meta["url"])
    document = FetchedDocument(page.read_bytes())
    return meta, provider, identity, document


def golden_check(receipt, golden: Path, update: bool) -> None:
    actual = json.dumps(receipt.to_json(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if update:
        golden.parent.mkdir(exist_ok=True)
        golden.write_text(actual, encoding="utf-8")
    assert golden.exists(), f"missing golden {golden.name}: run with --update-golden and review it"
    assert actual == golden.read_text(encoding="utf-8"), f"golden mismatch: {golden}"


def test_fixtures_exist_for_every_provider():
    providers_with_fixtures = {path.parent.name for path in META_FILES}
    assert providers_with_fixtures == set(registry.codes)


@pytest.mark.parametrize("meta_path", META_FILES, ids=lambda p: f"{p.parent.name}/{p.stem}")
def test_fixture(meta_path, update_golden):
    meta, provider, identity, document = load(meta_path)
    assert meta_path.parent.name == provider.code, "fixture is in the wrong provider folder"
    expect = meta["expect"]

    if "error" in expect:
        with pytest.raises(ReceiptError) as raised:
            provider.parse(document, identity)
        assert raised.value.code == expect["error"]
        return

    receipt = provider.parse(document, identity)
    name = meta_path.name.removesuffix(".meta.json")
    golden_check(receipt, meta_path.parent / "expected" / f"{name}.json", update_golden)
    assert [issue.code for issue in validate(receipt)] == expect["warnings"]
    assert receipt.provider_code == provider.code
    assert receipt.parser_version in {layout.name for layout in provider.layouts}
