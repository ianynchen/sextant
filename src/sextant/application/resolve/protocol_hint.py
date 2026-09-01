"""Protocol reclassification — the `protocol_hint` pass (2H design §6).

Nothing declares SSE. The same `@GetMapping` is an ordinary REST route or an
event stream depending on what it returns and what it says it produces, so the
row is derived as HTTP by the engine that reads the mapping and reclassified
here, once every engine has finished.

**Three promises, and they are the whole contract** (D02's `protocol_hint`
section):

1. It changes `protocol`, never `direction`. Direction is resolved at match
   time and the inbound/outbound merge has already run by the time this pass
   sees a row; a pass that moved direction afterwards would silently corrupt a
   `both` row the merge had already built. A merged row reclassifies
   WHOLESALE — one identity in, one identity out.
2. It never creates or deletes an endpoint. Every row it writes is a row an
   engine already minted; the row count is identical before and after.
3. It only ever moves a row of the SOURCE protocol its own catalog declares.
   A catalog's `protocol_hint` block is scoped by that catalog's own
   `protocol` field, so an HTTP catalog can only reclassify HTTP rows —
   the graphql, websocket and messaging rows no catalog names as a source are
   untouchable rather than merely untouched.

**Where it runs, and why there** (2H design §6's amendment to D02, which said
"runs last with `config_join`" before resolve passes existed): after the
engines and their merge — the rows must all exist, and a merged `both` row
must already be one row — and BEFORE `resolve_format`, so a reclassified row
takes the format ladder under its true protocol. Rung 1 reads `protocol`
directly; running afterwards would answer the ladder for a protocol the row
no longer has.

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

Every framework, protocol, MIME and type name this pass compares against is
catalog data (2H design §6). No such name appears below.
"""

import json
from dataclasses import dataclass
from typing import Any

from sextant.application.ports.catalogs import Catalog, CatalogError
from sextant.application.ports.workspace import Workspace
from sextant.domain.closed_sets import Protocol
from sextant.domain.symbols import type_descriptor

# The block, and the three keys it may carry. Closed on purpose: a key this
# pass does not implement is refused rather than ignored, because an ignored
# key makes a catalog that MEANT to reclassify indistinguishable from one that
# declared nothing — the same reason `parse_calls` refuses a malformed entry
# instead of skipping it.
_BLOCK = "protocol_hint"
_TARGET = "protocol"
_MEDIA = "hint_media"
_RETURNS = "hint_returns"
_KEYS = (_TARGET, _MEDIA, _RETURNS)

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
# - `produces` carried onto a merged `both` row from the outbound twin the
#   merge deleted is what a CALLER expects to receive. Also evidence: the
#   thing on the wire is an event stream either way.
# - `consumes`, on ANY row, means "this accepts event-stream REQUEST BODIES".
#   That is a statement about input and is never evidence that anything serves
#   a stream. A route declaring it is a handler being HANDED an event stream —
#   a real, if unusual, thing to write — and reclassifying it would rename the
#   channel after what it eats.
#
# Reading `consumes` on a client-side row was tempting (there it is what the
# client RECEIVES) and is refused anyway, because after the merge the column's
# PROVENANCE is gone: `merge_endpoints.sql` coalesces, keeping the surviving
# inbound row's own `consumes` first, so a `both` row's `consumes` may be the
# inbound half's "accepts" declaration or the outbound half's "receives" one
# and nothing on the row says which. One column, one meaning, no direction
# table — a rule that cannot be read two ways is worth more than the outbound
# case it gives up, which no shipped catalog produces today.
_MEDIA_COLUMNS = ("produces",)

# The row identity a reclassification is matched back onto — the same six
# columns `stamp_format.sql` and `bind_request_shape.sql` use, for the same
# reason: `(protocol, direction, method, path)` is not unique in this table,
# and `handler`/`caller` are what separate two rows that share it.
_MATCH_COLUMNS = ("protocol", "direction", "method", "path", "handler", "caller")


def apply_protocol_hints(workspace: Workspace, catalogs: list[Catalog]) -> None:
    """Reclassifies every row whose evidence names another protocol.

    Runs after the engines' merge and before the format ladder
    (`resolve/pipeline.py`). Reads only catalog vocabulary and the row's own
    columns; writes exactly one column, on rows that already existed.
    """
    hints = _vocabulary(catalogs)
    if not hints:
        return
    rows: list[dict[str, Any]] = []
    for endpoint in workspace.query("endpoints"):
        hint = hints.get(str(endpoint["protocol"]))
        if hint is None:
            continue
        if _declares_media(endpoint, hint) or _returns_marker(endpoint, hint):
            rows.append(
                {column: endpoint.get(column) for column in _MATCH_COLUMNS}
                | {"reclassified": hint.target}
            )
    workspace.derive("reclassify_protocol", rows=rows)
    # The ledger follows the rows. `open_questions.protocol` is a SNAPSHOT of
    # a wire identity, not a join, and `parse_binding` took its copy before
    # this pass ran — so a reclassified row's question would otherwise publish
    # one protocol while the endpoint published another. Two statements
    # because DuckDB binds parameters only on the last one of an execute, not
    # because they are two decisions: same `$rows`, one call site.
    workspace.derive("reclassify_open_questions", rows=rows)


# --- the two evidence kinds -----------------------------------------------


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
    evidence. `media` holds MIME strings verbatim; `returns` holds symbols,
    already converted from the catalog's dotted notation — the binding-seam
    discipline every other catalog reader keeps, so no rung above has to
    remember which notation it is holding."""

    target: str
    media: frozenset[str]
    returns: frozenset[str]


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
    on filename order). The evidence lists are UNIONED, because they are
    additive: `spring-mvc.yml` and `spring-web.yml` each name the marker types
    their own artifact declares, and a module pulling in one of them must
    still get that one's markers.
    """
    hints: dict[str, _Hint] = {}
    origin: dict[str, Catalog] = {}
    for catalog in catalogs:
        block = catalog.protocol_hint
        if not block:
            continue
        target, media, returns = _checked(block, catalog)
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
        )
        origin.setdefault(source, catalog)
    return hints


def _checked(block: Any, catalog: Catalog) -> tuple[str, frozenset[str], frozenset[str]]:
    """Refuses a malformed block at run start.

    Four refusals, each of them a case where reading on would make a broken
    catalog look like an absent one:

    - an unknown key — the block's vocabulary is closed, and a typo silently
      ignored is a rule the author believes is running;
    - a target outside D00's protocol set, or equal to the catalog's own —
      the value is written straight into a published closed column (NFR-5),
      and reclassifying a protocol to itself is a no-op nobody meant to write;
    - evidence lists that are not lists of strings;
    - a block naming NO evidence at all, which would be indistinguishable
      from a catalog that declares no block (the `parse_calls` precedent).
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
    if not _string_list(media) or not _string_list(returns) or not (media or returns):
        raise CatalogError(
            f"loading catalog {catalog.source}: `{_BLOCK}` must name at least one of "
            f"`{_MEDIA}`/`{_RETURNS}`, each a list of strings — a block with no evidence "
            f"reclassifies nothing, which is what declaring no block already means"
        )
    return (
        str(target),
        frozenset(str(mime) for mime in media),
        frozenset(type_descriptor(str(name)) for name in returns),
    )


def _string_list(declared: Any) -> bool:
    return isinstance(declared, list) and all(isinstance(entry, str) for entry in declared)
