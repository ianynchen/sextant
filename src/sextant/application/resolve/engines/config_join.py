"""`config_join` engine for endpoint derivation (D02 §2's `config_join`
style, reading §2d's two vocabularies).

The eighth style, and the first whose evidence is not a call site or an
annotation at all: **the code carries a name, and configuration says what
the name means** (D02 §2d). A declared bean's own name plus a
catalog-declared key template is an address; a module-level serializer class
under another declared key is a media type. Both halves read exactly one
input — the `resolved_config` table M04's pass 2 wrote (`resolve/config.py`)
— which is why this style is the first to name a PIPELINE-declared
capability in `requires` (D02 §1).

**The name has two sources** (D02 §2d, 2O design §5a). `bean_name` is the
original: a declared method's own name. `annotation_value` is the second: the
value of a named ARGUMENT on a named annotation — a channel name written on
the method the framework wires to that channel. The DESTINATION side is
identical for both and is still `resolved_config` alone; what differs is only
where the name being asked about comes from, and a name whose destination
configuration never answers is handled differently by each (`_derive_channels`
states why).

Three jobs, two of them here:

* `address_from_config` derives endpoint rows — one per selected binding —
  through the standard `call_endpoints` insert-if-absent every other style
  uses.
* `media_from_config` STAMPS `consumes`/`produces` onto rows other engines
  already minted, which is why this style runs LAST in the engine loop
  (`resolve/endpoints.py`, the `protocol_hint` ordering precedent, D02 §3):
  a stamp cannot enrich a row that does not exist yet.
* The third — peer resolution — is a named query (`resolved_peers`), never
  a write: endpoint rows keep their expressions, `resolved_config` keeps the
  values, and nothing here rewrites a row per environment.

`gaps` is not a fourth job and derives nothing: it is the `channel_destination`
hand-off an `annotation_value` catalog files for a name configuration never
answered, and it rides the `service_identity` seam rather than `run` because
the ledger is reset AFTER the engine loop (`resolve/pipeline.py`).

Framework knowledge — which key template names a destination, which
functional interface means which binding suffix and direction, which
serializer class means which MIME type, which binder name means which
protocol — is catalog data. No framework name appears in this module.
"""

import json
from typing import Any

from sextant.application.ports.catalogs import Catalog, CatalogError
from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.shapes.contracts import _payload_descriptor
from sextant.application.resolve.shapes.expansion import _enum_symbols, _rules_of
from sextant.application.resolve.shapes.rooting import catalog_symbols
from sextant.domain.closed_sets import Direction, Protocol
from sextant.domain.paths import canonical_http_path, serves_urls
from sextant.domain.symbols import bare_descriptor, method_name

_ADDRESS = "address_from_config"
_MEDIA = "media_from_config"
# The one placeholder a key template carries. A template names the binding
# it is asking about; everything else in the key is literal.
_BINDING = "{binding}"
# The two `binding.from` sources this engine implements. A catalog naming
# anything else is refused rather than silently read as one of them.
#
# `bean_name` (D02 §2d: "its bean name is the method's own name") was the
# only one until Task 9. `annotation_value` is the second: the name is the
# value of the argument `channels` declares, on the annotation `channels`
# declares. Measured before it was built on (§8.1) — the probe found those
# arguments reaching the fact stream verbatim, keyed by attribute name, on
# both the consuming and the producing side of one flow
# (`scripts/probes/spring-integration-destinations.md`, Q2/Q3).
_BEAN_NAME = "bean_name"
_ANNOTATION_VALUE = "annotation_value"
_BINDING_SOURCES = (_ANNOTATION_VALUE, _BEAN_NAME)
# `annotation_value`'s own rule list: one entry per `(annotation, argument)`
# pair the framework spells a name with, each carrying the direction that
# argument means. A framework uses more than one annotation and more than one
# attribute for this, and which attribute means which direction is exactly
# the knowledge that must stay in the catalog.
_CHANNELS = "channels"
# D01 §3's two media columns — the closed set `fills` may name.
_FILLABLE = ("consumes", "produces")
# The vocabulary's own default separators (D02 §2d): `selected_by` names a
# LIST of bindings, and one entry may itself COMPOSE several functions into
# a single binding. Both are declarable per catalog (`selection_separator`,
# `composition_separator`) — these are only what a catalog that states
# neither gets, so the two behaviours D02 §2d describes in prose have a
# spelling even before a second framework family declares its own.
_SELECTION_SEPARATOR = ";"
_COMPOSITION_SEPARATOR = "|"
# The 2K hand-off this style files (2G design §6's closed set, extended by 2O
# design §0 — `resolve/open_questions.py` is where the set lives and where a
# value outside it is refused).
_CHANNEL_DESTINATION = "channel_destination"
# The two REASONS a channel's destination went unanswered, kept apart because
# they are different facts and the trail is what a reader acts on: nobody was
# asked, versus somebody was asked and configuration did not answer with one
# value. Neither names a framework — the trail names the tables and the key
# this pass actually read, which is what the column is for.
_NO_KEY_TEMPLATE = (
    "this catalog declares no destination key template, so no configuration "
    "key names this channel's destination"
)
_NO_AGREED_VALUE = "resolved_config carries no value every environment agrees on for `{key}`"


