"""Every surface the round-1b sweep fix pass mirrors is pinned to CP-12's
bytecode.

`scripts/probes/cp12_sweep_round1b.md` carries the table its committed harness
generates — one row per framework question, with the artifact the run resolved,
the version that JAR reported about itself, and what `javap` said. This file is
the offline half: it asserts the shipped catalogs still cover what the
measurement found.

## Why these pins run in the OTHER direction from CP-10's

`test_catalog_descriptors.py` asks whether every descriptor a catalog declares
names a real method. Every finding this file serves is the converse — the
framework declares something and the catalog does not name it — and a
descriptor sweep cannot see that shape at all (`A-Mi5`). So each test below
reads the framework's whole set out of the probe table and asserts the
catalog's own list covers it, which fails when a framework GROWS as well as
when a catalog shrinks.

That direction is what makes it a §5.4 instrument: re-running the harness after
a version bump and pasting a changed table makes the catalog fail until it is
brought back into line, which is the moment a version-scoped rule is supposed
to be re-decided.

It is OFFLINE and deterministic (NFR-1): it reads two committed files and runs
nothing. What makes the table trustworthy is the harness's own abort on a
mislabelled identity, not this test.
"""

import re
from pathlib import Path

import yaml

REPO = Path(__file__).parents[2]
CATALOGS = REPO / "src" / "sextant" / "catalogs"
PROBE = REPO / "scripts" / "probes" / "cp12_sweep_round1b.md"

# The generated table's own header, matched in full: a header that has drifted
# means the columns below are being read positionally against something else.
_HEADER = "| # | question | artifact | version | observed |"
_BACKTICKED = re.compile(r"^`(.*)`$")
# `name(Ldescriptor;…)` as `probe.py` prints one member of a measured set.
_MEMBER = re.compile(r"^([\w$]+)\(")


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
        f"generates:\n  {_HEADER}\nRe-run scripts/probes/cp12_sweep_round1b/run.sh and paste its "
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


def measured(question: str) -> dict[str, set[str]]:
    """`version -> the set of member NAMES` the probe recorded for one
    question, over every row that question produced.

    Names rather than whole signatures, because that is the granularity every
    grammar in scope keys on: a `fluent` root matches on owner and method name,
    and a `terminal` on the name alone.
    """
    found: dict[str, set[str]] = {}
    for number, row in probe_rows().items():
        if number.rstrip("abcdefgh") != question:
            continue
        names = {
            match.group(1) for part in row["observed"].split(", ") if (match := _MEMBER.match(part))
        }
        found.setdefault(row["version"], set()).update(names)
    assert found, f"CP-12's table carries no question {question}"
    return found


def catalog(name: str) -> dict:
    return yaml.safe_load((CATALOGS / f"{name}.yml").read_text(encoding="utf-8")) or {}


def test_the_probe_table_is_readable_at_all():
    """A pin that parses nothing passes for the wrong reason: an empty table has
    no disagreements either. Asserts every question is present, and that the
    two-minor questions really did produce two rows — the version split is
    `A-M4`'s whole finding, and a table that had collapsed to one row would let
    every version assertion below pass vacuously."""
    numbers = {number.rstrip("abcdefgh") for number in probe_rows()}
    assert numbers == {str(n) for n in range(1, 13)}
    for question in ("1", "2", "3", "4"):
        assert set(measured(question)) == {"6.1.6", "7.0.2"}, (
            f"CP-12 question {question} was measured at one Spring minor, not two — "
            "`A-M4` is a finding about the DIFFERENCE between them"
        )


def _roots_of(catalog_id: str) -> set[str]:
    return {str(root["method"]) for root in catalog(catalog_id)["matches"]["roots"]}


def test_both_spring_http_clients_declare_a_root_for_every_request_starter():
    """`A-M3`. `WebClient` and `RestClient` each declare eight request-starting
    methods at both measured minors (CP-12 Q1, Q3), and each catalog declared
    five — GET/POST/PUT/DELETE/PATCH, which is exactly the fixture's verb
    vocabulary and §8.1 rule 1's own failure shape.

    The cost of a missing root is total, not partial: a chain whose first call
    matches no root is never rooted, so nothing reaches a terminal and the whole
    outbound call vanishes. An omission leaves no wrong row to notice."""
    for catalog_id, question in (("spring-webclient", "1"), ("spring-restclient", "3")):
        declared = _roots_of(catalog_id)
        for version, starters in sorted(measured(question).items()):
            missing = sorted(starters - declared)
            assert missing == [], (
                f"{catalog_id}.yml declares no root for request-starting methods the client "
                f"has at {version}: {missing}. Each one roots no chain, so every call made "
                "through it is absent from the export entirely."
            )


def test_webclients_terminal_list_holds_every_exchange_form_spring_7_kept():
    """`A-M4`, the half that costs recall. `exchangeToMono` and
    `exchangeToFlux` are `WebClient`'s exchange-style terminals at BOTH
    measured minors and the only ones at 7.0.2 (CP-12 Q2); the catalog listed
    neither, so a module using them derived nothing at all.

    Asserted against the 7.0.2 column rather than the union, and that is the
    load-bearing choice: 6.1.6's set also contains `exchange`, which 7.0.2
    removed, and demanding the union would demand a dead entry forever."""
    declared = set(catalog("spring-webclient")["matches"]["terminal"])
    missing = sorted(measured("2")["7.0.2"] - declared)
    assert missing == [], (
        "spring-webclient.yml declares no terminal for `WebClient$RequestHeadersSpec` methods "
        f"that obtain a response at spring-webflux 7.0.2: {missing}. A chain reaching no "
        "declared terminal is never executed and derives no row."
    )


def test_restclient_does_not_borrow_webclients_reactive_terminals():
    """`A-M4`'s other side, and the reason the two twin catalogs cannot share
    one list. `RestClient` is synchronous: CP-12 Q4 shows an `exchange` family
    and no `exchangeToMono`/`exchangeToFlux` at either minor.

    A terminal a catalog declares and the framework does not have is dead data
    rather than a wrong row — but declaring the reactive pair HERE would say
    this file was copied rather than measured, which is how
    `spring-restclient.yml` came to state "no `exchange` on this synchronous
    surface" about a type that declares two of them."""
    declared = set(catalog("spring-restclient")["matches"]["terminal"])
    observed = set().union(*measured("4").values())
    assert declared <= observed, (
        "spring-restclient.yml declares terminals `RestClient$RequestHeadersSpec` has at "
        f"neither measured minor: {sorted(declared - observed)}"
    )
    assert {"exchangeToMono", "exchangeToFlux"} & declared == set()
    missing = sorted(measured("4")["7.0.2"] - declared)
    assert missing == [], f"spring-restclient.yml declares no terminal for: {missing}"
