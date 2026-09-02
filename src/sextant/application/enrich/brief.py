"""`compose_brief` — the deterministic half of enrichment (2K design §5).

Everything an agent is handed for one run, built once and never touched
again after: the machine-rendered `architecture.md`, `metadata.json`'s own
gaps, every `open_questions` row (its `path` `redact_text`-ed — 2K Task 7
ruling 1, "the brief IS the wire"), a digest of the endpoint and config rows
the graph itself marked doubtful, the four content requests, and the closed
anchor list a claim may place itself at. Same workspace, same rendered
document, same overlay-free run → the same prompt bytes (NFR-1's one stated
exception is the model's own response, never the brief that produced it).

Nothing here talks to a model, a tool, or the filesystem beyond the plain
strings it is handed — `architecture_md`/`metadata` are produced by the
caller (`cli/app.py`) so this module stays a pure function over data,
testable without a rendered workspace on disk.
"""

import json
from pathlib import Path
from typing import Any

from sextant.application.enrich.tools import ToolDefinition
from sextant.application.ports.enrichment import EnrichmentBrief
from sextant.application.ports.workspace import Workspace
from sextant.domain.redaction import Redactor

# The four content kinds 2K design §5 names, plus the verification seat
# (§7) — stated once, verbatim in every brief, so the request never drifts
# from run to run or reader to reader.
_CONTENT_REQUESTS = """Write whatever of the following you can genuinely ground in what you
read through the tools below — skip a kind entirely rather than restate
what the rendered document above already says, or write something you
cannot back with a real citation:

1. Components and their purposes — named groupings of the module's own
   types, and why they exist together.
2. Extension guides — how to add another operation, listener, or client
   call, following the pattern the module's own code already uses.
3. Algorithm descriptions — how a non-obvious piece of logic actually
   works, in prose.
4. Simplified class or sequence diagrams — a mermaid diagram showing the
   shape of something without reproducing the whole module.

And for every open question above that you can look into: a verdict —
an assessment grounded in what you found, or an honest `unanswered` with
what you searched and why it fell short. The graph never changes because
of what you write; a verdict only ever renders beside its question."""

# The closed set `domain/closed_sets.Anchor` names, restated here in the
# prose the brief itself uses — the enum is the authority INSTRUCTIONS.md
# and validation both check against; this is the brief's own reminder of
# where each claim it asks for belongs.
_ANCHOR_LINES = (
    "- `after-component-overview` — a `component` or `diagram` claim about the module as a whole.",
    "- `after-endpoint-table` — a `section` claim spanning several endpoints.",
    "- `beside-open-question` — a `verdict` claim, directly under the question it answers.",
    "- `end-of-document` — anything that does not belong beside a more specific position.",
)

# Resolutions the graph itself is unsure about (D01's closed Resolution set,
# 2F's doubtful evidence) — `resolved`/`partial` rows are not doubtful in
# the sense this digest exists for; `partial` is a shape's own resolution
# and does not appear on an endpoint row, but the check is written against
# both names it could plausibly carry rather than one, since a new doubtful
# marker landing here unnoticed would silently stop being surfaced.
_DOUBTFUL_RESOLUTIONS = frozenset({"unresolved", "narrowed"})


