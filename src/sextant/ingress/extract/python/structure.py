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
from dataclasses import dataclass, field, replace

from sextant.domain.closed_sets import ConstructKind
from sextant.domain.facts import (
    CallArgument,
    Fact,
    FieldWriteFact,
    Parameter,
    ParameterKind,
    ParentsUnread,
    Signature,
    SymbolFact,
    TypeParameter,
    TypeRef,
)
from sextant.domain.symbols import PY_SIGNATURE, method_descriptor, names_a_type
from sextant.ingress.extract.python.calls import (
    CLINIT,
    INIT,
    BodyReader,
    FileContext,
    ModuleType,
    ParameterValues,
    Scope,
    is_stub_body,
    own_return_type,
)
from sextant.ingress.extract.python.imports import (
    Binding,
    ModuleIndex,
    ProjectNames,
    Target,
    bind_names,
    holds_decorated_value,
    is_typing,
)
from sextant.ingress.extract.python.typing_rules import (
    ANY,
    BUILTINS,
    SELF,
    UNANNOTATED,
    ClassShape,
    Hierarchy,
    TypeScope,
    class_shape,
    is_class_variable,
    type_parameter_name,
    type_ref,
    type_symbol,
    wire_projected,
    written_type,
)

_SETTER_SUFFIX = "="

# Two words of the general reason list (`application/resolve/values.py` `_REASONS`).
# An ingress module cannot import that layer, so they are spelled here; a test holds
# them to the list.
_NOT_READABLE = "not_readable"
_EXTERNAL = "external"

_ENUM_BASES = frozenset({"Enum", "IntEnum", "StrEnum", "Flag", "IntFlag"})


@dataclass(frozen=True)
class FileFacts:
    """One file's facts, and what in it was not read: one line per class whose parents
    stop early, for the document's `partial_reason` (D00 §2)."""

    facts: list[Fact]
    not_read: list[str]
    # What the reading could not settle about the file as a whole, for the uncovered list.
    notes: list[str] = field(default_factory=list)


def file_facts(tree: ast.Module, context: FileContext, last_line: int) -> FileFacts:
    """Every structural fact of one parsed file, in source order.

    A module-level name's type is that of every value written to it in the file (design
    2026-11-06-reading-decorators §3b), and a value's type can rest on another name's
    (`module` is made by `cli.group()`). The first reading answers from the writes read
    so far, and is kept where every answer is the one all the writes give: a name
    written before it is read, the usual order. Else the file is read again from no
    types, each time with the types the reading before found, until a reading finds no
    new type for a name it asked about. A type is only ever added there (a write whose
    type is known stays known), so those readings end, at most one per name."""
    rebound = _rebound_names(tree)
    writer = _Writer(context, rebound, None)
    writer.module(tree, last_line)
    if writer.agrees(writer.module_types()):
        return FileFacts(writer.facts, writer.not_read)
    known: dict[str, ModuleType] = {}
    # Each reading that does not end adds a type to at least one name.
    limit = len(writer.written_names()) + 1
    for _ in range(limit):
        writer = _Writer(context, rebound, known)
        writer.module(tree, last_line)
        found = writer.module_types()
        if writer.agrees(found):
            return FileFacts(writer.facts, writer.not_read)
        known = found
    # A defect in the rule (it only ever adds a type): the file keeps a reading with no
    # module-level types at all, which claims nothing, and a note names it.
    writer = _Writer(context, rebound, {})
    writer.module(tree, last_line)
    note = (
        f"the types of its module-level names did not settle in {limit} readings, "
        "so none is written"
    )
    return FileFacts(writer.facts, writer.not_read, [note])


