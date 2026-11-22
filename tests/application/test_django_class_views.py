"""Class views behind `path`: one row per verb method the class defines (plan
2026-11-22-python-django-core-inbound, Task 5; ruling R3).

`path("x/", Items.as_view())` serves the names in `http_method_names` that the class defines,
own or inherited, project bases and library bases alike (probe, "Class views"). The handler
of each row is the verb method, on the class that defines it. `View.options` and the
automatic `head` that `View.setup` sets are Django's own answers, never rows; a class that
overrides `dispatch` without calling `super().dispatch` answers every method itself, so its
row is the any-method row with `dispatch` as the handler. The rules are Django's own,
measured in `scripts/probes/django_rules.md`; the harness is `test_django_routes`'s.
"""

from pathlib import Path

import test_django_routes
from test_django_routes import _handler, _resolved, _rows

libraries = test_django_routes.libraries
orders_django_env = test_django_routes.orders_django_env

_HEAD = "from django.urls import path\nfrom django.views import View\n"
_LIBRARY = "sextant-python pypi django 5.2.8 django/views/generic/base/"


def _views(tmp_path: Path, libraries, body: str, route: str = "path('x/', Items.as_view())"):
    """The rows of `urls.py` holding `body` and `urlpatterns = [<route>]`."""
    return _rows(
        _resolved(tmp_path, libraries, {"urls.py": _HEAD + body + f"urlpatterns = [{route}]\n"})
    )


def _questions(workspace) -> list[dict]:
    return [
        row
        for row in workspace.query("open_questions")
        if row["question"] == "handler_pass_through"
    ]


_ITEMS = (
    "class Items(View):\n"
    "    def get(self, request):\n        return None\n"
    "    def delete(self, request):\n        return None\n"
)


def test_a_view_subclass_serves_the_verbs_it_defines(tmp_path: Path, libraries):
    """Probe: `as_view()` dispatches only methods the class defines. No OPTIONS row
    (`View.options`, the framework's own) and no HEAD row (`View.setup`'s automatic `head`)."""
    rows = _views(tmp_path, libraries, _ITEMS)

    assert rows == [
        ("DELETE", None, "/x/", _handler("delete", "app/urls/Items"), "resolved"),
        ("GET", None, "/x/", _handler("get", "app/urls/Items"), "resolved"),
    ]


def test_verbs_inherited_from_a_project_base(tmp_path: Path, libraries):
    """Probe: verb methods are inherited through the MRO; each row names the class that
    defines the method."""
    rows = _views(
        tmp_path,
        libraries,
        _ITEMS + "class Child(Items):\n    def post(self, request):\n        return None\n",
        "path('x/', Child.as_view())",
    )

    assert rows == [
        ("DELETE", None, "/x/", _handler("delete", "app/urls/Items"), "resolved"),
        ("GET", None, "/x/", _handler("get", "app/urls/Items"), "resolved"),
        ("POST", None, "/x/", _handler("post", "app/urls/Child"), "resolved"),
    ]


def test_a_library_base_supplies_the_verb(tmp_path: Path, libraries):
    """`TemplateView` defines `get`: a subclass that defines no verb serves GET, its handler
    the library's method."""
    rows = _views(
        tmp_path,
        libraries,
        "from django.views.generic import TemplateView\n"
        "class Home(TemplateView):\n    template_name = 'home.html'\n",
        "path('x/', Home.as_view())",
    )

    assert rows == [("GET", None, "/x/", f"{_LIBRARY}TemplateView#get(sig_", "resolved")]


def test_a_library_class_called_directly_with_initkwargs(tmp_path: Path, libraries):
    """`TemplateView.as_view(template_name="x")`: an initkwarg other than `http_method_names`
    changes no verb (probe: `as_view(**initkwargs)` sets instance attributes)."""
    rows = _views(
        tmp_path,
        libraries,
        "from django.views.generic import TemplateView\n",
        "path('x/', TemplateView.as_view(template_name='a.html'))",
    )

    assert rows == [("GET", None, "/x/", f"{_LIBRARY}TemplateView#get(sig_", "resolved")]


