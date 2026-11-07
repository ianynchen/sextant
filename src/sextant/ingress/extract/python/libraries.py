"""Library signatures and types for the Python scanner (spec 2026-11-06 §3e "Libraries").

The scanned module's libraries are read from the project's installed environment, the
`site-packages` folder the detector reports (`ScanRequest.dependency_archives`), and from
the pinned typeshed copy Sextant ships (`resources/typeshed`). Nothing is imported, run
or downloaded: a library file is parsed with `ast`, as a module file is.

- **Which libraries:** each distribution the module declares and the environment holds,
  found by its `*.dist-info/RECORD`; and the standard library, from typeshed's `stdlib`
  (its `VERSIONS` file says which modules the environment's Python has). A declared
  library that is not installed has no symbols, so a name imported from it stays as the
  import line writes it (the detector says it is not installed).
- **Which files:** a type file (`.pyi`) before a source file. A distribution that ships
  no types (no `py.typed` marker) is read from its typeshed stub package where typeshed
  has one (`requests`).
- **Defining symbols:** a library name is always its defining symbol. A re-export is
  followed through the library's own imports (`from .routing import APIRouter`), into any
  distribution the environment holds, and through star imports (`__all__`, else every
  name not starting with `_`). A name the library binds differently in branches is the
  closed list of its bindings.
- **Lazily:** only the modules a name of the scanned module leads to are read, and each
  once. Their signatures are used inside the scanner only, to type the module's own call
  sites, values and returns.
- **Headers, as on the JVM (ruled A, 2026-11-06):** what is written of a library is one
  `type_header` (D00 §5) per library type the module refers to, then transitively up its
  bases, each with its `origin` (the distribution, or `typeshed@<commit>/<stub
  package>@<version>`). No library member, document or `symbol` fact is written: a
  library's bodies are read only when the module opts in (`extract_libraries`, D04 §2a).
- **Overloads:** a call's return type is the one overload the argument types choose, as
  a type checker chooses: the first that matches. An argument whose type is not known,
  where the overloads that match give it different parameter types, leaves the closed
  list of what those overloads return (`narrowed`). A literal is not callable, so it
  never fits a `Callable` parameter.
- **Callables (design 2026-11-06-reading-decorators §3b):** a return written
  `Callable[[P, ...], R]` is a callable whose call gives `R` (a decorator factory's
  result: `click.group()` returns `Callable[[F], Group]`). `R` is a class, or a type
  variable the call's arguments fill; the scanner reads the call (`calls.py`).

A `sys.version_info` test in a type file is read against the environment's Python (its
`site-packages` path names it); a `sys.platform` test is not decided, so both branches
are read.
"""

import ast
import builtins
import posixpath
import re
import sys
import tomllib
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from sextant.application.ports.detector import LibraryRoot
from sextant.domain.closed_sets import ConstructKind
from sextant.domain.facts import (
    CallArgument,
    CallSiteFact,
    Fact,
    FieldWriteFact,
    MethodReturnFact,
    SymbolFact,
    TypeHeaderFact,
    TypeRef,
)
from sextant.domain.symbols import (
    NOT_APPLICABLE,
    PYTHON_SCHEME,
    bare_descriptor,
    is_type_descriptor,
    names_a_type,
    without_type_marker,
)
from sextant.ingress.extract.python.calls import FileContext
from sextant.ingress.extract.python.imports import (
    Binding,
    CallableType,
    ModuleIndex,
    Returned,
    Target,
    bind_names,
)
from sextant.ingress.extract.python.structure import file_facts
from sextant.ingress.extract.python.typing_rules import (
    BUILTINS,
    TypeScope,
    written_type,
)

_PACKAGE_MANAGER = "pypi"
_TYPED_MARKER = "py.typed"
_STUB_METADATA = "METADATA.toml"
_SOURCE_SUFFIXES = (".pyi", ".py")
# One line of typeshed's `stdlib/VERSIONS`: `module: 3.7-` or `module: 3.0-3.11`.
_VERSIONS_LINE = re.compile(r"\s*([\w.]+)\s*:\s*(\d+\.\d+)\s*-\s*(\d+\.\d+)?")
# Python's root type: every class has it and no base list writes it, so it gets no header,
# as the JVM's root type gets none (D00 §5 `type_header`).
_C3_ROOT = "builtins/object#"
# The kinds of library declaration a header is written for: a type (a Python module is a
# type, ruling R4), never a member.
_TYPE_KINDS = frozenset(
    {ConstructKind.CLASS, ConstructKind.PROTOCOL, ConstructKind.ENUM, ConstructKind.MODULE}
)
# The kinds of argument whose type a call site states, with the Python value they hold.
_LITERAL_KINDS = frozenset({"string", "int", "long", "boolean", "null", "concat"})
# The builtin classes a literal argument is checked against, and the literal types each
# accepts (`bool` is a subtype of `int`, and `int` is accepted where `float` is written).
_ACCEPTS: dict[str, tuple[type, ...]] = {
    "bool": (bool,),
    "int": (int,),
    "float": (int, float),
    "complex": (int, float, complex),
    "str": (str,),
    "bytes": (bytes,),
}


@dataclass(frozen=True)
class _Provider:
    """Where the files of one top-level import name come from, and what their facts
    record: the folder import paths are relative to, the `origin`, and the package and
    version that prefix their symbols and name their headers."""

    root: Path
    origin: str
    package: str
    version: str


@dataclass(frozen=True)
class _Source:
    module: str
    path: Path
    is_package: bool
    provider: _Provider


# One way a library module binds a name: `("own", kind)` for a definition, `("from", module,
# name)` for an imported name and `("module", path)` for an imported module.
type _Entry = tuple[str, ...]


