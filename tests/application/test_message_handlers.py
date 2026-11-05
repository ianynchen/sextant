"""Message handler registrations are read per behavior (spec 2026-11-04 §3b, §3d items 1-3):
one `message_handlers` row per case, in chain order, and `reachable_handlers` applies the
first-match rule a behavior dispatches by.

The chains are hand-built call sites in the shape javac emits (CP-57), read through the
shipped Pekko handler catalog, so each test is one shape: an immutable builder chain, a
mutable one held in a local, persistence state builders. The first-match rule is tested on
rows directly, because it is a rule over rows. The whole pipeline over real bytecode is
`tests/e2e/test_actors_delivered.py`.
"""

from pathlib import Path

import pytest

from flow_facts import straight_line
from sextant.application.ports.catalogs import Catalog
from sextant.application.resolve.message_handlers import (
    reachable_handlers,
    record_message_handlers,
    served_cases,
)
from sextant.domain.closed_sets import OriginTier
from sextant.domain.factfile import write_fact_file
from sextant.domain.facts import CallArgument, CallSiteFact, CallTarget, Document, SymbolFact
from sextant.domain.symbols import method_descriptor
from sextant.ingress.catalogs.yaml_source import YamlCatalogSource
from sextant.resources import catalogs_dir
from sextant.storage.duckdb.workspace import DuckDbWorkspace

_MODULE = "sextant-jvm maven com.acme/shop 1.0.0 "
_SHOP = "com/acme/shop/Shop#"
_P = "org/apache/pekko"
_BEHAVIORS = f"{_P}/actor/typed/javadsl/Behaviors#"
_BEHAVIOR_BUILDER = f"{_P}/actor/typed/javadsl/BehaviorBuilder#"
_COMMAND_BUILDER = f"{_P}/persistence/typed/javadsl/CommandHandlerBuilder#"
_BY_STATE = f"{_P}/persistence/typed/javadsl/CommandHandlerBuilderByState#"
_IMMUTABLE = f"L{_P}/actor/typed/javadsl/BehaviorBuilder;"
_STATE = f"L{_P}/persistence/typed/javadsl/CommandHandlerBuilderByState;"
_FUNCTION = f"L{_P}/japi/function/Function;"
_ON_MESSAGE = f"(Ljava/lang/Class;{_FUNCTION})"
_ON_COMMAND = "(Ljava/lang/Class;Ljava/util/function/BiFunction;)"
_HANDLER_JVM = "(Ljava/lang/Object;)Ljava/lang/Object;"


def _handlers_catalog(catalog_id: str = "pekko-actor-handlers") -> Catalog:
    return next(
        catalog for catalog in YamlCatalogSource(catalogs_dir()).load() if catalog.id == catalog_id
    )


# The two families' handler catalogs, by the package their builders live in: the same
# descriptors after the prefix (CP-57 finding 10).
_FAMILIES = [("pekko-actor-handlers", "org/apache/pekko"), ("akka-actor-handlers", "akka")]


def _document() -> Document:
    return Document(
        document_id="doc_1",
        relative_path="com/acme/shop/Shop.java",
        module_id="com.acme:shop",
        language="java",
        sextant_version="0.1.0",
        fact_schema_version=2,
        scanner_id="asm",
        content_hash="sha256:a",
        origin_entry="target/classes",
        origin_tier=OriginTier.MODULE_OUTPUT,
        redaction_set_hash="sha256:b",
    )


def _site(
    caller: str,
    ordinal: int,
    owner: str,
    name: str,
    descriptor: str,
    *,
    receiver: int | None = None,
    result: int | None = None,
    arguments: tuple[CallArgument, ...] = (),
) -> CallSiteFact:
    return CallSiteFact(
        document_id="doc_1",
        caller=caller,
        target=CallTarget(owner=owner, name=name, descriptor=descriptor),
        invoke_kind="static" if receiver is None else "virtual",
        ordinal=ordinal,
        receiver=receiver,
        result=result,
        arguments=list(arguments),
    )


def _class(name: str) -> CallArgument:
    return CallArgument(kind="class", symbol=f"com/acme/shop/Shop${name}#")