def derives_rows(catalog: Catalog) -> bool:
    """Whether this catalog DERIVES endpoint rows rather than only enriching
    rows other catalogs derived — read by `resolve/endpoints.py`'s ordering
    (fix round 1, M-3), which must run every deriving `config_join` catalog
    before any purely stamping one.

    The reason is the same one that puts this whole style last: a stamp
    cannot enrich a row that does not exist yet. Left to the filename
    tiebreak, a stamping catalog sorting alphabetically ahead of a deriving
    one would silently skip every row that deriving catalog was about to
    write — no error, just a media column that stayed NULL for reasons
    nothing in the answer explains.

    Lives here, not in the registry: which `matches` block means "derives"
    is this style's own vocabulary, and `endpoints.py` names no catalog
    vocabulary of its own.

    **An address block is not enough, and the missing conjunct was a defect**
    (OI-1). `key` is what asks configuration where a name's destination is,
    and a catalog with no `key` can only ever answer NO channel: `run` reaches
    `_derive_channels`, which `continue`s on every name (`key` is optional for
    `annotation_value` alone, and its absence is that vocabulary's honest
    statement that the framework standardises no such key). Reading only the
    block said such a file DERIVES, which is what made `endpoints.py` demand a
    `protocol` of `spring-integration.yml` and put `amqp` on every question it
    files. The ordering half was harmless — a catalog writing no rows may sort
    anywhere — and the wire-identity half was not.

    Read defensively rather than after `_validate_matches`, because
    `endpoints.py` asks this BEFORE any engine runs: a malformed block is
    refused by `run`'s own validation, with the message that names the field."""
    address = catalog.matches.get(_ADDRESS)
    return isinstance(address, dict) and "key" in address


def run(workspace: Workspace, catalog: Catalog) -> None:
    """Runs whichever of D02 §2d's two vocabularies this catalog declares.

    Both blocks are optional and independent — a catalog may derive
    addresses, stamp media, or do both — but a `config_join` catalog
    declaring NEITHER is a broken file (it would run, read `resolved_config`,
    and produce nothing at all, which reads as "this framework configures
    nothing").
    """
    _validate_matches(catalog)
    if _ADDRESS in catalog.matches:
        if _binding_source(catalog) == _ANNOTATION_VALUE:
            _derive_channels(workspace, catalog)
        else:
            _derive_bindings(workspace, catalog)
    if _MEDIA in catalog.matches:
        _stamp_media(workspace, catalog)


def _binding_source(catalog: Catalog) -> str:
    """Which of `_BINDING_SOURCES` this catalog's address block names.

    Read through one accessor rather than indexed at each site: `run` and
    `gaps` both branch on it, and `_validate_matches` has already refused
    anything outside the pair, so neither caller repeats that check."""
    return str(catalog.matches[_ADDRESS]["binding"]["from"])


# --- job 1: addresses that live in configuration (D02 §2d) ----------------


def _derive_bindings(workspace: Workspace, catalog: Catalog) -> None:
    """One row per selected binding, inserted through the same
    `call_endpoints` derive every call-site style uses (D02 §5).

    Rows are verbless (`method` always NULL — a binding declares no
    HTTP-style verb), `evidence: compiler` (the bean's own declared type is
    what named the interface, and the configuration is a file the build
    itself carries), and carry this catalog's `catalog_id` like every other
    derived row.

    **`handler` versus `caller` follows D01 §3's direction rule, not the
    style**: an inbound binding's bean method is the row's `handler`
    (`caller` NULL); an outbound one's is its `caller` (`handler` NULL). The
    schema is explicit that "an outbound row carries `caller` with `handler`
    NULL", and a `Supplier`-shaped bean is exactly that — a producer.

    **`handler_signature` is deliberately NULL on every row this job
    derives**, the same as every `single_call`/`fluent` call-site row and
    every `reply` row: `derive_endpoint_contracts.sql`'s owner-keyed update
    fills a row's shapes from its own declared signature and is guarded on
    exactly that column, so a binding row carrying one would have the
    payload computed HERE (the functional interface's own type argument,
    which is the only place the wire payload appears) overwritten by a
    descriptor rooted at the functional interface itself — a `Consumer`
    reported as the thing on the wire. The row computes its own
    `request_shape` instead, and `shapes/contracts.py` harvests that column's
    roots back out for expansion, exactly as it does for the other
    pass-computed rows.
    """
    address = catalog.matches[_ADDRESS]
    binding = address["binding"]
    key_template = str(address["key"])
    suffix_rules = list(binding["suffix"])
    config = _config_values(workspace)
    candidates = _candidates(workspace, suffix_rules)
    entries = _selected_entries(config, binding, candidates)

    rules = _rules_of(catalog)
    enums = _enum_symbols(workspace)
    # `_payload_descriptor` requires an accumulator and this one is
    # DISCARDED, the `annotation_driven._derive_replies` precedent: what
    # carries these payloads into shape expansion is the `request_shape`
    # column itself, which `shapes/contracts.py` reads back through
    # `_shape_roots_of` for every row whose `handler_signature` is NULL.
    referenced: list[str] = []

    rows: list[dict[str, Any]] = []
    # Only a row whose identity is known dedups (the `single_call`/`fluent`
    # precedent): the composition row and a missing-key row both carry
    # `path` NULL and nothing to compare, so each stays its own row — a
    # dict keyed on the wire identity alone would silently collapse them
    # into one and lose whichever came second.
    seen: set[tuple[str, str, str]] = set()
    composition = str(binding.get("composition_separator", _COMPOSITION_SEPARATOR))
    for entry in entries:
        candidate = None if composition in entry else candidates.get(entry)
        if candidate is None:
            # Two ways an entry names no single readable bean, and both land
            # on the SAME degraded row — `path` NULL, `handler` AND `caller`
            # NULL, `unresolved`, the catalog's own declared direction, since
            # no functional shape was read to say otherwise:
            #
            # * a COMPOSED entry (D02 §2d): not decomposed, because guessing
            #   which half contributed the destination would be an invention;
            # * a GHOST entry (fix round 1, M-1): a name the selection states
            #   but no candidate answers to — a bean renamed, deleted, or of
            #   a shape this catalog's interfaces say nothing about.
            #
            # The ghost case used to derive nothing at all, which made the
            # most common real cause of it — configuration still selecting a
            # bean the code has since renamed — look exactly like a module
            # that never selected it. The configuration DID declare a
            # binding; that it names nobody is the finding, not a reason to
            # stay silent.
            rows.append(_row(catalog, catalog.protocol, catalog.direction, None, None, None))
            continue
        for suffix, direction, payload_arg in _rule_bindings(candidate.rule, catalog):
            name = entry + suffix
            protocol = _protocol_of(config, address, name, catalog)
            resolved = _agreed(config, key_template.replace(_BINDING, name))
            destination = None if resolved is None else _addressed(resolved, protocol, direction)
            if destination is not None:
                identity = (protocol, direction, destination)
                if identity in seen:
                    continue
                seen.add(identity)
            rows.append(
                _row(
                    catalog,
                    protocol,
                    direction,
                    destination,
                    candidate.symbol,
                    _request_shape(candidate.returns, payload_arg, rules, enums, referenced),
                )
            )

    workspace.derive("call_endpoints", rows=rows)


