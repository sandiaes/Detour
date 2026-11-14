"""Search aliases: every name a traveller might type, normalised for matching only.

Display and search are separate: these strings are never shown, and the stored original is never
changed. ``normalize_text`` (shared with the search query) folds case, removes accents from Latin
letters and turns punctuation into spaces; ``fold_ascii`` adds the spelling of German and
Scandinavian letters without accents (Mönchsberg -> moenchsberg), next to the plain one
(monchsberg), so both are found.
"""

from collections.abc import Iterable, Mapping
from dataclasses import replace
from typing import Any

from detour_api.names.records import NameRecord, osm_records
from detour_api.names.translit import transliterate
from detour_api.textnorm import normalize_text

_ASCII_FOLDS = str.maketrans(
    {
        "ä": "ae",
        "ö": "oe",
        "ü": "ue",
        "Ä": "Ae",
        "Ö": "Oe",
        "Ü": "Ue",
        "ß": "ss",
        "ẞ": "SS",
        "å": "aa",
        "Å": "Aa",
        "æ": "ae",
        "Æ": "Ae",
        "ø": "oe",
        "Ø": "Oe",
    }
)
SEPARATOR = "|"
MAX_ALIASES = 60
MAX_CHARS = 4000


def fold_ascii(value: str) -> str:
    """The language-specific ASCII spelling of German and Scandinavian letters."""
    return value.translate(_ASCII_FOLDS)


def search_forms(value: str) -> list[str]:
    """The normalised forms of one name: plain, and with the ASCII folds when they differ."""
    forms = [normalize_text(value)]
    folded = normalize_text(fold_ascii(value))
    if folded != forms[0]:
        forms.append(folded)
    return [f for f in forms if f]


def alias_norm(records: Iterable[NameRecord], exclude: Iterable[str | None] = ()) -> str | None:
    """The ``|``-joined normalised aliases of a place (search only), without the forms already
    held in ``name_norm`` and ``name_en_norm``. The transliteration of the original is included,
    so "Gyeongbokgung" finds 경복궁 even when no source romanized it."""
    skip = {e for e in exclude if e}
    out: list[str] = []
    seen: set[str] = set(skip)
    pool = list(records)
    for record in pool:
        if record.name_type == "original" and record.step == "original":
            made = transliterate(record.name, record.lang.split("-")[0])
            if made is not None:
                pool.append(replace(record, name=made.text, name_type="search_alias", step=None))
    for record in pool:
        for form in search_forms(record.name):
            if form not in seen:
                seen.add(form)
                out.append(form)
    joined: list[str] = []
    size = 0
    for form in out[:MAX_ALIASES]:
        if size + len(form) + 1 > MAX_CHARS:
            break
        joined.append(form)
        size += len(form) + 1
    return SEPARATOR.join(joined) or None


def place_alias_norm(
    name: str | None,
    names_i18n: Mapping[str, str] | None,
    tags: Mapping[str, Any] | None,
    name_en_norm: str | None = None,
) -> str | None:
    """The OpenStreetMap-derived aliases of an imported place (``geo.place.alias_norm``)."""
    records = osm_records(name, names_i18n, tags)
    return alias_norm(records, exclude=(normalize_text(name) if name else None, name_en_norm))
