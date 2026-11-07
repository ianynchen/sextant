"""Name binding for one Python file (spec 2026-11-06 §3a): which symbol each name of the
file's own scope refers to.

A name is bound by an import, a `class`, a `def` or an assignment. An import is bound by
PATH only: `from app.models import Order` is the member `Order` of the module `app/models`,
or the module `app/models/Order` when such a file exists in the module's import roots. The
other file's body is never read (M03: one file at a time).

A decorated `def` binds its name to what its outermost decorator returns (`f = dec(f)`,
design 2026-11-06-reading-decorators §3e): a value, so the name is a `variable`. The
language's own descriptors (`DESCRIPTORS`) keep the name a `function`.

Two branches that bind one name differently give a CLOSED LIST of both bindings, in the
order the branches are written: `try: import ujson as json` / `except ImportError: import
json` binds `json` to `ujson` and to `json`, and never to the first one silently.
"""

import ast
import builtins
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal, Protocol

from sextant.domain.facts import CallArgument, TypeRef

if TYPE_CHECKING:
    from sextant.ingress.extract.python.typing_rules import ClassShape

# What a name of THIS file is, where the file can tell. An imported name has no kind:
# whether `fastapi.FastAPI` is a class or a function is in a file this scanner does not
# read.
Kind = Literal["class", "function", "variable", "type_variable", "type_alias"]

# The calls that make a name a type variable (the typing specification's three).
_TYPE_VARIABLE_FACTORIES = frozenset({"TypeVar", "ParamSpec", "TypeVarTuple"})
_TYPING_MODULES = frozenset({"typing", "typing_extensions"})


@dataclass(frozen=True)
class Target:
    """One thing a name refers to: the module `module` itself when `member` is None,
    else the name `member` inside it (`Outer.Inner` for a nested class)."""

    module: str
    member: str | None = None
    # Set only for a name this file defines.
    kind: Kind | None = None
    # A `type X = ...` statement or a `TypeAlias` assignment: the written type.
    alias_of: ast.expr | None = None


@dataclass(frozen=True)
class Binding:
    """The closed list of targets a name has: one for nearly every name, several where
    branches bind it differently."""

    targets: tuple[Target, ...]


@dataclass(frozen=True)
class CallableType:
    """`Callable[[P, ...], R]`, as the typing specification defines it: calling the value
    gives `returns`. `parameters` are the written parameter types, None for `...`. A type
    variable in `returns` takes the type of the argument that fills it (design
    2026-11-06-reading-decorators §3b)."""

    parameters: tuple[TypeRef, ...] | None
    returns: TypeRef


@dataclass(frozen=True)
class Returned:
    """What a library call returns, by its written signatures: one type where the
    argument types choose one overload (`resolved`), else the closed list of what the
    overloads they leave return (`narrowed`). A type is a class, or a callable that
    gives one (a decorator factory's result)."""

    types: tuple[TypeRef | CallableType, ...]
    resolution: Literal["resolved", "narrowed"]


class LibraryNames(Protocol):
    """What the scanned environment's libraries and typeshed say (`libraries.py`)."""

    def member(self, target: Target, name: str) -> tuple[Target, ...] | None:
        """`target.name` as the library defines it, or None where no library read says:
        one target, or the closed list where the library's branches bind it differently."""
        ...

    def call_returns(
        self,
        owner: str,
        name: str,
        arguments: Sequence[CallArgument],
        *,
        unpacked: bool = False,
        receiver: TypeRef | None = None,
        argument_types: Sequence[TypeRef | None] = (),
        self_type: TypeRef | None = None,
    ) -> Returned | None:
        """What the call `owner.name(arguments)` returns, or None where nothing says.
        `unpacked`: the call unpacks `*args`, so how many arguments it has is not known.
        `receiver`: the type written for the receiver, whose type arguments fill the
        class's type variables; `argument_types`: each argument's type where it is known;
        `self_type`: what `Self` is, where the receiver is a subclass's."""
        ...

    def construct(
        self,
        owner: str,
        arguments: Sequence[CallArgument],
        argument_types: Sequence[TypeRef | None],
    ) -> TypeRef | None:
        """The type the constructor call `owner(arguments)` makes, with its type arguments
        filled by the arguments, or None."""
        ...

    def shape_of(self, symbol: str) -> "ClassShape | None":
        """A library class's type parameters, written bases and members, or None."""
        ...