def class_shapes(
    body: list[ast.stmt], here: str, names: dict[str, Binding], types: TypeScope
) -> dict[str, ClassShape]:
    """The type parameters, written bases and members of each class the module body and
    its class bodies define, read before any body so a use above the class sees it. A name
    bound more than once (a class defined on two branches) is not one class: none."""
    found: dict[str, ClassShape] = {}
    seen: set[str] = set()
    pending: list[tuple[str | None, ast.ClassDef]] = [
        (None, node) for node in body if isinstance(node, ast.ClassDef)
    ]
    while pending:
        outer, node = pending.pop(0)
        path = f"{outer}.{node.name}" if outer else node.name
        symbol = type_symbol(Target(here, path))
        single = outer is not None or len(names.get(node.name, Binding(())).targets) == 1
        if symbol in seen or not single:
            found.pop(symbol, None)
            seen.add(symbol)
            continue
        seen.add(symbol)
        found[symbol] = class_shape(node, types, node.body)
        pending += [(path, inner) for inner in node.body if isinstance(inner, ast.ClassDef)]
    return found


def _rebound_names(tree: ast.Module) -> set[str]:
    """The module-level names some statement binds to a value this scanner does not read
    as a write: a loop or `with` target, an import, `del`, `:=`, an `except ... as`, a
    `match` capture, `+=`, or a `global` in a function. Such a name's
    writes are not all known, so it has no class."""
    rebound: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Global):
            rebound.update(node.names)
    for node in _module_level(tree.body):
        if isinstance(node, ast.Import | ast.ImportFrom):
            rebound.update(
                (alias.asname or alias.name).partition(".")[0]
                for alias in node.names
                if alias.name != "*"
            )
        elif isinstance(node, ast.For | ast.AsyncFor):
            rebound.update(_names(node.target))
        elif isinstance(node, ast.With | ast.AsyncWith):
            for item in node.items:
                if item.optional_vars is not None:
                    rebound.update(_names(item.optional_vars))
        elif isinstance(node, ast.Delete):
            for target in node.targets:
                rebound.update(_names(target))
        elif isinstance(node, ast.AugAssign | ast.NamedExpr):
            rebound.update(_names(node.target))
        elif isinstance(node, ast.ExceptHandler | ast.MatchAs | ast.MatchStar) and node.name:
            rebound.add(node.name)
        elif isinstance(node, ast.MatchMapping) and node.rest is not None:
            rebound.add(node.rest)
    return rebound


def _module_level(body: list[ast.stmt]) -> list[ast.AST]:
    """Every node of the module's own scope: its statements and expressions, not the
    bodies of the functions and classes it defines (a comprehension's `:=` binds here)."""
    found: list[ast.AST] = []
    pending: list[ast.AST] = list(body)
    while pending:
        node = pending.pop()
        found.append(node)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda):
            # Its decorators and defaults run here; its body does not.
            pending.extend(getattr(node, "decorator_list", []))
            pending.extend(d for d in [*node.args.defaults, *node.args.kw_defaults] if d)
            continue
        if isinstance(node, ast.ClassDef):
            pending.extend([*node.decorator_list, *node.bases, *node.keywords])
            continue
        pending.extend(ast.iter_child_nodes(node))
    return found


