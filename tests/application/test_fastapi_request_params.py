"""FastAPI request parameters and the request body (plan 2026-11-08-python-fastapi-inbound
Task 7; N3, N4; Review Focus 5).

FastAPI reads a handler parameter's meaning off the marker call that made its default or one of
its `Annotated` metadata elements (`dependencies/utils.py` `analyze_param`, quoted with lines in
`scripts/probes/fastapi_rules.md` §4): `Query`, `Header` and `Cookie` are request parameters,
`Path` is the address's own variable, `Body`/`Form`/`File` are the body, and `Depends`/`Security`
are dependencies (Task 8). A parameter with no marker is the path variable it names, else a query
parameter where its type is a scalar, else the body. The six request types (`Request`,
`Response`, ...) are no parameter at all.

Each test writes a small FastAPI program, scans it with the real Python scanner against the
FastAPI 0.162.0 that `fixtures/orders-fastapi` locks, and runs the real pipeline with the
shipped catalogs (`test_fastapi_routes._resolved`). It then reads `endpoint_metadata` and the
row's `request_shape`.
"""

import json
import shutil
from pathlib import Path

import pytest
import test_fastapi_routes
from test_fastapi_routes import _bare, _handler, _questions, _resolved, _rows

from sextant.application.ports.catalogs import CatalogError
from sextant.ingress.catalogs.yaml_source import YamlCatalogSource
from sextant.resources import catalogs_dir

# The FastAPI environment the route tests read, shared rather than restated.
libraries = test_fastapi_routes.libraries

_HEAD = (
    "from typing import Annotated, Optional\n"
    "from fastapi import APIRouter, BackgroundTasks, Body, Cookie, Depends, Header, Path, Query\n"
    "from fastapi import Request, Response\n"
    "from pydantic import BaseModel\n"
    "router = APIRouter()\n"
    "class Item(BaseModel):\n"
    "    name: str\n"
    "def dep() -> str:\n"
    "    return ''\n"
)


def _params(workspace) -> list[tuple[object, ...]]:
    """Each request parameter as (method, path, kind, name, requirement, resolution)."""
    return sorted(
        (
            (
                row["method"],
                row["path"],
                row["kind"],
                row["name"],
                row["requirement"],
                row["resolution"],
            )
            for row in workspace.query("endpoint_metadata")
            if row["direction"] == "inbound" and row["kind"] in ("query", "header", "cookie")
        ),
        key=lambda row: tuple("" if part is None else str(part) for part in row),
    )


def _bodies(workspace) -> dict[tuple[object, object], str | None]:
    """Each fastapi row's request body: the shape it names, else its wire type, else None."""
    found: dict[tuple[object, object], str | None] = {}
    for row in workspace.query("endpoints"):
        if row["catalog_id"] != "fastapi":
            continue
        shape = row["request_shape"]
        described = None if shape is None else json.loads(shape)
        found[(row["method"], row["path"])] = (
            None if described is None else str(described.get("shape_id") or described["wire_type"])
        )
    return found


def _route(signature: str, path: str = "/x", verb: str = "get") -> dict[str, str]:
    return {
        "main.py": _HEAD
        + f"@router.{verb}('{path}')\ndef handler({signature}) -> str:\n    return ''\n"
    }


def test_a_defaulted_scalar_is_an_optional_query(tmp_path: Path, libraries):
    """Review Focus 5: `limit: int = 10` is a query parameter, optional (`default_value =
    value`)."""
    workspace = _resolved(tmp_path, libraries, _route("limit: int = 10"))

    assert _params(workspace) == [("GET", "/x", "query", "limit", "optional", "resolved")]


def test_optional_without_default_is_required(tmp_path: Path, libraries):
    """Review Focus 5: `q: str | None` and `Optional[int]` with no default are required
    (pydantic v2): only a default makes a parameter optional."""
    workspace = _resolved(tmp_path, libraries, _route("q: str | None, n: Optional[int]"))

    assert _params(workspace) == [
        ("GET", "/x", "query", "n", "required", "resolved"),
        ("GET", "/x", "query", "q", "required", "resolved"),
    ]


def test_query_ellipsis_is_required(tmp_path: Path, libraries):
    """Review Focus 5: `Query(...)` is required (`...` is `RequiredParam`), as is `Query()`,
    whose default is unset though a default expression is written."""
    workspace = _resolved(tmp_path, libraries, _route("q: str = Query(...), r: str = Query()"))

    assert _params(workspace) == [
        ("GET", "/x", "query", "q", "required", "resolved"),
        ("GET", "/x", "query", "r", "required", "resolved"),
    ]


