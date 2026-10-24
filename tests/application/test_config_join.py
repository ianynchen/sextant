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

import copy
import dataclasses
import json
from pathlib import Path

import pytest

from sextant.application.ports.catalogs import Catalog, CatalogError
from sextant.application.resolve.config import resolve_config
from sextant.application.resolve.endpoints import derive_endpoints
from sextant.application.resolve.engines import config_join
from sextant.application.resolve.open_questions import reset_open_questions
from sextant.application.resolve.service_identity import record_service_identity_gaps
from sextant.domain.closed_sets import ConstructKind, OriginTier
from sextant.domain.factfile import write_fact_file
from sextant.domain.facts import (
    AnnotationFact,
    AnnotationUse,
    CallArgument,
    CallSiteFact,
    CallTarget,
    ConfigEntryFact,
    Document,
    ModuleFact,
    Parameter,
    Signature,
    SymbolFact,
    TypeRef,
)
from sextant.domain.symbols import type_descriptor
from sextant.ingress.catalogs.yaml_source import YamlCatalogSource
from sextant.storage.duckdb.workspace import DuckDbWorkspace

CATALOGS_DIR = Path(__file__).parents[2] / "src" / "sextant" / "catalogs"
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
# The invented framework's own coordinate. `config_join` is dependency-gated
# (`resolve/dependencies.py`, `A-C5`), so a catalog of this style that declares
# none is refused at the gate — deliberately, since a `config_join` match can be
# satisfied by code naming no framework at all.
INVENTED_COORDINATE = "com.acme:acme-bindings"
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
        fact_schema_version=2,
        scanner_id="asm",
        content_hash="sha256:a",
        origin_entry="target/classes",
        origin_tier=OriginTier.MODULE_OUTPUT,
        redaction_set_hash="sha256:b",
    )


def _module_document() -> Document:
    """The document carrying the module fact the dependency gate reads."""
    return Document(
        document_id="doc_module",
        relative_path="module",
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


def _catalog(
    matches: dict | None = None, *, direction: str = "inbound", protocol: str = "kafka"
) -> Catalog:
    """`protocol` is a parameter for one reason (OI-1): a catalog declaring no
    `key` mints no endpoint row, and `resolve/endpoints.py` refuses a wire
    identity on a catalog that mints none. Every catalog here that derives
    rows keeps the default pair; the key-less ones declare neither, exactly as
    the shipped `spring-integration.yml` does."""
    return Catalog(
        id="invented-bindings",
        style="config_join",
        protocol=protocol,
        direction=direction,
        requires=("resolved_config",),
        matches=matches if matches is not None else {"address_from_config": _address()},
        source=Path("tests/invented-bindings.yml"),
        detect_coordinates=(INVENTED_COORDINATE,),
    )


def _workspace(
    tmp_path: Path,
    facts: list[SymbolFact] | list[SymbolFact | AnnotationFact] | None = None,
    config: list[tuple[str, str, str | None]] | None = None,
    *,
    coordinates: tuple[str, ...] | None = None,
) -> DuckDbWorkspace:
    """A workspace holding the given symbol facts and the given already
    resolved configuration — `(key, environment, value)`, a `None` value
    meaning the environment has the key but never resolved it (D01's
    unresolved-with-a-reason row, spelled `missing_key` here).

    `coordinates=None` writes no module fact at all, which is what every test
    below that reaches the engine DIRECTLY wants: the dependency gate lives in
    `derive_endpoints`, not in the engine, so a direct call never asks. The
    three tests that go through `derive_endpoints` name their coordinates,
    because since `config_join` joined `DEPENDENCY_GATED` the answer to "does
    this module declare the framework" decides whether the catalog runs at all
    (`test_derived_resource.py`'s own `_workspace` precedent)."""
    write_fact_file(tmp_path / "facts" / "Bindings.jsonl", _document(), list(facts or []))
    if coordinates is not None:
        write_fact_file(
            tmp_path / "facts" / "module.jsonl",
            _module_document(),
            [
                ModuleFact(
                    document_id="doc_module",
                    module_id="com.acme:orders-service",
                    module_kind="service",
                    languages=["java"],
                    source_roots=["src/main/java"],
                    output_dirs=["target/classes"],
                    dependency_coordinates=list(coordinates),
                )
            ],
        )
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    # The channel edge's stash (spec 2026-09-21 §3b), created the way the pipeline leaves
    # it before an engine runs: `run` writes its `read_by` end, and the tests below reach
    # `run` directly rather than through `derive_endpoints`, which owns the reset.
    workspace.derive("channel_bindings_reset")
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


@pytest.mark.pins("config_join.unmapped-binder-derives-no-row")
def test_a_binder_name_the_catalog_does_not_map_derives_no_row(tmp_path: Path):
    """F2 §3.4. This test pinned the opposite until W13, and its own name said
    so: `..._falls_back_to_its_protocol`, on the stated grounds that "an
    unmapped name is a gap to grow the catalog from, not a guess".

    It was a guess. The row it asserted carried the catalog's declared
    `protocol` — a value the matched evidence says nothing about — at
    `resolved`, which is the defaulted-identity rule's own definition of the
    defect (`tests/architecture/test_defaulted_identity_values.py`). That rule
    audits `fluent` captures and could not see this one, because this default
    lives in catalog data rather than in an engine.

    It is the one defect in this analysis that leaves the bundle: `protocol` is
    identity, DR-5 gates linking on protocol equality, and a row published on a
    protocol nobody read links into another consumer's graph against endpoints
    this module never speaks to.

    No row now. The `binder_protocol` question that replaces it is asserted by
    `test_an_unmapped_binder_derives_no_row_and_files_a_question` against the
    SHIPPED catalog; this one keeps the invented-catalog half, where the map is
    `{queues: jms}` and the configured name is `unheard-of`.
    """
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
    rows = _rows(workspace)
    workspace.close()

    assert rows == []


def test_a_binder_name_the_catalog_DOES_map_keeps_that_protocol(tmp_path: Path):
    """The paired positive the test above needs: a change that dropped every
    row whatever the binder said would pass it. `queues` is in the map, so the
    row derives on `jms` — the mapped protocol, not the catalog's `kafka`."""
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
        detect_coordinates=(INVENTED_COORDINATE,),
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


def _stamp_format(
    workspace: DuckDbWorkspace,
    direction: str,
    caller: str | None,
    answer: tuple,
    media: tuple[str | None, str | None] = (None, None),
) -> None:
    """One row's format pair, applied through the shipped `stamp_format` derive rather
    than a hand-written UPDATE — the columns below have to arrive the way the format pass
    actually writes them.

    `media` is passed through because `stamp_format.sql` matches on `consumes`/`produces`
    as well as on the wire identity: a row carrying a stamped media type is not the row a
    format stamp naming NULL media would find."""
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
                "consumes": media[0],
                "produces": media[1],
                "request_shape": None,
                "response_shape": None,
                "format": answer[0],
                "format_resolution": answer[1],
            }
        ],
    )


