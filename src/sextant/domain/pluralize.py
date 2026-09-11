"""English pluralization, as the JVM library a Spring Data REST app resolves
performs it (2O design §2b, CP-2).

**Attribution.** This module is a port of the rule set of **Evo Inflector**
(`org.atteo:evo-inflector`, Copyright 2011 Atteo), which is licensed under the
Apache License, Version 2.0 — http://www.apache.org/licenses/LICENSE-2.0. A
port of a rule set is a derivative of it, so Apache-2.0 §4's attribution
travels with it: `LICENSE-evo-inflector`, beside this file, carries the origin
and the licence text in full, and `README.md`'s Dependencies section names it
where a reader looks for what this repository took from elsewhere. Evo
Inflector is itself an
implementation of Damian Conway's *An Algorithmic Approach to English
Pluralization*; this port mirrors Evo's own `English`/`TwoFormInflector`
classes rule for rule and in their registration order, because the answer that
matters is what THAT library returns, not what English arguably ought to do.

**Why a port and not a dependency.** The rules are English pluralization, the
port takes no new Python dependency into Sextant, and the port must mirror the
exact library the analysed JVM application resolved — a different Python
pluralizer that is "better" would be wrong here by definition (DR-6).

**Which mode is ported, and the condition that would make that wrong.** Evo
ships two modes. Only `MODE.ENGLISH_ANGLICIZED` is ported, because that is the
mode the static `English.plural(String)` entry point uses, and that entry point
is the one Spring HATEOAS's `EvoInflectorLinkRelationProvider` calls
(`scripts/probes/cp2_data_rest.md` records the live stack). Porting
`ENGLISH_CLASSICAL` would be code no caller can reach. That holds as long as
nothing in this codebase pluralizes for a caller that selects the classical
mode — if one ever does, this module gains the mode rather than approximating
it.

**Who decides whether to call this.** Spring HATEOAS selects its relation
provider by classpath presence, so pluralization is a property of the analysed
application's classpath and not of English. This module therefore answers only
"what is the plural"; the caller decides whether the framework it is mirroring
pluralizes at all. (For Spring Data REST specifically, CP-2 established that it
always does: `spring-data-rest-core` depends on `org.atteo:evo-inflector` at
compile scope, non-optionally, and the application fails at runtime without it.)

**Determinism (NFR-1).** Pure, table-driven, no I/O, no locale: one word in,
one word out, the same on every machine.
"""

import re

# Evo's own `English` categories, verbatim and in its own declaration order.
# Each is a suffix list a `CategoryRule` matches case-insensitively (see
# `_category`), never a word list — `"radix"` matches `"helix"`'s sibling
# `"appendix"` only if the suffix itself is a suffix of it.
_CATEGORY_EX_ICES = ("codex", "murex", "silex")

_CATEGORY_IX_ICES = ("radix", "helix")

_CATEGORY_UM_A = (
    "bacterium",
    "agendum",
    "desideratum",
    "erratum",
    "stratum",
    "datum",
    "ovum",
    "extremum",
    "candelabrum",
)

# Always us -> i
_CATEGORY_US_I = (
    "alumnus",
    "alveolus",
    "bacillus",
    "bronchus",
    "locus",
    "nucleus",
    "stimulus",
    "meniscus",
    "thesaurus",
)

_CATEGORY_ON_A = (
    "criterion",
    "perihelion",
    "aphelion",
    "phenomenon",
    "prolegomenon",
    "noumenon",
    "organon",
    "asyndeton",
    "hyperbaton",
)

_CATEGORY_A_AE = ("alumna", "alga", "vertebra", "persona")

# Always o -> os
_CATEGORY_O_OS = (
    "albino",
    "archipelago",
    "armadillo",
    "commando",
    "crescendo",
    "fiasco",
    "ditto",
    "dynamo",
    "embryo",
    "ghetto",
    "guano",
    "inferno",
    "jumbo",
    "lumbago",
    "magneto",
    "manifesto",
    "medico",
    "octavo",
    "photo",
    "pro",
    "quarto",
    "canto",
    "lingo",
    "generalissimo",
    "stylo",
    "rhino",
    "casino",
    "auto",
    "macro",
    "zero",
    "todo",
)

# Classical o -> i (anglicized -> os, which is the mode ported here)
_CATEGORY_O_I = (
    "solo",
    "soprano",
    "basso",
    "alto",
    "contralto",
    "tempo",
    "piano",
    "virtuoso",
)

# -a to -as (anglicized) or -ata (classical)
_CATEGORY_A_ATA = (
    "anathema",
    "enema",
    "oedema",
    "bema",
    "enigma",
    "sarcoma",
    "carcinoma",
    "gumma",
    "schema",
    "charisma",
    "lemma",
    "soma",
    "diploma",
    "lymphoma",
    "stigma",
    "dogma",
    "magma",
    "stoma",
    "drama",
    "melisma",
    "trauma",
    "edema",
    "miasma",
)

