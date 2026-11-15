"""Text normalization for matching and search keys (pure Python, requirements §9.5).

Normalized text is a *key*: it never replaces the original receipt text.
"""

import hashlib
import re
import string
import unicodedata

# Capital letters that look identical in the Latin and Greek alphabets.
_LATIN_LOOKALIKES = "ABEHIKMNOPTXYZ"
_GREEK_LOOKALIKES = "ΑΒΕΗΙΚΜΝΟΡΤΧΥΖ"
_TO_GREEK = str.maketrans(_LATIN_LOOKALIKES, _GREEK_LOOKALIKES)
_TO_LATIN = str.maketrans(_GREEK_LOOKALIKES, _LATIN_LOOKALIKES)
_AMBIGUOUS = set(_LATIN_LOOKALIKES) | set(_GREEK_LOOKALIKES)
_GREEK_ONLY = set("ΑΒΓΔΕΖΗΘΙΚΛΜΝΞΟΠΡΣΤΥΦΧΨΩ") - _AMBIGUOUS
_LATIN_ONLY = set(string.ascii_uppercase) - _AMBIGUOUS

_NOT_KEPT = re.compile(r"(?:[^\w.%]|_)+")  # keep letters/digits of any script, '.', '%'
_LOOSE_DOT = re.compile(r"(?<!\d)\.|\.(?!\d)")
_DECIMAL_COMMA = re.compile(r"(?<=\d),(?=\d)")


def strip_diacritics(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text)
    return unicodedata.normalize(
        "NFC", "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    )


def _unify_script(token: str) -> str:
    """Write look-alike letters in the token's dominant script.

    Tokens made only of look-alike letters (e.g. ``KAKAO`` vs ``ΚΑΚΑΟ``) are written
    in Latin so both spellings produce the same key.
    """
    greek = sum(ch in _GREEK_ONLY for ch in token)
    latin = sum(ch in _LATIN_ONLY for ch in token)
    if greek > latin:
        return token.translate(_TO_GREEK)
    return token.translate(_TO_LATIN)


def normalize_text(text: str) -> str:
    """Uppercase, accent-free, script-unified, punctuation-collapsed matching key."""
    value = unicodedata.normalize("NFKC", text)
    value = strip_diacritics(value).upper()  # upper() also turns final sigma into Σ
    value = _DECIMAL_COMMA.sub(".", value)
    value = _NOT_KEPT.sub(" ", value)
    value = _LOOSE_DOT.sub(" ", value)
    return " ".join(_unify_script(token) for token in value.split())


def collapse_whitespace(text: str) -> str:
    return " ".join(text.split())


def fingerprint(text: str) -> str:
    """SHA-256 hex digest, used to refer to sensitive values (e.g. receipt URLs) in logs."""
    return hashlib.sha256(text.encode()).hexdigest()
