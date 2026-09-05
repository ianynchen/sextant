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


# `NAME[attr():Ldescriptor;,…]` as `probe.py` prints one Retrofit annotation.
_ANNOTATION = re.compile(r"^(\w+)\[(.*)\]$")
# A request-method annotation's own path attribute: a SCALAR `String`. `@Headers`
# is method-targeted too and declares a `String[] value()` of header lines, which
# is the framework's own way of saying it names no path.
_NAMES_A_PATH = "value():Ljava/lang/String;"


def test_retrofit_declares_every_annotation_that_names_a_request_method():
    """`A-M5`. `retrofit2.http` holds eight request-method annotations at
    2.11.0 (CP-12 Q5) and the catalog declared six, with `@OPTIONS` deriving
    nothing and no COVERAGE row saying so.

    The seven path-carrying ones are identified by the framework's own
    declaration rather than by a list typed here: a scalar `String value()`.
    `@HTTP` is the eighth and is deliberately absent — it holds its verb in a
    plain `String` that `$method_from`'s enum-symbol extract would turn into
    the empty string — so it is asserted as an EXCLUSION rather than skipped,
    which is what stops the boundary from being lost the next time this list is
    read."""
    [observed] = [row["observed"] for number, row in probe_rows().items() if number == "5"]
    parsed = {
        match.group(1): match.group(2)
        for part in observed.split(", ")
        if (match := _ANNOTATION.match(part))
    }
    path_carrying = {name for name, attributes in parsed.items() if _NAMES_A_PATH in attributes}
    assert "HTTP" in parsed and _NAMES_A_PATH not in parsed["HTTP"], (
        "`@HTTP` no longer looks the way the boundary in `retrofit.yml` describes; re-read it"
    )

    declared = {
        str(entry["fqn"]).rpartition(".")[2]
        for entry in catalog("retrofit")["matches"]["mapping"]["annotations"]
    }
    assert sorted(path_carrying - declared) == [], (
        "retrofit.yml declares no mapping entry for request-method annotations Retrofit has: "
        f"{sorted(path_carrying - declared)}. A method wearing one derives nothing at all."
    )
    assert "HTTP" not in declared, (
        "`retrofit2.http.HTTP` is declared, and the engine cannot read its verb: "
        "`$method_from` extracts an enum constant's name and `@HTTP.method` is a plain String, "
        "so the row would ship with `method: ''`. Change the engine first."
    )


# `name:Ldescriptor;` and `name:Ldescriptor;=AliasFor(target)`, as `probe.py`
# prints one annotation attribute.
_ATTRIBUTE = re.compile(r"^(\w+):([^=]+)(?:=AliasFor\((\w+)\))?$")


def test_the_sqs_listener_catalog_reads_both_spellings_of_one_attribute():
    """`A-M8`. `@SqsListener` declares `value()` and `queueNames()`, and
    `queueNames` carries `@AliasFor(value = "value")` (CP-12 Q10) — Spring's
    own statement that they are ONE attribute. The catalog read `value` alone,
    so a `queueNames` listener composed an empty destination and the
    addresses-nothing gate withheld the row: absent from the export, not
    present with a blank address.

    Read out of the probe's alias record rather than hard-coded, so a second
    alias added by a later Spring Cloud AWS fails here instead of going
    silent."""
    [observed] = [row["observed"] for number, row in probe_rows().items() if number == "10"]
    aliases = {
        match.group(1): match.group(3)
        for part in observed.split(", ")
        if (match := _ATTRIBUTE.match(part))
    }
    destination = {name for name, target in aliases.items() if target == "value"} | {"value"}
    declared = set(catalog("spring-sqs")["matches"]["mapping"]["path_from"])
    assert sorted(destination - declared) == [], (
        "spring-sqs.yml does not read every spelling of `@SqsListener`'s destination attribute: "
        f"{sorted(destination - declared)}. A listener using one derives nothing at all."
    )
    assert declared <= set(aliases), (
        "spring-sqs.yml reads `@SqsListener` attributes it does not declare: "
        f"{sorted(declared - set(aliases))}"
    )
