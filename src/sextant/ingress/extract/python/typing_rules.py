"""Rule 1 (spec 2026-11-06 §3a): a type WRITTEN in the code, as a `TypeRef`.

The written name is bound through the file's own names (`imports.py`) and read as the
typing specification defines it:
- `Optional[X]` and `X | None` are `X` with `nullable`;
- a union is the type arguments of `typing/Union#`;
- `type[X]` is `X` itself, so a factory that returns a class reads as that class;
- `Annotated[X, ...]`, `ClassVar[X]`, `Final[X]`, `Required[X]`, `NotRequired[X]` and
  `ReadOnly[X]` are `X`;
- a type variable is its bare name, as a JVM type variable is (D00 §5a);
- `Self` is the enclosing class.

A name the file does not bind gives no type: it is never guessed. A name bound to a closed
list (`imports.py`) is the union of what each binding names. A name of a library is its
defining symbol where the scan's libraries say (`libraries.py`); elsewhere an imported name
keeps the symbol its import line gives.
"""

import ast
import builtins
from dataclasses import dataclass, field, replace

from sextant.domain.facts import TypeRef
from sextant.ingress.extract.python.imports import (
    Binding,
    ModuleIndex,
    Target,
    is_typing,
    resolve,
)

BUILTINS = "builtins"
UNION = "typing/Union#"
ANY = "typing/Any#"
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
