"""The module architecture document (M07). Adds no information: every row
comes from `report`, and every omission — the call graph, a Maven POM the
detector could not read correctly, a payload type nothing could expand, or a
catalog skipped by capability gating — is named rather than silently absent
(NFR-7).

**Two serializers, one assembly (2K design §6/§6b).**
`assemble_module_document` produces the `AssembledDocument` — a list of typed
sections — and `markdown_document` writes it out as `architecture.md`. The
HTML emitter consumes the SAME list. Nothing downstream parses the finished
markdown to find out where a claim went: placement is decided once, here, and
a second serializer that had to re-derive it would eventually disagree.

**Add-only.** An overlay's claims are INTERLEAVED at their anchors; machine
text is never rewritten, reordered or replaced. The machine half of the
document is emitted verbatim in the order it was built, and the only bytes an
overlay can add outside its own block are the blank lines that keep a
blockquote from swallowing the line after it. With no overlay the output is
byte-identical to what this renderer produced before any of this existed.
"""

import json
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import cast

from pydantic import ValidationError

from sextant.application.ports.detector import ModuleModel

# The walk's own answer, carried in as data (2Q `G4`/`I3`). `egress` reads a
# report and renders it; the composition root calls `traces_of` and hands the
# result here, exactly as it already hands `shape_fields` and `open_questions`
# — this module never reaches for a workspace, which is the import-linter
# contract "Egress is read-only" in one line.
from sextant.application.query.trace import Step, Trace
from sextant.application.resolve.pipeline import ResolveReport

# The root a trace ran from, for the addresses it carries (2Q close, defect 1).
# Imported for its TYPE and read field by field: the join from a root to the
# addresses that reach it was made in `resolve/roots.py`, and re-making it here
# is the derivation "Egress is read-only" exists to forbid.
from sextant.application.resolve.roots import Root
from sextant.domain.closed_sets import Anchor, Protocol, Resolution, TraceStop
from sextant.domain.enrichment import (
    UNANSWERED,
    Claim,
    ComponentClaim,
    ConfigQuestionRef,
    DiagramClaim,
    EnrichmentOverlay,
    Provenance,
    SectionClaim,
    VerdictClaim,
    open_question_identity,
)
from sextant.domain.redaction import Redactor
from sextant.domain.symbols import (
    bare_descriptor,
    member_name,
    method_name,
    owner_of,
    without_type_marker,
)
from sextant.egress.render.diagrams import class_diagram, sequence_diagram
from sextant.egress.render.viewmodel import (
    ClassEdge,
    ClassNode,
    SequenceAlternatives,
    SequenceBranch,
    SequenceMessage,
    SequenceParticipant,
    simple_name,
)

_GAPS = [
    "An @HttpExchange interface implemented server-side is still reported outbound.",
    (
        "Base addresses built by computation — concatenation, setter injection, "
        "a method's return value — are not traced; only a directly-read field or "
        "property reaches configuration."
    ),
    (
        "Configuration constructed in code — a settings module, a config "
        "factory — is not read; only configuration files reach resolution."
    ),
    (
        "A trace is reachability, never execution: branches are not distinguished, "
        "two return statements are two possible answers rather than the one that "
        "runs, and no step is asserted to have happened."
    ),
    "The structure diagram covers contract types only: inheritance edges are not extracted.",
    (
        "A trace stops where this workspace read no body, and `Stop` says `boundary` "
        "whether that body is a third-party library, the JDK, a data-access API or a "
        "SIBLING BUILD MODULE. `Reaches` classifies the ones a catalog knows, so a "
        "data-access call is no longer indistinguishable from a JDK one — but the "
        "SIBLING MODULE is the case that under-reports and it is not separated: a body "
        "exists somewhere, in a workspace this one does not hold, and on a multi-module "
        "build it is where a response is composed."
    ),
    (
        "A method is expanded once per trace, not once per route to it: a second "
        "route to the same method reads `revisited` and its calls are shown at the "
        "first, so a path through a trace is not always followable to a terminal."
    ),
    (
        "A root is a handler this module exposes or schedules. A functional route "
        "carries no handler symbol, so it produces no root and gets no trace; a "
        "program entry point has no producer at all, so a module whose only "
        "starting point is a batch job or a command-line tool gets none either."
    ),
    (
        "Maven profiles and transitive dependencies are not resolved: the "
        "detector reads pom.xml files instead of asking Maven to resolve them. "
        "Parent inheritance, reactor `<modules>` discovery, "
        "`<dependencyManagement>`, imported BOMs and `${property}` "
        "interpolation ARE read — but a dependency declared inside a profile, "
        "and one that reaches the module only through another artifact's own "
        "dependencies, are absent from the recorded set."
    ),
    (
        "Catalogs are matched to modules only where the framework rule is "
        "conditional on the library being present: `detect.coordinates` is read, "
        "and such a catalog is skipped with a reason where the module's build "
        "declares none of them. Every other catalog still runs against every "
        "module whether or not the module depends on that framework — and a "
        "framework reaching a module only as another artifact's own transitive "
        "dependency cannot be told apart from an absent one."
    ),
    (
        "Module classification reads only a container file and a declared main "
        "class: a module showing neither is reported `undetermined` rather than "
        "weighed against the rest of the evidence."
    ),
    (
        "Endpoint request and response contracts are scoped to the catalog "
        "that produced them. Shape expansion itself is not: a payload type "
        "reachable from several catalogs is still expanded once, under "
        "whichever catalog's rules reach it first, not necessarily the ones "
        "that produced the endpoint referencing it. The shipped catalogs do "
        "not declare identical rules, so a wrapper type one of them unwraps "
        "and another does not can be named below as unexpanded even where the "
        "shape behind it was expanded correctly."
    ),
    (
        "Reactive and lambda flow is recorded but not traced: calls inside "
        "flatMap and map derive endpoints, and a functional route's handler "
        "resolves, but the sequence between reactive calls — and the "
        "payloads read inside a functional handler's body — await the call "
        "graph."
    ),
    (
        "A bytes-only channel whose payload is parsed further than one "
        "delegation hop from its handler is not bound: the parse is found "
        "and listed as an open question instead, because a flow followed "
        "further than it was observed is an assumption, not a fact."
    ),
    (
        "A bytes-only channel whose payload reaches two different parses "
        "binds neither: two answers about one wire is a question for a "
        "reader, and picking the one that sorts first would publish a "
        "coin toss as a contract."
    ),
]

# The protocols whose verb is not an HTTP method, so the protocol name is
# itself part of the identity a reader needs (D06, 2H design §1): `graphql
# query orders` names an operation, while a bare `query orders` names nothing
# in particular — `query` is not a word that implies its own protocol the way
# `GET` does. `sse` is qualified for the mirror-image reason (2H design §6):
# its verb IS an HTTP method, because an SSE stream is a route a client GETs,
# and a bare `GET /events/stream` therefore reads as an ordinary REST route
# and loses the one thing the reclassification established. HTTP and gRPC
# read correctly without the prefix, which is also what every pin written
# before this expects.
_PROTOCOL_QUALIFIED = frozenset({"graphql", "sse"})

# D00 §4 closed-set protocol names whose wire identity has no verb: a Kafka
# topic, a JMS destination, an SQS queue or a Pub/Sub topic is addressed, not
# called, so there is no method to render beside the path. SOAP belongs here
# too (spec §1, 2I Task 4 fix round 1, ruled) — an operation is addressed by
# its payload root or its SOAPAction URI, never a verb, the same 2D messaging
# shape as a Kafka topic. It sat in the verbed half from 2H (when no catalog
# owned the protocol, so the misclassification rendered nothing) through 2I
# Task 2's own live rows, which is what let every SOAP row render a phantom
# `(unresolved)` verb nobody ever failed to read.
#
# Derived from D00's closed set by SUBTRACTING the verbed protocols, rather
# than hand-listing the verbless ones. Two sets naming halves of one closed
# set drift; one set and a subtraction cannot. Which half to hand-list is
# then the question of what an UNLISTED new protocol should default to, and
# verbless is the honest default: it renders `protocol path`, while the other
# way round renders `(unresolved) path` — a verb reported as unread when the
# protocol was never going to have one. The verbed half is also the stable
# half: growth in D00's set is broker families, not new request-response
# verbs.
#
# The qualified set is UNIONED in rather than repeated, so "every qualified
# protocol is a verbed one" is structural. Stating it twice is what let `sse`
# be added to one list and silently fall out of the other — a GET route
# reclassified into the verbless half renders `sse /events/stream` and drops
# the verb it does have.
# `temporal` joins verbed rather than qualified: its `method` carries the row's
# operation kind (`workflow`/`signal`/`query`/`update`/`activity`), the same
# role GraphQL's `query`/`mutation` play in this column.
_VERBED_PROTOCOLS = frozenset({"http", "grpc", "temporal"}) | _PROTOCOL_QUALIFIED
_VERBLESS_PROTOCOLS = frozenset(p.value for p in Protocol) - _VERBED_PROTOCOLS

# The verbed protocols whose rows may legitimately carry NO verb. A GraphQL
# resolver is addressed by `Type.field` alone — it implements a field, it does
# not answer an operation — so its NULL method is an absence rather than a
# verb the analysis failed to read. Its own set, deliberately not
# `_PROTOCOL_QUALIFIED` reused: an SSE row is qualified and its verb is still
# an HTTP method, so a NULL there genuinely is unread and must render as such.
_VERB_OPTIONAL_PROTOCOLS = frozenset({"graphql"})

# Redaction is DEFAULT-ON at this exit (2K design §1): a caller that names no
# redactor still gets the built-in set, so the failure mode of forgetting to
# wire one is a masked document, never a leaked one. The composition root
# passes the module's own redactor, widened by its `.sextant.yml`.
_DEFAULT_REDACTOR = Redactor.from_rules()


class ClaimRedactionError(ValueError):
    """A redaction rule that leaves a claim unreadable.

    The redactor is applied to a claim's own strings at assembly, and the
    result is re-validated against the claim's schema. Almost every rule leaves
    that intact — it rewrites prose. A pathological one (a value pattern
    matching `llm`, say, or one that eats a required field whole) does not, and
    the honest answer is to refuse the render and say which rule did what: the
    alternative is publishing a claim with a field replaced by a marker, or
    reporting a repository's own `redact:` section as a crash in the tool.
    """


type Run = tuple[str, str]
"""One inline span of machine text: `("code", content)` for a backtick-quoted
identifier, path or key, `("text", content)` for everything else, or
`("shaperef", name)` for a named shape's display name where it is CITED
rather than declared — a `### Shapes` entry's own table lives once, under
its own heading, and every other place that shape is mentioned carries this
instead of a second copy (2M design §5c). The builders below already know
which is which — every code span they ever wrote was wrapped in backticks by
hand, and every citation is built through `_shape_ref` alone — so a `Run`
never has to be guessed at after the fact by an HTML emitter that would
otherwise have to decide what a backtick means on its own (2M design §5b).
`html.py` turns a `shaperef` run into an in-page link to the `### Shapes`
entry of the same name; every other serializer treats it as plain text,
since naming the shape is all a reader needs where linking is not
possible."""


def _runs(markdown: str) -> tuple[Run, ...]:
    """`markdown` split into alternating text/code runs on backtick-delimited
    spans — the inverse of how every machine string below is already built.

    **Total: round-trips for ANY input, balanced or not** (fix round 2). A
    balanced (EVEN) backtick count is the common case — every code span this
    renderer ever opened, it closed — and splits cleanly into alternating
    text/code parts. An UNBALANCED (odd) count leaves one backtick with no
    partner, which `str.split` turns into one EXTRA part (an even part
    count); merging that trailing pair back into one text part, with the
    backtick that used to separate them put back in literally, undoes
    exactly that one bad cut. Everything before it still alternates
    text/code normally, so this is a single, local repair rather than a
    second parse — `_runs_to_markdown(_runs("a`b")) == "a`b"` now, not the
    `` a`b` `` a spurious reconstructed closing backtick used to produce.

    Kept EVEN for an empty code span (`` `` ``, two adjacent backticks): `if
    part or i % 2` — never `if part` alone, which would silently drop an
    empty *code* run (odd index) along with every genuinely empty text run
    (even index) and, for `` a``b ``, reconstruct as `ab` — two backticks lost
    outright, not merely misplaced. Dropping an EMPTY text run is always
    safe: an empty string contributes nothing to `_runs_to_markdown` whether
    kept or dropped."""
    parts = markdown.split("`")
    if len(parts) % 2 == 0:
        parts = [*parts[:-2], f"{parts[-2]}`{parts[-1]}"]
    return tuple(
        ("code" if i % 2 else "text", part) for i, part in enumerate(parts) if part or i % 2
    )


def _runs_to_markdown(runs: Sequence[Run]) -> str:
    """The exact inverse of `_runs` over the two kinds `_runs` can ever
    produce: a code run is rewrapped in backticks, a text run passes through
    unchanged, and the two concatenate back into the original markdown. A
    `shaperef` run — never one `_runs` itself produces, only `_shape_ref` —
    renders as its bare name: markdown has no in-page link to give it, so
    NAMING the shape is the whole of what this serializer owes a reader
    (2M design §5c; `html.py`'s own emitter is what turns the same run into
    a link)."""
    return "".join(f"`{content}`" if kind == "code" else content for kind, content in runs)


def _text(content: str) -> tuple[Run, ...]:
    """A single run of plain text — for a value this renderer never wraps in
    backticks (a resolution enum, a media type, a peer address), so splitting
    it for embedded backticks would be answering a question that was never
    asked."""
    return (("text", content),)


def _code(content: str) -> tuple[Run, ...]:
    """A single run of code — for a value that is ALWAYS a whole code span on
    its own (a wire identity, a bare descriptor), never text mixed with one."""
    return (("code", content),)


def _shape_ref(name: str) -> tuple[Run, ...]:
    """A single run naming a shape declared once, elsewhere, in the
    `### Shapes` subsection (2M design §5c) — `name` is the shape's DISPLAY
    name (`simple_name(shape_id)`), the same string the shape's own entry is
    headed by, so both ends of the reference are built from the one value
    rather than a name derived one way at the citation and another at the
    declaration."""
    return (("shaperef", name),)


@dataclass(frozen=True)
class MachineHeading:
    """A `#`-to-`###` heading, as the level and its plain text — never runs,
    since every heading this renderer writes is a literal title with no code
    span in it."""

    level: int
    text: str


# The markdown marker each heading level opens with, INCLUDING its trailing
# space — a lookup table rather than repeating a single hash-mark literal by
# `level`, which would put that one bare character on its own between quotes
# in this file and trip `test_symbol_grammar_confinement.py`'s check for
# SCIP-symbol-splitting parses outside its one seam (`domain/symbols.py`).
# Markdown's heading marker is a different grammar entirely; the table
# sidesteps the false match rather than asking that check to tell the two
# apart.
_HEADING_MARKERS = {1: "# ", 2: "## ", 3: "### "}

# The only levels a `MachineHeading` may carry — this dict's own keys, so
# there is exactly one place that decides the bound rather than two that
# could drift. Exported (no leading underscore) so `html._heading_html`
# checks the SAME bound instead of trusting `<h{level}>` to accept anything:
# a level outside it fails identically in both serializers rather than one
# `KeyError`-ing here and the other silently emitting a tag markdown has no
# heading for.
HEADING_LEVELS = tuple(_HEADING_MARKERS)


@dataclass(frozen=True)
class MachineParagraph:
    """One line of machine prose, as runs."""

    runs: tuple[Run, ...]


@dataclass(frozen=True)
class MachineList:
    """A run of `-` bullets with no blank line between them — one list, one
    section. An item that must sit beside its OWN placement anchor (an open
    question a verdict answers) is instead its own single-item `MachineList`,
    which is what lets `_Anchors` key on it directly."""

    items: tuple[tuple[Run, ...], ...]


@dataclass(frozen=True)
class MachineTable:
    """A markdown table: plain-text headers (never code — a column name is
    never a value to look up) and rows of cells, each cell its own runs."""

    headers: tuple[str, ...]
    rows: tuple[tuple[tuple[Run, ...], ...], ...]


@dataclass(frozen=True)
class DetailEntry:
    """One line of a `MachineDetail` — a title, and EITHER an inline body OR
    a nested table, never both (the shape `_descriptor_entry`/`_via_entry`
    already builds one of). `table is None and body is None` is the bare
    title of the block's own header line (`- `{identity}``), which has
    neither."""

    title: tuple[Run, ...]
    body: tuple[Run, ...] | None
    table: MachineTable | None

    def __post_init__(self) -> None:
        # Enforced, not merely documented above: a builder that ever passed
        # both would hand both serializers a shape neither actually renders
        # (markdown's `if entry.table is not None` branch would silently
        # swallow a body it also carried) — a hard error here, the same
        # stance `ClaimRedactionError`/the html emitter's "no rendering
        # rule" refusals already take, beats a table quietly winning.
        if self.body is not None and self.table is not None:
            raise ValueError(
                f"a DetailEntry carries EITHER a body OR a table, never both: {self!r}"
            )


