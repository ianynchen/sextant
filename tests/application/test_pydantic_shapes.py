"""The pydantic shape model: a model's fields, their names on the wire, and the types pydantic
writes as something else (plan 2026-11-08-python-fastapi-inbound Task 9; N12, N13; rulings R2,
R3, R24, R25).

Pydantic 2.14's output name is the first that applies of `serialization_alias`, `alias`, the
model's `alias_generator(name)`, and the name (`scripts/probes/pydantic_naming.md` §2); the
generator comes from the `model_config` of the written bases, last base winning, then the
class's own (§3, ruling R2); a field with no default is required, and a name starting with `_`
is no field (§4). A field whose accepted input names differ from its output name is `partial`
(N13 option B), as is one whose names the code does not let us read (R3).

Each test writes a small FastAPI program, scans it with the real Python scanner against the
FastAPI 0.162.0 and pydantic 2.14.3 that `fixtures/orders-fastapi` locks, runs the real
pipeline with the shipped catalogs (`test_fastapi_routes._resolved`) and reads `shape_fields`.
"""

import json
from pathlib import Path

import pytest
import test_fastapi_routes
from test_fastapi_routes import _resolved

from sextant.application.ports.catalogs import CatalogError
from sextant.ingress.catalogs.yaml_source import YamlCatalogSource
from sextant.resources import catalogs_dir

# The FastAPI environment the route tests read, shared rather than restated.
libraries = test_fastapi_routes.libraries

_HEAD = (
    "import datetime\n"
    "import uuid\n"
    "from decimal import Decimal\n"
    "from typing import Annotated, Generic, Optional, TypeVar\n"
    "from fastapi import APIRouter, Cookie, Header, Query\n"
    "from pydantic import UUID4, AliasChoices, BaseModel, ConfigDict, Field, PrivateAttr\n"
    "from pydantic.alias_generators import to_camel, to_pascal\n"
    "router = APIRouter()\n"
)


def _program(models: str, body: str = "Item") -> dict[str, str]:
    """`models` and one route taking `body` as its request body and returning it."""
    return {
        "main.py": _HEAD
        + models
        + f"@router.post('/x')\ndef handler(item: {body}) -> {body}:\n    return item\n"
    }


def _fields(workspace, shape: str = "Item") -> dict[str | None, tuple[object, ...]]:
    """Each field of `app/main/<shape>#` by wire name: (wire_type, wire_format, required,
    resolution)."""
    return {
        row["wire_name"]: (
            row["wire_type"],
            row["wire_format"],
            row["required"],
            row["resolution"],
        )
        for row in workspace.query("shape_fields")
        if row["shape_id"] == f"app/main/{shape}#"
    }


def _open(workspace, shape: str = "Item") -> bool:
    (row,) = [row for row in workspace.query("shapes") if row["shape_id"] == f"app/main/{shape}#"]
    return bool(row["open"])


def test_a_defaulted_field_is_on_the_wire_and_not_required(tmp_path: Path, libraries):
    """`required: no_default` (§4): a field is required when it writes no default. `Optional[X]`
    with no default is required; `= None`, a literal, `Field(3)`, `Field(default=...)` and
    `Field(default_factory=...)` write one; `Field(...)` and `Field()` do not."""
    workspace = _resolved(
        tmp_path,
        libraries,
        _program(
            "class Item(BaseModel):\n"
            "    needs: int\n"
            "    opt_no_default: Optional[int]\n"
            "    opt_none: Optional[int] = None\n"
            "    literal: int = 3\n"
            "    positional: int = Field(3)\n"
            "    keyword: int = Field(default=3)\n"
            "    factory: list[int] = Field(default_factory=list)\n"
            "    ellipsis: int = Field(...)\n"
            "    empty: int = Field()\n"
        ),
    )

    assert {name: row[2] for name, row in _fields(workspace).items()} == {
        "needs": True,
        "opt_no_default": True,
        "opt_none": False,
        "literal": False,
        "positional": False,
        "keyword": False,
        "factory": False,
        "ellipsis": True,
        "empty": True,
    }
    assert {row[3] for row in _fields(workspace).values()} == {"resolved"}


def test_field_alias_names_the_wire_field(tmp_path: Path, libraries):
    """`Field(alias="X")` names the field on the wire, in and out."""
    workspace = _resolved(
        tmp_path,
        libraries,
        _program("class Item(BaseModel):\n    x_field: int = Field(0, alias='X')\n"),
    )

    assert _fields(workspace) == {"X": ("integer", None, False, "resolved")}


def test_serialization_alias_wins_over_alias(tmp_path: Path, libraries):
    """`serialization_alias` is the output name ahead of `alias` (§2). The field is then read
    under `alias`, which differs from its output name, so it is `partial` (N13 B); alone,
    `serialization_alias` likewise leaves the field read under its own name."""
    workspace = _resolved(
        tmp_path,
        libraries,
        _program(
            "class Item(BaseModel):\n"
            "    both: int = Field(0, alias='Al', serialization_alias='Ser')\n"
            "    only: int = Field(0, serialization_alias='Out')\n"
        ),
    )

    assert _fields(workspace) == {
        "Ser": ("integer", None, False, "partial"),
        "Out": ("integer", None, False, "partial"),
    }


