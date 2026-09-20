"""The inbound request-requirements pass (spec 2026-09-19 §5a): the writer, the
combinator's `route_requirements` stash joined to the `endpoints` rows it was minted
with, and §5b's `request_params` — the parameter annotations on the handler, read off
`endpoints.handler_signature` against a catalog's `request_params` entries.

Then §5c's mapping attributes — Spring's `@RequestMapping(params=, headers=)` expressions,
read as `ParamsRequestCondition`/`HeadersRequestCondition` parse them (CP-25 rows 4 and
13) — and §5d's `request_reads`, the handler body's own reads matched against every
loaded catalog's list (CP-24 rows 5–6, CP-25 rows 14–17). A run with nothing declared
still writes NOTHING rather than an empty-looking something, which the first test says.

## The binder predicate (§5b, CP-25 rows 2–8)

`requirement: binder` is Spring's `AbstractNamedValueMethodArgumentResolver` read off
the class file: a missing value takes `defaultValue` when one is written, else the
request is rejected when `required` and not `MethodParameter.isOptional()` — `Optional`
type, a DECLARATION annotation whose simple name is `Nullable`, or a declared default.
Micronaut's rule is the same predicate with no `required` attribute (CP-25 row 7). The
tests below flip each disjunct on its own against a parameter that is otherwise
`required`, and — the near-miss GUIDELINES §10 asks for — hold `required` where the
type reference is `nullable: true` by LANGUAGE RULE with no annotation saying so (D00 §5:
every Java reference type reads that way; Spring's `hasNullableAnnotation()` never looks
at the type), the case that ruled `type.nullable` out of the predicate (2026-09-20).

## Everything here is invented

Invented symbols, an invented catalog id, an invented header — the reason every pass test
in this directory gives: one behaviour per test, isolated and fast, with the shipped
answer pinned once in `test_pipeline.py` against real bytecode.
"""

import json
from pathlib import Path

import pytest

from sextant.application.ports.catalogs import Catalog, CatalogError
from sextant.application.resolve.request_requirements import (
    _expression,
    record_request_requirements,
)
from sextant.domain.closed_sets import OriginTier
from sextant.domain.factfile import write_fact_file
from sextant.domain.facts import (
    AnnotationFact,
    AnnotationUse,
    CallArgument,
    CallSiteFact,
    CallTarget,
    Document,
)
from sextant.ingress.catalogs.yaml_source import YamlCatalogSource
from sextant.storage.duckdb.workspace import DuckDbWorkspace

CATALOGS = Path(__file__).parents[2] / "src" / "sextant" / "catalogs"

_MODULE = "sextant-jvm maven com.acme/orders-service 1.0.0 "
ROUTES = _MODULE + "com/acme/orders/OrderRoutes#routes(sig_00000001)."
HANDLER = _MODULE + "com/acme/orders/OrderRoutes#routes$lambda$1(sig_00000002)."
OTHER_HANDLER = _MODULE + "com/acme/orders/OrderRoutes#routes$lambda$2(sig_00000003)."
CATALOG = "invented-dsl"


def _catalog() -> Catalog:
    """An inbound catalog declaring none of §5's keys — the case every shipped catalog is
    in until its own task lands."""
    return Catalog(
        id=CATALOG,
        style="combinator",
        protocol="http",
        direction="inbound",
        requires=(),
        matches={},
        source=Path("tests/invented.yml"),
        wrappers=[],
        nullability={},
        serialization={},
        known_types=[],
    )


def _workspace(
    tmp_path: Path,
    *rows: tuple[str, str, str, str, str | None],
    signature: dict[str, object] | None = None,
    catalog_id: str = CATALOG,
) -> DuckDbWorkspace:
    """A workspace holding exactly the inbound endpoint rows a test names, as
    `(protocol, method, path, handler, caller)` — the columns an engine mints a route
    with, `catalog_id` fixed — and an empty `route_requirements` stash, the way the
    pipeline leaves both before this pass runs. `signature` is the handler's symbol
    signature as `derive_endpoints.sql` copies it onto `handler_signature` (JSON text),
    NULL when a test names none."""
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.derive("endpoint_metadata_reset")
    workspace.derive("route_requirements_reset")
    for protocol, method, path, handler, caller in rows:
        workspace._connection.execute(
            "INSERT INTO endpoints (protocol, direction, method, path, handler, caller, "
            "catalog_id, handler_signature) VALUES (?, 'inbound', ?, ?, ?, ?, ?, ?)",
            [
                protocol,
                method,
                path,
                handler,
                caller,
                catalog_id,
                None if signature is None else json.dumps(signature),
            ],
        )
    return workspace


def _stash(
    workspace: DuckDbWorkspace,
    handler: str,
    name: str,
    requirement: str | None,
    **overrides: object,
) -> None:
    workspace.derive(
        "route_requirements_insert",
        rows=[
            {
                "caller": ROUTES,
                "handler": handler,
                "method": "GET",
                "path": "/orders",
                "catalog_id": CATALOG,
                "kind": "header",
                "name": name,
                "value": None,
                "requirement": requirement,
                "resolution": "resolved",
                "evidence": "compiler",
                **overrides,
            }
        ],
    )


def _entries(workspace: DuckDbWorkspace) -> list[dict[str, object]]:
    return [dict(row) for row in workspace.query("endpoint_metadata")]


def test_nothing_declared_writes_nothing(tmp_path: Path):
    """An inbound endpoint, a catalog declaring none of §5's keys and an empty stash: the
    table stays empty. Not an entry with every column NULL — the absence of a row is the
    statement "the code states nothing", and a NULL row would be a different one."""
    workspace = _workspace(tmp_path, ("http", "GET", "/orders", HANDLER, ROUTES))
    record_request_requirements(workspace, [_catalog()])
    entries = _entries(workspace)
    workspace.close()

    assert entries == []


def test_the_stash_is_joined_to_its_row_and_carries_the_rows_final_protocol(tmp_path: Path):
    """§4d/§5a: the combinator stashes a requirement under the columns it minted the route
    with — `(caller, handler, method, path, catalog_id)` — and this pass, running after
    `apply_protocol_hints`, writes it against the row as it stands THEN: the row's own
    `protocol` (reclassified to `sse` here, the stash knowing nothing of it), `caller` the
    handler, `direction` inbound. A stash row whose route no longer exists — the engine
    refused it, or another catalog's row won the address — is dropped rather than written
    against nothing."""
    workspace = _workspace(tmp_path, ("sse", "GET", "/orders", HANDLER, ROUTES))
    _stash(workspace, HANDLER, "X-Api-Version", "required", value="2")
    _stash(workspace, HANDLER, "debug", None, kind="query")
    _stash(workspace, OTHER_HANDLER, "X-Orphan", "required")
    record_request_requirements(workspace, [_catalog()])
    entries = _entries(workspace)
    workspace.close()

    assert entries == [
        {
            "protocol": "sse",
            "direction": "inbound",
            "method": "GET",
            "path": "/orders",
            "caller": HANDLER,
            "kind": "header",
            "name": "X-Api-Version",
            "value": "2",
            "resolution": "resolved",
            "evidence": "compiler",
            "requirement": "required",
        },
        {
            "protocol": "sse",
            "direction": "inbound",
            "method": "GET",
            "path": "/orders",
            "caller": HANDLER,
            "kind": "query",
            "name": "debug",
            "value": None,
            "resolution": "resolved",
            "evidence": "compiler",
            "requirement": None,
        },
    ]