@dataclass(frozen=True)
class MachineDetail:
    """One endpoint's nested detail block — the two-level list markdown
    already wrote (`- `{identity}`` then indented `Via:`/`Request:`/
    `Response:` lines), typed rather than carried as opaque text (2M design
    §5b, adversarial review C2). `entries[0]` is always the block's own
    header (a bare title, no body or table); every entry after it is one
    nested line, indented one level in markdown and rendered as its own
    `<dt>`/`<dd>` pair in HTML.

    A `MachineTable` entry serializes as a real nested `<table>` rather than
    the indented markdown block scanned back apart — the whole point of
    typing this instead of leaving it as `MachineSection` lines.

    `anchor` names the HTML `id` this block's header is addressed by — set
    only for a `### Shapes` entry, which a `shaperef` run elsewhere in the
    document links to (`_shape_anchor_id`, 2M design §5c); `None` for every
    ordinary endpoint block, which nothing points at. Markdown ignores it —
    an in-page id is an HTML-only concept — so this is the one field the two
    serializers do not both read from every block."""

    entries: tuple[DetailEntry, ...]
    anchor: str | None = None


@dataclass(frozen=True)
class MachineSection:
    """A run of machine-derived PROSE, as markdown lines — verbatim, in
    order. The escape hatch left behind by the 2M §5b typed-section refactor:
    `assemble_module_document` no longer builds one (every region it used to
    emit as opaque lines is now one of the typed kinds above), but the type —
    and `markdown_document`/`html_document`'s support for it — stays, for
    machine text a future region has no typed shape for yet rather than one
    this renderer would otherwise have to invent a shape for on the spot.

    The one exception is a diagram, which is `MachineDiagram` below: a fence
    buried in these lines would be a fence the HTML emitter could only find by
    scanning markdown.
    """

    lines: tuple[str, ...]


@dataclass(frozen=True)
class MachineDiagram:
    """A machine-derived mermaid diagram, as its SOURCE rather than as a fenced
    block inside `MachineSection.lines`.

    This renderer builds the fence itself, so it already knows where the
    diagram starts and ends; handing a serializer the source is free, and
    handing it three opaque lines instead would force the HTML emitter to scan
    markdown for ```` ```mermaid ```` to find the thing it has to wrap in a
    pan-zoom container. With this, EVERY diagram in the assembled document —
    this one and an overlay's `DiagramClaim` — reaches a serializer as data.

    The markdown emitter re-fences it byte for byte, which is what the golden
    document pins.

    `elides` is what this diagram leaves out, in the machine's own words, or
    `None` for one that leaves nothing out. It is `DiagramClaim.elides`' rule
    applied to the machine half — *"a simplified diagram that does not say it
    is simplified is a diagram that lies about the system's size"* — and it
    reaches both serializers exactly as the claim's does: markdown writes an
    `Elides:` line under the fence, HTML passes it to `_diagram_html`'s
    caption. `None` renders nothing at all, which is why `## Structure`'s
    class diagram is byte-identical to what it was before this field existed:
    that diagram draws every contract type there is.
    """

    mermaid: str
    elides: str | None = None


@dataclass(frozen=True)
class EnrichmentSection:
    """The overlay claims placed at one position, with the provenance of the
    run that produced them. Typed rather than pre-rendered: this is the half
    the HTML emitter styles differently — a badge, a pan-zoomable diagram
    container — so it must reach a serializer as claims, not as prose it would
    have to take apart again.

    The claims are already REDACTED (`assemble_module_document`), so every
    serializer inherits that without having to remember to ask.
    """

    provenance: Provenance
    claims: tuple[Claim, ...]


@dataclass(frozen=True)
class StaleNoticeSection:
    """The count of claims excluded because their referents no longer exist
    (2K design §6). Visible, never silent: a claim quietly dropped is a
    document that looks complete and is not (NFR-7). The overlay file keeps
    the claim — only this render leaves it out.
    """

    provenance: Provenance
    count: int


type Section = (
    MachineHeading
    | MachineParagraph
    | MachineList
    | MachineTable
    | MachineDetail
    | MachineSection
    | MachineDiagram
    | EnrichmentSection
    | StaleNoticeSection
)
type AssembledDocument = tuple[Section, ...]


def _wire_identity(endpoint: dict[str, object], redactor: Redactor) -> str:
    """One `endpoints`-shaped row's wire identity, through `_wire_address`.

    Kept as the row-shaped entry point every caller in this file has always
    used, so the three columns are named once here rather than at each call
    site; `## Traces` reads the same three off a `RootIdentity` instead and
    calls `_wire_address` directly (2Q close, defect 1). Both spellings of one
    address therefore come out of one function — two would be two answers to
    "what is this endpoint called" in one document.
    """
    return _wire_address(endpoint["protocol"], endpoint["method"], endpoint["path"], redactor)


# The ledger questions whose NULL verb is an ABSENCE rather than a verb the
# analysis could not read. A `routing_conflict` between two verbless
# `@RequestMapping`s is refused at EVERY verb, and `routing_conflicts._verbs_of`
# files it once with no verb rather than eight times — so NULL there is how one
# row says "all of them", and `_wire_address`'s `(unresolved)` would report a
# verb as unread that was read perfectly well. The same distinction
# `_VERB_OPTIONAL_PROTOCOLS` draws for a GraphQL resolver, drawn on the question
# instead of the protocol because an `http` row is verbed for every other one.
_ANY_VERB_QUESTIONS = frozenset({"routing_conflict"})


def _question_identity(row: dict[str, object], redactor: Redactor) -> str:
    """One `open_questions` row's wire identity — `_wire_identity`'s reading,
    except for the questions above, whose absent verb renders as `any`."""
    method = row["method"]
    if method is None and str(row["question"]) in _ANY_VERB_QUESTIONS:
        method = "any"
    return _wire_address(row["protocol"], method, row["path"], redactor)


def _wire_address(
    protocol_value: object, method_value: object, path_value: object, redactor: Redactor
) -> str:
    """A wire identity as one string. A protocol in `_VERBLESS_PROTOCOLS`
    defines no verb, so it renders `protocol path` with no method at all;
    every other protocol renders `method path`, prefixed by the protocol where
    its verb does not imply one. Any half of any shape may be NULL, and
    `(unresolved)` stays the marker for an identity the analysis could not
    read — never a bare `None`.

    `path` is one of the two columns that can carry a whole address (D01 §3,
    2I's ruling that an expression lands in it unsplit), so it passes the
    redactor: `https://user:pass@host/x` renders with its userinfo stripped,
    and a repo value pattern masks whatever else it names. A `${...}`
    expression passes through whole — it is a reference to a value, not the
    value."""
    protocol = "" if protocol_value is None else str(protocol_value)
    rendered_path = "(unresolved)" if path_value is None else redactor.redact_text(str(path_value))
    # NO protocol at all — the address alone, with no verb and no prefix
    # (OI-1). Only an `open_questions` row reaches this: an `endpoints` row
    # always carries one (`resolve/endpoints.py` refuses a catalog that mints
    # rows and declares none), while a question filed by a catalog with no
    # wire identity of its own carries the empty string its catalog declared.
    # Without this arm such a row falls through to the verbed branch and
    # renders `(unresolved) ordersIn` — a verb reported as unread, which is
    # the exact failure `_VERBLESS_PROTOCOLS`'s own comment above names, about
    # a row whose protocol was never going to have one either.
    if not protocol:
        return rendered_path
    if protocol in _VERBLESS_PROTOCOLS:
        return f"{protocol} {rendered_path}"
    method = method_value
    # A verbed protocol whose row carries no verb *by design*
    # (`_VERB_OPTIONAL_PROTOCOLS`, above): rendering `(unresolved)` there
    # would report a gap that does not exist. Every other verbed protocol —
    # HTTP and the SSE routes reclassified out of it alike — has a method it
    # was supposed to read, so a NULL genuinely is unread.
    if method is None and protocol in _VERB_OPTIONAL_PROTOCOLS:
        return f"{protocol} {rendered_path}"
    rendered_method = "(unresolved)" if method is None else str(method)
    prefix = f"{protocol} " if protocol in _PROTOCOL_QUALIFIED else ""
    return f"{prefix}{rendered_method} {rendered_path}"


def _short_handler(descriptor: str) -> str:
    """`descriptor` (a BARE descriptor, `bare_descriptor`'s own output) as the
    human spelling a reader recognizes at a glance: the owning type's simple
    name and the method name, joined by `#` — `UserResource#deleteUser` for
    `io/github/jhipster/sample/web/rest/UserResource#deleteUser(sig_4a71b976).`
    — never the package path, the `sig_` disambiguator, or the trailing `.`
    (2M design §5c, the JHipster field run's own example). A descriptor with
    no owner (a free function) has no `#` to join around, so it renders as
    its own bare simple name alone.

    Deliberately lossy: two overloads sharing a name now spell identically
    here (the ruled consequence spec §5c states outright), which is exactly
    why the FULL descriptor — `sig_` hash included — moves to the endpoint's
    detail block instead of being deleted (`_handler_identity`, below)."""
    owner = owner_of(descriptor)
    method = method_name(descriptor)
    if owner is None:
        return simple_name(method)
    return f"{simple_name(owner)}#{method}"


def _handler_symbol(endpoint: dict[str, object]) -> str | None:
    """The Handler column's underlying symbol — the owner's BARE descriptor,
    package and `sig_` hash included — or `None` where there is no code to
    report at all. `_handler_fallback` is the two different things a `None`
    here can mean; this function only ever answers "is there a symbol."""
    handler = endpoint.get("handler")
    return None if handler is None else bare_descriptor(str(handler))


def _handler_fallback(endpoint: dict[str, object]) -> str:
    """One of the two different things a NULL `handler` can mean, for a row
    `_handler_symbol` answered `None` for.

    Until 2H every inbound row with no handler was a row whose address could
    not be read either, so one word covered both. `schema_operations` (2H
    design §3) makes the second case real: a schema declares an operation
    outright — `resolution` is `resolved`, the identity is complete — and
    names no code at all, because a schema never does and the wiring that
    would is explicitly not read (COVERAGE). Printing `unresolved` there would
    report a gap that does not exist, the same mistake `_wire_identity`
    already refuses to make for a GraphQL resolver's NULL verb.

    `none recorded` rather than `none`: the claim is about what this evidence
    carries, never that the service implements nothing — that would be a
    statement about code this analysis deliberately did not read. The
    discriminator is the row's own two columns, not its protocol or catalog: a
    row that names neither a handler nor a caller and still resolved its
    address is one whose evidence had no symbol to give.
    """
    if endpoint.get("caller") is None and endpoint.get("resolution") == "resolved":
        return "none recorded"
    return "unresolved"


def _handler_cell(endpoint: dict[str, object]) -> tuple[Run, ...]:
    """The Handler column itself: the HUMAN spelling of the symbol, as a code
    run, or the fallback text where there is none — never the machine
    identity `io/github/.../UserResource#deleteUser(sig_4a71b976).` used to
    print verbatim (2M design §5c). The full identity is not lost, only
    moved: `_handler_identity` renders it in the endpoint's own detail block,
    which every endpoint now gets."""
    symbol = _handler_symbol(endpoint)
    if symbol is not None:
        return _code(_short_handler(symbol))
    return _text(_handler_fallback(endpoint))


def _handler_identity(endpoint: dict[str, object]) -> tuple[Run, ...]:
    """The full identity that used to be the Handler column's whole content —
    package path, `sig_` hash and all — now the SYMBOL half of the endpoint's
    own detail header (`_detail_header`, fix round 1 MEDIUM 1): moved, not
    deleted, and still the one place two same-named overloads read as the
    two different methods they are. Where there is no symbol, the same
    fallback text the column itself would have shown stands in — there is
    nothing to move for a row that had no symbol to begin with."""
    symbol = _handler_symbol(endpoint)
    if symbol is not None:
        return _code(symbol)
    return _text(_handler_fallback(endpoint))


def _detail_header(identity: str, symbol_or_fallback: tuple[Run, ...]) -> DetailEntry:
    """A detail block's own header line: the wire identity, then the full
    symbol (or its fallback text) that used to be a table column's whole
    content, joined by ` — ` — ONE convention regardless of direction (fix
    round 1, MEDIUM 1: a two-conventions split, where an inbound header
    carried the symbol alone and an outbound one carried the identity alone,
    left three handler-less rows reading the indistinguishable `- unresolved`
    three times over, naming no endpoint at all). The identity says WHICH
    endpoint the block documents; the symbol is what moved out of the table.
    `entries[0]` stays a bare title — no body or table — matching every
    other detail header."""
    return DetailEntry(_code(identity) + _text(" — ") + symbol_or_fallback, None, None)


_MEDIA_NONE_RECORDED = "—"  # em dash — never a bare blank cell.

# The legend printed once, directly under an inbound table that carries a
# Media column: the glyph is self-explanatory only once, not on every row it
# appears in (2M design §5c).
_MEDIA_LEGEND = f"Media reads `consumes → produces`; `{_MEDIA_NONE_RECORDED}` means none recorded."


def _media(value: object) -> str:
    """One side of the Media column: the JSON list's comma-joined members, or
    the em dash `—` when the side is NULL — never a bare blank cell, so
    a row with both sides NULL still says so rather than reading as an
    omission. `—` rather than a bare hyphen (2M design §5c, the JHipster
    field run): one glyph, one meaning, spelled out once in `_MEDIA_LEGEND`
    rather than read as a stray dash a table cell just happens to contain."""
    if value is None:
        return _MEDIA_NONE_RECORDED
    return ", ".join(json.loads(str(value)))


def _format(endpoint: dict[str, object]) -> str:
    """The Format column beside Media: `protobuf` at `resolved`, `protobuf
    (assumed)` at anything else, `unresolved` where the ladder left `format`
    NULL — the same NULL-renders-`unresolved` rule `rendered_handler` already
    keeps below (2E precedent).

    `format_resolution` is the authority on trust (schema.sql's own comment),
    and this column is the ONLY place a reader sees it — the rendered
    document carries no separate trust column. So `resolved` is the only
    marker that ever prints unhedged; every other non-NULL marker hedges,
    including `narrowed` and a value schema-valid but off today's live
    surface like `partial`. It also covered the case where a row carries a
    non-NULL format beside an `unresolved` marker — which `merge_endpoints.sql`
    produced by taking the weaker of two halves' markers until W27 deleted it
    (F5 §6.1), and which nothing writes today. Printing that plain would make an
    unresolved-trust value typographically identical to a resolved one,
    which is exactly what "an assumed format must never look observed" (2G
    design §5) forbids (task 8 review round 1)."""
    value = endpoint.get("format")
    if value is None:
        return "unresolved"
    if endpoint.get("format_resolution") != "resolved":
        return f"{value} (assumed)"
    return str(value)


def _via_entry(endpoint: dict[str, object], origin_by_symbol: dict[str, str]) -> DetailEntry | None:
    """The `Via:` detail entry for a row an extracted LIBRARY contributed, or
    `None` at all for the ordinary case.

    A library-contributed row is otherwise indistinguishable from one the
    module's own code declares — same table, same columns, same resolution —
    and the difference matters to a reader: the operation is real, but nothing
    in this repository declares it, so the place to go and look is the
    library's.

    **Keyed on the SURVIVING evidence, which is the handler wherever there is
    one.** A merged `both` row keeps the handler's own declaration and carries
    the caller onto it (D02 §3), so a path this module HANDLES is locally
    declared even where the client that calls it came out of a jar — marking it
    would attribute this module's own endpoint to a library. Only where there
    is no handler at all is the caller the deriving side. A row naming neither
    is a row nothing can attribute, and it is left unmarked rather than guessed
    at.
    """
    deriving = endpoint.get("handler") or endpoint.get("caller")
    origin = None if deriving is None else origin_by_symbol.get(str(deriving))
    return None if origin is None else DetailEntry(_text("Via"), _code(origin), None)


def _declared_throws(endpoint: dict[str, object]) -> list[str]:
    """The handler's own DECLARED exceptions (JVMS 4.7.5, `Signature.throws`), read off
    the same `handler_signature` JSON `contracts.py`/`protocol_hint.py` already parse for
    the Request/Response lines — never a second query for what one row already carries.
    Empty wherever the row has no signature at all: a schema-declared operation, an
    outbound-only row, or a handler this pass never named."""
    raw = endpoint.get("handler_signature")
    if raw is None:
        return []
    return [str(symbol) for symbol in json.loads(str(raw)).get("throws", [])]


