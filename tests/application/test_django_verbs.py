"""A function view's methods, narrowed by the decorators Django defines (plan
2026-11-22-python-django-core-inbound, Task 4; rulings R10–R12).

A function view serves every method (probe, "Function views"): one row with no method. A
`require_*` decorator of `django.views.decorators.http` narrows it to exactly its set, one row
per method (`annotations` in `django.yml`, the `spring-mvc.yml` words). The rules are Django's own, measured in
`scripts/probes/django_rules.md`; the harness is `test_django_routes`'s.
"""

import json
from pathlib import Path

import pytest
import test_django_routes
from test_django_routes import _handler, _resolved, _rows

libraries = test_django_routes.libraries
orders_django_env = test_django_routes.orders_django_env

_HTTP = (
    "from django.urls import path\n"
    "from django.views.decorators.http import require_GET, require_POST, require_safe, "
    "require_http_methods\n"
    "from django.contrib.auth.decorators import login_required\n"
)


def _view(tmp_path: Path, libraries, body: str, route: str = "path('x/', v)"):
    """The rows of `urls.py` holding `body` and `urlpatterns = [<route>]`."""
    return _rows(
        _resolved(tmp_path, libraries, {"urls.py": _HTTP + body + f"urlpatterns = [{route}]\n"})
    )


_DEF = "def v(request):\n    return None\n"


def test_require_post_serves_post_alone(tmp_path: Path, libraries):
    """Review Focus 3: `@require_POST` gives one POST row and no other (probe: POST 200, GET,
    PUT, DELETE 405)."""
    rows = _view(tmp_path, libraries, "@require_POST\n" + _DEF)

    assert rows == [("POST", None, "/x/", _handler("v"), "resolved")]


def test_require_get_serves_get_alone(tmp_path: Path, libraries):
    """Probe: `require_GET` answers HEAD and OPTIONS 405, so GET is its only row."""
    rows = _view(tmp_path, libraries, "@require_GET\n" + _DEF)

    assert rows == [("GET", None, "/x/", _handler("v"), "resolved")]


def test_require_safe_serves_get_and_head(tmp_path: Path, libraries):
    """Probe: `require_safe` answers GET and HEAD 200. HEAD is a row: the program wrote it."""
    rows = _view(tmp_path, libraries, "@require_safe\n" + _DEF)

    assert rows == [
        ("GET", None, "/x/", _handler("v"), "resolved"),
        ("HEAD", None, "/x/", _handler("v"), "resolved"),
    ]


def test_require_http_methods_serves_its_list(tmp_path: Path, libraries):
    """Review Focus 3: `@require_http_methods(["GET", "POST"])` gives two rows."""
    rows = _view(tmp_path, libraries, "@require_http_methods(['GET', 'POST'])\n" + _DEF)

    assert rows == [
        ("GET", None, "/x/", _handler("v"), "resolved"),
        ("POST", None, "/x/", _handler("v"), "resolved"),
    ]


def test_require_http_methods_by_keyword_serves_its_list(tmp_path: Path, libraries):
    """`method_from: { arg: 0, keyword: request_method_list }` (design 2026-11-23 §4b): the
    list written by keyword is read as the one written by position."""
    rows = _view(
        tmp_path,
        libraries,
        "@require_http_methods(request_method_list=['GET', 'POST'])\n" + _DEF,
    )

    assert rows == [
        ("GET", None, "/x/", _handler("v"), "resolved"),
        ("POST", None, "/x/", _handler("v"), "resolved"),
    ]


def test_require_http_methods_with_a_list_held_in_a_module_name_serves_its_list(
    tmp_path: Path, libraries
):
    """R12: the list is read by the value walk, which reads a list a module name holds when
    its exact values are known (ruled 2026-11-23, `test_fastapi_routes`: "a verb list held in
    a module name is read"): one row per method, `resolved`."""
    rows = _view(
        tmp_path,
        libraries,
        "ALLOWED = ['PUT', 'DELETE']\n@require_http_methods(ALLOWED)\n" + _DEF,
    )

    assert rows == [
        ("DELETE", None, "/x/", _handler("v"), "resolved"),
        ("PUT", None, "/x/", _handler("v"), "resolved"),
    ]


