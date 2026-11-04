"""The Akka and Pekko actor catalogs (spec 2026-11-04 §3a): each derives its `actor` row
from a call on the owner it names, and nothing from the same call on any other type.

Invented call sites, `test_call_engines.py`'s form: one behaviour per test, with the
shipped answer pinned against real bytecode in `tests/e2e/test_actors_delivered.py`.
Every descriptor is CP-57's (`scripts/probes/cp57_actors.md`); the two families' are the
same after the package prefix, so each case runs once per family.
"""

from pathlib import Path

import pytest

from flow_facts import straight_line
from sextant.application.resolve.endpoints import derive_endpoints
from sextant.domain.closed_sets import OriginTier
from sextant.domain.factfile import write_fact_file
from sextant.domain.facts import CallArgument, CallSiteFact, CallTarget, Document
from sextant.ingress.catalogs.yaml_source import YamlCatalogSource
from sextant.storage.duckdb.workspace import DuckDbWorkspace

CATALOGS_DIR = Path(__file__).parents[2] / "src" / "sextant" / "catalogs"
CAPABILITIES = {"call_site", "string_constants", "array_arguments"}
_CALLER = "com/acme/actors/Wiring#start()."
# An application's own type with the same method names: the owner conjunct's near-miss.
_OWN = "com/acme/actors/OwnRegistry#"

# The package prefix of each family, in the slash form a call site carries.
_FAMILIES = {"pekko": "org/apache/pekko/", "akka": "akka/"}


def _document() -> Document:
    return Document(
        document_id="doc_1",
        relative_path="com/acme/actors/Wiring.java",
        module_id="com.acme:actors",
        language="java",
        sextant_version="0.1.0",
        fact_schema_version=2,
        scanner_id="asm",
        content_hash="sha256:a",
        origin_entry="target/classes",
        origin_tier=OriginTier.MODULE_OUTPUT,
        redaction_set_hash="sha256:b",
    )


def _call(
    owner: str, name: str, descriptor: str, arguments: list, ordinal: int, result: int
) -> CallSiteFact:
    return CallSiteFact(
        document_id="doc_1",
        caller=_CALLER,
        target=CallTarget(owner=owner, name=name, descriptor=descriptor),
        invoke_kind="special" if name == "<init>" else "static",
        ordinal=ordinal,
        receiver=None,
        result=result,
        arguments=arguments,
    )


def _key_factory(p: str, owner: str, name: str, ordinal: int = 0) -> CallSiteFact:
    """`ServiceKey.create(C.class, "stock")` or `EntityTypeKey.create(C.class, "stock")`,
    result 5."""
    return _call(
        f"{p}{owner}#",
        "create",
        f"(Ljava/lang/Class;Ljava/lang/String;)L{p}{owner};",
        [
            CallArgument(kind="class", symbol="com/acme/actors/Stock$Command#"),
            CallArgument(kind="string", value="stock"),
        ],
        ordinal,
        5,
    )


def _receptionist(p: str, owner: str, name: str) -> list[CallSiteFact]:
    receptionist = f"{p}actor/typed/receptionist/"
    return [
        _key_factory(p, "actor/typed/receptionist/ServiceKey", "create"),
        _call(
            owner,
            name,
            f"(L{receptionist}ServiceKey;L{p}actor/typed/ActorRef;)L{receptionist}Receptionist$Command;",
            [CallArgument(kind="unresolved", source=5), CallArgument(kind="unresolved")],
            1,
            6,
        ),
    ]


def _sharding_init(p: str, owner: str, name: str) -> list[CallSiteFact]:
    sharding = f"{p}cluster/sharding/typed/javadsl/"
    return [
        _key_factory(p, "cluster/sharding/typed/javadsl/EntityTypeKey", "create"),
        _call(
            f"{sharding}Entity#",
            "of",
            f"(L{sharding}EntityTypeKey;L{p}japi/function/Function;)L{sharding}Entity;",
            [CallArgument(kind="unresolved", source=5), CallArgument(kind="unresolved")],
            1,
            7,
        ),
        _call(
            owner,
            name,
            f"(L{sharding}Entity;)L{p}actor/typed/ActorRef;",
            [CallArgument(kind="unresolved", source=7)],
            2,
            8,
        ),
    ]


def _entity_ref(p: str, owner: str, name: str) -> list[CallSiteFact]:
    sharding = f"{p}cluster/sharding/typed/javadsl/"
    return [
        _key_factory(p, "cluster/sharding/typed/javadsl/EntityTypeKey", "create"),
        _call(
            owner,
            name,
            f"(L{sharding}EntityTypeKey;Ljava/lang/String;)L{sharding}EntityRef;",
            [CallArgument(kind="unresolved", source=5), CallArgument(kind="parameter", value=0)],
            1,
            6,
        ),
    ]


def _message(descriptor: str, arity: int, topic: bool):
    """`new Subscribe("stock", self)` and its kin: a literal topic at argument 0, or for
    `Put(self)` the actor ref alone. `~` in the descriptor is the family's prefix."""

    def build(p: str, owner: str, name: str) -> list[CallSiteFact]:
        first = (
            CallArgument(kind="string", value="stock") if topic else CallArgument(kind="unresolved")
        )
        rest = [CallArgument(kind="unresolved")] * (arity - 1)
        return [_call(owner, name, descriptor.replace("~", p), [first, *rest], 0, 6)]

    return build