def test_inherited_to_camel_generator_names_unaliased_fields(tmp_path: Path, libraries):
    """Review Focus 4. The generator is the config merged over the written bases, the last base
    winning, then the class's own (`ConfigWrapper.for_model`, §3, ruling R2): a child with no
    config, or one that sets another key, keeps its parent's; `alias_generator=None` removes it;
    `Both(Left, Right)` takes `Right`'s, which the C3 order would not."""
    workspace = _resolved(
        tmp_path,
        libraries,
        _program(
            "class Parent(BaseModel):\n"
            "    model_config = ConfigDict(alias_generator=to_camel)\n"
            "class Child(Parent):\n"
            "    item_name: int = 0\n"
            "class Strip(Parent):\n"
            "    model_config = ConfigDict(str_strip_whitespace=True)\n"
            "    item_name: int = 0\n"
            "class Plain(Parent):\n"
            "    model_config = ConfigDict(alias_generator=None)\n"
            "    item_name: int = 0\n"
            "class Left(BaseModel):\n"
            "    model_config = ConfigDict(alias_generator=to_camel)\n"
            "class Right(BaseModel):\n"
            "    model_config = ConfigDict(alias_generator=to_pascal)\n"
            "class Both(Left, Right):\n"
            "    item_name: int = 0\n"
            "class Item(BaseModel):\n"
            "    child: Child\n"
            "    strip: Strip\n"
            "    plain: Plain\n"
            "    both: Both\n"
        ),
    )

    assert list(_fields(workspace, "Child")) == ["itemName"]
    assert list(_fields(workspace, "Strip")) == ["itemName"]
    assert list(_fields(workspace, "Plain")) == ["item_name"]
    assert list(_fields(workspace, "Both")) == ["ItemName"]
    assert {row[3] for row in _fields(workspace, "Both").values()} == {"resolved"}


def test_explicit_alias_wins_over_the_generator(tmp_path: Path, libraries):
    """An `alias` written on the field is its name under a generator (priority 2); a literal
    `alias_priority=1` lets the generator replace it (R3); one not written as a literal is not
    read, so the field is `partial`."""
    workspace = _resolved(
        tmp_path,
        libraries,
        _program(
            "LOW = 1\n"
            "def priority() -> int:\n"
            "    return 1\n"
            "class Item(BaseModel):\n"
            "    model_config = ConfigDict(alias_generator=to_camel)\n"
            "    explicit_one: int = Field(0, alias='Explicit')\n"
            "    low_one: int = Field(0, alias='Low', alias_priority=1)\n"
            "    unread_one: int = Field(0, alias='Unread', alias_priority=priority())\n"
        ),
    )

    assert {name: row[3] for name, row in _fields(workspace).items()} == {
        "Explicit": "resolved",
        "lowOne": "resolved",
        "Unread": "partial",
    }


def test_humps_camelize_is_read_as_the_probe_said(tmp_path: Path, libraries):
    """mealie's generator, `humps.main.camelize`, is the `camel` strategy: it agrees with
    `to_camel` on all 465 of mealie's field names (`pydantic_naming.md` §1). With
    `populate_by_name` a field is read under its name too, which is not its output name, so a
    renamed field is `partial` (N13 B) and an unrenamed one is not."""
    workspace = _resolved(
        tmp_path,
        libraries,
        _program(
            "from humps.main import camelize\n"
            "class Item(BaseModel):\n"
            "    model_config = ConfigDict(alias_generator=camelize, populate_by_name=True)\n"
            "    created_at: int = 0\n"
            "    name: str = ''\n"
        ),
    )

    assert _fields(workspace) == {
        "createdAt": ("integer", None, False, "partial"),
        "name": ("string", None, False, "resolved"),
    }


def test_an_unknown_generator_leaves_names_unresolved_and_the_shape_open(tmp_path: Path, libraries):
    """A generator no `functions` entry names is not guessed at (§2g): the fields it names have
    no wire name, `unresolved`, and the shape is open. A field with its own `alias` is named by
    it whatever the generator is."""
    workspace = _resolved(
        tmp_path,
        libraries,
        _program(
            "def shout(name: str) -> str:\n"
            "    return name.upper()\n"
            "class Item(BaseModel):\n"
            "    model_config = ConfigDict(alias_generator=shout)\n"
            "    my_field: int = 0\n"
            "    named: int = Field(0, alias='Named')\n"
        ),
    )

    assert _fields(workspace) == {
        None: ("integer", None, False, "unresolved"),
        "Named": ("integer", None, False, "resolved"),
    }
    assert _open(workspace) is True


def test_a_wrapper_of_field_with_unpacked_kwargs_is_not_readable(tmp_path: Path, libraries):
    """mealie's `UpdatedAtField` sets the aliases in a dict it hands `Field` as `**kwargs`: the
    names are not read, so the field is `partial`, named by what the rest of the rules give."""
    workspace = _resolved(
        tmp_path,
        libraries,
        _program(
            "def UpdatedAtField(*args, **kwargs):\n"
            "    kwargs['alias_priority'] = 2\n"
            "    kwargs['serialization_alias'] = 'updatedAt'\n"
            "    return Field(*args, **kwargs)\n"
            "class Item(BaseModel):\n"
            "    updated_at: int = UpdatedAtField(None)\n"
            "    other: int = Field(None)\n"
        ),
    )

    assert {name: row[3] for name, row in _fields(workspace).items()} == {
        "updated_at": "partial",
        "other": "resolved",
    }
    # Review M2, ruled 2026-11-09: the default `UpdatedAtField` hands `Field` sits in `*args`, so
    # whether one is written is not read: `required` is unknown (NULL), never a guess.
    assert _fields(workspace)["updated_at"][2] is None


def test_private_attributes_are_not_fields(tmp_path: Path, libraries):
    """`private_prefix: "_"` (§4): pydantic keeps a name starting with `_` as a private
    attribute, never a field."""
    workspace = _resolved(
        tmp_path,
        libraries,
        _program(
            "class Item(BaseModel):\n"
            "    name: str\n"
            "    _secret: int = 0\n"
            "    _cache: dict = PrivateAttr(default_factory=dict)\n"
        ),
    )

    assert list(_fields(workspace)) == ["name"]