def _throws_by_root(rows: Sequence[dict[str, object]]) -> dict[str, tuple[str | None, ...]]:
    """`reachable_throws` (`G-74`), grouped by the root it was walked from — the shape
    `_fields_by_shape`/`origin_by_symbol` already group their own rows into before a
    per-endpoint loop reads them. A NULL `target` is kept, once per row: it is a real
    reachable throw whose type this pass could not read (`G-52`'s rethrow case), not an
    absence to drop."""
    by_root: dict[str, list[str | None]] = {}
    for row in rows:
        by_root.setdefault(str(row["root"]), []).append(cast(str | None, row.get("target")))
    return {root: tuple(targets) for root, targets in by_root.items()}


def _fails_with_entry(
    endpoint: dict[str, object], throws_by_root: dict[str, tuple[str | None, ...]]
) -> DetailEntry | None:
    """The `Fails with:` detail line (`G-74`): what the handler DECLARES (`Signature.
    throws`) beside what it is OBSERVED to throw — a reachable `invoke_kind: throw` call
    site (`G-52`'s own fact, joined to the handler here by `reachable_throws`). Declared
    first, each half sorted on its own (NFR-1) — the two halves answer different
    questions and merging them would read as one claim rather than two.

    `None` where both halves are empty: "declares nothing and none of its reachable calls
    throw" is not a claim this renderer makes, the same restraint `_via_entry` already
    keeps for a row with no library to name.

    An unread throw target (a rethrow whose type lives in the try-catch table this pass
    does not read) renders the same words `_call_cell` already settled on for it
    (`bfece6f`) — `(type unread)` — collapsed to ONE mention however many unread rethrows
    are reachable: every one of them says the identical "some type, not read", and
    repeating a non-fact is not evidence."""
    declared = sorted(simple_name(symbol) for symbol in _declared_throws(endpoint))
    handler = endpoint.get("handler")
    observed = throws_by_root.get(str(handler), ()) if handler is not None else ()
    named = sorted({simple_name(target) for target in observed if target is not None})
    unread = any(target is None for target in observed)
    if not declared and not named and not unread:
        return None
    parts = [f"`{name}` (declared)" for name in declared]
    parts += [f"`{name}` (thrown)" for name in named]
    if unread:
        parts.append("(type unread) (thrown)")
    return DetailEntry(_text("Fails with"), _runs(", ".join(parts)), None)


def _library_gap_item(what: str, entry: str) -> tuple[Run, ...]:
    """One unreachable library, as the runs of `<what>, so nothing above
    accounts for it: library `<coordinate>` — <reason>.` (minus the bullet's
    own leading `- `, which `MachineList` supplies).

    The producer writes `<coordinate>: <reason>` — the shape `uncovered`
    already uses — and only the coordinate is set in code here: a reason is a
    sentence for a person to read, and typesetting a sentence as an identifier
    is how a document teaches its reader to skip it. An entry with no reason at
    all still renders, as the coordinate alone.
    """
    coordinate, _, reason = entry.partition(": ")
    tail = f" — {reason}" if reason else ""
    return _runs(f"{what}, so nothing above accounts for it: library `{coordinate}`{tail}.")


def _candidate_line(question: str, candidate: dict[str, object]) -> str:
    """One open question's candidate, in the same prose the writing pass
    already puts in its own `evidence` trail (`resolve/format.py`,
    `resolve/shapes/parse_binding.py`, `resolve/service_identity.py`'s three
    engines) — so the fact reads the same way in the trail and in this list.
    Each kind's candidates carry different keys (2G design §6, 2O design §0),
    so this switches on `question` rather than guessing a common shape out of
    the JSON — the same discipline `open_questions.py`'s own docstring asks
    of "the renderer"."""
    if question == "format_conflict":
        return f"{candidate['format']} from {candidate['seen_in']} ({candidate['why']})"
    if question == "payload_binding":
        return (
            f"{candidate['payload_type']} in {candidate['seen_in']} "
            f"via {candidate['why']} at {candidate['hops']} hop(s)"
        )
    if question == "service_identity":
        # All three writers (`resolve/engines/supertype_derived.py`,
        # `injected_client.py`, `annotation_driven.py`'s `gaps`) file the same
        # two keys — the flagged class and why its identity did not resolve —
        # verified against each engine's own `candidates` line rather than
        # trusting `open_questions.py`'s comment (2O design §1b).
        return f"{candidate['class']}: {candidate['reason']}"
    if question == "channel_destination":
        # 2O §5: the channel name and the handler symbol
        # `spring-integration.yml` flags, verified against the writer's own
        # `candidates` line (`resolve/engines/config_join.py`). *This comment
        # said "Task 9, not yet shipped" until the 2O documentation sweep
        # (`A-Mi23`); Task 9 shipped the writer and left the arm's comment
        # describing the day before.*
        return f"{candidate['channel']} → {candidate['handler']}"
    if question == "environment_divergence":
        # 2O §2b: the config key and its per-environment values, filed by
        # `resolve/engines/derived_resource.py:224` where
        # `spring.data.rest.base-path` differs between environments — shipped
        # in Task 6, which this comment said it was waiting for until the 2O
        # documentation sweep (`A-Mi23`). Sorted so two runs compose the
        # identical sentence (NFR-1), the same discipline
        # `supertype_derived._reason` already keeps for its own composed text.
        per_environment = ", ".join(
            f"{env}={value}"
            for env, value in sorted(cast(dict[str, object], candidate["values"]).items())
        )
        return f"{candidate['key']}: {per_environment}"
    if question == "binder_protocol":
        # F2 §3.4: the binding and the configured binder name
        # `spring-cloud-stream.yml` could not map to a protocol, filed by
        # `resolve/engines/config_join.py`'s `gaps` and verified against that
        # writer's own `candidates` line.
        return f"{candidate['binding']}: binder `{candidate['binder']}` maps to no protocol"
    if question == "unselected_binding":
        # F2 §3.4: one candidate the cardinality rule declined to choose between,
        # and the configuration key that would say which binds. Filed by
        # `resolve/engines/config_join.py`'s `gaps`, and verified against that
        # writer's own `candidates` line.
        return f"{candidate['candidate']} (set `{candidate['selected_by']}` to choose)"
    if question == "registration_activation":
        # `OI-64`: a registration whose framework needs a later ACTIVATION call,
        # built and handed back rather than started here. Filed by
        # `resolve/engines/interface_implementation.py`, and verified against that
        # writer's own `candidates` line.
        #
        # The sentence names the enclosing method because that is where a reader has
        # to look: the question is not "is this subscription real" but "does anyone
        # call the thing this method returns, and start it". Without the method there
        # is nothing to open.
        return (
            f"{candidate['registration']} in {candidate['enclosing']} is returned, not "
            f"activated — nothing here calls {candidate['activated_by']}"
        )
    if question == "handler_protocol":
        # F2 §3.6: the class, the annotation two frameworks share, and the wire
        # ONE of them would publish it on — filed by
        # `resolve/engines/annotation_driven.py`'s `gaps` where the build settles
        # neither library. Verified against that writer's own `candidates` line.
        #
        # The protocol is what makes a candidate answerable (§3.6 review, finding
        # 3). Both catalogs ask about one class, `service_identity._merged` folds
        # them into a single question, and its candidates are then one line per
        # wire — without the protocol they rendered as the same sentence twice
        # and a verdict could only ever anchor to the first.
        #
        # The wire leads, because the candidates render joined on one line and it
        # is the only part that differs between them.
        return f"`{candidate['protocol']}` — {candidate['class']} carries {candidate['annotation']}"
    if question == "self_exchange":
        # F5 §6.1 (W27): one side of a wire identity this module both serves and calls,
        # filed by `resolve/self_exchange.py` and verified against that writer's own
        # `candidates` line.
        #
        # The ADDRESS is what makes a candidate answerable, and it is the whole reason
        # these rows stopped being merged: the fixture's SOAP pair shares a payload
        # QName while the call goes to `${soap.billing.uri}`, and a reader cannot see
        # that in a sentence that names only the symbols. A called side with no resolved
        # address says so rather than reading as one that reaches nowhere.
        # A schema-first row names no method at all — its operation is declared by a
        # `.wsdl` or a `.proto` — so the symbol may legitimately be absent on either
        # side, and saying so beats a sentence that trails off.
        symbol = candidate["symbol"] or "no method here"
        if candidate["side"] == "served":
            return f"served here by {symbol}"
        return f"called by {symbol} at {candidate.get('peer') or 'no resolved address'}"
    if question == "routing_conflict":
        # F5 §6.1 (W28): one handler claiming an address another handler also claims,
        # filed by `resolve/routing_conflicts.py` and verified against that writer's own
        # `candidates` line. The candidates render joined on one line, and the handler is
        # the only thing that differs between them.
        return f"{candidate['handler']}"
    if question == "routing_depth":
        # Spec 2026-09-19 §4a (A2): a routing body's helper chain the combinator engine
        # stopped following at its depth bound, filed by
        # `resolve/engines/combinator.py::_routing_depth_rows` and verified against that
        # writer's own `candidates` line — one row per run, one candidate per chain, the
        # bound carried on the candidate so this arm states what the engine did rather
        # than repeating its constant. The sentence names the entry's caller because
        # that is where a reader has to open the file, and the first unread callee
        # because that is where the walk stopped.
        return (
            f"a routing helper chain deeper than {candidate['depth']} calls from "
            f"{candidate['caller']} was not followed; its first unread callee is "
            f"{candidate['callee']}"
        )
    # `open_questions.py`'s QUESTIONS is a closed set enforced at WRITE time
    # (`record_open_questions` raises on anything outside it) — this arm list
    # is the matching enforcement at RENDER time. The two are independent
    # code paths, so this holds only as long as every kind added to QUESTIONS
    # ships its arm here in the same change; reaching this line means that
    # discipline slipped and the two sets have diverged (NFR-5).
    raise ValueError(f"open question `{question!r}` has no rendering rule")


def render_module_document(
    module: ModuleModel,
    report: ResolveReport,
    commit: str,
    uncovered: tuple[str, ...] = (),
    shape_fields: Sequence[dict[str, object]] = (),
    type_hierarchy: Sequence[dict[str, object]] = (),
    resolved_config: Sequence[dict[str, object]] = (),
    open_questions: Sequence[dict[str, object]] = (),
    library_symbols: Sequence[dict[str, object]] = (),
    libraries_not_scanned: tuple[str, ...] = (),
    redactor: Redactor = _DEFAULT_REDACTOR,
    overlay: EnrichmentOverlay | None = None,
    stale: frozenset[int] = frozenset(),
    traces: Sequence[Trace] = (),
    reachable_throws: Sequence[dict[str, object]] = (),
) -> str:
    """`architecture.md` — the markdown serialization of the assembled
    document. Kept as its own entry point because it is what every caller of
    this renderer has always asked for; the assembly it composes is
    `assemble_module_document`, and the HTML emitter serializes that same
    list rather than re-reading these bytes."""
    return markdown_document(
        assemble_module_document(
            module,
            report,
            commit,
            uncovered,
            shape_fields=shape_fields,
            type_hierarchy=type_hierarchy,
            resolved_config=resolved_config,
            open_questions=open_questions,
            library_symbols=library_symbols,
            libraries_not_scanned=libraries_not_scanned,
            redactor=redactor,
            overlay=overlay,
            stale=stale,
            traces=traces,
            reachable_throws=reachable_throws,
        )
    )


