"""The engine registry and gating (D02 §2).

Adding a style is an engine function and a registry entry, and `_engine_for`
refuses any catalog naming a style that is not in it."""

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial

from sextant.application.boundary.observability import (
    SKIP_MISSING_CAPABILITY,
    SKIP_SUPERSEDED,
)
from sextant.application.boundary.vocabulary import kinds_fed_by
from sextant.application.ports.catalogs import Catalog, CatalogError
from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.capabilities import missing_capabilities
from sextant.application.resolve.channel_bindings import mint_channel_rows
from sextant.application.resolve.dependencies import _declared_coordinates, dependency_gate
from sextant.application.resolve.engines import (
    annotation_driven,
    combinator,
    config_join,
    derived_resource,
    error_advice,
    fluent,
    injected_client,
    interface_implementation,
    scheduled_chain,
    scheduled_work,
    schema_operations,
    single_call,
    supertype_derived,
    supertype_dispatch,
)
from sextant.application.resolve.shapes.rooting import catalog_symbols

# The styles that run after every call-site and annotation style, whatever
# their own declared direction (D02 §3). The `protocol_hint` precedent: a
# style that ENRICHES rows other engines minted — reclassifying one, stamping
# a declared media type onto one — cannot run before the rows exist, so its
# position is a property of the style, never a request the catalog file
# makes. `config_join` is the first of them to ship.
#
# `schema_operations` (2H design §3) is the second, for the same reason twice
# over. It stamps a declared response shape onto rows other engines minted, so
# it cannot precede them; and its own rows meet the insert-if-absent guard
# LAST on purpose — a schema states an operation, an annotation states the
# operation AND the code serving it, and running afterwards is the whole of
# what makes the annotation row the one that survives. First-writer agreement
# by ordering, with no second rule to keep in step.
#
# `derived_resource` (2O design §2b) is the third, for a reason that is its
# own: it derives rows nobody OBSERVED. A Spring Data REST route exists because
# the framework serves it, not because any code in the module declares it — so
# where a real controller serves the same URL, the OBSERVED row is the one that
# must survive, and `derive_call_endpoints.sql`'s insert-if-absent guard makes
# that true only if every observing style has already written. Running last is
# what turns "insert if absent" into "a prediction never displaces an
# observation". (2O design §2b also says "and BEFORE `config_join`". That half
# is NOT implementable and is not load-bearing — ruling R3: within this group
# the ranks below decide, and there is no per-style rank, so the two are
# ordered by `_derives_rows` and then by filename. They mint disjoint
# identities — HTTP routes versus messaging destinations — so their relative
# order changes no output.)
_RUNS_LAST = frozenset({"config_join", "schema_operations", "derived_resource"})

# Within the runs-last group, the same reason applies once more, one level
# down (fix round 1, M-3): a style whose catalogs may EITHER derive rows or
# only stamp them must run every deriving one first, or a stamp arrives
# before the rows it was meant to enrich and silently reaches none of them.
# The predicate lives on the engine — which `matches` block means "derives"
# is that style's own vocabulary, and this module names none. A style absent
# from this map has no such split, and every one of its catalogs ranks alike.
_DERIVES_ROWS: dict[str, Callable[[Catalog], bool]] = {
    "config_join": config_join.derives_rows,
}

# The one exception to running last, ahead of every other rank (spec
# 2026-09-21 §3a): a catalog whose only effect on the loop is the `read_by`
# end of the channel edge — the shipped channel index — runs FIRST, because
# an engine in this same loop reads those names to resolve a channel
# reference by parameter name (the fluent engine's bean fold), and a name
# written after that engine ran resolves nothing. Such a catalog mints no
# row and stamps nothing, so nothing that made the style run last applies to
# it. The predicate lives on the engine, as `_DERIVES_ROWS`' does: which
# blocks mean "only the edge" is that style's own vocabulary.
_WRITES_ONLY_THE_CHANNEL_EDGE: dict[str, Callable[[Catalog], bool]] = {
    "config_join": config_join.writes_only_the_channel_edge,
}