@dataclass(frozen=True)
class ModuleIndex:
    """The module paths that exist in the scanned module's import roots, by file path
    alone (`app/api/items` for `app/api/items.py` or `app/api/items/__init__.py`), and
    the libraries a name of another module is looked up in."""

    modules: frozenset[str]
    libraries: LibraryNames | None = field(default=None, compare=False)
    # Every module path and every folder above one: `owns`' answer, worked out once,
    # because every name of another module asks it (GUIDELINES §8.7).
    _owned: frozenset[str] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        owned = set(self.modules)
        for module in self.modules:
            while "/" in module:
                module = module.rpartition("/")[0]
                owned.add(module)
        object.__setattr__(self, "_owned", frozenset(owned))

    def is_module(self, path: str) -> bool:
        return path in self.modules

    def owns(self, path: str) -> bool:
        """Whether `path` or a package above it is in the scanned module."""
        return path in self._owned


def module_path(relative: str) -> tuple[str, bool]:
    """The module path of a file relative to its import root, and whether it is a
    package: `app/api/items.py` is `app/api/items`, `app/api/__init__.py` is the
    package `app/api`."""
    without = relative.removesuffix(".py")
    if without == "__init__":
        return "", True
    if without.endswith("/__init__"):
        return without.removesuffix("/__init__"), True
    return without, False


def member_of(
    target: Target, name: str, index: ModuleIndex, *, more_follow: bool
) -> tuple[Target, ...]:
    """`target.name`: a submodule where one exists by path, else a member. For a library
    module, which this scanner cannot list, a name with more names after it is taken
    as a module (`fastapi.routing.APIRouter`), and so is a library member with a name
    after it (`from fastapi import routing`, then `routing.APIRouter`). Where a library
    read says (`libraries.py`), its answer is taken: a submodule, or the member's defining
    symbol (`fastapi.APIRouter` is `fastapi.routing.APIRouter`), or the closed list of
    them where the library's branches bind the name differently."""
    if index.libraries is not None and not index.owns(target.module):
        found = index.libraries.member(target, name)
        if found is not None:
            return found
    if target.member is not None and not index.owns(target.module):
        submodule = f"{target.module}/{target.member.replace('.', '/')}"
        return member_of(Target(submodule), name, index, more_follow=more_follow)
    if target.member is not None:
        return (Target(target.module, f"{target.member}.{name}"),)
    candidate = f"{target.module}/{name}" if target.module else name
    if index.is_module(candidate):
        return (Target(candidate),)
    if more_follow and not index.owns(target.module):
        return (Target(candidate),)
    return (Target(target.module, name),)


def bind_names(
    body: list[ast.stmt],
    here: str,
    *,
    is_package: bool,
    index: ModuleIndex,
    owner: str | None = None,
) -> dict[str, Binding]:
    """Every name the statements bind in the scope they belong to, read in order. A
    later binding replaces an earlier one; alternative branches add up. `owner` is the
    dotted class path (`Outer.Inner`) when the statements are a class body."""
    binder = _Binder(here, is_package, index, owner)
    return binder.run(body, {})