# `(catalog suffix, owner after the prefix, method, facts builder, expected row)`.
_CASES = [
    (
        "receptionist",
        "actor/typed/receptionist/Receptionist",
        "register",
        _receptionist,
        ("inbound", "stock", "resolved"),
    ),
    (
        "receptionist",
        "actor/typed/receptionist/Receptionist",
        "subscribe",
        _receptionist,
        ("outbound", "stock", "resolved"),
    ),
    (
        "receptionist",
        "actor/typed/receptionist/Receptionist",
        "find",
        _receptionist,
        ("outbound", "stock", "resolved"),
    ),
    (
        "cluster-sharding",
        "cluster/sharding/typed/javadsl/ClusterSharding",
        "init",
        _sharding_init,
        ("inbound", "stock", "resolved"),
    ),
    (
        "cluster-sharding",
        "cluster/sharding/typed/javadsl/ClusterSharding",
        "entityRefFor",
        _entity_ref,
        ("outbound", "stock", "resolved"),
    ),
    (
        "pubsub-subscribe",
        "cluster/pubsub/DistributedPubSubMediator$Subscribe",
        "<init>",
        _message("(Ljava/lang/String;L~actor/ActorRef;)V", 2, topic=True),
        ("inbound", "stock", "resolved"),
    ),
    (
        "pubsub-put",
        "cluster/pubsub/DistributedPubSubMediator$Put",
        "<init>",
        _message("(L~actor/ActorRef;)V", 1, topic=False),
        ("inbound", None, "unresolved"),
    ),
    (
        "pubsub-publish",
        "cluster/pubsub/DistributedPubSubMediator$Publish",
        "<init>",
        _message("(Ljava/lang/String;Ljava/lang/Object;)V", 2, topic=True),
        ("outbound", "stock", "resolved"),
    ),
    (
        "pubsub-send",
        "cluster/pubsub/DistributedPubSubMediator$Send",
        "<init>",
        _message("(Ljava/lang/String;Ljava/lang/Object;Z)V", 3, topic=True),
        ("outbound", "stock", "resolved"),
    ),
]

_PARAMS = [
    pytest.param(family, *case, id=f"{family}-{case[0]}-{case[2]}")
    for family in _FAMILIES
    for case in _CASES
]


def _rows(tmp_path: Path, family: str, catalog: str, facts: list) -> set:
    write_fact_file(tmp_path / "facts" / "Wiring.jsonl", _document(), straight_line(facts))
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    shipped = next(
        c for c in YamlCatalogSource(CATALOGS_DIR).load() if c.id == f"{family}-{catalog}"
    )
    assert derive_endpoints(workspace, [shipped], capabilities=CAPABILITIES) == []
    rows = {
        (str(r["direction"]), r["path"], str(r["resolution"]))
        for r in workspace.query("endpoints")
        if str(r["protocol"]) == "actor"
    }
    workspace.close()
    return rows


@pytest.mark.parametrize(("family", "catalog", "owner", "name", "build", "expected"), _PARAMS)
def test_a_call_on_the_owner_derives_its_actor_row(
    tmp_path, family, catalog, owner, name, build, expected
):
    """The positive each near-miss below is measured against: the call at CP-57's
    descriptor on the owner the catalog names derives the row, the key read through its
    factory (`ServiceKey.create`/`EntityTypeKey.create` argument 1, and `Entity.of`
    argument 0 before it for `init`)."""
    p = _FAMILIES[family]
    assert _rows(tmp_path, family, catalog, build(p, f"{p}{owner}#", name)) == {expected}


@pytest.mark.declines("pekko-receptionist")
@pytest.mark.declines("pekko-cluster-sharding")
@pytest.mark.declines("pekko-pubsub-subscribe")
@pytest.mark.declines("pekko-pubsub-put")
@pytest.mark.declines("pekko-pubsub-publish")
@pytest.mark.declines("pekko-pubsub-send")
@pytest.mark.declines("akka-receptionist")
@pytest.mark.declines("akka-cluster-sharding")
@pytest.mark.declines("akka-pubsub-subscribe")
@pytest.mark.declines("akka-pubsub-put")
@pytest.mark.declines("akka-pubsub-publish")
@pytest.mark.declines("akka-pubsub-send")
@pytest.mark.pins("single_call.call-site-owner")
@pytest.mark.parametrize(("family", "catalog", "owner", "name", "build", "expected"), _PARAMS)
def test_the_same_call_on_an_applications_own_type_derives_nothing(
    tmp_path, family, catalog, owner, name, build, expected
):
    """§10 near-miss, measuring the OWNER conjunct alone: the name, the descriptor and the
    key's factory all hold, and only the type the call is made on differs. `register`,
    `subscribe`, `find`, `init` and a constructor are ordinary names for an application's
    own registry or message classes, and without the owner conjunct each would publish an
    actor key at `resolved`."""
    p = _FAMILIES[family]
    assert _rows(tmp_path, family, catalog, build(p, _OWN, name)) == set()