def _handler(name: str) -> CallArgument:
    """A method reference `Shop::<name>`: a `lambda` argument naming the method itself."""
    return CallArgument(
        kind="lambda", symbol=method_descriptor(_SHOP, name, _HANDLER_JVM), captures=0
    )


def _handler_symbol(name: str) -> SymbolFact:
    return SymbolFact(
        document_id="doc_1",
        symbol=_MODULE + method_descriptor(_SHOP, name, _HANDLER_JVM),
        construct_kind="method",
        enclosing=_MODULE + _SHOP,
    )


def _caller(name: str) -> str:
    return method_descriptor(_SHOP, name, "()Ljava/lang/Object;")


def _rows(
    tmp_path: Path,
    facts: list,
    hierarchy: tuple[tuple[str, str], ...] = (),
    catalog_id: str = "pekko-actor-handlers",
) -> list[dict]:
    """The `message_handlers` rows `facts` give, `hierarchy` as `(child, superclass)` pairs,
    each written as the child's own symbol fact naming its superclass, as the extractor
    writes one."""
    handlers = sorted(
        {
            str(argument.symbol).split("#")[1].split("(")[0]
            for fact in facts
            if isinstance(fact, CallSiteFact)
            for argument in fact.arguments
            if argument.kind == "lambda"
        }
    )
    write_fact_file(
        tmp_path / "facts" / "Shop.jsonl",
        _document(),
        straight_line(
            [
                *facts,
                *(_handler_symbol(name) for name in handlers),
                *(
                    SymbolFact(
                        document_id="doc_1",
                        symbol=_MODULE + child,
                        construct_kind="class",
                        superclass=_MODULE + parent,
                    )
                    for child, parent in hierarchy
                ),
            ]
        ),
    )
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    try:
        workspace.load_facts(tmp_path / "facts")
        record_message_handlers(workspace, [_handlers_catalog(catalog_id)])
        return workspace.query("message_handlers")
    finally:
        workspace.close()


def _cases(rows: list[dict]) -> list[tuple]:
    """`(behavior's caller method, position, message_type, message_value, predicated,
    handler's method name)`, the module prefix and signatures left out."""
    return [
        (
            str(row["behavior"]).split("#")[1].split("(")[0]
            + "#"
            + str(row["behavior"]).rsplit("#", 1)[1],
            row["position"],
            None if row["message_type"] is None else str(row["message_type"]).split("$")[1],
            row["message_value"],
            row["predicated"],
            None if row["handler"] is None else str(row["handler"]).split("#")[1].split("(")[0],
        )
        for row in rows
    ]


@pytest.mark.pins("message-handlers.the-cases-are-WRITTEN")
def test_an_immutable_builder_chain_is_one_behavior(tmp_path: Path):
    """`Behaviors.receive(Command.class).onMessage(A).onMessage(B).onMessage(C).build()`:
    each `onMessage` returns a NEW builder (CP-57 finding 1), so the behavior is the chain
    walked from each result to the next call, and its cases keep the chain's order."""
    caller = _caller("behavior")
    facts = [
        _site(
            caller,
            0,
            _BEHAVIORS,
            "receive",
            f"(Ljava/lang/Class;){_IMMUTABLE}",
            result=1,
            arguments=(_class("Command"),),
        ),
        _site(
            caller,
            1,
            _BEHAVIOR_BUILDER,
            "onMessage",
            f"{_ON_MESSAGE}{_IMMUTABLE}",
            receiver=1,
            result=2,
            arguments=(_class("Reserve"), _handler("onReserve")),
        ),
        _site(
            caller,
            2,
            _BEHAVIOR_BUILDER,
            "onMessage",
            f"{_ON_MESSAGE}{_IMMUTABLE}",
            receiver=2,
            result=3,
            arguments=(_class("Release"), _handler("onRelease")),
        ),
        _site(
            caller,
            3,
            _BEHAVIOR_BUILDER,
            "onMessage",
            f"{_ON_MESSAGE}{_IMMUTABLE}",
            receiver=3,
            result=4,
            arguments=(_class("Restock"), _handler("onRestock")),
        ),
        _site(
            caller,
            4,
            _BEHAVIOR_BUILDER,
            "build",
            f"()L{_P}/actor/typed/Behavior;",
            receiver=4,
            result=5,
        ),
    ]
    rows = _rows(tmp_path, facts)
    assert _cases(rows) == [
        ("behavior#0", 0, "Reserve#", None, False, "onReserve"),
        ("behavior#0", 1, "Release#", None, False, "onRelease"),
        ("behavior#0", 2, "Restock#", None, False, "onRestock"),
    ]
    assert {str(row["behavior"]) for row in rows} == {f"{caller}#0"}
    assert {str(row["handler"]).startswith(_MODULE) for row in rows} == {True}
    assert {row["delivers"] for row in rows} == {False}
    assert {row["evidence"] for row in rows} == {"compiler"}


