"""`PythonScanner`: the two facts a shape is built from (plan 2 task 3).

An annotated class-body name not written `ClassVar` declares an instance variable (PEP 526),
whatever its value; its value is still the class body's `field_write`. A type reference
carries the wire type the language itself fixes (D00 §5b); what a serializer decides is left
to the catalog's `known_types`. Every tree is built in `tmp_path`; nothing is imported or
run."""

from pathlib import Path

from test_structure import _facts, _scan, _symbols

from sextant.domain.facts import FieldWriteFact, TypeRef


def _field(tree, descriptor: str):
    return _symbols(tree)[descriptor][0]


def test_an_annotated_class_name_with_a_default_is_an_instance_field(tmp_path: Path):
    """`name: str = "x"` and `items: list[int] = Field(default_factory=list)` declare
    instance variables, as `id: int` does; the class body writes their value."""
    _, tree = _scan(
        tmp_path,
        {
            "app/m.py": "from pydantic import BaseModel, Field\n"
            "class Order(BaseModel):\n"
            "    id: int\n"
            "    name: str = 'x'\n"
            "    items: list[int] = Field(default_factory=list)\n"
        },
    )
    for name in ("id", "name", "items"):
        assert _field(tree, f"app/m/Order#{name}.").modifiers["static"] is False, name
    written = {w.field for w in _facts(tree, FieldWriteFact)}
    assert {"app/m/Order#name.", "app/m/Order#items."} <= written
    assert "app/m/Order#id." not in written


def test_classvar_and_unannotated_names_stay_static(tmp_path: Path):
    """`ClassVar[...]` (bare, dotted, inside `Annotated`, in a string, or with no value) and a
    name assigned without an annotation belong to the class."""
    _, tree = _scan(
        tmp_path,
        {
            "app/m.py": "import typing\n"
            "from typing import Annotated, ClassVar\n"
            "class Order:\n"
            "    a: ClassVar[int] = 1\n"
            "    b: typing.ClassVar[str] = 'b'\n"
            "    c: ClassVar = 3\n"
            "    d: Annotated[ClassVar[int], 'meta'] = 4\n"
            "    e: 'ClassVar[int]' = 5\n"
            "    f = 6\n"
            "    g: ClassVar[int]\n"
        },
    )
    for name in "abcdefg":
        assert _field(tree, f"app/m/Order#{name}.").modifiers["static"] is True, name


def test_builtin_types_carry_their_wire_type(tmp_path: Path):
    _, tree = _scan(
        tmp_path,
        {
            "app/m.py": "import datetime, uuid, decimal\n"
            "from collections.abc import Mapping, Sequence\n"
            "class Other: pass\n"
            "class Order:\n"
            "    s: str\n"
            "    i: int\n"
            "    f: float\n"
            "    b: bool\n"
            "    l: list\n"
            "    st: set\n"
            "    fs: frozenset\n"
            "    t: tuple\n"
            "    sq: Sequence\n"
            "    d: dict\n"
            "    mp: Mapping\n"
            "    o: Other\n"
            "    by: bytes\n"
            "    dt: datetime.datetime\n"
            "    u: uuid.UUID\n"
            "    dc: decimal.Decimal\n"
        },
    )
    expected = {
        "s": "string",
        "i": "integer",
        "f": "number",
        "b": "boolean",
        "l": "array",
        "st": "array",
        "fs": "array",
        "t": "array",
        "sq": "array",
        "d": "map",
        "mp": "map",
        "o": "object",
        # The serializer's (N12 `known_types`), not the language's.
        "by": None,
        "dt": None,
        "u": None,
        "dc": None,
    }
    for name, wire in expected.items():
        returns = _field(tree, f"app/m/Order#{name}.").signature.returns
        assert (returns.wire_type, returns.wire_format) == (wire, None), name