def test_query_none_with_alias_is_optional_and_named_by_alias(tmp_path: Path, libraries):
    """Review Focus 5: `Query(None, alias="search")` is optional and named `search`; a default
    factory makes a marker optional too."""
    workspace = _resolved(
        tmp_path,
        libraries,
        _route("q: str | None = Query(None, alias='search'), t: str = Query(default_factory=str)"),
    )

    assert _params(workspace) == [
        ("GET", "/x", "query", "search", "optional", "resolved"),
        ("GET", "/x", "query", "t", "optional", "resolved"),
    ]


def test_annotated_header_takes_the_parameter_default_and_hyphenates(tmp_path: Path, libraries):
    """Review Focus 5: a marker in `Annotated` takes the parameter's own default (`field_info.
    default = value`), and `Header` converts `_` to `-` where no alias is written."""
    workspace = _resolved(
        tmp_path,
        libraries,
        _route(
            "x_trace_id: Annotated[str, Header()] = '-', "
            "x_other: Annotated[str, Header(alias='X_Other')] = '-'"
        ),
    )

    assert _params(workspace) == [
        ("GET", "/x", "header", "X_Other", "optional", "resolved"),
        ("GET", "/x", "header", "x-trace-id", "optional", "resolved"),
    ]


def test_convert_underscores_false_keeps_the_name(tmp_path: Path, libraries):
    """`Header(convert_underscores=False)` keeps the parameter's name as written; a `Query`
    name is never converted."""
    workspace = _resolved(
        tmp_path,
        libraries,
        _route("user_agent: str = Header(convert_underscores=False), page_size: int = Query()"),
    )

    assert _params(workspace) == [
        ("GET", "/x", "header", "user_agent", "required", "resolved"),
        ("GET", "/x", "query", "page_size", "required", "resolved"),
    ]


def test_cookie_in_annotated_without_default_is_required(tmp_path: Path, libraries):
    """`Annotated[str, Cookie()]` with no `=` default: `field_info.default = RequiredParam`."""
    workspace = _resolved(tmp_path, libraries, _route("session_id: Annotated[str, Cookie()]"))

    assert _params(workspace) == [("GET", "/x", "cookie", "session_id", "required", "resolved")]


def test_a_path_variable_writes_no_row(tmp_path: Path, libraries):
    """A parameter naming a path variable is the path's (`is_path_param`), marked `Path()` or
    not; so is one naming a variable a prefix put in front of the route. The address carries
    it, as Spring writes no row for `@PathVariable`."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "main.py": _HEAD
            + "outer = APIRouter(prefix='/{org}')\n"
            + "@router.get('/{a}/{b}')\n"
            + "def handler(a: int, b: Annotated[int, Path()], org: str, n: int) -> str:\n"
            + "    return ''\n"
            + "outer.include_router(router)\n"
        },
    )

    assert _params(workspace) == [("GET", "/{org}/{a}/{b}", "query", "n", "required", "resolved")]


def test_an_unmarked_model_is_the_body_not_a_query(tmp_path: Path, libraries):
    """A parameter whose type is not a scalar (a model) is the body (`params.Body`); the scalar
    beside it is a query. A `Body()` marker is the body whatever its type."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "main.py": _HEAD
            + "@router.post('/a')\ndef a(item: Item, dry_run: bool = False) -> str:\n"
            + "    return ''\n"
            + "@router.post('/b')\ndef b(note: str = Body()) -> str:\n    return ''\n"
        },
    )

    assert _params(workspace) == [("POST", "/a", "query", "dry_run", "optional", "resolved")]
    bodies = _bodies(workspace)
    assert bodies[("POST", "/a")] is not None and bodies[("POST", "/a")].endswith("Item#")
    assert bodies[("POST", "/b")] == "string"