def test_validation_alias_makes_the_field_partial(tmp_path: Path, libraries):
    """N13 B: `validation_alias` changes what a request may send, not the output name, so the
    field is published under its output name at `partial`, a string or `AliasChoices` alike."""
    workspace = _resolved(
        tmp_path,
        libraries,
        _program(
            "class Item(BaseModel):\n"
            "    single: int = Field(0, validation_alias='s')\n"
            "    choices: int = Field(0, validation_alias=AliasChoices('c1', 'c2'))\n"
        ),
    )

    assert _fields(workspace) == {
        "single": ("integer", None, False, "partial"),
        "choices": ("integer", None, False, "partial"),
    }


def test_decimal_is_a_string(tmp_path: Path, libraries):
    """`known_types` (§2g, pydantic 2 JSON mode, `scripts/probes/pydantic_known_types.md`):
    `Decimal` is a string, as are the date types, `UUID`, pydantic's `UUID4` and `bytes`, each
    with the format the probe read (ruling: formats follow the probe)."""
    workspace = _resolved(
        tmp_path,
        libraries,
        _program(
            "class Item(BaseModel):\n"
            "    price: Decimal\n"
            "    at: datetime.datetime\n"
            "    on: datetime.date\n"
            "    key: uuid.UUID\n"
            "    key4: UUID4\n"
            "    raw: bytes\n"
        ),
    )

    assert {name: row[:2] for name, row in _fields(workspace).items()} == {
        "price": ("string", None),
        "at": ("string", "date-time"),
        "on": ("string", "date"),
        "key": ("string", "uuid"),
        "key4": ("string", "uuid4"),
        "raw": ("string", "binary"),
    }


def _response(workspace, path: str) -> object:
    (row,) = [row for row in workspace.query("endpoints") if row["path"] == path]
    return None if row["response_shape"] is None else json.loads(row["response_shape"])


def test_a_generic_response_model_is_read_as_the_type_it_names(tmp_path: Path, libraries):
    """R24: a type form in a type slot (`response_model=ListResource[Order]`, `list[Order]`, the
    `<form>#__class_getitem__` call N2 writes) is the type it names, with its arguments; the
    generic model's field typed by its parameter is bound to the argument. A generic model
    imported from another file (polar's `ListResource`, a PEP 695 class) is subscripted as a
    class too, though the scanner writes that subscript `__getitem__`."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "pagination.py": "from pydantic import BaseModel\n"
            "class Page[T](BaseModel):\n"
            "    items: list[T]\n",
            "schemas.py": "from pydantic import BaseModel\nclass Line(BaseModel):\n    sku: str\n",
            "main.py": _HEAD + "from app.pagination import Page\n"
            "from app.schemas import Line\n"
            "T = TypeVar('T')\n"
            "class Order(BaseModel):\n"
            "    id: int\n"
            "class ListResource(BaseModel, Generic[T]):\n"
            "    items: list[T]\n"
            "@router.get('/orders', response_model=ListResource[Order])\n"
            "def orders():\n"
            "    return None\n"
            "@router.get('/plain', response_model=list[Order])\n"
            "def plain():\n"
            "    return None\n"
            "@router.get('/lines', response_model=Page[Line])\n"
            "def lines():\n"
            "    return None\n",
        },
    )

    paged = _response(workspace, "/orders")
    assert paged["wire_type"] == "object"
    assert paged["shape_id"] == "app/main/ListResource#<app/main/Order#>"
    (items,) = [
        row
        for row in workspace.query("shape_fields")
        if row["shape_id"] == "app/main/ListResource#<app/main/Order#>"
    ]
    assert items["wire_name"] == "items"
    assert json.loads(items["item"])["shape_id"] == "app/main/Order#"
    listed = _response(workspace, "/plain")
    assert listed["wire_type"] == "array"
    assert listed["item"]["shape_id"] == "app/main/Order#"
    assert _response(workspace, "/lines")["shape_id"] == "app/pagination/Page#<app/schemas/Line#>"
    (lines,) = [
        row
        for row in workspace.query("shape_fields")
        if row["shape_id"] == "app/pagination/Page#<app/schemas/Line#>"
    ]
    assert json.loads(lines["item"])["shape_id"] == "app/schemas/Line#"
    assert {row["resolution"] for row in workspace.query("endpoints")} == {"resolved"}


def _params(workspace) -> list[tuple[object, ...]]:
    """Each request parameter as (kind, name, requirement, resolution)."""
    return sorted(
        (row["kind"], row["name"], row["requirement"], row["resolution"])
        for row in workspace.query("endpoint_metadata")
        if row["direction"] == "inbound" and row["kind"] in ("query", "header", "cookie")
    )


def test_a_query_model_expands_to_one_param_per_field(tmp_path: Path, libraries):
    """R25 (FastAPI 0.162.0, `scripts/probes/fastapi_param_models.md`): a model marked `Query()`,
    `Header()` or `Cookie()` is one parameter per field, named by its input name (`validation_
    alias`, else `alias`, else the generator's, else the name, which `Header` hyphenates), and
    required where it writes no default."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "main.py": _HEAD + "class Filters(BaseModel):\n"
            "    page: int = 1\n"
            "    sort_by: str\n"
            "    org: str = Field('', alias='organization_id')\n"
            "    out: str = Field('', serialization_alias='Out')\n"
            "    _private: int = 0\n"
            "class Camel(BaseModel):\n"
            "    model_config = ConfigDict(alias_generator=to_camel)\n"
            "    created_at: int = 0\n"
            "class Trace(BaseModel):\n"
            "    x_trace_id: str = '-'\n"
            "@router.get('/q')\n"
            "def q(f: Annotated[Filters, Query()], c: Annotated[Camel, Query()]) -> str:\n"
            "    return ''\n"
            "@router.get('/h')\n"
            "def h(t: Annotated[Trace, Header()], k: Annotated[Trace, Cookie()]) -> str:\n"
            "    return ''\n"
        },
    )

    assert _params(workspace) == [
        ("cookie", "x_trace_id", "optional", "resolved"),
        ("header", "x-trace-id", "optional", "resolved"),
        ("query", "createdAt", "optional", "resolved"),
        ("query", "organization_id", "optional", "resolved"),
        ("query", "out", "optional", "resolved"),
        ("query", "page", "optional", "resolved"),
        ("query", "sort_by", "required", "resolved"),
    ]


