"""Transliteration adapters: only for scripts whose reading can be inferred from the letters.

Two levels, both labelled "automatically romanized" wherever they are shown:

* **Language-specific** (confidence 0.70): Greek (ELOT 743, simplified), Cyrillic by language
  (Russian BGN/PCGN without diacritics, Ukrainian national system of 2010, Bulgarian Streamlined
  System, Serbian and Macedonian official Latin alphabets), Korean Hangul (Revised Romanization,
  with the linking rule) and Japanese kana (Hepburn). The language must be known for Cyrillic.
* **Generic** (confidence 0.35, the last resort): Cyrillic of unknown language (the Russian table),
  Georgian (national system), Armenian, Devanagari (letter by letter, final schwa dropped for
  Hindi).

**Never transliterated:** Han characters (Chinese hanzi, Japanese kanji, Korean hanja: the reading
cannot be inferred), Arabic and Urdu, Hebrew, Thai, Lao, Khmer, Burmese, Tibetan and every script
not listed. A name that mixes such a script with a safe one is not transliterated at all.
"""

import unicodedata
from collections.abc import Callable
from dataclasses import dataclass

from detour_api.names.scripts import char_script, scripts_of


@dataclass(frozen=True)
class Transliteration:
    text: str
    method: str  # "el-elot743", "ru-bgn", "ko-rr", "ja-hepburn", "generic-cyrl", ...
    specific: bool  # language-specific (0.70) rather than generic (0.35)


# -- Greek ---------------------------------------------------------------------------------------

_GREEK_DIGRAPHS = {
    "ου": "ou",
    "αυ": "av",
    "ευ": "ev",
    "ηυ": "iv",
    "γγ": "ng",
    "γκ": "gk",
    "γξ": "nx",
    "γχ": "nch",
    "μπ": "mp",
    "ντ": "nt",
    "αι": "ai",
    "ει": "ei",
    "οι": "oi",
}
_GREEK = {
    "α": "a",
    "β": "v",
    "γ": "g",
    "δ": "d",
    "ε": "e",
    "ζ": "z",
    "η": "i",
    "θ": "th",
    "ι": "i",
    "κ": "k",
    "λ": "l",
    "μ": "m",
    "ν": "n",
    "ξ": "x",
    "ο": "o",
    "π": "p",
    "ρ": "r",
    "σ": "s",
    "ς": "s",
    "τ": "t",
    "υ": "y",
    "φ": "f",
    "χ": "ch",
    "ψ": "ps",
    "ω": "o",
}


def _strip_marks(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text)
    return unicodedata.normalize(
        "NFC", "".join(c for c in decomposed if not unicodedata.combining(c))
    )


def _greek(text: str) -> str:
    return _by_table(_strip_marks(text), _GREEK_DIGRAPHS, _GREEK)


# -- Cyrillic ------------------------------------------------------------------------------------

_RU = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "е": "e",
    "ё": "yo",
    "ж": "zh",
    "з": "z",
    "и": "i",
    "й": "y",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "kh",
    "ц": "ts",
    "ч": "ch",
    "ш": "sh",
    "щ": "shch",
    "ъ": "",
    "ы": "y",
    "ь": "",
    "э": "e",
    "ю": "yu",
    "я": "ya",
}
_UK = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "h",
    "ґ": "g",
    "д": "d",
    "е": "e",
    "є": "ie",
    "ж": "zh",
    "з": "z",
    "и": "y",
    "і": "i",
    "ї": "i",
    "й": "i",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "kh",
    "ц": "ts",
    "ч": "ch",
    "ш": "sh",
    "щ": "shch",
    "ь": "",
    "ю": "iu",
    "я": "ia",
    "'": "",
    "’": "",
}
_UK_INITIAL = {"є": "ye", "ї": "yi", "й": "y", "ю": "yu", "я": "ya"}
_BG = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "е": "e",
    "ж": "zh",
    "з": "z",
    "и": "i",
    "й": "y",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "h",
    "ц": "ts",
    "ч": "ch",
    "ш": "sh",
    "щ": "sht",
    "ъ": "a",
    "ь": "y",
    "ю": "yu",
    "я": "ya",
}
_SR = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "ђ": "đ",
    "е": "e",
    "ж": "ž",
    "з": "z",
    "и": "i",
    "ј": "j",
    "к": "k",
    "л": "l",
    "љ": "lj",
    "м": "m",
    "н": "n",
    "њ": "nj",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "ћ": "ć",
    "у": "u",
    "ф": "f",
    "х": "h",
    "ц": "c",
    "ч": "č",
    "џ": "dž",
    "ш": "š",
}
_MK = {
    **{k: v for k, v in _SR.items() if k not in ("ђ", "ћ")},
    "ѓ": "gj",
    "ѕ": "dz",
    "ќ": "kj",
}