_CATEGORY_IS_IDES = ("iris", "clitoris")

# -us to -uses (anglicized) or -us (classical)
_CATEGORY_US_US = (
    "apparatus",
    "impetus",
    "prospectus",
    "cantus",
    "nexus",
    "sinus",
    "coitus",
    "plexus",
    "status",
    "hiatus",
)

_CATEGORY_S_ES = (
    "acropolis",
    "chaos",
    "lens",
    "aegis",
    "cosmos",
    "mantis",
    "alias",
    "dais",
    "marquis",
    "asbestos",
    "digitalis",
    "metropolis",
    "atlas",
    "epidermis",
    "pathos",
    "bathos",
    "ethos",
    "pelvis",
    "bias",
    "gas",
    "polis",
    "caddis",
    "glottis",
    "rhinoceros",
    "cannabis",
    "glottis",
    "sassafras",
    "canvas",
    "ibis",
    "trellis",
)

_CATEGORY_MAN_MANS = (
    "human",
    "Alabaman",
    "Bahaman",
    "Burman",
    "German",
    "Hiroshiman",
    "Liman",
    "Nakayaman",
    "Oklahoman",
    "Panaman",
    "Selman",
    "Sonaman",
    "Tacoman",
    "Yakiman",
    "Yokohaman",
    "Yuman",
)

# Evo's `uncountable` list — words that do not inflect, registered FIRST so
# nothing below can reach them.
_UNCOUNTABLE = (
    # endings
    "fish",
    "ois",
    "sheep",
    "deer",
    "pox",
    "itis",
    # words
    "bison",
    "flounder",
    "pliers",
    "bream",
    "gallows",
    "proceedings",
    "breeches",
    "graffiti",
    "rabies",
    "britches",
    "headquarters",
    "salmon",
    "carp",
    "herpes",
    "scissors",
    "chassis",
    "high-jinks",
    "sea-bass",
    "clippers",
    "homework",
    "series",
    "cod",
    "innings",
    "shears",
    "contretemps",
    "jackanapes",
    "species",
    "corps",
    "mackerel",
    "swine",
    "debris",
    "measles",
    "trout",
    "diabetes",
    "mews",
    "tuna",
    "djinn",
    "mumps",
    "whiting",
    "eland",
    "news",
    "wildebeest",
    "elk",
    "pincers",
    "sugar",
)

# Evo's `irregular` pairs. The base set, then the ANGLICIZED set — the two
# `irregular(...)` calls the ported mode makes, in that order.
_IRREGULAR = (
    ("child", "children"),
    ("ephemeris", "ephemerides"),
    ("mongoose", "mongoose"),
    ("mythos", "mythoi"),
    ("soliloquy", "soliloquies"),
    ("trilby", "trilbys"),
    ("genus", "genera"),
    ("quiz", "quizzes"),
    ("beef", "beefs"),
    ("brother", "brothers"),
    ("cow", "cows"),
    ("genie", "genies"),
    ("money", "moneys"),
    ("octopus", "octopuses"),
    ("opus", "opuses"),
)


def _regexp(pattern: str, replacement: str) -> "tuple[re.Pattern[str], str]":
    """Evo's `RegExpRule`: the FIRST match anywhere in the word is replaced and
    the tail appended (`Matcher.find` + `appendReplacement` + `appendTail`),
    case-insensitively. `re.subn(..., count=1)` is that, and the count is what
    tells a match from a miss — Evo returns `null` for a miss, and a rule that
    silently returned the word unchanged would stop the ladder at the wrong
    rung."""
    return re.compile(pattern, re.IGNORECASE), replacement


def _irregular(singular: str, plural: str) -> "tuple[re.Pattern[str], str]":
    """Evo's `TwoFormInflector.irregular`, for a pair whose two forms START
    WITH THE SAME LETTER: one case-insensitive rule that captures the word's
    own first character and re-emits it, so `Child` pluralizes to `Children`
    rather than to `children`.

    Evo's other branch — a pair whose forms start with DIFFERENT letters, which
    it registers as two case-pinned rules — is not ported because no pair in
    the anglicized rule set above is of that shape. That holds as long as the
    pairs stay as Evo published them; a future pair like `person`/`people`
    would need the second branch, and `_build` asserts the shape rather than
    letting it pass silently.
    """
    assert singular[0].lower() == plural[0].lower(), (
        f"Evo's differing-first-letter `irregular` branch is not ported ({singular} -> {plural})"
    )
    return _regexp(f"({re.escape(singular[0])}){re.escape(singular[1:])}$", "\\1" + plural[1:])


