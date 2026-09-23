"""The `sextant` CLI (2N Task 5, §5b): every command below is a thin
wrapper over `sextant.api`'s own composition — parse flags, call one
function there, translate a `SextantError` into a `click.ClickException`
carrying the SAME message the API raised, then print exactly what this
module printed before the extraction. `sextant.api`'s own module docstring
carries the composition's rationale; this module carries only the CLI's own
concerns — flag parsing, `RichProgress`, and the exact text each command has
always printed."""

import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import click

from sextant import api
from sextant.application.ports.progress import Progress
from sextant.cli.progress import RichProgress


@click.group()
def cli() -> None:
    """Sextant — architecture from compiled code."""


@cli.group()
def module() -> None:
    """Operate on one buildable unit."""


@contextmanager
def _rich_progress() -> Iterator[Progress]:
    """The CLI's own `Progress` — a fresh `RichProgress` per module, closed
    when the `with` block exits. `sextant.api` never imports `RichProgress`
    itself (its own "quiet" contract); this is the one place that hands it
    one, through the same `Progress` port `application.stages.analyze`
    already defines."""
    progress = RichProgress()
    try:
        yield progress
    finally:
        progress.close()


# The table's dir column (2M Task 2 fix round 1, F8): a cap, not a guess at
# a terminal width — one fixed number keeps the column, and therefore the
# two columns after it, aligned regardless of how long any one module's
# relative path happens to be.
_TABLE_DIR_WIDTH = 50


def _truncated(text: str, width: int) -> str:
    return text if len(text) <= width else text[: width - 1] + "…"


@module.command("analyze")
@click.argument("path", type=click.Path(exists=True, path_type=Path))
@click.option("--workspace", "workspace_dir", type=click.Path(path_type=Path), default=None)
@click.option(
    "--allow-resolve",
    "allow_resolve",
    is_flag=True,
    default=False,
    help="Permit one online dependency-resolution retry when the detector needs it.",
)
@click.option(
    "--shadow",
    "shadow",
    is_flag=True,
    default=False,
    help=(
        "Also record what the backward value walk WOULD resolve, into `value_resolutions`. "
        "Publishes nothing: every other table is what it would be without this flag."
    ),
)
def module_analyze(
    path: Path, workspace_dir: Path | None, allow_resolve: bool, shadow: bool
) -> None:
    try:
        result, multi_module = api._analyze(
            path,
            workspace_dir=workspace_dir,
            allow_resolve=allow_resolve,
            progress_factory=_rich_progress,
            on_module=click.echo,
            shadow=shadow,
        )
    except api.SextantError as refused:
        raise click.ClickException(str(refused)) from refused

    if not multi_module:
        click.echo(json.dumps({"endpoints": result.modules[0].endpoints}))
        return

    # No header, no rows, for an empty reactor (2M Task 2 fix round 1, F8):
    # a table with a header and nothing under it reads as a tool that found
    # nothing to say, not as the honest empty case it is.
    if not result.modules:
        return
    click.echo()
    click.echo(f"{'dir':<{_TABLE_DIR_WIDTH}} {'kind':<15} analyzed")
    for outcome in result.modules:
        dir_cell = _truncated(outcome.dir, _TABLE_DIR_WIDTH)
        analyzed_cell = "yes" if outcome.analyzed else "no"
        click.echo(f"{dir_cell:<{_TABLE_DIR_WIDTH}} {outcome.kind:<15} {analyzed_cell}")


@module.command("render")
@click.argument("path", type=click.Path(exists=True, path_type=Path))
@click.option("--workspace", "workspace_dir", type=click.Path(path_type=Path), default=None)
def module_render(path: Path, workspace_dir: Path | None) -> None:
    """Reads the workspace `analyze` left behind — it never re-detects,
    re-scans, or re-resolves (M00 "no analysis"; the workspace persists
    precisely so render is a cheap read).

    It takes no display flag: one module, one document, and that document is
    the complete one (GUIDELINES §8.4)."""
    try:
        result = api._render(path, workspace_dir=workspace_dir)
    except api.SextantError as refused:
        raise click.ClickException(str(refused)) from refused
    click.echo(str(result.markdown))
    click.echo(str(result.html))


