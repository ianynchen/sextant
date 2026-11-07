"""The headers of the module's own files (OI-324 part 2, round 1; user choice A, 2026-11-07).

A file is still read one at a time (M03), but what it imports from another file of the same
module is read the way a library is (`libraries.py`): that file's HEADER and nothing else of
its bodies — its module-level names (imports, re-exports and aliases, as `imports.py` binds
them), its classes' written bases and type parameters, the return each `def` declares and
the attribute each class body declares (`client: HttpClient`). A file's header is parsed
once per scan, whichever files import it.

- **Defining symbols, as for a library:** a name another file re-exports (`from .order import
  Order` in `polar/models/__init__.py`) or aliases (`Logger = structlog.stdlib.BoundLogger`)
  is followed to where it is defined: a class of the module, or a library's defining symbol
  (`libraries.py`). Each answer is a pure function of the headers read, followed afresh per
  question, so it never depends on which file asked first.
- **Reuse (OI-325):** every header a file's reading consults is recorded among the questions
  that file asked the module index (`("header", module)`), and its answer is the header's
  digest: a re-read of another file's header that changes re-reads this one, and a change to
  that file's bodies alone does not.
"""

import ast
import hashlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path

from sextant.domain.facts import TypeRef
from sextant.domain.symbols import (
    is_type_descriptor,
    names_a_type,
    owner_of,
    without_type_marker,
)
from sextant.ingress.extract.python.imports import Binding, ModuleIndex, Target, bind_names
from sextant.ingress.extract.python.typing_rules import ClassShape, TypeScope, type_symbol

# The question a file asks the module index for another file's header (`ModuleIndex.asked`).
HEADER = "header"


@dataclass(frozen=True)
class ModuleHeader:
    """What a file's header says, its symbols as the file writes them (by import path)."""

    names: dict[str, Binding]
    classes: dict[str, ClassShape]
    returns: dict[str, TypeRef]
    fields: dict[str, TypeRef]
    digest: str


def header_digest(tree: ast.Module) -> str:
    """The digest of a file's header: its syntax tree with every function body and every
    statement that binds no name removed, so an edit inside a body leaves it unchanged. The
    tree is changed in place: a caller hands over a tree it no longer reads."""
    _strip(tree.body)
    text = ast.dump(tree, include_attributes=False)
    return "sha256:" + hashlib.sha256(text.encode()).hexdigest()


def _strip(body: list[ast.stmt]) -> None:
    kept: list[ast.stmt] = []
    for node in body:
        if isinstance(node, ast.Expr | ast.Pass | ast.Raise | ast.Return | ast.Delete):
            continue
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            node.body = [ast.Pass()]
        elif isinstance(node, ast.ClassDef):
            _strip(node.body)
        elif isinstance(node, ast.If | ast.For | ast.AsyncFor | ast.While):
            _strip(node.body)
            _strip(node.orelse)
        elif isinstance(node, ast.With | ast.AsyncWith):
            _strip(node.body)
        elif isinstance(node, ast.Try | ast.TryStar):
            _strip(node.body)
            _strip(node.orelse)
            _strip(node.finalbody)
            for handler in node.handlers:
                _strip(handler.body)
        kept.append(node)
    body[:] = kept