def assemble_module_document(
    module: ModuleModel,
    report: ResolveReport,
    commit: str,
    uncovered: tuple[str, ...] = (),
    shape_fields: Sequence[dict[str, object]] = (),
    type_hierarchy: Sequence[dict[str, object]] = (),
    resolved_config: Sequence[dict[str, object]] = (),
    open_questions: Sequence[dict[str, object]] = (),
    library_symbols: Sequence[dict[str, object]] = (),
    # Carried in rather than read off `module`, unlike `libraries_not_resolved`:
    # resolution is a property of the module the detector described, while a
    # scan failing is something that happened during one analysis of it.
    libraries_not_scanned: tuple[str, ...] = (),
    # The render EXIT's redactor (2K design §1). Defaulted rather than
    # required so redaction is on for every caller, including one written
    # before this existed — see `_DEFAULT_REDACTOR`.
    redactor: Redactor = _DEFAULT_REDACTOR,
    # The overlay, already schema-validated, or `None` for the ordinary module
    # with no enrichment at all — which assembles to one machine section and
    # therefore to exactly the document this renderer produced before 2K.
    overlay: EnrichmentOverlay | None = None,
    # The positions in `overlay.claims` whose referents no longer exist
    # (`application/enrich/stale_claims`). Excluded from the document and
    # counted in a visible notice; the overlay file keeps them. Indices rather
    # than claims because the overlay is a list written wholesale, and a
    # position is what locates one in the file a reader would go and look at.
    stale: frozenset[int] = frozenset(),
    # One walk per row of `roots`, already performed by
    # `application/query/trace.py` and handed in by the composition root.
    # Carried like every other table this renderer shows and NOT re-derived
    # here: `egress` reads and renders, and a renderer reaching for a
    # workspace to walk a graph is derivation hiding in presentation — the
    # thing the "Egress is read-only" import contract exists to forbid. Empty
    # for a module that exposes nothing and schedules nothing, which renders
    # `None found.` the way the two non-wire sections above it do.
    traces: Sequence[Trace] = (),
    # `G-74`'s own join, carried in the same way: `storage/duckdb/workspace.py`'s
    # `reachable_throws` query joins `reachability` to `call_sites` at the composition
    # root, and this renders the answer rather than re-deriving it — one row per (root,
    # caller, ordinal), `target` the thrown type or NULL for an unread rethrow (`G-52`).
    reachable_throws: Sequence[dict[str, object]] = (),
) -> AssembledDocument:
    """Adds no information. Every row comes from the graph, and every omission
    is stated (M07). Rendering the same report twice is byte-identical
    (NFR-1): nothing here reads a clock, and endpoint and shape order is
    whatever the graph query already fixed.

    The two columns that can carry an address — `path`, through
    `_wire_identity`, and `peer` — pass `redactor` on their way into a line.
    Nothing else here renders a configuration VALUE: the module document names
    the expression a row carries and the KEYS pass 2 could not resolve, never
    the values behind them, so the resolved-config exposure this redactor
    closes is the export exit's (`storage/duckdb/workspace.py`), not this
    one's."""
    fields_by_shape = _fields_by_shape(shape_fields)
    origin_by_symbol = {str(row["symbol"]): str(row["origin"]) for row in library_symbols}
    throws_by_root = _throws_by_root(reachable_throws)
    # Wire identities already carrying a library attribution, so the outbound
    # section does not repeat one the inbound section stated (a `both` row is
    # listed in both).
    attributed: set[str] = set()

    # Typed sections, built at the sites that already know the structure (2M
    # design §5b) — the flat line list this used to be is gone, and with it
    # the need to lift a diagram back out of one: `MachineDiagram` is
    # appended directly where the fence used to be spliced in.
    sections: list[Section] = [
        MachineHeading(1, module.module_id),
        MachineParagraph(_runs(f"Generated from commit `{commit}`.")),
        MachineHeading(2, "Coverage"),
    ]
    coverage_items = [
        _runs(f"Documents analysed: {report.coverage.get('documents', 0)}"),
        _runs(f"Partial documents: {report.coverage.get('partial_documents', 0)}"),
        _runs(f"Facts loaded: {report.facts_loaded}"),
    ]
    coverage_items += _understanding_items(report.coverage)
    coverage_items += _config_coverage_items(resolved_config)
    coverage_items += _unresolved_derivation_items(report.endpoints)
    # Per-environment peer AUTHORITIES — one substituted address per
    # environment for a resolved outbound row — are the system-scope
    # document's material (M06 stitcher, M07 system scope): this module
    # document names the expression a row carries (`path`/`peer`), never the
    # per-environment values `resolved_peers` joins them against.
    coverage_items.append(
        _runs(
            "Per-environment peer resolution is the system architecture "
            "document's material, not repeated per module here."
        )
    )
    sections.append(MachineList(tuple(coverage_items)))
    # `beside-open-question`'s config placement (2N design §2): a config
    # verdict answers one of the "Configuration key unresolved" lines just
    # written above, so it lands right after the Coverage listing that
    # carries them — the whole listing, not a per-row index, since the brief
    # prints those rows as one listing rather than one section apiece the way
    # `## Open questions` does.
    config_end = len(sections)

    sections.append(MachineHeading(2, "Structure"))
    if report.shapes:
        nodes, edges = _contract_nodes(report.shapes, shape_fields, type_hierarchy)
        mermaid = class_diagram(nodes, edges).rstrip("\n")
        sections.append(MachineDiagram(mermaid))
    else:
        sections.append(MachineParagraph(_runs("None derived.")))
    # `after-component-overview` (2K design §6). `## Structure` IS this
    # document's component overview: the contract class diagram is the only
    # place it draws the module's own types as a whole. An anchor is a
    # position, so it is recorded here — where the section ends — rather than
    # searched for afterwards in text that would then have to be parsed.
    structure_end = len(sections)

    sections.append(MachineHeading(2, "Inbound endpoints"))
    inbound = [e for e in report.endpoints if str(e["direction"]) in ("inbound", "both")]
    if inbound:
        # Two passes (fix round 1, MEDIUM 2): a citation needs the shape's
        # FINAL display name, and two different shapes sharing one simple
        # name can only be told apart once every shape this section will
        # cite is already known — a citation built inline, endpoint by
        # endpoint, could not yet know a same-named collision two endpoints
        # later was coming. `_cited_named_shapes` is pass one, over ALL of
        # `inbound`; `shape_names` is the disambiguated registry both the
        # per-endpoint citations and `### Shapes` itself read from pass two.
        cited_shapes = _cited_named_shapes(inbound, fields_by_shape)
        shape_names = _disambiguated_shape_names(cited_shapes)

        headers = ("Endpoint", "Handler", "Media", "Format", "Resolution")
        rows = []
        for endpoint in inbound:
            media = f"{_media(endpoint.get('consumes'))} → {_media(endpoint.get('produces'))}"
            rows.append(
                (
                    _code(_wire_identity(endpoint, redactor)),
                    _handler_cell(endpoint),
                    _text(media),
                    _text(_format(endpoint)),
                    _text(str(endpoint["resolution"])),
                )
            )
        sections.append(MachineTable(headers, tuple(rows)))
        sections.append(MachineParagraph(_runs(_MEDIA_LEGEND)))
        # Every inbound endpoint now gets a detail block, not only the ones
        # with a `Via`/`Request`/`Response` line to hang under it (2M design
        # §5c, adversarial review C3): the full symbol the Handler column no
        # longer spells out lives here instead, and with one block per row in
        # table order, correlating a block back to its row needs no shared
        # identity between them.
        for endpoint in inbound:
            request = _descriptor_entry(
                "Request", endpoint.get("request_shape"), fields_by_shape, shape_names
            )
            response = _descriptor_entry(
                "Response", endpoint.get("response_shape"), fields_by_shape, shape_names
            )
            streaming = _streaming_entry(endpoint.get("response_shape"))
            via = _via_entry(endpoint, origin_by_symbol)
            fails_with = _fails_with_entry(endpoint, throws_by_root)
            entries = [
                entry
                for entry in (via, request, response, streaming, fails_with)
                if entry is not None
            ]
            identity = _wire_identity(endpoint, redactor)
            header = _detail_header(identity, _handler_identity(endpoint))
            sections.append(MachineDetail((header, *entries)))
            if via is not None:
                attributed.add(identity)
        if cited_shapes:
            sections.append(MachineHeading(3, "Shapes"))
            for shape_id, shape_rows in cited_shapes.items():
                name = shape_names[shape_id]
                shape_header = DetailEntry(_code(name), None, None)
                fields_entry = DetailEntry(_text("Fields"), None, _shape_fields_table(shape_rows))
                sections.append(
                    MachineDetail((shape_header, fields_entry), anchor=_shape_anchor_id(name))
                )
    else:
        sections.append(MachineParagraph(_runs("None found.")))

    # An empty section is now a real statement rather than a stand-in for
    # "not implemented" — outbound derivation exists (NFR-7).
    sections.append(MachineHeading(2, "Outbound endpoints"))
    outbound = [e for e in report.endpoints if str(e["direction"]) in ("outbound", "both")]
    if outbound:
        headers = ("Endpoint", "Peer", "Caller", "Format", "Resolution")
        rows = []
        for endpoint in outbound:
            peer = endpoint.get("peer")
            caller = bare_descriptor(str(endpoint["caller"]))
            rows.append(
                (
                    _code(_wire_identity(endpoint, redactor)),
                    _text("unresolved" if peer is None else redactor.redact_text(str(peer))),
                    _code(caller),
                    _text(_format(endpoint)),
                    _text(str(endpoint["resolution"])),
                )
            )
        sections.append(MachineTable(headers, tuple(rows)))
        # The outbound half has no request/response detail to hang under, so
        # this is its whole detail block — written only where there is
        # something to say, which is the same rule the inbound one keeps.
        #
        # Once per identity, never once per section: a `both` row is listed in
        # BOTH tables (it is one wire this module exposes and calls), so an
        # attribution already stated above must not be stated again here. The
        # same attribution twice reads as two findings.
        for endpoint in outbound:
            identity = _wire_identity(endpoint, redactor)
            via = None if identity in attributed else _via_entry(endpoint, origin_by_symbol)
            if via is not None:
                # One convention with inbound (fix round 1, MEDIUM 1): the
                # identity, then the caller's own full symbol — the same
                # unshortened form the Caller column already carries (2M
                # §5c never touches that column, only the inbound Handler
                # one), not a second spelling invented for this line alone.
                caller_symbol = _code(bare_descriptor(str(endpoint["caller"])))
                header = _detail_header(identity, caller_symbol)
                sections.append(MachineDetail((header, via)))
                attributed.add(identity)
    else:
        sections.append(MachineParagraph(_runs("None found.")))
    # `after-endpoint-table`: after BOTH tables and their detail blocks. The
    # document's endpoint listing is one thing to a reader — a claim about "the
    # endpoints" that landed between the inbound and outbound halves would read
    # as a claim about the inbound ones alone.
    endpoints_end = len(sections)

    # The two NON-WIRE sections (2O design §4), below the endpoint tables and
    # above the ledger: they are module SURFACE, like the tables, and not a
    # hand-off inbox like the questions.
    #
    # **Both render unconditionally, "None found." included**, which is the
    # endpoint tables' rule rather than the `Open questions` one below. The
    # difference is what an absent section would mean. An empty inbox is not a
    # finding; "this service runs no background work" and "this service
    # declares no error contract" both ARE — and a section that simply
    # disappears leaves a reader unable to tell that answer from a Sextant that
    # never looked, which is the silent under-report FR-17 exists to prevent.
    # The cost is two short sections in every document, which is the cheap
    # side of that trade.
    sections.append(MachineHeading(2, "Scheduled work"))
    sections.extend(_scheduled_work_sections(report.scheduled_work))
    sections.append(MachineHeading(2, "Error handling"))
    sections.extend(_error_handler_sections(report.error_handlers))

    # BELOW both non-wire sections, and for the reason they sit where they do:
    # a trace starts from a ROOT, and a root is an inbound endpoint OR a
    # scheduled job (2Q `I1`/`I3`). Placing this under `## Inbound endpoints`
    # would say the scheduled traces are endpoint traces; placing it under
    # `## Scheduled work` would say the reverse. It goes after both, where it
    # is a claim about everything above it.
    #
    # Unconditional, `None found.` included — the `Scheduled work`/`Error
    # handling` rule rather than the `Open questions` one. "Nothing in this
    # module starts any work" is a finding; a section that disappears leaves a
    # reader unable to tell it from a Sextant that never walked (FR-17).
    sections.append(MachineHeading(2, "Traces"))
    sections.extend(_trace_sections(traces, redactor))

    # Rendered only when the ledger holds rows (2G design §8): a run with
    # nothing to ask leaves the section absent, the `## Catalogs skipped`
    # precedent below rather than the NFR-7 "looked and found nothing" one —
    # this is a hand-off inbox for 2K, and an empty inbox is not a finding.
    beside_question: list[tuple[tuple[str | None, ...], int]] = []
    if open_questions:
        sections.append(MachineHeading(2, "Open questions"))
        for row in open_questions:
            question = str(row["question"])
            candidates = json.loads(str(row["candidates"]))
            rendered = "; ".join(_candidate_line(question, c) for c in candidates)
            item = _runs(f"`{_question_identity(row, redactor)}` — {question}: {rendered}")
            # One question, one single-item `MachineList`: a `beside-open-
            # question` verdict has to land right after THIS question and no
            # other, so the question needs its own section index to anchor
            # on — a shared list covering every question would only ever let
            # a claim land after the last one.
            sections.append(MachineList((item,)))
            # `beside-open-question`, per question: a verdict renders under the
            # very line it answers. Keyed on the row's own values, NOT on the
            # rendered line — matching on presentation would make placement
            # depend on how a line happens to be formatted. The key is the
            # SHARED `open_question_identity`, the very function validation
            # matches a verdict on (2K final review, F3): keying on the RAW
            # `path` here while validation canonicalized the redacted one meant
            # a verdict on a question whose path changes under redaction
            # validated cleanly and then rendered at `questions_end` instead of
            # beside its question.
            beside_question.append((open_question_identity(row, redactor), len(sections)))
    # Where a `beside-open-question` claim goes when no single question owns
    # it: after the last question, or — with no section at all — where the
    # section would have been. Only a verdict names a question; every other
    # kind anchored here is a claim about the open questions as a group.
    questions_end = beside_question[-1][1] if beside_question else endpoints_end

    sections.append(MachineHeading(2, "Known gaps"))
    gap_items = [_runs(gap) for gap in _GAPS]
    # Named one by one, because a compiled source nothing read is the one gap
    # a reader can act on: it says which part of the module this document is
    # silent about (FR-17, M03).
    gap_items += [
        _runs(f"Not read, so nothing above accounts for it: `{source}`.") for source in uncovered
    ]
    # Named one by one for the same reason: a payload type nothing could open
    # is the gap between "this shape is the contract" and "this shape is as
    # much of the contract as anyone could see", and only the name says which
    # catalog entry would close it (FR-17).
    # F4 §5.2 (W25): the LEVER, not only the gap. A payload type nothing could open
    # used to render as a bare statement of absence, which tells a reader that something
    # is missing and nothing about how to get it — and the two ways to get it are both
    # things only they can do. A type compiled in a reactor sibling arrives once that
    # sibling is built; one compiled in a third-party jar arrives once `extract_libraries`
    # names it. Neither is something this analysis can do on the reader's behalf, which
    # is exactly why naming them is the whole value of the line (§8.1 rule 3).
    gap_items += [
        _runs(
            f"Not expanded, so the shapes referring to it are open: `{symbol}`. "
            "Its fields arrive when the module that compiles it is built alongside this "
            "one, or — for a type from a dependency outside the build — when "
            "`extract_libraries` names that dependency in `.sextant.yml`."
        )
        for symbol in report.unexpanded_types
    ]
    # Named one by one for the same reason again: a library this module asked
    # to extract and nobody could read is the difference between "nothing is
    # called through it" and "nobody looked" (FR-17, M02). Both lists carry
    # `<coordinate>: <reason>`, and the reason is the point — it says what to
    # go and do, which a bare coordinate never could.
    gap_items += [
        _library_gap_item("Not resolved", entry) for entry in module.libraries_not_resolved
    ]
    gap_items += [_library_gap_item("Not scanned", entry) for entry in libraries_not_scanned]
    sections.append(MachineList(tuple(gap_items)))

    if report.skipped_catalogs:
        sections.append(MachineHeading(2, "Catalogs skipped"))
        skipped_items = [
            _runs(f"`{skipped.catalog_id}` requires {', '.join(skipped.missing_capabilities)}")
            for skipped in report.skipped_catalogs
        ]
        sections.append(MachineList(tuple(skipped_items)))

    return _interleave(
        tuple(sections),
        _Anchors(
            structure_end,
            endpoints_end,
            tuple(beside_question),
            questions_end,
            config_end,
            len(sections),
        ),
        overlay,
        stale,
        redactor,
    )


_SCHEDULED_HEADERS = ("Handler", "Trigger", "Expression", "Resolution")
_ERROR_HEADERS = ("Exception", "Status", "Handler", "Declared by", "Scope", "Response")
# Never a bare blank cell, the `_MEDIA_NONE_RECORDED` precedent: an empty cell
# reads as a formatting slip, while an em dash reads as "nothing recorded",
# which is what a NULL in either table means.
_NONE_RECORDED = "—"


def _scheduled_work_sections(rows: Sequence[dict[str, object]]) -> list[Section]:
    """The `scheduled_work` table as one machine table, or the "None found."
    paragraph the endpoint sections use.

    The expression is rendered as CODE and never reformatted: a cron string
    re-spaced for the page names a different schedule from the one that runs.
    `resolution` rides along because an `unresolved` expression is a
    placeholder this analysis did not substitute, and a reader who cannot see
    that would read `${orders.cron}` as the schedule itself.
    """
    if not rows:
        return [MachineParagraph(_runs("None found."))]
    table = tuple(
        (
            _code(bare_descriptor(str(row["handler"]))),
            _text(str(row["trigger"])),
            _code(str(row["expression"])),
            _text(str(row["resolution"])),
        )
        for row in rows
    )
    return [MachineTable(_SCHEDULED_HEADERS, table)]


def _error_handler_sections(rows: Sequence[dict[str, object]]) -> list[Section]:
    """The `error_handlers` table, exception first.

    Exception first because that is what a reader looks a row up BY — "what
    does this service answer when an order is missing" — while the handler is
    the answer. The status is rendered through `member_name` rather than
    `simple_name`: the value is an enum REFERENCE, so the constant is the part
    after the type marker, and `simple_name` would keep the declaring type
    glued to it. `Declared by` and `Scope` sit together deliberately: they are
    one claim in two columns, and reading either alone gets a controller's own
    handler and an application-wide advice the wrong way round.
    """
    if not rows:
        return [MachineParagraph(_runs("None found."))]
    table = tuple(
        (
            _code(simple_name(str(row["exception"]))),
            _text(_cell(row["status"], member_name)),
            _code(bare_descriptor(str(row["handler"]))),
            _text(_cell(row["declared_by"], simple_name)),
            _text(_cell(row["scope"], str)),
            _text(_cell(row["response_shape"], simple_name)),
        )
        for row in rows
    )
    return [MachineTable(_ERROR_HEADERS, table)]


def _cell(value: object, render: Callable[[str], str]) -> str:
    """One optional column, rendered or marked as not recorded. NULL keeps
    exactly one meaning in both tables — nothing evidenced it — and never
    becomes a guess at what the framework would have done."""
    return _NONE_RECORDED if value is None else render(str(value))


# --------------------------------------------------------------------------
# `## Traces` (2Q `G4`/`I3`, FR-6/FR-7) — the walk, rendered.
#
# **This section renders; it does not decide.** Every column below is a field
# `application/query/trace.py` already carries, spelled out rather than
# summarised, and the four places a reader could be misled are stated in the
# section's own preamble rather than fixed here by a rule this file invented:
#
# - **`revisited`.** A method is expanded once per trace, so a path through
#   the table is not always followable to a terminal. The step is still a ROW
#   — dropping it would delete the call — and its `Stop` says `revisited`,
#   which means "this callee's own calls are drawn at its first appearance
#   above". The renderer neither copies that subtree here (exponential on an
#   ordinary diamond, D01's own reason for not storing traces) nor hides the
#   call.
# - **Reachability, never execution.** Said in the preamble, said again in
#   every diagram's `Elides:`, and built into the diagram: there are no return
#   arrows, because the walk records what a callee HANDS BACK and never when
#   control comes back.
# - **`Reaches` is read, not decided here** (W30). `terminal_kind` gained a
#   producer — `resolve/terminals.py`, over catalog data — so this column
#   renders what that pass wrote and classifies nothing itself. Inventing the
#   classification here would be derivation hiding in presentation, which the
#   import-linter contract exists to forbid; the note that used to stand here
#   said `terminal_kind` had no producer at all, which stopped being true in
#   the same commit that added this column.
# - **Cross-module stops read as `boundary` too**, because no body was read in
#   THIS workspace — which is the truth about what was measured and an
#   under-report of what exists. Stated where the reader meets it. `Reaches`
#   does NOT separate them either: a sibling-module call and a third-party
#   call both read `unresolved` unless a catalog names the type, so the `Call`
#   column's full descriptor is still what a reader tells them apart by.
# --------------------------------------------------------------------------

_TRACE_HEADERS = (
    "Reached by",
    "Root",
    "Starts as",
    "Depth",
    "Steps",
    "Terminals",
    "Detail",
)

_TRACE_STEP_HEADERS = (
    "Depth",
    "Caller",
    "Call",
    "Dispatch",
    "Resolution",
    "Value",
    "Returns",
    "Stop",
    # F7 §8.2 (W30). What the call REACHES, beside why the walk stopped — the two answer
    # different questions and a step carries both.
    "Reaches",
)