# The one style whose derivation runs once per resolve over every catalog of
# the style, with a per-catalog half at each catalog's turn (P-4). Named here
# because `derive_endpoints` calls the style's `stage` before the turns begin;
# `_ENGINES` maps the style to the turn's half. Which statement is worth
# staging is a measured property of the statement — its bind cost — and
# `annotation_driven.stage` carries the number.
_STAGED = "annotation_driven"


@dataclass(frozen=True)
class SkippedCatalog:
    catalog_id: str
    missing_capabilities: tuple[str, ...]
    # The boundary kinds this catalog would have fed had it run (spec 2026-10-22 §4b),
    # recorded here because the catalog is in hand and a bundle's reader will not have it.
    feeds: tuple[str, ...] = ()
    # WHICH gate skipped it, one of `observability.SKIP_CAUSES` (ruled 2026-10-22): the map
    # reads it to tell a framework simply not used from a gap, so it is data, never parsed
    # from `missing_capabilities`' prose. `None` only where nothing recorded one — a
    # skip read back from a `metadata.json` written before the field existed.
    cause: str | None = None


def _feeds(catalog: Catalog) -> tuple[str, ...]:
    """What `kinds_fed_by` says of this catalog. `Catalog` carries a `shape_model`'s three
    blocks resolved, not the model's name, so "names a shape model" is read as "has any of
    the three". A catalog could declare the blocks itself instead of naming a model, and
    would then feed `data-contract` all the same, since it expands shapes; none shipped
    does, so today the two readings select the same 70 catalogs."""
    return kinds_fed_by(
        catalog.style,
        catalog.direction,
        bool(catalog.serialization or catalog.nullability or catalog.known_types),
    )


def derive_endpoints(
    workspace: Workspace, catalogs: list[Catalog], capabilities: set[str]
) -> list[SkippedCatalog]:
    """Runs each catalog whose required capabilities are met, and reports the
    rest. A skipped catalog is never silent (M04, FR-17)."""
    return derive_endpoints_with_runs(workspace, catalogs, capabilities)[0]


