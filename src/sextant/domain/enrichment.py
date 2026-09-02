"""The enrichment overlay — `.sextant-enrichment.json` (2K design §6).

**A pure program artifact.** `enrich` writes this file WHOLESALE, `render` and
`export` read it, and nobody edits it: there is no promotion mechanism, no
per-claim suppression, and no partial write. Reading a diff in a pull request
is not editing — that is why the format is JSON and why every field is
explicit rather than inferred. Regeneration replaces the file entirely, which
is what lets `produced_by` state one run of one model against one graph rather
than a history nothing tracks.

**Schema-validated at every load, refusals loud.** A claim naming a kind or an
anchor outside its closed set is Sextant's own input written wrong (D04 §2a) —
refused, never coerced into the nearest legal value. The union discriminates on
`kind`, so an unknown kind names itself in the error instead of failing four
times over as "no variant matched".

**`evidence` is `llm` and nothing else.** The overlay exists to keep model
output typographically and structurally distinct from machine output; a claim
that could carry `compiler` would be a claim that could launder an assertion
into the derived half of the document. Making the field a one-value literal is
what keeps that impossible rather than merely discouraged.

Validation *by construction* — the members, nodes, files and questions a claim
names must exist — is the application layer's (`application/enrich/validate.py`):
it needs the workspace and the module root, and this module stays pure.
"""

from collections.abc import Mapping
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator

from sextant.domain.closed_sets import Anchor, Evidence
from sextant.domain.redaction import Redactor

# The overlay's name and place: the module root, beside `.sextant.yml` and
# `.sextantignore`. One file per module, versionable in git.
ENRICHMENT_FILE = ".sextant-enrichment.json"

# The one assessment that answers nothing (2K design §7). Spelled once here
# because both the schema's own shape rule and the validator's "always valid"
# rule turn on it, and two spellings of one word is how the honesty discipline
# would quietly stop applying to half the claims.
UNANSWERED = "unanswered"


class Provenance(BaseModel):
    """One run of one model against one graph (2K design §6).

    Every field is required. A provenance block with a hole in it is a document
    that cannot say what produced the words a reader is about to trust, which
    is the whole reason the block exists — so the schema refuses rather than
    defaulting. `run_at` is carried as the text it was written as (ISO 8601, UTC)
    rather than a `datetime`: this file must round-trip byte-exactly, and a
    parsed timestamp re-serializes in whatever spelling the library prefers.
    """

    model_config = {"frozen": True, "extra": "forbid"}
    model: str
    agent: str
    instructions_hash: str
    redaction_set_hash: str
    run_at: str
    workspace_fingerprint: str


class _ClaimBase(BaseModel):
    """What every claim carries whatever it says.

    `extra: forbid` throughout: a field render does not know about is a claim
    half of which would silently vanish from the document, and a program
    artifact has no reason to carry one.
    """

    model_config = {"frozen": True, "extra": "forbid"}
    # Tied to the closed set rather than spelled as a bare string, so the
    # marker in the overlay and the marker in the fact stream cannot drift
    # apart. The value is `llm`, and the type admits no other.
    evidence: Literal[Evidence.LLM]
    anchor: Anchor


class ComponentClaim(_ClaimBase):
    """A named component and why it exists, over member symbols that must
    exist (2K design §6). The purpose is the part no analysis can derive; the
    members are what makes the claim checkable."""

    kind: Literal["component"]
    name: str
    purpose: str
    members: list[str]


class SectionClaim(_ClaimBase):
    """Prose — a high-level design note, an extension guide, an algorithm
    description — citing the files it was read from. `cites` is not decoration:
    it is the claim's own evidence trail, and validation refuses a citation
    that names nothing."""

    kind: Literal["section"]
    title: str
    body: str
    cites: list[str]


class DiagramClaim(_ClaimBase):
    """A simplified mermaid diagram with an explicit statement of what it
    leaves out. `elides` is required because a simplified diagram that does not
    say it is simplified is a diagram that lies about the system's size —
    "showing 8 of 23 classes; error paths elided" is the whole point of
    letting a model draw one at all."""

    kind: Literal["diagram"]
    mermaid: str
    elides: str


def question_identity(
    protocol: object, method: object, path: object, kind: object
) -> tuple[str | None, ...]:
    """The four columns that identify one `open_questions` row (2K design §7):
    its wire identity, then the kind of question asked.

    One spelling, here, because two different passes compare it — validation
    matches a verdict to a row, and assembly places that verdict under the same
    row's rendered line. Two spellings of one identity is a verdict that
    validates against a question and then renders nowhere near it. `object`
    rather than `str | None` because one caller holds a claim's typed fields
    and the other holds a query row's untyped columns.
    """
    return tuple(None if value is None else str(value) for value in (protocol, method, path, kind))


