"""`BoundarySource` (spec 2026-10-22-boundary-vocabulary-and-diff §2, §3a): one side of a
comparison, read the same way whether it is a workspace or an exported bundle.

Most tests write the tables a kind reads row by row — the source is a reader of those
tables, and a row written by hand says exactly what the test is about. The two that need a
symbol's declaring DOCUMENT (the evidence and the `origin`) go through real fact files and
the shipped `spring-web` catalog, because the join from a handler to its document is the
thing they pin.
"""

import json
import shutil
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from click.testing import CliRunner

from sextant.application.boundary.source import (
    ROW_KEYS,
    STAMPS,
    BoundarySource,
    NotABoundarySource,
)
from sextant.application.boundary.vocabulary import KINDS
from sextant.application.resolve.bean_conditions import record_bean_conditions
from sextant.application.resolve.config import resolve_config
from sextant.application.resolve.endpoints import derive_endpoints
from sextant.application.resolve.request_requirements import record_request_requirements
from sextant.cli.app import cli
from sextant.domain.closed_sets import ConstructKind, OriginTier
from sextant.domain.factfile import write_fact_file
from sextant.domain.facts import (
    AnnotationFact,
    AnnotationUse,
    ConfigEntryFact,
    Document,
    Parameter,
    Signature,
    SymbolFact,
    TypeRef,
)
from sextant.ingress.catalogs.yaml_source import YamlCatalogSource
from sextant.storage.duckdb import workspace as workspace_module
from sextant.storage.duckdb.workspace import DuckDbWorkspace, open_read_only

CATALOGS = Path(__file__).parents[3] / "src" / "sextant" / "catalogs"
FIXTURE = Path(__file__).parents[3] / "fixtures" / "orders-service"
_MODULE = "sextant-jvm maven com.acme/orders-service 1.0.0 "

_METADATA = {
    "schema_version": 7,
    "boundary_vocabulary_version": 2,
    "catalog_hash": "sha256:catalogs",
    "module": {
        "id": "com.acme:orders-service",
        "kind": "service",
        "languages": ["java"],
        "dependency_source": "declared",
    },
    "provenance": {"commit": "630906a7", "sextant_version": "0.1.0", "fact_schema_version": 2},
    "environments": ["default", "prod"],
}


@pytest.fixture
def sources() -> Iterator[Callable[[Path], BoundarySource]]:
    """Opens sources and closes every one at teardown, so no test leaves a file locked."""
    opened: list[BoundarySource] = []

    def open_one(path: Path) -> BoundarySource:
        source = BoundarySource.open(path, open_read_only)
        opened.append(source)
        return source

    yield open_one
    for source in opened:
        source.close()


def _workspace_dir(root: Path) -> Path:
    directory = root / ".sextant"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "metadata.json").write_text(json.dumps(_METADATA), encoding="utf-8")
    return directory


def _insert(workspace: DuckDbWorkspace, table: str, **columns: object) -> None:
    names = ", ".join(columns)
    marks = ", ".join("?" for _ in columns)
    workspace._connection.execute(
        f"INSERT INTO {table} ({names}) VALUES ({marks})", list(columns.values())
    )


def _endpoint(workspace: DuckDbWorkspace, **columns: object) -> None:
    _insert(
        workspace,
        "endpoints",
        **{"protocol": "http", "direction": "inbound", "resolution": "resolved", **columns},
    )


def _built(root: Path, build: Callable[[DuckDbWorkspace], None]) -> Path:
    """A workspace directory whose tables `build` filled, closed so the source can open it."""
    directory = _workspace_dir(root)
    workspace = DuckDbWorkspace(directory / "workspace.duckdb")
    try:
        build(workspace)
    finally:
        workspace.close()
    return directory


# --- grouping on identity ---------------------------------------------------------------


def _document(document_id: str, tier: OriginTier) -> Document:
    return Document(
        document_id=document_id,
        relative_path=document_id.rstrip("#") + ".java",
        module_id="com.acme:orders-service",
        language="java",
        sextant_version="0.1.0",
        fact_schema_version=2,
        scanner_id="sextant-jvm-extractor",
        content_hash="sha256:c",
        origin_entry="target/classes",
        origin_tier=tier,
        redaction_set_hash="sha256:none",
    )


