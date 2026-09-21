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
  uses. `indexed` (spec 2026-09-21 §7b) is the address block's third form and
  the first whose NAME is in configuration too: items under a list prefix,
  each with fields, one of them a list of predicates read through a
  catalog-named grammar — a route declared wholly in configuration.
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

The channel edge is data since spec 2026-09-21 §3b: `run` also writes one
`read_by` row per indexed channel to `channel_bindings` (`_derive_channels`),
so an engine that learns what FEEDS a channel can be joined to the handler
reading it (`resolve/channel_bindings.py`), and `gaps` asks only about a
channel no `fed_by` row names.

Framework knowledge — which key template names a destination, which
functional interface means which binding suffix and direction, which
serializer class means which MIME type, which binder name means which
protocol — is catalog data. No framework name appears in this module.
"""

import json
from typing import Any, cast

from sextant.application.ports.catalogs import Catalog, CatalogError
from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.config import _DEFAULT_PLACEHOLDERS
from sextant.application.resolve.dependencies import unmet_dependency
from sextant.application.resolve.shapes.contracts import _payload_descriptor
from sextant.application.resolve.shapes.expansion import _enum_symbols, _rules_of
from sextant.application.resolve.shapes.rooting import catalog_symbols, names_a_type
from sextant.domain.closed_sets import Direction, Protocol
from sextant.domain.paths import canonical_http_path, serves_urls
from sextant.domain.symbols import bare_descriptor, method_name

_ADDRESS = "address_from_config"
_MEDIA = "media_from_config"
# The third address form (spec 2026-09-21 §7b): `{prefix, item}` — items are the
# `<prefix>[N]` keys the config layer flattens a list to, and `item` says which fields
# to read and how. Every word in it is catalog data: the predicate names, the field
# order each one binds its positional arguments into, the positional-key prefix the
# framework spells (`positional`), and which names narrow WHO is served and are passed
# through. The engine knows one grammar, `shortcut` — `Name=a,b`, split on the first
# `=`, tokenised on `,` — and two ways a predicate gathers its positional arguments.
_INDEXED = "indexed"
_SHORTCUT = "shortcut"
_GATHER_LIST = "list"
_GATHER_LIST_TAIL_FLAG = "list_tail_flag"
_GATHERS = (_GATHER_LIST, _GATHER_LIST_TAIL_FLAG)
# The four requirement kinds the stash's readers know (`request_requirements.py`,
# the combinator's `_REQUIREMENT_KINDS`) — closed for the same reason `_FILLABLE` is.
_REQUIREMENT_KINDS = ("header", "query", "cookie", "param")
# The served any-path pattern a route naming no path serves (the DSL sibling's rule,
# spec §7 case 3 as ruled for the combinator: a host-only route serves every path).
_ANY_PATH = "/**"
_ENVIRONMENT_DIVERGENCE = "environment_divergence"
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
_BINDER_PROTOCOL = "binder_protocol"
_UNSELECTED_BINDING = "unselected_binding"
_UNCHOSEN = (
    "{count} candidates were found and the selection key names none of them, so which one "
    "this module binds was not read — the count taken here is over declared methods, not "
    "over registered beans, so it is not the count the framework takes either"
)
_UNMAPPED_BINDER = (
    "the configured binder `{binder}` is absent from this catalog's `binder_protocols`, "
    "so the protocol this binding speaks was not read"
)
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
# The two ends of the channel edge this engine touches (spec 2026-09-21 §3b): it WRITES
# `read_by` — a handler whose annotation names a channel — and READS `fed_by` in `gaps`,
# to ask only about a channel nothing fed. `sends_to` is the slot for later writers.
_READ_BY = "read_by"
_FED_BY = "fed_by"


def writes_only_the_channel_edge(catalog: Catalog) -> bool:
    """Whether this catalog's whole effect on the engine loop is the `read_by`
    end of the channel edge (spec 2026-09-21 §3b): an annotation-valued
    address block with no `key` — so `_derive_channels` mints no row — and no
    media block to stamp. Read by `resolve/endpoints.py`'s ordering, which
    runs such a catalog FIRST.

    The style runs last so that its rows meet the insert-if-absent guard after
    every observing engine has written, and its stamps reach rows that already
    exist; a catalog with neither has nothing to order after them (`derives_rows`
    already says such a file "may sort anywhere"). It has one thing to order
    BEFORE them: the names it writes are what a bean-resolving engine reads to
    tell a channel a handler subscribes to from a parameter name that is
    nothing (spec §3a's name rung, `fluent._READ_BY`), and that engine runs
    in the same loop. `gaps` is unaffected: it runs from the `service_identity`
    seam, after everything.

    The shipped channel index (`spring-integration.yml`) is exactly this shape.
    A channels catalog that ALSO declares a `key` keeps its last turn — its
    rows must — and its names reach no engine that ran before it: stated here
    as the boundary, with no shipped instance."""
    address = catalog.matches.get(_ADDRESS)
    if (
        not isinstance(address, dict)
        or "key" in address
        or _MEDIA in catalog.matches
        or _INDEXED in catalog.matches
    ):
        return False
    binding = address.get("binding")
    return isinstance(binding, dict) and binding.get("from") == _ANNOTATION_VALUE


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
    if isinstance(catalog.matches.get(_INDEXED), dict):
        # The third form always mints rows: its items ARE the declarations.
        return True
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
    if _INDEXED in catalog.matches:
        _derive_indexed(workspace, catalog)
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
            #
            # The BINDER is resolved for this row too. It used to take
            # `catalog.protocol` unconditionally, bypassing `_protocol_of`
            # entirely — so `definition: a|b` under an unmapped binder published
            # `protocol: kafka`, a wire nobody read, on the very path F2 §3.4
            # says removes the default "entirely". Its `path` is NULL so it never
            # linked by address, which is the only reason that was not the same
            # defect as the row above; the column was wrong all the same.
            degraded = _protocol_of(config, address, entry, catalog)
            if degraded is None:
                continue
            rows.append(_row(catalog, degraded, catalog.direction, None, None, None))
            continue
        for suffix, direction, payload_arg in _rule_bindings(candidate.rule, catalog):
            name = entry + suffix
            protocol = _protocol_of(config, address, name, catalog)
            if protocol is None:
                # The configured binder maps to no protocol, so the WIRE is
                # unread. No row: `gaps` files a `binder_protocol` question
                # instead, which says the binding exists and its protocol did
                # not resolve — where a row would have asserted a wire nobody
                # read (F2 §3.4).
                continue
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
        signature = cast(dict[str, Any] | None, row["signature"])
        if signature is None:
            continue
        returns = signature.get("returns")
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
    """The dotted names a `when.implements` writes, in the order it wrote them.

    Paired with `catalog_symbols`'s output one-for-one so a list produces one
    `declared` entry per name. The dotted half of each pair is NOT read — the
    search below unpacks `for _, symbol, rule in declared` — and it predates
    §3.1; it is carried here rather than dropped because dropping an unread
    element of a shipped tuple is a separate change from widening the key, and
    is recorded as such.

    Any other shape falls through to `catalog_symbols`, which is the one place
    that refuses it, naming the file and the key."""
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


# F2 §3.4's cardinality conjunct: what binds when the selection key names
# nobody. `all` is every candidate; `sole` is the one candidate where there is
# exactly one, and NOTHING where there are several.
_UNSELECTED = "unselected_binds"
_ALL = "all"
_SOLE = "sole"
_UNSELECTED_VALUES = (_ALL, _SOLE)


def _unselected(binding: dict[str, Any], candidates: dict[str, _Candidate]) -> list[str]:
    """Which candidates bind when the selection key names nobody.

    Defaults to `all`, which is what this engine did before the conjunct existed
    — the default is the old behaviour, so declaring the key is what changes a
    catalog rather than the reverse.

    `sole` mirrors a framework that binds a lone candidate implicitly and refuses
    to choose between several. That is not a policy this engine invents: Spring
    Cloud Function's own `normalizeFunctionDefinition` opens its guard with
    `eligibleFunction.size() == 1`, and `FunctionBindingRegistrar` then binds only
    a definition with text, so with two eligible functions nothing binds
    (`scripts/probes/w13_stream_binding.md`).

    **Two or more under `sole` bind nothing HERE and earn a question**, and the
    reason is a mismatch this engine cannot close on its own. The framework counts
    registered BEANS; `_candidates` counts every declared method whose return type
    is one of the declared interfaces — no `@Bean` conjunct exists yet
    (`docs/COVERAGE.md` records the over-count). Those are different sets, so a
    count taken here is not the count the framework takes.

    The first version of this rule suppressed silently, on the reasoning that "the
    framework binds nothing, so no row is the complete answer". That reasoning
    needed our count to EQUAL the framework's, and it does not: measured, one real
    `Consumer` bean beside one ordinary helper method returning `Function` derived
    nothing at all, where the framework binds the bean. It traded a known
    over-report for an unknown silent under-report, which is the worse of the two
    by §8 — an absent row that nothing explains cannot be told from a module that
    has no such boundary.

    So the caller files one `unselected_binding` question naming every candidate.
    Not a guess, not a fabricated row, and not silence.
    """
    declared = binding.get(_UNSELECTED, _ALL)
    if declared not in _UNSELECTED_VALUES:
        raise CatalogError(
            f"`{_UNSELECTED}: {declared!r}` is not one of {list(_UNSELECTED_VALUES)} "
            f"(F2 §3.4). `all` binds every candidate when the selection key names nobody; "
            f"`sole` binds one candidate only where there is exactly one."
        )
    if declared == _ALL or len(candidates) == 1:
        return list(candidates)
    return []


def _suppressed_by_cardinality(
    config: dict[str, dict[str, str | None]],
    binding: dict[str, Any],
    candidates: dict[str, _Candidate],
) -> list[str]:
    """The candidates `sole` declined to choose between, or nothing.

    Empty whenever the selection key ANSWERED — a module that named its function
    has no unanswered question — and whenever one candidate or `all` applies.
    """
    key = binding.get(_UNSELECTED, _ALL)
    if key != _SOLE or len(candidates) < 2:
        return []
    selected = binding.get("selected_by")
    if selected is not None and config.get(str(selected)) is not None:
        return []
    return sorted(candidates)


def _selected_entries(
    config: dict[str, dict[str, str | None]],
    binding: dict[str, Any],
    candidates: dict[str, _Candidate],
) -> list[str]:
    """D02 §2d's `selected_by`: the configuration key that narrows the
    candidate set, read through `resolved_config`.

    **Absent — or declared but resolvable in no environment — the CARDINALITY
    rule decides** (F2 §3.4, `unselected` below), and the two values it can take
    are the only two a framework has been observed to use. Present, the value's
    separator-split entries are the answer, in the order the value lists them,
    and a candidate the value never names derives nothing at all: selection is
    the only thing that can exclude a bean whose facts are otherwise identical
    to a selected one's.

    This used to read "absent — every candidate binds, **the framework's own
    default**", and that sentence named a framework as its authority while
    saying the opposite of what the framework does. Measured
    (`scripts/probes/w13_stream_binding.md`): Spring Cloud Function's
    `normalizeFunctionDefinition` defaults the definition only when
    `eligibleFunction.size() == 1`, so two beans and no definition bind NOTHING
    — while this bound both, one fabricated endpoint each.

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
        return _unselected(binding, candidates)
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
    return _payload_descriptor(arguments[payload_arg], rules, enums, referenced, rules.wrappers)


def _protocol_of(
    config: dict[str, dict[str, str | None]],
    address: dict[str, Any],
    name: str,
    catalog: Catalog,
) -> str | None:
    """The protocol a binding speaks: read from configuration where the
    catalog declares where to look AND maps the configured name to a
    protocol, else the catalog's own declared default (D02 §2c — a match may
    resolve `protocol` differently from the file's default).

    Two declared keys, most specific first: the binding's own, then the
    module-wide default.

    **A configured name absent from `binder_protocols` returns None**, and the
    caller drops the row and files a `binder_protocol` question (F2 §3.4). It
    used to fall back to the catalog's declared `protocol:`, described in place
    as "a gap to grow the catalog from, never a guessed protocol" — the
    parenthetical was false. Measured (`scripts/probes/w13_stream_binding.md`): a
    module whose binder is `rocketmq` derived a row on `kafka`, complete and
    confident, with no question anywhere saying the protocol had not been read.

    That is the one defect in this analysis that leaves the bundle. Protocol is
    IDENTITY and DR-5 gates linking on protocol equality, so the row links to
    Kafka endpoints in a service this module never speaks to, and fails to link
    to the ones it does — in a graph assembled from bundles this analysis never
    sees.

    NO configured name at all is a different answer and keeps the catalog's
    default: nothing was configured, so the catalog's own declaration is the
    only statement there is, which is D02 §2c's rule and not a fallback.
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
    mapped = protocols.get(configured)
    return None if mapped is None else str(mapped)


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


# --- job 1, the third address form: `indexed:` (spec 2026-09-21 §7b) ------


class _Predicate:
    """One predicate of an item, parsed and NOT yet interpreted: its name and its
    arguments as the framework's own definition holds them (CP-29 row 3: a name and
    a `Map<String, String>` of args, positional ones keyed `<positional>N`). `name` is
    None for a spelling the framework itself refuses — a shortcut with no `=`."""

    __slots__ = ("args", "name")

    def __init__(self, name: str | None, args: dict[str, str]) -> None:
        self.name = name
        self.args = args


class _Item:
    """One `<prefix>[N]` item: the values every environment agreed on, by field; the
    fields declared and resolved NOWHERE (a placeholder no environment answers —
    `unread`, rendered unresolved); and the keys environments answer DIFFERENTLY
    (`diverged` — no row, one question). Read once for `run` and `gaps` alike."""

    __slots__ = ("diverged", "index", "unread", "values")

    def __init__(self, index: int) -> None:
        self.index = index
        self.values: dict[str, str] = {}
        self.unread: set[str] = set()
        self.diverged: dict[str, dict[str, str | None]] = {}


def _indexed_items(
    config: dict[str, dict[str, str | None]], catalog: Catalog
) -> tuple[str, list[_Item]]:
    """Every item under the block's prefix, in index order, with only the fields the
    block reads — the predicate list and the peer field. `id`, `order`, `metadata` and
    `filters[…]` are not read: the served path is the predicate's, and a filter that
    rewrites it changes the UPSTREAM path (spec §7b's stated boundary). Each read key
    is settled across environments three ways — `_agreed`'s one answer, split (fix
    round 1): one value everywhere is the value; a value in SOME environments, or two
    values, is true divergence (`diverged` — `run` mints nothing for the item, `gaps`
    files the question); declared and unresolved EVERYWHERE — `uri: ${ORDERS_URL}`
    with no environment answering — is `unread`, and the field renders unresolved
    while the item's other rows are minted."""
    block = catalog.matches[_INDEXED]
    prefix = str(block["prefix"]) + "["
    predicates = str(block["item"]["predicates"]["field"]) + "["
    peer = str(block["item"]["peer"]["field"])
    items: dict[int, _Item] = {}
    for key, per_environment in config.items():
        if not key.startswith(prefix):
            continue
        close = key.find("].", len(prefix))
        if close < 0 or not key[len(prefix) : close].isdigit():
            continue
        index = int(key[len(prefix) : close])
        field = key[close + 2 :]
        if not (field.startswith(predicates) or field == peer):
            continue
        item = items.setdefault(index, _Item(index))
        distinct = set(per_environment.values())
        if len(distinct) > 1:
            item.diverged[key] = per_environment
        elif distinct == {None}:
            item.unread.add(field)
        elif distinct:
            item.values[field] = str(distinct.pop())
    return str(block["prefix"]), [items[index] for index in sorted(items)]


