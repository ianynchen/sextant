"""Count the FastAPI and pydantic shapes in Python source trees (plan 2, Task 0).

Uses only the standard library `ast`. Run it isolated, so a planted module cannot load:

    python -I scripts/probes/fastapi_shapes.py <root>...

It prints one block per root. Every count is a syntactic count over the files under the root
(`.venv`, `node_modules` and `site-packages` are skipped). Each count is given for all files and
for the files outside any `tests` or `test_*` path. A name is matched by its last dotted part, so
`fastapi.Query` and `Query` are the same. The probe does no type resolution: a count that needs
one says so.

The counts back the numbers quoted in plan 2's N1-N13 (`fastapi_rules.md` lists them).
"""

from __future__ import annotations

import ast
import sys
from collections import Counter
from pathlib import Path

SKIPPED_PARTS = {".venv", "venv", "node_modules", "site-packages", "__pycache__", ".git"}
VERBS = {"get", "post", "put", "delete", "patch", "head", "options", "trace"}
ROUTE_METHODS = VERBS | {"api_route", "add_api_route"}
MARKERS = {"Query", "Path", "Header", "Cookie", "Body", "Form", "File"}
BODY_MARKERS = {"Body", "Form", "File"}
SPECIAL_TYPES = {
    "Request",
    "Response",
    "WebSocket",
    "HTTPConnection",
    "BackgroundTasks",
    "SecurityScopes",
}
SCALAR_NAMES = {
    "int",
    "float",
    "str",
    "bool",
    "bytes",
    "UUID",
    "datetime",
    "date",
    "time",
    "Decimal",
    "timedelta",
    "Enum",
}
MODELS: set[str] = set()
PYDANTIC_KEYS = {
    "validation_alias",
    "serialization_alias",
    "alias_generator",
    "populate_by_name",
    "validate_by_name",
    "validate_by_alias",
    "AliasChoices",
    "AliasPath",
}


def last_name(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Call):
        return last_name(node.func)
    return None


def keyword(call: ast.Call, name: str) -> ast.keyword | None:
    return next((kw for kw in call.keywords if kw.arg == name), None)


def is_test_path(path: Path, root: Path) -> bool:
    parts = path.relative_to(root).parts
    return any(part in {"tests", "test"} or part.startswith("test_") for part in parts)


def python_files(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*.py")
        if not (set(path.relative_to(root).parts) & SKIPPED_PARTS)
    )


def annotated_alias_value(value: ast.AST) -> bool:
    return isinstance(value, ast.Subscript) and last_name(value.value) == "Annotated"


def module_aliases(tree: ast.Module) -> set[str]:
    """Names bound at module level to an `Annotated[...]` type form."""
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Assign) and annotated_alias_value(node.value):
            names.update(t.id for t in node.targets if isinstance(t, ast.Name))
        elif (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.value is not None
            and annotated_alias_value(node.value)
        ):
            names.add(node.target.id)
        elif isinstance(node, ast.TypeAlias) and annotated_alias_value(node.value):
            names.add(node.name.id)
    return names


def route_decorator(func: ast.FunctionDef | ast.AsyncFunctionDef) -> ast.Call | None:
    """The first decorator that is a call of a route method with a path-like first argument."""
    for deco in func.decorator_list:
        if (
            isinstance(deco, ast.Call)
            and isinstance(deco.func, ast.Attribute)
            and deco.func.attr in (VERBS | {"api_route"})
        ):
            first = deco.args[0] if deco.args else None
            path_kw = keyword(deco, "path")
            if first is not None or path_kw is not None:
                return deco
    return None


def annotation_names(annotation: ast.AST | None) -> set[str]:
    if annotation is None:
        return set()
    return {n.id for n in ast.walk(annotation) if isinstance(n, ast.Name)} | {
        n.attr for n in ast.walk(annotation) if isinstance(n, ast.Attribute)
    }


def marker_calls(node: ast.AST | None) -> list[str]:
    if node is None:
        return []
    return [
        last_name(n.func)
        for n in ast.walk(node)
        if isinstance(n, ast.Call) and last_name(n.func) in MARKERS
    ]