def _catch_all(
    root: Path,
    owner: str,
    tier: OriginTier = OriginTier.MODULE_OUTPUT,
    parameters: tuple[Parameter, ...] = (),
    on_class: tuple[AnnotationUse, ...] = (),
) -> None:
    """A `@RestController` with one `@GetMapping("/**")` handler; `parameters` are the
    handler's, `on_class` further annotations on the class (a `@Profile`)."""
    handler = _MODULE + owner + "get(sig_00000001)."
    write_fact_file(
        root / f"{owner.replace('/', '_')}.jsonl",
        _document(owner, tier),
        [
            SymbolFact(
                document_id=owner, symbol=_MODULE + owner, construct_kind=ConstructKind.CLASS
            ),
            SymbolFact(
                document_id=owner,
                symbol=handler,
                construct_kind=ConstructKind.METHOD,
                enclosing=_MODULE + owner,
                signature=Signature(parameters=list(parameters)) if parameters else None,
            ),
            *[
                AnnotationFact(
                    document_id=owner, target=_MODULE + owner, retention="runtime", use=use
                )
                for use in on_class
            ],
            AnnotationFact(
                document_id=owner,
                target=_MODULE + owner,
                retention="runtime",
                use=AnnotationUse(
                    annotation="org/springframework/web/bind/annotation/RestController#", args={}
                ),
            ),
            AnnotationFact(
                document_id=owner,
                target=handler,
                retention="runtime",
                use=AnnotationUse(
                    annotation="org/springframework/web/bind/annotation/GetMapping#",
                    args={"value": ["/**"]},
                ),
            ),
        ],
    )


def _service(root: Path, owner: str, method: str, on_class: tuple[AnnotationUse, ...] = ()) -> str:
    """A `@Service` class with one method, the code an outbound call is made from; `on_class`
    further annotations on the class (a `@ConditionalOnProperty`). Returns the method."""
    caller = _MODULE + owner + method
    write_fact_file(
        root / f"{owner.replace('/', '_')}.jsonl",
        _document(owner, OriginTier.MODULE_OUTPUT),
        [
            SymbolFact(
                document_id=owner, symbol=_MODULE + owner, construct_kind=ConstructKind.CLASS
            ),
            SymbolFact(
                document_id=owner,
                symbol=caller,
                construct_kind=ConstructKind.METHOD,
                enclosing=_MODULE + owner,
            ),
            *[
                AnnotationFact(
                    document_id=owner, target=_MODULE + owner, retention="runtime", use=use
                )
                for use in (
                    AnnotationUse(annotation="org/springframework/stereotype/Service#", args={}),
                    *on_class,
                )
            ],
        ],
    )
    return caller


def _two_catch_alls(root: Path, tiers: tuple[OriginTier, OriginTier]) -> Path:
    facts = root / "facts"
    _catch_all(facts, "com/acme/a/AController#", tiers[0])
    _catch_all(facts, "com/acme/b/BController#", tiers[1])

    def build(workspace: DuckDbWorkspace) -> None:
        workspace.load_facts(facts)
        spring = next(c for c in YamlCatalogSource(CATALOGS).load() if c.id == "spring-web")
        derive_endpoints(workspace, [spring], capabilities={"annotation_args", "type_annotations"})

    return _built(root, build)


def test_several_handlers_behind_one_wire_identity_are_one_row_with_several_symbols(
    tmp_path: Path, sources: Callable[[Path], BoundarySource]
):
    both = (OriginTier.MODULE_OUTPUT, OriginTier.MODULE_OUTPUT)
    rows = sources(_two_catch_alls(tmp_path, both)).rows(KINDS["endpoint"])
    (row,) = [r for r in rows if r["path"] == "/**"]
    assert [s.split("/")[-1] for s in row["evidence"]["symbols"]] == [  # type: ignore[index, attr-defined]
        "AController#get(sig_00000001).",
        "BController#get(sig_00000001).",
    ]
    assert row["evidence"]["documents"] == [  # type: ignore[index]
        "com/acme/a/AController.java",
        "com/acme/b/BController.java",
    ]
    assert row["origin"] == "module_output"


def test_a_row_is_a_dependencys_only_where_every_grounding_document_is(
    tmp_path: Path, sources: Callable[[Path], BoundarySource]
):
    """Attribution follows origin (FR-22): a boundary any of the module's own classes
    declares is the module's; one only a dependency's classes declare is the dependency's."""
    own, dep = OriginTier.MODULE_OUTPUT, OriginTier.DEPENDENCY
    mixed = sources(_two_catch_alls(tmp_path / "mixed", (own, dep))).rows(KINDS["endpoint"])
    assert [r["origin"] for r in mixed if r["path"] == "/**"] == ["module_output"]
    only = sources(_two_catch_alls(tmp_path / "only", (dep, dep))).rows(KINDS["endpoint"])
    assert [r["origin"] for r in only if r["path"] == "/**"] == ["dependency"]