@dataclass
class _Table:
    """The names one library module binds at its top level, without following them. A
    name that branches bind differently (a platform test, a `try` with an `except
    ImportError` fallback) has each binding, in written order: a closed list, as
    `imports.py` reads a name of the scanned module. Also the modules it star-imports,
    its `__all__` where it writes one, and the value of each name it assigns."""

    source: _Source
    tree: ast.Module
    names: dict[str, tuple[_Entry, ...]] = field(default_factory=dict)
    stars: list[str] = field(default_factory=list)
    exports: frozenset[str] | None = None
    values: dict[str, list[ast.expr]] = field(default_factory=dict)
    # Read on first use: the names as the scanner binds them, for a written type.
    scope: TypeScope | None = None


type _Function = tuple[_Table, Target, list[ast.FunctionDef | ast.AsyncFunctionDef]]


class Libraries:
    """The libraries of one scan (one environment), read lazily and each module once."""

    def __init__(
        self,
        archives: Sequence[LibraryRoot],
        typeshed: Path,
        environment: Path | None = None,
    ) -> None:
        self._typeshed = typeshed
        self._commit = (typeshed / "COMMIT").read_text(encoding="utf-8").strip()
        self._site = _site_packages(environment) or (archives[0].archive if archives else None)
        self._python = _python_version(environment, self._site)
        self._stdlib = _stdlib_versions(typeshed / "stdlib" / "VERSIONS")
        self._stubs = {
            _normalize(folder.name): folder
            for folder in sorted((typeshed / "stubs").iterdir())
            if (folder / _STUB_METADATA).is_file()
        }
        self._installed: dict[str, LibraryRoot] = {}
        for library in archives:
            for top in top_level_names(library):
                self._installed.setdefault(top, library)
        self._declared = frozenset(self._installed)
        # Every other distribution of the environment, by import name: read only where a
        # re-export of a declared one leads, and listed on first need.
        self._others: dict[str, LibraryRoot] | None = None
        # Where a name the scan follows is defined in a distribution that is not installed.
        self.notes: list[str] = []
        # Set while a library's own file is read: its names may lead into any installed
        # distribution, where a name of the scanned module starts only from a declared one.
        self._inside = False
        self._providers: dict[str, _Provider | None] = {}
        self._sources: dict[str, _Source | None] = {}
        self._tables: dict[str, _Table | None] = {}
        # The file names in each folder a module was looked for in, read once.
        self._listings: dict[Path, frozenset[str]] = {}
        self._index = ModuleIndex(frozenset(), self)
        # Each library module's own `symbol` facts, read once: where a header's construct
        # kind and written bases come from. They are not written.
        self._symbols: dict[str, dict[str, SymbolFact]] = {}
        # A call's callee, read once however many calls name it (GUIDELINES §8.7).
        self._functions: dict[tuple[str, str], _Function | None] = {}
        self._recording = True

    @property
    def identity(self) -> str:
        """What the header read reads: the declared distributions and their versions, the
        environment's Python and the typeshed commit, one per line."""
        lines = [f"typeshed {self._commit}", f"python {self._python[0]}.{self._python[1]}"]
        lines += sorted(
            {f"{library.coordinate} {library.version}" for library in self._installed.values()}
        )
        return "\n".join(lines)

    # -- the scanner's questions (`imports.LibraryNames`) ------------------------------

    def member(self, target: Target, name: str) -> tuple[Target, ...] | None:
        top = target.module.partition("/")[0]
        if not self._inside and top not in self._declared and top not in self._stdlib:
            return None
        if target.member is None:
            submodule = f"{target.module}/{name}" if target.module else name
            if self._source(submodule) is not None:
                return (Target(submodule),)
            return self._defining(target.module, name, set()) or None
        if self._is_class(target.module, target.member):
            return (Target(target.module, f"{target.member}.{name}"),)
        return None

    def call_returns(
        self, owner: str, name: str, arguments: Sequence[CallArgument], *, unpacked: bool = False
    ) -> Returned | None:
        key = (owner, name)
        if key not in self._functions:
            self._functions[key] = self._function(owner, name)
        known = self._functions[key]
        if known is None:
            return None
        table, target, defined = known
        recording, self._recording = self._recording, False
        inside, self._inside = self._inside, True
        try:
            found = self._choose(
                defined,
                list(arguments),
                self._scope(table),
                method=target.member is not None,
                unpacked=unpacked or any(a.keyword == _UNPACKED for a in arguments),
            )
        finally:
            self._recording = recording
            self._inside = inside
        if found is None or not all(self._gives_a_class(t) for t in found.types):
            # A type variable (`-> _T`), a special form or a name no library read defines:
            # what the call returns depends on more than the signature says.
            return None
        return found

    def _gives_a_class(self, returned: TypeRef | CallableType) -> bool:
        """A class; or a callable whose call gives a class, or a type variable that one of
        its own parameters fills, so the call's argument decides it."""
        if isinstance(returned, TypeRef):
            return self._names_a_class(returned.symbol)
        result = returned.returns.symbol
        if names_a_type(result):
            return self._names_a_class(result)
        return any(parameter.symbol == result for parameter in returned.parameters or ())

    def _function(self, owner: str, name: str) -> _Function | None:
        """Each written definition of the function `owner.name` (its `@overload` stubs
        among them), with the module it is in."""
        target = self._target_of(owner)
        if target is None:
            return None
        table = self._table(target.module)
        if table is None:
            return None
        body = table.tree.body if target.member is None else self._class_body(table, target)
        if body is None:
            return None
        defined = [
            node
            for node in _statements(body, self._python)
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name == name
        ]
        return (table, target, defined) if defined else None

    # -- overloads -----------------------------------------------------------------------

    def _choose(
        self,
        defined: list[ast.FunctionDef | ast.AsyncFunctionDef],
        arguments: list[CallArgument],
        scope: TypeScope,
        *,
        method: bool,
        unpacked: bool,
    ) -> Returned | None:
        """The return of the one overload the arguments choose, else the closed list of
        the returns of those they leave. A function with no `@overload` that branches
        define differently is several definitions: each is one of the closed list."""
        overloads = [node for node in defined if _is_overload(node)]
        alternatives = not overloads
        candidates = overloads or defined
        if unpacked:
            # `*args` or `**options`: how many arguments, and which names, is not known.
            return self._returned(candidates, scope)
        matches: list[tuple[ast.FunctionDef | ast.AsyncFunctionDef, dict[int, ast.expr | None]]]
        matches = []
        # Per match, the positions whose fit this rule cannot decide.
        undecided: set[int] = set()
        for node in candidates:
            bound = _bind_arguments(node, arguments, method=method)
            if bound is None:
                continue
            fits = {
                position: self._fits(_value(arguments[position]), annotation, scope, _DEPTH)
                for position, annotation in bound.items()
                if position != _RECEIVER and _value(arguments[position]) is not _UNKNOWN_VALUE
            }
            if any(fit is False for fit in fits.values()):
                continue
            undecided |= {position for position, fit in fits.items() if fit is None}
            matches.append((node, bound))
        if not matches:
            return None
        if alternatives:
            return self._returned([node for node, _ in matches], scope)
        # An argument of unknown type, or one whose fit is not decided here (an alias or a
        # protocol this rule does not read), decides nothing where every match gives its
        # parameter the same written type; then the first match is the one a type checker
        # takes. The receiver is one such argument: an overload that writes a type for
        # `self` (`def lower(self: LiteralString)`) is chosen by it.
        unknown = [p for p, argument in enumerate(arguments) if _value(argument) is _UNKNOWN_VALUE]
        deciding = any(
            len({_text(bound.get(position)) for _, bound in matches}) > 1
            for position in [_RECEIVER, *unknown, *sorted(undecided)]
        )
        return self._returned([node for node, _ in (matches if deciding else matches[:1])], scope)

    def _returned(
        self, chosen: list[ast.FunctionDef | ast.AsyncFunctionDef], scope: TypeScope
    ) -> Returned | None:
        types: list[TypeRef | CallableType] = []
        for node in chosen:
            if node.returns is None:
                return None
            returned = _callable(node.returns, scope) or written_type(node.returns, scope)
            if returned not in types:
                types.append(returned)
        return Returned(tuple(types), "narrowed" if len(types) > 1 else "resolved")

    def _fits(
        self, value: object, annotation: ast.expr | None, scope: TypeScope, depth: int
    ) -> bool | None:
        """Whether a literal argument fits the written type: True, False, or None where
        this rule cannot say (a protocol, a type variable, a class it does not read). An
        alias is read through to what it names, in its own module."""
        if annotation is None:
            return True
        if depth == 0:
            return None
        if isinstance(annotation, ast.BinOp) and isinstance(annotation.op, ast.BitOr):
            return _any_fits(
                [self._fits(value, part, scope, depth - 1) for part in _alternatives(annotation)]
            )
        if isinstance(annotation, ast.Constant):
            if annotation.value is None:
                return value is None
            if isinstance(annotation.value, str):
                try:
                    written = ast.parse(annotation.value.strip(), mode="eval").body
                except SyntaxError:
                    return None
                return self._fits(value, written, scope, depth - 1)
            return None
        if isinstance(annotation, ast.Subscript):
            return self._fits_form(value, annotation, scope, depth)
        if not _is_name(annotation):
            return None
        targets = scope.lookup(annotation)
        if len(targets) != 1:
            return None
        target = targets[0]
        if _is_callable_form(target):
            # A function and a class are callable; no literal is.
            return value is _FUNCTION_VALUE or value is _CLASS_VALUE
        if target.module == BUILTINS:
            return _fits_builtin(value, target.member or "")
        if target.module in _TYPING and target.member in ("Any", "LiteralString"):
            return target.member == "Any" or isinstance(value, str) or value is _SOME_TEXT
        alias = self._alias(target)
        if alias is None:
            return None
        written, alias_scope = alias
        return self._fits(value, written, alias_scope, depth - 1)

    def _fits_form(
        self, value: object, annotation: ast.Subscript, scope: TypeScope, depth: int
    ) -> bool | None:
        written = (
            list(annotation.slice.elts)
            if isinstance(annotation.slice, ast.Tuple)
            else [annotation.slice]
        )
        targets = scope.lookup(annotation.value) if _is_name(annotation.value) else ()
        if len(targets) != 1:
            return None
        target = targets[0]
        if _is_callable_form(target):
            return value is _FUNCTION_VALUE or value is _CLASS_VALUE
        if target.module in _TYPING:
            if target.member == "Literal":
                if value is _SOME_TEXT:
                    return None
                return any(
                    isinstance(part, ast.Constant)
                    and type(part.value) is type(value)
                    and part.value == value
                    for part in written
                )
            if target.member == "Optional":
                return _any_fits([value is None, self._fits(value, written[0], scope, depth - 1)])
            if target.member == "Union":
                return _any_fits([self._fits(value, part, scope, depth - 1) for part in written])
            if target.member == "Annotated":
                return self._fits(value, written[0], scope, depth - 1)
            return None
        # A generic class (`list[str]`): the literal fits its class or does not.
        return self._fits(value, annotation.value, scope, depth - 1)

    def _alias(self, target: Target) -> tuple[ast.expr, TypeScope] | None:
        """What a library name assigned once to a type names (`OpenTextMode = ...`), with
        the names of its module; None where it is not one such name."""
        if target.member is None or "." in target.member:
            return None
        defined = self._defining(target.module, target.member, set())
        if len(defined) != 1 or defined[0].member is None:
            return None
        table = self._table(defined[0].module)
        if table is None:
            return None
        values = table.values.get(defined[0].member, [])
        entries = table.names.get(defined[0].member, ())
        if len(values) != 1 or entries != (("own", "variable"),):
            return None
        return values[0], self._scope(table)

    # -- the facts -----------------------------------------------------------------------

    def headers(
        self, referenced: Iterable[str], own: set[str], document_id: str
    ) -> tuple[list[TypeHeaderFact], int, list[str]]:
        """A `type_header` (D00 §5) for every library type the module refers to, then
        transitively up each one's written bases, as the JVM scanner reads a classpath:
        the symbol, construct kind, `superclass` and `interfaces` mapped from the bases as
        the scanner maps a module class's (first base `superclass`, the rest `interfaces`,
        `object` not written), no annotation (a decorator is a call), and the `origin`.
        Also how many referenced types no library holds (`type_headers_unlocated`), and a
        line for each library class whose bases are not all read: `type_header` has no
        key to say so, so it gets no header, and a lookup reaching it ends there."""
        facts: list[TypeHeaderFact] = []
        unlocated = 0
        not_read: list[str] = []
        seen = set(own) | {_C3_ROOT}
        queue = [symbol for symbol in sorted(set(referenced)) if symbol not in seen]
        seen.update(queue)
        while queue:
            symbol = queue.pop(0)
            found = self._declaration(symbol)
            if found is None:
                unlocated += 1
                continue
            declared, provider = found
            if declared.parents_unread is not None:
                not_read.append(
                    f"{without_type_marker(symbol).replace('/', '.').replace('$', '.')}: "
                    f"{declared.parents_unread.detail}; no type header is written for it"
                )
                continue
            facts.append(
                TypeHeaderFact(
                    document_id=document_id,
                    symbol=declared.symbol,
                    construct_kind=declared.construct_kind,
                    superclass=declared.superclass,
                    interfaces=declared.interfaces,
                    origin=provider.origin,
                    version=provider.version,
                )
            )
            for parent in [declared.superclass, *declared.interfaces]:
                bare = bare_descriptor(parent) if parent is not None else None
                if bare is not None and bare not in seen:
                    seen.add(bare)
                    queue.append(bare)
        return facts, unlocated, not_read

    def _declaration(self, symbol: str) -> tuple[SymbolFact, _Provider] | None:
        """The library's own `symbol` fact for the type `symbol` (a class or a module),
        read as the scanner reads a module file, and where it was read from."""
        target = self._target_of(symbol)
        if target is None:
            return None
        table = self._table(target.module)
        if table is None:
            return None
        declared = self._module_symbols(table).get(symbol)
        if declared is None or declared.construct_kind not in _TYPE_KINDS:
            return None
        return declared, table.source.provider

    def _module_symbols(self, table: _Table) -> dict[str, SymbolFact]:
        module = table.source.module
        if module not in self._symbols:
            source = table.source
            provider = source.provider
            manager = NOT_APPLICABLE if provider.package == NOT_APPLICABLE else _PACKAGE_MANAGER
            prefix = f"{PYTHON_SCHEME} {manager} {provider.package} {provider.version} "
            context = FileContext(module, source.is_package, self._index, prefix, "")
            recording, self._recording = self._recording, False
            inside, self._inside = self._inside, True
            try:
                read = file_facts(table.tree, context, 1)
            finally:
                self._recording = recording
                self._inside = inside
            self._symbols[module] = {
                bare_descriptor(fact.symbol): fact
                for fact in read.facts
                if isinstance(fact, SymbolFact)
            }
        return self._symbols[module]

    # -- reading -------------------------------------------------------------------------

    def _defining(self, module: str, name: str, seen: set[tuple[str, str]]) -> tuple[Target, ...]:
        """Where `module.name` is defined, through the module's imports and star imports:
        one target, or the closed list where branches bind it differently. Empty where no
        library read says."""
        if (module, name) in seen:
            return ()
        seen.add((module, name))
        table = self._table(module)
        if table is None:
            return ()
        entries = table.names.get(name)
        if entries is None:
            # A star import gives the names its module lists in `__all__`, or with no
            # `__all__` every name not starting with `_`.
            return _distinct(
                target
                for star in table.stars
                if self._exports(star, name)
                for target in self._defining(star, name, set(seen))
            )
        return _distinct(
            target for entry in entries for target in self._entry(module, name, entry, seen)
        )

    def _entry(
        self, module: str, name: str, entry: _Entry, seen: set[tuple[str, str]]
    ) -> tuple[Target, ...]:
        if entry[0] == "own":
            return (Target(module, name),)
        if entry[0] == "module":
            return (Target(entry[1]),) if self._source(entry[1]) is not None else ()
        base, original = entry[1], entry[2]
        submodule = f"{base}/{original}" if base else original
        if self._source(submodule) is not None:
            return (Target(submodule),)
        top = base.partition("/")[0]
        if base and self._provider(top) is None:
            # Defined in a distribution this environment does not hold: the name is the
            # one the library's own import gives, and the scan says it was not read.
            if self._recording:
                note = (
                    f"{module.replace('/', '.')}.{name}: defined in {top}, "
                    "which is not installed in the scanned environment"
                )
                if note not in self.notes:
                    self.notes.append(note)
            return (Target(base, original),)
        return self._defining(base, original, seen)

    def _exports(self, module: str, name: str) -> bool:
        table = self._table(module)
        if table is None:
            return False
        if table.exports is not None:
            return name in table.exports
        return not name.startswith("_")

    def _is_class(self, module: str, member: str) -> bool:
        table = self._table(module)
        return table is not None and self._class_body(table, Target(module, member)) is not None

    def _class_body(self, table: _Table, target: Target) -> list[ast.stmt] | None:
        body: list[ast.stmt] = table.tree.body
        for part in (target.member or "").split("."):
            found = next(
                (
                    node
                    for node in _statements(body, self._python)
                    if isinstance(node, ast.ClassDef) and node.name == part
                ),
                None,
            )
            if found is None:
                return None
            body = found.body
        return body

    def _target_of(self, symbol: str) -> Target | None:
        """The module or class a type symbol of a library names."""
        path = without_type_marker(symbol)
        if self._source(path) is not None:
            return Target(path)
        module, _, member = path.rpartition("/")
        if module and self._source(module) is not None:
            return Target(module, member.replace("$", "."))
        return None

    def _names_a_class(self, symbol: str) -> bool:
        target = self._target_of(symbol)
        return (
            target is not None
            and target.member is not None
            and self._is_class(target.module, target.member)
        )

    def _scope(self, table: _Table) -> TypeScope:
        if table.scope is None:
            source = table.source
            names: dict[str, Binding] = bind_names(
                table.tree.body, source.module, is_package=source.is_package, index=self._index
            )
            table.scope = TypeScope(names=names, here=source.module, index=self._index)
        return table.scope

    def _table(self, module: str) -> _Table | None:
        if module in self._tables:
            return self._tables[module]
        source = self._source(module)
        table = None
        if source is not None:
            try:
                tree = ast.parse(source.path.read_bytes(), filename=str(source.path))
            except (OSError, SyntaxError, ValueError, RecursionError):
                tree = None
            if tree is not None:
                table = _Table(source, tree)
                package = module if source.is_package else module.rpartition("/")[0]
                _bind(tree.body, table, package, self._python)
        self._tables[module] = table
        return table

    def _source(self, module: str) -> _Source | None:
        if module in self._sources:
            return self._sources[module]
        found = None
        provider = self._provider(module.partition("/")[0]) if module else None
        if provider is not None and self._available(module, provider):
            base = provider.root / module
            candidates = [
                (base.with_name(base.name + suffix), False) for suffix in _SOURCE_SUFFIXES
            ]
            candidates += [(base / f"__init__{suffix}", True) for suffix in _SOURCE_SUFFIXES]
            for path, is_package in candidates:
                if self._is_file(path):
                    found = _Source(module, path, is_package, provider)
                    break
        self._sources[module] = found
        return found

    def _is_file(self, path: Path) -> bool:
        """Whether `path` is a file, its name matched exactly: on a file system that
        ignores case (macOS), `Child.py` must not find `child.py`."""
        folder = path.parent
        if folder not in self._listings:
            try:
                self._listings[folder] = frozenset(
                    entry.name for entry in folder.iterdir() if entry.is_file()
                )
            except OSError:
                self._listings[folder] = frozenset()
        return path.name in self._listings[folder]

    def _available(self, module: str, provider: _Provider) -> bool:
        """Whether the environment's Python has a standard library module (typeshed's
        `VERSIONS`); every other library module is there when its file is."""
        if provider.package != NOT_APPLICABLE:
            return True
        dotted = module.replace("/", ".")
        while dotted:
            if dotted in self._stdlib:
                low, high = self._stdlib[dotted]
                return low <= self._python and (high is None or self._python <= high)
            dotted = dotted.rpartition(".")[0]
        return False

    def _provider(self, top: str) -> _Provider | None:
        if top in self._providers:
            return self._providers[top]
        provider = None
        if top in self._stdlib:
            version = f"{self._python[0]}.{self._python[1]}"
            provider = _Provider(
                self._typeshed / "stdlib",
                f"typeshed@{self._commit}/stdlib@{version}",
                NOT_APPLICABLE,
                NOT_APPLICABLE,
            )
        elif top in self._installed:
            library = self._installed[top]
            stub = self._stubs.get(_normalize(library.coordinate))
            typed = (library.archive / top / _TYPED_MARKER).is_file()
            if stub is not None and not typed and _covers(stub, top):
                provider = _Provider(
                    stub,
                    f"typeshed@{self._commit}/{stub.name}@{_stub_version(stub)}",
                    library.coordinate,
                    library.version,
                )
            else:
                provider = _Provider(
                    library.archive,
                    library.coordinate,
                    library.coordinate,
                    library.version,
                )
        elif (other := self._other_distributions().get(top)) is not None:
            provider = _Provider(
                other.archive,
                other.coordinate,
                other.coordinate,
                other.version,
            )
        self._providers[top] = provider
        return provider

    def _other_distributions(self) -> dict[str, LibraryRoot]:
        """Every distribution of the environment the module does not declare, by import
        name, from each `*.dist-info` (`METADATA`'s name and version, `RECORD`'s files)."""
        if self._others is None:
            self._others = {}
            for info in sorted(self._site.glob("*.dist-info")) if self._site else []:
                name, version = _name_and_version(info)
                if name is None or version is None:
                    continue
                library = LibraryRoot(coordinate=name, version=version, archive=info.parent)
                for top in top_level_names(library):
                    if top not in self._installed:
                        self._others.setdefault(top, library)
        return self._others


