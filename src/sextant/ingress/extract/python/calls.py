"""Calls, values and returns of one Python body as D00 facts (spec 2026-11-06 §3a, "Flow
inside one function", "Calls whose owner is not known", "Decorators").

Every body is read: a module body and a class body (their `<clinit>`), a function, a nested
function and a `lambda`. Each call is a `call_site` with the same meaning the JVM extractor
gives it (D00 §5):
- `invoke_kind` is `static` for a function, `virtual` for a call on an object and `special`
  for a constructor (`<init>`) and for `super().m()`;
- a call on a value whose type this file does not write names its receiver's value id and
  leaves the owner to the resolver;
- `receiver` and `result` are value ids, one counter per method, and an argument a call
  produced carries that call's `result` as its `source`.

Values are D00 §5's argument grammar:
- an f-string, or `+` with a string literal, is `concat`: the template, with `{}` for each
  value, and a `dynamic` site `builtins/str#format` whose arguments fill the holes;
- a list or a tuple is `array`, a function is `lambda`, a parameter is `parameter`;
- `a if c else b` and `a or b` are `merge`;
- `await x` is the value of `x`;
- a constructed object is `instance`, whose `source` is the constructor's receiver.

Arguments are written as the call writes them (ruling R27): the positional ones in order, an
unpacked sequence among them marked `keyword: "*"`, then each keyword one with its name in
`keyword` (`**` for an unpacked mapping). The resolver binds them to parameters.

A local name holds the last value written to it on this path. Where two paths join with
different values, the name is a `merge` of them, as a JVM frame slot two branches wrote; it
is `unresolved` where a path does not set it or sets a value not followed. Every path that
reaches the join counts: a loop's `continue`s and `break`s, and the values an exception may
leave a `try` or a swallowing `with` with. Each call's place in its body's control flow (D00 §5
rule 9) is read by `flow.py`, which the statements below drive.

Every `return` is a `method_return`, plus the implicit `return None` where the end of the
body is reachable. A generator returns a generator object, so its one `method_return` is
`unresolved`. An `@overload` stub, and an abstract or `Protocol` method whose body is only
`...`, `pass` or a docstring, has no body and no `method_return` (spec §3b).

`self.x = …` and `C.x = …` are `field_write`s. A write to an attribute of another object is
not written: `field_write` has no key for its receiver.

A call's owner is the type the code writes for its receiver (design
2026-11-06-reading-decorators §3b), with `declared` evidence as every written type:
- a library call's result has the class its written signature returns (`libraries.py`), and
  calling a result written `Callable[[P, ...], R]` gives `R`, where a type variable in `R`
  takes the type of the argument that fills it (`click.group()` applied to `cli` is a
  `Group`). Where `R` is still not a class, the result has no type;
- a library method whose written return holds a type variable gives the type the receiver's
  type arguments, the class's own written bases (a class of this file among them) or the
  arguments fill it with (OI-324, `libraries.py`); a method a class of this file defines
  has a body, which the resolver follows, so its own signature is not read here;
- `for x in xs` is `xs.__iter__()`, then `__next__()` on the iterator before each pass,
  each a call site, as javac writes `iterator()` and `next()` for a for-each loop
  (`__aiter__` and `__anext__` for `async for`, whose step is awaited); a comprehension's
  `for` is the same. A tuple target takes a `tuple[A, B]` apart by position; `xs[i]` is
  `xs.__getitem__(i)`. Subscripting a class or a typing form makes a type, not an item
  read, and is not a call here;
- a module-level name has the type of the values written to it in its file: one class (or
  one callable) where every write gives it, read anywhere in the file. Two classes are a closed
  list, and a write whose type is not known (a loop, an import, `global`) gives none: the
  owner is then left to the resolver. A write from another file is not seen.
"""

import ast
import builtins
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from typing import Literal

from pydantic import PrivateAttr

from sextant.domain.closed_sets import ConstructKind
from sextant.domain.facts import (
    CallArgument,
    CallSiteFact,
    CallTarget,
    Fact,
    FieldWriteFact,
    MethodReturnFact,
    Signature,
    TypeRef,
)
from sextant.domain.symbols import (
    PY_SIGNATURE,
    member_name,
    method_descriptor,
    names_a_type,
    owner_of,
)
from sextant.ingress.extract.python.flow import Flow
from sextant.ingress.extract.python.imports import (
    Binding,
    CallableType,
    ModuleIndex,
    Target,
    bind_names,
    resolve,
)
from sextant.ingress.extract.python.typing_rules import (
    ANY,
    BUILTINS,
    TUPLE,
    UNION,
    ClassShape,
    Hierarchy,
    TypeScope,
    is_class_object,
    parameter_mapping,
    substitute,
    type_ref,
    type_symbol,
    union_of,
)

INIT = "<init>"
CLINIT = "<clinit>"
# The name a call of a VALUE has: Python calls `type(value).__call__`.
CALL = "__call__"
# What `with x as y` binds `y` to: `type(x).__enter__(x)`.
_ENTER = "__enter__"
_ASYNC_ENTER = "__aenter__"
# What `for` calls: `type(xs).__iter__(xs)`, then `__next__` on the iterator per pass; and
# what a subscript calls, `type(xs).__getitem__(xs, i)`.
_ITER = "__iter__"
_NEXT = "__next__"
_ASYNC_ITER = "__aiter__"
_ASYNC_NEXT = "__anext__"
_GETITEM = "__getitem__"
_SLICE = TypeRef(symbol="builtins/slice#")
# The type of a class object: `type[X]`, as the scanner holds a value written `type[X]` or
# `Type[X]` (a written type reads it as `X`, for a call through the class).
_TYPE_OF = "builtins/type#"
_NONE = "builtins/None#"
# The awaitables whose awaited value is their last type argument, as `async for` awaits
# what `__anext__` returns.
_AWAITABLES = frozenset({"typing/Awaitable#", "typing/Coroutine#"})
_TYPING_MODULES = frozenset({"typing", "typing_extensions"})
# The arguments the language reads as a type expression (ruling R37): `cast`'s type and
# `isinstance`'s or `issubclass`'s class, by position.
_TYPE_ARGUMENTS = {
    ("typing#", "cast"): 0,
    ("typing_extensions#", "cast"): 0,
    ("builtins#", "isinstance"): 1,
    ("builtins#", "issubclass"): 1,
}
# The `dynamic` site an f-string or a string `+` is: its template is a `str.format` text.
_STRING = "builtins/str#"
_FORMAT = "format"
_HOLE = "{}"
# A keyword argument unpacked from a mapping (`f(**options)`): its names are not written.
_UNPACKED = "**"
_UNPACKED_POSITIONAL = "*"
# The name prefix javac gives a lambda body in a static initializer and in a constructor.
_PREFIXES = {CLINIT: "static", INIT: "new"}

# The class a literal or a comprehension builds (OI-324 part 2).
_LITERAL_CLASSES: dict[type[ast.expr], str] = {
    ast.List: "builtins/list#",
    ast.Tuple: TUPLE,
    ast.Set: "builtins/set#",
    ast.Dict: "builtins/dict#",
}
_COMPREHENSION_CLASSES: dict[type[ast.expr], str] = {
    ast.ListComp: "builtins/list#",
    ast.SetComp: "builtins/set#",
    ast.DictComp: "builtins/dict#",
}

_UNKNOWN = CallArgument(kind="unresolved")
# The receiver of a method (`self`, `cls`). It is never a parameter (D00 §5 numbering) and
# reads as `unresolved` where it is used as a value; only its identity is tested.
_SELF = CallArgument(kind="unresolved")


class _Part(CallArgument):
    """A value the scanner knows the type of though no call produced it: a part of a
    tuple taken apart by position (`for k, v in d.items()`). It is `unresolved` in every
    fact; its type is the scanner's own, for the owner of a call on it."""

    _typed: TypeRef | None = PrivateAttr(default=None)


def _is_part(value: CallArgument) -> bool:
    """Whether `value` is an `unresolved` value only the scanner knows the type of: it folds
    as unknown where paths give different ones. A typed `array` keeps its own fact."""
    return isinstance(value, _Part) and value.kind == "unresolved"


def _part(typed: TypeRef) -> CallArgument:
    found = _Part(kind="unresolved")
    found._typed = typed
    return found


# A literal a local holds that the code it is handed to can change: read once as written.
_MUTABLE = (ast.List, ast.Dict, ast.Set, ast.ListComp, ast.DictComp, ast.SetComp)
_NESTED_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)
_COMPREHENSIONS = (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)


@dataclass(frozen=True)
class FileContext:
    """What one file's facts are written against."""

    here: str
    is_package: bool
    index: ModuleIndex
    # `sextant-python <manager> <package> <version> `, ending in the separator.
    prefix: str
    document_id: str


@dataclass
class Body:
    """One method's own counters: call ordinals, value ids, return ordinals and lambda
    numbers are per method (D00 §5)."""

    caller: str
    ordinal: int = 0
    next_value: int = 0
    returns: int = 0
    lambdas: int = 0
    # The type a library call's result is, by the library's written signature
    # (`libraries.py`), keyed by the call's `result` value id, and the type a library
    # class's constructor makes, keyed by its receiver's.
    returned: dict[int, TypeRef] = field(default_factory=dict)
    # The callable a library call's result is (`Callable[[P, ...], R]`), keyed the same way.
    callables: dict[int, CallableType] = field(default_factory=dict)
    # The type a call of a function or method of this file DECLARES it returns, keyed by the
    # call's `result`: no owner is written from it for a call on the result, since the body's
    # returns, which the resolver follows, are what runs; it types only what the scanner
    # reads off the result through a library's signature (an element, a part, an entered
    # value), which nothing else can answer.
    declared: dict[int, TypeRef] = field(default_factory=dict)

    def value_id(self) -> int:
        found = self.next_value
        self.next_value += 1
        return found


@dataclass(frozen=True)
class Callee:
    """What a call names, after its receiver was read."""

    target: CallTarget
    invoke_kind: str
    receiver: int | None = None
    receiver_parameter: int | None = None
    receiver_field: str | None = None
    receiver_field_kind: Literal["instance"] | None = None
    # The whole type written for the receiver, type arguments and all, where one is.
    typed: TypeRef | None = None
    # `typed` is what a function of this file declares it returns (`Body.declared`), not
    # the receiver's own written type: it gives the call no owner.
    hinted: bool = False


