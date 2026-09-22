"""The `metadata_from` pass (spec 2026-09-22 §1f): a qualifying attribute an annotation
states about an inbound endpoint, written to `endpoint_metadata` beside the entries
`request_requirements` and the fluent engine already write.

§1f's rule is what the key is for. A routing fact enters the row's `path` only where BOTH
sides of the wire can read it; where only one side can — a task queue the caller's own
interface declaration can never spell — the fact is an `endpoint_metadata` entry a later
linking tier may use as a refinement. A behavioural fact (a consumer group, a selector, a
durable subscription name) was never a candidate for the path at all. Both land here, for
two different stated reasons, and the tests below pin the writer rather than either
reason.

## The two declaration sites

An attribute is looked for on the handler AND on the handler's enclosing type, because
the first consumer's task queue sits on a TYPE-level annotation on the class that
implements a contract interface while the row's `handler` is that class's own overriding
method. Where BOTH carry the same annotation the NEAREST wins: a test per site, one for
each of the two ways a union would go wrong (two values for one endpoint; a measured
default beside the explicit value contradicting it), and one holding that nearest-wins is
per annotation rather than per handler.

## Everything here is invented

Invented symbols, an invented catalog id, invented annotations — the reason every pass
test in this directory gives: one behaviour per test, isolated and fast. No shipped
catalog declares `metadata_from` yet, so there is no shipped answer to pin beside these.
"""

from pathlib import Path

import pytest

from sextant.application.ports.catalogs import Catalog, CatalogError
from sextant.application.resolve.endpoint_attributes import record_endpoint_attributes
from sextant.domain.closed_sets import OriginTier
from sextant.domain.factfile import write_fact_file
from sextant.domain.facts import AnnotationFact, AnnotationUse, Document
from sextant.storage.duckdb.workspace import DuckDbWorkspace

_MODULE = "sextant-jvm maven com.acme/orders-service 1.0.0 "
IMPL = "com/acme/orders/OrderWorkflowImpl#"
HANDLER = IMPL + "process(sig_00000001)."
OTHER_HANDLER = IMPL + "cancel(sig_00000002)."
CATALOG = "invented-workflow"

# Invented annotations, in the dotted form a catalog spells them. `IMPL_ANNOTATION` is the
# type-level one carrying an array attribute; `LISTEN` is the method-level one carrying a
# scalar and a boolean.
IMPL_ANNOTATION = "com.acme.boot.WorkflowImpl"
LISTEN = "com.acme.boot.Listen"
MAPPING_ANNOTATION = "com.acme.contract.WorkflowMethod"

TASK_QUEUE = {"annotation": IMPL_ANNOTATION, "attribute": "taskQueues", "kind": "task_queue"}


