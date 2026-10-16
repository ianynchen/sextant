"""Every type-gated destination position can be DECIDED, or this fails and names it.

`single_call` refuses a producer whose return type cannot be the type its row declares at
the destination position — Java separates two overloads by parameter type, and §8.1 says
mirroring a language's own rule is not optional. That refusal is only safe if the
conformance table is COMPLETE for the surface it governs: a missing entry refuses a
producer that should have been followed, and §8 says an omission leaves no wrong row for
a reader to notice.

So the table is not trusted to be complete — it is CHECKED, and the check derives its own
work from the catalogs rather than from a list anyone maintains. §8.3: a new rule ships
with every existing site it governs, enumerated as a failing allowlist that must shrink.

**The blind spot this was built to avoid.** The first version of this measurement read
producer return types from the fixtures' own `call_sites`. That had a 40% hole — 56 of 138
pairs unknown, because 11 producers (`Arrays.asList`, `Collections.singletonList`,
`Session.createTopic`, both `javax.jms` spellings and more) are named by a catalog and
exercised by no fixture. A pair nothing exercises is exactly where a silent miss would
live, so the return types below come from `javap` ON THE JAR instead, and are committed
here as measurement rather than re-derived from whatever happens to be scanned.
"""

from pathlib import Path

import yaml

from sextant.domain.symbols import descriptor_parameter_types
from sextant.ingress.catalogs.yaml_source import YamlCatalogSource

CATALOGS = Path(__file__).resolve().parents[2] / "src" / "sextant" / "catalogs"

# MEASURED with `javap`, one class per entry, against the JDK this repo builds with
# (Temurin 21.0.12.1+1) and these jars from the local Maven repository:
#   jakarta.jms-api-3.1.0.jar, javax.jms-api-2.0.jar,
#   pekko-connectors-kafka_2.13-1.1.0.jar, vertx-core-5.0.0.jar
#
# A constructor produces the type it constructs, which is why `java.net.URI.<init>` maps to
# `java.net.URI` and not to the `void` its descriptor records.
#
# **An entry is added here only after running `javap`**, never from recollection: §8.1
# states that a rule taken from memory is a prediction, and this repository has shipped a
# wrong one that way. The first draft of the conformance table asserted
# `java.util.List extends java.util.Collection`, which is FALSE on JDK 21 — `List` reaches
# `Collection` through `SequencedCollection` (JEP 431). Measuring caught it.
_PRODUCER_RETURNS = {
    "io.vertx.core.eventbus.MessageConsumerOptions.setAddress": (
        "io.vertx.core.eventbus.MessageConsumerOptions"
    ),
    "jakarta.jms.Session.createQueue": "jakarta.jms.Queue",
    "jakarta.jms.Session.createTopic": "jakarta.jms.Topic",
    "java.net.URI.<init>": "java.net.URI",
    "java.net.URI.create": "java.net.URI",
    "java.util.Arrays.asList": "java.util.List",
    "java.util.Collections.singletonList": "java.util.List",
    "java.util.List.of": "java.util.List",
    "java.util.regex.Pattern.compile": "java.util.regex.Pattern",
    "javax.jms.Session.createQueue": "javax.jms.Queue",
    "javax.jms.Session.createTopic": "javax.jms.Topic",
    "org.apache.pekko.kafka.Subscriptions.topicPattern": (
        "org.apache.pekko.kafka.AutoSubscription"
    ),
    "org.apache.pekko.kafka.Subscriptions.topics": "org.apache.pekko.kafka.AutoSubscription",
}


def _rows_with_a_destination_type(document: object) -> list[dict]:
    """Every row the type gate governs: one declaring `channel_via`, a `descriptor` to read
    a parameter type from, and a destination slot to read it AT.

    `fluent`'s roots, steps and terminals declare `url_via`/`channel_via` with neither a
    descriptor nor a `channel_arg` — a different shape, and Task 9's question rather than
    this one. They are skipped here rather than silently counted as decidable.
    """
    found: list[dict] = []

    def walk(node: object) -> None:
        if isinstance(node, dict):
            has_slot = node.get("channel_arg") is not None or node.get("url_arg") is not None
            if "channel_via" in node and node.get("descriptor") and has_slot:
                found.append(node)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(document)
    return found


def _conforms(got: str, want: str, table: list[dict]) -> bool:
    """The engine's own rule, restated nowhere: equality, then the declared links walked
    transitively. Kept in step with `single_call._conforms` by this module's last test,
    which asserts the two agree on every pair the catalogs produce."""
    if got == want:
        return True
    reach, frontier = {got}, [got]
    while frontier:
        current = frontier.pop()
        for entry in table:
            if entry["subtype"] == current and entry["supertype"] not in reach:
                if entry["supertype"] == want:
                    return True
                reach.add(entry["supertype"])
                frontier.append(entry["supertype"])
    return False