def test_each_direction_keeps_its_own_media_and_format(tmp_path: Path):
    """What five tests about the MERGE's carrying rules were really protecting, now that
    there is no merge (F5 §6.1, W27).

    `config_join` stamps `produces` on the outbound half of a path the module both exposes
    and calls. That stamp used to be destroyed with the twin `merge_endpoints.sql` deleted,
    leaving one row reading "no producer declared" — indistinguishable from a module that
    declares none — and the fix was to make the merge coalesce both media columns, both
    format columns, and take the weaker of the two format markers.

    None of that machinery exists any more, because neither row is deleted. Each half keeps
    what was stamped on it, which is stronger than carrying: a `format` from one direction
    beside a `format_resolution` from the other was possible under `arg_min` and is not
    possible here, and "some client of this path declared this peer" no longer has to stand
    in for saying which client.
    """
    workspace = _workspace(tmp_path)
    _seed(
        workspace,
        {"direction": "inbound", "path": "shared", "consumes": JSON_MEDIA},
        {"direction": "outbound", "path": "shared", "produces": JSON_MEDIA, "caller": "c"},
    )
    _stamp_format(workspace, "inbound", None, (None, "unresolved"), (JSON_MEDIA, None))
    _stamp_format(workspace, "outbound", "c", ("protobuf", "resolved"), (None, JSON_MEDIA))
    rows = {str(row["direction"]): row for row in _rows(workspace)}
    workspace.close()

    assert set(rows) == {"inbound", "outbound"}, "the two halves are never folded together"
    assert (rows["inbound"]["consumes"], rows["inbound"]["produces"]) == (JSON_MEDIA, None)
    assert (rows["outbound"]["consumes"], rows["outbound"]["produces"]) == (None, JSON_MEDIA)
    # The weakening rule went with the merge: an unanswered half no longer drags a
    # resolved one down, because there is no shared row for it to drag.
    assert (rows["inbound"]["format"], rows["inbound"]["format_resolution"]) == (
        None,
        "unresolved",
    )
    assert (rows["outbound"]["format"], rows["outbound"]["format_resolution"]) == (
        "protobuf",
        "resolved",
    )


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
        coordinates=(INVENTED_COORDINATE,),
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
    `invented-z-bindings.yml`, neither is `direction: inbound`, and both are
    the same style — so the filename tiebreak alone would run the stamper
    first and leave the binding row's `produces` NULL. The rank is what makes
    it land.

    **The binding side is OUTBOUND for the sake of that adversity (OI-1).** A
    stamping catalog now declares no wire identity at all — it mints no
    endpoint row, so `resolve/endpoints.py` refuses the pair on it — and an
    absent `direction` sorts on the wrong side of the `direction != "inbound"`
    tiebreak. Against an INBOUND binding catalog the tiebreak alone would
    order these two correctly and the rank under test would never be
    consulted."""
    workspace = _workspace(
        tmp_path,
        [_bean("emit", SOURCE, EVENT)],
        _selection("emit")
        + _destination("emit-out-0", "events")
        + [(MEDIA_KEY, "default", WRITER), (MEDIA_KEY, "prod", WRITER)],
        coordinates=(INVENTED_COORDINATE,),
    )
    binding_catalog = Catalog(
        id="invented-z-bindings",
        style="config_join",
        protocol="kafka",
        direction="outbound",
        requires=("resolved_config",),
        matches={"address_from_config": _address()},
        source=Path("tests/invented-z-bindings.yml"),
        detect_coordinates=(INVENTED_COORDINATE,),
    )
    stamping_catalog = Catalog(
        id="invented-a-stamper",
        style="config_join",
        protocol="",
        direction="",
        requires=("resolved_config",),
        matches={
            "media_from_config": {
                "rules": [
                    {
                        "key": MEDIA_KEY,
                        "fills": "produces",
                        "on": {"protocol": "kafka", "direction": "outbound"},
                    }
                ],
                "values": {WRITER: "application/json"},
            }
        },
        source=Path("tests/invented-a-stamper.yml"),
        detect_coordinates=(INVENTED_COORDINATE,),
    )
    skipped = derive_endpoints(
        workspace, [stamping_catalog, binding_catalog], capabilities=CAPABILITIES
    )
    [row] = _rows(workspace)
    workspace.close()

    assert skipped == []
    assert row["path"] == "events"
    assert row["produces"] == JSON_MEDIA


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
        ({}, "declares none of"),
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
            "must be one of `annotation_value`, `bean_name`",
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


# --- `A-C5` (principles sweep §3.2): the dependency gate ---------------------
#
# Against the SHIPPED `spring-cloud-stream` catalog rather than an invented
# stand-in, because the defect is not in the engine's reading of catalog data —
# it is that the shipped file's whole match reduces, on a module with no
# configuration, to "this method returns a `java.util.function` interface",
# which ordinary Java satisfies constantly.

_STREAM = "org.springframework.cloud:spring-cloud-stream"


def _helpers_facts() -> list[SymbolFact]:
    """Three ordinary utility methods on a plain class. No `@Bean`, no
    `@Configuration`, nothing naming Spring Cloud Stream anywhere — the exact
    input sweep 1 measured four fabricated Kafka boundaries from."""
    return [
        _bean(
            "nameNormalizer",
            "java.util.function.Function",
            "java/lang/String#",
            "java/lang/String#",
        ),
        _bean("auditSink", "java.util.function.Consumer", "java/lang/String#"),
        _bean("clockSupplier", "java.util.function.Supplier", "java/time/Clock#"),
    ]


def _stream_catalog() -> Catalog:
    return next(c for c in YamlCatalogSource(CATALOGS_DIR).load() if c.id == "spring-cloud-stream")


def test_spring_cloud_stream_derives_nothing_for_a_module_that_does_not_declare_it(
    tmp_path: Path,
):
    """`A-C5`, the near-miss. Three `java.util.function`-returning methods on a
    plain class, in a module whose build declares no Spring Cloud Stream at
    all, asserted four Kafka boundaries: `path` NULL at `unresolved`, naming
    real application methods as their handlers.

    Nothing about that row set is an address fabrication — it is worse in kind.
    It asserts the EXISTENCE of four boundaries the module does not have, which
    is §8's cardinal sin with the address column left honest.

    `rows == []` is the assertion the sweep's Tier-1 backlog requires, and the
    skip beside it is the other half: a catalog that derives nothing must be
    distinguishable from a framework that exposes nothing (M04, FR-17)."""
    # The selection NAMES one helper, so `rows == []` is attributable to the gate
    # and to nothing else. Without it the three helpers bind nothing for the
    # CARDINALITY reason (F2 §3.4) — measured: with the gate removed entirely,
    # `rows == []` still held, and only the `skipped` bookkeeping assertion below
    # caught it. A near-miss satisfied by a second, unrelated rule proves nothing
    # about the rule it names.
    workspace = _workspace(
        tmp_path,
        _helpers_facts(),
        _bindings(
            ("spring.cloud.function.definition", "auditSink"),
            ("spring.cloud.stream.bindings.auditSink-in-0.destination", "audit.events"),
        ),
        coordinates=("com.acme:something-else",),
    )
    skipped = derive_endpoints(workspace, [_stream_catalog()], capabilities=CAPABILITIES)
    rows = _rows(workspace)
    workspace.close()

    assert rows == []
    assert [entry.catalog_id for entry in skipped] == ["spring-cloud-stream"]
    assert _STREAM in skipped[0].missing_capabilities[0]


def test_spring_cloud_stream_still_derives_for_a_module_that_does_declare_it(
    tmp_path: Path,
):
    """The paired positive. Same facts, one coordinate different — so what the
    near-miss above proves is the GATE and not some other conjunct quietly
    matching nothing. A rule that declined everything would pass the near-miss
    and look correct all the way down (§10).

    It also records what the gate does NOT close, which is the honest half:
    `_candidates` reads every declared method and filters on the return type
    alone, so a utility method that merely RETURNS a functional interface is a
    candidate. Narrowing that needs a `@Bean` conjunct, and whether Spring Cloud
    Stream actually requires `@Bean` is a framework question no probe in this
    repository has answered — §8.1 forbids inventing the conjunct, so it is
    stated in `docs/COVERAGE.md` instead.

    **The selection is now load-bearing here, and was not before W13.** These
    three helpers used to derive four boundaries with no
    `spring.cloud.function.definition` at all. F2 §3.4's cardinality rule ends
    that — three candidates and no selection bind NOTHING, because the framework
    binds nothing (`eligibleFunction.size() == 1`) — so this test names one, and
    what it proves is unchanged: the gate is what the near-miss above measures,
    not some other conjunct silencing everything.

    Selecting `auditSink` rather than asserting on all three is also the smaller
    claim: one selected bean is enough to show rows derive at all."""
    workspace = _workspace(
        tmp_path,
        _helpers_facts(),
        # The SHIPPED catalog's own keys, not `_selection`/`_destination` — those
        # spell the invented framework's (`acme.function.definition`), and this
        # test drives `spring-cloud-stream.yml`.
        _bindings(
            ("spring.cloud.function.definition", "auditSink"),
            ("spring.cloud.stream.bindings.auditSink-in-0.destination", "audit.events"),
        ),
        coordinates=(_STREAM,),
    )
    skipped = derive_endpoints(workspace, [_stream_catalog()], capabilities=CAPABILITIES)
    rows = _rows(workspace)
    workspace.close()

    assert skipped == []
    assert {row["handler"] or row["caller"] for row in rows} != set()


# --- the `stamp_media.sql` settlement (principles sweep §7.4) ---------------
#
# Two sweeps touched this file and neither read it. Sweep 1 (backlog row 33)
# alleged that the UPDATE matches on `(protocol, direction)` ONLY — no
# `catalog_id`, no module scoping — so one module's
# `spring.kafka.producer.value-serializer` would stamp every `kafka/outbound`
# row in the workspace including rows other catalogs derived, and marked the
# row unverified. Sweep 2 (#25) recorded `spring-kafka-media.yml`'s own
# narrower claim — "a stamp lands only where every resolved environment agrees,
# and never over a non-NULL column" — as UNVERIFIED for the opposite reason.
#
# The SQL settles both. Sweep 2's claim is TRUE, and two tests above already
# proved each half against the engine. Sweep 1's is half true: the match really
# is `(protocol, direction)` alone, so it does reach rows another catalog
# derived — which is this catalog's whole PURPOSE, since it derives none of its
# own — but the CROSS-MODULE half is impossible. `endpoints` has no `module`
# column at all (`storage/duckdb/schema.sql`), `api.py` gives every submodule
# its own workspace, and `resolve()` runs once per module, so one module's
# configuration cannot reach another module's rows by any path.
#
# What is left is the reach WITHIN one module, and the two tests below pin it
# against the SHIPPED catalog rather than an invented one, because the question
# is about a real key on a real row set.

_KAFKA_MEDIA_KEY = "spring.kafka.producer.value-serializer"
_JSON_SERIALIZER = "org.springframework.kafka.support.serializer.JsonSerializer"


def _shipped_media_catalog() -> Catalog:
    from sextant.ingress.catalogs.yaml_source import YamlCatalogSource
    from sextant.resources import catalogs_dir

    return next(c for c in YamlCatalogSource(catalogs_dir()).load() if c.id == "spring-kafka-media")


def test_a_media_stamp_reaches_every_kafka_row_in_the_module_whatever_derived_it(
    tmp_path: Path,
):
    """§7.4, settled and pinned. `stamp_media.sql` matches on
    `(protocol, direction)` and nothing else, so a `spring.kafka.*` serializer
    stamps rows `kafka-clients.yml` derived from a RAW `KafkaProducer` as well
    as rows `spring-kafka-template.yml` derived.

    That is deliberate for the template — `spring-kafka-media.yml` derives no
    rows of its own and exists only to stamp others' — and it is an
    OVER-REPORT for the raw producer, which builds its own `Properties` and
    reads no `spring.kafka.*` key. The column is `produces`, carried data
    rather than identity: no address, verb or protocol is affected, and dedup
    and merge never compare it. It is recorded here rather than fixed because
    scoping a rule to a set of catalog ids is a D02 §2d schema change, and
    because the fix must not throw away the cross-catalog reach the rule needs.

    Bounded by the dependency gate: `config_join` joined `DEPENDENCY_GATED` in
    round 1a, so this catalog runs only on a module whose build declares
    `org.springframework.kafka:spring-kafka` — a module using the raw producer
    ALONE is never stamped at all. **Falsified by** a module that declares
    spring-kafka and also publishes through a raw `KafkaProducer` configured
    differently."""
    workspace = _workspace(
        tmp_path,
        config=[
            (_KAFKA_MEDIA_KEY, "default", _JSON_SERIALIZER),
            (_KAFKA_MEDIA_KEY, "prod", _JSON_SERIALIZER),
        ],
    )
    _seed(
        workspace,
        {"path": "orders", "catalog_id": "spring-kafka-template"},
        {"path": "raw-audit", "catalog_id": "kafka-clients"},
    )
    config_join.run(workspace, _shipped_media_catalog())
    rows = {row["path"]: row for row in _rows(workspace)}
    workspace.close()

    assert rows["orders"]["produces"] == JSON_MEDIA
    assert rows["raw-audit"]["produces"] == JSON_MEDIA


def test_a_media_stamp_reaches_no_row_of_another_protocol_or_direction(tmp_path: Path):
    """The near-miss for the same settlement, and the half sweep 1's row does
    NOT allege: the two columns the rule DOES name are honoured exactly. A
    `kafka/inbound` row and an `amqp/outbound` row sit beside the stamped ones
    and neither is touched, so the reach is wide within one `(protocol,
    direction)` pair and zero outside it.

    It discriminates: dropping either predicate from the UPDATE's WHERE makes
    this fail with a producer's serializer stamped onto a consumer's row."""
    workspace = _workspace(
        tmp_path,
        config=[
            (_KAFKA_MEDIA_KEY, "default", _JSON_SERIALIZER),
            (_KAFKA_MEDIA_KEY, "prod", _JSON_SERIALIZER),
        ],
    )
    _seed(
        workspace,
        {"path": "orders"},
        {"path": "orders-in", "direction": "inbound"},
        {"path": "orders-amqp", "protocol": "amqp"},
    )
    config_join.run(workspace, _shipped_media_catalog())
    rows = {row["path"]: row for row in _rows(workspace)}
    workspace.close()

    assert rows["orders"]["produces"] == JSON_MEDIA
    assert (rows["orders-in"]["produces"], rows["orders-in"]["consumes"]) == (None, None)
    assert (rows["orders-amqp"]["produces"], rows["orders-amqp"]["consumes"]) == (None, None)


# --- job 1's SECOND binding source: `from: annotation_value` (Task 9) ------
#
# The name a `config_join` catalog asks configuration about no longer has to
# be a bean's own method name. It may be the VALUE OF AN ANNOTATION ARGUMENT
# — a channel name written on the method the framework wires to that channel —
# which the probe measured reaching the fact stream verbatim, keyed by
# attribute name (`scripts/probes/spring-integration-destinations.md`, Q2).
#
# The vocabulary below is invented for the same reason every other block in
# this file is: a test that reached for the real framework's spellings would
# not prove the engine reads catalog data rather than knowing them. The
# shipped catalog's own answers are pinned separately, in the section after
# this one.

HANDLERS = "com/acme/streams/Handlers#"
ACTIVATOR = "com.acme.fn.Activator"
ACTIVATOR_SYMBOL = "com/acme/fn/Activator#"
EMITTER = "com.acme.fn.Emitter"
EMITTER_SYMBOL = "com/acme/fn/Emitter#"
CHANNEL_KEY = "acme.channels.{binding}.destination"


def _handler(name: str) -> SymbolFact:
    """One ordinary declared method — the target a channel annotation sits on.
    Its return type is `void`, so it is not a candidate for any suffix rule
    above and the two binding sources cannot be confused for each other."""
    return SymbolFact(
        document_id="doc_1",
        symbol=f"{_MODULE}{HANDLERS}{name}(sig_{name}).",
        construct_kind=ConstructKind.METHOD,
        enclosing=_MODULE + HANDLERS,
        signature=Signature(parameters=[], returns=TypeRef(symbol="void#")),
    )


def _handler_symbol(name: str) -> str:
    return f"{_MODULE}{HANDLERS}{name}(sig_{name})."


def _annotated(
    args: dict[str, object],
    *,
    annotation: str = ACTIVATOR_SYMBOL,
    target: str = "handle",
) -> AnnotationFact:
    return AnnotationFact(
        document_id="doc_1",
        target=_handler_symbol(target),
        use=AnnotationUse(annotation=annotation, args=args),
        retention="RUNTIME",
    )


def _channel_rules() -> list[dict]:
    """Two annotations, three attributes, each with the direction the
    framework's own attribute means — the whole of what this source needs to
    be told, and all of it catalog data."""
    return [
        {"annotation": ACTIVATOR, "arg": "inputChannel", "direction": "inbound"},
        {"annotation": ACTIVATOR, "arg": "outputChannel", "direction": "outbound"},
        {"annotation": EMITTER, "arg": "channel", "direction": "outbound"},
    ]


def _channel_address(**overrides: object) -> dict:
    binding: dict = {"from": "annotation_value", "channels": _channel_rules()}
    binding.update(overrides.pop("binding", {}))  # type: ignore[arg-type]
    address: dict = {"key": CHANNEL_KEY, "binding": binding}
    address.update(overrides)
    return address


def _channel_catalog(
    address: dict | None = None, *, direction: str = "inbound", protocol: str = "kafka"
) -> Catalog:
    return _catalog(
        {"address_from_config": address if address is not None else _channel_address()},
        direction=direction,
        protocol=protocol,
    )


def _channel_destination(channel: str, value: str | None) -> list[tuple[str, str, str | None]]:
    key = CHANNEL_KEY.replace("{binding}", channel)
    return [(key, "default", value), (key, "prod", value)]


def test_a_channel_named_by_an_annotation_argument_derives_a_row_from_its_key(
    tmp_path: Path,
):
    """The whole second source in one row. Nothing about this method's own
    NAME matters — `handle` appears in no key — and nothing about its return
    type matters either. The annotation argument carries the name,
    configuration says what the name means, and the annotated method is the
    row's handler."""
    workspace = _workspace(
        tmp_path,
        [_handler("handle"), _annotated({"inputChannel": "ordersIn"})],
        _channel_destination("ordersIn", "orders.queue"),
    )
    config_join.run(workspace, _channel_catalog())
    [row] = _rows(workspace)
    workspace.close()

    assert row["protocol"] == "kafka"
    assert row["direction"] == "inbound"
    assert row["method"] is None
    assert row["path"] == "orders.queue"
    assert row["handler"] == _handler_symbol("handle")
    assert row["caller"] is None
    assert row["peer"] is None
    assert row["resolution"] == "resolved"
    assert row["evidence"] == "compiler"
    assert row["catalog_id"] == "invented-bindings"
    # A channel annotation names a channel and nothing else: no functional
    # type argument was read, so no payload is claimed for it.
    assert row["request_shape"] is None
    assert row["handler_signature"] is None


def test_one_annotation_naming_two_channels_derives_a_row_for_each_direction(
    tmp_path: Path,
):
    """Both attributes of one use are read, and each carries the direction its
    own catalog row declares — the method CONSUMES from one channel and SENDS
    to the other, which is two boundaries and not one row whose direction
    cannot say which. `handler` and `caller` follow D01 §3's direction rule,
    exactly as the bean source's both-halves case does."""
    workspace = _workspace(
        tmp_path,
        [
            _handler("handle"),
            _annotated({"inputChannel": "ordersIn", "outputChannel": "auditOut"}),
        ],
        _channel_destination("ordersIn", "orders.queue")
        + _channel_destination("auditOut", "audit.queue"),
    )
    config_join.run(workspace, _channel_catalog())
    rows = {row["direction"]: row for row in _rows(workspace)}
    workspace.close()

    assert set(rows) == {"inbound", "outbound"}
    assert rows["inbound"]["path"] == "orders.queue"
    assert rows["inbound"]["handler"] == _handler_symbol("handle")
    assert rows["inbound"]["caller"] is None
    assert rows["outbound"]["path"] == "audit.queue"
    assert rows["outbound"]["caller"] == _handler_symbol("handle")
    assert rows["outbound"]["handler"] is None


def test_a_second_annotation_the_catalog_declares_contributes_its_own_channel(
    tmp_path: Path,
):
    """`channels` is a LIST of `(annotation, attribute)` rules, not one
    annotation with several attributes: a framework spells "this method feeds
    a channel" with more than one annotation, and each names its attribute."""
    workspace = _workspace(
        tmp_path,
        [
            _handler("tick"),
            _annotated({"channel": "ticks"}, annotation=EMITTER_SYMBOL, target="tick"),
        ],
        _channel_destination("ticks", "ticks.topic"),
    )
    config_join.run(workspace, _channel_catalog())
    [row] = _rows(workspace)
    workspace.close()

    assert (row["direction"], row["path"]) == ("outbound", "ticks.topic")
    assert row["caller"] == _handler_symbol("tick")


def test_a_channel_no_configuration_key_answers_derives_no_row_and_no_ghost_row(
    tmp_path: Path,
):
    """The rule that separates this source from the bean one, and it is a
    deliberate asymmetry (Task 9 step 5).

    A bean-name binding whose key nobody answered still derives a row: the
    BEAN is the declaration, it exists, and only its address is unread. A
    channel name is not a declaration of a wire at all — it names an
    in-process pipe — so a row with `path` NULL would assert a boundary
    nothing in the module states. There is no endpoint row and no ghost row;
    the channel becomes a question instead (`gaps` below)."""
    workspace = _workspace(
        tmp_path,
        [_handler("handle"), _annotated({"inputChannel": "ordersIn"})],
    )
    config_join.run(workspace, _channel_catalog())
    rows = _rows(workspace)
    workspace.close()

    assert rows == []


def test_a_catalog_declaring_no_key_template_derives_nothing(tmp_path: Path):
    """`key` is OPTIONAL for this source and required for the other, because
    the two are asking different questions. A framework whose channels have no
    standard configuration key at all declares none — the catalog then asks
    configuration nothing, derives nothing, and every channel it finds files a
    question. Left required, such a catalog would have to invent a key
    template, which is a convention no framework states."""
    workspace = _workspace(
        tmp_path,
        [_handler("handle"), _annotated({"inputChannel": "ordersIn"})],
        _channel_destination("ordersIn", "orders.queue"),
    )
    address = _channel_address()
    del address["key"]
    config_join.run(workspace, _channel_catalog(address))
    rows = _rows(workspace)
    workspace.close()

    assert rows == []


def test_two_methods_on_one_channel_whose_destination_resolves_derive_one_row(
    tmp_path: Path,
):
    """Wire identity dedups here exactly as it does for every other style
    (D02 §5): one destination, one direction, one protocol is one boundary,
    however many methods the framework subscribes to it."""
    workspace = _workspace(
        tmp_path,
        [
            _handler("handle"),
            _handler("audit"),
            _annotated({"inputChannel": "ordersIn"}),
            _annotated({"inputChannel": "ordersIn"}, target="audit"),
        ],
        _channel_destination("ordersIn", "orders.queue"),
    )
    config_join.run(workspace, _channel_catalog())
    rows = _rows(workspace)
    workspace.close()

    assert [(row["direction"], row["path"]) for row in rows] == [("inbound", "orders.queue")]