def test_a_class_imported_from_another_file(tmp_path: Path, libraries):
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "views.py": "from django.views import View\n" + _ITEMS,
            "urls.py": "from django.urls import path\nfrom app.views import Items\n"
            "urlpatterns = [path('items/', Items.as_view())]\n",
        },
    )

    assert _rows(workspace) == [
        ("DELETE", None, "/items/", _handler("delete", "app/views/Items"), "resolved"),
        ("GET", None, "/items/", _handler("get", "app/views/Items"), "resolved"),
    ]


def test_a_class_whose_base_is_not_read_is_partial(tmp_path: Path, libraries):
    """A base this analysis cannot read (a library not installed) may define more verbs: the
    verbs found are published, never `resolved`."""
    rows = _views(
        tmp_path,
        libraries,
        "from not_installed import Mixin\n"
        "class Items(Mixin, View):\n    def get(self, request):\n        return None\n",
    )

    assert rows == [("GET", None, "/x/", _handler("get", "app/urls/Items"), "partial")]


def test_an_own_head_is_a_row_and_an_own_options_is_a_row(tmp_path: Path, libraries):
    """Probe: an own `head` is kept (203) and a subclass `options` replaces `View.options`:
    both are methods the program wrote."""
    rows = _views(
        tmp_path,
        libraries,
        "class Items(View):\n"
        "    def get(self, request):\n        return None\n"
        "    def head(self, request):\n        return None\n"
        "    def options(self, request):\n        return None\n",
    )

    assert rows == [
        ("GET", None, "/x/", _handler("get", "app/urls/Items"), "resolved"),
        ("HEAD", None, "/x/", _handler("head", "app/urls/Items"), "resolved"),
        ("OPTIONS", None, "/x/", _handler("options", "app/urls/Items"), "resolved"),
    ]


def test_a_class_with_no_verb_methods_has_no_row(tmp_path: Path, libraries):
    """Probe: a `View` subclass with no verb methods answers 405 to every method but OPTIONS,
    which `View.options` answers: nothing the program wrote is served."""
    rows = _views(tmp_path, libraries, "class Items(View):\n    pass\n")

    assert rows == []


def test_a_dispatch_override_serves_every_method(tmp_path: Path, libraries):
    """Probe: a class that overrides `dispatch` answers every method itself. One any-method
    row, the handler `dispatch`; the `get` it also defines is never reached by Django."""
    rows = _views(
        tmp_path,
        libraries,
        "class Items(View):\n"
        "    def dispatch(self, request, *a, **k):\n        return None\n"
        "    def get(self, request):\n        return None\n",
    )

    assert rows == [(None, "any", "/x/", _handler("dispatch", "app/urls/Items"), "resolved")]


def test_a_dispatch_override_that_calls_super_keeps_the_verbs(tmp_path: Path, libraries):
    """Probe: a `dispatch` override that calls `super().dispatch` keeps `View.dispatch`'s
    verb lookup (GET 200, POST 405), the servlet catalog's delegating `service()`."""
    rows = _views(
        tmp_path,
        libraries,
        "class Items(View):\n"
        "    def dispatch(self, request, *a, **k):\n"
        "        return super().dispatch(request, *a, **k)\n"
        "    def get(self, request):\n        return None\n",
    )

    assert rows == [("GET", None, "/x/", _handler("get", "app/urls/Items"), "resolved")]


def test_a_class_http_method_names_leaves_the_verbs_partial(tmp_path: Path, libraries):
    """Probe: `http_method_names = ['get']` on a class that defines `post` leaves POST 405.
    The attribute is not read here (a stated boundary): every verb row is `partial`, never a
    `resolved` POST."""
    rows = _views(
        tmp_path,
        libraries,
        "class Items(View):\n"
        "    http_method_names = ['get']\n"
        "    def get(self, request):\n        return None\n"
        "    def post(self, request):\n        return None\n",
    )

    assert rows == [
        ("GET", None, "/x/", _handler("get", "app/urls/Items"), "partial"),
        ("POST", None, "/x/", _handler("post", "app/urls/Items"), "partial"),
    ]