@pytest.mark.parametrize(
    ("serialization", "says"),
    [
        ("{name_from: [{call: pydantic.fields.Field}]}", "name_from"),
        ("{input_name_from: [{call: Field, arg: {keyword: alias}}]}", "input_name_from"),
        (
            (
                "{name_generator: {config_field: model_config, config_call: a.B, arg: {keyword: g},"
                " functions: [{function: a.f, strategy: kebab, by: x.md}]}}"
            ),
            "strategy",
        ),
        ("{required: always}", "required"),
        ("{private_prefix: ''}", "private_prefix"),
        ("{defaults: [{call: a.f, default_arg: 0}]}", "defaults"),
        ("{naming: camel}", "serialization.naming"),
        ("{excluded_when: {keyword: exclude}}", "excluded_when"),
        ("{open_when: {arg: {keyword: extra}, values: []}}", "open_when"),
        ("{output_fields: [{decorator: computed_field}]}", "output_fields"),
        ("{output_open_when: [{method: __x__, also_input: yes_please}]}", "output_open_when"),
    ],
)
def test_a_malformed_shape_model_is_refused_by_file(tmp_path: Path, serialization: str, says: str):
    """`_check_shape_model` (D02 §1b, §2f): a key N12/N13 do not define, or one of theirs in
    another form, is refused naming the file, never read as no naming at all."""
    (tmp_path / "shape-models").mkdir()
    (tmp_path / "shape-models" / "tiny.yml").write_text(
        f"id: tiny\nserialization: {serialization}\n", encoding="utf-8"
    )

    with pytest.raises(CatalogError) as raised:
        YamlCatalogSource(tmp_path).load()

    assert says in str(raised.value)
    assert "tiny.yml" in str(raised.value)


def test_a_field_in_annotated_metadata_names_and_defaults_the_field(tmp_path: Path, libraries):
    """Review M1. pydantic reads a `Field(...)` in `Annotated` metadata as it reads one written
    as the value (`FieldInfo.from_annotated_attribute`): its alias, `default` and
    `default_factory`. Several merge in written order, the class-body value last, each call
    overriding what it writes (an `alias` writes both names). Probe, pydantic 2.14.3:
    `pydantic_naming.md` §5."""
    workspace = _resolved(
        tmp_path,
        libraries,
        _program(
            "class Item(BaseModel):\n"
            "    plain_name: Annotated[str, Field(alias='PlainAlias')]\n"
            "    with_default: Annotated[int, Field(default=3)]\n"
            "    with_factory: Annotated[list[int], Field(default_factory=list)]\n"
            "    a: Annotated[int, Field(alias='A1')] = Field(alias='A2')\n"
            "    b: Annotated[int, Field(alias='B1')] = Field(default=3)\n"
            "    c: Annotated[int, Field(alias='C1')] = 4\n"
            "    d: Annotated[int, Field(alias='D1'), Field(alias='D2')]\n"
            "    e: Annotated[int, Field(default=1)] = Field(alias='E')\n"
            "    g: Annotated[int, Field(serialization_alias='G1')] = Field(alias='G2')\n"
            "    v: Annotated[int, Field(validation_alias='V')] = 0\n"
        ),
    )

    assert {name: (row[2], row[3]) for name, row in _fields(workspace).items()} == {
        "PlainAlias": (True, "resolved"),
        "with_default": (False, "resolved"),
        "with_factory": (False, "resolved"),
        "A2": (True, "resolved"),
        "B1": (False, "resolved"),
        "C1": (False, "resolved"),
        "D2": (True, "resolved"),
        "E": (False, "resolved"),
        "G2": (True, "resolved"),
        "v": (False, "partial"),
    }


def test_a_default_made_by_a_call_not_read_is_not_a_default(tmp_path: Path, libraries):
    """Review M2, ruled 2026-11-09: a value made by a call no naming rule reads (sqlmodel's own
    `Field`, a library helper, `" ".join(...)`) may or may not write a default, so `required` is
    unknown (NULL) at `partial`. Any other value, a literal or a display such as `{}`, is a
    default; no value at all is required."""
    workspace = _resolved(
        tmp_path,
        libraries,
        _program(
            "from sqlmodel import Field as SqlField\n"
            "class Item(BaseModel):\n"
            "    email: str = SqlField(max_length=255)\n"
            "    plain: int = 3\n"
            "    headers: dict[str, str] = {}\n"
            "    scope: str = ' '.join(['a', 'b'])\n"
            "    bare: str\n"
        ),
    )

    assert {name: (row[2], row[3]) for name, row in _fields(workspace).items()} == {
        "email": (None, "partial"),
        "plain": (False, "resolved"),
        "headers": (False, "resolved"),
        "scope": (None, "partial"),
        "bare": (True, "resolved"),
    }