class _Writer(BodyReader):
    def __init__(
        self,
        context: FileContext,
        rebound: set[str],
        module_types: dict[str, ModuleType] | None,
    ) -> None:
        self._context = context
        self.facts: list[Fact] = []
        self.not_read: list[str] = []
        self._methods = {}
        self._bodies = {}
        self._rebound = rebound
        self._module_types = module_types
        self._module_writes = {}
        self.consulted = {}
        self._local_classes = {}
        self._hierarchy = Hierarchy(self._shape_or_none)
        self._own_returns = {}
        self._own_fields = {}

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
        self._local_classes = class_shapes(tree.body, here, names, types)
        self._own_returns, self._own_fields = declared_types(
            tree.body, here, types, is_package=self._context.is_package, index=self._context.index
        )
        libraries = self._context.index.libraries
        self._hierarchy = Hierarchy(
            self._shape_or_none,
            None if libraries is None else libraries.hierarchy,
            _ModuleClasses(self._local_classes, self._context.index.headers),
        )
        self._symbol(owner, ConstructKind.MODULE, None, 1, last_line)
        clinit = self._clinit(owner, 1, last_line)
        scope = Scope(owner, types, self._body(clinit))
        self._statements(tree.body, scope)
        self._positions(scope)

    def _generic_parameters(self, owner: str) -> list[TypeParameter]:
        """A class's type parameters where it declares them without PEP 695's list: its
        `Generic[...]` or `Protocol[...]` list, else the type variables of its written bases
        in order, by the typing specification (`class_shape`). Each by name: a variable
        declared by `TypeVar(...)` elsewhere has a bound this file does not read."""
        shape = self._local_classes.get(owner)
        return [] if shape is None else [TypeParameter(name=name) for name in shape.parameters]

    def _shape_or_none(self, symbol: str) -> ClassShape | None:
        found = self._local_classes.get(symbol)
        headers = self._context.index.headers
        if found is None and headers is not None:
            found = headers.shape_of(symbol)
        libraries = self._context.index.libraries
        if found is None and libraries is not None:
            found = libraries.shape_of(symbol)
        return found

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
        written, parents_unread = self._parents(node, generic)
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
        # Each written parent with its type arguments, where it has any (`RepositoryBase
        # [Product]`), as the JVM's generic supertype and interfaces (D00 §5a): what a class
        # of another file's type parameters are, read through this one.
        generic_bases: list[TypeRef | None] = []
        for written_base, parent in zip(node.bases, written, strict=False):
            typed = (
                type_ref(written_base, generic) if isinstance(written_base, ast.Subscript) else None
            )
            generic_bases.append(
                typed if typed is not None and typed.arguments and typed.symbol == parent else None
            )
        callees = self._decorators(node, scope)
        # The bases and the class keywords are read where the class is defined.
        for written_base in node.bases:
            self._type_form(written_base, scope)
        for keyword in node.keywords:
            self._value(keyword.value, scope)
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
                parents_unread=parents_unread,
                type_parameters=_type_parameters(node.type_params, generic)
                or self._generic_parameters(owner),
                supertype=wire_projected(generic_bases[0], generic)
                if generic_bases and generic_bases[0] is not None
                else None,
                generic_interfaces=[
                    wire_projected(base, generic) for base in generic_bases[1:] if base is not None
                ],
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
        self._positions(body)
        applied = self._apply(callees, CallArgument(kind="class", symbol=owner), scope)
        self._bind_nested(node.name, applied, scope)
        if scope.frame is None and scope.class_path is None:
            self._module_write(node.name, applied, scope)

    def _parents(
        self, node: ast.ClassDef, types: TypeScope
    ) -> tuple[list[str], ParentsUnread | None]:
        """The written parents' symbols, in written order, up to the first one this file
        cannot name as a class: a value (`Base = declarative_base()`), a call, or a name
        it does not bind. Nothing after that one is written, so no later parent moves
        into its place. The class then carries `parents_unread` (`not_readable` for a
        value, a call or two different bindings; `external` for a name no statement of
        the file binds, as a star import leaves it), and the document says the class's
        parents were not all read. `object` is the root every class has, and is not
        written, as the JVM's root is not (D00 §5 `superclass`)."""
        written: list[str] = []
        for position, base in enumerate(node.bases, 1):
            targets = types.lookup(_unsubscripted(base))
            if len(targets) != 1 or targets[0].kind in ("variable", "function"):
                text = ast.unparse(base)
                if not targets and isinstance(_unsubscripted(base), ast.Name | ast.Attribute):
                    reason = _EXTERNAL
                    detail = f"base {position} '{text}' is a name this file does not bind"
                elif len(targets) > 1:
                    reason = _NOT_READABLE
                    detail = f"base {position} '{text}' is bound two ways, so it names no one class"
                elif isinstance(_unsubscripted(base), ast.Call):
                    reason = _NOT_READABLE
                    detail = f"base {position} '{text}' is a call result, not a class name"
                else:
                    reason = _NOT_READABLE
                    detail = f"base {position} '{text}' is a value, not a class name"
                self.not_read.append(
                    f"{node.name}: base {position} '{text}' is not a class name "
                    "this file can read; parents from here on are not read"
                )
                return written, ParentsUnread(
                    reason=reason, detail=f"{detail}; parents from here on are not read"
                )
            if targets[0] != Target(BUILTINS, "object"):
                written.append(type_symbol(targets[0]))
        return written, None

    # -- module and class names ----------------------------------------------------------

    def _assignment(self, node: ast.Assign | ast.AnnAssign, scope: Scope) -> None:
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        value = None if node.value is None else self._value(node.value, scope)
        written = None
        instance = False
        if isinstance(node, ast.AnnAssign):
            written = written_type(node.annotation, scope.types)
            instance = not is_class_variable(node.annotation, scope.types)
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
                        signature=Signature(returns=wire_projected(written, scope.types))
                        if written is not None
                        else None,
                        # A module-level name belongs to the module. In a class body an
                        # annotated name not written `ClassVar` declares an instance
                        # variable, whatever its value (PEP 526); a name assigned with no
                        # annotation, or a `ClassVar`, belongs to the class.
                        modifiers={"static": scope.class_path is None or not instance},
                    )
                if value is None:
                    continue
                if scope.class_path is None:
                    self._module_write(
                        name, value if named is not None else CallArgument(kind="unresolved"), scope
                    )
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
        # A classmethod is bound to the class, not to an instance (D00 §5a `static`): `cls`
        # is taken by the receiver as `self` is, and a call through the class fills no `cls`.
        is_class_method = any(t == Target(BUILTINS, "classmethod") for t in decorators)
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
        # The defaults, then the annotations that are not a plain type, are read where the
        # function is defined, before it is decorated.
        values = self._parameter_values(node.args, scope)
        if nested:
            self._method_known(descriptor, scope.owner, name)
        applied = self._apply(
            callees, CallArgument(kind="lambda", symbol=descriptor, captures=0), scope
        )
        self._bind_nested(node.name, applied, scope)
        if not nested and holds_decorated_value(node, scope.types.lookup):
            # `f = dec(f)` (design 2026-11-06-reading-decorators §3e): the name is a field of
            # the module or the class, written from the outermost decorator's result.
            self._decorated_name(node, applied, scope)
        if not nested and not in_class:
            self._module_write(node.name, applied, scope)
        receiver_taken = in_class and not is_static
        generic = scope.types.with_type_parameters(node.type_params)
        self._symbol(
            descriptor,
            kind,
            scope.owner,
            node.lineno,
            node.end_lineno or node.lineno,
            signature=_wire_signature(
                self._signature(node, generic, skip_first=receiver_taken, values=values), generic
            ),
            type_parameters=_type_parameters(node.type_params, generic),
            modifiers={
                "abstract": abstract,
                "static": not receiver_taken or is_class_method,
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
            class_receiver=is_class_method,
            has_body=not stub and not ((abstract or scope.protocol) and is_stub_body(node.body)),
            types=replace(generic, class_names={}),
        )

    def _decorated_name(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef, applied: CallArgument, scope: Scope
    ) -> None:
        descriptor = f"{scope.owner}{node.name}."
        if descriptor not in scope.fields:
            scope.fields.add(descriptor)
            self._symbol(
                descriptor,
                ConstructKind.FIELD,
                scope.owner,
                node.lineno,
                node.end_lineno or node.lineno,
                modifiers={"static": True},
            )
        self.facts.append(
            FieldWriteFact(
                document_id=self._context.document_id,
                field=descriptor,
                value=applied,
                written_by=scope.body.caller,
            )
        )

    def _signature(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda,
        types: TypeScope,
        *,
        skip_first: bool,
        values: ParameterValues | None = None,
    ) -> Signature:
        written = node.args
        # Each parameter with how a call fills it (D00 §5a `kind`), in the order Python lists
        # them: `self` (or `cls`) taken by the receiver is not one.
        ordered: list[tuple[ast.arg, ParameterKind]] = [
            *((a, "positional_only") for a in written.posonlyargs),
            *((a, "positional") for a in written.args),
        ]
        if skip_first and ordered:
            ordered = ordered[1:]
        ordered += [(a, "var_positional") for a in (written.vararg,) if a is not None]
        ordered += [(a, "keyword_only") for a in written.kwonlyargs]
        ordered += [(a, "var_keyword") for a in (written.kwarg,) if a is not None]
        parameters = []
        defaults = {} if values is None else values.defaults
        annotated = {} if values is None else values.annotated
        for argument, kind in ordered:
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
                    kind=kind,
                    declares_default=argument.arg in defaults,
                    default=defaults.get(argument.arg),
                    annotation_value=annotated.get(argument.arg),
                )
            )
        returned = (
            node.returns if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) else None
        )
        # `Self` in a method's return is kept as written (D00 §5a): it is the class the call
        # was made through, which the resolver reads per path, never the defining class.
        read_as = replace(types, self_type=SELF) if types.self_type is not None else types
        returns = written_type(returned, read_as) if returned is not None else None
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