# -- the types the module refers to -------------------------------------------------------


def referenced_types(facts: Iterable[Fact]) -> set[str]:
    """Every type symbol, bare, that the module's own facts name: a call's owner, a class
    or an instance argument, a written base, a parameter or return type and its type
    arguments. The JVM scanner reads the same from a class file's constant pool."""
    found: set[str] = set()
    for fact in facts:
        if isinstance(fact, SymbolFact):
            for parent in [fact.superclass, *fact.interfaces]:
                if parent is not None:
                    found.add(parent)
            if fact.signature is not None:
                for parameter in fact.signature.parameters:
                    _type_symbols(parameter.type, found)
                    if parameter.erased_symbol is not None:
                        found.add(parameter.erased_symbol)
                if fact.signature.returns is not None:
                    _type_symbols(fact.signature.returns, found)
            for type_parameter in fact.type_parameters:
                for bound in type_parameter.bounds:
                    _type_symbols(bound, found)
        elif isinstance(fact, CallSiteFact):
            if fact.target.owner is not None:
                found.add(fact.target.owner)
            for argument in fact.arguments:
                _argument_symbols(argument, found)
        elif isinstance(fact, MethodReturnFact | FieldWriteFact) and fact.value is not None:
            _argument_symbols(fact.value, found)
    return {bare for bare in map(bare_descriptor, found) if is_type_descriptor(bare)}


