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
  followed through the library's own imports (`from .routing import APIRouter`), and a
  star import is followed where one module only defines the name.
- **Lazily:** only the modules a name of the scanned module leads to are read, and each
  once. A read module's facts are written beside the module's own, with `origin` naming
  the distribution, or `typeshed@<commit>/<stub package>@<version>`. They are the
  signatures and types only: `symbol` facts (classes with their written parents,
  functions and their `@overload` stubs with typed signatures, fields). Bodies are not
  written. A class's parents are read too, so a lookup can continue through them.
- **Overloads:** a call's return type is the one overload the argument types choose, as
  a type checker chooses: the first that matches. An argument whose type is not known,
  where the overloads that match give it different parameter types, leaves the closed
  list of what those overloads return (`narrowed`).

A `sys.version_info` test in a type file is read against the environment's Python (its
`site-packages` path names it); a `sys.platform` test is not decided, so both branches
are read.
"""

import ast
import hashlib
import re
import sys
import tomllib
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from sextant.application.ports.detector import LibraryRoot
from sextant.domain.closed_sets import OriginTier
from sextant.domain.facts import CallArgument, Document, Fact, SymbolFact, TypeRef
from sextant.domain.symbols import (
    NOT_APPLICABLE,
    PYTHON_SCHEME,
    bare_descriptor,
    names_a_type,
    without_type_marker,
)
from sextant.domain.version import FACT_SCHEMA_VERSION, SEXTANT_VERSION
from sextant.ingress.extract.python.calls import FileContext
from sextant.ingress.extract.python.imports import (
    Binding,
    ModuleIndex,
    Returned,
    Target,
    bind_names,
)
from sextant.ingress.extract.python.structure import file_facts
from sextant.ingress.extract.python.typing_rules import (
    ANY,
    BUILTINS,
    TypeScope,
    written_type,
)

_SCANNER_ID = "sextant-python-scanner"
_LANGUAGE = "python"
_PACKAGE_MANAGER = "pypi"
_NO_REDACTION_HASH = "sha256:none"
_TYPED_MARKER = "py.typed"
_STUB_METADATA = "METADATA.toml"
_SOURCE_SUFFIXES = (".pyi", ".py")
# One line of typeshed's `stdlib/VERSIONS`: `module: 3.7-` or `module: 3.0-3.11`.
_VERSIONS_LINE = re.compile(r"\s*([\w.]+)\s*:\s*(\d+\.\d+)\s*-\s*(\d+\.\d+)?")
# The folder under the fact root that library facts are written to (`facts/lib/`, which the
# analysis clears before every scan, so a library no longer read leaves nothing behind).
_LIBRARY_FOLDER = "lib"
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
    version that prefix their symbols."""

    root: Path
    origin: str
    package: str
    version: str
    # The folder under `facts/lib/` its facts are written to.
    folder: str


@dataclass(frozen=True)
class _Source:
    module: str
    path: Path
    is_package: bool
    provider: _Provider

    @property
    def relative(self) -> str:
        return self.path.relative_to(self.provider.root).as_posix()


@dataclass
class _Table:
    """The names one library module binds at its top level, without following them:
    `("own", kind)` for a definition, `("from", module, name)` for an imported name and
    `("module", path)` for an imported module; and the modules it star-imports."""

    source: _Source
    tree: ast.Module
    names: dict[str, tuple[str, ...]] = field(default_factory=dict)
    stars: list[str] = field(default_factory=list)
    # Read on first use: the names as the scanner binds them, for a written type.
    scope: TypeScope | None = None


type _Function = tuple[_Table, Target, list[ast.FunctionDef | ast.AsyncFunctionDef]]


