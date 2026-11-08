"""Print FastAPI's own answer for each rule the FastAPI reader mirrors (plan 2, Task 0).

Run it inside a throwaway environment that has FastAPI installed, never inside the repository's
`.venv`:

    uv venv /tmp/probe && uv pip install -p /tmp/probe/bin/python fastapi==0.162.0 httpx
    /tmp/probe/bin/python scripts/probes/fastapi_rules.py

It prints one JSON document: the FastAPI version, then one entry per rule. The rules and the
source lines they come from are in `fastapi_rules.md`. The probe imports FastAPI and runs its
registration code on purpose. Sextant itself never does that (spec 7).
"""

# ruff: noqa: UP045, B008
# The probe writes `Optional[X]` and marker calls in defaults on purpose: they are the shapes
# under test.

from __future__ import annotations

import functools
import json
import sys
import types
from typing import Annotated, Any, Optional

import fastapi
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Body,
    Cookie,
    Depends,
    FastAPI,
    File,
    Header,
    Path,
    Query,
    Request,
    Response,
    UploadFile,
)
from fastapi.dependencies.utils import get_dependant
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from pydantic import BaseModel
from starlette.routing import Mount, Route


class Item(BaseModel):
    name: str


class Other(BaseModel):
    size: int


def _error(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"


def attempt(fn):
    """The value `fn` returns, or `{"raises": "<type>: <message>"}`."""
    try:
        return fn()
    except BaseException as exc:  # noqa: BLE001 - the probe reports every failure
        return {"raises": _error(exc)}


# ---------------------------------------------------------------------------------------------
# What a dependant asks of the request: FastAPI's own flattening
# ---------------------------------------------------------------------------------------------


def _field_row(field: Any) -> dict[str, Any]:
    info = field.field_info
    required = field.required if hasattr(field, "required") else info.is_required()
    return {
        "name": field.name,
        "alias": getattr(field, "alias", None) or info.alias,
        "required": bool(required),
        "marker": type(info).__name__,
    }


def flatten(dependant: Any) -> dict[str, Any]:
    """The request parameters of `dependant` and of every dependency under it, in order."""
    out: dict[str, Any] = {
        "path": [],
        "query": [],
        "header": [],
        "cookie": [],
        "body": [],
        "special": [],
        "dependencies": [],
    }

    def walk(node: Any) -> None:
        for kind in ("path", "query", "header", "cookie", "body"):
            for field in getattr(node, f"{kind}_params"):
                out[kind].append(_field_row(field))
        for slot in (
            "request_param_name",
            "websocket_param_name",
            "http_connection_param_name",
            "response_param_name",
            "background_tasks_param_name",
            "security_scopes_param_name",
        ):
            if getattr(node, slot, None):
                out["special"].append(f"{getattr(node, slot)}:{slot}")
        for sub in node.dependencies:
            out["dependencies"].append(getattr(sub.call, "__name__", repr(sub.call)))
            walk(sub)

    walk(dependant)
    return {key: value for key, value in out.items() if value}


def classify(path: str, call: Any) -> Any:
    return attempt(lambda: flatten(get_dependant(path=path, call=call)))


# ---------------------------------------------------------------------------------------------
# Parameter cases (rule: analyze_param)
# ---------------------------------------------------------------------------------------------


def dep_a(a_query: int) -> int:
    return a_query


def dep_b(b_header: Annotated[str, Header()]) -> str:
    return b_header


Alias = Annotated[int, Query(ge=1)]
DbAlias = Annotated[int, Depends(dep_a)]


def p_query_ellipsis(x: int = Query(...)): ...
def p_query_none(x: Optional[int] = Query(None)): ...
def p_query_empty(x: int = Query()): ...
def p_query_default(x: int = Query(5)): ...
def p_query_default_factory(x: int = Query(default_factory=lambda: 5)): ...
def p_unmarked_scalar(x: int): ...
def p_unmarked_scalar_default(x: int = 3): ...
def p_unmarked_optional_no_default(x: Optional[int]): ...
def p_unmarked_optional_none(x: Optional[int] = None): ...
def p_unmarked_list(x: list[int]): ...
def p_unmarked_list_default(x: list[int] = [1]): ...  # noqa: B006 - the shape is the point
def p_unmarked_model(x: Item): ...
def p_unmarked_dict(x: dict[str, int]): ...
def p_marked_list_query(x: list[int] = Query()): ...
def p_path_unmarked(x: int): ...  # used with path "/{x}"
def p_path_default(x: int = 5): ...  # used with path "/{x}"
def p_path_marked(x: int = Path()): ...  # used with path "/{x}"
def p_path_annotated_default(x: Annotated[int, Path()] = 5): ...  # used with path "/{x}"
def p_path_query_marker(x: int = Query()): ...  # used with path "/{x}"
def p_header_default(user_agent: str = Header()): ...
def p_header_no_convert(user_agent: str = Header(convert_underscores=False)): ...
def p_header_alias(user_agent: str = Header(alias="x_ua")): ...
def p_header_annotated(user_agent: Annotated[str, Header()]): ...
def p_header_annotated_no_convert(
    user_agent: Annotated[str, Header(convert_underscores=False)],
): ...
def p_cookie(session_id: str = Cookie()): ...
def p_query_underscore(my_name: str = Query()): ...
def p_annotated_query(x: Annotated[int, Query()]): ...
def p_annotated_query_default(x: Annotated[int, Query()] = 4): ...
def p_annotated_query_none(x: Annotated[Optional[int], Query()] = None): ...
def p_annotated_last_wins(x: Annotated[int, Query(alias="first"), Query(alias="second")]): ...
def p_annotated_marker_then_body(x: Annotated[int, Query(), Body()]): ...
def p_annotated_body_then_header(x: Annotated[int, Body(), Header()]): ...
def p_annotated_plain_metadata_after(x: Annotated[int, Query(alias="q"), "note"]): ...
def p_annotated_default_inside(x: Annotated[int, Query(5)]): ...
def p_annotated_ellipsis_inside(x: Annotated[int, Query(...)]): ...
def p_annotated_and_default_marker(x: Annotated[int, Query()] = Query()): ...
def p_annotated_depends(x: Annotated[int, Depends(dep_a)]): ...
def p_annotated_depends_then_query(x: Annotated[int, Depends(dep_a), Query()]): ...
def p_annotated_query_then_depends(x: Annotated[int, Query(), Depends(dep_a)]): ...
def p_annotated_depends_and_default(x: Annotated[int, Depends(dep_a)] = Depends(dep_a)): ...
def p_depends_default(x: int = Depends(dep_a)): ...
def p_depends_empty(x: Item = Depends()): ...
def p_depends_with_params(x: str = Depends(dep_b)): ...
def p_alias_type(x: Alias): ...
def p_alias_depends(x: DbAlias): ...
def p_request(request: Request): ...
def p_response(response: Response): ...
def p_background(tasks: BackgroundTasks): ...
def p_request_marked(request: Request = Query()): ...
def p_request_with_depends(request: Annotated[Request, Depends(dep_a)]): ...
def p_body_marker(x: int = Body()): ...
def p_body_model_marked(x: Item = Body()): ...
def p_body_two_models(a: Item, b: Other): ...
def p_file_unmarked(x: UploadFile): ...
def p_file_marked(x: bytes = File()): ...
def p_default_is_call_result(x: int = Query(int("3"))): ...


PARAM_CASES = [
    ("query_ellipsis", "/", p_query_ellipsis),
    ("query_none", "/", p_query_none),
    ("query_empty_call", "/", p_query_empty),
    ("query_with_default", "/", p_query_default),
    ("query_default_factory", "/", p_query_default_factory),
    ("unmarked_scalar", "/", p_unmarked_scalar),
    ("unmarked_scalar_with_default", "/", p_unmarked_scalar_default),
    ("unmarked_optional_no_default", "/", p_unmarked_optional_no_default),
    ("unmarked_optional_none", "/", p_unmarked_optional_none),
    ("unmarked_list", "/", p_unmarked_list),
    ("unmarked_list_with_default", "/", p_unmarked_list_default),
    ("unmarked_model", "/", p_unmarked_model),
    ("unmarked_dict", "/", p_unmarked_dict),
    ("list_marked_query", "/", p_marked_list_query),
    ("path_variable_unmarked", "/{x}", p_path_unmarked),
    ("path_variable_with_default", "/{x}", p_path_default),
    ("path_variable_marked_path", "/{x}", p_path_marked),
    ("path_variable_annotated_with_default", "/{x}", p_path_annotated_default),
    ("path_variable_marked_query", "/{x}", p_path_query_marker),
    ("header_default", "/", p_header_default),
    ("header_no_convert", "/", p_header_no_convert),
    ("header_alias_underscore", "/", p_header_alias),
    ("header_annotated", "/", p_header_annotated),
    ("header_annotated_no_convert", "/", p_header_annotated_no_convert),
    ("cookie", "/", p_cookie),
    ("query_name_with_underscore", "/", p_query_underscore),
    ("annotated_query", "/", p_annotated_query),
    ("annotated_query_with_default", "/", p_annotated_query_default),
    ("annotated_query_none", "/", p_annotated_query_none),
    ("annotated_last_marker_wins", "/", p_annotated_last_wins),
    ("annotated_query_then_body", "/", p_annotated_marker_then_body),
    ("annotated_body_then_header", "/", p_annotated_body_then_header),
    ("annotated_plain_metadata_after_marker", "/", p_annotated_plain_metadata_after),
    ("annotated_default_inside_marker", "/", p_annotated_default_inside),
    ("annotated_ellipsis_inside_marker", "/", p_annotated_ellipsis_inside),
    ("annotated_marker_and_default_marker", "/", p_annotated_and_default_marker),
    ("annotated_depends", "/", p_annotated_depends),
    ("annotated_depends_then_query", "/", p_annotated_depends_then_query),
    ("annotated_query_then_depends", "/", p_annotated_query_then_depends),
    ("annotated_depends_and_default_depends", "/", p_annotated_depends_and_default),
    ("depends_as_default", "/", p_depends_default),
    ("depends_empty_uses_type", "/", p_depends_empty),
    ("depends_with_own_header", "/", p_depends_with_params),
    ("type_alias_marker", "/", p_alias_type),
    ("type_alias_depends", "/", p_alias_depends),
    ("request_typed", "/", p_request),
    ("response_typed", "/", p_response),
    ("background_tasks_typed", "/", p_background),
    ("request_typed_with_marker", "/", p_request_marked),
    ("request_typed_with_depends", "/", p_request_with_depends),
    ("body_marker", "/", p_body_marker),
    ("body_marker_model", "/", p_body_model_marked),
    ("two_models_unmarked", "/", p_body_two_models),
    ("uploadfile_unmarked", "/", p_file_unmarked),
    ("file_marker", "/", p_file_marked),
    ("default_is_call_result", "/", p_default_is_call_result),
]


# ---------------------------------------------------------------------------------------------
# Rule: get_typed_signature follows __wrapped__
# ---------------------------------------------------------------------------------------------


def wrapped_target(q: int, h: str = Header()): ...


@functools.wraps(wrapped_target)
def wrapper(*args, **kwargs):
    return wrapped_target(*args, **kwargs)


def no_wraps_wrapper(*args, **kwargs):
    return wrapped_target(*args, **kwargs)


def forward_reference_case() -> dict[str, Any]:
    """The globals FastAPI evaluates a string annotation in: the wrapper's or the wrapped's."""
    inner = types.ModuleType("probe_inner")
    outer = types.ModuleType("probe_outer")
    exec("Qt = int\ndef target(q: 'Qt'): ...\n", inner.__dict__)  # noqa: S102 - the probe's own text
    exec(  # noqa: S102 - the probe's own text
        "import functools\ndef deco(f):\n    @functools.wraps(f)\n"
        "    def w(*a, **k): return f(*a, **k)\n    return w\n",
        outer.__dict__,
    )
    return classify("/", outer.deco(inner.target))


# ---------------------------------------------------------------------------------------------
# Rule: routes, prefixes, methods, HEAD
# ---------------------------------------------------------------------------------------------


def endpoint() -> dict[str, str]:
    return {}


def served(app: FastAPI) -> dict[str, list[str]]:
    """Path to sorted verbs of the paths the app serves, from its own OpenAPI document."""
    paths = app.openapi()["paths"]
    return {path: sorted(verb.upper() for verb in verbs) for path, verbs in paths.items()}


def requests_answered(app: FastAPI, checks: list[tuple[str, str]]) -> dict[str, int]:
    client = TestClient(app)
    return {f"{verb} {path}": client.request(verb, path).status_code for verb, path in checks}


def composition() -> dict[str, Any]:
    app = FastAPI()
    inner = APIRouter(prefix="/inner")
    inner.add_api_route("/leaf", endpoint)
    inner.add_api_route("", endpoint, name="bare")
    middle = APIRouter(prefix="/middle")
    middle.include_router(inner, prefix="/a")
    app.include_router(middle, prefix="/b")
    plain = APIRouter()
    plain.add_api_route("/p", endpoint)
    app.include_router(plain)
    app.include_router(plain, prefix="/twice")
    return {
        "note": (
            "inner prefix /inner; inner included in middle with /a; middle prefix /middle "
            "included in app with /b; plain router included twice"
        ),
        "served": served(app),
    }


def include_assertions() -> dict[str, Any]:
    def build(prefix: str, path: str, *, router_prefix: str = "") -> Any:
        app = FastAPI()
        router = APIRouter(prefix=router_prefix)
        router.add_api_route(path, endpoint)
        app.include_router(router, prefix=prefix)
        return sorted(served(app))

    def self_include() -> Any:
        router = APIRouter()
        router.include_router(router)

    def cycle() -> Any:
        a, b = APIRouter(), APIRouter()
        a.include_router(b)
        b.include_router(a)

    return {
        "prefix_without_leading_slash": attempt(lambda: build("a", "/x")),
        "prefix_with_trailing_slash": attempt(lambda: build("/a/", "/x")),
        "prefix_slash_only": attempt(lambda: build("/", "/x")),
        "empty_prefix_and_empty_path": attempt(lambda: build("", "")),
        "empty_prefix_empty_path_router_prefix_set": attempt(
            lambda: build("", "", router_prefix="/r")
        ),
        "include_prefix_set_empty_path": attempt(lambda: build("/a", "")),
        "include_itself": attempt(self_include),
        "include_cycle": attempt(cycle),
        "router_prefix_trailing_slash": attempt(lambda: APIRouter(prefix="/r/")),
        "router_prefix_no_leading_slash": attempt(lambda: APIRouter(prefix="r")),
        "route_path_without_leading_slash": attempt(lambda: build("", "x")),
        "router_prefix_then_route_path_without_slash": attempt(
            lambda: build("", "x", router_prefix="/r")
        ),
    }


def mounts() -> dict[str, Any]:
    async def asgi(scope, receive, send): ...

    return {
        "trailing_slash_stripped": attempt(lambda: Mount("/x/", app=asgi).path),
        "root_slash_becomes_empty": attempt(lambda: Mount("/", app=asgi).path),
        "empty_path": attempt(lambda: Mount("", app=asgi).path),
        "no_leading_slash": attempt(lambda: Mount("x", app=asgi).path),
        "double_trailing_slash": attempt(lambda: Mount("/x//", app=asgi).path),
        "neither_app_nor_routes": attempt(lambda: Mount("/x")),
    }


def methods_and_head() -> dict[str, Any]:
    app = FastAPI()

    @app.get("/get")
    def get_route(): ...

    @app.post("/post")
    def post_route(): ...

    app.add_api_route("/default", endpoint)
    app.add_api_route("/lower", endpoint, methods=["get", "Post"])
    refused_empty = attempt(lambda: app.add_api_route("/empty_list", endpoint, methods=[]))
    app.add_api_route("/set", endpoint, methods={"put", "DELETE"})
    app.add_api_route("/head_listed", endpoint, methods=["GET", "HEAD"])

    @app.api_route("/api_route_default")
    def api_route_default(): ...

    @app.api_route("/api_route_two", methods=["get", "patch"])
    def api_route_two(): ...

    app.add_route("/starlette_default", lambda request: JSONResponse({}))
    app.add_route("/starlette_post", lambda request: JSONResponse({}), methods=["POST"])

    rows: dict[str, Any] = {}
    for route in app.routes:
        if isinstance(route, (APIRoute, Route)):
            rows[route.path] = sorted(route.methods or [])
    return {
        "methods_empty_list": refused_empty,
        "route_methods": {key: value for key, value in rows.items() if key.startswith("/")},
        "head_answers": requests_answered(
            app, [("HEAD", "/get"), ("GET", "/get"), ("HEAD", "/starlette_default")]
        ),
    }


def lazy_versus_eager() -> dict[str, Any]:
    """Register a route on a router after the router was included."""
    app = FastAPI()
    router = APIRouter(prefix="/late")
    router.add_api_route("/before", endpoint)
    app.include_router(router)
    router.add_api_route("/after", endpoint)
    nested_inner = APIRouter(prefix="/in")
    nested_outer = APIRouter(prefix="/out")
    nested_outer.include_router(nested_inner)
    app.include_router(nested_outer)
    nested_inner.add_api_route("/after_nested", endpoint)
    return {
        "served": sorted(served(app)),
        "after_include_is_served": "/late/after" in served(app),
        "after_include_in_nested_is_served": "/out/in/after_nested" in served(app),
    }


# ---------------------------------------------------------------------------------------------
# Rule: dependencies= on routes, routers, includes and the app
# ---------------------------------------------------------------------------------------------


def dep_route(route_q: int) -> None: ...
def dep_router(router_q: int) -> None: ...
def dep_include(include_q: int) -> None: ...
def dep_app(app_q: int) -> None: ...
def dep_parent_router(parent_q: int) -> None: ...


def handler_with_own(own_q: str) -> None: ...


def dependencies_join() -> dict[str, Any]:
    app = FastAPI(dependencies=[Depends(dep_app)])
    parent = APIRouter(prefix="/parent", dependencies=[Depends(dep_parent_router)])
    router = APIRouter(prefix="/r", dependencies=[Depends(dep_router)])
    router.add_api_route("/x", handler_with_own, dependencies=[Depends(dep_route)])
    parent.include_router(router, dependencies=[Depends(dep_include)])
    app.include_router(parent)
    out: dict[str, Any] = {}
    for route in app.routes:
        if isinstance(route, APIRoute) and route.path.endswith("/x"):
            out[route.path] = flatten(route.dependant)
    if not out:  # lazy include (0.141+): the effective route is not in `app.routes`
        out["via_openapi"] = {
            path: [p["name"] for op in item.values() for p in op.get("parameters", [])]
            for path, item in app.openapi()["paths"].items()
            if path.endswith("/x")
        }
    return out


# ---------------------------------------------------------------------------------------------
# Rule: the response model when response_model is not written
# ---------------------------------------------------------------------------------------------


def r_none_written(): ...
def r_item() -> Item: ...
def r_list_item() -> list[Item]: ...
def r_optional_item() -> Optional[Item]: ...
def r_response() -> Response: ...
def r_json_response() -> JSONResponse: ...
def r_union_with_response() -> Item | Response: ...
def r_dict() -> dict[str, int]: ...
def r_none_annotation() -> None: ...
def r_any() -> Any: ...


def response_models() -> dict[str, Any]:
    def model_of(fn: Any, **kwargs: Any) -> Any:
        route = APIRoute("/", fn, **kwargs)
        return repr(route.response_model)

    return {
        "no_annotation": attempt(lambda: model_of(r_none_written)),
        "annotation_item": attempt(lambda: model_of(r_item)),
        "annotation_list_item": attempt(lambda: model_of(r_list_item)),
        "annotation_optional_item": attempt(lambda: model_of(r_optional_item)),
        "annotation_response": attempt(lambda: model_of(r_response)),
        "annotation_json_response": attempt(lambda: model_of(r_json_response)),
        "annotation_item_or_response": attempt(lambda: model_of(r_union_with_response)),
        "annotation_dict": attempt(lambda: model_of(r_dict)),
        "annotation_none": attempt(lambda: model_of(r_none_annotation)),
        "annotation_any": attempt(lambda: model_of(r_any)),
        "response_model_written_over_annotation": attempt(
            lambda: model_of(r_item, response_model=Other)
        ),
        "response_model_none_over_annotation": attempt(
            lambda: model_of(r_item, response_model=None)
        ),
        "response_model_written_over_response_annotation": attempt(
            lambda: model_of(r_json_response, response_model=Other)
        ),
        "response_model_written_no_annotation": attempt(
            lambda: model_of(r_none_written, response_model=Item)
        ),
    }


# ---------------------------------------------------------------------------------------------


def main() -> None:
    result: dict[str, Any] = {
        "fastapi": fastapi.__version__,
        "python": sys.version.split()[0],
    }
    result["parameters"] = {name: classify(path, fn) for name, path, fn in PARAM_CASES}
    result["wrapped"] = {
        "functools_wraps_wrapper": classify("/", wrapper),
        "wrapper_without_wraps": classify("/", no_wraps_wrapper),
        "string_annotation_wrapper_globals_or_wrapped": attempt(forward_reference_case),
    }
    result["composition"] = attempt(composition)
    result["include_assertions"] = include_assertions()
    result["mounts"] = mounts()
    result["methods_and_head"] = attempt(methods_and_head)
    result["lazy_versus_eager"] = attempt(lazy_versus_eager)
    result["dependencies_join"] = attempt(dependencies_join)
    result["response_models"] = response_models()
    json.dump(result, sys.stdout, indent=1, sort_keys=False, default=repr)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
