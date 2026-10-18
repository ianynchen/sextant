"""`interface_implementation` engine for endpoint derivation (D02 §2's
`interface_implementation` style).

Unlike `single_call`/`fluent`, the boundary here is not one call's own
declaration but two facts joined together: a *registration* call site — the
framework binding a receiver to a channel, `Subscriber.newBuilder(name,
receiver)` — and, where the receiver is a named instance rather than a
lambda, that instance's own declared `interfaces` (D00 §5a's
`implemented_interfaces` capability). **The registration is the evidence**:
a class that implements the declared interface but is never handed to a
matching registration call derives nothing, exactly as D02 states — this
style needed no execute-terminal (fluent's `terminal`/`terminal_via_argument`) —
*wrong, and `registration.started_by` is the correction: construction subscribes
to nothing, so a registration whose framework requires a later activation call is
not a boundary until that call is reached (`OI-64`)*
because binding a receiver to a subscription already IS the intent a built,
unlogged HTTP request is not.

Framework knowledge — the interface, the registration owner+method, which
argument is the channel and which is the receiver — arrives as catalog data;
this module never names a framework."""

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, cast

from sextant.application.ports.catalogs import Catalog, CatalogError
from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.effective_calls import effective_call_sites
from sextant.application.resolve.open_questions import record_open_questions
from sextant.application.resolve.shapes.arguments import (
    _arg_at,
    channel_of_answer,
    valid_via_arity,
)
from sextant.application.resolve.shapes.rooting import catalog_symbols
from sextant.application.resolve.values import (
    ValueIndex,
    cached_value_index,
    resolve_site,
)
from sextant.domain.symbols import (
    bare_descriptor,
    method_name,
)

_REQUIRED_MATCHES = ("interface", "handler_method", "registration")

# The question a registration files when nothing in its own method activates it and
# the built object leaves the method (`OI-64`). Named for what is UNKNOWN, like every
# other kind in the closed set: not "this is dead", but "we cannot tell from here".
_REGISTRATION_ACTIVATION = "registration_activation"
_REQUIRED_REGISTRATION = ("owner", "method", "channel_arg", "receiver_arg")


