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
from test_django_includes import _SINK, _sunk
from test_django_routes import _handler, _resolved, _rows

from sextant.application.ports.detector import LibraryRoot

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
    """A base this analysis cannot read (a library not installed) comes first in the lookup
    order, so it may define `as_view` itself: the value walk does not read `Items.as_view()` as
    `Items` (design 2026-11-23 §9a, the handler value read by the value walk). The path is
    published, no handler and no method named, never `resolved`."""
    rows = _views(
        tmp_path,
        libraries,
        "from not_installed import Mixin\n"
        "class Items(Mixin, View):\n    def get(self, request):\n        return None\n",
    )

    assert rows == [(None, "any", "/x/", None, "partial")]


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


def test_a_dispatch_override_that_calls_its_parent_keeps_the_verbs(tmp_path: Path, libraries):
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
    """`annotations` and the any-method row stay the function view's (Task 4)."""
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


# Fix round 1 (ruling R14): the auth mixins, every `dispatch` override on the chain read.

_MIXINS = "from django.contrib.auth.mixins import "


def test_login_required_mixin_keeps_the_verbs(tmp_path: Path, libraries):
    """Probe, "Class views": a `LoginRequiredMixin` view answers its verbs for a user that
    passes. `LoginRequiredMixin.dispatch` (a library body) calls `super().dispatch` on the
    passing path; the redirect on the other is the handler's own answer."""
    rows = _views(
        tmp_path,
        libraries,
        _MIXINS + "LoginRequiredMixin\n"
        "class Items(LoginRequiredMixin, View):\n"
        "    def get(self, request):\n        return None\n"
        "    def post(self, request):\n        return None\n",
    )

    assert rows == [
        ("GET", None, "/x/", _handler("get", "app/urls/Items"), "resolved"),
        ("POST", None, "/x/", _handler("post", "app/urls/Items"), "resolved"),
    ]


def test_login_required_mixin_over_a_list_view(tmp_path: Path, libraries):
    rows = _views(
        tmp_path,
        libraries,
        _MIXINS + "LoginRequiredMixin\nfrom django.views.generic import ListView\n"
        "class Items(LoginRequiredMixin, ListView):\n    model = None\n",
    )

    assert rows == [
        (
            "GET",
            None,
            "/x/",
            "sextant-python pypi django 5.2.8 django/views/generic/list/BaseListView#get(sig_",
            "resolved",
        )
    ]


def test_permission_and_test_mixins_keep_the_verbs(tmp_path: Path, libraries):
    rows = _views(
        tmp_path,
        libraries,
        _MIXINS + "PermissionRequiredMixin, UserPassesTestMixin\n"
        "class Perm(PermissionRequiredMixin, View):\n"
        "    permission_required = 'app.perm'\n"
        "    def get(self, request):\n        return None\n"
        "class Passes(UserPassesTestMixin, View):\n"
        "    def test_func(self):\n        return True\n"
        "    def post(self, request):\n        return None\n",
        "path('p/', Perm.as_view()), path('t/', Passes.as_view())",
    )

    assert rows == [
        ("GET", None, "/p/", _handler("get", "app/urls/Perm"), "resolved"),
        ("POST", None, "/t/", _handler("post", "app/urls/Passes"), "resolved"),
    ]


def test_an_own_dispatch_over_login_required_mixin_reads_alike(tmp_path: Path, libraries):
    """The same class with an own `dispatch` calling super: every override on the chain is
    read and hands the request back, so the resolution is the one without it."""
    rows = _views(
        tmp_path,
        libraries,
        _MIXINS + "LoginRequiredMixin\n"
        "class Items(LoginRequiredMixin, View):\n"
        "    def dispatch(self, request, *a, **k):\n"
        "        return super().dispatch(request, *a, **k)\n"
        "    def get(self, request):\n        return None\n",
    )

    assert rows == [("GET", None, "/x/", _handler("get", "app/urls/Items"), "resolved")]