def compose_brief(
    workspace: Workspace,
    module_root: Path,
    instructions: str,
    architecture_md: str,
    metadata: dict[str, Any],
    redactor: Redactor,
    tool_definitions: tuple[ToolDefinition, ...],
    jailed_roots: tuple[Path, ...],
) -> EnrichmentBrief:
    """The brief for one enrichment run over `module_root`.

    `architecture_md` is the MACHINE-rendered document and nothing else (2K
    design §5): the caller assembles it in memory with no overlay rather than
    reading `render/architecture.md`, which after one `enrich` carries the
    previous run's own claims (2K final review, F1). `metadata` is read off
    disk by that same caller (`cli/app.py`, whose "refuse-if-unrendered"
    check, 2K design §8, still gates on the file's presence) — both passed in
    already-loaded so this function stays a pure projection of its arguments,
    the same reason `egress/render/document.py`'s own assembly takes its rows
    as plain sequences rather than reaching for a workspace path itself.

    `tool_definitions`/`jailed_roots` come from the same `ToolExecutor` the
    stage constructs to actually run the agent (or from a plain tuple for
    `--dry-run`, which never builds one) — carried through rather than built
    here, so there is exactly one `ToolExecutor` per run rather than one this
    function makes and a second the stage uses to execute calls.
    """
    module_id = str(metadata.get("module", {}).get("id", module_root.name))
    sections = [
        f"# Enriching {module_id}",
        "",
        (
            "Everything below is what Sextant already knows about this "
            "module. Read it, then use the tools you were given to look at "
            "the module's own source before you write anything — every "
            "claim you make has to trace back to something you actually "
            "read."
        ),
        "",
        "## Rendered document (architecture.md)",
        "",
        architecture_md.rstrip("\n"),
        "",
        "## Known gaps (metadata.json)",
        "",
        *(_gap_lines(metadata)),
        "",
        "## Open questions",
        "",
        *(_open_question_lines(workspace, redactor)),
        "",
        "## Rows the graph itself is unsure about",
        "",
        *(_doubtful_rows_digest(workspace, redactor)),
        "",
        "## What to produce",
        "",
        _CONTENT_REQUESTS,
        "",
        "## Where a claim may anchor",
        "",
        *_ANCHOR_LINES,
    ]
    prompt = "\n".join(sections) + "\n"
    return EnrichmentBrief(
        prompt=prompt,
        instructions=instructions,
        tool_definitions=tool_definitions,
        jailed_roots=jailed_roots,
    )


def _gap_lines(metadata: dict[str, Any]) -> list[str]:
    gaps = metadata.get("gaps", [])
    if not gaps:
        return ["None recorded."]
    return [f"- {gap}" for gap in gaps]


def _open_question_lines(workspace: Workspace, redactor: Redactor) -> list[str]:
    """Every `open_questions` row, verbatim except for `path` (2K Task 7
    ruling 1): `redact_text`-ed before it ever reaches the brief, so an
    address-shaped value the repository's own `redact:` section (or a plain
    `scheme://user:pass@host` literal) would mask is never handed to the
    model in the first place. Printed as the exact JSON `OpenQuestionRef`
    shape a `verdict` claim's `question` field carries, so an answer can
    copy it back unchanged.
    """
    rows = workspace.query("open_questions")
    if not rows:
        return ["None open."]
    lines: list[str] = []
    for row in rows:
        path = row.get("path")
        redacted_path = None if path is None else redactor.redact_text(str(path))
        identity = json.dumps(
            {
                "protocol": row.get("protocol"),
                "method": row.get("method"),
                "path": redacted_path,
                "kind": row.get("question"),
            },
            sort_keys=True,
        )
        lines.append(f"- {identity}")
        evidence = row.get("evidence")
        if evidence:
            lines.append(f"  - why this is open: {evidence}")
        candidates = json.loads(str(row.get("candidates") or "[]"))
        if candidates:
            lines.append(
                f"  - candidates considered and not chosen: "
                f"{json.dumps(candidates, sort_keys=True)}"
            )
    return lines


def _doubtful_rows_digest(workspace: Workspace, redactor: Redactor) -> list[str]:
    """Every endpoint row at `unresolved`/`narrowed` and every `resolved_config`
    row with no value, each with the reason already on record (2F's doubtful
    evidence, no new dataset — the same rows `egress/render/document.py`
    already surfaces in `architecture.md`'s own Coverage and endpoint tables,
    pulled out here as a standalone list rather than left for the model to
    re-derive by reading the whole document again)."""
    lines: list[str] = []
    doubtful_endpoints = [
        row
        for row in workspace.query("endpoints")
        if row.get("resolution") in _DOUBTFUL_RESOLUTIONS
    ]
    if doubtful_endpoints:
        lines.append("Endpoints:")
        for row in doubtful_endpoints:
            path = row.get("path")
            rendered_path = "(unresolved)" if path is None else redactor.redact_text(str(path))
            method = row.get("method")
            verb = f"{method} " if method else ""
            lines.append(
                f"- {row.get('protocol')} {verb}{rendered_path} — "
                f"resolution: {row.get('resolution')}"
            )
    doubtful_config = [
        row for row in workspace.query("resolved_config") if row.get("value") is None
    ]
    if doubtful_config:
        lines.append("Configuration:")
        for row in doubtful_config:
            lines.append(
                f"- {row.get('key')} — {row.get('unresolved_reason')} in {row.get('environment')}"
            )
    return lines or ["None recorded."]
