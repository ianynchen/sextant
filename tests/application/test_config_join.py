"""Tests for the `config_join` engine (D02 §2's eighth style, reading §2d's
`address_from_config` and `media_from_config` vocabularies), plus the two
things that surround it: `merge_endpoints.sql`'s media carry and the
`resolved_peers` named query.

Everything here is built by hand — invented interfaces, invented
configuration keys, invented serializer class names — for the reason every
other engine test in this directory states: a behaviour per test, isolated
and fast, with the shipped catalogs' own live answers pinned once in
`test_pipeline.py` against real bytecode. The invented vocabulary is also
the point: a test that reached for the real framework's spellings would not
prove the engine reads catalog data rather than knowing them.

CHECKPOINT FACT (item (1), verified live): a functional bean's own
`signature.returns` carries the interface symbol with the payload type as
its type ARGUMENT — `{"symbol": "…/Sink#", "arguments": [{"symbol":
"…/Event#", …}]}` — which is what makes a binding row's `request_shape`
rootable at all. The facts below mirror that shape exactly.
"""

import json
from pathlib import Path

import pytest

from sextant.application.ports.catalogs import Catalog, CatalogError
from sextant.application.resolve.endpoints import derive_endpoints
from sextant.application.resolve.engines import config_join
from sextant.domain.closed_sets import ConstructKind, OriginTier
from sextant.domain.factfile import write_fact_file
from sextant.domain.facts import (
    CallArgument,
    CallSiteFact,
    CallTarget,
    Document,
    Signature,
    SymbolFact,
    TypeRef,
)
from sextant.domain.symbols import type_descriptor
from sextant.storage.duckdb.workspace import DuckDbWorkspace

CAPABILITIES = {"resolved_config", "typed_signatures", "implemented_interfaces"}
# The module-coordinates prefix every real symbol fact carries (D00 §5a);
# a signature's own type references stay bare, exactly as the extractor
# emits them (`test_interface_engine.py`'s `_MODULE` precedent).
_MODULE = "sextant-jvm maven com.acme/orders-service 1.0.0 "

BEANS = "com/acme/streams/Bindings#"
SINK = "com.acme.fn.Sink"
SOURCE = "com.acme.fn.Source"
PIPE = "com.acme.fn.Pipe"
EVENT = "com/acme/contracts/Event#"
RECEIPT = "com/acme/contracts/Receipt#"

DESTINATION_KEY = "acme.bindings.{binding}.destination"
SELECTION_KEY = "acme.function.definition"
BINDER_KEY = "acme.bindings.{binding}.binder"
DEFAULT_BINDER_KEY = "acme.default-binder"

EVENT_PAYLOAD = {
    "nullable": True,
    "shape_id": EVENT,
    "wire_format": "",
    "wire_type": "object",
}
RECEIPT_PAYLOAD = {**EVENT_PAYLOAD, "shape_id": RECEIPT}


def _document() -> Document:
    return Document(
        document_id="doc_1",
        relative_path="com/acme/streams/Bindings.java",
        module_id="com.acme:orders-service",
        language="java",
        sextant_version="0.1.0",
        fact_schema_version="1.0.0",
        scanner_id="asm",
        scanner_version="9.8",
        content_hash="sha256:a",
        origin_entry="target/classes",
        origin_tier=OriginTier.MODULE_OUTPUT,
        redaction_set_hash="sha256:b",
    )


def _payload(symbol: str) -> TypeRef:
    return TypeRef(symbol=symbol, arguments=[], wire_type="object", wire_format="", nullable=True)


def _bean(name: str, interface: str, *payloads: str) -> SymbolFact:
    """One `@Bean`-shaped factory method: a declared method whose RETURN type
    is a functional interface parameterized by the payloads it carries. The
    interface may be written in either notation — a catalog spells a type
    dotted, a fact spells it as a symbol (D02 §1), and the tests below read
    more clearly naming the type once."""
    return SymbolFact(
        document_id="doc_1",
        symbol=f"{_MODULE}{BEANS}{name}(sig_{name}).",
        construct_kind=ConstructKind.METHOD,
        enclosing=_MODULE + BEANS,
        signature=Signature(
            parameters=[],
            returns=TypeRef(
                symbol=interface if interface.endswith("#") else type_descriptor(interface),
                arguments=[_payload(payload) for payload in payloads],
                wire_type="object",
                wire_format="",
                nullable=True,
            ),
        ),
    )


def _type(symbol: str, interfaces: list[str] | None = None) -> SymbolFact:
    return SymbolFact(
        document_id="doc_1",
        symbol=_MODULE + symbol,
        construct_kind=ConstructKind.CLASS,
        interfaces=[_MODULE + entry for entry in (interfaces or [])],
    )


def _suffix_rules() -> list[dict]:
    """The three-shape suffix table D02 §2d sketches, in invented spellings:
    a one-way consumer, a one-way producer, and a both-halves-at-once type
    whose single entry derives TWO rows through parallel `direction` and
    `payload_arg` lists."""
    return [
        {"when": {"implements": SINK}, "then": "-in-0", "direction": "inbound", "payload_arg": 0},
        {
            "when": {"implements": SOURCE},
            "then": "-out-0",
            "direction": "outbound",
            "payload_arg": 0,
        },
        {
            "when": {"implements": PIPE},
            "then": ["-in-0", "-out-0"],
            "direction": ["inbound", "outbound"],
            "payload_arg": [0, 1],
        },
    ]


def _address(**overrides: object) -> dict:
    binding: dict = {
        "from": "bean_name",
        "selected_by": SELECTION_KEY,
        "selection_separator": ";",
        "composition_separator": "|",
        "suffix": _suffix_rules(),
    }
    binding.update(overrides.pop("binding", {}))  # type: ignore[arg-type]
    address: dict = {"key": DESTINATION_KEY, "binding": binding}
    address.update(overrides)
    return address


def _catalog(matches: dict | None = None, *, direction: str = "inbound") -> Catalog:
    return Catalog(
        id="invented-bindings",
        style="config_join",
        protocol="kafka",
        direction=direction,
        requires=("resolved_config",),
        matches=matches if matches is not None else {"address_from_config": _address()},
        source=Path("tests/invented-bindings.yml"),
    )