class Libraries:
    """The libraries of one scan (one environment), read lazily and each module once."""

    def __init__(self, archives: Sequence[LibraryRoot], typeshed: Path) -> None:
        self._typeshed = typeshed
        self._commit = (typeshed / "COMMIT").read_text(encoding="utf-8").strip()
        site = archives[0].archive if archives else None
        self._python = _python_version(site)
        self._stdlib = _stdlib_versions(typeshed / "stdlib" / "VERSIONS")
        self._stubs = {
            _normalize(folder.name): folder
            for folder in sorted((typeshed / "stubs").iterdir())
            if (folder / _STUB_METADATA).is_file()
        }
        self._installed: dict[str, LibraryRoot] = {}
        for library in archives:
            for top in _top_level_names(library):
                self._installed.setdefault(top, library)
        self._providers: dict[str, _Provider | None] = {}
        self._sources: dict[str, _Source | None] = {}
        self._tables: dict[str, _Table | None] = {}
        self._index = ModuleIndex(frozenset(), self)
        # The modules whose facts are written, in the order a name first led to them.
        self._needed: dict[str, None] = {}
        # A call's callee, read once however many calls name it (GUIDELINES §8.7).
        self._functions: dict[tuple[str, str], _Function | None] = {}
        self._recording = True

    # -- the scanner's questions (`imports.LibraryNames`) ------------------------------

    def member(self, target: Target, name: str) -> Target | None:
        if target.member is None:
            submodule = f"{target.module}/{name}" if target.module else name
            if self._source(submodule) is not None:
                return Target(submodule)
            return self._defining(target.module, name, set())
        if self._is_class(target.module, target.member):
            return Target(target.module, f"{target.member}.{name}")
        return None

    def call_returns(
        self, owner: str, name: str, arguments: Sequence[CallArgument]
    ) -> Returned | None:
        key = (owner, name)
        if key not in self._functions:
            self._functions[key] = self._function(owner, name)
        known = self._functions[key]
        if known is None:
            return None
        table, target, defined = known
        recording, self._recording = self._recording, False
        try:
            scope = self._scope(table)
            found = _choose(defined, list(arguments), scope, method=target.member is not None)
        finally:
            self._recording = recording
        if found is None or not all(self._names_a_class(t.symbol) for t in found.types):
            # A type variable (`-> _T`), a special form or a name no library read defines:
            # what the call returns depends on more than the signature says.
            return None
        for returned in found.types:
            self._record_type(returned.symbol)
        return found

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

    # -- the facts -----------------------------------------------------------------------

    def documents(
        self, module_id: str, out_dir: Path
    ) -> Iterator[tuple[Path, Document, list[Fact]]]:
        """Each library module a name of the scan led to, as a document of its
        signatures and types, with the fact file it is written to. A class's parents are
        added as they are found, so the walk ends where the parents leave every library."""
        done: set[str] = set()
        while pending := [module for module in self._needed if module not in done]:
            for module in pending:
                done.add(module)
                written = self._document(module, module_id, out_dir)
                if written is not None:
                    yield written

    def _document(
        self, module: str, module_id: str, out_dir: Path
    ) -> tuple[Path, Document, list[Fact]] | None:
        table = self._table(module)
        if table is None:
            return None
        source = table.source
        provider = source.provider
        content = source.path.read_bytes()
        relative = source.relative
        document = Document(
            document_id=hashlib.sha256(f"{provider.origin}/{relative}".encode()).hexdigest(),
            relative_path=relative,
            module_id=module_id,
            language=_LANGUAGE,
            sextant_version=SEXTANT_VERSION,
            fact_schema_version=FACT_SCHEMA_VERSION,
            scanner_id=_SCANNER_ID,
            content_hash="sha256:" + hashlib.sha256(content).hexdigest(),
            origin_entry=str(provider.root),
            origin_tier=OriginTier.DEPENDENCY,
            redaction_set_hash=_NO_REDACTION_HASH,
            origin=provider.origin,
        )
        manager = NOT_APPLICABLE if provider.package == NOT_APPLICABLE else _PACKAGE_MANAGER
        prefix = f"{PYTHON_SCHEME} {manager} {provider.package} {provider.version} "
        context = FileContext(module, source.is_package, self._index, prefix, document.document_id)
        recording, self._recording = self._recording, False
        try:
            read = file_facts(table.tree, context, len(content.splitlines()) or 1)
        finally:
            self._recording = recording
        # Signatures and types only: the bodies (calls, values, returns) are not written.
        symbols = [fact for fact in read.facts if isinstance(fact, SymbolFact)]
        facts: list[Fact] = list(symbols)
        for fact in symbols:
            for parent in [fact.superclass, *fact.interfaces]:
                if parent is not None:
                    self._record_type(bare_descriptor(parent))
        if read.not_read:
            document = document.model_copy(
                update={"partial": True, "partial_reason": "\n".join(read.not_read)}
            )
        target = out_dir / _LIBRARY_FOLDER / provider.folder / f"{relative}.jsonl"
        return target, document, facts

    # -- reading -------------------------------------------------------------------------

    def _defining(self, module: str, name: str, seen: set[tuple[str, str]]) -> Target | None:
        """Where `module.name` is defined, through the module's imports and star imports;
        None where no library read says, or where two star imports both define it."""
        if (module, name) in seen:
            return None
        seen.add((module, name))
        table = self._table(module)
        if table is None:
            return None
        entry = table.names.get(name)
        if entry is None:
            found = {
                one
                for star in table.stars
                if (one := self._defining(star, name, set(seen))) is not None
            }
            return found.pop() if len(found) == 1 else None
        if entry[0] == "own":
            self._record(module)
            return Target(module, name)
        if entry[0] == "module":
            return Target(entry[1]) if self._source(entry[1]) is not None else None
        base, original = entry[1], entry[2]
        submodule = f"{base}/{original}" if base else original
        if self._source(submodule) is not None:
            return Target(submodule)
        return self._defining(base, original, seen)

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

    def _record(self, module: str) -> None:
        if self._recording:
            self._needed.setdefault(module)

    def _record_type(self, symbol: str) -> None:
        """Write the facts of the module that defines the class `symbol`."""
        if not names_a_type(symbol) or symbol == ANY:
            return
        target = self._target_of(symbol)
        if target is not None and target.member is not None:
            self._needed.setdefault(target.module)

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
                if path.is_file():
                    found = _Source(module, path, is_package, provider)
                    break
        self._sources[module] = found
        return found

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
                "typeshed/stdlib",
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
                    f"typeshed/{stub.name}",
                )
            else:
                provider = _Provider(
                    library.archive,
                    library.coordinate,
                    library.coordinate,
                    library.version,
                    f"{_PACKAGE_MANAGER}/{library.coordinate}",
                )
        self._providers[top] = provider
        return provider