def _cyrillic(table: dict[str, str], initial: dict[str, str] | None = None) -> Callable[[str], str]:
    def run(text: str) -> str:
        out: list[str] = []
        previous_letter = False
        for char in text:
            lower = char.lower()
            if initial and not previous_letter and lower in initial:
                piece = initial[lower]
            elif lower in table:
                piece = table[lower]
            else:
                piece = char
            if char != lower and piece:
                piece = piece[0].upper() + piece[1:]
            out.append(piece)
            previous_letter = char.isalpha()
        return "".join(out)

    return run


def _ukrainian(text: str) -> str:
    # The 2010 system writes зг as zgh, so it is not read as zh.
    return _cyrillic(_UK, _UK_INITIAL)(text.replace("зг", "zgh").replace("Зг", "Zgh"))


def _bulgarian(text: str) -> str:
    # The Streamlined System writes a word-final "ия" as "ia".
    words = [
        w[:-2] + ("ia" if w[-2:].islower() else "IA") if w.lower().endswith("ия") else w
        for w in text.split(" ")
    ]
    return _cyrillic(_BG)(" ".join(words))


# -- Korean (Revised Romanization) ---------------------------------------------------------------

_HANGUL_INITIALS = [
    "g",
    "kk",
    "n",
    "d",
    "tt",
    "r",
    "m",
    "b",
    "pp",
    "s",
    "ss",
    "",
    "j",
    "jj",
    "ch",
    "k",
    "t",
    "p",
    "h",
]
_HANGUL_VOWELS = [
    "a",
    "ae",
    "ya",
    "yae",
    "eo",
    "e",
    "yeo",
    "ye",
    "o",
    "wa",
    "wae",
    "oe",
    "yo",
    "u",
    "wo",
    "we",
    "wi",
    "yu",
    "eu",
    "ui",
    "i",
]
_HANGUL_FINALS = [
    "",
    "k",
    "k",
    "k",
    "n",
    "n",
    "n",
    "t",
    "l",
    "k",
    "m",
    "l",
    "l",
    "l",
    "p",
    "l",
    "m",
    "p",
    "p",
    "t",
    "t",
    "ng",
    "t",
    "t",
    "k",
    "t",
    "p",
    "t",
]
# A final consonant read as the next syllable's initial when that syllable starts with ㅇ.
_HANGUL_LINKED = [
    "",
    "g",
    "kk",
    "ks",
    "n",
    "nj",
    "nh",
    "d",
    "r",
    "lg",
    "lm",
    "lb",
    "ls",
    "lt",
    "lp",
    "lh",
    "m",
    "b",
    "bs",
    "s",
    "ss",
    "ng",
    "j",
    "ch",
    "k",
    "t",
    "p",
    "h",
]


def _hangul_parts(char: str) -> tuple[int, int, int] | None:
    code = ord(char) - 0xAC00
    if not 0 <= code < 11172:
        return None
    return code // 588, (code % 588) // 28, code % 28