# --- §5b `request_params` ----------------------------------------------------------

# Invented annotation and type names, in the dotted form a catalog spells them; the
# facts spell the same names as descriptors (`com/acme/web/Query#`), which is the seam
# `_catalog_symbol` crosses once, at comparison.
QUERY = "com.acme.web.Query"
HEADER = "com.acme.web.Header"
NULLABLE = "com.acme.lang.Nullable"
OPTIONAL_TYPE = "com.acme.lang.Maybe"
WHOLE_MAP = "com.acme.lang.Bag"
BINDER_ENTRY = {
    "annotation": QUERY,
    "kind": "param",
    "name_attrs": ["name", "value"],
    "requirement": "binder",
    "required_attr": "required",
    "default_attr": "defaultValue",
    "optional_types": [OPTIONAL_TYPE],
    "skip_types": [WHOLE_MAP, "com.acme.lang.MultiBag"],
}
OPTIONAL_ENTRY = {
    "annotation": HEADER,
    "kind": "header",
    "name_attrs": ["value"],
    "requirement": "optional",
    "default_annotation": "com.acme.web.DefaultValue",
}


def _params_catalog(
    *entries: dict[str, object], nullable: tuple[str, ...] = (NULLABLE,), catalog_id: str = CATALOG
) -> Catalog:
    """An inbound annotation catalog declaring `request_params` and — as its shape
    model would hand it — the `nullability.nullable` spellings the binder rule reads."""
    return Catalog(
        id=catalog_id,
        style="annotation_driven",
        protocol="http",
        direction="inbound",
        requires=(),
        matches={"request_params": list(entries)},
        source=Path("tests/invented-params.yml"),
        wrappers=[],
        nullability={"nullable": list(nullable)},
        serialization={},
        known_types=[],
    )


def _descriptor(dotted: str) -> str:
    return dotted.replace(".", "/") + "#"


def _parameter(
    name: str | None = "q",
    *,
    erased: str | None = "java/lang/String#",
    annotations: list[dict[str, object]] | None = None,
    nullable: bool = True,
    **extra: object,
) -> dict[str, object]:
    """One signature parameter as the extractor writes it (D00 §5a): a Java `String`
    by default — whose type reference is `nullable: true` by LANGUAGE RULE — carrying
    one `@Query` with the given `args`. `name=None` is a parameter compiled without
    names; `erased=None` a parameter the scanner could not type."""
    parameter: dict[str, object] = {
        "annotations": annotations if annotations is not None else [_use(QUERY)],
        "type": {"symbol": erased or "", "nullable": nullable, "arguments": []},
        "type_annotations": [],
        **extra,
    }
    if name is not None:
        parameter["name"] = name
    if erased is not None:
        parameter["erased_symbol"] = erased
    return parameter


def _use(dotted: str, **args: object) -> dict[str, object]:
    return {"annotation": _descriptor(dotted), "args": args}


def _signature(*parameters: dict[str, object]) -> dict[str, object]:
    return {"parameters": list(parameters), "returns": {"symbol": "void#"}}


def _row(name: object, requirement: object, **overrides: object) -> dict[str, object]:
    return {
        "protocol": "http",
        "direction": "inbound",
        "method": "GET",
        "path": "/orders",
        "caller": HANDLER,
        "kind": "param",
        "name": name,
        "value": None,
        "resolution": "resolved",
        "evidence": "compiler",
        "requirement": requirement,
        **overrides,
    }


def _run(
    tmp_path: Path, signature: dict[str, object] | None, *catalogs: Catalog, path: str = "/orders"
) -> list:
    tmp_path.mkdir(exist_ok=True)
    workspace = _workspace(tmp_path, ("http", "GET", path, HANDLER, ROUTES), signature=signature)
    record_request_requirements(workspace, list(catalogs) or [_params_catalog(BINDER_ENTRY)])
    entries = _entries(workspace)
    workspace.close()
    return entries


def test_binder_writes_required_when_nothing_makes_the_parameter_optional(tmp_path: Path):
    """CP-25 row 2: with no `defaultValue`, `required` at its default and
    `isOptional()` false, Spring calls `handleMissingValue` — a 400. The row states
    that: `kind` from the entry, `name` from the parameter (no name attribute written),
    `value` NULL (an annotation names, it never demands a value), `caller` the handler,
    `evidence: compiler` — the class file said all of it."""
    assert _run(tmp_path, _signature(_parameter("q"))) == [_row("q", "required")]


def test_the_language_rule_nullable_type_alone_is_still_required(tmp_path: Path):
    """The near-miss the ruling of 2026-09-20 was made on. A Java `String` parameter's
    type reference is `nullable: true` at `resolution: resolved` because the LANGUAGE
    says every reference type may be null (D00 §5), and Spring's
    `hasNullableAnnotation()` reads the parameter's declaration annotations by simple
    name and never the type (CP-25 row 3) — so a request without this value is
    rejected, and `optional` here would claim the framework serves what it refuses."""
    signature = _signature(_parameter("q", nullable=True, annotations=[_use(QUERY)]))
    assert _run(tmp_path, signature) == [_row("q", "required")]


@pytest.mark.parametrize(
    ("label", "parameter"),
    [
        ("required=false", _parameter("q", annotations=[_use(QUERY, required=False)])),
        ("defaultValue written", _parameter("q", annotations=[_use(QUERY, defaultValue="0")])),
        ("defaultValue written empty", _parameter("q", annotations=[_use(QUERY, defaultValue="")])),
        (
            "one of the entry's optional_types",
            _parameter("q", erased=_descriptor(OPTIONAL_TYPE), nullable=False),
        ),
        (
            "a declaration annotation the shape model lists as nullable",
            _parameter("q", annotations=[_use(NULLABLE), _use(QUERY)]),
        ),
        ("declares a default", _parameter("q", nullable=False, declares_default=True)),
    ],
    ids=lambda value: value if isinstance(value, str) else "",
)
def test_each_binder_disjunct_alone_flips_the_parameter_to_optional(
    tmp_path: Path, label: str, parameter: dict[str, object]
):
    """CP-25 rows 2, 3 and 5, one disjunct at a time. `required = false` is the
    attribute's own literal `false`; a WRITTEN `defaultValue` — even the empty string —
    is present in the annotation's `args` and an unwritten one is not (row 5:
    `#14(#15=s#16)` against `#14()`), so presence is the test; the optional-value
    container the entry names (`java.util.Optional` on the shipped catalogs) is
    `isOptional()`'s first disjunct; an annotation in the shape model's `nullable` list
    is its second (kotlinc emits one of those on every public nullable parameter, so a
    nullable type reaches here without the language being named); `declares_default`
    is the Kotlin delegate's `KParameter.isOptional()` (R1)."""
    assert _run(tmp_path, _signature(parameter)) == [_row("q", "optional")]