def _row(behavior: str, position: int, message_type=None, message_value=None, predicated=False):
    return {
        "behavior": behavior,
        "position": position,
        "message_type": message_type,
        "message_value": message_value,
        "predicated": predicated,
        "handler": f"h{behavior}{position}",
        "delivers": False,
        "evidence": "compiler",
    }


_SUPERTYPES = {"Reserve#": {"Command#"}, "Release#": {"Command#"}, "Tick#": {"Command#"}}


@pytest.mark.pins("message-handlers.the-FIRST-unpredicated-match-wins")
def test_first_match_wins_within_a_behavior():
    """A message reaches the FIRST unpredicated case its class is assignable to: `Reserve`
    is a `Command`, so `onMessage(Command)` at 0 takes it and `onMessage(Reserve)` at 1 is
    never reached."""
    rows = [_row("b", 0, "Command#"), _row("b", 1, "Reserve#")]
    assert [row["position"] for row in reachable_handlers(rows, "Reserve#", None, _SUPERTYPES)] == [
        0
    ]


def test_the_case_a_message_reaches_is_found_past_cases_of_other_classes():
    """A case for another class neither matches nor shadows: `Release` reaches position 1."""
    rows = [_row("b", 0, "Reserve#"), _row("b", 1, "Release#"), _row("b", 2, "Command#")]
    assert [row["position"] for row in reachable_handlers(rows, "Release#", None, _SUPERTYPES)] == [
        1
    ]


@pytest.mark.pins("message-handlers.a-PREDICATED-case-never-shadows")
def test_a_predicated_case_never_shadows():
    """`onMessage(Release, pred)` at 1 may decline a `Release` (its predicate is not read), so
    `onMessage(Release)` at 2 is reachable too; both are hop targets."""
    rows = [
        _row("b", 0, "Reserve#"),
        _row("b", 1, "Release#", predicated=True),
        _row("b", 2, "Release#"),
        _row("b", 3, "Command#"),
    ]
    assert [row["position"] for row in reachable_handlers(rows, "Release#", None, _SUPERTYPES)] == [
        1,
        2,
    ]


@pytest.mark.pins("message-handlers.a-PREDICATE-only-case-tests-every-message")
def test_a_predicate_with_no_class_tests_every_message():
    """`onCommand(Predicate, h)` names no class: it may take any command, so it is reachable
    by every message and shadows nothing."""
    rows = [_row("b", 0, predicated=True), _row("b", 1, "Reserve#")]
    assert [row["position"] for row in reachable_handlers(rows, "Reserve#", None, _SUPERTYPES)] == [
        0,
        1,
    ]


@pytest.mark.pins("message-handlers.a-VALUE-case-matches-by-IDENTITY")
def test_a_value_case_matches_its_constant_only():
    """`onMessageEquals(Tick.INSTANCE)` matches the constant by identity (§3d item 3): a
    `Tick.INSTANCE` send reaches it, a `new Tick()` (its class alone) does not, and reaches
    the class case after it."""
    rows = [_row("b", 0, message_value="Tick#INSTANCE."), _row("b", 1, "Command#")]
    constant = reachable_handlers(rows, "Tick#", "Tick#INSTANCE.", _SUPERTYPES)
    assert [row["position"] for row in constant] == [0]
    constructed = reachable_handlers(rows, "Tick#", None, _SUPERTYPES)
    assert [row["position"] for row in constructed] == [1]