def header_types(
    tree: ast.Module, module: str, types: TypeScope, is_package: bool
) -> tuple[
    dict[str, ClassShape],
    dict[str, TypeRef],
    dict[str, TypeRef],
    dict[str, TypeRef],
    dict[str, tuple[Target, ...]],
]:
    """What another file's header says (`project.ProjectHeaders`): its class shapes, the
    returns its `def`s declare, the attributes its class bodies declare, the type each
    module-level type alias is and the function each module-level name is written from
    (`factory_calls`), read as this file's own are. An alias bound two ways, or whose
    type the file does not name, has none."""
    classes = class_shapes(tree.body, module, types.names, types)
    returns, fields = declared_types(
        tree.body, module, types, is_package=is_package, index=types.index
    )
    factories = factory_calls(tree, types)
    aliases: dict[str, TypeRef] = {}
    for name, binding in types.names.items():
        if len(binding.targets) != 1:
            continue
        (target,) = binding.targets
        if target.kind != "type_alias" or target.module != module or target.member != name:
            continue
        typed = type_ref(target.alias_of, types) if target.alias_of is not None else None
        if typed is not None:
            aliases[name] = typed
    return classes, returns, fields, aliases, factories


def factory_calls(tree: ast.Module, types: TypeScope) -> dict[str, tuple[Target, ...]]:
    """The function each module-level name is written from, where every write to it in the
    file is a call of a named function (`APIRouter = get_api_router_class(APIRoute)`), by
    name: the function's target, as the file binds it. What the call returns is read by
    `project.ProjectHeaders.class_object`, which may read another file's header (ruling
    R17). A name some statement binds in a way not read as a write (`_rebound_names`), that
    the file also binds as a function, a class or an import, or that a write gives any other
    value, has none: the resolver follows its writes."""
    rebound = _rebound_names(tree)
    written: dict[str, list[Target | None]] = {}
    for node in _module_level(tree.body):
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets, value = [node.target], node.value
        else:
            continue
        called = _called_function(value, types)
        for target in targets:
            for name in _names(target):
                written.setdefault(name, []).append(
                    called if isinstance(target, ast.Name) else None
                )
    found: dict[str, tuple[Target, ...]] = {}
    for name, writes in written.items():
        binding = types.names.get(name)
        if (
            name in rebound
            or binding is None
            or any(target.kind != "variable" for target in binding.targets)
            or any(write is None for write in writes)
        ):
            continue
        found[name] = tuple(dict.fromkeys(write for write in writes if write is not None))
    return found