def test_an_http_method_names_initkwarg_leaves_the_verbs_partial(tmp_path: Path, libraries):
    """Probe: `as_view(http_method_names=['post'])` replaces the list for that route."""
    rows = _views(
        tmp_path,
        libraries,
        _ITEMS,
        "path('x/', Items.as_view(http_method_names=['get']))",
    )

    assert rows == [
        ("DELETE", None, "/x/", _handler("delete", "app/urls/Items"), "partial"),
        ("GET", None, "/x/", _handler("get", "app/urls/Items"), "partial"),
    ]


def test_a_stated_pass_through_wrapper_keeps_the_rows(tmp_path: Path, libraries):
    """`login_required` and `csrf_exempt` hand the view on (`value-models/django.yml`)."""
    rows = _views(
        tmp_path,
        libraries,
        "from django.contrib.auth.decorators import login_required\n"
        "from django.views.decorators.csrf import csrf_exempt\n" + _ITEMS,
        "path('x/', login_required(Items.as_view())), path('y/', csrf_exempt(Items.as_view()))",
    )

    assert rows == [
        ("DELETE", None, "/x/", _handler("delete", "app/urls/Items"), "resolved"),
        ("DELETE", None, "/y/", _handler("delete", "app/urls/Items"), "resolved"),
        ("GET", None, "/x/", _handler("get", "app/urls/Items"), "resolved"),
        ("GET", None, "/y/", _handler("get", "app/urls/Items"), "resolved"),
    ]


def test_an_unstated_wrapper_is_partial_with_a_question(tmp_path: Path, libraries):
    """Task 4's convention (R13): a wrapper no value model states hides what runs: one row,
    no handler, `partial`, and a `handler_pass_through` question."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "urls.py": _HEAD
            + "from django.utils.decorators import decorator_from_middleware\n"
            + "from django.middleware.common import CommonMiddleware\n"
            + "own_wrapper = decorator_from_middleware(CommonMiddleware)\n"
            + _ITEMS
            + "urlpatterns = [path('x/', own_wrapper(Items.as_view()))]\n"
        },
    )

    assert _rows(workspace) == [(None, "any", "/x/", None, "partial")]
    assert len(_questions(workspace)) == 1


def test_method_decorator_on_the_class_hides_no_verb(tmp_path: Path, libraries):
    """`method_decorator(login_required, name="dispatch")` was not measured and is not
    modelled. Pinned: it must neither hide the verbs nor publish an any-method row."""
    rows = _views(
        tmp_path,
        libraries,
        "from django.contrib.auth.decorators import login_required\n"
        "from django.utils.decorators import method_decorator\n"
        "@method_decorator(login_required, name='dispatch')\n" + _ITEMS,
    )

    assert rows == [
        ("DELETE", None, "/x/", _handler("delete", "app/urls/Items"), "resolved"),
        ("GET", None, "/x/", _handler("get", "app/urls/Items"), "resolved"),
    ]


def test_a_function_view_beside_a_class_view_keeps_its_row(tmp_path: Path, libraries):
    """`narrowed_by` and the any-method row stay the function view's (Task 4)."""
    rows = _views(
        tmp_path,
        libraries,
        "from django.views.decorators.http import require_POST\n"
        "@require_POST\ndef buy(request):\n    return None\n" + _ITEMS,
        "path('buy/', buy), path('x/', Items.as_view())",
    )

    assert rows == [
        ("DELETE", None, "/x/", _handler("delete", "app/urls/Items"), "resolved"),
        ("GET", None, "/x/", _handler("get", "app/urls/Items"), "resolved"),
        ("POST", None, "/buy/", _handler("buy"), "resolved"),
    ]
