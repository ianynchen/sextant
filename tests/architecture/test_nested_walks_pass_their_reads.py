"""A walk passes every read it makes to the position that asked, and a kept answer hands on the
reads it was worked out with.

A binding round keeps every shared upward path that read nothing its new edges change
(`values.suffixes_kept`), and walks a site again only where its walk read one of them
(`receiver_binding._walk`). Both hold only if a position's record holds every read made while
it was worked out. Two things can lose one, and each rule below guards one of them:

- **A walk started inside a walk** (task 8 re-review C1). `_Walk` takes the read stack of the
  walk that started it as a required argument, and every walk started inside `_Walk`, or in a
  function `_Walk` reaches, is handed that stack: `self._deps`, or the `deps` the function was
  itself handed.
- **A cache** (task 8 re-review R3-1): an answer worked out once and taken by a later asker
  without the reads it was worked out with. Every cache in the walk's modules is a
  `values.Kept`, which keeps each answer with its reads and replays them on a hit. A container
  written any other way is either no cache (a stack or a guard, named below with why), or a
  cache whose computing reads nothing a binding round changes, which is checked. A container
  held by a module-level or enclosing-function name is no exception (re-review round 4).
- **A read never recorded** (task 8 re-review M4-1): a walk that reads a part of the call
  index a round changes (`callers`, `callees`, `called_at`, `reached`) records that read
  (`_Walk._depends`) in the same function, so a round walks again what read it.
"""

import ast
from collections import Counter
from collections.abc import Iterator
from pathlib import Path

from sextant.application.resolve import parameter_markers, values

# The modules a walk runs in: `values`, and `parameter_markers`, whose markers `_Walk` reads.
_MODULES = {
    "values": values.__file__,
    "parameter_markers": parameter_markers.__file__,
}

# The functions that start a walk of their own. Each is a leaf here: what it passes its own
# `_Walk` is the asker's business, checked where it is called.
_STARTS_A_WALK = frozenset(
    {
        "producer_paths",
        "producers_of",
        "resolve_positions",
        "resolve_positions_on_paths",
        "resolve_site",
        "_Walk",
    }
)

# Containers written in these modules that are no cache, and why.
_NOT_A_CACHE = {
    "_deps": "the read stack itself",
    "_pending": "the positions the current path is in the middle of: a cycle guard",
    "_open": "the pending positions a result below answered `cycle` about",
    "_reads": "what an object walk read of its asker's frames, kept with its answer",
    "markers": (
        "`parameter_markers`' whole answer, for readers outside a walk; a walk takes a "
        "parameter's markers from `markers_kept` (`_Walk._recipe_paths`)"
    ),
}

# Caches whose computing reads nothing a binding round changes: their answers rest on no read,
# so they need no `Kept`. Checked by `test_a_cache_kept_without_its_reads_reads_nothing_a_round_changes`.
_READS_NOTHING_A_ROUND_CHANGES = frozenset(
    {"slots_memo", "declared_memo", "mappings", "namespaces", "_chains"}
)

# What a binding round changes, as the index names it, and the walk's way of recording a read.
_ROUND_CHANGES = frozenset({"callers", "callees", "called_at", "reached", "_depends", "_depended"})

# Each part of the call index a binding round changes, and the read kind a walk records for it
# (`values.READ_*`).
_RECORDED_AS = {
    "callers": "READ_CALLERS",
    "callees": "READ_CALLEES",
    "called_at": "READ_CALLED_AT",
    "reached": "READ_REACHED",
}

# Containers held by a module-level name in these modules that are written, and why each is
# no cache of what a walk works out.
_MODULE_STATE = {
    "_INDEX_BY_WORKSPACE": (
        "the index each workspace's readers share, built from fact queries; "
        "`reset_value_index` drops it after binding"
    ),
}


def _trees() -> dict[str, ast.Module]:
    return {
        name: ast.parse(Path(path).read_text(encoding="utf-8")) for name, path in _MODULES.items()
    }


def _functions(trees: dict[str, ast.Module]) -> dict[tuple[str, str], ast.FunctionDef]:
    """Every function and method of the modules, as `(module, name)` or `(module,
    Class.name)`."""
    found: dict[tuple[str, str], ast.FunctionDef] = {}
    for module, tree in trees.items():
        for node in tree.body:
            if isinstance(node, ast.FunctionDef):
                found[(module, node.name)] = node
            elif isinstance(node, ast.ClassDef):
                for member in node.body:
                    if isinstance(member, ast.FunctionDef):
                        found[(module, f"{node.name}.{member.name}")] = member
    return found


