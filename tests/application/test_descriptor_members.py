"""A class member whose value is a descriptor is read through the descriptor (task 9c
re-review N1), and a class body's never-running blocks keep their symbols (N2).

Python's attribute lookup: reading a name found on a class whose value's class defines
`__get__` gives what `__get__` returns. pydantic's `BaseModel.model_fields` is such a member
(`@_utils.deprecated_instance_property @classmethod`, whose `__get__` hands back the wrapped
function's result, `scripts/probes/pydantic_field_sets.md` §16), so `cls.model_fields.items()`
calls `dict.items`, never a method of the descriptor class.
"""

from pathlib import Path

import test_fastapi_routes
from test_fastapi_routes import _resolved
from test_pydantic_shapes import _HEAD, _fields

libraries = test_fastapi_routes.libraries

_DESCRIPTORS = (
    "from typing import Callable, Generic, TYPE_CHECKING, TypeVar\n"
    "T = TypeVar('T')\n"
    "R = TypeVar('R')\n"
    "class wrapping(Generic[T, R]):\n"
    "    def __init__(self, fget: Callable[[type[T]], R], /) -> None:\n"
    "        self.fget = fget\n"
    "    def __get__(self, instance: T | None, objtype: type[T]) -> R:\n"
    "        return self.fget.__get__(instance, objtype)()\n"
    "class Box:\n"
    "    def open(self) -> int:\n"
    "        return 1\n"
    "class boxing:\n"
    "    def __init__(self, f) -> None:\n"
    "        self.f = f\n"
    "    def __get__(self, instance, owner) -> Box:\n"
    "        return Box()\n"
    "class opaque:\n"
    "    def __init__(self, f) -> None:\n"
    "        self.f = f\n"
    "    def __get__(self, instance, owner):\n"
    "        return self.f\n"
    "class inner:\n"
    "    def __get__(self, instance, owner) -> int:\n"
    "        return 1\n"
    "    def bit_length(self) -> int:\n"
    "        return 1\n"
    "class chaining:\n"
    "    def __init__(self, f) -> None:\n"
    "        self.f = f\n"
    "    def __get__(self, instance, owner) -> inner:\n"
    "        return inner()\n"
    "class M(BaseModel):\n"
    "    @chaining\n"
    "    def chained(self) -> str:\n"
    "        return ''\n"
    "    @wrapping\n"
    "    @classmethod\n"
    "    def stuff(cls) -> dict[str, int]:\n"
    "        return {}\n"
    "    @boxing\n"
    "    def boxed(self) -> str:\n"
    "        return ''\n"
    "    @opaque\n"
    "    def hidden(self) -> str:\n"
    "        return ''\n"
    "def module_descriptor():\n"
    "    return M.stuff.items()\n"
    "def library_descriptor():\n"
    "    return M.model_fields.items()\n"
    "def concrete_get():\n"
    "    return M.boxed.open()\n"
    "def chained_get():\n"
    "    return M.chained.bit_length()\n"
    "def unread_get():\n"
    "    return M.hidden.upper()\n"
)


def _targets(workspace, caller: str) -> list[str | None]:
    return sorted(
        str(row["target"])
        for row in workspace.query("call_edges")
        if f"#{caller}(" in str(row["caller"])
    )


def test_a_descriptor_member_is_read_through_its_get(tmp_path: Path, libraries):
    """A member decorated with a class defining `__get__` takes `__get__`'s return where it
    names a class (`Box`); where `__get__` hands back a type variable its constructor's
    callable gives, the wrapped function's return (`dict`), for a module class and for
    pydantic's own `deprecated_instance_property`; where neither is read, or what `__get__`
    gives is itself a descriptor (whose read is not this one), nothing. Never a descriptor
    class."""
    workspace = _resolved(tmp_path, libraries, {"main.py": _HEAD + _DESCRIPTORS})

    every = [
        target
        for caller in (
            "module_descriptor",
            "library_descriptor",
            "concrete_get",
            "unread_get",
            "chained_get",
        )
        for target in _targets(workspace, caller)
    ]
    assert not [
        target
        for target in every
        if "wrapping#" in target
        or "deprecated_instance_property#" in target
        or "boxing#" in target
        or "opaque#" in target
        or "chaining#" in target
        or "inner#" in target
    ]
    assert _targets(workspace, "module_descriptor") == ["builtins/dict#items(sig_dd69782a)."]
    assert _targets(workspace, "library_descriptor") == ["builtins/dict#items(sig_dd69782a)."]
    assert _targets(workspace, "concrete_get") == ["app/main/Box#open(sig_dd69782a)."]