def model_class_names(trees: list[tuple[Path, ast.Module]]) -> set[str]:
    """Class names whose bases lead, by name, to `BaseModel` (a name-only closure)."""
    bases: dict[str, set[str]] = {}
    for _, tree in trees:
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                bases.setdefault(node.name, set()).update(
                    b for b in (last_name(base) for base in node.bases) if b
                )
    models = {"BaseModel"}
    changed = True
    while changed:
        changed = False
        for name, parents in bases.items():
            if name not in models and parents & models:
                models.add(name)
                changed = True
    return models


def looks_like_body(param: ast.arg, default: ast.AST | None, aliases: set[str]) -> bool:
    """An approximation of N4's body rule, without type resolution.

    A parameter is a body if a Body/Form/File marker is written, or if it has no other marker, is
    not Depends, is not a special type, and its annotation names a model class (a class whose
    bases lead to `BaseModel` by name), or is a `list[...]`/`dict[...]`.
    """
    annotation = param.annotation
    markers = marker_calls(annotation) + marker_calls(default)
    if any(m in BODY_MARKERS for m in markers):
        return True
    if markers or "Depends" in annotation_names(annotation) or last_name(default) == "Depends":
        return False
    names = annotation_names(annotation)
    if names & SPECIAL_TYPES or names & aliases:
        return False
    if isinstance(annotation, ast.Subscript) and last_name(annotation.value) in {
        "list",
        "List",
        "dict",
        "Dict",
    }:
        return True
    return bool(names & MODELS)


def alias_values(tree: ast.Module) -> list[ast.AST]:
    values: list[ast.AST] = []
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None:
            if annotated_alias_value(node.value):
                values.append(node.value)
        elif isinstance(node, ast.TypeAlias) and annotated_alias_value(node.value):
            values.append(node.value)
    return values


