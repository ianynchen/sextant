"""`PythonScanner` part 1 (spec 2026-11-06 §3a): the structure of one Python file as the
existing facts — modules and classes as types, a body as `<clinit>`, module-level names as
static fields, decorators as the calls they are. Every tree is built in `tmp_path`; nothing
is imported or run."""

import sys
from pathlib import Path

import pytest

from sextant.application.ports.scanner import ScanRequest
from sextant.domain.factfile import read_fact_tree
from sextant.domain.facts import (
    AnnotationFact,
    CallArgument,
    CallSiteFact,
    Document,
    FieldWriteFact,
    ParentsUnread,
    SymbolFact,
    TypeParameter,
    TypeRef,
)
from sextant.domain.ignorefile import IgnoreRules
from sextant.domain.symbols import PY_SIGNATURE, bare_descriptor, disambiguator_of, names_a_type
from sextant.ingress.extract.python.scanner import PythonScanner

DIS = disambiguator_of(PY_SIGNATURE)


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _scan(
    tmp_path: Path,
    files: dict[str, str],
    *,
    coordinates: str = ".",
    version: str = ".",
    ignore: IgnoreRules | None = None,
):
    root = tmp_path / "src"
    for relative, text in files.items():
        _write(root / relative, text)
    out = tmp_path / "facts"
    report = PythonScanner().scan(
        ScanRequest(
            module_id="shop",
            coordinates=coordinates,
            version=version,
            classes_dir=root,
            out_dir=out,
            ignore=ignore,
        )
    )
    return report, read_fact_tree(out)


def _facts(tree, kind):
    return [fact for _, _, facts in tree for fact in facts if isinstance(fact, kind)]


def _symbols(tree) -> dict[str, list[SymbolFact]]:
    found: dict[str, list[SymbolFact]] = {}
    for fact in _facts(tree, SymbolFact):
        found.setdefault(bare_descriptor(fact.symbol), []).append(fact)
    return found


def test_scanner_declares_what_it_reads_and_accepts_python():
    scanner = PythonScanner()

    assert scanner.accepts({"python"})
    assert not scanner.accepts({"java"})
    assert scanner.rank() == 0
    assert scanner.capabilities() == {
        "typed_signatures",
        "annotation_args",
        "type_annotations",
        "value_ids",
    }


def test_a_module_is_a_type_and_its_top_level_function_is_its_method(tmp_path: Path):
    report, tree = _scan(
        tmp_path,
        {
            "app/__init__.py": "",
            "app/api/__init__.py": "",
            "app/api/items.py": "def create_item(): pass\n",
        },
        coordinates="shop",
        version="1.0.0",
    )

    symbols = _symbols(tree)
    assert "app/api/items#" in symbols
    method = symbols[f"app/api/items#create_item({DIS})."][0]
    assert method.symbol == f"sextant-python pypi shop 1.0.0 app/api/items#create_item({DIS})."
    assert method.enclosing == "sextant-python pypi shop 1.0.0 app/api/items#"
    assert report.documents == 3


def test_a_package_init_is_the_module_of_its_package_path(tmp_path: Path):
    _, tree = _scan(tmp_path, {"app/api/__init__.py": "def ping(): pass\n"})

    assert f"app/api#ping({DIS})." in _symbols(tree)


def test_a_class_is_a_type_beside_its_module_and_a_nested_class_uses_dollar(tmp_path: Path):
    _, tree = _scan(
        tmp_path,
        {
            "app/api/items.py": (
                "class OrderService:\n"
                "    def create(self): pass\n"
                "    class Inner:\n"
                "        def run(self): pass\n"
            )
        },
    )

    symbols = _symbols(tree)
    assert symbols["app/api/items/OrderService#"][0].enclosing.endswith(" app/api/items#")
    assert f"app/api/items/OrderService#create({DIS})." in symbols
    assert f"app/api/items/OrderService$Inner#run({DIS})." in symbols


