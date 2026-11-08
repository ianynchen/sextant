"""The scanner types constructions (plan 2026-11-08-python-fastapi-inbound Task 4b, ruling R17;
design 2026-11-06-reading-decorators §3b, option A).

Calling a class, of a library or of the module, gives an instance of it, and a name a value of
`type[X]` is bound to is the class `X`. A later call on the name is written with that owner,
as click's `Group` is. A module-level name takes the types written to it in its own file only:
a write in another file is the resolver's.

Every library is a fake one built in `tmp_path` (`test_libraries._install`): nothing is
installed, imported or run."""

from pathlib import Path

from test_libraries import _install, _library_symbols, _scan, _sites

from sextant.application.ports.detector import LibraryRoot

# A FastAPI shaped as the real one is: the classes are defined in submodules and re-exported
# by the package.
_FASTAPI = {
    "fastapi/__init__.py": (
        "from .applications import FastAPI as FastAPI\nfrom .routing import APIRouter as APIRouter\n"
    ),
    "fastapi/applications.py": (
        "class FastAPI:\n    def get(self, path: str):\n        return lambda f: f\n"
    ),
    "fastapi/routing.py": (
        "class APIRoute:\n    pass\n"
        "class APIRouter:\n"
        "    def __init__(self, prefix: str = ''):\n        self.prefix = prefix\n"
        "    def get(self, path: str):\n        return lambda f: f\n"
    ),
    "fastapi/py.typed": "",
}
_APP = "fastapi/applications/FastAPI#"
_ROUTER = "fastapi/routing/APIRouter#"


def _fastapi(tmp_path: Path) -> LibraryRoot:
    return _install(tmp_path / "site", "fastapi", "0.162.0", _FASTAPI)


def _calls(tree, caller: str) -> list[tuple[str | None, str | None, str]]:
    return [
        (site.target.owner, site.target.name, site.invoke_kind) for site in _sites(tree, caller)
    ]


def test_a_library_class_call_types_the_name_it_is_bound_to(tmp_path: Path):
    """`app = FastAPI()`: the call stays the static call the file writes (the resolver reads
    it as the construction), and its result is a `FastAPI`, so `app.get` is written with that
    owner. A local name in a function is typed by the same rule."""
    _, tree = _scan(
        tmp_path,
        {
            "app/main.py": "from fastapi import FastAPI, APIRouter\n"
            "app = FastAPI()\n"
            "@app.get('/health')\n"
            "def health():\n    return 1\n"
            "def build():\n"
            "    r = APIRouter(prefix='/r')\n"
            "    r.get('/x')\n"
        },
        (_fastapi(tmp_path),),
    )

    assert _calls(tree, "app/main#<clinit>") == [
        ("fastapi/applications#", "FastAPI", "static"),
        (_APP, "get", "virtual"),
        (None, "__call__", "virtual"),
    ]
    assert _calls(tree, "app/main#build") == [
        ("fastapi/routing#", "APIRouter", "static"),
        (_ROUTER, "get", "virtual"),
    ]


def test_a_type_of_x_factory_in_another_file_types_the_construction(tmp_path: Path):
    """Polar's shape: `kit.py` defines a factory whose written return is `type[_APIRouter]`,
    `routing.py` binds `APIRouter` to a call of it, and `orders.py` calls that name. The name
    is the class `X` through the project headers, so the call is a `virtual <init>` of `X`
    (`X` or a subclass, R37) read through the name's field, and the name it is bound to is
    an `X`. The same holds in the file that binds it."""
    _, tree = _scan(
        tmp_path,
        {
            "app/__init__.py": "",
            "app/kit.py": "from fastapi import APIRouter as _APIRouter\n"
            "from fastapi.routing import APIRoute\n"
            "def get_cls(route: type[APIRoute]) -> type[_APIRouter]:\n"
            "    class R(_APIRouter):\n        pass\n"
            "    return R\n",
            "app/routing.py": "from fastapi.routing import APIRoute\n"
            "from app.kit import get_cls\n"
            "APIRouter = get_cls(APIRoute)\n"
            "local = APIRouter()\n"
            "local.get('/l')\n",
            "app/orders.py": "from app.routing import APIRouter\n"
            "router = APIRouter(prefix='/orders')\n"
            "@router.get('/x')\n"
            "def h():\n    return 1\n",
        },
        (_fastapi(tmp_path),),
    )

    (made,) = [s for s in _sites(tree, "app/orders#<clinit>") if s.target.name == "<init>"]
    assert made.receiver_field == "app/routing#APIRouter."
    assert _calls(tree, "app/orders#<clinit>") == [
        (_ROUTER, "<init>", "virtual"),
        (_ROUTER, "get", "virtual"),
        (None, "__call__", "virtual"),
    ]
    assert _calls(tree, "app/routing#<clinit>")[-2:] == [
        (_ROUTER, "<init>", "virtual"),
        (_ROUTER, "get", "virtual"),
    ]


