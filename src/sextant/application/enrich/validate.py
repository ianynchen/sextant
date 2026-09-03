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
- **Diagram nodes** are compared as SIMPLE names — the last dotted segment of
  whatever the scan extracted — because a mermaid node id is an identifier and
  a descriptor is not one. That is a weaker check than the member check by
  construction: two classes of the same name in different packages are
  indistinguishable here, and this module does not pretend otherwise. Stated
  rather than tightened — the alternative is refusing a correct diagram over a
  notation the format cannot express. What the scan extracts, and what it
  deliberately cannot see, is spelled out at `_NODE_DECLARATION` below.
- **Cited files** must resolve to a file UNDER the module root. Containment is
  checked after resolution, so a cite escaping through `..` or a symlink is
  refused rather than followed.
- **A verdict's question** must match an `open_questions` row on all four of
  protocol, method, path and kind, OR an unresolved `resolved_config` row
  (`value IS NULL`) on all four of key, source, environment and
  unresolved_reason (2N design §2) — whichever shape the claim's `question`
  itself carries. Either way an `unanswered` verdict is included, whose
  exemption is about the ANSWER and not the row it answers. Matching is against
  the row's own values as the workspace holds them.
"""

import re
from dataclasses import dataclass
from pathlib import Path

from sextant.application.ports.workspace import Workspace
from sextant.domain.enrichment import (
    Claim,
    ComponentClaim,
    ConfigQuestionRef,
    DiagramClaim,
    EnrichmentOverlay,
    SectionClaim,
    VerdictClaim,
    open_question_identity,
    resolved_config_identity,
)
from sextant.domain.redaction import Redactor
from sextant.domain.symbols import bare_descriptor, simple_name

# The diagram node scan (2K design §6, "every node/participant must validate
# against real symbols"), stated exactly because a reader has to know what is
# NOT covered:
#
#   a line whose first word — leading whitespace aside — is `class`,
#   `participant` or `actor` contributes the identifier that follows it, and
#   nothing else on the line does; a DECLARATION line carrying a comma —
#   `class`, `participant` or `actor` alike — contributes nothing at all.
#
# That is a class declaration in a `classDiagram` (`class OrderView {`, `class
# OrderView`) and a participant declaration in a `sequenceDiagram`
# (`participant OrderView`, `participant OrderView as the view`).
#
# **`participant X as Y` is checked on EITHER spelling (spec §5a).** The
# alias can be a human label (`participant Ingest as the ingestion edge`) or
# it can carry the real name — an LLM copying a machine-quoted identifier, or
# writing `participant J as Real$Name` itself — and the scan cannot tell
# which. The conservative reading accepts a citation of either side rather
# than refusing a correct diagram for guessing wrong about which one is the
# type.
#
# **A backtick-quoted identifier is unquoted before comparison** — the
# diagram builder's own convention (`egress/render/diagrams.py`) for a name
# mermaid's bare grammar refuses, most often a JVM `$` nested-class name.
#
# **The identifier admits dots, and only the last dotted segment is compared.**
# A model writing `participant com.acme.orders.Ingest` is naming a real type in
# the notation its own sources use; scanning to the first dot would take `com`
# and refuse a VALID diagram as a phantom. Comparison stays on the simple name
# for the reason the docstring above gives — a mermaid node id is an
# identifier, not a descriptor — so `com.acme.Ingest` and `other.pkg.Ingest`
# are equally accepted wherever an `Ingest` exists. That is the same
# same-name-different-package weakness the simple-name rule already has, one
# notation wider; it is not a new one.
#
# A HYPHEN still truncates (`order-service` scans as `order`), and that is left
# alone deliberately: `-` is mermaid's own edge syntax, and admitting it would
# make `A-->B` scan as one identifier. A JVM type name cannot contain a hyphen,
# so nothing this validator is meant to check can be spelled with one.
#
# The comma exclusion drops the flowchart `class A,B someStyle` form, which
# applies a CSS class to nodes and names no type at all: scanning it would
# refuse a valid flowchart over a keyword it shares with `classDiagram`.
#
# **Conservative on purpose: what the rule cannot see is not validated and not
# refused.** A node introduced only by an edge (`A --> B`), a message arrow, a
# note, a namespace block or a `class` line the model spelled unusually is
# invisible here — it passes, unchecked, and so does every node on a
# comma-carrying DECLARATION line of any of the three keywords. The alternative is a scan that guesses at
# mermaid's grammar and refuses TRUE claims when it guesses wrong, and a
# validator that rejects correct work teaches its user to stop running it. The
# claim still carries `evidence: llm` and the diagram still says what it elides;
# this check catches the invented class name, not every possible one.
_IDENTIFIER = r"`[^`]*`|[A-Za-z_][\w$.]*"
_NODE_DECLARATION = re.compile(
    rf"^[ \t]*(?:class|participant|actor)[ \t]+({_IDENTIFIER})"
    rf"(?:[ \t]+as[ \t]+({_IDENTIFIER}))?"
)

# 2K Task 7 ruling 1: the brief IS the wire, so a redaction-sensitive
# `open_questions.path` (an address that can carry userinfo, or match a
# repo's own `redact:` value pattern) reaches the model already
# `redact_text`-ed — the model never sees the raw value, and a verdict it
# writes can only ever echo the redacted spelling back. Defaulted, like
# `document._DEFAULT_REDACTOR`, so every existing caller of this module —
# every test that builds an overlay by hand — keeps comparing against the
# built-in set alone, unchanged.
_DEFAULT_REDACTOR = Redactor.from_rules()


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
    overlay: EnrichmentOverlay,
    workspace: Workspace,
    module_root: Path,
    redactor: Redactor = _DEFAULT_REDACTOR,
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

    `redactor` canonicalizes a verdict's `question.path` (or, for a
    config-shaped question, its `key`/`source`) match the same way on both
    sides (2K Task 7 ruling 1, widened by 2N design §2): the brief hands the
    model a `redact_text`-ed row, so a model copying that row back into a
    `verdict` can only ever echo the redacted spelling — the shared
    `open_question_identity`/`resolved_config_identity` redacts the WORKSPACE
    row's own address columns before comparing (the same functions assembly
    keys its placement on), so a redaction that changed nothing (the ordinary
    case) still matches on the raw value and a redaction that changed
    something still matches on the value the model actually saw.
    """
    descriptors = set()
    names = set()
    for row in workspace.query("declared_symbols"):
        descriptor = bare_descriptor(str(row["symbol"]))
        descriptors.add(descriptor)
        names.add(simple_name(descriptor))
    questions = {open_question_identity(row, redactor) for row in workspace.query("open_questions")}
    # Only the UNRESOLVED rows (`value IS NULL`) are addressable (2N design
    # §2/§3): a config verdict answers a row pass 2 could not resolve, never
    # a resolved one — the same "only rows the machine already computes gain
    # an address" rule §3 states for the whole task.
    config_questions = {
        resolved_config_identity(row, redactor)
        for row in workspace.query("resolved_config")
        if row.get("value") is None
    }

    accepted: list[Claim] = []
    refusals: list[Refusal] = []
    for index, claim in enumerate(overlay.claims):
        reason = _reason_to_refuse(
            claim, descriptors, names, questions, config_questions, module_root
        )
        if reason is None:
            accepted.append(claim)
        else:
            refusals.append(Refusal(index, reason))
    return tuple(accepted), tuple(refusals)