def test_each_behavior_answers_on_its_own():
    """Two behaviors handling one class both reach a handler, one each (§3c): a message is
    not dispatched across behaviors, and which one a reference holds is not read."""
    rows = [_row("a", 0, "Reserve#"), _row("b", 0, "Command#"), _row("b", 1, "Reserve#")]
    assert [
        (row["behavior"], row["position"])
        for row in reachable_handlers(rows, "Reserve#", None, _SUPERTYPES)
    ] == [("a", 0), ("b", 0)]


def test_a_message_no_case_takes_reaches_nothing():
    rows = [_row("b", 0, "Reserve#")]
    assert reachable_handlers(rows, "Placed#", None, _SUPERTYPES) == []


_CONSTANTS = {"Tick#INSTANCE.": "Tick#", "Other#INSTANCE.": "Other#"}


def _served(rows: list[dict], message_class: str | None) -> list[tuple]:
    return [
        (row["behavior"], row["position"])
        for row in served_cases(rows, message_class, _SUPERTYPES, _CONSTANTS)
    ]


@pytest.mark.pins("message-handlers.a-key-reaches-the-cases-of-its-SUBTYPES")
def test_a_key_class_reaches_each_case_of_a_subtype():
    """An inbound key carries a `Command` (spec §3d item 6): every case some `Command` reaches
    is one of its handlers — `Reserve`'s, both `Release` cases (a predicate never shadows) —
    and a case for a class that is no `Command` is not."""
    rows = [
        _row("b", 0, "Reserve#"),
        _row("b", 1, "Release#", predicated=True),
        _row("b", 2, "Release#"),
        _row("c", 0, "Placed#"),
    ]
    assert _served(rows, "Command#") == [("b", 0), ("b", 1), ("b", 2)]


@pytest.mark.pins("message-handlers.a-key-reaches-a-VALUE-case-of-its-class")
def test_a_key_class_reaches_a_value_case_whose_constant_is_one():
    """`onMessageEquals(Tick.INSTANCE)`: the constant is a `Tick`, a `Command`, so a key
    carrying `Command`s reaches the case. A constant of a class that is no `Command` does
    not."""
    rows = [
        _row("b", 0, message_value="Tick#INSTANCE."),
        _row("b", 1, message_value="Other#INSTANCE."),
    ]
    assert _served(rows, "Command#") == [("b", 0)]


def test_a_case_a_key_class_shadows_is_not_reached():
    """The hop rule, per class: `onMessage(Command)` at 0 takes every `Command`, so
    `onMessage(Reserve)` after it is never run and is no handler of the key."""
    rows = [_row("b", 0, "Command#"), _row("b", 1, "Reserve#")]
    assert _served(rows, "Command#") == [("b", 0)]


def test_a_key_of_one_class_reaches_only_that_class():
    """A key carrying `Reserve` alone (the samples' `ServiceKey.create(ProcessText.class,
    …)`) reaches `Reserve`'s case, not `Release`'s."""
    rows = [_row("b", 0, "Reserve#"), _row("b", 1, "Release#")]
    assert _served(rows, "Reserve#") == [("b", 0)]


def test_a_key_whose_class_no_case_takes_reaches_nothing():
    """And a class not read reaches nothing either: never every case."""
    rows = [_row("b", 0, "Reserve#")]
    assert _served(rows, "Placed#") == []
    assert _served(rows, None) == []


def _state_chain(caller: str, at: int, builder: int, root: str, case: str, handler: str):
    """`builder.<root>(…).onCommand(<case>.class, <handler>)` at ordinals `at`, `at + 1`."""
    root_descriptor = {
        "forAnyState": f"(){_STATE}",
        "forState": f"(Ljava/util/function/Predicate;){_STATE}",
    }[root]
    return [
        _site(
            caller,
            at,
            _COMMAND_BUILDER,
            root,
            root_descriptor,
            receiver=builder,
            result=10 + at,
        ),
        _site(
            caller,
            at + 1,
            _BY_STATE,
            "onCommand",
            f"{_ON_COMMAND}{_STATE}",
            receiver=10 + at,
            result=20 + at,
            arguments=(_class(case), _handler(handler)),
        ),
    ]


