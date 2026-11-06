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

The calls, values, returns and field writes of every body are read by `calls.py`; the
control-flow fields are read by a later part of this scanner.
"""

import ast
from dataclasses import dataclass, replace

from sextant.domain.closed_sets import ConstructKind
from sextant.domain.facts import (
    CallArgument,
    Fact,
    FieldWriteFact,
    Parameter,
    Signature,
    SymbolFact,
    TypeParameter,
)
from sextant.domain.symbols import PY_SIGNATURE, method_descriptor, names_a_type
from sextant.ingress.extract.python.calls import (
    CLINIT,
    INIT,
    BodyReader,
    FileContext,
    Scope,
    is_stub_body,
)
from sextant.ingress.extract.python.imports import Target, bind_names, is_typing
from sextant.ingress.extract.python.typing_rules import (
    ANY,
    BUILTINS,
    UNANNOTATED,
    TypeScope,
    type_parameter_name,
    type_ref,
    type_symbol,
    written_type,
)

_SETTER_SUFFIX = "="

_ENUM_BASES = frozenset({"Enum", "IntEnum", "StrEnum", "Flag", "IntFlag"})


@dataclass(frozen=True)
class FileFacts:
    """One file's facts, and what in it was not read: one line per class whose parents
    stop early, for the document's `partial_reason` (D00 §2)."""

    facts: list[Fact]
    not_read: list[str]


def file_facts(tree: ast.Module, context: FileContext, last_line: int) -> FileFacts:
    """Every structural fact of one parsed file, in source order."""
    writer = _Writer(context)
    writer.module(tree, last_line)
    return FileFacts(writer.facts, writer.not_read)


class _Writer(BodyReader):
    def __init__(self, context: FileContext) -> None:
        self._context = context
        self.facts: list[Fact] = []
        self.not_read: list[str] = []
        self._signatures = {}
        self._methods = {}
        self._bodies = {}

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
        self._collect_signatures(tree.body)
        self._statements(tree.body, Scope(owner, types, self._body(clinit)))

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

    def _class(self, node: ast.ClassDef, scope: Scope) -> None:
        """A class. One defined inside a function is named after the function that holds
        it (`outer$Local`), as kotlinc names a local class."""
        base = scope.class_path
        if scope.frame is not None:
            base = f"{base}.{scope.frame.prefix}" if base else scope.frame.prefix
        path = f"{base}.{node.name}" if base else node.name
        owner = type_symbol(Target(self._context.here, path))
        generic = scope.types.with_type_parameters(node.type_params)
        unread = len(self.not_read)
        written = self._parents(node, generic)
        kind = ConstructKind.CLASS
        if any(
            is_typing(target, "Protocol")
            for base_node in node.bases
            for target in scope.types.lookup(_unsubscripted(base_node))
        ):
            kind = ConstructKind.PROTOCOL
        elif any(
            target.module == "enum" and target.member in _ENUM_BASES
            for base_node in node.bases
            for target in scope.types.lookup(_unsubscripted(base_node))
        ):
            kind = ConstructKind.ENUM
        callees = self._decorators(node, scope)
        # The bases and the class keywords are read where the class is defined.
        for written_base in [*node.bases, *(keyword.value for keyword in node.keywords)]:
            self._value(written_base, scope)
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
        if scope.frame is not None:
            self._know_class(node, owner)
        body = Scope(
            owner,
            types,
            self._body(clinit),
            path,
            protocol=kind == ConstructKind.PROTOCOL,
            # `super()` starts at the first written parent; with none written it is
            # `object`, and where the parents were not read it is not known.
            super_owner=written[0]
            if written
            else (None if len(self.not_read) > unread else type_symbol(Target(BUILTINS, "object"))),
        )
        self._statements(node.body, body)
        self._bind_nested(
            node.name, self._apply(callees, CallArgument(kind="class", symbol=owner), scope), scope
        )

    def _parents(self, node: ast.ClassDef, types: TypeScope) -> list[str]:
        """The written parents' symbols, in written order, up to the first one this file
        cannot name as a class: a value (`Base = declarative_base()`), a call, or a name
        it does not bind. Nothing after that one is written, so no later parent moves
        into its place, and the document says the class's parents were not all read.
        `object` is the root every class has, and is not written, as the JVM's root is
        not (D00 §5 `superclass`)."""
        written: list[str] = []
        for position, base in enumerate(node.bases, 1):
            targets = types.lookup(_unsubscripted(base))
            if len(targets) != 1 or targets[0].kind in ("variable", "function"):
                self.not_read.append(
                    f"{node.name}: base {position} '{ast.unparse(base)}' is not a class name "
                    "this file can read; parents from here on are not read"
                )
                break
            if targets[0] != Target(BUILTINS, "object"):
                written.append(type_symbol(targets[0]))
        return written

    # -- module and class names ----------------------------------------------------------

    def _assignment(self, node: ast.Assign | ast.AnnAssign, scope: Scope) -> None:
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        value = None if node.value is None else self._value(node.value, scope)
        written = None
        if isinstance(node, ast.AnnAssign):
            written = written_type(node.annotation, scope.types)
        for target in targets:
            if value is not None and isinstance(target, ast.Attribute | ast.Subscript):
                self._store(target, value, scope)
                continue
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

    def _function(self, node: ast.FunctionDef | ast.AsyncFunctionDef, scope: Scope) -> None:
        nested = scope.frame is not None
        in_class = scope.class_path is not None and not nested
        decorators = [
            target for decorator in node.decorator_list for target in scope.types.lookup(decorator)
        ]
        is_static = any(t == Target(BUILTINS, "staticmethod") for t in decorators)
        stub = any(is_typing(t, "overload") for t in decorators)
        abstract = stub or any(t == Target("abc", "abstractmethod") for t in decorators)
        name = node.name
        kind = ConstructKind.METHOD
        if nested:
            name = self._nested_name(node, scope)
        elif in_class and name == "__init__":
            name, kind = INIT, ConstructKind.CONSTRUCTOR
        elif in_class and _is_setter(node):
            name = name + _SETTER_SUFFIX
        descriptor = method_descriptor(scope.owner, name, PY_SIGNATURE)
        callees = self._decorators(node, scope)
        # The defaults are read where the function is defined, before it is decorated.
        for default in [*node.args.defaults, *node.args.kw_defaults]:
            if default is not None:
                self._value(default, scope)
        if nested:
            self._method_known(descriptor, scope.owner, name)
            self._know((scope.owner, name), node, skip_first=False)
        applied = self._apply(
            callees, CallArgument(kind="lambda", symbol=descriptor, captures=0), scope
        )
        self._bind_nested(node.name, applied, scope)
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
        # A method's body reads the module's names, not its class body's.
        self._read_function(
            node,
            descriptor,
            scope,
            name=name,
            receiver_taken=receiver_taken,
            has_body=not stub and not ((abstract or scope.protocol) and is_stub_body(node.body)),
            types=replace(generic, class_names={}),
        )

    def _signature(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda,
        types: TypeScope,
        *,
        skip_first: bool,
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
            # A type variable erases to `Any`, as a JVM one erases to its bound. A type the
            # file does not name keeps its written text: it is not `Any`.
            unnamed = (
                argument.annotation is not None and type_ref(argument.annotation, types) is None
            )
            parameters.append(
                Parameter(
                    name=argument.arg,
                    type=found,
                    erased_symbol=found.symbol if names_a_type(found.symbol) or unnamed else ANY,
                )
            )
        returned = (
            node.returns if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) else None
        )
        returns = written_type(returned, types) if returned is not None else None
        return Signature(parameters=parameters, returns=returns)

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