def _predicates_of(item: _Item, block: dict[str, Any]) -> list[_Predicate]:
    """The item's predicate list, in `[M]` order, each in either spelling: a scalar at
    `predicates[M]` is a shortcut string; `predicates[M].name` plus
    `predicates[M].args.<k>` is the map form, its args taken as written."""
    field = str(block["item"]["predicates"]["field"])
    positional = str(block["item"]["predicates"]["positional"])
    by_index: dict[int, _Predicate] = {}
    for key, value in item.values.items():
        if not key.startswith(field + "["):
            continue
        close = key.find("]", len(field) + 1)
        index = int(key[len(field) + 1 : close])
        rest = key[close + 1 :]
        if rest == "":
            by_index[index] = _shortcut(value, positional)
        elif rest == ".name":
            by_index.setdefault(index, _Predicate(None, {})).name = value
        elif rest.startswith(".args."):
            by_index.setdefault(index, _Predicate(None, {})).args[rest[len(".args.") :]] = value
    return [by_index[index] for index in sorted(by_index)]


def _shortcut(spelling: str, positional: str) -> _Predicate:
    """The `shortcut` grammar (CP-29 row 3): the name is everything before the FIRST
    `=` — none, and the framework refuses the definition, so the name is None here —
    and each `,`-separated token after it is a positional argument, trimmed, empties
    dropped, keyed `<positional>N` in order."""
    at = spelling.find("=")
    if at <= 0:
        return _Predicate(None, {})
    tokens = [token.strip() for token in spelling[at + 1 :].split(",")]
    return _Predicate(
        spelling[:at],
        {f"{positional}{n}": token for n, token in enumerate(t for t in tokens if t)},
    )


