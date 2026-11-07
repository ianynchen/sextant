"""Rule 1 (spec 2026-11-06 §3a): a type WRITTEN in the code, as a `TypeRef`.

The written name is bound through the file's own names (`imports.py`) and read as the
typing specification defines it:
- `Optional[X]` and `X | None` are `X` with `nullable`;
- a union is the type arguments of `typing/Union#`;
- `type[X]` is `X` itself, so a factory that returns a class reads as that class;
- `Annotated[X, ...]`, `ClassVar[X]`, `Final[X]`, `Required[X]`, `NotRequired[X]` and
  `ReadOnly[X]` are `X`;
- a type variable is its bare name, as a JVM type variable is (D00 §5a);
- `Self` is the enclosing class;
- `List`, `Dict` and typing's other aliases of a builtin or `collections` class are that
  class (PEP 585), and `LiteralString` is `str`, whose methods it has.

A generic class's type parameters (`class C[T]`, `Generic[T]`, else the type variables of
its written bases in order) take the type arguments of a type written for it, and its
written bases map them on to theirs (`class Users(list[User])`): `substitute` and
`Hierarchy`, the typing specification's rules for generic classes, read by the scanner to
type what a library method returns (OI-324).

A name the file does not bind gives no type: it is never guessed. A name bound to a closed
list (`imports.py`) is the union of what each binding names. A name of a library is its
defining symbol where the scan's libraries say (`libraries.py`); elsewhere an imported name
keeps the symbol its import line gives.
"""

import ast
import builtins
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace

from sextant.domain.facts import TypeRef
from sextant.domain.symbols import ANY_TYPE, UNION_TYPE, names_a_type
from sextant.ingress.extract.python.imports import (
    Binding,
    ModuleIndex,
    Target,
    is_typing,
    resolve,
)

BUILTINS = "builtins"
UNION = UNION_TYPE
ANY = ANY_TYPE
NONE = "builtins/None#"
# The type a Python value has where no type is written: the typing specification's own
# rule for an unannotated parameter.
UNANNOTATED = TypeRef(symbol=ANY)

_RESOLVED = "resolved"
_BUILTIN_NAMES = frozenset(dir(builtins))
# Forms whose meaning is their one type argument.
_WRAPPERS = frozenset({"ClassVar", "Final", "Required", "NotRequired", "ReadOnly", "Type"})
# A bound on how deep a written type is followed, so an alias that names itself ends.
_DEPTH = 32
# typing's names for builtin and `collections` classes (PEP 585), and `LiteralString`,
# which has `str`'s methods: each is the class it names.
_ALIASES = {
    "List": "builtins/list#",
    "Dict": "builtins/dict#",
    "Set": "builtins/set#",
    "FrozenSet": "builtins/frozenset#",
    "Tuple": "builtins/tuple#",
    "DefaultDict": "collections/defaultdict#",
    "OrderedDict": "collections/OrderedDict#",
    "Counter": "collections/Counter#",
    "ChainMap": "collections/ChainMap#",
    "Deque": "collections/deque#",
    "LiteralString": "builtins/str#",
}
_TYPING_NAMES = frozenset({"typing", "typing_extensions"})
OBJECT = "builtins/object#"
TUPLE = "builtins/tuple#"
# The type variable `Self` is read as in a library's signature: the receiver's type fills it.
SELF = "Self"
# The forms whose type arguments are a class's own type parameters, and nothing else.
_PARAMETER_FORMS = ("Generic", "Protocol")


@dataclass(frozen=True)
class TypeScope:
    """What a written type is read against: the module's names, the enclosing class
    body's names (a method's annotations are read in its class body), the PEP 695 type
    parameters of the enclosing class and function, and the class `Self` stands for."""

    names: dict[str, Binding]
    here: str
    index: ModuleIndex = field(default_factory=lambda: ModuleIndex(frozenset()))
    class_names: dict[str, Binding] = field(default_factory=dict)
    self_type: str | None = None
    type_parameters: dict[str, Binding] = field(default_factory=dict)

    def with_type_parameters(self, written: list[ast.type_param]) -> "TypeScope":
        """This scope with `written` (`def f[S]`, `class C[T]`) bound as type
        variables, which hide every other binding of their names."""
        if not written:
            return self
        own = {
            name: Binding((Target(self.here, name, "type_variable"),))
            for name in map(type_parameter_name, written)
        }
        return replace(self, type_parameters={**self.type_parameters, **own})

    def lookup(self, node: ast.expr) -> tuple[Target, ...]:
        """The targets a written name or dotted name refers to: the type parameters
        first, then the class body, then the module, then the builtins."""
        for names in (self.type_parameters, self.class_names, self.names):
            found = resolve(node, names, self.index)
            if found:
                return found
        head = node
        while isinstance(head, ast.Attribute):
            head = head.value
        if isinstance(head, ast.Name) and head.id in _BUILTIN_NAMES:
            return resolve(node, {head.id: Binding((Target(BUILTINS, head.id),))}, self.index)
        return ()


