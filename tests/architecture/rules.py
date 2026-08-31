"""Source-level architecture rules (ARCHITECTURE §10).

import-linter reasons about imports between packages. Four of §10's rules are
about what a file *says* — a protocol name in a query, a Kotlin flag in the
resolver — which no import contract can see. These read the source instead.

Comments and docstrings are excluded on purpose. Explaining *why* a rule exists
often requires naming the thing it forbids, and a rule that punished its own
rationale would be quietly deleted. What counts is identifiers and string
literals: the parts that change behaviour.
"""

import ast
import re
from pathlib import Path

SRC = Path(__file__).parents[2] / "src" / "sextant"

# Catalogs are data, not code, and framework names are precisely what they are
# for (D02). Scanning them would forbid the design.
_DATA = {"catalogs"}


def python_files(*relative: str) -> list[Path]:
    roots = [SRC.joinpath(part) for part in relative] or [SRC]
    return sorted(
        path
        for root in roots
        for path in root.rglob("*.py")
        if not set(path.relative_to(SRC).parts) & _DATA
    )


def sql_files(*relative: str) -> list[Path]:
    roots = [SRC.joinpath(part) for part in relative] or [SRC]
    return sorted(path for root in roots for path in root.rglob("*.sql"))


def yaml_files(*relative: str) -> list[Path]:
    roots = [SRC.joinpath(part) for part in relative] or [SRC]
    return sorted(path for root in roots for path in root.rglob("*.yml"))


def code_words(path: Path) -> set[str]:
    """Every identifier and string literal in a file, lowercased.

    Docstrings and comments are left out — see the module docstring.
    """
    if path.suffix == ".sql":
        stripped = re.sub(r"--[^\n]*", "", path.read_text(encoding="utf-8"))
        return _words(stripped)

    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings = {
        node.body[0].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
    }

    words: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node not in docstrings:
                words |= _words(node.value)
        elif isinstance(node, ast.Name):
            words |= _split(node.id)
        elif isinstance(node, ast.Attribute):
            words |= _split(node.attr)
        elif isinstance(node, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            words |= _split(node.name)
        elif isinstance(node, ast.arg):
            words |= _split(node.arg)
        elif isinstance(node, ast.alias):
            words |= _split(node.name.replace(".", "_"))
            if node.asname:
                words |= _split(node.asname)
        elif isinstance(node, ast.ImportFrom) and node.module:
            words |= _split(node.module.replace(".", "_"))
    return words


def _words(text: str) -> set[str]:
    """Every token, and its parts.

    A compound name hides its halves: `spring_http` must answer to both, or a
    framework name survives by being glued to something else — which a mutation
    of this rule proved it could.
    """
    found: set[str] = set()
    for token in re.findall(r"[A-Za-z0-9_]+", text):
        found.add(token.lower())
        found |= _split(token)
    return found


def _split(identifier: str) -> set[str]:
    """`AsmScanner` and `extract_jvm` both yield their parts."""
    spaced = re.sub(r"(?<!^)(?=[A-Z])", " ", identifier).replace("_", " ")
    return set(spaced.lower().split())


def offenders(files: list[Path], forbidden: set[str]) -> dict[Path, set[str]]:
    """Which files use which forbidden words, for an error a reader can act on."""
    found = {}
    for path in files:
        hits = code_words(path) & forbidden
        if hits:
            found[path.relative_to(SRC)] = hits
    return found