def _imported(tree: ast.AST) -> dict[str, str]:
    """The names `tree` imports from one of the modules, to that module."""
    found: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            module = node.module.rsplit(".", 1)[-1]
            if module in _MODULES:
                for alias in node.names:
                    found[alias.asname or alias.name] = module
    return found


def _named(
    module: str,
    function: ast.FunctionDef,
    tree: ast.Module,
    functions: dict[tuple[str, str], ast.FunctionDef],
) -> Iterator[tuple[str, str]]:
    """The module functions `function` names, called or handed on as a value."""
    imported = {**_imported(tree), **_imported(function)}
    for node in ast.walk(function):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            home = imported.get(node.id, module)
            if (home, node.id) in functions:
                yield (home, node.id)


def _reached_from_the_walk(
    trees: dict[str, ast.Module], functions: dict[tuple[str, str], ast.FunctionDef]
) -> set[tuple[str, str]]:
    """`_Walk`'s methods, and every function they reach by name, short of a walk start."""
    pending = [key for key in functions if key[0] == "values" and key[1].startswith("_Walk.")]
    seen = set(pending)
    while pending:
        key = pending.pop()
        for one in _named(key[0], functions[key], trees[key[0]], functions):
            if one[1] not in _STARTS_A_WALK and one not in seen:
                seen.add(one)
                pending.append(one)
    return seen


def _deps_slot(function: ast.FunctionDef) -> int | None:
    """The position `deps` is passed at, None where it is keyword-only or absent."""
    positional = [argument.arg for argument in function.args.args]
    if positional and positional[0] == "self":
        positional = positional[1:]
    return positional.index("deps") if "deps" in positional else None


def _takes_deps(function: ast.FunctionDef) -> bool:
    return any(
        argument.arg == "deps" for argument in (*function.args.args, *function.args.kwonlyargs)
    )


def _handed(call: ast.Call, slot: int | None) -> ast.expr | None:
    for keyword in call.keywords:
        if keyword.arg == "deps":
            return keyword.value
    if slot is not None and slot < len(call.args):
        return call.args[slot]
    return None


def _is_own_stack(value: ast.expr | None, function: ast.FunctionDef, in_walk: bool) -> bool:
    """Whether `value` is the asker's stack: `self._deps` inside `_Walk`, else the `deps` the
    function was handed."""
    if value is None:
        return False
    if in_walk:
        return (
            isinstance(value, ast.Attribute)
            and value.attr == "_deps"
            and isinstance(value.value, ast.Name)
            and value.value.id == "self"
        )
    return isinstance(value, ast.Name) and value.id == "deps" and _takes_deps(function)


def test_every_walk_started_inside_a_walk_is_handed_its_stack():
    """Inside `_Walk`, and in every function it reaches, each call of a walk start or of a
    function taking a read stack passes the asker's stack on."""
    trees = _trees()
    functions = _functions(trees)
    walk_init = functions[("values", "_Walk.__init__")]
    missing = []
    for key in sorted(_reached_from_the_walk(trees, functions)):
        module, name = key
        function = functions[key]
        in_walk = name.startswith("_Walk.")
        imported = {**_imported(trees[module]), **_imported(function)}
        # A function named under another name in this body (`start = producer_paths`).
        aliases = {
            target.id: node.value.id
            for node in ast.walk(function)
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Name)
            for target in node.targets
            if isinstance(target, ast.Name)
        }
        for node in ast.walk(function):
            if not isinstance(node, ast.Call):
                continue
            if isinstance(node.func, ast.Name):
                called = aliases.get(node.func.id, node.func.id)
            elif isinstance(node.func, ast.Attribute) and node.func.attr in _STARTS_A_WALK:
                called = node.func.attr
            else:
                continue
            if called == "_Walk":
                target = walk_init
            else:
                held = functions.get((imported.get(called, module), called))
                if held is None or not (called in _STARTS_A_WALK or _takes_deps(held)):
                    continue
                target = held
            if not _is_own_stack(_handed(node, _deps_slot(target)), function, in_walk):
                missing.append(f"{module}.{name}: {called} at line {node.lineno}")

    assert missing == []


