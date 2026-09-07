"""Tests for parse-call payload binding (2G design §6) and the
`payload_binding` half of the `open_questions` ledger.

Everything here is built by hand — invented parser classes, an invented
marker hierarchy, invented payload types — for the reason every other engine
test in this directory states: a behaviour per test, isolated and fast, with
the shipped catalogs' own live answers pinned once in `test_pipeline.py` and
`test_vertical_slice.py` against real bytecode. The invented vocabulary is
also the point: a test reaching for the real library's spellings would not
prove the pass reads catalog data rather than knowing them.

**What every test here depends on, and why it is written the way it is**
(Phase 2G checkpoint, Task 3): a call argument that is a BARE load of the
caller's parameter arrives as `{"kind": "parameter", "value": <declared
index>}`, and a value merged from a parameter and anything else arrives as
`{"kind": "unresolved"}`. So a handler that parses conditionally names no
parameter anywhere and binds nothing — which is why the ambiguous case below
is two sequential parses rather than a ternary, and why the last test pins
the merged form explicitly.
"""

import json
from pathlib import Path

import pytest

from sextant.application.ports.catalogs import Catalog, CatalogError
from sextant.application.resolve.open_questions import reset_open_questions
from sextant.application.resolve.shapes.parse_binding import bind_parse_calls
from sextant.domain.closed_sets import ConstructKind, OriginTier
from sextant.domain.factfile import write_fact_file
from sextant.domain.facts import (
    CallArgument,
    CallSiteFact,
    CallTarget,
    Document,
    Fact,
    Parameter,
    Signature,
    SymbolFact,
    TypeRef,
)
from sextant.domain.symbols import type_descriptor
from sextant.storage.duckdb.workspace import DuckDbWorkspace

_MODULE = "sextant-jvm maven com.acme/orders-service 1.0.0 "

# Invented vocabulary. None of it is a real library, class or marker — every
# one is a value the catalog below declares and the pass looks up.
READER = "com.acme.serde.ScrollReader"
MARKER = "com.acme.serde.Scroll"
BYTES_TYPE = "com.acme.wire.Envelope"

# The types a parse can name. `SCROLL` is reached by the hierarchy rule (its
# own declared interface IS the marker); `NOTE` is named by a class literal.
SCROLL = "com/acme/contracts/Scroll#"
NOTE = "com/acme/contracts/Note#"

# The methods the tests build bodies for.
LISTENER = "com/acme/Listener#"
INGEST = "com/acme/Ingest#"
RELAY = "com/acme/Relay#"


def _payload(shape_id: str) -> str:
    """The descriptor an object payload column holds (D01 §3) — written the
    way `_described` writes it, so an assertion compares the real bytes."""
    return json.dumps(
        {"nullable": True, "shape_id": shape_id, "wire_format": "", "wire_type": "object"},
        sort_keys=True,
        separators=(",", ":"),
    )


# What a bytes-shaped payload parameter looks like on the row before the pass
# runs: the envelope type the catalog names, described as the object it is.
BYTES_PAYLOAD = _payload(type_descriptor(BYTES_TYPE))


def _document() -> Document:
    return Document(
        document_id="doc_1",
        relative_path="com/acme/Listener.java",
        module_id="com.acme:orders-service",
        language="java",
        sextant_version="0.1.0",
        fact_schema_version=2,
        scanner_id="asm",
        scanner_version="9.12",
        content_hash="sha256:a",
        origin_entry="target/classes",
        origin_tier=OriginTier.MODULE_OUTPUT,
        redaction_set_hash="sha256:b",
    )


def _method(owner: str, name: str, parameters: int = 1) -> SymbolFact:
    """A declared method taking `parameters` bytes-shaped parameters — what
    `callee_of` resolves a call's target against, and what `_body_parameter`
    reads the payload position off."""
    return SymbolFact(
        document_id="doc_1",
        symbol=f"{_MODULE}{owner}{name}().",
        construct_kind=ConstructKind.METHOD,
        enclosing=_MODULE + owner,
        signature=Signature(
            parameters=[
                Parameter(name=f"a{index}", type=TypeRef(symbol=type_descriptor(BYTES_TYPE)))
                for index in range(parameters)
            ],
            returns=TypeRef(symbol="void#", wire_type=""),
        ),
    )


def _handler(name: str = "onEvent", parameters: int = 1) -> str:
    return f"{_MODULE}{LISTENER}{name}()."


