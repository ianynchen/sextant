"""The `@HttpExchange` direction flip is pinned to CP-7's bytecode.

`scripts/probes/cp7_http_exchange.md` carries the table its committed harness
generates — one row per Spring question, with the artifact the run resolved, the
version that JAR reported about itself, and what `javap` said. This file is the
offline half: it asserts the shipped catalog still says what the measurement
says.

## Why a pin and not a comment

The flip's condition was WRITTEN WRONG once already, in the spec that ordered it:
§6 gated on "the owner is implemented in this module", which is a condition
Spring does not have — it serves an implemented interface only where the
implementation is a handler bean. GUIDELINES §8.1's own worked example carried
the same class of error for a month (`@Controller` **or** a type-level
`@RequestMapping`, corrected in `8b4d174`). A comment recording the measurement
rots the same way. A test fails.

The direction matters, and it is the same one
`test_sweep_round1_framework_rules.py` chose: this pins the CATALOG against the
MEASUREMENT, so re-running the harness after a framework bump and pasting a
changed table makes the catalog fail until it is brought back into line — which
is the moment a version-scoped rule is supposed to be re-decided (§5.4).

It is OFFLINE and deterministic (NFR-1): it reads two committed files and runs
nothing. What makes the table trustworthy is the harness's own abort on a
mislabelled identity, not this test.
"""

import re
from pathlib import Path

import yaml

REPO = Path(__file__).parents[2]
CATALOGS = REPO / "src" / "sextant" / "catalogs"
PROBE = REPO / "scripts" / "probes" / "cp7_http_exchange.md"

# The generated table's own header, matched in full: a header that has drifted
# means the columns below are being read positionally against something else.
_HEADER = "| # | question | artifact | version | observed |"
_BACKTICKED = re.compile(r"^`(.*)`$")


def _cell(text: str) -> str:
    stripped = text.strip()
    match = _BACKTICKED.match(stripped)
    return match.group(1) if match else stripped


def probe_rows() -> dict[str, dict[str, str]]:
    """The committed measurement, keyed by the question number the harness
    printed (`1a`, `1b`, `2a`, …)."""
    lines = PROBE.read_text(encoding="utf-8").splitlines()
    start = next((i for i, line in enumerate(lines) if line.strip() == _HEADER), None)
    assert start is not None, (
        f"{PROBE.relative_to(REPO)} carries no observation table with the header the harness "
        f"generates:\n  {_HEADER}\nRe-run scripts/probes/cp7_http_exchange/run.sh and paste its "
        "second table in verbatim."
    )
    rows = {}
    for line in lines[start + 2 :]:
        if not line.startswith("|"):
            break
        cells = [_cell(cell) for cell in line.strip().strip("|").split("|")]
        rows[cells[0]] = {
            "question": cells[1],
            "artifact": cells[2],
            "version": cells[3],
            "observed": cells[4],
        }
    return rows


def catalog(name: str) -> dict:
    return yaml.safe_load((CATALOGS / f"{name}.yml").read_text(encoding="utf-8")) or {}


def _rows_for(question: str) -> dict[str, str]:
    """Every observation for one question number, keyed by the version it was
    read at — so an assertion covers the WHOLE version scope rather than
    whichever row happened to be first."""
    return {
        row["version"]: row["observed"]
        for number, row in probe_rows().items()
        if number.rstrip("abcdefgh") == question
    }


def test_the_probe_table_is_readable_at_all():
    """A pin that parses nothing passes for the wrong reason: an empty table has
    no disagreements either. Asserts every question is present, and that the
    handler predicate was read at more than one Spring minor — a stability
    claim measured once is not a stability claim."""
    numbers = {number.rstrip("abcdefgh") for number in probe_rows()}
    assert numbers == {"1", "2", "3", "4"}, (
        f"CP-7's observation table is missing questions — found {sorted(numbers)}"
    )
    assert len(_rows_for("1")) >= 2, (
        "CP-7 Q1 was read at one Spring minor only, so the table cannot support the claim "
        "that the handler predicate is stable across minors"
    )