def _workspace(
    tmp_path: Path,
    facts: list[SymbolFact] | None = None,
    config: list[tuple[str, str, str | None]] | None = None,
) -> DuckDbWorkspace:
    """A workspace holding the given symbol facts and the given already
    resolved configuration — `(key, environment, value)`, a `None` value
    meaning the environment has the key but never resolved it (D01's
    unresolved-with-a-reason row, spelled `missing_key` here)."""
    write_fact_file(tmp_path / "facts" / "Bindings.jsonl", _document(), list(facts or []))
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    if config:
        workspace.derive(
            "resolved_config_insert",
            rows=[
                {
                    "key": key,
                    "value": value,
                    "source": "invented.yml" if value is not None else None,
                    "environment": environment,
                    "unresolved_reason": None if value is not None else "missing_key",
                }
                for key, environment, value in config
            ],
        )
    return workspace


def _rows(workspace: DuckDbWorkspace) -> list[dict]:
    return workspace.query("endpoints")


def _selection(value: str) -> list[tuple[str, str, str | None]]:
    return [(SELECTION_KEY, "default", value), (SELECTION_KEY, "prod", value)]


def _destination(binding: str, value: str | None) -> list[tuple[str, str, str | None]]:
    key = DESTINATION_KEY.replace("{binding}", binding)
    return [(key, "default", value), (key, "prod", value)]


# --- job 1: the three functional shapes ----------------------------------


def test_a_consumer_shaped_bean_derives_one_inbound_row_from_its_binding_key(
    tmp_path: Path,
):
    """The whole style in one row: nothing in the facts names a destination.
    The bean's own return type picks the suffix and the direction, its own
    method name is the binding name, and configuration supplies the address.
    The deriving method lands in `handler` (D01 §3's direction rule), and
    the payload roots from the interface's own type argument."""
    workspace = _workspace(
        tmp_path,
        [_bean("handle", SINK, EVENT)],
        _selection("handle") + _destination("handle-in-0", "events"),
    )
    config_join.run(workspace, _catalog())
    [row] = _rows(workspace)
    workspace.close()

    assert row["protocol"] == "kafka"
    assert row["direction"] == "inbound"
    assert row["method"] is None
    assert row["path"] == "events"
    assert row["handler"] == f"{_MODULE}{BEANS}handle(sig_handle)."
    assert row["caller"] is None
    assert row["peer"] is None
    assert row["resolution"] == "resolved"
    assert row["evidence"] == "compiler"
    assert row["catalog_id"] == "invented-bindings"
    assert json.loads(row["request_shape"]) == EVENT_PAYLOAD
    assert row["response_shape"] is None
    # Deliberately NULL: this row already answered its own payload, and
    # `derive_endpoint_contracts.sql`'s owner-keyed update is guarded on
    # exactly this column so it is not answered again — from a signature
    # whose return type is the functional interface itself.
    assert row["handler_signature"] is None


def test_a_supplier_shaped_bean_derives_an_outbound_row_naming_its_caller(
    tmp_path: Path,
):
    """The mirror image, through the second suffix rule: `-out-0`,
    `outbound`, and therefore `caller` set with `handler` NULL — the schema's
    own contract for an outbound row, which spec §3's blanket "handler is the
    bean's method symbol" predates."""
    workspace = _workspace(
        tmp_path,
        [_bean("emit", SOURCE, EVENT)],
        _selection("emit") + _destination("emit-out-0", "audit"),
    )
    config_join.run(workspace, _catalog())
    [row] = _rows(workspace)
    workspace.close()

    assert row["direction"] == "outbound"
    assert row["path"] == "audit"
    assert row["handler"] is None
    assert row["caller"] == f"{_MODULE}{BEANS}emit(sig_emit)."
    assert json.loads(row["request_shape"]) == EVENT_PAYLOAD


def test_a_both_halves_bean_derives_two_rows_from_one_definition_entry(
    tmp_path: Path,
):
    """D02 §2d: "a `Function` is both halves at once, and its one entry
    derives TWO rows" — rather than a single row whose direction cannot say
    which. Each half goes through the same key template with its own suffix,
    so the two halves can and do name different destinations; each carries
    its own direction and its own payload position, which is why those two
    are parallel lists in the catalog rather than something the engine
    derives from the suffix string."""
    workspace = _workspace(
        tmp_path,
        [_bean("relay", PIPE, EVENT, RECEIPT)],
        _selection("relay")
        + _destination("relay-in-0", "requests")
        + _destination("relay-out-0", "replies"),
    )
    config_join.run(workspace, _catalog())
    rows = {row["direction"]: row for row in _rows(workspace)}
    workspace.close()

    assert set(rows) == {"inbound", "outbound"}
    assert rows["inbound"]["path"] == "requests"
    assert rows["inbound"]["handler"].endswith("relay(sig_relay).")
    assert rows["inbound"]["caller"] is None
    # Type argument 0 is what it receives; argument 1 is what it sends.
    assert json.loads(rows["inbound"]["request_shape"]) == EVENT_PAYLOAD

    assert rows["outbound"]["path"] == "replies"
    assert rows["outbound"]["caller"].endswith("relay(sig_relay).")
    assert rows["outbound"]["handler"] is None
    assert json.loads(rows["outbound"]["request_shape"]) == RECEIPT_PAYLOAD


def test_a_bean_whose_declared_type_implements_the_interface_is_a_candidate_too(
    tmp_path: Path,
):
    """D02 §2d's second reading of "a method whose return type IS, or
    implements, one of the declared interfaces". Here the return type is a
    module-local class that DECLARES the interface, so the candidate test
    falls through equality to the `implemented_interfaces` join.

    CHECKPOINT FACT (item (1)): this half is unreachable for an interface
    the module does not compile — a library's functional interface has no
    symbol fact and can therefore never appear in any class's interface
    table — so the shipped catalog exercises the equality half only and
    this case is proved synthetically. Both entries in a class's own
    `interfaces` list and the class symbol itself are module-prefixed in the
    real emitted fact, so both need the same strip."""
    named = "com/acme/streams/NamedSink#"
    workspace = _workspace(
        tmp_path,
        [
            _bean("handle", named, EVENT),
            _type(named, [SINK.replace(".", "/") + "#"]),
        ],
        _selection("handle") + _destination("handle-in-0", "events"),
    )
    config_join.run(workspace, _catalog())
    [row] = _rows(workspace)
    workspace.close()

    assert row["direction"] == "inbound"
    assert row["path"] == "events"


