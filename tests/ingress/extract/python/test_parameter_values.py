"""`PythonScanner`: what a parameter's default and its annotation evaluate to (plan
2026-11-08-python-fastapi-inbound N1, N2; OI-328; D00 §5a).

A `def` evaluates its defaults, then its annotations, in the body that runs it: the owner's
`<clinit>` for a module function or a method, the enclosing function for a nested `def`. The
scanner already wrote those calls there; each parameter now names them. `default` is the
default's value and `annotation_value` the annotation's, written only where it is not a plain
type: an `Annotated[...]`, which is the static call `typing/Annotated#__class_getitem__`, or a
name bound to a module-level type alias. Every tree is built in `tmp_path`; nothing is
imported or run."""

from pathlib import Path

from sextant.application.ports.scanner import ScanRequest
from sextant.domain.factfile import read_fact_tree
from sextant.domain.facts import CallArgument, CallSiteFact, Parameter, SymbolFact
from sextant.domain.symbols import bare_descriptor
from sextant.ingress.extract.python.scanner import PythonScanner

_ANNOTATED = "typing/Annotated#"
_CLASS_GETITEM = "__class_getitem__"


def _scan(tmp_path: Path, files: dict[str, str]):
    root = tmp_path / "src"
    for name, text in files.items():
        path = root / "app" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    out = tmp_path / "facts"
    PythonScanner().scan(
        ScanRequest(
            module_id="shop", coordinates="shop", version="1.0.0", classes_dir=root, out_dir=out
        )
    )
    return read_fact_tree(out)


def _facts(tree):
    return [fact for _, _, facts in tree for fact in facts]


def _method(symbol: str) -> str:
    """A method symbol without its signature hash: `app/run#f`."""
    return bare_descriptor(symbol).partition("(")[0]


def _parameter(tree, method: str, name: str) -> Parameter:
    for fact in _facts(tree):
        if isinstance(fact, SymbolFact) and _method(fact.symbol) == method:
            assert fact.signature is not None
            for parameter in fact.signature.parameters:
                if parameter.name == name:
                    return parameter
    raise AssertionError(f"no parameter {name} on {method}")


def _sites(tree, caller: str) -> list[CallSiteFact]:
    return [
        fact
        for fact in _facts(tree)
        if isinstance(fact, CallSiteFact) and _method(fact.caller) == caller
    ]


def _site(tree, caller: str, owner: str | None, name: str) -> CallSiteFact:
    found = [
        site
        for site in _sites(tree, caller)
        if site.target.owner == owner and site.target.name == name
    ]
    assert len(found) == 1, found
    return found[0]


_DEPS = (
    "from typing import Annotated\n"
    "from fastapi import Depends\n"
    "from app.db import Session\n"
    "def get_db():\n"
    "    return Session()\n"
    "DbSession = Annotated[Session, Depends(get_db)]\n"
)
_DB = "class Session:\n    pass\n"


def test_a_literal_default_is_the_parameter_default(tmp_path: Path):
    tree = _scan(tmp_path, {"run.py": "def f(limit: int = 10, name=None):\n    pass\n"})

    limit = _parameter(tree, "app/run#f", "limit")
    assert limit.default == CallArgument(kind="int", value=10)
    assert limit.declares_default
    assert limit.type.symbol == "builtins/int#"
    named = _parameter(tree, "app/run#f", "name")
    assert named.default == CallArgument(kind="null")
    assert named.declares_default


def test_a_parameter_without_a_default_declares_none(tmp_path: Path):
    """The near-miss: no default written, no key; a keyword-only parameter after one with a
    default is still told apart by its own entry."""
    tree = _scan(tmp_path, {"run.py": "def f(a, b=1, *, c, d=2):\n    pass\n"})

    for name in ("a", "c"):
        parameter = _parameter(tree, "app/run#f", name)
        assert parameter.default is None
        assert not parameter.declares_default
    assert _parameter(tree, "app/run#f", "b").default == CallArgument(kind="int", value=1)
    assert _parameter(tree, "app/run#f", "d").default == CallArgument(kind="int", value=2)