class _Binder:
    def __init__(self, here: str, is_package: bool, index: ModuleIndex, owner: str | None) -> None:
        self._here = here
        self._package = here if is_package else here.rpartition("/")[0]
        self._index = index
        self._owner = owner

    def _own(self, name: str, kind: Kind, alias_of: ast.expr | None = None) -> Binding:
        member = f"{self._owner}.{name}" if self._owner else name
        return _one(Target(self._here, member, kind, alias_of))

    def run(self, body: Iterable[ast.stmt], names: dict[str, Binding]) -> dict[str, Binding]:
        names = dict(names)
        for statement in body:
            names = self._statement(statement, names)
        return names

    def _statement(self, node: ast.stmt, names: dict[str, Binding]) -> dict[str, Binding]:
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname is not None:
                    names[alias.asname] = _one(Target(alias.name.replace(".", "/")))
                else:
                    head = alias.name.partition(".")[0]
                    names[head] = _one(Target(head))
        elif isinstance(node, ast.ImportFrom):
            base = self._from_base(node)
            if base is not None:
                for alias in node.names:
                    if alias.name == "*":
                        continue
                    targets = member_of(Target(base), alias.name, self._index, more_follow=False)
                    names[alias.asname or alias.name] = Binding(targets)
        elif isinstance(node, ast.ClassDef):
            names[node.name] = self._own(node.name, "class")
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            decorated = holds_decorated_value(node, lambda written: self._lookup(written, names))
            kind: Kind = "variable" if decorated else "function"
            names[node.name] = self._own(node.name, kind)
        elif isinstance(node, ast.TypeAlias) and isinstance(node.name, ast.Name):
            names[node.name.id] = self._own(node.name.id, "type_alias", node.value)
        elif isinstance(node, ast.Assign | ast.AnnAssign):
            self._assignment(node, names)
        elif isinstance(node, ast.If):
            names = _either(names, [self.run(node.body, names), self.run(node.orelse, names)])
        elif isinstance(node, ast.Try | ast.TryStar):
            tried = self.run(node.orelse, self.run(node.body, names))
            handled = [self.run(handler.body, names) for handler in node.handlers]
            names = self.run(node.finalbody, _either(names, [tried, *handled]))
        elif isinstance(node, ast.With | ast.AsyncWith):
            names = self.run(node.body, names)
        elif isinstance(node, ast.For | ast.AsyncFor | ast.While):
            names = _either(names, [names, self.run([*node.body, *node.orelse], names)])
        elif isinstance(node, ast.Match):
            names = _either(names, [self.run(case.body, names) for case in node.cases])
        return names

    def _lookup(self, node: ast.expr, names: dict[str, Binding]) -> tuple[Target, ...]:
        """What a written name refers to, then the builtins, as `TypeScope.lookup` reads."""
        found = resolve(node, names, self._index)
        if found or not isinstance(node, ast.Name) or node.id not in _BUILTIN_NAMES:
            return found
        return (Target(_BUILTINS, node.id),)

    def _assignment(self, node: ast.Assign | ast.AnnAssign, names: dict[str, Binding]) -> None:
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        aliased = self._alias(node, names, targets)
        if aliased is not None:
            names[aliased[0]] = aliased[1]
            return
        kind, alias_of = self._assigned(node, names)
        for written in targets:
            for name in _names_in(written):
                names[name] = self._own(name, kind, alias_of)

    def _alias(
        self,
        node: ast.Assign | ast.AnnAssign,
        names: dict[str, Binding],
        targets: Sequence[ast.expr],
    ) -> tuple[str, Binding] | None:
        """A module-level name given another name of a module, a class or a function
        (`DecodeError = jwt.DecodeError`) is bound as that name is, as an import binds
        it. A computed value, or a name of a value, stays a value."""
        value = node.value
        if self._owner is not None or value is None or len(targets) != 1:
            return None
        if not isinstance(targets[0], ast.Name) or not isinstance(value, ast.Name | ast.Attribute):
            return None
        found = resolve(value, names, self._index)
        if not found or any(target.kind not in (None, "class", "function") for target in found):
            return None
        return targets[0].id, Binding(found)

    def _assigned(
        self, node: ast.Assign | ast.AnnAssign, names: dict[str, Binding]
    ) -> tuple[Kind, ast.expr | None]:
        if (
            isinstance(node, ast.AnnAssign)
            and node.value is not None
            and self._is_typing(node.annotation, names, {"TypeAlias"})
        ):
            return "type_alias", node.value
        value = node.value
        if isinstance(value, ast.Call) and self._is_typing(
            value.func, names, _TYPE_VARIABLE_FACTORIES
        ):
            return "type_variable", None
        return "variable", None

    def _is_typing(
        self, node: ast.expr, names: dict[str, Binding], members: frozenset[str] | set[str]
    ) -> bool:
        """Whether `node` names one of the typing specification's `members`, by what
        the file binds the name to, never by the name alone."""
        return any(
            is_typing(target, member)
            for target in resolve(node, names, self._index)
            for member in members
        )

    def _from_base(self, node: ast.ImportFrom) -> str | None:
        written = (node.module or "").replace(".", "/")
        if node.level == 0:
            return written
        package = self._package
        for _ in range(node.level - 1):
            if not package:
                # Above the import root: a relative import this module cannot resolve.
                return None
            package = package.rpartition("/")[0]
        return "/".join(part for part in (package, written) if part)