# What a reader has to know before the first table, in the machine's own
# words. Every line is a property of the WALK rather than of this rendering —
# which is why they are stated once here and not repeated per trace, and why
# the wording matches `application/query/trace.py`'s own docstring rather than
# paraphrasing it.
_TRACE_PREAMBLE = (
    (
        "`Reached by` is the wire address a request arrives at, spelled exactly as the "
        "inbound endpoint table above spells it, so a trace can be found by the URL a "
        "reader knows. A handler serving several addresses is ONE trace listing all of "
        "them — the walk is the same walk whichever address invoked it — and `no wire "
        "address` is a root nothing on the wire reaches, a scheduled job above all. "
        "That is an absence, not an unread value; `(unresolved)` is how this document "
        "says a half of an address was not read."
    ),
    (
        "A trace is REACHABILITY, never execution: every step is a call the compiler "
        "recorded, branches are not distinguished, and two `return` statements are two "
        "possible answers rather than the one that runs. No path below is asserted to "
        "have happened."
    ),
    (
        "Steps are in the walk's own depth-first order, and `Depth` counts edges from "
        "the root — so a step's caller is named on its own row rather than left to be "
        "inferred from indentation."
    ),
    (
        "`Stop` says why a step was not expanded. `boundary` means this workspace read "
        "no body for the callee: a third-party library, the JDK, a MyBatis mapper and a "
        "SIBLING BUILD MODULE all read alike there, because each is a body that is not "
        "here. **`Reaches` is the other half of that question** (W30) — what the call "
        "reaches rather than why the walk stopped — so a data-access call now says "
        "`persistence (database)` or `persistence (cache)` where a JDK call says "
        "`unresolved`. `unresolved` means the terminal was examined and no catalog "
        "claimed it, which on real repositories is most of them — 94-96% across the three "
        "measured. It does NOT separate a sibling build module from a third-party "
        "library: both read `unresolved` unless a catalog names the type, so the `Call` "
        "column's full descriptor is still what tells them apart."
    ),
    (
        "`revisited` means the callee was expanded ELSEWHERE in this same trace and its "
        "own calls are shown at that first appearance: a method is expanded once per "
        "trace, not once per route to it, so a path through one of these tables is not "
        "always followable to a terminal. `cycle` means the callee is already on the "
        "path from the root. There is no third reason a walk stops short of the "
        "evidence: the depth bound retired with W31, so a trace ends where the code "
        "does."
    ),
    (
        "`Value` is the value id the call site produced and `Returns` what the callee "
        "hands back — both LOCAL to the method on that row, so an id in a step's "
        "`Returns` is a value inside the callee and matches its own rows, never the "
        "caller's. `Response` is what the root method itself returns."
    ),
    (
        "`Detail` says whether this trace's steps and diagram are drawn below. Every "
        "trace is drawn, every trace is listed with its depth and its step count, and "
        "the sentence under the table says how many were drawn. A trace is never drawn "
        "in part: half a trace is the under-report this section exists not to be."
    ),
)


def _traces_drawn_sentence(traces: Sequence[Trace]) -> str:
    """What this section drew, in the machine's own words.

    **Never absent, and never a silence.** M07: *"every reduced output states
    that it was reduced"* — a reader who is not told how much of the section is
    drawn cannot tell a complete one from a reduced one, and the sentence is
    where they meet that boundary. This section reduces nothing, so it says the
    count it drew and the count it walked, and they are the same count.

    **The count is stated rather than implied by the blocks below it.** A
    reader — or an agent — counting diagrams to check the table is doing the
    document's work for it, and would find nothing to compare the answer
    against.
    """
    return (
        f"Every trace is rendered in full below: {len(traces)} of {len(traces)}, "
        f"{sum(len(trace.steps) for trace in traces)} steps."
    )


def _trace_sections(traces: Sequence[Trace], redactor: Redactor) -> list[Section]:
    """`## Traces`' whole body: the preamble, one summary row per root, the
    sentence saying how much of it is drawn, then one detail block and one
    sequence diagram per root, in `roots`' own fixed order (NFR-1).

    The summary table then one block per row, in table order, is the inbound
    endpoint section's shape reused deliberately (§13.5) — correlating a block
    back to its row needs no identity shared between them, only the order.

    **Every trace is in the summary and every trace is drawn.** A `Detail`
    column says so per row, and no trace is ever dropped: the second cardinal
    sin is under-reporting, and a root that vanished from this table would be a
    walk the document denies. `render --brief` once drew a prefix of this
    section and was deleted rather than repaired (GUIDELINES §8.4's audit list),
    because taking the first N traces in table order is an arbitrary cut
    presented as a reduced document, and which traces are worth keeping is not
    a judgement this renderer can make.
    """
    if not traces:
        return [MachineParagraph(_runs("None found."))]
    sections: list[Section] = [MachineList(tuple(_runs(line) for line in _TRACE_PREAMBLE))]
    summary = tuple(
        (
            _root_addresses(trace.root, redactor),
            _code(bare_descriptor(trace.root.handler)),
            _text(str(trace.root.kind)),
            _text(str(trace.depth)),
            _text(str(len(trace.steps))),
            _text(str(len(trace.terminals))),
            _text("below"),
        )
        for trace in traces
    )
    sections.append(MachineTable(_TRACE_HEADERS, summary))
    sections.append(MachineParagraph(_runs(_traces_drawn_sentence(traces))))
    for trace in traces:
        sections.append(_trace_detail(trace, redactor))
        participants, messages = _sequence_view(trace)
        sections.append(
            MachineDiagram(
                sequence_diagram(participants, messages).rstrip("\n"),
                elides=_trace_elision(trace),
            )
        )
    return sections


_NO_WIRE_ADDRESS = "no wire address"


def _root_addresses(root: Root, redactor: Redactor) -> tuple[Run, ...]:
    """Every wire address that reaches `root`, as one cell — joined, because
    several addresses are several ways to the SAME walk and printing the first
    would publish a coin toss (`_returns_cell`'s rule, one table on).

    **Read off the root, never joined here.** `roots` carries the address on
    its own row (2Q close, defect 1) precisely so this file does not have to
    re-make a join against `endpoints`: `egress` reads and renders, and a join
    performed in presentation is a derivation hiding in it, which the
    "Egress is read-only" contract exists to forbid.

    A root with no address renders the absence in words rather than an em
    dash. The dash means "nothing recorded" everywhere else in this document,
    and a scheduled job's missing address is not a value that went unread.
    """
    if not root.identities:
        return _text(_NO_WIRE_ADDRESS)
    return _code(
        "; ".join(
            _wire_address(identity.protocol, identity.method, identity.path, redactor)
            for identity in root.identities
        )
    )


def _trace_detail(trace: Trace, redactor: Redactor) -> MachineDetail:
    """One root's block: its own header, the step table, and what the root
    method returns.

    The header names the root by its HANDLER, its kind and every address that
    reaches it — the last so that a reader who knows only a URL can find the
    block, which is the whole reason `roots` carries the address. A root is
    still a METHOD: a handler serving three paths is one root, one walk and one
    block listing three addresses, never three copies of one answer.
    """
    header = DetailEntry(
        _code(bare_descriptor(trace.root.handler))
        + _text(f" — {trace.root.kind}, reached by ")
        + _root_addresses(trace.root, redactor),
        None,
        None,
    )
    entries = [header]
    if trace.steps:
        entries.append(DetailEntry(_text("Steps"), None, _trace_step_table(trace, redactor)))
    else:
        # A root whose body calls nothing is an answer, not an omission —
        # `/admin/refreshToken` on `mall-admin` is pure string work — so it
        # says so rather than showing an empty table.
        entries.append(DetailEntry(_text("Steps"), _text("None — this root calls nothing."), None))
    entries.append(
        DetailEntry(_text("Response"), _text(_returns_cell(trace.response, redactor)), None)
    )
    return MachineDetail(tuple(entries))


def _reaches_cell(step: Step) -> str:
    """What one step's call REACHES (D00 §4's `terminal_kind`, F7 §8.2, W30).

    `persistence (database)` where the sub-field says which store, `persistence` alone
    where a rule named a kind and no target. A step that is not a terminal shows nothing —
    the walk expanded it, so there is nothing to reach — and one no catalog claimed shows
    `unresolved`, which says it was examined.

    Composed here rather than derived here: both values arrive on the row (D01 §3), and
    inventing the classification in the renderer would be derivation hiding in
    presentation, which the import-linter contract forbids.
    """
    if step.terminal_kind is None:
        return _NONE_RECORDED
    if step.target_kind is None:
        return step.terminal_kind
    return f"{step.terminal_kind} ({step.target_kind})"


def _trace_step_table(trace: Trace, redactor: Redactor) -> MachineTable:
    """Every step of one trace, one row each, in the walk's order — never a
    filtered or collapsed subset. A step the renderer dropped would be a call
    the document denies, which is the under-report FR-17 exists to prevent."""
    rows = tuple(
        (
            _text(str(step.depth)),
            _code(_short_handler(bare_descriptor(step.caller))),
            _call_cell(step),
            _text(step.invoke_kind),
            _text(str(step.resolution)),
            _text(_NONE_RECORDED if step.result is None else str(step.result)),
            _text(_returns_cell(step.returns, redactor)),
            _text(_NONE_RECORDED if step.stop is None else str(step.stop)),
            _text(_reaches_cell(step)),
        )
        for step in trace.steps
    )
    return MachineTable(_TRACE_STEP_HEADERS, rows)


def _call_cell(step: Step) -> tuple[Run, ...]:
    """The `Call` column: what the compiler WROTE at that line, and — where
    dispatch resolved it into a different body — that body after an arrow.

    Both, never one. The bare `target` is the declaration a reader finds in
    the source; the `callee` is what the walk went on to expand, and an
    interface call showing only the implementation would hide that the source
    names an interface (`OmsOrderService#list → OmsOrderServiceImpl#list` is
    the shape). Where the two are the same descriptor, or where the callee is
    NULL because no body was read, the target alone IS the whole answer.

    Full descriptors, not `_short_handler`'s spelling: this column is where a
    reader tells `com/macro/mall/dao/OmsOrderDao#getList` from a runtime
    library's own unboxing call, and a sibling build module's
    `com/macro/mall/common/api/CommonResult#success` from either. The package
    IS the entire distinction — nothing here classifies a terminal — so
    shortening this column would delete the only evidence a reader has. The
    `Caller` column shortens because a caller is always a method in this
    module, already named elsewhere in the document."""
    # `G-52`: a throw whose type the extractor could not read has NO target — there is
    # no method, and the thrown type lives in a try-catch table nothing reads yet. Said
    # in words rather than rendered as a symbol: `_code(None)` would put the string
    # `None` into the document, a method nobody wrote and a name that matches nothing.
    if step.target is None:
        return _text("throws (type unread)")
    if step.callee is None:
        return _code(step.target)
    callee = bare_descriptor(step.callee)
    if callee == step.target:
        return _code(step.target)
    return _code(step.target) + _text(" → ") + _code(callee)


def _returns_cell(returns: Sequence[tuple[int, str]], redactor: Redactor) -> str:
    """What a method hands back, as one cell: every recorded return, joined —
    because several returns are several POSSIBLE answers and no single one,
    and printing the first would publish a coin toss.

    An empty tuple is the em dash, which here means one of three things the
    walk deliberately does not tell apart: the callee returns nothing, its body
    was not read, or the site is a `dynamic` one whose `result` is the lambda
    instance rather than anything a body returned. All three are "nothing was
    recorded", which is what `_NONE_RECORDED` says everywhere else in this
    document."""
    if not returns:
        return _NONE_RECORDED
    return "; ".join(_returned_value(json.loads(value), redactor) for _ordinal, value in returns)


def _returned_value(value: object, redactor: Redactor) -> str:
    """One entry of D00 §5's argument grammar as one short string.

    **Presentation of a closed grammar, not interpretation of it.** Every key
    the grammar defines is printed if the entry carries it — the kind, the
    symbol it names, the literal it is, the value id it came from, the
    elements of an array — and an entry whose kind this function has never
    heard of still prints that kind rather than vanishing. There is no branch
    here that decides an entry means something other than what it says.

    A JSON `null` (as opposed to `{"kind": "null"}`) is the VOID return, which
    is the one distinction `method_returns` keeps deliberately: a method that
    returns nothing said something, and a method whose return value could not
    be named said something else (`{"kind": "unresolved"}`).

    A string literal passes the redactor. Nothing else in this document
    renders a value rather than a name, and a hard-coded credential returned
    from a method is exactly the exposure `_wire_identity` already masks in a
    path."""
    if value is None:
        return "void"
    if not isinstance(value, dict):
        # Not a shape the grammar can produce. Printed rather than dropped:
        # a fact this renderer cannot read is a gap a reader must see.
        return f"unreadable {json.dumps(value)}"
    parts = [str(value.get("kind", "unreadable"))]
    symbol = value.get("symbol")
    if symbol is not None:
        parts.append(f"`{symbol}`")
    literal = value.get("value")
    if literal is not None:
        rendered = json.dumps(literal)
        parts.append(redactor.redact_text(rendered) if isinstance(literal, str) else rendered)
    elements = value.get("elements")
    if elements is not None:
        # An empty list is a ZERO-LENGTH varargs call, which is a real call
        # rather than a failure to read one (capability 9.15) — so `[]` is
        # printed, not skipped.
        inner = ", ".join(_returned_value(element, redactor) for element in elements)
        parts.append(f"[{inner}]")
    source = value.get("source")
    if source is not None:
        parts.append(f"value {source}")
    return " ".join(parts)


def _sequence_view(
    trace: Trace,
) -> tuple[list[SequenceParticipant], list[SequenceMessage | SequenceAlternatives]]:
    """One trace as participants and messages — the projection, where every
    decision about the diagram is made (M07 "The renderer adds nothing").

    A participant is the OWNING TYPE of a method, not the method: a sequence
    diagram's lifeline is the thing that holds state and receives calls, and a
    lifeline per method would draw `OmsOrderServiceImpl` four times over on
    `/order/list` alone. First-appearance order, root first, then each step's
    caller before its target — the walk's own order, so the diagram and the
    step table are the same sequence read two ways (NFR-1).

    **An arrow ends at the body the walk EXPANDED, not at the type the
    compiler named** — the `callee`, falling back to the `target` where no
    body was read. The two differ exactly where dispatch resolved an
    interface call into its implementation, and drawing the interface there
    breaks the diagram outright: on `/order/list` the arrow would land on
    `OmsOrderService`, and `OmsOrderServiceImpl` would then send four
    messages nobody ever sent it — a lifeline appearing from nowhere, which
    is a diagram a reader cannot follow. The declared type is not lost: the
    message label names it (`_message_label`), and the step table's `Call`
    column carries both descriptors in full.
    """
    participants: dict[str, str] = {}

    def _participant(descriptor: str) -> str:
        owner = owner_of(descriptor)
        # A descriptor with no owner is a free function — it has no type to
        # draw, so it is its own lifeline, keyed by the whole descriptor so
        # two of them can never merge.
        key = descriptor if owner is None else owner
        if key not in participants:
            participants[key] = f"a{len(participants)}"
        return participants[key]

    # The root's own lifeline first, before any step: a root whose body calls
    # nothing still draws as itself rather than as an empty diagram, and the
    # leftmost lifeline is always the thing that starts the work.
    _participant(bare_descriptor(trace.root.handler))

    def _message(step: Step) -> SequenceMessage:
        return SequenceMessage(
            source=_participant(bare_descriptor(step.caller)),
            target=_participant(_reached(step)),
            label=_message_label(step),
        )

    messages = _grouped(list(trace.steps), _message)
    labels = _sequence_labels(participants)
    messages = _named(messages, labels)
    drawn = [
        SequenceParticipant(identifier, labels[identifier]) for identifier in participants.values()
    ]
    return drawn, messages


def _named(
    messages: list["SequenceMessage | SequenceAlternatives"], labels: dict[str, str]
) -> list["SequenceMessage | SequenceAlternatives"]:
    """Every alternatives branch's participant ID replaced by that lifeline's display
    label — a second pass because the labels are not known until every participant has
    been seen (`_sequence_labels` disambiguates a colliding simple name against the whole
    set)."""
    return [
        message
        if isinstance(message, SequenceMessage)
        else SequenceAlternatives(
            branches=tuple(
                SequenceBranch(
                    label=labels[branch.label],
                    messages=tuple(_named(list(branch.messages), labels)),
                )
                for branch in message.branches
            )
        )
        for message in messages
    ]