@pytest.mark.pins("message-handlers.each-ROOT-is-its-own-behavior")
def test_each_for_state_chain_is_its_own_behavior(tmp_path: Path):
    """`forState(p1).onCommand(Cancel, a)`, `forState(p2).onCommand(Cancel, b)` and
    `forAnyState().onCommand(Place, c)` on one `CommandHandlerBuilder`: each call returns a
    NEW state builder (CP-57 finding 2), so each is a behavior of its own, and a class handled
    in two states is a case in each."""
    caller = _caller("commandHandler")
    facts = [
        _site(
            caller, 0, _SHOP, "newCommandHandlerBuilder", f"()L{_COMMAND_BUILDER[:-1]};", result=1
        ),
        *_state_chain(caller, 1, 1, "forState", "Cancel", "onCancelEmpty"),
        *_state_chain(caller, 3, 1, "forState", "Cancel", "onCancel"),
        *_state_chain(caller, 5, 1, "forAnyState", "Place", "onPlace"),
        _site(
            caller,
            7,
            _COMMAND_BUILDER,
            "build",
            f"()L{_P}/persistence/typed/javadsl/CommandHandler;",
            receiver=1,
            result=30,
        ),
    ]
    assert _cases(_rows(tmp_path, facts)) == [
        ("commandHandler#1", 0, "Cancel#", None, False, "onCancelEmpty"),
        ("commandHandler#3", 0, "Cancel#", None, False, "onCancel"),
        ("commandHandler#5", 0, "Place#", None, False, "onPlace"),
    ]


def test_a_state_chain_holds_every_case_it_is_given(tmp_path: Path):
    """The persistence shape real code writes (`ShoppingCart`, `AuctionEntity`):
    `b.forState(p).onCommand(A).onCommand(B).onCommand(C); b.forAnyState().onCommand(Get)`.
    `onCommand` returns `this` and is also what makes a state builder a behavior, so reaching
    the first one does not end the chain: one behavior with three cases, and one with one."""
    caller = _caller("commandHandler")
    on_command = f"{_ON_COMMAND}{_STATE}"
    facts = [
        _site(
            caller, 0, _SHOP, "newCommandHandlerBuilder", f"()L{_COMMAND_BUILDER[:-1]};", result=1
        ),
        _site(
            caller,
            1,
            _COMMAND_BUILDER,
            "forState",
            f"(Ljava/util/function/Predicate;){_STATE}",
            receiver=1,
            result=2,
        ),
        _site(
            caller,
            2,
            _BY_STATE,
            "onCommand",
            on_command,
            receiver=2,
            result=3,
            arguments=(_class("AddItem"), _handler("onAddItem")),
        ),
        _site(
            caller,
            3,
            _BY_STATE,
            "onCommand",
            on_command,
            receiver=3,
            result=4,
            arguments=(_class("RemoveItem"), _handler("onRemoveItem")),
        ),
        _site(
            caller,
            4,
            _BY_STATE,
            "onCommand",
            on_command,
            receiver=4,
            result=5,
            arguments=(_class("Checkout"), _handler("onCheckout")),
        ),
        _site(caller, 5, _COMMAND_BUILDER, "forAnyState", f"(){_STATE}", receiver=1, result=6),
        _site(
            caller,
            6,
            _BY_STATE,
            "onCommand",
            on_command,
            receiver=6,
            result=7,
            arguments=(_class("Get"), _handler("onGet")),
        ),
        _site(
            caller,
            7,
            _COMMAND_BUILDER,
            "build",
            f"()L{_P}/persistence/typed/javadsl/CommandHandler;",
            receiver=1,
            result=8,
        ),
    ]
    assert _cases(_rows(tmp_path, facts)) == [
        ("commandHandler#1", 0, "AddItem#", None, False, "onAddItem"),
        ("commandHandler#1", 1, "RemoveItem#", None, False, "onRemoveItem"),
        ("commandHandler#1", 2, "Checkout#", None, False, "onCheckout"),
        ("commandHandler#5", 0, "Get#", None, False, "onGet"),
    ]


