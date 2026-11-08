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
