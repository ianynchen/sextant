"""Tests for the `interface_implementation` engine (D02 §3b's
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
`RawPubSubSubscribers#lambda$withLambdaReceiver$0(...).`) for the lambda
receiver — confirming both real registrations named in the task brief.
CHECKPOINT FACT, also pinned by the probe: a class symbol fact's own
`interfaces` entries are module-prefixed exactly like the class's own
`symbol` (`ClassScanner`'s `interfaceSymbolsJson` runs every entry through
the same `symbolOf`), not the bare form a hand-built `SymbolFact` unit test
elsewhere in this repo happens to use — both the outer key and each interface
entry need the same module-prefix strip."""

from pathlib import Path

import pytest

from sextant.application.ports.catalogs import Catalog, CatalogError
from sextant.application.resolve.endpoints import derive_endpoints
from sextant.domain.closed_sets import ConstructKind, OriginTier
from sextant.domain.factfile import write_fact_file
from sextant.domain.facts import CallArgument, CallSiteFact, CallTarget, Document, SymbolFact
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


def _document(document_id: str = "doc_1") -> Document:
    return Document(
        document_id=document_id,
        relative_path="com/acme/messaging/raw/RawPubSubSubscribers.java",
        module_id="com.acme:orders-service",
        language="java",
        sextant_version="0.1.0",
        fact_schema_version="1.0.0",
        scanner_id="asm",
        scanner_version="9.7",
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


def _receiver_symbol_fact(interfaces: list[str] | None = None) -> SymbolFact:
    return SymbolFact(
        document_id="doc_1",
        symbol=_MODULE + RECEIVER_TYPE,
        construct_kind=ConstructKind.CLASS,
        interfaces=[] if interfaces is None else interfaces,
    )


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
    return Catalog(
        id="test-pubsub-subscriber",
        style="interface_implementation",
        protocol="pubsub",
        direction="inbound",
        requires=("call_site", "string_constants", "implemented_interfaces"),
        matches=matches,
        source=Path(source),
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


def _resolve(tmp_path: Path, facts: list, catalog: Catalog | None = None) -> DuckDbWorkspace:
    write_fact_file(tmp_path / "facts" / "Client.jsonl", _document(), facts)
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
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
        _receiver_symbol_fact([_MODULE + "com/google/cloud/pubsub/v1/MessageReceiver#"]),
    ]
    workspace = _resolve(tmp_path, facts)
    [endpoint] = workspace.query("endpoints")
    workspace.close()

    assert endpoint["protocol"] == "pubsub"
    assert endpoint["direction"] == "inbound"
    assert endpoint["method"] is None
    assert endpoint["path"] == "raw-notify"
    assert endpoint["handler"] == RECEIVER_TYPE + "receiveMessage"
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
    ]
    workspace = _resolve(tmp_path, facts)
    [endpoint] = workspace.query("endpoints")
    workspace.close()

    assert endpoint["path"] == "raw-notify-lambda"
    assert endpoint["handler"] == LAMBDA_SYMBOL
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
        _receiver_symbol_fact([_MODULE + "com/google/cloud/pubsub/v1/MessageReceiver#"]),
    ]
    workspace = _resolve(tmp_path, facts)
    [endpoint] = workspace.query("endpoints")
    workspace.close()

    assert endpoint["path"] is None
    assert endpoint["resolution"] == "unresolved"
    # The receiver was perfectly readable — only the channel failed — so the
    # handler still resolves (D02 §2's unresolved-is-an-answer, per capture).
    assert endpoint["handler"] == RECEIVER_TYPE + "receiveMessage"


# --- (e) an implementing class with NO registration derives nothing --------


def test_an_implementing_class_never_registered_derives_nothing(tmp_path: Path):
    facts = [
        # The class implements the interface, but no `newBuilder` call site
        # ever hands it to a registration — implementing an interface is not
        # an endpoint (D02 §3b).
        _receiver_symbol_fact([_MODULE + "com/google/cloud/pubsub/v1/MessageReceiver#"]),
    ]
    workspace = _resolve(tmp_path, facts)
    endpoints = workspace.query("endpoints")
    workspace.close()

    assert endpoints == []


# --- (f) a registered instance whose type does NOT implement the interface -


def test_a_registered_instance_whose_type_does_not_implement_the_interface_has_a_null_handler(
    tmp_path: Path,
):
    facts = [
        _linked_of_site(CALLER, "raw-notify"),
        _registration_site(
            CALLER,
            CallArgument(kind="unresolved", source=7),
            CallArgument(kind="instance", source=8, symbol=OTHER_TYPE),
        ),
        # `OTHER_TYPE` carries no symbol fact at all (never scanned as
        # implementing anything) — the same honest answer as a symbol fact
        # whose own `interfaces` names a different interface entirely.
    ]
    workspace = _resolve(tmp_path, facts)
    [endpoint] = workspace.query("endpoints")
    workspace.close()

    assert endpoint["path"] == "raw-notify"
    assert endpoint["resolution"] == "resolved"
    assert endpoint["handler"] is None


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
    the real `RawPubSubSubscribers#withNamedReceiver`/`withLambdaReceiver`
    registrations. Confirms both real receiver-argument shapes named in the
    task brief resolve exactly as the hand-built (a)/(b) cases above assert.
    """
    import subprocess

    from sextant.application.ports.scanner import ScanRequest
    from sextant.cli.resources import extractor_jar
    from sextant.ingress.extract.jvm.scanner import AsmScanner

    repo = Path(__file__).parents[2]
    fixture = repo / "fixtures" / "orders-service"
    subprocess.run(["mvn", "-q", "-o", "compile"], cwd=fixture, check=True)
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
                    # never `com.google.cloud.pubsub.v1` — the design doc's own
                    # §3b example names the wrong package for this one form.
                    {
                        "owner": "com.google.pubsub.v1.ProjectSubscriptionName",
                        "method": "of",
                        "arg": 1,
                    }
                ],
            },
        },
        source=Path("probe-pubsub-subscriber.yml"),
    )
    skipped = derive_endpoints(workspace, [real_catalog], capabilities=CAPABILITIES)
    assert skipped == []
    endpoints = {e["path"]: e for e in workspace.query("endpoints")}
    workspace.close()

    assert set(endpoints) == {"raw-notify", "raw-notify-lambda"}
    named = endpoints["raw-notify"]
    assert named["resolution"] == "resolved"
    assert named["handler"] is not None
    assert named["handler"].endswith("RawPubSubReceiver#receiveMessage")

    lambda_row = endpoints["raw-notify-lambda"]
    assert lambda_row["resolution"] == "resolved"
    assert lambda_row["handler"] is not None
    assert "lambda$withLambdaReceiver" in lambda_row["handler"]
