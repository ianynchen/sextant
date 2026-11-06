"""The structure of one Python file as D00 facts (spec 2026-11-06 §3a, ruling R4).

- A module (file) is a NAMESPACE for its classes and a TYPE for its own members:
  `app/api/items#create_item(<dis>).` is a module-level function, `app/api/items#app.` a
  module-level name, `app/api/items/OrderService#` a class and
  `app/api/items/Outer$Inner#` a nested class. A package `__init__.py` is the module of
  its package path (`app/api#`).
- A module body is the module type's `<clinit>`; a class body is the class's `<clinit>`.
  `__init__` is `<init>`.
- A name assigned in a module or class body is a static field, written there by
  `field_write`. It is not a `constant`: a Python global can be rebound.
- A property's getter and setter are two members, `x` and `x=`. An `@overload` stub is
  type information with no body (`abstract`). Two real definitions of one name are two
  facts with one symbol, one row each.
- A decorator is written as the calls it is, never as an `annotation` fact:
  `@router.get("/x")` on `def f` is the call `router.get("/x")`, then the call of its
  result with `f` as a function reference (`lambda`) argument.

Calls in function bodies, keyword arguments and control flow are read by later parts of
this scanner; this part writes the calls a module or class body makes to build its
names and to decorate its definitions.
"""

import ast
import builtins
from collections.abc import Iterable
from dataclasses import dataclass, field, replace

from sextant.domain.closed_sets import ConstructKind
from sextant.domain.facts import (
    CallArgument,
    CallSiteFact,
    CallTarget,
    Fact,
    FieldWriteFact,
    Parameter,
    Signature,
    SymbolFact,
    TypeParameter,
)
from sextant.domain.symbols import PY_SIGNATURE, method_descriptor, names_a_type
from sextant.ingress.extract.python.imports import (
    ModuleIndex,
    Target,
    bind_names,
    is_typing,
)
from sextant.ingress.extract.python.typing_rules import (
    ANY,
    BUILTINS,
    UNANNOTATED,
    TypeScope,
    type_parameter_name,
    type_symbol,
    written_type,
)

INIT = "<init>"
CLINIT = "<clinit>"
# The name a call of a VALUE has: Python calls `type(value).__call__`.
CALL = "__call__"
_SETTER_SUFFIX = "="

_ENUM_BASES = frozenset({"Enum", "IntEnum", "StrEnum", "Flag", "IntFlag"})


@dataclass(frozen=True)
class FileContext:
    """What one file's facts are written against."""

    here: str
    is_package: bool
    index: ModuleIndex
    # `sextant-python <manager> <package> <version> `, ending in the separator.
    prefix: str
    document_id: str


def file_facts(tree: ast.Module, context: FileContext, last_line: int) -> list[Fact]:
    """Every structural fact of one parsed file, in source order."""
    writer = _Writer(context)
    writer.module(tree, last_line)
    return writer.facts


@dataclass
class _Body:
    """One method's own counters: call ordinals and value ids are per method (D00 §5)."""

    caller: str
    ordinal: int = 0
    next_value: int = 0

    def value_id(self) -> int:
        found = self.next_value
        self.next_value += 1
        return found


@dataclass(frozen=True)
class _Callee:
    """What a call names, after its receiver was read."""

    target: CallTarget
    invoke_kind: str
    receiver: int | None = None
    receiver_field: str | None = None


@dataclass
class _Scope:
    """The body being read: the type it belongs to, its names, its `<clinit>`."""

    owner: str
    types: TypeScope
    body: _Body
    # The dotted class path (`Outer.Inner`), or None for the module body.
    class_path: str | None = None
    fields: set[str] = field(default_factory=set)