def run(workspace: Workspace, catalog: Catalog) -> None:
    """Derives one row per resolved channel tuple, per registration call
    site — the same `call_endpoints` insert-if-absent every style uses
    (D02 §5). Rows are verbless (`method` always NULL) and carry no shape
    (`request_shape`/`response_shape` always NULL — `PubsubMessage` is a
    declared no-shape envelope, the `jakarta.jms.Message` precedent): the
    registration names an identity and, where readable, a handler, nothing
    more. `caller`/`peer` are always NULL — the row's own method is a
    `handler` (inbound only, D02 §2's `interface_implementation` example) and a destination is never
    split into a peer (§2d)."""
    _validate_matches(catalog)
    matches = catalog.matches
    # A LIST or a scalar (§3.1): the handler interface may be reachable under
    # more than one name. Plural, so any consumer left comparing with `==` fails.
    interface_symbols = catalog_symbols(
        matches["interface"], f"{catalog.source}: matches.interface"
    )
    handler_method = matches["handler_method"]
    registration = matches["registration"]
    # A LIST or a scalar (§3.1). Plural name, so a consumer still comparing with
    # `==` fails loudly rather than matching nothing.
    owners = registration_owners(catalog)
    method_name = registration["method"]
    channel_arg = registration["channel_arg"]
    receiver_arg = registration["receiver_arg"]
    implemented = _implemented_interfaces(workspace)
    method_symbols = _method_symbols(workspace)
    declarations = _declarations(workspace)

    # `arguments` arrives decoded, once per load, from the workspace
    # (`_DECODED_COLUMNS`) — every engine used to decode it again for itself.
    call_sites: list[dict[str, Any]] = effective_call_sites(workspace)
    by_caller: dict[str, list[dict[str, Any]]] = {}
    for site in call_sites:
        by_caller.setdefault(str(site["caller"]), []).append(site)

    started_by = _started_by_steps(registration)
    rows: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    # Only a row whose identity is known dedups (D02 §2's
    # unresolved-is-an-answer): two registrations whose channels nobody could
    # read carry nothing to compare, so each stays its own row — the key is
    # the identity columns, never the `resolution` column. `handler` is PART
    # of that identity, not decoration: two
    # registrations of the SAME channel by two DIFFERENT receivers — two
    # `@KafkaHandler`-shaped methods sharing one subscription is the real
    # precedent (`test_pipeline.py`) — are two distinct facts, and a key that
    # dropped `handler` would silently discard the second one. Duplicate
    # registrations of the SAME handler on the SAME channel still collapse,
    # exactly as every other style's own wire-identity dedup does.
    seen: set[tuple[str, str, str, str]] = set()
    # The walk's five-query fold, built AT MOST ONCE per run and only where a registration
    # was actually found (spec §3b's own guard shape: on `orders-quarkus` eight catalogs
    # declared `metadata_from` and zero walks ran). It costs 0.16 s on `mall-admin` —
    # more than walking every position in that corpus put together — so building it above
    # this loop would charge every module that declares none of this catalog's framework.
    index: ValueIndex | None = None
    # `call_sites` is already ordered `caller, ordinal` (NFR-1); filtering it
    # in place, rather than grouping by owner first, keeps that order.
    for site in call_sites:
        if not accepts_registration(site, owners, method_name):
            continue
        caller = str(site["caller"])
        # `cached_value_index`, not `value_index`: the fold is shared across every
        # engine and catalog in one resolve. Yesterday's measurement that justified
        # sharing it landed in `fluent` alone and was not carried here — the same
        # cross-engine miss `OI-143` records for the url reader, in the same file pair.
        if index is None:
            index = cached_value_index(workspace)
        # **The backward walk, in place of this engine's own copy of `single_call`'s
        # `channel_of`-then-`linked_channels`** (spec §2b, Task 7). The ladder it replaces
        # was two rungs, each capped at one hop: the literal at the declared position, then
        # ONE `source` link back to a `channel_via`-named call. `resolve_site` answers the
        # same position with no cap and no direction named per catalog — and where the
        # value came from a producer whose result is opaque, the identity table the loader
        # hoisted (`catalog.value_model`, §2) says which of that producer's arguments IS
        # the value. That is the same two statements `channel_via` welded together (§0b),
        # with the distance half now the walk's and the meaning half still catalog data.
        # **One tuple per distinct destination, not one per path.** Several paths are
        # several bindings by design (§1c) — several callers of the method that registers,
        # several returns of a callee it reads through — and they routinely AGREE about
        # this one slot while differing elsewhere. Two paths that both read `raw-notify`
        # are one destination; keeping them apart here would mint a second row for a
        # subscription declared once, and two paths that both read NOTHING would mint two
        # unresolved rows where the ladder this replaces minted one (an unresolved wire
        # identity never dedups downstream, so nothing else would collapse them). Order is
        # the walk's own, which is deterministic (NFR-1).
        destinations = _distinct(
            channel_of_answer(binding.slots.get(channel_arg))
            for binding in resolve_site(workspace, site, index, catalog.value_model)
        ) or [(None, None, "unresolved")]
        arguments = site["arguments"]
        # The activation conjunct, before the handler is resolved: an unstarted
        # registration is not a boundary, and resolving its handler would only make a
        # row we must not mint look better founded. It runs AFTER the destination
        # ladder because the question it may file names the channel.
        if started_by and _activation_of(site, by_caller.get(caller, []), started_by) != "started":
            unresolved.append(
                {
                    "protocol": catalog.protocol,
                    "method": None,
                    # The channel as this site resolved it, the walk and the identity
                    # table included — the fixture reaches its subscription through
                    # `ProjectSubscriptionName.of`, so reading the literal
                    # argument here would file every question against a
                    # null path and make them indistinguishable.
                    "path": next(
                        (path for _, path, _ in destinations if path is not None),
                        None,
                    ),
                    "question": _REGISTRATION_ACTIVATION,
                    "candidates": json.dumps(
                        [
                            {
                                "registration": f"{site['owner']}{site['name']}",
                                "enclosing": caller,
                                "activated_by": " then ".join(
                                    f"{s['owner']}.{s['method']}" for s in started_by
                                ),
                            }
                        ],
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    "evidence": (
                        "constructed, but nothing in this method completes the "
                        "activation chain — and a value that leaves the method by a "
                        "field store is invisible here, so this is 'we cannot tell' "
                        "rather than 'it is never started'"
                    ),
                }
            )
            continue
        receiver_argument = _arg_at(arguments, receiver_arg)
        handler = _handler_of(
            receiver_argument,
            handler_method,
            interface_symbols,
            implemented,
            method_symbols,
            declarations,
        )
        for peer, path, resolution in destinations:
            if path is not None:
                key = (catalog.protocol, catalog.direction, path, handler or "")
                if key in seen:
                    continue
                seen.add(key)
            rows.append(
                {
                    "protocol": catalog.protocol,
                    "direction": catalog.direction,
                    "method": None,
                    "path": path,
                    "handler": handler,
                    "caller": None,
                    "peer": peer,
                    "handler_signature": None,
                    "resolution": resolution,
                    "evidence": "compiler",
                    "catalog_id": catalog.id,
                    "request_shape": None,
                    "response_shape": None,
                    "consumes": None,
                    "produces": None,
                }
            )

    workspace.derive("call_endpoints", rows=rows)
    # Filed after the rows, so a registration that both derives and asks cannot have
    # its question written and its row lost to a later failure.
    record_open_questions(workspace, unresolved)


def registration_owners(catalog: Catalog) -> tuple[str, ...]:
    """The owner symbols this catalog's `registration` names, converted once — `run`'s own
    first read, named so that something other than `run` can ask the same question."""
    return catalog_symbols(
        catalog.matches["registration"]["owner"], f"{catalog.source}: registration.owner"
    )


def accepts_registration(site: Mapping[str, Any], owners: tuple[str, ...], method: str) -> bool:
    """Whether a call site is the registration this catalog describes.

    **Exposed rather than inlined so that a MEASUREMENT can ask production the question
    instead of re-asking it in its own words** (`scripts/measure_production_match.py`).
    The shadow reader over-matches on purpose — it models the keys, never the engines'
    reachability — so how much of what it asks about a consuming matcher would really
    accept is a question only the consuming matcher can answer, and Task 5 published a
    headline maximum from a corpus whose every site production refuses. One function, one
    caller in `run` and one in the script, so the two cannot drift."""
    return site["owner"] in owners and site["name"] == method


def _distinct(
    destinations: "Iterable[tuple[None, str | None, str]]",
) -> list[tuple[None, str | None, str]]:
    """The destination tuples, first occurrence kept and order preserved — a `dict` over
    a `set` for exactly that reason (NFR-1: two runs over one module derive one order)."""
    return list(dict.fromkeys(destinations))


def _handler_of(
    argument: dict[str, Any] | None,
    handler_method: str,
    interface_symbols: tuple[str, ...],
    implemented: dict[str, list[str]],
    method_symbols: dict[str, str],
    declarations: "_Declarations",
) -> str | None:
    """D02 §2's `interface_implementation` handler rule, resolved against the
    method symbols the facts actually carry: a `lambda`-kind receiver names
    its own synthetic body method (D00 §5a), an `instance`-kind receiver (a
    `NEW`-produced named class) names `<type>#<handler_method>` — but a call
    argument's own `symbol` is always the BARE descriptor, with no module
    coordinates, and an instance receiver's is the type's alone, with no
    signature. Neither is a symbol any fact ever emitted, so **both branches
    join** `method_symbols` (keyed by that same bare form) and write the
    module-prefixed symbol they found, verbatim — a `handler` that joined to
    no `symbols` row would be a column nothing else in the graph could ever
    follow.

    The instance branch resolves only when that type's own declared
    `interfaces` include the declared interface — **direct implementers
    only**: the fact carries a class's own interface table, never a
    superclass's, so this is a one-hop check by construction, not an
    explicit walk this function has to refuse.

    Anything else — no receiver captured, an `unresolved` kind, a registered
    instance whose type does not implement the interface, a receiver whose
    handler method no scanned document declares (the implementer lives
    outside the scanned module), or several same-named candidates nothing can
    tell apart (`_sole_handler`) — resolves to None: the subscription still
    derives (the row above), only its handler is unread, never fabricated.
    Since `A-M1` that sentence is true; before it, the last case published
    whichever overload's descriptor hash sorted first.
    """
    if argument is None:
        return None
    kind = argument.get("kind")
    if kind == "lambda":
        symbol = argument.get("symbol")
        return method_symbols.get(str(symbol)) if symbol is not None else None
    if kind == "instance":
        symbol = argument.get("symbol")
        if symbol is None:
            return None
        symbol = str(symbol)
        if any(name in implemented.get(symbol, []) for name in interface_symbols):
            # `symbol` already carries its own trailing `#` (D00 §5a's bare
            # descriptor form), so the descriptor searched for is
            # `<type>#<handler_method>(` without a second separator — a
            # prefix, not an equality, because the method symbol ends in the
            # signature hash the registration site never carries.
            prefix = f"{symbol}{handler_method}("
            candidates = [
                found for bare, found in method_symbols.items() if bare.startswith(prefix)
            ]
            return _sole_handler(candidates, handler_method, interface_symbols, declarations)
    return None


def _sole_handler(
    candidates: list[str],
    handler_method: str,
    interface_symbols: tuple[str, ...],
    declarations: "_Declarations",
) -> str | None:
    """Which of an implementing type's same-named methods IS the handler.

    **This used to take the first match in `method_symbols`' own symbol
    order** — a SHA-256 prefix of the descriptor — and the comment justifying
    it reasoned about the INTERFACE while the lookup ran against the
    implementing CLASS (`A-M1`). The interface declaring exactly one
    `receiveMessage` says nothing about how many the implementer declares:
    nothing stops a private helper, a convenience form or a javac bridge
    sitting beside it, and `ClassScanner.visitMethod` deliberately keeps all
    three. So the "tiebreak" was a hash-order coin flip between two methods,
    one of which is wrong — published at `resolved`/`compiler`, where nothing
    downstream can tell it from an observation, and part of this engine's own
    dedup key, so a wrong pick can also split or merge rows.

    JLS 8.4.2: a method's signature is its name AND its parameter types in
    order. So the selector is the pair, exactly as `supertype_dispatch._members`
    already resolves the same question (§8.1's language rule, and sweep 6
    clears that implementation as the reference one in this tree).

    Three cases, and the third is the one the old code got wrong:

    * ONE candidate — the overwhelmingly common shape, and the answer is
      unchanged from before this fix.
    * SEVERAL, and the interface is SCANNED and declares exactly one method of
      this name — its parameter types name which candidate implements it.
    * SEVERAL, and they cannot be told apart — the interface lives in a jar
      this scan never opened (every shipped catalog's does), or it declares
      overloads of its own. **None**, which is the unread handler `:172`
      already promises: the subscription still derives, only its attribution
      is absent. §8's "ambiguous evidence, produce nothing".

    A generic interface's javac BRIDGE carries the interface's own erased
    parameter types, so where the interface is scanned and generic the bridge
    is what the selector names rather than the real override. That is a
    narrower error than the coin flip it replaces and it is unreachable for
    every shipped catalog (whose interfaces are all library types), and it
    closes when this function reads `ACC_BRIDGE`, and it is now one column
    away: `methodModifiersJson` records `synthetic` with `ACC_BRIDGE` folded in,
    and `method_declarations` carries `modifiers` since OI-47. *This engine
    builds its own rows from that query and does not read the column yet* — the
    same shape of gap OI-47 was filed for, recorded rather than left implied.
    """
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        return None
    declared = [
        parameters
        for name in interface_symbols
        for symbol, parameters in declarations.by_type.get(name, [])
        if symbol == handler_method
    ]
    if len(declared) != 1:
        return None
    matched = [
        candidate
        for candidate in candidates
        if declarations.parameters.get(candidate) == declared[0]
    ]
    return matched[0] if len(matched) == 1 else None


@dataclass(frozen=True)
class _Declarations:
    """The parameter half of a method's signature (JLS 8.4.2), read once.

    `parameters` is keyed by the FULL symbol, because that is what
    `method_symbols` hands back as a candidate. `by_type` is keyed by the BARE
    enclosing type, because the interface a catalog names arrives through
    `_catalog_symbol` with no module coordinates — the same coordinate space
    `_implemented_interfaces` already normalises both its sides into.

    A method with no `signature` fact contributes an empty tuple rather than
    being absent: it is a declaration whose parameters could not be read, and
    an empty tuple can only ever match an interface method that genuinely
    takes none.
    """

    parameters: dict[str, tuple[str, ...]]
    by_type: dict[str, list[tuple[str, tuple[str, ...]]]]
    # The RETURN type's symbol per method, for `registration.started_by`: a method
    # that returns the type it just built is handing it to a caller this walk cannot
    # follow, which is the difference between "not a boundary" and "cannot tell from
    # here" (`_activation_of`). Absent where a method declares no signature.
    returns: dict[str, str]


def _declarations(workspace: Workspace) -> _Declarations:
    parameters: dict[str, tuple[str, ...]] = {}
    by_type: dict[str, list[tuple[str, tuple[str, ...]]]] = {}
    returns: dict[str, str] = {}
    for row in workspace.query("method_declarations"):
        symbol = str(row["symbol"])
        # `or {}`: the column may be SQL NULL, and it may also hold the JSON
        # literal `null` — a method fact written with no signature at all, which
        # every hand-built unit fact in this repo is — and the workspace decodes
        # both to `None`.
        signature = cast(dict[str, Any], row["signature"] or {})
        # `erased_symbol` — the DESCRIPTOR's own answer — because these tuples are
        # compared BETWEEN declarations: `_handler_for_interface` tests an
        # implementation's against the interface's. `type.symbol` is the signature's
        # answer where there is one, so a `Handler<E>` reads `E` and the class
        # implementing it reads the concrete type; a name scoped to one declaration
        # matches nothing in the other, and the handler attribution is lost outright.
        types = tuple(
            bare_descriptor(
                str(
                    parameter.get("erased_symbol")
                    or (parameter.get("type") or {}).get("symbol", "")
                )
            )
            for parameter in signature.get("parameters") or []
        )
        parameters[symbol] = types
        returned = (signature.get("returns") or {}).get("symbol")
        if returned:
            returns[symbol] = str(returned)
        enclosing = row["enclosing"]
        if enclosing is not None:
            name = method_name(bare_descriptor(symbol))
            by_type.setdefault(bare_descriptor(str(enclosing)), []).append((name, types))
    return _Declarations(parameters=parameters, by_type=by_type, returns=returns)


def _method_symbols(workspace: Workspace) -> dict[str, str]:
    """Every declared method symbol, keyed by its bare descriptor — the same
    module-prefix strip `_implemented_interfaces` applies below, for the same
    reason: a call argument's own `symbol` never carries the module
    coordinates, so the bare form is the only key the two sides share. The
    value is the symbol exactly as the fact wrote it, which is what a
    `handler` must be to join `symbols` at all."""
    return {
        bare_descriptor(str(row["symbol"])): str(row["symbol"])
        for row in workspace.query("method_symbols")
    }


def _implemented_interfaces(workspace: Workspace) -> dict[str, list[str]]:
    """Every class symbol's own directly declared interfaces (D00 §5a's
    `implemented_interfaces` capability), keyed by the type's bare
    descriptor — the form a `NEW`-produced `instance` argument's own
    `symbol` carries, never the module-prefixed identity the `implementations`
    query's own `symbol` column holds (the same stripping `supertypes_of`
    applies to its own rows, D02 §2h, for the same reason).

    CHECKPOINT FACT: each declared interface is itself module-prefixed in the
    real emitted fact (`ClassScanner`'s `interfaceSymbolsJson` runs every
    entry through the same `symbolOf` the class's own type symbol uses) —
    stripped here too, not only on the outer key, or a real registration's
    type would never be found to implement the catalog's declared
    interface."""
    return {
        bare_descriptor(str(row["symbol"])): [
            bare_descriptor(str(entry)) for entry in json.loads(str(row["interfaces"]))
        ]
        for row in workspace.query("implementations")
    }


def _validate_matches(catalog: Catalog) -> None:
    """Refuses a broken catalog before any call site is matched
    (`ports/catalogs.py`'s own discipline, the `single_call._validate_methods`
    precedent): a `matches` block missing `interface`/`handler_method`/
    `registration`, a `registration` missing one of its own required keys, or
    a malformed `channel_via` entry, is a broken file, not a degraded run."""
    matches = catalog.matches
    missing = [key for key in _REQUIRED_MATCHES if key not in matches]
    if missing:
        raise CatalogError(
            f"loading catalog {catalog.source}: `matches` is missing "
            f"{', '.join(missing)} — `interface_implementation` needs `interface`, "
            f"`handler_method` and `registration` (D02 §2's `interface_implementation` style)"
        )
    registration = matches["registration"]
    missing_registration = [key for key in _REQUIRED_REGISTRATION if key not in registration]
    if missing_registration:
        raise CatalogError(
            f"loading catalog {catalog.source}: `registration` is missing "
            f"{', '.join(missing_registration)} — `registration` needs `owner`, `method`, "
            f"`channel_arg` and `receiver_arg` (D02 §2's `interface_implementation` style)"
        )
    for entry in _channel_via_entries(registration):
        valid = (
            isinstance(entry, dict)
            and isinstance(entry.get("owner"), str)
            and isinstance(entry.get("method"), str)
            and (entry.get("arg") == "all_strings" or isinstance(entry.get("arg"), int))
            and valid_via_arity(entry)
        )
        if not valid:
            raise CatalogError(
                f"loading catalog {catalog.source}: `registration.channel_via` declares an "
                f'entry that must be `{{owner, method, arg: int|"all_strings", arity?: int}}`, '
                f"got {entry!r}"
            )


def _channel_via_entries(registration: dict[str, Any]) -> list[Any]:
    """`channel_via`'s `{owner, method, arg}` | `[{...}, ...]` grammar,
    normalized to a list without touching the entries themselves — the
    `single_call._channel_via_entries` precedent, shared in spirit rather
    than in code (this module owns its own `registration` shape, not a
    `methods` row)."""
    via = registration.get("channel_via")
    if via is None:
        return []
    return via if isinstance(via, list) else [via]


def _started_by_steps(registration: dict[str, Any]) -> list[dict[str, str]]:
    """`registration.started_by` — the calls that must FOLLOW a registration before it
    is a live boundary (D02 §2, GUIDELINES §8.6).

    **Why this key exists.** `Subscriber.newBuilder(subscription, receiver).build()` is
    CONSTRUCTION, and construction subscribes to nothing: messages arrive only once
    something calls `startAsync()`. Without this conjunct the catalog derived a live
    inbound endpoint from the construction alone — and our own acceptance fixture built
    two subscribers, started neither, and had both published as endpoints the test suite
    asserted were correct (`OI-64`).

    Each step is `{owner, method}`, applied in order, each linked to the previous by
    receiver-to-result within one method (D00 §5). Absent, the style behaves exactly as
    before: the registration alone is the evidence, which is right for a framework whose
    registration call IS the subscription.
    """
    declared = registration.get("started_by")
    if declared is None:
        return []
    if not isinstance(declared, list) or not declared:
        raise CatalogError("`registration.started_by` must be a non-empty list of steps")
    for step in declared:
        if not isinstance(step, dict) or not step.get("owner") or not step.get("method"):
            raise CatalogError(
                "each `registration.started_by` step names an `owner` and a `method`"
            )
    return declared


def _activation_of(
    site: dict[str, Any],
    caller_sites: list[dict[str, Any]],
    steps: list[dict[str, str]],
) -> str:
    """`started` when this registration's activation chain completes here, `unknown`
    otherwise.

    Follows the value the registration produced, forward through this method, looking
    for each declared step in order and skipping any number of intervening calls — a
    builder's configuration methods each return the builder again, so
    `newBuilder(sub, receiver).setParallelPullCount(2).build().startAsync()` is the
    ordinary spelling and the step being sought is arbitrarily far along. Every path is
    explored, not the first: `b.build(); b.build().startAsync();` starts the SECOND
    one, and a walk that committed to the first found nothing.

    **There are two answers, not three, and the third one was wrong.** An earlier
    version also returned `inert` — "built and dropped, provably not a boundary" —
    whenever no later CALL referred to the value. That is not proof. A subscriber
    assigned to a field leaves the method through `putfield`, which is not a call site
    and therefore not a fact this walk can see; `Shapes.buildsIntoField` was measured
    deriving nothing and asking nothing while `startsTheField` started it two methods
    away. GUIDELINES §8 permits exclusion only on proof, and "no call mentions this
    value" is inference — it cannot tell a discarded value from one the bytecode stored
    somewhere we do not read.

    So anything that is not demonstrably started is `unknown`, and the caller files a
    question. The cost is a question for the rare subscriber that really is built and
    thrown away; the alternative is silence for the common one that is stored in a
    field, and silence is the failure this whole change exists to remove.
    """
    if _completes(site.get("result"), caller_sites, steps):
        return "started"
    return "unknown"


def _completes(
    value: object, caller_sites: list[dict[str, Any]], steps: list[dict[str, str]]
) -> bool:
    """Whether some forward path from `value` matches every remaining step in order.

    Recursive over the steps and breadth-first over the value chain, because a value
    may be the receiver of several calls and only one of them leads anywhere: taking
    the first match is what made `b.build(); b.build().startAsync();` read as unstarted.
    """
    if not steps:
        return True
    # `catalog_symbols`, not `type_descriptor`: every other owner in this file accepts
    # a scalar OR a list (§3.1), and a `started_by` step that could not would be the one
    # key in the schema where naming a second spelling is impossible.
    owners = catalog_symbols(steps[0]["owner"], "registration.started_by[].owner")
    seen: set[Any] = set()
    frontier: list[object] = [value]
    while frontier:
        current = frontier.pop(0)
        if current is None or current in seen:
            continue
        seen.add(current)
        for other in caller_sites:
            if other.get("receiver") != current:
                continue
            if (
                str(other["owner"]) in owners
                and str(other["name"]) == steps[0]["method"]
                and _completes(other.get("result"), caller_sites, steps[1:])
            ):
                return True
            frontier.append(other.get("result"))
    return False
