"""Every catalog `descriptor:` is pinned to bytecode somebody actually read.

`single_call._validate_methods` refuses a `descriptor` that is not a string
opening with `(`, and that is the whole of the load-time check. A descriptor
with a wrong return type, a misspelled package or a stale erasure passes it,
CLAIMS its candidate set in `_matching_method`, and makes every overload of that
name derive nothing — with no error, no COVERAGE row, and every test that
asserts absence still passing. GUIDELINES §10 names that shape exactly: "could a
change to it be WRONG without being INVALID?".

Twenty-three rows gained a descriptor in one sweep. A guard that only asks
whether each is well-formed would have waved every one of them through.

## What this pins, and what it cannot

`scripts/probes/cp10_catalog_descriptors.md` carries the table its committed
harness generates: one row per catalog descriptor, with the artifact the run
resolved the owner out of, the version that JAR reported about itself, and
whether `javap -p -s` found that exact erased descriptor on the owner or a
superclass. This test asserts the two agree in both directions —

* every `descriptor:` in every shipped catalog appears in the table, so a row
  added without re-running the harness fails here rather than in silence;
* every table row still names a catalog that declares it, so a descriptor
  deleted or edited leaves a stale row that fails here too;
* every table row's verdict is `declared`, so a descriptor the jar does not
  carry cannot be committed even with the table regenerated.

It is OFFLINE and deterministic (NFR-1): it reads two committed files and runs
nothing. What makes the table itself trustworthy is the harness — which reads
each jar's version out of that jar's own bytes and aborts when it disagrees with
the coordinate that resolved it (§5.4) — not this test, which can only refuse a
catalog and a measurement that have drifted apart.

**Version scope.** A descriptor is version-scoped: an overload re-typed in a
later release is a different answer. The table names the version each row was
measured against, and this test does not re-measure. Bumping a framework means
re-running `scripts/probes/cp10_catalog_descriptors/run.sh`.
"""

import re
from pathlib import Path

import yaml

REPO = Path(__file__).parents[2]
CATALOGS = REPO / "src" / "sextant" / "catalogs"
PROBE = REPO / "scripts" / "probes" / "cp10_catalog_descriptors.md"

# The generated table's own header, matched in full: a header that has drifted
# means the columns below are being read positionally against something else.
_HEADER = "| # | catalog | owner | method | arity | descriptor | artifact | version | verdict |"
_BACKTICKED = re.compile(r"^`(.*)`$")


def _cell(text: str) -> str:
    """One table cell, with the backticks the generated table wraps code in."""
    stripped = text.strip()
    match = _BACKTICKED.match(stripped)
    return match.group(1) if match else stripped


def probe_rows() -> list[dict[str, str]]:
    """The committed measurement, one dict per generated table row."""
    lines = PROBE.read_text(encoding="utf-8").splitlines()
    start = next((i for i, line in enumerate(lines) if line.strip() == _HEADER), None)
    assert start is not None, (
        f"{PROBE.relative_to(REPO)} carries no descriptor table with the header the harness "
        f"generates:\n  {_HEADER}\nRe-run scripts/probes/cp10_catalog_descriptors/run.sh and "
        "paste its second table in verbatim."
    )
    rows = []
    for line in lines[start + 2 :]:
        if not line.startswith("|"):
            break
        cells = [_cell(cell) for cell in line.strip().strip("|").split("|")]
        rows.append(
            {
                "catalog": cells[1],
                "owner": cells[2],
                "name": cells[3],
                "arity": cells[4],
                "descriptor": cells[5],
                "artifact": cells[6],
                "version": cells[7],
                "verdict": cells[8],
            }
        )
    return rows


