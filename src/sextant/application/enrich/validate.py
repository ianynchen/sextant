"""Validation by construction (2K design §6) and staleness (design §6, "at
render").

**The one rule this module enforces: a claim naming a phantom is never
written.** The schema (`domain/enrichment.py`) says a claim is well FORMED;
this says it is well GROUNDED — the member symbols, the diagram's nodes, the
cited files and the question a verdict answers all have to exist in the
workspace and the module the claim was made about. A model that invents a
class name gets its claim refused with the reason, at ingest, before the
overlay is written.

**Staleness is the same check, later.** `stale_claims` re-runs `validate_overlay`
against a CURRENT workspace: a claim that was grounded when it was written and
whose referents have since vanished from the graph comes back refused, and
render excludes it with a visible count line rather than showing a claim about
code that is gone. One implementation, two names — a second copy of the checks
would drift, and the drift would be silent in exactly the direction that
matters (accepted at ingest, invisible at render, or the reverse).

**What the checks compare, precisely.**

- **Component members** are compared as full descriptors (`domain/symbols.py`'s
  `bare_descriptor` — D00 §5a: a symbol is module coordinates then a
  descriptor, and only the descriptor is ever compared). A claim may spell a
  member either way, with coordinates or without; a claim may not name a type
  that is not in the workspace.
- **Diagram nodes** are compared as SIMPLE names, because a mermaid node id is
  an identifier and a descriptor is not one. That is a weaker check than the
  member check by construction: two classes of the same name in different
  packages are indistinguishable here, and this module does not pretend
  otherwise. Stated rather than tightened — the alternative is refusing a
  correct diagram over a notation the format cannot express.
- **Cited files** must resolve to a file UNDER the module root. Containment is
  checked after resolution, so a cite escaping through `..` or a symlink is
  refused rather than followed.
- **A verdict's question** must match an `open_questions` row on all four of
  protocol, method, path and kind. Matching is against the row's own values as
  the workspace holds them.
"""

import re
from dataclasses import dataclass
from pathlib import Path

from sextant.application.ports.workspace import Workspace
from sextant.domain.enrichment import (
    UNANSWERED,
    Claim,
    ComponentClaim,
    DiagramClaim,
    EnrichmentOverlay,
    SectionClaim,
    VerdictClaim,
    question_identity,
)
from sextant.domain.symbols import bare_descriptor, simple_name

# The diagram node scan (2K design §6, "every node/participant must validate
# against real symbols"), stated exactly because a reader has to know what is
# NOT covered:
#
#   a line whose first word — leading whitespace aside — is `class`,
#   `participant` or `actor` contributes the identifier that follows it, and
#   nothing else on the line does.
#
# That is a class declaration in a `classDiagram` (`class OrderView {`, `class
# OrderView`) and a participant declaration in a `sequenceDiagram`
# (`participant OrderView`, `participant OrderView as the view` — the alias is
# a label for humans, so the identifier before `as` is what gets checked).
#
# **Conservative on purpose: what the rule cannot see is not validated and not
# refused.** A node introduced only by an edge (`A --> B`), a message arrow, a
# note, a namespace block or a `class` line the model spelled unusually is
# invisible here — it passes, unchecked. The alternative is a scan that guesses
# at mermaid's grammar and refuses TRUE claims when it guesses wrong, and a
# validator that rejects correct work teaches its user to stop running it. The
# claim still carries `evidence: llm` and the diagram still says what it elides;
# this check catches the invented class name, not every possible one.
_NODE_DECLARATION = re.compile(r"^[ \t]*(?:class|participant|actor)[ \t]+([A-Za-z_][\w$]*)")


@dataclass(frozen=True)
class Refusal:
    """One claim that could not be accepted, by its position in the overlay's
    own `claims` list and the reason in the words a person can act on.

    The index rather than a copy of the claim: the overlay is written wholesale
    and read as a list, so "claim 3" locates the offending object exactly, in
    the file and in the report, without restating it.
    """

    index: int
    reason: str


