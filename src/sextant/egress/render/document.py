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
from collections.abc import Sequence
from dataclasses import dataclass

from pydantic import ValidationError

from sextant.application.ports.detector import ModuleModel
from sextant.application.resolve.pipeline import ResolveReport
from sextant.domain.closed_sets import Anchor, Protocol
from sextant.domain.enrichment import (
    UNANSWERED,
    Claim,
    ComponentClaim,
    DiagramClaim,
    EnrichmentOverlay,
    Provenance,
    SectionClaim,
    VerdictClaim,
    open_question_identity,
)
from sextant.domain.redaction import Redactor
from sextant.domain.symbols import bare_descriptor
from sextant.egress.render.diagrams import class_diagram
from sextant.egress.render.viewmodel import ClassEdge, ClassNode, simple_name

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
    "Sequence diagrams await the call graph.",
    "The structure diagram covers contract types only: inheritance edges are not extracted.",
    "The call graph is not implemented: there are no traces or sequence diagrams.",
    (
        "Maven parent POMs, profiles, and property interpolation are not resolved: "
        "the detector reads pom.xml directly instead of asking Maven to resolve it, "
        "so any POM that depends on a parent, an active profile, or a property "
        "placeholder will be misread — which is most real-world POMs."
    ),
    (
        "Catalogs are not matched to modules: every catalog's `detect.coordinates` "
        "is declared and read by nobody, so every catalog runs against every "
        "module whether or not the module depends on that framework."
    ),
    (
        "Module classification reads only a container file and a declared main "
        "class: a module showing neither is reported `undetermined` rather than "
        "weighed against the rest of the evidence."
    ),
    (
        "A path the module both exposes and calls keeps only the handler's "
        "declared contract: where the client's declaration differs, that "
        "difference is not recorded."
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
_VERBED_PROTOCOLS = frozenset({"http", "grpc"}) | _PROTOCOL_QUALIFIED
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
identifier, path or key, `("text", content)` for everything else. The
builders below already know which is which — every code span they ever wrote
was wrapped in backticks by hand — so a `Run` never has to be guessed at
after the fact by an HTML emitter that would otherwise have to decide what a
backtick means on its own (2M design §5b)."""


def _runs(markdown: str) -> tuple[Run, ...]:
    """`markdown` split into alternating text/code runs on backtick-delimited
    spans — the inverse of how every machine string below is already built.

    **Round-trips exactly when `markdown` carries an EVEN number of
    backticks** — every code span this renderer ever opened, it closed, so
    its own output always qualifies, and so does any evidence text (a
    reason, a candidate's `why`/`seen_in`) that happens to contain a
    complete, or no, backtick pair. An ODD (unbalanced) count does NOT
    round-trip: the trailing part after the last backtick lands at an ODD
    index and is read back as a code run, so `_runs_to_markdown(_runs("a`b"))`
    produces `` a`b` `` — a spurious closing backtick the input never had —
    never a raised error or a dropped character. This function does not
    validate; it only ever has to be reversible for the balanced case that is
    every string it actually receives in practice.

    Kept EVEN for an empty code span (`` `` ``, two adjacent backticks): `if
    part or i % 2` — never `if part` alone, which would silently drop an
    empty *code* run (odd index) along with every genuinely empty text run
    (even index) and, for `` a``b ``, reconstruct as `ab` — two backticks lost
    outright, not merely misplaced. Dropping an EMPTY text run is always
    safe: an empty string contributes nothing to `_runs_to_markdown` whether
    kept or dropped."""
    return tuple(
        ("code" if i % 2 else "text", part)
        for i, part in enumerate(markdown.split("`"))
        if part or i % 2
    )


def _runs_to_markdown(runs: Sequence[Run]) -> str:
    """The exact inverse of `_runs`: a code run is rewrapped in backticks, a
    text run passes through unchanged, and the two concatenate back into the
    original markdown."""
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
    typing this instead of leaving it as `MachineSection` lines."""

    entries: tuple[DetailEntry, ...]


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
    """

    mermaid: str


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
    """A row's wire identity as one string. A protocol in `_VERBLESS_PROTOCOLS`
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
    protocol = str(endpoint["protocol"])
    path = endpoint["path"]
    rendered_path = "(unresolved)" if path is None else redactor.redact_text(str(path))
    if protocol in _VERBLESS_PROTOCOLS:
        return f"{protocol} {rendered_path}"
    method = endpoint["method"]
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


def _handler(endpoint: dict[str, object]) -> str:
    """The Handler column: the owner's bare descriptor, or one of the two
    different things a NULL `handler` can mean.

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
    handler = endpoint.get("handler")
    if handler is not None:
        return f"`{bare_descriptor(str(handler))}`"
    if endpoint.get("caller") is None and endpoint.get("resolution") == "resolved":
        return "none recorded"
    return "unresolved"


def _media(value: object) -> str:
    """One side of the Media column: the JSON list's comma-joined members, or
    `-` when the side is NULL — never a bare blank cell, so a row with both
    sides NULL still says so rather than reading as an omission."""
    if value is None:
        return "-"
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
    surface like `partial`, and including the `merge_endpoints.sql` exception
    where a merged row keeps a non-NULL format beside the WEAKER of its two
    halves' markers (schema.sql's own note) — a merged row may read
    `(protobuf, unresolved)`. Printing that plain would make an
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
    `resolve/shapes/parse_binding.py`) — so the fact reads the same way in
    the trail and in this list. `payload_binding` and `format_conflict`
    candidates carry different keys (2G design §6), so this switches on
    `question` rather than guessing a common shape out of the JSON — the same
    discipline `open_questions.py`'s own docstring asks of "the renderer"."""
    if question == "format_conflict":
        return f"{candidate['format']} from {candidate['seen_in']} ({candidate['why']})"
    if question == "payload_binding":
        return (
            f"{candidate['payload_type']} in {candidate['seen_in']} "
            f"via {candidate['why']} at {candidate['hops']} hop(s)"
        )
    # Unreached while `open_questions.py`'s QUESTIONS stays the two-kind
    # closed set it enforces at write time — a new kind is a schema change,
    # never a rendering guess (NFR-5).
    raise ValueError(f"open question `{question!r}` has no rendering rule")


def render_module_document(
    module: ModuleModel,
    report: ResolveReport,
    commit: str,
    uncovered: tuple[str, ...] = (),
    shape_fields: Sequence[dict[str, object]] = (),
    resolved_config: Sequence[dict[str, object]] = (),
    open_questions: Sequence[dict[str, object]] = (),
    library_symbols: Sequence[dict[str, object]] = (),
    libraries_not_scanned: tuple[str, ...] = (),
    redactor: Redactor = _DEFAULT_REDACTOR,
    overlay: EnrichmentOverlay | None = None,
    stale: frozenset[int] = frozenset(),
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
            resolved_config=resolved_config,
            open_questions=open_questions,
            library_symbols=library_symbols,
            libraries_not_scanned=libraries_not_scanned,
            redactor=redactor,
            overlay=overlay,
            stale=stale,
        )
    )


def assemble_module_document(
    module: ModuleModel,
    report: ResolveReport,
    commit: str,
    uncovered: tuple[str, ...] = (),
    shape_fields: Sequence[dict[str, object]] = (),
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

    sections.append(MachineHeading(2, "Structure"))
    if report.shapes:
        nodes, edges = _contract_nodes(report.shapes, shape_fields)
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
        headers = ("Endpoint", "Handler", "Media", "Format", "Resolution")
        rows = []
        for endpoint in inbound:
            media = f"{_media(endpoint.get('consumes'))} → {_media(endpoint.get('produces'))}"
            rows.append(
                (
                    _code(_wire_identity(endpoint, redactor)),
                    _runs(_handler(endpoint)),
                    _text(media),
                    _text(_format(endpoint)),
                    _text(str(endpoint["resolution"])),
                )
            )
        sections.append(MachineTable(headers, tuple(rows)))
        for endpoint in inbound:
            request = _descriptor_entry("Request", endpoint.get("request_shape"), fields_by_shape)
            response = _descriptor_entry(
                "Response", endpoint.get("response_shape"), fields_by_shape
            )
            via = _via_entry(endpoint, origin_by_symbol)
            entries = [entry for entry in (via, request, response) if entry is not None]
            if entries:
                identity = _wire_identity(endpoint, redactor)
                header = DetailEntry(_code(identity), None, None)
                sections.append(MachineDetail((header, *entries)))
            if via is not None:
                attributed.add(_wire_identity(endpoint, redactor))
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
                header = DetailEntry(_code(identity), None, None)
                sections.append(MachineDetail((header, via)))
                attributed.add(identity)
    else:
        sections.append(MachineParagraph(_runs("None found.")))
    # `after-endpoint-table`: after BOTH tables and their detail blocks. The
    # document's endpoint listing is one thing to a reader — a claim about "the
    # endpoints" that landed between the inbound and outbound halves would read
    # as a claim about the inbound ones alone.
    endpoints_end = len(sections)

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
            item = _runs(f"`{_wire_identity(row, redactor)}` — {question}: {rendered}")
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
    gap_items += [
        _runs(f"Not expanded, so the shapes referring to it are open: `{symbol}`.")
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
            structure_end, endpoints_end, tuple(beside_question), questions_end, len(sections)
        ),
        overlay,
        stale,
        redactor,
    )


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
    shapes: list[dict[str, object]], shape_fields: Sequence[dict[str, object]]
) -> tuple[list[ClassNode], list[ClassEdge]]:
    """`shapes`/`shape_fields` projected into the view model the emitter draws
    (M07 "Structure — contract class diagram"): one node per shape with its
    own wire fields, one edge per field whose `item` descriptor points at
    another shape."""
    grouped = _fields_by_shape(shape_fields)
    nodes: list[ClassNode] = []
    edges: list[ClassEdge] = []
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
    return nodes, edges


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


