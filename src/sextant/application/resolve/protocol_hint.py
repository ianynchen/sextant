"""Protocol reclassification — the `protocol_hint` pass (2H design §6).

Nothing declares SSE. The same `@GetMapping` is an ordinary REST route or an
event stream depending on what it returns and what it says it produces, so the
row is derived as HTTP by the engine that reads the mapping and reclassified
here, once every engine has finished.

**Three promises, and they are the whole contract** (D02's `protocol_hint`
section):

1. It changes `protocol`, never `direction`. Direction is resolved at match
   time, and a pass that moved it afterwards would be re-answering a question
   the engine already answered from the evidence. *The reason used to be the
   inbound/outbound merge — "would silently corrupt a `both` row the merge had
   already built" — and W27 deleted that merge. The promise stands on its own:
   direction comes from what the catalog matched, and nothing here looks at
   that evidence.*
2. It never creates or deletes an endpoint. Every row it writes is a row an
   engine already minted; the row count is identical before and after.
3. It only ever moves a row of the SOURCE protocol its own catalog declares.
   A catalog's `protocol_hint` block is scoped by that catalog's own
   `protocol` field, so an HTTP catalog can only reclassify HTTP rows —
   the graphql, websocket and messaging rows no catalog names as a source are
   untouchable rather than merely untouched.

**Where it runs, and why there** (2H design §6's amendment to D02, which said
"runs last with `config_join`" before resolve passes existed): after every
engine — the rows must all exist — and BEFORE `resolve_format`, so a
reclassified row takes the format ladder under its true protocol. Rung 1 reads
`protocol` directly; running afterwards would answer the ladder for a protocol
the row no longer has. *The "and their merge" half of this went with the merge
in W27; two passes now run BELOW it instead, `self_exchange` and
`record_routing_conflicts`, both because `protocol` is part of the identity
they name.*

**Two evidence kinds, media first.** A row whose own declared media names the
protocol's envelope is the cheaper and stronger read: it is the channel's own
declaration, made in the source. The return-type read exists because a
handler may declare no media at all and still be a stream — the return type
is then the only statement there is.

The media read is `produces` ONLY, on every row, and deliberately narrower
than the format ladder's (`_MEDIA_COLUMNS` states the rule): `consumes` says
what a channel ACCEPTS, and a channel is not named after what it eats.

**One thing outside `endpoints` moves with a row**: its `open_questions`. The
2K ledger snapshots a wire identity rather than joining to it, and the
payload-binding pass took that snapshot before this one ran — see
`reclassify_open_questions.sql`.

**What `hint_returns` matches, precisely.** A return type is a TREE, not a
name: `SseEmitter` is a flat `TypeRef` whose own symbol is the marker, while
`Flux<ServerSentEvent<OrderView>>` carries the marker in the MIDDLE of a
two-level `arguments` chain and has an ordinary reactive type at the outer
symbol. So the rule is **the marker appears ANYWHERE in the return type's
generic chain** — the outer symbol, or any symbol reachable through nested
`arguments`, to any depth. Matching the outer symbol alone would catch the
first and miss the second entirely; matching only nested arguments would do
the reverse. The chain itself is data the facts carry and the markers are
catalog data — no type name appears below.

**Two evidence kinds read off the OWNER rather than the row** (spec
2026-09-18 §3c, §5b): `hint_annotations`, presence of a listed annotation on
the handler/caller or its enclosing type; `hint_when`, the §2 condition on
the same two targets. This is the one widening of what the pass reads —
annotation facts for the owner — and it still writes exactly one column on
rows that already exist.

**`hint_annotations` yields to a declared media sibling on the owner** (the
final review's Important 2, CP-19 row 2a). Quarkus implies SSE from the
element-type annotation only when the METHOD-level `@Produces` is empty —
CP-19 row 2a's `EndpointIndexer` lines 720-723 read `@Produces` off the
method first and fall to the element type only when that read is empty — so a handler
carrying `@Produces(APPLICATION_STREAM_JSON)` beside `@RestStreamElementType`
serves what it declares, not an event stream. The pass mirrors that with the
declaring catalog's own `mapping.produces_from_siblings` annotations
(`_Hint.media_annotations`): evidence 3 fires only when the OWNER itself —
never its type — carries none of them. The row's `produces` column is not
the check, because `type_media_from_siblings` fills it from the class
default too, and a class-level `@Produces` is exactly what Quarkus does NOT
consult here.

**A stated boundary, not a built one** (Task 5's review, widened by the
final review — `OI-92`): this pass reads RAW annotation facts only.
`annotation_index` folds the `annotations` table, and the inheritance walk's
synthesized rows — a type-level prefix, an inherited mapping and, for a
catalog opting in, its siblings — exist only as `derive_endpoints.sql`'s
`$synthetic` parameter, which nothing here sees. So neither of the two
inherited forms reaches evidence 3 or 4: a class-level hint annotation
declared on an INTERFACE the handler's class implements is never carried
onto the implementor's class, and a METHOD-level one declared on an
interface method (`@GET @RestStreamElementType(...)` on the interface, an
annotation-free implementor) is never carried onto the implementing method
either, even though the walk carried the verb and the `@Path` beside it.
`hint_annotations` therefore sees only annotations written on the handler's
own declaration or its own class. The row derives `http` where the
framework serves an event stream — under-classified, never fabricated —
and the gap is left open rather than closed here.

Every framework, protocol, MIME and type name this pass compares against is
catalog data (2H design §6). No such name appears below.
"""