def _call(
    caller: str, owner: str, name: str, *arguments: CallArgument, ordinal: int = 0
) -> CallSiteFact:
    return CallSiteFact(
        document_id="doc_1",
        caller=caller,
        target=CallTarget(owner=owner, name=name, descriptor="()V"),
        invoke_kind="virtual",
        ordinal=ordinal,
        arguments=list(arguments),
    )


def _parameter(index: int) -> CallArgument:
    return CallArgument(kind="parameter", value=index)


def _marked(symbol: str) -> SymbolFact:
    """A payload type whose own declared interface is the catalog's marker —
    one of the three edges the `owner_hierarchy` rule walks, and the one a
    real generated protobuf message offers.

    It is not the only one: capability 9.13 emits a `superclass` field for
    every non-`Object` superclass, which `_extends` below uses. This
    docstring used to say a plain `extends` was "not in the fact stream at
    all", which was `A-M12`'s stale premise."""
    return SymbolFact(
        document_id="doc_1",
        symbol=_MODULE + symbol,
        construct_kind=ConstructKind.CLASS,
        interfaces=[_MODULE + type_descriptor(MARKER)],
    )


def _catalog(bytes_payloads: list[str] | None = None, calls: list[dict] | None = None) -> Catalog:
    """A catalog carrying 2G design §7's `parse_calls` vocabulary, plus the
    `request_body` rule the pass reads the payload parameter's position off
    (the same rule `derive_endpoint_shapes` reads its type off)."""
    return Catalog(
        id="invented",
        style="annotation_driven",
        protocol="sqs",
        direction="inbound",
        requires=(),
        matches={
            "request_body": {"annotation": "com.acme.Payload", "fallback": "sole_unannotated"}
        },
        source=Path("invented.yml"),
        known_types=[{"type": BYTES_TYPE, "wire": "object"}],
        parse_calls={
            "bytes_payloads": [BYTES_TYPE] if bytes_payloads is None else bytes_payloads,
            "calls": _CALLS if calls is None else calls,
        },
    )


# The two shapes of entry the design names: a payload type that IS the
# receiver, matched by the owner's ancestry, and one named by a class
# literal, matched by the owner's identity.
_CALLS = [
    {
        "owner_hierarchy": [MARKER],
        "method": "decode",
        "bytes_arg": 0,
        "payload_from": "receiver_owner",
    },
    {
        "owner": READER,
        "method": "read",
        "bytes_arg": 0,
        "payload_from": "class_arg",
        "class_arg": 1,
    },
]


def _workspace(tmp_path: Path, *facts: Fact) -> DuckDbWorkspace:
    write_fact_file(tmp_path / "facts" / "Listener.jsonl", _document(), list(facts))
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    reset_open_questions(workspace)
    return workspace


def _seed(workspace: DuckDbWorkspace, *rows: dict) -> None:
    """Rows the endpoint engines already minted, written through the same
    `call_endpoints` derive every style uses so they are indistinguishable
    from real ones. Every seeded row already carries the bytes-shaped payload
    its own signature declares — which is exactly the value the binding has to
    replace.

    Called with no rows at all, it seeds the one default row every test but
    the multi-row ones wants — `derive_call_endpoints` inserts nothing for an
    empty batch, and a silently empty table would make every assertion below
    pass for the wrong reason."""
    workspace.derive(
        "call_endpoints",
        rows=[
            {
                "protocol": "sqs",
                "direction": "inbound",
                "method": None,
                "path": "queue",
                "handler": _handler(),
                "caller": None,
                "peer": None,
                "handler_signature": json.dumps(
                    {
                        "parameters": [
                            {"name": "body", "type": {"symbol": type_descriptor(BYTES_TYPE)}}
                        ]
                    }
                ),
                "resolution": "resolved",
                "evidence": "compiler",
                "catalog_id": "invented",
                "request_shape": BYTES_PAYLOAD,
                "response_shape": None,
                "consumes": None,
                "produces": None,
                **row,
            }
            for row in (rows or ({},))
        ],
    )


def _shapes(workspace: DuckDbWorkspace) -> dict[str, str | None]:
    return {
        str(row["path"]): (None if row["request_shape"] is None else str(row["request_shape"]))
        for row in workspace.query("endpoints")
    }


# --- the rungs ------------------------------------------------------------