def _type_symbols(written: TypeRef, into: set[str]) -> None:
    into.add(written.symbol)
    for argument in written.arguments:
        _type_symbols(argument, into)


def _argument_symbols(argument: CallArgument, into: set[str]) -> None:
    if argument.kind in ("class", "instance") and argument.symbol is not None:
        into.add(argument.symbol)
    for nested in [*(argument.candidates or []), *(argument.elements or [])]:
        _argument_symbols(nested, into)


# -- the top-level names of a library module ----------------------------------------------


def _bind(body: list[ast.stmt], table: _Table, package: str, python: tuple[int, int]) -> None:
    table.names = _bound(body, {}, table, package, python)


def _bound(
    body: list[ast.stmt],
    names: dict[str, tuple[_Entry, ...]],
    table: _Table,
    package: str,
    python: tuple[int, int],
) -> dict[str, tuple[_Entry, ...]]:
    """The names after `body` ran, read as `imports.py` reads a module: a later binding
    replaces an earlier one, and branches that bind a name differently add up. An `if` on
    the Python version is decided."""
    names = dict(names)
    for node in body:
        if isinstance(node, ast.If):
            decided = _version_test(node.test, python)
            if decided is None:
                branches = [
                    _bound(node.body, names, table, package, python),
                    _bound(node.orelse, names, table, package, python),
                ]
                names = _either(names, branches)
            else:
                chosen = node.body if decided else node.orelse
                names = _bound(chosen, names, table, package, python)
        elif isinstance(node, ast.Try | ast.TryStar):
            tried = _bound(
                node.orelse,
                _bound(node.body, names, table, package, python),
                table,
                package,
                python,
            )
            handled = [_bound(h.body, names, table, package, python) for h in node.handlers]
            names = _bound(
                node.finalbody, _either(names, [tried, *handled]), table, package, python
            )
        else:
            for name, entry in _bindings(node, table, package):
                names[name] = (entry,)
    return names