def _grouped(
    steps: list[Step], message: Callable[[Step], SequenceMessage]
) -> list[SequenceMessage | SequenceAlternatives]:
    """`steps` as messages, with each NARROWED call site's candidates folded into one
    alternatives block (F7 §8.3, W32).

    **Why this is not cosmetic.** A `narrowed` site is several candidate bodies with none
    picked, and the walk records one step per candidate followed by that candidate's whole
    subtree. Drawn flat they read as a sequence — `spring-petclinic-rest`'s
    `ClinicServiceImpl#saveOwner` draws `save` to the JDBC repository and, eight arrows
    later, `save` to the JPA one, so the diagram says the service saves twice when at most
    one repository answers the call. 34 such sites in that corpus's `call_edges`, of which
    **31 are reached by a trace** and therefore appear in the document — the other three
    are in the graph and in no walk, and this sentence used to weld the two numbers
    together.

    **The ranges are already contiguous, which is what makes this possible.** The walk is
    depth-first, so a candidate is immediately followed by everything it leads to and then
    by the next candidate: a branch is the candidate's own step plus every following step
    DEEPER than it. Nothing is reordered and nothing is dropped — the same messages come
    out in the same order, inside a block that says what they are.

    A group is keyed on `(caller, ordinal)`, which is the call SITE (D00 §5), and only a
    site whose steps are `narrowed` groups: two steps sharing an ordinal is exactly the
    shape dispatch produces when it could not pick, and one step is an ordinary call
    however it resolved.
    """
    drawn: list[SequenceMessage | SequenceAlternatives] = []
    index = 0
    while index < len(steps):
        step = steps[index]
        span = _candidate_span(steps, index)
        if span is None:
            drawn.append(message(step))
            index += 1
            continue
        branches: list[SequenceBranch] = []
        for start, end in span:
            first = message(steps[start])
            branches.append(
                SequenceBranch(
                    # The participant ID this branch's own first arrow points at, resolved
                    # to a display name by `_named` once `_sequence_labels` has decided
                    # what every lifeline is called. Taken from the message rather than
                    # spelled again here: the branch names exactly the thing its arrow
                    # lands on, and two rules for one name would let a colliding simple
                    # name be disambiguated on the lifeline and stay ambiguous in the
                    # branch that names it.
                    label=first.target,
                    messages=(first, *_grouped(steps[start + 1 : end], message)),
                )
            )
        drawn.append(SequenceAlternatives(branches=tuple(branches)))
        index = span[-1][1]
    return drawn


def _candidate_span(steps: list[Step], index: int) -> list[tuple[int, int]] | None:
    """The `(start, end)` range of each candidate of the NARROWED site beginning at
    `index`, or None where that step is not one.

    A candidate's range runs to the next step at its own depth or shallower, which is
    where its subtree ends — the walk being depth-first is the whole of why that holds.

    **The `depth` equality below is defensive and currently unreachable**, stated rather
    than left as a clause a reader assumes is load-bearing: `_walk` expands a method once
    per trace (`expanded`), so every step naming one caller comes from that caller's
    single frame and shares its depth. Removing the check changes no output and fails no
    test. It stays for the reason the `len(spans) > 1` guard stays — the invariant is the
    walk's, not this function's — and it is the `caller`/`ordinal` equality that does the
    real work, which `test_two_narrowed_sites_in_one_caller_are_two_blocks` pins against a
    live shape.
    """
    first = steps[index]
    if first.resolution != Resolution.NARROWED:
        return None
    spans: list[tuple[int, int]] = []
    cursor = index
    while (
        cursor < len(steps)
        and steps[cursor].resolution == Resolution.NARROWED
        and (steps[cursor].caller, steps[cursor].ordinal) == (first.caller, first.ordinal)
        and steps[cursor].depth == first.depth
    ):
        end = cursor + 1
        while end < len(steps) and steps[end].depth > first.depth:
            end += 1
        spans.append((cursor, end))
        cursor = end
    # One candidate is not an alternative to anything: a `narrowed` row can stand alone
    # where dispatch found exactly one body but could not commit to it, and a one-branch
    # `alt` would tell a reader there is a choice where there is none.
    return spans if len(spans) > 1 else None


def _sequence_labels(participants: dict[str, str]) -> dict[str, str]:
    """Each participant id's display label: the owning type's simple name, or
    — for every member of a group whose simple names COLLIDE — the full
    descriptor with its type marker stripped.

    `_disambiguated_shape_names`' rule, applied per diagram (§13.5). Two
    distinct types reading as one lifeline label is not cosmetic: a diagram
    showing `Order` twice, or worse showing `com/a/Order` and `com/b/Order`
    under one name a reader assumes is one type, asserts a call between things
    that never touched. The fallback goes all the way to the key this dict is
    built on, which is unique by construction."""
    by_simple: dict[str, list[str]] = {}
    for key in participants:
        by_simple.setdefault(simple_name(key), []).append(key)
    labels: dict[str, str] = {}
    for name, colliding in by_simple.items():
        for key in colliding:
            labels[participants[key]] = name if len(colliding) == 1 else without_type_marker(key)
    return labels


def _reached(step: Step) -> str:
    """The BARE descriptor of the body this step reaches — the `callee` where
    the walk read one, the `target` the compiler wrote where it did not.

    One function, because the diagram's arrow and the diagram's participant
    list must agree about it: computed twice, a lifeline could be registered
    for one descriptor and addressed by another, and mermaid would silently
    draw an extra actor rather than fail.

    A `throw` whose type was unread (`G-52`) has neither: the arrow lands on the
    method that exits, drawn as a self-arrow — the `(dynamic)` precedent — because a
    lifeline is a type that holds state and receives calls, and a type nobody named
    is not one."""
    if step.target is None:
        return bare_descriptor(step.caller)
    return step.target if step.callee is None else bare_descriptor(step.callee)


def _message_label(step: Step) -> str:
    """One arrow's whole text: the method called, where it was DECLARED if
    that is not where it landed, and then what the walk did about it.

    `(declared X)` is what keeps the arrow honest after it was redirected to
    the implementing body: the source says `orderService.list(...)` and a
    diagram silently naming `OmsOrderServiceImpl` would be a claim about
    dispatch presented as a claim about the code. Named by simple name only —
    the step table's `Call` column carries both descriptors in full, and a
    package path inside an arrow label is unreadable.

    `(dynamic)` is not decoration either. An `invokedynamic` step names the
    body the site CREATES, and the lambda runs later, elsewhere, if at all —
    an arrow reading like an ordinary call there is the one place this diagram
    could assert something the graph does not say.

    `[stop]` marks a lifeline the walk did not enter, which is where the trace
    ends on that branch; a step with no stop was expanded, and its own calls
    follow.

    `throw` is the whole verb on a throw step (`G-52`). Its target is the thrown
    TYPE and names no method, so `method_name` of it is empty — measured, the arrow
    to `UninitializedMessageException` read `a2->>a7:  [boundary]`, a lifeline entered
    by nothing a reader could name. The lifeline is the exception type, which is right:
    the method leaves through it."""
    if step.invoke_kind == "throw":
        label = "throw" if step.target is not None else "throw (type unread)"
        return label if step.stop is None else f"{label} [{step.stop}]"
    # Only a throw step may lack a target (`query/trace.py`'s `Step`), and it returned.
    target = step.target or ""
    label = method_name(target)
    declared = owner_of(target)
    landed = owner_of(_reached(step))
    if declared is not None and landed != declared:
        label = f"{label} (declared {simple_name(declared)})"
    if step.invoke_kind == "dynamic":
        label = f"{label} (dynamic)"
    if step.stop is not None:
        label = f"{label} [{step.stop}]"
    return label


def _alternative_sites(trace: Trace) -> int:
    """How many call sites in this trace narrowed to SEVERAL bodies (F7 §8.3, W32).

    One per site, not per candidate: two candidates on one site is one choice a reader
    has to make, and counting the arrows would say two.
    """
    sites: set[tuple[str, int]] = set()
    counted: dict[tuple[str, int], int] = {}
    for step in trace.steps:
        if step.resolution != Resolution.NARROWED:
            continue
        key = (step.caller, step.ordinal)
        counted[key] = counted.get(key, 0) + 1
        if counted[key] > 1:
            sites.add(key)
    return len(sites)


def _trace_elision(trace: Trace) -> str:
    """What this trace's diagram leaves out, counted from the trace itself.

    Every step IS drawn — there is no cap and no filter, so the count is not
    the elision. What the diagram elides is what the WALK did not enter, and
    the counts say how much of each: a diagram whose arrows all end at
    lifelines nobody opened looks like a complete picture of a shallow system,
    and it is a complete picture of where we stopped looking.

    Zero-count clauses are omitted rather than printed as `0`, and the
    ordering is fixed, so the sentence is a function of the trace alone
    (NFR-1). Each count is phrased as a noun and a number rather than as a
    subject and a verb, so no clause has to agree with a count nobody can
    predict — the mistake `_stale_sentence` fixes with a plural `s` and this
    would need four of."""
    stops = {stop: 0 for stop in TraceStop}
    for step in trace.steps:
        if step.stop is not None:
            stops[step.stop] += 1
    # F7 §8.3 (W32). Counted from the steps rather than from the built diagram, so this
    # sentence and the arrows cannot disagree about how many choices there are.
    alternatives = _alternative_sites(trace)
    drawn = (
        "This root calls nothing, so the diagram is its own lifeline and no arrow at all."
        if not trace.steps
        else (
            f"All {len(trace.steps)} step{'' if len(trace.steps) == 1 else 's'} of this "
            f"trace {'is' if len(trace.steps) == 1 else 'are'} drawn, and none is dropped"
            + (
                "."
                if not alternatives
                else (
                    f" — but {alternatives} call site{'' if alternatives == 1 else 's'} "
                    f"here dispatch{'es' if alternatives == 1 else ''} to SEVERAL bodies "
                    "with none picked, and each is drawn as an `alt` block: exactly one "
                    "branch of each runs, never all of them, and which one is a runtime "
                    "question this analysis does not answer."
                )
            )
        )
    )
    parts = [
        (
            "Reachability, not execution: an arrow is a call the compiler recorded, not "
            "one observed to run, and branches are not distinguished — no order here is "
            "claimed to have happened."
        ),
        drawn,
    ]
    if stops[TraceStop.BOUNDARY]:
        parts.append(
            "Arrows ending at a lifeline this workspace read no body for — a library, the "
            "JDK, a mapper or a sibling build module alike — which the walk did not "
            f"enter: {stops[TraceStop.BOUNDARY]}."
        )
    if stops[TraceStop.REVISITED]:
        parts.append(
            "Arrows naming a method already expanded earlier in this trace, whose own "
            f"calls are drawn at that first arrow and not repeated here: "
            f"{stops[TraceStop.REVISITED]}."
        )
    if stops[TraceStop.CYCLE]:
        parts.append(
            "Arrows whose callee is already on the path from the root — recursion, stated "
            f"and not followed: {stops[TraceStop.CYCLE]}."
        )
    return " ".join(parts)


def _understanding_items(coverage: dict[str, object]) -> list[tuple[Run, ...]]:
    """FR-17 clause 3 (F8 §9.5, W38): how much of the call graph was UNDERSTOOD, beside how
    many files were opened.

    **`reach` leads and `resolution` follows, because the second alone misleads.**
    `resolution` says whether dispatch settled a call, and it reads 100% `resolved` on two
    of the four measured corpora — naming the target a compiler wrote is easy, and reading
    its BODY is the work. A reader shown only that would take a blind analysis for a
    complete one, which is the corpus blindness this line exists to instrument.

    Absent where there is no call graph at all, rather than printed as `0 of 0`: a module
    with no edges has nothing to be understood, and a percentage of nothing reads as a
    failure (NFR-7's "looked and found nothing" is for things that were looked FOR).
    """
    reach = coverage.get("reach")
    if not isinstance(reach, dict) or not reach:
        return []
    read = int(reach.get("body_read", 0))
    total = read + int(reach.get("boundary", 0))
    if total == 0:
        return []
    items = [
        _runs(
            f"Calls whose callee body this workspace read: {read} of {total} "
            f"({round(100 * read / total)}%). The rest end at a boundary — a library, the "
            "platform, a sibling module — which is what was measured, not what exists."
        )
    ]
    for key, unit, lead in (
        ("resolution", "call edges", "Dispatch"),
        ("method_resolution", "methods", "Method lookup"),
    ):
        distribution = coverage.get(key)
        if isinstance(distribution, dict) and distribution:
            counted = ", ".join(f"{name} {count}" for name, count in sorted(distribution.items()))
            items.append(_runs(f"{lead}, by outcome ({unit}): {counted}."))
    return items


def _config_coverage_items(
    resolved_config: Sequence[dict[str, object]],
) -> list[tuple[Run, ...]]:
    """Coverage's own view of pass 2 (2F design §2): which profiles resolved,
    and which declared keys did not — named with their reason and
    environment, never just counted, so a reader can act on the same row
    `resolved_config` itself carries (spec §5). An empty answer is stated,
    never a section that silently has nothing to say (NFR-7). Items, not
    lines: the bullet's own leading `- ` is `MachineList`'s job now."""
    environments = list(dict.fromkeys(str(row["environment"]) for row in resolved_config))
    if environments:
        rendered = ", ".join(f"`{e}`" for e in environments)
        items = [_runs(f"Environments resolved: {rendered}.")]
    else:
        items = [_runs("Environments resolved: none.")]
    unresolved = [row for row in resolved_config if row.get("value") is None]
    if not unresolved:
        items.append(_runs("Configuration keys unresolved: none."))
        return items
    for row in unresolved:
        items.append(
            _runs(
                f"Configuration key unresolved: {row['key']} — "
                f"{row['unresolved_reason']} in {row['environment']}."
            )
        )
    return items


def _unresolved_derivation_items(endpoints: Sequence[dict[str, object]]) -> list[tuple[Run, ...]]:
    """Every endpoint row a catalog derived but could not address (`path`
    NULL, `resolution: unresolved`) — named by the catalog that derived it
    and the site it read, since neither is visible from the wire-identity
    tables below. Covers every `config_join` row this way (I-1, Task 7
    review): a missing binding key derives with `handler` set (the bean
    method exists) and no key to name, since the key was never declared in
    any file and so carries no `resolved_config` row of its own; a composed
    `pipeA|pipeB` selection names no single bean at all, and the composed
    expression itself is not a column any row carries — there is no
    engine-to-report channel, so it renders as what it is, not what it said.
    The same filter also catches an unresolved row from any OTHER engine
    (a computed base address, Task 8 D-4): the row carries no marker naming
    its deriving STYLE, only its catalog, so this is deliberately a superset
    rather than a filter this data cannot make honestly — and the lead-in
    line below says so on the page itself, not only in this docstring."""
    rows = [e for e in endpoints if e.get("path") is None and e.get("resolution") == "unresolved"]
    items = [
        _runs(
            "Unresolved endpoint derivations — across every engine, whatever "
            "their evidence, not configuration alone:"
        )
    ]
    if not rows:
        items.append(_runs("None."))
        return items
    for row in rows:
        catalog_id = row.get("catalog_id")
        catalog = "unresolved" if catalog_id is None else str(catalog_id)
        handler = row.get("handler")
        caller = row.get("caller")
        if handler is not None:
            site = f"handler `{bare_descriptor(str(handler))}`"
        elif caller is not None:
            site = f"caller `{bare_descriptor(str(caller))}`"
        else:
            site = "a composed selection expression"
        items.append(_runs(f"Unresolved endpoint derivation: `{catalog}` — {site}."))
    return items


def _fields_by_shape(
    shape_fields: Sequence[dict[str, object]],
) -> dict[str, list[dict[str, object]]]:
    """`shape_fields` grouped by owning shape, in the ordinal order the
    `shape_fields` query already fixed (NFR-1)."""
    grouped: dict[str, list[dict[str, object]]] = {}
    for field in shape_fields:
        grouped.setdefault(str(field["shape_id"]), []).append(field)
    return grouped


