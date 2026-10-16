"""Tests for the `interface_implementation` engine (D02 §2's
`interface_implementation` style) — the registration/receiver join over a
class's own declared `interfaces` (D00 §5a's `implemented_interfaces`
capability).

Facts (a)-(g) are hand-built to mirror the *real* emitted grammar exactly —
verified against a live scan of `fixtures/orders-service`'s
`RawPubSubSubscribers`/`RawPubSubReceiver` during this task's checkpoint,
below in `test_the_real_fixture_registrations_probe_both_receiver_shapes` —
rather than compiling and scanning real bytecode for every case, so each
behaviour is isolated and fast.

CHECKPOINT FACT, pinned by the probe: a `newBuilder(subscription, receiver)`
call's own channel argument (arg 0) arrives `unresolved` — never `instance`
— because `ProjectSubscriptionName.of` is a static factory, not a `NEW`
(D00 §5's "only a NEW names a concrete type"); its `source` is what
`channel_via` follows regardless. The receiver argument (arg 1) arrives
`instance` (symbol the bare `RawPubSubReceiver#` descriptor, `NEW`-produced)
for the named receiver, and `lambda` (symbol the synthetic body method,
`RawPubSubSubscribers#lambda$buildsAndDiscards$0(...).`) for the lambda
receiver — confirming both real registrations named in the task brief.
CHECKPOINT FACT, also pinned by the probe: a class symbol fact's own
`interfaces` entries are module-prefixed exactly like the class's own
`symbol` (`ClassScanner`'s `interfaceSymbolsJson` runs every entry through
the same `symbolOf`), not the bare form a hand-built `SymbolFact` unit test
elsewhere in this repo happens to use — both the outer key and each interface
entry need the same module-prefix strip."""

from pathlib import Path

import pytest

from fixture_build import compile_fixture
from sextant.application.ports.catalogs import Catalog, CatalogError
from sextant.application.resolve.call_edges import record_call_edges
from sextant.application.resolve.endpoints import derive_endpoints
from sextant.domain.closed_sets import ConstructKind, OriginTier
from sextant.domain.factfile import write_fact_file
from sextant.domain.facts import (
    CallArgument,
    CallSiteFact,
    CallTarget,
    Document,
    MethodReturnFact,
    Parameter,
    Signature,
    SymbolFact,
    TypeRef,
)
from sextant.domain.symbols import method_descriptor, type_descriptor
from sextant.storage.duckdb.workspace import DuckDbWorkspace

CAPABILITIES = {"call_site", "string_constants", "implemented_interfaces"}
# The module-coordinates prefix a real symbol fact's own `symbol` — and, per
# this task's checkpoint, each of its `interfaces` entries — carries (D00
# §5a); every call-argument symbol stays bare, exactly as the real fixture
# emits it (`test_call_engines.py`'s own `_MODULE` precedent).
_MODULE = "sextant-jvm maven com.acme/orders-service 1.0.0 "

SUBSCRIBER = "com/google/cloud/pubsub/v1/Subscriber#"
SUBSCRIPTION_NAME = "com/google/pubsub/v1/ProjectSubscriptionName#"
MESSAGE_RECEIVER = "com.google.cloud.pubsub.v1.MessageReceiver"
RECEIVER_TYPE = "com/acme/messaging/raw/RawPubSubReceiver#"
OTHER_TYPE = "com/acme/messaging/raw/SomeOtherType#"
CALLER = "com/acme/messaging/raw/RawPubSubSubscribers#withNamedReceiver()."
LAMBDA_SYMBOL = "com/acme/messaging/raw/RawPubSubSubscribers#lambda$withLambdaReceiver$0(sig_1)."
# The BARE descriptors of the two receivers' own handler methods. A real
# emitted method symbol always ends `(sig_…).` (D00 §5a) and always carries
# the module coordinates — which is exactly why a `handler` has to be JOINED
# to a symbol fact rather than concatenated from a type descriptor and the
# catalog's method name (final review, FIX 1): the concatenated form named no
# symbol any fact ever wrote, so it joined to nothing.
RECEIVER_HANDLER = RECEIVER_TYPE + "receiveMessage(sig_r1)."
OTHER_HANDLER = OTHER_TYPE + "receiveMessage(sig_r1)."


def _document(document_id: str = "doc_1") -> Document:
    return Document(
        document_id=document_id,
        relative_path="com/acme/messaging/raw/RawPubSubSubscribers.java",
        module_id="com.acme:orders-service",
        language="java",
        sextant_version="0.1.0",
        fact_schema_version=2,
        scanner_id="asm",
        content_hash="sha256:a",
        origin_entry="target/classes",
        origin_tier=OriginTier.MODULE_OUTPUT,
        redaction_set_hash="sha256:b",
    )


def _registration_site(
    caller: str, channel_argument: CallArgument, receiver_argument: CallArgument
) -> CallSiteFact:
    return CallSiteFact(
        document_id="doc_1",
        caller=caller,
        target=CallTarget(owner=SUBSCRIBER, name="newBuilder", descriptor="(...)V"),
        invoke_kind="static",
        ordinal=2,
        result=11,
        arguments=[channel_argument, receiver_argument],
    )


def _linked_of_site(caller: str, value: str | None, *, result: int = 7) -> CallSiteFact:
    """The linked `ProjectSubscriptionName.of(project, name)` call `channel_via`
    follows — arg 1 a string literal when `value` is given, `unresolved`
    (the real shape for a parameter-fed value) otherwise."""
    return CallSiteFact(
        document_id="doc_1",
        caller=caller,
        target=CallTarget(owner=SUBSCRIPTION_NAME, name="of", descriptor="(...)V"),
        invoke_kind="static",
        ordinal=0,
        result=result,
        arguments=[
            CallArgument(kind="unresolved"),
            CallArgument(kind="string", value=value)
            if value is not None
            else CallArgument(kind="unresolved"),
        ],
    )