def test_rung_a_handler_body(tmp_path: Path):
    """The parse is in the handler itself and its bytes argument NAMES the
    handler's payload parameter, so the flow is not inferred at all — it is
    read off one call site. That is the strongest evidence this pass can
    have, and the only one that needs no join between methods."""
    workspace = _workspace(
        tmp_path,
        _marked(SCROLL),
        _method(LISTENER, "onEvent"),
        _call(_handler(), SCROLL, "decode", _parameter(0)),
    )
    _seed(workspace)
    bind_parse_calls(workspace, [_catalog()])

    assert _shapes(workspace) == {"queue": _payload(SCROLL)}
    assert workspace.query("open_questions") == []


def test_rung_b_one_hop(tmp_path: Path):
    """The handler hands its payload parameter, bare, to a module-local
    method, and the callee parses the parameter that argument POSITION
    becomes. Two facts, joined by position — never by name, and never by
    proximity."""
    workspace = _workspace(
        tmp_path,
        _marked(SCROLL),
        _method(LISTENER, "onEvent"),
        _method(INGEST, "process"),
        _call(_handler(), INGEST, "process", _parameter(0)),
        _call(f"{_MODULE}{INGEST}process().", SCROLL, "decode", _parameter(0)),
    )
    _seed(workspace)
    bind_parse_calls(workspace, [_catalog()])

    assert _shapes(workspace) == {"queue": _payload(SCROLL)}


def test_the_hop_joins_the_argument_position_not_the_parameter_index(tmp_path: Path):
    """The join is `caller argument position -> callee parameter index`, and
    the two are only equal by accident when the payload is the first
    parameter. Here the handler's payload is parameter 1 and it is passed at
    position 0, so a rung that carried the caller's index through would look
    at the callee's parameter 1 and find nothing."""
    workspace = _workspace(
        tmp_path,
        _marked(SCROLL),
        _method(LISTENER, "onEvent", parameters=2),
        _method(INGEST, "process", parameters=2),
        _call(_handler(), INGEST, "process", _parameter(1), _parameter(0)),
        _call(f"{_MODULE}{INGEST}process().", SCROLL, "decode", _parameter(0)),
    )
    # The catalog's body marker sits on parameter 1, so the pass looks for
    # `{"kind": "parameter", "value": 1}` — which the handler passes at
    # argument position 0, and the callee therefore reads as ITS parameter 0.
    _seed(
        workspace,
        {
            "handler_signature": json.dumps(
                {
                    "parameters": [
                        {"name": "ack", "type": {"symbol": type_descriptor("com.acme.Ack")}},
                        {
                            "name": "body",
                            "type": {"symbol": type_descriptor(BYTES_TYPE)},
                            "annotations": [{"annotation": type_descriptor("com.acme.Payload")}],
                        },
                    ]
                }
            )
        },
    )
    bind_parse_calls(workspace, [_catalog()])

    assert _shapes(workspace) == {"queue": _payload(SCROLL)}


def test_beyond_horizon_gap(tmp_path: Path):
    """Two hops. The parse EXISTS and the pass can see it, which is exactly
    why refusing it has to be recorded rather than left as silence: an empty
    payload column would read the same as a channel nobody parses at all.
    The candidate rides the ledger row so 2K can answer what this pass
    would not."""
    workspace = _workspace(
        tmp_path,
        _marked(SCROLL),
        _method(LISTENER, "onEvent"),
        _method(RELAY, "forward"),
        _method(INGEST, "process"),
        _call(_handler(), RELAY, "forward", _parameter(0)),
        _call(f"{_MODULE}{RELAY}forward().", INGEST, "process", _parameter(0)),
        _call(f"{_MODULE}{INGEST}process().", SCROLL, "decode", _parameter(0)),
    )
    _seed(workspace)
    bind_parse_calls(workspace, [_catalog()])

    assert _shapes(workspace) == {"queue": BYTES_PAYLOAD}
    [question] = workspace.query("open_questions")
    assert question["question"] == "payload_binding"
    assert json.loads(str(question["candidates"])) == [
        {
            "hops": "2",
            "payload_type": SCROLL,
            "seen_in": f"{INGEST}process().",
            "why": f"{SCROLL}decode",
        }
    ]
    assert "beyond the one-hop horizon" in str(question["evidence"])