def _document() -> Document:
    return Document(
        document_id="doc",
        relative_path="com/acme/orders/OrderWorkflowImpl.class",
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


def _descriptor(dotted: str) -> str:
    return dotted.replace(".", "/") + "#"


def _annotated(target: str, annotation: str, **args: object) -> AnnotationFact:
    """One annotation on a method or its class, as the extractor writes it — attribute
    values as the class file carries them, a `String[]` attribute a list."""
    return AnnotationFact(
        document_id="doc",
        target=_MODULE + target,
        use=AnnotationUse(annotation=_descriptor(annotation), args=args),  # type: ignore[arg-type]
        retention="RUNTIME",
    )


def _catalog(
    *entries: object,
    catalog_id: str = CATALOG,
    direction: str = "inbound",
    resolves: dict[str, object] | None = None,
    metadata_from: object = ...,
    requires: tuple[str, ...] = ("annotation_args",),
) -> Catalog:
    """An annotation catalog declaring `metadata_from` beside the mapping block its rows
    were derived from — the same `annotations`/`prefix_annotation` shape
    `effective_annotation_uses` reads its synthetic rows through. `requires` carries the
    capability the key reads through, which every declaring catalog must name."""
    matches: dict[str, object] = {
        "mapping": {
            "annotations": [{"fqn": MAPPING_ANNOTATION, "method": ["workflow"]}],
            "prefix_annotation": None,
        }
    }
    matches["metadata_from"] = list(entries) if metadata_from is ... else metadata_from
    return Catalog(
        id=catalog_id,
        style="annotation_driven",
        protocol="temporal",
        direction=direction,
        requires=requires,
        matches=matches,
        source=Path("tests/invented-workflow.yml"),
        wrappers=[],
        nullability={},
        serialization={},
        known_types=[],
        resolves=resolves or {},
    )


def _workspace(
    tmp_path: Path,
    annotations: list[AnnotationFact],
    *rows: tuple[str, str, str | None],
    catalog_id: str = CATALOG,
    direction: str = "inbound",
) -> DuckDbWorkspace:
    """Annotation facts loaded, then the endpoint rows a test names as `(method, path,
    handler)` — the columns an engine mints one with, `catalog_id` fixed. `direction` is
    the ROW's own, already final: the pass runs after every flip."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    write_fact_file(tmp_path / "facts" / "OrderWorkflowImpl.jsonl", _document(), annotations)
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    workspace.derive("endpoint_metadata_reset")
    for method, path, handler in rows:
        workspace._connection.execute(
            "INSERT INTO endpoints (protocol, direction, method, path, handler, caller, "
            "catalog_id) VALUES ('temporal', ?, ?, ?, ?, NULL, ?)",
            [direction, method, path, None if handler is None else _MODULE + handler, catalog_id],
        )
    return workspace


def _run(
    tmp_path: Path,
    annotations: list[AnnotationFact],
    *rows: tuple[str, str, str | None],
    catalogs: list[Catalog] | None = None,
    catalog_id: str = CATALOG,
    direction: str = "inbound",
) -> list[dict[str, object]]:
    if not rows:
        rows = (("workflow", "OrderWorkflow", HANDLER),)
    workspace = _workspace(tmp_path, annotations, *rows, catalog_id=catalog_id, direction=direction)
    record_endpoint_attributes(
        workspace, catalogs if catalogs is not None else [_catalog(TASK_QUEUE)]
    )
    entries = [dict(row) for row in workspace.query("endpoint_metadata")]
    workspace.close()
    return entries


def _shape(entries: list[dict[str, object]]) -> list[tuple]:
    """`(kind, name, value, resolution)` per row. The rows arrive in the named query's
    own whole-row order (NFR-1), not in the order the pass appended them, so every
    expectation below is written sorted."""
    return [(e["kind"], e["name"], e["value"], e["resolution"]) for e in entries]


def test_an_attribute_named_by_metadata_from_becomes_a_metadata_row(tmp_path: Path):
    """One `{annotation, attribute, kind}` triple, one present attribute, one row against
    the endpoint that declaration minted — the full `_entry` column shape
    `request_requirements` already keeps for an inbound entry: the row's own identity
    columns, `caller` the handler, `name` and `requirement` NULL, `evidence: compiler`."""
    annotations = [_annotated(IMPL, IMPL_ANNOTATION, taskQueues=["orders"])]
    assert _run(tmp_path, annotations) == [
        {
            "protocol": "temporal",
            "direction": "inbound",
            "method": "workflow",
            "path": "OrderWorkflow",
            "caller": _MODULE + HANDLER,
            "kind": "task_queue",
            "name": None,
            "value": "orders",
            "resolution": "resolved",
            "evidence": "compiler",
            "requirement": None,
        }
    ]


def test_an_array_attribute_is_one_row_per_element(tmp_path: Path):
    """A `String[]` attribute names as many queues as it lists, and each is its own row —
    the table is a set of stated facts, not one comma-joined string nothing can read."""
    annotations = [_annotated(IMPL, IMPL_ANNOTATION, taskQueues=["billing", "billing-retry"])]
    assert _shape(_run(tmp_path, annotations)) == [
        ("task_queue", None, "billing", "resolved"),
        ("task_queue", None, "billing-retry", "resolved"),
    ]


def test_a_scalar_attribute_reads_the_same_as_a_one_element_array(tmp_path: Path):
    """A `String` attribute is one row; a boolean is written lowercase, which is the text
    a JSON boolean reads back as and the spelling every other reader of an annotation
    argument in this repository compares against (`str(True)` would be `'True'`)."""
    annotations = [_annotated(HANDLER, LISTEN, selector="tenant = 'acme'", local=True)]
    catalog = _catalog(
        {"annotation": LISTEN, "attribute": "selector", "kind": "selector"},
        {"annotation": LISTEN, "attribute": "local", "kind": "delivery"},
    )
    assert _shape(_run(tmp_path, annotations, catalogs=[catalog])) == [
        ("delivery", None, "true", "resolved"),
        ("selector", None, "tenant = 'acme'", "resolved"),
    ]


def test_a_placeholder_value_stays_unresolved(tmp_path: Path):
    """GUIDELINES §8.2: this repository never guesses a deployed value. A placeholder is
    resolved by the framework at startup out of configuration a repository cannot see, so
    the value is carried VERBATIM and the row says `unresolved` rather than substituting
    something."""
    annotations = [_annotated(IMPL, IMPL_ANNOTATION, taskQueues=["${orders.queue}"])]
    assert _shape(_run(tmp_path, annotations)) == [
        ("task_queue", None, "${orders.queue}", "unresolved")
    ]


def test_an_absent_attribute_writes_absent_value_when_declared_and_nothing_otherwise(
    tmp_path: Path,
):
    """A framework default never reaches the annotation USE — the framework applies it
    after the class file is written — so a catalog that has MEASURED the annotation's own
    `AnnotationDefault` states it as `absent_value` and cites the probe beside the line.
    A triple with no `absent_value` writes nothing for the same absent attribute: silence
    is the honest answer where nobody measured the default."""
    annotations = [_annotated(HANDLER, LISTEN, value="orders")]
    measured = _catalog(
        {"annotation": LISTEN, "attribute": "local", "kind": "delivery", "absent_value": "true"}
    )
    unmeasured = _catalog({"annotation": LISTEN, "attribute": "local", "kind": "delivery"})
    assert _shape(_run(tmp_path, annotations, catalogs=[measured])) == [
        ("delivery", None, "true", "resolved")
    ]
    assert _run(tmp_path / "unmeasured", annotations, catalogs=[unmeasured]) == []


def test_an_annotation_the_declaration_does_not_carry_writes_nothing(tmp_path: Path):
    """The near-miss (GUIDELINES §10): the same absent attribute with the same
    `absent_value` writes nothing when the ANNOTATION itself is not on the declaration.
    `absent_value` states what the framework does when an attribute of a written
    annotation was left out — it says nothing at all about a declaration that never
    carried the annotation."""
    annotations = [_annotated(HANDLER, MAPPING_ANNOTATION)]
    measured = _catalog(
        {"annotation": LISTEN, "attribute": "local", "kind": "delivery", "absent_value": "true"}
    )
    assert _run(tmp_path, annotations, catalogs=[measured]) == []


def test_the_attribute_is_read_off_the_handlers_enclosing_type_as_well(tmp_path: Path):
    """The first consumer's task queue sits on a TYPE-level annotation on the class that
    implements a contract interface, while the row's `handler` is that class's own
    overriding method — so both declaration sites are read. Both handlers of the class
    get the class's queue."""
    annotations = [_annotated(IMPL, IMPL_ANNOTATION, taskQueues=["orders"])]
    entries = _run(
        tmp_path,
        annotations,
        ("workflow", "OrderWorkflow", HANDLER),
        ("signal", "OrderWorkflow/cancel", OTHER_HANDLER),
    )
    assert [(e["method"], e["path"], e["caller"], e["value"]) for e in entries] == [
        ("signal", "OrderWorkflow/cancel", _MODULE + OTHER_HANDLER, "orders"),
        ("workflow", "OrderWorkflow", _MODULE + HANDLER, "orders"),
    ]


def test_the_nearest_declaration_site_wins_and_the_enclosing_type_is_not_unioned_in(
    tmp_path: Path,
):
    """The handler's own annotation ANSWERS, and the enclosing type's use of the same
    annotation is not read at all. A union would put both consumer groups on one
    endpoint — one of them a group that endpoint is not in — and there is no measurement
    behind a claim that any framework honours both.

    The assertion is an exact LIST rather than a set, deliberately: a set cannot see a
    duplicate row, and a duplicate is one of the two failures this rule exists to
    prevent."""
    annotations = [
        _annotated(IMPL, IMPL_ANNOTATION, taskQueues=["class-queue", "shared"]),
        _annotated(HANDLER, IMPL_ANNOTATION, taskQueues=["method-queue", "shared"]),
    ]
    assert _shape(_run(tmp_path, annotations)) == [
        ("task_queue", None, "method-queue", "resolved"),
        ("task_queue", None, "shared", "resolved"),
    ]


def test_the_enclosing_types_annotation_does_not_supply_an_absent_value_for_the_handlers(
    tmp_path: Path,
):
    """The second failure a union would cause, and the worse one. The class carries the
    annotation with the attribute UNWRITTEN while the handler writes it explicitly: a
    union would emit the entry's measured `absent_value` beside the explicit value that
    contradicts it — a default attributed to a declaration that stated the opposite,
    which is the exact fabrication `absent_value` is fenced against. Nearest wins, so
    the class's use is not read and the explicit value stands alone."""
    annotations = [
        _annotated(IMPL, LISTEN),
        _annotated(HANDLER, LISTEN, local=False),
    ]
    catalog = _catalog(
        {"annotation": LISTEN, "attribute": "local", "kind": "delivery", "absent_value": "true"}
    )
    assert _shape(_run(tmp_path, annotations, catalogs=[catalog])) == [
        ("delivery", None, "false", "resolved")
    ]


def test_a_different_annotation_on_each_site_reads_both(tmp_path: Path):
    """Nearest-wins is PER ANNOTATION, not per handler: a starter annotation on the class
    and a listener annotation on the method are two different declarations, and the
    handler carrying one of them does not hide the other."""
    annotations = [
        _annotated(IMPL, IMPL_ANNOTATION, taskQueues=["orders"]),
        _annotated(HANDLER, LISTEN, selector="tenant = 'acme'"),
    ]
    catalog = _catalog(
        TASK_QUEUE, {"annotation": LISTEN, "attribute": "selector", "kind": "selector"}
    )
    assert _shape(_run(tmp_path, annotations, catalogs=[catalog])) == [
        ("selector", None, "tenant = 'acme'", "resolved"),
        ("task_queue", None, "orders", "resolved"),
    ]


def test_a_metadata_row_names_only_an_endpoint_its_own_catalog_minted(tmp_path: Path):
    """Two catalogs can match one handler — the two Spring web catalogs both match a
    `@RestController` class. An entry written against another catalog's row would state
    one framework's attribute about another framework's endpoint, so `catalog_id` is the
    filter. A row naming no handler is skipped too: there is nothing to read an
    annotation off."""
    annotations = [_annotated(IMPL, IMPL_ANNOTATION, taskQueues=["orders"])]
    assert _run(tmp_path, annotations, catalog_id="somebody-else") == []
    assert _run(tmp_path / "no-handler", annotations, ("workflow", "OrderWorkflow", None)) == []


def test_a_catalog_not_requiring_the_argument_capability_is_refused_naming_the_file(
    tmp_path: Path,
):
    """The key reads an annotation's ARGUMENTS and nothing else. A catalog that does not
    declare the capability producing them runs on a scan where every `args` map is empty,
    so every attribute reads as absent — and a declared `absent_value` would then be
    written against every endpoint the catalog owns, a measured default attributed to
    declarations nobody looked at. Refused rather than left to the capability gate: the
    gate skips a catalog that ASKED for a capability it did not get, and one that never
    asked is the silent case."""
    annotations = [_annotated(IMPL, IMPL_ANNOTATION, taskQueues=["orders"])]
    workspace = _workspace(tmp_path, annotations, ("workflow", "OrderWorkflow", HANDLER))
    with pytest.raises(CatalogError, match=r"invented-workflow\.yml") as raised:
        record_endpoint_attributes(workspace, [_catalog(TASK_QUEUE, requires=())])
    workspace.close()
    assert "annotation_args" in str(raised.value)


def test_an_outbound_row_gets_no_entry_even_where_the_declaration_carries_one(tmp_path: Path):
    """§1f: a qualifying attribute belongs to the side of the wire that DECLARES it, and
    every attribute this key reads sits on the receiving side. The pass reads each ROW's
    own `direction` — final by the time it runs, a `resolves.direction` flip included —
    so a catalog that can face both ways records the attribute on its inbound rows and
    never on its outbound ones."""
    annotations = [_annotated(IMPL, IMPL_ANNOTATION, taskQueues=["orders"])]
    flipping = _catalog(
        TASK_QUEUE,
        direction="outbound",
        resolves={
            "direction": [
                {
                    "when": {"owner_implemented_by_type_annotated": [IMPL_ANNOTATION]},
                    "then": "inbound",
                }
            ]
        },
    )
    assert _run(tmp_path, annotations, catalogs=[flipping], direction="outbound") == []
    assert _shape(
        _run(tmp_path / "flipped", annotations, catalogs=[flipping], direction="inbound")
    ) == [("task_queue", None, "orders", "resolved")]


def test_a_catalog_that_can_only_ever_be_outbound_is_refused_naming_the_file(tmp_path: Path):
    """An outbound catalog declaring the key would state a peer's configuration as this
    module's own. Refused rather than ignored, the shape every other catalog key is
    refused by — and the DECLARED direction is not the test, because a catalog reaching
    inbound through a `resolves.direction` flip is legitimate (the test above)."""
    annotations = [_annotated(IMPL, IMPL_ANNOTATION, taskQueues=["orders"])]
    workspace = _workspace(tmp_path, annotations, ("workflow", "OrderWorkflow", HANDLER))
    with pytest.raises(CatalogError, match=r"invented-workflow\.yml") as raised:
        record_endpoint_attributes(workspace, [_catalog(TASK_QUEUE, direction="outbound")])
    workspace.close()
    assert "§1f" in str(raised.value)


@pytest.mark.parametrize(
    ("declared", "names"),
    [
        ({"annotation": IMPL_ANNOTATION}, "must be a non-empty list"),
        ([], "must be a non-empty list"),
        ([{"annotation": IMPL_ANNOTATION, "attribute": "taskQueues"}], "`kind`"),
        ([{"attribute": "taskQueues", "kind": "task_queue"}], "`annotation`"),
        ([{**TASK_QUEUE, "kind": ""}], "`kind`"),
        ([{**TASK_QUEUE, "kind": 3}], "`kind`"),
        ([{**TASK_QUEUE, "requirement": "required"}], "entries carry only"),
        ([{**TASK_QUEUE, "absent_value": True}], "`absent_value`"),
    ],
    ids=[
        "not-a-list",
        "empty",
        "no-kind",
        "no-annotation",
        "empty-kind",
        "kind-not-a-string",
        "unknown-key",
        "absent-value-not-a-string",
    ],
)
def test_an_unknown_metadata_from_shape_is_refused_by_file(
    tmp_path: Path, declared: object, names: str
):
    """The SHAPE is closed and the VOCABULARY is not. `endpoint_metadata.kind`'s own
    comment says the set of kinds is per protocol and the catalog names it, so
    `task_queue` and `consumer_group` are the catalog's words and no engine has a list to
    check them against — but a missing key, an empty `kind` or a misspelt one is refused
    naming the file, because an entry read as absent records nothing while reading as
    though it did."""
    workspace = _workspace(tmp_path, [], ("workflow", "OrderWorkflow", HANDLER))
    with pytest.raises(CatalogError, match=r"invented-workflow\.yml") as raised:
        record_endpoint_attributes(workspace, [_catalog(metadata_from=declared)])
    workspace.close()
    assert names in str(raised.value)


def test_a_kind_outside_every_shipped_vocabulary_is_accepted(tmp_path: Path):
    """The other half of the rule above, asserted rather than implied: a `kind` no
    shipped catalog has ever written derives its row. The vocabulary is per protocol and
    the catalog names it — a closed set here would refuse the next protocol's word and
    force a schema change the column's own comment says is not needed."""
    annotations = [_annotated(IMPL, IMPL_ANNOTATION, taskQueues=["orders"])]
    catalog = _catalog({**TASK_QUEUE, "kind": "an_invented_word"})
    assert _shape(_run(tmp_path, annotations, catalogs=[catalog])) == [
        ("an_invented_word", None, "orders", "resolved")
    ]


def test_a_catalog_declaring_nothing_writes_nothing(tmp_path: Path):
    """The state every shipped catalog is in today: no `metadata_from`, no rows, and the
    workspace is not read at all. The absence of a row is the statement that the
    declaration named no qualifying attribute."""
    annotations = [_annotated(IMPL, IMPL_ANNOTATION, taskQueues=["orders"])]
    assert _run(tmp_path, annotations, catalogs=[_catalog(metadata_from=None)]) == []


def test_an_attribute_written_with_a_value_this_pass_cannot_spell_writes_nothing(
    tmp_path: Path,
):
    """An element that is a nested annotation is dropped rather than rendered — the
    `scheduled_work._verbatim` rule: an attribute that was written and could not be read
    must never become a stated value with an invented one. An explicitly EMPTY string
    goes the same way: a row whose `value` is empty states a queue named by nothing. The
    well-formed sibling in the same attribute derives."""
    annotations = [
        _annotated(IMPL, IMPL_ANNOTATION, taskQueues=["", "orders"]),
        _annotated(HANDLER, LISTEN, selector={"annotation": "com/acme/Nested#"}),
    ]
    catalog = _catalog(TASK_QUEUE, {"annotation": LISTEN, "attribute": "selector", "kind": "sel"})
    assert _shape(_run(tmp_path, annotations, catalogs=[catalog])) == [
        ("task_queue", None, "orders", "resolved")
    ]


@pytest.mark.parametrize(
    "written",
    ["com/acme/OrderFactory#", "com/acme/AckMode#EAGER."],
    ids=["class-reference", "enum-reference"],
)
def test_a_symbol_reference_is_not_published_as_a_wire_name(tmp_path: Path, written: str):
    """D00 §5a's literal model spells a class reference AND an enum reference as a symbol
    reference — a plain string carrying the symbol grammar's type marker. A symbol is not
    a name anything puts on a wire: `com/acme/OrderFactory#` in a `value` column would
    read as the queue a peer should look for. Dropped, so the declaration that named a
    type writes nothing rather than a row nobody can act on."""
    annotations = [_annotated(IMPL, IMPL_ANNOTATION, taskQueues=[written, "orders"])]
    assert _shape(_run(tmp_path, annotations)) == [("task_queue", None, "orders", "resolved")]