@pytest.mark.parametrize("catalog_id, prefix", _FAMILIES)
def test_the_classic_builders_static_factory_starts_a_behavior(
    tmp_path: Path, catalog_id: str, prefix: str
):
    """`ReceiveBuilder.create().match(Price.class, h).build()` (`ClusterClient` in the Pekko
    samples): the static factory returns a new classic builder (CP-57), a root like
    `receiveBuilder()`."""
    caller = _caller("createReceive")
    builder = f"{prefix}/japi/pf/ReceiveBuilder"
    facts = [
        _site(caller, 0, f"{builder}#", "create", f"()L{builder};", result=1),
        _site(
            caller,
            1,
            f"{builder}#",
            "match",
            f"(Ljava/lang/Class;L{prefix}/japi/pf/FI$UnitApply;)L{builder};",
            receiver=1,
            result=2,
            arguments=(_class("Price"), _handler("onPrice")),
        ),
        _site(
            caller,
            2,
            f"{builder}#",
            "build",
            f"()L{prefix}/actor/AbstractActor$Receive;",
            receiver=2,
            result=3,
        ),
    ]
    assert _cases(_rows(tmp_path, facts, catalog_id=catalog_id)) == [
        ("createReceive#0", 0, "Price#", None, False, "onPrice"),
    ]


@pytest.mark.pins("message-handlers.the-SUPERTYPE-closure-is-walked")
def test_a_supertype_closure_is_walked_whole():
    """`reachable_handlers` walks `supertypes` itself: a map of DIRECT supertypes reaches a
    case two levels up, through an interface (`Reserve implements Stocked extends Command`)."""
    rows = [_row("b", 0, "Command#")]
    direct = {"Reserve#": {"Stocked#"}, "Stocked#": {"Command#"}}
    assert [row["position"] for row in reachable_handlers(rows, "Reserve#", None, direct)] == [0]


def _statement_builder(prefix: str, caller: str, mutable: bool) -> list[CallSiteFact]:
    """`b = <root>; b.onMessage(Reserve, r); b.onMessage(Release, s); return b.build();` on
    the typed builder of the family under `prefix`: each registration called on the local
    and its result dropped. The mutable builder is `newReceiveBuilder()`, inherited and so
    called on the module's own class; the immutable one `Behaviors.receive(Command.class)`."""
    javadsl = f"{prefix}/actor/typed/javadsl"
    if mutable:
        owner, builder, built = (
            f"{javadsl}/ReceiveBuilder#",
            f"L{javadsl}/ReceiveBuilder;",
            f"L{javadsl}/Receive;",
        )
        root = _site(caller, 0, _SHOP, "newReceiveBuilder", f"(){builder}", result=1)
    else:
        owner, builder, built = (
            f"{javadsl}/BehaviorBuilder#",
            f"L{javadsl}/BehaviorBuilder;",
            f"L{prefix}/actor/typed/Behavior;",
        )
        root = _site(
            caller,
            0,
            f"{javadsl}/Behaviors#",
            "receive",
            f"(Ljava/lang/Class;){builder}",
            result=1,
            arguments=(_class("Command"),),
        )
    on_message = f"(Ljava/lang/Class;L{prefix}/japi/function/Function;){builder}"
    return [
        root,
        _site(
            caller,
            1,
            owner,
            "onMessage",
            on_message,
            receiver=1,
            result=2,
            arguments=(_class("Reserve"), _handler("onReserve")),
        ),
        _site(
            caller,
            2,
            owner,
            "onMessage",
            on_message,
            receiver=1,
            result=3,
            arguments=(_class("Release"), _handler("onRelease")),
        ),
        _site(caller, 3, owner, "build", f"(){built}", receiver=1, result=4),
    ]


def _behavior_heir(prefix: str) -> tuple[tuple[str, str], ...]:
    """`Shop extends AbstractBehavior`, the family's."""
    return ((_SHOP, f"{prefix}/actor/typed/javadsl/AbstractBehavior#"),)


@pytest.mark.parametrize("catalog_id, prefix", _FAMILIES)
@pytest.mark.pins("actor.a-builder-held-in-a-local-is-ONE-behavior-where-it-returns-this")
def test_a_mutable_builder_given_its_cases_as_statements_is_one_behavior(
    tmp_path: Path, catalog_id: str, prefix: str
):
    """`ReceiveBuilder.onMessage` returns `this` (CP-57 finding 1), so a builder held in a
    local and given its cases statement by statement holds both when `build()` reads it: one
    behavior, two cases, in statement order."""
    rows = _rows(
        tmp_path,
        _statement_builder(prefix, _caller("mutable"), mutable=True),
        hierarchy=_behavior_heir(prefix),
        catalog_id=catalog_id,
    )
    assert _cases(rows) == [
        ("mutable#0", 0, "Reserve#", None, False, "onReserve"),
        ("mutable#0", 1, "Release#", None, False, "onRelease"),
    ]