@dataclass
class Frame:
    """The names of one function body while it is read."""

    values: dict[str, CallArgument]
    local_names: set[str]
    # The type a written annotation gives a parameter or a local: a class, or a union.
    declared: dict[str, TypeRef]
    imported: dict[str, tuple[Target, ...]]
    global_names: frozenset[str]
    # The name a nested function or a lambda of this body starts with.
    prefix: str
    enclosing: "Frame | None"
    generator: bool
    self_name: str | None = None
    # The names that hold a list literal no read has handed out yet.
    mutable: set[str] = field(default_factory=set)
    # What the body's imports bind, branches read as at module level.
    bindings: dict[str, Binding] = field(default_factory=dict)
    # Per loop being read, innermost last: the names at each `break` and each `continue`.
    jumps: list["LoopJumps"] = field(default_factory=list)
    # Per protected block being read (a `try`, a `with`), innermost last: every value each
    # name was given in it, which an exception may leave the block with.
    writes: list[dict[str, list[CallArgument]]] = field(default_factory=list)
    # The names a nested function declares `nonlocal` and writes (`_rebound_nonlocal`).
    rebound: frozenset[str] = frozenset()
    # The receiver is the class the method was called through (`cls`), not an instance.
    class_receiver: bool = False


@dataclass
class LoopJumps:
    """The names where a loop's `break`s and `continue`s leave from."""

    breaks: list[dict[str, CallArgument]] = field(default_factory=list)
    continues: list[dict[str, CallArgument]] = field(default_factory=list)


@dataclass
class Scope:
    """The body being read: the type it belongs to, its names and its counters."""

    owner: str
    types: TypeScope
    body: Body
    # The dotted class path (`Outer.Inner`), or None outside a class.
    class_path: str | None = None
    fields: set[str] = field(default_factory=set)
    # Set for a function body; None for a module or a class body.
    frame: Frame | None = None
    protocol: bool = False
    # The first written parent of the class, where `super()` starts: `builtins/object#`
    # where none is written, None where the first parent is not a class name.
    super_owner: str | None = None
    # This reading of the body's control flow (one per body, D00 §5 rule 9).
    flow: Flow = field(default_factory=Flow)