def type_parameter_name(parameter: ast.type_param) -> str:
    """A PEP 695 type parameter's name; each of its three kinds has one."""
    assert isinstance(parameter, ast.TypeVar | ast.ParamSpec | ast.TypeVarTuple)
    return parameter.name


def type_ref(node: ast.expr, scope: TypeScope) -> TypeRef | None:
    """The written type `node` names, or None where the file does not say."""
    return _read(node, scope, _DEPTH)


def written_type(node: ast.expr, scope: TypeScope) -> TypeRef:
    """The type of a WRITTEN annotation. Where the file does not name it, the
    annotation's own text, bare: it names no type (`symbols.names_a_type`), and it is
    kept apart from `UNANNOTATED`, which is what a parameter with no annotation has."""
    found = type_ref(node, scope)
    if found is not None:
        return found
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return TypeRef(symbol=node.value.strip())
    return TypeRef(symbol=ast.unparse(node))


def type_symbol(target: Target) -> str:
    """The SCIP type descriptor of a target: `app/m#` for a module, `app/m/C#` for a
    class, `app/m/Outer$Inner#` for a nested class (D00 §1)."""
    if target.member is None:
        return f"{target.module}#"
    nested = target.member.replace(".", "$")
    return f"{target.module}/{nested}#" if target.module else f"{nested}#"


def _known(symbol: str, *, nullable: bool = False) -> TypeRef:
    return TypeRef(symbol=symbol, nullable=nullable, nullable_resolution=_RESOLVED)


def _read(node: ast.expr, scope: TypeScope, depth: int) -> TypeRef | None:
    if depth == 0:
        return None
    if isinstance(node, ast.Constant):
        if node.value is None:
            return _known(NONE, nullable=True)
        if isinstance(node.value, str):
            try:
                written = ast.parse(node.value.strip(), mode="eval").body
            except SyntaxError:
                return None
            return _read(written, scope, depth - 1)
        return None
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return _union([_read(part, scope, depth - 1) for part in _alternatives(node)])
    if isinstance(node, ast.Subscript):
        return _subscript(node, scope, depth)
    if isinstance(node, ast.Name | ast.Attribute):
        targets = scope.lookup(node)
        if len(targets) == 1:
            return _named(targets[0], scope, depth)
        return _union([_named(target, scope, depth) for target in targets]) if targets else None
    return None


def _named(target: Target, scope: TypeScope, depth: int) -> TypeRef | None:
    if target.kind == "type_variable" and target.member is not None:
        return TypeRef(symbol=target.member.rpartition(".")[2])
    if target.kind == "type_alias" and target.alias_of is not None:
        return _read(target.alias_of, scope, depth - 1)
    if target.kind in ("variable", "function"):
        return None
    if is_typing(target, "Any"):
        return TypeRef(symbol=ANY)
    if target.module in _TYPING_NAMES and target.member in _ALIASES:
        return _known(_ALIASES[target.member])
    if is_typing(target, "Self"):
        return _known(scope.self_type) if scope.self_type is not None else None
    if target.module == BUILTINS and target.member == "None":
        return _known(NONE, nullable=True)
    return _known(type_symbol(target))


def _subscript(node: ast.Subscript, scope: TypeScope, depth: int) -> TypeRef | None:
    targets = scope.lookup(node.value) if isinstance(node.value, ast.Name | ast.Attribute) else ()
    written = list(node.slice.elts) if isinstance(node.slice, ast.Tuple) else [node.slice]
    if len(targets) == 1:
        target = targets[0]
        if is_typing(target, "Optional"):
            return _union([_read(written[0], scope, depth - 1), _known(NONE, nullable=True)])
        if is_typing(target, "Union"):
            return _union([_read(part, scope, depth - 1) for part in written])
        if is_typing(target, "Annotated") or any(is_typing(target, w) for w in _WRAPPERS):
            return _read(written[0], scope, depth - 1)
        if target.module == BUILTINS and target.member == "type":
            return _read(written[0], scope, depth - 1)
        if is_typing(target, "Literal"):
            return _known(type_symbol(target))
    base = _read(node.value, scope, depth - 1)
    if base is None:
        return None
    arguments = [
        _read(part, scope, depth - 1)
        for part in written
        if not (isinstance(part, ast.Constant) and part.value is Ellipsis)
    ]
    # An argument the file does not name drops every argument, as an erased type does:
    # a partial list would put a known type at the wrong position.
    if any(argument is None for argument in arguments):
        return base
    return base.model_copy(update={"arguments": arguments})


