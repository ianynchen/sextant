"""Sextant reads itself (spec 2026-11-06-python-reader-design §7 item 1; plan 1 task 10).

The repository root is analysed once, as a user would run it, into a workspace outside the
tree. What is checked was read by hand from `src/sextant/cli/app.py` and `pyproject.toml`
`[project.scripts]`, never from a previous run:
- the root is one `sextant` module (a nested checkout such as `.claude/worktrees/*` is not
  a second one);
- the six commands are the six `entry_point` roots, each with a trace;
- the 24 parameters of those commands are their `request_params` rows;
- every call site has a target, or a reason from the one reason list.

One analysis for the file (about 9 s on the development Mac), shared read-only by every test,
as `tests/conftest.py`'s `analyzed_orders_service` is.
"""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from reason_guard import outside_the_list, stored_reason_tables, stored_reasons_outside_the_list
from sextant.application.query.trace import traces_of
from sextant.cli.app import cli
from sextant.domain.closed_sets import RootKind
from sextant.storage.duckdb.workspace import DuckDbWorkspace

REPO = Path(__file__).parents[2]

# `sextant` is `[project.scripts] sextant = "sextant.cli.app:cli"`; `module` and `system` are
# `@cli.group()` functions; each command is `@<group>.command("<word>")` on the function.
_COMMANDS = [
    ("sextant module analyze", "sextant/cli/app#module_analyze"),
    ("sextant module diff", "sextant/cli/app#module_diff"),
    ("sextant module enrich", "sextant/cli/app#module_enrich"),
    ("sextant module export", "sextant/cli/app#module_export"),
    ("sextant module render", "sextant/cli/app#module_render"),
    ("sextant system analyze", "sextant/cli/app#system_analyze"),
]

# Every `@click.argument` (required: none has a default) and `@click.option` above the six
# functions: `is_flag=True` is a flag, every other option is optional (none says `required`).
_PARAMS = sorted(
    [
        ("sextant module analyze", "argument", "path", "required"),
        ("sextant module analyze", "option", "--workspace", "optional"),
        ("sextant module analyze", "flag", "--allow-resolve", "optional"),
        ("sextant module analyze", "flag", "--shadow", "optional"),
        ("sextant system analyze", "argument", "path", "required"),
        ("sextant system analyze", "option", "--environment", "optional"),
        ("sextant module render", "argument", "path", "required"),
        ("sextant module render", "option", "--workspace", "optional"),
        ("sextant module enrich", "argument", "path", "required"),
        ("sextant module enrich", "option", "--workspace", "optional"),
        ("sextant module enrich", "option", "--agent", "optional"),
        ("sextant module enrich", "option", "--model", "optional"),
        ("sextant module enrich", "option", "--max-turns", "optional"),
        ("sextant module enrich", "option", "--auth", "optional"),
        ("sextant module enrich", "flag", "--dry-run", "optional"),
        ("sextant module enrich", "option", "--ingest", "optional"),
        ("sextant module export", "argument", "path", "required"),
        ("sextant module export", "option", "--workspace", "optional"),
        ("sextant module export", "option", "--out", "optional"),
        ("sextant module diff", "argument", "a", "required"),
        ("sextant module diff", "argument", "b", "required"),
        ("sextant module diff", "option", "--out", "optional"),
        ("sextant module diff", "option", "--format", "optional"),
        ("sextant module diff", "flag", "--allow-producer-change", "optional"),
    ]
)


@pytest.fixture(scope="module")
def analyzed(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, str]:
    """The repository root, analysed once; the workspace and what the command printed on
    standard output (the progress lines go to standard error)."""
    workspace = tmp_path_factory.mktemp("sextant-reads-itself")
    result = CliRunner().invoke(
        cli, ["module", "analyze", str(REPO), "--workspace", str(workspace)]
    )
    assert result.exit_code == 0, result.output
    return workspace, result.stdout


@pytest.fixture(scope="module")
def workspace(analyzed: tuple[Path, str]):
    opened = DuckDbWorkspace(analyzed[0] / "workspace.duckdb")
    yield opened
    opened.close()