def test_a_channel_expression_is_asked_about_verbatim_and_never_substituted(
    tmp_path: Path,
):
    """The probe measured a placeholder-valued channel attribute reaching the
    facts verbatim and unresolved, which is the honest answer. The engine asks
    configuration about the expression exactly as written: it resolves nothing
    on the way in, so a key template built from `${...}` finds nothing and the
    channel becomes a question rather than a guessed name."""
    workspace = _workspace(
        tmp_path,
        [_handler("handle"), _annotated({"inputChannel": "${acme.audit-channel}"})],
        _channel_destination("${acme.audit-channel}", "audit.queue"),
    )
    config_join.run(workspace, _channel_catalog())
    [row] = _rows(workspace)
    workspace.close()

    assert row["path"] == "audit.queue"


def test_an_annotation_argument_that_is_not_a_string_names_no_channel(tmp_path: Path):
    """A channel name is a string. An attribute the extractor recorded as an
    array, a nested annotation or a number is not one, and turning any of them
    into text would ask configuration about a name nobody wrote."""
    workspace = _workspace(
        tmp_path,
        [_handler("handle"), _annotated({"inputChannel": ["ordersIn"]})],
        _channel_destination("ordersIn", "orders.queue"),
    )
    config_join.run(workspace, _channel_catalog())
    rows = _rows(workspace)
    workspace.close()

    assert rows == []


def test_an_empty_channel_name_names_no_channel(tmp_path: Path):
    """The boundary value beside it. An attribute written empty is not a
    channel, and a key template built from it would ask about
    `acme.channels..destination` — a key whose answer belongs to nothing."""
    workspace = _workspace(
        tmp_path,
        [_handler("handle"), _annotated({"inputChannel": ""})],
        [("acme.channels..destination", "default", "orders.queue")],
    )
    config_join.run(workspace, _channel_catalog())
    rows = _rows(workspace)
    workspace.close()

    assert rows == []


def test_an_annotation_value_catalog_declaring_no_channels_is_refused_by_name():
    """`channels` is what `annotation_value` reads; a block declaring none
    would run, read nothing and derive nothing, which reads as "this framework
    wires no channels"."""
    with pytest.raises(CatalogError) as raised:
        config_join.run(
            _UnusedWorkspace(),
            _channel_catalog({"key": CHANNEL_KEY, "binding": {"from": "annotation_value"}}),
        )

    assert "`address_from_config.binding.channels` must be a non-empty list" in str(raised.value)
    assert "invented-bindings.yml" in str(raised.value)


def test_a_channel_rule_missing_its_attribute_is_refused_by_name():
    """Both halves of a rule are matched VERBATIM against a fact, so a rule
    that names only one of them can only ever decline — silently, forever."""
    with pytest.raises(CatalogError) as raised:
        config_join.run(
            _UnusedWorkspace(),
            _channel_catalog(_channel_address(binding={"channels": [{"annotation": ACTIVATOR}]})),
        )

    assert "must be `{annotation: <type>|[<type>, ...], arg: <attribute>" in str(raised.value)


def test_a_channel_rule_declaring_a_direction_outside_the_closed_set_is_refused():
    """NFR-5: the value reaches a derived row's `direction` column, where a
    typo is indistinguishable from an observation."""
    with pytest.raises(CatalogError) as raised:
        config_join.run(
            _UnusedWorkspace(),
            _channel_catalog(
                _channel_address(
                    binding={
                        "channels": [
                            {"annotation": ACTIVATOR, "arg": "inputChannel", "direction": "up"}
                        ]
                    }
                )
            ),
        )

    assert "closed sets are closed" in str(raised.value)


# --- the `channel_destination` hand-off (2O design §5) --------------------


def test_a_channel_no_key_template_covers_files_a_question_naming_it(tmp_path: Path):
    """The deliverable of the built-in shape. Nothing was derived — no wire
    row, no ghost row — and the channel is not lost either: it becomes a
    question carrying the two things an enrichment seat needs to answer it,
    the channel name and the method the framework wires to it.

    `candidates` is a LIST OF DICTS, the shape every other question kind uses
    and every renderer arm expects."""
    workspace = _workspace(
        tmp_path,
        [_handler("handle"), _annotated({"inputChannel": "ordersIn"})],
    )
    address = _channel_address()
    del address["key"]
    questions = config_join.gaps(workspace, _channel_catalog(address))
    workspace.close()

    assert questions == [
        {
            "protocol": "kafka",
            "method": None,
            "path": "ordersIn",
            "question": "channel_destination",
            "candidates": json.dumps(
                [{"channel": "ordersIn", "handler": _handler_symbol("handle")}],
                sort_keys=True,
                separators=(",", ":"),
            ),
            "evidence": (
                "this catalog declares no destination key template, so no configuration "
                "key names this channel's destination"
            ),
        }
    ]


def test_a_channel_whose_declared_key_nobody_answered_names_the_key_it_read(
    tmp_path: Path,
):
    """The other reason, kept apart from the first because the trail is what a
    reader acts on: a key WAS built and asked, and configuration did not
    answer it with one value. The question names that key."""
    workspace = _workspace(
        tmp_path,
        [_handler("handle"), _annotated({"inputChannel": "ordersIn"})],
        # Two environments disagreeing is one of the four ways `_agreed`
        # answers None, and the honest one to prove here: both values stay in
        # `resolved_config`, and neither becomes an address.
        [
            ("acme.channels.ordersIn.destination", "default", "dev.queue"),
            ("acme.channels.ordersIn.destination", "prod", "prod.queue"),
        ],
    )
    [question] = config_join.gaps(workspace, _channel_catalog())
    rows = _rows(workspace)
    workspace.close()

    assert rows == []
    assert question["path"] == "ordersIn"
    assert question["evidence"] == (
        "resolved_config carries no value every environment agrees on for "
        "`acme.channels.ordersIn.destination`"
    )


def test_a_channel_whose_destination_resolved_files_no_question(tmp_path: Path):
    """The paired positive for the whole ledger half: the question is filed
    where the answer is missing and nowhere else, so a channel the
    configuration DID name reaches the endpoint table and not the inbox."""
    workspace = _workspace(
        tmp_path,
        [_handler("handle"), _annotated({"inputChannel": "ordersIn"})],
        _channel_destination("ordersIn", "orders.queue"),
    )
    catalog = _channel_catalog()
    config_join.run(workspace, catalog)
    questions = config_join.gaps(workspace, catalog)
    rows = _rows(workspace)
    workspace.close()

    assert [row["path"] for row in rows] == ["orders.queue"]
    assert questions == []


def test_one_channel_read_by_two_methods_files_a_question_for_each(tmp_path: Path):
    """The question is about a channel AND the handler on it: two methods
    subscribed to one unanswered channel are two hand-offs, because the
    symbol is half of what makes the question answerable."""
    workspace = _workspace(
        tmp_path,
        [
            _handler("handle"),
            _handler("audit"),
            _annotated({"inputChannel": "ordersIn"}),
            _annotated({"inputChannel": "ordersIn"}, target="audit"),
        ],
    )
    address = _channel_address()
    del address["key"]
    questions = config_join.gaps(workspace, _channel_catalog(address))
    workspace.close()

    assert [json.loads(q["candidates"])[0]["handler"] for q in questions] == [
        _handler_symbol("audit"),
        _handler_symbol("handle"),
    ]


def test_a_method_on_both_ends_of_one_unanswered_channel_asks_once(tmp_path: Path):
    """The boundary beside it. One method that both consumes from and
    publishes to the same channel asks ONE question — "what destination does
    this channel carry" has one answer, and the direction is not part of it."""
    workspace = _workspace(
        tmp_path,
        [
            _handler("relay"),
            _annotated({"inputChannel": "loop", "outputChannel": "loop"}, target="relay"),
        ],
    )
    address = _channel_address()
    del address["key"]
    questions = config_join.gaps(workspace, _channel_catalog(address))
    workspace.close()

    assert [question["path"] for question in questions] == ["loop"]


def test_a_bean_name_catalog_files_no_question_at_all(tmp_path: Path):
    """Inert for the other binding source, and that is a claim rather than an
    omission: a bean-name binding whose key nobody answered already derives an
    endpoint row saying so (D02 §2d), and a question beside it would be a
    second record of a fact the endpoint table carries."""
    workspace = _workspace(tmp_path, [_bean("handle", SINK, EVENT)], _selection("handle"))
    questions = config_join.gaps(workspace, _catalog())
    workspace.close()

    assert questions == []


def test_a_media_only_catalog_files_no_question_at_all(tmp_path: Path):
    """Inert for the stamping shape too — it has no address block at all, so
    there is no channel and nothing to ask about."""
    workspace = _workspace(tmp_path)
    questions = config_join.gaps(
        workspace,
        _catalog(
            {
                "media_from_config": {
                    "rules": [
                        {
                            "key": MEDIA_KEY,
                            "fills": "produces",
                            "on": {"protocol": "kafka", "direction": "outbound"},
                        }
                    ]
                }
            }
        ),
    )
    workspace.close()

    assert questions == []


def test_the_questions_ride_the_gaps_seam_and_survive_the_ledger_reset(tmp_path: Path):
    """The step this task's own plan calls out (Task 9 step 2), and the reason
    `gaps` exists rather than a write inside `run`: `open_questions` is
    emptied ONCE per resolve, from the pipeline, AFTER the engine loop. A row
    written during `run` would be erased before anything read it — silently,
    because a shorter ledger reads exactly like a run with fewer questions.

    Run through the whole pipeline rather than the seam function alone, so
    what is proved is the ORDER and not just that a list was returned."""
    workspace = _workspace(
        tmp_path,
        [_handler("handle"), _annotated({"inputChannel": "ordersIn"})],
        coordinates=(INVENTED_COORDINATE,),
    )
    address = _channel_address()
    del address["key"]
    # No `key`, so no endpoint row, so no wire identity to declare (OI-1) —
    # `derive_endpoints` refuses the pair on a catalog that mints none.
    catalog = _channel_catalog(address, direction="", protocol="")
    derive_endpoints(workspace, [catalog], capabilities=CAPABILITIES)
    reset_open_questions(workspace)
    record_service_identity_gaps(workspace, [catalog])
    questions = workspace.query("open_questions")
    workspace.close()

    assert [(row["question"], row["path"]) for row in questions] == [
        ("channel_destination", "ordersIn")
    ]


# --- the path seam reads the ROW's own protocol and direction (step 4) ----


def test_a_config_join_row_is_canonicalized_by_its_own_protocol_and_direction(
    tmp_path: Path,
):
    """The Task 2 carry. `single_call` had this exact shape and this exact
    bug: its rows carry a per-row `direction` while its path seam asked
    `catalog.direction`, so the gate answered about a different row from the
    one being minted. Both halves of a `config_join` row's identity are
    per-row — direction from the suffix rule, protocol from the binder
    configuration — so a gate reading either catalog default answers about
    something else again.

    One HTTP catalog declared OUTBOUND, two suffix rules, the same slashless
    address: the rule overriding to inbound must become `/orders` (§8's
    canonical identity, CP-1), and the rule keeping the catalog's own
    direction must keep `orders` (ruling R8 — a client's relative mapping is
    resolved against its base address's path, so prefixing it rewrites an
    address rather than normalizing a spelling). The test therefore fails if
    the seam reads either direction alone.

    No shipped catalog reaches this branch, and that is stated rather than
    hidden: `serves_urls` is inbound HTTP alone and both shipped `config_join`
    catalogs speak broker protocols. It is written against the row because the
    seam is a property of the address."""
    catalog = Catalog(
        id="invented-http-bindings",
        style="config_join",
        protocol="http",
        direction="outbound",
        requires=("resolved_config",),
        matches={
            "address_from_config": {
                "key": DESTINATION_KEY,
                "binding": {
                    "from": "bean_name",
                    "suffix": [
                        {"when": {"implements": SINK}, "then": "-in-0", "direction": "inbound"},
                        {"when": {"implements": SOURCE}, "then": "-out-0"},
                    ],
                },
            }
        },
        source=Path("tests/invented-http-bindings.yml"),
        detect_coordinates=(INVENTED_COORDINATE,),
    )
    workspace = _workspace(
        tmp_path,
        [_bean("serve", SINK, EVENT), _bean("call", SOURCE, EVENT)],
        _destination("serve-in-0", "orders") + _destination("call-out-0", "orders"),
    )
    config_join.run(workspace, catalog)
    rows = {row["direction"]: row["path"] for row in _rows(workspace)}
    workspace.close()

    assert rows == {"inbound": "/orders", "outbound": "orders"}


def test_a_channel_row_takes_the_same_seam_from_its_own_channel_rule(tmp_path: Path):
    """The same rule through the other binding source, because the direction
    reaching `_addressed` comes from a different place there — a `channels`
    rule rather than a suffix rule — and a seam wired to only one of them
    would be right by accident."""
    catalog = Catalog(
        id="invented-http-channels",
        style="config_join",
        protocol="http",
        direction="outbound",
        requires=("resolved_config",),
        matches={"address_from_config": _channel_address()},
        source=Path("tests/invented-http-channels.yml"),
        detect_coordinates=(INVENTED_COORDINATE,),
    )
    workspace = _workspace(
        tmp_path,
        [
            _handler("handle"),
            _annotated({"inputChannel": "ordersIn", "outputChannel": "auditOut"}),
        ],
        _channel_destination("ordersIn", "orders") + _channel_destination("auditOut", "orders"),
    )
    config_join.run(workspace, catalog)
    rows = {row["direction"]: row["path"] for row in _rows(workspace)}
    workspace.close()

    assert rows == {"inbound": "/orders", "outbound": "orders"}


# --- the SHIPPED `spring-integration` catalog ------------------------------
#
# Everything above is invented on purpose. This section is the other half:
# what the file Sextant actually ships answers, in the framework's own
# spellings, so a change to those spellings fails here rather than silently
# covering nothing.

_SI = "org/springframework/integration/annotation/"
_SERVICE_ACTIVATOR = _SI + "ServiceActivator#"
_INBOUND_ADAPTER = _SI + "InboundChannelAdapter#"
_FLOW = "com/acme/orders/OrderFlow#"


def _spring_integration() -> Catalog:
    return next(
        catalog
        for catalog in YamlCatalogSource(CATALOGS_DIR).load()
        if catalog.id == "spring-integration"
    )


def _flow_method(name: str) -> SymbolFact:
    return SymbolFact(
        document_id="doc_1",
        symbol=f"{_MODULE}{_FLOW}{name}(sig_{name}).",
        construct_kind=ConstructKind.METHOD,
        enclosing=_MODULE + _FLOW,
        signature=Signature(parameters=[], returns=TypeRef(symbol="void#")),
    )


def _flow_annotation(
    args: dict[str, object],
    *,
    annotation: str = _SERVICE_ACTIVATOR,
    target: str = f"{_FLOW}handleOrder(sig_handleOrder).",
) -> AnnotationFact:
    return AnnotationFact(
        document_id="doc_1",
        target=_MODULE + target,
        use=AnnotationUse(annotation=annotation, args=args),
        retention="RUNTIME",
    )