def derive_endpoints_with_runs(
    workspace: Workspace, catalogs: list[Catalog], capabilities: set[str]
) -> tuple[list[SkippedCatalog], dict[str, int]]:
    """`derive_endpoints`, and also how many catalogs that RAN feed each kind — the other
    half of what the observability map needs (spec 2026-10-22 §4b): `not-observable` is
    "nothing that feeds this kind ran", which only the run count can say. Only kinds with
    a count appear."""
    # Every style is resolved before anything is written. A catalog naming an
    # engine that does not exist is a broken file, and a broken file must not
    # leave a half-emptied endpoints table behind it.
    engines = [
        (
            catalog,
            _bound(_engine_for(_wire_identity_checked(_shape_checked(catalog))), catalog, catalogs),
        )
        for catalog in catalogs
    ]
    # Emptied once, here, rather than once per catalog: D02 §5 has two
    # catalogs both matching and both producing endpoints, so a per-catalog
    # rebuild would leave only whichever ran last. Unconditional, so a resolve
    # in which every catalog is skipped still leaves an empty table rather
    # than the previous run's rows.
    workspace.derive("endpoints_reset")
    # The combinator's `route_requirements` stash (spec 2026-09-19 §4d), re-created here
    # for the same reason and at the same level: more than one catalog writes it during
    # this call, so a reset owned by an engine would erase whichever ran first, and a
    # resolve in which no route states a requirement leaves an empty table rather than
    # the previous run's rows. A TEMP table of this connection, so it lives exactly as
    # long as the resolve that reads it (`record_request_requirements`).
    workspace.derive("route_requirements_reset")
    # The channel edge (spec 2026-09-21 §3b), re-created here for the same reason again:
    # `config_join` writes its `read_by` end, and an engine that reads a channel's
    # destination (the fluent engine, from the spec's §4) writes its `fed_by` end, so
    # neither may own the reset, and a module naming no channel leaves an empty table.
    # Read by `mint_channel_rows` below and by `config_join.gaps` from the
    # `service_identity` seam, both on this connection.
    workspace.derive("channel_bindings_reset")
    # D02 §3: the merge runs once, after every engine, so this ordering does
    # not affect which rows it finds — it exists for determinism only (NFR-1):
    # inbound before outbound, filename breaking the tie within a direction,
    # which is the loader's own order.
    #
    # Some styles sort ahead of all of that, or rather behind it: a
    # `_RUNS_LAST` style enriches rows the other engines minted (above), so
    # its own declared direction says nothing about when it must run. Its rows
    # therefore face `derive_call_endpoints.sql`'s insert-if-absent guard
    # after every ANNOTATION and CALL-SITE style has written — which is a real
    # consequence and not an accident: a wire identity one of those catalogs
    # already recorded stays that catalog's row. (Not "last" outright: within
    # the runs-last group the ranks below decide, and two members of it are
    # ordered against each other by `_derives_rows` and then the tiebreaks,
    # exactly as any two catalogs are.)
    #
    # `_derives_rows` then orders WITHIN that group, for the same reason one
    # level down: a catalog that only stamps must not run before one that
    # still has rows to write, or the stamp reaches none of them (M-3).
    # Direction and filename stay the tiebreaks after both ranks, unchanged.
    ordered = sorted(
        engines,
        key=lambda pair: (
            not _writes_only_the_channel_edge(pair[0]),
            pair[0].style in _RUNS_LAST,
            _derives_rows(pair[0]),
            pair[0].direction != "inbound",
            str(pair[0].source),
        ),
    )
    skipped = []
    running = []
    for catalog, engine in ordered:
        missing = missing_capabilities(catalog, capabilities)
        if missing:
            skipped.append(
                SkippedCatalog(catalog.id, missing, _feeds(catalog), SKIP_MISSING_CAPABILITY)
            )
            continue
        # The second gate (2O design §2a, ruling R9), reported through the
        # same channel as the first: a style whose framework rule is
        # CONDITIONAL on a dependency must not derive for a module whose build
        # does not declare it, and must not degrade silently when the question
        # cannot be answered. `resolve/dependencies.py` states why this is a
        # property of the style rather than of every catalog.
        unmet = dependency_gate(workspace, catalog)
        if unmet is not None:
            cause, reason = unmet
            skipped.append(SkippedCatalog(catalog.id, (reason,), _feeds(catalog), cause))
            continue
        # The third gate (B/C Task 10 fix round 1): `detect.superseded_by`'s
        # negative twin of `detect.coordinates`. Two catalogs may read the
        # SAME evidence — JAX-RS's own annotations, which Quarkus REST
        # implements with — while their rules genuinely differ, and the
        # merge's insert-if-absent guard (`insert_endpoints.sql`) has no
        # notion of which catalog is more specific, only a filename
        # tie-break. Where the module's build records one of a catalog's
        # `detect_superseded_by` coordinates, the framework's own fact is
        # that the superseding artifact IS the implementation there, so this
        # catalog must not run at all rather than win — or lose — that race.
        superseded = _superseded_by(workspace, catalog)
        if superseded is not None:
            skipped.append(
                SkippedCatalog(
                    catalog.id, (f"superseded by {superseded}",), _feeds(catalog), SKIP_SUPERSEDED
                )
            )
            continue
        running.append((catalog, engine))
    # Both gates are asked before any engine runs, so that the staged style
    # below knows its whole batch up front. That moves no answer: each gate
    # reads the catalog and the fact tables only, and no engine writes those.
    #
    # P-4: the annotation-driven statement costs its SIZE at bind time (~50ms
    # for 1,300 lines, whatever the values) and ran once per catalog — 1.4s of
    # a 2.5s analyze. So every annotation-driven catalog that will run is
    # derived in ONE execution here, and `_ENGINES` maps the style to the
    # per-catalog half, which at each catalog's turn moves its rows into
    # `endpoints`. The turn is what keeps earlier-catalog-wins exact: the
    # call-site styles run BETWEEN annotation-driven catalogs in this order,
    # and a wire identity one of them minted in between still refuses a later
    # annotation-driven catalog's row, as it did when the whole statement ran
    # at that turn. A skipped catalog is not in the batch and contributes no
    # row; a batch with nothing in it stages nothing.
    annotation_driven.stage(
        workspace, [catalog for catalog, _ in running if catalog.style == _STAGED]
    )
    for catalog, engine in running:
        engine(workspace, catalog)
    # After every engine, because both ends of a channel edge must have been written
    # before the join can find a pair (spec 2026-09-21 §3b); before the drop below, so a
    # sibling module's channel rows are dropped like any other; and inside this call
    # rather than a pipeline step of its own, so the row set every later pass reads —
    # `apply_protocol_hints` first among them — is complete when `derive_endpoints`
    # returns, as it always was.
    mint_channel_rows(workspace, catalogs)
    # Once per resolve, after every catalog. F4 §5.2 (W24): a sibling module's own
    # rows are this module's to drop, never to publish.
    #
    # **A wire identity present in BOTH directions is no longer collapsed into one row**
    # (F5 §6.1, W27). It was, and the merged row asserted an identity nothing had
    # observed: measured on this repo's fixture, the `both` row for
    # `{http://orders.example.com/ws}placeOrderRequest` carried `peer:
    # ${soap.billing.uri}` — the module's own served operation and a call to the BILLING
    # service, published as one endpoint — and `POST /v1/orders` merged the module's own
    # handler with a call to `orders-loop`. The merge keyed on
    # `(protocol, method, path)` and `peer` is not part of endpoint identity (RC-5), so
    # a path this module serves collided with the same path anywhere else in the world.
    # The two rows now stand, and `record_self_exchange` asks the question instead.
    workspace.derive("borrowed_endpoints_drop")
    ran = Counter(kind for catalog, _ in running for kind in _feeds(catalog))
    return skipped, dict(ran)