def catalog_rows() -> list[dict[str, str]]:
    """Every `methods` row in every shipped catalog declaring a descriptor.

    Enumerated off the directory, never listed: the one thing this rule must
    not do is stop seeing a catalog.
    """
    rows = []
    for path in sorted(CATALOGS.glob("*.yml")):
        catalog = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        matches = catalog.get("matches") or {}
        # A catalog may name ONE library under several names (§3.1) — the class and
        # the interface a codebase more often declares its field as. One row per
        # owner, because the question is per owner: an interface declaring a SUBSET
        # of the class's methods matches some call sites and misses the rest, and a
        # check reading only the first name would never see it. The harness makes
        # the same split, and these two lists are compared against each other.
        declared_owner = matches.get("owner")
        catalog_owners = (
            [declared_owner]
            if isinstance(declared_owner, str) or declared_owner is None
            else list(declared_owner)
        )
        for method in matches.get("methods") or []:
            if isinstance(method, dict) and "descriptor" in method:
                # A ROW may narrow the catalog's own flat owner list to the one (or
                # few) it actually belongs to — `kafka-streams.yml`'s reason: its four
                # owners are unrelated types with disjoint method sets (`StreamsBuilder`
                # declares `stream`, `KStream` declares `to`, neither declares the
                # other's), not an interface/impl pair sharing one surface, so the
                # catalog-wide cross product this file otherwise takes would ask
                # `javap` whether `KStream` declares `stream` and fail on the honest
                # answer. Falls back to the catalog's own list — unchanged for every
                # catalog that does not narrow, which is every one before this.
                row_owner = method.get("owner")
                owners = (
                    catalog_owners
                    if row_owner is None
                    else ([row_owner] if isinstance(row_owner, str) else list(row_owner))
                )
                for owner in owners:
                    rows.append(
                        {
                            "catalog": path.stem,
                            "owner": str(owner),
                            "name": str(method["name"]),
                            "arity": "—" if method.get("arity") is None else str(method["arity"]),
                            "descriptor": str(method["descriptor"]),
                        }
                    )
    return rows


def _identity(row: dict[str, str]) -> tuple[str, str, str, str, str]:
    return (row["catalog"], row["owner"], row["name"], row["arity"], row["descriptor"])


def test_every_catalog_descriptor_was_measured_against_real_bytecode():
    """The rule. A descriptor the probe never read is a string nobody checked,
    and its failure mode is silence rather than an error."""
    unmeasured = sorted(set(map(_identity, catalog_rows())) - set(map(_identity, probe_rows())))
    assert unmeasured == [], (
        "these catalog `descriptor:` values appear in no row of "
        f"{PROBE.relative_to(REPO)}:\n"
        + "\n".join(
            f"  - {catalog}: {name}/{arity} {descriptor}"
            for catalog, _owner, name, arity, descriptor in unmeasured
        )
        + "\n\nRe-run scripts/probes/cp10_catalog_descriptors/run.sh and paste its tables in. "
        "A descriptor nobody measured claims its candidate set anyway, and every overload of "
        "that name then derives nothing — silently."
    )


def test_every_measured_descriptor_is_still_declared_by_a_shipped_catalog():
    """The other direction, and it is not symmetry for its own sake: a table row
    left behind by an edited or deleted catalog row makes the measurement look
    broader than it is, which is the shape §5.4 refuses."""
    stale = sorted(set(map(_identity, probe_rows())) - set(map(_identity, catalog_rows())))
    assert stale == [], (
        f"{PROBE.relative_to(REPO)} measures descriptors no shipped catalog declares:\n"
        + "\n".join(
            f"  - {catalog}: {name}/{arity} {descriptor}"
            for catalog, _owner, name, arity, descriptor in stale
        )
        + "\n\nRe-run the harness so the table describes what ships."
    )


def test_no_measured_descriptor_was_missing_from_the_bytecode():
    """The measurement's own verdict, asserted rather than admired. `javap`
    finding no such method on the owner or any superclass on the classpath is a
    descriptor no call site can ever equal — which still claims its candidate
    set, so the overload set derives nothing at all."""
    missing = [row for row in probe_rows() if row["verdict"] != "declared"]
    assert missing == [], (
        "the committed measurement says these descriptors are not declared by the jar they "
        "were checked against:\n"
        + "\n".join(
            f"  - {row['catalog']}: {row['owner']}.{row['name']} {row['descriptor']} "
            f"({row['artifact']} {row['version']}): {row['verdict']}"
            for row in missing
        )
    )


def test_the_scan_finds_the_descriptors_that_ship():
    """A check that discovers nothing passes for the wrong reason — an empty
    catalog scan agrees with an empty table, and the file would assert that two
    absences match. `spring-rabbit-template`'s arity-3 row is the pin: it is the
    descriptor the key was added for, and if the scan cannot see that one it can
    see none of them."""
    declared = {(row["catalog"], row["arity"]) for row in catalog_rows()}
    assert ("spring-rabbit-template", "3") in declared
    assert len(probe_rows()) == len(catalog_rows()) >= 4
