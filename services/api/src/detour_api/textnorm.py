"""Text normalisation shared by the importers and the search endpoints.

Search matches ``normalize_text(query)`` against columns that were filled with the same function,
so both sides always agree. Accents are removed only from Latin letters: stripping combining
marks from Japanese kana, for example, would change the word.
"""

import hashlib
import re
import unicodedata
import uuid

_SPECIAL_LATIN = str.maketrans(
    {"ø": "o", "đ": "d", "ł": "l", "\u0131": "i", "æ": "ae", "œ": "oe", "þ": "th", "ð": "d"}
)
_SPACES = re.compile(r"\s+")


def normalize_text(value: str) -> str:
    """Lower case, accents removed from Latin letters, punctuation turned into spaces."""
    out: list[str] = []
    for char in unicodedata.normalize("NFC", value):
        decomposed = unicodedata.normalize("NFKD", char)
        if len(decomposed) > 1 and unicodedata.name(decomposed[0], "").startswith("LATIN"):
            out.append(decomposed[0])
        else:
            out.append(char)
    folded = "".join(out).casefold().translate(_SPECIAL_LATIN)
    cleaned = "".join(c if c.isalnum() else " " for c in folded)
    return _SPACES.sub(" ", cleaned).strip()


def has_latin_letters(value: str) -> bool:
    """True if the text contains at least one letter of the Latin script."""
    return any(c.isalpha() and unicodedata.name(c, "").startswith("LATIN") for c in value)


def stable_uuid(namespace: str, reference: str) -> uuid.UUID:
    """A deterministic UUID (RFC 9562 version 8, custom) derived from a source reference.

    The same ``namespace`` and ``reference`` always give the same identifier, which is what keeps
    place identifiers stable across imports (docs/data-model.md).
    """
    digest = bytearray(hashlib.sha1(f"detour:{namespace}:{reference}".encode()).digest()[:16])  # noqa: S324
    digest[6] = (digest[6] & 0x0F) | 0x80
    digest[8] = (digest[8] & 0x3F) | 0x80
    return uuid.UUID(bytes=bytes(digest))