def test_an_unread_address_keeps_its_rows_together_and_distinct_peers_apart(
    tmp_path: Path, sources: Callable[[Path], BoundarySource]
):
    """Two `sendDefault` calls: method NULL, path NULL, the same peer, different callers. NULL
    joins NULL because the wire is what identifies — one dependency, two evidence symbols. A
    third call to another peer is another dependency."""

    def build(workspace: DuckDbWorkspace) -> None:
        for caller, peer in (("Z#a().", "billing"), ("Y#b().", "billing"), ("X#c().", "ledger")):
            _endpoint(workspace, protocol="kafka", direction="outbound", caller=caller, peer=peer)

    rows = sources(_built(tmp_path, build)).rows(KINDS["dependency"])
    assert [(r["peer"], r["evidence"]["symbols"]) for r in rows] == [  # type: ignore[index]
        ("billing", ["Y#b().", "Z#a()."]),
        ("ledger", ["X#c()."]),
    ]
    assert all(r["method"] is None and r["path"] is None for r in rows)


def test_a_both_direction_row_is_an_endpoint_and_a_dependency(
    tmp_path: Path, sources: Callable[[Path], BoundarySource]
):
    def build(workspace: DuckDbWorkspace) -> None:
        _endpoint(
            workspace, direction="both", method="GET", path="/x", handler="H#h().", caller="C#c()."
        )
        _endpoint(workspace, direction="inbound", method="GET", path="/y", handler="H#y().")
        _endpoint(workspace, direction="outbound", method="GET", path="/z", caller="C#z().")

    source = sources(_built(tmp_path, build))
    assert [r["path"] for r in source.rows(KINDS["endpoint"])] == ["/x", "/y"]
    assert [r["path"] for r in source.rows(KINDS["dependency"])] == ["/x", "/z"]


def test_the_queries_filter_on_the_text_the_vocabulary_states():
    """`Kind.where` is documentation of what the query does; two spellings of one filter
    are how a `both` row ended up on one side only, so the query is held to the text."""
    for name, query in (
        ("endpoint", "boundary_endpoint"),
        ("dependency", "boundary_dependency"),
    ):
        where = KINDS[name].where
        assert where is not None and where in workspace_module._NAMED_QUERIES[query]


# --- rows that disagree, and the documents behind schedule, error-handler and contract ----


def test_two_expressions_for_one_schedule_identity_are_both_kept(
    tmp_path: Path, sources: Callable[[Path], BoundarySource]
):
    """One method with two `@Scheduled(cron=...)` (javac folds them into `@Schedules`) is one
    `(handler, trigger)`. Taking the first row would drop the second expression silently."""

    def build(workspace: DuckDbWorkspace) -> None:
        for expression in ("0 30 * * * *", "0 0 * * * *"):
            _insert(workspace, "scheduled_work", handler="J#run().", trigger="cron",
                    expression=expression, resolution="resolved", evidence="compiler",
                    catalog_id="spring-scheduling")  # fmt: skip

    (row,) = sources(_built(tmp_path, build)).rows(KINDS["schedule"])
    assert row["expression"] == {"several": ["0 0 * * * *", "0 30 * * * *"]}
    assert row["resolution"] == "resolved"  # rows that agree keep the single value


def test_handlers_behind_one_address_with_different_request_shapes_are_all_kept(
    tmp_path: Path, sources: Callable[[Path], BoundarySource]
):
    def build(workspace: DuckDbWorkspace) -> None:
        _field(workspace, "com/acme/A#", 0, "a")
        _field(workspace, "com/acme/B#", 0, "b")
        for handler, shape in (("H#b().", "com/acme/B#"), ("H#a().", "com/acme/A#")):
            _endpoint(workspace, method="POST", path="/**", handler=handler,
                      request_shape=_shape_descriptor(shape))  # fmt: skip

    (row,) = sources(_built(tmp_path, build)).rows(KINDS["endpoint"])
    assert row["request_shape"] == {
        "several": [_shape_descriptor("com/acme/A#"), _shape_descriptor("com/acme/B#")]
    }
    several = row["request"]["several"]  # type: ignore[index]
    assert [[f["wire_name"] for f in fields] for fields in several] == [["a"], ["b"]]
    assert row["response"] is None and row["resolution"] == "resolved"
    assert row["evidence"]["symbols"] == ["H#a().", "H#b()."]  # type: ignore[index]