def _called_function(value: ast.expr, types: TypeScope) -> Target | None:
    """The one function a call written `f(...)` names, as the file binds `f`; None for any
    other value."""
    if not isinstance(value, ast.Call) or not isinstance(value.func, ast.Name):
        return None
    binding = types.names.get(value.func.id)
    if binding is None or len(binding.targets) != 1:
        return None
    (target,) = binding.targets
    if target.kind not in (None, "function") or target.member is None or "." in target.member:
        return None
    return target


def declared_types(
    body: list[ast.stmt], here: str, types: TypeScope, *, is_package: bool, index: ModuleIndex
) -> tuple[dict[str, TypeRef], dict[str, TypeRef]]:
    """The return type each module-level function and each method of a class of this
    file declares, read where its annotation is read (`_function`), by bare descriptor:
    what a call of it declares it gives (`calls.own_return_type`). A name defined twice
    keeps one only where every definition declares the same; a decorated one has none.
    Beside them, the type each class body declares for an attribute (`client:
    HttpClient`, PEP 526), by field symbol, read the same way."""
    found: dict[str, TypeRef | None] = {}
    fields: dict[str, TypeRef | None] = {}
    pending: list[tuple[str | None, list[ast.stmt], TypeScope]] = [(None, body, types)]
    while pending:
        path, statements, scope = pending.pop(0)
        owner = type_symbol(Target(here, path))
        for node in statements:
            if isinstance(node, ast.ClassDef):
                inner = f"{path}.{node.name}" if path else node.name
                generic = scope.with_type_parameters(node.type_params)
                class_names = bind_names(
                    node.body,
                    here,
                    is_package=is_package,
                    index=index,
                    owner=inner,
                )
                nested = replace(
                    generic,
                    class_names=class_names,
                    self_type=type_symbol(Target(here, inner)),
                )
                pending.append((inner, node.body, nested))
                continue
            if (
                path is not None
                and isinstance(node, ast.AnnAssign)
                and isinstance(node.target, ast.Name)
            ):
                field = f"{owner}{node.target.id}."
                typed = own_return_type(node.annotation, scope)
                fields[field] = None if field in fields and fields[field] != typed else typed
                continue
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            # A decorated name holds what its decorators made (`f = dec(f)`), whose call
            # the function's own declaration does not describe.
            decorated = holds_decorated_value(node, scope.lookup)
            name = node.name
            if path is not None and name == "__init__":
                name = INIT
            elif path is not None and _is_setter(node):
                name = name + _SETTER_SUFFIX
            descriptor = method_descriptor(owner, name, PY_SIGNATURE)
            written = (
                None
                if node.returns is None or decorated
                else own_return_type(
                    node.returns,
                    replace(
                        scope, self_type=SELF if scope.self_type else None
                    ).with_type_parameters(node.type_params),
                )
            )
            if descriptor in found and found[descriptor] != written:
                written = None
            found[descriptor] = written
    return (
        {key: value for key, value in found.items() if value is not None},
        {key: value for key, value in fields.items() if value is not None},
    )