def _written(tree: ast.Module) -> Iterator[tuple[str, str, ast.FunctionDef, str]]:
    """Each container an attribute holds that a function writes, as `(class, function, the
    function, attribute)`: an item stored, or a call that changes it, on `self.x`,
    `self._index.x` or `index.x`, or on a local naming one."""
    changing = {"add", "update", "append", "extend", "setdefault", "discard", "pop", "clear"}
    for owner in tree.body:
        members = owner.body if isinstance(owner, ast.ClassDef) else [owner]
        cls = owner.name if isinstance(owner, ast.ClassDef) else ""
        for function in members:
            if not isinstance(function, ast.FunctionDef):
                continue
            aliases = {
                target.id: attribute
                for node in ast.walk(function)
                if isinstance(node, ast.Assign)
                and (attribute := _attribute_of(node.value, {})) is not None
                for target in node.targets
                if isinstance(target, ast.Name)
            }
            for node in ast.walk(function):
                held = None
                if isinstance(node, ast.Assign | ast.AugAssign):
                    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                    for target in targets:
                        if isinstance(target, ast.Subscript):
                            held = _attribute_of(target.value, aliases)
                elif (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr in changing
                ):
                    held = _attribute_of(node.func.value, aliases)
                if held is not None:
                    yield cls, function.name, function, held


def _attribute_of(node: ast.expr, aliases: dict[str, str]) -> str | None:
    """The attribute `node` is, on `self`, `self._index` or `index`, or a local naming one."""
    if isinstance(node, ast.Subscript):
        return _attribute_of(node.value, aliases)
    if isinstance(node, ast.Name):
        return aliases.get(node.id)
    if not isinstance(node, ast.Attribute):
        return None
    base = node.value
    if isinstance(base, ast.Name) and base.id in ("self", "index"):
        return node.attr
    if (
        isinstance(base, ast.Attribute)
        and base.attr == "_index"
        and isinstance(base.value, ast.Name)
        and base.value.id == "self"
    ):
        return node.attr
    return None


def test_every_cache_a_walk_reads_keeps_its_answers_with_their_reads():
    """No container in the walk's modules is written as a cache but through `Kept`, which keeps
    each answer with its reads, unless it is no cache or reads nothing a round changes."""
    found = []
    for module, tree in _trees().items():
        for cls, name, _, held in _written(tree):
            if cls == "Kept":
                continue
            if held not in _NOT_A_CACHE and held not in _READS_NOTHING_A_ROUND_CHANGES:
                found.append(f"{module}.{cls + '.' if cls else ''}{name} writes {held}")

    assert found == []


def test_only_kept_reads_what_it_holds():
    """`Kept.held` is read and written by `Kept` alone, and by `suffixes_kept`, which keeps the
    entries a round's edges cannot change with their reads."""
    found = []
    for module, tree in _trees().items():
        for owner in tree.body:
            if isinstance(owner, ast.ClassDef) and owner.name == "Kept":
                continue
            if isinstance(owner, ast.FunctionDef) and owner.name == "suffixes_kept":
                continue
            for node in ast.walk(owner):
                if isinstance(node, ast.Attribute) and node.attr in ("held", "pending"):
                    found.append(f"{module} line {node.lineno}")

    assert found == []


def test_a_cache_kept_without_its_reads_reads_nothing_a_round_changes():
    """Each cache kept without `Kept` is worked out by code that reads no part of the index a
    binding round changes, records no read, and starts no walk, through every function and
    method it calls in these modules."""
    trees = _trees()
    functions = _functions(trees)
    found = []
    for module, tree in trees.items():
        for cls, name, function, held in _written(tree):
            if held not in _READS_NOTHING_A_ROUND_CHANGES:
                continue
            pending = [(module, f"{cls}.{name}" if cls else name, function)]
            seen = {pending[0][:2]}
            while pending:
                home, label, body = pending.pop()
                for node in ast.walk(body):
                    if isinstance(node, ast.Attribute) and node.attr in _ROUND_CHANGES:
                        found.append(f"{home}.{label} reads {node.attr} for {held}")
                    if isinstance(node, ast.Name) and node.id in _STARTS_A_WALK:
                        found.append(f"{home}.{label} starts a walk for {held}")
                    callee = None
                    if isinstance(node, ast.Name):
                        callee = (home, node.id)
                    elif (
                        isinstance(node, ast.Attribute)
                        and isinstance(node.value, ast.Name)
                        and node.value.id == "self"
                        and "." in label
                    ):
                        callee = (home, f"{label.split('.')[0]}.{node.attr}")
                    if callee in functions and callee not in seen:
                        seen.add(callee)
                        pending.append((*callee, functions[callee]))

    assert found == []


def _index_reads(function: ast.FunctionDef) -> Iterator[tuple[str, int]]:
    """Each read of a part of the call index a round changes, on `self._index`, `index`, or a
    local naming either, as `(field, line)`."""
    names = {"index"} | {
        target.id
        for node in ast.walk(function)
        if isinstance(node, ast.Assign) and _is_the_index(node.value, set())
        for target in node.targets
        if isinstance(target, ast.Name)
    }
    for node in ast.walk(function):
        if (
            isinstance(node, ast.Attribute)
            and node.attr in _RECORDED_AS
            and isinstance(node.ctx, ast.Load)
            and _is_the_index(node.value, names)
        ):
            yield node.attr, node.lineno