def test_a_typing_union_or_optional_form_is_no_class(tmp_path: Path, libraries):
    """Review M3: R24 reads a form as a type only where its owner is a class: a scanned one or
    a collection the shape model names. `Optional[X]` and `Union[...]`, alone, inside
    `list[...]` or behind an alias, stay unread, as before R24."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "main.py": _HEAD + "from typing import Union\n"
            "class Cat(BaseModel):\n"
            "    name: str\n"
            "class Dog(BaseModel):\n"
            "    name: str\n"
            "Pet = Union[Cat, Dog]\n"
            "@router.get('/optional', response_model=Optional[Cat])\n"
            "def optional():\n"
            "    return None\n"
            "@router.get('/union', response_model=Union[Cat, Dog])\n"
            "def union():\n"
            "    return None\n"
            "@router.get('/listed', response_model=list[Optional[Cat]])\n"
            "def listed():\n"
            "    return None\n"
            "@router.get('/alias', response_model=list[Pet])\n"
            "def alias():\n"
            "    return None\n"
        },
    )

    assert {
        row["path"]: (row["resolution"], row["response_shape"])
        for row in workspace.query("endpoints")
    } == {
        "/optional": ("unresolved", None),
        "/union": ("unresolved", None),
        "/listed": ("unresolved", None),
        "/alias": ("unresolved", None),
    }


def test_pydantic_string_types_are_strings(tmp_path: Path, libraries):
    """Review M5 (`pydantic_known_types.md`): pydantic's network and date types are strings
    with the format its schema states, and `SkipJsonSchema[X]` writes an `X`."""
    workspace = _resolved(
        tmp_path,
        libraries,
        _program(
            "from pydantic import AnyUrl, AwareDatetime, EmailStr, HttpUrl, IPvAnyAddress\n"
            "from pydantic.json_schema import SkipJsonSchema\n"
            "class Item(BaseModel):\n"
            "    email: EmailStr\n"
            "    site: HttpUrl\n"
            "    any_url: AnyUrl\n"
            "    address: IPvAnyAddress\n"
            "    at: AwareDatetime\n"
            "    hidden: SkipJsonSchema[int]\n"
        ),
    )

    assert {name: row[:2] for name, row in _fields(workspace).items()} == {
        "email": ("string", "email"),
        "site": ("string", "uri"),
        "any_url": ("string", "uri"),
        "address": ("string", "ipvanyaddress"),
        "at": ("string", "date-time"),
        "hidden": ("integer", None),
    }
    assert _open(workspace) is not None


def test_a_typed_dict_key_typing_marks_not_required_is_not_required(tmp_path: Path, libraries):
    """Review M6: in a `TypedDict` a key written `NotRequired[...]`, and every key of a
    `total=False` one not written `Required[...]`, may be left out (the typing
    specification; pydantic's `TypeAdapter` agrees)."""
    workspace = _resolved(
        tmp_path,
        libraries,
        _program(
            "from typing import NotRequired, Required, TypedDict\n"
            "class Settings(TypedDict):\n"
            "    must: int\n"
            "    may: NotRequired[bool]\n"
            "class Partial(TypedDict, total=False):\n"
            "    loose: int\n"
            "    tight: Required[int]\n"
            "class Item(BaseModel):\n"
            "    settings: Settings\n"
            "    partial: Partial\n"
        ),
    )

    assert {name: row[2] for name, row in _fields(workspace, "Settings").items()} == {
        "must": True,
        "may": False,
    }
    assert {name: row[2] for name, row in _fields(workspace, "Partial").items()} == {
        "loose": False,
        "tight": True,
    }


def test_a_tuple_of_two_types_and_a_bare_type_variable_are_not_misread(tmp_path: Path, libraries):
    """Review Minors 5 and 10: `tuple[int, str]` is no array of one item type, so no item is
    published and the shape is open; a field typed by a type variable nothing binds is
    `unresolved`, never the text `None`."""
    workspace = _resolved(
        tmp_path,
        libraries,
        _program(
            "T = TypeVar('T')\n"
            "class Env(BaseModel, Generic[T]):\n"
            "    data: T\n"
            "class Item(BaseModel):\n"
            "    pair: tuple[int, str]\n"
            "    env: Env\n"
        ),
    )

    (pair,) = [
        row
        for row in workspace.query("shape_fields")
        if row["shape_id"] == "app/main/Item#" and row["wire_name"] == "pair"
    ]
    assert (pair["wire_type"], pair["item"]) == ("array", None)
    assert _open(workspace) is True
    assert _fields(workspace, "Env")["data"][3] == "unresolved"


def test_an_excluded_field_leaves_the_response_shape_and_stays_in_the_request(
    tmp_path: Path, libraries
):
    """Review M4 (`excluded_when`, ruled 2026-11-09; `pydantic_naming.md` §6): pydantic never
    writes a field whose `Field` says `exclude=True`, and still reads it. A model only a
    response carries drops it; one only a request carries keeps it; one both carry keeps it at
    `partial`, since one shape holds both directions (N13 B). The `Annotated` merge applies:
    a later `exclude=False` keeps the field."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "main.py": _HEAD + "class Out(BaseModel):\n"
            "    name: str = ''\n"
            "    token: str = Field('', exclude=True)\n"
            "    ann: Annotated[str, Field(exclude=True)] = ''\n"
            "    undone: Annotated[str, Field(exclude=True)] = Field('', exclude=False)\n"
            "class In(BaseModel):\n"
            "    name: str = ''\n"
            "    token: str = Field('', exclude=True)\n"
            "class Both(BaseModel):\n"
            "    token: str = Field('', exclude=True)\n"
            "@router.get('/out')\n"
            "def out() -> Out:\n"
            "    return Out()\n"
            "@router.post('/in')\n"
            "def take(item: In) -> str:\n"
            "    return ''\n"
            "@router.post('/both')\n"
            "def both(item: Both) -> Both:\n"
            "    return item\n"
        },
    )

    assert list(_fields(workspace, "Out")) == ["name", "undone"]
    assert {name: row[3] for name, row in _fields(workspace, "In").items()} == {
        "name": "resolved",
        "token": "resolved",
    }
    assert {name: row[3] for name, row in _fields(workspace, "Both").items()} == {
        "token": "partial"
    }


def test_every_request_source_counts_toward_a_shapes_direction(tmp_path: Path, libraries):
    """Task 9 re-review R2-1: a body FastAPI assembles from several parameters, and one marked
    `Body(embed=True)`, carry their models as requests (their descriptor's `fields`), so a model
    such a body and a response both carry keeps its `exclude=True` field at `partial`: FastAPI
    0.162 publishes `Body2-Input` and `Exb-Input` with `sec`, their `-Output` without."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "main.py": _HEAD + "from fastapi import Body\n"
            "class Body1(BaseModel):\n"
            "    x: int = 0\n"
            "class Body2(BaseModel):\n"
            "    y: int = 0\n"
            "    sec: str = Field('', exclude=True)\n"
            "class Exb(BaseModel):\n"
            "    sec: str = Field('', exclude=True)\n"
            "@router.post('/two')\n"
            "def two(a: Body1, b: Body2) -> Body2:\n"
            "    return b\n"
            "@router.post('/emb')\n"
            "def emb(e: Annotated[Exb, Body(embed=True)]) -> Exb:\n"
            "    return e\n"
        },
    )

    assert {name: row[3] for name, row in _fields(workspace, "Body2").items()} == {
        "y": "resolved",
        "sec": "partial",
    }
    assert {name: row[3] for name, row in _fields(workspace, "Exb").items()} == {"sec": "partial"}