def test_one_body_marked_embed_is_an_object_holding_it(tmp_path: Path, libraries):
    """mealie's `recipe_scale: float = Body(1, embed=True)`: FastAPI embeds the body
    (`_should_embed_body_fields`: `embed` set), so the request is `{"recipe_scale": <number>}`,
    never a bare number."""
    workspace = _resolved(
        tmp_path,
        libraries,
        _route("item_id: int, recipe_scale: float = Body(1, embed=True)", "/{item_id}", "post"),
    )

    (row,) = [r for r in workspace.query("endpoints") if r["catalog_id"] == "fastapi"]
    assert json.loads(row["request_shape"]) == {
        "wire_type": "object",
        "wire_format": None,
        "nullable": False,
        "fields": [
            {
                "name": "recipe_scale",
                "required": "optional",
                "type": {"wire_type": "number", "wire_format": None, "nullable": False},
            }
        ],
    }


def test_several_body_parameters_are_one_object_named_by_alias(tmp_path: Path, libraries):
    """Several body parameters (`len(body_param_names_set) > 1`) are embedded: one field each,
    in declared order, named by the marker's `alias` else the parameter's name."""
    workspace = _resolved(
        tmp_path,
        libraries,
        _route("item: Item, note: str = Body(alias='Note'), q: int = 0", verb="post"),
    )

    (row,) = [r for r in workspace.query("endpoints") if r["catalog_id"] == "fastapi"]
    described = json.loads(row["request_shape"])
    assert described["wire_type"] == "object" and "shape_id" not in described
    assert [(field["name"], field["required"]) for field in described["fields"]] == [
        ("item", "required"),
        ("Note", "required"),
    ]
    assert described["fields"][0]["type"]["shape_id"].endswith("Item#")
    assert described["fields"][1]["type"]["wire_type"] == "string"
    assert _params(workspace) == [("POST", "/x", "query", "q", "optional", "resolved")]


def test_a_single_form_field_is_embedded_unless_it_is_a_model(tmp_path: Path, libraries):
    """Polar's `confirm: bool = Form(False)` and `token: str = Form()`: a single `Form` or `File`
    parameter that is no model is a field of the form (`_should_embed_body_fields`), so the
    body is `{confirm: bool}` (optional) and `{token: str}` (required). A model marked `Form`
    is the body itself; `Body(None)` beside another body is an optional field."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "main.py": _HEAD
            + "from fastapi import File, Form, UploadFile\n"
            + "@router.post('/a')\ndef a(confirm: bool = Form(False)) -> str:\n    return ''\n"
            + "@router.post('/b')\ndef b(token: str = Form()) -> str:\n    return ''\n"
            + "@router.post('/c')\ndef c(item: Annotated[Item, Form()]) -> str:\n    return ''\n"
            + "@router.post('/d')\ndef d(upload: UploadFile = File()) -> str:\n    return ''\n"
            + "@router.post('/e')\n"
            + "def e(item: Item, note: str | None = Body(None)) -> str:\n    return ''\n"
        },
    )

    shapes = {
        (r["path"]): json.loads(r["request_shape"])
        for r in workspace.query("endpoints")
        if r["catalog_id"] == "fastapi"
    }

    def fields(path: str) -> list[tuple[str, str, str | None]]:
        return [
            (f["name"], f["required"], (f["type"] or {}).get("wire_type"))
            for f in shapes[path]["fields"]
        ]

    assert fields("/a") == [("confirm", "optional", "boolean")]
    assert fields("/b") == [("token", "required", "string")]
    assert "fields" not in shapes["/c"] and shapes["/c"]["shape_id"].endswith("Item#")
    assert fields("/d") == [("upload", "required", "object")]
    assert fields("/e") == [("item", "required", "object"), ("note", "optional", "string")]


def test_a_literal_is_a_scalar_query(tmp_path: Path, libraries):
    """`Literal[...]` is a scalar (`field_annotation_is_scalar`), so unmarked it is a query
    parameter, never the body; `Optional[Literal[...]] = None` likewise, and optional."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "main.py": _HEAD
            + "from typing import Literal\n"
            + "@router.get('/x')\n"
            + "def handler(mode: Literal['a', 'b'] = 'a', "
            + "kind: Optional[Literal['a']] = None) -> str:\n    return ''\n"
        },
    )

    assert _params(workspace) == [
        ("GET", "/x", "query", "kind", "optional", "resolved"),
        ("GET", "/x", "query", "mode", "optional", "resolved"),
    ]
    assert _bodies(workspace) == {("GET", "/x"): None}