def test_module_body_is_clinit_and_its_names_are_static_fields_written_there(tmp_path: Path):
    _, tree = _scan(
        tmp_path,
        {"app/main.py": "from fastapi import FastAPI\n\napp = FastAPI()\n"},
    )

    writes = _facts(tree, FieldWriteFact)
    assert [(w.field, bare_descriptor(w.written_by or "")) for w in writes] == [
        ("app/main#app.", f"app/main#<clinit>({DIS})."),
    ]
    field = _symbols(tree)["app/main#app."][0]
    assert field.construct_kind == "field"
    assert field.modifiers["static"] is True
    # The value is the result of the call that built it, by value id.
    call = next(c for c in _facts(tree, CallSiteFact) if c.target.name == "FastAPI")
    assert writes[0].value == CallArgument(kind="unresolved", source=call.result)
    assert call.target.owner == "fastapi#"


def test_init_is_init_method(tmp_path: Path):
    _, tree = _scan(
        tmp_path,
        {"app/svc.py": "class OrderService:\n    def __init__(self, repo: int): pass\n"},
    )

    init = _symbols(tree)[f"app/svc/OrderService#<init>({DIS})."][0]
    assert init.construct_kind == "constructor"
    assert init.signature is not None
    # `self` is the receiver, not a parameter (D00 §5 numbering).
    assert [p.name for p in init.signature.parameters] == ["repo"]


def test_property_getter_and_setter_are_two_members(tmp_path: Path):
    _, tree = _scan(
        tmp_path,
        {
            "app/m.py": (
                "class C:\n"
                "    @property\n"
                "    def x(self) -> int: return 1\n"
                "    @x.setter\n"
                "    def x(self, value: int) -> None: pass\n"
            )
        },
    )

    symbols = _symbols(tree)
    assert len(symbols[f"app/m/C#x({DIS})."]) == 1
    assert len(symbols[f"app/m/C#x=({DIS})."]) == 1


def test_overload_stubs_are_types_not_bodies(tmp_path: Path):
    _, tree = _scan(
        tmp_path,
        {
            "app/m.py": (
                "from typing import overload\n"
                "@overload\n"
                "def f(x: int) -> int: ...\n"
                "@overload\n"
                "def f(x: str) -> str: ...\n"
                "def f(x): return x\n"
            )
        },
    )

    facts = _symbols(tree)[f"app/m#f({DIS})."]
    stubs = [f for f in facts if f.modifiers.get("abstract")]
    bodies = [f for f in facts if not f.modifiers.get("abstract")]
    assert len(stubs) == 2
    assert [s.signature.returns.symbol for s in stubs if s.signature and s.signature.returns] == [
        "builtins/int#",
        "builtins/str#",
    ]
    assert [(b.line_start, b.line_end) for b in bodies] == [(6, 6)]


def test_conditional_double_definition_is_two_bodies(tmp_path: Path):
    _, tree = _scan(
        tmp_path,
        {
            "app/m.py": (
                "import sys\n"
                "if sys.platform == 'win32':\n"
                "    def f(): return 1\n"
                "else:\n"
                "    def f(): return 2\n"
            )
        },
    )

    facts = _symbols(tree)[f"app/m#f({DIS})."]
    assert [(f.line_start, f.modifiers.get("abstract")) for f in facts] == [(3, False), (5, False)]


def test_written_type_has_evidence_declared(tmp_path: Path):
    """A type the code writes is recorded as written, bound through the file's own
    imports, and nothing is inferred. The document says the facts were read from
    source (`class_major` 0, D00 §2), which is what makes the type `declared` (D00 §5d's
    rule: a source origin is `declared`)."""
    _, tree = _scan(
        tmp_path,
        {
            "app/m.py": (
                "from app.models import Order\ndef f(order: Order) -> 'Order': return order\n"
            ),
            "app/models.py": "class Order: pass\n",
        },
    )

    method = _symbols(tree)[f"app/m#f({DIS})."][0]
    assert method.signature is not None
    assert method.signature.parameters[0].type.symbol == "app/models/Order#"
    assert method.signature.returns is not None
    assert method.signature.returns.symbol == "app/models/Order#"
    documents: list[Document] = [document for _, document, _ in tree]
    assert {(d.language, d.class_major) for d in documents} == {("python", 0)}