def _symbol_fact(type_symbol: str, interfaces: list[str] | None = None) -> SymbolFact:
    return SymbolFact(
        document_id="doc_1",
        symbol=_MODULE + type_symbol,
        construct_kind=ConstructKind.CLASS,
        interfaces=[] if interfaces is None else interfaces,
    )


def _method_symbol_fact(bare_descriptor: str) -> SymbolFact:
    """The method symbol fact a `handler` joins back to — module-prefixed
    exactly as a real one is (D00 §5a). Without it in the workspace there is
    no such method in any scanned document, and the handler reads NULL."""
    return SymbolFact(
        document_id="doc_1",
        symbol=_MODULE + bare_descriptor,
        construct_kind=ConstructKind.METHOD,
    )


def _receiver_symbol_fact(interfaces: list[str] | None = None) -> list[SymbolFact]:
    """The named receiver's own class fact plus the method fact its handler
    resolves to — the two always travel together, since a class that
    implements the interface but declares no such method is case (h), not a
    handler."""
    return [_symbol_fact(RECEIVER_TYPE, interfaces), _method_symbol_fact(RECEIVER_HANDLER)]


def _hoisted(registration: dict[str, object]) -> list[dict[str, object]]:
    """A registration's `channel_via` entries as the identity table the loader hands every
    catalog (`Catalog.value_model`, spec 2026-09-22 §2a step 1) — the same three fields,
    with `owner` in the SCIP form the facts carry.

    Written out here rather than imported because the hoist is the loader's and a test of
    this engine must not depend on how it is spelled; that the SHIPPED catalog really
    hoists this entry is pinned where the loader is tested
    (`tests/ingress/test_yaml_source.py`). An entry missing one of the three fields is
    skipped rather than converted, which costs those cases nothing: they exist to watch
    `_validate_matches` refuse the FILE, and it refuses it before a single call site is
    matched — so no identity table of any shape is ever read on that path.
    """
    entries = registration.get("channel_via") or []
    return [
        {
            "owner": type_descriptor(str(entry["owner"])),
            "method": entry["method"],
            "arg": entry["arg"],
            **({"arity": entry["arity"]} if "arity" in entry else {}),
        }
        for entry in (entries if isinstance(entries, list) else [entries])
        if isinstance(entry, dict) and {"owner", "method", "arg"} <= set(entry)
    ]


def _catalog(
    *, matches: dict[str, object] | None = None, source: str = "test-pubsub-subscriber.yml"
) -> Catalog:
    if matches is None:
        registration = {
            "owner": "com.google.cloud.pubsub.v1.Subscriber",
            "method": "newBuilder",
            "channel_arg": 0,
            "receiver_arg": 1,
            "channel_via": [
                {"owner": "com.google.pubsub.v1.ProjectSubscriptionName", "method": "of", "arg": 1}
            ],
        }
        matches = {
            "interface": MESSAGE_RECEIVER,
            "handler_method": "receiveMessage",
            "registration": registration,
        }
    declared = matches.get("registration")
    return Catalog(
        id="test-pubsub-subscriber",
        style="interface_implementation",
        protocol="pubsub",
        direction="inbound",
        requires=("call_site", "string_constants", "implemented_interfaces"),
        matches=matches,
        source=Path(source),
        value_model=_hoisted(declared) if isinstance(declared, dict) else [],
    )


def _default_registration() -> dict[str, object]:
    return {
        "owner": "com.google.cloud.pubsub.v1.Subscriber",
        "method": "newBuilder",
        "channel_arg": 0,
        "receiver_arg": 1,
        "channel_via": [
            {"owner": "com.google.pubsub.v1.ProjectSubscriptionName", "method": "of", "arg": 1}
        ],
    }


def _catalog_with_channel_via(entry: object) -> Catalog:
    registration = _default_registration()
    registration["channel_via"] = [entry]
    return _catalog(
        matches={
            "interface": MESSAGE_RECEIVER,
            "handler_method": "receiveMessage",
            "registration": registration,
        }
    )


def _resolve(
    tmp_path: Path,
    facts: list,
    catalog: Catalog | None = None,
    *,
    edges: bool = False,
) -> DuckDbWorkspace:
    write_fact_file(tmp_path / "facts" / "Client.jsonl", _document(), facts)
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    # `edges` builds the one derived table the walk's CROSSING edge is read from
    # (`bound_to_parameter`, spec §1a) — the pipeline runs this pass above
    # `derive_endpoints` for its own reasons, and only the two cases below cross a method
    # boundary, so it stays off by default rather than slowing every case here.
    if edges:
        record_call_edges(workspace)
    skipped = derive_endpoints(workspace, [catalog or _catalog()], capabilities=CAPABILITIES)
    assert skipped == []
    return workspace


# --- (a) named-receiver registration: resolved channel + resolved handler --


def test_a_named_receiver_registration_derives_a_resolved_row_with_its_handler(
    tmp_path: Path,
):
    facts = [
        _linked_of_site(CALLER, "raw-notify"),
        _registration_site(
            CALLER,
            CallArgument(kind="unresolved", source=7),
            CallArgument(kind="instance", source=8, symbol=RECEIVER_TYPE),
        ),
        *_receiver_symbol_fact([_MODULE + "com/google/cloud/pubsub/v1/MessageReceiver#"]),
    ]
    workspace = _resolve(tmp_path, facts)
    [endpoint] = workspace.query("endpoints")
    workspace.close()

    assert endpoint["protocol"] == "pubsub"
    assert endpoint["direction"] == "inbound"
    assert endpoint["method"] is None
    assert endpoint["path"] == "raw-notify"
    # The FULL, module-prefixed method symbol the fact carries, verbatim
    # (final review, FIX 1) — never the type descriptor with the catalog's
    # method name glued on, which named no symbol at all. The live probe
    # below asserts the same handler joins the real `symbols` table.
    assert endpoint["handler"] == _MODULE + RECEIVER_HANDLER
    assert endpoint["resolution"] == "resolved"
    assert endpoint["caller"] is None
    assert endpoint["peer"] is None
    assert endpoint["request_shape"] is None
    assert endpoint["response_shape"] is None