def test_require_http_methods_with_a_list_not_read_guesses_no_method(tmp_path: Path, libraries):
    """R12: a list the walk cannot read (a parameter of an unread call) names no method: the
    row is `unresolved` with method NULL, never the any-method row."""
    rows = _view(
        tmp_path,
        libraries,
        "import os\n@require_http_methods(os.environ['M'].split())\n" + _DEF,
    )

    assert rows == [(None, None, "/x/", _handler("v"), "unresolved")]


def test_no_decorator_is_the_any_method_row(tmp_path: Path, libraries):
    rows = _view(tmp_path, libraries, _DEF)

    assert rows == [(None, "any", "/x/", _handler("v"), "resolved")]


def test_login_required_above_require_post_still_narrows(tmp_path: Path, libraries):
    """`login_required` hands the view on (probe, "View decorators that hand the view on";
    `value-models/django.yml`): the handler is the function, and the `require_POST` below it
    narrows the row."""
    rows = _view(tmp_path, libraries, "@login_required\n@require_POST\n" + _DEF)

    assert rows == [("POST", None, "/x/", _handler("v"), "resolved")]


def test_login_required_below_require_post_still_narrows(tmp_path: Path, libraries):
    rows = _view(tmp_path, libraries, "@require_POST\n@login_required\n" + _DEF)

    assert rows == [("POST", None, "/x/", _handler("v"), "resolved")]


def test_login_required_alone_keeps_the_handler_and_every_method(tmp_path: Path, libraries):
    """R13: `login_required` is a stated pass-through, so the function is the handler; it
    narrows nothing, so the row is the any-method row."""
    rows = _view(tmp_path, libraries, "@login_required\n" + _DEF)

    assert rows == [(None, "any", "/x/", _handler("v"), "resolved")]


def _questions(workspace) -> list[dict]:
    return [
        row
        for row in workspace.query("open_questions")
        if row["question"] == "handler_pass_through"
    ]


def test_a_project_decorator_on_the_def_is_read_through_to_the_function_it_wraps(
    tmp_path: Path, libraries
):
    """The module's own decorator returns an inner function that calls the one it captured
    with what it was given (spec 2026-11-23 §4e): the handler is the wrapped `v`, and the
    `require_POST` under it still narrows the row."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "urls.py": _HTTP
            + "import functools\n"
            + "def audited(f):\n    @functools.wraps(f)\n    def inner(*a):\n        return f(*a)\n"
            + "    return inner\n"
            + "@audited\n@require_POST\n"
            + _DEF
            + "urlpatterns = [path('x/', v)]\n"
        },
    )

    assert _rows(workspace) == [("POST", None, "/x/", _handler("v"), "resolved")]
    assert _questions(workspace) == []


def test_an_unknown_library_decorator_on_the_def_ends_the_handler_walk(tmp_path: Path, libraries):
    """R13, the same for a library decorator no value model states."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "urls.py": _HTTP
            + "from functools import singledispatch\n@singledispatch\n"
            + _DEF
            + "urlpatterns = [path('x/', v)]\n"
        },
    )

    assert _rows(workspace) == [(None, "any", "/x/", None, "partial")]
    (question,) = _questions(workspace)
    ((unread,),) = [json.loads(question["candidates"])[0]["unread"]]
    assert unread["reason"] == "external"
    assert "singledispatch" in unread["detail"]