def test_an_unmarked_scalar_on_a_path_not_read_whole_is_no_surer_than_the_path(
    tmp_path: Path, libraries
):
    """Where the address is not read whole (a prefix or a path from the environment), an
    unmarked scalar may name one of its variables: its row takes the address's resolution,
    never `resolved`. A marked query is the query it says."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "main.py": _HEAD
            + "import os\nfrom fastapi import FastAPI\napp = FastAPI()\n"
            + "P = os.environ['P']\n"
            + "@router.get('/x')\ndef a(org: str, q: int = Query()) -> str:\n    return ''\n"
            + "app.include_router(router, prefix=os.environ['R'])\n"
            + "other = APIRouter()\n"
            + "@other.get(P)\ndef b(org: str) -> str:\n    return ''\n"
            + "app.include_router(other)\n"
        },
    )

    found = {(row[3], row[5]) for row in _params(workspace)}
    assert ("q", "resolved") in found
    assert {resolution for name, resolution in found if name == "org"} <= {
        "partial",
        "unresolved",
    }
    assert sum(1 for name, _ in found if name == "org") == 2


def test_an_unmarked_list_is_the_body(tmp_path: Path, libraries):
    """`ids: list[int]` with no marker is the body (`field_annotation_is_scalar` is false for a
    sequence); marked `Query()`, the same type is a query parameter."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "main.py": _HEAD
            + "@router.post('/a')\ndef a(ids: list[int]) -> str:\n    return ''\n"
            + "@router.get('/b')\ndef b(ids: list[int] = Query()) -> str:\n    return ''\n"
        },
    )

    assert _params(workspace) == [("GET", "/b", "query", "ids", "required", "resolved")]
    bodies = _bodies(workspace)
    assert bodies[("POST", "/a")] == "array"
    assert bodies[("GET", "/b")] is None


def test_request_and_background_tasks_write_nothing(tmp_path: Path, libraries):
    """`Request`, `Response` and `BackgroundTasks` are no request parameter at all, and never
    the body: FastAPI hands them in itself."""
    workspace = _resolved(
        tmp_path,
        libraries,
        _route(
            "request: Request, response: Response, tasks: BackgroundTasks, item: Item",
            verb="post",
        ),
    )

    assert _params(workspace) == []
    body = _bodies(workspace)[("POST", "/x")]
    assert body is not None and body.endswith("Item#")


def test_depends_in_default_and_annotated_is_refused(tmp_path: Path, libraries):
    """`Annotated[str, Depends(dep)] = Depends(dep)` is an assertion at registration ("Cannot
    specify `Depends` in `Annotated` and default value together"): FastAPI raises at import, so
    the app does not start. No row; a `refused_registration` question instead."""
    workspace = _resolved(
        tmp_path, libraries, _route("x: Annotated[str, Depends(dep)] = Depends(dep)")
    )

    assert _rows(workspace) == []
    assert _params(workspace) == []
    (question,) = _questions(workspace, "refused_registration")
    assert question["path"] == "/x"
    (candidate,) = json.loads(question["candidates"])
    assert (candidate["reason"], _bare(candidate["handler"])) == (
        "marked_twice",
        _handler("handler"),
    )


