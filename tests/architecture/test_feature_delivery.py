"""A feature is delivered when nothing open blocks it, and the matrix has to agree.

**Why this exists, stated plainly because the reason is the point.** `✅` in COVERAGE §2
means *every library catalogued*. It has never meant *no open defects*, so SOAP, GraphQL and
WebSocket all read `✅` while carrying open Majors, and a reader — correctly — took that as
"done". Five days of work produced no visible change in that document because nothing in it
measures delivery.

Principles did not fix this. Every rule about finishing work that was written down and not
enforced was broken; every rule with a failing test behind it held. So this is the rule with
a test behind it.

**Two directions, both enforced**:

* a feature with blockers must NOT read `✅`
* a feature reading `✅` must have NO blockers

**And the third, which is the one aimed at half-delivery**: every open Critical and Major in
the registers must be named somewhere in `docs/java-kotlin-delivery-list.md` — against the
feature it blocks, or in the `unassigned` block, or in `out-of-scope`. Doing half of an item
and filing the other half as a new issue then fails the suite until that half is placed
against the feature it belongs to. The register can no longer absorb work silently.
"""

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
DELIVERY = REPO / "docs" / "java-kotlin-delivery-list.md"
COVERAGE = REPO / "docs" / "COVERAGE.md"
OPEN_ISSUES = REPO / "docs" / "open-issues.md"

# The row both matrices carry for this target. One row, two tables (§2a application
# protocols over HTTP, §2b messaging and RPC), and a feature lives in exactly one of them.
_ROW = "**Java / Kotlin**"

# A feature the matrices do not score — see `test_every_feature_in_the_register_has_a_matrix_column`.
NO_COLUMN = "—"


def _fenced(language: str) -> list[str]:
    """The lines of the first ```<language> block in the delivery list."""
    match = re.search(rf"```{language}\n(.*?)```", DELIVERY.read_text(), re.DOTALL)
    assert match is not None, f"the delivery list has no ```{language} block"
    return [line for line in match.group(1).split("\n") if line.strip()]


def _register() -> dict[str, tuple[str, list[str]]]:
    """`feature -> (coverage column, blockers)` from the ```delivery block."""
    register: dict[str, tuple[str, list[str]]] = {}
    for line in _fenced("delivery"):
        parts = [cell.strip() for cell in line.split("|")]
        assert len(parts) == 3, f"a delivery row needs three cells, got: {line!r}"
        feature, column, blockers = parts
        register[feature] = (column, blockers.split())
    return register