def test_a_view_imported_from_another_module_is_narrowed(tmp_path: Path, libraries):
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "views.py": "from django.views.decorators.http import require_POST\n"
            "from django.contrib.auth.decorators import login_required\n"
            "@login_required\n@require_POST\ndef buy(request):\n    return None\n",
            "urls.py": "from django.urls import path\nfrom app import views\n"
            "urlpatterns = [path('buy/', views.buy)]\n",
        },
    )

    assert _rows(workspace) == [("POST", None, "/buy/", _handler("buy", "app/views"), "resolved")]


def test_csrf_exempt_in_the_registration_keeps_the_def_narrowed(tmp_path: Path, libraries):
    """Review Focus 3, probe: `csrf_exempt(require_POST(f))` serves POST alone."""
    rows = _view(
        tmp_path,
        libraries,
        "from django.views.decorators.csrf import csrf_exempt\n@require_POST\n" + _DEF,
        "path('x/', csrf_exempt(v))",
    )

    assert rows == [("POST", None, "/x/", _handler("v"), "resolved")]


def test_cache_page_in_the_registration_keeps_the_def_narrowed(tmp_path: Path, libraries):
    """Probe: `cache_page(60)(require_GET(f))` serves GET alone."""
    rows = _view(
        tmp_path,
        libraries,
        "from django.views.decorators.cache import cache_page\n@require_GET\n" + _DEF,
        "path('x/', cache_page(60)(v))",
    )

    assert rows == [("GET", None, "/x/", _handler("v"), "resolved")]


def test_a_narrowing_call_written_in_the_registration_narrows(tmp_path: Path, libraries):
    rows = _view(tmp_path, libraries, _DEF, "path('x/', require_POST(v))")

    assert rows == [("POST", None, "/x/", _handler("v"), "resolved")]


def test_an_unknown_wrapper_in_the_registration_is_partial_with_a_question(
    tmp_path: Path, libraries
):
    """R13: a library wrapper call nothing states hides which function runs: the row keeps its
    path, names no handler, is `partial`, and a `handler_pass_through` question names the call.
    Never a `resolved` any-method row with no handler."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "urls.py": _HTTP
            + "from django.views.decorators.gzip import gzip_page\n"
            + "from django.utils.decorators import decorator_from_middleware\n"
            + "from django.middleware.common import CommonMiddleware\n"
            + "own_wrapper = decorator_from_middleware(CommonMiddleware)\n"
            + _DEF
            + "urlpatterns = [path('x/', own_wrapper(v))]\n"
        },
    )

    assert _rows(workspace) == [(None, "any", "/x/", None, "partial")]
    questions = [
        row
        for row in workspace.query("open_questions")
        if row["question"] == "handler_pass_through"
    ]
    assert len(questions) == 1
    assert json.loads(questions[0]["candidates"])


def test_two_narrowing_decorators_serve_their_intersection(tmp_path: Path, libraries):
    """Django applies both: a method passes only if each allows it."""
    rows = _view(
        tmp_path,
        libraries,
        "@require_POST\n@require_http_methods(['GET', 'POST'])\n" + _DEF,
    )

    assert rows == [("POST", None, "/x/", _handler("v"), "resolved")]


def test_two_narrowing_decorators_with_no_method_in_common_serve_no_method(
    tmp_path: Path, libraries
):
    """Each refuses what it does not list, so no method passes both: no method row."""
    rows = _view(tmp_path, libraries, "@require_POST\n@require_GET\n" + _DEF)

    assert [row[:2] for row in rows] == []


def test_an_unknown_decorator_above_require_post_keeps_the_narrowing_and_asks(
    tmp_path: Path, libraries
):
    """The walk to the function ends at `singledispatch`, which no value model states: the
    handler is not named and a `handler_pass_through` question is asked, and the `require_POST`
    below it still narrows the row (Django runs it on the way to the view)."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "urls.py": _HTTP
            + "from functools import singledispatch\n@singledispatch\n@require_POST\n"
            + _DEF
            + "urlpatterns = [path('x/', v)]\n"
        },
    )

    assert _rows(workspace) == [("POST", None, "/x/", None, "partial")]
    assert len(_questions(workspace)) == 1