# --- (b) lambda receiver: handler is the synthetic method symbol -----------


def test_a_lambda_receiver_registration_derives_the_synthetic_method_symbol(tmp_path: Path):
    facts = [
        _linked_of_site(CALLER, "raw-notify-lambda"),
        _registration_site(
            CALLER,
            CallArgument(kind="unresolved", source=7),
            CallArgument(kind="lambda", source=8, symbol=LAMBDA_SYMBOL),
        ),
        _method_symbol_fact(LAMBDA_SYMBOL),
    ]
    workspace = _resolve(tmp_path, facts)
    [endpoint] = workspace.query("endpoints")
    workspace.close()

    assert endpoint["path"] == "raw-notify-lambda"
    # The lambda argument's own `symbol` is the BARE synthetic body
    # descriptor; the row carries the module-prefixed symbol the fact wrote
    # (final review, FIX 1), which is what joins `symbols`.
    assert endpoint["handler"] == _MODULE + LAMBDA_SYMBOL
    assert endpoint["resolution"] == "resolved"


# --- (c) unresolvable receiver: handler NULL, row still derives ------------


def test_an_unresolvable_receiver_derives_the_row_with_a_null_handler(tmp_path: Path):
    facts = [
        _linked_of_site(CALLER, "raw-notify"),
        _registration_site(
            CALLER,
            CallArgument(kind="unresolved", source=7),
            CallArgument(kind="unresolved"),
        ),
    ]
    workspace = _resolve(tmp_path, facts)
    [endpoint] = workspace.query("endpoints")
    workspace.close()

    assert endpoint["path"] == "raw-notify"
    assert endpoint["resolution"] == "resolved"
    assert endpoint["handler"] is None


# --- (d) unresolvable channel: path NULL, unresolved ------------------------


def test_an_unresolvable_channel_derives_a_null_path_unresolved_row(tmp_path: Path):
    facts = [
        # No linked `of` call site at all — `source` names nothing this
        # caller's own call sites carry.
        _registration_site(
            CALLER,
            CallArgument(kind="unresolved", source=999),
            CallArgument(kind="instance", source=8, symbol=RECEIVER_TYPE),
        ),
        *_receiver_symbol_fact([_MODULE + "com/google/cloud/pubsub/v1/MessageReceiver#"]),
    ]
    workspace = _resolve(tmp_path, facts)
    [endpoint] = workspace.query("endpoints")
    workspace.close()

    assert endpoint["path"] is None
    assert endpoint["resolution"] == "unresolved"
    # The receiver was perfectly readable — only the channel failed — so the
    # handler still resolves (D02 §2's unresolved-is-an-answer, per capture).
    assert endpoint["handler"] == _MODULE + RECEIVER_HANDLER


# --- (e) an implementing class with NO registration derives nothing --------


def test_an_implementing_class_never_registered_derives_nothing(tmp_path: Path):
    facts = [
        # The class implements the interface, but no `newBuilder` call site
        # ever hands it to a registration — implementing an interface is not
        # an endpoint (D02 §2's `interface_implementation` style).
        *_receiver_symbol_fact([_MODULE + "com/google/cloud/pubsub/v1/MessageReceiver#"]),
    ]
    workspace = _resolve(tmp_path, facts)
    endpoints = workspace.query("endpoints")
    workspace.close()

    assert endpoints == []


# --- (f) a registered instance whose type does NOT implement the interface -
# Two ways a type fails to qualify: never scanned as implementing anything
# at all, or scanned and found to implement a DIFFERENT interface entirely
# — both are the same honest "not this one" answer, never a fabricated
# handler.


@pytest.mark.parametrize(
    "extra_facts",
    [
        pytest.param([], id="never-scanned-as-implementing-anything"),
        pytest.param(
            [
                _symbol_fact(
                    OTHER_TYPE, [_MODULE + "com/acme/messaging/raw/SomeUnrelatedInterface#"]
                )
            ],
            id="scanned-but-implements-a-different-interface",
        ),
    ],
)
def test_a_registered_instance_whose_type_does_not_implement_the_interface_has_a_null_handler(
    tmp_path: Path, extra_facts: list
):
    facts = [
        _linked_of_site(CALLER, "raw-notify"),
        _registration_site(
            CALLER,
            CallArgument(kind="unresolved", source=7),
            CallArgument(kind="instance", source=8, symbol=OTHER_TYPE),
        ),
        *extra_facts,
    ]
    workspace = _resolve(tmp_path, facts)
    [endpoint] = workspace.query("endpoints")
    workspace.close()

    assert endpoint["path"] == "raw-notify"
    assert endpoint["resolution"] == "resolved"
    assert endpoint["handler"] is None


# --- (h) the handler method itself is outside the scanned code -------------
# Final review, FIX 1: the handler is a JOIN against the method symbols the
# facts carry, so a receiver whose class implements the interface but whose
# own `receiveMessage` no scanned document declares (the implementer compiled
# into a dependency, not this module) resolves to NULL — the honest answer
# this style already gives every other unread capture, never a symbol built
# by string concatenation that joins to nothing.


