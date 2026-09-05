"""Every catalog `methods:` row DECLARES a descriptor (GUIDELINES §8, §8.1).

`test_catalog_descriptors.py` is the other half of this rule and answers a
different question: it refuses a descriptor that is well-formed and WRONG, by
pinning every declared string to the committed CP-10 measurement. Nothing
refuses a row that declares NONE at all — so the defect the eight-commit
descriptor sweep closed can be reintroduced by the next catalog, silently, and
every test in the repository still passes.

## The defect this makes permanent

`single_call`'s matcher selected a row by method name and argument COUNT.
That is not a rule Java has: the language identifies a method by **name and
parameter types in order**, and arity is a consequence of that list rather than
the rule (§8.1, "a language's rules bind exactly as a framework's do"). Two
overloads sharing a count were therefore indistinguishable, and the row that
happened to be written first read its own argument 0 as an address. Live, it
published a message PAYLOAD as an AMQP destination, a JMS destination and a SOAP
service address — the cardinal sin, from a catalog that looked correct.

A row with no `descriptor` re-opens exactly that: it claims every overload of
its name at its arity, and whichever one a call site actually invoked is read
positionally against a signature nobody checked.

## Why an allowlist rather than a count

Fifty-seven rows across fifteen catalogs declare one today, and the state worth
making permanent is "all of them". Entries below are listed rather than counted
so that adding one is a deliberate edit visible in a diff, and so that an
OMISSION — a new row shipped with no descriptor and no entry — is a failure
rather than an arithmetic surprise. This list does not travel in the direction
of getting longer.

## What this cannot do

It asserts a key is present, nothing more. Whether the string is the erased
signature the jar actually declares is `test_catalog_descriptors.py`'s question,
and what makes THAT trustworthy is the CP-10 harness's own abort, not either
test. Presence and correctness are separate claims and are asserted separately.

It is OFFLINE and deterministic (NFR-1): it reads the shipped catalogs and runs
nothing.
"""

from pathlib import Path

import yaml

REPO = Path(__file__).parents[2]
CATALOGS = REPO / "src" / "sextant" / "catalogs"

# Rows that legitimately cannot declare a descriptor, by `(catalog id, method
# name)`. An ALLOWLIST, not a backlog: each entry records a row for which the
# key does not exist to be declared, and retiring one means the engine gained
# the key rather than that somebody got round to it.
#
# `spring-webflux-router`'s pair is the only one, and it is a ruling rather than
# an obstacle (descriptor sweep, R8). `matches.entries[*].methods` in a
# `combinator` catalog is a bare list of NAMES matched by
# `engines/combinator.py` on owner and name alone — a different grammar from
# `single_call`'s `methods` rows, which are mappings whose `descriptor` key pins
# a row to one overload's erased signature. The combinator engine has no such
# key, so closing the same overload question there is an engine change. The file
# states this beside the entry itself, which is where a reader will look.
_NO_DESCRIPTOR_KEY_IN_THIS_ENGINE = frozenset(
    {
        ("spring-webflux-router", "route"),
        ("spring-webflux-router", "nest"),
    }
)


