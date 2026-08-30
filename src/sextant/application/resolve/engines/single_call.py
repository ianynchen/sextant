"""single_call engine for endpoint derivation (D02 §2's `single_call` style).

One call carries the whole outbound declaration — a `RestTemplate.postForObject`,
a `.exchange` — so this pass reads `call_sites` directly rather than joining
annotation facts: it matches each site against the catalog's declared
`methods` by name, resolves the verb (a literal or an `enum` argument's own
symbol), splits the url argument into peer and path (CP-2) — or, for a
`channel_arg` destination, keeps it whole and peerless — and resolves the
request/response descriptors from the call's own arguments through
`shapes.arguments.argument_descriptor` (D02 §2h). Framework knowledge — the
owner type, which argument is which, the PTR/call-wrapper rules — arrives as
catalog data; this module never names a framework.
"""

import json
from collections.abc import Sequence
from typing import Any

from sextant.application.ports.catalogs import Catalog, CatalogError
from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.shapes.arguments import (
    CallFacts,
    CarrierRules,
    _arg_at,
    _capture_resolved,
    _linked_constructor,
    argument_descriptor,
    channel_of,
    linked_channels,
    supertypes_of,
    url_of,
)
from sextant.application.resolve.shapes.expansion import _enum_symbols, _rules_of
from sextant.application.resolve.shapes.rooting import _catalog_symbol
from sextant.domain.closed_sets import Direction

_DIRECTIONS = sorted(member.value for member in Direction)