def _category(
    suffixes: "tuple[str, ...]", singular: str, plural: str
) -> "tuple[tuple[str, ...], str, str]":
    """Evo's `CategoryRule`: when the lower-cased word ends with any suffix in
    the list, its trailing `singular` is replaced by `plural` — the cut is made
    on the ORIGINAL word, so case is preserved ahead of the suffix."""
    return suffixes, singular, plural


# Evo's `English(MODE.ENGLISH_ANGLICIZED)` constructor, rule for rule, in its
# own registration order — the order IS the algorithm: the first rule that
# matches answers, so moving one line changes the library's answer.
_RULES: "list[tuple[re.Pattern[str], str] | tuple[tuple[str, ...], str, str]]" = [
    # 2. Words that do not inflect in the plural.
    _category(_UNCOUNTABLE, "", ""),
    # 4. Standard irregular plurals (base set, then anglicized).
    *(_irregular(singular, plural) for singular, plural in _IRREGULAR),
    _category(_CATEGORY_MAN_MANS, "", "s"),
    # 5. Irregular inflections for common suffixes.
    _regexp("man$", "men"),
    _regexp("([lm])ouse$", "\\1ice"),
    _regexp("tooth$", "teeth"),
    _regexp("goose$", "geese"),
    _regexp("foot$", "feet"),
    _regexp("zoon$", "zoa"),
    _regexp("([csx])is$", "\\1es"),
    # 6. Fully assimilated classical inflections.
    _category(_CATEGORY_EX_ICES, "ex", "ices"),
    _category(_CATEGORY_IX_ICES, "ix", "ices"),
    _category(_CATEGORY_UM_A, "um", "a"),
    _category(_CATEGORY_ON_A, "on", "a"),
    _category(_CATEGORY_A_AE, "a", "ae"),
    # 7. (The classical variants Evo registers only in ENGLISH_CLASSICAL are
    # not registered in this mode, and are not ported — module docstring.)
    _category(_CATEGORY_US_I, "us", "i"),
    _regexp("([cs]h|[zx])$", "\\1es"),
    _category(_CATEGORY_S_ES, "", "es"),
    _category(_CATEGORY_IS_IDES, "", "es"),
    _category(_CATEGORY_US_US, "", "es"),
    _regexp("(us)$", "\\1es"),
    _category(_CATEGORY_A_ATA, "", "s"),
    # The suffixes -ch, -sh and -ss all take -es in the plural.
    _regexp("([cs])h$", "\\1hes"),
    _regexp("ss$", "sses"),
    # Certain words ending in -f or -fe take -ves in the plural.
    _regexp("([aeo]l)f$", "\\1ves"),
    _regexp("([^d]ea)f$", "\\1ves"),
    _regexp("(ar)f$", "\\1ves"),
    _regexp("([nlw]i)fe$", "\\1ves"),
    # Words ending in -y take -ys.
    _regexp("([aeiou]y)$", "\\1s"),
    _regexp("y$", "ies"),
    # Some words ending in -o take -os (including those preceded by a vowel).
    _category(_CATEGORY_O_I, "o", "os"),
    _category(_CATEGORY_O_OS, "o", "os"),
    _regexp("([aeiou]o)$", "\\1s"),
    # The rest take -oes.
    _regexp("(o)$", "\\1es"),
    _regexp("(ul)um$", "\\1a"),
    _category(_CATEGORY_A_ATA, "", "es"),
    _regexp("(s)$", "\\1es"),
    # Empty string in, empty string out; otherwise the plural just adds -s.
    _regexp("^$", ""),
    _regexp("$", "s"),
]


def pluralize(word: str) -> str:
    """`word`'s English plural, as `org.atteo.evo.inflector.English.plural`
    returns it in its default (anglicized) mode.

    Parameters: `word` — one word, any case, never a phrase; the caller has
    already reduced a type name to the single noun the framework pluralizes.
    Returns the plural in the same case pattern Evo produces, which preserves
    the input's own leading case. The empty string returns the empty string.
    No failure modes: the final rule matches everything, so every input has an
    answer — the same total function Evo's own rule list is.
    """
    for rule in _RULES:
        if len(rule) == 2:
            pattern, replacement = rule
            result, count = pattern.subn(replacement, word, count=1)
            if count:
                return result
        else:
            suffixes, singular, plural = rule
            lowered = word.lower()
            if any(lowered.endswith(suffix) for suffix in suffixes):
                return word[: len(word) - len(singular)] + plural
    # Unreachable: `_RULES`' last entry matches every string, including the
    # empty one. Stated rather than assumed, because a rule removed from the
    # tail of that list would otherwise make this function return `None`.
    raise AssertionError(f"no pluralization rule matched {word!r}")