# -- the top-level names of a library module ----------------------------------------------


def _bind(body: list[ast.stmt], table: _Table, package: str, python: tuple[int, int]) -> None:
    for node in _statements(body, python):
        if isinstance(node, ast.ClassDef):
            table.names[node.name] = ("own", "class")
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            table.names[node.name] = ("own", "function")
        elif isinstance(node, ast.Assign | ast.AnnAssign | ast.TypeAlias):
            targets = node.targets if isinstance(node, ast.Assign) else [_alias_name(node)]
            for target in targets:
                if isinstance(target, ast.Name):
                    table.names[target.id] = ("own", "variable")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname is not None:
                    table.names[alias.asname] = ("module", alias.name.replace(".", "/"))
                else:
                    head = alias.name.partition(".")[0]
                    table.names[head] = ("module", head)
        elif isinstance(node, ast.ImportFrom):
            base = _from_base(node, package)
            if base is None:
                continue
            for alias in node.names:
                if alias.name == "*":
                    table.stars.append(base)
                else:
                    table.names[alias.asname or alias.name] = ("from", base, alias.name)


def _alias_name(node: ast.AnnAssign | ast.TypeAlias) -> ast.expr:
    return node.target if isinstance(node, ast.AnnAssign) else node.name


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


def _python_version(site: Path | None) -> tuple[int, int]:
    """The environment's Python, from its `lib/python3.12/site-packages` path; the
    running one where there is no environment."""
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


def _top_level_names(library: LibraryRoot) -> list[str]:
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


def _covers(stub: Path, top: str) -> bool:
    return (stub / top).is_dir() or (stub / f"{top}.pyi").is_file()