def test_the_shipped_catalog_files_a_question_for_every_channel_and_derives_no_wire(
    tmp_path: Path,
):
    """The deliverable, whole (2O design §5). This catalog declares no `key`,
    because Spring Integration defines no standard configuration key for a
    channel's destination — a template here would be a PROJECT convention. So
    it derives nothing at all, and every channel the code names becomes a
    `channel_destination` question carrying the channel and the handler.

    The two shapes measured by the probe are both here: the service
    activator's `inputChannel`/`outputChannel` (Q2, Q3 — the same literal the
    adapter's own `setOutputChannelName` writes) and the polled adapter's
    `channel` (Q2). Never a fabricated wire, never `peer: in-process`.

    **And no protocol on the questions either (OI-1).** Every one of these read
    `amqp` from Task 9 until the wire-identity rule was re-keyed on what a
    catalog derives: this file mints no endpoint row, so it declares no wire
    identity, so the column the questions carry is empty rather than guessed.
    Which broker a channel reaches — if any — is the question, not the answer
    to it."""
    workspace = _workspace(
        tmp_path,
        [
            _flow_method("handleOrder"),
            _flow_method("tick"),
            _flow_annotation(
                {"inputChannel": "amqpInputChannel", "outputChannel": "amqpAuditChannel"}
            ),
            _flow_annotation(
                {"channel": "tickChannel"},
                annotation=_INBOUND_ADAPTER,
                target=f"{_FLOW}tick(sig_tick).",
            ),
        ],
    )
    catalog = _spring_integration()
    config_join.run(workspace, catalog)
    questions = config_join.gaps(workspace, catalog)
    rows = _rows(workspace)
    workspace.close()

    assert rows == []
    assert [(q["protocol"], q["path"], q["question"]) for q in questions] == [
        ("", "amqpAuditChannel", "channel_destination"),
        ("", "amqpInputChannel", "channel_destination"),
        ("", "tickChannel", "channel_destination"),
    ]
    assert json.loads(questions[1]["candidates"]) == [
        {
            "channel": "amqpInputChannel",
            "handler": f"{_MODULE}{_FLOW}handleOrder(sig_handleOrder).",
        }
    ]


@pytest.mark.declines("spring-integration")
@pytest.mark.pins("spring-integration.channels-are-the-channel-attributes")
def test_a_service_activator_naming_no_channel_attribute_asks_nothing(tmp_path: Path):
    """`sendTimeout` is a real `@ServiceActivator` attribute, it is a `String`
    exactly as the two channel attributes are, and it is not a channel. Every
    conjunct but one is satisfied here — the shipped annotation, on a method,
    with a string argument written — which is what makes this a near-miss
    rather than an empty input.

    Reading it would file a question about a channel called `3000` in the
    ledger a human is asked to answer, and an enrichment seat would go looking
    for a destination for a send timeout."""
    workspace = _workspace(
        tmp_path,
        [_flow_method("handleOrder"), _flow_annotation({"sendTimeout": "3000"})],
    )
    catalog = _spring_integration()
    config_join.run(workspace, catalog)
    questions = config_join.gaps(workspace, catalog)
    rows = _rows(workspace)
    workspace.close()

    assert (rows, questions) == ([], [])


@pytest.mark.pins("config_join.channel-target-is-a-method")
def test_a_channel_annotation_on_an_annotation_type_asks_nothing(tmp_path: Path):
    """`@ServiceActivator` is `@Target`-legal on an ANNOTATION TYPE, which is
    how a module composes its own stereotype. That declaration wires nothing
    to any channel: no method subscribes, so a question there would send an
    enrichment seat after a destination for a handler that does not exist.
    `scheduled_work.declaration-is-a-method` is the same conjunct one table
    over, and `derive_endpoints.sql`'s `handler-is-a-method` join is it on the
    wire side."""
    composed = "com/acme/orders/OnOrders#"
    workspace = _workspace(
        tmp_path,
        [
            SymbolFact(
                document_id="doc_1",
                symbol=_MODULE + composed,
                construct_kind=ConstructKind.INTERFACE,
            ),
            _flow_annotation({"inputChannel": "amqpInputChannel"}, target=composed),
        ],
    )
    catalog = _spring_integration()
    config_join.run(workspace, catalog)
    questions = config_join.gaps(workspace, catalog)
    rows = _rows(workspace)
    workspace.close()

    assert (rows, questions) == ([], [])


def test_the_shipped_catalog_is_skipped_where_the_build_declares_no_integration(
    tmp_path: Path,
):
    """The dependency gate, and the paired positive for the near-misses above
    in the other axis: a catalog that derived nothing must be distinguishable
    from a framework that exposes nothing (M04, FR-17). `config_join` is
    dependency-gated by STYLE, so this file is gated like the other two."""
    workspace = _workspace(
        tmp_path,
        [_flow_method("handleOrder"), _flow_annotation({"inputChannel": "amqpInputChannel"})],
        coordinates=("com.acme:something-else",),
    )
    skipped = derive_endpoints(
        workspace, [_spring_integration()], capabilities={"resolved_config", "annotation_args"}
    )
    workspace.close()

    assert [entry.catalog_id for entry in skipped] == ["spring-integration"]
    assert "spring-integration-core" in skipped[0].missing_capabilities[0]


# --- OI-1: the wire-identity rule, re-keyed on what a catalog DERIVES -------
#
# Task 8 keyed it on the STYLE, and `config_join` is a style whose catalogs
# may or may not mint endpoint rows. Under that reading `spring-integration.yml`
# had to declare a protocol to load, so it declared `amqp` and stamped it on
# every `channel_destination` question it filed — a Kafka- or JMS-fed
# channel's included. These four tests are the rule and its audit list
# (§8.3); `test_call_engines` runs every shipped catalog through
# `derive_endpoints`, which is what keeps the list honest as catalogs are
# added.


def test_a_catalog_with_no_destination_key_may_not_declare_a_wire_identity(tmp_path: Path):
    """The arm OI-1 opened. No `key` means `_derive_channels` answers no
    channel at all, so nothing this file writes has a protocol — and the one
    place the declaration would still reach is the `protocol` column of the
    questions it files, where it is a guess a reader believes."""
    address = _channel_address()
    del address["key"]
    workspace = _workspace(tmp_path, [], coordinates=(INVENTED_COORDINATE,))

    with pytest.raises(CatalogError) as raised:
        derive_endpoints(workspace, [_channel_catalog(address)], capabilities=CAPABILITIES)
    workspace.close()

    assert "derives no endpoint rows" in str(raised.value)
    assert "invented-bindings.yml" in str(raised.value)


def test_a_catalog_that_does_derive_rows_still_must_declare_both(tmp_path: Path):
    """The other arm, unchanged in effect and now asked of the catalog rather
    than the style: a `key` is an address this file will publish, and a row
    with no protocol is a boundary nobody can address."""
    workspace = _workspace(tmp_path, [], coordinates=(INVENTED_COORDINATE,))

    with pytest.raises(CatalogError) as raised:
        derive_endpoints(
            workspace, [_channel_catalog(protocol="", direction="")], capabilities=CAPABILITIES
        )
    workspace.close()

    assert "derives endpoint rows" in str(raised.value)
    assert "invented-bindings.yml" in str(raised.value)


def test_the_shipped_channel_catalog_declares_no_wire_identity():
    """`spring-integration.yml`, pinned. It mints no endpoint row, so it has
    no wire identity to state, and a later editor restoring `protocol: amqp`
    to make the file look like its neighbours would be restoring OI-1 —
    `amqp` on every question a Kafka- or JMS-fed channel files."""
    catalog = _spring_integration()
    assert (catalog.protocol, catalog.direction) == ("", "")
    assert config_join.derives_rows(catalog) is False


def test_the_shipped_media_catalog_declares_no_wire_identity():
    """`spring-kafka-media.yml`, the other half of the audit list. It only
    STAMPS columns onto rows other engines minted, and each of its own rules
    carries the `(protocol, direction)` pair of the rows it applies to — the
    top-level pair named nothing this file writes, and its `direction:
    inbound` was flatly at odds with the outbound rule sitting beside the
    inbound one."""
    catalog = next(
        entry
        for entry in YamlCatalogSource(CATALOGS_DIR).load()
        if entry.id == "spring-kafka-media"
    )
    assert (catalog.protocol, catalog.direction) == ("", "")
    assert config_join.derives_rows(catalog) is False


# --- F2 §3.4: cardinality, and the protocol that is never defaulted ---------
#
# Built on this file's own `_workspace`/`_bean` helpers rather than a second
# harness: they already write the module fact the dependency gate reads, and a
# private copy would be a second thing to keep in step with the catalog.


def _stream_questions(workspace: DuckDbWorkspace) -> list[dict]:
    """The questions the pipeline's own seam files, not `derive_endpoints`.

    The ledger is emptied once per resolve and every `gaps` writer runs AFTER
    that reset, from `service_identity` — so a test that called only
    `derive_endpoints` would read zero questions for every shape, including the
    one whose entire subject is a question.
    """
    reset_open_questions(workspace)
    record_service_identity_gaps(workspace, [_stream_catalog()])
    return workspace.query("open_questions")


def _bindings(*pairs: tuple[str, str]) -> list[tuple[str, str, str | None]]:
    """Configuration in the `(key, environment, value)` shape `_workspace` takes,
    stated for one environment because none of these questions is per-profile."""
    return [(key, "default", value) for key, value in pairs]


# `_workspace(coordinates=None)` writes NO module fact, which is right for the
# tests that call an engine directly. These four go through `derive_endpoints`,
# whose dependency gate would skip the catalog and make every assertion below
# hold for the wrong reason.
_STREAM_COORDINATE = "org.springframework.cloud:spring-cloud-stream"


@pytest.mark.pins("config_join.unselected-cardinality")
def test_two_function_beans_and_no_definition_bind_nothing(tmp_path: Path):
    """F2 §3.4's cardinality rule, mirrored from the framework's own code.

    `SimpleFunctionRegistry.normalizeFunctionDefinition` opens its guard with
    `eligibleFunction.size() == 1` — it defaults the definition to a bean only
    where there is exactly one. With two eligible functions and no
    `spring.cloud.function.definition` the definition stays empty and NOTHING
    binds (`scripts/probes/w13_stream_binding.md`).

    The catalog said the opposite in prose — "every candidate binds, the
    framework's own default" — and derived one endpoint per bean for an
    application that serves neither. A sentence naming the framework as its
    authority, saying what the framework does not do.
    """
    workspace = _workspace(
        tmp_path,
        [
            _bean("orders", "java.util.function.Consumer", "java/lang/String#"),
            _bean("payments", "java.util.function.Consumer", "java/lang/String#"),
        ],
        _bindings(
            ("spring.cloud.stream.default-binder", "kafka"),
            ("spring.cloud.stream.bindings.orders-in-0.destination", "orders.topic"),
            ("spring.cloud.stream.bindings.payments-in-0.destination", "payments.topic"),
        ),
        coordinates=(_STREAM_COORDINATE,),
    )
    skipped = derive_endpoints(workspace, [_stream_catalog()], capabilities=CAPABILITIES)
    rows = _rows(workspace)
    questions = _stream_questions(workspace)
    workspace.close()

    assert skipped == [], f"skipped, so this test measures nothing: {skipped}"
    assert rows == []
    # And the suppression is VISIBLE. Suppressing silently was the first version
    # of this rule, on the reasoning that the framework binds nothing so no row is
    # the complete answer — which needed our candidate count to equal the
    # framework's. It does not: `_candidates` counts declared METHODS returning
    # the declared interfaces, the framework counts registered BEANS. One real
    # bean beside one ordinary helper derived nothing at all.
    assert sorted((q["question"], q["path"]) for q in questions) == [
        ("unselected_binding", "orders"),
        ("unselected_binding", "payments"),
    ]


def test_one_function_bean_and_no_definition_still_binds(tmp_path: Path):
    """The paired positive: the framework DOES default to a lone function, so a
    rule that silenced both counts would pass the test above while losing every
    single-function Stream application in the estate."""
    workspace = _workspace(
        tmp_path,
        [_bean("orders", "java.util.function.Consumer", "java/lang/String#")],
        _bindings(
            ("spring.cloud.stream.default-binder", "kafka"),
            ("spring.cloud.stream.bindings.orders-in-0.destination", "orders.topic"),
        ),
        coordinates=(_STREAM_COORDINATE,),
    )
    skipped = derive_endpoints(workspace, [_stream_catalog()], capabilities=CAPABILITIES)
    rows = [(r["protocol"], r["path"]) for r in _rows(workspace)]
    workspace.close()

    assert skipped == []
    assert rows == [("kafka", "orders.topic")]


@pytest.mark.declines("spring-cloud-stream")
@pytest.mark.pins("config_join.unmapped-binder-derives-no-row")
def test_an_unmapped_binder_derives_no_row_and_files_a_question(tmp_path: Path):
    """F2 §3.4's second half, and the one defect in this analysis that leaves
    the bundle.

    A binder name absent from `binder_protocols` used to fall back to the
    catalog's declared `protocol:`, so a module bound to `rocketmq` published a
    row on `kafka` — complete, confident, with nothing saying the protocol had
    not been read. `protocol` is IDENTITY and DR-5 gates linking on protocol
    equality, so that row links into another consumer's graph against endpoints
    this module never speaks to, and misses the ones it does.

    No row now, and a `binder_protocol` question carrying the binding and the
    configured name — the two things a reader needs to close it. The question's
    own `protocol` is NULL: one that named a protocol would assert the very
    thing it reports as unread.
    """
    workspace = _workspace(
        tmp_path,
        [_bean("orders", "java.util.function.Consumer", "java/lang/String#")],
        _bindings(
            ("spring.cloud.stream.default-binder", "rocketmq"),
            ("spring.cloud.stream.bindings.orders-in-0.destination", "orders.topic"),
        ),
        coordinates=(_STREAM_COORDINATE,),
    )
    derive_endpoints(workspace, [_stream_catalog()], capabilities=CAPABILITIES)
    rows = _rows(workspace)
    questions = _stream_questions(workspace)
    workspace.close()

    assert rows == []
    assert [(q["question"], q["path"], q["protocol"]) for q in questions] == [
        ("binder_protocol", "orders-in-0", None)
    ]
    assert "rocketmq" in str(questions[0]["candidates"])


def test_a_mapped_binder_resolves_to_its_own_protocol_not_the_catalogs(tmp_path: Path):
    """The paired positive for the protocol half. `rabbit` maps to `amqp`, so
    this proves the map is READ rather than the file's `protocol: kafka` being
    returned for everything — a change that made every unmapped name silent
    could otherwise pass the test above by making every name silent."""
    workspace = _workspace(
        tmp_path,
        [_bean("orders", "java.util.function.Consumer", "java/lang/String#")],
        _bindings(
            ("spring.cloud.stream.default-binder", "rabbit"),
            ("spring.cloud.stream.bindings.orders-in-0.destination", "orders.queue"),
        ),
        coordinates=(_STREAM_COORDINATE,),
    )
    derive_endpoints(workspace, [_stream_catalog()], capabilities=CAPABILITIES)
    rows = [(r["protocol"], r["path"]) for r in _rows(workspace)]
    questions = _stream_questions(workspace)
    workspace.close()

    assert rows == [("amqp", "orders.queue")]
    assert questions == []