class _ModuleClasses:
    """The classes of the module, which a file's lookup orders are worked out for itself:
    this file's, and another file's by its header. Every other class is a library's."""

    def __init__(self, local: dict[str, ClassShape], headers: ProjectNames | None) -> None:
        self._local = local
        self._headers = headers

    def __contains__(self, symbol: object) -> bool:
        return isinstance(symbol, str) and (
            symbol in self._local
            or (self._headers is not None and self._headers.shape_of(symbol) is not None)
        )


def _type_parameters(written: list[ast.type_param], scope: TypeScope) -> list[TypeParameter]:
    """PEP 695 type parameters as the JVM's `type_parameters` (D00 §5a): the name, and
    the written bound where there is one. A constraint list is not a bound."""
    found = []
    for parameter in written:
        bound = getattr(parameter, "bound", None)
        bounds = (
            [wire_projected(written_type(bound, scope), scope)]
            if bound is not None and not isinstance(bound, ast.Tuple)
            else []
        )
        found.append(TypeParameter(name=type_parameter_name(parameter), bounds=bounds))
    return found


def _wire_signature(signature: Signature, types: TypeScope) -> Signature:
    """A signature as it is written to the facts: every type with its wire type (D00 §5b),
    read in the scope the signature was read in."""
    return signature.model_copy(
        update={
            "parameters": [
                p.model_copy(update={"type": wire_projected(p.type, types)})
                for p in signature.parameters
            ],
            "returns": None
            if signature.returns is None
            else wire_projected(signature.returns, types),
        }
    )


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