def _superseded_by(workspace: Workspace, catalog: Catalog) -> str | None:
    """The FIRST of `catalog.detect_superseded_by`'s coordinates the module's
    build recorded, in the catalog's own declared order, or `None` when none
    apply — no superseding coordinates declared at all, or the build recorded
    none of them.

    Reads the module fact the SAME way `unmet_dependency` does
    (`_declared_coordinates`, `resolve/dependencies.py`), rather than a second
    query: a workspace recording no module fact at all answers "could not
    tell" there, and the honest answer here is the same — a catalog is never
    refused by a question nothing answered.
    """
    if not catalog.detect_superseded_by:
        return None
    declared = _declared_coordinates(workspace)
    if declared is None:
        return None
    for coordinate in catalog.detect_superseded_by:
        if coordinate in declared:
            return coordinate
    return None


def _writes_only_the_channel_edge(catalog: Catalog) -> bool:
    """Whether `catalog` is the channel index alone (`_WRITES_ONLY_THE_CHANNEL_EDGE`),
    and so runs before every engine that reads its names."""
    predicate = _WRITES_ONLY_THE_CHANNEL_EDGE.get(catalog.style)
    return predicate is not None and predicate(catalog)


def _derives_rows(catalog: Catalog) -> int:
    """The within-group sort rank: 0 for a catalog that derives rows, 1 for
    one that only enriches them. `False < True` sorts a deriving catalog
    first, which is the whole point.

    A NON-WIRE style is not part of this question and keeps rank 0: it writes
    into its own table and enriches nothing, so reordering it by a predicate
    about `endpoints` would move it for a reason that does not apply to it.
    Everything else reads the same predicate `_wire_identity_checked` does —
    one answer to "does this catalog mint endpoint rows", so the ordering and
    the wire-identity rule can never disagree about a catalog."""
    if catalog.style in _NON_WIRE:
        return 0
    return 0 if _derives_endpoint_rows(catalog) else 1


# The styles that derive into a table of their own rather than into
# `endpoints` (2O design §4).
_NON_WIRE = frozenset({"scheduled_work", "scheduled_chain", "error_advice"})