def _korean(text: str) -> str:
    words = []
    for word in text.split(" "):
        out: list[str] = []
        chars = list(word)
        for index, char in enumerate(chars):
            parts = _hangul_parts(char)
            if parts is None:
                out.append(char)
                continue
            initial, vowel, final = parts
            nxt = _hangul_parts(chars[index + 1]) if index + 1 < len(chars) else None
            syllable = _HANGUL_INITIALS[initial] + _HANGUL_VOWELS[vowel]
            if out and out[-1] == "l" and initial == 5:  # ㄹ + ㄹ is written ll
                syllable = "l" + syllable[1:]
            # ㄴ before ㄹ, or ㄹ before ㄴ, is read and written ll (신라 Silla, 설날 Seollal).
            if final == 4 and nxt is not None and nxt[0] == 5:
                final = 8
            if out and out[-1] == "l" and initial == 2:
                syllable = "l" + syllable[1:]
            if final and nxt is not None and nxt[0] == 11 and final != 21:
                syllable += _HANGUL_LINKED[final]
                out.append(syllable)
                continue
            out.append(syllable)
            if final:
                out.append(_HANGUL_FINALS[final])
        joined = "".join(out)
        words.append(joined[:1].upper() + joined[1:])
    return " ".join(words)


# -- Japanese kana (Hepburn) ---------------------------------------------------------------------

_KANA_BASE = {
    "あ": "a",
    "い": "i",
    "う": "u",
    "え": "e",
    "お": "o",
    "か": "ka",
    "き": "ki",
    "く": "ku",
    "け": "ke",
    "こ": "ko",
    "さ": "sa",
    "し": "shi",
    "す": "su",
    "せ": "se",
    "そ": "so",
    "た": "ta",
    "ち": "chi",
    "つ": "tsu",
    "て": "te",
    "と": "to",
    "な": "na",
    "に": "ni",
    "ぬ": "nu",
    "ね": "ne",
    "の": "no",
    "は": "ha",
    "ひ": "hi",
    "ふ": "fu",
    "へ": "he",
    "ほ": "ho",
    "ま": "ma",
    "み": "mi",
    "む": "mu",
    "め": "me",
    "も": "mo",
    "や": "ya",
    "ゆ": "yu",
    "よ": "yo",
    "ら": "ra",
    "り": "ri",
    "る": "ru",
    "れ": "re",
    "ろ": "ro",
    "わ": "wa",
    "ゐ": "i",
    "ゑ": "e",
    "を": "o",
    "ん": "n",
    "が": "ga",
    "ぎ": "gi",
    "ぐ": "gu",
    "げ": "ge",
    "ご": "go",
    "ざ": "za",
    "じ": "ji",
    "ず": "zu",
    "ぜ": "ze",
    "ぞ": "zo",
    "だ": "da",
    "ぢ": "ji",
    "づ": "zu",
    "で": "de",
    "ど": "do",
    "ば": "ba",
    "び": "bi",
    "ぶ": "bu",
    "べ": "be",
    "ぼ": "bo",
    "ぱ": "pa",
    "ぴ": "pi",
    "ぷ": "pu",
    "ぺ": "pe",
    "ぽ": "po",
    "ぁ": "a",
    "ぃ": "i",
    "ぅ": "u",
    "ぇ": "e",
    "ぉ": "o",
    "ゔ": "vu",
}
_KANA_SMALL_Y = {"ゃ": "a", "ゅ": "u", "ょ": "o"}
_MACRON = {"a": "ā", "i": "ī", "u": "ū", "e": "ē", "o": "ō"}


def _to_hiragana(char: str) -> str:
    code = ord(char)
    return chr(code - 0x60) if 0x30A1 <= code <= 0x30F6 else char


def _japanese_kana(text: str) -> str:
    chars = [_to_hiragana(c) for c in text]
    out: list[str] = []
    double_next = False
    index = 0
    while index < len(chars):
        char = chars[index]
        nxt = chars[index + 1] if index + 1 < len(chars) else ""
        if char == "っ":
            double_next = True
            index += 1
            continue
        if char == "ー":
            if out and out[-1] and out[-1][-1] in _MACRON:
                out[-1] = out[-1][:-1] + _MACRON[out[-1][-1]]
            index += 1
            continue
        if char in _KANA_BASE:
            piece = _KANA_BASE[char]
            if nxt in _KANA_SMALL_Y and piece.endswith("i") and len(piece) > 1:
                stem = piece[:-1]
                piece = (stem if stem in ("sh", "ch", "j") else stem + "y") + _KANA_SMALL_Y[nxt]
                index += 1
            if char == "ん" and index + 1 < len(chars):
                follow = _KANA_BASE.get(chars[index + 1], "")
                if follow[:1] in ("a", "i", "u", "e", "o", "y"):
                    piece = "n'"
            if double_next and piece:
                piece = ("t" if piece.startswith("ch") else piece[0]) + piece
            double_next = False
            out.append(piece)
        else:
            out.append(char)
        index += 1
    joined = "".join(out)
    return " ".join(w[:1].upper() + w[1:] for w in joined.split(" "))