def test_the_flip_condition_is_the_controller_predicate_and_carries_no_disjunct():
    """Q1, and the whole reason the flip's condition is not spec §6's.

    Spring's server-side handler test is one
    `AnnotatedElementUtils.hasAnnotation(beanType, Controller.class)` call on
    every minor in scope. `@RequestMapping` appears in it nowhere — the disjunct
    GUIDELINES §8.1 asserted from memory for a month belongs to an older Spring.
    So a `@Service` implementing an `@HttpExchange` interface is served by
    nothing, and `owner_implemented_in_module: true` would have published an
    inbound route for one."""
    for version, observed in sorted(_rows_for("1").items()):
        assert "AnnotatedElementUtils.hasAnnotation" in observed, (
            f"spring-webmvc {version}'s isHandler is no longer a hasAnnotation predicate: {observed}"
        )
        assert "stereotype/Controller" in observed, (
            f"spring-webmvc {version}'s isHandler no longer names @Controller: {observed}"
        )
        assert "bind/annotation/RequestMapping" not in observed, (
            f"spring-webmvc {version}'s isHandler has gained a @RequestMapping disjunct — the "
            "flip's condition is now narrower than the framework's and under-reports"
        )


def test_the_server_side_reads_http_exchange_through_the_type_hierarchy():
    """Q2. Both halves of the flip's premise, in one measured sequence: the
    mapping builder accepts `@HttpExchange` as a mapping annotation at all, and
    it searches the TYPE HIERARCHY — which is what carries an interface's own
    exchange annotations onto the class implementing it without that class
    repeating them. Either half absent makes the inbound row a fabrication."""
    for version, observed in sorted(_rows_for("2").items()):
        assert "SearchStrategy.TYPE_HIERARCHY" in observed, (
            f"spring-webmvc {version} no longer searches the type hierarchy for a mapping "
            f"annotation, so an implemented interface's own mappings never reach the "
            f"implementing class: {observed}"
        )
        assert "service/annotation/HttpExchange" in observed, (
            f"spring-webmvc {version} no longer builds a mapping from @HttpExchange, so the "
            f"flipped inbound row names a route the server does not serve: {observed}"
        )


def test_an_inherited_default_method_is_still_a_handler_candidate():
    """Q3, and the reason the flip is keyed on the OWNER rather than on the
    method join. `MethodIntrospector.selectMethods` walks the target type's
    interfaces as well as the type itself, so a `default` method the controller
    never overrides is mapped and served — and a flip that required a method on
    the implementing class would have dropped exactly those routes."""
    for version, observed in sorted(_rows_for("3").items()):
        assert "getAllInterfacesForClassAsSet" in observed, (
            f"spring-core {version}'s handler-candidate walk no longer includes the type's "
            f"interfaces, so an inherited default method is no longer served: {observed}"
        )


def test_one_address_alias_list_serves_both_directions():
    """Q4. The client invoker reads `url()` and the server's mapping builder
    reads `value()`, which would be a divergence to model if they were separate
    attributes. They are `@AliasFor` each other, so only the one the author
    typed reaches the bytecode and the catalog's single `path_from` list answers
    for the outbound row and the flipped inbound one alike."""
    aliases = dict.fromkeys(_rows_for("4").values())
    for observed in aliases:
        assert "value() @AliasFor url" in observed and "url() @AliasFor value" in observed, (
            f"@HttpExchange's `value`/`url` are no longer aliases of one another: {observed}"
        )
    declared = catalog("spring-http-interface")["matches"]["mapping"]["path_from"]
    assert declared == ["value", "url"], (
        f"`spring-http-interface.yml` reads its address from {declared}, which is no longer the "
        "alias pair the measurement names"
    )
