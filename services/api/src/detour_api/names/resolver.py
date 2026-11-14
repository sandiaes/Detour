"""The resolver: from every name of a place to the one an English interface shows.

One function for every language, script and country. The hierarchy and its confidence values are
in :mod:`detour_api.names.config`; the class of place decides which steps may be used (a
restaurant keeps its own name). The original local name is always returned beside the display
name, transliterations are made only by :mod:`detour_api.names.translit` and are always labelled,
and machine translation is never made.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

import structlog

from detour_api.names import config
from detour_api.names.records import NameRecord, dedupe, make
from detour_api.names.scripts import detect_script
from detour_api.names.translit import transliterate

log = structlog.get_logger("detour.names")


@dataclass(frozen=True)
class ResolvedName:
    display: str | None  # None: the place has no name at all (an unnamed café)
    display_type: str  # name type of the display name (config.NAME_TYPES)
    step: str  # the hierarchy step that gave it
    source: str
    source_ref: str | None
    confidence: float
    generated: bool  # made by Detour (transliteration): the app says "Automatically romanized"
    user_override: bool
    local: str | None  # the original local name, None when it is the display name
    local_lang: str | None
    local_script: str | None
    aliases: tuple[str, ...] = field(default=())  # other names, for search and as alternatives
    conflicts: tuple[str, ...] = field(default=())  # high-confidence alternatives that disagree

    @property
    def secondary(self) -> str | None:
        """What the app shows under the display name."""
        return self.local


def _original(records: Sequence[NameRecord], place_class: str) -> NameRecord | None:
    originals = [r for r in records if r.name_type == "original"]
    if not originals:
        return None
    provider = [r for r in originals if r.step == "original"]
    if place_class == "settlement":
        # A city's provider name (GeoNames) is often the English exonym already; the local name
        # is the item's native label when Wikidata gave one.
        native = [r for r in originals if r.step is None and not r.lang.startswith("und")]
        if native:
            return native[0]
    return (provider or originals)[0]


def _allowed(step: str | None, place_class: str) -> bool:
    if step is None:
        return False
    if step == "machine_translation" and not config.ALLOW_MACHINE_TRANSLATION:
        return False
    return step in config.CLASS_STEPS.get(place_class, config.CLASS_STEPS["landmark"])


def resolve(
    records: Iterable[NameRecord],
    *,
    place_class: str = "landmark",
    place_ref: str | None = None,
) -> ResolvedName:
    """Choose the display name for an English interface.

    Order: the configured steps (config.STEPS), restricted to the place's class. Ties inside a
    step keep the order the records were given in. If two English candidates at or above the
    conflict threshold disagree, a candidate the source marks official wins, otherwise the step
    order does; the other is kept as an alias and the conflict is logged.
    """
    pool = dedupe(records)
    original = _original(pool, place_class)
    candidates = [r for r in pool if _allowed(r.step, place_class) and r.step != "original"]

    # Transliteration of the original, only if no source gave anything better and the class
    # allows it: computed here, never stored, always labelled.
    if original is not None and not any(
        config.STEP_ORDER[r.step or "original"] < config.STEP_ORDER["transliteration_specific"]
        for r in candidates
    ):
        lang = original.lang.split("-")[0]
        made = transliterate(original.name, None if lang in ("und", "mul") else lang)
        if made is not None and made.text != original.name:
            step = "transliteration_specific" if made.specific else "transliteration_generic"
            if _allowed(step, place_class):
                candidates.append(
                    make(
                        made.text,
                        lang=f"{lang}-Latn",
                        name_type="automatic_transliteration",
                        source="detour",
                        step=step,
                        method=made.method,
                    )
                )

    candidates.sort(key=lambda r: config.STEP_ORDER[r.step or "original"])
    chosen = candidates[0] if candidates else None
    conflicts: list[str] = []
    if chosen is not None:
        high = [
            r
            for r in candidates
            if r.confidence >= config.CONFLICT_THRESHOLD and r.name_type != "user_override"
        ]
        official = [r for r in high if r.official]
        if official and chosen.name_type != "user_override" and not chosen.official:
            chosen = official[0]
        conflicts = sorted(
            {r.name for r in high if r.name_norm != chosen.name_norm and r is not chosen}
        )
        if conflicts and chosen.name_type != "user_override":
            log.info(
                "place_name_conflict",
                place=place_ref,
                chosen=chosen.name,
                chosen_step=chosen.step,
                alternatives=conflicts,
            )

    display = chosen or original
    aliases = tuple(
        sorted({r.name for r in pool if display is None or r.name_norm != display.name_norm})
    )
    if display is None:
        return ResolvedName(
            display=None,
            display_type="original",
            step="original",
            source="none",
            source_ref=None,
            confidence=0.0,
            generated=False,
            user_override=False,
            local=None,
            local_lang=None,
            local_script=None,
            aliases=aliases,
        )
    local = original if original is not None and original.name_norm != display.name_norm else None
    return ResolvedName(
        display=display.name,
        display_type=display.name_type,
        step=display.step or "original",
        source=display.source,
        source_ref=display.source_ref,
        confidence=display.confidence if display is not original else 1.0,
        generated=display.generated,
        user_override=display.name_type == "user_override",
        local=local.name if local else None,
        local_lang=local.lang if local else None,
        local_script=(local.script or detect_script(local.name)) if local else None,
        aliases=aliases,
        conflicts=tuple(conflicts),
    )