@pytest.mark.parametrize(
    "spelling",
    [
        "jakarta.annotation.Nullable",
        "io.micronaut.core.annotation.Nullable",
        "javax.annotation.Nullable",
        "org.jetbrains.annotations.Nullable",
        "org.jspecify.annotations.Nullable",
        "edu.umd.cs.findbugs.annotations.Nullable",
        "androidx.annotation.Nullable",
        "org.eclipse.jdt.annotation.Nullable",
        "reactor.util.annotation.Nullable",
        "io.reactivex.annotations.Nullable",
        "io.reactivex.rxjava3.annotations.Nullable",
        "org.springframework.lang.Nullable",
        "org.checkerframework.checker.nullness.qual.Nullable",
    ],
)
def test_every_measured_nullable_spelling_in_the_shipped_shape_model_flips_to_optional(
    tmp_path: Path, spelling: str
):
    """The SHIPPED list, not an invented one: CP-25 row 8's eleven (the stereotype and the
    ten spellings Micronaut's processor maps onto it), plus the two more Spring's
    simple-name rule accepts in real code. A spelling missing from `shape-models/json.yml`
    reads `required` on a parameter both binders serve without — the false positive the
    2026-09-20 ruling forbids — so each is pinned against the file itself."""
    shipped = next(c for c in YamlCatalogSource(CATALOGS).load() if c.nullability.get("nullable"))
    assert spelling in shipped.nullability["nullable"], spelling
    catalog = _params_catalog(BINDER_ENTRY, nullable=tuple(shipped.nullability["nullable"]))
    signature = _signature(_parameter("q", annotations=[_use(spelling), _use(QUERY)]))
    assert _run(tmp_path, signature, catalog) == [_row("q", "optional")]


def test_required_true_written_out_stays_required(tmp_path: Path):
    """A literal `true` is not the absence of `false`: the attribute check compares
    against `False` itself, not against presence — the paired positive for the
    `required=false` flip."""
    signature = _signature(_parameter("q", annotations=[_use(QUERY, required=True)]))
    assert _run(tmp_path, signature) == [_row("q", "required")]


def test_the_optional_rule_is_optional_whatever_the_parameter_says(tmp_path: Path):
    """JAX-RS's rule (CP-25 rows 9–10): absent → null or `@DefaultValue`, never a 400.
    A plain, non-null, name-only parameter is `optional`; `default_annotation` is
    informational and changes nothing."""
    signature = _signature(
        _parameter("X-Trace", nullable=False, annotations=[_use(HEADER, value="X-Trace-Id")])
    )
    entries = _run(tmp_path, signature, _params_catalog(OPTIONAL_ENTRY))
    assert entries == [_row("X-Trace-Id", "optional", kind="header")]


def test_name_is_the_first_present_name_attribute_else_the_parameters_own(tmp_path: Path):
    """`name_attrs` in order — `name` wins over `value` when both are written, `value`
    serves when `name` is not — and an EMPTY string literal is not a name (Spring's
    `@AliasFor` pair defaults to `""`, which means "take the parameter's"), so it falls
    through to the parameter's declared name."""
    signature = _signature(
        _parameter("a", annotations=[_use(QUERY, name="fromName", value="fromValue")]),
        _parameter("b", annotations=[_use(QUERY, value="fromValue")]),
        _parameter("c", annotations=[_use(QUERY, name="", value="")]),
    )
    assert {(e["name"], e["requirement"]) for e in _run(tmp_path, signature)} == {
        ("fromName", "required"),
        ("fromValue", "required"),
        ("c", "required"),
    }


def test_a_parameter_with_no_name_anywhere_is_an_unresolved_row(tmp_path: Path):
    """A class compiled without `-parameters` and no `LocalVariableTable` states no
    name (D00 §5a), and the annotation wrote none: the handler binds SOMETHING it does
    not name, which is a different statement from binding nothing — `name` NULL,
    `resolution: unresolved`, the requirement still what the binder enforces."""
    signature = _signature(_parameter(None))
    assert _run(tmp_path, signature) == [_row(None, "required", resolution="unresolved")]


@pytest.mark.parametrize("erased", [_descriptor(WHOLE_MAP), _descriptor("com.acme.lang.MultiBag")])
def test_a_whole_map_binding_is_skipped(tmp_path: Path, erased: str):
    """`@RequestParam Map<String, String> all` binds EVERY parameter and names none;
    a row for it would name the parameter variable as a request parameter. Skipped,
    the types stated on the entry's `skip_types` (§5b) — every one of them, not the
    first alone."""
    assert _run(tmp_path, _signature(_parameter("all", erased=erased))) == []


def test_an_unreadable_parameter_is_a_miss_never_required(tmp_path: Path):
    """Controller resolution 1: a signature that is SQL NULL, and a parameter the
    scanner could not type (no `erased_symbol`), each write nothing for what cannot be
    read — silence is a miss, `required` would be a claim. The readable sibling in the
    same signature still derives."""
    assert _run(tmp_path / "null-signature", None) == []
    signature = _signature(_parameter("untyped", erased=None), _parameter("q"))
    assert _run(tmp_path / "untyped-parameter", signature) == [_row("q", "required")]


def test_a_use_whose_args_were_never_read_writes_nothing(tmp_path: Path):
    """D00 §5a: past the nesting bound the scanner records `{annotation, unresolved:
    depth_limit}` with NO `args` key — an empty `args` would read as an annotation
    written with none. An attribute list that was never opened states nothing about
    `required` or `defaultValue`, so the parameter gets no row rather than a `required`
    off a list nobody read; the readable sibling still derives."""
    unread = _parameter(
        "q", annotations=[{"annotation": _descriptor(QUERY), "unresolved": "depth_limit"}]
    )
    assert _run(tmp_path, _signature(unread, _parameter("r"))) == [_row("r", "required")]


@pytest.mark.parametrize(
    ("path", "variable"),
    [
        ("/orders/:id", "id"),
        ("/orders/{id}", "id"),
        ("/orders/{id?}", "id"),
        ("/files/{rest...}", "rest"),
    ],
    ids=["colon", "braces", "optional-suffix", "tailcard"],
)
def test_a_name_that_is_one_of_the_rows_path_variables_is_skipped_when_the_entry_says_so(
    tmp_path: Path, path: str, variable: str
):
    """`skip_path_variables: true` (reactive routes' `@Param`, CP-25 row 12: Vert.x's
    `getParam` serves path and query parameters alike): a name equal to one of the row's
    own path variables — `:name`, `{name}`, with A6's `?`/`...` suffixes stripped — is the
    path segment, not a query parameter, and gets no row. The query parameter beside it
    on the same handler still derives, which is the paired positive."""
    entry = {**OPTIONAL_ENTRY, "kind": "query", "skip_path_variables": True}
    signature = _signature(
        _parameter(variable, annotations=[_use(HEADER)]),
        _parameter("verbose", annotations=[_use(HEADER)]),
    )
    entries = _run(tmp_path, signature, _params_catalog(entry), path=path)
    assert entries == [_row("verbose", "optional", kind="query", path=path)]