def test_a_bean_matching_no_declared_interface_is_not_a_candidate(tmp_path: Path):
    """A declared method returning something the catalog says nothing about
    is not a candidate at all — the style needs a functional shape to read a
    suffix, a direction and a payload position from, and inventing one would
    mint an endpoint from a bean's name alone.

    No selection key here, so the candidate set IS the answer: the ordinary
    method beside the functional one contributes nothing, rather than
    contributing a degraded row. (A name the selection explicitly states but
    no candidate answers to is a different question, and a different row —
    the ghost case below.)"""
    workspace = _workspace(
        tmp_path,
        [_bean("handle", SINK, EVENT), _bean("helper", "com/acme/streams/Helper#", EVENT)],
        _destination("handle-in-0", "events") + _destination("helper-in-0", "other"),
    )
    config_join.run(workspace, _catalog())
    rows = _rows(workspace)
    workspace.close()

    assert [row["path"] for row in rows] == ["events"]


# --- job 1: selection ----------------------------------------------------


def test_only_the_beans_the_selection_key_names_derive_rows(tmp_path: Path):
    """The selection pin. Two beans with IDENTICAL facts — same interface,
    same payload, same enclosing type — and only one named by the selection
    key: nothing but selection can tell them apart, so a filter that quietly
    stopped filtering would show up here and nowhere else."""
    workspace = _workspace(
        tmp_path,
        [_bean("selected", SINK, EVENT), _bean("ignored", SINK, EVENT)],
        _selection("selected")
        + _destination("selected-in-0", "events")
        + _destination("ignored-in-0", "other-events"),
    )
    config_join.run(workspace, _catalog())
    rows = _rows(workspace)
    workspace.close()

    assert [row["path"] for row in rows] == ["events"]
    assert not [row for row in rows if row["handler"] and "ignored" in row["handler"]]


def test_every_candidate_binds_when_the_selection_key_is_absent(tmp_path: Path):
    """D02 §2d: "absent, every candidate binds" — the framework's own
    default. The candidates come out in a deterministic order (the symbol
    order `method_declarations` guarantees), so two runs read alike."""
    workspace = _workspace(
        tmp_path,
        [_bean("alpha", SINK, EVENT), _bean("beta", SINK, EVENT)],
        _destination("alpha-in-0", "a") + _destination("beta-in-0", "b"),
    )
    config_join.run(workspace, _catalog())
    rows = _rows(workspace)
    workspace.close()

    assert sorted(row["path"] for row in rows) == ["a", "b"]


def test_every_candidate_binds_when_the_key_exists_but_no_environment_resolved_it(
    tmp_path: Path,
):
    """Fix round 1, I-2, half one. A key declared somewhere but resolvable in
    no environment is still NOBODY having said anything: `resolved_config`
    carries the rows only so that "unresolved for prod" stays expressible, and
    an unreadable selection is not a selection. The framework default applies,
    exactly as it does when the key is absent altogether."""
    workspace = _workspace(
        tmp_path,
        [_bean("alpha", SINK, EVENT), _bean("beta", SINK, EVENT)],
        [(SELECTION_KEY, "default", None), (SELECTION_KEY, "prod", None)]
        + _destination("alpha-in-0", "a")
        + _destination("beta-in-0", "b"),
    )
    config_join.run(workspace, _catalog())
    rows = _rows(workspace)
    workspace.close()

    assert sorted(row["path"] for row in rows) == ["a", "b"]


@pytest.mark.parametrize("value", ["", "   ", ";", " ; ; "])
def test_an_explicitly_empty_selection_binds_nothing_at_all(tmp_path: Path, value: str):
    """Fix round 1, I-2, half two — the one path on which this engine could
    have FABRICATED boundaries rather than degraded.

    A selection that RESOLVED, to an empty value or to separators alone, is a
    statement: select nothing. Read as an absence it would fall through to the
    framework default and bind every candidate in the module — inventing a
    binding for each of them against a configuration that said the opposite,
    and inventing it silently, since each would look exactly like a
    default-selected bean.

    Both spellings are covered, and so is whitespace: a value is trimmed
    before it is judged empty, because a trailing separator or a stray space
    is not a different intent."""
    workspace = _workspace(
        tmp_path,
        [_bean("alpha", SINK, EVENT), _bean("beta", SINK, EVENT)],
        [(SELECTION_KEY, "default", value), (SELECTION_KEY, "prod", value)]
        + _destination("alpha-in-0", "a")
        + _destination("beta-in-0", "b"),
    )
    config_join.run(workspace, _catalog())
    rows = _rows(workspace)
    workspace.close()

    assert rows == []


def test_one_environment_selecting_nothing_does_not_erase_anothers_selection(
    tmp_path: Path,
):
    """The union rule and the empty-selection rule together: an environment
    that selects nothing removes nobody, because the SELECTION key is the one
    place environments are unioned rather than required to agree — it decides
    which rows EXIST rather than what a single-valued column holds, and a bean
    bound in one environment is a real boundary."""
    workspace = _workspace(
        tmp_path,
        [_bean("alpha", SINK, EVENT)],
        [(SELECTION_KEY, "default", ""), (SELECTION_KEY, "prod", "alpha")]
        + _destination("alpha-in-0", "a"),
    )
    config_join.run(workspace, _catalog())
    [row] = _rows(workspace)
    workspace.close()

    assert row["path"] == "a"


def test_a_selected_name_no_candidate_answers_to_derives_a_row_naming_nobody(
    tmp_path: Path,
):
    """Fix round 1, M-1: the ghost entry. The selection names `departed`, and
    no candidate answers to it — the realistic cause being a bean the code has
    since renamed or deleted while configuration kept selecting it.

    This used to derive NOTHING, which made a stale selection
    indistinguishable from a module that never selected anything: the
    configuration DID declare a binding, and that it names nobody is the
    finding. It lands on the same degraded row a composed entry does — `path`
    NULL, `handler` and `caller` NULL, the catalog's own direction, since no
    functional shape was read to say otherwise — and the surviving bean's own
    row is unaffected."""
    workspace = _workspace(
        tmp_path,
        [_bean("present", SINK, EVENT)],
        _selection("present;departed") + _destination("present-in-0", "events"),
    )
    config_join.run(workspace, _catalog())
    rows = {row["path"]: row for row in _rows(workspace)}
    workspace.close()

    assert set(rows) == {"events", None}
    assert rows["events"]["handler"].endswith("present(sig_present).")
    ghost = rows[None]
    assert ghost["protocol"] == "kafka"
    assert ghost["direction"] == "inbound"
    assert ghost["handler"] is None
    assert ghost["caller"] is None
    assert ghost["resolution"] == "unresolved"
    assert ghost["request_shape"] is None