class _Candidate:
    """One bean method that matched a declared suffix rule: its own
    module-prefixed symbol (what a `handler`/`caller` must be to join
    `symbols` at all), the `returns` reference its payload roots from, and
    the rule that matched."""

    __slots__ = ("returns", "rule", "symbol")

    def __init__(self, symbol: str, returns: dict[str, Any], rule: dict[str, Any]) -> None:
        self.symbol = symbol
        self.returns = returns
        self.rule = rule


def _candidates(workspace: Workspace, suffix_rules: list[dict[str, Any]]) -> dict[str, _Candidate]:
    """Every declared method whose RETURN type matches one of the declared
    suffix rules, keyed by its bean name (D02 §2d: "its bean name is the
    method's own name", the framework default stated as data rather than
    re-derived).

    **Two readings of "matches", tried in that order** (D02 §2d: "a method
    whose return type IS, or implements, one of the declared interfaces"):
    equality against the declared interface's own descriptor first, then the
    `implemented_interfaces` join for a SCANNED type that declares it. The
    equality half is the one a declared library interface reaches — an
    interface the module does not itself compile has no symbol fact and can
    therefore never appear in any class's interface table — and the join
    half is what a module's own named implementation of a framework
    interface needs.

    First match wins on both axes: suffix rules are tried in declared order
    (a type implementing two of them is the catalog's ordering to state, not
    this engine's to arbitrate), and two methods sharing one bean name keep
    the first in `method_declarations`' own symbol order (NFR-1) — a real
    module declares one bean per name, so this is a tiebreak rather than a
    choice.
    """
    implemented = _implemented_interfaces(workspace)
    # A LIST or a scalar (§3.1): the interface a bean is recognised by may be
    # reachable under more than one name. One entry per name, so the search below
    # is unchanged — it already scans a list of candidates.
    declared = [
        (str(name), symbol, rule)
        for rule in suffix_rules
        for name, symbol in zip(
            _declared_names(rule["when"]["implements"]),
            catalog_symbols(rule["when"]["implements"], "config_join: when.implements"),
            strict=True,
        )
    ]
    found: dict[str, _Candidate] = {}
    for row in workspace.query("method_declarations"):
        signature = row["signature"]
        if signature is None:
            continue
        returns = json.loads(str(signature)).get("returns")
        if not isinstance(returns, dict) or returns.get("symbol") is None:
            continue
        returned = bare_descriptor(str(returns["symbol"]))
        rule = next(
            (
                rule
                for _, symbol, rule in declared
                if symbol == returned or symbol in implemented.get(returned, [])
            ),
            None,
        )
        if rule is None:
            continue
        symbol = str(row["symbol"])
        found.setdefault(method_name(bare_descriptor(symbol)), _Candidate(symbol, returns, rule))
    return found


def _declared_names(declared: object) -> tuple[str, ...]:
    """The dotted names a `when.implements` writes, in the order it wrote them —
    the dotted half of what `catalog_symbols` converts, kept beside it because the
    suffix search below matches on the DOTTED name and the symbol both.

    Any other shape falls through to `catalog_symbols`, which is the one place that
    refuses it, naming the file and the key."""
    if isinstance(declared, str):
        return (declared,)
    if isinstance(declared, list):
        return tuple(str(name) for name in declared)
    return ()


def _implemented_interfaces(workspace: Workspace) -> dict[str, list[str]]:
    """Every class symbol's own directly declared interfaces, keyed and
    valued by bare descriptor — the same strip, for the same reason, as
    `interface_implementation._implemented_interfaces`: a returned type's
    `symbol` on a signature reference never carries module coordinates, and
    each declared interface entry in the fact is itself module-prefixed."""
    return {
        bare_descriptor(str(row["symbol"])): [
            bare_descriptor(str(entry)) for entry in json.loads(str(row["interfaces"]))
        ]
        for row in workspace.query("implementations")
    }