class BodyReader:
    """Reads the statements and expressions of every body of one file. The declarations
    (symbols, signatures, class parents) are written by the subclass."""

    _context: FileContext
    facts: list[Fact]
    # A nested function's or a lambda's bare descriptor, to its owner and name.
    _methods: dict[str, tuple[str, str]]
    # One counter set per method symbol: a name defined twice is one method with two
    # bodies, whose call ordinals, value ids and returns continue across both.
    _bodies: dict[str, Body]
    # The type of each module-level name, a class or a callable, by every write to it in
    # this file, as the previous reading of the file found them (`structure.file_facts`).
    # None on a first reading, which answers from the writes read so far and is kept only
    # where every answer it gave is the one all the file's writes give.
    _module_types: dict[str, str | CallableType] | None
    # The module-level names some statement binds to a value that is not read as a write
    # (a loop, an import, `global`): their writes are not all known, so they have no type.
    _rebound: set[str]
    # Each module-level name's writes in this reading: the type of each value, None where
    # it is not known.
    _module_writes: dict[str, list[str | CallableType | None]]
    # Each module-level name this reading asked about, with every answer it gave.
    consulted: dict[str, list[str | CallableType | None]]
    # The type parameters, written bases and members of each class this file defines, and
    # the lookup orders they and the libraries' classes give (`typing_rules.Hierarchy`).
    _local_classes: dict[str, ClassShape]
    _hierarchy: Hierarchy
    # The return type each function and method of this file declares, by bare descriptor,
    # type variables kept (`own_return_type`); a name defined twice with two different
    # declared returns has none.
    _own_returns: dict[str, TypeRef]

    def _body(self, caller: str) -> Body:
        return self._bodies.setdefault(caller, Body(caller))

    # -- declarations, written by the subclass ----------------------------------------

    def _function(self, node: ast.FunctionDef | ast.AsyncFunctionDef, scope: Scope) -> None:
        raise NotImplementedError

    def _class(self, node: ast.ClassDef, scope: Scope) -> None:
        raise NotImplementedError

    def _assignment(self, node: ast.Assign | ast.AnnAssign, scope: Scope) -> None:
        raise NotImplementedError

    def _full(self, descriptor: str) -> str:
        raise NotImplementedError

    def _signature(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda,
        types: TypeScope,
        *,
        skip_first: bool,
    ) -> Signature:
        raise NotImplementedError

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
    ) -> None:
        raise NotImplementedError

    # -- function bodies ---------------------------------------------------------------

    def _read_function(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        descriptor: str,
        scope: Scope,
        *,
        name: str,
        receiver_taken: bool,
        has_body: bool,
        types: TypeScope,
        class_receiver: bool = False,
    ) -> None:
        """A function's calls, returns and field writes, in its own method. `class_receiver`:
        the receiver is the class (a `@classmethod`'s `cls`), not an instance."""
        if not has_body:
            return
        frame = self._frame(node.args, node.body, scope, types, name, receiver_taken)
        frame.class_receiver = class_receiver
        inner = Scope(
            owner=scope.owner,
            types=types,
            body=self._body(self._full(descriptor)),
            class_path=scope.class_path,
            frame=frame,
            super_owner=scope.super_owner if receiver_taken else None,
        )
        self._statements(node.body, inner)
        if frame.generator:
            self._return(_UNKNOWN, inner)
        elif _falls_through(node.body):
            self._return(CallArgument(kind="null"), inner)
        self._positions(inner)

    def _positions(self, scope: Scope) -> None:
        """Each call of the body read, with its place in the body's control flow."""
        for index, fields in scope.flow.positions():
            self.facts[index] = self.facts[index].model_copy(update=fields)

    def _frame(
        self,
        written: ast.arguments,
        body: list[ast.stmt],
        scope: Scope,
        types: TypeScope,
        name: str,
        receiver_taken: bool,
    ) -> Frame:
        ordered = [*written.posonlyargs, *written.args]
        self_name = ordered[0].arg if receiver_taken and ordered else None
        if self_name is not None:
            ordered = ordered[1:]
        ordered += [a for a in (written.vararg,) if a is not None]
        ordered += written.kwonlyargs
        ordered += [a for a in (written.kwarg,) if a is not None]
        values = {a.arg: CallArgument(kind="parameter", value=i) for i, a in enumerate(ordered)}
        declared = {
            a.arg: written
            for a in ordered
            if a.annotation is not None
            for written in (_declared_type(a.annotation, types),)
            if written is not None
        }
        own = list(_own_nodes(body))
        for node in own:
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                annotated = _declared_type(node.annotation, types)
                if annotated is not None:
                    declared[node.target.id] = annotated
        global_names = {n for node in own if isinstance(node, ast.Global) for n in node.names}
        outer = {n for node in own if isinstance(node, ast.Nonlocal) for n in node.names}
        local_names = (_assigned(own) | set(values)) - global_names - outer
        rebound = _rebound_nonlocal(body) & local_names
        for shared in rebound & set(values):
            values[shared] = _UNKNOWN
        if self_name is not None:
            values[self_name] = _SELF
            local_names.add(self_name)
        return Frame(
            values=values,
            local_names=local_names,
            declared=declared,
            imported={},
            global_names=frozenset(global_names),
            prefix=_PREFIXES.get(name, name),
            enclosing=scope.frame,
            generator=any(isinstance(node, ast.Yield | ast.YieldFrom) for node in own),
            self_name=self_name,
            bindings=self._import_bindings(body, own),
            rebound=frozenset(rebound),
        )

    def _import_bindings(self, body: list[ast.stmt], own: list[ast.AST]) -> dict[str, Binding]:
        if not any(isinstance(node, ast.Import | ast.ImportFrom) for node in own):
            return {}
        context = self._context
        return bind_names(body, context.here, is_package=context.is_package, index=context.index)

    def _nested_name(self, node: ast.FunctionDef | ast.AsyncFunctionDef, scope: Scope) -> str:
        """A function defined inside a function is a method of the same owner, named
        after the function that holds it (`outer$inner`), as kotlinc names a local
        function."""
        assert scope.frame is not None
        return f"{scope.frame.prefix}${node.name}"

    def _bind_nested(self, name: str, value: CallArgument, scope: Scope) -> None:
        """A `def` or `class` inside a function binds its name there."""
        if scope.frame is not None:
            self._store(ast.Name(id=name, ctx=ast.Store()), value, scope)

    def _method_known(self, descriptor: str, owner: str, name: str) -> None:
        self._methods[descriptor] = (owner, name)

    def _return(self, value: CallArgument, scope: Scope) -> None:
        self.facts.append(
            MethodReturnFact(
                document_id=self._context.document_id,
                method=scope.body.caller,
                ordinal=scope.body.returns,
                value=value,
            )
        )
        scope.body.returns += 1

    # -- statements --------------------------------------------------------------------

    def _statements(self, body: Iterable[ast.stmt], scope: Scope) -> None:
        for node in body:
            self._statement(node, scope)

    def _statement(self, node: ast.stmt, scope: Scope) -> None:
        frame = scope.frame
        if not _raises_nothing(node):
            scope.flow.statement()
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            self._function(node, scope)
        elif isinstance(node, ast.ClassDef):
            self._class(node, scope)
        elif isinstance(node, ast.Assign | ast.AnnAssign):
            if frame is None:
                self._assignment(node, scope)
            elif node.value is not None:
                value = self._value(node.value, scope)
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    self._store(target, value, scope)
                    if isinstance(node.value, _MUTABLE) and isinstance(target, ast.Name):
                        frame.mutable.add(target.id)
            if _only_a_call(node):
                scope.flow.quiet()
        elif isinstance(node, ast.AugAssign):
            self._augmented(node, scope)
        elif isinstance(node, ast.Expr):
            self._value(node.value, scope)
            if _only_a_call(node):
                scope.flow.quiet()
        elif isinstance(node, ast.Return):
            value = (
                CallArgument(kind="null") if node.value is None else self._value(node.value, scope)
            )
            if frame is not None and not frame.generator:
                self._return(value, scope)
            if _only_a_call(node):
                scope.flow.quiet()
            scope.flow.jump("return")
        elif isinstance(node, ast.Break | ast.Continue):
            if frame is not None and frame.jumps and scope.flow.here() is not None:
                jumps = frame.jumps[-1]
                taken = jumps.breaks if isinstance(node, ast.Break) else jumps.continues
                taken.append(dict(frame.values))
            scope.flow.jump("break" if isinstance(node, ast.Break) else "continue")
        elif isinstance(node, ast.If):
            self._value(node.test, scope)
            self._branches([node.body, node.orelse], scope)
        elif isinstance(node, ast.For | ast.AsyncFor):
            asynchronous = isinstance(node, ast.AsyncFor)
            iterator = self._iterate(node.iter, scope, asynchronous=asynchronous)
            self._loop(
                node.body,
                node.orelse,
                scope,
                target=node.target,
                iterator=iterator,
                asynchronous=asynchronous,
            )
        elif isinstance(node, ast.While):
            self._loop(node.body, node.orelse, scope, test=node.test)
        elif isinstance(node, ast.With | ast.AsyncWith):
            enter = _ASYNC_ENTER if isinstance(node, ast.AsyncWith) else _ENTER
            managers = []
            before = self._protect(scope)
            for item in node.items:
                manager = self._value(item.context_expr, scope)
                entered = self._invoke(self._on_value(manager, enter, scope), [], scope)
                if item.optional_vars is not None:
                    self._store(item.optional_vars, entered, scope)
                managers.append(scope.flow.with_block())
            self._statements(node.body, scope)
            # A manager may swallow what the block raised, and the code after the block
            # then runs with any value the block gave a name before it raised.
            swallowed = self._raised(before, scope)
            for exit_point in reversed(managers):
                scope.flow.with_end(exit_point)
            if frame is not None and swallowed is not None:
                ended = [frame.values] if scope.flow.here() is not None else []
                frame.values = _join([swallowed, *ended])
        elif isinstance(node, ast.Try | ast.TryStar):
            self._try(node, scope)
        elif isinstance(node, ast.Match):
            subject = self._value(node.subject, scope)
            # A case's guard runs where its pattern matched; where the pattern or the guard
            # fails, the next case is tried. The names a pattern captures are written where
            # it matched, so its guard and its body read them.
            flow = scope.flow
            starts: list[int | None] = []
            captures = [_captures(case.pattern, subject) for case in node.cases]
            untried = flow.here()
            for case, captured in zip(node.cases, captures, strict=True):
                flow.at(untried)
                if case.guard is not None:
                    held = None if frame is None else dict(frame.values)
                    self._capture(captured, scope)
                    self._value(case.guard, scope)
                    if frame is not None and held is not None:
                        frame.values = held
                starts.append(flow.here())
                irrefutable = isinstance(case.pattern, ast.MatchAs) and case.pattern.pattern is None
                untried = flow.join(
                    [
                        None if irrefutable else untried,
                        flow.here() if case.guard is not None else None,
                    ]
                )
            self._branches(
                [case.body for case in node.cases] + [[]],
                scope,
                [*starts, untried],
                [*captures, []],
            )
        elif isinstance(node, ast.Raise):
            for part in (node.exc, node.cause):
                if part is not None:
                    self._value(part, scope)
            scope.flow.raises()
        elif isinstance(node, ast.Assert):
            # `python -O` drops it; else a false test raises.
            skipped = scope.flow.here()
            self._value(node.test, scope)
            passed = scope.flow.here()
            if node.msg is not None:
                self._value(node.msg, scope)
            scope.flow.raises()
            scope.flow.join([skipped, passed])
        elif isinstance(node, ast.Delete):
            for target in node.targets:
                self._store(target, _UNKNOWN, scope)
        elif isinstance(node, ast.Import | ast.ImportFrom):
            self._import(node, scope)

    def _augmented(self, node: ast.AugAssign, scope: Scope) -> None:
        """`x += v` is `x = x + v`, with the target's object read once. A module or class
        name is written to its static field, as an assignment there is."""
        loaded = _as_load(node.target)
        value = self._value(ast.BinOp(left=loaded, op=node.op, right=node.value), scope)
        if scope.frame is None and isinstance(node.target, ast.Name):
            self._write_field(f"{scope.owner}{node.target.id}.", value, scope)
        else:
            self._store(node.target, value, scope, evaluate=False)

    def _import(self, node: ast.Import | ast.ImportFrom, scope: Scope) -> None:
        """An import inside a function binds a local name. A module-level name that
        branches bind to several things (`try: import ujson as json` / `except
        ImportError: import json`) is read as a static field, one write per binding, so a
        call on it names the field as its receiver and the resolver follows each write."""
        context = self._context
        bound = bind_names([node], context.here, is_package=context.is_package, index=context.index)
        if scope.frame is not None:
            for name, binding in bound.items():
                # Branches that import one name differently give the closed list, as at
                # module level, never the import read last.
                final = scope.frame.bindings.get(name)
                closed = final is not None and all(t.kind is None for t in final.targets)
                scope.frame.imported[name] = final.targets if final and closed else binding.targets
                scope.frame.values.pop(name, None)
            return
        if scope.class_path is not None:
            return
        for name, binding in bound.items():
            final = scope.types.names.get(name)
            if final is None or len(final.targets) < 2:
                continue
            descriptor = f"{scope.owner}{name}."
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
            self._write_field(descriptor, _reference(binding.targets[0]), scope)

    def _branches(
        self,
        bodies: list[list[ast.stmt]],
        scope: Scope,
        starts: list[int | None] | None = None,
        captures: list[list[tuple[str, CallArgument]]] | None = None,
    ) -> None:
        """Each body runs from the same names, and from `starts` in the control flow (by
        default, from where the branch is); after them, a name keeps a value only where
        every body that reaches the end gives it the same one, and is a `merge` where they
        give different ones. `captures` are the names each body starts by writing (a
        `match` case's pattern)."""
        frame = scope.frame
        flow = scope.flow
        if starts is None:
            starts = [flow.here()] * len(bodies)
        if captures is None:
            captures = [[] for _ in bodies]
        points: list[int | None] = []
        if frame is None:
            for body, start, captured in zip(bodies, starts, captures, strict=True):
                flow.at(start)
                self._capture(captured, scope)
                self._statements(body, scope)
                points.append(flow.here())
            flow.join(points)
            return
        before = frame.values
        ends = []
        for body, start, captured in zip(bodies, starts, captures, strict=True):
            flow.at(start)
            frame.values = dict(before)
            self._capture(captured, scope)
            self._statements(body, scope)
            points.append(flow.here())
            if flow.here() is not None:
                ends.append(frame.values)
        flow.join(points)
        frame.values = _join(ends) if ends else dict(before)

    def _capture(self, captured: list[tuple[str, CallArgument]], scope: Scope) -> None:
        """Write each name a `match` pattern captured."""
        for name, value in captured:
            self._store(ast.Name(id=name, ctx=ast.Store()), value, scope)

    def _loop(
        self,
        body: list[ast.stmt],
        orelse: list[ast.stmt],
        scope: Scope,
        *,
        target: ast.expr | None = None,
        test: ast.expr | None = None,
        iterator: CallArgument | None = None,
        asynchronous: bool = False,
    ) -> None:
        """A loop body runs zero or more times, so a name it writes holds no one value at
        its start. Where the loop ends, a name holds its value from before, from the end of
        the body or from a `continue`; after the `else`, that value or one from a
        `break`, which skips the `else`."""
        frame = scope.frame
        flow = scope.flow
        before = dict(frame.values) if frame is not None else {}
        jumps = LoopJumps()
        if frame is not None:
            for name in _assigned(_own_nodes(body)) & set(frame.values):
                frame.values[name] = _UNKNOWN
            frame.jumps.append(jumps)
        loop = flow.loop()
        if test is not None:
            self._value(test, scope)
        element = _UNKNOWN if iterator is None else self._step(iterator, scope, asynchronous)
        flow.loop_tested(loop, endless=isinstance(test, ast.Constant) and bool(test.value))
        if target is not None:
            self._store(target, element, scope)
        self._statements(body, scope)
        if frame is not None:
            frame.jumps.pop()
            ended = [frame.values] if flow.here() is not None else []
            frame.values = _join([before, *jumps.continues, *ended])
        flow.loop_body_end(loop)
        self._statements(orelse, scope)
        if frame is not None:
            ended = [frame.values] if flow.here() is not None else []
            if jumps.breaks or ended:
                frame.values = _join([*jumps.breaks, *ended])
        flow.loop_end(loop)

    def _try(self, node: ast.Try | ast.TryStar, scope: Scope) -> None:
        frame = scope.frame
        flow = scope.flow
        before = self._protect(scope)
        jumped = [(len(j.breaks), len(j.continues)) for j in frame.jumps] if frame else []
        attempt = flow.try_body(has_finally=bool(node.finalbody))
        self._statements(node.body, scope)
        # A handler starts from any point of the body.
        handled = self._raised(before, scope, keep=True)
        flow.try_else(attempt)
        self._statements(node.orelse, scope)
        flow.try_handlers(attempt)
        ends = [frame.values] if frame is not None and flow.here() is not None else []
        for handler in node.handlers:
            flow.handler(attempt)
            if frame is not None and handled is not None:
                frame.values = dict(handled)
            if handler.type is not None:
                self._value(handler.type, scope)
            flow.handler_matched(attempt, catches_all=handler.type is None)
            if handler.name is not None:
                self._store(ast.Name(id=handler.name, ctx=ast.Store()), _UNKNOWN, scope)
            self._statements(handler.body, scope)
            if frame is not None and flow.here() is not None:
                ends.append(frame.values)
            flow.handler_end(attempt)
        # The `finally` also runs on the way out of an exception, a `return`, a `break` or
        # a `continue`, from any point of the body, the `else` and the handlers.
        raised = self._raised(before, scope)
        if frame is not None and before is not None:
            normal = _join(ends) if ends else dict(before)
            if node.finalbody and raised is not None:
                frame.values = _join([*ends, raised])
            else:
                frame.values = normal
        flow.try_finally(attempt)
        self._statements(node.finalbody, scope)
        flow.try_end(attempt)
        if frame is not None and before is not None and node.finalbody:
            # After it, only the normal way out goes on; the names the `finally` sets have
            # the values it gave them.
            assigned = _assigned(_own_nodes(node.finalbody))
            finished = frame.values
            frame.values = {
                **normal,
                **{name: finished.get(name, _UNKNOWN) for name in assigned},
            }
            for jumps, (breaks, continues) in zip(frame.jumps, jumped, strict=False):
                for state in [*jumps.breaks[breaks:], *jumps.continues[continues:]]:
                    state.update({name: _UNKNOWN for name in assigned})

    def _protect(self, scope: Scope) -> dict[str, CallArgument] | None:
        """Start a block an exception may leave from any point: the names now, and a
        record of every value the block gives a name. None outside a function."""
        frame = scope.frame
        if frame is None:
            return None
        frame.writes.append({})
        # A name an import binds holds a value this scanner does not follow.
        return {**{name: _UNKNOWN for name in frame.imported}, **frame.values}

    def _raised(
        self, before: dict[str, CallArgument] | None, scope: Scope, *, keep: bool = False
    ) -> dict[str, CallArgument] | None:
        """The names where an exception left the block `_protect` started: each one the
        block set holds its value from before (where it had one) or any value the block
        gave it. With `keep`, the block goes on being recorded."""
        frame = scope.frame
        if frame is None or before is None:
            return None
        writes = frame.writes[-1] if keep else frame.writes.pop()
        if not keep and frame.writes:
            # The enclosing block saw these values given too.
            for name, values in writes.items():
                frame.writes[-1].setdefault(name, []).extend(values)
        state = dict(before)
        for name, values in writes.items():
            state[name] = _one_of([before[name], *values] if name in before else values)
        return state

    def _store(
        self, target: ast.expr, value: CallArgument, scope: Scope, *, evaluate: bool = True
    ) -> None:
        """Write `value` to `target`: a local name, a field, or a part this scanner does
        not follow (a subscript, an attribute of another object)."""
        frame = scope.frame
        if isinstance(target, ast.Name):
            if frame is None:
                return
            if target.id in frame.global_names:
                self._write_field(f"{self._context.here}#{target.id}.", value, scope)
                return
            frame.local_names.add(target.id)
            frame.imported.pop(target.id, None)
            if target.id in frame.rebound:
                # A nested function rebinds it (`nonlocal`) at a time this body does not
                # order: no one value at any read.
                value = _UNKNOWN
            frame.values[target.id] = value
            frame.mutable.discard(target.id)
            if frame.writes:
                frame.writes[-1].setdefault(target.id, []).append(value)
        elif isinstance(target, ast.Tuple | ast.List):
            # Each name takes a part of the value: by position where its type is a tuple of
            # as many (`tuple[A, B]`), else a part this scanner does not split.
            parts = _parts(value, target.elts, scope)
            for position, element in enumerate(target.elts):
                part = _UNKNOWN if parts is None else _part(parts[position])
                self._store(element, part, scope, evaluate=evaluate)
        elif isinstance(target, ast.Starred):
            self._store(target.value, _UNKNOWN, scope, evaluate=evaluate)
        elif isinstance(target, ast.Attribute):
            written = self._field_target(target, scope)
            if written is not None:
                self._write_field(written, value, scope)
            elif evaluate:
                self._value(target.value, scope)
        elif isinstance(target, ast.Subscript) and evaluate:
            self._value(target.value, scope)
            self._value(target.slice, scope)

    def _field_target(self, target: ast.Attribute, scope: Scope) -> str | None:
        """The field `target` names: an attribute of `self`, or of a module or a class
        this file names. None for an attribute of any other object."""
        if self._is_self(target.value, scope):
            return f"{scope.owner}{target.attr}."
        targets = self._targets(target.value, scope)
        if targets is not None and len(targets) == 1:
            found = targets[0]
            if found.member is None or found.kind == "class":
                return f"{type_symbol(found)}{target.attr}."
        return None

    def _write_field(self, written: str, value: CallArgument, scope: Scope) -> None:
        parameter = value.value if value.kind == "parameter" else None
        self.facts.append(
            FieldWriteFact(
                document_id=self._context.document_id,
                field=written,
                from_parameter=parameter if isinstance(parameter, int) else None,
                value=None if isinstance(parameter, int) else value,
                written_by=scope.body.caller,
            )
        )

    # -- decorators ----------------------------------------------------------------------

    def _decorators(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef, scope: Scope
    ) -> list[Callee]:
        """Python reads every decorator expression top to bottom before the definition."""
        return [self._decorator(decorator, scope) for decorator in node.decorator_list]

    def _apply(self, callees: list[Callee], decorated: CallArgument, scope: Scope) -> CallArgument:
        """Then it applies them from the bottom up, each to the result of the one below
        it. The last result is what the name holds."""
        current = decorated
        for callee in reversed(callees):
            current = self._invoke(callee, [current], scope)
        return current

    def _decorator(self, decorator: ast.expr, scope: Scope) -> Callee:
        if isinstance(decorator, ast.Name | ast.Attribute):
            return self._callee(decorator, scope)
        return self._on_value(self._value(decorator, scope), CALL, scope)

    # -- calls ---------------------------------------------------------------------------

    def _call(self, node: ast.Call, scope: Scope) -> CallArgument:
        callee = self._callee(node.func, scope)
        positional = []
        types: list[TypeRef | None] = []
        type_at = _TYPE_ARGUMENTS.get((str(callee.target.owner), str(callee.target.name)))
        for position, argument in enumerate(node.args):
            if position == type_at:
                positional.append(self._type_form(argument, scope))
                types.append(None)
            elif isinstance(argument, ast.Starred):
                # Unpacked into the positional arguments (D00 §5 `keyword: "*"`): how many it
                # fills, and so where every later one lands, is not known.
                self._value(argument.value, scope)
                positional.append(_UNKNOWN.model_copy(update={"keyword": _UNPACKED_POSITIONAL}))
                types.append(None)
            else:
                positional.append(self._value(argument, scope))
                types.append(self._typed(argument, positional[-1], scope))
        keywords = []
        for keyword in node.keywords:
            keywords.append((keyword.arg, self._value(keyword.value, scope)))
            types.append(self._typed(keyword.value, keywords[-1][1], scope))
        return self._invoke(
            callee,
            self._arguments(positional, keywords),
            scope,
            unpacked=any(isinstance(a, ast.Starred) for a in node.args),
            types=types,
        )

    def _arguments(
        self,
        positional: list[CallArgument],
        keywords: list[tuple[str | None, CallArgument]],
    ) -> list[CallArgument]:
        """The arguments as written (ruling R27): the positional ones in order, then each
        keyword one with its name in `keyword` (`**` for a mapping unpacked into them). The
        resolver binds them to the callee's parameters, by one calling rule for every call
        (`values.parameter_slots`)."""
        return positional + [
            value.model_copy(update={"keyword": name or _UNPACKED}) for name, value in keywords
        ]

    def _invoke(
        self,
        callee: Callee,
        arguments: list[CallArgument],
        scope: Scope,
        *,
        unpacked: bool = False,
        types: list[TypeRef | None] | None = None,
    ) -> CallArgument:
        """Write the call; the value it gives. A constructor gives the `instance` whose
        `source` is its receiver, as `new` does on the JVM (D00 §5). `types` are the
        arguments' types where the scanner knows them, for the type the call gives."""
        constructs = callee.invoke_kind == "special" and callee.target.name == INIT
        result = None if constructs else scope.body.value_id()
        scope.flow.site(scope.body.ordinal, len(self.facts))
        self.facts.append(
            CallSiteFact(
                document_id=self._context.document_id,
                caller=scope.body.caller,
                target=callee.target,
                invoke_kind=callee.invoke_kind,
                ordinal=scope.body.ordinal,
                receiver=callee.receiver,
                receiver_parameter=callee.receiver_parameter,
                receiver_field=callee.receiver_field,
                receiver_field_kind=callee.receiver_field_kind,
                result=result,
                arguments=arguments,
            )
        )
        scope.body.ordinal += 1
        if result is not None:
            returned = self._library_returns(
                callee, arguments, scope, unpacked=unpacked, types=types or []
            )
            if isinstance(returned, CallableType):
                scope.body.callables[result] = returned
            elif returned is not None:
                scope.body.returned[result] = returned
            else:
                hinted = self._declared_result(callee)
                if hinted is not None:
                    scope.body.declared[result] = hinted
            return CallArgument(kind="unresolved", source=result)
        libraries = self._context.index.libraries
        if callee.receiver is not None and libraries is not None and not unpacked:
            made = libraries.construct(str(callee.target.owner), arguments, types or [])
            if made is not None:
                scope.body.returned[callee.receiver] = made
        if callee.receiver is not None:
            return CallArgument(kind="instance", symbol=callee.target.owner, source=callee.receiver)
        return _UNKNOWN

    def _callee(self, func: ast.expr, scope: Scope) -> Callee:
        """What `func(...)` calls. A name this file binds to a class is that class's
        `<init>`; to a function, or to a member of another module, a static call on its
        module type — whether that member is a class is in a file this scanner does not
        read, so the resolver decides. A call on a value names its receiver."""
        if isinstance(func, ast.Attribute):
            if _is_super(func.value, scope):
                return self._super(func.attr, scope)
            # `Base.__init__(self, …)` calls the method this scanner names `<init>`.
            attr = INIT if func.attr == "__init__" else func.attr
            if self._is_self(func.value, scope):
                return Callee(_target(scope.owner, attr), "virtual")
            owners = self._targets(func.value, scope) if _is_dotted(func.value) else None
            if owners is not None and len(owners) == 1:
                owner = owners[0]
                defined = self._library_member(owner, attr)
                if defined is not None:
                    method_owner, method_name = _split(defined)
                    return Callee(_target(method_owner, method_name), "static")
                if owner.member is None or owner.kind == "class" or _is_builtin_class(owner):
                    return Callee(_target(type_symbol(owner), attr), "static")
                if owner.kind in (None, "variable"):
                    return Callee(
                        _target(self._module_class(owner), attr),
                        "virtual",
                        scope.body.value_id(),
                        receiver_field=_field_of(owner),
                    )
            if owners is not None and len(owners) > 1:
                return Callee(
                    _target(None, attr),
                    "virtual",
                    scope.body.value_id(),
                    receiver_field=self._closed_list_field(func.value, scope),
                )
            value = self._value(func.value, scope)
            on_self = isinstance(func.value, ast.Attribute) and self._is_self(
                func.value.value, scope
            )
            return self._on_value(
                value, attr, scope, declared=self._declared(func.value, scope), on_self=on_self
            )
        if isinstance(func, ast.Name):
            if self._is_self(func, scope):
                if self._class_receiver(func, scope):
                    # `cls()` constructs the class the method was called through: this
                    # class or a subclass, the closed list a virtual `<init>` reads (R37).
                    return Callee(_target(scope.owner, INIT), "virtual")
                return Callee(_target(scope.owner, CALL), "virtual")
            targets = self._targets(func, scope)
            if targets is None:
                local = self._local(func.id, scope.frame)
                if local is not None and local.kind == "lambda" and local.symbol in self._methods:
                    method_owner, method_name = self._methods[str(local.symbol)]
                    return Callee(_target(method_owner, method_name), "static")
                if local is not None and local.kind == "class" and local.symbol is not None:
                    return Callee(_target(local.symbol, INIT), "special", scope.body.value_id())
                return self._on_value(
                    local or _UNKNOWN, CALL, scope, declared=self._declared(func, scope)
                )
            if len(targets) == 1:
                target = targets[0]
                if target.kind == "class" or _is_builtin_class(target):
                    return Callee(
                        _target(type_symbol(target), INIT), "special", scope.body.value_id()
                    )
                if target.kind == "variable":
                    typed = self._module_type(target)
                    receiver = scope.body.value_id()
                    if isinstance(typed, CallableType):
                        # The name holds a callable: what calling it gives is read with
                        # its arguments, as for a call's own result.
                        scope.body.callables[receiver] = typed
                    return Callee(
                        _target(typed if isinstance(typed, str) else None, CALL),
                        "virtual",
                        receiver,
                        receiver_field=_field_of(target),
                    )
                if target.member is not None and target.kind in (None, "function"):
                    method_owner, method_name = _split(target)
                    return Callee(_target(method_owner, method_name), "static")
            if len(targets) > 1:
                return Callee(
                    _target(None, CALL),
                    "virtual",
                    scope.body.value_id(),
                    receiver_field=self._closed_list_field(func, scope),
                )
        return self._on_value(self._value(func, scope), CALL, scope)

    def _library_member(self, owner: Target, name: str) -> Target | None:
        """`module.name` for a library module, as the library defines it: a re-export is
        its defining module's (`requests.get` is `requests.api.get`)."""
        index = self._context.index
        if owner.member is not None or index.libraries is None or index.owns(owner.module):
            return None
        found = index.libraries.member(owner, name)
        # A closed list (the library's branches bind the name differently) names no one
        # module: the call keeps the owner its own line writes.
        if found is None or len(found) != 1:
            return None
        (defined,) = found
        if defined.member is None or "." in defined.member:
            return None
        return defined

    def _library_returns(
        self,
        callee: Callee,
        arguments: list[CallArgument],
        scope: Scope,
        *,
        unpacked: bool,
        types: list[TypeRef | None],
    ) -> TypeRef | CallableType | None:
        """The type a library call returns, where its written signature chooses one, or
        the callable it returns; and the type a call of such a callable gives. On a union
        receiver, the one type every member gives, else none: several types are never
        one."""
        libraries = self._context.index.libraries
        owner = callee.target.owner
        if callee.target.name == INIT and callee.invoke_kind == "virtual" and owner is not None:
            # A class object called: an instance of its class (a subclass's, maybe).
            return TypeRef(symbol=owner)
        if owner is None and callee.target.name == CALL and callee.receiver is not None:
            called = scope.body.callables.get(callee.receiver)
            given = None if called is None else _call_gives(called, arguments, scope)
            return TypeRef(symbol=given) if isinstance(given, str) else given
        if libraries is None or callee.target.name is None:
            return None
        name = str(callee.target.name)
        typed = callee.typed
        if owner is None and callee.hinted and typed is not None and typed.symbol != UNION:
            return self._returns_on(typed, name, arguments, types, unpacked=unpacked)
        if owner is None:
            if typed is None or typed.symbol != UNION:
                return None
            each = [
                self._returns_on(member, name, arguments, types, unpacked=unpacked)
                for member in typed.arguments
            ]
            first = each[0] if each else None
            return first if first is not None and all(t == first for t in each) else None
        receiver = typed if typed is not None and typed.symbol == owner else TypeRef(symbol=owner)
        return self._returns_on(receiver, name, arguments, types, unpacked=unpacked)

    def _returns_on(
        self,
        receiver: TypeRef,
        name: str,
        arguments: list[CallArgument],
        types: list[TypeRef | None],
        *,
        unpacked: bool,
    ) -> TypeRef | CallableType | None:
        """What `name` called on a value of type `receiver` returns. A class of this file is
        looked up through its written bases (C3): a method it or a base of this file defines
        is a body, which the resolver follows; one a library class defines is read there,
        with what the receiver's type arguments give that class's type parameters."""
        libraries = self._context.index.libraries
        assert libraries is not None
        owner = receiver.symbol
        if owner in self._local_classes:
            order = self._hierarchy.order(owner)
            entries = [] if order is None else order
            defining = next(
                (e for e in entries if name in _members(self._hierarchy.shape_of(e.symbol))),
                None,
            )
            if defining is None or defining.symbol in self._local_classes:
                return None
            given = parameter_mapping(receiver, self._local_classes[owner])
            instance = substitute(defining, given) or TypeRef(symbol=defining.symbol)
            found = libraries.call_returns(
                defining.symbol,
                name,
                arguments,
                unpacked=unpacked,
                receiver=instance,
                argument_types=types,
                self_type=receiver,
            )
        else:
            found = libraries.call_returns(
                owner, name, arguments, unpacked=unpacked, receiver=receiver, argument_types=types
            )
        if found is None or found.resolution != "resolved" or len(found.types) != 1:
            return None
        (returned,) = found.types
        if isinstance(returned, CallableType):
            return returned
        if returned.symbol == UNION or _class_of(returned) is not None:
            return returned
        return None

    def _declared_result(self, callee: Callee) -> TypeRef | None:
        """The type a call of a function or method of this file declares it returns: a
        module-level function's, or the method a class of this file defines for the
        receiver (C3, through bases of this file), its type variables filled by the
        receiver's type arguments. None where the callee is another file's or a library's,
        or declares nothing that names a class."""
        owner, name = callee.target.owner, callee.target.name
        if name is None or name == INIT:
            return None
        if owner is None:
            typed = callee.typed if callee.hinted else None
            return None if typed is None else self._declared_on(typed, name)
        if callee.invoke_kind == "static" and owner == f"{self._context.here}#":
            return _a_class(self._own_returns.get(method_descriptor(owner, name, PY_SIGNATURE)))
        if owner in self._local_classes:
            typed = callee.typed
            receiver = (
                typed if typed is not None and typed.symbol == owner else TypeRef(symbol=owner)
            )
            return self._declared_on(receiver, name)
        return None

    def _declared_on(self, receiver: TypeRef, name: str) -> TypeRef | None:
        """What `name` called on a `receiver` of a class of this file declares it returns."""
        owner = receiver.symbol
        shape = self._local_classes.get(owner)
        if shape is None:
            return None
        order = self._hierarchy.order(owner)
        entries = [TypeRef(symbol=owner)] if order is None else order
        defining = next(
            (e for e in entries if name in _members(self._hierarchy.shape_of(e.symbol))), None
        )
        if defining is None or defining.symbol not in self._local_classes:
            return None
        written = self._own_returns.get(method_descriptor(defining.symbol, name, PY_SIGNATURE))
        if written is None:
            return None
        instance = substitute(defining, parameter_mapping(receiver, shape)) or defining
        mapping = parameter_mapping(instance, self._local_classes[defining.symbol])
        return _a_class(substitute(written, mapping))

    def _super(self, name: str, scope: Scope) -> Callee:
        """`super().m()` from a method: `special` on the class's first written parent, as
        the JVM's `super.m()` names the direct superclass. The `super()` call itself is
        the receiver, as `aload_0` is, and is not written."""
        method = INIT if name == "__init__" else name
        if scope.super_owner is not None:
            return Callee(_target(scope.super_owner, method), "special")
        return Callee(_target(None, method), "virtual", scope.body.value_id())

    def _on_value(
        self,
        value: CallArgument,
        name: str,
        scope: Scope,
        *,
        declared: TypeRef | None = None,
        on_self: bool = False,
        protocol: bool = False,
    ) -> Callee:
        """A call named `name` on `value`. The owner is the type written for it where
        there is one; else it is left to the resolver, and the receiver is named. A
        `protocol` call (one syntax makes, `xs[i]`, `for x in xs`) on a value of type
        `type[X]` runs on the class object, never on an `X`: no owner, and the resolver
        reads the class (ruling R37)."""
        if value.kind == "class" and value.symbol is not None:
            return Callee(_target(value.symbol, name), "static")
        if value.kind == "instance" and value.symbol is not None:
            made = None if value.source is None else scope.body.returned.get(value.source)
            return Callee(
                _target(value.symbol, name),
                "virtual",
                value.source,
                typed=made or TypeRef(symbol=value.symbol),
            )
        if value.kind in ("string", "concat"):
            declared = TypeRef(symbol=_STRING)
        if declared is None:
            declared = _known_type(value, scope)
        # What a function of this file declares the value is: it names no owner (the body's
        # returns run, and the resolver follows them), and types only what is read off it.
        hinted = False
        if declared is None and value.kind == "unresolved" and value.source is not None:
            declared = scope.body.declared.get(value.source)
            hinted = declared is not None
        if protocol and declared is not None and declared.symbol == _TYPE_OF:
            declared = None
        if name == CALL and declared is not None and declared.symbol == _TYPE_OF:
            # Calling a class object constructs it (R37): `X` or a subclass, as `cls()` is.
            name = INIT
            declared = declared.arguments[0] if len(declared.arguments) == 1 else None
            hinted = False
        owner = None if hinted else _class_of(declared)
        if value.kind == "parameter" and isinstance(value.value, int):
            return Callee(
                _target(owner, name),
                "virtual",
                None if owner is not None else scope.body.value_id(),
                receiver_parameter=value.value,
                typed=declared,
            )
        receiver = value.source if value.source is not None else scope.body.value_id()
        if value.kind == "field":
            return Callee(
                _target(owner, name),
                "virtual",
                receiver,
                receiver_field=value.symbol,
                receiver_field_kind="instance" if on_self else None,
                typed=declared,
            )
        return Callee(_target(owner, name), "virtual", receiver, typed=declared, hinted=hinted)

    def _closed_list_field(self, node: ast.expr, scope: Scope) -> str | None:
        """The static field a module-level name bound to a closed list is read as."""
        if (
            isinstance(node, ast.Name)
            and scope.types.names.get(node.id) is not None
            and (scope.frame is None or self._local(node.id, scope.frame) is None)
        ):
            return f"{self._context.here}#{node.id}."
        return None

    # -- values --------------------------------------------------------------------------

    def _value(self, node: ast.expr, scope: Scope) -> CallArgument:
        """One value as D00 §5's argument grammar, writing every call in it."""
        if isinstance(node, ast.Constant):
            return _constant(node.value)
        if isinstance(node, ast.Call):
            return self._call(node, scope)
        if isinstance(node, ast.JoinedStr):
            return self._concat([node], scope)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            parts = _added(node)
            if any(_is_text(part) for part in parts):
                return self._concat(parts, scope)
        if (
            isinstance(node, ast.UnaryOp)
            and isinstance(node.op, ast.USub)
            and isinstance(node.operand, ast.Constant)
            and type(node.operand.value) is int
        ):
            return CallArgument(kind="int", value=-node.operand.value)
        if isinstance(node, ast.Name):
            if self._is_self(node, scope):
                return _UNKNOWN
            if self._targets(node, scope) is None:
                return self._local(node.id, scope.frame) or _UNKNOWN
        if isinstance(node, ast.Attribute) and self._is_self(node.value, scope):
            return CallArgument(kind="field", symbol=f"{scope.owner}{node.attr}.")
        if isinstance(node, ast.Name | ast.Attribute) and _is_dotted(node):
            targets = self._targets(node, scope)
            if targets:
                if len(targets) == 1:
                    return _reference(targets[0])
                return CallArgument(kind="merge", candidates=[_reference(t) for t in targets])
        if isinstance(node, ast.List | ast.Tuple):
            elements = [self._value(element, scope) for element in node.elts]
            typed = self._literal_type(node, node.elts, elements, scope)
            if any(isinstance(element, ast.Starred) for element in node.elts):
                return _part(typed)
            found = _Part(kind="array", elements=elements)
            found._typed = typed
            return found
        if isinstance(node, ast.Dict | ast.Set):
            children = [c for c in ast.iter_child_nodes(node) if isinstance(c, ast.expr)]
            read = {id(child): self._value(child, scope) for child in children}
            if isinstance(node, ast.Set):
                return _part(
                    self._literal_type(node, node.elts, [read[id(e)] for e in node.elts], scope)
                )
            keys = [None if k is None else read[id(k)] for k in node.keys]
            return _part(self._dict_type(node, keys, [read[id(v)] for v in node.values], scope))
        if isinstance(node, ast.Lambda):
            return self._lambda(node, scope)
        if isinstance(node, ast.IfExp):
            self._value(node.test, scope)
            tested = scope.flow.here()
            chosen = self._value(node.body, scope)
            ends = [scope.flow.here()]
            scope.flow.at(tested)
            other = self._value(node.orelse, scope)
            scope.flow.join([*ends, scope.flow.here()])
            return _merge([chosen, other])
        if isinstance(node, ast.BoolOp):
            # Each value is read only where the ones before it did not decide.
            values, ends = [], []
            for operand in node.values:
                values.append(self._value(operand, scope))
                ends.append(scope.flow.here())
            scope.flow.join(ends)
            return _merge(values)
        if isinstance(node, ast.Await):
            return self._value(node.value, scope)
        if isinstance(node, ast.NamedExpr):
            value = self._value(node.value, scope)
            self._store(node.target, value, scope)
            return value
        if isinstance(node, _COMPREHENSIONS):
            return self._comprehension(node, scope)
        if isinstance(node, ast.Subscript):
            return self._subscript(node, scope)
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.expr):
                self._value(child, scope)
        return _UNKNOWN

    def _concat(self, parts: list[ast.expr], scope: Scope) -> CallArgument:
        """A string the code assembles: the template with `{}` for each value, and the
        `dynamic` site whose arguments are those values (D00 §5 `concat`). With no value
        in it, it is the string itself, as javac folds a constant concatenation."""
        template: list[str] = []
        operands: list[CallArgument] = []
        for part in parts:
            pieces = part.values if isinstance(part, ast.JoinedStr) else [part]
            for piece in pieces:
                if isinstance(piece, ast.Constant) and isinstance(piece.value, str):
                    template.append(piece.value)
                    continue
                written = piece.value if isinstance(piece, ast.FormattedValue) else piece
                operands.append(self._value(written, scope))
                template.append(_HOLE)
        text = "".join(template)
        if not operands:
            return CallArgument(kind="string", value=text)
        site = Callee(_target(_STRING, _FORMAT), "dynamic")
        produced = self._invoke(site, operands, scope)
        return CallArgument(kind="concat", value=text, source=produced.source)

    def _lambda(self, node: ast.Lambda, scope: Scope) -> CallArgument:
        """A `lambda` is a method of its own, named as javac names a lambda body
        (`lambda$<method>$<n>`, numbered per method); its value is its one return."""
        for default in [*node.args.defaults, *node.args.kw_defaults]:
            if default is not None:
                self._value(default, scope)
        prefix = scope.frame.prefix if scope.frame is not None else _PREFIXES[CLINIT]
        name = f"lambda${prefix}${scope.body.lambdas}"
        scope.body.lambdas += 1
        descriptor = method_descriptor(scope.owner, name, PY_SIGNATURE)
        self._method_known(descriptor, scope.owner, name)
        self._symbol(
            descriptor,
            ConstructKind.METHOD,
            scope.owner,
            node.lineno,
            node.end_lineno or node.lineno,
            signature=self._signature(node, scope.types, skip_first=False),
            modifiers={"abstract": False, "static": True, "varargs": node.args.vararg is not None},
        )
        frame = self._frame(node.args, [], scope, scope.types, name, receiver_taken=False)
        inner = Scope(
            owner=scope.owner,
            types=scope.types,
            body=self._body(self._full(descriptor)),
            class_path=scope.class_path,
            frame=frame,
        )
        self._return(self._value(node.body, inner), inner)
        self._positions(inner)
        return CallArgument(kind="lambda", symbol=descriptor, captures=0)

    def _comprehension(
        self, node: ast.ListComp | ast.SetComp | ast.DictComp | ast.GeneratorExp, scope: Scope
    ) -> CallArgument:
        """A comprehension runs in the method that holds it (PEP 709). Its own names
        hold one element at a time, and are gone after it."""
        frame = scope.frame
        flow = scope.flow
        saved = (dict(frame.values), set(frame.local_names)) if frame is not None else None
        # Each `for` is a loop; an `if` that is false takes its next element. A generator
        # expression runs its elements when it is consumed, possibly after this body ended.
        lazy = isinstance(node, ast.GeneratorExp)
        loops = []
        for generator in node.generators:
            asynchronous = bool(generator.is_async)
            iterator = self._iterate(generator.iter, scope, asynchronous=asynchronous)
            loops.append(flow.loop())
            if lazy and len(loops) == 1:
                # Its `iter()` runs now; every `next()` runs when it is consumed, so none
                # of them is on this body's way to its end.
                flow.loop_tested(loops[-1])
                flow.defer(True)
                element = self._step(iterator, scope, asynchronous)
            else:
                element = self._step(iterator, scope, asynchronous)
                flow.loop_tested(loops[-1])
            self._store(generator.target, element, scope, evaluate=False)
            for condition in generator.ifs:
                self._value(condition, scope)
                flow.loop_test(loops[-1])
        parts = [node.key, node.value] if isinstance(node, ast.DictComp) else [node.elt]
        made = [(part, self._value(part, scope)) for part in parts]
        typed = [self._element_type(part, value, scope) for part, value in made]
        if lazy:
            flow.defer(False)
        # An exhausted inner loop takes the outer loop's next element.
        for loop in reversed(loops):
            flow.loop_body_end(loop)
        flow.loop_end(loops[0])
        if frame is not None and saved is not None:
            frame.values, frame.local_names = saved
        if lazy:
            return _UNKNOWN
        # The object it builds is its class, with the type of what each pass adds.
        symbol = _COMPREHENSION_CLASSES[type(node)]
        if any(part is None for part in typed):
            return _part(TypeRef(symbol=symbol))
        return _part(TypeRef(symbol=symbol, arguments=[p for p in typed if p is not None]))

    # -- container literals (OI-324 part 2) ----------------------------------------------

    def _literal_type(
        self,
        node: ast.List | ast.Tuple | ast.Set,
        written: list[ast.expr],
        elements: list[CallArgument],
        scope: Scope,
    ) -> TypeRef:
        """The type a list, tuple or set literal builds: its class, with its elements'
        types where every one is known. Several types are their union (a closed list, never
        one of them); a tuple keeps them by position. An empty literal, a starred element or
        an element of no known type gives the class alone."""
        symbol = _LITERAL_CLASSES[type(node)]
        if not written or any(isinstance(element, ast.Starred) for element in written):
            return TypeRef(symbol=symbol)
        types = [self._element_type(w, e, scope) for w, e in zip(written, elements, strict=True)]
        if any(found is None for found in types):
            return TypeRef(symbol=symbol)
        if isinstance(node, ast.Tuple):
            return TypeRef(symbol=symbol, arguments=[t for t in types if t is not None])
        joined = union_of(list(types))
        return TypeRef(symbol=symbol, arguments=[] if joined is None else [joined])

    def _dict_type(
        self,
        node: ast.Dict,
        keys: list[CallArgument | None],
        values: list[CallArgument],
        scope: Scope,
    ) -> TypeRef:
        """A dict literal's type: `dict[K, V]` where every key and value has a known type,
        each the union of what is written; an unpacked `**mapping` or an unknown one gives
        `dict` alone."""
        dict_type = TypeRef(symbol=_LITERAL_CLASSES[ast.Dict])
        if not keys or any(key is None for key in keys):
            return dict_type
        key_types = [
            self._element_type(w, k, scope)
            for w, k in zip(node.keys, keys, strict=True)
            if w is not None and k is not None
        ]
        value_types = [
            self._element_type(w, v, scope) for w, v in zip(node.values, values, strict=True)
        ]
        joined = [union_of(list(key_types)), union_of(list(value_types))]
        if any(t is None for t in [*key_types, *value_types]) or any(j is None for j in joined):
            return dict_type
        return dict_type.model_copy(update={"arguments": [j for j in joined if j is not None]})

    def _element_type(self, node: ast.expr, value: CallArgument, scope: Scope) -> TypeRef | None:
        """The type of one element the code writes: a literal's own class, else what the
        scanner knows of the value (`_typed`). None where it is not known."""
        if isinstance(node, ast.Constant):
            if node.value is None:
                return TypeRef(symbol=_NONE, nullable=True)
            literal = type(node.value)
            if literal in (str, int, float, bool, bytes, complex):
                return TypeRef(symbol=f"{BUILTINS}/{literal.__name__}#")
            return None
        if value.kind in ("string", "concat"):
            return TypeRef(symbol=_STRING)
        return self._typed(node, value, scope)

    # -- names ---------------------------------------------------------------------------

    def _is_self(self, node: ast.expr, scope: Scope) -> bool:
        """Whether `node` is the method's receiver. A nested function or a `lambda` sees
        the receiver of the method that holds it, as a JVM lambda body sees `this`."""
        if not isinstance(node, ast.Name):
            return False
        current = scope.frame
        while current is not None:
            if node.id in current.global_names:
                return False
            if node.id in current.local_names:
                return node.id == current.self_name and current.values.get(node.id) is _SELF
            current = current.enclosing
        return False

    def _class_receiver(self, node: ast.Name, scope: Scope) -> bool:
        """Whether the receiver `node` names is a class (`cls` of a `@classmethod`)."""
        current = scope.frame
        while current is not None:
            if node.id in current.local_names:
                return current.class_receiver
            current = current.enclosing
        return False

    def _local(self, name: str, frame: Frame | None) -> CallArgument | None:
        """The value of a function's own name, or None where `name` is not one. A name
        of an enclosing function is `unresolved` (its value ids are another method's),
        except a function or a class it defines."""
        current, nested = frame, False
        while current is not None:
            if name in current.global_names:
                return None
            if name in current.local_names:
                value = current.values.get(name, _UNKNOWN)
                if value is _SELF:
                    return _UNKNOWN
                if nested and value.kind not in ("lambda", "class"):
                    return _UNKNOWN
                if name in current.mutable:
                    # A list can change once it is handed out, as a JVM array that
                    # reaches another call does: the first read gets the literal, a
                    # later read gets `unresolved`.
                    current.mutable.discard(name)
                    # Its class does not change; what it holds may have (OI-324 part 2).
                    typed = value._typed if isinstance(value, _Part) else None
                    current.values[name] = (
                        _UNKNOWN if typed is None else _part(TypeRef(symbol=typed.symbol))
                    )
                return value
            current, nested = current.enclosing, True
        return None

    def _targets(self, node: ast.expr, scope: Scope) -> tuple[Target, ...] | None:
        """The symbols a written name or dotted name refers to, through the function's
        own imports and then the module's names. None where its first name is a local
        value: it is followed as a value, not as a symbol."""
        head = node
        while isinstance(head, ast.Attribute):
            head = head.value
        if not isinstance(head, ast.Name):
            return None
        if isinstance(node, ast.Attribute):
            prefix = self._targets(node.value, scope)
            if prefix is None or not prefix or not all(map(self._names_a_namespace, prefix)):
                # An attribute of a value: no symbol names it.
                return None
        current = scope.frame
        while current is not None:
            if head.id in current.global_names:
                break
            if head.id in current.imported:
                local = {head.id: Binding(current.imported[head.id])}
                return resolve(node, local, self._context.index)
            if head.id in current.local_names:
                return None
            current = current.enclosing
        return scope.types.lookup(node)

    def _names_a_namespace(self, target: Target) -> bool:
        """Whether an attribute of `target` is a member a symbol names: `target` is a
        module, a class, or a member of a library module, which the import rule reads as
        a module (`imports.member_of`). A variable's attribute is a value's."""
        return (
            target.member is None
            or target.kind == "class"
            or _is_builtin_class(target)
            or (target.kind is None and not self._context.index.owns(target.module))
        )

    def _declared(self, node: ast.expr, scope: Scope) -> TypeRef | None:
        """The type written for a local name, where one is written; for a module-level
        name, the class its file writes to it."""
        if (
            isinstance(node, ast.Name)
            and scope.frame is not None
            and node.id in scope.frame.local_names
        ):
            return scope.frame.declared.get(node.id)
        if isinstance(node, ast.Name):
            targets = self._targets(node, scope)
            if targets is not None and len(targets) == 1:
                found = self._module_class(targets[0])
                return None if found is None else TypeRef(symbol=found)
        return None

    def _typed(self, node: ast.expr, value: CallArgument, scope: Scope) -> TypeRef | None:
        """The type of a value the code passes on, where the scanner knows it: the type
        written for the name, else the type of what produced the value."""
        declared = self._declared(node, scope) if isinstance(node, ast.Name) else None
        return declared or _known_type(value, scope)

    # -- iteration and subscripts (OI-324) ---------------------------------------------

    def _iterate(self, iterable: ast.expr, scope: Scope, *, asynchronous: bool) -> CallArgument:
        """`iter(xs)`: the value, then `type(xs).__iter__(xs)`; the iterator it gives."""
        value = self._value(iterable, scope)
        name = _ASYNC_ITER if asynchronous else _ITER
        return self._invoke(self._protocol(value, name, iterable, scope), [], scope)

    def _step(self, iterator: CallArgument, scope: Scope, asynchronous: bool) -> CallArgument:
        """`next(it)`, at the head of each pass: the element. `async for` awaits what
        `__anext__` returns, so the element has the awaited type."""
        name = _ASYNC_NEXT if asynchronous else _NEXT
        element = self._invoke(self._on_value(iterator, name, scope), [], scope)
        typed = None if element.source is None else scope.body.returned.get(element.source)
        if asynchronous and element.source is not None:
            awaited = (
                typed.arguments[-1]
                if typed is not None and typed.symbol in _AWAITABLES and typed.arguments
                else None
            )
            if awaited is None:
                scope.body.returned.pop(element.source, None)
            else:
                scope.body.returned[element.source] = awaited
        return element

    def _protocol(self, value: CallArgument, name: str, node: ast.expr, scope: Scope) -> Callee:
        """A protocol method Python looks up on the value's type. A class's own type is its
        metaclass, which this scanner does not read, so on a class the owner is left to
        the resolver."""
        if value.kind == "class":
            return Callee(_target(None, name), "virtual", scope.body.value_id())
        on_self = isinstance(node, ast.Attribute) and self._is_self(node.value, scope)
        return self._on_value(
            value,
            name,
            scope,
            declared=self._declared(node, scope),
            on_self=on_self,
            protocol=True,
        )

    def _subscript(self, node: ast.Subscript, scope: Scope) -> CallArgument:
        """`xs[i]` is `type(xs).__getitem__(xs, i)`. A slice is a `slice` object, which the
        argument grammar does not hold: it is `unresolved`, with the type `slice` for the
        overload it chooses. `pair[1]` on a `tuple[A, B]` is that position's type, the
        typing specification's rule for a tuple. Subscripting a class or a typing form
        (`list[int]`, `Optional[X]`) makes a type, and no call is written for it."""
        if self._names_a_type_form(node.value, scope):
            self._value(node.value, scope)
            self._value(node.slice, scope)
            return _UNKNOWN
        container = self._value(node.value, scope)
        if container.kind == "class":
            self._value(node.slice, scope)
            return _UNKNOWN
        if isinstance(node.slice, ast.Slice):
            for bound in (node.slice.lower, node.slice.upper, node.slice.step):
                if bound is not None:
                    self._value(bound, scope)
            index: CallArgument = _UNKNOWN
            index_type: TypeRef | None = _SLICE
        else:
            index = self._value(node.slice, scope)
            index_type = self._typed(node.slice, index, scope)
        callee = self._protocol(container, _GETITEM, node.value, scope)
        result = self._invoke(callee, [index], scope, types=[index_type])
        held = callee.typed
        if (
            held is not None
            and held.symbol == TUPLE
            and len(held.arguments) > 1
            and index.kind == "int"
            and isinstance(index.value, int)
            and -len(held.arguments) <= index.value < len(held.arguments)
            and result.source is not None
        ):
            scope.body.returned[result.source] = held.arguments[index.value]
        return result

    def _type_form(self, node: ast.expr, scope: Scope) -> CallArgument:
        """A type expression (ruling R37): a class base, `cast`'s type, `isinstance`'s
        class. A subscript in it makes a type (`__class_getitem__`), whatever its name
        binds to, so it is no `__getitem__` call; any other part is read as a value."""
        if isinstance(node, ast.Subscript):
            self._type_form(node.value, scope)
            self._type_form(node.slice, scope)
            return _UNKNOWN
        if isinstance(node, ast.Tuple) or (
            isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr)
        ):
            for part in node.elts if isinstance(node, ast.Tuple) else [node.left, node.right]:
                self._type_form(part, scope)
            return _UNKNOWN
        return self._value(node, scope)

    def _names_a_type_form(self, node: ast.expr, scope: Scope) -> bool:
        """Whether `node` names a class or one of typing's forms, whose subscript is a
        type: a class of this file, a builtin, a typing form, or a class a library
        defines. A name imported from another file of the module may be a class too; the
        resolver tells (ruling R37)."""
        if not isinstance(node, ast.Name | ast.Attribute):
            return False
        targets = self._targets(node, scope)
        return bool(targets) and all(
            t.kind == "class"
            or _is_builtin_class(t)
            or t.module in _TYPING_MODULES
            or self._library_class(t)
            for t in targets or ()
        )

    def _library_class(self, target: Target) -> bool:
        index = self._context.index
        return (
            target.kind is None
            and target.member is not None
            and index.libraries is not None
            and not index.owns(target.module)
            and index.libraries.shape_of(type_symbol(target)) is not None
        )

    def _module_class(self, target: Target) -> str | None:
        typed = self._module_type(target)
        return typed if isinstance(typed, str) else None

    def _module_type(self, target: Target) -> str | CallableType | None:
        """The type every write in this file gives the module-level name `target`, where
        it is one of this file's own names; None for any other target."""
        if (
            target.module != self._context.here
            or target.member is None
            or "." in target.member
            or target.kind not in ("variable", "function")
        ):
            return None
        return self._module_answer(target.member)

    def _module_answer(self, name: str) -> str | CallableType | None:
        """The type of this file's module-level `name`, as this reading answers it, and
        recorded as asked."""
        if self._module_types is not None:
            answer = self._module_types.get(name)
        else:
            answer = self._one_type(name, self._module_writes.get(name, []))
        answers = self.consulted.setdefault(name, [])
        if answer not in answers:
            answers.append(answer)
        return answer

    def _module_write(self, name: str, value: CallArgument, scope: Scope) -> None:
        """A module-level name written in this file, with the type of the value. A value
        read from another module-level name of this file (`alias = module`) has that name's
        type, settled by the same readings."""
        typed = _type_of(value, scope)
        if typed is None and value.kind == "field" and value.symbol is not None:
            read = str(value.symbol)
            if owner_of(read) == type_symbol(Target(self._context.here)):
                typed = self._module_answer(member_name(read))
        self._module_writes.setdefault(name, []).append(typed)

    def _one_type(
        self, name: str, written: list[str | CallableType | None]
    ) -> str | CallableType | None:
        """The one type every write gives; None where there is none, where a write's type
        is not known, or where writes give two (a closed list is never narrowed)."""
        if name in self._rebound or not written or written[0] is None:
            return None
        return written[0] if all(t == written[0] for t in written) else None

    def module_types(self) -> dict[str, str | CallableType]:
        """Each module-level name whose every write in this reading gives one type."""
        found: dict[str, str | CallableType] = {}
        for name, written in self._module_writes.items():
            typed = self._one_type(name, written)
            if typed is not None:
                found[name] = typed
        return found

    def written_names(self) -> list[str]:
        """The module-level names this reading saw written."""
        return list(self._module_writes)

    def agrees(self, found: dict[str, str | CallableType]) -> bool:
        """Whether every answer this reading gave is the type all the file's writes give."""
        return all(
            answer == found.get(name)
            for name, answers in self.consulted.items()
            for answer in answers
        )


