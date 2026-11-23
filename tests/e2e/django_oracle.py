"""Django's own answer to "what does this project serve?", printed as JSON.

Sets up the fixture's settings, walks the REAL resolver (`get_resolver().url_patterns`, joining
routes with Django's own `URLResolver._join_route`), and measures each pattern's methods by
BEHAVIOUR: the callback is called through `RequestFactory` once per method, and a method is
allowed when the answer is not 405. Run with the FIXTURE's interpreter, never Sextant's; nothing
here may come from Sextant. `SHOP_DEBUG=1` in the environment turns the fixture's DEBUG on.

    <fixture>/.venv/bin/python django_oracle.py <fixture root>
"""

import inspect
import json
import logging
import os
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any

METHODS = ("GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS")
# A text each built-in converter's `to_python` accepts; any other converter is given "x".
SAMPLES = {"IntConverter": "5", "UUIDConverter": str(uuid.UUID(int=1)), "PathConverter": "a/b"}


def _arguments(chain: list[Any]) -> tuple[list[str], dict[str, Any]]:
    """What the resolver would pass for a plausible URL: converted keywords for `path`, the
    named groups of `re_path` (or its unnamed groups, positionally, when it names none)."""
    from django.urls.resolvers import RoutePattern

    args: list[str] = []
    kwargs: dict[str, Any] = {}
    for pattern in chain:
        if isinstance(pattern, RoutePattern):
            for name, converter in pattern.converters.items():
                kwargs[name] = converter.to_python(SAMPLES.get(type(converter).__name__, "x"))
        elif pattern.regex.groupindex:
            kwargs.update(dict.fromkeys(pattern.regex.groupindex, "5"))
        else:
            args.extend(["x"] * pattern.regex.groups)
    return args, kwargs


def _allowed(callback: Any, chain: list[Any]) -> list[str]:
    from django.test import RequestFactory

    args, kwargs = _arguments(chain)
    allowed = []
    for method in METHODS:
        request = RequestFactory().generic(method, "/")
        request.user = SimpleNamespace(is_authenticated=True)  # a login wrapper lets it through
        if callback(request, *args, **kwargs).status_code != 405:
            allowed.append(method)
    return allowed


def _named(function: Any) -> str:
    return f"{function.__module__}.{function.__qualname__}"


def _row(pattern: Any, route: str, regex: str, chain: list[Any]) -> dict[str, Any]:
    from django.urls.resolvers import RegexPattern
    from django.views import View

    callback = pattern.callback
    view_class = getattr(callback, "view_class", None)
    row = {
        "route": route,
        "regex": regex,
        "kind": "regex" if any(isinstance(p, RegexPattern) for p in chain) else "route",
        "allowed": _allowed(callback, chain),
        "handler": None if view_class else _named(inspect.unwrap(callback)),
        "view_class": _named(view_class) if view_class else None,
    }
    if view_class:
        # The method each dispatched name reaches through the MRO, to name a row's handler.
        row["class_methods"] = {
            name: _named(getattr(view_class, name))
            for name in [*View.http_method_names, "dispatch"]
            if hasattr(view_class, name)
        }
    return row


def walk(patterns: list[Any], route: str, regex: str, chain: list[Any]) -> list[dict[str, Any]]:
    from django.urls import URLResolver

    join = URLResolver._join_route
    rows: list[dict[str, Any]] = []
    for pattern in patterns:
        here = join(route, str(pattern.pattern))
        here_regex = join(regex, pattern.pattern.regex.pattern)
        links = [*chain, pattern.pattern]
        if isinstance(pattern, URLResolver):
            rows.extend(walk(pattern.url_patterns, here, here_regex, links))
        else:
            rows.append(_row(pattern, here, here_regex, links))
    return rows


def main(argv: list[str]) -> None:
    sys.path.insert(0, str(Path(argv[1]).resolve()))
    os.environ["DJANGO_SETTINGS_MODULE"] = "shop.settings"
    import django
    from django.urls import get_resolver

    django.setup()
    logging.disable(logging.WARNING)  # Django logs every 405 it answers
    print(json.dumps(walk(get_resolver().url_patterns, "", "", []), indent=2))


if __name__ == "__main__":
    main(sys.argv)