def open_question_identity(row: Mapping[str, object], redactor: Redactor) -> tuple[str | None, ...]:
    """One `open_questions` WORKSPACE row's identity, canonicalized (2K Task 7
    ruling 1): `path` — the one column of the four that can carry a whole
    address — is `redact_text`-ed before the tuple is built, so the row matches
    on the spelling the model actually saw. The brief hands the model a redacted
    row, so a verdict can only ever echo the redacted spelling; a redaction that
    changed nothing (the ordinary case) still matches on the raw value.

    Both passes that key on a workspace row call THIS, never `question_identity`
    on `row["path"]` raw (2K final review, F3): validation matches a verdict to a
    row and assembly places that verdict under the same row's rendered line, and
    the two spellings had drifted — a verdict on a question whose path changes
    under redaction validated cleanly and then rendered at the section fallback
    instead of beside its question. One function, so they cannot drift again.
    """
    path = row.get("path")
    redacted_path = None if path is None else redactor.redact_text(str(path))
    return question_identity(
        row.get("protocol"), row.get("method"), redacted_path, row.get("question")
    )


class OpenQuestionRef(BaseModel):
    """The identity of one `open_questions` row (2K design §7): its wire
    identity plus the kind of question asked. `method` and `path` are nullable
    because the rows are — a messaging destination has no verb, and a question
    can be raised about an address nothing could read."""

    model_config = {"frozen": True, "extra": "forbid"}
    protocol: str
    method: str | None = None
    path: str | None = None
    kind: str

    @property
    def identity(self) -> tuple[str | None, ...]:
        return question_identity(self.protocol, self.method, self.path, self.kind)


class VerdictClaim(_ClaimBase):
    """The verification seat (2K design §7): an assessment of one open
    question, or an honest `unanswered`.

    **The graph is immutable.** A verdict never feeds resolve and never
    rewrites the row — the question stays open, and this claim renders beside
    it labelled as a model's assessment.

    Two shapes, one model: an answered verdict carries `because` (the grounding
    that makes it readable as evidence rather than opinion) and no `searched`;
    an `unanswered` one carries `searched` (what was looked at and why it was
    insufficient) and no `because`. A nested discriminator would need the
    assessment text itself to be a closed set, which it is not — the assessment
    is prose except for the one reserved word.
    """

    kind: Literal["verdict"]
    question: OpenQuestionRef
    assessment: str
    because: str | None = None
    searched: str | None = None

    @model_validator(mode="after")
    def _carries_the_half_its_assessment_requires(self) -> "VerdictClaim":
        if self.assessment == UNANSWERED:
            if self.searched is None:
                raise ValueError(
                    f"a `{UNANSWERED}` verdict must record what was searched and why it "
                    "was insufficient"
                )
            if self.because is not None:
                raise ValueError(
                    f"a `{UNANSWERED}` verdict answered nothing, so it carries no `because`"
                )
            return self
        if self.because is None:
            raise ValueError(
                f"a verdict must carry the `because` its assessment rests on, or say `{UNANSWERED}`"
            )
        if self.searched is not None:
            raise ValueError(f"`searched` belongs to a `{UNANSWERED}` verdict alone")
        return self


type Claim = Annotated[
    ComponentClaim | SectionClaim | DiagramClaim | VerdictClaim,
    Field(discriminator="kind"),
]


class EnrichmentOverlay(BaseModel):
    """The whole file. `claims` may legitimately be empty — a run that grounded
    nothing writes an overlay saying so, which is a different statement from no
    overlay at all."""

    model_config = {"frozen": True, "extra": "forbid"}
    produced_by: Provenance
    claims: list[Claim]


def load_overlay(module_root: Path) -> EnrichmentOverlay | None:
    """`module_root`'s overlay, or `None` where the module has none.

    `None` is the ordinary answer, not an error: most modules have never been
    enriched, and render must behave for them exactly as it did before any of
    this existed (2K design §6). A file that IS there and cannot be validated
    raises — `pydantic.ValidationError`, naming the field — because that is
    Sextant's own program artifact written wrong, and a silent fallback would
    render a document missing claims nobody was told about.
    """
    path = module_root / ENRICHMENT_FILE
    if not path.is_file():
        return None
    return EnrichmentOverlay.model_validate_json(path.read_text(encoding="utf-8"))