def test_a_composed_selection_entry_derives_one_row_naming_nobody(tmp_path: Path):
    """D02 §2d's composition degrade: a composed entry "is not decomposed
    here — the vocabulary records the whole expression rather than guessing
    which function contributed which half". One row, `path` NULL,
    `unresolved`, and — uniquely in this table — neither `handler` nor
    `caller`, because there is no single bean to name."""
    workspace = _workspace(
        tmp_path,
        [_bean("first", SINK, EVENT), _bean("second", SINK, EVENT)],
        _selection("first|second"),
    )
    config_join.run(workspace, _catalog())
    [row] = _rows(workspace)
    workspace.close()

    assert row["protocol"] == "kafka"
    # The catalog's own declared direction: no bean was read, so no suffix
    # rule spoke for this row.
    assert row["direction"] == "inbound"
    assert row["path"] is None
    assert row["handler"] is None
    assert row["caller"] is None
    assert row["resolution"] == "unresolved"
    assert row["request_shape"] is None


def test_a_composed_entry_and_a_missing_key_row_stay_two_rows(tmp_path: Path):
    """Both carry `(protocol, direction, NULL, NULL)` and both survive: SQL's
    `NULL = NULL` is unknown, and this pass's own dedup follows the same rule
    (`single_call`'s precedent — only a row whose identity is KNOWN dedups).
    A naive dict keyed on the wire identity would collapse them and silently
    lose one of the two degrades."""
    workspace = _workspace(
        tmp_path,
        [_bean("orphan", SINK, EVENT)],
        _selection("orphan;left|right"),
    )
    config_join.run(workspace, _catalog())
    rows = _rows(workspace)
    workspace.close()

    assert len(rows) == 2
    assert {row["path"] for row in rows} == {None}
    assert {row["handler"] for row in rows} == {None, f"{_MODULE}{BEANS}orphan(sig_orphan)."}


# --- job 1: unresolved addresses -----------------------------------------


def test_a_selected_bean_with_no_binding_key_still_derives_an_unresolved_row(
    tmp_path: Path,
):
    """D02 §2d: "an unresolved address is not an absent endpoint... Dropping
    it would make a partially-configured module look like a module with
    fewer boundaries." The handler is still named — the bean method exists
    regardless of what configuration forgot — and so is the payload."""
    workspace = _workspace(tmp_path, [_bean("orphan", SINK, EVENT)], _selection("orphan"))
    config_join.run(workspace, _catalog())
    [row] = _rows(workspace)
    workspace.close()

    assert row["path"] is None
    assert row["resolution"] == "unresolved"
    assert row["handler"].endswith("orphan(sig_orphan).")
    assert json.loads(row["request_shape"]) == EVENT_PAYLOAD


def test_a_destination_resolved_in_only_one_environment_derives_an_unresolved_row(
    tmp_path: Path,
):
    """A single-valued column cannot hold two answers. Where the
    environments disagree — here one resolved the key and the other never
    did — the row records that the address is not one thing, rather than
    picking an environment. The per-environment answer lives in
    `resolved_config`, which still carries both."""
    workspace = _workspace(
        tmp_path,
        [_bean("handle", SINK, EVENT)],
        _selection("handle")
        + [
            (DESTINATION_KEY.replace("{binding}", "handle-in-0"), "default", "events"),
            (DESTINATION_KEY.replace("{binding}", "handle-in-0"), "prod", None),
        ],
    )
    config_join.run(workspace, _catalog())
    [row] = _rows(workspace)
    workspace.close()

    assert row["path"] is None
    assert row["resolution"] == "unresolved"


def test_a_destination_with_two_real_values_across_environments_resolves_neither(
    tmp_path: Path,
):
    """Fix round 1, M-2. The sibling of the test above, and the sharper case:
    here BOTH environments answered, and answered differently. Agreement is
    required for an ADDRESS exactly as it is for a media stamp — `path` is one
    column, an endpoint row is environment-neutral by design, and folding two
    real answers into one would invent a third that neither environment gave.
    Picking the alphabetically-first, or the `default` one, would be that
    invention wearing a rule.

    The row is still derived — the binding exists — and both values are still
    in `resolved_config`, which is where a per-environment question is
    answered."""
    key = DESTINATION_KEY.replace("{binding}", "handle-in-0")
    workspace = _workspace(
        tmp_path,
        [_bean("handle", SINK, EVENT)],
        _selection("handle") + [(key, "default", "events"), (key, "prod", "prod-events")],
    )
    config_join.run(workspace, _catalog())
    [row] = _rows(workspace)
    resolved = {
        r["environment"]: r["value"] for r in workspace.query("resolved_config") if r["key"] == key
    }
    workspace.close()

    assert row["path"] is None
    assert row["resolution"] == "unresolved"
    assert row["handler"].endswith("handle(sig_handle).")
    # Neither value was lost — only the single-valued column declined to
    # claim one of them.
    assert resolved == {"default": "events", "prod": "prod-events"}


def test_a_destination_that_is_still_an_expression_is_written_verbatim(
    tmp_path: Path,
):
    """The phase-wide rule: rows keep expressions, `resolved_config` carries
    values, and nothing here rewrites a row per environment. This engine
    never interprets a destination it reads — a value still carrying a
    placeholder becomes the `path` exactly as written, and the row still
    resolves, because the address WAS found. The per-environment answer is
    the `resolved_peers` join's, below."""
    workspace = _workspace(
        tmp_path,
        [_bean("handle", SINK, EVENT)],
        _selection("handle") + _destination("handle-in-0", "${acme.topic}"),
    )
    config_join.run(workspace, _catalog())
    [row] = _rows(workspace)
    workspace.close()

    assert row["path"] == "${acme.topic}"
    assert row["resolution"] == "resolved"


# --- job 1: protocol from the binder configuration -----------------------


def test_a_bindings_own_binder_resolves_the_protocol_it_speaks(tmp_path: Path):
    """D02 §2c: a match may resolve `protocol` differently from the catalog's
    own declared default. The binding's own binder key is the most specific
    source, and the catalog's map is what turns a configured name into a
    protocol — the engine never knows either."""
    workspace = _workspace(
        tmp_path,
        [_bean("handle", SINK, EVENT)],
        _selection("handle")
        + _destination("handle-in-0", "events")
        + [
            (BINDER_KEY.replace("{binding}", "handle-in-0"), "default", "queues"),
            (BINDER_KEY.replace("{binding}", "handle-in-0"), "prod", "queues"),
        ],
    )
    address = _address(binder_key=BINDER_KEY, binder_protocols={"queues": "jms"})
    config_join.run(workspace, _catalog({"address_from_config": address}))
    [row] = _rows(workspace)
    workspace.close()

    assert row["protocol"] == "jms"