def _bindings(node: ast.stmt, table: _Table, package: str) -> list[tuple[str, _Entry]]:
    if isinstance(node, ast.ClassDef):
        return [(node.name, ("own", "class"))]
    if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
        return [(node.name, ("own", "function"))]
    if isinstance(node, ast.Assign | ast.AnnAssign | ast.TypeAlias | ast.AugAssign):
        targets = node.targets if isinstance(node, ast.Assign) else [_alias_name(node)]
        found: list[tuple[str, _Entry]] = []
        for target in targets:
            if not isinstance(target, ast.Name):
                continue
            if target.id == "__all__":
                table.exports = _listed(node.value, table.exports, isinstance(node, ast.AugAssign))
                continue
            if node.value is not None and not isinstance(node, ast.AugAssign):
                table.values.setdefault(target.id, []).append(node.value)
            found.append((target.id, ("own", "variable")))
        return found
    if isinstance(node, ast.Import):
        imported: list[tuple[str, _Entry]] = [
            (alias.asname, ("module", alias.name.replace(".", "/")))
            if alias.asname is not None
            else (alias.name.partition(".")[0], ("module", alias.name.partition(".")[0]))
            for alias in node.names
        ]
        return imported
    if isinstance(node, ast.ImportFrom):
        base = _from_base(node, package)
        if base is None:
            return []
        named: list[tuple[str, _Entry]] = []
        for alias in node.names:
            if alias.name == "*":
                table.stars.append(base)
            else:
                named.append((alias.asname or alias.name, ("from", base, alias.name)))
        return named
    return []


