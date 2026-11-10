"""Sextant's copy of `humps.main.camelize` against the real function (plan 2, final review M2).

Two steps, each with its own interpreter. First, with an interpreter that has pyhumps installed
(mealie's environment has 3.8.0), never the repository's `.venv`:

    <mealie>/.venv/bin/python scripts/probes/humps_camelize.py names <out.json> <root>...

It reads every `.py` file under each root (ast only; a `.venv`, `node_modules` or `.git` folder
is not entered) and takes every name a class body annotates (a field name), every other
identifier (names, attributes, parameters, function and class names), and the edge cases below.
It writes each name with what `humps.main.camelize` returns for it. Then, with the repository's
own interpreter:

    .venv/bin/python scripts/probes/humps_camelize.py check <out.json>

compares Sextant's `humps_camelize` strategy on every name and prints each difference. What the
results mean is in `humps_camelize.md`. The first step calls pyhumps on purpose. Sextant itself
never does that (spec 7).
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

_SKIPPED = {".venv", "venv", "node_modules", ".git", "__pycache__"}
# Shapes the corpora may not hold: digits, underscores at either end or doubled, upper-case
# words, names already camel- or Pascal-case, hyphens and spaces.
EDGE_CASES = [
    "",
    "_",
    "__",
    "a",
    "A",
    "ID",
    "URL",
    "HTTP_code",
    "http_Code",
    "user_ID",
    "is_2fa_enabled",
    "max_len_3d",
    "x_1y",
    "a1_b2",
    "field_1",
    "_leading",
    "__dunder__",
    "trailing_",
    "trailing__",
    "field__double",
    "a___b",
    "camelCase",
    "PascalCase",
    "already_camelCase_x",
    "ABC_def",
    "aB_c",
    "Mixed_Case_Name",
    "kebab-case-name",
    "with space",
    "123",
    "1_a",
    "_1",
    "é_accent",
    "snake_case_with_numbers_123_x",
]


def _names(root: Path) -> tuple[set[str], set[str]]:
    """The field names (class-body annotations) and every other identifier under `root`."""
    fields: set[str] = set()
    others: set[str] = set()
    for path in sorted(root.rglob("*.py")):
        if _SKIPPED & set(path.relative_to(root).parts):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError, ValueError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for statement in node.body:
                    if isinstance(statement, ast.AnnAssign) and isinstance(
                        statement.target, ast.Name
                    ):
                        fields.add(statement.target.id)
            if isinstance(node, ast.Name):
                others.add(node.id)
            elif isinstance(node, ast.Attribute):
                others.add(node.attr)
            elif isinstance(node, ast.arg):
                others.add(node.arg)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                others.add(node.name)
    return fields, others - fields


def names(out: Path, roots: list[Path]) -> None:
    import importlib.metadata

    from humps.main import camelize

    fields: set[str] = set()
    others: set[str] = set()
    for root in roots:
        found, rest = _names(root)
        fields |= found
        others |= rest
    others -= fields
    edge = set(EDGE_CASES) - fields - others
    document = {
        "pyhumps": importlib.metadata.version("pyhumps"),
        "python": sys.version.split()[0],
        "roots": [str(root) for root in roots],
        "groups": {
            "field names": {name: camelize(name) for name in sorted(fields)},
            "other identifiers": {name: camelize(name) for name in sorted(others)},
            "edge cases": {name: camelize(name) for name in EDGE_CASES},
        },
    }
    out.write_text(json.dumps(document, indent=1, ensure_ascii=False), encoding="utf-8")
    print(
        f"pyhumps {document['pyhumps']}: {len(fields)} field names, {len(others)} other "
        f"identifiers, {len(EDGE_CASES)} edge cases ({len(edge)} not already among the names)"
    )


def check(path: Path) -> None:
    from sextant.application.resolve.shapes.model_fields import STRATEGIES

    ours = STRATEGIES["humps_camelize"]
    camel = STRATEGIES["camel"]
    document = json.loads(path.read_text(encoding="utf-8"))
    print(f"pyhumps {document['pyhumps']} on Python {document['python']}")
    total = 0
    for group, pairs in document["groups"].items():
        differ = [(name, want, ours(name)) for name, want in pairs.items() if ours(name) != want]
        to_camel = sum(1 for name, want in pairs.items() if camel(name) != want)
        total += len(differ)
        print(
            f"{group}: {len(pairs)} names, {len(differ)} differ from humps_camelize, "
            f"{to_camel} differ from to_camel"
        )
        for name, want, got in differ:
            print(f"   {name!r}: pyhumps {want!r}, Sextant {got!r}")
    print(f"differences: {total}")


if __name__ == "__main__":
    if sys.argv[1] == "names":
        names(Path(sys.argv[2]), [Path(root) for root in sys.argv[3:]])
    else:
        check(Path(sys.argv[2]))