def test_a_project_mixin_that_returns_early_on_one_branch_delegates(tmp_path: Path, libraries):
    """A `dispatch` that answers on one branch and calls `super().dispatch` on the other hands
    the request back, as Django's own mixins do: the class's verbs, `resolved`."""
    rows = _views(
        tmp_path,
        libraries,
        "class Guard:\n"
        "    def dispatch(self, request, *a, **k):\n"
        "        if request.user is None:\n            return None\n"
        "        return super().dispatch(request, *a, **k)\n"
        "class Items(Guard, View):\n    def get(self, request):\n        return None\n",
    )

    assert rows == [("GET", None, "/x/", _handler("get", "app/urls/Items"), "resolved")]


def _stub(tmp_path: Path, text: str) -> LibraryRoot:
    """A distribution `stubviews` beside Django whose `__init__.py` is `text`."""
    site = tmp_path / "stub-site"
    (site / "stubviews").mkdir(parents=True)
    (site / "stubviews" / "__init__.py").write_text(text, encoding="utf-8")
    info = site / "stubviews-1.dist-info"
    info.mkdir()
    (info / "METADATA").write_text("Name: stubviews\nVersion: 1\n", encoding="utf-8")
    (info / "RECORD").write_text("stubviews/__init__.py,,\n", encoding="utf-8")
    return LibraryRoot("stubviews", "1", site)


def _stub_rows(tmp_path: Path, libraries, stub: str, body: str) -> list[tuple[object, ...]]:
    return _rows(
        _resolved(
            tmp_path,
            (*libraries, _stub(tmp_path, stub)),
            {"urls.py": _HEAD + body},
        )
    )


_STUB = "sextant-python pypi stubviews 1 stubviews/"


def test_a_library_base_whose_dispatch_does_not_hand_back_serves_every_method(
    tmp_path: Path, libraries
):
    """A library class whose `dispatch` answers itself: the any-method row, the library's
    `dispatch` the handler. Its body is read (a module class extends the class, ruling
    2026-11-23 option B) and does nothing with the method, so the row is `resolved`."""
    rows = _stub_rows(
        tmp_path,
        libraries,
        "from django.views import View\n"
        "class Answering(View):\n"
        "    def dispatch(self, request, *a, **k):\n        return None\n"
        "    def get(self, request):\n        return None\n",
        "from stubviews import Answering\n"
        "class Items(Answering):\n    pass\n"
        "urlpatterns = [path('x/', Items.as_view())]\n",
    )

    assert rows == [(None, "any", "/x/", _STUB + "Answering#dispatch(sig_", "resolved")]


def test_a_library_dispatch_that_does_not_call_its_parent_is_partial(tmp_path: Path, libraries):
    """DRF's `APIView.dispatch` shape: it never calls `super().dispatch` and picks the handler
    off `request.method.lower()`. One any-method row naming that `dispatch`, `partial` by the
    any-method rule (the body reads the method), never `resolved` (design 2026-11-23 §4c M4)."""
    rows = _stub_rows(
        tmp_path,
        libraries,
        "from django.views import View\n"
        "class APIish(View):\n"
        "    def dispatch(self, request, *a, **k):\n"
        "        handler = getattr(self, request.method.lower(), None)\n"
        "        return handler(request, *a, **k)\n",
        "from stubviews import APIish\n"
        "class Items(APIish):\n    def get(self, request):\n        return None\n"
        "urlpatterns = [path('x/', Items.as_view())]\n",
    )

    assert rows == [(None, "any", "/x/", _STUB + "APIish#dispatch(sig_", "partial")]


def test_a_library_dispatch_that_calls_its_parent_on_one_branch_keeps_the_verbs(
    tmp_path: Path, libraries
):
    """A library `dispatch` that answers on one branch and calls `super().dispatch` on the
    other hands the request back on some path: the class's verbs, `resolved`."""
    rows = _stub_rows(
        tmp_path,
        libraries,
        "from django.views import View\n"
        "class Guarded(View):\n"
        "    def dispatch(self, request, *a, **k):\n"
        "        if request.user is None:\n            return None\n"
        "        return super().dispatch(request, *a, **k)\n",
        "from stubviews import Guarded\n"
        "class Items(Guarded):\n"
        "    def get(self, request):\n        return None\n"
        "    def post(self, request):\n        return None\n"
        "urlpatterns = [path('x/', Items.as_view())]\n",
    )

    assert rows == [
        ("GET", None, "/x/", _handler("get", "app/urls/Items"), "resolved"),
        ("POST", None, "/x/", _handler("post", "app/urls/Items"), "resolved"),
    ]