class _Writer:
    def __init__(self, context: FileContext) -> None:
        self._context = context
        self.facts: list[Fact] = []

    def _full(self, descriptor: str) -> str:
        return self._context.prefix + descriptor

    # -- types -------------------------------------------------------------------------

    def module(self, tree: ast.Module, last_line: int) -> None:
        here = self._context.here
        owner = f"{here}#"
        names = bind_names(
            tree.body, here, is_package=self._context.is_package, index=self._context.index
        )
        types = TypeScope(names=names, here=here, index=self._context.index)
        self._symbol(owner, ConstructKind.MODULE, None, 1, last_line)
        clinit = self._clinit(owner, 1, last_line)
        self._statements(tree.body, _Scope(owner, types, _Body(clinit)))

    def _clinit(self, owner: str, start: int, end: int) -> str:
        descriptor = method_descriptor(owner, CLINIT, PY_SIGNATURE)
        self._symbol(
            descriptor,
            ConstructKind.METHOD,
            owner,
            start,
            end,
            modifiers={"abstract": False, "static": True, "varargs": False},
        )
        return self._full(descriptor)

    def _class(self, node: ast.ClassDef, scope: _Scope) -> None:
        path = f"{scope.class_path}.{node.name}" if scope.class_path else node.name
        owner = type_symbol(Target(self._context.here, path))
        generic = scope.types.with_type_parameters(node.type_params)
        parents = [self._parent(base, generic) for base in node.bases]
        written = [parent for parent in parents if parent is not None]
        kind = ConstructKind.CLASS
        if any(
            is_typing(target, "Protocol")
            for base in node.bases
            for target in scope.types.lookup(_unsubscripted(base))
        ):
            kind = ConstructKind.PROTOCOL
        elif any(
            target.module == "enum" and target.member in _ENUM_BASES
            for base in node.bases
            for target in scope.types.lookup(_unsubscripted(base))
        ):
            kind = ConstructKind.ENUM
        self._decorate(node, CallArgument(kind="class", symbol=owner), scope)
        self.facts.append(
            SymbolFact(
                document_id=self._context.document_id,
                symbol=self._full(owner),
                construct_kind=kind,
                enclosing=self._full(scope.owner),
                line_start=node.lineno,
                line_end=node.end_lineno or node.lineno,
                superclass=self._full(written[0]) if written else None,
                interfaces=[self._full(parent) for parent in written[1:]],
                type_parameters=_type_parameters(node.type_params, generic),
            )
        )
        class_names = bind_names(
            node.body,
            self._context.here,
            is_package=self._context.is_package,
            index=self._context.index,
            owner=path,
        )
        types = replace(generic, class_names=class_names, self_type=owner)
        clinit = self._clinit(owner, node.lineno, node.end_lineno or node.lineno)
        self._statements(node.body, _Scope(owner, types, _Body(clinit), path))

    def _parent(self, base: ast.expr, types: TypeScope) -> str | None:
        """A written parent class's symbol. `object` is the root every class has, and is
        not written, as the JVM's root is not (D00 §5 `superclass`)."""
        targets = types.lookup(_unsubscripted(base))
        if len(targets) != 1 or targets[0].kind in ("variable", "function"):
            return None
        if targets[0] == Target(BUILTINS, "object"):
            return None
        return type_symbol(targets[0])

    # -- statements ----------------------------------------------------------------------

    def _statements(self, body: Iterable[ast.stmt], scope: _Scope) -> None:
        for node in body:
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                self._function(node, scope)
            elif isinstance(node, ast.ClassDef):
                self._class(node, scope)
            elif isinstance(node, ast.Assign | ast.AnnAssign):
                self._assignment(node, scope)
            elif isinstance(node, ast.If | ast.For | ast.AsyncFor | ast.While):
                self._statements([*node.body, *node.orelse], scope)
            elif isinstance(node, ast.Try | ast.TryStar):
                handlers = [statement for handler in node.handlers for statement in handler.body]
                self._statements([*node.body, *handlers, *node.orelse, *node.finalbody], scope)
            elif isinstance(node, ast.With | ast.AsyncWith):
                self._statements(node.body, scope)
            elif isinstance(node, ast.Match):
                self._statements([s for case in node.cases for s in case.body], scope)

    def _assignment(self, node: ast.Assign | ast.AnnAssign, scope: _Scope) -> None:
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        value = None if node.value is None else self._value(node.value, scope)
        written = None
        if isinstance(node, ast.AnnAssign):
            written = written_type(node.annotation, scope.types)
        for target in targets:
            named = target if isinstance(target, ast.Name) else None
            for name in _names(target):
                descriptor = f"{scope.owner}{name}."
                if descriptor not in scope.fields:
                    scope.fields.add(descriptor)
                    self._symbol(
                        descriptor,
                        ConstructKind.FIELD,
                        scope.owner,
                        node.lineno,
                        node.end_lineno or node.lineno,
                        signature=Signature(returns=written) if written is not None else None,
                        # A module-level name, or a class attribute given a value in
                        # the class body, belongs to the type. An annotation alone in a
                        # class body declares an instance attribute.
                        modifiers={"static": scope.class_path is None or value is not None},
                    )
                if value is None:
                    continue
                self.facts.append(
                    FieldWriteFact(
                        document_id=self._context.document_id,
                        field=descriptor,
                        # One name takes the value; a name inside an unpacking takes a
                        # part of it this scanner does not split.
                        value=value if named is not None else CallArgument(kind="unresolved"),
                        written_by=scope.body.caller,
                    )
                )

    # -- functions -----------------------------------------------------------------------

    def _function(self, node: ast.FunctionDef | ast.AsyncFunctionDef, scope: _Scope) -> None:
        in_class = scope.class_path is not None
        decorators = [
            target for decorator in node.decorator_list for target in scope.types.lookup(decorator)
        ]
        is_static = any(t == Target(BUILTINS, "staticmethod") for t in decorators)
        stub = any(is_typing(t, "overload") for t in decorators)
        abstract = stub or any(t == Target("abc", "abstractmethod") for t in decorators)
        name = node.name
        kind = ConstructKind.METHOD
        if in_class and name == "__init__":
            name, kind = INIT, ConstructKind.CONSTRUCTOR
        elif in_class and _is_setter(node):
            name = name + _SETTER_SUFFIX
        descriptor = method_descriptor(scope.owner, name, PY_SIGNATURE)
        self._decorate(node, CallArgument(kind="lambda", symbol=descriptor, captures=0), scope)
        receiver_taken = in_class and not is_static
        generic = scope.types.with_type_parameters(node.type_params)
        self._symbol(
            descriptor,
            kind,
            scope.owner,
            node.lineno,
            node.end_lineno or node.lineno,
            signature=self._signature(node, generic, skip_first=receiver_taken),
            type_parameters=_type_parameters(node.type_params, generic),
            modifiers={
                "abstract": abstract,
                "static": not receiver_taken,
                "varargs": node.args.vararg is not None,
            },
        )

    def _signature(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef, types: TypeScope, *, skip_first: bool
    ) -> Signature:
        written = node.args
        ordered = [*written.posonlyargs, *written.args]
        if skip_first and ordered:
            ordered = ordered[1:]
        ordered += [a for a in (written.vararg,) if a is not None]
        ordered += written.kwonlyargs
        ordered += [a for a in (written.kwarg,) if a is not None]
        parameters = []
        for argument in ordered:
            found = (
                UNANNOTATED
                if argument.annotation is None
                else written_type(argument.annotation, types)
            )
            parameters.append(
                Parameter(
                    name=argument.arg,
                    type=found,
                    erased_symbol=found.symbol if names_a_type(found.symbol) else ANY,
                )
            )
        returns = written_type(node.returns, types) if node.returns is not None else None
        return Signature(parameters=parameters, returns=returns)

    # -- decorators and calls ------------------------------------------------------------

    def _decorate(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef,
        decorated: CallArgument,
        scope: _Scope,
    ) -> None:
        """Python reads every decorator expression top to bottom, then applies them from
        the bottom up, each to the result of the one below it."""
        callees = [self._decorator(decorator, scope) for decorator in node.decorator_list]
        current = decorated
        for callee in reversed(callees):
            current = CallArgument(kind="unresolved", source=self._emit(callee, [current], scope))

    def _decorator(self, decorator: ast.expr, scope: _Scope) -> _Callee:
        if isinstance(decorator, ast.Name | ast.Attribute):
            return self._callee(decorator, scope)
        produced = self._value(decorator, scope)
        return self._value_call(produced, scope)

    def _value_call(self, produced: CallArgument, scope: _Scope) -> _Callee:
        receiver = produced.source if produced.source is not None else scope.body.value_id()
        return _Callee(
            CallTarget(owner=None, name=CALL, descriptor=PY_SIGNATURE), "virtual", receiver
        )

    def _callee(self, func: ast.expr, scope: _Scope) -> _Callee:
        """What `func(...)` calls. A name this file binds to a class is that class's
        `<init>`; to a function, or to a member of another module, a static call on its
        module type — whether that member is a class is in a file this scanner does not
        read, so the resolver decides. A call on a value names its receiver."""
        if isinstance(func, ast.Attribute):
            owners = scope.types.lookup(func.value) if _is_dotted(func.value) else ()
            if len(owners) == 1 and (owners[0].member is None or owners[0].kind == "class"):
                return _Callee(_target(type_symbol(owners[0]), func.attr), "static")
            if len(owners) == 1 and owners[0].kind in (None, "variable"):
                return _Callee(
                    CallTarget(owner=None, name=func.attr, descriptor=PY_SIGNATURE),
                    "virtual",
                    scope.body.value_id(),
                    _field_of(owners[0]),
                )
            produced = self._value(func.value, scope)
            receiver = produced.source if produced.source is not None else scope.body.value_id()
            return _Callee(
                CallTarget(owner=None, name=func.attr, descriptor=PY_SIGNATURE),
                "virtual",
                receiver,
            )
        targets = scope.types.lookup(func) if isinstance(func, ast.Name) else ()
        if len(targets) == 1:
            target = targets[0]
            if target.kind == "class" or _is_builtin_class(target):
                return _Callee(_target(type_symbol(target), INIT), "special")
            if target.kind == "variable":
                return _Callee(
                    CallTarget(owner=None, name=CALL, descriptor=PY_SIGNATURE),
                    "virtual",
                    scope.body.value_id(),
                    _field_of(target),
                )
            if target.member is not None and target.kind in (None, "function"):
                owner, name = _split(target)
                return _Callee(_target(owner, name), "static")
        return self._value_call(self._value(func, scope), scope)

    def _emit(self, callee: _Callee, arguments: list[CallArgument], scope: _Scope) -> int:
        result = scope.body.value_id()
        self.facts.append(
            CallSiteFact(
                document_id=self._context.document_id,
                caller=scope.body.caller,
                target=callee.target,
                invoke_kind=callee.invoke_kind,
                ordinal=scope.body.ordinal,
                receiver=callee.receiver,
                receiver_field=callee.receiver_field,
                result=result,
                arguments=arguments,
            )
        )
        scope.body.ordinal += 1
        return result

    def _value(self, node: ast.expr, scope: _Scope) -> CallArgument:
        """One value as D00 §5's argument grammar. A name bound to a closed list is a
        `merge` of what each binding names."""
        if isinstance(node, ast.Constant):
            return _constant(node.value)
        if isinstance(node, ast.Call):
            callee = self._callee(node.func, scope)
            arguments = [
                CallArgument(kind="unresolved")
                if isinstance(argument, ast.Starred)
                else self._value(argument, scope)
                for argument in node.args
            ]
            return CallArgument(kind="unresolved", source=self._emit(callee, arguments, scope))
        if _is_dotted(node):
            targets = scope.types.lookup(node)
            if len(targets) == 1:
                return _reference(targets[0])
            if targets:
                return CallArgument(
                    kind="merge", candidates=[_reference(target) for target in targets]
                )
        return CallArgument(kind="unresolved")

    def _symbol(
        self,
        descriptor: str,
        kind: ConstructKind,
        enclosing: str | None,
        start: int,
        end: int,
        *,
        signature: Signature | None = None,
        modifiers: dict[str, bool] | None = None,
        type_parameters: list[TypeParameter] | None = None,
    ) -> None:
        self.facts.append(
            SymbolFact(
                document_id=self._context.document_id,
                symbol=self._full(descriptor),
                construct_kind=kind,
                enclosing=None if enclosing is None else self._full(enclosing),
                signature=signature,
                line_start=start,
                line_end=end,
                modifiers=modifiers or {},
                type_parameters=type_parameters or [],
            )
        )