def _listed(
    value: ast.expr | None, before: frozenset[str] | None, added: bool
) -> frozenset[str] | None:
    """The names an `__all__` list or tuple of strings gives; None where it is not one."""
    if not isinstance(value, ast.List | ast.Tuple) or not all(
        isinstance(e, ast.Constant) and isinstance(e.value, str) for e in value.elts
    ):
        return None
    listed = frozenset(str(e.value) for e in value.elts if isinstance(e, ast.Constant))
    return (before or frozenset()) | listed if added else listed


def _either(
    before: dict[str, tuple[_Entry, ...]], branches: list[dict[str, tuple[_Entry, ...]]]
) -> dict[str, tuple[_Entry, ...]]:
    """`imports._either` for a library's names: a name a branch did not touch keeps its
    binding from before on that branch; different bindings are a closed list."""
    merged: dict[str, tuple[_Entry, ...]] = {}
    for name in dict.fromkeys(key for branch in branches for key in branch):
        entries: list[_Entry] = []
        for branch in branches:
            for entry in branch.get(name, before.get(name, ())):
                if entry not in entries:
                    entries.append(entry)
        merged[name] = tuple(entries)
    return {**before, **merged}


def _distinct(targets: Iterable[Target]) -> tuple[Target, ...]:
    return tuple(dict.fromkeys(targets))


def _alias_name(node: ast.AnnAssign | ast.TypeAlias | ast.AugAssign) -> ast.expr:
    return node.name if isinstance(node, ast.TypeAlias) else node.target


def _from_base(node: ast.ImportFrom, package: str) -> str | None:
    written = (node.module or "").replace(".", "/")
    if node.level == 0:
        return written
    for _ in range(node.level - 1):
        if not package:
            return None
        package = package.rpartition("/")[0]
    return "/".join(part for part in (package, written) if part)


def _statements(body: list[ast.stmt], python: tuple[int, int]) -> Iterator[ast.stmt]:
    """The statements of a module or class body that run: an `if` on the Python version
    is decided, any other `if` gives both branches; a `try` gives its every block."""
    for node in body:
        if isinstance(node, ast.If):
            decided = _version_test(node.test, python)
            if decided is None:
                yield from _statements(node.body, python)
                yield from _statements(node.orelse, python)
            else:
                yield from _statements(node.body if decided else node.orelse, python)
        elif isinstance(node, ast.Try | ast.TryStar):
            for block in (node.body, *(h.body for h in node.handlers), node.orelse):
                yield from _statements(block, python)
            yield from _statements(node.finalbody, python)
        else:
            yield node