# -- helpers -------------------------------------------------------------------------------


def _target(owner: str | None, name: str) -> CallTarget:
    return CallTarget(owner=owner, name=name, descriptor=PY_SIGNATURE)


def _type_of(value: CallArgument, scope: Scope) -> str | CallableType | None:
    """The type of a value this body made: a constructed object's class, or the class or
    callable a call's written signature gives. None for any other value."""
    if value.kind == "instance":
        return value.symbol
    if isinstance(value, _Part):
        return _class_of(value._typed)
    if value.kind == "unresolved" and value.source is not None:
        typed = scope.body.returned.get(value.source)
        return _class_of(typed) if typed is not None else scope.body.callables.get(value.source)
    return None


def _members(shape: ClassShape | None) -> frozenset[str]:
    return frozenset() if shape is None else shape.members


def _known_type(value: CallArgument, scope: Scope) -> TypeRef | None:
    """The whole type of a value this body made, type arguments and all: a constructed
    object's, a library call result's, or a tuple part's. None for any other value."""
    if isinstance(value, _Part):
        return value._typed
    if value.source is None:
        return None
    if value.kind == "instance" and value.symbol is not None:
        return scope.body.returned.get(value.source) or TypeRef(symbol=value.symbol)
    if value.kind == "unresolved":
        return scope.body.returned.get(value.source)
    return None