def _alternatives(node: ast.expr) -> list[ast.expr]:
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return [*_alternatives(node.left), *_alternatives(node.right)]
    return [node]


def _union(members: list[TypeRef | None]) -> TypeRef | None:
    """One type for several: `None` among them is `nullable`, one other is itself, and
    several others are the arguments of `typing/Union#`. A member the file does not name
    makes the whole union unknown: a union missing a member would be a smaller claim
    presented as the whole."""
    if any(member is None for member in members):
        return None
    known = [member for member in members if member is not None]
    nullable = any(member.symbol == NONE for member in known)
    rest: list[TypeRef] = []
    for member in known:
        if member.symbol != NONE and member not in rest:
            rest.append(member)
    if not rest:
        return _known(NONE, nullable=True)
    if len(rest) == 1:
        return (
            rest[0].model_copy(update={"nullable": nullable, "nullable_resolution": _RESOLVED})
            if nullable
            else rest[0]
        )
    return TypeRef(symbol=UNION, arguments=rest, nullable=nullable, nullable_resolution=_RESOLVED)


# -- generic classes (OI-324) ---------------------------------------------------------------


@dataclass(frozen=True)
class ClassShape:
    """What a class's written definition says of its type parameters and methods:
    `parameters` in order, its `bases` written in those parameters (None where one is not
    read, so its lookup order is not known), the names its body defines, and which of
    them are methods."""

    parameters: tuple[str, ...]
    bases: tuple[TypeRef, ...] | None
    members: frozenset[str]
    methods: frozenset[str] = frozenset()


def class_shape(node: ast.ClassDef, scope: TypeScope, body: list[ast.stmt]) -> ClassShape:
    """A class's shape, by the typing specification: the PEP 695 parameters; else those
    `Generic[...]` or `Protocol[...]` lists; else every type variable of its written bases,
    in the order they appear. `Generic` and `Protocol` add no methods and are not bases
    here; a base this file does not name leaves the bases unread."""
    generic = scope.with_type_parameters(node.type_params)
    listed: list[str] | None = (
        [type_parameter_name(p) for p in node.type_params] if node.type_params else None
    )
    bases: list[TypeRef] | None = []
    for base in node.bases:
        head = base.value if isinstance(base, ast.Subscript) else base
        targets = generic.lookup(head) if isinstance(head, ast.Name | ast.Attribute) else ()
        if len(targets) == 1 and any(is_typing(targets[0], f) for f in _PARAMETER_FORMS):
            if listed is None and isinstance(base, ast.Subscript):
                written = base.slice.elts if isinstance(base.slice, ast.Tuple) else [base.slice]
                found = [type_ref(part, generic) for part in written]
                listed = [t.symbol for t in found if t is not None and _is_variable(t)]
            continue
        named = type_ref(base, generic)
        if named is None or not names_a_type(named.symbol) or bases is None:
            bases = None
            continue
        bases.append(named)
    if listed is None:
        listed = list(dict.fromkeys(_variables(bases or [])))
    methods = frozenset(
        n.name for n in body if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)
    )
    held = None if bases is None else tuple(bases)
    return ClassShape(tuple(listed), held, class_members(body), methods)


def class_members(body: list[ast.stmt]) -> frozenset[str]:
    """The names a class body defines: its methods and its assigned attributes."""
    names: set[str] = set()
    for node in body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            names.add(node.name)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
        elif isinstance(node, ast.Assign):
            names.update(t.id for t in node.targets if isinstance(t, ast.Name))
    return frozenset(names)


def _variables(types: list[TypeRef]) -> list[str]:
    found: list[str] = []
    for written in types:
        if _is_variable(written):
            found.append(written.symbol)
        found += _variables(list(written.arguments))
    return found


def _is_variable(written: TypeRef) -> bool:
    return not names_a_type(written.symbol)