def test_a_bare_ellipsis_value_is_required(tmp_path: Path, libraries):
    """Task 9 re-review R2-3: `x: int = ...` is a required field in pydantic (`...` is no
    default), as `Field(...)` is."""
    workspace = _resolved(
        tmp_path,
        libraries,
        _program("class Item(BaseModel):\n    x: int = ...\n    y: int = 1\n"),
    )

    assert {name: (row[2], row[3]) for name, row in _fields(workspace).items()} == {
        "x": (True, "resolved"),
        "y": (False, "resolved"),
    }


def test_skip_json_schema_is_the_shape_models_envelope(tmp_path: Path):
    """Task 9 re-review R2-9: `SkipJsonSchema[X]` is unwrapped by the pydantic shape model, so
    every catalog naming that model unwraps it, not the FastAPI catalog alone."""
    [catalog] = [one for one in YamlCatalogSource(catalogs_dir()).load() if one.id == "fastapi"]
    document = (catalogs_dir() / "fastapi.yml").read_text(encoding="utf-8")

    assert "SkipJsonSchema" not in document
    assert any(
        wrapper["type"] == "pydantic.json_schema.SkipJsonSchema" for wrapper in catalog.wrappers
    )


# -- Task 9c: library classes' fields read from their headers, so a shape can close ----------


def _with_library(tmp_path: Path, libraries, source: str):
    """The FastAPI environment plus `basekit`, a library installed beside it holding `source`
    as `basekit/__init__.py`: every entry of the environment's site linked into a new site."""
    from sextant.application.ports.detector import LibraryRoot

    real = libraries[0].archive
    site = tmp_path / "site"
    site.mkdir()
    for entry in real.iterdir():
        (site / entry.name).symlink_to(entry)
    (site / "basekit").mkdir()
    (site / "basekit" / "__init__.py").write_text(source, encoding="utf-8")
    info = site / "basekit-1.0.dist-info"
    info.mkdir()
    (info / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: basekit\nVersion: 1.0\n\n", encoding="utf-8"
    )
    (info / "RECORD").write_text(
        f"basekit/__init__.py,sha256=x,1\n{info.name}/METADATA,,\n{info.name}/RECORD,,\n",
        encoding="utf-8",
    )
    return (
        *(LibraryRoot(root.coordinate, root.version, site) for root in libraries),
        LibraryRoot("basekit", "1.0", site),
    )


def test_a_model_extending_base_model_is_closed(tmp_path: Path, libraries):
    """`BaseModel`'s class body declares only `ClassVar`s and names starting with `_`
    (`scripts/probes/pydantic_field_sets.md` §0), so read from its header it contributes no
    field, and a model extending it is described completely by its own body."""
    workspace = _resolved(tmp_path, libraries, _program("class Item(BaseModel):\n    a: int\n"))

    assert _fields(workspace) == {"a": ("integer", None, True, "resolved")}
    assert _open(workspace) is False


def test_a_library_base_with_fields_contributes_them(tmp_path: Path, libraries):
    """A library base's own fields join the model's (probe §2), named and defaulted by the
    shape model's rules as a module class's are; its `ClassVar` and private names are none. Its
    configuration's generator names the model's fields, and its computed field is a field of a
    response (probe §4b)."""
    library = _with_library(
        tmp_path,
        libraries,
        "from typing import ClassVar\n"
        "from pydantic import BaseModel, ConfigDict, Field, computed_field\n"
        "from pydantic.alias_generators import to_camel\n"
        "class Stamped(BaseModel):\n"
        "    model_config = ConfigDict(alias_generator=to_camel)\n"
        "    id: int\n"
        "    created_at: str = Field('now', alias='Created')\n"
        "    _hidden: int = 0\n"
        "    kind: ClassVar[str] = 'x'\n"
        "    @computed_field\n"
        "    @property\n"
        "    def label_text(self) -> str:\n"
        "        return ''\n",
    )
    workspace = _resolved(
        tmp_path,
        library,
        {
            "main.py": _HEAD + "from basekit import Stamped\n"
            "class Item(Stamped):\n"
            "    item_name: str\n"
            "@router.get('/x')\n"
            "def handler() -> Item:\n"
            "    return Item()\n"
        },
    )

    assert _fields(workspace) == {
        "itemName": ("string", None, True, "resolved"),
        "id": ("integer", None, True, "resolved"),
        "Created": ("string", None, False, "resolved"),
        "labelText": ("string", None, True, "resolved"),
    }
    assert _open(workspace) is False