def test_a_call_default_names_its_call_in_the_body_that_runs_the_def(tmp_path: Path):
    """`db = Depends(get_db)`: the default is the result of the `Depends` call the module body
    makes when it runs the `def`."""
    tree = _scan(
        tmp_path,
        {
            "run.py": "from fastapi import Depends\n"
            "def get_db():\n    return 1\n"
            "def f(db=Depends(get_db)):\n    pass\n"
        },
    )

    depends = _site(tree, "app/run#<clinit>", "fastapi#", "Depends")
    db = _parameter(tree, "app/run#f", "db")
    assert db.default == CallArgument(kind="unresolved", source=depends.result)
    assert db.declares_default


def test_a_method_default_is_read_in_the_class_body(tmp_path: Path):
    """A method's default runs in the class body (`C`'s `<clinit>`), a nested `def`'s in the
    function that holds it."""
    tree = _scan(
        tmp_path,
        {
            "run.py": "def make():\n    return 1\n"
            "class C:\n"
            "    def m(self, n=make()):\n"
            "        def inner(k=make()):\n            pass\n"
        },
    )

    in_class = _site(tree, "app/run/C#<clinit>", "app/run#", "make")
    assert _parameter(tree, "app/run/C#m", "n").default == CallArgument(
        kind="unresolved", source=in_class.result
    )
    in_method = _site(tree, "app/run/C#m", "app/run#", "make")
    assert _parameter(tree, "app/run/C#m$inner", "k").default == CallArgument(
        kind="unresolved", source=in_method.result
    )


def test_inline_annotated_writes_its_form_call_and_points_at_it(tmp_path: Path):
    """`q: Annotated[str, Query(max_length=3)]`: the form is the static call
    `typing/Annotated#__class_getitem__`, one argument per index element in written order;
    the parameter's type is `str` and its annotation value is that call's result."""
    tree = _scan(
        tmp_path,
        {
            "run.py": "from typing import Annotated\n"
            "from fastapi import Query\n"
            "def f(q: Annotated[str, Query(max_length=3)] = 'x'):\n    pass\n"
        },
    )

    query = _site(tree, "app/run#<clinit>", "fastapi#", "Query")
    form = _site(tree, "app/run#<clinit>", _ANNOTATED, _CLASS_GETITEM)
    assert form.invoke_kind == "static"
    assert form.arguments == [
        CallArgument(kind="class", symbol="builtins/str#"),
        CallArgument(kind="unresolved", source=query.result),
    ]
    q = _parameter(tree, "app/run#f", "q")
    assert q.type.symbol == "builtins/str#"
    assert q.annotation_value == CallArgument(kind="unresolved", source=form.result)
    assert q.default == CallArgument(kind="string", value="x")


def test_an_alias_in_another_file_is_its_type_and_its_field(tmp_path: Path):
    """`d: DbSession`, `DbSession = Annotated[Session, Depends(get_db)]` in `deps.py`: the type
    is `Session`, read through `deps.py`'s header, and the annotation value is the alias's
    field, whose write in `deps.py` is the form call holding `Depends(get_db)`."""
    tree = _scan(
        tmp_path,
        {
            "db.py": _DB,
            "deps.py": _DEPS,
            "run.py": "from app.deps import DbSession\ndef f(d: DbSession):\n    pass\n",
        },
    )

    d = _parameter(tree, "app/run#f", "d")
    assert d.type.symbol == "app/db/Session#"
    assert d.annotation_value == CallArgument(kind="field", symbol="app/deps#DbSession.")
    form = _site(tree, "app/deps#<clinit>", _ANNOTATED, _CLASS_GETITEM)
    depends = _site(tree, "app/deps#<clinit>", "fastapi#", "Depends")
    assert form.arguments[1] == CallArgument(kind="unresolved", source=depends.result)