def _parts(value: CallArgument, targets: list[ast.expr], scope: Scope) -> list[TypeRef] | None:
    """The types a tuple target's names take by position: those of a `tuple[A, B]` of as
    many parts. None where the value's type says no arity (`tuple[A, ...]`, a list) or a
    name is starred."""
    typed = _known_type(value, scope)
    if typed is None and value.kind == "unresolved" and value.source is not None:
        typed = scope.body.declared.get(value.source)
    if (
        typed is None
        or typed.symbol != TUPLE
        or len(typed.arguments) < 2
        or len(typed.arguments) != len(targets)
        or any(isinstance(target, ast.Starred) for target in targets)
    ):
        return None
    return list(typed.arguments)


def _call_gives(
    called: CallableType, arguments: list[CallArgument], scope: Scope
) -> str | CallableType | None:
    """What a call of `Callable[[P, ...], R]` gives: `R` where it is a class; where `R` is
    a type variable, the type of the positional argument whose parameter is that
    variable. None where neither is known (`Callable[[FC], FC]` applied to a function)."""
    result = called.returns.symbol
    if names_a_type(result):
        return result if result not in (ANY, UNION) else None
    if any(argument.keyword == _UNPACKED_POSITIONAL for argument in arguments):
        # Where each later argument lands is not known.
        return None
    positional = [argument for argument in arguments if argument.keyword is None]
    for parameter, argument in zip(called.parameters or (), positional, strict=False):
        if parameter.symbol == result:
            return _type_of(argument, scope)
    return None


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
    return _UNKNOWN