def _selected_entries(
    config: dict[str, dict[str, str | None]],
    binding: dict[str, Any],
    candidates: dict[str, _Candidate],
) -> list[str]:
    """D02 §2d's `selected_by`: the configuration key that narrows the
    candidate set, read through `resolved_config`.

    **Absent — or declared but resolvable in no environment — every
    candidate binds**, the framework's own default, in the candidates'
    deterministic order. Present, the value's separator-split entries are
    the answer, in the order the value lists them, and a candidate the value
    never names derives nothing at all: selection is the only thing that can
    exclude a bean whose facts are otherwise identical to a selected one's.

    **An EXPLICITLY EMPTY selection selects nothing** (fix round 1, I-2) —
    an empty value, or separators alone, is a statement, not an absence, and
    the two must not collapse into the same answer.

    Where environments DISAGREE about the selection, the entries are unioned
    in environment order rather than one environment being picked: a bean
    selected in production binds in production, and an endpoint row is
    environment-neutral by design (D01) — it says a boundary exists, never
    which profile it exists under.
    """
    key = binding.get("selected_by")
    per_environment = config.get(str(key)) if key is not None else None
    if per_environment is None:
        return list(candidates)
    separator = str(binding.get("selection_separator", _SELECTION_SEPARATOR))
    entries: list[str] = []
    # Whether ANY environment resolved this key to a value at all — the
    # distinction fix round 1 (I-2) turns on. "Nobody said anything" and
    # "somebody said: nothing" are opposite statements, and only the first is
    # the framework default. A key declared but resolvable in no environment
    # (every row a `missing_key`) is still nobody saying anything, so it takes
    # the default; a key that resolved to an empty value, or to separators
    # alone, is an explicit select-NOTHING and must derive nothing. Falling
    # through to `candidates` there would bind every bean in the module
    # against a configuration that said the opposite — the one place this
    # engine could fabricate a boundary rather than degrade.
    stated = False
    for environment in sorted(per_environment):
        value = per_environment[environment]
        if value is None:
            continue
        stated = True
        for entry in value.split(separator):
            stripped = entry.strip()
            if stripped and stripped not in entries:
                entries.append(stripped)
    return entries if stated else list(candidates)


def _rule_bindings(rule: dict[str, Any], catalog: Catalog) -> list[tuple[str, str, int]]:
    """One suffix rule's `(suffix, direction, payload_arg)` triples.

    `then` is a suffix or a LIST of them — D02 §2d's "both halves at once"
    case, where one declared bean is an input and an output in the same
    breath and derives TWO rows rather than a single row whose direction
    cannot say which. `direction` and `payload_arg` are read in parallel:
    a scalar applies to every suffix, a list gives each suffix its own. The
    parallel-list form is what makes the both-halves case expressible as
    data — each half of a two-argument functional type carries a different
    payload position and a different direction, and neither is derivable
    from the suffix string without the engine learning the framework's own
    naming convention.

    Defaults: the catalog's own declared `direction` where a rule states
    none, and payload position 0 — the single type argument a one-argument
    functional type carries.
    """
    then = rule["then"]
    suffixes = [str(entry) for entry in then] if isinstance(then, list) else [str(then)]
    directions = _parallel(rule.get("direction", catalog.direction), len(suffixes))
    payload_args = _parallel(rule.get("payload_arg", 0), len(suffixes))
    return [
        (suffixes[index], str(directions[index]), int(payload_args[index]))
        for index in range(len(suffixes))
    ]


def _parallel(value: Any, count: int) -> list[Any]:
    """A scalar repeated, or a list taken as written — `_validate_matches`
    has already refused a list of the wrong length."""
    return list(value) if isinstance(value, list) else [value] * count


def _request_shape(
    returns: dict[str, Any],
    payload_arg: int,
    rules: Any,
    enums: set[str],
    referenced: list[str],
) -> str | None:
    """The wire descriptor for the payload this binding carries — rooted
    from the functional type's own type ARGUMENT at the declared position,
    never from the functional type itself (which is machinery, not a
    payload).

    `request_shape` on both directions, the `reply` row precedent (D01 §3 as
    amended): an outbound row's payload is what it sends, and
    `response_shape` is reserved for a response the row actually receives —
    a binding has none.

    A raw functional type — no type arguments at all, or fewer than the
    declared position needs — leaves the column NULL: the payload is
    genuinely unread, and the shape rooting itself decides the rest (a
    declared envelope, a `void`).
    """
    arguments = returns.get("arguments") or []
    if payload_arg >= len(arguments):
        return None
    return _payload_descriptor(arguments[payload_arg], rules, enums, referenced)


def _protocol_of(
    config: dict[str, dict[str, str | None]],
    address: dict[str, Any],
    name: str,
    catalog: Catalog,
) -> str:
    """The protocol a binding speaks: read from configuration where the
    catalog declares where to look AND maps the configured name to a
    protocol, else the catalog's own declared default (D02 §2c — a match may
    resolve `protocol` differently from the file's default).

    Two declared keys, most specific first: the binding's own, then the
    module-wide default. A configured name absent from `binder_protocols`
    falls back to the catalog's default rather than inventing a protocol —
    an unmapped name is a gap to grow the catalog from, exactly as an
    unmapped serializer class is for the media half.
    """
    protocols = address.get("binder_protocols") or {}
    template = address.get("binder_key")
    configured = None
    if template is not None:
        configured = _agreed(config, str(template).replace(_BINDING, name))
    if configured is None and address.get("default_binder_key") is not None:
        configured = _agreed(config, str(address["default_binder_key"]))
    if configured is None:
        return catalog.protocol
    return str(protocols.get(configured, catalog.protocol))