def test_a_path_variable_name_still_derives_where_the_entry_does_not_skip(tmp_path: Path):
    """The near-miss's other side: an entry without `skip_path_variables` (Spring,
    JAX-RS, Micronaut — their path binding is a different annotation) writes the row
    whatever the path spells, because there `@RequestParam id` under `/{id}` really is
    a second, query-borne `id`."""
    signature = _signature(_parameter("id"))
    assert _run(tmp_path, signature, path="/orders/{id}") == [
        _row("id", "required", path="/orders/{id}")
    ]


def test_an_annotation_no_entry_names_writes_nothing(tmp_path: Path):
    """`@PathVariable`, `@RequestBody`, a validation annotation: not in
    `request_params`, not a row. And a catalog declaring `request_params` for a handler
    whose parameters carry nothing it names writes nothing — the absence of a row is
    the statement."""
    signature = _signature(_parameter("id", annotations=[_use("com.acme.web.PathVariable")]))
    assert _run(tmp_path, signature) == []


def test_only_the_owning_catalog_reads_a_row(tmp_path: Path):
    """`catalog_id` ownership (2E-prep §1a), as `request_body` has it: a catalog's
    `request_params` describe the rows its own rules minted. Another catalog's row —
    even one whose handler carries the very annotation — is not this catalog's to
    describe."""
    workspace = _workspace(
        tmp_path,
        ("http", "GET", "/orders", HANDLER, ROUTES),
        signature=_signature(_parameter("q")),
        catalog_id="somebody-else",
    )
    record_request_requirements(workspace, [_params_catalog(BINDER_ENTRY)])
    entries = _entries(workspace)
    workspace.close()
    assert entries == []


def test_the_nullable_spellings_are_the_union_of_every_loaded_catalogs(tmp_path: Path):
    """A catalog with no shape model (`micronaut-http.yml`, `quarkus-reactive-routes.yml`)
    carries an empty `nullability`, and a `Nullable` spelling is a `Nullable` spelling
    whichever catalog's model listed it (ruled 2026-09-20): the binder reads the union
    across the catalogs the run loaded, so the second catalog here lends its list to
    the first."""
    signature = _signature(_parameter("q", annotations=[_use(NULLABLE), _use(QUERY)]))
    bare = _params_catalog(BINDER_ENTRY, nullable=())
    lender = _params_catalog(nullable=(NULLABLE,), catalog_id="lender")
    assert _run(tmp_path, signature, bare, lender) == [_row("q", "optional")]


def test_every_row_sharing_the_handler_gets_the_entries(tmp_path: Path):
    """A handler mapped to two verbs is two `endpoints` rows with one signature; each
    row is an identity of its own and each carries the requirement (the signature is
    parsed once per handler, GUIDELINES §8.7, which no assertion can see — the two
    rows can)."""
    workspace = _workspace(
        tmp_path,
        ("http", "GET", "/orders", HANDLER, ROUTES),
        ("http", "HEAD", "/orders", HANDLER, ROUTES),
        signature=_signature(_parameter("q")),
    )
    record_request_requirements(workspace, [_params_catalog(BINDER_ENTRY)])
    entries = _entries(workspace)
    workspace.close()
    assert sorted(e["method"] for e in entries) == ["GET", "HEAD"]
    assert {e["name"] for e in entries} == {"q"}


@pytest.mark.parametrize(
    ("declared", "names"),
    [
        ({"request_params": {"annotation": QUERY}}, "must be a list"),
        ({"request_params": [{**BINDER_ENTRY, "kind": "form"}]}, "kind"),
        ({"request_params": [{**BINDER_ENTRY, "requirement": "required"}]}, "requirement"),
        ({"request_params": [{**BINDER_ENTRY, "name_attrs": "name"}]}, "name_attrs"),
        (
            {"request_params": [{k: v for k, v in BINDER_ENTRY.items() if k != "annotation"}]},
            "annotation",
        ),
        ({"request_params": [{**BINDER_ENTRY, "requried_attr": "required"}]}, "requried_attr"),
        ({"request_params": [{**BINDER_ENTRY, "skip_types": WHOLE_MAP}]}, "skip_types"),
        (
            {"request_params": [{**BINDER_ENTRY, "skip_path_variables": "yes"}]},
            "skip_path_variables",
        ),
    ],
    ids=[
        "not-a-list",
        "kind",
        "requirement",
        "name_attrs",
        "annotation",
        "misspelt-key",
        "skip_types",
        "skip_path_variables",
    ],
)
def test_a_malformed_request_params_entry_is_refused_naming_the_file(
    tmp_path: Path, declared: dict[str, object], names: str
):
    """The vocabulary is closed for `request_body`'s reason: a misspelt key read as
    absent turns the rule the author wrote into a different one silently —
    `requried_attr` would make every `required = false` parameter `required`. Refused
    with a `CatalogError` naming the file, at the pass's first use, which is where the
    other `matches` blocks are checked."""
    catalog = Catalog(
        id=CATALOG,
        style="annotation_driven",
        protocol="http",
        direction="inbound",
        requires=(),
        matches=declared,
        source=Path("tests/invented-params.yml"),
        wrappers=[],
        nullability={},
        serialization={},
        known_types=[],
    )
    workspace = _workspace(
        tmp_path, ("http", "GET", "/orders", HANDLER, ROUTES), signature=_signature(_parameter("q"))
    )
    with pytest.raises(CatalogError, match=r"invented-params\.yml") as raised:
        record_request_requirements(workspace, [catalog])
    workspace.close()
    assert names in str(raised.value)


# --- §5c `mapping.request_requirement_attrs` -----------------------------------------

# Invented mapping annotations, the routing-conflicts test's own pair: one per-verb
# annotation and one class-level prefix annotation, both carrying the two attributes.
GET_MAPPING = "com.acme.web.Get"
CLASS_MAPPING = "com.acme.web.Path"
CONTROLLER = "com/acme/orders/ParamsController#"
METHOD = CONTROLLER + "search(sig_00000011)."
OTHER_METHOD = CONTROLLER + "list(sig_00000012)."
ATTRS = {"params": "param", "headers": "header"}


