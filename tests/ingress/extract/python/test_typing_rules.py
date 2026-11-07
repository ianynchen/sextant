"""Rule 1 (spec 2026-11-06 §3a): a type written in the code, bound through the file's own
imports to a symbol. Nothing here reads another file's body or a library."""

import ast

from sextant.domain.facts import TypeRef
from sextant.ingress.extract.python.imports import ModuleIndex, bind_names
from sextant.ingress.extract.python.typing_rules import TypeScope, type_ref


def _scope(source: str, here: str = "app/m", modules: frozenset[str] = frozenset()) -> TypeScope:
    tree = ast.parse(source)
    index = ModuleIndex(modules | {here})
    return TypeScope(
        names=bind_names(tree.body, here, is_package=False, index=index), here=here, index=index
    )


def _type(annotation: str, source: str = "", **scope) -> TypeRef | None:
    return type_ref(ast.parse(annotation, mode="eval").body, _scope(source, **scope))


def test_optional_is_nullable():
    assert _type("Optional[int]", "from typing import Optional\n") == TypeRef(
        symbol="builtins/int#", nullable=True, nullable_resolution="resolved"
    )


def test_pipe_none_is_nullable():
    assert _type("int | None") == TypeRef(
        symbol="builtins/int#", nullable=True, nullable_resolution="resolved"
    )


def test_union_is_type_arguments():
    found = _type("Union[int, str]", "from typing import Union\n")

    assert found is not None
    assert found.symbol == "typing/Union#"
    assert [argument.symbol for argument in found.arguments] == ["builtins/int#", "builtins/str#"]


def test_type_of_x_return_means_x():
    found = _type("type[_APIRouter]", "from fastapi import APIRouter as _APIRouter\n")

    assert found is not None
    assert found.symbol == "fastapi/APIRouter#"


def test_generic_keeps_its_arguments():
    found = _type("list[Order]", "class Order: pass\n")

    assert found is not None
    assert found.symbol == "builtins/list#"
    assert [argument.symbol for argument in found.arguments] == ["app/m/Order#"]


def test_dotted_name_through_a_module_import():
    found = _type("routing.APIRouter", "from fastapi import routing\n")

    assert found is not None
    assert found.symbol == "fastapi/routing/APIRouter#"


def test_relative_import_is_bound_by_path():
    found = _type(
        "Order",
        "from .models import Order\n",
        here="app/api/items",
        modules=frozenset({"app/api/models"}),
    )

    assert found is not None
    assert found.symbol == "app/api/models/Order#"


def test_annotated_is_its_first_argument():
    found = _type("Annotated[int, Query()]", "from typing import Annotated\n")

    assert found is not None
    assert found.symbol == "builtins/int#"


def test_type_variable_is_its_bare_name():
    found = _type("T", "from typing import TypeVar\nT = TypeVar('T')\n")

    assert found == TypeRef(symbol="T")


def test_unknown_name_has_no_type():
    """A name the file does not bind is not guessed."""
    assert _type("Mystery") is None


def test_closed_list_binding_is_a_union_of_both():
    found = _type(
        "json.JSONDecodeError",
        "try:\n    import ujson as json\nexcept ImportError:\n    import json\n",
    )

    assert found is not None
    assert found.symbol == "typing/Union#"
    assert [argument.symbol for argument in found.arguments] == [
        "ujson/JSONDecodeError#",
        "json/JSONDecodeError#",
    ]