def run(workspace: Workspace, catalog: Catalog) -> None:
    """Derives one endpoint row per matching call site, via `call_endpoints`
    — a parameterised insert-if-absent on the same wire identity every other
    style uses (D02 §5). `caller` is the calling method symbol, unless the
    matched row's own `direction` is `inbound`, in which case it lands in
    `handler` instead (D02 §2); `peer` is NULL unless the row declares
    `url_arg` and that argument is itself an absolute URL (CP-2) — a
    `channel_arg` destination is never split, so its `peer` is always NULL;
    `method` is NULL where the verb itself
    could not be read (I2) or the row is verbless by declaration; `protocol`
    is the catalog's own declared field, exactly as `annotation_driven`
    forwards it, and `direction` is the catalog's own declared field unless
    the matched row overrides it."""
    matches = catalog.matches
    owner = _catalog_symbol(matches["owner"])
    # A list, not a dict-by-name (Task 6): `arity` lets two rows share a
    # `name` — `send(topic, payload)` and `send(topic, key, payload)` — and a
    # dict keyed by name would let the second overwrite the first.
    # `_matching_method` scans it per call site instead.
    methods = list(matches["methods"])
    _validate_methods(methods, catalog)
    record_wrappers = list(matches.get("record_wrappers", []))
    _validate_record_wrappers(record_wrappers, catalog)
    carrier_rules = CarrierRules(
        rules=_rules_of(catalog),
        enums=_enum_symbols(workspace),
        type_carriers=tuple(_catalog_symbol(t) for t in matches.get("type_carriers", [])),
        call_wrappers={
            _catalog_symbol(wrapper["type"]): wrapper["payload_ctor_arg"]
            for wrapper in matches.get("call_wrappers", [])
        },
    )
    # `record_arg`'s own lookup (D02 §2, Task 7): the record's type keys a
    # `(channel_ctor_arg, payload_ctor_arg)` pair, converted once here rather
    # than per call site, exactly as `call_wrappers` above is.
    record_wrapper_args = {
        _catalog_symbol(wrapper["type"]): (wrapper["channel_ctor_arg"], wrapper["payload_ctor_arg"])
        for wrapper in record_wrappers
    }
    supertypes = supertypes_of(workspace)
    # `arguments` is parsed once, here, rather than once per reader: the
    # `call_sites` query returns it as raw JSON text, and both the matching
    # loop below and the `call_wrappers` one-hop (over a *different* call
    # site's own arguments, `contracts._linked_constructor`) need the parsed
    # list, never the text.
    call_sites = [
        {**site, "arguments": json.loads(str(site["arguments"]))}
        for site in workspace.query("call_sites")
    ]
    by_caller: dict[str, list[dict[str, Any]]] = {}
    for site in call_sites:
        by_caller.setdefault(str(site["caller"]), []).append(site)

    # A list, not a set: the order call sites reach a shape decides the
    # order shape rows are written (NFR-1) — the same discipline
    # derive_endpoint_shapes keeps for its own `referenced` accumulator.
    referenced: list[str] = []
    rows: list[dict[str, Any]] = []
    # Only a *resolved* wire identity dedups here: two unresolved calls carry
    # no path to compare, and SQL's `NULL = NULL` is unknown rather than
    # true, so each stays its own row (D02 §2's unresolved-is-an-answer).
    seen: set[tuple[str, str, str, str]] = set()
    for site in call_sites:
        if site["owner"] != owner:
            continue
        arguments = site["arguments"]
        method = _matching_method(methods, site["name"], arguments)
        if method is None:
            continue
        # A row declaring neither `http_method` nor `method_arg` is verbless
        # by declaration (D02 §2) — a topic has no verb. Its `verb` reads
        # None too (`_verb_of` finds neither key), but that must not read as
        # I2's "the verb could not be captured": `verbless` tells the two
        # apart wherever `verb is not None` alone would otherwise stand in
        # for "a verb was declared and read".
        verbless = "http_method" not in method and "method_arg" not in method
        # NULL rather than dropped (I2): a call site matching the catalog's
        # own `owner` and `methods` IS an outbound call, and a verb the
        # scanner could not read — an `HttpMethod` arriving as a parameter
        # rather than as an enum constant — is one capture failing, exactly
        # like an unreadable url. Dropping the row would make "this method
        # calls something over HTTP" disappear on the strength of the one
        # column nobody could fill; `method` NULL on an `unresolved` row
        # says it instead (D02 §2's unresolved-is-an-answer).
        verb = _verb_of(method, arguments)
        caller = str(site["caller"])
        facts = CallFacts(
            supertypes=supertypes,
            caller_call_sites=by_caller.get(caller, []),
            referenced=referenced,
        )
        if "record_arg" in method:
            # `record_arg` names an argument whose *linked constructor*
            # carries both identity and payload (D02 §2, Task 7) —
            # `send(ProducerRecord)`'s one argument is the record, not the
            # topic or the value. `_validate_methods` already refused a row
            # declaring `record_arg` alongside `url_arg`/`channel_arg`/
            # `body_arg`/`response_arg`, so this is the row's only source
            # for both.
            record = _arg_at(arguments, method["record_arg"])
            url_argument, body_argument = _record_arguments(record, record_wrapper_args, facts)
            # `record_arg` is always a declared position (the row is only
            # reached here because it has one) — always True, the same
            # sentinel a `body_arg` row's own presence check collapses to.
            body_declared = True
        else:
            # `channel_arg` is `url_arg`'s alias for a destination-shaped
            # identity (D02 §2) — `_validate_methods` already refused a row
            # declaring both, so at most one of the two is ever present
            # here.
            url_argument = _arg_at(arguments, method.get("url_arg", method.get("channel_arg")))
            body_argument = _arg_at(arguments, method.get("body_arg"))
            body_declared = method.get("body_arg") is not None
        # `channel_arg` aliases `url_arg` in the grammar but not in the
        # READER (final review, IMPORTANT): a destination is an opaque
        # expression, never a URL to split. SQS's canonical destination is a
        # whole queue URL, and `url_of` would turn it into a fabricated peer
        # plus a truncated path. `_validate_methods` already refused a row
        # naming both, so this test is unambiguous.
        #
        # `channel_via` (Task 7) reads the destination off the call that
        # PRODUCED the argument instead of the argument's own position —
        # `session.createProducer(session.createQueue("raw-audit"))`'s topic
        # lives on `createQueue`'s own argument, never `createProducer`'s —
        # and it may read several channel identities off that one linked
        # call (`all_strings`). `linked_channels` always returns a list, so
        # this collapses to the same one-tuple list the non-`channel_via`
        # case builds by hand.
        destinations: Sequence[tuple[str | None, str | None, str]]
        if "channel_via" in method:
            destinations = linked_channels(url_argument, facts, _channel_via_forms(method))
        else:
            read_destination = channel_of if "channel_arg" in method else url_of
            destinations = [read_destination(url_argument)]
        response_argument = _arg_at(arguments, method.get("response_arg"))
        # `direction` on a row overrides the catalog's own declared
        # direction (D02 §2) — Pub/Sub's `subscribe` is inbound even inside
        # an otherwise outbound file.
        row_direction = method.get("direction", catalog.direction)
        # An inbound row's deriving method is the consumer, not the caller
        # (D02 §2): it lands in `handler`, and `caller` stays NULL — the
        # same handler/caller split `derive_endpoints.sql` keeps for the
        # annotation-driven styles, applied here per row rather than per
        # catalog.
        inbound = row_direction == "inbound"
        # Computed once, outside the destinations loop: neither depends on
        # `peer`/`path`/`url_resolution`, and `argument_descriptor` appends
        # to the shared `referenced` accumulator (deduped downstream,
        # `contracts.py`'s own `list(dict.fromkeys(...))`), so calling it
        # once per row rather than once per destination tuple keeps that
        # list from carrying the same shape root once per topic.
        request_shape = argument_descriptor(body_argument, facts, carrier_rules)
        response_shape = argument_descriptor(response_argument, facts, carrier_rules)
        # One row per destination tuple (the same multi-topic precedent
        # `annotation_driven._derive_replies` already keeps for a listener's
        # declared reply destinations) — every row shares the same verb/body
        # /response captures; only the destination itself varies.
        for peer, path, url_resolution in destinations:
            # Checkpoint ruling I1: any DECLARED capture that failed to
            # resolve drops the *row's* resolution, even when the url itself
            # read fine — `path` still carries the known template regardless
            # (it is the url's own answer, untouched by a body/response
            # capture's own failure), but a resolved row promises every
            # declared capture was read, not only the url. `path` stays
            # NULL-safe: this only ever narrows resolution from `resolved`
            # to `unresolved`, never the other way. A `record_arg` row's own
            # payload is exactly as "declared" as a `body_arg` row's
            # (`body_declared` stands in for either), so a linked
            # constructor whose payload slot could not be read narrows this
            # row's resolution the same way.
            resolution = (
                "resolved"
                if (verb is not None or verbless)
                and url_resolution == "resolved"
                and _capture_resolved(body_declared, body_argument)
                and _capture_resolved(method.get("response_arg") is not None, response_argument)
                else "unresolved"
            )
            # Only a *whole* resolved wire identity dedups, so an unreadable
            # verb keeps each row its own for the same reason an unreadable
            # url does: `NULL = NULL` is unknown in the table this batch is
            # inserted into, and two calls whose verbs nobody could read are
            # not known to be the same call. A verbless row dedups on
            # `(protocol, row_direction, path)` alone — there is no method to
            # distinguish them by — hence `verb or ""` rather than `verb`:
            # every shipped HTTP row declares `http_method` or `method_arg`,
            # so `verbless` is always False and `verb` is never None
            # wherever this key is built for them, making `verb or ""` equal
            # to `verb` and this change a no-op for those catalogs; likewise
            # no shipped row declares its own `direction`, so `row_direction`
            # is always `catalog.direction` there too.
            if path is not None and (verb is not None or verbless):
                key = (catalog.protocol, row_direction, verb or "", path)
                if key in seen:
                    continue
                seen.add(key)
            rows.append(
                {
                    "protocol": catalog.protocol,
                    "direction": row_direction,
                    "method": verb,
                    "path": path,
                    "handler": caller if inbound else None,
                    "caller": None if inbound else caller,
                    "peer": peer,
                    "handler_signature": None,
                    "resolution": resolution,
                    "evidence": "compiler",
                    "catalog_id": catalog.id,
                    "request_shape": request_shape,
                    "response_shape": response_shape,
                }
            )

    workspace.derive("call_endpoints", rows=rows)