class ProjectHeaders:
    """The headers of the module's files, read lazily, each once per scan.

    `files` are the module's files by module path, with whether each is a package;
    `previous` each file's content hash and header digest from the previous scan, so a
    question about a file that did not change is answered without reading it."""

    def __init__(
        self,
        files: Mapping[str, tuple[Path, bool]],
        previous: Mapping[str, tuple[str, str]],
        plain: ModuleIndex,
        read: Callable[
            [ast.Module, str, TypeScope, bool],
            tuple[dict[str, ClassShape], dict[str, TypeRef], dict[str, TypeRef]],
        ],
    ) -> None:
        self._files = files
        self._previous = previous
        # The index a header is bound against: the module's paths and the libraries, with no
        # headers of its own, so one file's header never reads another's.
        self._plain = plain
        # `structure`'s readers of a module body: its class shapes, declared returns and
        # attribute declarations (handed in, as `structure` is the module that reads files).
        self._read = read
        self._headers: dict[str, ModuleHeader | None] = {}
        self._hashes: dict[str, str | None] = {}
        # Each answer, with the modules whose headers it read.
        self._canonical: dict[str, tuple[str, frozenset[str]]] = {}
        # The questions of the file being read (`ModuleIndex.asked`), set by the scan.
        self.asked: set[tuple[str, str]] | None = None

    # -- what a reading of another file consults ------------------------------------------

    def header(self, module: str) -> ModuleHeader | None:
        """`module`'s header, recorded as read by the file being read."""
        if module not in self._files:
            return None
        if self.asked is not None:
            self.asked.add((HEADER, module))
        if module not in self._headers:
            self._headers[module] = self._build(module)
        return self._headers[module]

    def member(
        self, module: str, name: str, seen: frozenset[tuple[str, str]] = frozenset()
    ) -> tuple[Target, ...] | None:
        """Where `module.name` is defined, through the module files' re-exports and aliases:
        a name `module` itself defines, a library's defining symbol, or the closed list where
        `module`'s branches bind it differently. None where `module` is no file of the module
        or does not bind `name` (a submodule, a star import): the path stays as written."""
        header = self.header(module)
        if header is None or (module, name) in seen:
            return None
        binding = header.names.get(name)
        if binding is None:
            return None
        found: list[Target] = []
        for target in binding.targets:
            if target.module == module and target.member == name:
                found.append(Target(module, name))
            elif target.member is not None and "." not in target.member:
                deeper = self.member(target.module, target.member, seen | {(module, name)})
                found.extend(deeper or (Target(target.module, target.member),))
            else:
                found.append(Target(target.module, target.member))
        return tuple(dict.fromkeys(found))

    def names_a_value(self, module: str, name: str) -> bool:
        """Whether `module.name`, followed to where it is defined, is bound to a value, a
        function or a type alias rather than a class (`SaveFixture = Callable[...]`): such a
        name, written as a type in another file, names no class there."""
        defined = self.member(module, name)
        if not defined:
            return False
        for target in defined:
            header = self.header(target.module) if target.member is not None else None
            if header is None:
                return False
            binding = header.names.get(target.member or "")
            if binding is None or any(
                own.kind not in ("variable", "function", "type_alias")
                for own in binding.targets
                if own.module == target.module
            ):
                return False
            if not any(own.module == target.module for own in binding.targets):
                return False
        return True

    def canonical(self, symbol: str) -> str:
        """A type symbol written by import path, as the class it is defined as: a class a
        module file re-exports is that file's class (`polar/models/Order#` is
        `polar/models/order/Order#`), a library one its defining symbol. Unchanged where it is
        already, or where the path cannot be followed."""
        cached = self._canonical.get(symbol)
        if cached is not None:
            # The headers its answer read are read again by every file that asks.
            if self.asked is not None:
                self.asked.update((HEADER, module) for module in cached[1])
            return cached[0]
        outer, self.asked = self.asked, set()
        try:
            found = self._follow(symbol)
        finally:
            consulted, self.asked = self.asked, outer
        self._canonical[symbol] = (found, frozenset(module for _, module in consulted))
        if self.asked is not None:
            self.asked.update(consulted)
        return found

    def _follow(self, symbol: str) -> str:
        found = symbol
        path = without_type_marker(symbol)
        module, _, member = path.rpartition("/")
        if (
            is_type_descriptor(symbol)
            and "$" not in member
            and path not in self._files
            and module in self._files
        ):
            header = self.header(module)
            if header is not None and symbol not in header.classes:
                targets = self.member(module, member)
                if targets is not None and len(targets) == 1 and targets[0].member is not None:
                    found = type_symbol(targets[0])
        return found

    def shape_of(self, symbol: str) -> ClassShape | None:
        """A class of another module file: its type parameters, written bases (each by its
        defining symbol) and members. None for anything else."""
        named = self.canonical(symbol)
        header = self.header(self._module_of(named))
        shape = None if header is None else header.classes.get(named)
        if shape is None or shape.bases is None:
            return shape
        return replace(shape, bases=tuple(self._typed(base) for base in shape.bases))

    def returns(self, descriptor: str) -> TypeRef | None:
        """The return the `def` `descriptor` (a module function or a method, bare) of another
        module file declares, its types by their defining symbols."""
        return self._declared(descriptor, lambda header: header.returns)

    def field(self, field: str) -> TypeRef | None:
        """The type a class body of another module file declares for an attribute."""
        return self._declared(field, lambda header: header.fields)

    def digest(self, module: str) -> str | None:
        """The digest of `module`'s header, for the reuse key: the previous scan's where the
        file's content is the same, else read now. None where `module` is no readable file."""
        entry = self._files.get(module)
        if entry is None:
            return None
        if module not in self._hashes:
            try:
                content = entry[0].read_bytes()
            except OSError:
                content = None
            self._hashes[module] = (
                None if content is None else "sha256:" + hashlib.sha256(content).hexdigest()
            )
        previous = self._previous.get(module)
        if previous is not None and previous[0] == self._hashes[module]:
            return previous[1]
        if module not in self._headers:
            self._headers[module] = self._build(module)
        built = self._headers[module]
        return None if built is None else built.digest

    # -- reading ------------------------------------------------------------------------------

    def _declared(
        self, symbol: str, table: Callable[[ModuleHeader], dict[str, TypeRef]]
    ) -> TypeRef | None:
        owner = owner_of(symbol)
        if owner is None:
            return None
        named = self.canonical(owner)
        header = self.header(self._module_of(named))
        if header is None:
            return None
        written = table(header).get(named + symbol[len(owner) :])
        return None if written is None else self._typed(written)

    def _module_of(self, symbol: str) -> str:
        """The module file a type symbol is in: `a/b` for the module type `a/b#` and for the
        class `a/b/C#` (a nested class `a/b/Outer$Inner#` too)."""
        path = without_type_marker(symbol)
        return path if path in self._files else path.rpartition("/")[0]

    def _typed(self, written: TypeRef) -> TypeRef:
        """`written` with each type it names by its defining symbol."""
        symbol = self.canonical(written.symbol) if names_a_type(written.symbol) else written.symbol
        arguments = [self._typed(argument) for argument in written.arguments]
        if symbol == written.symbol and all(
            new == old for new, old in zip(arguments, written.arguments, strict=True)
        ):
            return written
        return written.model_copy(update={"symbol": symbol, "arguments": arguments})

    def _build(self, module: str) -> ModuleHeader | None:
        path, is_package = self._files[module]
        try:
            tree = ast.parse(path.read_bytes(), filename=str(path))
        except (OSError, SyntaxError, ValueError, RecursionError):
            return None
        names = bind_names(tree.body, module, is_package=is_package, index=self._plain)
        types = TypeScope(names=names, here=module, index=self._plain)
        classes, returns, fields = self._read(tree, module, types, is_package)
        return ModuleHeader(names, classes, returns, fields, header_digest(tree))