def validate_overlay(
    overlay: EnrichmentOverlay, workspace: Workspace, module_root: Path
) -> tuple[tuple[Claim, ...], tuple[Refusal, ...]]:
    """`overlay`'s claims split into the grounded and the refused.

    `accepted` keeps the overlay's own order — the order is part of what the
    document renders deterministically (NFR-1), so nothing here sorts. Every
    refused claim contributes exactly one `Refusal`: a claim is checked until
    its first failure and then reported, because a list of five reasons for one
    invented component is five ways of saying the same thing.

    `module_root` is the directory the module was analysed from — the root a
    `section` claim's citations are resolved against, and the boundary they
    must stay inside.
    """
    descriptors = set()
    names = set()
    for row in workspace.query("declared_symbols"):
        descriptor = bare_descriptor(str(row["symbol"]))
        descriptors.add(descriptor)
        names.add(simple_name(descriptor))
    questions = {_row_identity(row) for row in workspace.query("open_questions")}

    accepted: list[Claim] = []
    refusals: list[Refusal] = []
    for index, claim in enumerate(overlay.claims):
        reason = _reason_to_refuse(claim, descriptors, names, questions, module_root)
        if reason is None:
            accepted.append(claim)
        else:
            refusals.append(Refusal(index, reason))
    return tuple(accepted), tuple(refusals)


def stale_claims(
    overlay: EnrichmentOverlay, workspace: Workspace, module_root: Path
) -> tuple[Refusal, ...]:
    """The claims of `overlay` that no longer hold against `workspace` as it
    stands now — the ingest checks re-run at render time (2K design §6).

    Deliberately `validate_overlay` itself rather than a second set of checks:
    "stale" IS "would not be accepted today", and the moment the two are
    written separately they can disagree — a claim accepted at ingest and
    silently dropped at render, or the reverse. The refusals carry the same
    index and reason, which is what lets render say how many claims are not
    shown and a person find out why.

    Takes `module_root` for the reason `validate_overlay` does: a citation is
    resolved against a directory, and a file deleted since the run is exactly
    the kind of staleness this is looking for.
    """
    return validate_overlay(overlay, workspace, module_root)[1]


def _row_identity(row: dict[str, object]) -> tuple[str | None, ...]:
    """One `open_questions` row's identity. The row's own column is named
    `question`; the claim's field is named `kind`, because on a claim
    `question` is already the reference object."""
    return question_identity(
        row.get("protocol"), row.get("method"), row.get("path"), row.get("question")
    )


def _reason_to_refuse(
    claim: Claim,
    descriptors: set[str],
    names: set[str],
    questions: set[tuple[str | None, ...]],
    module_root: Path,
) -> str | None:
    """Why this claim cannot be accepted, or `None` when it can."""
    if isinstance(claim, ComponentClaim):
        return _first_missing_member(claim, descriptors)
    if isinstance(claim, DiagramClaim):
        return _first_missing_node(claim, names)
    if isinstance(claim, SectionClaim):
        return _first_missing_cite(claim, module_root)
    return _unmatched_question(claim, questions)


def _first_missing_member(claim: ComponentClaim, descriptors: set[str]) -> str | None:
    for member in claim.members:
        if bare_descriptor(member) not in descriptors:
            return (
                f"component `{claim.name}` names member `{member}`, which is not a symbol "
                "in this workspace"
            )
    return None


def _first_missing_node(claim: DiagramClaim, names: set[str]) -> str | None:
    for node in _declared_nodes(claim.mermaid):
        if node not in names:
            return f"diagram declares node `{node}`, which is not a type in this workspace"
    return None


def _declared_nodes(mermaid: str) -> list[str]:
    """Every identifier `_NODE_DECLARATION` can see, in source order — see the
    module comment above it for what the rule covers and what it deliberately
    does not."""
    return [
        match.group(1)
        for line in mermaid.splitlines()
        if (match := _NODE_DECLARATION.match(line)) is not None
    ]


def _first_missing_cite(claim: SectionClaim, module_root: Path) -> str | None:
    root = module_root.resolve()
    for cite in claim.cites:
        cited = (module_root / cite).resolve()
        if not cited.is_relative_to(root) or not cited.is_file():
            return f"section `{claim.title}` cites `{cite}`, which is not a file in this module"
    return None


def _unmatched_question(claim: VerdictClaim, questions: set[tuple[str | None, ...]]) -> str | None:
    """An `unanswered` verdict is valid whatever the ledger holds (2K design
    §7): it asserts nothing about the graph — it says the model looked and
    could not ground an answer — and refusing it would delete the one honest
    outcome the instructions ask for. Every other verdict is an assessment OF a
    row, so the row has to exist."""
    if claim.assessment == UNANSWERED:
        return None
    question = claim.question
    if question.identity in questions:
        return None
    return (
        f"verdict answers `{question.kind}` for `{question.protocol} {question.path}`, "
        "which is not an open question in this workspace"
    )