def _derives_endpoint_rows(catalog: Catalog) -> bool:
    """Whether THIS CATALOG mints rows into `endpoints` — the question the
    wire-identity rule is actually about (OI-1).

    Task 8 first asked it of the STYLE, which was the right rule read one
    level too coarsely: `config_join` is a style whose catalogs may or may
    not mint rows, and `spring-integration.yml` is one that does not. Keyed on
    the style alone, that file had to declare a `protocol` to load — so it
    declared `amqp`, and stamped it on every `channel_destination` question it
    filed, a Kafka- or JMS-fed channel's included. A catalog that derives no
    endpoint row has no wire identity to declare, whatever its style is
    nominally called.

    A style absent from `_DERIVES_ROWS` has no such split and every one of its
    catalogs mints rows; a NON-WIRE style mints none, by definition of the
    split 2O design §4 drew."""
    if catalog.style in _NON_WIRE:
        return False
    declared = _DERIVES_ROWS.get(catalog.style)
    return declared is None or declared(catalog)


# Every key §3.1 widened, as the path to it inside `matches`. A tuple element is
# a nested mapping; a `[]` element is a LIST of mappings, each of which carries
# the key. Written down here rather than derived, because the engines read them
# through their own local names and there is nowhere else all twenty meet.
_WIDENED_KEYS: tuple[tuple[str, ...], ...] = (
    ("owner",),
    ("interface",),
    ("supertype",),
    ("type_annotation",),
    ("field_annotation",),
    ("annotation",),
    ("container",),
    ("handler_annotation",),
    ("status_annotation",),
    ("no_repository_bean",),
    ("resource_annotation",),
    ("member_annotation",),
    ("registration", "owner"),
    ("mapping", "prefix_annotation"),
    ("reply", "annotation"),
    ("media_values", "owner"),
    ("roots", "[]", "owner"),
    ("steps", "[]", "owner"),
    ("address_from_config", "binding", "suffix", "[]", "when", "implements"),
    ("address_from_config", "binding", "channels", "[]", "annotation"),
    # W12's twenty-first. Added a wave after the other twenty and MISSED here,
    # which cost exactly what this list exists to prevent: a malformed value at
    # this key raised from inside the engine, after `endpoints_reset`, and took
    # the previous run's rows with it. It also kept the key out of
    # `test_every_widened_key_a_shipped_catalog_declares_honours_a_second_spelling`,
    # which iterates this tuple — so the SOAP half of W12 had no coverage in the
    # suite at all, only in a probe, and `scripts/check.sh` runs no probes.
    ("methods", "[]", "path_from_argument_type", "annotation"),
)


def _at(holder: object, path: tuple[str, ...]) -> list[tuple[str, object]]:
    """Every `(label, value)` a widened key's path reaches, or nothing where the
    catalog does not declare it. A `[]` step fans out over a list of mappings, so
    `roots[].owner` yields one pair per root."""
    if not path:
        return []
    key, rest = path[0], path[1:]
    if key == "[]":
        if not isinstance(holder, list):
            return []
        found = []
        for index, element in enumerate(holder):
            found += [(f"[{index}].{label}", value) for label, value in _at(element, rest)]
        return found
    if not isinstance(holder, dict) or key not in holder:
        return []
    if not rest:
        return [(key, holder[key])]
    return [(f"{key}.{label}", value) for label, value in _at(holder[key], rest)]