@module.command("enrich")
@click.argument("path", type=click.Path(exists=True, path_type=Path))
@click.option("--workspace", "workspace_dir", type=click.Path(path_type=Path), default=None)
@click.option(
    "--agent",
    "agent_flag",
    default=None,
    help=(
        "For a live run, an `AGENT_REGISTRY` name (refused if unknown). Under "
        "--ingest/--dry-run, no adapter runs — a free-text label for the "
        "overlay's provenance instead."
    ),
)
@click.option("--model", "model_flag", default=None, help="Passed to the agent verbatim.")
@click.option("--max-turns", "max_turns_flag", type=int, default=None)
@click.option(
    "--auth",
    "auth_flag",
    type=click.Choice(["subscription", "api-key"]),
    default=None,
    help=(
        "Tradewind's backend for a live run: `subscription` (the machine's "
        "logged-in Claude Code), `api-key` (ANTHROPIC_API_KEY, read by Sextant). "
        "Default: subscription."
    ),
)
@click.option("--dry-run", is_flag=True, default=False, help="Write the brief; call no agent.")
@click.option(
    "--ingest",
    "ingest_path",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Validate an externally-authored answers file instead of calling an agent.",
)
def module_enrich(
    path: Path,
    workspace_dir: Path | None,
    agent_flag: str | None,
    model_flag: str | None,
    max_turns_flag: int | None,
    auth_flag: str | None,
    dry_run: bool,
    ingest_path: Path | None,
) -> None:
    """Composes the brief, runs the agent (or a `--dry-run`/`--ingest` door),
    validates the answer by construction, writes `.sextant-enrichment.json`,
    and auto-assembles both rendered outputs — one command, done (2K design
    §8: "no second render command"). Refuses a workspace with no rendered
    document, naming `render`, before composing anything."""
    try:
        outcome = api._enrich(
            path,
            workspace_dir=workspace_dir,
            agent_flag=agent_flag,
            model_flag=model_flag,
            max_turns_flag=max_turns_flag,
            auth_flag=auth_flag,
            dry_run=dry_run,
            ingest_path=ingest_path,
            # The same shape `on_module=click.echo` already gives `analyze`
            # (2N Task 5 fix round 1, MAJOR-1): `_enrich`'s own docstring
            # states exactly where this fires, and why it can no longer be
            # printed here, after the call returns — a later assembly
            # failure raises before returning at all.
            on_report=click.echo,
        )
    except api.SextantError as refused:
        raise click.ClickException(str(refused)) from refused

    if dry_run:
        click.echo(str(outcome.brief_path))
        click.echo(str(outcome.instructions_copy_path))
        return

    click.echo(str(outcome.overlay_path))
    click.echo(str(outcome.markdown))
    click.echo(str(outcome.html))


@module.command("export")
@click.argument("path", type=click.Path(exists=True, path_type=Path))
@click.option("--workspace", "workspace_dir", type=click.Path(path_type=Path), default=None)
@click.option("--out", "out_dir", type=click.Path(path_type=Path), default=None)
def module_export(path: Path, workspace_dir: Path | None, out_dir: Path | None) -> None:
    """Writes the analysis out as a D06 bundle: Parquet plus a manifest. Reads
    what `analyze` left — it never re-analyzes (M08). Publishing the directory
    anywhere is the caller's business; Sextant does not talk to artifact
    stores."""
    try:
        result = api._export(path, workspace_dir=workspace_dir, out_dir=out_dir)
    except api.SextantError as refused:
        raise click.ClickException(str(refused)) from refused
    click.echo(str(result.bundle))
