"""`anthropic` confinement (2K design §3, Task 6 brief): exactly one module
in the system is permitted to import the `anthropic` SDK — the ONE
sanctioned model-calling seam DR-2's amendment carves out (2K design §8).
Mirrors `tests/architecture/test_protobuf_confinement.py`'s own pattern for
`google.protobuf`: a package-level scan for the import, an allowlist of
one file, and a positive control proving the scan would actually catch a
violation rather than passing because nothing here imports the package at
all.

The layering contract in `pyproject.toml` (`agents` as a new outer group,
independent of `ingress`/`storage`/`egress`) is exercised by the generic
`tests/architecture/test_layering.py::test_import_contracts_hold_when_the_suite_runs`
once `lint-imports` runs against the extended contracts — nothing here
duplicates that check.
"""

import ast
import sys
from pathlib import Path

SOURCE_ROOT = Path(__file__).parents[2] / "src" / "sextant"

# The one file DR-2's amendment permits to import `anthropic` (2K design §3).
CLAUDE_API = SOURCE_ROOT / "agents" / "claude_api.py"


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
    """Every Python source Sextant ships that imports the package or
    anything under it."""
    return sorted(
        path
        for path in SOURCE_ROOT.rglob("*.py")
        if any(
            name == package or name.startswith(f"{package}.") for name in _imported_modules(path)
        )
    )


def test_the_anthropic_sdk_is_imported_only_by_the_claude_api_adapter():
    offenders = [
        str(path.relative_to(SOURCE_ROOT)) for path in _importers("anthropic") if path != CLAUDE_API
    ]
    assert offenders == []


def test_the_check_finds_the_anthropic_sdk_where_one_is_allowed_to_be():
    """A confinement check that matches nothing anywhere passes for the
    wrong reason. `claude_api.py` is the one module that must reach the
    SDK, so the check must see the import there."""
    assert CLAUDE_API in _importers("anthropic")


def test_the_check_would_catch_a_module_that_imports_anthropic_elsewhere(tmp_path, monkeypatch):
    """`test_the_anthropic_sdk_is_imported_only_by_the_claude_api_adapter`
    asserts an empty offender list, which passes for two reasons a bare
    empty list cannot tell apart: no violation, or a checker blind to one.
    Nothing shipped imports `anthropic` outside the adapter — that is the
    point of the rule — so the positive control has to be synthetic, the
    same way the protobuf confinement test's `grpc_tools` control is."""
    offender = tmp_path / "offender.py"
    offender.write_text("import anthropic\n", encoding="utf-8")
    monkeypatch.setattr(sys.modules[__name__], "SOURCE_ROOT", tmp_path)
    assert _importers("anthropic") == [offender]


def test_agents_imports_no_ingress_storage_or_egress():
    """The `agents` outer group's own rule (2K design §8): it imports
    `application`/`domain` inward like any outer group, and nothing else
    outward. The layers contract already enforces this at the `pyproject.toml`
    level; this is the source-level half, independent of whether the
    contract file stays in sync."""
    forbidden = {"sextant.ingress", "sextant.storage", "sextant.egress"}
    offending: dict[str, set[str]] = {}
    for path in (SOURCE_ROOT / "agents").rglob("*.py"):
        hits = {
            name
            for name in _imported_modules(path)
            if any(name == group or name.startswith(f"{group}.") for group in forbidden)
        }
        if hits:
            offending[str(path.relative_to(SOURCE_ROOT))] = hits
    assert offending == {}
