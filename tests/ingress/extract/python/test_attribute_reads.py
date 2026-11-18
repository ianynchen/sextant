"""`PythonScanner`: an attribute read on a value of a known class is a read of the field the
class declares (plan 3 ruling R23, fact schema 15).

`s.url` with `s: Service` writes `{"kind": "field", "symbol": "app/run/Service#url."}`, the
DEFINING class's field (a JVM GETFIELD names it the same way), where it wrote `unresolved`.
A module-level name another file of the module writes from one class's construction
(`settings = Settings()`) holds that class, for a read of its fields; a write in a third file
is not seen, as for `ProjectHeaders.class_object` (R17). Every tree is built in `tmp_path`;
nothing is imported or run."""

from pathlib import Path

from test_generics import _owner_of, _sites, _write

from sextant.application.ports.scanner import ScanRequest
from sextant.domain.factfile import read_fact_tree
from sextant.ingress.extract.python.scanner import PythonScanner


def _scan(tmp_path: Path, files: dict[str, str]):
    root = tmp_path / "src"
    for name, text in files.items():
        _write(root / name, text)
    out = tmp_path / "facts"
    PythonScanner().scan(
        ScanRequest(
            module_id="shop",
            coordinates="shop",
            version="1.0.0",
            classes_dir=root,
            out_dir=out,
        )
    )
    return read_fact_tree(out)


def _argument(tree, caller: str, name: str):
    (site,) = [site for site in _sites(tree, caller) if site.target.name == name]
    return site.arguments[0]


_CLASSES = (
    "def send(x): ...\n"
    "def other(x): ...\n"
    "def third(x): ...\n"
    "class Base:\n"
    "    url: str = 'https://base.example'\n"
    "class Service(Base):\n"
    "    name: str\n"
    "    def __init__(self):\n"
    "        self.extra = 1\n"
)


def test_an_attribute_a_class_declares_is_a_read_of_its_defining_field(tmp_path: Path):
    tree = _scan(
        tmp_path,
        {
            "app/run.py": _CLASSES + "def f(s: Service):\n"
            "    send(s.name)\n"
            "    other(s.url)\n"
            "    third(s.extra)\n"
        },
    )
    name = _argument(tree, "app/run#f", "send")
    assert (name.kind, name.symbol) == ("field", "app/run/Service#name.")
    # Inherited: the class that declares it, as the lookup finds it.
    url = _argument(tree, "app/run#f", "other")
    assert (url.kind, url.symbol) == ("field", "app/run/Base#url.")
    # Assigned in `__init__` only, declared in no class body: not read as a field.
    assert _argument(tree, "app/run#f", "third").kind == "unresolved"


def test_a_variable_another_file_constructs_once_holds_that_class(tmp_path: Path):
    tree = _scan(
        tmp_path,
        {
            "app/__init__.py": "",
            "app/conf.py": _CLASSES + "settings = Service()\n",
            "app/run.py": "from app.conf import settings, send\n"
            "def f():\n"
            "    send(settings.url)\n"
            "    settings.reload()\n",
        },
    )
    url = _argument(tree, "app/run#f", "send")
    assert (url.kind, url.symbol) == ("field", "app/conf/Base#url.")
    # A call's owner stays the resolver's (design 2026-11-06 §3b: a third file may write the
    # name; `bound_receivers` settles it from every write).
    assert _owner_of(tree, "app/run#f", "reload") == [None]


def _typed_return(tmp_path: Path, factory: str, tail: str = ""):
    return _scan(
        tmp_path,
        {
            "app/__init__.py": "",
            "app/conf.py": _CLASSES + factory + "settings = get_settings()\n" + tail,
            "app/run.py": "from app.conf import settings, send\ndef f():\n    send(settings.url)\n",
        },
    )


def test_a_variable_from_a_typed_return_call_holds_the_class(tmp_path: Path):
    tree = _typed_return(
        tmp_path,
        "from functools import lru_cache\n@lru_cache\ndef get_settings() -> Service:\n    return Service()\n",
    )
    url = _argument(tree, "app/run#f", "send")
    assert (url.kind, url.symbol) == ("field", "app/conf/Base#url.")