def _version_test(test: ast.expr, python: tuple[int, int]) -> bool | None:
    """`sys.version_info >= (3, 11)` and its other comparisons, read against `python`;
    None for any other test."""
    if not (
        isinstance(test, ast.Compare)
        and len(test.ops) == 1
        and isinstance(test.left, ast.Attribute)
        and test.left.attr == "version_info"
        and isinstance(test.left.value, ast.Name)
        and test.left.value.id == "sys"
        and isinstance(test.comparators[0], ast.Tuple)
    ):
        return None
    try:
        written = tuple(int(ast.literal_eval(part)) for part in test.comparators[0].elts)
    except (ValueError, TypeError):
        return None
    running = python[: len(written)]
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


# -- distributions, typeshed ---------------------------------------------------------------


def _normalize(name: str) -> str:
    """PEP 503."""
    return re.sub(r"[-_.]+", "-", name).lower()


def _site_packages(environment: Path | None) -> Path | None:
    if environment is None:
        return None
    found = sorted((environment / "lib").glob("python*/site-packages"))
    return found[0] if found else None


def _python_version(environment: Path | None, site: Path | None) -> tuple[int, int]:
    """The environment's Python: `pyvenv.cfg`'s `version_info` (uv) or `version` (venv),
    else its `lib/python3.12/site-packages` path; the running one where there is no
    environment."""
    config = environment / "pyvenv.cfg" if environment is not None else None
    if config is not None and config.is_file():
        for line in config.read_text(encoding="utf-8", errors="replace").splitlines():
            key, _, value = line.partition("=")
            found = re.match(r"\s*(\d+)\.(\d+)", value)
            if key.strip() in ("version_info", "version") and found is not None:
                return int(found.group(1)), int(found.group(2))
    if site is not None:
        found = re.fullmatch(r"python(\d+)\.(\d+)t?", site.parent.name)
        if found is not None:
            return int(found.group(1)), int(found.group(2))
    return sys.version_info.major, sys.version_info.minor