def _is_the_index(node: ast.expr, names: set[str]) -> bool:
    if isinstance(node, ast.Name):
        return node.id in names
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "_index"
        and isinstance(node.value, ast.Name)
        and node.value.id == "self"
    )


def _recorded(function: ast.FunctionDef) -> Counter[str]:
    """How many reads of each kind `function` records: `self._depends((READ_X, ...))`."""
    found: Counter[str] = Counter()
    for node in ast.walk(function):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "_depends"
            and node.args
            and isinstance(node.args[0], ast.Tuple)
            and node.args[0].elts
            and isinstance(node.args[0].elts[0], ast.Name)
        ):
            found[node.args[0].elts[0].id] += 1
    return found


def test_every_read_of_the_call_index_in_a_walk_is_recorded():
    """Inside `_Walk`, and in every function it reaches, a function reading `callers`,
    `callees`, `called_at` or `reached` records that kind of read itself, once for each read
    (M4-1): a round that changes it then walks again every position and site that read it.
    Counted per read, so a function reading one part in two places cannot lose one record
    behind the other."""
    trees = _trees()
    functions = _functions(trees)
    missing = []
    for key in sorted(_reached_from_the_walk(trees, functions)):
        function = functions[key]
        reads = Counter(field for field, _ in _index_reads(function))
        recorded = _recorded(function)
        for field, count in sorted(reads.items()):
            if recorded[_RECORDED_AS[field]] < count:
                missing.append(
                    f"{key[0]}.{key[1]} reads {field} {count} times, records "
                    f"{recorded[_RECORDED_AS[field]]}"
                )

    assert missing == []


def _bound_in(function: ast.FunctionDef | ast.Lambda) -> set[str]:
    """The names `function` binds itself: its parameters, and every name it assigns."""
    arguments = function.args
    found = {
        argument.arg
        for argument in (*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs)
    }
    found |= {one.arg for one in (arguments.vararg, arguments.kwarg) if one is not None}
    for node in ast.walk(function):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            found.add(node.id)
    return found


def _changed_names(function: ast.FunctionDef) -> Iterator[tuple[str, int]]:
    """Each name whose container `function` writes: an item stored, or a call that changes
    it, as `(name, line)`."""
    changing = {"add", "update", "append", "extend", "setdefault", "discard", "pop", "clear"}
    for node in ast.walk(function):
        held = None
        if isinstance(node, ast.Assign | ast.AugAssign):
            for target in node.targets if isinstance(node, ast.Assign) else [node.target]:
                while isinstance(target, ast.Subscript):
                    target = target.value
                    if isinstance(target, ast.Name):
                        held = target
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in changing
            and isinstance(node.func.value, ast.Name)
        ):
            held = node.func.value
        if held is not None:
            yield held.id, node.lineno


def _module_names(tree: ast.Module) -> set[str]:
    """The names `tree` binds at module level."""
    found = set()
    for node in tree.body:
        targets = (
            node.targets
            if isinstance(node, ast.Assign)
            else [node.target]
            if isinstance(node, ast.AnnAssign | ast.AugAssign)
            else []
        )
        found |= {target.id for target in targets if isinstance(target, ast.Name)}
    return found


def test_no_module_level_container_is_written_by_walk_code():
    """A container held by a module-level name is no `self` attribute, so the cache rule above
    cannot see one used as a cache (re-review round 4: a module dict keyed on the index
    replaced `_setter_calls`, and every check passed). No function in the walk's modules writes
    a container a module-level name holds, and none declares a name `global` or `nonlocal`,
    unless it is named below with why it is no cache. A container a function binds for itself
    lives for that one call (an accumulator a nested function fills), and is not one."""
    found = []
    for module, tree in _trees().items():
        module_names = _module_names(tree)
        for owner in ast.walk(tree):
            if not isinstance(owner, ast.FunctionDef):
                continue
            local = _bound_in(owner)
            for node in ast.walk(owner):
                if isinstance(node, ast.Global | ast.Nonlocal):
                    found.append(f"{module}.{owner.name} declares {node.names}")
            for name, line in _changed_names(owner):
                if name in module_names and name not in local and name not in _MODULE_STATE:
                    found.append(f"{module}.{owner.name} writes {name} at line {line}")

    assert found == []