def test_decorator_is_written_as_two_calls(tmp_path: Path):
    _, tree = _scan(
        tmp_path,
        {
            "app/items.py": (
                "from fastapi import APIRouter\n"
                "router = APIRouter()\n"
                "@router.get('/x')\n"
                "def f(): pass\n"
            )
        },
    )

    calls = [c for c in _facts(tree, CallSiteFact) if c.target.name != "APIRouter"]
    get, apply = calls
    assert get.target.name == "get"
    assert get.invoke_kind == "virtual"
    assert get.receiver_field == "app/items#router."
    assert get.arguments == [CallArgument(kind="string", value="/x")]
    assert apply.receiver == get.result
    assert apply.arguments == [
        CallArgument(kind="lambda", symbol=f"app/items#f({DIS}).", captures=0)
    ]
    assert get.ordinal < apply.ordinal
    assert {bare_descriptor(c.caller) for c in calls} == {f"app/items#<clinit>({DIS})."}
    assert _facts(tree, AnnotationFact) == []


def test_try_import_fallback_binds_a_closed_list(tmp_path: Path):
    """Review Focus 2: two bindings, a closed list, never the first one silently."""
    _, tree = _scan(
        tmp_path,
        {
            "app/codec.py": (
                "try:\n"
                "    import ujson as json\n"
                "except ImportError:\n"
                "    import json\n"
                "codec = json\n"
            )
        },
    )

    (write,) = [w for w in _facts(tree, FieldWriteFact) if w.field == "app/codec#codec."]
    assert write.value == CallArgument(
        kind="merge",
        candidates=[
            CallArgument(kind="class", symbol="ujson#"),
            CallArgument(kind="class", symbol="json#"),
        ],
    )


def test_unparsable_file_is_uncovered_and_the_rest_is_scanned(tmp_path: Path):
    """Review Focus 5: a Python 2 file is reported with its reason; the rest is read."""
    report, tree = _scan(
        tmp_path,
        {"app/old.py": "print 'hello'\n", "app/new.py": "def f(): pass\n"},
    )

    assert len(report.uncovered) == 1
    assert report.uncovered[0].startswith("app/old.py: ")
    assert f"app/new#f({DIS})." in _symbols(tree)
    assert [document.relative_path for _, document, _ in tree] == ["app/new.py"]


def test_pep_695_type_parameters_are_type_variables(tmp_path: Path):
    _, tree = _scan(
        tmp_path,
        {
            "app/m.py": (
                "def ident[S](x: S) -> S: return x\nclass Box[T]:\n    def get(self) -> T: ...\n"
            )
        },
    )

    symbols = _symbols(tree)
    ident = symbols[f"app/m#ident({DIS})."][0]
    assert ident.signature is not None
    assert ident.signature.parameters[0].type == TypeRef(symbol="S")
    assert ident.signature.returns == TypeRef(symbol="S")
    assert ident.type_parameters == [TypeParameter(name="S")]
    get = symbols[f"app/m/Box#get({DIS})."][0]
    assert get.signature is not None and get.signature.returns == TypeRef(symbol="T")
    assert symbols["app/m/Box#"][0].type_parameters == [TypeParameter(name="T")]