def _fields_of(
    predicate: _Predicate, rule: dict[str, Any], positional: str
) -> dict[str, list[str]] | None:
    """The predicate's arguments bound onto the rule's declared field order (CP-29 row
    7), or None where they cannot be read as one binding. Under `gather: list` /
    `list_tail_flag` the framework's normaliser reads `args.values()` and tests NO key
    (`ShortcutType$2`/`$3.normalize`, CP-29 row 7) — so EVERY argument is collected:
    the positional `<positional>K` by K, then the remaining keys in flattened order
    (`k[N]` by N, then by name — `args.patterns: [/a/**, /b/**]` reaches here as
    `patterns[0]`, `patterns[1]`; `args.pattern: /x/**` as one value under a key the
    framework would not have tested either), into a list under field 0. A map-form
    scalar is ONE value, never split on `,` (fix round 1: the split was unmeasured;
    the binder wraps a scalar in a one-element list).

    The tail flag is found by VALUE, not by position (fix round 2). The framework
    hands the LAST value to the flag when it parses as a boolean, but `resolved_config`
    carries no declaration order (`ORDER BY environment, key`; an OI for the docs
    round), so which value the author wrote last is unknowable here — the documented
    map form `{patterns: /foo/**, matchTrailingSlash: false}` sorts as `[false,
    /foo/**]` by key. So: among the gathered values, the one that is literally
    `true`/`false` (case-insensitive, as `Boolean.parseBoolean` reads it) is the flag
    (field 1) wherever it sits, and the rest are the list. Two or more boolean
    literals, or a boolean literal in a gather that has no tail flag, is a binding
    this engine cannot settle — None, never a choice. Without `gather` (`DEFAULT`)
    positional K is field K and a named key binds to its own field."""
    order = [str(name) for name in rule["args"]]
    gather = rule.get("gather")
    indexed = sorted(
        (int(key[len(positional) :]), value)
        for key, value in predicate.args.items()
        if key.startswith(positional) and key[len(positional) :].isdigit()
    )
    values = [value for _, value in indexed]
    fields: dict[str, list[str]] = {}
    if gather in _GATHERS:
        values.extend(
            value
            for _, value in sorted(
                (_flattened_order(key), value)
                for key, value in predicate.args.items()
                if not (key.startswith(positional) and key[len(positional) :].isdigit())
            )
        )
        flags = [value for value in values if value.lower() in ("true", "false")]
        if len(flags) > 1 or (flags and gather != _GATHER_LIST_TAIL_FLAG):
            return None
        if flags:
            fields[order[1]] = flags
            values = [value for value in values if value.lower() not in ("true", "false")]
        if values:
            fields[order[0]] = values
        return fields
    for n, value in enumerate(values):
        if n < len(order):
            fields[order[n]] = [value]
    for key, value in predicate.args.items():
        if key in order:
            fields[key] = [value]
    return fields