def test_a_library_class_no_module_class_extends_keeps_its_dispatch_unread(
    tmp_path: Path, libraries
):
    """`Answering.as_view()` straight from the library: no module class has `Answering` in its
    lookup order, so its bodies are not read (the targeted read) and what its `dispatch` does
    is not known: the rows its verbs give, `partial`, never `resolved`."""
    rows = _stub_rows(
        tmp_path,
        libraries,
        "from django.views import View\n"
        "class Answering(View):\n"
        "    def dispatch(self, request, *a, **k):\n        return None\n"
        "    def get(self, request):\n        return None\n",
        "from stubviews import Answering\nurlpatterns = [path('x/', Answering.as_view())]\n",
    )

    assert rows == [("GET", None, "/x/", _STUB + "Answering#get(sig_", "partial")]


def test_an_unread_library_dispatch_on_a_class_of_no_verbs_is_its_any_method_row(
    tmp_path: Path, libraries
):
    """zulip's `SCIMView.as_view(implemented=False)` (OI-549): a library class no module class
    extends, with a `dispatch` and no verb method. Its `dispatch` is what Django calls, and
    whether it hands the request back is not read: the any-method row naming that `dispatch`,
    `partial`, never no row at all."""
    rows = _stub_rows(
        tmp_path,
        libraries,
        "from django.views import View\n"
        "class Answering(View):\n"
        "    def dispatch(self, request, *a, **k):\n        return None\n",
        "from stubviews import Answering\nurlpatterns = [path('x/', Answering.as_view())]\n",
    )

    assert rows == [(None, "any", "/x/", _STUB + "Answering#dispatch(sig_", "partial")]


def test_a_narrowing_wrapper_narrows_the_class_rows(tmp_path: Path, libraries):
    """`require_POST(V.as_view())`: Django answers 405 to every method but POST before the view
    runs (probe, "Function views"), so only the class's POST row stays."""
    rows = _views(
        tmp_path,
        libraries,
        "from django.views.decorators.http import require_POST\n"
        "class Items(View):\n"
        "    def get(self, request):\n        return None\n"
        "    def post(self, request):\n        return None\n",
        "path('x/', require_POST(Items.as_view()))",
    )

    assert rows == [("POST", None, "/x/", _handler("post", "app/urls/Items"), "resolved")]


def test_a_class_handed_through_a_helper_serves_its_verbs(tmp_path: Path, libraries):
    """The handler value is read by the value walk (design 2026-11-23 §9a): `view_of(Items)`
    returns `cls.as_view()`, which is `cls`, which is `Items` at this call."""
    rows = _views(
        tmp_path,
        libraries,
        _ITEMS + "def view_of(cls):\n    return cls.as_view()\n",
        "path('x/', view_of(Items))",
    )

    assert rows == [
        ("DELETE", None, "/x/", _handler("delete", "app/urls/Items"), "resolved"),
        ("GET", None, "/x/", _handler("get", "app/urls/Items"), "resolved"),
    ]


def test_no_member_found_past_a_base_not_read_names_no_method(tmp_path: Path, libraries):
    """A class with no verb method of its own, below a base not read, may serve anything that
    base defines, `as_view` included: one row naming no handler, never `resolved`."""
    rows = _views(
        tmp_path,
        libraries,
        "from not_installed import Mixin\nclass Items(Mixin, View):\n    pass\n",
    )

    assert rows == [(None, "any", "/x/", None, "partial")]


# -- `as_view` read by the value walk (plan 2026-11-23-python-django-redesign, Task 5) ------


def test_as_view_names_the_class_it_is_called_on(tmp_path: Path, libraries):
    """`X.as_view()` hands back a view of the class it is called on (`value-models/django.yml`,
    `returns_receiver` on `View.as_view`): the value is that class, `View` itself as well."""
    sunk = _sunk(
        tmp_path,
        libraries,
        _HEAD + _SINK + _ITEMS + "def read():\n"
        "    sink(Items.as_view())\n    sink(View.as_view())\n",
    )

    assert sunk == [[("app/urls/Items#", None)], [("django/views/generic/base/View#", None)]]