def _type_parameters(written: list[ast.type_param], scope: TypeScope) -> list[TypeParameter]:
    """PEP 695 type parameters as the JVM's `type_parameters` (D00 §5a): the name, and
    the written bound where there is one. A constraint list is not a bound."""
    found = []
    for parameter in written:
        bound = getattr(parameter, "bound", None)
        bounds = (
            [written_type(bound, scope)]
            if bound is not None and not isinstance(bound, ast.Tuple)
            else []
        )
        found.append(TypeParameter(name=type_parameter_name(parameter), bounds=bounds))
    return found


def _target(owner: str, name: str) -> CallTarget:
    return CallTarget(owner=owner, name=name, descriptor=PY_SIGNATURE)


def _split(target: Target) -> tuple[str, str]:
    """A member target as its owning type and its own name: `app/m#` and `x` for the
    module-level `x`, `app/m/C#` and `x` for the class attribute `C.x`."""
    assert target.member is not None
    path, _, name = target.member.rpartition(".")
    return type_symbol(Target(target.module, path or None)), name


def _field_of(target: Target) -> str | None:
    if target.member is None:
        return None
    owner, name = _split(target)
    return f"{owner}{name}."


def _reference(target: Target) -> CallArgument:
    """A name used as a value: a module or class is a `class` reference, a function a
    function reference (`lambda`), anything else a static `field`."""
    if target.member is None or target.kind == "class" or _is_builtin_class(target):
        return CallArgument(kind="class", symbol=type_symbol(target))
    owner, name = _split(target)
    if target.kind == "function" or (target.module == BUILTINS and callable(_builtin(name))):
        return CallArgument(
            kind="lambda", symbol=method_descriptor(owner, name, PY_SIGNATURE), captures=0
        )
    return CallArgument(kind="field", symbol=f"{owner}{name}.")