@pytest.mark.parametrize(
    "handler_facts",
    [
        pytest.param([], id="no-method-symbol-at-all"),
        pytest.param(
            [_method_symbol_fact(RECEIVER_TYPE + "onMessage(sig_r1).")],
            id="the-class-declares-a-differently-named-method",
        ),
    ],
)
def test_a_receiver_whose_handler_method_no_document_declares_has_a_null_handler(
    tmp_path: Path, handler_facts: list
):
    facts = [
        _linked_of_site(CALLER, "raw-notify"),
        _registration_site(
            CALLER,
            CallArgument(kind="unresolved", source=7),
            CallArgument(kind="instance", source=8, symbol=RECEIVER_TYPE),
        ),
        _symbol_fact(RECEIVER_TYPE, [_MODULE + "com/google/cloud/pubsub/v1/MessageReceiver#"]),
        *handler_facts,
    ]
    workspace = _resolve(tmp_path, facts)
    [endpoint] = workspace.query("endpoints")
    workspace.close()

    assert endpoint["path"] == "raw-notify"
    assert endpoint["resolution"] == "resolved"
    assert endpoint["handler"] is None


# --- Fix round 1, item 1: `handler` is part of the dedup key ---------------
# Two DIFFERENT receivers registered on the SAME channel — the
# `@KafkaHandler`-shaped precedent of two consumer methods sharing one
# subscription (`test_pipeline.py`) — must both survive, each with its own
# `handler`. A key that dropped `handler` would silently discard the second
# registration's own row.


def test_two_receivers_registered_on_the_same_channel_both_derive_their_own_row(
    tmp_path: Path,
):
    other_caller = "com/acme/messaging/raw/RawPubSubSubscribers#withAnotherNamedReceiver()."
    interfaces = [_MODULE + "com/google/cloud/pubsub/v1/MessageReceiver#"]
    facts = [
        _linked_of_site(CALLER, "raw-notify"),
        _registration_site(
            CALLER,
            CallArgument(kind="unresolved", source=7),
            CallArgument(kind="instance", source=8, symbol=RECEIVER_TYPE),
        ),
        *_receiver_symbol_fact(interfaces),
        _linked_of_site(other_caller, "raw-notify"),
        _registration_site(
            other_caller,
            CallArgument(kind="unresolved", source=7),
            CallArgument(kind="instance", source=8, symbol=OTHER_TYPE),
        ),
        _symbol_fact(OTHER_TYPE, interfaces),
        _method_symbol_fact(OTHER_HANDLER),
    ]
    workspace = _resolve(tmp_path, facts)
    endpoints = {e["handler"]: e for e in workspace.query("endpoints")}
    workspace.close()

    assert set(endpoints) == {
        _MODULE + RECEIVER_HANDLER,
        _MODULE + OTHER_HANDLER,
    }
    for endpoint in endpoints.values():
        assert endpoint["path"] == "raw-notify"
        assert endpoint["resolution"] == "resolved"


# --- Fix round 1, item 2: the channel ladder tries the literal read first --
# `channel_via` is declared alongside a genuine literal overload
# (`Subscriber.newBuilder(String, MessageReceiver)`) — a catalog naming
# `channel_via` must still resolve a plain string argument directly, never
# fall through to (and fail) the linked-call follow.


def test_a_channel_via_registration_still_resolves_a_plain_string_literal(tmp_path: Path):
    facts = [
        # No linked `of` call site at all — the ladder must not need one.
        _registration_site(
            CALLER,
            CallArgument(kind="string", value="raw-notify-literal"),
            CallArgument(kind="instance", source=8, symbol=RECEIVER_TYPE),
        ),
        *_receiver_symbol_fact([_MODULE + "com/google/cloud/pubsub/v1/MessageReceiver#"]),
    ]
    # The default catalog (`_catalog()`) declares `channel_via`.
    workspace = _resolve(tmp_path, facts)
    [endpoint] = workspace.query("endpoints")
    workspace.close()

    assert endpoint["path"] == "raw-notify-literal"
    assert endpoint["resolution"] == "resolved"
    assert endpoint["handler"] == _MODULE + RECEIVER_HANDLER


# --- Task 7: what the walk answers that the one-hop ladder could not --------
# The ladder this engine used to carry read the literal at the declared position, then
# followed ONE `source` link. A registration inside a HELPER was invisible to both: the
# argument is the helper's parameter, and its value is one method away.

_STARTERS = "com/acme/messaging/raw/Starters#"
_HELPER = "com/acme/messaging/raw/Registrations#"
_TAKES_STRING = "(Ljava/lang/String;)V"
# Spelled through `method_descriptor` rather than written out: a method symbol's
# signature part is a hash of the JVM descriptor, and the call target the crossing edge
# joins back to carries that same descriptor (D00 §5a, OI-4's two-spellings rule).
_REGISTER = method_descriptor(_HELPER, "register", _TAKES_STRING)


def _helper_facts(first: CallArgument, second: CallArgument) -> list:
    """A `register(String subscription)` helper holding the registration, called twice —
    the M-1 shape (spec §0c) at this engine's own door."""
    return [
        _symbol_fact(_HELPER),
        # The `method_return` fact a void method still carries, one per return
        # instruction (D00 §5): `dispatch` reads this table to answer "did we read a
        # body", so a callee without one is indistinguishable from a third-party call
        # and binds no parameter at all (`test_values.py::_void` states the same).
        MethodReturnFact(document_id="doc_1", method=_MODULE + _REGISTER, ordinal=0, value=None),
        SymbolFact(
            document_id="doc_1",
            symbol=_MODULE + _REGISTER,
            construct_kind=ConstructKind.METHOD,
            enclosing=_MODULE + _HELPER,
            signature=Signature(
                parameters=[
                    Parameter(name="subscription", type=TypeRef(symbol="java/lang/String#"))
                ]
            ),
        ),
        _registration_site(
            _MODULE + _REGISTER,
            CallArgument(kind="parameter", value=0),
            CallArgument(kind="instance", source=8, symbol=RECEIVER_TYPE),
        ),
        *_receiver_symbol_fact([_MODULE + "com/google/cloud/pubsub/v1/MessageReceiver#"]),
        *[
            CallSiteFact(
                document_id="doc_1",
                caller=_MODULE + caller,
                target=CallTarget(owner=_HELPER, name="register", descriptor=_TAKES_STRING),
                invoke_kind="static",
                ordinal=0,
                arguments=[argument],
            )
            for caller, argument in (
                (method_descriptor(_STARTERS, "first", "()V"), first),
                (method_descriptor(_STARTERS, "second", "()V"), second),
            )
        ],
    ]