def test_a_written_annotation_the_file_cannot_name_is_not_any(tmp_path: Path):
    """An annotation the file writes and does not bind keeps its written text; it is not
    the `typing/Any#` an unannotated parameter has, and it names no type."""
    _, tree = _scan(tmp_path, {"app/m.py": "def f(x: Mystery, y) -> Mystery: pass\n"})

    method = _symbols(tree)[f"app/m#f({DIS})."][0]
    assert method.signature is not None
    written, unannotated = method.signature.parameters
    assert written.type.symbol == "Mystery"
    assert not names_a_type(written.type.symbol)
    assert unannotated.type.symbol == "typing/Any#"
    assert method.signature.returns is not None
    assert method.signature.returns.symbol == "Mystery"


def test_an_ignored_file_is_not_read(tmp_path: Path):
    """`.sextantignore` and its built-in layer govern the scan as every other walk."""
    (tmp_path / ".sextantignore").write_text("src/app/legacy/\n", encoding="utf-8")
    _, tree = _scan(
        tmp_path,
        {
            "app/secrets/x.py": "TOKEN = 'abc'\n",
            "app/legacy/old.py": "def f(): pass\n",
            "app/new.py": "def f(): pass\n",
        },
        ignore=IgnoreRules.load(tmp_path),
    )

    assert [document.relative_path for _, document, _ in tree] == ["app/new.py"]


def test_a_git_ignored_generated_file_in_the_module_is_scanned(tmp_path: Path):
    _write(tmp_path / ".gitignore", "*_pb2.py\n")
    _, tree = _scan(
        tmp_path,
        {"app/orders_pb2.py": "class Order: pass\n"},
        ignore=IgnoreRules.load(tmp_path),
    )

    assert "app/orders_pb2/Order#" in _symbols(tree)


def test_a_file_that_cannot_be_opened_is_uncovered_and_the_rest_is_scanned(tmp_path: Path):
    (tmp_path / "src" / "app").mkdir(parents=True)
    (tmp_path / "src" / "app" / "broken.py").symlink_to(tmp_path / "missing.py")
    report, tree = _scan(tmp_path, {"app/new.py": "def f(): pass\n"})

    assert len(report.uncovered) == 1
    assert report.uncovered[0].startswith("app/broken.py: ")
    assert [document.relative_path for _, document, _ in tree] == ["app/new.py"]


def _class_and_document(tree, descriptor: str):
    for _, document, facts in tree:
        for fact in facts:
            if isinstance(fact, SymbolFact) and bare_descriptor(fact.symbol) == descriptor:
                return fact, document
    raise AssertionError(descriptor)


def test_a_base_the_file_cannot_name_ends_the_parents_and_the_document_is_partial(
    tmp_path: Path,
):
    """A base bound to a call result is not a class name: it and every base after it are
    not written, and no later base moves into its place."""
    _, tree = _scan(
        tmp_path,
        {
            "app/models.py": (
                "from sqlalchemy.orm import declarative_base\n"
                "from app.mixins import TimestampMixin\n"
                "Base = declarative_base()\n"
                "class User(Base, TimestampMixin): pass\n"
            ),
            "app/mixins.py": "class TimestampMixin: pass\n",
        },
    )

    user, document = _class_and_document(tree, "app/models/User#")
    assert user.superclass is None
    assert user.interfaces == []
    assert document.partial is True
    assert document.partial_reason == (
        "User: base 1 'Base' is not a class name this file can read; "
        "parents from here on are not read"
    )


def test_named_bases_keep_their_written_order(tmp_path: Path):
    _, tree = _scan(tmp_path, {"app/m.py": "class A: pass\nclass B: pass\nclass C(A, B): pass\n"})

    c, document = _class_and_document(tree, "app/m/C#")
    assert c.superclass is not None and c.superclass.endswith(" app/m/A#")
    assert [bare_descriptor(i) for i in c.interfaces] == ["app/m/B#"]
    assert document.partial is False


def test_bases_after_an_unnamed_one_are_not_written(tmp_path: Path):
    _, tree = _scan(
        tmp_path,
        {"app/m.py": "class A: pass\nclass B: pass\ndef f(): pass\nclass C(A, f(), B): pass\n"},
    )

    c, document = _class_and_document(tree, "app/m/C#")
    assert c.superclass is not None and c.superclass.endswith(" app/m/A#")
    assert c.interfaces == []
    assert document.partial is True
    assert document.partial_reason == (
        "C: base 2 'f()' is not a class name this file can read; parents from here on are not read"
    )