def test_the_module_default_binder_answers_a_binding_that_declares_none(
    tmp_path: Path,
):
    workspace = _workspace(
        tmp_path,
        [_bean("handle", SINK, EVENT)],
        _selection("handle")
        + _destination("handle-in-0", "events")
        + [(DEFAULT_BINDER_KEY, "default", "queues"), (DEFAULT_BINDER_KEY, "prod", "queues")],
    )
    address = _address(
        binder_key=BINDER_KEY,
        default_binder_key=DEFAULT_BINDER_KEY,
        binder_protocols={"queues": "jms"},
    )
    config_join.run(workspace, _catalog({"address_from_config": address}))
    [row] = _rows(workspace)
    workspace.close()

    assert row["protocol"] == "jms"


def test_a_binder_name_the_catalog_does_not_map_falls_back_to_its_protocol(
    tmp_path: Path,
):
    """An unmapped name is a gap to grow the catalog from, not a guess: the
    row keeps the catalog's own declared protocol rather than inventing one
    or dropping to NULL — the same discipline the media half keeps for a
    serializer class absent from `values`."""
    workspace = _workspace(
        tmp_path,
        [_bean("handle", SINK, EVENT)],
        _selection("handle")
        + _destination("handle-in-0", "events")
        + [
            (BINDER_KEY.replace("{binding}", "handle-in-0"), "default", "unheard-of"),
            (BINDER_KEY.replace("{binding}", "handle-in-0"), "prod", "unheard-of"),
        ],
    )
    address = _address(binder_key=BINDER_KEY, binder_protocols={"queues": "jms"})
    config_join.run(workspace, _catalog({"address_from_config": address}))
    [row] = _rows(workspace)
    workspace.close()

    assert row["protocol"] == "kafka"


# --- job 2: serializer media stamping ------------------------------------

MEDIA_KEY = "acme.producer.value-writer"
WRITER = "com.acme.serde.JsonWriter"
JSON_MEDIA = '["application/json"]'


def _media_catalog(rules: list[dict] | None = None, values: dict | None = None) -> Catalog:
    return Catalog(
        id="invented-media",
        style="config_join",
        protocol="kafka",
        direction="inbound",
        requires=("resolved_config",),
        matches={
            "media_from_config": {
                "rules": rules
                if rules is not None
                else [
                    {
                        "key": MEDIA_KEY,
                        "fills": "produces",
                        "on": {"protocol": "kafka", "direction": "outbound"},
                    }
                ],
                "values": values if values is not None else {WRITER: "application/json"},
            }
        },
        source=Path("tests/invented-media.yml"),
    )


def _seed(workspace: DuckDbWorkspace, *rows: dict) -> None:
    """Rows another engine already minted — what a stamp enriches. Written
    through the same `call_endpoints` derive every style uses, so the rows
    are indistinguishable from real ones."""
    workspace.derive(
        "call_endpoints",
        rows=[
            {
                "protocol": "kafka",
                "direction": "outbound",
                "method": None,
                "path": None,
                "handler": None,
                "caller": None,
                "peer": None,
                "handler_signature": None,
                "resolution": "resolved",
                "evidence": "compiler",
                "catalog_id": "invented-other",
                "request_shape": None,
                "response_shape": None,
                "consumes": None,
                "produces": None,
                **row,
            }
            for row in rows
        ],
    )


def test_a_serializer_every_environment_agrees_on_stamps_its_media(tmp_path: Path):
    """The agreement precondition met: one class in every environment, and
    the class is in the catalog's `values` map, so one MIME string reaches
    every row the rule's `(protocol, direction)` pair names."""
    workspace = _workspace(
        tmp_path, config=[(MEDIA_KEY, "default", WRITER), (MEDIA_KEY, "prod", WRITER)]
    )
    _seed(workspace, {"path": "a"}, {"path": "b"}, {"direction": "inbound", "path": "c"})
    config_join.run(workspace, _media_catalog())
    rows = {row["path"]: row for row in _rows(workspace)}
    workspace.close()

    assert rows["a"]["produces"] == JSON_MEDIA
    assert rows["b"]["produces"] == JSON_MEDIA
    assert rows["a"]["consumes"] is None
    # A row the rule does not name is untouched in BOTH columns — the rule
    # fills one column, on one direction.
    assert rows["c"]["produces"] is None
    assert rows["c"]["consumes"] is None


def test_a_serializer_that_differs_per_environment_stamps_nothing(tmp_path: Path):
    """D02 §2d: "a stamp lands only where every resolved environment
    agrees... a per-environment split cannot be forced into one column
    without inventing an answer neither environment gave alone." The class
    names are still in `resolved_config`, which is what a later
    format-inference pass reads."""
    workspace = _workspace(
        tmp_path,
        config=[(MEDIA_KEY, "default", WRITER), (MEDIA_KEY, "prod", "com.acme.serde.XmlWriter")],
    )
    _seed(workspace, {"path": "a"})
    config_join.run(workspace, _media_catalog(values={WRITER: "application/json"}))
    [row] = _rows(workspace)
    workspace.close()

    assert row["produces"] is None


def test_a_stamp_never_overwrites_a_column_that_already_answered(tmp_path: Path):
    """First-writer discipline, D02 §2d: a declaration read off the code
    itself outranks a module-level default. The guard lives in the SQL's own
    WHERE clause, so no caller can bypass it."""
    workspace = _workspace(
        tmp_path, config=[(MEDIA_KEY, "default", WRITER), (MEDIA_KEY, "prod", WRITER)]
    )
    _seed(workspace, {"path": "a", "produces": '["text/csv"]'}, {"path": "b"})
    config_join.run(workspace, _media_catalog())
    rows = {row["path"]: row for row in _rows(workspace)}
    workspace.close()

    assert rows["a"]["produces"] == '["text/csv"]'
    assert rows["b"]["produces"] == JSON_MEDIA


def test_an_unknown_serializer_class_stamps_nothing(tmp_path: Path):
    """D02 §2d: "a class absent from `values` is a gap to grow the catalog
    from, not a guess"."""
    workspace = _workspace(
        tmp_path,
        config=[
            (MEDIA_KEY, "default", "com.acme.serde.Mystery"),
            (MEDIA_KEY, "prod", "com.acme.serde.Mystery"),
        ],
    )
    _seed(workspace, {"path": "a"})
    config_join.run(workspace, _media_catalog())
    [row] = _rows(workspace)
    workspace.close()

    assert row["produces"] is None