def test_the_three_other_marker_errors_are_refused(tmp_path: Path, libraries):
    """`analyze_param`'s other assertions: a marker in `Annotated` beside a marker default
    ("Cannot specify FastAPI annotations in `Annotated` and default value together"), a
    non-`Path` marker on a path variable ("Cannot use `Query` for path param"), and a path
    variable with an `Annotated` marker and a default ("Path parameters cannot have default
    values")."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "main.py": _HEAD
            + "@router.get('/a')\ndef a(x: Annotated[int, Query()] = Query()) -> str:\n"
            + "    return ''\n"
            + "@router.get('/b/{x}')\ndef b(x: int = Query()) -> str:\n    return ''\n"
            + "@router.get('/c/{x}')\ndef c(x: Annotated[int, Path()] = 5) -> str:\n"
            + "    return ''\n"
            + "@router.get('/d/{x}')\ndef d(x: Annotated[int, Path()]) -> str:\n    return ''\n"
        },
    )

    assert [(row[0], row[1]) for row in _rows(workspace)] == [("GET", "/d/{x}")]
    refused = sorted(
        (question["path"], candidate["reason"])
        for question in _questions(workspace, "refused_registration")
        for candidate in json.loads(question["candidates"])
    )
    assert refused == [
        ("/a", "marked_twice"),
        ("/b/{x}", "path_variable_marked"),
        ("/c/{x}", "path_variable_default"),
    ]


def test_the_last_annotated_marker_wins(tmp_path: Path, libraries):
    """`fastapi_specific_annotations[-1]`: the last FastAPI marker in `Annotated` is the one,
    whatever its kind, and a non-marker after it changes nothing."""
    workspace = _resolved(
        tmp_path,
        libraries,
        _route(
            "a: Annotated[int, Query(alias='first'), Query(alias='second')], "
            "b: Annotated[str, Query(), Header(), 'note'], "
            "c: Annotated[int, Depends(dep), Query()]"
        ),
    )

    assert _params(workspace) == [
        ("GET", "/x", "header", "b", "required", "resolved"),
        ("GET", "/x", "query", "c", "required", "resolved"),
        ("GET", "/x", "query", "second", "required", "resolved"),
    ]


def test_a_marker_through_a_module_alias_is_read(tmp_path: Path, libraries):
    """A marker reached through a module-level `Annotated` alias in another file is read as the
    marker it is (`parameter_markers` follows the alias); a `Depends` alias is no parameter."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "deps.py": (
                "from typing import Annotated\n"
                "from fastapi import Depends, Header\n"
                "def dep() -> str:\n    return ''\n"
                "Tenant = Annotated[str, Header(alias='X-Tenant')]\n"
                "Db = Annotated[str, Depends(dep)]\n"
            ),
            "main.py": _HEAD
            + "from app.deps import Db, Tenant\n"
            + "@router.get('/x')\ndef handler(tenant: Tenant, db: Db) -> str:\n    return ''\n",
        },
    )

    assert _params(workspace) == [("GET", "/x", "header", "X-Tenant", "required", "resolved")]


def test_a_marker_constructed_from_its_class_is_the_same_marker(tmp_path: Path, libraries):
    """`fastapi.params.Depends(f)` and `params.Query(alias=...)` construct the objects FastAPI
    reads (`isinstance(value, params.Depends)`), as the functions of `fastapi.param_functions`
    do: a dependency made so is no parameter and no body (polar's `file/auth.py`), and a query
    made so is the query it names."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "auth.py": (
                "from typing import Annotated\n"
                "from fastapi.params import Depends\n"
                "from pydantic import BaseModel\n"
                "class Subject(BaseModel):\n    name: str\n"
                "def subject() -> Subject:\n    return Subject(name='')\n"
                "Write = Annotated[Subject, Depends(subject)]\n"
            ),
            "main.py": _HEAD
            + "from fastapi import params\n"
            + "from app import auth\n"
            + "@router.delete('/{id}')\n"
            + "def handler(who: auth.Write, id: int, q: int = params.Query(alias='Q')) -> str:\n"
            + "    return ''\n",
        },
    )

    assert _params(workspace) == [("DELETE", "/{id}", "query", "Q", "required", "resolved")]
    assert _bodies(workspace) == {("DELETE", "/{id}"): None}


def test_a_query_model_names_no_parameter_it_does_not_carry(tmp_path: Path, libraries):
    """`Annotated[Filters, Query()]` makes the model's FIELDS the query parameters
    (`_get_flat_fields_from_params`), never one named `filters`: one row per field, named and
    required as the shape model reads the field (R25, `test_pydantic_shapes`)."""
    workspace = _resolved(
        tmp_path,
        libraries,
        _route("filters: Annotated[Item, Query()], limit: Annotated[int, Query()] = 10"),
    )

    assert _params(workspace) == [
        ("GET", "/x", "query", "limit", "optional", "resolved"),
        ("GET", "/x", "query", "name", "required", "resolved"),
    ]
    assert _bodies(workspace) == {("GET", "/x"): None}


def test_a_marked_parameter_of_a_type_named_by_no_symbol_names_nothing(tmp_path: Path, libraries):
    """polar's `SortingGetter`: a model class defined in the function that returns the recipe is
    written as text naming no type, so whether it is a query model (its fields the parameters)
    or a scalar is not known: one row of the marker's kind naming nothing, at `unresolved`,
    never a parameter named after the argument."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "main.py": _HEAD + "def getter():\n"
            "    class Params(BaseModel):\n"
            "        sorting: str = 'id'\n"
            "    def get(params: Annotated[Params, Query()]) -> str:\n"
            "        return params.sorting\n"
            "    return get\n"
            "@router.get('/x')\n"
            "def handler(s: str = Depends(getter())) -> str:\n"
            "    return s\n"
        },
    )

    assert _params(workspace) == [("GET", "/x", "query", None, None, "unresolved")]