def _declared(root: Path, owners: dict[str, tuple[OriginTier, str]]) -> Path:
    """Fact files declaring each owner class and one method on it, in the given origin tier."""
    facts = root / "facts"
    for owner, (tier, method) in owners.items():
        write_fact_file(
            facts / f"{owner.replace('/', '_')}.jsonl",
            _document(owner, tier),
            [
                SymbolFact(
                    document_id=owner, symbol=_MODULE + owner, construct_kind=ConstructKind.CLASS
                ),
                SymbolFact(
                    document_id=owner,
                    symbol=_MODULE + owner + method,
                    construct_kind=ConstructKind.METHOD,
                    enclosing=_MODULE + owner,
                ),
            ],
        )
    return facts


def test_a_contract_schedule_and_error_handler_name_their_documents_and_origin(
    tmp_path: Path, sources: Callable[[Path], BoundarySource]
):
    """The join from a shape or a handler to its declaring document is what makes `origin`
    mean anything: a failed join would read `module_output` for a dependency's class."""
    own, dep = OriginTier.MODULE_OUTPUT, OriginTier.DEPENDENCY
    facts = _declared(
        tmp_path,
        {
            "com/dep/Money#": (dep, "amount(sig_00000001)."),
            "com/acme/Job#": (own, "run(sig_00000002)."),
            "com/dep/Advice#": (dep, "bad(sig_00000003)."),
            "com/acme/Own#": (own, "x(sig_00000004)."),
        },
    )

    def build(workspace: DuckDbWorkspace) -> None:
        workspace.load_facts(facts)
        for shape, tier in (("com/dep/Money#", "dependency"), ("com/acme/Own#", "module_output"),
                            ("AuditEntry", None)):  # fmt: skip
            _insert(workspace, "shapes", shape_id=shape, content_hash="md5:1", open=False,
                    origin_tier=tier)  # fmt: skip
        _insert(workspace, "scheduled_work", handler=_MODULE + "com/acme/Job#run(sig_00000002).",
                trigger="cron", expression="0 * * * * *", resolution="resolved",
                evidence="compiler", catalog_id="c")  # fmt: skip
        _insert(workspace, "error_handlers", handler=_MODULE + "com/dep/Advice#bad(sig_00000003).",
                advice="com/dep/Advice#", exception="java/lang/Exception#", status="BAD_REQUEST",
                resolution="resolved", evidence="compiler", catalog_id="c")  # fmt: skip

    source = sources(_built(tmp_path, build))
    contracts = {r["shape_id"]: r for r in source.rows(KINDS["data-contract"])}
    money = contracts["com/dep/Money#"]
    assert money["evidence"]["documents"] == ["com/dep/Money.java"]  # type: ignore[index]
    assert money["evidence"]["origin_tier"] == "dependency"  # type: ignore[index]
    assert money["origin"] == "dependency"
    assert contracts["com/acme/Own#"]["evidence"]["documents"] == ["com/acme/Own.java"]  # type: ignore[index]
    assert contracts["com/acme/Own#"]["origin"] == "module_output"
    # A declared schema's bare name matches no class: no document, and the module's own.
    assert contracts["AuditEntry"]["evidence"]["documents"] == []  # type: ignore[index]
    assert contracts["AuditEntry"]["origin"] == "module_output"
    (schedule,) = source.rows(KINDS["schedule"])
    assert schedule["evidence"]["documents"] == ["com/acme/Job.java"]  # type: ignore[index]
    assert schedule["origin"] == "module_output"
    (handler,) = source.rows(KINDS["error-handler"])
    assert handler["evidence"]["documents"] == ["com/dep/Advice.java"]  # type: ignore[index]
    assert handler["origin"] == "dependency"


# --- bodies, requirements, conditions ---------------------------------------------------


def _field(workspace: DuckDbWorkspace, shape: str, ordinal: int, name: str, **columns: object):
    _insert(
        workspace,
        "shape_fields",
        shape_id=shape,
        ordinal=ordinal,
        wire_name=name,
        wire_type=columns.pop("wire_type", "string"),
        wire_format=None,
        required=columns.pop("required", False),
        nullable=columns.pop("nullable", False),
        resolution="resolved",
        evidence="declared",
        **columns,
    )


def _shape_descriptor(shape_id: str) -> str:
    return json.dumps(
        {"nullable": True, "shape_id": shape_id, "wire_format": "", "wire_type": "object"}
    )