def _document() -> Document:
    return Document(
        document_id="doc",
        relative_path="com/acme/orders/ParamsController.class",
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


def _mapping_catalog(attrs: object = ATTRS, catalog_id: str = CATALOG) -> Catalog:
    """An inbound annotation catalog whose mapping block declares
    `request_requirement_attrs` — the same `annotations`/`prefix_annotation` shape
    `routing_conflicts` reads discriminators through."""
    mapping: dict[str, object] = {
        "annotations": [{"fqn": GET_MAPPING, "method": ["GET"]}],
        "prefix_annotation": CLASS_MAPPING,
    }
    if attrs is not None:
        mapping["request_requirement_attrs"] = attrs
    return Catalog(
        id=catalog_id,
        style="annotation_driven",
        protocol="http",
        direction="inbound",
        requires=(),
        matches={"mapping": mapping},
        source=Path("tests/invented-mapping.yml"),
        wrappers=[],
        nullability={},
        serialization={},
        known_types=[],
    )


def _annotated(target: str, annotation: str, **args: object) -> AnnotationFact:
    """One mapping annotation on a method or its class, as the extractor writes it —
    attribute values as the class file carries them, a `String[]` attribute a list."""
    return AnnotationFact(
        document_id="doc",
        target=_MODULE + target,
        use=AnnotationUse(annotation=_descriptor(annotation), args=args),  # type: ignore[arg-type]
        retention="RUNTIME",
    )


def _mapping_workspace(
    tmp_path: Path, annotations: list[AnnotationFact], *rows: tuple[str, str, str | None]
) -> DuckDbWorkspace:
    """Annotation facts loaded, then the inbound rows a test names as `(method, path,
    handler)` — `handler` None a row naming no handler."""
    write_fact_file(tmp_path / "facts" / "ParamsController.jsonl", _document(), annotations)
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    workspace.derive("endpoint_metadata_reset")
    workspace.derive("route_requirements_reset")
    for method, path, handler in rows:
        workspace._connection.execute(
            "INSERT INTO endpoints (protocol, direction, method, path, handler, caller, "
            "catalog_id) VALUES ('http', 'inbound', ?, ?, ?, ?, ?)",
            [method, path, None if handler is None else _MODULE + handler, None, CATALOG],
        )
    return workspace


def _mapping_rows(
    tmp_path: Path,
    annotations: list[AnnotationFact],
    *rows: tuple[str, str, str | None],
    catalog: Catalog | None = None,
) -> set[tuple]:
    """`(method, path, handler, kind, name, value, requirement, resolution)` per row
    written, the handler as its bare descriptor."""
    if not rows:
        rows = (("GET", "/orders", METHOD),)
    workspace = _mapping_workspace(tmp_path, annotations, *rows)
    record_request_requirements(workspace, [catalog or _mapping_catalog()])
    entries = _entries(workspace)
    workspace.close()
    return {
        (
            e["method"],
            e["path"],
            None if e["caller"] is None else str(e["caller"]).removeprefix(_MODULE),
            e["kind"],
            e["name"],
            e["value"],
            e["requirement"],
            e["resolution"],
        )
        for e in entries
    }


@pytest.mark.parametrize(
    ("expression", "parsed"),
    [
        ("v", ("v", None, "required")),
        ("v=1", ("v", "1", "required")),
        ("!legacy", ("legacy", None, "absent")),
        ("v!=2", ("v", None, "optional")),
        # `name=` is a written empty value: required, and the value IS the empty string.
        ("v=", ("v", "", "required")),
        # A `=` inside the value stays in the value — only the FIRST `=` separates.
        ("q=a=b", ("q", "a=b", "required")),
        ("", None),
        ("=1", None),
        ("!", None),
        ("!=1", None),
    ],
)
def test_the_expression_grammar_is_the_frameworks_own(
    expression: str, parsed: tuple[str, str | None, str] | None
):
    """CP-25 row 13, `AbstractNameValueExpression(String)`: the first `=` splits name from
    value; with none, a leading `!` negates (`!name` → the framework requires the name
    to be ABSENT); with one, a `!` just before it negates (`name!=v` → served whenever
    the value is not `v`, absent included — `optional`, the excluded value lost, stated
    on the catalog). An empty name parses in Spring and matches nothing a client could
    send, so here it is None — skipped, never a nameless row."""
    assert _expression(expression) == parsed


def test_method_and_class_expressions_union_into_one_row_each(tmp_path: Path):
    """§5c: `ParamsRequestCondition.combine` adds the class's expressions to the method's
    — union, the same read `routing_conflicts._discriminators` makes — so a method under
    `@Path(params = "tenant")` carrying `@Get(params = "v=1", headers = "!X-Legacy")`
    demands all three: `v` = `1` required, `X-Legacy` absent, `tenant` required.
    `kind` is the attribute's, per the catalog (`params` → `param`: Spring cannot tell
    query from form through it); `caller` the handler; `evidence: compiler`."""
    annotations = [
        _annotated(METHOD, GET_MAPPING, value=["/orders"], params=["v=1"], headers=["!X-Legacy"]),
        _annotated(CONTROLLER, CLASS_MAPPING, params=["tenant"]),
    ]
    assert _mapping_rows(tmp_path, annotations) == {
        ("GET", "/orders", METHOD, "param", "v", "1", "required", "resolved"),
        ("GET", "/orders", METHOD, "header", "X-Legacy", None, "absent", "resolved"),
        ("GET", "/orders", METHOD, "param", "tenant", None, "required", "resolved"),
    }


def test_a_class_level_expression_reaches_every_method_and_a_method_level_one_its_own(
    tmp_path: Path,
):
    """The union's other face: the class's `tenant` lands on both handlers, `search`'s own
    `v=1` on `search` alone — `list` carries no attribute of its own and still gets the
    class's."""
    annotations = [
        _annotated(METHOD, GET_MAPPING, value=["/orders"], params=["v=1"]),
        _annotated(OTHER_METHOD, GET_MAPPING, value=["/all"]),
        _annotated(CONTROLLER, CLASS_MAPPING, params=["tenant"]),
    ]
    rows = _mapping_rows(
        tmp_path, annotations, ("GET", "/orders", METHOD), ("GET", "/all", OTHER_METHOD)
    )
    assert rows == {
        ("GET", "/orders", METHOD, "param", "v", "1", "required", "resolved"),
        ("GET", "/orders", METHOD, "param", "tenant", None, "required", "resolved"),
        ("GET", "/all", OTHER_METHOD, "param", "tenant", None, "required", "resolved"),
    }


def test_accept_and_content_type_header_expressions_are_skipped(tmp_path: Path):
    """A4, CP-25 row 4: `HeadersRequestCondition.parseExpressions` drops an expression
    whose name `equalsIgnoreCase` `Accept` or `Content-Type` — Spring routes those two
    into produces/consumes — so a `headers=` naming either, in any case, writes nothing,
    while the header beside them does. The skip is a HEADER rule: a `params = "Accept"`
    is an ordinary request parameter and still derives."""
    annotations = [
        _annotated(
            METHOD,
            GET_MAPPING,
            value=["/orders"],
            headers=["Accept=application/json", "content-type=text/xml", "X-Api"],
            params=["Accept"],
        ),
    ]
    assert _mapping_rows(tmp_path, annotations) == {
        ("GET", "/orders", METHOD, "header", "X-Api", None, "required", "resolved"),
        ("GET", "/orders", METHOD, "param", "Accept", None, "required", "resolved"),
    }


def test_a_malformed_expression_is_skipped_and_the_rest_derive(tmp_path: Path):
    """An empty expression, a bare `!`, a `=v` with no name: each parses to no name and
    is skipped rather than written as a nameless requirement; the well-formed sibling
    in the same attribute derives. A scalar attribute (one expression written without
    the array braces reaches the class file as a one-element array; the scalar form is
    the reader's tolerance, as `_discriminators` has it) reads the same as a list."""
    annotations = [
        _annotated(METHOD, GET_MAPPING, value=["/orders"], params=["", "!", "=v", "page"]),
        _annotated(CONTROLLER, CLASS_MAPPING, headers="X-Tenant=acme"),
    ]
    assert _mapping_rows(tmp_path, annotations) == {
        ("GET", "/orders", METHOD, "param", "page", None, "required", "resolved"),
        ("GET", "/orders", METHOD, "header", "X-Tenant", "acme", "required", "resolved"),
    }


def test_mapping_attributes_write_nothing_where_nothing_is_written(tmp_path: Path):
    """A mapping with neither attribute, a row naming no handler, a row another catalog
    owns: each writes nothing — the absence of a row is the statement."""
    annotations = [
        _annotated(METHOD, GET_MAPPING, value=["/orders"]),
        _annotated(OTHER_METHOD, GET_MAPPING, value=["/all"], params=["v=1"]),
    ]
    assert _mapping_rows(tmp_path, annotations, ("GET", "/orders", METHOD)) == set()
    assert _mapping_rows(tmp_path / "no-handler", annotations, ("GET", "/all", None)) == set()
    workspace = _mapping_workspace(
        tmp_path / "other-owner", annotations, ("GET", "/all", OTHER_METHOD)
    )
    record_request_requirements(workspace, [_mapping_catalog(catalog_id="somebody-else")])
    entries = _entries(workspace)
    workspace.close()
    assert entries == []


def test_every_row_sharing_the_handler_gets_the_mapping_expressions(tmp_path: Path):
    """A verbless mapping fans out to one row per verb, one handler; each row carries the
    expression (read once per handler, GUIDELINES §8.7)."""
    annotations = [_annotated(METHOD, GET_MAPPING, value=["/orders"], params=["v=1"])]
    rows = _mapping_rows(
        tmp_path, annotations, ("GET", "/orders", METHOD), ("HEAD", "/orders", METHOD)
    )
    assert {(r[0], r[4], r[5]) for r in rows} == {("GET", "v", "1"), ("HEAD", "v", "1")}


@pytest.mark.parametrize(
    ("attrs", "names"),
    [
        (["params", "headers"], "must be a mapping"),
        ({"params": "form"}, "kind"),
        ({3: "param"}, "attribute"),
    ],
    ids=["not-a-mapping", "kind", "attribute"],
)
def test_a_malformed_request_requirement_attrs_block_is_refused_naming_the_file(
    tmp_path: Path, attrs: object, names: str
):
    """The vocabulary is closed for the same reason `request_params`' is: a kind outside
    D01 §3's set, or a block of the wrong shape, is refused with a `CatalogError` naming
    the file at the pass's first use."""
    annotations = [_annotated(METHOD, GET_MAPPING, value=["/orders"], params=["v=1"])]
    workspace = _mapping_workspace(tmp_path, annotations, ("GET", "/orders", METHOD))
    with pytest.raises(CatalogError, match=r"invented-mapping\.yml") as raised:
        record_request_requirements(workspace, [_mapping_catalog(attrs)])
    workspace.close()
    assert names in str(raised.value)


# --- §5d `request_reads` -------------------------------------------------------------

# Invented request types. `Request` is read through OWNER entries (a call's own owner and
# name); `Call` is the container getter a `via` entry names — the read itself is a `get`
# on whatever the getter returned, told apart by the getter that produced the receiver.
REQUEST = "com.acme.web.Request"
CALL = "com.acme.web.Call"
VALIDATOR = "com.acme.web.Checked"
HEADER_READ = {"owner": REQUEST, "method": "header", "arity": 1, "name_arg": 0, "kind": "header"}
PARAM_READ = {"owner": REQUEST, "method": "param", "arity": 1, "name_arg": 0, "kind": "param"}
DEMAND = {
    "owner": REQUEST,
    "method": "demand",
    "arity": 2,
    "name_arg": 1,
    "kind": "query",
    "requirement": "required",
}
TYPED = {
    "owner": REQUEST,
    "method": "typed",
    "arity": 2,
    "name_arg": 0,
    "kind": "query",
    "then": {"method": "get", "requirement": "required"},
}
QUERY_VIA = {
    "via": {"owner": CALL, "method": "getQuery"},
    "method": "get",
    "arity": 1,
    "name_arg": 0,
    "kind": "query",
}
ALL_VIA = {
    "via": {"owner": CALL, "method": "getAll"},
    "method": "get",
    "arity": 1,
    "name_arg": 0,
    "kind": "query",
    "skip_path_variables": True,
}
MISSING = "com.acme.web.MissingValue"
THROWN_VIA = {**QUERY_VIA, "required_when_thrown": MISSING}
READS = [HEADER_READ, PARAM_READ, DEMAND, TYPED, THROWN_VIA, ALL_VIA]


def _reads_catalog(*entries: object, catalog_id: str = CATALOG) -> Catalog:
    return Catalog(
        id=catalog_id,
        style="combinator",
        protocol="http",
        direction="inbound",
        requires=(),
        matches={"request_reads": list(entries)},
        source=Path("tests/invented-reads.yml"),
        wrappers=[],
        nullability={},
        serialization={},
        known_types=[],
    )


def _site(
    ordinal: int,
    owner: str,
    name: str,
    *arguments: CallArgument,
    receiver: int | None = None,
    result: int | None = None,
    caller: str = HANDLER,
) -> CallSiteFact:
    """One call in the handler body: `receiver` the value id the call is made on (a
    producing call's `result`, or None for a parameter/field), `result` this call's own
    value id."""
    return CallSiteFact(
        document_id="doc",
        caller=caller,
        target=CallTarget(owner=_descriptor(owner), name=name, descriptor="(...)V"),
        invoke_kind="interface",
        ordinal=ordinal,
        receiver=receiver,
        result=result,
        arguments=list(arguments),
    )


def _literal(value: str) -> CallArgument:
    return CallArgument(kind="string", value=value)


def _reads_workspace(
    tmp_path: Path, sites: list[CallSiteFact], *rows: tuple[str, str, str | None]
) -> DuckDbWorkspace:
    write_fact_file(tmp_path / "facts" / "OrderRoutes.jsonl", _document(), sites)
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    workspace.derive("endpoint_metadata_reset")
    workspace.derive("route_requirements_reset")
    for method, path, handler in rows:
        workspace._connection.execute(
            "INSERT INTO endpoints (protocol, direction, method, path, handler, caller, "
            "catalog_id) VALUES ('http', 'inbound', ?, ?, ?, ?, ?)",
            [method, path, handler, ROUTES, CATALOG],
        )
    return workspace


def _reads(
    tmp_path: Path,
    sites: list[CallSiteFact],
    *rows: tuple[str, str, str | None],
    catalogs: list[Catalog] | None = None,
) -> set[tuple]:
    """`(method, path, kind, name, requirement, resolution)` per row written; every row
    carries `value` NULL, `caller` the handler and `evidence: compiler`, asserted once
    here for all of them."""
    if not rows:
        rows = (("GET", "/orders", HANDLER),)
    workspace = _reads_workspace(tmp_path, sites, *rows)
    record_request_requirements(workspace, catalogs or [_reads_catalog(*READS)])
    entries = _entries(workspace)
    workspace.close()
    handlers = {handler for _, _, handler in rows if handler is not None}
    assert all(
        e["value"] is None and e["caller"] in handlers and e["evidence"] == "compiler"
        for e in entries
    ), entries
    return {
        (e["method"], e["path"], e["kind"], e["name"], e["requirement"], e["resolution"])
        for e in entries
    }


def test_an_owner_read_is_a_row_with_null_requirement_at_its_arity_alone(tmp_path: Path):
    """A3 and F7 (CP-25 rows 14, 16): `request.header("X-Api")` says the handler READS
    the header and nothing more — `requirement` NULL, not `optional`, because the
    framework hands a null through and the handler may `throw` on it. `header("X-Set",
    "1")` is the same name at arity 2 — the response SETTER — and matches no entry: the
    entry carries the arity for exactly this."""
    sites = [
        _site(0, REQUEST, "header", _literal("X-Api"), receiver=None, result=3),
        _site(1, REQUEST, "header", _literal("X-Set"), _literal("1"), receiver=None),
        _site(2, REQUEST, "param", _literal("q"), receiver=None, result=4),
    ]
    assert _reads(tmp_path, sites) == {
        ("GET", "/orders", "header", "X-Api", None, "resolved"),
        ("GET", "/orders", "param", "q", None, "resolved"),
    }


def test_a_via_read_is_told_apart_by_the_getter_that_produced_its_receiver(tmp_path: Path):
    """CP-24 row 6: three containers end in one `get(String)`, so the read's own owner and
    name say nothing about WHICH value it reads; the receiver's PRODUCING call does —
    one `_producing_site` step, the `via` pair. `getQuery()` → `get("q")` is a query
    row. `get` on a receiver produced by a getter no entry names (`getOther`), on a
    receiver produced by nothing in the body (a parameter), or on a value id no site
    produced: no row — a `via` read that cannot name its container is not guessed."""
    sites = [
        _site(0, CALL, "getQuery", receiver=None, result=10),
        _site(1, "com.acme.web.Values", "get", _literal("q"), receiver=10, result=11),
        _site(2, CALL, "getOther", receiver=None, result=20),
        _site(3, "com.acme.web.Values", "get", _literal("other"), receiver=20, result=21),
        _site(4, "com.acme.web.Values", "get", _literal("bare"), receiver=None, result=31),
        _site(5, "com.acme.web.Values", "get", _literal("orphan"), receiver=99, result=41),
    ]
    assert _reads(tmp_path, sites) == {("GET", "/orders", "query", "q", None, "resolved")}


def test_then_makes_the_read_required_only_where_the_result_reaches_the_named_method(
    tmp_path: Path,
):
    """CP-25 row 15: `typed("n", Integer.class).get()` is `required` because the
    framework's `get()` throws on an absent value; the SAME read ending in
    `getOrDefault(1)`, or in nothing at all, stays NULL — the chain never reached the
    throwing method. One result-to-receiver step, the entry's `then`."""
    sites = [
        _site(0, REQUEST, "typed", _literal("n"), CallArgument(kind="class"), result=5),
        _site(1, VALIDATOR, "get", receiver=5, result=6),
        _site(2, REQUEST, "typed", _literal("page"), CallArgument(kind="class"), result=7),
        _site(3, VALIDATOR, "getOrDefault", CallArgument(kind="int", value=1), receiver=7),
        _site(4, REQUEST, "typed", _literal("unread"), CallArgument(kind="class"), result=8),
    ]
    assert _reads(tmp_path, sites) == {
        ("GET", "/orders", "query", "n", "required", "resolved"),
        ("GET", "/orders", "query", "page", None, "resolved"),
        ("GET", "/orders", "query", "unread", None, "resolved"),
    }


def test_required_when_thrown_marks_the_read_whose_name_the_body_throws_for(tmp_path: Path):
    """The inlined throwing read (fix round 1; CP-24 row 5 measured on the fixture's own
    class): `getOrFail` is `inline`, so the caller carries `get(name) ; ifnonnull ; new
    MissingRequestParameterException(name) ; athrow` and never a call to it. The entry's
    `required_when_thrown` names the exception; the read is `required` when the SAME body
    constructs it with the read's OWN name as its first argument — `cursor` here. `page`
    is a bare read beside it and stays NULL: the body throws for `cursor`, not for
    `page`, and a body throwing for another name says nothing about this read. A
    construction whose first argument is not a string literal (`other`) marks nothing;
    a read whose own name is unresolved cannot be equal to anything and stays NULL."""
    sites = [
        _site(0, CALL, "getQuery", result=10),
        _site(1, "com.acme.web.Values", "get", _literal("cursor"), receiver=10, result=11),
        _site(2, MISSING, "<init>", _literal("cursor"), receiver=12),
        _site(3, CALL, "getQuery", result=13),
        _site(4, "com.acme.web.Values", "get", _literal("page"), receiver=13, result=14),
        _site(5, CALL, "getQuery", result=15),
        _site(6, "com.acme.web.Values", "get", _literal("other"), receiver=15, result=16),
        _site(7, MISSING, "<init>", CallArgument(kind="unresolved"), receiver=17),
        _site(8, CALL, "getQuery", result=18),
        _site(9, "com.acme.web.Values", "get", CallArgument(kind="unresolved"), receiver=18),
    ]
    assert _reads(tmp_path, sites) == {
        ("GET", "/orders", "query", "cursor", "required", "resolved"),
        ("GET", "/orders", "query", "page", None, "resolved"),
        ("GET", "/orders", "query", "other", None, "resolved"),
        ("GET", "/orders", "query", None, None, "unresolved"),
    }


def test_an_exception_of_another_type_for_the_same_name_marks_nothing(tmp_path: Path):
    """The type is part of the rule: a handler's own `throw IllegalArgumentException("q")`
    is the handler's word, not the framework's (A3), and the entry names the framework's
    exception alone."""
    sites = [
        _site(0, CALL, "getQuery", result=10),
        _site(1, "com.acme.web.Values", "get", _literal("q"), receiver=10, result=11),
        _site(2, "java.lang.IllegalArgumentException", "<init>", _literal("q"), receiver=12),
    ]
    assert _reads(tmp_path, sites) == {("GET", "/orders", "query", "q", None, "resolved")}


def test_an_entrys_own_requirement_is_written_where_the_api_throws(tmp_path: Path):
    """CP-24 row 5: an API that refuses the request itself (`getOrFail`) is declared
    `requirement: required` on its entry and the row says so — the framework's word,
    not the handler's. `name_arg: 1` reads the second argument, the first being the
    container an extension function receives."""
    sites = [
        _site(0, REQUEST, "demand", CallArgument(kind="parameter", value=0), _literal("cursor"))
    ]
    assert _reads(tmp_path, sites) == {
        ("GET", "/orders", "query", "cursor", "required", "resolved")
    }


@pytest.mark.parametrize("path", ["/orders/{id}", "/orders/{id?}", "/orders/{id...}"])
def test_skip_path_variables_drops_the_rows_own_path_variable(tmp_path: Path, path: str):
    """A6: `call.parameters` merges path and query, so a `get("id")` on it under
    `/orders/{id}` — or Ktor's `{id?}`/`{id...}`, suffixes stripped — is the path
    variable and gets no row; `get("page")` on the same container is a query. The
    entry WITHOUT `skip_path_variables` (`getQuery`) writes `id` whatever the path
    spells, because there `id` really is a second, query-borne value."""
    sites = [
        _site(0, CALL, "getAll", result=10),
        _site(1, "com.acme.web.Values", "get", _literal("id"), receiver=10, result=11),
        _site(2, CALL, "getAll", result=12),
        _site(3, "com.acme.web.Values", "get", _literal("page"), receiver=12, result=13),
        _site(4, CALL, "getQuery", result=14),
        _site(5, "com.acme.web.Values", "get", _literal("id"), receiver=14, result=15),
    ]
    assert _reads(tmp_path, sites, ("GET", path, HANDLER)) == {
        ("GET", path, "query", "page", None, "resolved"),
        ("GET", path, "query", "id", None, "resolved"),
    }


@pytest.mark.parametrize(
    "argument",
    [
        CallArgument(kind="field", symbol="com/acme/web/Names#TRACE."),
        CallArgument(kind="unresolved"),
        CallArgument(kind="parameter", value=0),
    ],
    ids=["field", "unresolved", "parameter"],
)
def test_a_read_whose_name_is_not_a_literal_is_an_unresolved_row(
    tmp_path: Path, argument: CallArgument
):
    """§5a: "this handler reads a header it does not name" is a different statement
    from "reads none" — the row exists with `name` NULL and `resolution: unresolved`,
    `requirement` still the entry's (NULL here)."""
    sites = [_site(0, REQUEST, "header", argument, result=3)]
    assert _reads(tmp_path, sites) == {("GET", "/orders", "header", None, None, "unresolved")}


def test_reads_write_nothing_where_there_is_no_body_to_read(tmp_path: Path):
    """A row naming no handler, and a handler whose body has no call sites (or none an
    entry names): nothing. The absence of a row is the statement."""
    sites = [_site(0, REQUEST, "header", _literal("X-Api"), result=3, caller=OTHER_HANDLER)]
    assert _reads(tmp_path, sites, ("GET", "/orders", None)) == set()
    assert _reads(tmp_path / "no-sites", sites, ("GET", "/orders", HANDLER)) == set()


def test_request_reads_are_the_union_of_every_loaded_catalog_applied_by_handler(
    tmp_path: Path,
):
    """§5d: the lists are unioned and matched against EVERY inbound row's handler body,
    not the declaring catalog's rows alone — Javalin declares its list once and the
    rows its `ApiBuilder` sibling derives get the same reads. Here the row belongs to
    `CATALOG`, which declares nothing, and the entry comes from another catalog that
    owns no row."""
    sites = [_site(0, REQUEST, "header", _literal("X-Api"), result=3)]
    catalogs = [_catalog(), _reads_catalog(HEADER_READ, catalog_id="lender")]
    assert _reads(tmp_path, sites, catalogs=catalogs) == {
        ("GET", "/orders", "header", "X-Api", None, "resolved")
    }


def test_every_row_sharing_the_handler_gets_the_reads(tmp_path: Path):
    """Two verbs, one handler, one body scanned (GUIDELINES §8.7), two rows."""
    sites = [_site(0, REQUEST, "header", _literal("X-Api"), result=3)]
    rows = _reads(tmp_path, sites, ("GET", "/orders", HANDLER), ("HEAD", "/orders", HANDLER))
    assert rows == {
        ("GET", "/orders", "header", "X-Api", None, "resolved"),
        ("HEAD", "/orders", "header", "X-Api", None, "resolved"),
    }


@pytest.mark.parametrize(
    ("entry", "names"),
    [
        ({**HEADER_READ, "kind": "form"}, "kind"),
        ({**HEADER_READ, "requirement": "binder"}, "requirement"),
        ({**HEADER_READ, "requirement": "absent"}, "requirement"),
        ({**HEADER_READ, "method": ["header"]}, "method"),
        ({**HEADER_READ, "required_when_thrown": [MISSING]}, "required_when_thrown"),
        ({**HEADER_READ, "name_arg": 1}, "name_arg"),
        ({**HEADER_READ, "arity": "1"}, "arity"),
        ({**HEADER_READ, "via": {"owner": CALL, "method": "getQuery"}}, "exactly one of"),
        ({k: v for k, v in HEADER_READ.items() if k != "owner"}, "exactly one of"),
        ({**QUERY_VIA, "via": CALL + "#getQuery"}, "via"),
        ({**HEADER_READ, "then": {"requirement": "required"}}, "then"),
        ({**HEADER_READ, "then": {"method": "get", "requirement": "maybe"}}, "then"),
        ({**HEADER_READ, "skip_path_variables": "yes"}, "skip_path_variables"),
        ({**HEADER_READ, "name_args": 0}, "name_args"),
    ],
    ids=[
        "kind",
        "requirement",
        "requirement-absent",
        "method-not-a-name",
        "required_when_thrown",
        "name_arg-beyond-arity",
        "arity-not-int",
        "owner-and-via",
        "neither",
        "via-without-method",
        "then-without-method",
        "then-requirement",
        "skip_path_variables",
        "misspelt-key",
    ],
)
def test_a_malformed_request_reads_entry_is_refused_naming_the_file(
    tmp_path: Path, entry: dict[str, object], names: str
):
    """Closed vocabulary, `request_params`' reason: a misspelt `name_args` read as absent
    would make every read nameless; a `name_arg` beyond the arity can never be read; an
    entry naming both `owner` and `via`, or neither, states two rules or none. `absent`
    is refused on a read: no read API demands a value's absence (a route-tree word,
    §5c). `method` and `required_when_thrown` are names, checked as names rather than
    coerced — a list written by mistake would otherwise match nothing, silently."""
    sites = [_site(0, REQUEST, "header", _literal("X-Api"), result=3)]
    workspace = _reads_workspace(tmp_path, sites, ("GET", "/orders", HANDLER))
    with pytest.raises(CatalogError, match=r"invented-reads\.yml") as raised:
        record_request_requirements(workspace, [_reads_catalog(entry)])
    workspace.close()
    assert names in str(raised.value)


def test_request_reads_must_be_a_list(tmp_path: Path):
    workspace = _reads_workspace(tmp_path, [], ("GET", "/orders", HANDLER))
    catalog = Catalog(
        id=CATALOG,
        style="combinator",
        protocol="http",
        direction="inbound",
        requires=(),
        matches={"request_reads": HEADER_READ},
        source=Path("tests/invented-reads.yml"),
        wrappers=[],
        nullability={},
        serialization={},
        known_types=[],
    )
    with pytest.raises(CatalogError, match=r"invented-reads\.yml.*must be a list"):
        record_request_requirements(workspace, [catalog])
    workspace.close()