def _flattened_order(key: str) -> tuple[str, int]:
    """`(base, N)` for a flattened list key `base[N]`, `(key, -1)` for a bare one —
    the order the config layer wrote a list in (`ingress/read/yaml_config.py`)."""
    if key.endswith("]") and "[" in key:
        base, _, index = key[:-1].rpartition("[")
        if index.isdigit():
            return (base, int(index))
    return (key, -1)


def _derive_indexed(workspace: Workspace, catalog: Catalog) -> None:
    """One inbound row per (pattern × verb) and one outbound row per target, per item
    no environment answers differently. The rows carry no handler and no caller — a
    route declared in configuration dispatches to no method — so their identity is the
    address alone, and their requirements join the stash by `None == None`
    (`request_requirements._from_stash`). A predicate whose name the block does not
    read — neither the path, the verbs, a requirement nor a pass-through — narrows the
    served set in a way nothing here can read, and every row of that item says
    `unresolved` with the address it did read (§8: unresolved is an answer, invention
    is not); the framework's own refusal (a shortcut with no `=`) is the same answer;
    a predicate resolved in no environment is unread — the item's INBOUND rows say
    `unresolved` (the target is untouched: it was read), and where no pattern was read
    at all the path is NULL rather than the any-path pattern (nothing here names an
    address). A verb that is not one verb — a map-form scalar still carrying the
    grammar's `,` — is unread the same way: `method` NULL, the inbound row
    `unresolved` (the framework binds a method that matches nothing; publishing it as
    a verb would be a phantom). The target is written VERBATIM with `peer` NULL
    — a routing destination the framework resolves, kept whole (D02), exactly as the
    DSL sibling publishes it — or NULL and `unresolved` where no environment resolved
    it.

    Two items collapsing to ONE address (fix round 1; spec 2026-09-19 §4d, the
    combinator's `_shared` rule restated): two header-versioned routes on `/api/**`
    are two ways the framework may dispatch one address, and a request satisfying
    EITHER is served — so the row's requirements are those every alternative makes
    (an intersection, in the first item's order), and any unresolved alternative
    makes the row unresolved."""
    block = catalog.matches[_INDEXED]
    item_block = block["item"]
    predicates_field = str(item_block["predicates"]["field"]) + "["
    positional = str(item_block["predicates"]["positional"])
    path_rule, method_rule = item_block["path"], item_block["method"]
    requirement_rules: dict[str, dict[str, Any]] = item_block.get("requirements", {})
    pass_through = {str(name) for name in item_block.get("pass_through", [])}
    peer_field = str(item_block["peer"]["field"])
    peer_direction = str(item_block["peer"].get("direction", catalog.direction))
    inbound = str(Direction.INBOUND)
    config = _config_values(workspace)
    _, items = _indexed_items(config, catalog)
    # Insertion-ordered by wire identity: a later item on an address already minted
    # folds into the row rather than adding one or being dropped.
    minted: dict[tuple[str, str | None, str | int], _Minted] = {}
    for item in items:
        if item.diverged:
            continue
        patterns: list[str | None] = []
        verbs: list[str | None] = []
        requirements: list[tuple[str, str, str | None]] = []
        # `resolved` is the ITEM's: an unknown predicate name unsettles every row of it
        # (spec §7b). `served` is the inbound rows' alone: a predicate or a verb nobody
        # could read leaves the address in doubt and says nothing about the target.
        resolved = True
        served = not any(field.startswith(predicates_field) for field in item.unread)
        for predicate in _predicates_of(item, block):
            rule = (
                path_rule
                if predicate.name == path_rule["name"]
                else method_rule
                if predicate.name == method_rule["name"]
                else requirement_rules.get(str(predicate.name))
            )
            if rule is None:
                if predicate.name not in pass_through:
                    resolved = False
                continue
            fields = _fields_of(predicate, rule, positional)
            if fields is None:
                # A binding the engine could not settle (two flag literals, a flag
                # where none is declared): the address is in doubt, the target is not.
                served = False
            elif rule is path_rule:
                patterns.extend(fields.get(str(path_rule["args"][0]), []))
            elif rule is method_rule:
                for spelled in fields.get(str(method_rule["args"][0]), []):
                    if "," in spelled:
                        served = False
                    elif spelled not in verbs:
                        verbs.append(spelled)
            else:
                name = fields.get(str(rule["args"][0]))
                value = fields.get(str(rule["args"][1])) if len(rule["args"]) > 1 else None
                if name:
                    requirements.append((str(rule["kind"]), name[0], value[0] if value else None))
                else:
                    resolved = False
        if not patterns:
            patterns = [_ANY_PATH] if served else [None]
        for pattern in patterns:
            path = None if pattern is None else _addressed(pattern, catalog.protocol, inbound)
            for verb in verbs or [None]:
                _mint(minted, catalog, inbound, verb, path, resolved and served, requirements)
        if peer_field in item.unread:
            _mint(minted, catalog, peer_direction, None, None, False, [])
        target = item.values.get(peer_field)
        if target is not None:
            destination = _addressed(target, catalog.protocol, peer_direction)
            _mint(minted, catalog, peer_direction, None, destination, resolved, [])
    rows = [each.row for each in minted.values()]
    stash = [
        {
            "caller": None,
            "handler": None,
            "method": each.row["method"],
            "path": each.row["path"],
            "catalog_id": catalog.id,
            "kind": kind,
            "name": name,
            "value": value,
            "requirement": "required",
            "resolution": "resolved",
            "evidence": "compiler",
        }
        for each in minted.values()
        for kind, name, value in each.requirements
    ]
    workspace.derive("call_endpoints", rows=rows)
    if stash:
        workspace.derive("route_requirements_insert", rows=stash)


