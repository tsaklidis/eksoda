"""Shared machinery for turning saved receipt pages into personal-data-free fixtures.

A provider sanitizer replaces secret values *where they occur*: the text of the
specific elements that hold them (buyer data, payment ids, signatures; any length),
specific attributes (download tokens), and link-shaped occurrences matched by a
provider pattern (access tokens inside receipt URLs). Nothing is replaced by a
blind search over the whole page, so unrelated content (item codes, amounts,
inline images) is never touched. ``finish`` then verifies that no recorded
original survives anywhere; if one does, SanitizeError.
"""

import re
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass

from bs4 import BeautifulSoup, Tag

from apps.receipts.providers.html import text_of

# Originals shorter than this are replaced structurally but not searched for during
# verification: a 3-letter value would also match unrelated words.
_MIN_VERIFY_LENGTH = 4


class SanitizeError(Exception):
    pass


@dataclass(frozen=True)
class SanitizeResult:
    html: str
    replaced: dict[str, int]  # category → number of distinct values replaced


def fake_like(value: str, letter: str = "X") -> str:
    """Same shape: digits → 0, letters → ``letter``, other characters kept."""
    return "".join("0" if ch.isdigit() else letter if ch.isalpha() else ch for ch in value)


class Secrets:
    def __init__(self) -> None:
        self._originals: dict[str, str] = {}  # original → category (for counts and verify)
        self._patterns: list[tuple[re.Pattern, Callable[[str], str], str]] = []

    def record(self, original: str, category: str) -> None:
        if original:
            self._originals.setdefault(original, category)

    def replace_element(self, element: Tag | None, category: str) -> None:
        """Replace an element's whole text with a same-shape fake (any length)."""
        if element is None:
            return
        original = text_of(element)
        fake = fake_like(original)
        if not original or fake == original:  # empty, or already a fake (re-sanitizing)
            return
        element.string = fake
        self.record(original, category)

    def replace_attribute(
        self, element: Tag, attribute: str, category: str, fake: str = ""
    ) -> None:
        original = (element.get(attribute) or "").strip()
        if original and original != fake:
            element[attribute] = fake
            self.record(original, category)

    def replace_pattern(
        self, pattern: re.Pattern, fake_for: Callable[[str], str], category: str
    ) -> None:
        """Replace group 1 of every match of ``pattern`` (applied in ``finish``)."""
        self._patterns.append((pattern, fake_for, category))

    def _apply_patterns(self, output: str) -> str:
        for pattern, fake_for, category in self._patterns:

            def substitute(match: re.Match, fake_for=fake_for, category=category) -> str:
                original = match.group(1)
                fake = fake_for(original)
                if fake == original:
                    return match.group(0)
                self.record(original, category)
                start, end = match.span(1)
                offset = match.start(0)
                text = match.group(0)
                return text[: start - offset] + fake + text[end - offset :]

            output = pattern.sub(substitute, output)
        return output

    def items(self):
        return self._originals.items()

    def counts(self) -> dict[str, int]:
        counts: dict[str, int] = defaultdict(int)
        for category in self._originals.values():
            counts[category] += 1
        return dict(counts)


def strip_active_content(soup: BeautifulSoup) -> None:
    """Remove scripts, styles, external links and hidden form values."""
    for tag in soup(["script", "style", "noscript", "link"]):
        tag.decompose()
    for hidden in soup.select('input[type="hidden"]'):
        hidden["value"] = ""


def finish(soup: BeautifulSoup, secrets: Secrets) -> SanitizeResult:
    output = secrets._apply_patterns(str(soup))
    verify(output, secrets)
    return SanitizeResult(html=output, replaced=secrets.counts())


def verify(output: str, secrets: Secrets) -> None:
    check = BeautifulSoup(output, "lxml")
    attributes = " ".join(
        " ".join(value) if isinstance(value, list) else str(value)
        for tag in check.find_all(True)
        for value in tag.attrs.values()
    )
    haystack = "\n".join([output, check.get_text(" "), attributes])
    leaked = sorted(
        {
            category
            for original, category in secrets.items()
            if len(original) >= _MIN_VERIFY_LENGTH and original in haystack
        }
    )
    if leaked:
        raise SanitizeError(f"values still present after sanitizing: {', '.join(leaked)}")
