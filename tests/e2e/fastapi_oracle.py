"""FastAPI's own answer to "what does this project serve?", printed as JSON.

Run with the FIXTURE's interpreter, never Sextant's: it imports the fixture's app and asks
FastAPI itself. Sextant's answers are later compared against this one, so nothing here may
come from Sextant. Published OpenAPI is not the oracle (it filters routes); the route table is.

    <fixture>/.venv/bin/python fastapi_oracle.py <fixture root> [module:attribute]
"""

import json
import sys
from pathlib import Path
from typing import Any, get_origin

from fastapi.routing import APIRoute, _iter_routes_with_context
from starlette.routing import Mount


def _flatten(dependant: Any) -> dict[str, list[Any]]:
    """The request parameters of a dependant and of every dependency under it."""
    out: dict[str, list[Any]] = {kind: [] for kind in ("path", "query", "header", "cookie", "body")}

    def walk(node: Any) -> None:
        for kind, fields in out.items():
            fields.extend(getattr(node, f"{kind}_params"))
        for sub in node.dependencies:
            walk(sub)

    walk(dependant)
    return out


def _fields(fields: list[Any]) -> list[dict[str, Any]]:
    return [{"alias": f.alias, "required": bool(f.field_info.is_required())} for f in fields]


def _model_name(model: Any) -> str | None:
    if model is None:
        return None
    # A plain class is named; a generic such as `dict[str, str]` is written out in full.
    if isinstance(model, type) and get_origin(model) is None:
        return model.__name__
    return str(model)


def _row(route: Any, context: Any, prefix: str) -> dict[str, Any]:
    # An included route is read through its effective context: that carries the prefixes and
    # dependencies of every include above it. A route written on the app itself has no context.
    source = context if context is not None else route
    flat = _flatten(source.dependant)
    return {
        "methods": sorted(source.methods),
        "path": prefix + source.path,
        "endpoint": source.endpoint.__qualname__,
        "response_model": _model_name(source.response_model),
        "query": _fields(flat["query"]),
        "header": _fields(flat["header"]),
        "cookie": _fields(flat["cookie"]),
        "path_params": _fields(flat["path"]),
        "body": [f.name for f in flat["body"]],
    }


def routes_of(routes: Any, prefix: str = "") -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for route, context in _iter_routes_with_context(routes):
        if isinstance(route, Mount):
            # A mounted app is its own route table; its paths sit under the mount's path.
            rows.extend(routes_of(route.app.router.routes, prefix + route.path))
        elif isinstance(route, APIRoute):
            rows.append(_row(route, context, prefix))
    return rows


def main(argv: list[str]) -> None:
    root = Path(argv[1]).resolve()
    sys.path.insert(0, str(root))
    module, _, attribute = (argv[2] if len(argv) > 2 else "app.main:app").partition(":")
    app = getattr(__import__(module, fromlist=[attribute]), attribute)
    print(json.dumps(routes_of(app.router.routes), indent=2))


if __name__ == "__main__":
    main(sys.argv)