def test_a_contract_row_lists_its_fields_by_wire_name(
    tmp_path: Path, sources: Callable[[Path], BoundarySource]
):
    def build(workspace: DuckDbWorkspace) -> None:
        _insert(
            workspace, "shapes", shape_id="com/acme/OrderResult#", content_hash="md5:1", open=False
        )
        for ordinal, name in enumerate(("total", "id", "status")):  # declaration order
            _field(workspace, "com/acme/OrderResult#", ordinal, name, required=name == "id")

    (row,) = sources(_built(tmp_path, build)).rows(KINDS["data-contract"])
    assert row["shape_id"] == "com/acme/OrderResult#" and row["content_hash"] == "md5:1"
    assert row["fields"] == [  # type: ignore[comparison-overlap]
        {
            "wire_name": name,
            "wire_type": "string",
            "wire_format": None,
            "required": name == "id",
            "nullable": False,
        }
        for name in ("id", "status", "total")
    ]


def test_an_endpoints_bodies_are_field_sets_or_none(
    tmp_path: Path, sources: Callable[[Path], BoundarySource]
):
    """A NULL descriptor is no body (`None`); a named shape, or a collection of one, is that
    shape's fields; a shapeless payload is a body with no fields (`[]`). The raw descriptors
    ride along so a list of orders and one order stay different."""
    array = json.dumps(
        {"item": json.loads(_shape_descriptor("com/acme/Order#")), "nullable": True,
         "wire_format": "", "wire_type": "array"}
    )  # fmt: skip
    plain = json.dumps({"nullable": True, "wire_format": "", "wire_type": "string"})

    def build(workspace: DuckDbWorkspace) -> None:
        _field(workspace, "com/acme/Order#", 0, "id")
        _field(workspace, "com/acme/Order#", 1, "name")
        _endpoint(workspace, method="POST", path="/a", handler="H#a().")
        _endpoint(
            workspace, method="POST", path="/b", handler="H#b().",
            request_shape=_shape_descriptor("com/acme/Order#"), response_shape=array,
        )  # fmt: skip
        _endpoint(workspace, method="POST", path="/c", handler="H#c().", response_shape=plain)

    rows = {r["path"]: r for r in sources(_built(tmp_path, build)).rows(KINDS["endpoint"])}
    assert (rows["/a"]["request"], rows["/a"]["response"]) == (None, None)
    names = ["id", "name"]
    assert [f["wire_name"] for f in rows["/b"]["request"]] == names  # type: ignore[attr-defined, union-attr]
    assert [f["wire_name"] for f in rows["/b"]["response"]] == names  # type: ignore[attr-defined, union-attr]
    assert rows["/b"]["response_shape"] == array
    assert rows["/c"]["request"] is None and rows["/c"]["response"] == []
    assert set(rows["/b"]["request"][0]) == {  # type: ignore[index]
        "wire_name", "wire_type", "wire_format", "required", "nullable"
    }  # fmt: skip


def _annotated_parameter(name: str, annotation: str, **args: object) -> Parameter:
    """A `String` handler parameter carrying one Spring binder annotation, as the
    extractor writes it (D00 §5a)."""
    return Parameter(
        name=name,
        type=TypeRef(symbol="java/lang/String#", nullable=True),
        erased_symbol="java/lang/String#",
        annotations=[
            AnnotationUse(
                annotation=f"org/springframework/web/bind/annotation/{annotation}#", args=args
            )
        ],
    )


def _config_file(root: Path, relative_path: str, entries: dict[str, str]) -> None:
    document = _document(relative_path, OriginTier.MODULE_OUTPUT).model_copy(
        update={"relative_path": relative_path, "language": "yaml",
                "scanner_id": "sextant-config-reader", "origin_entry": "src/main/resources"}
    )  # fmt: skip
    write_fact_file(
        root / f"{relative_path}.jsonl",
        document,
        [
            ConfigEntryFact(document_id=relative_path, key_raw=k, key_path=k, value=v)
            for k, v in entries.items()
        ],
    )