def test_extra_allow_keeps_the_shape_open(tmp_path: Path, libraries):
    """`open_when` (probe §3, §11, §12): `extra='allow'` writes and reads keys no field
    declares, so the shape is open, set on the class, inherited from a module or a library base,
    or written as a plain dict; a child setting `extra='ignore'` over it closes it again, as
    the configuration merge says; a value written as no literal may be `allow`, so it is open."""
    library = _with_library(
        tmp_path,
        libraries,
        "from pydantic import BaseModel, ConfigDict\n"
        "class Loose(BaseModel):\n"
        "    model_config = ConfigDict(extra='allow')\n",
    )
    workspace = _resolved(
        tmp_path,
        library,
        _program(
            "from basekit import Loose\n"
            "def mode() -> str:\n"
            "    return 'allow'\n"
            "class Allows(BaseModel):\n"
            "    model_config = ConfigDict(extra='allow')\n"
            "    a: int = 0\n"
            "class Inherits(Allows):\n"
            "    b: int = 0\n"
            "class Ignores(Allows):\n"
            "    model_config = ConfigDict(extra='ignore')\n"
            "class Forbids(BaseModel):\n"
            "    model_config = ConfigDict(extra='forbid')\n"
            "    a: int = 0\n"
            "class Displayed(BaseModel):\n"
            "    model_config = {'extra': 'allow'}\n"
            "    a: int = 0\n"
            "class DisplayedForbids(BaseModel):\n"
            "    model_config = {'extra': 'forbid', 'alias_generator': to_camel}\n"
            "    a_b: int = 0\n"
            "class Unread(BaseModel):\n"
            "    model_config = ConfigDict(extra=mode())\n"
            "    a: int = 0\n"
            "class FromLibrary(Loose):\n"
            "    a: int = 0\n"
            "class Item(BaseModel):\n"
            "    allows: Allows\n"
            "    inherits: Inherits\n"
            "    ignores: Ignores\n"
            "    forbids: Forbids\n"
            "    displayed: Displayed\n"
            "    displayed_forbids: DisplayedForbids\n"
            "    unread: Unread\n"
            "    from_library: FromLibrary\n"
        ),
    )

    assert {
        shape: _open(workspace, shape)
        for shape in (
            "Allows",
            "Inherits",
            "Ignores",
            "Forbids",
            "Displayed",
            "DisplayedForbids",
            "Unread",
            "FromLibrary",
            "Item",
        )
    } == {
        "Allows": True,
        "Inherits": True,
        "Ignores": False,
        "Forbids": False,
        "Displayed": True,
        "DisplayedForbids": False,
        "Unread": True,
        "FromLibrary": True,
        "Item": False,
    }
    assert list(_fields(workspace, "DisplayedForbids")) == ["aB"]


def test_computed_field_is_a_response_field_not_a_request_field(tmp_path: Path, libraries):
    """`output_fields` (probe §4, §9, §10): a `@computed_field` is written on output and never
    read. It is a field of a shape only responses reach, typed by what its method returns,
    required unless `exclude_if` is written, named by its `alias=`, else by the generator; it
    is no field of a shape only requests reach; in one both reach it is `partial` (N13 B). An
    inherited one counts."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "main.py": _HEAD + "from pydantic import computed_field\n"
            "class Out(BaseModel):\n"
            "    model_config = ConfigDict(alias_generator=to_camel)\n"
            "    a: int = 0\n"
            "    @computed_field\n"
            "    @property\n"
            "    def doubled_value(self) -> int:\n"
            "        return 2\n"
            "    @computed_field(alias='T')\n"
            "    @property\n"
            "    def tripled(self) -> int:\n"
            "        return 3\n"
            "    @computed_field(exclude_if=lambda v: v > 5)\n"
            "    @property\n"
            "    def maybe(self) -> str:\n"
            "        return ''\n"
            "class OutChild(Out):\n"
            "    b: int = 0\n"
            "class In(BaseModel):\n"
            "    a: int = 0\n"
            "    @computed_field\n"
            "    @property\n"
            "    def doubled(self) -> int:\n"
            "        return 2\n"
            "class Both(BaseModel):\n"
            "    a: int = 0\n"
            "    @computed_field\n"
            "    @property\n"
            "    def doubled(self) -> int:\n"
            "        return 2\n"
            "@router.get('/out')\n"
            "def out() -> Out:\n"
            "    return Out()\n"
            "@router.get('/child')\n"
            "def child() -> OutChild:\n"
            "    return OutChild()\n"
            "@router.post('/in')\n"
            "def take(item: In) -> str:\n"
            "    return ''\n"
            "@router.post('/both')\n"
            "def both(item: Both) -> Both:\n"
            "    return item\n"
        },
    )

    assert _fields(workspace, "Out") == {
        "a": ("integer", None, False, "resolved"),
        "doubledValue": ("integer", None, True, "resolved"),
        "T": ("integer", None, True, "resolved"),
        "maybe": ("string", None, False, "resolved"),
    }
    assert set(_fields(workspace, "OutChild")) == {"b", "a", "doubledValue", "T", "maybe"}
    assert _fields(workspace, "In") == {"a": ("integer", None, False, "resolved")}
    assert _fields(workspace, "Both") == {
        "a": ("integer", None, False, "resolved"),
        "doubled": ("integer", None, True, "partial"),
    }
    assert {shape: _open(workspace, shape) for shape in ("Out", "OutChild", "In", "Both")} == {
        "Out": False,
        "OutChild": False,
        "In": False,
        "Both": False,
    }


def test_an_unreadable_base_keeps_the_shape_open(tmp_path: Path, libraries):
    """A base no library holds, and a library class whose bases are not read (a call result,
    so it gets no header), may declare fields nobody here can see: the shape stays open."""
    library = _with_library(
        tmp_path,
        libraries,
        "from pydantic import BaseModel\n"
        "def make_base():\n"
        "    return BaseModel\n"
        "class Made(make_base()):\n"
        "    x: int = 0\n",
    )
    workspace = _resolved(
        tmp_path,
        library,
        _program(
            "from basekit import Made\n"
            "from notinstalled import Missing\n"
            "class FromCall(Made):\n"
            "    a: int = 0\n"
            "class FromMissing(Missing):\n"
            "    a: int = 0\n"
            "class Item(BaseModel):\n"
            "    from_call: FromCall\n"
            "    from_missing: FromMissing\n"
        ),
    )

    assert _open(workspace, "FromCall") is True
    assert _open(workspace, "FromMissing") is True


def test_a_model_serializer_opens_the_response_shape_only(tmp_path: Path, libraries):
    """`output_open_when` (probe §6): a `@model_serializer`, plain or wrap, writes whatever it
    returns, so a shape a response reaches is open; the input it reads is the fields, so a
    shape only requests reach is closed."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "main.py": _HEAD + "from pydantic import model_serializer\n"
            "class Out(BaseModel):\n"
            "    a: int = 0\n"
            "    @model_serializer\n"
            "    def dump(self) -> dict:\n"
            "        return {}\n"
            "class Wrapped(BaseModel):\n"
            "    a: int = 0\n"
            "    @model_serializer(mode='wrap')\n"
            "    def dump(self, handler) -> dict:\n"
            "        return handler(self)\n"
            "class In(BaseModel):\n"
            "    a: int = 0\n"
            "    @model_serializer\n"
            "    def dump(self) -> dict:\n"
            "        return {}\n"
            "@router.get('/out')\n"
            "def out() -> Out:\n"
            "    return Out()\n"
            "@router.get('/wrapped')\n"
            "def wrapped() -> Wrapped:\n"
            "    return Wrapped()\n"
            "@router.post('/in')\n"
            "def take(item: In) -> str:\n"
            "    return ''\n"
        },
    )

    assert {shape: _open(workspace, shape) for shape in ("Out", "Wrapped", "In")} == {
        "Out": True,
        "Wrapped": True,
        "In": False,
    }