def _addressed(raw: str, protocol: str, direction: str) -> str:
    """A resolved destination as the identity the row publishes — the §8 path
    seam, asked of THIS ROW's own protocol and direction.

    The Task 2 carry (2O plan, Task 9 step 4). `single_call` had the same
    shape and the same bug: its rows carry a per-row `direction` override
    while its seam asked `catalog.direction`, so the gate answered about a
    different row from the one being minted. Both halves of this style's
    identity are per-row too — `direction` comes from the suffix rule or the
    channel rule (`_rule_bindings`, `_channels`), `protocol` from the
    binder configuration (`_protocol_of`) — so `catalog.protocol` and
    `catalog.direction` are each merely the DEFAULT one of them may fall back
    to, and neither is what this gate is about.

    No shipped catalog reaches the canonicalizing branch today: `serves_urls`
    is inbound HTTP alone, and this style's shipped protocols are broker
    protocols. It is written against the ROW rather than left unwritten
    because the seam is a property of the address, and a style with two
    binding sources is now reachable from a catalog neither of the shipped
    two resembles.
    """
    return canonical_http_path(raw) if serves_urls(protocol, direction) else raw


def _row(
    catalog: Catalog,
    protocol: str,
    direction: str,
    path: str | None,
    symbol: str | None,
    request_shape: str | None,
) -> dict[str, Any]:
    """One binding row's fixed shape.

    `path` NULL is `unresolved` and nothing else: the binding was declared —
    the bean exists, the key was built — and the configuration simply never
    answered it. D02 §2d is explicit that this row is still recorded, so a
    partially-configured module does not read as a module with fewer
    boundaries.

    A resolved destination is written VERBATIM. This engine never interprets
    what it reads: a value still carrying a placeholder expression keeps that
    expression as its `path` (the phase-wide rule — rows keep expressions,
    `resolved_config` carries values, and the per-environment answer is the
    `resolved_peers` join's, never a rewritten row).
    """
    inbound = direction == Direction.INBOUND
    return {
        "protocol": protocol,
        "direction": direction,
        "method": None,
        "path": path,
        "handler": symbol if inbound else None,
        "caller": None if inbound else symbol,
        "peer": None,
        "handler_signature": None,
        "resolution": "resolved" if path is not None else "unresolved",
        "evidence": "compiler",
        "catalog_id": catalog.id,
        "request_shape": request_shape,
        "response_shape": None,
        "consumes": None,
        "produces": None,
    }


# --- job 1, the second binding source: `from: annotation_value` -----------


class _Channel:
    """One name a declared annotation argument carried: the name itself, the
    METHOD the annotation sits on, and the direction the catalog says that
    argument means."""

    __slots__ = ("direction", "handler", "name")

    def __init__(self, name: str, handler: str, direction: str) -> None:
        self.name = name
        self.handler = handler
        self.direction = direction


def _derive_channels(workspace: Workspace, catalog: Catalog) -> None:
    """One row per named channel whose destination configuration ANSWERED,
    and nothing at all for the rest.

    **The asymmetry against `_derive_bindings` is the point, not an
    inconsistency.** A bean-name binding whose key nobody answered still
    derives a row, because the BEAN is the declaration: it exists, the
    binding was declared, and only the address is unread (D02 §2d, "an
    unresolved address is not an absent endpoint"). A channel name is not a
    declaration of a wire — it names an in-process pipe, and whether that
    pipe reaches a broker at all is exactly what nobody answered. A row with
    `path` NULL would therefore assert a boundary no declaration in the
    module makes, which is §8's cardinal sin with the address column left
    honest. The channel is not dropped either: `gaps` files it as a
    `channel_destination` question, which is a hand-off with the channel name
    and the handler in it rather than a fabricated wire.

    Rows carry no `request_shape`. A channel annotation names a channel and
    nothing else — there is no functional type argument to root a payload
    from, and the annotated method's own signature is not one either (what a
    framework passes a channel handler is its own convention, and no probe
    has measured one), so both shape columns and `handler_signature` stay
    NULL rather than claiming a contract nobody read.
    """
    address = catalog.matches[_ADDRESS]
    template = address.get("key")
    config = _config_values(workspace)
    rows: list[dict[str, Any]] = []
    # Every row here has a known identity — a channel with no answered
    # destination derives nothing at all — so unlike `_derive_bindings` this
    # set can never hold the NULL-path rows that must not collapse.
    seen: set[tuple[str, str, str]] = set()
    for channel in _channels(workspace, catalog):
        if template is None:
            continue
        protocol = _protocol_of(config, address, channel.name, catalog)
        resolved = _agreed(config, str(template).replace(_BINDING, channel.name))
        if resolved is None:
            continue
        destination = _addressed(resolved, protocol, channel.direction)
        identity = (protocol, channel.direction, destination)
        if identity in seen:
            continue
        seen.add(identity)
        rows.append(_row(catalog, protocol, channel.direction, destination, channel.handler, None))
    workspace.derive("call_endpoints", rows=rows)


