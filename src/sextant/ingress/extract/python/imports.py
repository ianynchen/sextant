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
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Literal, Protocol

from sextant.domain.facts import CallArgument, TypeRef

if TYPE_CHECKING:
    from sextant.ingress.extract.python.typing_rules import ClassShape, Hierarchy

# What a name of THIS file is, where the file can tell. An imported name has no kind:
# whether `fastapi.FastAPI` is a class or a function is in a file this scanner does not
# read.
# `new_class` is a name bound to a class the code makes by a call (the typing
# specification's functional `NamedTuple` and `TypedDict`): a new class with no class
# symbol, so the name names no type and a call of it is no construction of a known class.
Kind = Literal[
    "class", "function", "variable", "type_variable", "type_alias", "new_type", "new_class"
]

# The calls that make a name a type variable (the typing specification's three).
_TYPE_VARIABLE_FACTORIES = frozenset({"TypeVar", "ParamSpec", "TypeVarTuple"})
# The typing specification's functional forms that make a new class (ruling R17 review).
_CLASS_FACTORIES = frozenset({"NamedTuple", "TypedDict"})
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

    def metaclass_call(
        self,
        metaclass: str,
        arguments: Sequence[CallArgument],
        argument_types: Sequence[TypeRef | None],
        *,
        unpacked: bool,
    ) -> TypeRef | bool:
        """What calling a class of the metaclass `metaclass` gives: True for an instance of
        the class called, the one other class it names, or False where it makes a new class
        or cannot be told."""
        ...

    @property
    def hierarchy(self) -> "Hierarchy":
        """The lookup orders of the libraries' classes, worked out once per scan."""
        ...

    def shape_of(self, symbol: str) -> "ClassShape | None":
        """A library class's type parameters, written bases and members, or None."""
        ...


class ProjectNames(Protocol):
    """What the headers of the module's other files say (`project.py`)."""

    def member(self, module: str, name: str) -> tuple[Target, ...] | None:
        """Where `module.name` is defined, through the module files' re-exports."""
        ...

    def digest(self, module: str) -> str | None:
        """The digest of `module`'s header, for the reuse key."""
        ...

    def shape_of(self, symbol: str) -> "ClassShape | None":
        """A class another file of the module defines, by its header."""
        ...

    def names_a_value(self, module: str, name: str) -> bool:
        """Whether `module.name` is bound, where it is defined, to a value, not a class."""
        ...

    def returns(self, descriptor: str) -> TypeRef | None:
        """The return a `def` of another file of the module declares."""
        ...

    def field(self, field: str) -> TypeRef | None:
        """The type a class body of another file of the module declares for an attribute."""
        ...

    def names_an_alias(self, module: str, name: str) -> bool:
        """Whether that file binds `module.name` to a module-level type alias, whether or not
        the type it is can be named."""
        ...

    def alias(self, module: str, name: str) -> TypeRef | None:
        """The type `module.name` is, where that file binds it to a module-level type alias
        (`DbSession = Annotated[Session, ...]` is `Session`). None for any other name."""
        ...

    def binds_class(self, module: str, name: str) -> bool:
        """Whether that file binds `module.name` to its own class `name` alone, and to no other
        value on any statement: a call of it constructs that class."""
        ...

    def class_object(self, module: str, name: str) -> str | None:
        """The class `X` that `module.name` holds, where every write to it in that file gives
        a written `type[X]` (ruling R17). None for any other name."""
        ...


# The question a file asks for another file's header (`project.HEADER`).
_HEADER_QUESTION = "header"


@dataclass(frozen=True)
class ModuleIndex:
    """The module paths that exist in the scanned module's import roots, by file path
    alone (`app/api/items` for `app/api/items.py` or `app/api/items/__init__.py`), and
    the libraries a name of another module is looked up in."""

    modules: frozenset[str]
    libraries: LibraryNames | None = field(default=None, compare=False)
    # Every question asked of the index, as (`is_module` or `owns`, path), where the scan
    # records them: the answers are what one file's facts read from the module's other
    # files, so a later scan keeps the file's facts only where every answer is the same
    # (OI-325). None records nothing.
    asked: set[tuple[str, str]] | None = field(default=None, compare=False, repr=False)
    # The headers of the module's files (`project.py`), where the scan reads them.
    headers: ProjectNames | None = field(default=None, compare=False, repr=False)
    # How a library module's version tests are decided (`libraries.py`), by module path:
    # the Python it is read for and its names for `sys` (`VersionTests`), as that Python runs
    # only one arm (ruling R22). None for the module's own files, whose every branch is read.
    versions: "Callable[[str], VersionTests | None] | None" = field(
        default=None, compare=False, repr=False
    )
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
        if self.asked is not None:
            self.asked.add(("is_module", path))
        return path in self.modules

    def owns(self, path: str) -> bool:
        """Whether `path` or a package above it is in the scanned module."""
        if self.asked is not None:
            self.asked.add(("owns", path))
        return path in self._owned

    def answers(self, asked: Iterable[tuple[str, str]]) -> list[bool | str | None]:
        """What this index answers to each question, in order, recording none: for another
        file's header, its digest."""
        return [
            (None if self.headers is None else self.headers.digest(path))
            if question == _HEADER_QUESTION
            else path in (self.modules if question == "is_module" else self._owned)
            for question, path in asked
        ]


@dataclass(frozen=True)
class VersionTests:
    """What one library module's `if` on the Python version is decided against (ruling
    R22): the Python it is read for, the names the module's imports bind to the module
    `sys` (`import sys`, `import sys as _sys`), and those they bind to `sys.version_info`
    (`from sys import version_info`)."""

    python: tuple[int, int]
    modules: frozenset[str]
    values: frozenset[str]


