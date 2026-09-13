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
    assert numbers == {str(n) for n in range(1, 15)}
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


def _declared_signatures(catalog_id: str) -> set[str]:
    """`name(Largs;)` for every `single_call` row a catalog declares, rebuilt
    from its own `descriptor` so it is comparable with the probe's cells."""
    return {
        f"{row['name']}{str(row['descriptor']).split(')')[0]})"
        for row in catalog(catalog_id)["matches"]["methods"]
    }


def _missing(question: str, catalog_id: str, keep: str | None = None) -> list[str]:
    observed = set().union(*measured_signatures(question).values())
    if keep is not None:
        observed = {name for name in observed if name.startswith(keep + "(")}
    return sorted(observed - _declared_signatures(catalog_id))


def measured_signatures(question: str) -> dict[str, set[str]]:
    """`version -> the whole signatures` the probe recorded for one question.

    `measured()` above reduces to names because the `fluent` grammar keys on
    names; a `single_call` row keys on the erased descriptor, so these
    comparisons need the argument list too."""
    found: dict[str, set[str]] = {}
    for number, row in probe_rows().items():
        if number.rstrip("abcdefgh") != question:
            continue
        found.setdefault(row["version"], set()).update(row["observed"].split(", "))
    assert found, f"CP-12's table carries no question {question}"
    return found


def test_the_kafka_catalogs_declare_every_overload_that_names_a_destination():
    """`A-M6`. Three catalogs declared the arity the fixture happened to call
    and nothing else, and `_matching_method` filters candidates on arity BEFORE
    it consults a descriptor — so `producer.send(record, callback)`,
    `consumer.subscribe(topics, listener)` and
    `kafkaTemplate.send(topic, partition, key, value)` each matched no row and
    derived nothing, while COVERAGE listed all three "✅ shipped" with no arity
    qualification.

    `assign` is excluded by name and the exclusion is asserted: its argument is
    a collection of `TopicPartition` OBJECTS with the topic inside each, which
    is two hops from the call site where every `channel_via` form is one, so it
    is a COVERAGE §5.8 boundary rather than a row."""
    assert _missing("6", "kafka-clients") == []
    assert _missing("7", "kafka-consumer", keep="subscribe") == []
    assert _missing("8", "spring-kafka-template") == []
    assert "assign(Ljava/util/Collection;)" in set().union(*measured_signatures("7").values()), (
        "`KafkaConsumer.assign` is no longer in the measurement the COVERAGE boundary describes"
    )
    assert not any(
        row["name"] == "assign" for row in catalog("kafka-consumer")["matches"]["methods"]
    ), (
        "`assign` is declared, and its topic lives inside a `TopicPartition` constructor two hops "
        "from the call site — `channel_arg: 0` would read the partition list as a destination"
    )


def test_jakarta_jms_declares_every_factory_that_opens_a_consumer():
    """`A-M7`. `jakarta.jms.Session` declares thirteen factories that open a
    receiver on a destination (CP-12 Q9, read off the jar as "returns a
    `MessageConsumer`, a `TopicSubscriber` or a `QueueBrowser`"), of which
    ELEVEN are consumers and the catalog modelled one. Every selector-carrying
    consumer and every durable or shared subscription derived nothing.

    The two `createBrowser` forms are excluded, and the exclusion is asserted
    rather than skipped: a `QueueBrowser` enumerates a queue without consuming
    from it, so publishing it as an inbound endpoint would claim delivery the
    broker never makes."""
    browsers = {
        name
        for name in set().union(*measured_signatures("9").values())
        if name.startswith("createBrowser(")
    }
    assert len(browsers) == 2, f"CP-12 Q9's browser set changed: {sorted(browsers)}"
    consumers = set().union(*measured_signatures("9").values()) - browsers
    assert len(consumers) == 11, (
        f"CP-12 Q9 no longer finds eleven consumer factories: {len(consumers)}"
    )
    missing = sorted(consumers - _declared_signatures("jakarta-jms"))
    assert missing == [], (
        "jakarta-jms.yml declares no row for `Session` factories that open a consumer: "
        f"{missing}. Each is a real inbound JMS endpoint on a destination `channel_via` can "
        "already resolve, and it derives nothing."
    )
    assert not (browsers & _declared_signatures("jakarta-jms")), (
        "`createBrowser` is declared: a `QueueBrowser` enumerates a queue without consuming from "
        "it, so the row would claim a delivery the broker does not make"
    )