import json
from dataclasses import dataclass
from typing import Any

from sextant.application.ports.catalogs import Catalog, CatalogError
from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.conditions import (
    AnnotationArg,
    annotation_index,
    enclosing_type_of,
    holds,
    parse_condition,
)
from sextant.domain.closed_sets import Protocol
from sextant.domain.symbols import type_descriptor

# The block, and the four keys it may carry. Closed on purpose: a key this
# pass does not implement is refused rather than ignored, because an ignored
# key makes a catalog that MEANT to reclassify indistinguishable from one that
# declared nothing — the same reason `parse_calls` refuses a malformed entry
# instead of skipping it.
_BLOCK = "protocol_hint"
_TARGET = "protocol"
_MEDIA = "hint_media"
_RETURNS = "hint_returns"
_ANNOTATIONS = "hint_annotations"
_WHEN = "hint_when"
_KEYS = (_TARGET, _MEDIA, _RETURNS, _ANNOTATIONS, _WHEN)

# The ONE media column that may carry protocol evidence — `produces`, on every
# row, whatever its direction. This is the one place this pass deliberately
# does NOT follow the format ladder's rung 2, which folds both columns into one
# answer.
#
# `format` describes one wire and both columns describe it, so rung 2 is right
# to read both. A PROTOCOL hint is a narrower claim — "this channel IS an event
# stream" — and only one of the two columns can ever evidence it:
#
# - `produces` on an INBOUND row is what the route streams back. Evidence.
# - `produces` on an OUTBOUND row is what a caller expects to receive. Also
#   evidence: the thing on the wire is an event stream either way. *This used to
#   read "carried onto a merged `both` row from the outbound twin the merge
#   deleted"; W27 deleted the merge, so the outbound row is simply its own row
#   now and the reasoning is unchanged.*
# - `consumes`, on ANY row, means "this accepts event-stream REQUEST BODIES".
#   That is a statement about input and is never evidence that anything serves
#   a stream. A route declaring it is a handler being HANDED an event stream —
#   a real, if unusual, thing to write — and reclassifying it would rename the
#   channel after what it eats.
#
# Reading `consumes` on a client-side row was tempting — there it is what the
# client RECEIVES — and is refused anyway: ONE COLUMN, ONE MEANING. A rule that
# read `consumes` as "accepts" on one direction and "receives" on the other
# would need every reader to check the direction before it could read the
# column at all, and it buys an outbound case no shipped catalog produces.
#
# *The reason this once gave was the merge — `merge_endpoints.sql` coalesced,
# so a `both` row's `consumes` might be either half's and nothing said which.
# W27 deleted that statement and the provenance is no longer lost. The rule
# stands on the argument above, which is the one D02 now states; the dead one is
# recorded here rather than quietly swapped, because a rationale that has become
# false is worse than none (§9).*
_MEDIA_COLUMNS = ("produces",)

# What a reclassification is matched back onto: the row's `row_id`, which names
# exactly the row read (follow-the-object, Ruling 7) — `(protocol, direction,
# method, path)` is not unique in this table.
_MATCH_COLUMNS = ("row_id",)