def _one(target: Target) -> Binding:
    return Binding((target,))


def _either(before: dict[str, Binding], branches: list[dict[str, Binding]]) -> dict[str, Binding]:
    """The names after one of `branches` ran. A name a branch did not touch keeps its
    value from `before` on that branch; different values on different branches are a
    closed list, in written order."""
    merged: dict[str, Binding] = {}
    for name in dict.fromkeys(key for branch in branches for key in branch):
        targets: list[Target] = []
        for branch in branches:
            found = branch.get(name, before.get(name))
            for target in found.targets if found is not None else ():
                if target not in targets:
                    targets.append(target)
        merged[name] = Binding(tuple(targets))
    return merged


def _names_in(target: ast.expr) -> list[str]:
    if isinstance(target, ast.Name):
        return [target.id]
    if isinstance(target, ast.Tuple | ast.List):
        return [name for element in target.elts for name in _names_in(element)]
    if isinstance(target, ast.Starred):
        return _names_in(target.value)
    return []


def resolve(node: ast.expr, names: dict[str, Binding], index: ModuleIndex) -> tuple[Target, ...]:
    """The targets a written name or dotted name refers to, or none where the file does
    not bind its first name."""
    chain: list[str] = []
    while isinstance(node, ast.Attribute):
        chain.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name) or node.id not in names:
        return ()
    chain.reverse()
    found: list[Target] = []
    for start in names[node.id].targets:
        reached: tuple[Target, ...] = (start,)
        for position, name in enumerate(chain):
            follow = position < len(chain) - 1
            reached = tuple(
                one
                for target in reached
                for one in member_of(target, name, index, more_follow=follow)
            )
        for target in reached:
            if target not in found:
                found.append(target)
    return tuple(found)


# The language's own method kinds (design 2026-11-06-reading-decorators §3e): a `def` they
# decorate keeps the method model, as a JVM modifier does. Matched by the symbol a
# decorator names, never by its text.
DESCRIPTORS = frozenset(
    {
        ("builtins", "staticmethod"),
        ("builtins", "classmethod"),
        ("builtins", "property"),
        ("functools", "cached_property"),
        ("typing", "overload"),
        ("typing_extensions", "overload"),
        ("abc", "abstractmethod"),
    }
)
_BUILTINS = "builtins"
_BUILTIN_NAMES = frozenset(dir(builtins))
# A property's own decorators (`@x.setter` on `def x`): the property's methods.
_PROPERTY_PARTS = frozenset({"setter", "getter", "deleter"})


def is_descriptor(
    decorator: ast.expr, name: str, lookup: Callable[[ast.expr], tuple[Target, ...]]
) -> bool:
    """Whether `decorator`, on the `def` named `name`, is one of the language's own method
    kinds: a name bound to one of `DESCRIPTORS`, or `@name.setter` (`getter`, `deleter`) of
    the property of that name."""
    if (
        isinstance(decorator, ast.Attribute)
        and decorator.attr in _PROPERTY_PARTS
        and isinstance(decorator.value, ast.Name)
        and decorator.value.id == name
    ):
        return True
    if not isinstance(decorator, ast.Name | ast.Attribute):
        return False
    targets = lookup(decorator)
    return len(targets) == 1 and (targets[0].module, targets[0].member) in DESCRIPTORS


def holds_decorated_value(
    node: ast.FunctionDef | ast.AsyncFunctionDef, lookup: Callable[[ast.expr], tuple[Target, ...]]
) -> bool:
    """Whether the name of `node` holds its decorators' result rather than the function:
    it carries a decorator that is not one of the language's own method kinds. With both
    kinds, the name holds the outermost decorator's result (design §3e)."""
    return any(not is_descriptor(d, node.name, lookup) for d in node.decorator_list)


def is_typing(target: Target, name: str) -> bool:
    """Whether `target` is the typing specification's `name` (`typing.Optional`,
    `typing_extensions.Optional`)."""
    return target.module in _TYPING_MODULES and target.member == name
