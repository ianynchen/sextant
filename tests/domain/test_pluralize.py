"""The Evo Inflector port (2O design §2b), pinned against CP-2's committed
expectation table (`scripts/probes/cp2_data_rest.md`).

Every expected value below is `org.atteo.evo.inflector.English.plural`'s own
answer, run live against version 1.3 — the version `spring-data-rest-core`
5.0.1 resolves — never what English arguably ought to say. `person` →
`persons`, not `people`, is the clearest case of the difference, and it is the
whole reason this table is evidence rather than intuition: mirroring the
library is the requirement (DR-6), so a "better" pluralizer would be wrong.

The probe compared the port against the library across all 235,976 words of
`/usr/share/dict/words` with zero mismatches; this file samples one word per
rule family so a regression names which rule broke.
"""

import pytest

from sextant.domain.pluralize import pluralize


@pytest.mark.parametrize(
    "singular, plural",
    [
        # The plain rule, and the two suffix rules a real entity name is most
        # likely to hit.
        ("order", "orders"),
        ("category", "categories"),
        ("box", "boxes"),
        # Irregulars and the uncountable list.
        ("child", "children"),
        ("sheep", "sheep"),
        ("news", "news"),
        ("series", "series"),
        ("mongoose", "mongoose"),
        ("quiz", "quizzes"),
        ("genus", "genera"),
        ("octopus", "octopuses"),
        # NOT `people`: Evo Inflector has no person/people pair, and the
        # framework's answer is the one a derived route must carry.
        ("person", "persons"),
        # Suffix rules, one per family.
        ("man", "men"),
        ("mouse", "mice"),
        ("status", "statuses"),
        ("datum", "data"),
        ("medium", "mediums"),
        ("index", "indexes"),
        ("alumnus", "alumni"),
        ("wolf", "wolves"),
        ("life", "lives"),
        ("roof", "roofs"),
        ("day", "days"),
        ("photo", "photos"),
        ("hero", "heroes"),
        ("piano", "pianos"),
    ],
)
def test_the_port_matches_evo_inflector(singular: str, plural: str) -> None:
    assert pluralize(singular) == plural


@pytest.mark.parametrize(
    "word, expected",
    [
        # The library preserves the word's own leading case through its
        # irregular and category rules — a derived collection path is built
        # from an uncapitalized name, but the port must not quietly normalize
        # case on the way, or it would stop being a mirror.
        ("ORDER", "ORDERs"),
        ("CHILD", "Children"),
        ("Quiz", "Quizzes"),
        ("Sheep", "Sheep"),
        # Evo's own `^$` rule: empty in, empty out — never an "s".
        ("", ""),
    ],
)
def test_case_and_the_empty_word_follow_the_library_too(word: str, expected: str) -> None:
    assert pluralize(word) == expected