def test_an_unresolved_media_key_stamps_nothing(tmp_path: Path):
    """The key exists but no environment resolved it: nothing to look up,
    and nothing to write."""
    workspace = _workspace(
        tmp_path, config=[(MEDIA_KEY, "default", None), (MEDIA_KEY, "prod", None)]
    )
    _seed(workspace, {"path": "a"})
    config_join.run(workspace, _media_catalog())
    [row] = _rows(workspace)
    workspace.close()

    assert row["produces"] is None


def test_the_merge_carries_a_deleted_twins_media_onto_the_surviving_row(
    tmp_path: Path,
):
    """Checkpoint falsification F-4. `config_join` stamps BEFORE
    `merge_endpoints.sql` runs (the merge is once-per-resolve, after every
    engine), so a `produces` stamped on the outbound half of a path the
    module both exposes and calls used to be destroyed with the twin the
    merge deletes — leaving a `both` row that read as "no producer
    declared", indistinguishable from a module that declares none.

    The merge now coalesces both media columns off the twin, the same way it
    already coalesces `peer`. D02 §3 calls these columns "carried data,
    never identity — dedup and merge never *compare* these two columns";
    carrying is not comparing, and the surviving row's own answer still
    wins."""
    workspace = _workspace(tmp_path)
    _seed(
        workspace,
        {"direction": "inbound", "path": "shared", "consumes": JSON_MEDIA},
        {"direction": "outbound", "path": "shared", "produces": JSON_MEDIA, "caller": "c"},
    )
    workspace.derive("endpoints_merge")
    [row] = _rows(workspace)
    workspace.close()

    assert row["direction"] == "both"
    assert row["consumes"] == JSON_MEDIA
    assert row["produces"] == JSON_MEDIA


def test_the_merge_keeps_the_surviving_rows_own_media_over_the_twins(
    tmp_path: Path,
):
    """The coalesce is first-writer too: the twin only ever fills a column
    the surviving row left NULL."""
    workspace = _workspace(tmp_path)
    _seed(
        workspace,
        {"direction": "inbound", "path": "shared", "produces": '["text/csv"]'},
        {"direction": "outbound", "path": "shared", "produces": JSON_MEDIA, "caller": "c"},
    )
    workspace.derive("endpoints_merge")
    [row] = _rows(workspace)
    workspace.close()

    assert row["produces"] == '["text/csv"]'


# --- 2G Task 6: the merge's format carry ---------------------------------


def _stamp_format(
    workspace: DuckDbWorkspace, direction: str, caller: str | None, answer: tuple
) -> None:
    """One row's format pair, applied through the shipped `stamp_format`
    derive rather than a hand-written UPDATE — the columns the merge below
    carries have to arrive the way the format pass actually writes them."""
    workspace.derive(
        "stamp_format",
        rows=[
            {
                "protocol": "kafka",
                "direction": direction,
                "method": None,
                "path": "shared",
                "handler": None,
                "caller": caller,
                "request_shape": None,
                "response_shape": None,
                "format": answer[0],
                "format_resolution": answer[1],
            }
        ],
    )


def test_the_merge_carries_a_deleted_twins_format_onto_the_surviving_row(tmp_path: Path):
    """The two format columns (2G design §4) are carried for the same reason
    the media columns above are: the twin is about to be DELETED, so anything
    it alone answered goes with it unless the surviving row takes it.

    **Inert in the live pipeline today, deliberately tested anyway.**
    `resolve/format.py` is the LAST pass of a resolve and this merge is the
    last statement of `derive_endpoints`, so both columns are still NULL on
    every row when the merge runs live. The carry exists because the day
    anything stamps a format before the merge — a derivation reading one off
    a declaration, a reordered pipeline — a silently discarded half would
    look exactly like a module that declared no format. Stamping the rows
    here first is what makes the rule observable at all."""
    workspace = _workspace(tmp_path)
    _seed(
        workspace,
        {"direction": "inbound", "path": "shared"},
        {"direction": "outbound", "path": "shared", "caller": "c"},
    )
    _stamp_format(workspace, "inbound", None, (None, None))
    _stamp_format(workspace, "outbound", "c", ("json", "resolved"))
    workspace.derive("endpoints_merge")
    [row] = _rows(workspace)
    workspace.close()

    assert row["direction"] == "both"
    assert (row["format"], row["format_resolution"]) == ("json", "resolved")


def test_the_merge_takes_the_weaker_of_the_two_format_resolutions(tmp_path: Path):
    """`format` coalesces (the surviving row's own answer first, the media
    precedent); `format_resolution` does NOT — it takes the WEAKER of the two
    markers present, ordering `unresolved` < `narrowed` < `resolved`.

    The rule exists so a half that only GUESSED cannot launder into an
    observation by being merged with a half that knew. Here the inbound half
    says `json` at the observed tier and the outbound half says `json` at the
    assumed one: the surviving row keeps `json` — both halves agree on it —
    but must report it as assumed, because one of the two directions of this
    single wire identity was never actually observed."""
    workspace = _workspace(tmp_path)
    _seed(
        workspace,
        {"direction": "inbound", "path": "shared"},
        {"direction": "outbound", "path": "shared", "caller": "c"},
    )
    _stamp_format(workspace, "inbound", None, ("json", "resolved"))
    _stamp_format(workspace, "outbound", "c", ("json", "narrowed"))
    workspace.derive("endpoints_merge")
    [row] = _rows(workspace)
    workspace.close()

    assert (row["format"], row["format_resolution"]) == ("json", "narrowed")


def test_the_merge_lets_an_unresolved_half_weaken_the_whole_row(tmp_path: Path):
    """`unresolved` is the weakest of the three markers, so a half that could
    not be answered drags the merged row down to it — even though `format`
    itself still coalesces to the answer the other half had.

    That pair reads oddly on purpose: "this is the format one direction
    declared, and this row as a whole is not settled" is exactly the honest
    reading of one wire identity whose two halves were not equally
    observable."""
    workspace = _workspace(tmp_path)
    _seed(
        workspace,
        {"direction": "inbound", "path": "shared"},
        {"direction": "outbound", "path": "shared", "caller": "c"},
    )
    _stamp_format(workspace, "inbound", None, (None, "unresolved"))
    _stamp_format(workspace, "outbound", "c", ("protobuf", "resolved"))
    workspace.derive("endpoints_merge")
    [row] = _rows(workspace)
    workspace.close()

    assert (row["format"], row["format_resolution"]) == ("protobuf", "unresolved")


# --- job 3: the peer join ------------------------------------------------


