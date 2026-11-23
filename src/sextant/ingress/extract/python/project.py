"""The headers of the module's own files (OI-324 part 2, round 1; user choice A, 2026-11-07).

A file is still read one at a time (M03), but what it imports from another file of the same
module is read the way a library is (`libraries.py`): that file's HEADER and nothing else of
its bodies — its module-level names (imports, re-exports and aliases, as `imports.py` binds
them), its classes' written bases and type parameters, the return each `def` declares, the
attribute each class body declares (`client: HttpClient`) and the type each module-level
type alias is (`DbSession = Annotated[Session, Depends(get_db)]` is `Session`). A file's header is parsed
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
    PY_SIGNATURE,
    is_type_descriptor,
    method_descriptor,
    names_a_type,
    owner_of,
    without_type_marker,
)
from sextant.ingress.extract.python.calls import TYPE_OF
from sextant.ingress.extract.python.imports import (
    Binding,
    ModuleIndex,
    Target,
    bind_names,
    star_bases,
    star_exports,
)
from sextant.ingress.extract.python.typing_rules import ClassShape, TypeScope, type_symbol

# The question a file asks the module index for another file's header (`ModuleIndex.asked`).
HEADER = "header"
# A bound on how many aliases of other files one type is followed through, so an alias that
# names itself ends.
_ALIAS_DEPTH = 32


@dataclass(frozen=True)
class ModuleHeader:
    """What a file's header says, its symbols as the file writes them (by import path)."""

    names: dict[str, Binding]
    classes: dict[str, ClassShape]
    returns: dict[str, TypeRef]
    fields: dict[str, TypeRef]
    digest: str
    # The type each module-level type alias is (`DbSession = Annotated[Session, ...]`,
    # `X: TypeAlias = ...`, `type X = ...`), by name, read in the file's own scope.
    aliases: dict[str, TypeRef]
    # The function each module-level name is written from, where every write to it in the
    # file is a call of a named function (ruling R17), by name, as the file binds it.
    factories: dict[str, tuple[Target, ...]]
    # The modules its top-level `from m import *` statements read, in written order, and the
    # names its `__all__` lists (None where it writes none): what a star import takes from it.
    stars: tuple[str, ...] = ()
    exports: tuple[str, ...] | None = None


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
            tuple[
                dict[str, ClassShape],
                dict[str, TypeRef],
                dict[str, TypeRef],
                dict[str, TypeRef],
                dict[str, tuple[Target, ...]],
            ],
        ],
    ) -> None:
        self._files = files
        self._previous = previous
        # The index a header is bound against: the module's paths and the libraries, with no
        # headers of its own, so one file's header never reads another's.
        self._plain = plain
        # `structure`'s readers of a module body: its class shapes, declared returns,
        # attribute declarations, type aliases and the functions module-level names are
        # written from (handed in, as `structure` is the module that reads files).
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
            return self._starred(module, header, name, seen)
        found: list[Target] = []
        for target in binding.targets:
            if target.module == module and target.member == name:
                # A class a call makes keeps saying so (`new_class`); every other own name is
                # followed by what it is bound to.
                found.append(
                    Target(module, name, "new_class")
                    if target.kind == "new_class"
                    else Target(module, name)
                )
            elif target.member is not None and "." not in target.member:
                deeper = self.member(target.module, target.member, seen | {(module, name)})
                reached = deeper or (Target(target.module, target.member),)
                if target.kind == "new_type":
                    # A `NewType` keeps saying it is one: a call of it is no construction.
                    reached = tuple(replace(one, kind="new_type") for one in reached)
                found.extend(reached)
            else:
                # A `NewType`, or a class a call makes, keeps saying it is one: a call of it
                # is no construction of a known class.
                kind = target.kind if target.kind in ("new_type", "new_class") else None
                found.append(Target(target.module, target.member, kind))
        return tuple(dict.fromkeys(found))

    def _starred(
        self, module: str, header: ModuleHeader, name: str, seen: frozenset[tuple[str, str]]
    ) -> tuple[Target, ...] | None:
        """Where `module.name` is defined when `module` binds `name` by no statement of its own
        but a `from m import *` may: Python's rule, the last star that takes the name winning.
        A star takes a name its source lists in `__all__`, else any without a leading `_`. A
        source that is no file of the module (a library) says nothing, so the name stays as
        written."""
        for base in reversed(header.stars):
            source = self.header(base)
            if source is None:
                continue
            if name not in source.exports if source.exports is not None else name.startswith("_"):
                continue
            found = self.member(base, name, seen | {(module, name)})
            if found is not None:
                return found
        return None

    def names_a_value(self, module: str, name: str) -> bool:
        """Whether `module.name`, followed to where it is defined, is bound to a value, a
        function or a type alias rather than a class (`SaveFixture = Callable[...]`): such a
        name, written as a type in another file, names no class there."""
        return self._bound_to(module, name, ("variable", "function", "type_alias", "new_class"))

    def names_a_variable(self, module: str, name: str) -> bool:
        """Whether `module.name`, followed to where it is defined, is bound to a variable on
        every statement: an import of it binds the importing module's name to that value."""
        return self._bound_to(module, name, ("variable",))

    def _bound_to(self, module: str, name: str, kinds: tuple[str, ...]) -> bool:
        defined = self.member(module, name)
        if not defined:
            return False
        for target in defined:
            header = self.header(target.module) if target.member is not None else None
            if header is None:
                return False
            binding = header.names.get(target.member or "")
            if binding is None or any(
                own.kind not in kinds for own in binding.targets if own.module == target.module
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

    def names_an_alias(self, module: str, name: str) -> bool:
        """Whether `module` binds `name`, on its one binding, to a module-level type alias of its
        own, whether or not the type the alias is can be named."""
        header = self.header(module)
        binding = None if header is None else header.names.get(name)
        return (
            binding is not None
            and len(binding.targets) == 1
            and binding.targets[0].kind == "type_alias"
            and binding.targets[0].module == module
        )

    def alias(self, module: str, name: str) -> TypeRef | None:
        """The type `module.name` is where that file binds it to a module-level type alias,
        its types by their defining symbols. None for any other name."""
        header = self.header(module)
        written = None if header is None else header.aliases.get(name)
        if written is None:
            return None
        # `written` is the alias already read through once in its own file.
        return self._typed(written, reading=frozenset({f"{module}/{name}#"}))

    def binds_class(self, module: str, name: str) -> bool:
        """Whether `module` binds `name` to its own class `name` alone, its one binding the
        class statement: `Session = Client` after `class Session` binds the name to `Client`,
        and `Session = make()` makes it a variable, as `effective_calls._class_calls` reads
        both."""
        header = self.header(module)
        binding = None if header is None else header.names.get(name)
        return binding is not None and binding.targets == (Target(module, name, "class"),)

    def class_object(self, module: str, name: str) -> str | None:
        """The class `X` that `module.name` holds, where every write to it in that file is a
        call of a `def` of the module whose written return is `type[X]` (ruling R17; polar's
        `APIRouter = get_api_router_class(APIRoute)`), by its defining symbol. None for any
        other name, and where the writes give two classes: the closed list is never one."""
        header = self.header(module)
        called = None if header is None else header.factories.get(name)
        if not called:
            return None
        held = {self._factory_class(target) for target in called}
        if len(held) != 1:
            return None
        return held.pop()

    def variable_class(self, module: str, name: str) -> str | None:
        """The class whose instance `module.name` holds, where every write to it in that file
        constructs one and the same class (`settings = Settings()`, ruling R23), by its
        defining symbol: a class of the module or of a library. Likewise where the one write calls
        a scanned `def` that declares `-> X` (OI-444). None for any other name: two classes, a
        call of an unannotated function, any other value."""
        header = self.header(module)
        called = None if header is None else header.factories.get(name)
        if not called or len(called) != 1:
            return None
        (target,) = called
        if target.member is None:
            return None
        defined = self.member(target.module, target.member) or (target,)
        if len(defined) != 1 or defined[0].member is None:
            return None
        symbol = type_symbol(defined[0])
        if self._has_shape(symbol):
            return symbol
        returned = self._returned_class(defined[0])
        return returned if returned is not None and self._has_shape(returned) else None

    def _has_shape(self, symbol: str) -> bool:
        """Whether `symbol` is a class of the module or of a library with a known shape."""
        libraries = self._plain.libraries
        return self.shape_of(symbol) is not None or (
            libraries is not None and libraries.shape_of(symbol) is not None
        )

    def _returned_class(self, function: Target) -> str | None:
        """The class `X` a call of the function `function` gives, where the `def` of the module
        that defines it declares `-> X` (`settings = get_settings()`, OI-444); None for any
        other function, and for `type[X]`, which is the class, not an instance."""
        if function.module not in self._files:
            return None
        returned = self.returns(
            method_descriptor(
                type_symbol(Target(function.module)), str(function.member), PY_SIGNATURE
            )
        )
        if returned is None or returned.symbol == TYPE_OF or not names_a_type(returned.symbol):
            return None
        return returned.symbol

    def _factory_class(self, target: Target) -> str | None:
        """The class `X` a call of the function `target` gives, where the `def` of the module
        that defines it declares `type[X]`; None for any other function."""
        if target.member is None:
            return None
        defined = self.member(target.module, target.member) or (target,)
        if len(defined) != 1 or defined[0].member is None or defined[0].module not in self._files:
            return None
        (function,) = defined
        returned = self.returns(
            method_descriptor(
                type_symbol(Target(function.module)), str(function.member), PY_SIGNATURE
            )
        )
        if (
            returned is None
            or returned.symbol != TYPE_OF
            or len(returned.arguments) != 1
            or not names_a_type(returned.arguments[0].symbol)
        ):
            return None
        return returned.arguments[0].symbol

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

    def _typed(
        self, written: TypeRef, depth: int = _ALIAS_DEPTH, reading: frozenset[str] = frozenset()
    ) -> TypeRef:
        """`written` with each type it names by its defining symbol. A name another module
        file binds to a type alias (read in that file's scope, which reads no other header,
        as a path) is the type the alias is: the path names no class. An alias that names
        itself on the path (`Tree = list[Tree]`) stays its name, as the code writes it."""
        symbol = self.canonical(written.symbol) if names_a_type(written.symbol) else written.symbol
        aliased = (
            None if written.arguments or depth == 0 or symbol in reading else self._aliased(symbol)
        )
        if aliased is not None:
            found = self._typed(aliased, depth - 1, reading | {symbol})
            if written.nullable and not found.nullable:
                found = found.model_copy(
                    update={"nullable": True, "nullable_resolution": written.nullable_resolution}
                )
            return found
        arguments = [self._typed(argument, depth, reading) for argument in written.arguments]
        if symbol == written.symbol and all(
            new == old for new, old in zip(arguments, written.arguments, strict=True)
        ):
            return written
        return written.model_copy(update={"symbol": symbol, "arguments": arguments})

    def _aliased(self, symbol: str) -> TypeRef | None:
        """The type a top-level type symbol of a module file is, where that file binds its
        name to a type alias; None for a class and anything else."""
        path = without_type_marker(symbol)
        module, _, member = path.rpartition("/")
        if not is_type_descriptor(symbol) or "$" in member or module not in self._files:
            return None
        header = self.header(module)
        return None if header is None else header.aliases.get(member)

    def _build(self, module: str) -> ModuleHeader | None:
        path, is_package = self._files[module]
        try:
            tree = ast.parse(path.read_bytes(), filename=str(path))
        except (OSError, SyntaxError, ValueError, RecursionError):
            return None
        names = bind_names(tree.body, module, is_package=is_package, index=self._plain)
        types = TypeScope(names=names, here=module, index=self._plain)
        classes, returns, fields, aliases, factories = self._read(tree, module, types, is_package)
        # Read before the digest: it strips the tree.
        bases = star_bases(tree.body, module, is_package=is_package)
        exports = star_exports(tree.body)
        return ModuleHeader(
            names,
            classes,
            returns,
            fields,
            header_digest(tree),
            aliases,
            factories,
            bases,
            exports,
        )