def test_requirements_conditions_and_headers_are_sorted_sets(
    tmp_path: Path, sources: Callable[[Path], BoundarySource]
):
    """The inbound rows are written by the REAL passes through the shipped `spring-web`
    catalog — `record_request_requirements` and `record_bean_conditions` — because the
    writer is what decides which column names the endpoint: an inbound `endpoint_metadata`
    row carries the HANDLER in its `caller` column while the `endpoints` row's `caller` is
    NULL, and a test that wrote both by hand matched them on a NULL nobody writes.

    Two handlers behind `GET /**`: A binds `@RequestParam(required = false) q` and
    `@RequestHeader("X-Id")` and sits under `@Profile("prod")`; B binds the same header.
    The header is one entry, the condition is A's declared one. The outbound header is
    written as `engines/single_call.py` writes one — `caller` the calling method on both
    tables, so the dependency's join is on `caller`.

    Re-pinned by spec 2026-10-23-deployment-set-conditions (ruling 3): a row's conditions are
    the `{kind, expression}` its code declares. The verdict in each environment — here
    `unresolved` in `default` and `true` in `prod` — is evidence, kept in the workspace and
    the documents and out of the row a diff compares."""
    facts = tmp_path / "facts"
    header = _annotated_parameter("id", "RequestHeader", value="X-Id")
    _catch_all(facts, "com/acme/a/AController#",
               parameters=(_annotated_parameter("q", "RequestParam", required=False), header),
               on_class=(AnnotationUse(annotation="org/springframework/context/annotation/Profile#",
                                       args={"value": ["prod"]}),))  # fmt: skip
    _catch_all(facts, "com/acme/b/BController#", parameters=(header,))
    _config_file(facts, "application.yml", {"server.port": "8080"})
    _config_file(facts, "application-prod.yml", {"server.port": "80"})

    def build(workspace: DuckDbWorkspace) -> None:
        workspace.load_facts(facts)
        spring = next(c for c in YamlCatalogSource(CATALOGS).load() if c.id == "spring-web")
        derive_endpoints(workspace, [spring], capabilities={"annotation_args", "type_annotations"})
        resolve_config(workspace, [spring])
        workspace.derive("endpoint_metadata_reset")
        record_request_requirements(workspace, [spring])
        workspace.derive("bean_conditions_reset")
        record_bean_conditions(workspace, [spring])
        # Not vacuous: the writer names the handler, and the endpoint row has no caller.
        (inbound,) = {(r["caller"], r["handler"]) for r in workspace.query("endpoints")
                      if r["handler"].startswith(_MODULE + "com/acme/a/")}  # fmt: skip
        assert inbound[0] is None
        assert inbound[1] in {str(r["caller"]) for r in workspace.query("endpoint_metadata")}
        _endpoint(workspace, direction="outbound", method="GET", path="/o", caller="C#o().",
                  peer="p")  # fmt: skip
        _insert(workspace, "endpoint_metadata", protocol="http", direction="outbound",
                method="GET", path="/o", caller="C#o().", kind="header", name="Accept",
                value="application/json")  # fmt: skip
        _insert(workspace, "endpoint_metadata", protocol="http", direction="outbound",
                method="GET", path="/o", caller="C#o().", kind="query", name="page", value="1")  # fmt: skip

    source = sources(_built(tmp_path, build))
    (endpoint,) = source.rows(KINDS["endpoint"])
    assert endpoint["requirements"] == [
        {"kind": "header", "name": "X-Id", "requirement": "required"},
        {"kind": "param", "name": "q", "requirement": "optional"},
    ]
    # Ruling 3: the declared `{kind, expression}` once, whatever each environment's verdict.
    assert endpoint["conditions"] == [
        {"kind": "profile", "expression": '{"expressions": ["prod"]}'}
    ]
    (dependency,) = source.rows(KINDS["dependency"])
    assert dependency["headers"] == [{"name": "Accept", "value": "application/json"}]


@pytest.mark.pins("boundary.a-DEPENDENCY-condition-is-matched-on-its-CALLER")
def test_a_dependency_carries_the_conditions_of_the_bean_it_is_called_from(
    tmp_path: Path, sources: Callable[[Path], BoundarySource]
):
    """Spec 2026-10-23-deployment-set-conditions, ruling 2: conditions belong to beans, so
    every row a bean produces carries them, in either direction. An outbound row has no
    handler; its code is its `caller`, and the conditions are its caller's bean's, written by
    the REAL pass. Two calls to one address from two callers, one under
    `@ConditionalOnProperty`: only that caller's dependency carries the condition, because a
    dependency's conditions are matched on the row and its `caller`, never on the NULL
    handler both rows share."""
    facts = tmp_path / "facts"
    conditional = AnnotationUse(
        annotation="org/springframework/boot/autoconfigure/condition/ConditionalOnProperty#",
        args={"name": ["billing.enabled"], "havingValue": "true"},
    )
    billing = _service(facts, "com/acme/BillingClient#", "charge().", on_class=(conditional,))
    ledger = _service(facts, "com/acme/LedgerClient#", "post().")

    def build(workspace: DuckDbWorkspace) -> None:
        workspace.load_facts(facts)
        spring = next(c for c in YamlCatalogSource(CATALOGS).load() if c.id == "spring-web")
        record_bean_conditions(workspace, [spring])
        for caller, peer in ((billing, "billing"), (ledger, "ledger")):
            _endpoint(workspace, direction="outbound", method="POST", path="/v1/charges",
                      caller=caller, peer=peer)  # fmt: skip

    rows = {r["peer"]: r for r in sources(_built(tmp_path, build)).rows(KINDS["dependency"])}
    assert rows["billing"]["conditions"] == [
        {
            "kind": "property",
            "expression": '{"having_value": "true", "keys": ["billing.enabled"], '
            '"match_if_missing": false}',
        }
    ]
    assert rows["ledger"]["conditions"] == []