def test_a_single_placeholder_address_resolves_once_per_environment(tmp_path: Path):
    """`resolved_peers` is a JOIN, never a write: the endpoint row keeps its
    expression and the query answers it per environment. One row in, one row
    per environment out."""
    workspace = _workspace(
        tmp_path,
        config=[
            ("acme.base", "default", "http://acme.internal"),
            ("acme.base", "prod", "http://acme.prod.internal"),
        ],
    )
    _seed(workspace, {"protocol": "http", "path": "${acme.base}/invoices", "caller": "c"})
    rows = {row["environment"]: row for row in workspace.query("resolved_peers")}
    workspace.close()

    assert rows["default"]["resolved_path"] == "http://acme.internal/invoices"
    assert rows["prod"]["resolved_path"] == "http://acme.prod.internal/invoices"
    assert {row["unresolved_reason"] for row in rows.values()} == {None}
    # The row itself is untouched — the expression is still what the graph
    # carries.
    assert {row["path"] for row in rows.values()} == {"${acme.base}/invoices"}


def test_an_address_whose_key_is_missing_for_one_environment_only_says_so(
    tmp_path: Path,
):
    """D01's "unresolved for prod, resolved for dev" is expressible here
    exactly as it is in `resolved_config`: the two environments are two rows,
    and only one of them carries a reason."""
    workspace = _workspace(
        tmp_path,
        config=[("acme.base", "default", "http://acme.internal"), ("acme.base", "prod", None)],
    )
    _seed(workspace, {"protocol": "http", "path": "${acme.base}/invoices", "caller": "c"})
    rows = {row["environment"]: row for row in workspace.query("resolved_peers")}
    workspace.close()

    assert rows["default"]["resolved_path"] == "http://acme.internal/invoices"
    assert rows["default"]["unresolved_reason"] is None
    assert rows["prod"]["resolved_path"] is None
    assert rows["prod"]["unresolved_reason"] == "missing_key"


def test_an_address_carrying_two_placeholders_is_substitutable_only_piecewise(
    tmp_path: Path,
):
    """D01's fifth unresolved reason, and the only one M04's pass 2 never
    emits: `multi_placeholder` belongs to this join alone, because it is a
    property of an ENDPOINT expression rather than of a configuration
    value."""
    workspace = _workspace(
        tmp_path,
        config=[("acme.base", "default", "http://acme.internal"), ("acme.leaf", "default", "x")],
    )
    _seed(workspace, {"protocol": "http", "path": "${acme.base}/${acme.leaf}", "caller": "c"})
    [row] = workspace.query("resolved_peers")
    workspace.close()

    assert row["resolved_path"] is None
    assert row["unresolved_reason"] == "multi_placeholder"


def test_an_address_with_no_placeholder_passes_through_with_its_literal(
    tmp_path: Path,
):
    """A literal is already the answer, in every environment — and `peer` is
    resolved independently of `path`, so a row carrying an authority and a
    path answers for both halves."""
    workspace = _workspace(tmp_path, config=[("acme.base", "default", "http://acme.internal")])
    _seed(
        workspace,
        {"protocol": "http", "path": "/exports", "peer": "acme.internal", "caller": "c"},
    )
    [row] = workspace.query("resolved_peers")
    workspace.close()

    assert row["resolved_path"] == "/exports"
    assert row["resolved_peer"] == "acme.internal"
    assert row["unresolved_reason"] is None


def test_a_merged_both_row_is_answered_like_the_outbound_row_it_absorbed(
    tmp_path: Path,
):
    """`direction <> 'inbound'`, not `= 'outbound'`: a `both` row is a path
    the module both exposes and CALLS, so it carries a caller's address
    expression exactly as an outbound row does. An equality test would
    silently drop every merged one."""
    workspace = _workspace(tmp_path, config=[("acme.base", "default", "http://acme.internal")])
    _seed(
        workspace,
        {"protocol": "http", "direction": "both", "path": "${acme.base}/orders", "caller": "c"},
        {"protocol": "http", "direction": "inbound", "path": "/exposed"},
    )
    rows = workspace.query("resolved_peers")
    workspace.close()

    assert [row["resolved_path"] for row in rows] == ["http://acme.internal/orders"]


# --- catalog validation ---------------------------------------------------


def test_the_engine_is_registered_for_the_style_and_runs_after_every_other(
    tmp_path: Path,
):
    """The registry entry and the ordering, together: a `config_join`
    catalog's rows are the LAST inserted, so a wire identity another catalog
    already recorded stays that catalog's row (D02 §3's `protocol_hint`
    ordering precedent — a style that ENRICHES rows other engines minted
    cannot run before them, and a stamp cannot reach a row that does not
    exist yet).

    The two catalogs here are deliberately arranged so that the ordinary
    rule would give the opposite answer: both declare `direction: inbound`,
    and `invented-bindings.yml` sorts BEFORE `invented-caller.yml` by
    filename, so without the runs-last rule the binding would be inserted
    first and the call-site row would be the one dropped by
    `derive_call_endpoints.sql`'s insert-if-absent guard. It is the other
    way round, and the surviving row's own `handler` says which engine
    wrote it."""
    caller = "com/acme/streams/Feeder#feed()."
    facts = [
        CallSiteFact(
            document_id="doc_1",
            caller=caller,
            target=CallTarget(owner="com/acme/streams/Feeder#", name="listen", descriptor="()V"),
            invoke_kind="virtual",
            ordinal=0,
            receiver=1,
            result=None,
            arguments=[CallArgument(kind="string", value="events")],
        ),
        _bean("handle", SINK, EVENT),
    ]
    workspace = _workspace(
        tmp_path,
        facts,
        _selection("handle") + _destination("handle-in-0", "events"),
    )
    call_site_catalog = Catalog(
        id="invented-caller",
        style="single_call",
        protocol="kafka",
        direction="inbound",
        requires=("call_site", "string_constants"),
        matches={
            "owner": "com.acme.streams.Feeder",
            "methods": [{"name": "listen", "channel_arg": 0}],
        },
        source=Path("tests/invented-caller.yml"),
    )
    skipped = derive_endpoints(
        workspace,
        [_catalog(), call_site_catalog],
        capabilities=CAPABILITIES | {"call_site", "string_constants"},
    )
    rows = _rows(workspace)
    workspace.close()

    assert skipped == []
    # One row for the identity, and the call-site engine wrote it: the
    # binding for the same identity arrived afterwards and lost.
    assert [(row["path"], row["catalog_id"]) for row in rows] == [("events", "invented-caller")]