def test_an_unannotated_factory_leaves_the_variable_untyped(tmp_path: Path):
    tree = _typed_return(tmp_path, "def get_settings():\n    return Service()\n")
    assert _argument(tree, "app/run#f", "send").kind == "unresolved"


def test_a_class_returning_factory_is_not_an_instance(tmp_path: Path):
    tree = _typed_return(tmp_path, "def get_settings() -> type[Service]:\n    return Service\n")
    assert _argument(tree, "app/run#f", "send").kind == "unresolved"


def test_a_reassigned_variable_stays_untyped(tmp_path: Path):
    tree = _typed_return(
        tmp_path,
        "def get_settings() -> Service:\n    return Service()\n",
        "settings = None\n",
    )
    assert _argument(tree, "app/run#f", "send").kind == "unresolved"


def test_a_call_of_a_call_through_def_anywhere_is_typed_by_its_return(tmp_path: Path):
    # The wrapper returns what the def returns, so a call inside a function is typed too.
    tree = _scan(
        tmp_path,
        {
            "app/__init__.py": "",
            "app/conf.py": _CLASSES
            + "from functools import lru_cache\n"
            + "@lru_cache\ndef get_settings() -> Service:\n    return Service()\n",
            "app/run.py": "from app.conf import get_settings, send\n"
            "def f():\n"
            "    x = get_settings()\n"
            "    send(x.url)\n",
        },
    )
    url = _argument(tree, "app/run#f", "send")
    assert (url.kind, url.symbol) == ("field", "app/conf/Base#url.")


def test_a_call_form_decorator_leaves_the_return_unread(tmp_path: Path):
    tree = _typed_return(
        tmp_path,
        "from functools import lru_cache\n"
        "@lru_cache(maxsize=None)\ndef get_settings() -> Service:\n    return Service()\n",
    )
    assert _argument(tree, "app/run#f", "send").kind == "unresolved"


def test_a_variable_written_from_two_classes_holds_neither(tmp_path: Path):
    tree = _scan(
        tmp_path,
        {
            "app/__init__.py": "",
            "app/conf.py": _CLASSES + "settings = Service()\nif flag:\n    settings = Base()\n",
            "app/run.py": "from app.conf import settings, send\n"
            "def f():\n"
            "    send(settings.url)\n"
            "    settings.reload()\n",
        },
    )
    assert _argument(tree, "app/run#f", "send").kind == "unresolved"
    assert _owner_of(tree, "app/run#f", "reload") == [None]


def test_a_guard_names_the_field_each_typed_read_of_its_test_is(tmp_path: Path):
    # R27: `guards[].fields` maps a read's text to the field symbol the same read would be as a
    # call argument; a read the scanner cannot type is absent from it.
    tree = _scan(
        tmp_path,
        {
            "app/__init__.py": "",
            "app/conf.py": _CLASSES + "settings = Service()\n",
            "app/run.py": "from app.conf import settings, send\n"
            "import os\n"
            "if settings.url and os.name and unknown.x:\n"
            "    send(1)\n",
        },
    )
    (site,) = [s for s in _sites(tree, "app/run#<clinit>") if s.target.name == "send"]
    (guard,) = site.guards
    # `os.name` is a library module's variable, read as the call argument reads it.
    assert guard.fields == {"settings.url": "app/conf/Base#url.", "os.name": "os#name."}


_MODELS = "class Service:\n    url: str = 'https://x.example'\n"
_READ = "from app.pkg import Service\ndef send(x): ...\ndef f(s: Service):\n    send(s.url)\n"


def _starred(tmp_path: Path, files: dict[str, str]):
    """`app/run.py` reads `Service` from the package `app/pkg`, whose files are `files`."""
    return _argument(
        _scan(
            tmp_path,
            {
                "app/__init__.py": "",
                **{f"app/pkg/{name}": text for name, text in files.items()},
                "app/run.py": _READ,
            },
        ),
        "app/run#f",
        "send",
    )


def test_a_name_a_package_star_re_exports_is_the_class_it_defines(tmp_path: Path):
    url = _starred(tmp_path, {"__init__.py": "from .models import *\n", "models.py": _MODELS})
    assert (url.kind, url.symbol) == ("field", "app/pkg/models/Service#url.")