def _contract_nodes(
    shapes: list[dict[str, object]],
    shape_fields: Sequence[dict[str, object]],
    hierarchy: Sequence[dict[str, object]] = (),
) -> tuple[list[ClassNode], list[ClassEdge]]:
    """`shapes`/`shape_fields` projected into the view model the emitter draws
    (M07 "Structure — contract class diagram"): one node per shape with its
    own wire fields, one edge per field whose `item` descriptor points at
    another shape, and — since W33 — one INHERITANCE edge per ancestor that
    explains where a contract came from (F7 §8.4).

    **Which ancestors earn an arrow, measured.** Not all of them: `type_hierarchy` holds
    every supertype, and drawing every one buries the diagram in noise that says nothing
    about the wire. On `mall-admin` 30 of the 34 shape ancestors are one marker interface;
    on this repo's fixture four are a protobuf runtime base and four are generated builder
    interfaces. So the rule is what the ancestor CONTRIBUTES:

    * a **scanned** ancestor that is itself a shape here — its fields were inlined into
      this shape's own list (the field pass walks the ancestry), so the arrow is what
      explains their presence;
    * an **unscanned SUPERCLASS of a shape that is itself `open`** — it may declare fields
      nobody read, which is exactly why the subtype is open, and the arrow plus an
      `<<open>>` node is where a reader is told the rest of the contract lives;
    * nothing else. An **unscanned interface** cannot hold instance fields (an interface's
      own fields are constants), so it explains no part of the payload, and a scanned
      ancestor that contributed nothing has nothing to explain either.

    An unscanned superclass gets a node of its own, with no fields and `<<open>>` — D02's
    stereotype means "the expansion stopped here", which is exactly what it is.

    **Reading the shape's own `open` flag is what keeps the two halves of the diagram from
    contradicting each other.** A type whose contract comes from a SCHEMA takes nothing
    from its class file, so it is closed however exotic its generated superclass is — every
    protobuf message extends the runtime's unscanned `GeneratedMessage`, and drawing that
    arrow put four `<<open>>` boxes above four shapes the `.proto` describes completely.
    Deciding it from the flag rather than re-deriving the reason means the arrow and the
    stereotype can never disagree.

    **A scanned ancestor that is NOT itself a shape gets no arrow**, and that is a stated
    boundary rather than an oversight. `mall-admin`'s `dto/OmsOrderDetail extends
    model/OmsOrder` is the case: the parent's 45 fields are IN the child's own list, since
    the field pass walks the ancestry, so the contract on the diagram is complete and an
    arrow would point at an empty box. JSON has no inheritance; the flattening is what the
    wire really carries, and this diagram draws the wire.
    """
    grouped = _fields_by_shape(shape_fields)
    described = {str(shape["shape_id"]) for shape in shapes}
    ancestors = _ancestors_by_child(hierarchy)
    nodes: list[ClassNode] = []
    edges: list[ClassEdge] = []
    opened: list[str] = []
    for shape in shapes:
        shape_id = str(shape["shape_id"])
        rows = grouped.get(shape_id, [])
        fields = tuple((str(row["wire_name"]), str(row["wire_type"])) for row in rows)
        nodes.append(ClassNode(shape_id, fields, bool(shape["open"])))
        for row in rows:
            item = row.get("item")
            if not item:
                continue
            target = json.loads(str(item)).get("shape_id")
            if target:
                edges.append(ClassEdge(shape_id, str(target)))
        # A parameterised shape id names a type plus its bound arguments; the hierarchy is
        # keyed on the type alone, exactly as the field and accessor passes key it.
        for ancestor, kind, scanned in ancestors.get(_unparameterised(shape_id), ()):
            drawn_as = _described_as(ancestor, shape_id, described)
            if scanned and drawn_as is not None:
                edges.append(ClassEdge(shape_id, drawn_as, kind))
            elif not scanned and kind == "extends" and bool(shape["open"]):
                edges.append(ClassEdge(shape_id, ancestor, kind))
                if ancestor not in described and ancestor not in opened:
                    opened.append(ancestor)
    # After every shape's own node, so a reader meets the module's types first and the
    # boundary they stop at second. `open=True` and no fields is the whole of what is
    # known about one.
    nodes.extend(ClassNode(ancestor, (), True) for ancestor in opened)
    return nodes, edges


def _described_as(ancestor: str, child: str, described: set[str]) -> str | None:
    """Which shape id in the diagram IS this ancestor, or None where none is.

    The hierarchy names a TYPE (`a/Slice#`) and a shape id names a type plus its bound
    arguments (`a/Slice#<a/OrderView#>`), so a plain membership test misses every
    parameterised contract — and `Page<T>`/`Slice<T>` is precisely the case W33 cites as
    the reason its `<|..` rule ships at all. Measured against the shipped projection before
    this: `Page#<OrderView#> implements Slice#` drew zero edges with both shapes described.

    **The child's own binding is preferred**, because a generic type that extends another
    usually passes its parameter straight through — `Page<T> extends Slice<T>` — so
    `Page#<OrderView#>`'s ancestor is `Slice#<OrderView#>` and not some other `Slice`.
    Where that exact binding is not described, the BARE ancestor is used if it is; where
    the ancestor is described only under bindings that are not the child's, there is no
    edge, because the erased hierarchy fact does not say which of them this child extends
    and drawing a guess would be a claim about the source.
    """
    if ancestor in described:
        return ancestor
    arguments = child[len(_unparameterised(child)) :]
    if arguments and (bound := ancestor + arguments) in described:
        return bound
    return None


def _unparameterised(shape_id: str) -> str:
    """A shape id with its bound type arguments dropped — `CommonResult#<OrderView#>`
    becomes `CommonResult#`. The hierarchy is keyed on the TYPE, which is what declares a
    supertype; the binding belongs to the reference."""
    return shape_id.split("<", 1)[0]


def _ancestors_by_child(
    hierarchy: Sequence[dict[str, object]],
) -> dict[str, list[tuple[str, str, bool]]]:
    """`type_hierarchy` rows as `child -> [(ancestor, kind, scanned)]`, in the table's own
    `position` order so two runs draw one order (NFR-1)."""
    found: dict[str, list[tuple[str, str, bool]]] = {}
    for row in hierarchy:
        found.setdefault(str(row["child"]), []).append(
            (str(row["ancestor"]), str(row["kind"]), bool(row["scanned"]))
        )
    return found


def _inline_descriptor(descriptor: dict[str, object]) -> str:
    """The payload label for a descriptor with no shape at its own level —
    a scalar, or a collection of one — since there is no shape to tabulate
    (`array of object OrderView`, `string`)."""
    wire_type = str(descriptor.get("wire_type"))
    shape_id = descriptor.get("shape_id")
    if shape_id:
        return f"{wire_type} {simple_name(str(shape_id))}"
    item = descriptor.get("item")
    if isinstance(item, dict):
        return f"{wire_type} of {_inline_descriptor(item)}"
    return wire_type


_SHAPE_FIELD_HEADERS = ("Field", "Type", "Required", "Nullable")

# `Response: none recorded` (2M design §5c): a shape whose OWN fields query
# came back empty renders one line, never a table with a header row and no
# body — the `## Coverage`/`## Known gaps` NFR-7 discipline this document
# keeps everywhere else, extended to a shape table specifically because a
# header-only `| Field | Type | Required | Nullable |` with nothing under it
# is indistinguishable, at a glance, from a table a reader just has not
# scrolled far enough to see the rows of.
_SHAPE_NONE_RECORDED = "none recorded"


def _shape_fields_table(rows: Sequence[dict[str, object]]) -> MachineTable:
    """A shape's OWN field table — `_SHAPE_FIELD_HEADERS` beside one row per
    `shape_fields` entry — factored out of `_descriptor_entry` so it can be
    built exactly once per shape (`_named_shape_reference`) rather than once
    per endpoint that happens to reference the same shape (2M design §5c,
    "each shape's table emitted exactly once")."""
    table_rows = []
    for row in rows:
        # The schema's own field number (protobuf), shown the same
        # unobtrusive way `wire_format` already rides beside `wire_type` —
        # NULL for Avro and every annotation-derived field, which render
        # unchanged (2G design §8, Task 5).
        field_number = row.get("field_number")
        wire_name = (
            f"{row['wire_name']} ({field_number})"
            if field_number is not None
            else str(row["wire_name"])
        )
        wire_format = row.get("wire_format")
        field_type = f"{row['wire_type']} ({wire_format})" if wire_format else str(row["wire_type"])
        required = "yes" if row["required"] else "no"
        nullable = "yes" if row["nullable"] else "no"
        table_rows.append((_text(wire_name), _text(field_type), _text(required), _text(nullable)))
    return MachineTable(_SHAPE_FIELD_HEADERS, tuple(table_rows))


_ANCHOR_UNSAFE = re.compile(r"[^A-Za-z0-9_-]+")


def _shape_anchor_id(display_name: str) -> str:
    """The in-page HTML `id` a `### Shapes` entry's header carries, and a
    `shaperef` run's `<a href="#...">` targets — both built from the SAME
    already-FINAL display name (`_disambiguated_shape_names`), never
    re-derived independently at each end, so the two can never name two
    different anchors for one shape (2M design §5c). Every character an
    HTML id cannot safely carry — a QName's `{`/`}`, a disambiguated
    fallback's own `/` — is replaced with `-`, since a display name is no
    longer always a bare SCIP simple name once `#5c`'s per-shape
    disambiguation can fall back to something closer to the raw id.

    This sanitizing is lossy — a `.` and a `-` both collapse to the same
    `-` — so it is `_disambiguated_shape_names`' job, not this function's,
    to guarantee the mirror mistake (fix round 1, MEDIUM 2) never happens:
    that two DIFFERENT final names handed to this function never produce
    the same anchor, ACROSS EVERY shape in one document, not only within
    whichever group first collided (2M Task 7 fix round 1, High: the
    per-group fallback alone still let two names from DIFFERENT groups
    collide — `_globally_unique_anchors` is where that promise is actually
    kept). This function alone cannot promise it; it only sanitizes what it
    is given."""
    return f"shape-{_ANCHOR_UNSAFE.sub('-', display_name)}"


def _shape_display_name(shape_id: str) -> str:
    """One shape id's own display name, honestly — never blindly
    `simple_name`, which reads the last `/`-segment and assumes every shape
    id is a SCIP symbol. A SOAP element's shape id is a QName wire identity,
    `{uri}local` (D00 §4's own verbless-protocol shape), and the URI's own
    path segments make `simple_name` land mid-URI —
    `{http://orders.example.com/ws}quoteOrderRequest` reads back as
    `ws}quoteOrderRequest`, not `quoteOrderRequest` (fix round 1, LOW
    finding). A QName's own grammar says a local part is whatever follows
    the LAST `}`; an ordinary package-path shape id has none, and keeps
    `simple_name`'s existing convention exactly — trailing `#` stripped by
    `without_type_marker` on THIS branch too (2M Task 7 ride-along): nothing
    says a QName's local part can never carry the same SCIP type marker a
    package-path shape id does, and `without_type_marker` is a harmless
    no-op everywhere it does not. `domain.symbols.simple_name` itself is
    untouched — this is local to the two `### Shapes` call sites that are
    the first to ever display a shape id that might not be SCIP at all."""
    if "}" in shape_id:
        return without_type_marker(shape_id.rsplit("}", 1)[-1])
    return simple_name(shape_id)


def _disambiguated_shape_names(cited_shapes: dict[str, list[dict[str, object]]]) -> dict[str, str]:
    """Every cited shape id's FINAL display name: `_shape_display_name`
    ordinarily, or — within a group of shape ids whose OWN display names
    would sanitize to the SAME `_shape_anchor_id` — the shape id itself
    (trailing `#` stripped, otherwise verbatim) for every member of that
    group (fix round 1, MEDIUM 2). Two shapes reading as the same name is
    not a cosmetic near-miss: their `### Shapes` entries become
    indistinguishable and their citations' anchors collide (an invalid,
    duplicate HTML `id`, and a link that can no longer promise which table
    it lands on) — so a collision falls all the way back to something
    already guaranteed unique, the very key this dict (and `cited_shapes`)
    is built on, rather than a half-measure that only postpones the next
    collision.

    Grouped on the SANITIZED anchor id (`_shape_anchor_id` of the display
    name), not the display name's own bytes (2M Task 7 ride-along): two
    display names that read as different TEXT — `order.request` and
    `order-request` — still sanitize to the identical `order-request` once
    `_shape_anchor_id` collapses a `.` to the same `-` a literal `-` already
    is, so comparing the pre-sanitized strings let exactly this pair through
    uncaught. Comparing the anchor each would actually produce is the only
    check that matches what `_shape_anchor_id` itself promises never
    collides.

    Built in `cited_shapes`' own order (its first-seen citation order, the
    order `### Shapes` itself renders in) before the final pass below runs,
    so which shape wins a shared anchor bare is the one the document cites
    first — not an artifact of which dict this function happened to group
    things into internally.

    `_globally_unique_anchors` then runs ONCE, over every shape at once,
    because the per-group fallback above is not by itself enough (fix round
    1, High — the reviewer's proven counterexample): `p/q/A#` and `p/r/A#`
    collide on the simple name `A` and fall back to their own full ids,
    `p/q/A` and `p/r/A` — genuinely distinct from EACH OTHER — but a THIRD,
    unrelated shape `x/p-q-A#`, alone in its own group, keeps its unchanged
    display name `p-q-A`, whose anchor (`shape-p-q-A`) is the SAME one
    `p/q/A`'s fallback produces once `/` and `-` both sanitize to `-`. No
    per-group check ever compares those two names, because they were never
    in the same group — only a pass over the WHOLE finished set can."""
    display_names = {shape_id: _shape_display_name(shape_id) for shape_id in cited_shapes}
    by_anchor: dict[str, list[str]] = {}
    for shape_id, display in display_names.items():
        by_anchor.setdefault(_shape_anchor_id(display), []).append(shape_id)
    per_group: dict[str, str] = {}
    for colliding in by_anchor.values():
        if len(colliding) == 1:
            shape_id = colliding[0]
            per_group[shape_id] = display_names[shape_id]
        else:
            for shape_id in colliding:
                per_group[shape_id] = without_type_marker(shape_id)
    ordered = {shape_id: per_group[shape_id] for shape_id in cited_shapes}
    return _globally_unique_anchors(ordered)


def _globally_unique_anchors(names: dict[str, str]) -> dict[str, str]:
    """`names`, walked in order, with a positional ordinal (` (2)`, ` (3)`,
    ...) appended to any name whose `_shape_anchor_id` a PRIOR entry in this
    same walk already claimed (fix round 1, High — see
    `_disambiguated_shape_names`' own docstring for the counterexample this
    closes). The first shape to reach a given anchor keeps its name bare;
    every later one competing for the same anchor gets the next free
    ordinal — deterministic (NFR-1) because `names` itself is already
    ordered, and because a digit is a character `_shape_anchor_id` never
    touches, so appending one is guaranteed to change the anchor it
    produces.

    A churn hazard worth naming: appending a NEW shape earlier in citation
    order than an existing one that happens to share its anchor can shift
    which one keeps the bare name and which gets `(2)` — this walk has no
    memory of a PRIOR run's assignment, only of citation order within the
    CURRENT one."""
    claimed: set[str] = set()
    final: dict[str, str] = {}
    for shape_id, name in names.items():
        candidate = name
        anchor = _shape_anchor_id(candidate)
        ordinal = 2
        while anchor in claimed:
            candidate = f"{name} ({ordinal})"
            anchor = _shape_anchor_id(candidate)
            ordinal += 1
        claimed.add(anchor)
        final[shape_id] = candidate
    return final


def _cited_named_shapes(
    endpoints: Sequence[dict[str, object]],
    fields_by_shape: dict[str, list[dict[str, object]]],
) -> dict[str, list[dict[str, object]]]:
    """Every NAMED shape (a `request_shape`/`response_shape` descriptor
    carrying a `shape_id`) with recorded fields, cited by at least one of
    `endpoints`, keyed by shape id in FIRST-SEEN order — pass ONE of the two
    `### Shapes` needs (fix round 1, MEDIUM 2's own reasoning): the full set
    of cited shapes must be known before ANY citation can pick a (possibly
    disambiguated) display name, so nothing here builds an entry yet. An
    empty-fields shape (`Response: none recorded`, NFR-7) is deliberately
    excluded: nothing about it is ever named or linked."""
    cited: dict[str, list[dict[str, object]]] = {}
    for endpoint in endpoints:
        for key in ("request_shape", "response_shape"):
            descriptor_json = endpoint.get(key)
            if descriptor_json is None:
                continue
            shape_id = json.loads(str(descriptor_json)).get("shape_id")
            if not shape_id:
                continue
            shape_id = str(shape_id)
            rows = fields_by_shape.get(shape_id, [])
            if rows and shape_id not in cited:
                cited[shape_id] = rows
    return cited


def _descriptor_entry(
    label: str,
    descriptor_json: object,
    fields_by_shape: dict[str, list[dict[str, object]]],
    shape_names: dict[str, str],
) -> DetailEntry | None:
    """One endpoint's request or response, nested under its detail block's
    header entry: a citation of the shape's own `### Shapes` entry (by its
    FINAL, already-disambiguated `shape_names` entry) when the payload is
    itself a NAMED shape with recorded fields, the `Response: none recorded`
    one-liner for a shape with none (NFR-7), or an inline label when it is a
    scalar or a collection of one (anonymous — nothing to tabulate, so
    nothing to name or move). `None` (no descriptor) contributes nothing.
    `shape_names` is READ ONLY here — pass two of the two `### Shapes` needs,
    over the registry `_cited_named_shapes`/`_disambiguated_shape_names`
    already finished building from every inbound endpoint at once."""
    if descriptor_json is None:
        return None
    descriptor = json.loads(str(descriptor_json))
    shape_id = descriptor.get("shape_id")
    if not shape_id:
        return DetailEntry(_text(label), _text(_inline_descriptor(descriptor)), None)
    shape_id = str(shape_id)
    if not fields_by_shape.get(shape_id):
        return DetailEntry(_text(label), _text(_SHAPE_NONE_RECORDED), None)
    return DetailEntry(_text(label), _shape_ref(shape_names[shape_id]), None)