def _merge(candidates: list[CallArgument]) -> CallArgument:
    """One of several values, identical ones folded (D00 §5 `merge`). A tuple part is an
    `unresolved` value in the facts, and folds as one where the parts differ."""
    if any(candidate != candidates[0] for candidate in candidates):
        candidates = [_UNKNOWN if _is_part(c) else c for c in candidates]
    folded: list[CallArgument] = []
    for candidate in candidates:
        if candidate not in folded:
            folded.append(candidate)
    return folded[0] if len(folded) == 1 else CallArgument(kind="merge", candidates=folded)


def _join(ends: list[dict[str, CallArgument]]) -> dict[str, CallArgument]:
    """The names after several paths meet: a value where every path gives the same one,
    else a `merge` of each path's value, as a JVM frame slot two branches wrote (D00 §5).
    A name some path does not set is `unresolved`."""
    joined: dict[str, CallArgument] = {}
    for name in dict.fromkeys(key for end in ends for key in end):
        joined[name] = _one_of([end.get(name, _UNKNOWN) for end in ends])
    return joined


def _one_of(values: list[CallArgument]) -> CallArgument:
    """One of `values`: itself where they are all one, `unresolved` where one of them is a
    value this scanner did not follow, else their `merge`."""
    if all(value == values[0] for value in values):
        return values[0]
    if any(value == _UNKNOWN or _is_part(value) for value in values):
        return _UNKNOWN
    return _merge([c for value in values for c in (value.candidates or [value])])