def test_a_lone_bean_beside_a_helper_method_is_not_silently_suppressed(tmp_path: Path):
    """The Critical this rule's first version introduced, kept as a test.

    One real `Consumer` bean and one ordinary helper returning `Function` — a
    shape the framework binds, because it counts registered BEANS and sees one.
    `_candidates` counts declared METHODS returning the declared interfaces and
    sees two, so the cardinality rule suppressed both and the module's real
    binding vanished with nothing saying so.

    The count cannot be fixed here — closing it needs a `@Bean` conjunct nobody
    has measured yet (`docs/COVERAGE.md` records the over-count). What CAN be
    fixed is the silence, and that is what this asserts: no fabricated row, and
    no absence that reads like a module with no such boundary.
    """
    workspace = _workspace(
        tmp_path,
        [
            _bean("orders", "java.util.function.Consumer", "java/lang/String#"),
            _bean(
                "nameHelper",
                "java.util.function.Function",
                "java/lang/String#",
                "java/lang/String#",
            ),
        ],
        _bindings(
            ("spring.cloud.stream.default-binder", "kafka"),
            ("spring.cloud.stream.bindings.orders-in-0.destination", "orders.topic"),
        ),
        coordinates=(_STREAM_COORDINATE,),
    )
    derive_endpoints(workspace, [_stream_catalog()], capabilities=CAPABILITIES)
    rows = _rows(workspace)
    questions = _stream_questions(workspace)
    workspace.close()

    assert rows == []
    assert {q["question"] for q in questions} == {"unselected_binding"}
    assert sorted(q["path"] for q in questions) == ["nameHelper", "orders"]


def test_a_module_that_does_not_declare_the_dependency_files_no_question(tmp_path: Path):
    """`record_service_identity_gaps` re-checks neither `requires` nor the
    dependency gate, which costs nothing for a `gaps` that re-walks the same facts
    `run` needed. This one reads `method_declarations` and `resolved_config`,
    which a SKIPPED catalog's module still has — so it published a question
    asserting a binding exists for a catalog the run explicitly declined.

    The skip message names the parent-POM case, which is exactly when
    configuration is present and the coordinate is not."""
    workspace = _workspace(
        tmp_path,
        [_bean("orders", "java.util.function.Consumer", "java/lang/String#")],
        _bindings(("spring.cloud.stream.default-binder", "rocketmq")),
        coordinates=("com.acme:something-else",),
    )
    skipped = derive_endpoints(workspace, [_stream_catalog()], capabilities=CAPABILITIES)
    questions = _stream_questions(workspace)
    workspace.close()

    assert skipped != [], "the catalog was not skipped, so this test measures nothing"
    assert questions == []


def test_a_composed_definition_under_an_unmapped_binder_derives_no_row(tmp_path: Path):
    """The degrade row took `catalog.protocol` unconditionally, bypassing the
    binder resolution entirely — so `definition: a|b` under an unmapped binder
    published `protocol: kafka`, a wire nobody read, on the very path §3.4 says
    removes the default *entirely*. Its `path` is NULL so it never linked by
    address, which is the only reason it was not the same defect as the row it
    sits beside."""
    workspace = _workspace(
        tmp_path,
        [_bean("orders", "java.util.function.Consumer", "java/lang/String#")],
        _bindings(
            ("spring.cloud.function.definition", "orders|payments"),
            ("spring.cloud.stream.default-binder", "rocketmq"),
        ),
        coordinates=(_STREAM_COORDINATE,),
    )
    derive_endpoints(workspace, [_stream_catalog()], capabilities=CAPABILITIES)
    rows = _rows(workspace)
    questions = _stream_questions(workspace)
    workspace.close()

    assert rows == []
    assert [q["question"] for q in questions] == ["binder_protocol"]


# --- job 1, the third address form: `indexed:` (spec 2026-09-21 §7b) ---------------


_ROUTES = "acme.edge.routes"
_EDGE_COORDINATE = "com.acme:acme-edge"


def _indexed(**overrides: object) -> dict:
    """The invented edge router's `indexed:` block — items under a list prefix, each
    with a predicate list read through the `shortcut` grammar and a target field —
    in the shape `spring-cloud-gateway-properties.yml` declares, with invented
    spellings for the reason every other block in this file is invented."""
    item: dict = {
        "predicates": {"field": "predicates", "grammar": "shortcut", "positional": "_pos_"},
        "path": {
            "name": "Path",
            "args": ["patterns", "matchTrailingSlash"],
            "gather": "list_tail_flag",
        },
        "method": {"name": "Method", "args": ["methods"], "gather": "list"},
        "requirements": {
            "Header": {"kind": "header", "args": ["header", "regexp"]},
            "Query": {"kind": "query", "args": ["param", "regexp", "predicate"]},
            "Cookie": {"kind": "cookie", "args": ["name", "regexp"]},
        },
        "pass_through": ["Host", "After", "Weight"],
        "peer": {"field": "uri", "direction": "outbound"},
    }
    item.update(overrides.pop("item", {}))  # type: ignore[arg-type]
    block: dict = {"prefix": _ROUTES, "item": item}
    block.update(overrides)
    return block


def _edge_catalog(matches: dict | None = None) -> Catalog:
    return Catalog(
        id="invented-edge",
        style="config_join",
        protocol="http",
        direction="inbound",
        requires=("resolved_config",),
        matches=matches if matches is not None else {"indexed": _indexed()},
        source=Path("tests/invented-edge.yml"),
        detect_coordinates=(_EDGE_COORDINATE,),
    )


def _route(index: int, *entries: tuple[str, str]) -> list[tuple[str, str, str | None]]:
    """One item's keys, agreed across two environments — `entries` are `(field, value)`
    pairs under `<prefix>[index].`, the field spelled as the config layer flattens it
    (`predicates[0]`, `predicates[1].name`, `predicates[1].args.patterns`, `uri`)."""
    return [
        (f"{_ROUTES}[{index}].{field}", environment, value)
        for field, value in entries
        for environment in ("default", "prod")
    ]


def _edge_rows(workspace: DuckDbWorkspace) -> list[tuple]:
    """Every row's identity columns, in one total order (`key=str`: a verb-less row sits
    beside verbed ones on the same path)."""
    return sorted(
        (
            (
                r["direction"],
                r["method"],
                r["path"],
                r["handler"],
                r["caller"],
                r["peer"],
                r["resolution"],
            )
            for r in _rows(workspace)
        ),
        key=str,
    )


def _edge_stash(workspace: DuckDbWorkspace) -> list[tuple]:
    return sorted(
        (
            (
                r["caller"],
                r["handler"],
                r["method"],
                r["path"],
                r["kind"],
                r["name"],
                r["value"],
                r["requirement"],
                r["resolution"],
            )
            for r in workspace.query("route_requirements")
        ),
        key=str,
    )


def _edge_questions(workspace: DuckDbWorkspace, catalog: Catalog) -> list[dict]:
    reset_open_questions(workspace)
    record_service_identity_gaps(workspace, [catalog])
    return workspace.query("open_questions")


def _edge_workspace(tmp_path: Path, config: list[tuple[str, str, str | None]]) -> DuckDbWorkspace:
    workspace = _workspace(tmp_path, [], config, coordinates=(_EDGE_COORDINATE,))
    # The pipeline creates the requirement stash before the engines run
    # (`derive_endpoints`); reaching `run` directly, the test does.
    workspace.derive("route_requirements_reset")
    return workspace


def test_a_shortcut_route_derives_one_inbound_row_per_verb_and_its_target(tmp_path: Path):
    """The whole form in one item: `Path=/orders/**`, `Method=GET,POST` and
    `uri: lb://orders` under `routes[0]` derive two inbound rows — one per verb, the
    pattern as the served path, no handler and no caller (a configured route dispatches
    to no method) — and one outbound row carrying the target VERBATIM with `peer` NULL,
    exactly as the DSL sibling publishes a `uri(…)`: a routing destination is kept whole,
    never split into a peer and an empty path. Every row `resolved`, `evidence:
    compiler`, this catalog's id."""
    workspace = _edge_workspace(
        tmp_path,
        _route(
            0,
            ("predicates[0]", "Path=/orders/**"),
            ("predicates[1]", "Method=GET,POST"),
            ("uri", "lb://orders"),
        ),
    )
    config_join.run(workspace, _edge_catalog())
    rows = _edge_rows(workspace)
    whole = _rows(workspace)
    workspace.close()

    assert rows == [
        ("inbound", "GET", "/orders/**", None, None, None, "resolved"),
        ("inbound", "POST", "/orders/**", None, None, None, "resolved"),
        ("outbound", None, "lb://orders", None, None, None, "resolved"),
    ]
    assert {(r["protocol"], r["evidence"], r["catalog_id"]) for r in whole} == {
        ("http", "compiler", "invented-edge")
    }


def test_a_route_with_no_method_predicate_is_one_verb_less_row(tmp_path: Path):
    """§0b A7: no `Method=` → `method` NULL, resolved — the DSL catalog's rendering of a
    method-less route, one family one rendering, never an `all_methods` fan-out. Two
    patterns → two rows; a trailing `true`/`false` on `Path` is the framework's
    `matchTrailingSlash` flag (CP-29 row 7, GATHER_LIST_TAIL_FLAG), not a pattern."""
    workspace = _edge_workspace(
        tmp_path,
        _route(
            0, ("predicates[0]", "Path=/a/**,/b/**,false"), ("uri", "http://items.internal:8080")
        ),
    )
    config_join.run(workspace, _edge_catalog())
    rows = _edge_rows(workspace)
    workspace.close()

    assert rows == [
        ("inbound", None, "/a/**", None, None, None, "resolved"),
        ("inbound", None, "/b/**", None, None, None, "resolved"),
        ("outbound", None, "http://items.internal:8080", None, None, None, "resolved"),
    ]


def test_the_map_form_reads_the_same_item(tmp_path: Path):
    """`predicates[M].name` + `predicates[M].args.<field>` is the same predicate the
    shortcut spells (CP-29 row 3: a `PredicateDefinition` is a name and an args map, and
    the shortcut fills the map with positional keys). A GATHERING predicate collects
    EVERY args value and tests no key (CP-29 row 7, `ShortcutType$2/$3.normalize` read
    `args.values()`): a positional `_pos_K` by K, then the remaining keys in flattened
    order — so `args.pattern: /items/**` (a key the framework's field order does not
    name) is one pattern, `args.patterns: [/a/**, /b/**]` (flattened to `patterns[0]`,
    `patterns[1]`) is two, and `args.methods: [GET, DELETE]` is two verbs. A map-form
    scalar is ONE value, never split on `,`: `methods: PUT,PATCH` is a verb string that
    is not one verb — the framework binds a method matching nothing — so `method` is
    NULL and the inbound row `unresolved`, never a phantom `PUT,PATCH` verb; the target
    row is untouched, its address was read."""
    workspace = _edge_workspace(
        tmp_path,
        _route(
            0,
            ("predicates[0].name", "Path"),
            ("predicates[0].args.pattern", "/items/**"),
            ("predicates[1].name", "Method"),
            ("predicates[1].args.methods[0]", "GET"),
            ("predicates[1].args.methods[1]", "DELETE"),
            ("uri", "lb://items"),
        )
        + _route(
            1,
            ("predicates[0].name", "Path"),
            ("predicates[0].args.patterns[0]", "/a/**"),
            ("predicates[0].args.patterns[1]", "/b/**"),
            ("predicates[1].name", "Method"),
            ("predicates[1].args._pos_0", "PUT"),
            ("uri", "lb://ab"),
        )
        + _route(
            2,
            ("predicates[0].name", "Path"),
            ("predicates[0].args._pos_0", "/x/**"),
            ("predicates[1].name", "Method"),
            ("predicates[1].args.methods", "PUT,PATCH"),
            ("uri", "lb://x"),
        ),
    )
    config_join.run(workspace, _edge_catalog())
    rows = _edge_rows(workspace)
    workspace.close()

    assert rows == sorted(
        [
            ("inbound", "GET", "/items/**", None, None, None, "resolved"),
            ("inbound", "DELETE", "/items/**", None, None, None, "resolved"),
            ("inbound", "PUT", "/a/**", None, None, None, "resolved"),
            ("inbound", "PUT", "/b/**", None, None, None, "resolved"),
            ("inbound", None, "/x/**", None, None, None, "unresolved"),
            ("outbound", None, "lb://items", None, None, None, "resolved"),
            ("outbound", None, "lb://ab", None, None, None, "resolved"),
            ("outbound", None, "lb://x", None, None, None, "resolved"),
        ],
        key=str,
    )


def test_the_tail_flag_is_found_by_value_and_two_or_a_misplaced_one_are_unread(
    tmp_path: Path,
):
    """Fix round 2. `resolved_config` carries no declaration order, and the round-1 read
    took the LAST gathered value (by key order) as the flag — so the documented map form
    `{patterns: /foo/**, matchTrailingSlash: false}` sorted to `[false, /foo/**]` and
    published a RESOLVED served path `/false`. The flag is found by VALUE now: the one
    `true`/`false` literal among the gathered values is the flag wherever it sits, and
    the rest are the patterns — the map form and the positional `Path=/foo/**,false`
    both derive one row `/foo/**`. Two boolean literals, or one in a gather with no tail
    flag (`Method=true`), are a binding nobody can settle: the inbound row is
    `unresolved` with `path` NULL, never a choice; the target row is untouched."""
    workspace = _edge_workspace(
        tmp_path,
        _route(
            0,
            ("predicates[0].name", "Path"),
            ("predicates[0].args.patterns", "/foo/**"),
            ("predicates[0].args.matchTrailingSlash", "false"),
            ("uri", "lb://foo"),
        )
        + _route(1, ("predicates[0]", "Path=/bar/**,false"), ("uri", "lb://bar"))
        + _route(
            2,
            ("predicates[0].name", "Path"),
            ("predicates[0].args.patterns", "/a/**"),
            ("predicates[0].args.matchTrailingSlash", "true"),
            ("predicates[0].args.extra", "false"),
            ("uri", "lb://two"),
        )
        + _route(
            3, ("predicates[0]", "Path=/m/**"), ("predicates[1]", "Method=true"), ("uri", "lb://m")
        ),
    )
    config_join.run(workspace, _edge_catalog())
    rows = _edge_rows(workspace)
    workspace.close()

    assert rows == sorted(
        [
            ("inbound", None, "/foo/**", None, None, None, "resolved"),
            ("inbound", None, "/bar/**", None, None, None, "resolved"),
            ("inbound", None, None, None, None, None, "unresolved"),
            ("inbound", None, "/m/**", None, None, None, "unresolved"),
            ("outbound", None, "lb://foo", None, None, None, "resolved"),
            ("outbound", None, "lb://bar", None, None, None, "resolved"),
            ("outbound", None, "lb://two", None, None, None, "resolved"),
            ("outbound", None, "lb://m", None, None, None, "resolved"),
        ],
        key=str,
    )