def stale_claims(
    overlay: EnrichmentOverlay,
    workspace: Workspace,
    module_root: Path,
    redactor: Redactor = _DEFAULT_REDACTOR,
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
    the kind of staleness this is looking for. `redactor` should be the same
    one the run was ingested with (ordinarily the module's own, since render
    and enrich share one), for the reason `validate_overlay`'s own docstring
    gives.
    """
    return validate_overlay(overlay, workspace, module_root, redactor)[1]


def _reason_to_refuse(
    claim: Claim,
    descriptors: set[str],
    names: set[str],
    questions: set[tuple[str | None, ...]],
    config_questions: set[tuple[str | None, ...]],
    module_root: Path,
) -> str | None:
    """Why this claim cannot be accepted, or `None` when it can."""
    if isinstance(claim, ComponentClaim):
        return _first_missing_member(claim, descriptors)
    if isinstance(claim, DiagramClaim):
        return _first_missing_node(claim, names)
    if isinstance(claim, SectionClaim):
        return _first_missing_cite(claim, module_root)
    return _unmatched_question(claim, questions, config_questions)


def _first_missing_member(claim: ComponentClaim, descriptors: set[str]) -> str | None:
    for member in claim.members:
        if bare_descriptor(member) not in descriptors:
            return (
                f"component `{claim.name}` names member `{member}`, which is not a symbol "
                "in this workspace"
            )
    return None


def _first_missing_node(claim: DiagramClaim, names: set[str]) -> str | None:
    for spellings in _declared_nodes(claim.mermaid):
        if not any(spelling in names for spelling in spellings):
            return f"diagram declares node `{spellings[0]}`, which is not a type in this workspace"
    return None


def _simple_spelling(identifier: str) -> str:
    """Strip `identifier`'s backtick quoting, if any, then reduce it to its
    last dotted segment — the same simple-name comparison every declared node
    gets (see the comment above `_NODE_DECLARATION`)."""
    if identifier.startswith("`") and identifier.endswith("`"):
        identifier = identifier[1:-1]
    return identifier.rsplit(".", 1)[-1]


def _declared_nodes(mermaid: str) -> list[tuple[str, ...]]:
    """Every declaration `_NODE_DECLARATION` can see, in source order, as the
    tuple of spellings that satisfy it. A bare declaration (`class X`,
    `participant X`, `actor X`) yields a one-element tuple; `participant X as
    Y` yields both — see the comment above the pattern for why either side is
    accepted, and for what the rule deliberately does not cover.

    A line carrying a comma is skipped whole: that is the flowchart `class A,B
    someStyle` form, which names a CSS class rather than a type."""
    nodes: list[tuple[str, ...]] = []
    for line in mermaid.splitlines():
        if "," in line:
            continue
        match = _NODE_DECLARATION.match(line)
        if match is None:
            continue
        nodes.append(
            tuple(_simple_spelling(group) for group in match.groups() if group is not None)
        )
    return nodes


def _first_missing_cite(claim: SectionClaim, module_root: Path) -> str | None:
    root = module_root.resolve()
    for cite in claim.cites:
        cited = (module_root / cite).resolve()
        if not cited.is_relative_to(root) or not cited.is_file():
            return f"section `{claim.title}` cites `{cite}`, which is not a file in this module"
    return None


def _unmatched_question(
    claim: VerdictClaim,
    questions: set[tuple[str | None, ...]],
    config_questions: set[tuple[str | None, ...]],
) -> str | None:
    """Every verdict answers a row in the ledger, and the row has to exist —
    an `open_questions` row for the endpoint shape, an unresolved
    `resolved_config` row for the config one (2N design §2), by whichever
    shape `claim.question` itself carries.

    **`unanswered` exempts the ASSESSMENT, never the REFERENT** (Task 3 review,
    ruled, unchanged by the identity widening). "`unanswered` beats a guess"
    (2K design §5/§7) is a rule about the answer: a model that looked and
    could not ground one is never refused for saying so, and no grounding is
    demanded of the text it gives. But an `unanswered` verdict still names a
    question, still renders beside it, and still counts as a claim in the
    file — so a verdict against a question nobody asked is a phantom whichever
    way it is answered, and exempting the referent as well would leave open
    the one channel by which an invented row could reach the document.
    """
    question = claim.question
    if isinstance(question, ConfigQuestionRef):
        if question.identity in config_questions:
            return None
        return (
            f"verdict answers `{question.kind}` for config key `{question.key}` in "
            f"`{question.environment}`, which is not an unresolved configuration row "
            "in this workspace"
        )
    if question.identity in questions:
        return None
    return (
        f"verdict answers `{question.kind}` for `{question.protocol} {question.path}`, "
        "which is not an open question in this workspace"
    )