def count_file(path: Path, tree: ast.Module, all_aliases: set[str], tally: Counter[str]) -> None:
    here_aliases = module_aliases(tree)
    tally["annotated_alias_definitions"] += len(here_aliases)
    for value in alias_values(tree):
        inner = [last_name(n.func) for n in ast.walk(value) if isinstance(n, ast.Call)]
        if "Depends" in inner or "Security" in inner:
            tally["  aliases that hold a Depends"] += 1
        if any(n in MARKERS for n in inner):
            tally["  aliases that hold a Query/Path/Header/Cookie/Body/Form/File marker"] += 1
        for n in ast.walk(value):
            if (
                isinstance(n, ast.Call)
                and last_name(n.func) in {"Depends", "Security"}
                and n.args
                and isinstance(n.args[0], ast.Call)
            ):
                tally["  aliases whose Depends argument is a call result"] += 1
    for fn in ast.walk(tree):
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            a = fn.args
            for param in a.posonlyargs + a.args + a.kwonlyargs:
                if annotation_names(param.annotation) & all_aliases:
                    tally["any_function_params_typed_by_an_alias"] += 1
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = last_name(node.func)
            if name == "Depends" and node.args and isinstance(node.args[0], ast.Call):
                tally["depends_of_a_call_result"] += 1
            if name == "Security" and node.args and isinstance(node.args[0], ast.Call):
                tally["security_of_a_call_result"] += 1
            if name in {"Depends", "Security"}:
                tally[f"{name.lower()}_calls"] += 1
                if not node.args and keyword(node, "dependency") is None:
                    tally["depends_with_no_argument"] += 1
            if name in {"APIRouter", "FastAPI"}:
                tally[f"{name}_constructions"] += 1
                if keyword(node, "dependencies"):
                    tally[f"dependencies_on_{name}"] += 1
                if keyword(node, "prefix"):
                    tally[f"prefix_on_{name}"] += 1
            if isinstance(node.func, ast.Attribute):
                attr = node.func.attr
                if attr == "include_router":
                    tally["include_router_calls"] += 1
                    if keyword(node, "dependencies"):
                        tally["dependencies_on_include_router"] += 1
                    if keyword(node, "prefix"):
                        tally["prefix_on_include_router"] += 1
                if attr in {"api_route", "add_api_route"} and keyword(node, "methods"):
                    tally[f"methods_keyword_on_{attr}"] += 1
                if attr == "add_api_route":
                    tally["add_api_route_calls"] += 1
                if attr == "mount" or name == "Mount":
                    tally["mount_calls"] += 1
            if name == "Mount":
                tally["Mount_constructions"] += 1
            if name == "Field":
                for key in ("alias", "validation_alias", "serialization_alias"):
                    if keyword(node, key):
                        tally[f"Field_{key}"] += 1
            if name == "ConfigDict" or name == "Config":
                for key in ("alias_generator", "populate_by_name", "validate_by_name"):
                    if keyword(node, key):
                        tally[f"ConfigDict_{key}"] += 1
            if name in {"AliasChoices", "AliasPath"}:
                tally[name] += 1
        elif isinstance(node, ast.ClassDef):
            if node.name == "Config":
                tally["pydantic_v1_class_Config"] += 1
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "model_config":
                    tally["model_config_assignments"] += 1
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            deco = route_decorator(node)
            if deco is None:
                continue
            tally["route_handlers"] += 1
            written = keyword(deco, "response_model")
            if written is not None:
                tally["response_model_written"] += 1
            elif node.returns is not None:
                tally["return_annotation_only"] += 1
            else:
                tally["neither_written"] += 1
            if keyword(deco, "dependencies"):
                tally["dependencies_on_route_decorator"] += 1
            args = node.args
            params = args.posonlyargs + args.args + args.kwonlyargs
            defaults = [None] * (len(args.posonlyargs) + len(args.args) - len(args.defaults))
            defaults += list(args.defaults) + list(args.kw_defaults)
            bodies = 0
            multipart = 0
            for param, default in zip(params, defaults, strict=False):
                names = annotation_names(param.annotation)
                if names & all_aliases:
                    tally["handler_params_typed_by_an_alias"] += 1
                if looks_like_body(param, default, all_aliases):
                    bodies += 1
                    if set(marker_calls(param.annotation) + marker_calls(default)) & {
                        "Form",
                        "File",
                    }:
                        multipart += 1
                if last_name(default) in MARKERS:
                    tally["handler_params_marker_as_default"] += 1
                elif "Annotated" in names and any(
                    m in MARKERS for m in marker_calls(param.annotation)
                ):
                    tally["handler_params_marker_in_annotated"] += 1
                if "Header" in marker_calls(param.annotation) + marker_calls(default):
                    tally["handler_params_header_marked"] += 1
            if bodies > 1:
                tally["handlers_with_several_body_params_approx"] += 1
                if multipart:
                    tally["  of those, with a Form or File marker"] += 1
            if node.decorator_list and any(
                isinstance(d, (ast.Name, ast.Attribute))
                or (isinstance(d, ast.Call) and d is not deco)
                for d in node.decorator_list
            ):
                tally["route_handlers_with_another_decorator"] += 1


def count_root(root: Path) -> None:
    files = python_files(root)
    trees: list[tuple[Path, ast.Module]] = []
    unreadable = 0
    for path in files:
        try:
            trees.append((path, ast.parse(path.read_text(encoding="utf-8"), filename=str(path))))
        except (SyntaxError, UnicodeDecodeError, ValueError):
            unreadable += 1
    all_aliases = set().union(*(module_aliases(tree) for _, tree in trees)) if trees else set()
    MODELS.clear()
    MODELS.update(model_class_names(trees))
    non_test = Counter()
    every = Counter()
    for path, tree in trees:
        count_file(path, tree, all_aliases, every)
        if not is_test_path(path, root):
            count_file(path, tree, all_aliases, non_test)
    print(f"## {root}")
    print(
        f"files parsed: {len(trees)} (unreadable: {unreadable}); distinct alias names: {len(all_aliases)}"
    )
    keys = sorted(set(every) | set(non_test))
    print(f"{'count':52} {'all files':>10} {'outside tests':>14}")
    for key in keys:
        print(f"{key:52} {every[key]:>10} {non_test[key]:>14}")
    print()


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    for arg in argv:
        root = Path(arg).resolve()
        if not root.is_dir():
            print(f"not a directory: {root}", file=sys.stderr)
            return 1
        count_root(root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