# -- Generic tables (the last resort) ------------------------------------------------------------

_GEORGIAN = dict(
    zip(
        "აბგდევზთიკლმნოპჟრსტუფქღყშჩცძწჭხჯჰ",
        [
            "a",
            "b",
            "g",
            "d",
            "e",
            "v",
            "z",
            "t",
            "i",
            "k",
            "l",
            "m",
            "n",
            "o",
            "p",
            "zh",
            "r",
            "s",
            "t",
            "u",
            "p",
            "k",
            "gh",
            "q",
            "sh",
            "ch",
            "ts",
            "dz",
            "ts",
            "ch",
            "kh",
            "j",
            "h",
        ],
        strict=True,
    )
)
_ARMENIAN = dict(
    zip(
        "աբգդեզէըթժիլխծկհձղճմյնշոչպջռսվտրցւփքօֆ",
        [
            "a",
            "b",
            "g",
            "d",
            "e",
            "z",
            "e",
            "y",
            "t",
            "zh",
            "i",
            "l",
            "kh",
            "ts",
            "k",
            "h",
            "dz",
            "gh",
            "ch",
            "m",
            "y",
            "n",
            "sh",
            "o",
            "ch",
            "p",
            "j",
            "r",
            "s",
            "v",
            "t",
            "r",
            "ts",
            "w",
            "p",
            "k",
            "o",
            "f",
        ],
        strict=True,
    )
)
_ARMENIAN_DIGRAPHS = {"ու": "u"}
_ARMENIAN["և"] = "ev"

_DEVA_CONSONANTS = dict(
    zip(
        "कखगघङचछजझञटठडढणतथदधनपफबभमयरलवशषसह",
        [
            "k",
            "kh",
            "g",
            "gh",
            "n",
            "ch",
            "chh",
            "j",
            "jh",
            "n",
            "t",
            "th",
            "d",
            "dh",
            "n",
            "t",
            "th",
            "d",
            "dh",
            "n",
            "p",
            "ph",
            "b",
            "bh",
            "m",
            "y",
            "r",
            "l",
            "v",
            "sh",
            "sh",
            "s",
            "h",
        ],
        strict=True,
    )
)
_DEVA_VOWELS = dict(
    zip("अआइईउऊऋएऐओऔ", ["a", "a", "i", "i", "u", "u", "ri", "e", "ai", "o", "au"], strict=True)
)
_DEVA_SIGNS = dict(zip("ािीुूृेैोौ", ["a", "i", "i", "u", "u", "ri", "e", "ai", "o", "au"], strict=True))
_DEVA_NUKTA = {"क": "q", "ख": "kh", "ग": "gh", "ज": "z", "फ": "f", "ड": "r", "ढ": "rh"}
_VIRAMA, _NUKTA = "्", "़"


def _devanagari(text: str, drop_final_schwa: bool) -> str:
    text = unicodedata.normalize("NFD", text)
    words = []
    for word in text.split(" "):
        out: list[str] = []
        index = 0
        while index < len(word):
            char = word[index]
            nxt = word[index + 1] if index + 1 < len(word) else ""
            if char in _DEVA_CONSONANTS:
                piece = _DEVA_CONSONANTS[char]
                if nxt == _NUKTA:
                    piece = _DEVA_NUKTA.get(char, piece)
                    index += 1
                    nxt = word[index + 1] if index + 1 < len(word) else ""
                if nxt == _VIRAMA:
                    index += 1
                elif nxt in _DEVA_SIGNS:
                    piece += _DEVA_SIGNS[nxt]
                    index += 1
                else:
                    piece += "a"
                out.append(piece)
            elif char in _DEVA_VOWELS:
                out.append(_DEVA_VOWELS[char])
            elif char in ("ं", "ँ"):
                out.append("n")
            elif char == "ः":
                out.append("h")
            else:
                out.append(char)
            index += 1
        joined = "".join(out)
        if (
            drop_final_schwa
            and len(joined) > 2
            and joined.endswith("a")
            and word[-1:] in _DEVA_CONSONANTS
        ):
            joined = joined[:-1]
        words.append(joined[:1].upper() + joined[1:])
    return " ".join(words)