def _streaming_entry(descriptor_json: object) -> DetailEntry | None:
    """gRPC's `unary | server-streaming | client-streaming | bidi` (2O design
    §1a), when the descriptor carries one — a typed 2M Detail line, not a new
    `endpoints` column, `schema_operations.py`'s own ruling for exactly this
    reason. `_grpc_operation_row` writes the word under a `streaming` key
    beside `response_shape`'s own `shape_id`, a key no other schema format's
    descriptor ever carries, so a bare presence check is the whole rule:
    every non-gRPC row's `None` here is silence, not a gap."""
    if descriptor_json is None:
        return None
    streaming = json.loads(str(descriptor_json)).get("streaming")
    if streaming is None:
        return None
    return DetailEntry(_text("Streaming"), _text(str(streaming)), None)


@dataclass(frozen=True)
class _Anchors:
    """The indices into the assembled `sections` list that the four anchors of
    `domain/enrichment.Anchor` name (2K design §6; keyed on SECTION INDEX
    rather than line offset since 2M design §5b's typed-section refactor —
    the flat line list these used to be offsets into is gone).

    Recorded WHERE THEY HAPPEN, as the sections are built, rather than found
    afterwards by searching the finished document for a heading. A search
    would make placement depend on how a heading is spelled — and on whether
    an earlier claim's prose happened to contain the same words — which is
    precisely the markdown-parsing round trip §6b forbids.
    """

    structure_end: int
    endpoints_end: int
    # One entry per open question, in the order the section renders them: the
    # row's identity and the index just past its own single-item section.
    beside_question: tuple[tuple[tuple[str | None, ...], int], ...]
    questions_end: int
    # Where a config-shaped verdict lands (2N design §2): the index just past
    # the Coverage section's single `MachineList`, which is where the
    # "Configuration key unresolved" lines it answers are printed. One index
    # for the whole listing, not one per row — unlike `beside_question`,
    # config rows are not each given their own single-item section.
    config_end: int
    document_end: int

    def index_of(self, claim: Claim) -> int:
        """Where `claim` goes. An endpoint-shaped `beside-open-question`
        verdict goes under the line of the very question it answers; a
        config-shaped one goes beside the coverage table's unresolved-
        configuration listing; anything else anchored there goes after the
        last question, since nothing in a component, section or diagram claim
        names a single row."""
        if claim.anchor is Anchor.AFTER_COMPONENT_OVERVIEW:
            return self.structure_end
        if claim.anchor is Anchor.AFTER_ENDPOINT_TABLE:
            return self.endpoints_end
        if claim.anchor is Anchor.END_OF_DOCUMENT:
            return self.document_end
        if isinstance(claim, VerdictClaim):
            if isinstance(claim.question, ConfigQuestionRef):
                return self.config_end
            for identity, index in self.beside_question:
                if identity == claim.question.identity:
                    return index
        return self.questions_end


def _interleave(
    machine_sections: tuple[Section, ...],
    anchors: _Anchors,
    overlay: EnrichmentOverlay | None,
    stale: frozenset[int],
    redactor: Redactor,
) -> AssembledDocument:
    """The typed machine sections and the overlay's claims as one ordered
    section list.

    **Deterministic by construction** (NFR-1): claims are grouped by the
    section index their anchor resolves to, the indices are visited in
    ascending document order, and within one index the claims keep the order
    the overlay file lists them in. Nothing here sorts by content, so
    re-running assembly over the same workspace and the same overlay produces
    the same list.

    With 2M design §5b's typed sections, there is no line list left to slice:
    a claim at index N is simply inserted before `machine_sections[N]` (or
    after everything, at `N == len(machine_sections)`), which is what makes
    this a single pass over the machine list rather than the line-splitting
    this used to be.
    """
    placed: dict[int, list[Claim]] = {}
    if overlay is not None:
        for index, claim in enumerate(overlay.claims):
            if index in stale:
                continue
            placed.setdefault(anchors.index_of(claim), []).append(
                _redacted_claim(index, claim, redactor)
            )

    # A claim dropped silently is exactly what this file's own discipline
    # refuses everywhere else (NFR-7's visible stale-claim notice, below): a
    # section index outside the document's own range would otherwise sit in
    # `placed` unvisited by either loop below and vanish with no trace. Every
    # `_Anchors.index_of` result is built from `len(sections)` at some point
    # during assembly, so this never fires in practice — it is here for the
    # day a future anchor kind computes one wrong, so that bug is a loud
    # failure here rather than a claim quietly missing from the page.
    for section_index in placed:
        if not 0 <= section_index <= len(machine_sections):
            raise ValueError(
                f"claim anchor resolved to section index {section_index}, outside "
                f"the document's own 0..{len(machine_sections)} range — a claim must "
                "never be silently dropped"
            )

    sections: list[Section] = []
    for index, section in enumerate(machine_sections):
        if index in placed:
            assert overlay is not None
            sections.append(EnrichmentSection(overlay.produced_by, tuple(placed[index])))
        sections.append(section)
    if len(machine_sections) in placed:
        assert overlay is not None
        sections.append(
            EnrichmentSection(overlay.produced_by, tuple(placed[len(machine_sections)]))
        )
    if stale and overlay is not None:
        sections.append(StaleNoticeSection(overlay.produced_by, len(stale)))
    return tuple(sections)


def _redacted_claim(index: int, claim: Claim, redactor: Redactor) -> Claim:
    """One claim with every string it carries passed through the redactor.

    **Belt and braces, stated as such.** A claim's prose is model output that
    already came back through Sextant's own tools, and those redact on read
    (2K design §4) — so in the ordinary case this changes nothing. It is
    applied anyway because the overlay has a second door: `--ingest` accepts
    answers from an agent that ran under its own permissions and outside our
    jail (design §3's honesty note), and render is a publishing exit. Masking
    at ASSEMBLY rather than in a serializer is what makes it apply to both
    outputs: the HTML emitter reads these same claims.

    `redact_json` over the model's own JSON, rather than a hand-written walk
    of the four claim shapes: one traversal that already knows to touch string
    leaves and leave object keys alone, and a fifth claim kind inherits it
    without anyone remembering to extend a walk.

    Re-validated afterwards, and a failure is `ClaimRedactionError` naming the
    claim: a repository's `redact:` section can widen masking into any value
    pattern it likes, including one that eats a required field or the evidence
    marker itself. That is the repository's own input written wrong (D04 §2a),
    so it is refused with a message rather than raised as a pydantic traceback
    from inside a renderer.
    """
    masked = redactor.redact_json(claim.model_dump_json())
    try:
        return type(claim).model_validate_json(masked)
    except ValidationError as broken:
        raise ClaimRedactionError(
            f"a redaction rule rewrote enrichment claim {index} "
            f"({claim.kind}) into something the claim schema refuses — "
            f"widen the rule less, or narrow what it matches: {broken}"
        ) from broken


def markdown_document(sections: AssembledDocument) -> str:
    """`architecture.md` from an assembled document.

    Machine lines are emitted verbatim, in order, and a `MachineDiagram` is
    re-fenced into exactly the three-plus-n lines it was lifted from — so with
    no overlay the bytes are the ones this renderer produced before any of 2K
    existed, which is what the golden document pins.

    **Exactly one blank line between ANY two adjacent sections whose own
    lines do not already touch one** (fix round 1, HIGH — generalized past
    2K's own enrichment-only rule below, which is now this rule's special
    case rather than a second one living beside it). Required, not cosmetic,
    for two different reasons that both land on the same fix: an enrichment
    blockquote followed immediately by a list item swallows that item as a
    lazy continuation, so a claim would eat the next open question; and a
    plain paragraph landing immediately under a pipe table with no blank
    line between them is read by GFM as one more row of the table itself —
    four empty cells a reader never wrote (the media legend under the
    inbound endpoint table is exactly this, since a `MachineTable` and the
    `MachineParagraph` after it were the first two adjacent sections in this
    document that both actually need a separator neither already supplies).
    Where the neighbouring lines already begin or end with a blank of their
    own — a heading's own leading blank, `### Shapes` right before its first
    entry — none is added, so this never doubles what a section already
    provides for itself.

    **One deliberate exception: two adjacent `MachineList` sections stay
    tight, no blank forced between them.** `## Open questions` builds ONE
    single-item `MachineList` per question (`_Anchors`'s own docstring: a
    `beside-open-question` claim has to land right after THIS question and
    no other, which is only possible if each question owns its own section
    index) — several of those, with no claim landing between any two of
    them, are meant to read as ONE continuous bulleted list, the same way
    `## Coverage`'s bullets do from inside a single `MachineList`. The
    general rule would otherwise read consecutive questions as two
    paragraphs' worth of unrelated bullets rather than one list.
    """
    lines: list[str] = []
    for index, section in enumerate(sections):
        if isinstance(section, EnrichmentSection | StaleNoticeSection):
            if lines and lines[-1] != "":
                lines.append("")
            lines += _enrichment_lines(section)
        else:
            lines += _machine_lines(section, is_first=index == 0) or ()
        following = sections[index + 1] if index + 1 < len(sections) else None
        following_lines = () if following is None else _opening_lines(following)
        both_lists = isinstance(section, MachineList) and isinstance(following, MachineList)
        if (
            not both_lists
            and lines
            and lines[-1] != ""
            and following_lines
            and following_lines[0] != ""
        ):
            lines.append("")
    return "\n".join(lines) + "\n"


def _opening_lines(section: Section) -> Sequence[str]:
    """The lines `section` would render as, machine or enrichment alike —
    used ONLY to peek at whether the NEXT section already opens on a blank
    line of its own, from `markdown_document`'s blank-line rule above. Each
    section still renders through its own branch when its own turn comes;
    this never decides what gets written, only whether a separator is still
    needed before it."""
    if isinstance(section, EnrichmentSection | StaleNoticeSection):
        return _enrichment_lines(section)
    return _machine_lines(section) or ()


def _machine_lines(section: Section, is_first: bool = False) -> tuple[str, ...] | None:
    """The markdown lines of a MACHINE section — or `None` for a section that
    is not machine text at all. One place decides what "machine" means, so
    the emitter's blank-line rule and its per-kind rendering rule cannot
    disagree about a diagram — or, now, about a heading, a list, a table or a
    detail block.

    `is_first` matters only for `MachineHeading`: every heading is preceded
    by a blank line EXCEPT the module title, which opens the document."""
    if isinstance(section, MachineHeading):
        lines = () if is_first else ("",)
        return (*lines, f"{_HEADING_MARKERS[section.level]}{section.text}", "")
    if isinstance(section, MachineParagraph):
        return (_runs_to_markdown(section.runs),)
    if isinstance(section, MachineList):
        return tuple(f"- {_runs_to_markdown(item)}" for item in section.items)
    if isinstance(section, MachineTable):
        return _table_lines(section)
    if isinstance(section, MachineDetail):
        return _detail_lines(section)
    if isinstance(section, MachineSection):
        return section.lines
    if isinstance(section, MachineDiagram):
        fence = ("```mermaid", *section.mermaid.split("\n"), "```")
        if section.elides is None:
            return fence
        # The blank line is `_claim_lines`' own shape for a `DiagramClaim`,
        # kept identical here: a line landing directly under a closing fence
        # reads as part of the code block in some renderers, and a machine
        # diagram's elision must be as visible as a model's.
        return (*fence, "", f"Elides: {section.elides}")
    return None


def _table_lines(table: MachineTable, indent: str = "") -> tuple[str, ...]:
    """One `MachineTable` as markdown pipe-table lines, `indent` spaces before
    every `|` — `""` for a top-level endpoint table, four spaces for a shape
    table nested inside a `MachineDetail` entry, matching the indent the
    line-based renderer this replaces always used for a nested one."""
    header = f"{indent}| " + " | ".join(table.headers) + " |"
    separator = f"{indent}|" + "|".join("---" for _ in table.headers) + "|"
    rows = tuple(
        f"{indent}| " + " | ".join(_runs_to_markdown(cell) for cell in row) + " |"
        for row in table.rows
    )
    return (header, separator, *rows)


def _detail_lines(detail: MachineDetail) -> tuple[str, ...]:
    """One `MachineDetail` as the two-level markdown list it always was: the
    header entry (`entries[0]`) as the unindented bullet, then every entry
    after it nested one level, either as an inline `label: body` or as a
    `label:` followed by its table indented four spaces.

    No leading blank line of its own (fix round 1, HIGH): `markdown_document`
    now guarantees exactly one between this block and whatever precedes it —
    an endpoint table, the media legend, another detail block, a heading —
    so a leading blank hardcoded here on top of that would double up
    whenever the block right before this one ALSO ends on non-blank content
    that the shared rule would already have separated (this is what fixed
    the double blank line between `### Shapes` and its first entry)."""
    lines: list[str] = []
    for index, entry in enumerate(detail.entries):
        prefix = "-" if index == 0 else "  -"
        title = _runs_to_markdown(entry.title)
        if entry.table is not None:
            lines.append(f"{prefix} {title}:")
            lines.append("")
            lines += _table_lines(entry.table, indent="    ")
        elif entry.body is not None:
            lines.append(f"{prefix} {title}: {_runs_to_markdown(entry.body)}")
        else:
            lines.append(f"{prefix} {title}")
    return tuple(lines)


def _provenance_line(provenance: Provenance) -> str:
    """The header every enrichment block sits under: what the block is, the
    evidence marker it carries, and the run that produced it (2K design §6,
    "clearly marked")."""
    return f"**Enrichment — evidence: llm** (model {provenance.model}, agent {provenance.agent})"


def _enrichment_lines(section: EnrichmentSection | StaleNoticeSection) -> list[str]:
    """One enrichment block as markdown: a horizontal rule, the provenance
    header, each claim blank-line separated, and a closing rule.

    The rules are the markdown answer to the HTML serializer's bordered,
    badged box: they bound the block on BOTH sides, so a reader always sees
    where the model's text ends and the machine document resumes. The old
    form marked only the first line (as a blockquote), which left the claims
    visually indistinguishable from machine prose — and a blockquote is also
    why this is rules rather than `> `-prefixing the whole block: a mermaid
    fence inside a blockquote does not render on GitHub, and a diagram claim
    must render in BOTH outputs or the two disagree."""
    if isinstance(section, StaleNoticeSection):
        return [
            "---",
            "",
            f"{_provenance_line(section.provenance)} — {_stale_sentence(section.count)}",
            "",
            "---",
        ]
    lines = ["---", "", _provenance_line(section.provenance)]
    for claim in section.claims:
        lines += ["", *_claim_lines(claim)]
    lines += ["", "---"]
    return lines


def _stale_sentence(count: int) -> str:
    """The visible count of what is not shown (2K design §6). Never a silent
    omission, and never a claim rendered from referents that no longer
    exist."""
    return f"{count} enrichment claim{'' if count == 1 else 's'} stale, not shown."


def _claim_lines(claim: Claim) -> list[str]:
    """One claim as markdown. Each kind renders as what it is — a component
    with its members, prose with its citations, a mermaid fence with its
    elision statement, an assessment with its grounding — and every one of
    them reads as an addition beside the machine text, never as part of it."""
    if isinstance(claim, ComponentClaim):
        return [
            f"**Component: {claim.name}**",
            "",
            claim.purpose,
            "",
            f"Members: {_ticked(claim.members)}",
        ]
    if isinstance(claim, SectionClaim):
        return [
            f"**{claim.title}**",
            "",
            *claim.body.split("\n"),
            "",
            f"Cites: {_ticked(claim.cites)}",
        ]
    if isinstance(claim, DiagramClaim):
        return [
            "```mermaid",
            *claim.mermaid.rstrip("\n").split("\n"),
            "```",
            "",
            f"Elides: {claim.elides}",
        ]
    return _verdict_lines(claim)


def _verdict_lines(claim: VerdictClaim) -> list[str]:
    """The verification seat's label (2K design §7, widened by 2N design §2).
    The question's own identity is repeated on the line because a verdict
    does not always land directly under its question — one anchored
    `end-of-document`, or one whose row the section did not render, would
    otherwise name nothing. A config-shaped question prints its own columns
    (`key`, `source`, `environment`) the same way; `kind` is common to both
    shapes and always printed in the parenthetical that follows."""
    question = claim.question
    if isinstance(question, ConfigQuestionRef):
        identity = " ".join(
            part for part in (question.key, question.source, question.environment) if part
        )
    else:
        identity = " ".join(
            part for part in (question.protocol, question.method, question.path) if part
        )
    label = f"**LLM assessment** for `{identity}` ({question.kind}): {claim.assessment}"
    if claim.assessment == UNANSWERED:
        return [f"{label} — searched: {claim.searched}"]
    return [f"{label} — because {claim.because}"]


def _ticked(values: Sequence[str]) -> str:
    """A claim's list of identifiers or paths, comma-joined and typeset as
    code — they are names to look up, not prose."""
    return ", ".join(f"`{value}`" for value in values)
