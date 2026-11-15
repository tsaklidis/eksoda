"""Dependency rules between modules (TD §2.2).

Provider/parsing code must stay plain Python so it can be tested with fixtures
alone; some apps must not depend on others. Paths that do not exist yet (later
milestones) are checked as soon as they are created.
"""

import ast
from pathlib import Path

APPS = Path(__file__).resolve().parent.parent / "apps"

PURE_PATHS = [
    "receipts/providers",
    "receipts/canonical.py",
    "receipts/mydata.py",
    "receipts/fetching.py",
    "receipts/links.py",
    "receipts/errors.py",
    "receipts/validation.py",
    "receipts/vocabulary.py",
    "receipts/classification.py",
    "products/units.py",
    "products/packages.py",
    "analytics/periods.py",
    "common/text.py",
    "common/numbers.py",
]
PURE_FORBIDDEN_ROOTS = {"django", "rest_framework", "celery"}

# (importing package, forbidden module prefix)
LAYER_RULES = [
    ("merchants", "apps.receipts.services"),
    ("merchants", "apps.receipts.models"),
    ("products", "apps.receipts.services"),
    ("receipts/providers", "apps.receipts.services"),
    ("common", "apps.receipts"),
    ("common", "apps.products"),
]


def python_files(path: Path):
    if path.is_file():
        yield path
    elif path.is_dir():
        yield from path.rglob("*.py")


def imported_modules(source: str) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            modules.add(node.module)
    return modules


def is_pure_violation(module: str) -> bool:
    root = module.split(".")[0]
    return root in PURE_FORBIDDEN_ROOTS or (module.startswith("apps.") and ".models" in module)


def test_pure_modules_do_not_import_frameworks():
    violations = [
        f"{file.relative_to(APPS)} imports {module}"
        for rel in PURE_PATHS
        for file in python_files(APPS / rel)
        for module in imported_modules(file.read_text())
        if is_pure_violation(module)
    ]
    assert not violations, violations


def test_layering_rules():
    violations = [
        f"{file.relative_to(APPS)} imports {module}"
        for package, forbidden in LAYER_RULES
        for file in python_files(APPS / package)
        for module in imported_modules(file.read_text())
        if module.startswith(forbidden)
    ]
    assert not violations, violations


def test_checker_detects_violations():
    source = (
        "import django\nfrom apps.products.models import Product\nfrom decimal import Decimal\n"
    )
    modules = imported_modules(source)
    assert {m for m in modules if is_pure_violation(m)} == {"django", "apps.products.models"}
