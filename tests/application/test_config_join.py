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
    Document,
    ModuleFact,
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
                "consumes": None,
                "produces": None,
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
    workspace = _workspace(tmp_path, _helpers_facts(), coordinates=("com.acme:something-else",))
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
    with the dependency present these same three utility methods still derive
    four boundaries, because `_candidates` reads every declared method and
    filters on the return type alone. Narrowing that needs a `@Bean` conjunct,
    and whether Spring Cloud Stream actually requires `@Bean` is a framework
    question no probe in this repository has answered — §8.1 forbids inventing
    the conjunct, so it is stated in `docs/COVERAGE.md` instead."""
    workspace = _workspace(tmp_path, _helpers_facts(), coordinates=(_STREAM,))
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