def test_an_alias_of_an_alias_in_a_third_file_is_the_type_it_ends_at(tmp_path: Path):
    """`Db = Annotated[DbSession, ...]` where `DbSession` is another file's alias: the type is
    `Session`, never the path `app/deps/DbSession#`, which names no class."""
    tree = _scan(
        tmp_path,
        {
            "db.py": _DB,
            "deps.py": _DEPS,
            "more.py": "from typing import Annotated\n"
            "from app.deps import DbSession\n"
            "Db = Annotated[DbSession, 'tag']\n",
            "run.py": "from app.more import Db\ndef f(d: Db):\n    pass\n",
        },
    )

    d = _parameter(tree, "app/run#f", "d")
    assert d.type.symbol == "app/db/Session#"
    assert d.annotation_value == CallArgument(kind="field", symbol="app/more#Db.")


def test_an_alias_in_the_same_file_in_each_spelling_is_its_type_and_its_field(tmp_path: Path):
    """`X = Annotated[T, ...]`, `X: TypeAlias = ...` and `type X = ...` are type aliases."""
    tree = _scan(
        tmp_path,
        {
            "db.py": _DB,
            "run.py": "from typing import Annotated, TypeAlias\n"
            "from app.db import Session\n"
            "A = Annotated[Session, 'a']\n"
            "B: TypeAlias = Annotated[Session, 'b']\n"
            "type C = Annotated[Session, 'c']\n"
            "def f(a: A, b: B, c: C):\n    pass\n",
        },
    )

    for name, alias in (("a", "A"), ("b", "B"), ("c", "C")):
        parameter = _parameter(tree, "app/run#f", name)
        assert parameter.type.symbol == "app/db/Session#", name
        assert parameter.annotation_value == CallArgument(kind="field", symbol=f"app/run#{alias}.")


def test_ellipsis_is_the_builtin_constant(tmp_path: Path):
    """`Query(...)` (required): `...` is the field `builtins#Ellipsis.`, never `unresolved`."""
    tree = _scan(
        tmp_path,
        {"run.py": "from fastapi import Query\ndef f(r: str = Query(...)):\n    pass\n"},
    )

    query = _site(tree, "app/run#<clinit>", "fastapi#", "Query")
    assert query.arguments == [CallArgument(kind="field", symbol="builtins#Ellipsis.")]


def test_a_plain_type_annotation_writes_no_annotation_value(tmp_path: Path):
    """The near-miss for each half of the rule: a plain type, a subscripted type, a name bound
    to a class (`Plain = Session` binds as the class), a module-level value that is no alias,
    and an `Annotated` that is not typing's. No form call is written for an annotation."""
    tree = _scan(
        tmp_path,
        {
            "db.py": _DB,
            "run.py": "from typing import Optional\n"
            "from mylib import Annotated\n"
            "from app.db import Session\n"
            "Plain = Session\n"
            "Value = make()\n"
            "def f(a: int, b: Optional[list[int]], c: Plain, d: Value, e: Annotated[int, 1]):\n"
            "    pass\n",
        },
    )

    for name in "abcde":
        assert _parameter(tree, "app/run#f", name).annotation_value is None, name
    names = [site.target.name for site in _sites(tree, "app/run#<clinit>")]
    assert _CLASS_GETITEM not in names


def test_a_subscript_of_a_type_form_evaluated_as_a_value_is_its_class_getitem_call(
    tmp_path: Path,
):
    """`response_model=list[Item]`: the static call `builtins/list#__class_getitem__(Item)`,
    whose result is the argument. A subscript of a value is still `__getitem__`."""
    tree = _scan(
        tmp_path,
        {
            "run.py": "class Item:\n    pass\n"
            "def f(rows):\n"
            "    route(response_model=list[Item])\n"
            "    return rows[0]\n"
        },
    )

    form = _site(tree, "app/run#f", "builtins/list#", _CLASS_GETITEM)
    assert form.invoke_kind == "static"
    assert form.arguments == [CallArgument(kind="class", symbol="app/run/Item#")]
    route = _site(tree, "app/run#f", None, "__call__")
    assert route.arguments == [
        CallArgument(kind="unresolved", source=form.result, keyword="response_model")
    ]
    assert [site.target.name for site in _sites(tree, "app/run#f")].count("__getitem__") == 1