def apply_protocol_hints(workspace: Workspace, catalogs: list[Catalog]) -> None:
    """Reclassifies every row whose evidence names another protocol.

    Runs after the engines' merge and before the format ladder
    (`resolve/pipeline.py`). Reads catalog vocabulary, the row's own columns
    and — for `hint_annotations`/`hint_when` — the owner's and its type's
    annotation facts; writes exactly one column, on rows that already
    existed, and the entries and questions about those rows follow them.
    """
    hints = _vocabulary(catalogs)
    if not hints:
        return
    # Built once, and only if some hint actually needs it: the two owner-read
    # kinds are the exception rather than the rule, and a module with no
    # `hint_annotations`/`hint_when` anywhere must not pay for a fold over
    # `annotations` it never reads.
    index = (
        annotation_index(workspace)
        if any(hint.annotations or hint.conditions for hint in hints.values())
        else {}
    )
    rows: list[dict[str, Any]] = []
    for endpoint in workspace.query("endpoints"):
        hint = hints.get(str(endpoint["protocol"]))
        if hint is None:
            continue
        if (
            _declares_media(endpoint, hint)
            or _returns_marker(endpoint, hint)
            or _owner_annotated(endpoint, hint, index)
            or _condition_holds(endpoint, hint, index)
        ):
            rows.append(
                {column: endpoint.get(column) for column in _MATCH_COLUMNS}
                | {"reclassified": hint.target}
            )
    # The ledger follows the rows. `open_questions.protocol` is a SNAPSHOT of
    # a wire identity, not a join, and `parse_binding` took its copy before
    # this pass ran — so a reclassified row's question would otherwise publish
    # one protocol while the endpoint published another. Two statements
    # because DuckDB binds parameters only on the last one of an execute, not
    # because they are two decisions: same `$rows`, one call site. The ledger
    # FIRST: it finds its questions by the protocol the row still holds.
    workspace.derive("reclassify_open_questions", rows=rows)
    workspace.derive("reclassify_protocol", rows=rows)
    # And the entries bound to a reclassified row take its new protocol (Ruling 7).
    workspace.derive("endpoint_rows_follow")


# --- the four evidence kinds ------------------------------------------------


def _declares_media(endpoint: dict[str, Any], hint: "_Hint") -> bool:
    """Evidence 1: the row's own declared MIME strings name the protocol's
    envelope. The channel said so, in the source, which is why this is read
    first — and why a row carrying it needs no return type at all.

    Only `produces` counts (`_MEDIA_COLUMNS` states why): `consumes` says what
    a channel ACCEPTS, and a channel is not named after what it eats."""
    return any(
        mime in hint.media for column in _MEDIA_COLUMNS for mime in _mime_list(endpoint.get(column))
    )


def _returns_marker(endpoint: dict[str, Any], hint: "_Hint") -> bool:
    """Evidence 2: a marker type appears anywhere in the handler's return
    type — as the returned type itself, or as any type argument nested inside
    it, to any depth (see the module docstring for why both are one rule).

    A row with no handler (an outbound call site) declares no return type at
    all and is answered by its media or not at all.
    """
    declared = endpoint.get("handler_signature")
    if declared is None:
        return False
    signature = json.loads(str(declared))
    returns = signature.get("returns") if isinstance(signature, dict) else None
    return bool(_symbols_of(returns) & hint.returns)


def _symbols_of(reference: Any) -> set[str]:
    """Every type symbol one `TypeRef` names, its own and its type arguments'
    transitively (D00 §5a).

    A set, not a list: the question each caller asks is membership, and a
    generic chain that repeats a type says nothing more by repeating it.
    Non-mapping members are skipped rather than refused — `arguments` is a
    JSON array the scanner writes, and a rung that raised on one would turn a
    fact-stream defect into a failure of this pass rather than of the scanner.
    """
    found: set[str] = set()
    pending = [reference]
    while pending:
        current = pending.pop()
        if not isinstance(current, dict):
            continue
        symbol = current.get("symbol")
        if symbol is not None:
            found.add(str(symbol))
        pending.extend(current.get("arguments") or [])
    return found


def _owner(endpoint: dict[str, Any]) -> str | None:
    """The row's OWNER — `handler` for an inbound row, `caller` for an
    outbound one. This pass runs before the linking tier that populates BOTH
    on a `both`-direction row (D01 §3), so at this point in the pipeline one
    of the two is always NULL and reading `handler or caller` never has to
    choose between them. `None` for neither, which is the only case evidence
    3 and 4 have nothing to read."""
    return str(endpoint["handler"] or endpoint["caller"] or "") or None