def _matrix_cells() -> dict[str, str]:
    """`column header -> cell` for the Java/Kotlin row of both §2 matrices."""
    cells: dict[str, str] = {}
    header: list[str] | None = None
    for line in COVERAGE.read_text().split("\n"):
        if not line.startswith("|"):
            header = None
            continue
        values = [cell.strip() for cell in line.strip("|").split("|")]
        if header is None:
            # A column header is a markdown link, `[REST in](#51-rest-inbound)`; the label
            # is what the delivery register names, so the anchor is dropped here rather
            # than duplicated there.
            header = [re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", cell) for cell in values]
            continue
        if values and values[0] == _ROW:
            for name, cell in zip(header, values, strict=False):
                if name not in ("Language", "Scanner", _ROW):
                    cells.setdefault(name, cell)
    return cells


def test_every_feature_in_the_register_has_a_matrix_column():
    """A feature naming a column that does not exist is a register that cannot be checked."""
    cells = _matrix_cells()
    # `—` is a feature the COVERAGE matrices do not score, because they are per-protocol
    # and it is not one. Meridian's FR-21..FR-24 are the case: four committed requirements
    # with no implementation, which belong on a delivery list precisely because leaving
    # them off one is how they went unbuilt for a week.
    missing = {
        feature: column
        for feature, (column, _) in _register().items()
        if column != NO_COLUMN and column not in cells
    }
    assert missing == {}, (
        f"these features name a COVERAGE column that is not in the Java/Kotlin row: {missing}. "
        f"available columns: {sorted(cells)}"
    )


@pytest.mark.parametrize("feature", sorted(_register()))
def test_a_feature_with_blockers_does_not_claim_to_be_delivered(feature: str):
    """The direction that was false for SOAP, GraphQL and WebSocket on 2026-09-11: three
    cells read `✅` while each carried an open Major."""
    column, blockers = _register()[feature]
    if column == NO_COLUMN:
        pytest.skip("not scored by the COVERAGE matrices; its blockers are checked elsewhere")
    cell = _matrix_cells()[column]
    if not blockers:
        return
    assert not cell.startswith("✅"), (
        f"{feature} reads `{cell}` in COVERAGE §2 but the delivery register lists "
        f"{len(blockers)} open blocker(s): {' '.join(blockers)}. A feature with an open "
        f"Critical or Major is not delivered — close them, or stop claiming the cell."
    )


@pytest.mark.parametrize("feature", sorted(_register()))
def test_a_feature_with_no_blockers_is_marked_delivered(feature: str):
    """The other direction, so the register cannot quietly under-claim either: work that is
    finished has to show up in the document a reader opens."""
    column, blockers = _register()[feature]
    if column == NO_COLUMN:
        pytest.skip("not scored by the COVERAGE matrices; its blockers are checked elsewhere")
    cell = _matrix_cells()[column]
    if blockers:
        return
    if feature in _scoped_out():
        # The matrix scores every library in every language; this target is Spring Boot.
        # SSE's only gap is JAX-RS and gRPC's are Go, Python, Rust and Swift — so those
        # cells read `◐` correctly and forever, and saying so here is what keeps the
        # check from demanding a lie in the other direction.
        assert not cell.startswith("✅"), (
            f"{feature} is listed as scoped-out yet reads `{cell}` — if it really is "
            f"delivered outright, remove it from the ```scoped-out block."
        )
        return
    assert cell.startswith("✅"), (
        f"{feature} has no open blockers in the delivery register but COVERAGE §2 still "
        f"reads `{cell}`. Either it is delivered and the matrix is stale, or a blocker is "
        f"missing from the register."
    )


def _scoped_out() -> set[str]:
    """Features whose only remaining matrix gaps are out of this target's scope, so their
    cell stays `◐` and that is the correct reading rather than an outstanding debt."""
    return set(" | ".join(_fenced("scoped-out")).split(" | "))


def _severity() -> dict[str, str]:
    """`id -> severity`, from the delivery list's own ```severity block.

    Folded here from `docs/java-gap-analysis-2026-09-06.md` when that file was removed
    (2026-09-11). It was the input audit of 2026-09-06 — 123 rows, of which 14 were still
    open — and keeping a 804-line document alive so one test could read two columns out of
    it is the documentation sprawl this consolidation exists to end.
    """
    return {line.split("|")[0].strip(): line.split("|")[1].strip() for line in _fenced("severity")}


def _open_criticals_and_majors() -> set[str]:
    """Every id graded Critical or Major."""
    return {name for name, grade in _severity().items() if grade in ("Critical", "Major")}


def test_every_open_critical_and_major_is_placed_against_a_feature():
    """**The half-delivery check.**

    Doing half an item and filing the rest as a new issue is the pattern that made the
    register grow while nothing reached delivered. A Critical or Major that is not named
    against a feature, not in `unassigned`, and not `out-of-scope` fails here — so the
    unfinished half has to be written down where it belongs before the build goes green.
    """
    placed: set[str] = set()
    for _, blockers in _register().values():
        placed.update(blockers)
    placed.update(" ".join(_fenced("unassigned")).split())
    placed.update(" ".join(_fenced("out-of-scope")).split())
    # A blocker leaves the register only with the test that proves it — the `closed` block
    # names each one beside the assertion that fails if it regresses.
    placed.update(line.split("|")[0].strip() for line in _fenced("closed"))
    # Closed by audit rather than by a test: a weaker claim, recorded separately so the
    # difference between "a test fails if this regresses" and "somebody read the code
    # once" stays legible instead of being flattened into one word.
    placed.update(" ".join(_fenced("closed-by-audit")).split())

    unplaced = sorted(_open_criticals_and_majors() - placed - _closed_ids())
    assert unplaced == [], (
        "these are graded Critical or Major and are placed nowhere in "
        f"docs/java-kotlin-delivery-list.md: {unplaced}. Name each against the feature it "
        "blocks, or in the `unassigned` block if it blocks none, or in `out-of-scope`."
    )


def _closed_ids() -> set[str]:
    """Ids the registers record as closed, by either document's own convention."""
    closed: set[str] = set()
    text = OPEN_ISSUES.read_text()
    for match in re.finditer(r"(G-\d+|OI-\d+)[^\n]*?\*\*(?:CLOSED|Closed by)", text):
        closed.add(match.group(1))
    return closed


def test_a_closed_entry_names_the_ci_run_that_proved_it():
    """Done means green in CI, not green on a laptop.

    Ruled by the user 2026-09-11 after `G-36` was recorded closed on a local pass and had
    to be reopened within the hour. A `closed` entry carries the test that proves the
    feature and the CI run where that test passed; without both there is nothing to
    distinguish "it worked on my machine" from "it is delivered".
    """
    malformed = [
        line
        for line in _fenced("closed")
        if len([cell for cell in line.split("|") if cell.strip()]) != 3
        or "http" not in line.split("|")[-1]
    ]
    assert malformed == [], (
        "a closed entry reads `id | test node id | CI run URL` and every field is "
        f"required — the run URL is what makes it checkable. Malformed: {malformed}"
    )


def test_the_register_names_no_id_that_does_not_exist():
    """A blocker id nobody can look up is a register that reads as rigorous and is not."""
    known = _open_criticals_and_majors() | _closed_ids()
    # Every id the severity block carries, at any grade — `G-73` and `G-74` are Moderate
    # and are still real, lookup-able work.
    known |= set(_severity())
    known |= {match.group(0) for match in re.finditer(r"OI-\d+", OPEN_ISSUES.read_text())}
    known |= {match.group(0) for match in re.finditer(r"GAP-\d+", OPEN_ISSUES.read_text())}

    named: set[str] = set()
    for _, blockers in _register().values():
        named.update(blockers)
    named.update(" ".join(_fenced("unassigned")).split())
    named.update(" ".join(_fenced("out-of-scope")).split())
    named.update(line.split("|")[0].strip() for line in _fenced("closed"))
    named.update(" ".join(_fenced("closed-by-audit")).split())

    # Slugs are deliberate: several blockers have no register id because they were found
    # by measurement rather than by an audit — `W44-verb-overloads`, `jdk-httpclient`.
    # They are still real work and still have to be named; they simply are not ids.
    phantom = sorted(
        name for name in named if re.fullmatch(r"(G|OI|GAP)-\d+", name) and name not in known
    )
    assert phantom == [], f"the delivery register names ids that exist in no register: {phantom}"