def _channels(workspace: Workspace, catalog: Catalog) -> list[_Channel]:
    """Every name a declared `channels` rule found, deterministically ordered.

    **The target must be a METHOD**, and that is a conjunct rather than
    housekeeping — the `scheduled_work._declarations` rule, one table over. An
    annotation that names a channel is `@Target`-legal on an ANNOTATION TYPE
    too, which is how a module composes its own stereotype; that declaration
    wires nothing to any channel, so publishing it would name a boundary
    against a type the framework never invokes and a handler nobody calls.

    **The value must be a non-empty STRING.** An argument the extractor
    recorded as an array, a nested annotation or a number is not a channel
    name, and spelling one as text would ask configuration about a name
    nobody wrote; an argument written empty is not a name either, and the key
    template built from it would carry an answer belonging to nothing.

    Nothing is resolved on the way in: a name still carrying a placeholder
    expression is asked about exactly as written, which is the phase-wide
    rule (rows keep expressions, `resolved_config` keeps values).
    """
    rules = catalog.matches[_ADDRESS]["binding"][_CHANNELS]
    by_annotation: dict[str, list[dict[str, Any]]] = {}
    for rule in rules:
        # A LIST or a scalar (§3.1): one rule reachable under several annotation
        # names files under each, which is what a dict keyed by symbol already
        # expects — the rule object itself is shared, not copied.
        for symbol in catalog_symbols(rule["annotation"], f"{catalog.source}: rule.annotation"):
            by_annotation.setdefault(symbol, []).append(rule)
    methods = {str(row["symbol"]) for row in workspace.query("method_symbols")}
    found: list[_Channel] = []
    seen: set[tuple[str, str, str]] = set()
    for row in workspace.query("annotations"):
        target = str(row["target"])
        if target not in methods:
            continue
        args = _annotation_arguments(row["args"])
        for rule in by_annotation.get(str(row["annotation"]), []):
            value = args.get(str(rule["arg"]))
            if not isinstance(value, str) or not value:
                continue
            direction = str(rule.get("direction", catalog.direction))
            if (value, direction, target) in seen:
                continue
            seen.add((value, direction, target))
            found.append(_Channel(value, target, direction))
    # Sorted here rather than relying on the `annotations` query's own order:
    # the order rows reach `call_endpoints` and the ledger is a property of
    # this pass (NFR-1), and two rules of one catalog may answer for the same
    # annotation fact.
    return sorted(found, key=lambda channel: (channel.name, channel.direction, channel.handler))