def _stub_version(stub: Path) -> str:
    """The `version` a typeshed stub package's `METADATA.toml` states."""
    with (stub / _STUB_METADATA).open("rb") as handle:
        return str(tomllib.load(handle).get("version", NOT_APPLICABLE))


# -- overloads ------------------------------------------------------------------------------


def _choose(
    defined: list[ast.FunctionDef | ast.AsyncFunctionDef],
    arguments: list[CallArgument],
    scope: TypeScope,
    *,
    method: bool,
) -> Returned | None:
    overloads = [node for node in defined if _is_overload(node)] or defined[-1:]
    matches: list[tuple[ast.FunctionDef | ast.AsyncFunctionDef, dict[int, ast.expr | None]]] = []
    for node in overloads:
        bound = _bind_arguments(node, arguments, method=method)
        if bound is None:
            continue
        if any(
            _refuses(arguments[position], annotation, scope)
            for position, annotation in bound.items()
            if position != _RECEIVER
        ):
            continue
        matches.append((node, bound))
    if not matches:
        return None
    # An argument of unknown type decides nothing where every match gives its parameter
    # the same written type; then the first match is the one a type checker takes.
    # The receiver is one such argument: its type is not known here, and an overload that
    # writes a type for `self` (`def lower(self: LiteralString)`) is chosen by it.
    unknown = [p for p, argument in enumerate(arguments) if _value(argument) is _UNKNOWN_VALUE]
    deciding = any(
        len({_text(bound.get(position)) for _, bound in matches}) > 1
        for position in [_RECEIVER, *unknown]
    )
    chosen = matches if deciding else matches[:1]
    types: list[TypeRef] = []
    for node, _ in chosen:
        returned = written_type(node.returns, scope) if node.returns is not None else None
        if returned is None:
            return None
        if returned not in types:
            types.append(returned)
    return Returned(tuple(types), "narrowed" if len(types) > 1 else "resolved")


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
# Where `_bind_arguments` puts the receiver's written type (`self`), beside the arguments'
# positions.
_RECEIVER = -1


def _value(argument: CallArgument) -> object:
    """The Python value of an argument whose type the call site states."""
    if argument.kind not in _LITERAL_KINDS:
        return _UNKNOWN_VALUE
    if argument.kind == "null":
        return None
    if argument.kind == "concat":
        return ""
    return argument.value


def _refuses(argument: CallArgument, annotation: ast.expr | None, scope: TypeScope) -> bool:
    """Whether a literal argument certainly does not fit the written type. A type this
    rule does not read (a class, an alias) is taken to fit."""
    value = _value(argument)
    if value is _UNKNOWN_VALUE or annotation is None:
        return False
    if isinstance(annotation, ast.BinOp) and isinstance(annotation.op, ast.BitOr):
        return _refuses(argument, annotation.left, scope) and _refuses(
            argument, annotation.right, scope
        )
    if isinstance(annotation, ast.Constant):
        return annotation.value is None and value is not None
    if isinstance(annotation, ast.Subscript):
        targets = scope.lookup(annotation.value) if _is_name(annotation.value) else ()
        written = (
            list(annotation.slice.elts)
            if isinstance(annotation.slice, ast.Tuple)
            else [annotation.slice]
        )
        if len(targets) != 1 or targets[0].module not in ("typing", "typing_extensions"):
            return False
        form = targets[0].member
        if form == "Literal":
            return not any(
                isinstance(part, ast.Constant)
                and type(part.value) is type(value)
                and part.value == value
                for part in written
            )
        if form == "Optional":
            return value is not None and _refuses(argument, written[0], scope)
        if form == "Union":
            return all(_refuses(argument, part, scope) for part in written)
        return False
    if _is_name(annotation):
        targets = scope.lookup(annotation)
        if len(targets) != 1 or targets[0].module != BUILTINS:
            return False
        accepted = _ACCEPTS.get(targets[0].member or "")
        return accepted is not None and not isinstance(value, accepted)
    return False


def _is_name(node: ast.expr) -> bool:
    return isinstance(node, ast.Name | ast.Attribute)


def _text(annotation: ast.expr | None) -> str:
    return "" if annotation is None else ast.unparse(annotation)