def test_two_callers_of_one_registering_helper_are_two_rows_and_not_four(tmp_path: Path):
    """**The conversion this migration exists for, and the M-1 rule holding at the same
    time.** The registration's own argument is a PARAMETER, which the one-hop ladder could
    only answer `unresolved` — one row, no address. The walk crosses to each caller, so
    the two subscriptions are two rows; and because the unit of resolution is the PATH,
    they are two and never the four a per-position reading would mint (there is one other
    slot on this call, and it is resolved out of the same binding)."""
    facts = _helper_facts(
        CallArgument(kind="string", value="first-sub"),
        CallArgument(kind="string", value="second-sub"),
    )
    workspace = _resolve(tmp_path, facts, edges=True)
    rows = {(row["path"], str(row["resolution"])) for row in workspace.query("endpoints")}
    workspace.close()

    assert rows == {("first-sub", "resolved"), ("second-sub", "resolved")}


def test_two_paths_that_both_read_nothing_are_one_unresolved_row(tmp_path: Path):
    """**A miss is one honest fact, however many ways the walk reached it.** Several paths
    are several bindings by design (§1c), and two of them agreeing that the subscription
    is unreadable is still ONE thing nobody could read — D02 §2's unresolved-is-an-answer.
    A row per path would multiply one registration into as many unresolved rows as it has
    callers, and an unresolved wire identity never dedups downstream, so nothing else in
    the pipeline would collapse them."""
    facts = _helper_facts(
        CallArgument(kind="unresolved"),
        CallArgument(kind="unresolved"),
    )
    workspace = _resolve(tmp_path, facts, edges=True)
    rows = [dict(row) for row in workspace.query("endpoints")]
    workspace.close()

    assert [(row["path"], str(row["resolution"])) for row in rows] == [(None, "unresolved")]


@pytest.mark.pins("arguments.only-a-string-literal-is-a-destination")
def test_a_declaration_reference_in_the_channel_slot_is_never_published_as_an_address(
    tmp_path: Path,
):
    """**Spec §7's one failure, guarded where it would happen.** The walk carries a
    declaration reference as a `symbol` literal (ruling T-3) precisely so a consumer can
    tell it from text; a channel reader that did not would write
    `com/acme/messaging/raw/RawPubSubReceiver#` into `path` — a wrong ADDRESS at
    `resolved`, which in a diff looks exactly like a right one. The row still derives,
    with no address, which is the answer this style has always given an unreadable one."""
    facts = [
        _registration_site(
            CALLER,
            CallArgument(kind="instance", source=8, symbol=RECEIVER_TYPE),
            CallArgument(kind="instance", source=8, symbol=RECEIVER_TYPE),
        ),
        *_receiver_symbol_fact([_MODULE + "com/google/cloud/pubsub/v1/MessageReceiver#"]),
    ]
    workspace = _resolve(tmp_path, facts)
    [endpoint] = workspace.query("endpoints")
    workspace.close()

    assert endpoint["path"] is None
    assert endpoint["resolution"] == "unresolved"


# --- (g) malformed matches: CatalogError, naming the file -------------------


def test_matches_missing_a_required_key_is_refused_at_run_start(tmp_path: Path):
    write_fact_file(tmp_path / "facts" / "Client.jsonl", _document(), [])
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    catalog = _catalog(
        matches={"handler_method": "receiveMessage", "registration": {}},
        source="broken.yml",
    )
    with pytest.raises(CatalogError, match="broken.yml"):
        derive_endpoints(workspace, [catalog], capabilities=CAPABILITIES)
    workspace.close()


@pytest.mark.parametrize(
    "missing_key",
    ["owner", "method", "channel_arg", "receiver_arg"],
)
def test_a_registration_missing_a_required_key_is_refused_at_run_start(
    tmp_path: Path, missing_key: str
):
    write_fact_file(tmp_path / "facts" / "Client.jsonl", _document(), [])
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    registration = _default_registration()
    del registration[missing_key]
    catalog = _catalog(
        matches={
            "interface": MESSAGE_RECEIVER,
            "handler_method": "receiveMessage",
            "registration": registration,
        },
        source="broken-registration.yml",
    )
    with pytest.raises(CatalogError, match="broken-registration.yml"):
        derive_endpoints(workspace, [catalog], capabilities=CAPABILITIES)
    workspace.close()


@pytest.mark.parametrize(
    "entry",
    [
        {"owner": "x.Y", "method": "of"},  # missing `arg`
        {"owner": "x.Y", "arg": 1},  # missing `method`
        {"method": "of", "arg": 1},  # missing `owner`
        {"owner": "x.Y", "method": "of", "arg": "not-an-int"},
        "just-a-string",
        # `arity`, when declared, is an int (A2 Task 8 fix round 2) — one helper,
        # `valid_via_arity`, for every engine that reads a via form.
        {"owner": "x.Y", "method": "of", "arg": 1, "arity": "one"},
    ],
)
def test_a_malformed_channel_via_entry_is_refused_at_run_start(tmp_path: Path, entry: object):
    write_fact_file(tmp_path / "facts" / "Client.jsonl", _document(), [])
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    catalog = _catalog_with_channel_via(entry)
    with pytest.raises(CatalogError, match=str(catalog.source)):
        derive_endpoints(workspace, [catalog], capabilities=CAPABILITIES)
    workspace.close()