class _Minted:
    """One row on its way to `call_endpoints` and the requirements every item that
    collapsed onto it makes."""

    __slots__ = ("requirements", "row")

    def __init__(
        self, row: dict[str, Any], requirements: list[tuple[str, str, str | None]]
    ) -> None:
        self.row = row
        self.requirements = requirements


def _mint(
    minted: dict[tuple[str, str | None, str | int], _Minted],
    catalog: Catalog,
    direction: str,
    method: str | None,
    path: str | None,
    resolved: bool,
    requirements: list[tuple[str, str, str | None]],
) -> None:
    """Adds one row, or folds it into the row of the same identity: the requirements
    the two have in common, in the kept row's order (`combinator._shared`'s rule —
    only a demand every alternative makes is one the framework enforces at that
    address), and `unresolved` if either is. A row with no address never collapses
    (SQL's `NULL = NULL` is unknown, and each is its own unread declaration) and
    carries NO requirement (fix round 2): a demand on an address nobody read states
    nothing useful, and the requirements pass keys the stash on `path`, so two such
    rows' demands would both land on whichever one it read last."""
    resolution = "resolved" if resolved else "unresolved"
    # A NULL address is keyed by its own ordinal, so it never collapses.
    identity = (direction, method, len(minted) if path is None else path)
    kept = minted.get(identity)
    if kept is None:
        minted[identity] = _Minted(
            _indexed_row(catalog, direction, method, path, resolution),
            [] if path is None else list(requirements),
        )
        return
    kept.requirements = [each for each in kept.requirements if each in requirements]
    if not resolved:
        kept.row["resolution"] = "unresolved"


def _indexed_row(
    catalog: Catalog, direction: str, method: str | None, path: str | None, resolution: str
) -> dict[str, Any]:
    """`_row`'s shape with the verb the item's method predicate named and the
    resolution the item's predicates earned — the one place this style writes a
    resolved address under `unresolved`, because the address WAS read and the
    predicate beside it was not."""
    return {
        **_row(catalog, catalog.protocol, direction, path, None, None),
        "method": method,
        "resolution": resolution,
    }