def method_rows() -> list[dict[str, str]]:
    """Every `methods:` row in every shipped catalog, wherever it is nested.

    Enumerated off the directory and walked recursively, never listed: the one
    thing this rule must not do is stop seeing a row. `single_call` writes its
    rows at `matches.methods`, `combinator` writes them at
    `matches.entries[*].methods`, and a style added later that writes them
    somewhere else a third time must be caught by this scan rather than
    quietly exempted by it.

    A row is a mapping (`single_call`) or a bare name (`combinator`); the
    second declares no descriptor by construction, which is the point of the
    allowlist above.
    """
    rows = []
    for path in sorted(CATALOGS.glob("*.yml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for where, method in _methods_in(document, path.stem):
            rows.append(
                {
                    "catalog": path.stem,
                    "where": where,
                    "name": str(method["name"]) if isinstance(method, dict) else str(method),
                    "arity": (
                        "—"
                        if not isinstance(method, dict) or method.get("arity") is None
                        else str(method["arity"])
                    ),
                    "descriptor": (
                        str(method["descriptor"])
                        if isinstance(method, dict) and "descriptor" in method
                        else ""
                    ),
                }
            )
    return rows


def _methods_in(node: object, where: str) -> list[tuple[str, object]]:
    """`(dotted location, row)` for every `methods:` list under `node`.

    Keyed on the exact key name: `all_methods` and `crud_methods` are different
    vocabulary — HTTP verb sets and repository operation names — and neither
    names a JVM method this project matches a call site against.
    """
    found: list[tuple[str, object]] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "methods" and isinstance(value, list):
                found.extend((f"{where}.methods", row) for row in value)
            else:
                found.extend(_methods_in(value, f"{where}.{key}"))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            found.extend(_methods_in(value, f"{where}[{index}]"))
    return found


def _identity(row: dict[str, str]) -> tuple[str, str]:
    return (row["catalog"], row["name"])


def test_every_catalog_method_row_declares_a_descriptor():
    """The rule. A row without one claims every overload of its name and reads
    whichever the call site invoked positionally — which is how a payload
    became a destination."""
    undeclared = sorted(
        {
            (row["catalog"], row["where"], row["name"], row["arity"])
            for row in method_rows()
            if not row["descriptor"] and _identity(row) not in _NO_DESCRIPTOR_KEY_IN_THIS_ENGINE
        }
    )
    assert undeclared == [], (
        "these shipped catalog `methods:` rows declare no `descriptor:` and are not on this "
        "file's allowlist:\n"
        + "\n".join(
            f"  - {catalog}: {name}/{arity} at {where}"
            for catalog, where, name, arity in undeclared
        )
        + "\n\nRead the erased signature off the jar (`javap -p -s <owner>`), declare it, then "
        "re-run scripts/probes/cp10_catalog_descriptors/run.sh and paste its tables into "
        "scripts/probes/cp10_catalog_descriptors.md so test_catalog_descriptors.py can pin it. "
        "Adding the row to _NO_DESCRIPTOR_KEY_IN_THIS_ENGINE is the other option, and it is "
        "correct only when the engine reading that row has no `descriptor` key at all."
    )


def test_the_allowlist_only_ever_shrinks():
    """An entry naming a row that now declares a descriptor, or names no
    shipped row at all, must go in the same commit.

    Without this the list is write-only: a pair could sit here forever after
    the engine gained the key, exempting a row that no longer needs exempting
    and — worse — exempting any FUTURE row of that name in that catalog.
    """
    rows = method_rows()
    declared = {_identity(row) for row in rows if row["descriptor"]}
    shipped = {_identity(row) for row in rows}
    stale = sorted(_NO_DESCRIPTOR_KEY_IN_THIS_ENGINE & declared)
    unknown = sorted(_NO_DESCRIPTOR_KEY_IN_THIS_ENGINE - shipped)
    assert (stale, unknown) == ([], []), (
        "_NO_DESCRIPTOR_KEY_IN_THIS_ENGINE is out of date — "
        f"now declares a descriptor, so remove them: {stale or 'none'}; "
        f"names no shipped `methods:` row at all: {unknown or 'none'}"
    )


def test_the_scan_finds_the_method_rows_that_ship():
    """A check that discovers nothing passes for the wrong reason — an empty
    scan has no undeclared rows either, and the file would assert only that the
    allowlist is complete.

    Two pins, one per grammar, because the walk has to see both: the
    `combinator` row it exempts is the one nested two levels deeper than the
    `single_call` rows it enforces, so a walk that stopped at `matches.methods`
    would exempt nothing and enforce everything, and a walk that lost
    `matches.methods` would enforce nothing at all.
    """
    rows = method_rows()
    assert ("spring-rabbit-template", "convertAndSend") in {_identity(row) for row in rows}, (
        "the scan no longer sees `spring-rabbit-template`'s rows — the descriptor key was "
        "added for that file's arity-3 overload, and if the walk cannot see that one it can "
        "see none of the `single_call` rows"
    )
    assert ("spring-webflux-router", "route") in {_identity(row) for row in rows}, (
        "the scan no longer reaches `matches.entries[*].methods` — the allowlist would then "
        "be exempting a row this file cannot see, which is an exemption that measures nothing"
    )
    # A floor, deliberately not the shipped total: a count that tracked the
    # fifty-seven would fail a second time on every legitimate row deletion and
    # say nothing the rule above has not already said.
    assert len([row for row in rows if row["descriptor"]]) >= 4