def gaps(workspace: Workspace, catalog: Catalog) -> list[dict[str, Any]]:
    """The `channel_destination` open questions this catalog's unanswered
    channels earn — one per `(channel, handler)` whose destination
    configuration did not give.

    **Why this is a `gaps` function and not a write inside `run`.** The ledger
    is emptied ONCE per resolve, from the pipeline, and that reset runs AFTER
    the engine loop (`resolve/pipeline.py`, `resolve/open_questions.py`'s own
    module docstring): a row written during `run` would be erased before
    anything read it, silently. Every shipped writer sits after the reset, and
    this one rides the same seam (`resolve/service_identity.py`).

    Inert for both other shapes, by construction rather than by an id list: a
    `media_from_config`-only catalog has no address block, and a `bean_name`
    catalog already answers its own unresolved bindings with a row (D02 §2d)
    — a question there would be a second record of a fact the endpoint table
    already carries.

    Called for every catalog of this style whatever the two gates said — the
    `service_identity` seam re-checks neither `requires` nor the dependency
    gate — and that costs nothing: this walk reads the same annotation facts
    `run` did, so a module that declares none of the catalog's annotations
    finds nothing here either.
    """
    _validate_matches(catalog)
    if _ADDRESS not in catalog.matches or _binding_source(catalog) != _ANNOTATION_VALUE:
        return []
    address = catalog.matches[_ADDRESS]
    template = address.get("key")
    config = _config_values(workspace)
    rows: list[dict[str, Any]] = []
    # One question per channel-and-handler pair, not per direction: the
    # question is "what destination does this channel carry", and a method
    # that both consumes from and publishes to one channel is still asking it
    # once.
    seen: set[tuple[str, str]] = set()
    for channel in _channels(workspace, catalog):
        key = None if template is None else str(template).replace(_BINDING, channel.name)
        if key is not None and _agreed(config, key) is not None:
            continue
        if (channel.name, channel.handler) in seen:
            continue
        seen.add((channel.name, channel.handler))
        rows.append(
            {
                "protocol": _protocol_of(config, address, channel.name, catalog),
                "method": None,
                # The channel name IS the identity this question is about;
                # there is no address, which is the whole question.
                "path": channel.name,
                "question": _CHANNEL_DESTINATION,
                # A list of dicts, the shape every other question kind and
                # every renderer arm uses (`egress/render/document.py`).
                "candidates": json.dumps(
                    [{"channel": channel.name, "handler": channel.handler}],
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                "evidence": _NO_KEY_TEMPLATE if key is None else _NO_AGREED_VALUE.format(key=key),
            }
        )
    return rows


def _annotation_arguments(raw: object) -> dict[str, Any]:
    """One annotation's arguments, decoded — an empty mapping where the fact
    carries none, which is what an annotation written with no arguments is
    (the `scheduled_work._arguments` precedent)."""
    if raw is None:
        return {}
    decoded = json.loads(str(raw))
    return decoded if isinstance(decoded, dict) else {}


# --- job 2: serializer media stamping (D02 §2d's `media_from_config`) -----


def _stamp_media(workspace: Workspace, catalog: Catalog) -> None:
    """Stamps each declared rule's media type onto the rows it names.

    The ENGINE computes the value and the SQL only applies it, the same
    division every Python-built derivation in this codebase keeps: agreement
    across environments and the class-to-MIME lookup are both decisions, and
    a decision belongs where the vocabulary is read.

    **Agreement is strict** (D02 §2d): every environment must carry the same
    resolved class. An environment that resolves a different class, and an
    environment that never resolved the key at all, both leave the column
    NULL — `consumes`/`produces` are single-valued, so a per-environment
    split cannot be folded into one column without inventing an answer
    neither environment gave. **An unknown class stamps nothing**: it is
    still in `resolved_config` for a later pass to read, and a class absent
    from `values` is a gap to grow the catalog from, not a guess.

    First-writer discipline lives in the SQL (`stamp_media.sql` only ever
    fills a column that IS NULL), so a row another evidence kind already
    answered is never overwritten by a module-level default.
    """
    media = catalog.matches[_MEDIA]
    values = media.get("values") or {}
    config = _config_values(workspace)
    for rule in media["rules"]:
        declared = _agreed(config, str(rule["key"]))
        if declared is None:
            continue
        mime = values.get(declared)
        if mime is None:
            continue
        on = rule["on"]
        workspace.derive(
            "stamp_media",
            column=str(rule["fills"]),
            # The same JSON-array-of-strings shape every other evidence kind
            # writes into these two columns (D01 §3): one declared type here,
            # since a module-level default is a single class.
            value=json.dumps([str(mime)]),
            protocol=str(on["protocol"]),
            direction=str(on["direction"]),
        )


# --- reading `resolved_config` -------------------------------------------


def _config_values(workspace: Workspace) -> dict[str, dict[str, str | None]]:
    """`resolved_config` as `key -> {environment: value}`, read once per job
    rather than once per lookup — the whole table is one small answer and
    every lookup below is a membership test against it.

    A value of `None` is an environment that has the key but could not
    resolve it (D01's unresolved-with-a-reason row); a key missing from the
    outer dict was never declared in any environment at all. Both are
    answers, and `_agreed` treats them the same way deliberately."""
    values: dict[str, dict[str, str | None]] = {}
    for row in workspace.query("resolved_config"):
        environments = values.setdefault(str(row["key"]), {})
        environments[str(row["environment"])] = None if row["value"] is None else str(row["value"])
    return values


def _agreed(config: dict[str, dict[str, str | None]], key: str) -> str | None:
    """The one value every environment gives `key`, or None.

    None means all four of "never declared", "declared but unresolved
    everywhere", "resolved in some environments only" and "resolved
    differently per environment" — deliberately one answer, because every
    column this feeds is single-valued and every one of those four cases is
    the same honest "configuration did not tell us one thing"."""
    per_environment = config.get(key)
    if not per_environment:
        return None
    distinct = set(per_environment.values())
    if len(distinct) != 1:
        return None
    return distinct.pop()


# --- catalog validation ---------------------------------------------------


def _validate_matches(catalog: Catalog) -> None:
    """Refuses a broken catalog before anything is read (the
    `interface_implementation._validate_matches` precedent): every value
    below reaches either a derived row's identity columns or a bound SQL
    parameter, where a typo is indistinguishable from an observation."""
    matches = catalog.matches
    if _ADDRESS not in matches and _MEDIA not in matches:
        raise CatalogError(
            f"loading catalog {catalog.source}: `matches` declares neither "
            f"`{_ADDRESS}` nor `{_MEDIA}` — a `config_join` catalog declares at "
            f"least one of D02 §2d's two vocabularies"
        )
    if _ADDRESS in matches:
        _validate_address(catalog, matches[_ADDRESS])
    if _MEDIA in matches:
        _validate_media(catalog, matches[_MEDIA])


def _validate_address(catalog: Catalog, address: Any) -> None:
    if not isinstance(address, dict) or not isinstance(address.get("binding"), dict):
        raise CatalogError(
            f"loading catalog {catalog.source}: `{_ADDRESS}` needs `key` and `binding` (D02 §2d)"
        )
    source = address["binding"].get("from")
    if source not in _BINDING_SOURCES:
        raise CatalogError(
            f"loading catalog {catalog.source}: `{_ADDRESS}.binding.from` must be one of "
            f"{', '.join(f'`{name}`' for name in _BINDING_SOURCES)} — the binding-name "
            f"sources this engine implements (D02 §2d)"
        )
    # `key` is required for `bean_name` and OPTIONAL for `annotation_value`,
    # and the split is a claim about the two sources rather than a relaxation.
    # A bean-name binding with no key template asks configuration nothing and
    # can then only ever derive the degraded rows below — a file that reads as
    # a whole framework's bindings and means none of them. A framework whose
    # channels have NO standard configuration key is a real case, and the
    # honest catalog for it declares none: it enumerates the names, derives
    # nothing, and files each one as a question. Requiring a key there would
    # force a template to be invented, which is a convention no framework
    # states.
    if source == _BEAN_NAME and "key" not in address:
        raise CatalogError(
            f"loading catalog {catalog.source}: `{_ADDRESS}` needs `key` and `binding` (D02 §2d)"
        )
    # Both per-binding templates take the same check (fix round 1, M-8):
    # `binder_key` is as per-binding as `key` is, and one missing placeholder
    # is the whole difference between "what does THIS binding speak" and "read
    # one key and answer it for every bean in the module". `default_binder_key`
    # is deliberately not in this list — it is the module-wide fallback, and
    # naming no binding is exactly what makes it that.
    for field in ("key", "binder_key"):
        template = address.get(field)
        if template is not None and _BINDING not in str(template):
            raise CatalogError(
                f"loading catalog {catalog.source}: `{_ADDRESS}.{field}` must carry the "
                f"`{_BINDING}` placeholder — a per-binding key template naming no "
                f"binding resolves the same answer for every bean (D02 §2d)"
            )
    binding = address["binding"]
    if source == _ANNOTATION_VALUE:
        channels = binding.get(_CHANNELS)
        if not isinstance(channels, list) or not channels:
            raise CatalogError(
                f"loading catalog {catalog.source}: `{_ADDRESS}.binding.{_CHANNELS}` must "
                f"be a non-empty list of rules (D02 §2d)"
            )
        for rule in channels:
            _validate_channel_rule(catalog, rule)
    else:
        suffix = binding.get("suffix")
        if not isinstance(suffix, list) or not suffix:
            raise CatalogError(
                f"loading catalog {catalog.source}: `{_ADDRESS}.binding.suffix` must be "
                f"a non-empty list of rules (D02 §2d)"
            )
        for rule in suffix:
            _validate_suffix_rule(catalog, rule)
    for name, protocol in (address.get("binder_protocols") or {}).items():
        _closed(catalog, f"{_ADDRESS}.binder_protocols.{name}", protocol, Protocol)


def _validate_channel_rule(catalog: Catalog, rule: Any) -> None:
    """One `channels` entry. Both halves are matched VERBATIM against a fact —
    the annotation's fully qualified name and the argument's attribute name —
    so a typo in either declines silently and forever, which is why they are
    checked for shape here and paired with a near-miss and a positive in the
    suite (§10)."""
    valid = (
        isinstance(rule, dict)
        and isinstance(rule.get("annotation"), str)
        and isinstance(rule.get("arg"), str)
    )
    if not valid:
        raise CatalogError(
            f"loading catalog {catalog.source}: every `{_ADDRESS}.binding.{_CHANNELS}` "
            f"entry must be `{{annotation: <type>, arg: <attribute>, direction: <direction>}}`, "
            f"got {rule!r}"
        )
    _closed(
        catalog,
        f"{_ADDRESS}.binding.{_CHANNELS}.direction",
        rule.get("direction", catalog.direction),
        Direction,
    )


def _validate_suffix_rule(catalog: Catalog, rule: Any) -> None:
    valid = (
        isinstance(rule, dict)
        and isinstance(rule.get("when"), dict)
        and isinstance(rule["when"].get("implements"), str)
        and "then" in rule
    )
    if not valid:
        raise CatalogError(
            f"loading catalog {catalog.source}: every `{_ADDRESS}.binding.suffix` "
            f"entry must be `{{when: {{implements: <type>}}, then: <suffix>|[<suffix>...]}}`, "
            f"got {rule!r}"
        )
    count = len(rule["then"]) if isinstance(rule["then"], list) else 1
    for field in ("direction", "payload_arg"):
        value = rule.get(field)
        if isinstance(value, list) and len(value) != count:
            raise CatalogError(
                f"loading catalog {catalog.source}: `{_ADDRESS}.binding.suffix` "
                f"declares {count} suffixes and {len(value)} `{field}` values — a "
                f"parallel list must name one per suffix (D02 §2d)"
            )
    for declared in _parallel(rule.get("direction", catalog.direction), count):
        _closed(catalog, f"{_ADDRESS}.binding.suffix.direction", declared, Direction)


def _validate_media(catalog: Catalog, media: Any) -> None:
    rules = media.get("rules") if isinstance(media, dict) else None
    if not isinstance(rules, list) or not rules:
        raise CatalogError(
            f"loading catalog {catalog.source}: `{_MEDIA}.rules` must be a non-empty list (D02 §2d)"
        )
    for rule in rules:
        valid = (
            isinstance(rule, dict)
            and isinstance(rule.get("key"), str)
            and isinstance(rule.get("on"), dict)
            and "protocol" in rule["on"]
            and "direction" in rule["on"]
        )
        if not valid:
            raise CatalogError(
                f"loading catalog {catalog.source}: every `{_MEDIA}.rules` entry "
                f"must be `{{key, fills, on: {{protocol, direction}}}}`, got {rule!r}"
            )
        if rule.get("fills") not in _FILLABLE:
            raise CatalogError(
                f"loading catalog {catalog.source}: `{_MEDIA}.rules` declares "
                f"`fills: {rule.get('fills')!r}` — one of {', '.join(_FILLABLE)} "
                f"(D01 §3's two media columns)"
            )
        _closed(catalog, f"{_MEDIA}.rules.on.protocol", rule["on"]["protocol"], Protocol)
        _closed(catalog, f"{_MEDIA}.rules.on.direction", rule["on"]["direction"], Direction)


def _closed(catalog: Catalog, field: str, value: Any, values: Any) -> None:
    """One catalog value against one of D00's closed sets — the same check
    the loader (`ingress/catalogs/yaml_source.py`) applies to a catalog's own
    top-level `protocol`/`direction`, applied here because these values live
    inside `matches`, which the loader carries through unread. A value
    outside a closed set is a mistake, and the file it came from is the only
    place it is still cheap to name (NFR-5)."""
    allowed = sorted(member.value for member in values)
    if value not in allowed:
        raise CatalogError(
            f"loading catalog {catalog.source}: `{field}: {value}` is not one of "
            f"{', '.join(allowed)} — D00's closed sets are closed (NFR-5)"
        )