def _pairs() -> list[tuple[str, str, str, str]]:
    pairs: list[tuple[str, str, str, str]] = []
    for path in sorted(CATALOGS.glob("*.yml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(document, dict):
            continue
        for row in _rows_with_a_destination_type(document):
            declared = descriptor_parameter_types(str(row["descriptor"]))
            slot = row.get("url_arg", row.get("channel_arg"))
            if not isinstance(slot, int) or slot >= len(declared):
                continue
            for entry in row.get("channel_via") or []:
                if isinstance(entry, dict) and "owner" in entry:
                    pairs.append(
                        (path.name, declared[slot], str(entry["owner"]), str(entry["method"]))
                    )
    return pairs


def test_every_type_gated_producer_has_a_measured_return_type():
    """**The allowlist that must shrink, and the one that must not grow.** A catalog naming
    a producer absent from `_PRODUCER_RETURNS` makes the gate undecidable at that position,
    so it fails HERE — in the fast suite, naming the producer and the `javap` to run — and
    never as a destination that quietly stopped resolving."""
    missing = sorted(
        {
            f"{owner}.{method}  (declared by {catalog})"
            for catalog, _, owner, method in _pairs()
            if f"{owner}.{method}" not in _PRODUCER_RETURNS
        }
    )
    assert missing == [], (
        "type-gated producers with no measured return type — run "
        "`javap -cp <the owner's jar> <owner>` and add the result to `_PRODUCER_RETURNS`:\n  "
        + "\n  ".join(missing)
    )


def test_every_type_gated_pair_is_decided_by_the_conformance_table():
    """Each pair must come out conformant or not — and a pair the table cannot reach is
    neither. Those are listed by name with the `javap` that would settle them, because a
    pair nobody decided is a producer the engine refuses for no stated reason."""
    table = YamlCatalogSource(CATALOGS).type_model()
    undecided = sorted(
        {
            f"{got} -> {want}  (needed by {catalog}: {owner}.{method})"
            for catalog, want, owner, method in _pairs()
            if (got := _PRODUCER_RETURNS.get(f"{owner}.{method}")) is not None
            and not _conforms(got, want, table)
        }
    )
    assert undecided == [], (
        "type pairs the conformance table cannot decide. Each is either a missing "
        "`type-models/` entry (measure it with `javap` and add it, with its `by`) or a "
        "CATALOG DEFECT — a producer declared on a row whose parameter type it cannot "
        "satisfy, which is what the sixteen `createQueue` entries on the JMS catalogs' "
        "`Topic`-typed rows turned out to be:\n  " + "\n  ".join(undecided)
    )


def test_every_conformance_entry_is_reachable_from_a_catalog():
    """The allowlist shrinks from both ends. An entry no catalog needs is either dead
    weight or the trace of a declaration someone removed, and either way it should not sit
    in a measured table implying it is load-bearing."""
    table = YamlCatalogSource(CATALOGS).type_model()
    needed = {
        (got, want)
        for _, want, owner, method in _pairs()
        if (got := _PRODUCER_RETURNS.get(f"{owner}.{method}")) is not None and got != want
    }
    reachable = {
        (subtype, supertype)
        for subtype, supertype in {(e["subtype"], e["supertype"]) for e in table}
        if any(_conforms(got, want, table) and got == subtype for got, want in needed)
    }
    orphans = sorted(
        f"{e['subtype']} -> {e['supertype']}"
        for e in table
        if (e["subtype"], e["supertype"]) not in reachable
    )
    assert orphans == [], (
        "`type-models/` entries no catalog's type-gated row needs — remove them, or say "
        "which row is meant to need them:\n  " + "\n  ".join(orphans)
    )


def test_the_engines_conformance_rule_and_this_tests_agree():
    """Two readings of one rule drift (§0a), so this asserts they have not. If
    `single_call._conforms` is changed and this is not, the disagreement fails here rather
    than becoming a gate that passes while the engine refuses."""
    from sextant.application.resolve.engines.single_call import _conforms as engine_conforms
    from sextant.application.resolve.shapes.rooting import _catalog_symbol

    table = YamlCatalogSource(CATALOGS).type_model()
    for _, want, owner, method in _pairs():
        got = _PRODUCER_RETURNS.get(f"{owner}.{method}")
        if got is None:
            continue
        mine = _conforms(got, want, table)
        theirs = engine_conforms(_catalog_symbol(got), _catalog_symbol(want), table)
        assert mine == theirs, f"{got} -> {want}: this test says {mine}, the engine says {theirs}"
