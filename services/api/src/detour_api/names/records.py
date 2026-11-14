"""The normalized place-name model, and the builders that read each source into it.

A :class:`NameRecord` is one name of one place from one source. Records are built on the fly from
the data Detour already holds (the OpenStreetMap tags of ``geo.place``, the GeoNames city row),
read from ``geo.place_name`` (names fetched from Wikidata and Wikipedia) and from
``app.place_name_override`` (the user's approved name). The original provider name is never
changed: it is always its own record of type ``original``.
"""

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any

from detour_api.names import config
from detour_api.names.scripts import bcp47, detect_script, is_latin, parse_tag_language
from detour_api.textnorm import normalize_text

# OpenStreetMap keys whose value lists several names separated by ";".
_LIST_KEYS = ("alt_name", "old_name")
# A trailing qualifier of a Wikipedia title ("Mercury (planet)"): not part of the name.
_QUALIFIER = re.compile(r"\s*\([^()]*\)\s*$")


@dataclass(frozen=True)
class NameRecord:
    name: str
    lang: str  # BCP 47 language tag ("en", "ja-Latn", "und")
    script: str | None  # ISO 15924
    name_type: str  # one of config.NAME_TYPES
    source: str  # "user", "provider", "osm", "geonames", "wikidata", "enwiki", "detour"
    step: str | None  # the hierarchy step this record can fill (config.STEPS); None: alias only
    source_ref: str | None = None  # "Q123", "node/1", "enwiki:Himeji Castle", GeoNames id
    confidence: float = 0.0
    official: bool = False  # the source marks the name official
    user_approved: bool = False
    retrieved_at: datetime | None = None
    expires_at: datetime | None = None
    method: str | None = None  # how a generated name was made ("ko-rr")
    extra: dict[str, Any] = field(default_factory=dict, compare=False)

    @property
    def name_norm(self) -> str:
        return normalize_text(self.name)

    @property
    def generated(self) -> bool:
        return self.name_type in config.GENERATED_TYPES

    def dedupe_key(self) -> tuple[str, str, str]:
        """Names are the same record when language, source and normalised value agree."""
        return (self.lang, self.source, self.name_norm)


def make(
    name: str,
    *,
    lang: str,
    name_type: str,
    source: str,
    step: str | None,
    source_ref: str | None = None,
    official: bool = False,
    **kwargs: Any,
) -> NameRecord:
    confidence = (
        config.STEP_BY_KEY[step].confidence if step is not None else config.ALIAS_CONFIDENCE
    )
    script = detect_script(name)
    return NameRecord(
        name=name.strip(),
        lang=lang,
        script=script,
        name_type=name_type,
        source=source,
        step=step,
        source_ref=source_ref,
        confidence=confidence,
        official=official,
        **kwargs,
    )


def dedupe(records: Iterable[NameRecord]) -> list[NameRecord]:
    """Keep the first record of each (language, source, normalised value): callers list the better
    record first. Empty names are dropped."""
    seen: set[tuple[str, str, str]] = set()
    out: list[NameRecord] = []
    for record in records:
        if not record.name or not record.name_norm:
            continue
        key = record.dedupe_key()
        if key in seen:
            continue
        seen.add(key)
        out.append(record)
    return out