def test_a_core_schema_hook_keeps_the_shape_open(tmp_path: Path, libraries):
    """`output_open_when` (probe §7): a model's own `__get_pydantic_core_schema__` may build
    any schema, so the shape is open in both directions, declared on the model or inherited;
    `BaseModel`'s own is the default pydantic does not call (`_generate_schema.py`), so a plain
    model stays closed. Whether the method returns `handler(source)` is not read (ruling)."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "main.py": _HEAD + "class Hooked(BaseModel):\n"
            "    a: int = 0\n"
            "    @classmethod\n"
            "    def __get_pydantic_core_schema__(cls, source, handler, /):\n"
            "        return handler(source)\n"
            "class Heir(Hooked):\n"
            "    b: int = 0\n"
            "class Plain(BaseModel):\n"
            "    a: int = 0\n"
            "@router.post('/in')\n"
            "def take(item: Hooked) -> str:\n"
            "    return ''\n"
            "@router.get('/heir')\n"
            "def heir() -> Heir:\n"
            "    return Heir()\n"
            "@router.get('/plain')\n"
            "def plain() -> Plain:\n"
            "    return Plain()\n"
        },
    )

    assert {shape: _open(workspace, shape) for shape in ("Hooked", "Heir", "Plain")} == {
        "Hooked": True,
        "Heir": True,
        "Plain": False,
    }


def test_a_root_model_shape_stays_open(tmp_path: Path, libraries):
    """Probe §5: a `RootModel`'s wire value is its root, not an object holding `root`. Ruled
    2026-11-09: it stays open, with no key. `RootModel[list[str]]` binds the type variable its
    `root` field is declared with, which the expansion does not substitute through a base, so
    the field holds an undescribed value and the shape is open."""
    workspace = _resolved(
        tmp_path,
        libraries,
        _program(
            "from pydantic import RootModel\n"
            "class Tags(RootModel[list[str]]):\n"
            "    pass\n"
            "class Item(BaseModel):\n"
            "    tags: Tags\n"
        ),
    )

    assert _open(workspace, "Tags") is True


def test_a_field_serializer_leaves_the_field_set(tmp_path: Path, libraries):
    """Probe §8: `@field_serializer` changes what a field's value is written as, not which
    fields there are, so the shape is closed with the field it names. (Its output TYPE is the
    serializer's return; that is logged, not built, ruling 2026-11-09.)"""
    workspace = _resolved(
        tmp_path,
        libraries,
        _program(
            "from pydantic import field_serializer\n"
            "class Item(BaseModel):\n"
            "    a: int = 0\n"
            "    @field_serializer('a')\n"
            "    def as_text(self, value: int) -> str:\n"
            "        return str(value)\n"
        ),
    )

    assert list(_fields(workspace)) == ["a"]
    assert _open(workspace) is False


def test_a_field_read_under_another_name_opens_a_shape_requests_reach(tmp_path: Path, libraries):
    """N13 B keeps one shape per model, under its output names. A field a request is read under
    another name (`serialization_alias` alone, polar's `MetadataInputMixin`) or under names not
    read (`AliasChoices`) leaves the shape's input field set described under names a request
    does not send, so a shape requests reach is open; one only responses reach is closed."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "main.py": _HEAD + "class In(BaseModel):\n"
            "    metadata: dict = Field(default_factory=dict, serialization_alias='user_metadata')\n"
            "class Out(BaseModel):\n"
            "    metadata: dict = Field(validation_alias=AliasChoices('user_metadata', 'metadata'))\n"
            "class Choices(BaseModel):\n"
            "    metadata: dict = Field(validation_alias=AliasChoices('user_metadata', 'metadata'))\n"
            "@router.post('/in')\n"
            "def take(item: In, other: Choices) -> Out:\n"
            "    return Out(metadata={})\n"
        },
    )

    assert {shape: _open(workspace, shape) for shape in ("In", "Out", "Choices")} == {
        "In": True,
        "Out": False,
        "Choices": True,
    }
