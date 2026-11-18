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