def _shape_checked(catalog: Catalog) -> Catalog:
    """Refuses a catalog whose declared shape the derivation cannot honour, and
    returns it otherwise. Two rules today: the widened type-name keys, and §3.5's
    `class_level` vocabulary.

    Both are here for the same reason, and it is the reason this function was
    renamed from `_owner_form_checked`. A check that lives inside an ENGINE runs
    after `endpoints_reset` — and worse, runs only when the catalog's
    capabilities are met, so a typo in a skipped catalog is not caught at all
    until the day the capability arrives. Shape is knowable without running
    anything, so it is checked before anything is written.

    Here, in the pre-flight, for the reason stated above `endpoints_reset`: each
    conversion otherwise happens inside an engine, which runs once the table has
    already been emptied — so a malformed key raised there left every previous
    run's endpoint gone and no new rows written. A broken file half-emptying the
    table is exactly what resolving every style up front exists to prevent.

    ALL of §3.1's widened keys, not `matches.owner` alone. The first version
    checked that one key and its docstring said the failure class was closed;
    it was reachable at all nineteen others, and reproducing it took setting
    `registration.owner` to `7` in `google-pubsub-subscriber.yml` — the refusal
    fired from inside `interface_implementation` with the previous run's rows
    already gone.

    Keys NOT listed are the ones §3.1 did not widen: their refusal still comes
    from `type_descriptor` at the read site, and a pre-flight for a form nothing
    may write is a check with no consumer (OI-53).
    """
    matches = getattr(catalog, "matches", None)
    mapping = matches.get("mapping") if isinstance(matches, dict) else None
    if isinstance(mapping, dict) and "class_level" in mapping:
        declared = mapping["class_level"]
        if declared not in ("prefix", "sibling"):
            raise CatalogError(
                f"loading catalog {catalog.source}: `mapping.class_level: {declared!r}` is not "
                f"one of ['prefix', 'sibling'] (F2 §3.5). `prefix` composes a class-level "
                f"address with each method's; `sibling` lets a method that names its own "
                f"destination stand alone. A typo falls through to the default and composes "
                f"silently, which is the failure the conjunct exists to stop."
            )
    for path in _WIDENED_KEYS:
        for label, declared in _at(matches, path):
            # An explicit `None` is "this catalog declares no such gate", which
            # several optional keys spell by writing the key with no value —
            # `jakarta-jws-client.yml` writes `prefix_annotation:` bare. The
            # engines already read that as absence; refusing it here would
            # refuse shipped catalogs for saying nothing.
            if declared is None:
                continue
            catalog_symbols(declared, f"{catalog.source}: matches.{label}")
    return catalog


def _wire_identity_checked(catalog: Catalog) -> Catalog:
    """Refuses a catalog whose declared wire identity does not match what it
    derives, and returns it otherwise.

    Here rather than in the loader for the reason `_engine_for` below is here:
    which catalogs derive wire rows is knowledge of this layer, and `ingress`
    may not import it. Both directions are refused, and both are real:

    * a catalog that MINTS endpoint rows and declares no protocol would bind
      SQL NULL into `endpoints.protocol` — a row with no protocol is a
      boundary nobody can address, and D01's wire identity is protocol-scoped,
      so it would also never merge or link. Every catalog written before 2O
      declares one, so this refuses a mistake rather than a shape that used to
      work.
    * a catalog that mints NONE and declares one is the failure this whole
      split exists to prevent: a `protocol` on a `scheduled_work` catalog is
      read by nothing — neither table has the column — and a `protocol` on a
      `config_join` catalog that mints no row reaches one place only, the
      `protocol` column of the open questions it files, where it is a guess a
      reader believes and no derivation honours. §5.3's "a name existing is
      not a mechanism existing".

    **The audit list this rule governs** (§8.3), which is why the message
    names the catalog rather than the style: the two NON-WIRE styles
    (`spring-scheduling.yml`, `spring-error-advice.yml`) and the two
    `config_join` catalogs that mint nothing — `spring-integration.yml`, which
    only files questions, and `spring-kafka-media.yml`, which only stamps
    columns other engines' rows already carry. Every other shipped catalog
    mints rows and declares both. `test_call_engines` runs every shipped
    catalog through `derive_endpoints`, so the list is checked rather than
    written down.
    """
    declared = catalog.protocol or catalog.direction
    if not _derives_endpoint_rows(catalog) and declared:
        raise CatalogError(
            f"loading catalog {catalog.source}: this catalog derives no endpoint rows, "
            f"so it must declare neither `protocol` nor `direction` — got "
            f"protocol={catalog.protocol!r}, direction={catalog.direction!r} (2O design §4)"
        )
    if _derives_endpoint_rows(catalog) and not (catalog.protocol and catalog.direction):
        raise CatalogError(
            f"loading catalog {catalog.source}: this catalog derives endpoint rows, "
            f"so it must declare both `protocol` and `direction` — got "
            f"protocol={catalog.protocol!r}, direction={catalog.direction!r} (D02 §1)"
        )
    return catalog


# The engines that read the RESOLVE's config model rather than their own catalog's, by
# style: both `scheduled_work` engines decide what a placeholder is (`config_model_of`).
_READS_THE_CONFIG_MODEL: dict[str, Callable[..., None]] = {
    "scheduled_work": scheduled_work.run,
    "scheduled_chain": scheduled_chain.run,
}