def test_the_webflux_router_catalog_reads_every_verb_both_dsls_declare():
    """`A-M9`. `RequestPredicates` and `CoRouterFunctionDsl` each declare seven
    per-verb factories at both measured minors (CP-12 Q11, Q12) and the catalog
    encoded GET/POST/HEAD for Java and GET/POST for Kotlin — which is exactly
    the verb vocabulary `fixtures/orders-service`'s own two route files use.

    That is §8.1 rule 1's failure shape said in the catalog's own words: it
    states the standard it was built to ("exactly what 2E's checkpoint froze
    against a real scan… nothing here is invented past that"), and applying
    that standard to a FIXTURE rather than to the framework encodes the
    examples in front of the author.

    The probe's own upper-case filter is what separates a verb factory from
    `all`, `path`, `accept` and the two generic `method`/`methods` forms, so
    the demanded set below is read off the jar rather than typed here."""
    declared: dict[str, set[str]] = {}
    for entry in catalog("spring-webflux-router")["matches"]["vocabulary"]["verbs"]:
        declared.setdefault(str(entry["owner"]).rpartition(".")[2], set()).add(str(entry["method"]))
    for question, owner in (
        ("11", "RequestPredicates"),
        ("12", "CoRouterFunctionDsl"),
        ("13", "RouterFunctionDsl"),
    ):
        for version, verbs in sorted(measured(question).items()):
            missing = sorted(verbs - declared.get(owner, set()))
            assert missing == [], (
                f"spring-webflux-router.yml declares no verb row for `{owner}` factories the "
                f"framework has at {version}: {missing}. A route declared with one derives "
                "neither a verb nor an address."
            )


def test_both_router_catalogs_declare_every_router_dsl_verb_overload():
    """`W44-verb-overloads`, `GAP-1b` (A1 Task 5). `RouterFunctionDsl` declares
    FIVE overloads per verb on both stacks at both measured minors (CP-12 Q13, Q14),
    and each catalog carried one rule per verb — matched on owner and name alone,
    so four of the five were read through the wrong positions — or, on the reactive
    side, no rule at all. Every measured overload must now have a rule whose
    `arity` and `arg_types` accept it and no other: the erased descriptor the probe
    prints is exactly what the engine's `_matching_rule` compares against."""
    for question, catalog_id, owner in (
        (
            "13",
            "spring-webflux-router",
            "org.springframework.web.reactive.function.server.RouterFunctionDsl",
        ),
        ("14", "spring-mvc-router", "org.springframework.web.servlet.function.RouterFunctionDsl"),
    ):
        rules = [
            entry
            for entry in catalog(catalog_id)["matches"]["vocabulary"]["verbs"]
            if str(entry["owner"]) == owner
        ]
        for version, signatures in sorted(measured_signatures(question).items()):
            unaccepted = sorted(
                signature for signature in signatures if not _accepts_exactly_one(rules, signature)
            )
            assert unaccepted == [], (
                f"{catalog_id}.yml has no single verb rule accepting these `{owner}` overloads "
                f"the framework declares at {version}: {unaccepted}"
            )


def _accepts_exactly_one(rules: list[dict], signature: str) -> bool:
    """Whether exactly one rule's `method`/`arity`/`arg_types` accept a probe-printed
    signature such as `GET(Ljava/lang/String;Lkotlin/jvm/functions/Function1;)`."""
    name, _, rest = signature.partition("(")
    descriptor = rest.rstrip(")")
    types = [segment.lstrip("L").replace("/", ".") for segment in descriptor.split(";") if segment]
    accepting = [
        rule
        for rule in rules
        if str(rule["method"]) == name
        and rule.get("arity") in (None, len(types))
        and all(
            position < len(types) and types[position] == typed
            for position, typed in (rule.get("arg_types") or {}).items()
        )
    ]
    return len(accepting) == 1