def _stdlib_versions(path: Path) -> dict[str, tuple[tuple[int, int], tuple[int, int] | None]]:
    """typeshed's `VERSIONS`: each standard library module, the first Python that has it
    and the last, where it was removed."""
    found: dict[str, tuple[tuple[int, int], tuple[int, int] | None]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        # A comment line, or a blank one, does not match.
        written = _VERSIONS_LINE.match(line)
        if written is not None:
            module, low, high = written.groups()
            found[module] = (_version(low), _version(high) if high else None)
    return found


def _version(text: str) -> tuple[int, int]:
    major, _, minor = text.strip().partition(".")
    return int(major), int(minor)


def record_files(library: LibraryRoot) -> list[str] | None:
    """The `.py` files a distribution's `RECORD` lists, relative to its `site-packages`
    folder and sorted: exactly its own files, so a namespace folder another distribution
    shares (`google/`) gives none of the other's. None where the distribution has no
    `RECORD`, or one that cannot be read: its files are then not known."""
    coordinate = _normalize(library.coordinate)
    for info in sorted(library.archive.glob("*.dist-info")):
        if _normalize(info.name.removesuffix(".dist-info").rpartition("-")[0]) != coordinate:
            continue
        try:
            lines = (info / "RECORD").read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            return None
        files: set[str] = set()
        for line in lines:
            written = posixpath.normpath(line.partition(",")[0])
            # A script installed outside `site-packages` (`../../bin/x`) is not a module.
            if written.endswith(".py") and not written.startswith(("..", "/")):
                files.add(written)
        return sorted(files)
    return None


def top_level_names(library: LibraryRoot) -> list[str]:
    """The import names a distribution installs, from its `RECORD`: the first part of
    each `.py`, `.pyi` or package path it lists."""
    coordinate = _normalize(library.coordinate)
    for info in sorted(library.archive.glob("*.dist-info")):
        if _normalize(info.name.removesuffix(".dist-info").rpartition("-")[0]) != coordinate:
            continue
        record = info / "RECORD"
        if not record.is_file():
            return []
        names: set[str] = set()
        for line in record.read_text(encoding="utf-8", errors="replace").splitlines():
            path = line.partition(",")[0]
            top, separator, _ = path.partition("/")
            if top.endswith(".dist-info") or top.startswith((".", "__pycache__")):
                continue
            if separator or path.endswith(_SOURCE_SUFFIXES):
                names.add(top.removesuffix(".pyi").removesuffix(".py"))
        return sorted(name for name in names if name.isidentifier())
    return []


def _name_and_version(info: Path) -> tuple[str | None, str | None]:
    """`Name` (PEP 503) and `Version` from a `*.dist-info/METADATA`."""
    headers: dict[str, str] = {}
    metadata = info / "METADATA"
    if metadata.is_file():
        for line in metadata.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip():
                break
            key, _, value = line.partition(":")
            if key in ("Name", "Version") and key not in headers:
                headers[key] = value.strip()
    name = headers.get("Name")
    return (_normalize(name) if name else None), headers.get("Version")


def _covers(stub: Path, top: str) -> bool:
    return (stub / top).is_dir() or (stub / f"{top}.pyi").is_file()


def _stub_version(stub: Path) -> str:
    """The `version` a typeshed stub package's `METADATA.toml` states."""
    with (stub / _STUB_METADATA).open("rb") as handle:
        return str(tomllib.load(handle).get("version", NOT_APPLICABLE))


# -- overloads ------------------------------------------------------------------------------


def _is_overload(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    return any(
        (isinstance(d, ast.Name) and d.id == "overload")
        or (isinstance(d, ast.Attribute) and d.attr == "overload")
        for d in node.decorator_list
    )


def _bind_arguments(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    arguments: list[CallArgument],
    *,
    method: bool,
) -> dict[int, ast.expr | None] | None:
    """Each argument's parameter annotation (None where none is written), and for a
    method the receiver's at `_RECEIVER`; or None where the arguments do not fit the
    parameters: too many, a name it does not take, or a parameter with no default left
    out."""
    written = node.args
    static = any(isinstance(d, ast.Name) and d.id == "staticmethod" for d in node.decorator_list)
    positional = [*written.posonlyargs, *written.args]
    bound: dict[int, ast.expr | None] = {}
    if method and not static and positional:
        bound[_RECEIVER] = positional[0].annotation
        positional = positional[1:]
    defaults = len(written.defaults)
    optional = (
        {a.arg for a in [*written.posonlyargs, *written.args][-defaults:]} if defaults else set()
    )
    optional |= {
        a.arg for a, default in zip(written.kwonlyargs, written.kw_defaults) if default is not None
    }
    by_name = {a.arg: a for a in [*written.args, *written.kwonlyargs]}
    given: set[str] = set()
    place = 0
    for position, argument in enumerate(arguments):
        if argument.keyword is None:
            if place < len(positional):
                parameter = positional[place]
                place += 1
                given.add(parameter.arg)
                bound[position] = parameter.annotation
            elif written.vararg is not None:
                bound[position] = written.vararg.annotation
            else:
                return None
        elif argument.keyword in by_name and argument.keyword not in given:
            given.add(argument.keyword)
            bound[position] = by_name[argument.keyword].annotation
        elif written.kwarg is not None:
            bound[position] = written.kwarg.annotation
        else:
            return None
    required = [a.arg for a in [*positional, *written.kwonlyargs] if a.arg not in optional]
    if any(name not in given for name in required):
        return None
    return bound


_UNKNOWN_VALUE = object()
# A text argument whose value is not known (an f-string): it is a `str`, of no one literal.
_SOME_TEXT = object()
# A function (a `lambda` argument) and a class (a `class` argument): callable values whose
# own type is not read, so they fit a `Callable`, `object` and `Any`, and no literal type.
_FUNCTION_VALUE = object()
_CLASS_VALUE = object()
_TYPING = frozenset({"typing", "typing_extensions"})
_CALLABLE_MODULES = frozenset({*_TYPING, "collections/abc", "_collections_abc"})
# A bound on how far a written type and its aliases are followed.
_DEPTH = 16
# A keyword argument unpacked from a mapping (`f(**options)`), as `calls.py` writes it.
_UNPACKED = "**"
# Where `_bind_arguments` puts the receiver's written type (`self`), beside the arguments'
# positions.
_RECEIVER = -1


def _value(argument: CallArgument) -> object:
    """The Python value of an argument whose type the call site states."""
    if argument.kind == "lambda":
        return _FUNCTION_VALUE
    if argument.kind == "class":
        return _CLASS_VALUE
    if argument.kind not in _LITERAL_KINDS:
        return _UNKNOWN_VALUE
    if argument.kind == "null":
        return None
    if argument.kind == "concat":
        return _SOME_TEXT
    return argument.value


def _any_fits(fits: list[bool | None]) -> bool | None:
    """One of several types: fits where one fits, refuses where every one refuses."""
    if any(fit is True for fit in fits):
        return True
    return False if all(fit is False for fit in fits) else None


def _fits_builtin(value: object, name: str) -> bool | None:
    """A literal against a builtin class: by Python's own class of the value, with the
    typing specification's promotions (`int` where `float` is written)."""
    if name == "object":
        return True
    if value is _FUNCTION_VALUE:
        return False
    if value is _CLASS_VALUE:
        # A class is an instance of its metaclass, a `type`.
        return name == "type"
    if value is _SOME_TEXT:
        value = ""
    accepted = _ACCEPTS.get(name)
    if accepted is not None:
        return isinstance(value, accepted)
    written = getattr(builtins, name, None)
    if isinstance(written, type):
        return isinstance(value, written)
    return None


def _callable(annotation: ast.expr, scope: TypeScope) -> CallableType | None:
    """A return written `Callable[[P, ...], R]` (or `Callable[..., R]`), as the callable
    it is; None for any other return. `R` is kept only where it is a class name or a type
    variable: anything else (an alias, a special form) says nothing of what the call
    gives."""
    if isinstance(annotation, ast.Constant) and isinstance(annotation.value, str):
        try:
            annotation = ast.parse(annotation.value.strip(), mode="eval").body
        except SyntaxError:
            return None
    if not isinstance(annotation, ast.Subscript) or not _is_name(annotation.value):
        return None
    targets = scope.lookup(annotation.value)
    if len(targets) != 1 or not _is_callable_form(targets[0]):
        return None
    written = annotation.slice
    if not isinstance(written, ast.Tuple) or len(written.elts) != 2:
        return None
    parameters, result = written.elts
    returns = written_type(result, scope)
    if not names_a_type(returns.symbol) and not _is_type_variable(result, scope):
        return None
    # `...`, a `ParamSpec` or `Concatenate[...]`: the parameters are not listed.
    listed = (
        tuple(written_type(parameter, scope) for parameter in parameters.elts)
        if isinstance(parameters, ast.List)
        else None
    )
    return CallableType(listed, returns)


def _is_callable_form(target: Target) -> bool:
    """`typing.Callable` or `collections.abc.Callable`."""
    return target.member == "Callable" and target.module in _CALLABLE_MODULES


def _is_type_variable(node: ast.expr, scope: TypeScope) -> bool:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        try:
            node = ast.parse(node.value.strip(), mode="eval").body
        except SyntaxError:
            return False
    if not _is_name(node):
        return False
    targets = scope.lookup(node)
    return len(targets) == 1 and targets[0].kind == "type_variable"


def _alternatives(node: ast.expr) -> list[ast.expr]:
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return [*_alternatives(node.left), *_alternatives(node.right)]
    return [node]


def _is_name(node: ast.expr) -> bool:
    return isinstance(node, ast.Name | ast.Attribute)


def _text(annotation: ast.expr | None) -> str:
    return "" if annotation is None else ast.unparse(annotation)
