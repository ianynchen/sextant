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

A keyword argument is put at its parameter's position where this file writes the callee's
parameter list (a function or a class constructor of this file, by a `static` or `special`
call). Elsewhere it keeps its name in `keyword` (ruling R2), and the resolver binds it.

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
"""

import ast
import builtins
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from typing import Literal

from sextant.domain.closed_sets import ConstructKind
from sextant.domain.facts import (
    CallArgument,
    CallSiteFact,
    CallTarget,
    Fact,
    FieldWriteFact,
    MethodReturnFact,
    Signature,
)
from sextant.domain.symbols import PY_SIGNATURE, method_descriptor, names_a_type
from sextant.ingress.extract.python.flow import Flow
from sextant.ingress.extract.python.imports import (
    Binding,
    ModuleIndex,
    Target,
    bind_names,
    resolve,
)
from sextant.ingress.extract.python.typing_rules import (
    ANY,
    BUILTINS,
    UNION,
    TypeScope,
    type_ref,
    type_symbol,
)

INIT = "<init>"
CLINIT = "<clinit>"
# The name a call of a VALUE has: Python calls `type(value).__call__`.
CALL = "__call__"
# What `with x as y` binds `y` to: `type(x).__enter__(x)`.
_ENTER = "__enter__"
_ASYNC_ENTER = "__aenter__"
# The `dynamic` site an f-string or a string `+` is: its template is a `str.format` text.
_STRING = "builtins/str#"
_FORMAT = "format"
_HOLE = "{}"
# A keyword argument unpacked from a mapping (`f(**options)`): its names are not written.
_UNPACKED = "**"
# The name prefix javac gives a lambda body in a static initializer and in a constructor.
_PREFIXES = {CLINIT: "static", INIT: "new"}

_UNKNOWN = CallArgument(kind="unresolved")
# The receiver of a method (`self`, `cls`). It is never a parameter (D00 §5 numbering) and
# reads as `unresolved` where it is used as a value; only its identity is tested.
_SELF = CallArgument(kind="unresolved")

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


@dataclass
class Frame:
    """The names of one function body while it is read."""

    values: dict[str, CallArgument]
    local_names: set[str]
    # The owner type a written annotation gives a parameter or a local.
    declared: dict[str, str]
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


@dataclass(frozen=True)
class Params:
    """A callee's parameter list as this file writes it, receiver left out."""

    positional: tuple[str, ...]
    positional_only: int
    vararg: str | None
    keyword_only: tuple[str, ...]
    kwarg: str | None
    defaults: tuple[tuple[str, CallArgument], ...]

    @classmethod
    def of(cls, written: ast.arguments, *, skip_first: bool) -> "Params":
        ordered = [*written.posonlyargs, *written.args]
        defaults = dict(
            zip(
                [a.arg for a in ordered][len(ordered) - len(written.defaults) :],
                [_default(d) for d in written.defaults],
                strict=True,
            )
        )
        for argument, default in zip(written.kwonlyargs, written.kw_defaults, strict=True):
            if default is not None:
                defaults[argument.arg] = _default(default)
        skipped = 1 if skip_first and ordered else 0
        return cls(
            positional=tuple(a.arg for a in ordered[skipped:]),
            positional_only=max(len(written.posonlyargs) - skipped, 0),
            vararg=written.vararg.arg if written.vararg else None,
            keyword_only=tuple(a.arg for a in written.kwonlyargs),
            kwarg=written.kwarg.arg if written.kwarg else None,
            defaults=tuple(defaults.items()),
        )

    def bind(
        self, positional: list[CallArgument], keywords: list[tuple[str, CallArgument]]
    ) -> list[CallArgument] | None:
        """One argument per parameter, in parameter order, or None where Python would
        refuse the call or where a keyword goes into `**kwargs`. A parameter the call
        leaves out has its default; `*args` is one `array`, as a JVM varargs slot is."""
        slots: dict[str, CallArgument] = {}
        extra: list[CallArgument] = []
        for position, value in enumerate(positional):
            if position < len(self.positional):
                slots[self.positional[position]] = value
            elif self.vararg is not None:
                extra.append(value)
            else:
                return None
        if self.vararg is not None:
            slots[self.vararg] = CallArgument(kind="array", elements=extra)
        named = (*self.positional[self.positional_only :], *self.keyword_only)
        for name, value in keywords:
            if name not in named or name in slots:
                return None
            slots[name] = value
        if self.kwarg is not None:
            # A mapping, empty here: the grammar has no kind for a mapping.
            slots[self.kwarg] = _UNKNOWN
        defaults = dict(self.defaults)
        order = [
            *self.positional,
            *(name for name in (self.vararg,) if name is not None),
            *self.keyword_only,
            *(name for name in (self.kwarg,) if name is not None),
        ]
        bound = []
        for name in order:
            found = slots.get(name, defaults.get(name))
            if found is None:
                return None
            bound.append(found)
        return bound