def _indexed_questions(workspace: Workspace, catalog: Catalog) -> list[dict[str, Any]]:
    """One `environment_divergence` question per item some environment answers
    differently (spec §7b: a route that differs between environments is one question,
    no row) — keyed on the item's own prefix key, every disagreeing key and its
    per-environment values as the candidates, the shape `derived_resource.gaps` files
    for a base path."""
    config = _config_values(workspace)
    prefix, items = _indexed_items(config, catalog)
    rows: list[dict[str, Any]] = []
    for item in items:
        if not item.diverged:
            continue
        keys = sorted(item.diverged)
        rows.append(
            {
                "protocol": catalog.protocol,
                "method": None,
                "path": f"{prefix}[{item.index}]",
                "question": _ENVIRONMENT_DIVERGENCE,
                "candidates": json.dumps(
                    [
                        {"key": key, "values": dict(sorted(item.diverged[key].items()))}
                        for key in keys
                    ],
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                "evidence": f"{', '.join(f'`{key}`' for key in keys)} differs between environments",
            }
        )
    return rows


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

    **The same walk also writes the channel edge** (spec 2026-09-21 §3b): one
    `read_by` row per indexed channel — the handler, the direction the
    annotation's attribute means, and nothing about the wire, so `protocol` and
    `destination` are NULL and a feeder's row supplies both when the join pass
    finds one. Collected in this loop rather than in a second one so the
    annotation facts, the method symbols and `resolved_config` are each read
    once per run (GUIDELINES §8.7), and BEFORE the key-template gate below:
    the edge is written whether or not the catalog declares a `key`, and that
    is the point of the table — this catalog's destinations are not in
    configuration at all, so the only thing that can answer for a channel is
    an engine that read the adapter feeding it, and this edge is how that
    answer reaches the handler.

    The channel NAME on the edge is resolved on the way in, unlike the key
    lookup one line down, because the two ask different things. The key
    template asks configuration about the name AS WRITTEN — a project
    convention keyed on the spelling. The edge must carry the name the
    framework actually subscribes the handler to, which for a placeholder is
    the configured VALUE, or the feeder that read that value never joins
    (§0c B5).
    """
    address = catalog.matches[_ADDRESS]
    template = address.get("key")
    config = _config_values(workspace)
    placeholders = catalog.config_model.get("placeholders", _DEFAULT_PLACEHOLDERS)
    rows: list[dict[str, Any]] = []
    readers: list[dict[str, Any]] = []
    # Every row here has a known identity — a channel with no answered
    # destination derives nothing at all — so unlike `_derive_bindings` this
    # set can never hold the NULL-path rows that must not collapse.
    seen: set[tuple[str, str, str]] = set()
    for channel in _channels(workspace, catalog):
        name, resolution = _channel_name(config, placeholders, channel.name)
        readers.append(
            {
                "channel": name,
                "role": _READ_BY,
                "symbol": channel.handler,
                "protocol": None,
                "direction": channel.direction,
                "destination": None,
                "catalog_id": catalog.id,
                "resolution": resolution,
            }
        )
        if template is None:
            continue
        protocol = _protocol_of(config, address, channel.name, catalog)
        if protocol is None:
            # The same rule as the `bean_name` loop's, and reached the same way:
            # a configured binder the catalog maps to no protocol leaves the WIRE
            # unread, so no row. `gaps` files the question — its
            # `channel_destination` arm already runs for this shape, and
            # `_unmapped_binder_questions` covers the other.
            #
            # Unreachable for every shipped catalog of this shape today (none
            # declares `binder_protocols`), and written rather than asserted
            # away: the type says it can happen, and a shape that silently
            # published `None` as a protocol is exactly what this change exists
            # to stop.
            continue
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
    workspace.derive("channel_bindings_insert", rows=readers)


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


def channel_index(workspace: Workspace, catalog: Catalog) -> list[_Channel]:
    """`_channels` under its public name (spec 2026-09-21 §3a): the channel names a
    module's handlers subscribe to, which a bean-identity caller reads to resolve a
    channel reference by name — the container auto-creates a channel under any
    referenced name, so a name this index knows is a channel whether or not a method
    declares it. Each entry carries `name`, `handler` and `direction`."""
    return _channels(workspace, catalog)


def _channel_name(
    config: dict[str, dict[str, str | None]], placeholders: dict[str, str], raw: str
) -> tuple[str, str]:
    """The channel name the framework subscribes a handler to, and whether it was read:
    `(value, "resolved")` for a name whose every placeholder configuration answered
    with one value (`_agreed`), `(raw, "unresolved")` where any placeholder went
    unanswered, and `(raw, "resolved")` for a name carrying no placeholder at all —
    nothing was asked, so nothing went unanswered.

    The delimiters are the config model's, read as `resolve/config.py` reads them and
    defaulting as it defaults, never hard-coded here. An opening delimiter with no
    closing one is text, as it is there. A `default_separator` inside a placeholder
    splits the KEY off for the lookup and nothing more: a spelled default is not
    substituted when configuration does not answer, so such a name stays `unresolved`
    rather than resolving to a default this pass did not verify the framework applies
    under every layering — the conservative answer, revisited if a fixture spells one."""
    open_ = placeholders.get("open", "${")
    close_ = placeholders.get("close", "}")
    separator = placeholders.get("default_separator", ":")
    parts: list[str] = []
    index = 0
    while True:
        start = raw.find(open_, index)
        if start == -1:
            parts.append(raw[index:])
            break
        end = raw.find(close_, start + len(open_))
        if end == -1:
            parts.append(raw[index:])
            break
        key = raw[start + len(open_) : end].split(separator, 1)[0]
        value = _agreed(config, key)
        if value is None:
            return raw, "unresolved"
        parts.append(raw[index:start])
        parts.append(value)
        index = end + len(close_)
    return "".join(parts), "resolved"


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

    Inert for a `media_from_config`-only catalog by construction: it has no
    address block.

    A `bean_name` catalog answers most of its unresolved bindings with a row
    (D02 §2d), so a question there would duplicate what the endpoint table
    already carries — with ONE exception, which is why this function no longer
    returns early for that shape: a binding whose configured binder maps to no
    protocol produces NO row (F2 §3.4), because the wire it speaks is unread.
    That one earns a question, and without it the binding vanishes silently.

    A binding that binds nothing for CARDINALITY reasons earns none, and the
    distinction is worth stating because both produce no row. Where two or more
    candidates exist and the selection names nobody, the framework binds nothing
    — so "no row" is the complete and correct answer, not a gap. Where the
    binder maps to no protocol, the module DOES bind something and we cannot say
    on what wire. The first is knowledge; the second is a question.

    Called for every catalog of this style whatever the two gates said — the
    `service_identity` seam re-checks neither `requires` nor the dependency
    gate — and that costs nothing: this walk reads the same annotation facts
    `run` did, so a module that declares none of the catalog's annotations
    finds nothing here either.
    """
    _validate_matches(catalog)
    # The third form's questions ride beside whichever address arm follows (spec
    # 2026-09-21 §7b): one per item some environment answers differently.
    indexed = _indexed_questions(workspace, catalog) if _INDEXED in catalog.matches else []
    if _ADDRESS not in catalog.matches:
        return indexed
    if _binding_source(catalog) != _ANNOTATION_VALUE:
        return indexed + _bean_name_questions(workspace, catalog)
    address = catalog.matches[_ADDRESS]
    template = address.get("key")
    config = _config_values(workspace)
    placeholders = catalog.config_model.get("placeholders", _DEFAULT_PLACEHOLDERS)
    # A channel some engine FED (spec 2026-09-21 §3b) has its destination answered — the
    # join pass minted the row, or the feeder's own chain derived it — so the question
    # would ask a human for what the document states. Any direction and any protocol:
    # an outbound handler bean's edge says `outbound` and answers the channel just the
    # same. An `unresolved` feeder counts too: it both mints an `unresolved` row and
    # suppresses this question, so the human hand-off for that unread destination is the
    # feeding engine's own row, not a `channel_destination` question here. Keyed on the
    # name the framework uses, which for a placeholder-spelled channel is the configured
    # value the feeder read, never the handler's spelling.
    fed = {
        str(row["channel"]) for row in workspace.query("channel_bindings") if row["role"] == _FED_BY
    }
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
        name, resolution = _channel_name(config, placeholders, channel.name)
        if resolution == "resolved" and name in fed:
            continue
        if (channel.name, channel.handler) in seen:
            continue
        seen.add((channel.name, channel.handler))
        rows.append(
            {
                # NULL where the binder maps to no protocol: a question that
                # named one would assert the very thing it reports as unread.
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
    return indexed + rows


def _bean_name_questions(workspace: Workspace, catalog: Catalog) -> list[dict[str, Any]]:
    """The two questions the `bean_name` shape earns where `run` wrote no row
    (F2 §3.4): `binder_protocol`, and `unselected_binding`.

    **Gated on the module's build declaration, unlike this file's other `gaps`.**
    `record_service_identity_gaps` re-checks neither `requires` nor the dependency
    gate, which costs nothing for a `gaps` that re-walks the same facts `run`
    needed — but this one reads `method_declarations` and `resolved_config`, which
    a skipped catalog's module still has. Without the gate a module that declares
    no Spring Cloud Stream at all published a question asserting a binding
    exists, for a catalog the run explicitly declined; the skip message names the
    parent-POM case, which is exactly when configuration is present and the
    coordinate is not.

    `binder_protocol` carries the BINDING and the configured NAME — the two things
    a reader needs to close it: add the name to `binder_protocols` if that binder
    speaks a protocol D00 declares, or record why it does not.

    `protocol` on the question row itself is NULL, and that is the point of the
    whole change — a question that named a protocol would assert the very thing
    it says was unread.
    """
    if unmet_dependency(workspace, catalog) is not None:
        return []
    address = catalog.matches[_ADDRESS]
    binding = address.get("binding") or {}
    config = _config_values(workspace)
    rules = binding.get("suffix") or []
    candidates = _candidates(workspace, rules)
    entries = _selected_entries(config, binding, candidates)
    protocols = address.get("binder_protocols") or {}
    rows: list[dict[str, Any]] = [
        {
            "protocol": None,
            "method": None,
            "path": name,
            "question": _UNSELECTED_BINDING,
            "candidates": json.dumps(
                [{"candidate": name, "selected_by": str(binding.get("selected_by"))}],
                sort_keys=True,
                separators=(",", ":"),
            ),
            "evidence": _UNCHOSEN.format(count=len(candidates)),
        }
        for name in _suppressed_by_cardinality(config, binding, candidates)
    ]
    seen: set[tuple[str, str]] = set()
    composition = str(binding.get("composition_separator", _COMPOSITION_SEPARATOR))
    for entry in entries:
        candidate = None if composition in entry else candidates.get(entry)
        # A composed or ghost entry has no suffix rules to walk, so the BINDING
        # is the entry itself. Skipping those left the degrade row's own dropped
        # binder unquestioned — no row and no question, the silence this whole
        # change exists to remove.
        names = (
            [entry]
            if candidate is None
            else [entry + suffix for suffix, _d, _p in _rule_bindings(candidate.rule, catalog)]
        )
        for name in names:
            configured = None
            template = address.get("binder_key")
            if template is not None:
                configured = _agreed(config, str(template).replace(_BINDING, name))
            if configured is None and address.get("default_binder_key") is not None:
                configured = _agreed(config, str(address["default_binder_key"]))
            if configured is None or configured in protocols:
                continue
            if (name, configured) in seen:
                continue
            seen.add((name, configured))
            rows.append(
                {
                    "protocol": None,
                    "method": None,
                    "path": name,
                    "question": _BINDER_PROTOCOL,
                    "candidates": json.dumps(
                        [{"binding": name, "binder": configured}],
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    "evidence": _UNMAPPED_BINDER.format(binder=configured),
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
    if _ADDRESS not in matches and _MEDIA not in matches and _INDEXED not in matches:
        raise CatalogError(
            f"loading catalog {catalog.source}: `matches` declares none of "
            f"`{_ADDRESS}`, `{_INDEXED}` and `{_MEDIA}` — a `config_join` catalog declares at "
            f"least one of D02 §2d's vocabularies"
        )
    if _ADDRESS in matches:
        _validate_address(catalog, matches[_ADDRESS])
    if _INDEXED in matches:
        _validate_indexed(catalog, matches[_INDEXED])
    if _MEDIA in matches:
        _validate_media(catalog, matches[_MEDIA])


def _validate_indexed(catalog: Catalog, block: Any) -> None:
    """The third form's shape (spec 2026-09-21 §7b). Every value below reaches a
    derived row's identity, the stash, or the key match against `resolved_config`, so
    a misspelling is a silent miss or a wrong row: the one grammar and the two gather
    words are closed; a requirement's `kind` is one of the stash readers' four; the
    peer's direction is D00's; `args` is the field order a rule binds positional
    arguments into, so it is a non-empty list of names."""
    where = f"loading catalog {catalog.source}: `{_INDEXED}`"
    item = block.get("item") if isinstance(block, dict) else None
    if not isinstance(
        block.get("prefix") if isinstance(block, dict) else None, str
    ) or not isinstance(item, dict):
        raise CatalogError(f"{where} needs `prefix` and `item` (D02 §2d)")
    predicates = item.get("predicates")
    if (
        not isinstance(predicates, dict)
        or not isinstance(predicates.get("field"), str)
        or not isinstance(predicates.get("positional"), str)
        or predicates.get("grammar") != _SHORTCUT
    ):
        raise CatalogError(
            f"{where}.item.predicates must be `{{field, grammar: {_SHORTCUT}, positional}}` — "
            f"the one grammar this engine reads — got {predicates!r}"
        )

    def rule(name: str, declared: Any, *, kind: bool = False) -> None:
        shaped = (
            isinstance(declared, dict)
            and (kind or isinstance(declared.get("name"), str))
            and isinstance(declared.get("args"), list)
            and declared["args"]
            and all(isinstance(field, str) for field in declared["args"])
            and ("gather" not in declared or declared["gather"] in _GATHERS)
        )
        if not shaped:
            raise CatalogError(
                f"{where}.item.{name} must be `{{{'kind' if kind else 'name'}, args: [<field>, ...], "
                f"gather?: {' | '.join(_GATHERS)}}}` — got {declared!r}"
            )
        if declared.get("gather") == _GATHER_LIST_TAIL_FLAG and len(declared["args"]) < 2:
            raise CatalogError(
                f"{where}.item.{name}: `gather: {_GATHER_LIST_TAIL_FLAG}` needs two fields"
            )
        if kind:
            _closed_string(
                catalog, f"{_INDEXED}.item.{name}.kind", declared.get("kind"), _REQUIREMENT_KINDS
            )

    rule("path", item.get("path"))
    rule("method", item.get("method"))
    requirements = item.get("requirements", {})
    if not isinstance(requirements, dict):
        raise CatalogError(
            f"{where}.item.requirements must map a predicate name to `{{kind, args}}`"
        )
    for name, declared in requirements.items():
        rule(f"requirements.{name}", declared, kind=True)
    if not isinstance(item.get("pass_through", []), list):
        raise CatalogError(f"{where}.item.pass_through must be a list of predicate names")
    peer = item.get("peer")
    if not isinstance(peer, dict) or not isinstance(peer.get("field"), str):
        raise CatalogError(f"{where}.item.peer must be `{{field, direction?}}`, got {peer!r}")
    _closed(
        catalog,
        f"{_INDEXED}.item.peer.direction",
        peer.get("direction", catalog.direction),
        Direction,
    )


def _closed_string(catalog: Catalog, field: str, value: Any, values: tuple[str, ...]) -> None:
    if value not in values:
        raise CatalogError(
            f"loading catalog {catalog.source}: `{field}: {value}` is not one of "
            f"{', '.join(values)} (NFR-5)"
        )


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
        _validate_unselected(catalog, binding)
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
        and names_a_type(rule.get("annotation"))
        and isinstance(rule.get("arg"), str)
    )
    if not valid:
        raise CatalogError(
            f"loading catalog {catalog.source}: every `{_ADDRESS}.binding.{_CHANNELS}` "
            f"entry must be `{{annotation: <type>|[<type>, ...], arg: <attribute>, "
            f"direction: <direction>}}`, "
            f"got {rule!r}"
        )
    _closed(
        catalog,
        f"{_ADDRESS}.binding.{_CHANNELS}.direction",
        rule.get("direction", catalog.direction),
        Direction,
    )


def _validate_unselected(catalog: Catalog, binding: dict[str, Any]) -> None:
    """Refuses an `unselected_binds` value outside the closed pair, at LOAD time.

    `_unselected` also refuses it, and that was the only check — reached solely
    when a module's configuration failed to answer the selection key. So a typo
    shipped, behaved normally on every module that configured the key, and raised
    mid-derivation on one that did not. Shape is knowable without running
    anything, which is where it belongs.
    """
    declared = binding.get(_UNSELECTED, _ALL)
    if declared not in _UNSELECTED_VALUES:
        raise CatalogError(
            f"loading catalog {catalog.source}: `{_ADDRESS}.binding.{_UNSELECTED}: "
            f"{declared!r}` is not one of {list(_UNSELECTED_VALUES)} (F2 §3.4). `all` binds "
            f"every candidate when the selection key names nobody; `sole` binds one only "
            f"where there is exactly one, and files a question otherwise."
        )


def _validate_suffix_rule(catalog: Catalog, rule: Any) -> None:
    valid = (
        isinstance(rule, dict)
        and isinstance(rule.get("when"), dict)
        and names_a_type(rule["when"].get("implements"))
        and "then" in rule
    )
    if not valid:
        raise CatalogError(
            f"loading catalog {catalog.source}: every `{_ADDRESS}.binding.suffix` "
            f"entry must be `{{when: {{implements: <type>|[<type>, ...]}}, "
            f"then: <suffix>|[<suffix>...]}}`, "
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