def test_a_star_exports_only_what_all_lists(tmp_path: Path):
    url = _starred(
        tmp_path,
        {
            "__init__.py": "from .models import *\n",
            "models.py": "__all__ = ['Other']\nclass Other: ...\n" + _MODELS,
        },
    )
    assert url.kind == "unresolved"


def test_a_star_carries_a_name_all_lists(tmp_path: Path):
    url = _starred(
        tmp_path,
        {
            "__init__.py": "from .models import *\n",
            "models.py": "__all__ = ['Service']\n" + _MODELS,
        },
    )
    assert url.kind == "field"


def test_a_star_leaves_a_leading_underscore_name_behind(tmp_path: Path):
    url = _starred(
        tmp_path,
        {
            "__init__.py": "from .models import *\n",
            "models.py": _MODELS.replace("Service", "_Service"),
        },
    )
    assert url.kind == "unresolved"


def test_an_explicit_binding_beats_a_star_name(tmp_path: Path):
    url = _starred(
        tmp_path,
        {
            "__init__.py": "from .models import *\nfrom .own import Service\n",
            "models.py": _MODELS.replace("url", "star_url"),
            "own.py": _MODELS,
        },
    )
    assert (url.kind, url.symbol) == ("field", "app/pkg/own/Service#url.")


def test_a_later_star_wins_over_an_earlier_one(tmp_path: Path):
    url = _starred(
        tmp_path,
        {
            "__init__.py": "from .first import *\nfrom .second import *\n",
            "first.py": _MODELS.replace("url", "first_url"),
            "second.py": _MODELS,
        },
    )
    assert (url.kind, url.symbol) == ("field", "app/pkg/second/Service#url.")


def test_a_star_chain_is_followed_to_the_definition(tmp_path: Path):
    url = _starred(
        tmp_path,
        {
            "__init__.py": "from .middle import *\n",
            "middle.py": "from .models import *\n",
            "models.py": _MODELS,
        },
    )
    assert (url.kind, url.symbol) == ("field", "app/pkg/models/Service#url.")


def test_a_star_cycle_ends_with_the_name_unresolved(tmp_path: Path):
    url = _starred(
        tmp_path,
        {
            "__init__.py": "from .a import *\n",
            "a.py": "from .b import *\n",
            "b.py": "from .a import *\n",
        },
    )
    assert url.kind == "unresolved"


def test_an_imported_call_through_factory_types_the_variable(tmp_path: Path):
    tree = _scan(
        tmp_path,
        {
            "app/__init__.py": "",
            "app/factory.py": _CLASSES
            + "from functools import lru_cache\n"
            + "@lru_cache\ndef get_settings() -> Service:\n    return Service()\n",
            "app/conf.py": "from app.factory import get_settings\nsettings = get_settings()\n",
            "app/run.py": "from app.conf import settings\n"
            "from app.factory import send\n"
            "def f():\n"
            "    send(settings.url)\n",
        },
    )
    url = _argument(tree, "app/run#f", "send")
    assert (url.kind, url.symbol) == ("field", "app/factory/Base#url.")


def test_a_call_through_factory_returning_a_star_re_exported_class(tmp_path: Path):
    # The mealie shape: the return names a class the package only star-re-exports, and
    # another file binds the variable from the imported factory.
    tree = _scan(
        tmp_path,
        {
            "app/__init__.py": "",
            "app/pkg/__init__.py": "from .models import *\n",
            "app/pkg/models.py": _MODELS,
            "app/factory.py": "from functools import lru_cache\nfrom app.pkg import Service\n"
            "@lru_cache\ndef get_settings() -> Service:\n    return Service()\n",
            "app/conf.py": "from app.factory import get_settings\nsettings = get_settings()\n",
            "app/run.py": "from app.conf import settings\n"
            "def send(x): ...\n"
            "def f():\n"
            "    send(settings.url)\n",
        },
    )
    url = _argument(tree, "app/run#f", "send")
    assert (url.kind, url.symbol) == ("field", "app/pkg/models/Service#url.")