class BodyReader:
    """Reads the statements and expressions of every body of one file. The declarations
    (symbols, signatures, class parents) are written by the subclass."""

    _context: FileContext
    facts: list[Fact]
    _signatures: dict[tuple[str, str], Params | None]
    # A nested function's or a lambda's bare descriptor, to its owner and name.
    _methods: dict[str, tuple[str, str]]
    # One counter set per method symbol: a name defined twice is one method with two
    # bodies, whose call ordinals, value ids and returns continue across both.
    _bodies: dict[str, Body]

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

    # -- known parameter lists ---------------------------------------------------------

    def _collect_signatures(self, body: list[ast.stmt], class_path: str | None = None) -> None:
        """The parameter lists this file writes for its module-level functions and its
        class constructors, read before any body, because a call runs after the whole
        module was read. A decorated definition, or a name defined twice, is not known:
        what the name holds is then not the written definition."""
        here = self._context.here
        for node in _top_statements(body):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and class_path is None:
                self._know((f"{here}#", node.name), node, skip_first=False)
            elif isinstance(node, ast.ClassDef):
                path = f"{class_path}.{node.name}" if class_path else node.name
                self._know_class(node, type_symbol(Target(here, path)))
                self._collect_signatures(node.body, path)

    def _know_class(self, node: ast.ClassDef, owner: str) -> None:
        inits = [
            s
            for s in _top_statements(node.body)
            if isinstance(s, ast.FunctionDef | ast.AsyncFunctionDef) and s.name == "__init__"
        ]
        if len(inits) == 1:
            self._know(
                (owner, INIT), inits[0], skip_first=True, decorated=bool(node.decorator_list)
            )

    def _know(
        self,
        key: tuple[str, str],
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        *,
        skip_first: bool,
        decorated: bool = False,
    ) -> None:
        if key in self._signatures or decorated or node.decorator_list:
            self._signatures[key] = None
        else:
            self._signatures[key] = Params.of(node.args, skip_first=skip_first)

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
    ) -> None:
        """A function's calls, returns and field writes, in its own method."""
        if not has_body:
            return
        frame = self._frame(node.args, node.body, scope, types, name, receiver_taken)
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
            a.arg: owner
            for a in ordered
            if a.annotation is not None
            for owner in (_owner(a.annotation, types),)
            if owner is not None
        }
        own = list(_own_nodes(body))
        for node in own:
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                owner = _owner(node.annotation, types)
                if owner is not None:
                    declared[node.target.id] = owner
        global_names = {n for node in own if isinstance(node, ast.Global) for n in node.names}
        outer = {n for node in own if isinstance(node, ast.Nonlocal) for n in node.names}
        local_names = (_assigned(own) | set(values)) - global_names - outer
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
                    if isinstance(node.value, ast.List) and isinstance(target, ast.Name):
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
            self._value(node.iter, scope)
            self._loop(node.body, node.orelse, scope, target=node.target)
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
            self._value(node.subject, scope)
            # A case's guard runs where its pattern matched; where the pattern or the guard
            # fails, the next case is tried.
            flow = scope.flow
            starts: list[int | None] = []
            untried = flow.here()
            for case in node.cases:
                flow.at(untried)
                if case.guard is not None:
                    self._value(case.guard, scope)
                starts.append(flow.here())
                irrefutable = isinstance(case.pattern, ast.MatchAs) and case.pattern.pattern is None
                untried = flow.join(
                    [
                        None if irrefutable else untried,
                        flow.here() if case.guard is not None else None,
                    ]
                )
            self._branches([case.body for case in node.cases] + [[]], scope, [*starts, untried])
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
    ) -> None:
        """Each body runs from the same names, and from `starts` in the control flow (by
        default, from where the branch is); after them, a name keeps a value only where
        every body that reaches the end gives it the same one, and is a `merge` where they
        give different ones."""
        frame = scope.frame
        flow = scope.flow
        if starts is None:
            starts = [flow.here()] * len(bodies)
        points: list[int | None] = []
        if frame is None:
            for body, start in zip(bodies, starts, strict=True):
                flow.at(start)
                self._statements(body, scope)
                points.append(flow.here())
            flow.join(points)
            return
        before = frame.values
        ends = []
        for body, start in zip(bodies, starts, strict=True):
            flow.at(start)
            frame.values = dict(before)
            self._statements(body, scope)
            points.append(flow.here())
            if flow.here() is not None:
                ends.append(frame.values)
        flow.join(points)
        frame.values = _join(ends) if ends else dict(before)

    def _loop(
        self,
        body: list[ast.stmt],
        orelse: list[ast.stmt],
        scope: Scope,
        *,
        target: ast.expr | None = None,
        test: ast.expr | None = None,
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
        flow.loop_tested(loop, endless=isinstance(test, ast.Constant) and bool(test.value))
        if target is not None:
            self._store(target, _UNKNOWN, scope)
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
            frame.values[target.id] = value
            frame.mutable.discard(target.id)
            if frame.writes:
                frame.writes[-1].setdefault(target.id, []).append(value)
        elif isinstance(target, ast.Tuple | ast.List):
            # Each name takes a part of the value, which this scanner does not split.
            for element in target.elts:
                self._store(element, _UNKNOWN, scope, evaluate=evaluate)
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
        for argument in node.args:
            if isinstance(argument, ast.Starred):
                self._value(argument.value, scope)
                positional.append(_UNKNOWN)
            else:
                positional.append(self._value(argument, scope))
        keywords = [(k.arg, self._value(k.value, scope)) for k in node.keywords]
        return self._invoke(callee, self._arguments(callee, node, positional, keywords), scope)

    def _arguments(
        self,
        callee: Callee,
        node: ast.Call,
        positional: list[CallArgument],
        keywords: list[tuple[str | None, CallArgument]],
    ) -> list[CallArgument]:
        """Arguments by position where this file writes the callee's parameters, else
        positional ones in order and then each keyword one with its name."""
        unpacked = any(isinstance(a, ast.Starred) for a in node.args)
        known = None
        if callee.invoke_kind in ("static", "special") and callee.target.owner is not None:
            known = self._signatures.get((callee.target.owner, str(callee.target.name)))
        named = [(name, value) for name, value in keywords if name is not None]
        if known is not None and not unpacked and len(named) == len(keywords):
            bound = known.bind(positional, named)
            if bound is not None:
                return bound
        return positional + [
            value.model_copy(update={"keyword": name or _UNPACKED}) for name, value in keywords
        ]

    def _invoke(self, callee: Callee, arguments: list[CallArgument], scope: Scope) -> CallArgument:
        """Write the call; the value it gives. A constructor gives the `instance` whose
        `source` is its receiver, as `new` does on the JVM (D00 §5)."""
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
            return CallArgument(kind="unresolved", source=result)
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
            if self._is_self(func.value, scope):
                return Callee(_target(scope.owner, func.attr), "virtual")
            owners = self._targets(func.value, scope) if _is_dotted(func.value) else None
            if owners is not None and len(owners) == 1:
                owner = owners[0]
                if owner.member is None or owner.kind == "class" or _is_builtin_class(owner):
                    return Callee(_target(type_symbol(owner), func.attr), "static")
                if owner.kind in (None, "variable"):
                    return Callee(
                        _target(None, func.attr),
                        "virtual",
                        scope.body.value_id(),
                        receiver_field=_field_of(owner),
                    )
            if owners is not None and len(owners) > 1:
                return Callee(
                    _target(None, func.attr),
                    "virtual",
                    scope.body.value_id(),
                    receiver_field=self._closed_list_field(func.value, scope),
                )
            value = self._value(func.value, scope)
            on_self = isinstance(func.value, ast.Attribute) and self._is_self(
                func.value.value, scope
            )
            return self._on_value(
                value, func.attr, scope, declared=self._declared(func.value, scope), on_self=on_self
            )
        if isinstance(func, ast.Name):
            if self._is_self(func, scope):
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
                    return Callee(
                        _target(None, CALL),
                        "virtual",
                        scope.body.value_id(),
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
        declared: str | None = None,
        on_self: bool = False,
    ) -> Callee:
        """A call named `name` on `value`. The owner is the type written for it where
        there is one; else it is left to the resolver, and the receiver is named."""
        if value.kind == "class" and value.symbol is not None:
            return Callee(_target(value.symbol, name), "static")
        if value.kind == "instance" and value.symbol is not None:
            return Callee(_target(value.symbol, name), "virtual", value.source)
        if value.kind in ("string", "concat"):
            declared = _STRING
        if value.kind == "parameter" and isinstance(value.value, int):
            return Callee(
                _target(declared, name),
                "virtual",
                None if declared is not None else scope.body.value_id(),
                receiver_parameter=value.value,
            )
        receiver = value.source if value.source is not None else scope.body.value_id()
        if value.kind == "field":
            return Callee(
                _target(declared, name),
                "virtual",
                receiver,
                receiver_field=value.symbol,
                receiver_field_kind="instance" if on_self else None,
            )
        return Callee(_target(declared, name), "virtual", receiver)

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
            if any(isinstance(element, ast.Starred) for element in node.elts):
                return _UNKNOWN
            return CallArgument(kind="array", elements=elements)
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
            self._value(generator.iter, scope)
            loops.append(flow.loop())
            flow.loop_tested(loops[-1])
            if lazy and len(loops) == 1:
                flow.defer(True)
            self._store(generator.target, _UNKNOWN, scope, evaluate=False)
            for condition in generator.ifs:
                self._value(condition, scope)
                flow.loop_test(loops[-1])
        parts = [node.key, node.value] if isinstance(node, ast.DictComp) else [node.elt]
        for part in parts:
            self._value(part, scope)
        if lazy:
            flow.defer(False)
        # An exhausted inner loop takes the outer loop's next element.
        for loop in reversed(loops):
            flow.loop_body_end(loop)
        flow.loop_end(loops[0])
        if frame is not None and saved is not None:
            frame.values, frame.local_names = saved
        return _UNKNOWN

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
                    current.values[name] = _UNKNOWN
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

    def _declared(self, node: ast.expr, scope: Scope) -> str | None:
        """The owner type written for a local name, where one is written."""
        if (
            isinstance(node, ast.Name)
            and scope.frame is not None
            and node.id in scope.frame.local_names
        ):
            return scope.frame.declared.get(node.id)
        return None


# -- helpers -------------------------------------------------------------------------------


def _target(owner: str | None, name: str) -> CallTarget:
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
    return _UNKNOWN


def _default(node: ast.expr) -> CallArgument:
    """A parameter's default as a caller's argument. It is evaluated where the function
    is defined, so only a literal is the same value in the caller."""
    return _constant(node.value) if isinstance(node, ast.Constant) else _UNKNOWN


def _merge(candidates: list[CallArgument]) -> CallArgument:
    """One of several values, identical ones folded (D00 §5 `merge`)."""
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
    if any(value == _UNKNOWN for value in values):
        return _UNKNOWN
    return _merge([c for value in values for c in (value.candidates or [value])])


def _owner(annotation: ast.expr, types: TypeScope) -> str | None:
    """The one class a written annotation names, as the owner of a call on that value.
    A union, `Any`, a type variable or an unnamed type gives none."""
    found = type_ref(annotation, types)
    if found is None or not names_a_type(found.symbol) or found.symbol in (UNION, ANY):
        return None
    return found.symbol


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


def _top_statements(body: Iterable[ast.stmt]) -> Iterator[ast.stmt]:
    """The statements of one scope, through `if`, `try`, `with`, loops and `match`."""
    for node in body:
        yield node
        if isinstance(node, ast.If | ast.For | ast.AsyncFor | ast.While):
            yield from _top_statements([*node.body, *node.orelse])
        elif isinstance(node, ast.Try | ast.TryStar):
            handlers = [s for handler in node.handlers for s in handler.body]
            yield from _top_statements([*node.body, *handlers, *node.orelse, *node.finalbody])
        elif isinstance(node, ast.With | ast.AsyncWith):
            yield from _top_statements(node.body)
        elif isinstance(node, ast.Match):
            yield from _top_statements([s for case in node.cases for s in case.body])


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