def test_optional_list_of_str_is_a_nullable_array_of_string(tmp_path: Path):
    """The projection reaches every level of the reference, and a method's parameters and
    return as well as a field's type."""
    _, tree = _scan(
        tmp_path,
        {
            "app/m.py": "from typing import Optional\n"
            "class Order:\n"
            "    tags: Optional[list[str]] = None\n"
            "    def f(self, n: int | None) -> dict[str, bool]: ...\n"
        },
    )
    tags = _field(tree, "app/m/Order#tags.")
    assert tags.modifiers["static"] is False
    assert tags.signature.returns == TypeRef(
        symbol="builtins/list#",
        arguments=[
            TypeRef(
                symbol="builtins/str#",
                wire_type="string",
                nullable=False,
                nullable_resolution="resolved",
            )
        ],
        wire_type="array",
        nullable=True,
        nullable_resolution="resolved",
    )
    method = next(s for d, (s, *_) in _symbols(tree).items() if d.startswith("app/m/Order#f("))
    assert method.signature.parameters[0].type.wire_type == "integer"
    assert method.signature.parameters[0].type.nullable is True
    returns = method.signature.returns
    assert returns.wire_type == "map"
    assert [a.wire_type for a in returns.arguments] == ["string", "boolean"]


def test_a_classvar_imported_under_another_name_stays_static(tmp_path: Path):
    """`ClassVar` is matched by the symbol it binds, never its text."""
    _, tree = _scan(
        tmp_path,
        {"app/m.py": "from typing import ClassVar as CV\nclass Order:\n    x: CV[int] = 1\n"},
    )
    assert _field(tree, "app/m/Order#x.").modifiers["static"] is True


def test_the_typing_spelling_of_a_container_carries_its_wire_type(tmp_path: Path):
    """`typing.Iterable[str]` is an array of string and `Counter[str]` a map: the typing
    forms real code writes, as well as `collections.abc`'s and `collections`'."""
    _, tree = _scan(
        tmp_path,
        {
            "app/m.py": "import typing\n"
            "from collections import Counter, OrderedDict, defaultdict, deque\n"
            "from collections.abc import MutableMapping\n"
            "class Order:\n"
            "    names: typing.Iterable[str]\n"
            "    counts: Counter[str]\n"
            "    seen: typing.MutableSet[int]\n"
            "    queue: deque[int]\n"
            "    ordered: OrderedDict[str, int]\n"
            "    grouped: defaultdict[str, list[int]]\n"
            "    table: MutableMapping[str, int]\n"
            "    items: typing.Collection[int]\n"
        },
    )
    names = _field(tree, "app/m/Order#names.").signature.returns
    assert names.wire_type == "array"
    assert [a.wire_type for a in names.arguments] == ["string"]
    expected = {
        "counts": "map",
        "seen": "array",
        "queue": "array",
        "ordered": "map",
        "grouped": "map",
        "table": "map",
        "items": "array",
    }
    for name, wire in expected.items():
        assert _field(tree, f"app/m/Order#{name}.").signature.returns.wire_type == wire, name


def test_a_type_parameter_is_an_object_so_a_generic_models_field_stays_open(tmp_path: Path):
    """`class Page(BaseModel, Generic[T])`'s `items: list[T]` and `first: T`: `T` is a
    type to come, an object as the JVM's `T` is; a PEP 695 parameter and `Self` too. Text
    the file does not name stays unset."""
    _, tree = _scan(
        tmp_path,
        {
            "app/m.py": "from typing import Generic, Self, TypeVar\n"
            "from pydantic import BaseModel\n"
            "T = TypeVar('T')\n"
            "class Page(BaseModel, Generic[T]):\n"
            "    first: T\n"
            "    items: list[T]\n"
            "    other: Mystery\n"
            "    def copy(self) -> Self: ...\n"
            "class Box[S]:\n"
            "    held: S\n"
            "    def get[U](self, u: U) -> S: ...\n"
        },
    )
    assert _field(tree, "app/m/Page#first.").signature.returns.wire_type == "object"
    items = _field(tree, "app/m/Page#items.").signature.returns
    assert (items.wire_type, [a.wire_type for a in items.arguments]) == ("array", ["object"])
    assert _field(tree, "app/m/Page#other.").signature.returns.wire_type is None
    assert _field(tree, "app/m/Box#held.").signature.returns.wire_type == "object"
    symbols = _symbols(tree)
    copy = next(s for d, (s, *_) in symbols.items() if d.startswith("app/m/Page#copy("))
    assert copy.signature.returns.wire_type == "object"
    get = next(s for d, (s, *_) in symbols.items() if d.startswith("app/m/Box#get("))
    assert get.signature.parameters[0].type.wire_type == "object"
    assert get.signature.returns.wire_type == "object"