def _bound(
    engine: "Callable[[Workspace, Catalog], None]", catalog: Catalog, catalogs: list[Catalog]
) -> "Callable[[Workspace, Catalog], None]":
    """`engine`, handed every catalog of the resolve when its style reads the config model:
    which placeholder opener to read is the RESOLVE's config model, chosen across catalogs
    (`config_model_of`), and the engine's own catalog declares none."""
    if catalog.style in _READS_THE_CONFIG_MODEL:
        return partial(_READS_THE_CONFIG_MODEL[catalog.style], catalogs=catalogs)
    return engine


def _engine_for(catalog: Catalog) -> "Callable[[Workspace, Catalog], None]":
    """Resolves the engine for a catalog's declared style, or refuses it.

    A style with no engine is a broken catalog, not a degraded run. Capability
    gating reports what it skips; an unmatched style would produce no endpoints
    and no skip, which reads as "this framework exposes nothing" — the failure
    the reporting exists to prevent.
    """
    try:
        return _ENGINES[catalog.style]
    except KeyError:
        raise CatalogError(
            f"loading catalog {catalog.source}: `style: {catalog.style}` has no engine "
            f"— one of {', '.join(sorted(_ENGINES))} (D02 §2)"
        ) from None


# One entry per engine style D02 §2 declares and this codebase implements.
_ENGINES: dict[str, Callable[[Workspace, Catalog], None]] = {
    # The per-catalog HALF of the staged style (`_STAGED`): `derive_endpoints`
    # stages every annotation-driven catalog's rows in one statement before
    # the turns begin, and this moves one catalog's rows into `endpoints` at
    # its turn. `annotation_driven.run` — stage a batch of one, then insert —
    # is the entry for a caller that hands the engine a single catalog.
    "annotation_driven": annotation_driven.insert,
    "single_call": single_call.run,
    "fluent": fluent.run,
    "interface_implementation": interface_implementation.run,
    "combinator": combinator.run,
    "config_join": config_join.run,
    "schema_operations": schema_operations.run,
    # 2O design §1b/§1c (Task 5): both derive rows from their OWN evidence —
    # a supertype's own facts, an injected field's own annotation — rather
    # than enriching rows another engine minted, so neither belongs in
    # `_RUNS_LAST` above.
    "supertype_derived": supertype_derived.run,
    "injected_client": injected_client.run,
    # 2O design §3b (Task 7b): a third style deriving from its OWN evidence,
    # for the same reason as the two above — a type-level annotation, a
    # declared supertype and the members a class overrides are all facts of
    # the class itself, not rows another engine minted — so it stays out of
    # `_RUNS_LAST` too.
    "supertype_dispatch": supertype_dispatch.run,
    # 2O design §2 (Task 6): the first style that derives rows from a
    # FRAMEWORK RULE rather than from a declaration — see `_RUNS_LAST` above
    # for why it runs after every observing style, and
    # `resolve/dependencies.py` for the gate that decides whether the rule
    # applies to this module at all.
    "derived_resource": derived_resource.run,
    # 2O design §4 (Task 8): the two NON-WIRE styles. They are registered here,
    # and run inside `derive_endpoints`'s own loop, because everything that
    # loop does for a catalog applies to them unchanged — the style is resolved
    # before anything is written, capability gating and the dependency gate
    # report a skip through the same channel, and the ordering is the same
    # deterministic one. What they do NOT share is the table: each writes to
    # its own, so neither is affected by `endpoints_reset` or by the merge, and
    # neither belongs in `_RUNS_LAST` — a scheduled declaration and an
    # exception handler are facts of the declaring class, not enrichments of
    # rows another engine minted. Their own tables are emptied once per resolve
    # by the pipeline, for the reason `_NON_WIRE` states.
    "scheduled_work": scheduled_work.run,
    # Quartz spec 2026-10-28 §3d: the second shape of evidence for `scheduled_work`, a
    # schedule BUILT by a chain of calls rather than declared by an annotation. Non-wire,
    # and outside `_RUNS_LAST`, on the same terms as the annotation engine above.
    "scheduled_chain": scheduled_chain.run,
    "error_advice": error_advice.run,
}
