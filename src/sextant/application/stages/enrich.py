"""The enrich stage (2K design §5/§8): refuse-if-unrendered, compose the
brief, then turn whichever door supplied the answers — the real agent, or
an externally-authored `--ingest` file — into a validated, honestly-labelled
`EnrichmentOverlay`.

**What this module does not do.** `application` reads no files (an
architecture rule `tests/architecture/test_source_rules.py` enforces by AST,
not merely by convention) — the composition root (`cli/app.py`'s
`module_enrich`) reads `architecture.md`/`metadata.json` off disk and hands
this module their CONTENT, and is likewise the one that writes the overlay
file, the transcript, and the two rendered documents (which also needs
`egress.render`, itself off limits to `application` by the import-linter
layering). This module makes decisions over data it is handed; it touches no
path.
"""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter, ValidationError

from sextant.application.enrich.brief import compose_brief
from sextant.application.enrich.tools import ToolDefinition
from sextant.application.enrich.validate import Refusal, validate_overlay
from sextant.application.ports.enrichment import EnrichmentBrief
from sextant.application.ports.workspace import Workspace
from sextant.domain.enrichment import Claim, EnrichmentOverlay, Provenance
from sextant.domain.redaction import Redactor

_CLAIMS = TypeAdapter(list[Claim])


class NotRenderedError(RuntimeError):
    """The workspace carries no rendered `architecture.md` — enrich needs
    one to compose a brief from and refuses rather than assembling a brief
    around a document that does not exist (2K design §8: "enrich still
    refuses a workspace with no rendered doc ... tell the user to render
    first, loudly, with the command")."""


class MalformedAnswersError(RuntimeError):
    """The answer text — the agent's own final response, or an `--ingest`
    file — is not a JSON array the overlay's claim schema can parse at all.

    Distinct from `validate.Refusal`: a Refusal is a well-FORMED claim
    naming something that does not exist (a phantom member, a citation to a
    file that is not there) and is reported per claim while every other
    claim in the same answer is still considered. This is the answer not
    being a list of claims in the first place — nothing here can be
    validated claim by claim, so the whole run is refused rather than
    guessing at which fragment the author meant.
    """


class EmptyPartialAnswerError(RuntimeError):
    """A partial answer whose text is empty (2N design §1) — a capped run
    that produced no final text at all, reachable on any adapter whose loop
    can end mid-turn with nothing yet written. Distinct from
    `MalformedAnswersError`: an empty string is not "text that exists and
    does not parse" — it is the honest absence `partial_reason` already
    explains, so the failure names THAT reason rather than describing a JSON
    parse that was never attempted."""


@dataclass(frozen=True)
class EnrichResult:
    """One run's outcome, whichever door supplied the answers.

    `overlay` carries only the ACCEPTED claims — `validate.py`'s own module
    docstring states a refused claim is "never written", and that holds all
    the way to the file `cli/app.py` writes, not only to what render shows.
    `refusals` is the honest report of what did not make it and why (2K
    design §6, spec §10's refused-at-ingest golden case).
    `partial`/`partial_reason` carry `EnrichmentAnswers`' own honesty record
    forward unchanged (2K Task 7 ruling 4) — `False`/`None` for `--ingest`,
    which has no notion of a truncated run.
    """

    overlay: EnrichmentOverlay
    refusals: tuple[Refusal, ...]
    partial: bool
    partial_reason: str | None
    transcript: tuple[dict[str, object], ...]


def compose(
    workspace: Workspace,
    module_root: Path,
    instructions: str,
    architecture_md: str | None,
    metadata: dict[str, Any],
    redactor: Redactor,
    tool_definitions: tuple[ToolDefinition, ...],
    jailed_roots: tuple[Path, ...],
) -> EnrichmentBrief:
    """The brief for one run over `module_root` — what every door composes
    before any answer exists, and the whole of what `--dry-run` writes.

    `architecture_md` is `None` for exactly one reason: the composition root
    could not find a rendered document to read (2K design §8's
    refuse-if-unrendered gate). Refused here, loudly, naming the exact
    command to run — the DECISION belongs to the stage even though the
    FILESYSTEM CHECK that produced `None` had to happen one layer out
    (`application` reads no files; see the module docstring).
    """
    if architecture_md is None:
        raise NotRenderedError(
            f"{module_root} has no rendered document — run "
            f"`sextant module render {module_root}` first"
        )
    return compose_brief(
        workspace,
        module_root,
        instructions,
        architecture_md,
        metadata,
        redactor,
        tool_definitions,
        jailed_roots,
    )


