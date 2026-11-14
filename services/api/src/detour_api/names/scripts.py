"""Which writing system a name uses (ISO 15924 codes), read from the Unicode character names.

No language is guessed from the script: Cyrillic may be Russian, Ukrainian, Serbian or another
language, so the language comes from the source (``name:uk`` equal to ``name``) or stays unknown.
"""

import re
import unicodedata
from collections import Counter

# Prefix of the Unicode character name -> ISO 15924 script code.
_PREFIXES: tuple[tuple[str, str], ...] = (
    ("LATIN", "Latn"),
    ("CYRILLIC", "Cyrl"),
    ("GREEK", "Grek"),
    ("ARABIC", "Arab"),
    ("HEBREW", "Hebr"),
    ("DEVANAGARI", "Deva"),
    ("BENGALI", "Beng"),
    ("GURMUKHI", "Guru"),
    ("GUJARATI", "Gujr"),
    ("ORIYA", "Orya"),
    ("TAMIL", "Taml"),
    ("TELUGU", "Telu"),
    ("KANNADA", "Knda"),
    ("MALAYALAM", "Mlym"),
    ("SINHALA", "Sinh"),
    ("THAI", "Thai"),
    ("LAO", "Laoo"),
    ("KHMER", "Khmr"),
    ("MYANMAR", "Mymr"),
    ("TIBETAN", "Tibt"),
    ("GEORGIAN", "Geor"),
    ("ARMENIAN", "Armn"),
    ("ETHIOPIC", "Ethi"),
    ("HANGUL", "Hang"),
    ("HIRAGANA", "Hira"),
    ("KATAKANA", "Kana"),
    ("CJK", "Hani"),
    ("MONGOLIAN", "Mong"),
)

_BCP47 = re.compile(r"^(?P<lang>[a-z]{2,3})(?:[-_](?P<script>[A-Z][a-z]{3}))?(?:[-_].*)?$")


def char_script(char: str) -> str | None:
    """The script of one letter; None for digits, spaces, punctuation and marks of no script."""
    if not char.isalpha():
        return None
    name = unicodedata.name(char, "")
    if char == "ー" or name.startswith("KATAKANA-HIRAGANA"):
        return "Kana"
    if name.startswith("HALFWIDTH KATAKANA"):
        return "Kana"
    if name.startswith("FULLWIDTH LATIN"):
        return "Latn"
    for prefix, code in _PREFIXES:
        if name.startswith(prefix):
            return code
    return "Zyyy"


def scripts_of(text: str) -> Counter[str]:
    """How many letters of each script the text has."""
    return Counter(s for c in text if (s := char_script(c)) is not None)


def detect_script(text: str) -> str | None:
    """The ISO 15924 code of the text's writing system.

    Japanese (kana with or without kanji) is ``Jpan``; Korean with hanja is ``Kore``; a name in
    two unrelated scripts (``Café 東京``) is the script with the most letters. None for a text
    without letters.
    """
    counts = scripts_of(text)
    if not counts:
        return None
    keys = set(counts)
    if keys & {"Hira", "Kana"}:
        return "Jpan" if keys & {"Hani"} or len(keys & {"Hira", "Kana"}) == 2 else _one_of(counts)
    if "Hang" in keys and "Hani" in keys:
        return "Kore"
    return _one_of(counts)


def _one_of(counts: Counter[str]) -> str:
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]


def is_mixed(text: str) -> bool:
    """True if the text uses letters of more than one script (Japanese kana plus kanji counts as
    one writing system)."""
    keys = set(scripts_of(text))
    keys -= {"Hira", "Kana", "Hani"} if keys & {"Hira", "Kana"} else set()
    return len(keys) + (1 if set(scripts_of(text)) & {"Hira", "Kana"} else 0) > 1


def is_latin(text: str) -> bool:
    """Every letter is Latin (and there is at least one)."""
    counts = scripts_of(text)
    return bool(counts) and set(counts) == {"Latn"}


def parse_tag_language(key: str) -> tuple[str, str | None, bool] | None:
    """Read an OpenStreetMap language suffix (``ja``, ``ja-Latn``, ``zh-Latn-pinyin``, ``ja_rm``,
    ``ko_rm``, ``zh_pinyin``) as (language, script, romanized). None if it is not a language."""
    if key in ("int", "en"):
        return None if key == "int" else ("en", "Latn", False)
    lowered = key.replace("_", "-")
    if lowered.endswith(("-rm", "-pinyin", "-kana")) and not lowered.endswith("-Latn"):
        base = lowered.split("-")[0]
        if lowered.endswith("-kana"):
            return (base, "Kana", False) if re.fullmatch(r"[a-z]{2,3}", base) else None
        return (base, "Latn", True) if re.fullmatch(r"[a-z]{2,3}", base) else None
    match = _BCP47.match(key)
    if not match:
        return None
    script = match.group("script")
    return match.group("lang"), script, script == "Latn"


def bcp47(lang: str | None, script: str | None = None) -> str:
    """A BCP 47 tag from a language and an optional script: ``ja-Latn``, ``und`` when unknown."""
    base = lang or "und"
    return f"{base}-{script}" if script else base