def _bare(symbol: str | None) -> str | None:
    """`sextant/cli/app#module_analyze` from the full symbol: no scheme, version or
    descriptor, so a version bump does not move the test."""
    return None if symbol is None else symbol.rsplit(" ", 1)[-1].split("(", 1)[0]


def test_the_repository_root_is_one_sextant_module(analyzed: tuple[Path, str]):
    """One module prints one JSON line, not the per-module table; its module fact is
    `sextant`, read from `pyproject.toml`."""
    path, output = analyzed
    assert [json.loads(line) for line in output.splitlines()] == [{"endpoints": 0}]
    modules = [
        json.loads(line)
        for line in (path / "facts" / "module.jsonl").read_text().splitlines()
        if json.loads(line)["kind"] == "module"
    ]
    assert [(m["module_id"], m["entry_points"]) for m in modules] == [
        ("sextant", {"sextant": "sextant.cli.app:cli"})
    ]


def test_the_six_commands_are_the_entry_point_roots(workspace: DuckDbWorkspace):
    roots = sorted(
        (row["path"], _bare(row["handler"]))
        for row in workspace.query("roots")
        if row["root_kind"] == str(RootKind.ENTRY_POINT)
    )
    assert roots == _COMMANDS


def test_each_command_has_a_trace_with_a_hop(workspace: DuckDbWorkspace):
    traced = {
        trace.root.identities[0].path: len(trace.steps)
        for trace in traces_of(workspace)
        if trace.root.kind is RootKind.ENTRY_POINT
    }
    assert sorted(traced) == [path for path, _ in _COMMANDS]
    assert all(steps >= 1 for steps in traced.values()), traced


def test_the_commands_parameters_are_their_request_params(workspace: DuckDbWorkspace):
    rows = [
        row
        for row in workspace.query("endpoint_metadata")
        if row["protocol"] is None and row["direction"] == "inbound"
    ]
    assert sorted((r["path"], r["kind"], r["name"], r["requirement"]) for r in rows) == _PARAMS
    assert {(r["resolution"], _bare(r["caller"])) for r in rows} == {
        ("resolved", handler) for _, handler in _COMMANDS
    }


def test_every_call_site_has_a_target_or_a_reason(workspace: DuckDbWorkspace):
    """A site the scanner wrote with an owner has its target. A site it left to the resolver
    has a `bound_receivers` row per path, naming an owner or a reason, or is a call of a
    function value whose edge enters the function's body (ruling R29); nothing else."""
    neither = list(
        workspace._connection.execute(
            """
            SELECT s.caller, s.ordinal, s.name FROM call_sites s
            WHERE s.owner IS NULL
              AND NOT EXISTS (
                  SELECT 1 FROM bound_receivers b
                  WHERE b.caller = s.caller AND b.ordinal = s.ordinal
                    AND (b.owner IS NOT NULL OR b.reason IS NOT NULL))
              AND NOT EXISTS (
                  SELECT 1 FROM call_edges e
                  WHERE e.caller = s.caller AND e.ordinal = s.ordinal AND e.callee IS NOT NULL)
            ORDER BY 1, 2
            """
        ).fetchall()
    )
    assert neither == []
    bound = [dict(row) for row in workspace.query("bound_receivers")]
    assert bound, "no site was left to the resolver: the check above would be vacuous"
    # No `detail=`: a bound row may carry one too (a `narrowed` row names the declared
    # union), so only an unbound row is required to have one.
    assert (
        outside_the_list(
            bound, "bound_receivers", "reason", found=lambda row: row["owner"] is not None
        )
        == []
    )
    assert [row for row in bound if row["reason"] is not None and not row["detail"]] == []


def test_the_one_reason_list_guard_holds_on_this_workspace(workspace: DuckDbWorkspace):
    """`tests/application/test_one_reason_list.py`'s check, over Sextant's own tables."""
    tables = stored_reason_tables(workspace)
    assert any(row["reason"] for row in tables["method_resolution"])
    assert stored_reasons_outside_the_list(tables) == []