# --- A live probe against the real fixture facts ----------------------------


def test_the_real_fixture_registrations_probe_both_receiver_shapes(tmp_path: Path):
    """Engine-level, against real compiled-and-scanned bytecode rather than
    hand-built facts — the checkpoint this task's brief requires: compiles
    and scans `fixtures/orders-service` once, then runs an invented catalog
    (this style ships no shipped catalog yet — that is a later task) against
    the real `RawPubSubSubscribers#startNamedReceiver`/`startLambdaReceiver`
    registrations. Confirms both real receiver-argument shapes named in the
    task brief resolve exactly as the hand-built (a)/(b) cases above assert.
    """

    from sextant.application.ports.scanner import ScanRequest
    from sextant.ingress.extract.jvm.scanner import AsmScanner
    from sextant.resources import extractor_jar

    repo = Path(__file__).parents[2]
    fixture = repo / "fixtures" / "orders-service"
    compile_fixture(fixture)
    facts = tmp_path / "facts"
    AsmScanner(extractor_jar()).scan(
        ScanRequest(
            module_id="com.acme:orders-service",
            coordinates="com.acme/orders-service",
            version="1.0.0",
            classes_dir=fixture / "target" / "classes",
            out_dir=facts,
        )
    )
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(facts)
    real_catalog = Catalog(
        id="probe-pubsub-subscriber",
        style="interface_implementation",
        protocol="pubsub",
        direction="inbound",
        requires=("call_site", "string_constants", "implemented_interfaces"),
        matches={
            "interface": MESSAGE_RECEIVER,
            "handler_method": "receiveMessage",
            "registration": {
                "owner": "com.google.cloud.pubsub.v1.Subscriber",
                "method": "newBuilder",
                "channel_arg": 0,
                "receiver_arg": 1,
                "channel_via": [
                    # CHECKPOINT FACT: the real package is `com.google.pubsub.v1`,
                    # never `com.google.cloud.pubsub.v1` — pinned against the real
                    # fixture, not assumed from the design doc's own example.
                    {
                        "owner": "com.google.pubsub.v1.ProjectSubscriptionName",
                        "method": "of",
                        "arg": 1,
                    }
                ],
            },
        },
        source=Path("probe-pubsub-subscriber.yml"),
        # What the loader hoists from the `channel_via` above (spec §2a step 1) — the
        # engine resolves the destination through it since Task 7.
        value_model=[
            {"owner": "com/google/pubsub/v1/ProjectSubscriptionName#", "method": "of", "arg": 1}
        ],
    )
    skipped = derive_endpoints(workspace, [real_catalog], capabilities=CAPABILITIES)
    assert skipped == []
    endpoints = {e["path"]: e for e in workspace.query("endpoints")}
    declared_symbols = {str(row["symbol"]) for row in workspace.query("method_symbols")}
    workspace.close()

    # THREE subscriptions in the fixture since `OI-64`, and all three derive here
    # because this catalog declares no `started_by`. That default is the assertion:
    # a framework whose registration call IS the subscription must keep deriving from
    # the registration alone, and adding the conjunct must not have changed it.
    assert set(endpoints) == {"raw-notify", "raw-notify-factory", "raw-notify-lambda"}
    named = endpoints["raw-notify"]
    assert named["resolution"] == "resolved"
    assert named["handler"] is not None
    assert named["handler"].endswith("RawPubSubReceiver#receiveMessage(sig_bb1c3cf6).")

    lambda_row = endpoints["raw-notify-lambda"]
    assert lambda_row["resolution"] == "resolved"
    assert lambda_row["handler"] is not None
    assert "lambda$startLambdaReceiver" in lambda_row["handler"]

    # The whole point of FIX 1 (final review): a `handler` names a method
    # symbol some scanned document actually declared. Before the fix BOTH of
    # these joined nothing — the instance branch glued a bare type descriptor
    # to a bare method name (no module coordinates, no `(sig_…)`), and the
    # lambda branch emitted the argument's own bare descriptor. This assertion
    # is what keeps either from silently regressing to a decorative string.
    assert {named["handler"], lambda_row["handler"]} <= declared_symbols


# --- `A-M1` (principles sweep §3.3): which overload IS the handler ----------
#
# The lookup used to take the first match in `method_symbols`' own symbol
# order — a SHA-256 prefix of the descriptor — and the comment defending it
# reasoned about the INTERFACE ("the interface declares exactly one, which
# makes that ordering a tiebreak rather than a choice") while the lookup ran
# against the implementing CLASS. Nothing stops a class declaring a private
# helper, a convenience form or a javac bridge beside its real override, and
# `ClassScanner.visitMethod` deliberately keeps all three.

_OVERLOAD_HANDLER = RECEIVER_TYPE + "receiveMessage(sig_0b978848)."