def _owner_annotated(
    endpoint: dict[str, Any], hint: "_Hint", index: dict[str, list[tuple[str, dict[str, Any]]]]
) -> bool:
    """Evidence 3: a listed annotation targets the row's owner, or — only if
    the owner itself carries none of the listed names — its enclosing type
    (`conditions.enclosing_type_of`, the same nearer-wins precedence
    `hint_when` reads). Quarkus's `@RestStreamElementType` is the shipped
    case (CP-19 row 2): a class-level use reaches every method the class
    declares only through this fallback, since the annotation names no
    member of its own."""
    owner = _owner(endpoint)
    if owner is None or not hint.annotations:
        return False
    # CP-19 row 2a: a method-level media sibling on the OWNER wins over the
    # element-type marker — the framework reads `@Produces` first and only
    # an empty read falls to the marker (module docstring). The owner alone:
    # a class-level `@Produces` is the default Quarkus consults AFTER this
    # decision, never before it.
    if any(annotation in hint.media_annotations for annotation, _ in index.get(owner, [])):
        return False
    for target in (owner, enclosing_type_of(owner)):
        if target and any(
            annotation in hint.annotations for annotation, _ in index.get(target, [])
        ):
            return True
    return False


def _condition_holds(
    endpoint: dict[str, Any], hint: "_Hint", index: dict[str, list[tuple[str, dict[str, Any]]]]
) -> bool:
    """Evidence 4: one of the catalog's `hint_when` conditions holds for the
    row's owner (`conditions.holds`, Task 7's `annotation_arg` — owner first,
    its enclosing type only on a total miss). Micronaut's
    `@JMSListener("sqsJmsConnectionFactory")` is the shipped case (CP-21 rows
    1a/3a): a `jms` row becomes `sqs` only where its own attribute names that
    factory, never for the whole family."""
    owner = _owner(endpoint)
    return owner is not None and any(holds(c, owner, index) for c in hint.conditions)


def _mime_list(column: object) -> list[str]:
    """The MIME strings one media column holds — `resolve/format.py`'s own
    reading of the same two columns, restated here rather than imported: this
    pass runs BEFORE the ladder and must not depend on it, and the rule (a
    JSON array of strings, or NULL) is D01 §3's contract on the column, not
    the ladder's."""
    if column is None:
        return []
    parsed = json.loads(str(column))
    return [str(entry) for entry in parsed] if isinstance(parsed, list) else []


# --- catalog vocabulary ---------------------------------------------------


@dataclass(frozen=True)
class _Hint:
    """What one SOURCE protocol's rows may be reclassified to, and on what
    evidence. `media` holds MIME strings verbatim; `returns` and
    `annotations` hold symbols, already converted from the catalog's dotted
    notation — the binding-seam discipline every other catalog reader keeps,
    so no rung above has to remember which notation it is holding.
    `conditions` holds one `AnnotationArg` per catalog that declared a
    `hint_when` (already parsed, never a raw block). `media_annotations`
    holds the declaring catalogs' `mapping.produces_from_siblings`
    annotation symbols — the method-level media declaration that, when
    present on the owner, stops `annotations` from firing (CP-19 row 2a);
    unioned across a family exactly as the evidence lists are."""

    target: str
    media: frozenset[str]
    returns: frozenset[str]
    annotations: frozenset[str]
    conditions: tuple[AnnotationArg, ...]
    media_annotations: frozenset[str]


def _vocabulary(catalogs: list[Catalog]) -> dict[str, _Hint]:
    """Every catalog's `protocol_hint` block, keyed by the SOURCE protocol —
    which is the declaring catalog's own `protocol`, never a name in the block.
    That is what scopes the pass: an HTTP catalog reclassifies HTTP rows and
    can reach nothing else, without this module knowing what HTTP is.

    Validated in full before a single row is read — the "broken file, not a
    half-answered table" discipline `resolve_format` and `resolve_config` both
    keep.

    **Merged across catalogs, and the two halves merge differently.** The
    target protocol is a single value per source, so two catalogs of a family
    disagreeing about it is refused rather than resolved (`format.py`'s
    `_merged` rule: picking either side silently would make the answer depend
    on filename order). The evidence — all four kinds, `hint_when`'s parsed
    condition included — is UNIONED, because it is additive: `spring-mvc.yml`
    and `spring-web.yml` each name the marker types their own artifact
    declares, and a module pulling in one of them must still get that one's
    markers. A `hint_when` condition is one per catalog, never merged into
    the others of its own block, so two catalogs of a family each get their
    own entry in `conditions` — the rule Task 9's shipped case needs, since
    Micronaut's `@JMSListener` and `@JMSProducer` are two different catalogs'
    own conditions, not one condition two catalogs would have to agree on.
    """
    hints: dict[str, _Hint] = {}
    origin: dict[str, Catalog] = {}
    for catalog in catalogs:
        block = catalog.protocol_hint
        if not block:
            continue
        target, media, returns, annotations, condition = _checked(block, catalog)
        source = catalog.protocol
        held = hints.get(source)
        if held is not None and held.target != target:
            raise CatalogError(
                f"loading catalog {catalog.source}: `{_BLOCK}.{_TARGET}: {target}` contradicts "
                f"`{held.target}`, declared for the same source protocol `{source}` in "
                f"{origin[source].source} — one source protocol, one target (2H design §6)"
            )
        hints[source] = _Hint(
            target=target,
            media=media | (held.media if held else frozenset()),
            returns=returns | (held.returns if held else frozenset()),
            annotations=annotations | (held.annotations if held else frozenset()),
            conditions=(held.conditions if held else ()) + ((condition,) if condition else ()),
            media_annotations=_media_siblings(catalog)
            | (held.media_annotations if held else frozenset()),
        )
        origin.setdefault(source, catalog)
    return hints