def test_a_base_that_is_a_value_says_its_parents_are_not_readable(tmp_path: Path):
    """The SQLAlchemy shape: the class carries `parents_unread`, so method lookup does not
    take it for a class with no parents."""
    _, tree = _scan(
        tmp_path,
        {
            "app/models.py": (
                "from sqlalchemy.orm import declarative_base\n"
                "from app.mixins import TimestampMixin\n"
                "Base = declarative_base()\n"
                "class User(Base, TimestampMixin): pass\n"
            ),
            "app/mixins.py": "class TimestampMixin: pass\n",
        },
    )

    user, _ = _class_and_document(tree, "app/models/User#")
    assert user.parents_unread == ParentsUnread(
        reason="not_readable",
        detail="base 1 'Base' is a value, not a class name; parents from here on are not read",
    )


def test_a_base_from_an_import_the_file_cannot_read_says_external(tmp_path: Path):
    _, tree = _scan(
        tmp_path,
        {"app/m.py": "from vendor import *\nclass A: pass\nclass C(A, Mystery): pass\n"},
    )

    c, _ = _class_and_document(tree, "app/m/C#")
    assert c.superclass is not None and c.superclass.endswith(" app/m/A#")
    assert c.parents_unread == ParentsUnread(
        reason="external",
        detail="base 2 'Mystery' is a name this file does not bind; "
        "parents from here on are not read",
    )


def test_a_class_with_every_base_named_has_no_parents_unread(tmp_path: Path):
    _, tree = _scan(tmp_path, {"app/m.py": "class A: pass\nclass B: pass\nclass C(A, B): pass\n"})

    c, _ = _class_and_document(tree, "app/m/C#")
    assert c.parents_unread is None


def test_the_two_reason_words_are_words_of_the_general_list():
    from sextant.application.resolve import values
    from sextant.ingress.extract.python import structure

    assert {structure._NOT_READABLE, structure._EXTERNAL} <= set(values._REASONS)


# `except A, B:` without brackets is Python 3.14 syntax (PEP 758). The scanner reads with the
# interpreter that runs Sextant, so the same file is read on 3.14 and uncovered below it.
_BARE_EXCEPT = "def f():\n    try:\n        pass\n    except KeyError, ValueError:\n        pass\n"


@pytest.mark.skipif(sys.version_info < (3, 14), reason="`except A, B:` needs Python 3.14")
def test_python_314_syntax_is_read_on_314(tmp_path: Path):
    report, tree = _scan(tmp_path, {"app/new.py": _BARE_EXCEPT})

    assert report.uncovered == ()
    assert _class_and_document(tree, "app/new#")[1].partial is False


@pytest.mark.skipif(sys.version_info >= (3, 14), reason="Python 3.14 reads this file")
def test_python_314_syntax_below_314_is_uncovered_and_the_reason_names_the_version(
    tmp_path: Path,
):
    report, _ = _scan(tmp_path, {"app/new.py": _BARE_EXCEPT, "app/ok.py": "x = 1\n"})

    running = f"read with Python {sys.version_info.major}.{sys.version_info.minor}"
    assert len(report.uncovered) == 1
    assert report.uncovered[0].startswith("app/new.py: ")
    assert running in report.uncovered[0]


def test_a_call_as_a_base_is_named_a_call_result(tmp_path: Path):
    _, tree = _scan(tmp_path, {"app/m.py": "def f(): pass\nclass C(f()): pass\n"})

    c, _ = _class_and_document(tree, "app/m/C#")
    assert c.parents_unread == ParentsUnread(
        reason="not_readable",
        detail="base 1 'f()' is a call result, not a class name; parents from here on are not read",
    )