def _overloaded_receiver_facts(*, declare_the_interface: bool) -> list:
    """The registration, plus a receiver class declaring TWO
    `receiveMessage`s: the real arity-2 override and a private helper whose
    descriptor hash sorts FIRST.

    `sig_0b978848` sorts before `sig_r1`, which is the sweep's own reproduction
    — the wrong method is not merely reachable, it is the one the old
    first-match-wins rule picked."""
    facts: list = [
        _linked_of_site(CALLER, "raw-notify"),
        _registration_site(
            CALLER,
            CallArgument(kind="unresolved", source=7),
            CallArgument(kind="instance", source=8, symbol=RECEIVER_TYPE),
        ),
        _symbol_fact(RECEIVER_TYPE, [_MODULE + "com/google/cloud/pubsub/v1/MessageReceiver#"]),
        _signed_method(
            RECEIVER_HANDLER, ["com/google/pubsub/v1/PubsubMessage#", "java/lang/Object#"]
        ),
        _signed_method(_OVERLOAD_HANDLER, ["java/lang/String#", "java/lang/String#"]),
    ]
    if declare_the_interface:
        facts += [
            _symbol_fact_of_kind(
                "com/google/cloud/pubsub/v1/MessageReceiver#", ConstructKind.INTERFACE
            ),
            _signed_method(
                "com/google/cloud/pubsub/v1/MessageReceiver#receiveMessage(sig_if).",
                ["com/google/pubsub/v1/PubsubMessage#", "java/lang/Object#"],
                enclosing="com/google/cloud/pubsub/v1/MessageReceiver#",
            ),
        ]
    return facts


def _symbol_fact_of_kind(type_symbol: str, kind: ConstructKind) -> SymbolFact:
    return SymbolFact(document_id="doc_1", symbol=_MODULE + type_symbol, construct_kind=kind)


def _signed_method(
    bare: str,
    parameter_types: list[str],
    enclosing: str | None = None,
    erasures: list[str] = (),
) -> SymbolFact:
    """A method fact carrying its own parameter types — which is what makes a
    selector (JLS 8.4.2: name AND parameter types in order) readable at all.
    Every other method fact in this file omits the signature, and that is
    deliberate: the rule below must keep answering for those too.

    `erasures` is what the DESCRIPTOR says, which differs from `parameter_types`
    only where the declaration is generic (D00 §5a): an interface declaring
    `handle(E event)` reads `E` from its `Signature` attribute and its erasure
    from the descriptor. Defaults to `parameter_types`, the two being one string
    for every non-generic declaration."""
    return SymbolFact(
        document_id="doc_1",
        symbol=_MODULE + bare,
        construct_kind=ConstructKind.METHOD,
        enclosing=_MODULE + (enclosing or bare.partition("#")[0] + "#"),
        signature=Signature(
            parameters=[
                Parameter(
                    name=f"p{index}",
                    type=TypeRef(symbol=symbol, wire_type="object"),
                    erased_symbol=(erasures[index] if index < len(erasures) else symbol),
                )
                for index, symbol in enumerate(parameter_types)
            ],
            returns=TypeRef(symbol="void#", wire_type=""),
        ),
    )


def test_a_scanned_GENERIC_interface_still_names_which_overload_it_is(tmp_path: Path):
    """W5, and the regression it nearly shipped. Same two candidates, and the
    interface is scanned — but it declares `receiveMessage(E, Object)` on a type
    parameter of its own, so reading the `Signature` attribute makes its first
    parameter read `E`.

    A type variable's name is scoped to the declaration that introduced it, and
    this selector compares an INTERFACE's parameter tuple against an
    IMPLEMENTATION's. `E` matches neither candidate, `matched` is empty, and the
    handler goes back to NULL — the attribution lost silently, on evidence that is
    right there. The descriptor's own answer is the erasure, which is what both
    sides share and what this compared before W5.

    (Which candidate it names for a generic interface — the real override or
    javac's bridge — is the narrower, pre-existing question this engine's own
    docstring records. This asserts it still names ONE.)"""
    facts = [
        _linked_of_site(CALLER, "raw-notify"),
        _registration_site(
            CALLER,
            CallArgument(kind="unresolved", source=7),
            CallArgument(kind="instance", source=8, symbol=RECEIVER_TYPE),
        ),
        _symbol_fact(RECEIVER_TYPE, [_MODULE + "com/google/cloud/pubsub/v1/MessageReceiver#"]),
        _signed_method(
            RECEIVER_HANDLER, ["com/google/pubsub/v1/PubsubMessage#", "java/lang/Object#"]
        ),
        _signed_method(_OVERLOAD_HANDLER, ["java/lang/String#", "java/lang/String#"]),
        _symbol_fact_of_kind(
            "com/google/cloud/pubsub/v1/MessageReceiver#", ConstructKind.INTERFACE
        ),
        _signed_method(
            "com/google/cloud/pubsub/v1/MessageReceiver#receiveMessage(sig_if).",
            ["E", "java/lang/Object#"],
            enclosing="com/google/cloud/pubsub/v1/MessageReceiver#",
            erasures=["com/google/pubsub/v1/PubsubMessage#", "java/lang/Object#"],
        ),
    ]
    workspace = _resolve(tmp_path, facts)
    [endpoint] = workspace.query("endpoints")
    workspace.close()

    assert endpoint["handler"] == _MODULE + RECEIVER_HANDLER


def test_an_ambiguous_handler_is_unread_rather_than_guessed_by_hash_order(tmp_path: Path):
    """`A-M1`'s near-miss, and the shape the fix is FOR. Two `receiveMessage`
    methods on the implementing class, an interface this scan never opened
    (which is every shipped catalog's case — `MessageReceiver` lives in a jar),
    so nothing can say which one implements it.

    The required answer is a NULL handler, which is exactly what this engine's
    own docstring already promises: "the subscription still derives (the row
    above), only its handler is unread, never fabricated". What it did instead
    was publish the private helper — `sig_0b978848` sorts before `sig_r1` — at
    `resolved`/`compiler`, where nothing downstream can tell an invented
    attribution from an observed one.

    The row itself must still derive: the destination is a separate fact and
    withholding it would trade a fabrication for a silent drop."""
    workspace = _resolve(tmp_path, _overloaded_receiver_facts(declare_the_interface=False))
    [endpoint] = workspace.query("endpoints")
    workspace.close()

    assert (endpoint["path"], endpoint["handler"]) == ("raw-notify", None)