@pytest.mark.parametrize("catalog_id, prefix", _FAMILIES)
@pytest.mark.declines("pekko-actor-handlers")
@pytest.mark.declines("akka-actor-handlers")
@pytest.mark.pins("actor.a-DROPPED-immutable-builder-registers-nothing")
def test_an_immutable_builder_whose_results_are_dropped_registers_nothing(
    tmp_path: Path, catalog_id: str, prefix: str
):
    """The same statements on the immutable `BehaviorBuilder`: each `onMessage` returns a NEW
    builder (CP-57 finding 1) and the statement drops it, so the builder `build()` reads holds
    no case at all, and no row says it does. Every conjunct of a case holds but the one that
    the call's result is what the chain goes on with."""
    assert (
        _rows(
            tmp_path,
            _statement_builder(prefix, _caller("immutable"), mutable=False),
            catalog_id=catalog_id,
        )
        == []
    )


@pytest.mark.pins("dispatch.an-inherited-root-needs-the-ANCESTRY")
def test_an_inherited_builder_method_is_a_root_only_on_a_class_that_inherits_it(
    tmp_path: Path,
):
    """`newReceiveBuilder()` is called on `this`, so the site names the module's own class
    (javac writes the class the call is made through). It is the library's method only where
    that class's ancestry reaches the declared owner, through a base class of the module as
    well: the same call on a class extending something else builds nothing this catalog
    knows."""
    prefix = "org/apache/pekko"
    chain = _statement_builder(prefix, _caller("mutable"), mutable=True)
    assert _rows(tmp_path / "unrelated", chain, hierarchy=((_SHOP, "com/acme/shop/Other#"),)) == []
    through_a_base = _rows(
        tmp_path / "base",
        chain,
        hierarchy=(
            (_SHOP, "com/acme/shop/BaseBehavior#"),
            ("com/acme/shop/BaseBehavior#", f"{prefix}/actor/typed/javadsl/AbstractBehavior#"),
        ),
    )
    assert [row["position"] for row in through_a_base] == [0, 1]


@pytest.mark.pins("dispatch.an-heir-DECLARING-the-method-runs-its-own")
def test_a_class_declaring_the_builder_method_itself_runs_its_own(tmp_path: Path):
    """A subclass that declares its own `newReceiveBuilder()` answers the call with its own
    body (JVMS 5.4.3.3 stops at the first declaration), so the call is not the library's
    root, and its chain is no behavior this catalog knows."""
    prefix = "org/apache/pekko"
    chain = _statement_builder(prefix, _caller("mutable"), mutable=True)
    own = SymbolFact(
        document_id="doc_1",
        symbol=_MODULE
        + method_descriptor(
            _SHOP, "newReceiveBuilder", f"()L{prefix}/actor/typed/javadsl/ReceiveBuilder;"
        ),
        construct_kind="method",
        enclosing=_MODULE + _SHOP,
    )
    assert _rows(tmp_path, [*chain, own], hierarchy=_behavior_heir(prefix)) == []