def _clean(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    value = " ".join(value.split())
    return value or None


def original_language(name: str | None, names_i18n: Mapping[str, str] | None) -> str | None:
    """The language of the original name, when the source states it: the plain language code
    whose ``name:<lang>`` equals ``name`` (``name:de=Festung Hohensalzburg``). Several matching
    codes, or none, leave it unknown."""
    if not name or not names_i18n:
        return None
    norm = normalize_text(name)
    langs = sorted(
        k
        for k, v in names_i18n.items()
        if re.fullmatch(r"[a-z]{2,3}", k) and k not in ("en", "int") and normalize_text(v) == norm
    )
    return langs[0] if len(langs) == 1 else None


def osm_records(
    name: str | None,
    names_i18n: Mapping[str, str] | None,
    tags: Mapping[str, Any] | None,
    *,
    source_ref: str | None = None,
) -> list[NameRecord]:
    """Every name an OpenStreetMap object gives, as records. ``names_i18n`` is the import's
    ``name:*`` map (``int_name`` under ``int``); ``tags`` are the object's other kept tags."""
    names = dict(names_i18n or {})
    tags = dict(tags or {})
    out: list[NameRecord] = []
    original = _clean(name)
    local_lang = original_language(original, names)
    if original:
        out.append(
            make(
                original,
                lang=bcp47(local_lang),
                name_type="original",
                source="osm",
                step="original",
                source_ref=source_ref,
            )
        )

    def add(value: object, step: str | None, name_type: str, lang: str, **kw: Any) -> None:
        text = _clean(value)
        if text:
            out.append(
                make(
                    text,
                    lang=lang,
                    name_type=name_type,
                    source="osm",
                    step=step,
                    source_ref=source_ref,
                    **kw,
                )
            )

    add(names.get("en"), "osm_name_en", "established_english", "en")
    add(
        tags.get("official_name:en"),
        "osm_official_name_en",
        "official_english",
        "en",
        official=True,
    )
    add(tags.get("brand:en"), "osm_brand_en", "localized_brand", "en")
    add(tags.get("short_name:en"), "osm_short_name_en", "established_english", "en")
    int_name = _clean(names.get("int"))
    if int_name:
        # int_name is not always English: it counts only in Latin letters, and only as an
        # international name (never as "official English").
        latin = is_latin(int_name)
        original_latin = bool(original) and is_latin(original or "")
        add(
            int_name,
            "osm_int_name" if latin else None,
            "official_romanization" if latin and not original_latin else "search_alias",
            "und-Latn" if latin else "und",
        )
    # Romanizations the source gives: name:ja-Latn, name:ja_rm, name:zh-Latn-pinyin, name:ko_rm.
    romanized: list[tuple[int, str, str, str]] = []
    for key, value in sorted(names.items()):
        parsed = parse_tag_language(key)
        if parsed is None or key == "en":
            continue
        lang, script, is_roman = parsed
        text = _clean(value)
        if not text:
            continue
        if is_roman and is_latin(text):
            rank = 0 if lang == local_lang else 1
            romanized.append((rank, key, text, bcp47(lang, "Latn")))
        else:
            add(text, None, "search_alias", bcp47(lang, script))
    for _rank, key, text, tag in sorted(romanized):
        add(text, "provider_romanization", "official_romanization", tag, extra={"key": key})
    # Further names only help search.
    add(tags.get("official_name"), None, "search_alias", bcp47(local_lang))
    add(tags.get("short_name"), None, "search_alias", bcp47(local_lang))
    add(tags.get("brand"), None, "search_alias", bcp47(local_lang))
    for key in _LIST_KEYS:
        for part in str(tags.get(key) or "").split(";"):
            add(part, None, "search_alias", bcp47(local_lang))
    return dedupe(out)


def geonames_records(
    name: str | None, ascii_name: str | None, geoname_id: int | None
) -> list[NameRecord]:
    """A GeoNames city: its main name is the provider's name (often already the English exonym,
    but GeoNames does not say which language it is), so it is the original of unknown language."""
    out: list[NameRecord] = []
    ref = str(geoname_id) if geoname_id is not None else None
    if _clean(name):
        out.append(
            make(
                str(name),
                lang="und",
                name_type="original",
                source="geonames",
                step="original",
                source_ref=ref,
            )
        )
    if _clean(ascii_name):
        out.append(
            make(
                str(ascii_name),
                lang="und-Latn",
                name_type="search_alias",
                source="geonames",
                step=None,
                source_ref=ref,
            )
        )
    return dedupe(out)


def wikidata_records(
    qid: str,
    labels: Mapping[str, str],
    aliases: Mapping[str, list[str]],
    enwiki_title: str | None,
    *,
    native_lang: str | None = None,
    retrieved_at: datetime | None = None,
    expires_at: datetime | None = None,
) -> list[NameRecord]:
    """The names a Wikidata item gives: its English label, its English Wikipedia title (without a
    trailing qualifier such as "(castle)"), its labels in other languages and its aliases (search
    only). Nothing is stored beyond these strings and the identifiers.

    ``native_lang`` (cities and areas): the local language; the item's label in it (or its ``mul``
    label) is the local name shown under the English one ("Vienna" / "Wien")."""
    stamp: dict[str, Any] = {"retrieved_at": retrieved_at, "expires_at": expires_at}
    out: list[NameRecord] = []
    en = _clean(labels.get("en"))
    if en:
        out.append(
            make(
                en,
                lang="en",
                name_type="established_english",
                source="wikidata",
                step="wikidata_label_en",
                source_ref=qid,
                **stamp,
            )
        )
    title = _clean(enwiki_title)
    if title:
        shown = _QUALIFIER.sub("", title) or title
        out.append(
            make(
                shown,
                lang="en",
                name_type="established_english",
                source="enwiki",
                step="enwiki_title",
                source_ref=f"enwiki:{title}",
                **stamp,
            )
        )
        if shown != title:
            out.append(
                make(
                    title,
                    lang="en",
                    name_type="search_alias",
                    source="enwiki",
                    step=None,
                    source_ref=f"enwiki:{title}",
                    **stamp,
                )
            )
    native = _clean(labels.get(native_lang or "")) or _clean(labels.get("mul"))
    if native:
        native_tag = native_lang if native_lang and _clean(labels.get(native_lang)) else "mul"
        out.append(
            make(
                native,
                lang=native_tag,
                name_type="original",
                source="wikidata",
                step=None,
                source_ref=qid,
                **stamp,
            )
        )
    for lang, value in sorted(labels.items()):
        text = _clean(value)
        if lang != "en" and text:
            out.append(
                make(
                    text,
                    lang=lang,
                    name_type="search_alias",
                    source="wikidata",
                    step=None,
                    source_ref=qid,
                    **stamp,
                )
            )
    for lang, values in sorted(aliases.items()):
        for value in values[: config.MAX_ALIASES]:
            text = _clean(value)
            if text:
                out.append(
                    make(
                        text,
                        lang=lang,
                        name_type="search_alias",
                        source="wikidata",
                        step=None,
                        source_ref=qid,
                        **stamp,
                    )
                )
    return dedupe(out)


def override_record(name: str, approved_at: datetime | None = None) -> NameRecord:
    return make(
        name,
        lang="en",
        name_type="user_override",
        source="user",
        step="user_override",
        user_approved=True,
        retrieved_at=approved_at,
    )


def stored_record(row: Mapping[str, Any]) -> NameRecord:
    """A row of ``geo.place_name`` (as a mapping) back into a record."""
    step = row.get("step")
    record = make(
        str(row["name"]),
        lang=str(row.get("lang") or "und"),
        name_type=str(row["name_type"]),
        source=str(row["source"]),
        step=step if step in config.STEP_BY_KEY else None,
        source_ref=row.get("source_ref"),
        official=bool(row.get("official") or False),
        retrieved_at=row.get("retrieved_at"),
        expires_at=row.get("expires_at"),
    )
    confidence = row.get("confidence")
    return replace(record, confidence=float(confidence)) if confidence is not None else record