def _descriptor_entry(
    label: str,
    descriptor_json: object,
    fields_by_shape: dict[str, list[dict[str, object]]],
) -> DetailEntry | None:
    """One endpoint's request or response, nested under its detail block's
    header entry: a contract table of the referenced shape's fields when the
    payload is itself a shape, or an inline label when it is a scalar or a
    collection of one. `None` (no descriptor) contributes nothing."""
    if descriptor_json is None:
        return None
    descriptor = json.loads(str(descriptor_json))
    shape_id = descriptor.get("shape_id")
    if not shape_id:
        return DetailEntry(_text(label), _text(_inline_descriptor(descriptor)), None)
    rows = []
    for row in fields_by_shape.get(str(shape_id), []):
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
        rows.append((_text(wire_name), _text(field_type), _text(required), _text(nullable)))
    return DetailEntry(_text(label), None, MachineTable(_SHAPE_FIELD_HEADERS, tuple(rows)))


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
    document_end: int

    def index_of(self, claim: Claim) -> int:
        """Where `claim` goes. A `beside-open-question` verdict goes under the
        line of the very question it answers; anything else anchored there
        goes after the last question, since nothing in a component, section or
        diagram claim names a single row."""
        if claim.anchor is Anchor.AFTER_COMPONENT_OVERVIEW:
            return self.structure_end
        if claim.anchor is Anchor.AFTER_ENDPOINT_TABLE:
            return self.endpoints_end
        if claim.anchor is Anchor.END_OF_DOCUMENT:
            return self.document_end
        if isinstance(claim, VerdictClaim):
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

    An enrichment block is separated from whatever surrounds it by exactly one
    blank line — required, not cosmetic: a markdown blockquote followed
    immediately by a list item swallows that item as a lazy continuation, so
    the claim would eat the next open question. Where the neighbouring machine
    lines already begin or end with a blank of their own, none is added, so an
    overlay adds no blank lines it does not need.
    """
    lines: list[str] = []
    for index, section in enumerate(sections):
        if not isinstance(section, EnrichmentSection | StaleNoticeSection):
            lines += _machine_lines(section, is_first=index == 0) or ()
            continue
        if lines and lines[-1] != "":
            lines.append("")
        lines += _enrichment_lines(section)
        following = sections[index + 1] if index + 1 < len(sections) else None
        # `following_lines` can be empty only for a machine section carrying
        # none, which assembly does not build — guarded anyway, because
        # indexing a serializer's input on the assumption that a producer
        # never yields an empty one is a crash waiting for the day it does.
        # `following` is never the document's own first section (something
        # always precedes an enrichment block), so `is_first` is left at its
        # default here.
        following_lines = () if following is None else (_machine_lines(following) or ())
        if following_lines and following_lines[0] != "":
            lines.append("")
    return "\n".join(lines) + "\n"


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
        return ("```mermaid", *section.mermaid.split("\n"), "```")
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
    """One `MachineDetail` as the two-level markdown list it always was: a
    leading blank line (every detail block in the document follows either an
    endpoint table or another detail block, never opens one), the header
    entry (`entries[0]`) as the unindented bullet, and every entry after it
    nested one level, either as an inline `label: body` or as a `label:`
    followed by its table indented four spaces."""
    lines: list[str] = [""]
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
    evidence marker it carries, and the run that produced it. A blockquote, so
    a reader scanning the document sees the mark before the words (2K design
    §6, "clearly marked")."""
    return f"> **Enrichment — evidence: llm** (model {provenance.model}, agent {provenance.agent})"


def _enrichment_lines(section: EnrichmentSection | StaleNoticeSection) -> list[str]:
    """One enrichment block as markdown: the provenance header, then each
    claim, blank-line separated."""
    if isinstance(section, StaleNoticeSection):
        return [f"{_provenance_line(section.provenance)} — {_stale_sentence(section.count)}"]
    lines = [_provenance_line(section.provenance)]
    for claim in section.claims:
        lines += ["", *_claim_lines(claim)]
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
    """The verification seat's label (2K design §7). The question's own
    identity is repeated on the line because a verdict does not always land
    directly under its question — one anchored `end-of-document`, or one whose
    row the section did not render, would otherwise name nothing."""
    question = claim.question
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