def test_a_predicated_and_a_value_case_are_read_as_such(tmp_path: Path):
    """`onMessage(Release, pred, h)` is predicated, its handler argument 2; `onMessageEquals(
    Tick.INSTANCE, h)` is a value case whose identity is the constant's symbol, no class."""
    caller = _caller("behavior")
    tick = CallArgument(kind="enum", symbol="com/acme/shop/Shop$Tick#INSTANCE.")
    predicate = CallArgument(
        kind="lambda",
        symbol=method_descriptor(_SHOP, "lambda$0", "(Ljava/lang/Object;)Z"),
        captures=0,
    )
    facts = [
        _site(
            caller,
            0,
            _BEHAVIORS,
            "receive",
            f"(Ljava/lang/Class;){_IMMUTABLE}",
            result=1,
            arguments=(_class("Command"),),
        ),
        _site(
            caller,
            1,
            _BEHAVIOR_BUILDER,
            "onMessage",
            f"(Ljava/lang/Class;L{_P}/japi/function/Predicate;{_FUNCTION}){_IMMUTABLE}",
            receiver=1,
            result=2,
            arguments=(_class("Release"), predicate, _handler("onUrgentRelease")),
        ),
        _site(
            caller,
            2,
            _BEHAVIOR_BUILDER,
            "onMessageEquals",
            f"(Ljava/lang/Object;L{_P}/japi/function/Creator;){_IMMUTABLE}",
            receiver=2,
            result=3,
            arguments=(tick, _handler("onTick")),
        ),
        _site(
            caller,
            3,
            _BEHAVIOR_BUILDER,
            "build",
            f"()L{_P}/actor/typed/Behavior;",
            receiver=3,
            result=4,
        ),
    ]
    assert _cases(_rows(tmp_path, facts)) == [
        ("behavior#0", 0, "Release#", None, True, "onUrgentRelease"),
        ("behavior#0", 1, None, "com/acme/shop/Shop$Tick#INSTANCE.", False, "onTick"),
    ]


def test_a_builder_never_built_registers_nothing(tmp_path: Path):
    """`Behaviors.receive(C).onMessage(A, h)` whose builder never reaches `build()` is no
    behavior (D02 §4: a chain that never reaches a terminal derives nothing)."""
    caller = _caller("unbuilt")
    facts = [
        _site(
            caller,
            0,
            _BEHAVIORS,
            "receive",
            f"(Ljava/lang/Class;){_IMMUTABLE}",
            result=1,
            arguments=(_class("Command"),),
        ),
        _site(
            caller,
            1,
            _BEHAVIOR_BUILDER,
            "onMessage",
            f"{_ON_MESSAGE}{_IMMUTABLE}",
            receiver=1,
            result=2,
            arguments=(_class("Reserve"), _handler("onReserve")),
        ),
    ]
    assert _rows(tmp_path, facts) == []


@pytest.mark.parametrize(
    "entry, refused",
    [
        ({"class_arg": 0, "value_arg": 0, "handler_arg": 1}, "never both"),
        ({"class_arg": 0}, "no `handler_arg`"),
        ({"handler_arg": 1}, "no `class_arg`, `value_arg` or `predicate_arg`"),
        ({"class_arg": 0, "handler_arg": 2}, "not an argument"),
        ({"class_arg": 0, "handler_arg": 0}, "one argument for two meanings"),
        ({"class_arg": 0, "handler_arg": 1, "returns_message": "always"}, "not true or false"),
        ({"class_arg": 0, "handler_arg": 1, "message_arg": 0}, "unknown keys"),
    ],
)
def test_a_malformed_registration_is_refused_at_load(tmp_path: Path, entry: dict, refused: str):
    from sextant.application.ports.catalogs import CatalogError

    (tmp_path / "c.yml").write_text(
        "id: c\nstyle: message_handlers\nmatches:\n  message_handlers:\n"
        "    - { owner: a.B, method: handle, descriptor: '(Ljava/lang/Class;Ljava/lang/Object;)V', "
        + ", ".join(
            f"{key}: {value!r}" if not isinstance(value, str) else f"{key}: {value}"
            for key, value in entry.items()
        )
        + " }\n",
        encoding="utf-8",
    )
    with pytest.raises(CatalogError, match=refused):
        YamlCatalogSource(tmp_path).load()


def test_a_registration_is_loaded_with_its_positions(tmp_path: Path):
    (tmp_path / "c.yml").write_text(
        "id: c\nstyle: message_handlers\nmatches:\n  message_handlers:\n"
        "    - { owner: a.B, method: handle, descriptor: '(Ljava/lang/Class;Ljava/lang/Object;)V', "
        "class_arg: 0, handler_arg: 1, returns_message: true }\n",
        encoding="utf-8",
    )
    [catalog] = YamlCatalogSource(tmp_path).load()
    assert catalog.message_handlers == (
        {
            "owner": "a/B#",
            "method": "handle",
            "descriptor": "(Ljava/lang/Class;Ljava/lang/Object;)V",
            "class_arg": 0,
            "value_arg": None,
            "predicate_arg": None,
            "handler_arg": 1,
            "returns_message": True,
        },
    )