def _media_siblings(catalog: Catalog) -> frozenset[str]:
    """The catalog's `mapping.produces_from_siblings` annotations as symbols —
    the method-level media declaration evidence 3 yields to. Empty for a
    catalog that declares none (every non-JAX-RS-shaped one), which leaves
    evidence 3 reading presence alone, as before. Read here rather than
    validated: `annotation_driven._sibling_sources` already refused a
    malformed list at load."""
    mapping = catalog.matches.get("mapping") or {}
    return frozenset(
        type_descriptor(str(source["annotation"]))
        for source in (mapping.get("produces_from_siblings") or [])
    )


def _checked(
    block: Any, catalog: Catalog
) -> tuple[str, frozenset[str], frozenset[str], frozenset[str], AnnotationArg | None]:
    """Refuses a malformed block at run start.

    Four refusals, each of them a case where reading on would make a broken
    catalog look like an absent one:

    - an unknown key — the block's vocabulary is closed, and a typo silently
      ignored is a rule the author believes is running;
    - a target outside D00's protocol set, or equal to the catalog's own —
      the value is written straight into a published closed column (NFR-5),
      and reclassifying a protocol to itself is a no-op nobody meant to write;
    - evidence lists that are not lists of strings, or a `hint_when` this
      module's own `conditions.parse_condition` refuses by name (spec §2);
    - a block naming NONE of the four evidence kinds, which would be
      indistinguishable from a catalog that declares no block (the
      `parse_calls` precedent).
    """
    allowed = sorted(member.value for member in Protocol)
    if not isinstance(block, dict) or not set(block) <= set(_KEYS):
        raise CatalogError(
            f"loading catalog {catalog.source}: `{_BLOCK}` must be a mapping of "
            f"{'/'.join(_KEYS)}, got {block!r}"
        )
    target = block.get(_TARGET)
    if target not in allowed or target == catalog.protocol:
        raise CatalogError(
            f"loading catalog {catalog.source}: `{_BLOCK}.{_TARGET}: {target!r}` must be one of "
            f"{', '.join(allowed)} (D00's closed sets are closed — NFR-5) and must differ from "
            f"the catalog's own `{catalog.protocol}`"
        )
    media, returns = block.get(_MEDIA) or [], block.get(_RETURNS) or []
    annotations = block.get(_ANNOTATIONS) or []
    if not _string_list(media) or not _string_list(returns) or not _string_list(annotations):
        raise CatalogError(
            f"loading catalog {catalog.source}: `{_MEDIA}`/`{_RETURNS}`/`{_ANNOTATIONS}` must "
            f"each be a list of strings — got {block!r}"
        )
    condition = (
        parse_condition(block[_WHEN], f"loading catalog {catalog.source}: `{_BLOCK}.{_WHEN}`")
        if _WHEN in block
        else None
    )
    if not (media or returns or annotations or condition):
        raise CatalogError(
            f"loading catalog {catalog.source}: `{_BLOCK}` must name at least one of "
            f"`{_MEDIA}`/`{_RETURNS}`/`{_ANNOTATIONS}`/`{_WHEN}` — a block with no evidence "
            f"reclassifies nothing, which is what declaring no block already means"
        )
    return (
        str(target),
        frozenset(str(mime) for mime in media),
        frozenset(type_descriptor(name) for name in returns),
        frozenset(type_descriptor(name) for name in annotations),
        condition,
    )


def _string_list(declared: Any) -> bool:
    return isinstance(declared, list) and all(isinstance(entry, str) for entry in declared)