def test_a_path_predicate_left_with_no_pattern_after_its_flag_is_unread(tmp_path: Path):
    """Fix round 3. `Path=true` — or the map form `{matchTrailingSlash: true}` with no
    pattern — gathers nothing once the flag is taken, and the framework's factory over
    an empty pattern list matches nothing: the route is unreachable. That is NOT "no
    Path predicate at all", which serves every path (`/**`, resolved, unchanged here):
    a declared gather with an empty value list is unread — the inbound row `unresolved`
    with `path` NULL, the target row untouched."""
    workspace = _edge_workspace(
        tmp_path,
        _route(0, ("predicates[0]", "Path=true"), ("uri", "lb://flag"))
        + _route(
            1,
            ("predicates[0].name", "Path"),
            ("predicates[0].args.matchTrailingSlash", "true"),
            ("uri", "lb://map"),
        )
        + _route(2, ("predicates[0]", "Host=**.acme.com"), ("uri", "lb://host")),
    )
    config_join.run(workspace, _edge_catalog())
    rows = _edge_rows(workspace)
    workspace.close()

    assert rows == sorted(
        [
            ("inbound", None, None, None, None, None, "unresolved"),
            ("inbound", None, None, None, None, None, "unresolved"),
            ("inbound", None, "/**", None, None, None, "resolved"),
            ("outbound", None, "lb://flag", None, None, None, "resolved"),
            ("outbound", None, "lb://map", None, None, None, "resolved"),
            ("outbound", None, "lb://host", None, None, None, "resolved"),
        ],
        key=str,
    )


def test_a_row_with_no_address_carries_no_requirement(tmp_path: Path):
    """Fix round 2. A requirement on an address nobody read states nothing useful — and
    the requirements pass keys the stash on `path`, so two NULL-path items both carrying
    a `Header=` would have joined the LAST row it read. Two items whose `Path` no
    environment resolved, each with a header: two unresolved NULL-path rows, an empty
    stash."""
    a, b = f"{_ROUTES}[0].predicates[0]", f"{_ROUTES}[1].predicates[0]"
    workspace = _edge_workspace(
        tmp_path,
        [(a, "default", None), (a, "prod", None), (b, "default", None), (b, "prod", None)]
        + _route(0, ("predicates[1]", "Header=X-A,1"), ("uri", "lb://a"))
        + _route(1, ("predicates[1]", "Header=X-B,2"), ("uri", "lb://b")),
    )
    config_join.run(workspace, _edge_catalog())
    rows = _edge_rows(workspace)
    stash = _edge_stash(workspace)
    workspace.close()

    assert [r for r in rows if r[0] == "inbound"] == [
        ("inbound", None, None, None, None, None, "unresolved"),
        ("inbound", None, None, None, None, None, "unresolved"),
    ]
    assert stash == []


def test_two_items_on_one_address_intersect_their_requirements(tmp_path: Path):
    """Fix round 1; spec 2026-09-19 §4d, the combinator's `_shared` rule restated: two
    items collapsing to ONE address — header-versioned `/api/**`, `Header=X-Version,v1`
    and `Header=X-Version,v2` — are two ways the framework may dispatch it, and a request
    satisfying EITHER is served, so the row carries only what every alternative demands:
    here nothing (`X-Version=v1` AND `v2` both required would be a demand the framework
    never makes). The common `Query=tenant` survives. And an unresolved alternative
    makes the collapsed row unresolved — first-wins would have published `resolved` for
    an address one of its routes could not read."""
    workspace = _edge_workspace(
        tmp_path,
        _route(
            0,
            ("predicates[0]", "Path=/api/**"),
            ("predicates[1]", "Header=X-Version,v1"),
            ("predicates[2]", "Query=tenant"),
            ("uri", "lb://v1"),
        )
        + _route(
            1,
            ("predicates[0]", "Path=/api/**"),
            ("predicates[1]", "Header=X-Version,v2"),
            ("predicates[2]", "Query=tenant"),
            ("uri", "lb://v2"),
        )
        + _route(2, ("predicates[0]", "Path=/legacy/**"), ("uri", "lb://old"))
        + _route(
            3,
            ("predicates[0]", "Path=/legacy/**"),
            ("predicates[1]", "Version=1"),
            ("uri", "lb://older"),
        ),
    )
    config_join.run(workspace, _edge_catalog())
    rows = _edge_rows(workspace)
    stash = _edge_stash(workspace)
    workspace.close()

    assert [r for r in rows if r[0] == "inbound"] == [
        ("inbound", None, "/api/**", None, None, None, "resolved"),
        ("inbound", None, "/legacy/**", None, None, None, "unresolved"),
    ]
    assert stash == [(None, None, None, "/api/**", "query", "tenant", None, "required", "resolved")]


def test_a_key_resolved_in_no_environment_renders_unresolved_and_drops_nothing_else(
    tmp_path: Path,
):
    """Fix round 1: `_agreed`'s one None covered both "environments disagree" and
    "declared but unresolved everywhere", and the second is not divergence — `uri:
    ${ORDERS_URL}` with no environment answering is one route whose target nobody
    could read. So: the item's OTHER rows are minted, the unread field renders
    unresolved — an outbound row with `path` NULL — and no `environment_divergence`
    question is filed. A `Path` predicate unresolved everywhere is the inbound half of
    the same rule: the address is in doubt, so the item's inbound row is `unresolved`
    with `path` NULL (nothing here names an address; `/**` would assert one), and its
    target row is untouched."""
    uri = f"{_ROUTES}[0].uri"
    path_key = f"{_ROUTES}[1].predicates[0]"
    config = (
        _route(0, ("predicates[0]", "Path=/o/**"))
        + [(uri, "default", None), (uri, "prod", None)]
        + _route(1, ("uri", "lb://p"))
        + [(path_key, "default", None), (path_key, "prod", None)]
    )
    workspace = _edge_workspace(tmp_path, config)
    catalog = _edge_catalog()
    config_join.run(workspace, catalog)
    rows = _edge_rows(workspace)
    questions = _edge_questions(workspace, catalog)
    workspace.close()

    assert rows == sorted(
        [
            ("inbound", None, "/o/**", None, None, None, "resolved"),
            ("outbound", None, None, None, None, None, "unresolved"),
            ("inbound", None, None, None, None, None, "unresolved"),
            ("outbound", None, "lb://p", None, None, None, "resolved"),
        ],
        key=str,
    )
    assert questions == []


def test_header_query_and_cookie_predicates_are_the_rows_requirements(tmp_path: Path):
    """`Header=X-Api,v2`, `Query=debug` and `Cookie=session,.*` narrow WHO is served,
    never the address: each is one `route_requirements` row against EVERY inbound row
    of the item — `caller` and `handler` NULL (the join in `_from_stash` is `None ==
    None`), `required`, the regexp as written in `value` or NULL where none was
    written, `resolved`. The pass-throughs (`Host=…`) contribute nothing and poison
    nothing."""
    workspace = _edge_workspace(
        tmp_path,
        _route(
            0,
            ("predicates[0]", "Path=/g/**"),
            ("predicates[1]", "Method=GET,POST"),
            ("predicates[2]", "Header=X-Api,v2"),
            ("predicates[3]", "Query=debug"),
            ("predicates[4]", "Cookie=session,.*"),
            ("predicates[5]", "Host=**.acme.com"),
            ("uri", "lb://g"),
        ),
    )
    catalog = _edge_catalog()
    config_join.run(workspace, catalog)
    rows = _edge_rows(workspace)
    stash = _edge_stash(workspace)
    workspace.derive("endpoint_metadata_reset")
    from sextant.application.resolve.request_requirements import record_request_requirements

    record_request_requirements(workspace, [catalog])
    metadata = sorted(
        (r["method"], r["path"], r["caller"], r["kind"], r["name"], r["value"], r["requirement"])
        for r in workspace.query("endpoint_metadata")
    )
    workspace.close()

    assert [r[:3] for r in rows] == [
        ("inbound", "GET", "/g/**"),
        ("inbound", "POST", "/g/**"),
        ("outbound", None, "lb://g"),
    ]
    assert stash == sorted(
        (None, None, verb, "/g/**", kind, name, value, "required", "resolved")
        for verb in ("GET", "POST")
        for kind, name, value in (
            ("header", "X-Api", "v2"),
            ("query", "debug", None),
            ("cookie", "session", ".*"),
        )
    )
    assert metadata == sorted(
        (verb, "/g/**", None, kind, name, value, "required")
        for verb in ("GET", "POST")
        for kind, name, value in (
            ("header", "X-Api", "v2"),
            ("query", "debug", None),
            ("cookie", "session", ".*"),
        )
    )


def test_an_unknown_predicate_name_leaves_the_items_rows_unresolved(tmp_path: Path):
    """A name that is neither the path, the method, a requirement nor a pass-through —
    a predicate this catalog never measured — narrows the served set in a way nothing
    here can read (§8: never assert what the evidence does not support). The rows keep
    the address they read and say `unresolved`; a shortcut with no `=` (the framework
    refuses it) is the same answer. No row is dropped: the route is declared."""
    workspace = _edge_workspace(
        tmp_path,
        _route(
            0, ("predicates[0]", "Path=/v/**"), ("predicates[1]", "Version=1.0"), ("uri", "lb://v")
        )
        + _route(
            1, ("predicates[0]", "Path=/w/**"), ("predicates[1]", "Broken"), ("uri", "lb://w")
        ),
    )
    config_join.run(workspace, _edge_catalog())
    rows = _edge_rows(workspace)
    workspace.close()

    assert rows == [
        ("inbound", None, "/v/**", None, None, None, "unresolved"),
        ("inbound", None, "/w/**", None, None, None, "unresolved"),
        ("outbound", None, "lb://v", None, None, None, "unresolved"),
        ("outbound", None, "lb://w", None, None, None, "unresolved"),
    ]


def test_a_route_with_no_path_predicate_serves_every_path(tmp_path: Path):
    """The DSL sibling's rule (spec §7 case 3): a route whose predicates name no path — a
    host-only route — serves every path, `/**`."""
    workspace = _edge_workspace(
        tmp_path, _route(0, ("predicates[0]", "Host=**.acme.com"), ("uri", "lb://h"))
    )
    config_join.run(workspace, _edge_catalog())
    rows = _edge_rows(workspace)
    workspace.close()

    assert rows == [
        ("inbound", None, "/**", None, None, None, "resolved"),
        ("outbound", None, "lb://h", None, None, None, "resolved"),
    ]


def test_an_item_that_differs_between_environments_is_one_question_and_no_row(tmp_path: Path):
    """The existing `config_join` rule applied per item: every key the item is read
    from passes through `_agreed`, and one that environments answer differently — or
    that only one environment declares, since `resolved_config` carries a `missing_key`
    row for the other — is not one route. No row for that item (the other item is
    untouched), and one `environment_divergence` question from `gaps`, keyed on the
    item, with every disagreeing key and its per-environment values as candidates."""
    key = f"{_ROUTES}[0].uri"
    config = (
        _route(0, ("predicates[0]", "Path=/d/**"))
        + [
            (key, "default", "lb://d-dev"),
            (key, "prod", "lb://d-prod"),
        ]
        + _route(1, ("predicates[0]", "Path=/s/**"), ("uri", "lb://s"))
    )
    workspace = _edge_workspace(tmp_path, config)
    catalog = _edge_catalog()
    config_join.run(workspace, catalog)
    rows = _edge_rows(workspace)
    questions = _edge_questions(workspace, catalog)
    workspace.close()

    assert rows == [
        ("inbound", None, "/s/**", None, None, None, "resolved"),
        ("outbound", None, "lb://s", None, None, None, "resolved"),
    ]
    assert [(q["question"], q["protocol"], q["method"], q["path"]) for q in questions] == [
        ("environment_divergence", "http", None, f"{_ROUTES}[0]")
    ]
    assert json.loads(questions[0]["candidates"]) == [
        {"key": key, "values": {"default": "lb://d-dev", "prod": "lb://d-prod"}}
    ]
    assert key in questions[0]["evidence"]


@pytest.mark.declines("spring-cloud-gateway-properties")
@pytest.mark.pins("config_join.indexed-item-exists-through-its-read-fields")
def test_keys_outside_the_prefix_and_unread_fields_derive_nothing(tmp_path: Path):
    """The near-miss: a sibling prefix (`acme.edge.routes-extra[0]…`), a scalar at the
    prefix itself, and an item whose only keys are `filters[…]`/`id`/`order` are not
    routes. The third is the guard this pins: an item exists only through the fields
    the block READS, so an entry with none of them is no item — without that it would
    be an item with no predicates and mint a resolved `/**` row for a route declaring
    no address and no target. The shipped catalog reads the same block, so its decline
    is this one."""
    workspace = _edge_workspace(
        tmp_path,
        [
            (f"{_ROUTES}-extra[0].predicates[0]", "default", "Path=/no/**"),
            (f"{_ROUTES}-extra[0].uri", "default", "lb://no"),
            (_ROUTES, "default", "nothing"),
            (f"{_ROUTES}[0].id", "default", "only-an-id"),
            (f"{_ROUTES}[0].filters[0]", "default", "StripPrefix=1"),
            (f"{_ROUTES}[0].order", "default", "1"),
        ],
    )
    config_join.run(workspace, _edge_catalog())
    rows = _edge_rows(workspace)
    workspace.close()

    assert rows == []


@pytest.mark.parametrize(
    ("item", "message"),
    [
        (
            {"predicates": {"field": "predicates", "grammar": "csv", "positional": "_pos_"}},
            "grammar",
        ),
        ({"path": {"name": "Path", "args": ["patterns"], "gather": "set"}}, "gather"),
        ({"requirements": {"Header": {"kind": "form", "args": ["header"]}}}, "kind"),
        ({"peer": {"field": "uri", "direction": "sideways"}}, "direction"),
        ({"pass_through": "Host"}, "pass_through"),
    ],
    ids=["grammar", "gather", "kind", "direction", "pass_through"],
)
def test_an_indexed_block_of_the_wrong_shape_is_refused_at_load(
    tmp_path: Path, item: dict, message: str
):
    """Every value of the block reaches a row's identity or the stash: an unknown grammar
    or gather word, a requirement kind outside the closed four, a direction outside
    D00's set, a pass-through list that is not a list — refused at load, naming the
    field."""
    with pytest.raises(CatalogError, match=message):
        config_join.run(
            _edge_workspace(tmp_path, []), _edge_catalog({"indexed": _indexed(item=item)})
        )