def _extracted_array(answers_text: str) -> str:
    """The JSON array inside `answers_text`, tolerating the one wrapper a
    live engine actually produces.

    INSTRUCTIONS says "a single JSON array and nothing else", and the
    api-key path obeys. But the subscription path runs the Claude Code
    ENGINE, whose persona narrates — the first live flight (2026-09-03)
    returned a perfect claims array wrapped in one line of prose and a
    ```json fence, and a strict parse threw the whole run away at char 0. A
    later flight returned the mirror image: a bare array followed by a
    trailing sentence of narration, which fails a strict parse for the same
    reason at the opposite end. Leniency here is bounded and honest: text
    that already parses AS AN ARRAY is returned untouched; otherwise the
    slice from the first `[` to the last `]` is tried — the narrowest rule
    that unwraps prose and fences, leading or trailing, without ever
    INVENTING structure. Anything else still fails as malformed, and
    validation-by-construction downstream judges every claim exactly as
    before; nothing about leniency loosens what a claim must prove."""
    stripped = answers_text.strip()
    try:
        if isinstance(json.loads(stripped), list):
            return stripped
    except json.JSONDecodeError:
        pass
    start = stripped.find("[")
    end = stripped.rfind("]")
    if start != -1 and end > start:
        return stripped[start : end + 1]
    return stripped


def validate_and_finish(
    answers_text: str,
    workspace: Workspace,
    module_root: Path,
    redactor: Redactor,
    agent_name: str,
    model_name: str,
    instructions_hash: str,
    workspace_fingerprint: str,
    partial: bool = False,
    partial_reason: str | None = None,
    transcript: tuple[dict[str, object], ...] = (),
    run_at: str | None = None,
) -> EnrichResult:
    """`answers_text` (the agent's final response text, or an `--ingest`
    file's whole content) turned into a validated `EnrichResult` — the step
    every door shares once it has answers, agent-driven or supplied.

    `run_at` defaults to now, in UTC, to the second (2K design §6's own
    `Provenance.run_at`: carried as written text, ISO 8601, so a caller
    pinning a golden fixture's run_at need only pass one through rather than
    patch a clock).
    """
    if partial and not answers_text.strip():
        # 2N design §1: a capped run that produced no final text is a loud
        # failure NAMING the partial reason, never `MalformedAnswersError`
        # — there is no JSON to have failed to parse. Checked before the
        # `json.loads` below, which an empty string would otherwise fail on
        # the wrong way (a decode error, not this honest absence).
        raise EmptyPartialAnswerError(
            f"the run ended early ({partial_reason}) and returned no answers"
        )
    try:
        raw = json.loads(_extracted_array(answers_text))
        claims = _CLAIMS.validate_python(raw)
    except (json.JSONDecodeError, ValidationError) as broken:
        raise MalformedAnswersError(
            f"the answer is not a JSON array of claims the overlay schema accepts: {broken}"
        ) from broken

    provenance = Provenance(
        model=model_name,
        agent=agent_name,
        instructions_hash=instructions_hash,
        redaction_set_hash=redactor.rule_set_hash,
        run_at=run_at or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        workspace_fingerprint=workspace_fingerprint,
    )
    draft = EnrichmentOverlay(produced_by=provenance, claims=claims)
    accepted, refusals = validate_overlay(draft, workspace, module_root, redactor)
    overlay = EnrichmentOverlay(produced_by=provenance, claims=list(accepted))
    return EnrichResult(
        overlay=overlay,
        refusals=refusals,
        partial=partial,
        partial_reason=partial_reason,
        transcript=transcript,
    )