def _matching_method(
    rows: list[dict[str, Any]], name: str, arguments: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """The one `methods` row matching a call site's own name and argument
    count (D02 §2's `arity`) — first match wins. A row without `arity`
    matches every overload, so the shipped 2C catalogs (none of which
    declare it) parse unchanged; a catalog that needs to tell
    `send(topic, payload)` from `send(topic, key, payload)` apart writes one
    row per arity instead, and this is the scan that replaces the old
    dict-by-name (`:40` before Task 6), which could only ever keep one row
    per name."""
    for row in rows:
        if row["name"] != name:
            continue
        arity = row.get("arity")
        if arity is not None and arity != len(arguments):
            continue
        return row
    return None


def _validate_methods(rows: list[dict[str, Any]], catalog: Catalog) -> None:
    """Refuses a broken `methods` row before any call site is matched — the
    `fluent._validate_steps` precedent: an unchecked value does not stay in
    the file (`ports/catalogs.py`'s own discipline), so this runs once, at
    `run` start, over every declared row, rather than lazily on whichever
    row a call site happens to reach first.

    `url_arg` and `channel_arg` name the same capture (D02 §2); a row
    declaring both is a broken catalog, not two pieces of evidence. A row's
    own `direction`, where declared, still has to be one of D00's closed
    Direction values — the catalog-level `direction` is checked at load time
    (`yaml_source.py`'s `_closed`), but a row's override lives inside
    `matches`, opaque to that loader-level check, so it is checked here
    instead. `record_arg` (Task 7) IS the channel+payload source — a row
    declaring it alongside `url_arg`/`channel_arg`/`body_arg`/`response_arg`
    is contradictory evidence, not a richer row. `channel_via` (Task 7's
    linked-call follow) says HOW to read an instance already named by
    `channel_arg`/`url_arg` — it is not itself a position, so a row
    declaring it without either is missing the position it describes; each
    declared form must be `{owner, method, arg: int|"all_strings"}`, the
    same shape discipline `record_wrappers` entries keep."""
    for row in rows:
        if "url_arg" in row and "channel_arg" in row:
            raise CatalogError(
                f"loading catalog {catalog.source}: `{row['name']}` declares both "
                f"`url_arg` and `channel_arg` — they name the same capture (D02 §2's "
                f"single_call style)"
            )
        if "channel_via" in row and "channel_arg" not in row and "url_arg" not in row:
            raise CatalogError(
                f"loading catalog {catalog.source}: `{row['name']}` declares `channel_via` "
                f"without `channel_arg`/`url_arg` — `channel_via` says how to read an "
                f"instance already named by one of those, never a destination position on "
                f"its own (D02 §2h)"
            )
        for entry in _channel_via_entries(row):
            valid = (
                isinstance(entry, dict)
                and isinstance(entry.get("owner"), str)
                and isinstance(entry.get("method"), str)
                and (entry.get("arg") == "all_strings" or isinstance(entry.get("arg"), int))
            )
            if not valid:
                raise CatalogError(
                    f"loading catalog {catalog.source}: `{row['name']}` declares a "
                    f"`channel_via` entry that must be `{{owner, method, "
                    f'arg: int|"all_strings"}}`, got {entry!r}'
                )
        if "record_arg" in row:
            conflicts = [
                key for key in ("url_arg", "channel_arg", "body_arg", "response_arg") if key in row
            ]
            if conflicts:
                raise CatalogError(
                    f"loading catalog {catalog.source}: `{row['name']}` declares "
                    f"`record_arg` together with {', '.join(conflicts)} — the record IS "
                    f"the channel+payload source (D02 §2's `record_arg`)"
                )
        direction = row.get("direction")
        if direction is not None and direction not in _DIRECTIONS:
            raise CatalogError(
                f"loading catalog {catalog.source}: `{row['name']}` declares "
                f"`direction: {direction}`, which is not one of {', '.join(_DIRECTIONS)} "
                f"— D00's closed sets are closed (NFR-5)"
            )


def _channel_via_entries(method: dict[str, Any]) -> list[Any]:
    """`channel_via`'s `{owner, method, arg}` | `[{...}, ...]` grammar,
    normalized to a list without touching the entries themselves — shared by
    `_validate_methods` (which must not crash reading `owner`/`method` off a
    malformed entry) and `_channel_via_forms` below (which converts each
    `owner` once a row is already known-valid)."""
    via = method.get("channel_via")
    if via is None:
        return []
    return via if isinstance(via, list) else [via]


def _channel_via_forms(method: dict[str, Any]) -> list[dict[str, Any]]:
    """Task 7's `channel_via` entries, each declared `owner` converted to
    the SCIP symbol form once — the same binding-seam discipline
    `call_wrappers`/`record_wrappers` keep. Only ever called on a row
    `_validate_methods` already passed, at `run` start."""
    return [
        {"owner": _catalog_symbol(entry["owner"]), "method": entry["method"], "arg": entry["arg"]}
        for entry in _channel_via_entries(method)
    ]


def _validate_record_wrappers(rows: list[dict[str, Any]], catalog: Catalog) -> None:
    """Refuses a broken `record_wrappers` block before any call site is
    matched — the same `_validate_methods` discipline, applied to the
    catalog-level block a `record_arg` row's lookup depends on. Each entry
    must be `{type, channel_ctor_arg, payload_ctor_arg}`: `type` a string,
    `channel_ctor_arg` an int, and `payload_ctor_arg` either an int or the
    literal string `"last"` (the constructor's own final argument) —
    anything else is a broken catalog, never a silent no-op once a call site
    reaches it."""
    for wrapper in rows:
        payload_ctor_arg = wrapper.get("payload_ctor_arg")
        valid = (
            isinstance(wrapper.get("type"), str)
            and isinstance(wrapper.get("channel_ctor_arg"), int)
            and (isinstance(payload_ctor_arg, int) or payload_ctor_arg == "last")
        )
        if not valid:
            raise CatalogError(
                f"loading catalog {catalog.source}: a `record_wrappers` entry must be "
                f'`{{type, channel_ctor_arg: int, payload_ctor_arg: int|"last"}}`, got '
                f"{wrapper!r}"
            )


def _record_arguments(
    record: dict[str, Any] | None,
    record_wrapper_args: dict[str, tuple[int, int | str]],
    facts: CallFacts,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """A `record_arg` row's channel and payload arguments (D02 §2's
    `record_wrappers`, Task 7): the record argument's own linked
    constructor — the same one-hop `contracts._linked_constructor` already
    gives `call_wrappers` — read at the catalog's declared
    `channel_ctor_arg`/`payload_ctor_arg` positions, `"last"` meaning the
    constructor's own final argument. Returns the two raw argument dicts,
    fed straight back into `url_of`/`argument_descriptor` exactly as a
    direct `url_arg`/`body_arg` row's own arguments are — the record path
    invents no second resolution rule.

    `(None, None)` wherever the chain breaks: the record itself was not
    captured as a constructed `instance`, its type names no
    `record_wrappers` entry, or no `<init>` call site in this same caller
    links to it. Each of these is I1's declared-capture failure, not a
    crash — the caller derives the row regardless, `resolution:
    unresolved`.

    The payload position is also None whenever it resolves to the SAME ctor
    slot `channel_ctor_arg` already claims — a 1-arg linked constructor with
    `channel_ctor_arg: 0` and `payload_ctor_arg: "last"` is exactly this
    collision (Task 7 review, MAJOR). Reporting the topic string back as
    the payload would be silently wrong rather than an honest capture
    failure; the channel argument itself is untouched by this guard, so
    `path` still carries whatever it read (I1: only the declared payload
    capture failed)."""
    if record is None or record.get("kind") != "instance" or record.get("symbol") is None:
        return None, None
    symbol = str(record["symbol"])
    wrapper = record_wrapper_args.get(symbol)
    if wrapper is None:
        return None, None
    channel_ctor_arg, payload_ctor_arg = wrapper
    constructor = _linked_constructor(symbol, record.get("source"), facts)
    if constructor is None:
        return None, None
    ctor_arguments = constructor.get("arguments") or []
    channel_argument = _arg_at(ctor_arguments, channel_ctor_arg)
    if isinstance(payload_ctor_arg, int):
        payload_index: int | None = payload_ctor_arg
    else:
        payload_index = len(ctor_arguments) - 1 if ctor_arguments else None
    if payload_index is None or payload_index == channel_ctor_arg:
        payload_argument = None
    else:
        payload_argument = _arg_at(ctor_arguments, payload_index)
    return channel_argument, payload_argument


def _verb_of(method: dict[str, Any], arguments: list[dict[str, Any]]) -> str | None:
    """D02 §2's two ways a `methods` row states the verb: `http_method` is a
    literal the catalog already knows (`postForObject` is always a POST, so
    the catalog states it once); `method_arg` is a position the call site
    carries instead (`exchange`'s verb is its own `HttpMethod` argument, an
    `enum`-kind entry) — the tail of the constant's symbol, after `#` and its
    trailing `.` (checkpoint-verified against the real emitted grammar:
    `org/springframework/http/HttpMethod#POST.` reads as `POST`).

    None where the declared `method_arg` slot holds anything else — a verb
    passed in as a parameter, the compiler's `unresolved`. The caller keeps
    the row with `method` NULL and `resolution: unresolved` (I2)."""
    literal = method.get("http_method")
    if literal is not None:
        return str(literal)
    arg = _arg_at(arguments, method.get("method_arg"))
    if arg is None or arg.get("kind") != "enum" or not arg.get("symbol"):
        return None
    return str(arg["symbol"]).rpartition("#")[2].removesuffix(".")