def _by_table(text: str, digraphs: dict[str, str], table: dict[str, str]) -> str:
    out: list[str] = []
    index = 0
    while index < len(text):
        pair = text[index : index + 2]
        if pair.lower() in digraphs:
            piece = digraphs[pair.lower()]
            if pair[0].isupper():
                piece = piece[:1].upper() + piece[1:]
            out.append(piece)
            index += 2
            continue
        char = text[index]
        piece = table.get(char.lower(), char)
        if char.isupper() and piece:
            piece = piece[:1].upper() + piece[1:]
        out.append(piece)
        index += 1
    return "".join(out)


def _title_words(text: str) -> str:
    return " ".join(w[:1].upper() + w[1:] for w in text.split(" "))


# -- The adapters --------------------------------------------------------------------------------

# Scripts that are never transliterated: the reading cannot be inferred from the letters.
UNSAFE_SCRIPTS = frozenset({"Hani", "Arab", "Hebr", "Thai", "Laoo", "Khmr", "Mymr", "Tibt", "Zyyy"})

_CYRILLIC_BY_LANGUAGE: dict[str, tuple[str, Callable[[str], str]]] = {
    "ru": ("ru-bgn", _cyrillic(_RU)),
    "be": ("ru-bgn", _cyrillic(_RU)),
    "uk": ("uk-2010", _ukrainian),
    "bg": ("bg-streamlined", _bulgarian),
    "sr": ("sr-latin", _cyrillic(_SR)),
    "mk": ("mk-latin", _cyrillic(_MK)),
}


def transliterate(text: str, lang: str | None) -> Transliteration | None:
    """A Latin transliteration of ``text`` when it is safe, else None.

    ``lang`` is the name's language when the source states it (None if unknown). Latin letters,
    digits and punctuation pass through, so a mixed name ("Café Москва") keeps its Latin part; a
    name with any letter of an unsafe script is never transliterated.
    """
    counts = scripts_of(text)
    keys = set(counts) - {"Latn"}
    if not keys or keys & UNSAFE_SCRIPTS:
        return None
    if keys <= {"Hira", "Kana"}:
        result, method, specific = _japanese_kana(text), "ja-hepburn", True
    elif keys == {"Hang"}:
        result, method, specific = _korean(text), "ko-rr", True
    elif keys == {"Grek"}:
        result, method, specific = _title_words(_greek(text)), "el-elot743", True
    elif keys == {"Cyrl"}:
        if lang in _CYRILLIC_BY_LANGUAGE:
            method, run = _CYRILLIC_BY_LANGUAGE[lang]
            result, specific = run(text), True
        else:
            result, method, specific = _cyrillic(_RU)(text), "generic-cyrl", False
    elif keys == {"Geor"}:
        result, method, specific = (
            _title_words(_by_table(text, {}, _GEORGIAN)),
            "generic-geor",
            False,
        )
    elif keys == {"Armn"}:
        result = _title_words(_by_table(text, _ARMENIAN_DIGRAPHS, _ARMENIAN))
        method, specific = "generic-armn", False
    elif keys == {"Deva"}:
        result = _devanagari(text, drop_final_schwa=lang in (None, "hi", "mr", "ne"))
        method, specific = "generic-deva", False
    else:
        return None
    # Anything left that is not Latin means a letter the table does not know: give up.
    if any(char_script(c) not in (None, "Latn") for c in result):
        return None
    result = " ".join(result.split())
    return Transliteration(result, method, specific) if result else None