def test_a_callee_reached_by_two_paths_is_measured_by_the_shorter_one(tmp_path: Path):
    """The hop count decides whether a row binds or is refused, so a method
    reachable BOTH directly and through another callee must be measured at
    its shortest distance. The handler here calls the relay first (so a walk
    that went depth-first would meet the parse at two hops and refuse it) and
    calls the parsing callee itself second — one hop, and it binds.

    Without the breadth-first walk this is an ordering coin toss: the same
    two facts would bind or not depending on which call site was read first.
    """
    workspace = _workspace(
        tmp_path,
        _marked(SCROLL),
        _method(LISTENER, "onEvent"),
        _method(RELAY, "forward"),
        _method(INGEST, "process"),
        _call(_handler(), RELAY, "forward", _parameter(0)),
        _call(_handler(), INGEST, "process", _parameter(0), ordinal=1),
        _call(f"{_MODULE}{RELAY}forward().", INGEST, "process", _parameter(0)),
        _call(f"{_MODULE}{INGEST}process().", SCROLL, "decode", _parameter(0)),
    )
    _seed(workspace)
    bind_parse_calls(workspace, [_catalog()])

    assert _shapes(workspace) == {"queue": _payload(SCROLL)}
    assert workspace.query("open_questions") == []


def test_multi_caller_binds_both(tmp_path: Path):
    """Two listeners delegating to ONE callee is not ambiguity: both
    channels' bytes provably reach that parse, so both rows carry it. A rule
    that refused on "this parse has more than one caller" would lose the most
    ordinary shape real code takes."""
    workspace = _workspace(
        tmp_path,
        _marked(SCROLL),
        _method(LISTENER, "onEvent"),
        _method(LISTENER, "onOther"),
        _method(INGEST, "process"),
        _call(_handler(), INGEST, "process", _parameter(0)),
        _call(_handler("onOther"), INGEST, "process", _parameter(0)),
        _call(f"{_MODULE}{INGEST}process().", SCROLL, "decode", _parameter(0)),
    )
    _seed(workspace, {}, {"path": "other", "handler": _handler("onOther")})
    bind_parse_calls(workspace, [_catalog()])

    assert _shapes(workspace) == {"queue": _payload(SCROLL), "other": _payload(SCROLL)}
    assert workspace.query("open_questions") == []


def test_ambiguous_refuses(tmp_path: Path):
    """One payload parameter, two parses naming two different types. Both are
    real and this pass cannot say which describes the wire, so it binds
    neither and hands BOTH candidates on — picking the one that sorts first
    would publish a coin toss as a contract."""
    workspace = _workspace(
        tmp_path,
        _marked(SCROLL),
        _method(LISTENER, "onEvent"),
        _call(_handler(), SCROLL, "decode", _parameter(0)),
        _call(
            _handler(),
            type_descriptor(READER),
            "read",
            _parameter(0),
            CallArgument(kind="class", symbol=NOTE),
            ordinal=1,
        ),
    )
    _seed(workspace)
    bind_parse_calls(workspace, [_catalog()])

    assert _shapes(workspace) == {"queue": BYTES_PAYLOAD}
    [question] = workspace.query("open_questions")
    assert [c["payload_type"] for c in json.loads(str(question["candidates"]))] == [NOTE, SCROLL]
    assert "ambiguous" in str(question["evidence"])


def test_unrelated_parse_ignored(tmp_path: Path):
    """A parse of something else in the same handler binds nothing. The join
    is the payload PARAMETER, not the presence of a parse: a handler that
    decodes an unrelated field and a handler that decodes its own payload
    look identical to any rule that only counts calls."""
    workspace = _workspace(
        tmp_path,
        _marked(SCROLL),
        _method(LISTENER, "onEvent"),
        _call(_handler(), SCROLL, "decode", CallArgument(kind="field", symbol="com/acme/A#b.")),
    )
    _seed(workspace)
    bind_parse_calls(workspace, [_catalog()])

    assert _shapes(workspace) == {"queue": BYTES_PAYLOAD}
    assert workspace.query("open_questions") == []


