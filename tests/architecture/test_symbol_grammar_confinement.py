"""Symbol-grammar confinement (2E-prep design §0b): SCIP `owner#member`
string parsing lives only in `domain/symbols.py`, the seam that replaced the
four ad hoc parse sites this phase found.

`test_language_confinement.py` and `test_source_rules.py` grep for forbidden
*words* — a language name, a framework name. Neither `<init>` nor
`descriptor.index("#")` is a word, so this rule needs a check of its own: the
*shape* a symbol-grammar parse takes, wherever it appears.

SQL is out of scope. `derive_endpoints.sql:82`'s
`regexp_extract(v, '#([A-Za-z0-9_]+)\\.$', 1)` is the one known, deliberate
SQL-side reader of the enum-constant grammar — the seam is a Python module
and cannot reach into a `.sql` file. Excluded here rather than silently
skipped, so the exemption is a decision on record, not an absence nobody
explains.
"""

import re
from pathlib import Path

SOURCE_ROOT = Path(__file__).parents[2] / "src" / "sextant"
SEAM = SOURCE_ROOT / "domain" / "symbols.py"

# The shapes ad hoc symbol-grammar parsing took before the seam existed: a
# bare `"#"` literal (`.index("#")`, `.rstrip("#")`, `.rpartition("#")`), and
# a bare `" "` literal handed to `partition`/`rpartition`/`rsplit` (splitting
# a symbol on the space between its module coordinates and its descriptor,
# D00 §5a). A match outside the seam is a second copy of the grammar, not a
# variant of it.
_SYMBOL_GRAMMAR = re.compile(
    r"""['\"]#['\"]|r?partition\(\s*['\"] ['\"]\s*\)|rsplit\(\s*['\"] ['\"]"""
)


def _confined_sources() -> list[Path]:
    """Every Python source Sextant ships except the seam itself."""
    return sorted(path for path in SOURCE_ROOT.rglob("*.py") if path != SEAM)


def _hits(path: Path) -> list[str]:
    return [
        f"{path.relative_to(SOURCE_ROOT)}:{number}: {line.strip()}"
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if _SYMBOL_GRAMMAR.search(line)
    ]


def test_no_symbol_grammar_parsing_appears_outside_the_seam():
    offences = [hit for path in _confined_sources() for hit in _hits(path)]
    assert offences == [], (
        "symbol-grammar string parsing outside sextant.domain.symbols:\n" + "\n".join(offences)
    )


def test_the_check_finds_symbol_grammar_parsing_where_one_is_allowed_to_be():
    """A confinement check that matches nothing anywhere passes for the wrong
    reason. The seam itself parses the grammar, so the pattern must see it
    there."""
    named = _hits(SEAM)
    assert named, "the symbol-grammar pattern matches nothing even inside domain/symbols.py"