def version_tests(tree: ast.Module, python: tuple[int, int]) -> VersionTests:
    """The module's names for `sys` and `sys.version_info`, by its imports, wherever they
    are written. A name some import binds to anything else as well is neither: what it is
    when the test runs depends on which import ran."""
    modules: set[str] = set()
    values: set[str] = set()
    other: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "sys":
                    modules.add(alias.asname or "sys")
                else:
                    other.add(alias.asname or alias.name.partition(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == "*":
                    continue
                bound = alias.asname or alias.name
                if node.module == "sys" and node.level == 0 and alias.name == "version_info":
                    values.add(bound)
                else:
                    other.add(bound)
    return VersionTests(python, frozenset(modules - other), frozenset(values - other))


def live_arm(node: ast.If, index: ModuleIndex, here: str) -> list[ast.stmt] | None:
    """The one arm of `node` that runs, where `node` tests the Python version and `index`
    reads the library module `here` for a known Python (`ModuleIndex.versions`); None where
    both arms are read."""
    tests = index.versions(here) if index.versions is not None else None
    decided = None if tests is None else version_test(node.test, tests)
    if decided is None:
        return None
    return node.body if decided else node.orelse


def live_statements(body: list[ast.stmt], index: ModuleIndex, here: str) -> list[ast.stmt]:
    """`body` with each `if` on the Python version that `live_arm` decides replaced by the
    statements of its live arm, at every depth; every other statement as it is."""
    found: list[ast.stmt] = []
    for node in body:
        live = live_arm(node, index, here) if isinstance(node, ast.If) else None
        if live is None:
            found.append(node)
        else:
            found.extend(live_statements(live, index, here))
    return found


def version_test(test: ast.expr, tests: VersionTests) -> bool | None:
    """`sys.version_info >= (3, 11)` and its other comparisons, read against the Python
    `tests` holds, `sys` and `version_info` being whatever names the module's imports bind
    them to; None for any other test."""
    if not (
        isinstance(test, ast.Compare)
        and len(test.ops) == 1
        and _names_version_info(test.left, tests)
        and isinstance(test.comparators[0], ast.Tuple)
    ):
        return None
    try:
        written = tuple(int(ast.literal_eval(part)) for part in test.comparators[0].elts)
    except (ValueError, TypeError):
        return None
    running = tests.python[: len(written)]
    operator = test.ops[0]
    if isinstance(operator, ast.GtE):
        return running >= written
    if isinstance(operator, ast.Gt):
        return running > written
    if isinstance(operator, ast.Lt):
        return running < written
    if isinstance(operator, ast.LtE):
        return running <= written
    return None


def _names_version_info(node: ast.expr, tests: VersionTests) -> bool:
    if isinstance(node, ast.Name):
        return node.id in tests.values
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "version_info"
        and isinstance(node.value, ast.Name)
        and node.value.id in tests.modules
    )


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
    them where the library's branches bind the name differently. A module file's header
    answers the same way for the module's own re-exports (`project.py`)."""
    if index.libraries is not None and not index.owns(target.module):
        found = index.libraries.member(target, name)
        if found is not None:
            return found
    if index.headers is not None and target.member is None and index.owns(target.module):
        # A file of the module re-exports or aliases the name: it is where it is defined, as a
        # library's is (round 1, item 3), read off that file's header.
        defined = index.headers.member(target.module, name)
        if defined is not None:
            return defined
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
            decided = live_arm(node, self._index, self._here)
            if decided is not None:
                names = self.run(decided, names)
            else:
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
        it, and so is a `NewType` of a class. A computed value, or a name of a value, stays a
        value."""
        value = node.value
        if self._owner is not None or value is None or len(targets) != 1:
            return None
        new_type = (
            isinstance(value, ast.Call)
            and len(value.args) == 2
            and self._is_typing(value.func, names, {"NewType"})
        )
        if isinstance(value, ast.Call) and new_type:
            # `UserId = NewType("UserId", int)`: at run time the name is a function that hands
            # its argument back, so every value of the type is an `int`, whose methods run (the
            # typing specification's NewType). As a type it names the type it wraps; called, it
            # is no construction (`new_type`).
            value = value.args[1]
        if not isinstance(targets[0], ast.Name) or not isinstance(value, ast.Name | ast.Attribute):
            return None
        found = resolve(value, names, self._index)
        if not found or any(
            target.kind not in (None, "class", "function", "new_type") for target in found
        ):
            return None
        if new_type:
            found = tuple(replace(target, kind="new_type") for target in found)
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
        if isinstance(value, ast.Subscript) and self._is_typing(value.value, names, {"Annotated"}):
            # `X = Annotated[T, ...]` (plan 2026-11-08 N2): the name holds the form, and as a
            # type it is `T`, as a `TypeAlias` is what it is written to be.
            return "type_alias", value
        if isinstance(value, ast.Call) and self._is_typing(
            value.func, names, _TYPE_VARIABLE_FACTORIES
        ):
            return "type_variable", None
        if isinstance(value, ast.Call) and self._is_typing(value.func, names, _CLASS_FACTORIES):
            return "new_class", None
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


def makes_a_class(target: Target) -> bool:
    """Whether calling `target` makes a new class: one of the typing specification's
    functional forms (`NamedTuple("Point", ...)`, `TypedDict("Movie", ...)`), never by the
    name alone."""
    return any(is_typing(target, name) for name in _CLASS_FACTORIES)


def is_typing(target: Target, name: str) -> bool:
    """Whether `target` is the typing specification's `name` (`typing.Optional`,
    `typing_extensions.Optional`)."""
    return target.module in _TYPING_MODULES and target.member == name