def test_a_payload_merged_from_a_branch_binds_nothing(tmp_path: Path):
    """The checkpoint's own semantics, pinned where they cost recall: a value
    merged from a parameter and any other producer reads `unresolved`, so a
    handler that parses a conditionally chosen value names no parameter and
    binds nothing — not even the branch that IS the payload. That is the
    honest answer (the merge genuinely could have come from either side), and
    it is the reason the ambiguous fixture is written as two unconditional
    statements rather than a ternary."""
    workspace = _workspace(
        tmp_path,
        _marked(SCROLL),
        _method(LISTENER, "onEvent"),
        _call(_handler(), SCROLL, "decode", CallArgument(kind="unresolved")),
    )
    _seed(workspace)
    bind_parse_calls(workspace, [_catalog()])

    assert _shapes(workspace) == {"queue": BYTES_PAYLOAD}
    assert workspace.query("open_questions") == []


def test_a_declared_payload_type_is_never_rebound(tmp_path: Path):
    """A handler whose payload parameter names a real type is already
    described by its own signature. Binding it from a parse would replace a
    declaration with an inference, so the pass never looks at such a row —
    the bytes-shaped gate is a precondition, not a preference."""
    workspace = _workspace(
        tmp_path,
        _marked(SCROLL),
        _method(LISTENER, "onEvent"),
        _call(_handler(), SCROLL, "decode", _parameter(0)),
    )
    _seed(
        workspace,
        {
            "handler_signature": json.dumps(
                {"parameters": [{"name": "body", "type": {"symbol": NOTE}}]}
            ),
            "request_shape": _payload(NOTE),
        },
    )
    bind_parse_calls(workspace, [_catalog()])

    assert _shapes(workspace) == {"queue": _payload(NOTE)}


def test_a_binding_never_overwrites_an_answer_that_is_not_its_own(tmp_path: Path):
    """First-writer discipline, as the compare-and-set it is implemented as
    (`bind_request_shape.sql`): the update fires only where the column still
    holds the value the pass read. Here the row's payload column changes
    between the decision and the write, and the earlier answer survives."""
    workspace = _workspace(
        tmp_path,
        _marked(SCROLL),
        _method(LISTENER, "onEvent"),
        _call(_handler(), SCROLL, "decode", _parameter(0)),
    )
    _seed(workspace)
    workspace.derive(
        "bind_request_shape",
        rows=[
            {
                "protocol": "sqs",
                "direction": "inbound",
                "method": None,
                "path": "queue",
                "handler": _handler(),
                "caller": None,
                # Not what the row holds: a value written by someone else
                # after this decision was taken.
                "bytes_shape": _payload(NOTE),
                "request_shape": _payload(SCROLL),
            }
        ],
    )

    assert _shapes(workspace) == {"queue": BYTES_PAYLOAD}


def test_a_parse_reached_only_outside_the_module_binds_nothing(tmp_path: Path):
    """The hop is module-local by construction: a call whose target the
    module never declares leaves the horizon at the first step, and there is
    no body to read. Nothing is recorded either — the pass saw no parse at
    all, which is a different claim from having seen one and refused it."""
    workspace = _workspace(
        tmp_path,
        _marked(SCROLL),
        _method(LISTENER, "onEvent"),
        _call(_handler(), INGEST, "process", _parameter(0)),
    )
    _seed(workspace)
    bind_parse_calls(workspace, [_catalog()])

    assert _shapes(workspace) == {"queue": BYTES_PAYLOAD}
    assert workspace.query("open_questions") == []