def test_a_project_wrapper_in_the_registration_is_followed_into(tmp_path: Path, libraries):
    """A wrapper the module defines is followed into its code, as every catalog's handler is
    (design 2026-11-06-reading-decorators §6): its inner `def` calls the function it captured
    with the request, so the handler is that function (spec 2026-11-23 §4e)."""
    rows = _view(
        tmp_path,
        libraries,
        "def own_wrapper(f):\n    def inner(request):\n        return f(request)\n"
        "    return inner\n" + _DEF,
        "path('x/', own_wrapper(v))",
    )

    assert rows == [(None, "any", "/x/", _handler("v"), "resolved")]


def test_a_handler_read_on_one_path_and_not_on_another_names_no_function(tmp_path: Path, libraries):
    """`deco` hands back `wrap(f)` on one path and what a library call no value model states
    makes on another: the handler is the wrapped `v`, or what was not read. No function is
    named as the one that answers (spec 2026-11-23 §9a); naming `v` would be a guess."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "urls.py": _HTTP
            + "from lib import fallback\n"
            + "def wrap(f):\n    def inner(request):\n        return f(request)\n"
            + "    return inner\n"
            + "def deco(f=None):\n    if f:\n        return wrap(f)\n    return fallback()\n"
            + "@deco\n"
            + _DEF
            + "urlpatterns = [path('x/', v)]\n"
        },
    )

    assert _rows(workspace) == [(None, "any", "/x/", None, "partial")]
    assert len(_questions(workspace)) == 1


def test_a_decorator_that_hands_back_a_bare_function_on_one_path_names_both(
    tmp_path: Path, libraries
):
    """`deco` hands back `wrap(f)` on one path and the bare `wrap` on another (the shape of a
    decorator usable with and without arguments): the walk does not evaluate `if f`, so the
    handler is the wrapped `v` or `wrap` itself, both read, one alternative each."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "urls.py": _HTTP
            + "def wrap(f):\n    def inner(request):\n        return f(request)\n"
            + "    return inner\n"
            + "def deco(f=None):\n    if f:\n        return wrap(f)\n    return wrap\n"
            + "@deco\n"
            + _DEF
            + "urlpatterns = [path('x/', v)]\n"
        },
    )

    assert _rows(workspace) == [
        (None, "any", "/x/", _handler("v"), "narrowed"),
        (None, "any", "/x/", _handler("wrap"), "narrowed"),
    ]


def test_one_decorator_factory_applied_twice_to_one_view_is_not_read(tmp_path: Path, libraries):
    """A known limit (spec 2026-11-23 §9b): the walk enters one helper once on a path, so the
    second application of `guard` on the same view is not followed, and the handler is not
    read: `partial`, never the wrapper."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "urls.py": _HTTP
            + "def guard(name):\n    def deco(f):\n        def inner(request):\n"
            + "            return f(request) if name else None\n"
            + "        return inner\n    return deco\n"
            + "@guard('a')\n@guard('b')\n"
            + _DEF
            + "urlpatterns = [path('x/', v)]\n"
        },
    )

    assert _rows(workspace) == [(None, "any", "/x/", None, "partial")]


def test_an_unknown_wrapper_over_a_narrowing_call_is_partial_and_narrowed(
    tmp_path: Path, libraries
):
    """Review item 2: the unstated wrapper is found over a call, not only over the name; the
    `require_POST` under it still narrows the row."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "urls.py": _HTTP
            + "from functools import singledispatch\n"
            + _DEF
            + "urlpatterns = [path('x/', singledispatch(require_POST(v)))]\n"
        },
    )

    assert _rows(workspace) == [("POST", None, "/x/", None, "partial")]
    assert len(_questions(workspace)) == 1