def test_a_stamping_catalog_runs_after_every_deriving_one_whatever_its_filename(
    tmp_path: Path,
):
    """Fix round 1, M-3: the runs-last rule again, one level down. A
    `config_join` catalog that only STAMPS must not run before one that still
    has rows to write, or the stamp reaches none of them — silently, since a
    column that was never offered a value and one that refused it both read
    NULL.

    The filenames are deliberately adverse, the same pattern the runs-last
    test above uses: `invented-a-stamper.yml` sorts BEFORE
    `invented-z-bindings.yml`, both declare `direction: inbound`, and both are
    the same style — so the filename tiebreak alone would run the stamper
    first and leave the binding row's `consumes` NULL. The rank is what makes
    it land."""
    workspace = _workspace(
        tmp_path,
        [_bean("handle", SINK, EVENT)],
        _selection("handle")
        + _destination("handle-in-0", "events")
        + [(MEDIA_KEY, "default", WRITER), (MEDIA_KEY, "prod", WRITER)],
    )
    binding_catalog = Catalog(
        id="invented-z-bindings",
        style="config_join",
        protocol="kafka",
        direction="inbound",
        requires=("resolved_config",),
        matches={"address_from_config": _address()},
        source=Path("tests/invented-z-bindings.yml"),
    )
    stamping_catalog = Catalog(
        id="invented-a-stamper",
        style="config_join",
        protocol="kafka",
        direction="inbound",
        requires=("resolved_config",),
        matches={
            "media_from_config": {
                "rules": [
                    {
                        "key": MEDIA_KEY,
                        "fills": "consumes",
                        "on": {"protocol": "kafka", "direction": "inbound"},
                    }
                ],
                "values": {WRITER: "application/json"},
            }
        },
        source=Path("tests/invented-a-stamper.yml"),
    )
    skipped = derive_endpoints(
        workspace, [stamping_catalog, binding_catalog], capabilities=CAPABILITIES
    )
    [row] = _rows(workspace)
    workspace.close()

    assert skipped == []
    assert row["path"] == "events"
    assert row["consumes"] == JSON_MEDIA


def test_a_catalog_requiring_the_config_capability_is_skipped_without_it(
    tmp_path: Path,
):
    """The first PIPELINE-declared capability (D02 §1) gates exactly like a
    scanner-declared one: the catalog does not run, and the skip is
    reported. The gate is on the PASS having run, never on the table having
    rows — an empty `resolved_config` is a real answer."""
    workspace = _workspace(tmp_path, [_bean("handle", SINK, EVENT)])
    skipped = derive_endpoints(workspace, [_catalog()], capabilities=set())
    rows = _rows(workspace)
    workspace.close()

    assert [(entry.catalog_id, entry.missing_capabilities) for entry in skipped] == [
        ("invented-bindings", ("resolved_config",))
    ]
    assert rows == []


@pytest.mark.parametrize(
    ("matches", "expected"),
    [
        ({}, "declares neither"),
        (
            {"address_from_config": {"binding": {"from": "bean_name", "suffix": []}}},
            "needs `key` and `binding`",
        ),
        (
            {
                "address_from_config": {
                    "key": "acme.destination",
                    "binding": {"from": "bean_name", "suffix": _suffix_rules()},
                }
            },
            "{binding}",
        ),
        (
            {
                "address_from_config": {
                    "key": DESTINATION_KEY,
                    "binding": {"from": "annotation", "suffix": _suffix_rules()},
                }
            },
            "must be `bean_name`",
        ),
        (
            {
                "address_from_config": {
                    "key": DESTINATION_KEY,
                    "binding": {"from": "bean_name", "suffix": []},
                }
            },
            "non-empty list of rules",
        ),
        (
            {
                "address_from_config": {
                    "key": DESTINATION_KEY,
                    "binding": {"from": "bean_name", "suffix": [{"then": "-in-0"}]},
                }
            },
            "must be `{when",
        ),
        (
            {
                "address_from_config": {
                    "key": DESTINATION_KEY,
                    "binding": {
                        "from": "bean_name",
                        "suffix": [
                            {
                                "when": {"implements": PIPE},
                                "then": ["-in-0", "-out-0"],
                                "direction": ["inbound"],
                            }
                        ],
                    },
                }
            },
            "parallel list must name one per suffix",
        ),
        (
            {
                "address_from_config": {
                    "key": DESTINATION_KEY,
                    "binding": {
                        "from": "bean_name",
                        "suffix": [
                            {"when": {"implements": SINK}, "then": "-in-0", "direction": "sideways"}
                        ],
                    },
                }
            },
            "closed sets are closed",
        ),
        (
            {
                "address_from_config": _address(binder_protocols={"queues": "smoke-signal"}),
            },
            "closed sets are closed",
        ),
        # Fix round 1, M-8: `binder_key` is as per-binding as `key` is, and
        # one missing placeholder is the difference between "what does THIS
        # binding speak" and one key answered for every bean in the module.
        (
            {"address_from_config": _address(binder_key="acme.bindings.binder")},
            "`address_from_config.binder_key` must carry the",
        ),
        ({"media_from_config": {"rules": []}}, "non-empty list"),
        (
            {"media_from_config": {"rules": [{"key": MEDIA_KEY, "fills": "produces"}]}},
            "must be `{key, fills",
        ),
        (
            {
                "media_from_config": {
                    "rules": [
                        {
                            "key": MEDIA_KEY,
                            "fills": "path",
                            "on": {"protocol": "kafka", "direction": "outbound"},
                        }
                    ]
                }
            },
            "one of consumes, produces",
        ),
        (
            {
                "media_from_config": {
                    "rules": [
                        {
                            "key": MEDIA_KEY,
                            "fills": "produces",
                            "on": {"protocol": "smoke-signal", "direction": "outbound"},
                        }
                    ]
                }
            },
            "closed sets are closed",
        ),
    ],
)
def test_a_broken_catalog_is_refused_by_name(matches: dict, expected: str):
    """A broken file, not a degraded run — the same discipline every other
    engine's own `_validate_matches` keeps. Every value checked here reaches
    either a derived row's identity columns or a bound SQL parameter, where
    a typo is indistinguishable from an observation."""
    with pytest.raises(CatalogError) as raised:
        config_join.run(_UnusedWorkspace(), _catalog(matches))

    assert expected in str(raised.value)
    assert "invented-bindings.yml" in str(raised.value)


class _UnusedWorkspace:
    """Refuses every call: validation must refuse a broken catalog BEFORE it
    reads anything at all."""

    def query(self, name: str, **params: object) -> list[dict[str, object]]:
        raise AssertionError(f"queried {name} on a catalog that should have been refused")

    def derive(self, name: str, **params: object) -> None:
        raise AssertionError(f"derived {name} on a catalog that should have been refused")