def _constant(value: object) -> CallArgument:
    if isinstance(value, bool):
        return CallArgument(kind="boolean", value=value)
    if isinstance(value, int):
        return CallArgument(kind="int", value=value)
    if isinstance(value, str):
        return CallArgument(kind="string", value=value)
    if value is None:
        return CallArgument(kind="null")
    return CallArgument(kind="unresolved")


def _builtin(name: str) -> object:
    return getattr(builtins, name, None)


def _is_builtin_class(target: Target) -> bool:
    return (
        target.module == BUILTINS
        and target.member is not None
        and isinstance(_builtin(target.member), type)
    )


def _is_dotted(node: ast.expr) -> bool:
    while isinstance(node, ast.Attribute):
        node = node.value
    return isinstance(node, ast.Name)


def _unsubscripted(node: ast.expr) -> ast.expr:
    return node.value if isinstance(node, ast.Subscript) else node


def _is_setter(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """`@x.setter` on `def x`: the setter of the property `x`, a member of its own."""
    return any(
        isinstance(decorator, ast.Attribute)
        and decorator.attr == "setter"
        and isinstance(decorator.value, ast.Name)
        and decorator.value.id == node.name
        for decorator in node.decorator_list
    )


def _names(target: ast.expr) -> list[str]:
    if isinstance(target, ast.Name):
        return [target.id]
    if isinstance(target, ast.Tuple | ast.List):
        return [name for element in target.elts for name in _names(element)]
    if isinstance(target, ast.Starred):
        return _names(target.value)
    return []