def test_an_unknown_wrapper_over_a_stated_wrapper_is_partial(tmp_path: Path, libraries):
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "urls.py": _HTTP
            + "from functools import singledispatch\n"
            + "from django.views.decorators.csrf import csrf_exempt\n"
            + _DEF
            + "urlpatterns = [path('x/', singledispatch(csrf_exempt(v)))]\n"
        },
    )

    assert _rows(workspace) == [(None, "any", "/x/", None, "partial")]
    assert len(_questions(workspace)) == 1


def test_login_required_over_a_narrowing_call_in_the_registration(tmp_path: Path, libraries):
    rows = _view(tmp_path, libraries, _DEF, "path('x/', login_required(require_POST(v)))")

    assert rows == [("POST", None, "/x/", _handler("v"), "resolved")]


def test_require_http_methods_publishes_its_list_as_written(tmp_path: Path, libraries):
    """R12: Django compares the list unchanged (probe, "Function views"), so `'get'` is
    published as written, never respelled."""
    rows = _view(tmp_path, libraries, "@require_http_methods(['get'])\n" + _DEF)

    assert rows == [("get", None, "/x/", _handler("v"), "resolved")]


_KEYWORD_ONLY = [
    "@login_required(login_url='/l')\n",
    "@login_required()\n",
    (
        "from django.contrib.admin.views.decorators import staff_member_required\n"
        "@staff_member_required(login_url='/l')\n"
    ),
]


@pytest.mark.parametrize("decorator", _KEYWORD_ONLY)
def test_a_stated_decorator_called_without_the_view_ends_the_handler_walk(
    tmp_path: Path, libraries, decorator: str
):
    """Fix round 2: `login_required(login_url=...)` writes no argument 0, so the value model's
    `result_calls: arg0` (the `d(view)` spelling) states nothing for it, and one entry per call
    cannot state the other spelling too. It ends the handler walk like any unstated decorator:
    `partial`, handler NULL, one question; never `resolved` with no handler."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {"urls.py": _HTTP + decorator + _DEF + "urlpatterns = [path('x/', v)]\n"},
    )

    assert _rows(workspace) == [(None, "any", "/x/", None, "partial")]
    assert len(_questions(workspace)) == 1


@pytest.mark.parametrize("decorator", _KEYWORD_ONLY)
def test_a_stated_decorator_called_without_the_view_still_lets_require_post_narrow(
    tmp_path: Path, libraries, decorator: str
):
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "urls.py": _HTTP
            + decorator
            + "@require_POST\n"
            + _DEF
            + "urlpatterns = [path('x/', v)]\n"
        },
    )

    assert _rows(workspace) == [("POST", None, "/x/", None, "partial")]
    assert len(_questions(workspace)) == 1


@pytest.mark.parametrize(
    "wrapper",
    [
        "login_required(login_url='/l')",
        "login_required()",
        "staff_member_required(login_url='/l')",
    ],
)
def test_the_registration_spelling_of_a_decorator_without_the_view_gives_the_same_row(
    tmp_path: Path, libraries, wrapper: str
):
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "urls.py": _HTTP
            + "from django.contrib.admin.views.decorators import staff_member_required\n"
            + _DEF
            + f"urlpatterns = [path('x/', {wrapper}(v))]\n"
        },
    )

    assert _rows(workspace) == [(None, "any", "/x/", None, "partial")]
    assert len(_questions(workspace)) == 1


def test_any_stated_decorator_called_without_its_function_is_never_resolved_without_a_handler(
    tmp_path: Path, libraries
):
    """The safety net, on a value model that is not Django's: `functools.lru_cache` is stated
    `result_calls: arg0` (`value-models/python-wrappers.yml`); `lru_cache(maxsize=8)` writes no
    argument 0 and returns a decorator, which states nothing."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "urls.py": _HTTP
            + "import functools\n@functools.lru_cache(maxsize=8)\n"
            + _DEF
            + "urlpatterns = [path('x/', v)]\n"
        },
    )

    assert _rows(workspace) == [(None, "any", "/x/", None, "partial")]
    assert len(_questions(workspace)) == 1