def _declared_type(annotation: ast.expr, types: TypeScope) -> TypeRef | None:
    """The type a written annotation gives a value: a class, with its type arguments, or a
    union of them. `Any`, a type variable or an unnamed type gives none."""
    found = type_ref(annotation, types)
    if found is None or not names_a_type(found.symbol) or found.symbol == ANY:
        return None
    if is_class_object(annotation, types):
        return TypeRef(symbol=_TYPE_OF, arguments=[found], nullable=found.nullable)
    return found


def own_return_type(annotation: ast.expr, types: TypeScope) -> TypeRef | None:
    """The type a function of this file declares it returns, as the scanner reads it off a
    call's result: the written type, type variables kept for the receiver's type arguments to
    fill, and `type[X]` the class object (`_declared_type`). None where the file does not
    name it, or it is `Any`."""
    found = type_ref(annotation, types)
    if found is None or found.symbol == ANY:
        return None
    if is_class_object(annotation, types):
        return TypeRef(symbol=_TYPE_OF, arguments=[found], nullable=found.nullable)
    return found


def _a_class(typed: TypeRef | None) -> TypeRef | None:
    """`typed` where it names a class, a class object or a union of them; None for a type
    variable left unfilled, `Any`, an unnamed type or `None` itself."""
    if typed is None or typed.symbol in (ANY, _NONE):
        return None
    if typed.symbol == UNION:
        return typed if all(_class_of(member) for member in typed.arguments) else None
    return typed if _class_of(typed) is not None else None