# --- the other kinds --------------------------------------------------------------------


def test_the_remaining_kinds_carry_their_columns_and_evidence(
    tmp_path: Path, sources: Callable[[Path], BoundarySource]
):
    def build(workspace: DuckDbWorkspace) -> None:
        _insert(workspace, "resolved_config", key="orders.url", value="http://x", source="application.yml",
                environment="default")  # fmt: skip
        _insert(workspace, "resolved_config", key="orders.url", value=None, source="application.yml",
                environment="prod", unresolved_reason="missing_key")  # fmt: skip
        _insert(workspace, "scheduled_work", handler="J#run().", trigger="cron", expression="0 * * * * *",
                resolution="resolved", evidence="compiler", catalog_id="spring-scheduling")  # fmt: skip
        _insert(workspace, "error_handlers", handler="A#bad().", advice="A#", declared_by="Advice#",
                exception="java/lang/IllegalArgumentException#", status="BAD_REQUEST",
                resolution="resolved", evidence="compiler", catalog_id="spring-web-advice")  # fmt: skip

    source = sources(_built(tmp_path, build))
    prod, default = (
        {r["environment"]: r for r in source.rows(KINDS["boundary-property"])}[e]
        for e in ("prod", "default")
    )
    assert (default["value"], default["unresolved_reason"]) == ("http://x", None)
    assert (prod["value"], prod["unresolved_reason"]) == (None, "missing_key")
    assert default["evidence"]["source"] == "application.yml"
    assert [r["environment"] for r in source.rows(KINDS["boundary-property"])] == [
        "default",
        "prod",
    ]
    (schedule,) = source.rows(KINDS["schedule"])
    assert (schedule["handler"], schedule["trigger"], schedule["expression"]) == (
        "J#run().", "cron", "0 * * * * *",
    )  # fmt: skip
    assert schedule["evidence"]["catalogs"] == ["spring-scheduling"]  # type: ignore[index]
    (handler,) = source.rows(KINDS["error-handler"])
    assert (handler["exception"], handler["advice"], handler["status"]) == (
        "java/lang/IllegalArgumentException#", "A#", "BAD_REQUEST",
    )  # fmt: skip
    assert handler["evidence"]["symbols"] == ["A#bad()."]  # type: ignore[index]


def test_the_module_kind_is_one_row_from_the_metadata(
    tmp_path: Path, sources: Callable[[Path], BoundarySource]
):
    (row,) = sources(_built(tmp_path, lambda w: None)).rows(KINDS["module"])
    assert row["module_id"] == "com.acme:orders-service"
    assert (row["kind"], row["languages"], row["dependency_source"]) == (
        "service", ["java"], "declared",
    )  # fmt: skip


# --- opening ----------------------------------------------------------------------------


def test_a_workspace_is_found_by_its_directory_or_its_modules(
    tmp_path: Path, sources: Callable[[Path], BoundarySource]
):
    directory = _built(tmp_path, lambda w: None)
    for given in (directory, tmp_path):
        source = sources(given)
        assert (source.module_id, source.commit, source.is_bundle) == (
            "com.acme:orders-service", "630906a7", False,
        )  # fmt: skip
        assert source.module_root == tmp_path
        assert source.environments == ["default", "prod"]
        assert source.producer == {
            "sextant_version": "0.1.0",
            "fact_schema_version": 2,
            "graph_schema_version": 7,
            "boundary_vocabulary_version": 2,
            "catalog_hash": "sha256:catalogs",
        }


def test_a_stamp_the_metadata_lacks_is_absent_from_the_producer(
    tmp_path: Path, sources: Callable[[Path], BoundarySource]
):
    directory = _built(tmp_path, lambda w: None)
    metadata = json.loads((directory / "metadata.json").read_text())
    del metadata["catalog_hash"]
    (directory / "metadata.json").write_text(json.dumps(metadata))
    assert "catalog_hash" not in sources(directory).producer


def test_opening_a_path_that_is_neither_workspace_nor_bundle_raises(
    tmp_path: Path, sources: Callable[[Path], BoundarySource]
):
    with pytest.raises(NotABoundarySource) as refused:
        sources(tmp_path)
    assert refused.value.path == tmp_path and "manifest.json" in refused.value.looked_for