def test_a_scanned_interfaces_own_parameter_types_name_which_overload_it_is(tmp_path: Path):
    """`A-M1`'s paired positive. Same two candidates, one thing added: the
    interface is itself in the scan and declares its `receiveMessage`'s
    parameter types. That is the selector JLS 8.4.2 defines, and it names the
    real override rather than the helper that sorts first.

    Pairing this with the near-miss is what makes the near-miss an assertion
    rather than a rule that declines everything — a fix that simply returned
    None for every overloaded receiver would pass that test and lose a handler
    the evidence names."""
    workspace = _resolve(tmp_path, _overloaded_receiver_facts(declare_the_interface=True))
    [endpoint] = workspace.query("endpoints")
    workspace.close()

    assert endpoint["handler"] == _MODULE + RECEIVER_HANDLER


# --- `OI-64`: construction is not subscription -----------------------------
#
# `Subscriber.newBuilder(...).build()` delivers nothing until `startAsync()` runs, and
# `google-pubsub-subscriber.yml` used to derive a live inbound endpoint from the
# construction alone. Our own fixture built two subscribers, started NEITHER, and had
# both published as endpoints these tests asserted were correct — the suite protected
# the fabrication, which is why nothing noticed it for three phases.
#
# The fixture now models all three shapes and each gets a different answer. They are
# asserted together, from one resolve, because what matters is that the three are
# DISTINGUISHED: a rule that derived all three, or silenced all three, would satisfy
# any one of these assertions taken alone.


def _resolved_raw_pubsub(tmp_path: Path) -> tuple[DuckDbWorkspace, list]:
    """Compile and scan the real fixture, then resolve the SHIPPED catalog over it.

    The shipped catalog, not an invented one: `started_by` lives in that file, and a
    test that reproduced it here would pass while the shipped catalog said something
    else — which is how the fabrication survived. The workspace is handed back open."""

    from sextant.application.ports.scanner import ScanRequest
    from sextant.ingress.catalogs.yaml_source import YamlCatalogSource
    from sextant.ingress.extract.jvm.scanner import AsmScanner
    from sextant.resources import extractor_jar

    repo = Path(__file__).parents[2]
    fixture = repo / "fixtures" / "orders-service"
    compile_fixture(fixture)
    facts = tmp_path / "facts"
    AsmScanner(extractor_jar()).scan(
        ScanRequest(
            module_id="com.acme:orders-service",
            coordinates="com.acme/orders-service",
            version="1.0.0",
            classes_dir=fixture / "target" / "classes",
            out_dir=facts,
        )
    )
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(facts)
    catalog = next(
        c
        for c in YamlCatalogSource(repo / "src" / "sextant" / "catalogs").load()
        if c.id == "google-pubsub-subscriber"
    )
    skipped = derive_endpoints(workspace, [catalog], capabilities=CAPABILITIES)
    assert [s.catalog_id for s in skipped] == [], (
        "the shipped catalog must RUN here; a skip would make every assertion below "
        "pass for the wrong reason"
    )
    return workspace, skipped


def test_only_started_subscribers_derive_rows(tmp_path: Path):
    """The positive arm, and it covers BOTH receiver shapes.

    `startNamedReceiver` and `startLambdaReceiver` each build and start in one method,
    so the whole §8.6 chain is present. `withNamedReceiver` builds and hands back
    without starting, and derives nothing."""
    workspace, _ = _resolved_raw_pubsub(tmp_path)

    paths = {str(row["path"]) for row in workspace.query("endpoints")}
    workspace.close()

    assert paths == {"raw-notify", "raw-notify-lambda"}, (
        "only the started subscribers are boundaries; `raw-notify-factory` is returned "
        "without being started"
    )


def test_a_builder_setter_between_construction_and_build_still_derives(tmp_path: Path):
    """The regression this walk was rewritten for.

    `startLambdaReceiver` puts `setParallelPullCount(2)` between `newBuilder` and
    `build` — the spelling Google's own documentation uses. An earlier version required
    each declared step to be the IMMEDIATELY next call on the value, so this ordinary
    shape matched nothing and derived nothing: one over-report traded for a silent
    false negative on the commonest real spelling of the thing being modelled. The
    assertion is that an intervening call changes no answer."""
    workspace, _ = _resolved_raw_pubsub(tmp_path)

    paths = {str(row["path"]) for row in workspace.query("endpoints")}
    workspace.close()

    assert "raw-notify-lambda" in paths


def test_a_returned_subscriber_asks_rather_than_deriving_or_vanishing(tmp_path: Path):
    """The middle arm, and the reason an unstarted subscriber asks rather than vanishing.

    `withNamedReceiver` is an ordinary factory: it builds a subscriber and hands it
    back, and its caller may well start it. Chain reconstruction is within-method only
    (D00 §5), so we cannot join the two. Answering "no boundary" would trade the
    fabricated row for a silent false negative, which §8 forbids just as firmly.

    **There is no third, "provably dead" answer, and an earlier version claimed one.**
    It called a construction inert when no later CALL mentioned the value — but a
    subscriber assigned to a FIELD leaves the method through `putfield`, which is not a
    call site and so not a fact this walk can see. Measured: a `buildsIntoField` shape
    derived nothing and asked nothing while another method started it. "No call
    mentions this value" is inference, and §8 permits exclusion only on proof."""
    workspace, _ = _resolved_raw_pubsub(tmp_path)

    questions = [
        row
        for row in workspace.query("open_questions")
        if str(row["question"]) == "registration_activation"
    ]
    workspace.close()

    assert len(questions) == 1
    assert str(questions[0]["path"]) == "raw-notify-factory"
    assert "startAsync" in str(questions[0]["candidates"])