def test_open_questions_deterministic(tmp_path: Path):
    """Two runs, the same bytes (NFR-1) — including where the ordering TIES.

    Wire identity plus `question` is not a total order: two listeners whose
    destination could not be read raise the same kind of question about the
    same `(protocol, method, path)` — all three NULL — and their order would
    otherwise be the insert order. The candidates are what differ, so the
    query orders on them too. Both halves are asserted here: the tie exists,
    and the answer is stable across a second, independently built workspace.

    A NULL path is also the only way to BUILD the tie through the shipped
    derivation: `derive_call_endpoints` dedups on wire identity, and two
    rows sharing a real path would collapse into one before this pass ever
    saw them. Two listeners on one destination reach the same tie through
    `derive_endpoints.sql` in the live fixture.

    **The seeded rows are `unresolved`, and that is what a listener whose
    destination could not be read actually is** — `single_call` and `fluent`
    both stamp `resolved` only where the address argument itself resolved. They
    were `resolved` here, which `derive_call_endpoints.sql`'s addresses-nothing
    gate now refuses: a row claiming its address was READ and that there is
    none names no endpoint. The tie this test is about is untouched, because
    the tie is in the path and the question kind.
    """
    facts: list[Fact] = [
        _marked(SCROLL),
        _marked(NOTE),
        _method(LISTENER, "onEvent"),
        _method(LISTENER, "onOther"),
        _method(RELAY, "forward"),
        _method(RELAY, "carry"),
        _method(INGEST, "process"),
        _method(INGEST, "handle"),
        # Two handlers on one unread destination, each two hops from a parse
        # of a DIFFERENT type: same protocol, method, path and question.
        _call(_handler(), RELAY, "forward", _parameter(0)),
        _call(f"{_MODULE}{RELAY}forward().", INGEST, "process", _parameter(0)),
        _call(f"{_MODULE}{INGEST}process().", SCROLL, "decode", _parameter(0)),
        _call(_handler("onOther"), RELAY, "carry", _parameter(0)),
        _call(f"{_MODULE}{RELAY}carry().", INGEST, "handle", _parameter(0)),
        _call(f"{_MODULE}{INGEST}handle().", NOTE, "decode", _parameter(0)),
    ]

    def _run(directory: Path) -> list[dict[str, object]]:
        workspace = _workspace(directory, *facts)
        _seed(
            workspace,
            {"path": None, "resolution": "unresolved"},
            {"path": None, "resolution": "unresolved", "handler": _handler("onOther")},
        )
        bind_parse_calls(workspace, [_catalog()])
        return workspace.query("open_questions")

    first = _run(tmp_path / "one")
    second = _run(tmp_path / "two")

    # The tie is real: two rows agreeing on every column the pre-2G ordering
    # used.
    assert [(q["protocol"], q["path"], q["question"]) for q in first] == [
        ("sqs", None, "payload_binding"),
        ("sqs", None, "payload_binding"),
    ]
    # And it is broken by the candidates, deterministically, in both runs.
    assert first == second
    assert [json.loads(str(q["candidates"]))[0]["payload_type"] for q in first] == [NOTE, SCROLL]


# --- catalog vocabulary ---------------------------------------------------


def test_an_entry_naming_no_bytes_argument_binds_nothing(tmp_path: Path):
    """An entry that names WHERE the payload type is but not where the bytes
    are describes a parse whose bytes arrive through something else entirely.
    No rung can prove the channel's bytes reach it, so it matches no call —
    and it stays in the catalog, because the type is what a later
    decoder-tracing rung would need."""
    workspace = _workspace(
        tmp_path,
        _method(LISTENER, "onEvent"),
        _call(
            _handler(),
            type_descriptor(READER),
            "read",
            CallArgument(kind="class", symbol=NOTE),
        ),
    )
    _seed(workspace)
    bind_parse_calls(
        workspace,
        [
            _catalog(
                calls=[
                    {"owner": READER, "method": "read", "payload_from": "class_arg", "class_arg": 0}
                ]
            )
        ],
    )

    assert _shapes(workspace) == {"queue": BYTES_PAYLOAD}


@pytest.mark.parametrize(
    "entry",
    [
        {"method": "read", "payload_from": "receiver_owner", "bytes_arg": 0},
        {
            "owner": READER,
            "owner_hierarchy": [MARKER],
            "method": "read",
            "payload_from": "class_arg",
            "class_arg": 1,
        },
        {"owner": READER, "payload_from": "receiver_owner", "bytes_arg": 0},
        {"owner": READER, "method": "read", "payload_from": "the_return_value"},
        {"owner": READER, "method": "read", "payload_from": "class_arg"},
    ],
    ids=["no-owner", "both-owners", "no-method", "unknown-source", "class-arg-without-position"],
)
def test_a_malformed_entry_is_refused_by_name(tmp_path: Path, entry: dict):
    """A broken catalog is a broken file, not a degraded run. Each of these
    would otherwise make the rungs a silent no-op — indistinguishable from a
    catalog that declares no parses at all, which is the one outcome the
    loader's own discipline exists to prevent."""
    workspace = _workspace(tmp_path, _method(LISTENER, "onEvent"))
    _seed(workspace)
    with pytest.raises(CatalogError, match="parse_calls"):
        bind_parse_calls(workspace, [_catalog(calls=[entry])])