def test_a_workspace_with_no_metadata_is_refused_by_name(
    tmp_path: Path, sources: Callable[[Path], BoundarySource]
):
    directory = _built(tmp_path, lambda w: None)
    (directory / "metadata.json").unlink()
    with pytest.raises(NotABoundarySource, match="metadata.json is missing"):
        sources(directory)


def test_opening_a_workspace_changes_nothing(
    tmp_path: Path, sources: Callable[[Path], BoundarySource]
):
    """`DuckDbWorkspace.__init__` runs the schema on every open; a diff must not. The file
    is the same bytes after a full read of every kind."""
    directory = _built(tmp_path, lambda w: _endpoint(w, method="GET", path="/x", handler="H#h()."))
    database = directory / "workspace.duckdb"
    before = database.read_bytes()
    source = sources(directory)
    for kind in KINDS.values():
        source.rows(kind)
    source.close()
    assert database.read_bytes() == before


# --- a bundle, and the workspace it came from -------------------------------------------


@pytest.fixture
def exported(analyzed_workspace_copy: Path) -> tuple[Path, Path]:
    """The analysed fixture's private workspace and the bundle exported from it."""
    result = CliRunner().invoke(
        cli, ["module", "export", str(FIXTURE), "--workspace", str(analyzed_workspace_copy)]
    )
    assert result.exit_code == 0, result.output
    return analyzed_workspace_copy, Path(result.output.strip())


def _identities(source: BoundarySource, kind_name: str) -> list[tuple[object, ...]]:
    kind = KINDS[kind_name]
    return [tuple(row[column] for column in kind.identity) for row in source.rows(kind)]


def test_a_workspace_and_its_bundle_answer_the_same_identities_for_every_kind(
    exported: tuple[Path, Path], sources: Callable[[Path], BoundarySource]
):
    """Identities only: the bundle's addresses and values are masked at export and the
    workspace's are not, which is the diff's to account for (§3d). The fixture masks nothing
    in an identity, so the sets are equal — and every kind but `schedule` has rows, or this would
    pass vacuously."""
    workspace, bundle = exported
    side_a, side_b = sources(workspace), sources(bundle)
    assert (side_a.is_bundle, side_b.is_bundle) == (False, True)
    assert side_b.module_root is None
    for name in KINDS:
        identities = _identities(side_a, name)
        # The fixture schedules nothing; every other kind has rows to compare.
        assert identities or name == "schedule", name
        assert identities == _identities(side_b, name), name


def test_a_row_carries_every_identity_and_attribute_column_of_its_kind(
    exported: tuple[Path, Path], sources: Callable[[Path], BoundarySource]
):
    side = sources(exported[0])
    for kind in KINDS.values():
        for row in side.rows(kind):
            for token in (*kind.identity, *kind.attributes):
                assert ROW_KEYS.get(token, token) in row, (kind.name, token)
            assert set(row["evidence"]) >= {"symbols", "documents"}  # type: ignore[call-overload]
            assert row["origin"] in ("module_output", "dependency")


def test_a_bundle_is_read_with_the_stamps_of_its_manifest(
    exported: tuple[Path, Path], sources: Callable[[Path], BoundarySource]
):
    workspace, bundle = exported
    side_a, side_b = sources(workspace), sources(bundle)
    assert (side_b.module_id, side_b.commit) == (side_a.module_id, side_a.commit)
    assert side_b.environments == side_a.environments
    # The five a workspace carries, and the one only an export computes.
    assert set(side_a.producer) == set(STAMPS) - {"redaction_set_hash"}
    assert set(side_b.producer) == set(STAMPS)
    assert {k: v for k, v in side_b.producer.items() if k in side_a.producer} == side_a.producer


def test_the_fixtures_bodies_are_the_same_through_both_readers(
    exported: tuple[Path, Path], sources: Callable[[Path], BoundarySource]
):
    """Beyond identity: field sets, requirements, conditions and the grounding documents of
    every endpoint and contract agree across workspace and bundle."""
    workspace, bundle = exported
    for name in ("endpoint", "data-contract", "schedule", "error-handler"):
        assert sources(workspace).rows(KINDS[name]) == sources(bundle).rows(KINDS[name]), name


def test_a_bundle_missing_a_table_the_queries_read_is_refused_by_name(
    exported: tuple[Path, Path], tmp_path: Path, sources: Callable[[Path], BoundarySource]
):
    bundle = tmp_path / "old-bundle"
    shutil.copytree(exported[1], bundle)
    (bundle / "graph" / "endpoint_conditions.parquet").unlink()
    with pytest.raises(NotABoundarySource, match="endpoint_conditions"):
        sources(bundle)