def test_a_project_class_construction_types_its_name(tmp_path: Path):
    """A class of another file of the module follows the same rule as a library one:
    `from app.a import Session; s = Session()` makes `s.get` a call on `Session`."""
    _, tree = _scan(
        tmp_path,
        {
            "app/__init__.py": "",
            "app/a.py": "class Session:\n    def get(self, path):\n        return path\n",
            "app/b.py": "from app.a import Session\n"
            "s = Session()\n"
            "s.get('/a')\n"
            "def run():\n"
            "    t = Session()\n"
            "    t.get('/b')\n",
        },
        (),
    )

    assert _calls(tree, "app/b#<clinit>") == [
        ("app/a#", "Session", "static"),
        ("app/a/Session#", "get", "virtual"),
    ]
    assert _calls(tree, "app/b#run") == [
        ("app/a#", "Session", "static"),
        ("app/a/Session#", "get", "virtual"),
    ]


def test_a_name_written_two_classes_is_the_closed_list(tmp_path: Path):
    """`app` is a `FastAPI` on one branch and an `APIRouter` on the other: the closed list
    is never narrowed to one, so the call names no owner and the resolver reads each path."""
    _, tree = _scan(
        tmp_path,
        {
            "app/main.py": "import os\n"
            "from fastapi import FastAPI, APIRouter\n"
            "app = FastAPI()\n"
            "if os.environ:\n"
            "    app = APIRouter()\n"
            "app.get('/x')\n"
        },
        (_fastapi(tmp_path),),
    )

    (get,) = [s for s in _sites(tree, "app/main#<clinit>") if s.target.name == "get"]
    assert get.target.owner is None
    assert get.receiver_field == "app/main#app."


def test_a_class_only_a_static_call_names_gets_a_header(tmp_path: Path):
    """`FastAPI()` names the class only as a static call on its module. The class gets a
    type header all the same, so the resolver can read the call as its construction."""
    _, tree = _scan(
        tmp_path,
        {"app/main.py": "from fastapi import FastAPI\napp = FastAPI()\n"},
        (_fastapi(tmp_path),),
    )

    assert _APP in _library_symbols(tree)


def test_a_name_rebound_in_another_file_is_not_typed_here(tmp_path: Path):
    """`app` is a `FastAPI` in `a.py`, where it is written. `b.py` writes it again, and
    `c.py` reads it: a write in another file is the resolver's (design §3b), so in `c.py`
    the call names no owner. In `a.py` the name keeps the type its own writes give."""
    _, tree = _scan(
        tmp_path,
        {
            "app/__init__.py": "",
            "app/a.py": "from fastapi import FastAPI\napp = FastAPI()\napp.get('/a')\n",
            "app/b.py": "from fastapi import APIRouter\nfrom app import a\na.app = APIRouter()\n",
            "app/c.py": "from app.a import app\napp.get('/c')\n",
        },
        (_fastapi(tmp_path),),
    )

    assert _calls(tree, "app/a#<clinit>")[-1] == (_APP, "get", "virtual")
    (get,) = _sites(tree, "app/c#<clinit>")
    assert get.target.owner is None