def substitute(written: TypeRef, mapping: Mapping[str, TypeRef]) -> TypeRef | None:
    """`written` with each type variable replaced, at once, by the type `mapping` gives it.
    None where a type variable is left at the top or in a union: what it is depends on
    more than is known. An argument left unfilled drops every argument, as an erased type
    does (`_subscript`)."""
    if _is_variable(written):
        found = mapping.get(written.symbol)
        if found is None:
            return None
        return _union([found, _known(NONE, nullable=True)]) if written.nullable else found
    if written.symbol == UNION:
        members: list[TypeRef | None] = []
        for member in written.arguments:
            filled = substitute(member, mapping)
            if filled is not None and filled.symbol == UNION:
                members += filled.arguments
                if filled.nullable:
                    members.append(_known(NONE, nullable=True))
            else:
                members.append(filled)
        if written.nullable:
            members.append(_known(NONE, nullable=True))
        return _union(members)
    if not written.arguments:
        return written
    arguments = [substitute(argument, mapping) for argument in written.arguments]
    if any(argument is None for argument in arguments):
        return written.model_copy(update={"arguments": []})
    if all(new is old for new, old in zip(arguments, written.arguments, strict=True)):
        return written
    return written.model_copy(update={"arguments": arguments})


def parameter_mapping(instance: TypeRef, shape: ClassShape) -> dict[str, TypeRef]:
    """What a type written for a class gives each of its type parameters: its arguments by
    position. A tuple is the typing specification's own case: `tuple[A, B]` is a sequence of
    `A | B`. Arguments that do not match the parameters fill none (a bare `list` is
    `list[Any]`)."""
    arguments = list(instance.arguments)
    if len(arguments) == len(shape.parameters):
        return dict(zip(shape.parameters, arguments, strict=True))
    if instance.symbol == TUPLE and len(shape.parameters) == 1 and arguments:
        joined = _union(list(arguments))
        return {} if joined is None else {shape.parameters[0]: joined}
    return {}


class Hierarchy:
    """Each class's lookup order, C3 linearization as Python's own (the resolver's `c3`
    rule, spec §3b), each entry the class as the first one's type parameters fill it:
    `list` is `list[_T]`, `MutableSequence[_T]`, ..., `Iterable[_T]`, `object`. Worked out
    once per class (GUIDELINES §8.7); None where a class or a base is not read."""

    def __init__(
        self,
        shape_of: Callable[[str], ClassShape | None],
        shared: "Hierarchy | None" = None,
        own: frozenset[str] = frozenset(),
    ) -> None:
        self.shape_of = shape_of
        self._orders: dict[str, list[TypeRef] | None] = {}
        # Where a class not in `own` is ordered: the libraries' orders, worked out once for
        # the whole scan, not once per file.
        self._shared = shared
        self._own = own

    def order(self, symbol: str) -> list[TypeRef] | None:
        if self._shared is not None and symbol not in self._own:
            return self._shared.order(symbol)
        if symbol in self._orders:
            return self._orders[symbol]
        # A class being worked out names itself through its bases: no order.
        self._orders[symbol] = None
        self._orders[symbol] = self._linear(symbol)
        return self._orders[symbol]

    def _linear(self, symbol: str) -> list[TypeRef] | None:
        shape = self.shape_of(symbol)
        if shape is None or shape.bases is None:
            return None
        own = TypeRef(symbol=symbol, arguments=[TypeRef(symbol=p) for p in shape.parameters])
        bases = list(shape.bases) or ([] if symbol == OBJECT else [TypeRef(symbol=OBJECT)])
        sequences: list[list[TypeRef]] = []
        for base in bases:
            order = self.order(base.symbol)
            base_shape = self.shape_of(base.symbol)
            if order is None or base_shape is None:
                return None
            mapping = parameter_mapping(base, base_shape)
            entries = [substitute(entry, mapping) for entry in order]
            sequences.append([entry for entry in entries if entry is not None])
        sequences.append(bases)
        merged = _c3(sequences)
        return None if merged is None else [own, *merged]


def _c3(sequences: list[list[TypeRef]]) -> list[TypeRef] | None:
    """C3's merge, by class: None where the classes cannot be ordered (Python refuses such
    a class)."""
    pending = [list(sequence) for sequence in sequences if sequence]
    merged: list[TypeRef] = []
    while pending:
        for sequence in pending:
            head = sequence[0].symbol
            if not any(head in [t.symbol for t in other[1:]] for other in pending):
                break
        else:
            return None
        merged.append(sequence[0])
        pending = [[t for t in other if t.symbol != head] for other in pending]
        pending = [other for other in pending if other]
    return merged