def test_the_shipped_edge_catalog_derives_property_routes_through_derive_endpoints(tmp_path: Path):
    """The shipped `spring-cloud-gateway-properties.yml` through `derive_endpoints` — the
    dependency gate (its `detect.coordinates`), the `derives_rows` ordering, the stash
    reset — on the two routes `fixtures/orders-gateway`'s `application.yml` declares,
    spelled here as `resolved_config` rows."""
    catalog = next(
        c
        for c in YamlCatalogSource(CATALOGS_DIR).load()
        if c.id == "spring-cloud-gateway-properties"
    )
    prefix = "spring.cloud.gateway.server.webflux.routes"
    workspace = _workspace(
        tmp_path,
        [],
        [
            (f"{prefix}[0].id", "default", "cfg-orders"),
            (f"{prefix}[0].uri", "default", "lb://orders"),
            (f"{prefix}[0].predicates[0]", "default", "Path=/cfg/orders/**"),
            (f"{prefix}[0].predicates[1]", "default", "Method=GET,POST"),
            (f"{prefix}[0].predicates[2]", "default", "Header=X-Api,v2"),
            (f"{prefix}[1].id", "default", "cfg-items"),
            (f"{prefix}[1].uri", "default", "http://items.internal:8080"),
            (f"{prefix}[1].predicates[0].name", "default", "Path"),
            (f"{prefix}[1].predicates[0].args.patterns", "default", "/cfg/items/**"),
        ],
        coordinates=("org.springframework.cloud:spring-cloud-gateway-server-webflux",),
    )
    skipped = derive_endpoints(workspace, [catalog], capabilities={"resolved_config"})
    rows = _edge_rows(workspace)
    stash = _edge_stash(workspace)
    workspace.close()

    assert skipped == []
    # **`/cfg/items/**` declares no `Method=` and is now one row per method; the
    # `/cfg/orders/**` route declares `Method=GET,POST` and stays two.** That contrast IS
    # the user's ruling of 2026-10-17 — fan out, but only to methods that are supported —
    # and it is why the fan-out keys on `matches.all_methods` rather than on "the verb is
    # NULL": a declared pair is not widened, and the four outbound forward targets are not
    # fanned either, since eight rows naming one destination say one thing eight times.
    # Sorted with `_edge_rows`' own `key=str` rather than hand-ordered: ten rows in a
    # total order no reader can verify by eye is a pin that passes for the wrong reason.
    assert rows == sorted(
        [
            ("inbound", "GET", "/cfg/orders/**", None, None, None, "resolved"),
            ("inbound", "POST", "/cfg/orders/**", None, None, None, "resolved"),
            *(
                ("inbound", verb, "/cfg/items/**", None, None, None, "resolved")
                for verb in ("GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "TRACE")
            ),
            ("outbound", None, "http://items.internal:8080", None, None, None, "resolved"),
            ("outbound", None, "lb://orders", None, None, None, "resolved"),
        ],
        key=str,
    )
    assert stash == [
        (None, None, "GET", "/cfg/orders/**", "header", "X-Api", "v2", "required", "resolved"),
        (None, None, "POST", "/cfg/orders/**", "header", "X-Api", "v2", "required", "resolved"),
    ]


# --- SmallRye Reactive Messaging: channels wired as Quarkus wires them -------
#
# Spec 2026-10-24 §3a/§3c, rulings 1-2, against the SHIPPED
# `smallrye-reactive-messaging.yml`: every value these tests turn on — the connector
# names, the protocol each speaks, the destination attribute per direction, the two key
# spellings, the orphan rule — is that file's, cited there to CP-49/50/51. Each test
# runs the real passes in order: configuration (`resolve_config`, through the shipped
# `spring-web` model, so a `${…}` is substituted by `config.substitute` exactly as in a
# real resolve), then `derive_endpoints` (the dependency gate included), then the
# `service_identity` seam that files the questions.

_SMALLRYE_ID = "smallrye-reactive-messaging"
_QUOTES = "com/acme/quotes/QuoteProcessor#"
_RESOURCE = "com/acme/quotes/QuoteResource#"
_MP = "org/eclipse/microprofile/reactive/messaging/"
_INCOMING = _MP + "Incoming#"
_OUTGOING = _MP + "Outgoing#"
_INCOMINGS = "io/smallrye/reactive/messaging/annotations/Incomings#"
_CHANNEL = _MP + "Channel#"
_EMITTER = _MP + "Emitter#"
_MULTI = "io/smallrye/mutiny/Multi#"
_KAFKA_EXTENSION = "io.quarkus:quarkus-messaging-kafka"
_AMQP_EXTENSION = "io.quarkus:quarkus-messaging-amqp"
_RABBIT_EXTENSION = "io.quarkus:quarkus-messaging-rabbitmq"
_MESSAGING_CAPABILITIES = {
    "resolved_config",
    "annotation_args",
    "nested_annotation_args",
    "typed_signatures",
}


def _shipped(catalog_id: str) -> Catalog:
    return next(c for c in YamlCatalogSource(CATALOGS_DIR).load() if c.id == catalog_id)


def _quote_method(name: str) -> str:
    return f"{_MODULE}{_QUOTES}{name}(sig_{name})."


def _channel_method(name: str, *uses: AnnotationUse) -> list[SymbolFact | AnnotationFact]:
    """`QuoteProcessor#<name>()` carrying `uses`, each an annotation on the METHOD."""
    symbol = _quote_method(name)
    return [
        SymbolFact(
            document_id="doc_1",
            symbol=symbol,
            construct_kind=ConstructKind.METHOD,
            enclosing=_MODULE + _QUOTES,
            signature=Signature(parameters=[], returns=TypeRef(symbol="void#")),
        ),
        *(
            AnnotationFact(document_id="doc_1", target=symbol, use=use, retention="RUNTIME")
            for use in uses
        ),
    ]


def _incoming(channel: str) -> AnnotationUse:
    return AnnotationUse(annotation=_INCOMING, args={"value": channel})


def _outgoing(channel: str) -> AnnotationUse:
    return AnnotationUse(annotation=_OUTGOING, args={"value": channel})


def _injected_field(name: str, field_type: str, channel: str) -> list[SymbolFact | AnnotationFact]:
    """`@Inject @Channel("<channel>") <field_type><String> <name>;` on `QuoteResource`."""
    symbol = f"{_MODULE}{_RESOURCE}{name}."
    return [
        SymbolFact(
            document_id="doc_1",
            symbol=symbol,
            construct_kind=ConstructKind.FIELD,
            enclosing=_MODULE + _RESOURCE,
            signature=Signature(
                returns=TypeRef(symbol=field_type, arguments=[_payload("java/lang/String#")])
            ),
        ),
        AnnotationFact(
            document_id="doc_1",
            target=symbol,
            use=AnnotationUse(annotation=_CHANNEL, args={"value": channel}),
            retention="RUNTIME",
        ),
    ]


def _messaging(
    tmp_path: Path,
    facts: list[SymbolFact | AnnotationFact],
    properties: dict[str, str] | None = None,
    coordinates: tuple[str, ...] = (_KAFKA_EXTENSION,),
    *,
    gated: bool = False,
) -> DuckDbWorkspace:
    """The module through configuration, the endpoint loop and the questions seam.

    `properties` is `application.properties`, read by the shipped Spring config model —
    the only `config_model` that ships, and the one a Quarkus module's file is resolved
    through in a real run. `coordinates` is the module's dependency set: the classpath
    the connector table is checked against. The catalog must RUN unless `gated` says the
    dependency gate is what the test is about — a skipped catalog derives nothing, and a
    test asserting nothing was derived would otherwise pass for that reason alone."""
    root = tmp_path / "facts"
    write_fact_file(root / "Quotes.jsonl", _document(), list(facts))
    write_fact_file(
        root / "module.jsonl",
        _module_document(),
        [
            ModuleFact(
                document_id="doc_module",
                module_id="com.acme:orders-service",
                module_kind="service",
                languages=["java"],
                source_roots=["src/main/java"],
                output_dirs=["target/classes"],
                dependency_coordinates=list(coordinates),
            )
        ],
    )
    if properties:
        document = _document().model_copy(
            update={
                "document_id": "application.properties",
                "relative_path": "application.properties",
                "language": "properties",
                "scanner_id": "sextant-config-reader",
                "origin_entry": "src/main/resources",
            }
        )
        write_fact_file(
            root / "application.properties.jsonl",
            document,
            [
                ConfigEntryFact(
                    document_id="application.properties", key_raw=key, key_path=key, value=value
                )
                for key, value in properties.items()
            ],
        )
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(root)
    smallrye = _shipped(_SMALLRYE_ID)
    resolve_config(workspace, [_shipped("spring-web"), smallrye])
    skipped = derive_endpoints(workspace, [smallrye], capabilities=_MESSAGING_CAPABILITIES)
    assert [entry.catalog_id for entry in skipped] == ([_SMALLRYE_ID] if gated else [])
    reset_open_questions(workspace)
    record_service_identity_gaps(workspace, [smallrye])
    return workspace


def _messaging_rows(workspace: DuckDbWorkspace) -> list[tuple[object, ...]]:
    return sorted(
        (
            (r["protocol"], r["direction"], r["path"], r["handler"] or r["caller"], r["resolution"])
            for r in workspace.query("endpoints")
        ),
        key=str,
    )


def _messaging_questions(workspace: DuckDbWorkspace) -> list[dict]:
    return [
        {**row, "candidates": json.loads(str(row["candidates"]))}
        for row in workspace.query("open_questions")
    ]


@pytest.mark.pins("messaging.an-ORPHAN-channel-takes-the-sole-connector")
def test_the_kafka_quickstart_processor_takes_the_one_connector_on_the_classpath(
    tmp_path: Path,
):
    """Review focus 1, the quickstart's processor exactly: `@Incoming("requests")
    @Outgoing("quotes")`, `quarkus-messaging-kafka` the only connector on the classpath and
    no `mp.messaging.*` key at all. Both names are orphans — each is carried by one
    direction only (CP-50 row 1) — and Quarkus attaches the one connector of each
    direction to them (row 7), whose destination defaults to the channel name (CP-51
    rows 4-5). So two Kafka rows, each at its channel's name, and nothing to ask."""
    workspace = _messaging(
        tmp_path, _channel_method("process", _incoming("requests"), _outgoing("quotes"))
    )
    rows = _messaging_rows(workspace)
    questions = _messaging_questions(workspace)
    workspace.close()

    assert rows == [
        ("kafka", "inbound", "requests", _quote_method("process"), "resolved"),
        ("kafka", "outbound", "quotes", _quote_method("process"), "resolved"),
    ]
    assert questions == []


def test_an_emitter_on_a_channel_is_an_outbound_row_naming_the_field(tmp_path: Path):
    """`@Channel` on an injected `Emitter` is OUTGOING (CP-49 rows 21, 26 — the type is one
    an `@EmitterFactoryFor` names, row 14), and the field it sits on is the row's caller,
    as spec §3c's `QuoteResource.emitter (Emitter)`."""
    workspace = _messaging(tmp_path, _injected_field("emitter", _EMITTER, "quote-requests"))
    rows = _messaging_rows(workspace)
    workspace.close()

    assert rows == [
        ("kafka", "outbound", "quote-requests", f"{_MODULE}{_RESOURCE}emitter.", "resolved")
    ]


def test_a_stream_on_a_channel_is_an_inbound_row(tmp_path: Path):
    """Any other injected type — a `Multi` — makes `@Channel` INCOMING (CP-49 rows 21, 26:
    `handleChannelInjection` → `produceIncomingChannel`)."""
    workspace = _messaging(tmp_path, _injected_field("prices", _MULTI, "prices"))
    rows = _messaging_rows(workspace)
    workspace.close()

    assert rows == [("kafka", "inbound", "prices", f"{_MODULE}{_RESOURCE}prices.", "resolved")]


def test_a_channel_injected_through_a_constructor_parameter_is_read_too(tmp_path: Path):
    """`@Channel`'s `@Target` includes PARAMETER (CP-49 rows 3, 7), and a constructor
    parameter is an injection point exactly as a field is. The parameter's annotations
    live inside its declaration's signature, never as an `annotation` fact, so this is a
    second read; the constructor is the row's caller."""
    constructor = f"{_MODULE}{_RESOURCE}`<init>`(sig_init)."
    parameter = Parameter(
        name="emitter",
        type=TypeRef(symbol=_EMITTER, arguments=[_payload("java/lang/String#")]),
        erased_symbol=_EMITTER,
        annotations=[AnnotationUse(annotation=_CHANNEL, args={"value": "quote-requests"})],
    )
    workspace = _messaging(
        tmp_path,
        [
            SymbolFact(
                document_id="doc_1",
                symbol=constructor,
                construct_kind=ConstructKind.CONSTRUCTOR,
                enclosing=_MODULE + _RESOURCE,
                signature=Signature(parameters=[parameter], returns=TypeRef(symbol="void#")),
            )
        ],
    )
    rows = _messaging_rows(workspace)
    workspace.close()

    assert rows == [("kafka", "outbound", "quote-requests", constructor, "resolved")]


@pytest.mark.declines("smallrye-reactive-messaging")
@pytest.mark.pins("messaging.an-IN-MEMORY-channel-is-no-boundary")
def test_an_in_memory_pair_is_no_boundary_even_beside_a_connector(tmp_path: Path):
    """Review focus 2. A name one method produces and another consumes is carried by both
    directions, so `detectOrphanChannels`' `removeAll` takes it out of both (CP-50 rows 1,
    11): it is never an orphan, nothing attaches to it, and it is an in-process pipe. No
    row and no question — even with the Kafka connector on the classpath, which would
    otherwise wire each half."""
    workspace = _messaging(
        tmp_path,
        [
            *_channel_method("produce", _outgoing("in-memory")),
            *_channel_method("consume", _incoming("in-memory")),
        ],
    )
    rows = _messaging_rows(workspace)
    questions = _messaging_questions(workspace)
    workspace.close()

    assert rows == []
    assert questions == []


def test_a_configured_topic_is_the_destination(tmp_path: Path):
    workspace = _messaging(
        tmp_path,
        _channel_method("process", _incoming("requests")),
        {"mp.messaging.incoming.requests.topic": "quote-requests-v2"},
    )
    rows = _messaging_rows(workspace)
    workspace.close()

    assert rows == [("kafka", "inbound", "quote-requests-v2", _quote_method("process"), "resolved")]


def test_a_placeholder_topic_resolves_through_the_one_placeholder_rule(tmp_path: Path):
    """Review focus 4. `${REQ_TOPIC:requests}` is substituted by `resolve_config`
    (`config.substitute`): its default where nothing sets `REQ_TOPIC`, and the set value
    where something does — the destination is configuration's answer, never the
    expression and never a second substitution here."""
    unset = _messaging(
        tmp_path / "unset",
        _channel_method("process", _incoming("requests")),
        {"mp.messaging.incoming.requests.topic": "${REQ_TOPIC:requests}"},
    )
    unset_rows = _messaging_rows(unset)
    unset.close()
    set_ = _messaging(
        tmp_path / "set",
        _channel_method("process", _incoming("requests")),
        {
            "mp.messaging.incoming.requests.topic": "${REQ_TOPIC:requests}",
            "REQ_TOPIC": "live-requests",
        },
    )
    set_rows = _messaging_rows(set_)
    set_.close()

    assert unset_rows == [("kafka", "inbound", "requests", _quote_method("process"), "resolved")]
    assert set_rows == [("kafka", "inbound", "live-requests", _quote_method("process"), "resolved")]


def test_the_quarkus_spelling_of_a_key_is_read_as_the_mp_one(tmp_path: Path):
    """CP-50 row 19: at 3.40.1.1 `quarkus.messaging.<dir>.<channel>.<attr>` and
    `mp.messaging.…` name the same attribute, so either spelling configures the channel —
    and where both give ONE value, that value."""
    quarkus = _messaging(
        tmp_path / "quarkus",
        _channel_method("process", _incoming("requests")),
        {"quarkus.messaging.incoming.requests.topic": "spelled-quarkus"},
    )
    quarkus_rows = _messaging_rows(quarkus)
    quarkus.close()
    both = _messaging(
        tmp_path / "both",
        _channel_method("process", _incoming("requests")),
        {
            "quarkus.messaging.incoming.requests.topic": "agreed",
            "mp.messaging.incoming.requests.topic": "agreed",
        },
    )
    both_rows = _messaging_rows(both)
    both.close()

    assert quarkus_rows == [
        ("kafka", "inbound", "spelled-quarkus", _quote_method("process"), "resolved")
    ]
    assert both_rows == [("kafka", "inbound", "agreed", _quote_method("process"), "resolved")]


def test_two_spellings_disagreeing_leave_the_destination_unread_naming_both_keys(
    tmp_path: Path,
):
    """Which spelling wins when both are set is `smallrye-config`'s precedence, which
    CP-50 did not measure (its NOT-measured list). So the row is `unresolved`, its `path`
    unread, and the question says why in words naming BOTH keys — in the candidate,
    because the candidate is what the rendered document prints."""
    workspace = _messaging(
        tmp_path,
        _channel_method("process", _incoming("requests")),
        {
            "mp.messaging.incoming.requests.topic": "one",
            "quarkus.messaging.incoming.requests.topic": "two",
        },
    )
    rows = _messaging_rows(workspace)
    [question] = _messaging_questions(workspace)
    workspace.close()

    assert rows == [("kafka", "inbound", None, _quote_method("process"), "unresolved")]
    assert (question["protocol"], question["path"], question["question"]) == (
        "kafka",
        "requests",
        "channel_destination",
    )
    [candidate] = question["candidates"]
    assert candidate["channel"] == "requests"
    assert "mp.messaging.incoming.requests.topic" in candidate["reason"]
    assert "quarkus.messaging.incoming.requests.topic" in candidate["reason"]


def test_two_connectors_and_none_configured_ask_which_naming_both(tmp_path: Path):
    """Ruling 2: with two connectors of a direction on the classpath Quarkus attaches
    neither (CP-50 row 7, `Set.size() == 1`), so the wire is unread — no row, which
    would name a protocol nobody chose, and a `binder_protocol` question carrying each
    connector."""
    workspace = _messaging(
        tmp_path,
        _channel_method("process", _incoming("requests")),
        coordinates=(_KAFKA_EXTENSION, _AMQP_EXTENSION),
    )
    rows = _messaging_rows(workspace)
    [question] = _messaging_questions(workspace)
    workspace.close()

    assert rows == []
    assert (question["protocol"], question["path"], question["question"]) == (
        None,
        "requests",
        "binder_protocol",
    )
    assert sorted(c["binder"] for c in question["candidates"]) == [
        "smallrye-amqp",
        "smallrye-kafka",
    ]
    assert all(c["binding"] == "requests" for c in question["candidates"])


def test_a_configured_connector_the_table_does_not_know_asks_naming_it(tmp_path: Path):
    """Ruling 1: a connector with no entry in the table — MQTT has no Protocol member
    (spec §4) — leaves the wire unread. Named, never defaulted to the catalog's own
    `protocol:`, never silent."""
    workspace = _messaging(
        tmp_path,
        _channel_method("process", _incoming("prices")),
        {"mp.messaging.incoming.prices.connector": "smallrye-mqtt"},
    )
    rows = _messaging_rows(workspace)
    [question] = _messaging_questions(workspace)
    workspace.close()

    assert rows == []
    assert question["question"] == "binder_protocol"
    assert [(c["binding"], c["binder"]) for c in question["candidates"]] == [
        ("prices", "smallrye-mqtt")
    ]


@pytest.mark.pins("messaging.the-CONNECTOR-table-names-the-protocol")
def test_a_configured_connector_wins_over_the_sole_connector_on_the_classpath(
    tmp_path: Path,
):
    """Review focus 3. A channel whose connector key is set is connector-managed, and a
    connector-managed channel is never an orphan (CP-50 rows 1, 8), so the sole Kafka
    connector is NOT attached to it: the row is `amqp`, the configured connector's own
    protocol, at its `address` default — the channel name (CP-51 rows 9-10).

    What the framework does with exactly this module is a BUILD FAILURE: CP-50 row 8
    matches the configured name against the connector beans and throws "configured with
    an unknown connector" when none answers. So no module that was built is in this
    state; a classpath lacking the configured connector is this analysis's reading of
    the dependency set falling short (a declared-only set, a coordinate the table does
    not list), and the configured connector is what the running application wires."""
    workspace = _messaging(
        tmp_path,
        _channel_method("process", _incoming("requests")),
        {"mp.messaging.incoming.requests.connector": "smallrye-amqp"},
    )
    rows = _messaging_rows(workspace)
    workspace.close()

    assert rows == [("amqp", "inbound", "requests", _quote_method("process"), "resolved")]


@pytest.mark.pins("messaging.the-CONNECTOR-table-names-the-protocol")
def test_rabbitmq_publishes_to_an_exchange_and_consumes_from_a_queue(tmp_path: Path):
    """CP-51 rows 14-15: RabbitMQ's outgoing destination is `exchange.name`, its incoming
    one `queue.name` — an incoming `exchange.name` is the exchange the queue is bound to,
    not where the message is read from. Each defaults to the channel name."""
    workspace = _messaging(
        tmp_path,
        [
            *_channel_method("publish", _outgoing("prices-out")),
            *_channel_method("consume", _incoming("prices-in")),
            *_channel_method("defaults", _incoming("unset-in"), _outgoing("unset-out")),
        ],
        {
            "mp.messaging.outgoing.prices-out.exchange.name": "prices-exchange",
            "mp.messaging.outgoing.prices-out.queue.name": "not-an-outgoing-destination",
            "mp.messaging.incoming.prices-in.exchange.name": "prices-exchange",
            "mp.messaging.incoming.prices-in.queue.name": "prices-queue",
        },
        coordinates=(_RABBIT_EXTENSION,),
    )
    rows = _messaging_rows(workspace)
    workspace.close()

    assert rows == sorted(
        [
            ("amqp", "outbound", "prices-exchange", _quote_method("publish"), "resolved"),
            ("amqp", "inbound", "prices-queue", _quote_method("consume"), "resolved"),
            ("amqp", "inbound", "unset-in", _quote_method("defaults"), "resolved"),
            ("amqp", "outbound", "unset-out", _quote_method("defaults"), "resolved"),
        ],
        key=str,
    )


def test_an_incomings_container_is_one_row_per_nested_incoming(tmp_path: Path):
    """Two `@Incoming`s on one method reach the class file as ONE `@Incomings` whose
    `value` holds both (CP-49 rows 5, 9 — the SmallRye copies are `@Repeatable`), and
    Quarkus reads the container (rows 19-20). Reading only `@Incoming` would lose both."""
    container = AnnotationUse(
        annotation=_INCOMINGS,
        args={"value": [_incoming("orders"), _incoming("refunds")]},
    )
    workspace = _messaging(tmp_path, _channel_method("consume", container))
    rows = _messaging_rows(workspace)
    workspace.close()

    assert rows == [
        ("kafka", "inbound", "orders", _quote_method("consume"), "resolved"),
        ("kafka", "inbound", "refunds", _quote_method("consume"), "resolved"),
    ]


def test_a_kafka_topics_list_leaves_the_incoming_destination_unread(tmp_path: Path):
    """CP-51's attribute table: an incoming Kafka channel may name its topics as a LIST
    (`topics`) or as a regex (`pattern=true`). This table reads `topic` alone, so either
    one configured leaves the destination unread — a row at the channel name would name
    a topic the consumer does not read."""
    workspace = _messaging(
        tmp_path,
        [
            *_channel_method("listed", _incoming("listed")),
            *_channel_method("patterned", _incoming("patterned")),
        ],
        {
            "mp.messaging.incoming.listed.topics": "a,b",
            "mp.messaging.incoming.patterned.topic": "orders-.*",
            "mp.messaging.incoming.patterned.pattern": "true",
        },
    )
    rows = _messaging_rows(workspace)
    questions = _messaging_questions(workspace)
    workspace.close()

    assert rows == [
        ("kafka", "inbound", None, _quote_method("listed"), "unresolved"),
        ("kafka", "inbound", None, _quote_method("patterned"), "unresolved"),
    ]
    assert sorted(q["path"] for q in questions) == ["listed", "patterned"]
    assert {q["question"] for q in questions} == {"channel_destination"}


def test_a_disabled_connector_channel_produces_no_channel_at_all(tmp_path: Path):
    """CP-50 rows 3-4: a connector-configured channel whose `enabled` is `false` produces
    no channel item — no row, and it does not stand in the orphan maps either."""
    workspace = _messaging(
        tmp_path,
        _channel_method("process", _incoming("requests")),
        {
            "mp.messaging.incoming.requests.connector": "smallrye-kafka",
            "mp.messaging.incoming.requests.enabled": "false",
        },
    )
    rows = _messaging_rows(workspace)
    questions = _messaging_questions(workspace)
    workspace.close()

    assert rows == []
    assert questions == []


def test_attachment_switched_off_wires_no_orphan(tmp_path: Path):
    """CP-50 rows 7, 10: the attachment sits behind
    `quarkus.messaging.auto-connector-attachment` (default `true`). Off, an orphan takes
    no connector, and only a configured one is a boundary."""
    workspace = _messaging(
        tmp_path,
        [
            *_channel_method("orphan", _incoming("orphan")),
            *_channel_method("configured", _incoming("configured")),
        ],
        {
            "quarkus.messaging.auto-connector-attachment": "false",
            "mp.messaging.incoming.configured.connector": "smallrye-kafka",
        },
    )
    rows = _messaging_rows(workspace)
    workspace.close()

    assert rows == [("kafka", "inbound", "configured", _quote_method("configured"), "resolved")]


def test_a_dotted_channel_name_is_quoted_in_its_key(tmp_path: Path):
    """CP-50 rows 5, 15: a channel name containing `.` is written into the key quoted."""
    workspace = _messaging(
        tmp_path,
        _channel_method("process", _incoming("quotes.v2")),
        {'mp.messaging.incoming."quotes.v2".topic': "quotes-v2"},
    )
    rows = _messaging_rows(workspace)
    workspace.close()

    assert rows == [("kafka", "inbound", "quotes-v2", _quote_method("process"), "resolved")]


@pytest.mark.declines("smallrye-reactive-messaging")
@pytest.mark.pins("messaging.wired-questions-ride-the-dependency-gate")
def test_a_module_whose_build_names_no_messaging_artifact_derives_and_asks_nothing(
    tmp_path: Path,
):
    """The dependency gate (`config_join` is gated, `resolve/dependencies.py`) — and the
    questions seam re-checks no gate, so the catalog's `gaps` must: a module with the
    annotations and no SmallRye on its build files no question either."""
    workspace = _messaging(
        tmp_path,
        _channel_method("process", _incoming("prices")),
        {"mp.messaging.incoming.prices.connector": "smallrye-mqtt"},
        coordinates=("io.quarkus:quarkus-rest",),
        gated=True,
    )
    rows = _messaging_rows(workspace)
    questions = _messaging_questions(workspace)
    workspace.close()

    assert rows == []
    assert questions == []


def _rewired(edit: object) -> Catalog:
    """The shipped SmallRye catalog with `edit(address)` applied to a deep copy of its
    `address_from_config` block."""
    catalog = _shipped(_SMALLRYE_ID)
    matches = copy.deepcopy(dict(catalog.matches))
    edit(matches["address_from_config"])  # type: ignore[operator]
    return dataclasses.replace(catalog, matches=matches)


def _first_connector(address: dict) -> dict:
    return address["wiring"]["connectors"][0]


@pytest.mark.parametrize(
    ("edit", "expected"),
    [
        (
            lambda a: a.update(key="mp.messaging.incoming.{binding}.topic"),
            "both `key` and `wiring`",
        ),
        (lambda a: a["wiring"].update(keys={}), "keys must map a direction"),
        (
            lambda a: a["wiring"]["keys"].update(inbound=["mp.messaging.incoming.{binding}"]),
            "carrying `{binding}` and `{attribute}`",
        ),
        (lambda a: a["wiring"]["keys"].pop("outbound"), "declares no templates for outbound"),
        (lambda a: a["wiring"]["keys"].update(sideways=["{binding}.{attribute}"]), "closed"),
        (lambda a: a["wiring"].pop("connector_attribute"), "connector_attribute must name"),
        (lambda a: a["wiring"].update(connector_names="loosely"), "is not one of exact"),
        (lambda a: a["wiring"].update(quote={"containing": "."}), "quote must be"),
        (lambda a: a["wiring"].update(disabled_when={"attribute": "enabled"}), "disabled_when"),
        (lambda a: a["wiring"]["orphans"].update(attach="every_connector"), "is not one of"),
        (lambda a: a["wiring"]["orphans"].update(unless={"key": "x"}), "orphans.unless"),
        (lambda a: a["wiring"].update(connectors=[]), "connectors must be a non-empty list"),
        (lambda a: _first_connector(a).update(protocol="mqtt"), "closed sets are closed"),
        (lambda a: _first_connector(a).update(coordinates=[]), "entries must be"),
        (lambda a: _first_connector(a).update(destination={}), "entries must be"),
        (lambda a: _first_connector(a).pop("default"), "entries must be"),
        (
            lambda a: _first_connector(a).update(destination={"both": "topic"}),
            "for which `keys` declares no templates",
        ),
        (
            lambda a: _first_connector(a).update(unread_when={"inbound": [{"value": "x"}]}),
            "unread_when.inbound must be a list",
        ),
        (
            lambda a: a["wiring"]["connectors"].append(
                {**_first_connector(a), "name": "SmallRye-Kafka"}
            ),
            "names `SmallRye-Kafka` twice",
        ),
        (
            lambda a: a["binding"]["channels"][0].update(
                annotation=[
                    "org.eclipse.microprofile.reactive.messaging.Incoming",
                    "io.smallrye.reactive.messaging.annotations.Incoming",
                ]
            ),
            "ONE container type beside ONE annotation",
        ),
        (lambda a: a["binding"].update(injected={"annotation": "x"}), "must be a list of rules"),
        (lambda a: a["binding"]["injected"][0].pop("arg"), "entries must be"),
        (
            lambda a: a["binding"]["injected"][0].update(direction_by_type={"upward": ["a.B"]}),
            "closed sets are closed",
        ),
        (
            lambda a: a["binding"].update(**{"from": "bean_name", "suffix": _suffix_rules()}),
            "needs `binding.from: annotation_value`",
        ),
    ],
)
def test_a_broken_wiring_block_is_refused_by_name(edit: object, expected: str):
    """Every `wiring`, `injected` and `container` word is refused at load when it is the
    wrong shape — before any fact is read (`_UnusedWorkspace`), because each one reaches a
    configuration key looked up verbatim, a row's protocol or the classpath test, where a
    typo reads as an observation."""
    with pytest.raises(CatalogError) as raised:
        config_join.run(_UnusedWorkspace(), _rewired(edit))

    assert expected in str(raised.value)
    assert "smallrye-reactive-messaging.yml" in str(raised.value)