def test_an_alias_read_as_a_type_is_read_by_its_known_type(tmp_path: Path, libraries):
    """pydantic's `UUID4 = Annotated[UUID, UuidVersion(4)]` is no class, so the `object` wire a
    type reference carries for it says nothing about its kind; pydantic's `known_types` (plan 2
    Task 9) says it is a string, so it is a scalar, which FastAPI reads as a query parameter,
    never the body."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "main.py": _HEAD
            + "from pydantic import UUID4\n"
            + "@router.get('/x')\ndef handler(organization_id: UUID4) -> str:\n    return ''\n"
        },
    )

    assert _params(workspace) == [("GET", "/x", "query", "organization_id", "required", "resolved")]
    assert _bodies(workspace) == {("GET", "/x"): None}


def test_rows_on_two_include_paths_each_read_their_own_path_variables(tmp_path: Path, libraries):
    """A route reached on two include paths is two rows (Task 6), and each reads its parameters
    against its own path: `org` is the path's under `/{org}` and a query under `/plain`."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "main.py": _HEAD
            + "from fastapi import FastAPI\n"
            + "app = FastAPI()\n"
            + "@router.get('/x')\ndef handler(org: str) -> str:\n    return ''\n"
            + "app.include_router(router, prefix='/{org}')\n"
            + "app.include_router(router, prefix='/plain')\n"
        },
    )

    assert _params(workspace) == [("GET", "/plain/x", "query", "org", "required", "resolved")]


@pytest.mark.parametrize(
    ("written", "replaced", "named"),
    [
        (
            "{ unmarked: true, kind: query,",
            "{ unmarked: true, kind: query, scalar: true,",
            "unmarked",
        ),
        ("equals_field: builtins.Ellipsis }", "equals_field: Ellipsis }", "required_when"),
        ("annotated_default: parameter }", "annotated_default: marker }", "annotated_default"),
        ('replace: { "_": "-" }', 'replace: "-"', "spelling"),
        ("method: Cookie, kind: cookie,", "method: Cookie, kind: option,", "`kind`"),
        ("fastapi.param_functions.Form,", "Form,", "marker_calls"),
        ("implicit_bindings: [path_variable, scalar]", "implicit_bindings: [scalars]", "implicit"),
        ("unless_subtype_of: [pydantic.main.BaseModel]", "unless: BaseModel", "embed_markers"),
    ],
)
def test_a_malformed_parameter_entry_is_refused(
    tmp_path: Path, libraries, written: str, replaced: str, named: str
):
    """A misspelt key or word would load and read every parameter another way, silently."""
    catalogs = tmp_path / "catalogs"
    shutil.copytree(catalogs_dir(), catalogs)
    text = (catalogs / "fastapi.yml").read_text(encoding="utf-8")
    assert written in text
    (catalogs / "fastapi.yml").write_text(text.replace(written, replaced), encoding="utf-8")

    with pytest.raises(CatalogError) as raised:
        _resolved(tmp_path, libraries, _route("q: int = Query()"), catalogs)

    assert named in str(raised.value)


@pytest.mark.parametrize(
    ("catalog", "written", "replaced", "named"),
    [
        (
            "spring-mvc.yml",
            "request_body: { annotation: org.springframework.web.bind.annotation.RequestBody,",
            (
                "request_body: { marker_calls: [a.b.C], "
                "annotation: org.springframework.web.bind.annotation.RequestBody,"
            ),
            "marker_calls",
        ),
        ("fastapi.yml", "fallback: sole_unbound", "fallback: sole_unannotated", "bound_by_calls"),
    ],
)
def test_the_loader_refuses_call_keys_where_nothing_reads_them(
    tmp_path: Path, catalog: str, written: str, replaced: str, named: str
):
    """`request_body`'s call keys are read only on a `fluent` catalog, and `bound_by_calls`
    only beside `sole_unbound`: anywhere else they would be read as nothing."""
    catalogs = tmp_path / "catalogs"
    shutil.copytree(catalogs_dir(), catalogs)
    text = (catalogs / catalog).read_text(encoding="utf-8")
    assert written in text
    (catalogs / catalog).write_text(text.replace(written, replaced), encoding="utf-8")

    with pytest.raises(CatalogError) as raised:
        YamlCatalogSource(catalogs).load()

    assert named in str(raised.value)