def test_a_catalog_declaring_no_parse_calls_changes_nothing(tmp_path: Path):
    """The gate: a catalog that never names a parse never binds one, and its
    rows are exactly what they were before 2G."""
    workspace = _workspace(
        tmp_path,
        _marked(SCROLL),
        _method(LISTENER, "onEvent"),
        _call(_handler(), SCROLL, "decode", _parameter(0)),
    )
    _seed(workspace)
    silent = Catalog(
        id="invented",
        style="annotation_driven",
        protocol="sqs",
        direction="inbound",
        requires=(),
        matches={},
        source=Path("invented.yml"),
    )
    bind_parse_calls(workspace, [silent])

    assert _shapes(workspace) == {"queue": BYTES_PAYLOAD}


def test_an_array_type_name_reaches_the_symbol_the_facts_carry(tmp_path: Path):
    """A catalog writes `byte[]`; the facts spell that type `byte#[]`. The
    notation seam carries the suffix PAST the descriptor marker rather than
    into it, so an array payload parameter is recognised at all — without it
    the most ordinary bytes-shaped signature there is would never match."""
    workspace = _workspace(
        tmp_path,
        _marked(SCROLL),
        _method(LISTENER, "onEvent"),
        _call(_handler(), SCROLL, "decode", _parameter(0)),
    )
    _seed(
        workspace,
        {
            "handler_signature": json.dumps(
                {"parameters": [{"name": "body", "type": {"symbol": "byte#[]"}}]}
            ),
            "request_shape": None,
        },
    )
    bind_parse_calls(workspace, [_catalog(bytes_payloads=["byte[]"])])

    assert _shapes(workspace) == {"queue": _payload(SCROLL)}


# --- `A-M12` (principles sweep §3.3): the ancestry walk's own missing edge ---


def _extends(symbol: str, superclass: str) -> SymbolFact:
    """A payload type whose only route to the marker is a plain, NON-GENERIC
    `extends` — the edge capability 9.13 emits as `superclass` and which the
    `parse_calls` ancestry walk never read.

    `_marked` above reaches the marker through an INTERFACE, and its own
    docstring says why: "a plain `extends` is not in the fact stream at all".
    That sentence was true when it was written and capability 9.13 falsified
    it; this fact is the counterexample."""
    return SymbolFact(
        document_id="doc_1",
        symbol=_MODULE + symbol,
        construct_kind=ConstructKind.CLASS,
        superclass=_MODULE + type_descriptor(superclass),
    )


def test_a_payload_reaching_its_marker_by_a_plain_extends_binds(tmp_path: Path):
    """`A-M12`, the positive half, and `A-C4`'s rule in a second engine. The
    walk built its ancestry from `supertypes` + `implementations` and never
    from `superclasses`, so a type whose only route to a marker is a
    non-generic `extends` reached nothing and its parse bound nothing — the
    endpoint kept the bytes-shaped payload its signature declared, which is
    an under-report, not a wrong type.

    `supertype` is emitted only where the superclass carries type ARGUMENTS
    (D00 §5a's parameterised-type carrier), and `superclass` is emitted for
    every non-`Object` superclass (capability 9.13). Reading the first as the
    class-inheritance edge is the invented rule `A-C4` names, here in the
    payload-binding walk instead of the annotation one."""
    workspace = _workspace(
        tmp_path,
        _extends(SCROLL, MARKER),
        _method(LISTENER, "onEvent"),
        _call(_handler(), SCROLL, "decode", _parameter(0)),
    )
    _seed(workspace)
    bind_parse_calls(workspace, [_catalog()])

    assert _shapes(workspace) == {"queue": _payload(SCROLL)}


def test_a_payload_whose_extends_reaches_no_marker_binds_nothing(tmp_path: Path):
    """`A-M12`'s near-miss. The same shape, one cell different: the superclass
    is an ordinary type the catalog's `owner_hierarchy` does not name. The walk
    must reach it, find no marker, and bind NOTHING — the endpoint keeps the
    bytes payload its own signature declared.

    Without this the fix would read as "any `extends` binds", which is the
    fabrication direction: a parse call on an unrelated receiver would replace
    a real payload type with one no evidence names. It discriminates —
    comparing the walk's reached set against the marker LIST rather than
    against each target makes it fail."""
    workspace = _workspace(
        tmp_path,
        _extends(SCROLL, "com.acme.serde.NotTheMarker"),
        _method(LISTENER, "onEvent"),
        _call(_handler(), SCROLL, "decode", _parameter(0)),
    )
    _seed(workspace)
    bind_parse_calls(workspace, [_catalog()])

    assert _shapes(workspace) == {"queue": BYTES_PAYLOAD}