def _class_of(typed: TypeRef | None) -> str | None:
    """The one class a type names, as the owner of a call on a value of it. A union,
    `Any` or a type variable gives none. A class object's (`type[X]`) is `X`: a call
    through the class, as the scanner has always read it."""
    if typed is not None and typed.symbol == _TYPE_OF and len(typed.arguments) == 1:
        return _class_of(typed.arguments[0])
    if typed is None or not names_a_type(typed.symbol) or typed.symbol in (UNION, ANY):
        return None
    return typed.symbol


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


def _is_super(node: ast.expr, scope: Scope) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "super"
        and scope.types.lookup(node.func) == (Target(BUILTINS, "super"),)
    )


def _is_text(node: ast.expr) -> bool:
    return isinstance(node, ast.JoinedStr) or (
        isinstance(node, ast.Constant) and isinstance(node.value, str)
    )


def _added(node: ast.expr) -> list[ast.expr]:
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return [*_added(node.left), *_added(node.right)]
    return [node]


def _as_load(node: ast.expr) -> ast.expr:
    """`node` read rather than written, for `x += v`."""
    if isinstance(node, ast.Name):
        return ast.Name(id=node.id, ctx=ast.Load())
    if isinstance(node, ast.Attribute):
        return ast.Attribute(value=node.value, attr=node.attr, ctx=ast.Load())
    if isinstance(node, ast.Subscript):
        return ast.Subscript(value=node.value, slice=node.slice, ctx=ast.Load())
    return node


def _own_nodes(body: Iterable[ast.AST]) -> Iterator[ast.AST]:
    """Every node of one function's own scope: not inside a nested function, class,
    `lambda` or comprehension, whose names are their own."""
    stack = list(body)
    while stack:
        node = stack.pop()
        yield node
        if isinstance(node, _NESTED_SCOPES):
            # The name it binds, its decorators and its defaults are in this scope.
            if not isinstance(node, ast.Lambda):
                stack.extend(node.decorator_list)
            continue
        if isinstance(node, _COMPREHENSIONS):
            stack.append(node.generators[0].iter)
            continue
        stack.extend(ast.iter_child_nodes(node))


def _rebound_nonlocal(body: list[ast.stmt]) -> set[str]:
    """The names a function nested at any depth in `body` declares `nonlocal` and writes:
    it may run at any time the enclosing body hands it on to, so that body cannot order
    those writes against its own reads. A name of a deeper function bound again between
    is counted too, which can only leave a value unknown."""
    found: set[str] = set()
    for node in (each for statement in body for each in ast.walk(statement)):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            own = list(_own_nodes(node.body))
            declared = {n for each in own if isinstance(each, ast.Nonlocal) for n in each.names}
            found |= declared & _assigned(own)
    return found


def _captures(pattern: ast.pattern, subject: CallArgument) -> list[tuple[str, CallArgument]]:
    """The names a `match` case's pattern binds, each with its value: the subject itself for
    a capture of the whole (`case Client() as s`, `case s`), and a part of it, which this
    scanner does not split, for every other (`case [s, *rest]`, `case {"k": s, **rest}`)."""
    found: list[tuple[str, CallArgument]] = []
    for node in ast.walk(pattern):
        if isinstance(node, ast.MatchAs | ast.MatchStar) and node.name:
            found.append((node.name, subject if node is pattern else _UNKNOWN))
        elif isinstance(node, ast.MatchMapping) and node.rest:
            found.append((node.rest, _UNKNOWN))
    return found


def _assigned(nodes: Iterable[ast.AST]) -> set[str]:
    """The names nodes of one scope write: Python makes each of them local."""
    found: set[str] = set()
    for node in nodes:
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store | ast.Del):
            found.add(node.id)
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            found.add(node.name)
        elif isinstance(node, ast.Import | ast.ImportFrom):
            found.update(
                (alias.asname or alias.name).partition(".")[0]
                for alias in node.names
                if alias.name != "*"
            )
        elif isinstance(node, ast.ExceptHandler | ast.MatchAs | ast.MatchStar) and node.name:
            found.add(node.name)
        elif isinstance(node, ast.MatchMapping) and node.rest:
            found.add(node.rest)
    return found


def is_stub_body(body: list[ast.stmt]) -> bool:
    """Whether a body is only `...`, `pass` and a docstring: no code to run."""
    return all(
        isinstance(node, ast.Pass)
        or (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Constant)
            and (node.value.value is Ellipsis or isinstance(node.value.value, str))
        )
        for node in body
    )


def _falls_through(body: list[ast.stmt]) -> bool:
    """Whether the end of `body` is reachable: no `return` or `raise` on every path."""
    return all(_statement_falls_through(node) for node in body)


def _statement_falls_through(node: ast.stmt) -> bool:
    if isinstance(node, ast.Return | ast.Raise):
        return False
    if isinstance(node, ast.If):
        return _falls_through(node.body) or _falls_through(node.orelse)
    if isinstance(node, ast.While):
        endless = isinstance(node.test, ast.Constant) and node.test.value is True
        return not endless or _breaks(node.body)
    if isinstance(node, ast.With | ast.AsyncWith):
        return _falls_through(node.body)
    if isinstance(node, ast.Try | ast.TryStar):
        tried = _falls_through(node.body + node.orelse) or any(
            _falls_through(handler.body) for handler in node.handlers
        )
        return tried and _falls_through(node.finalbody)
    if isinstance(node, ast.Match):
        irrefutable = any(
            isinstance(case.pattern, ast.MatchAs)
            and case.pattern.pattern is None
            and case.guard is None
            for case in node.cases
        )
        return not irrefutable or any(_falls_through(case.body) for case in node.cases)
    return True


def _breaks(body: list[ast.stmt]) -> bool:
    """Whether a `break` of this loop is in `body`: anywhere in it but a nested function,
    a class, or the body of a nested loop (whose `break`s are its own; its `else` is
    this loop's)."""
    for node in body:
        if isinstance(node, ast.Break):
            return True
        inner: list[ast.stmt] = []
        if isinstance(node, ast.If):
            inner = [*node.body, *node.orelse]
        elif isinstance(node, ast.For | ast.AsyncFor | ast.While):
            inner = node.orelse
        elif isinstance(node, ast.Try | ast.TryStar):
            handlers = [s for handler in node.handlers for s in handler.body]
            inner = [*node.body, *handlers, *node.orelse, *node.finalbody]
        elif isinstance(node, ast.With | ast.AsyncWith):
            inner = node.body
        elif isinstance(node, ast.Match):
            inner = [s for case in node.cases for s in case.body]
        if _breaks(inner):
            return True
    return False


def _raises_nothing(node: ast.stmt) -> bool:
    """Whether a statement can raise nothing of its own: `pass`, a jump, `global`, a
    docstring, or a `return` of a name or a constant."""
    if isinstance(node, ast.Pass | ast.Break | ast.Continue | ast.Global | ast.Nonlocal):
        return True
    if isinstance(node, ast.Expr):
        return isinstance(node.value, ast.Constant)
    if isinstance(node, ast.Return):
        return node.value is None or isinstance(node.value, ast.Constant | ast.Name)
    return False


def _only_a_call(node: ast.Expr | ast.Assign | ast.AnnAssign | ast.Return) -> bool:
    """Whether the statement is one call and nothing that may raise after it: `a()`,
    `x = a()`, `return a()`."""
    if isinstance(node, ast.Assign | ast.AnnAssign):
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if not all(isinstance(target, ast.Name) for target in targets):
            return False
    return isinstance(node.value, ast.Call)
