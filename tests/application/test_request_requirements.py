"""The inbound request-requirements pass (spec 2026-09-19 §5a): the writer, the
combinator's `route_requirements` stash joined to the `endpoints` rows it was minted
with, and §5b's `request_params` — the parameter annotations on the handler, read off
`endpoints.handler_signature` against a catalog's `request_params` entries.

The two other mechanisms (§5c mapping attributes, §5d handler reads) arrive in their own
tasks and are tested there; here they return nothing, which is what lets the first test
say that a run with nothing declared writes NOTHING rather than an empty-looking
something.

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
from sextant.application.resolve.request_requirements import record_request_requirements
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