def test_a_never_running_block_keeps_its_symbols_out_of_the_field_set_only(
    tmp_path: Path, libraries
):
    """Review N2: a class body's `if TYPE_CHECKING:` declarations stay symbols, so a call to a
    method stub declared there keeps its callee; only the field set leaves them out. A name
    the running arm declares too is a field (openai's `if TYPE_CHECKING: ... else: ...`). The
    class extends a library class, whose methods are not read, as polar's `AuthorizationServer`
    does: without the stub's symbol the lookup would end there."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "main.py": _HEAD + "from typing import TYPE_CHECKING\n"
            "class Svc(APIRouter):\n"
            "    if TYPE_CHECKING:\n"
            "        def go(self) -> int: ...\n"
            "class Item(BaseModel):\n"
            "    a: int\n"
            "    if TYPE_CHECKING:\n"
            "        hinted: int\n"
            "        both: int\n"
            "    else:\n"
            "        both: int\n"
            "def make():\n"
            "    return Svc()\n"
            "def call():\n"
            "    return make().go()\n"
            "@router.post('/x')\n"
            "def handler(item: Item) -> Item:\n"
            "    return item\n"
        },
    )

    declared = {
        str(row["symbol"]).rsplit(" ", 1)[-1] for row in workspace.query("declared_symbols")
    }
    assert "app/main/Svc#go(sig_dd69782a)." in declared
    assert "app/main/Item#hinted." in declared
    assert "app/main/Svc#go(sig_dd69782a)." in _targets(workspace, "call")
    assert set(_fields(workspace)) == {"a", "both"}


def test_a_descriptor_applies_only_to_an_object_found_on_the_class(tmp_path: Path, libraries):
    """Review R2-2: Python runs `__get__` only for an object found in the class's namespace. An
    object an instance holds (`self.tool = Tool()` in `__init__`) is read as itself, so
    `self.tool.run()` calls `Tool.run`; the same descriptor written in the class body is read
    through `__get__`."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "main.py": _HEAD + "class Box:\n"
            "    def open(self) -> int:\n"
            "        return 1\n"
            "class Tool:\n"
            "    def __get__(self, obj, owner) -> Box:\n"
            "        return Box()\n"
            "    def run(self) -> int:\n"
            "        return 1\n"
            "class Holder:\n"
            "    def __init__(self) -> None:\n"
            "        self.tool = Tool()\n"
            "    def use(self) -> int:\n"
            "        return self.tool.run()\n"
            "class Owner:\n"
            "    tool = Tool()\n"
            "    def use(self) -> int:\n"
            "        return self.tool.open()\n"
        },
    )

    assert [t for t in _targets(workspace, "use") if "run" in t] == [
        "app/main/Tool#run(sig_dd69782a)."
    ]
    assert "app/main/Box#open(sig_dd69782a)." in _targets(workspace, "use")


def test_an_overloaded_get_is_unknown_and_a_get_returning_self_is_the_descriptor(
    tmp_path: Path, libraries
):
    """Review R2-1: a `__get__` overloaded by access (the class gets one type, an instance
    another) is not read by its first overload: nothing is read. A `__get__` written to return
    `Self` gives the descriptor object itself, as Python does."""
    workspace = _resolved(
        tmp_path,
        libraries,
        {
            "main.py": _HEAD + "from typing import Any, Self, overload\n"
            "class Expr:\n"
            "    def desc(self) -> 'Expr':\n"
            "        return self\n"
            "class Col:\n"
            "    @overload\n"
            "    def __get__(self, instance: None, owner: Any) -> Expr: ...\n"
            "    @overload\n"
            "    def __get__(self, instance: object, owner: Any) -> int: ...\n"
            "    def __get__(self, instance, owner):\n"
            "        return 1\n"
            "class SelfDesc:\n"
            "    def __get__(self, instance, owner) -> Self:\n"
            "        return self\n"
            "    def ping(self) -> int:\n"
            "        return 1\n"
            "class M:\n"
            "    c = Col()\n"
            "    s = SelfDesc()\n"
            "    def overloaded(self) -> int:\n"
            "        return self.c.bit_length()\n"
            "    def itself(self) -> int:\n"
            "        return self.s.ping()\n"
        },
    )

    assert not [t for t in _targets(workspace, "overloaded") if "Expr#" in t or "Col#" in t]
    assert _targets(workspace, "itself") == ["app/main/SelfDesc#ping(sig_dd69782a)."]
