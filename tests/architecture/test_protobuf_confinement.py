"""Schema-format confinement (2G design §3): exactly one module in the system
understands a schema format, and exactly one shells to a schema compiler.

The layering contracts in `pyproject.toml` reason about `sextant.*` packages,
so neither can see an import of a third-party runtime. This rule is about a
third-party import, and it is the rule the whole "dumb extractor / one
interpreter" layering rests on: a second reader of `google.protobuf` is a
second place that knows what a descriptor means, and the next schema format
would then need adding twice.

`grpc_tools` is confined the same way for the same reason, one step earlier —
compiling `.proto` text is the source-file reader's job, not the
interpreter's, and not anybody else's.
"""

import ast
from pathlib import Path

SOURCE_ROOT = Path(__file__).parents[2] / "src" / "sextant"

# The interpreter of 2G design §3, and the `.proto` reader of §2. The reader
# arrives with the readers task; until it does, its allowlist entry names a
# file that does not exist yet, which is exactly what an allowlist should do —
# permit, never require.
INTERPRETER = SOURCE_ROOT / "ingress" / "interpret" / "descriptors.py"
PROTO_READER = SOURCE_ROOT / "ingress" / "read" / "proto_source.py"


def _imported_modules(path: Path) -> set[str]:
    """Every module name a file imports, dotted — `from x import y` counted
    as both `x` and `x.y`, so a package reached through either spelling is
    seen."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            names |= {f"{node.module}.{alias.name}" for alias in node.names}
    return names


def _importers(package: str) -> list[Path]:
    """Every Python source Sextant ships that imports the package or anything
    under it."""
    return sorted(
        path
        for path in SOURCE_ROOT.rglob("*.py")
        if any(
            name == package or name.startswith(f"{package}.") for name in _imported_modules(path)
        )
    )


def _offenders(package: str, allowed: Path) -> list[str]:
    return [str(path.relative_to(SOURCE_ROOT)) for path in _importers(package) if path != allowed]


def test_the_protobuf_runtime_is_imported_only_by_the_interpreter():
    assert _offenders("google.protobuf", INTERPRETER) == []


def test_the_schema_compiler_is_imported_only_by_the_proto_reader():
    assert _offenders("grpc_tools", PROTO_READER) == []


def test_the_check_finds_the_protobuf_runtime_where_one_is_allowed_to_be():
    """A confinement check that matches nothing anywhere passes for the wrong
    reason. The interpreter is the one module that must read descriptors, so
    the check must see the import there."""
    assert INTERPRETER in _importers("google.protobuf")