def test_a_stated_call_matches_a_subclass_receiver(tmp_path: Path, libraries):
    """The entry is on `View`; a call on `Sub`, a subclass two levels down through a library
    base (`ListView`), finds it in `Sub`'s lookup order, as Python's own lookup does."""
    sunk = _sunk(
        tmp_path,
        libraries,
        _HEAD
        + "from django.views.generic import ListView\n"
        + _SINK
        + "class Sub(ListView):\n    pass\n"
        "def read():\n    sink(Sub.as_view())\n",
    )

    assert sunk == [[("app/urls/Sub#", None)]]


def test_a_nearer_definition_in_read_code_wins_over_the_entry(tmp_path: Path, libraries):
    """A class nearer in the lookup order than `View` that defines its own `as_view` is what
    runs: the entry does not apply, and that body is followed, for the class and for its
    subclass alike."""
    sunk = _sunk(
        tmp_path,
        libraries,
        _HEAD + _SINK + "class Own(View):\n"
        "    @classmethod\n    def as_view(cls, **kwargs):\n        return 'own'\n"
        "class Deeper(Own):\n    pass\n"
        "def read():\n    sink(Own.as_view())\n    sink(Deeper.as_view())\n",
    )

    assert sunk == [[("own", None)], [("own", None)]]


def test_an_admin_mount_publishes_no_route_of_the_admins_own_body(tmp_path: Path, libraries):
    """`class Mine(admin.ModelAdmin)` has `ModelAdmin`'s bodies read (fact schema 22); the
    `path()` calls of `ModelAdmin.get_urls` register Django's admin, not this module's routes
    (F4 §5.2, `drop_borrowed_endpoints.sql`). The module's own route stays."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "urls.py": _HEAD + "from django.contrib import admin\n"
            "class Mine(admin.ModelAdmin):\n    pass\n"
            "def home(request):\n    return None\n"
            "urlpatterns = [path('admin/', admin.site.urls), path('', home)]\n"
        },
    )

    library = {str(row["symbol"]) for row in workspace.query("header_symbols")}
    assert any("django/contrib/admin/options/ModelAdmin#get_urls" in one for one in library)
    assert not [row for row in workspace.query("endpoints") if row["caller"] in library]
    assert not [
        row
        for row in workspace.query("open_questions")
        if any(one in str(row["candidates"]) for one in library)
    ]
    assert ("/", _handler("home")) in [
        (path, handler) for _, _, path, handler, _ in _rows(workspace)
    ]


def test_a_module_route_with_a_library_handler_stays(tmp_path: Path, libraries):
    """`path('r/', RedirectView.as_view(url='/x'))` is this module's route although its handler
    is the library's `RedirectView.get`: the drop keys on where the registration is written,
    the module's urls."""
    rows = _views(
        tmp_path,
        libraries,
        "from django.views.generic import RedirectView\n",
        "path('r/', RedirectView.as_view(url='/x'))",
    )

    assert [(method, handler) for method, _, _, handler, _ in rows if method == "GET"] == [
        ("GET", "sextant-python pypi django 5.2.8 django/views/generic/base/RedirectView#get(sig_")
    ]


def test_a_class_narrowed_through_a_project_helper_keeps_the_allowed_rows(
    tmp_path: Path, libraries
):
    """Final review C1: the stated call the value walk passed through inside the helper
    narrows the class's rows as one written in the registration does."""
    rows = _views(
        tmp_path,
        libraries,
        "from django.views.decorators.http import require_POST\n"
        "class Items(View):\n"
        "    def get(self, request):\n        return None\n"
        "    def post(self, request):\n        return None\n"
        "def post_only(view):\n    return require_POST(view)\n",
        "path('x/', post_only(Items.as_view()))",
    )

    assert rows == [("POST", None, "/x/", _handler("post", "app/urls/Items"), "resolved")]
