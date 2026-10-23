import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from sextant.application.ports.catalogs import CatalogSource
from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.bean_conditions import record_bean_conditions
from sextant.application.resolve.call_edges import record_call_edges
from sextant.application.resolve.config import resolve_config
from sextant.application.resolve.endpoint_attributes import record_endpoint_attributes
from sextant.application.resolve.endpoints import SkippedCatalog, derive_endpoints_with_runs
from sextant.application.resolve.environment_divergence import record_environment_divergence
from sextant.application.resolve.format import resolve_format
from sextant.application.resolve.open_questions import reset_open_questions
from sextant.application.resolve.path_prefix import apply_path_prefixes
from sextant.application.resolve.protocol_hint import apply_protocol_hints
from sextant.application.resolve.reachability import record_reachability
from sextant.application.resolve.request_requirements import record_request_requirements
from sextant.application.resolve.resolved_schedules import record_resolved_schedules
from sextant.application.resolve.return_flow import record_return_flows
from sextant.application.resolve.roots import record_roots
from sextant.application.resolve.routing_conflicts import record_routing_conflicts
from sextant.application.resolve.self_exchange import record_self_exchange
from sextant.application.resolve.service_identity import record_service_identity_gaps
from sextant.application.resolve.shadow import record_value_resolutions
from sextant.application.resolve.shapes import derive_endpoint_shapes
from sextant.application.resolve.shapes.parse_binding import bind_parse_calls
from sextant.application.resolve.values import reset_value_index

_log = logging.getLogger(__name__)


@contextmanager
def _timed(pass_name: str) -> Iterator[None]:
    """Seconds one resolve pass took, logged at INFO once it returns (`OI-68`).

    The per-pass table that entry carries was produced by a throwaway script every
    time it was needed; this makes the instrument standing. It changes nothing the
    pass does — the log line is the whole effect — and the line has the shape of
    `RichProgress`'s plain fallback (label, then seconds to one decimal), so the two
    read alike on a terminal that shows both. `logging` rather than the `Progress`
    port because a pass is not a stage: the port renders five rows a user watches,
    and fifteen more would be noise there and are a profile here, off by default
    until a caller raises the level."""
    started = time.perf_counter()
    try:
        yield
    finally:
        _log.info("%s  %.1fs", pass_name, time.perf_counter() - started)


@dataclass(frozen=True)
class ResolveReport:
    facts_loaded: int
    endpoints: list[dict[str, object]] = field(default_factory=list)
    skipped_catalogs: list[SkippedCatalog] = field(default_factory=list)
    # How many catalogs that RAN feed each boundary kind (spec 2026-10-22 §4b); kinds with
    # none are absent. Written to `metadata.json` because a bundle's reader has no catalogs.
    catalogs_run: dict[str, int] = field(default_factory=dict)
    coverage: dict[str, object] = field(default_factory=dict)
    shapes: list[dict[str, object]] = field(default_factory=list)
    # The two NON-WIRE families (2O design §4): work the framework starts on a
    # clock, and which exceptions the module answers. Carried on the report
    # beside `endpoints` and `shapes` — never inside them — because the
    # endpoint table is wire-true and neither of these has a wire identity at
    # all. Empty lists for a module that schedules nothing and handles nothing,
    # which is the same answer their pre-declared tables give.
    scheduled_work: list[dict[str, object]] = field(default_factory=list)
    error_handlers: list[dict[str, object]] = field(default_factory=list)
    # The conditions every BEAN carries, one row per (bean, route, condition, environment)
    # (spec 2026-10-22-conditional-beans §2): what every derived row finds through its own
    # code's owner class, and the document's detail lines are derived from these rows and
    # `bean_presence` below, and from nothing else (spec 2026-10-21-conditional-controllers).
    bean_conditions: list[dict[str, object]] = field(default_factory=list)
    # Where each conditional bean EXISTS, per environment — the one answer to "does this exist
    # here" (OR across a bean's routes, AND within one), which "holds in N of M" is read from.
    bean_presence: list[dict[str, object]] = field(default_factory=list)
    # The bean each code symbol belongs to (own symbol, then owner class), from the workspace's
    # one rule — the documents read it rather than re-deriving it (Task 5, ruling 1).
    symbol_beans: list[dict[str, object]] = field(default_factory=list)
    # Which candidates of each narrowed call site exist in each environment (spec §3), which a
    # trace block states under the site.
    candidate_presence: list[dict[str, object]] = field(default_factory=list)
    # The types the expansion reached and could not open: no field facts and
    # no catalog entry describing them. Carried rather than counted, because a
    # count cannot be acted on and a catalog only grows from observation
    # (FR-17).
    unexpanded_types: tuple[str, ...] = ()
    # Spec 2026-09-22 §7a: how many rows shadow mode recorded, and 0 on every ordinary
    # analysis. Carried so a `--shadow` run can SAY what it recorded — the failure mode
    # this number exists to expose is a flag that silently did not arrive, which leaves an
    # empty table and reads to a reviewer as "nothing would resolve".
    value_resolutions: int = 0


def coverage_of(workspace: Workspace) -> dict[str, object]:
    """`coverage`, plus FR-17 clause 3's distributions (F8 §9.5, W38).

    **How many files we OPENED and how much we UNDERSTOOD are different numbers**, and
    until this the report carried only the first: `{documents, partial_documents}`. Every
    resolution figure quoted about this project came from a throwaway script written once
    and discarded; these make them standing.

    Three buckets rather than the one the design names, and the reason is the design's own
    warning about the one. `resolution` reads **100% `resolved` on two of the four measured
    corpora** — mall-admin 24,591 of 24,591, jhipster 1,686 of 1,686 — which looks perfect
    and says almost nothing: naming the target a compiler wrote is easy, and reading its
    BODY is the work. `reach` is the number that answers the question the row was added
    for (`mall-admin` 78%, the other three 32%), and `method_resolution` says WHY a body
    was missed — an owner in an unscanned jar is a scanning decision, while
    `no_declaration_found` would be a defect.

    Shipping the distribution alone would satisfy the row's letter and leave the standing
    instrument reading 100% forever.
    """
    coverage = dict(workspace.query("coverage")[0])
    for key, named, unit in (
        ("resolution", "resolution_distribution", "edges"),
        ("reach", "reach_distribution", "edges"),
        ("method_resolution", "method_resolution_distribution", "methods"),
    ):
        # Sorted by the query, and a dict of counts rather than a list of rows: a reader
        # asks "how many `owner_not_scanned`", never "what was the third bucket". The
        # bucket names differ per distribution and each is the column's own vocabulary —
        # `resolution` can only ever hold `resolved` or `narrowed`, because `call_edges`
        # writes `NARROWED if len(callees) > 1 else RESOLVED` and nothing else.
        coverage[key] = {str(row["bucket"]): int(str(row[unit])) for row in workspace.query(named)}
    return coverage


def resolve(
    workspace: Workspace,
    fact_root: Path,
    catalogs: CatalogSource,
    capabilities: set[str],
    # Spec 2026-09-22 §7a. Defaulted OFF, so every existing caller — every test
    # that builds this pipeline by hand, and every ordinary `analyze` — resolves
    # exactly what it resolved before this parameter existed. On, one extra pass
    # runs at the very bottom and writes one table nothing reads; it publishes
    # nothing and moves no row anywhere else.
    shadow: bool = False,
) -> ResolveReport:
    """Facts in, graph out. Language-blind: it branches on capabilities, never
    on names (M04)."""
    # Before anything can ask for it: the walk's index is cached per workspace for the
    # duration of ONE resolve, and clearing it here is what bounds that lifetime (see
    # `values.cached_value_index`). A resolve that reused a previous one's index would
    # answer from facts this run has not loaded yet.
    reset_value_index()
    with _timed("load_facts"):
        loaded = workspace.load_facts(fact_root)
    declared = catalogs.load()
    # M04 pass 2 (D01, D02 §2i): the generic config-model interpreter, run
    # before endpoint derivation — the `config_join` engine (2F design §3)
    # that will consume `resolved_config` runs as an endpoint style, so its
    # capability has to exist before `derive_endpoints` gates the catalogs.
    # Unconditional, empty in and empty out (`resolve_config`'s own
    # contract), so a config-less run still leaves the table's earlier
    # contents cleared rather than stale.
    with _timed("resolve_config"):
        resolve_config(workspace, declared)
    # The first PIPELINE-declared capability (D02 §1): every capability
    # above it is scanner-declared, earned once up front by the scanner
    # that produced a module's facts. This one is earned by the pipeline
    # itself, once pass 2 has run — a catalog naming it in `requires` is
    # skipped, visibly, the same as any unmet scanner capability, until this
    # line has run in THIS resolve.
    capabilities = capabilities | {"resolved_config"}
    # The two NON-WIRE tables (2O design §4) are emptied once, here, ahead of
    # the engines that write them rather than inside either engine — the
    # `reset_open_questions` discipline, and for the same reason it exists:
    # §4a's "Quartz: later catalog, same table" means MORE THAN ONE catalog
    # writes to `scheduled_work`, and a reset owned by the engine would run
    # once per catalog and leave only whichever ran last. `derive_endpoints`
    # states the identical defect for `endpoints` at its own reset.
    # Unconditional, so a resolve in which every catalog is skipped still
    # leaves empty tables rather than the previous run's rows.
    workspace.derive("scheduled_work_reset")
    workspace.derive("error_handlers_reset")
    # 2Q `G3`, and its position says what it depends on: NOTHING any engine
    # writes. It reads `call_sites`, `method_returns` and the type hierarchy —
    # compiler facts, all loaded — and writes a table of its own, so it could
    # sit anywhere below `load_facts`. It sits here, above the catalog-driven
    # half, because it takes no catalog and gates on no capability: there is no
    # framework knowledge in a return, and a pass that cannot be skipped should
    # not read as though it might be.
    with _timed("record_return_flows"):
        record_return_flows(workspace)
    # 2Q `G4`, beside `G3` and for the same reason: it reads `call_sites` and
    # the type hierarchy — compiler facts, all loaded — takes no catalog and
    # gates on no capability. The two are independent (disjoint tables, one
    # shared reader in `resolve/dispatch.py` that each builds for itself), so
    # this order is the order they were written and nothing depends on it.
    # `declared` for D00 §4's `terminal_kind` alone (F7 §8.2, W30): the edges themselves
    # are compiler facts, and only the classification of what a terminal REACHES needs a
    # catalog to have said what the callee is.
    with _timed("record_call_edges"):
        record_call_edges(workspace, declared)
    # F5 §6.2 (W29): emptied once, here, ahead of every engine that writes it — the
    # `open_questions`/`resolved_config` discipline. More than one catalog contributes
    # entries, so a reset owned by an engine would erase whichever ran first, and a
    # resolve whose calls carry no metadata leaves an empty table rather than the previous
    # run's rows.
    workspace.derive("endpoint_metadata_reset")
    # Spec 2026-10-22-conditional-beans (the general rule spec 2026-10-21-conditional-
    # controllers was a case of): replaced whole per resolve, the same discipline.
    workspace.derive("bean_conditions_reset")
    # Its feeder, the combinator's `route_requirements` stash (spec 2026-09-19 §4d/§5a),
    # is re-created by `derive_endpoints` beside `endpoints_reset` — the engines write it
    # there, and `record_request_requirements` below joins it to `endpoints` once every
    # row's protocol is final.
    # The 2K hand-off ledger (2G design §6) is emptied once, here, ahead of
    # every pass that writes to it rather than inside one of them — the
    # `resolved_config` reset discipline, lifted out of the writing pass
    # because more than one pass writes these rows. A resolve whose passes
    # had nothing to ask still leaves an empty table rather than the previous
    # run's rows. ABOVE `derive_endpoints`, not below it (spec 2026-09-19 §4a): two
    # engines file questions as they derive — `interface_implementation`'s
    # `registration_activation` and the combinator's `routing_depth` — and a reset
    # that ran after them erased both before any later pass read the table. Every
    # other writer runs below `derive_endpoints` either way, so nothing else moves.
    reset_open_questions(workspace)
    with _timed("derive_endpoints"):
        skipped, catalogs_run = derive_endpoints_with_runs(workspace, declared, capabilities)
    # **The module's own server prefix, and it runs HERE for a reason** (spec 2026-10-18 §3,
    # `OI-148`): every row exists by now, and nothing has copied an address yet.
    # `record_roots`, `record_routing_conflicts` and `record_self_exchange` all key on the
    # path, so a prefix applied after any of them would leave a root and a conflict keyed on
    # an address the module does not serve — `OI-28`'s shape.
    #
    # Before `derive_endpoint_shapes` too, which is merely the earliest safe point rather
    # than a requirement: shapes come off the handler's signature and never off the path.
    with _timed("apply_path_prefixes"):
        apply_path_prefixes(workspace, declared)
    # After the endpoints, never beside them: an endpoint's payload types come
    # off its handler's signature, which is a column on the row derive_endpoints
    # just wrote.
    with _timed("derive_endpoint_shapes"):
        expanded = derive_endpoint_shapes(workspace, declared, capabilities)
    # Above the ladder and below the reset, which is exactly where the
    # comment on that line asks a payload-binding pass to go (2G design §6):
    # it WRITES `open_questions` rows, so it must run after the reset, and
    # the format ladder's rung 4 READS the payload column it binds — a bound
    # schema-described parse is what lifts a NULL format to that schema's own
    # format at `narrowed`.
    with _timed("bind_parse_calls"):
        bound = bind_parse_calls(workspace, declared)
    # 2O design §1b/§1c: `supertype_derived`/`injected_client`'s own
    # `service_identity` gaps, filed here for the same reason
    # `bind_parse_calls` sits here rather than inside `derive_endpoints` —
    # `service_identity.py`'s own module docstring states it in full. Order
    # against `bind_parse_calls` itself does not matter (disjoint tables,
    # disjoint question kinds); it sits below it only because it was added
    # after it.
    with _timed("record_service_identity_gaps"):
        record_service_identity_gaps(workspace, declared)
    # 2O design §2b, and it sits here for the same reason the two passes above
    # do: it WRITES `open_questions`, so it must run after the reset. Its order
    # against them does not matter — disjoint question kinds, disjoint tables.
    with _timed("record_environment_divergence"):
        record_environment_divergence(workspace, declared, capabilities)
    # Between the binding and the ladder, and both sides of that are the
    # pass's own contract (2H design §6). AFTER every engine: this pass
    # reclassifies rows others minted, so they must all exist. BEFORE
    # `resolve_format`: the ladder's rung 1 reads `protocol` directly, so a
    # row answered before it was reclassified would carry the format of a
    # protocol it no longer has. (The "and its merge" half of the first
    # condition went with the merge in W27; two passes run BELOW this line
    # now instead, and each says why on its own call.)
    with _timed("apply_protocol_hints"):
        apply_protocol_hints(workspace, declared)
    # Spec 2026-09-19 §5a, and BELOW `apply_protocol_hints` for the reason the two passes
    # under it give: an `endpoint_metadata` entry names its row by the row's identity
    # columns, `protocol` among them, and that pass reclassifies `protocol` on rows the
    # engines minted. Written above this line, an inbound entry would name a wire its
    # endpoint no longer speaks. (The fluent engine's OUTBOUND entries are written inside
    # `derive_endpoints`, above the hint pass — W29's order, unchanged here.)
    with _timed("record_request_requirements"):
        record_request_requirements(workspace, declared)
    # Spec 2026-10-22-conditional-beans (ruled 2026-10-22), where spec 2026-10-21's
    # endpoint-only pass ran. It names no endpoint any more — the `endpoint_conditions` view
    # joins rows to beans when read — so the position only needs `resolve_config` (the
    # environments) and `record_call_edges` (what a factory constructs, `type_hierarchy`),
    # both far above.
    with _timed("record_bean_conditions"):
        record_bean_conditions(workspace, declared)
    # Spec 2026-10-23-configured-schedules §3b: a placeholder job's value per environment.
    # It needs `resolve_config` (the values) and `derive_endpoints` (the scheduled-work
    # engine runs as one of its styles), both above; nothing below reads what it writes,
    # and it resets its own table, being its only writer.
    with _timed("record_resolved_schedules"):
        record_resolved_schedules(workspace, declared)
    # Spec 2026-09-22 §1f, and BELOW `apply_protocol_hints` for the reason
    # `record_request_requirements` above gives in full: a qualifying attribute names its
    # row by the row's identity columns, `protocol` among them, and that pass reclassifies
    # `protocol` on rows the engines minted. Below the `endpoint_metadata` reset too,
    # because it WRITES that table and a row written above the reset would simply be
    # erased. Its order against `record_request_requirements` does not matter — the two
    # write disjoint kinds, and the insert is insert-if-absent on the whole row either way.
    with _timed("record_endpoint_attributes"):
        record_endpoint_attributes(workspace, declared)
    # F5 §6.1 (W27), and BELOW `apply_protocol_hints` rather than beside the other
    # question-filing passes: `protocol` is part of the identity this question names,
    # and that pass reclassifies it on rows other engines minted. Filed above this line,
    # a question would name a wire the endpoint no longer speaks — the same defect the
    # roots pass was moved down to fix. Above the reset it would simply be erased.
    with _timed("record_self_exchange"):
        record_self_exchange(workspace)
    # F5 §6.1 (W28), and below `apply_protocol_hints` — but NOT for the reason above.
    # Spring's registry knows nothing about SSE versus plain HTTP; `protocol` is in this
    # question's identity because a detector must not compare rows two different engines
    # minted, and it makes the detector NARROWER than the framework: an `SseEmitter`-
    # returning `@GetMapping("/events")` is moved to `sse` and so is never compared with
    # a plain `@GetMapping("/events")` that Spring genuinely refuses. That is an
    # under-report, which is the direction NFR-2 asks for, and running below the pass
    # that moves it is what keeps the identity stable within one run.
    with _timed("record_routing_conflicts"):
        record_routing_conflicts(workspace, list(declared))
    # 2Q `I1`, and its position is a dependency rather than a preference: it
    # reads `endpoints.handler`/`direction`, `endpoints`' three WIRE columns
    # and `scheduled_work.handler`, and every one of those is final only here.
    # `derive_endpoints` writes the handler and the direction; the scheduled
    # engine runs as one of its styles; and `apply_protocol_hints`
    # RECLASSIFIES `protocol` on rows those engines already minted. (It also
    # ran an inbound/outbound merge that turned two rows into one `both` row
    # until W27 deleted it; the columns this list depends on are unchanged.)
    #
    # **It sat above the three passes between them until the address columns
    # landed, and that was measurable rather than theoretical** (2Q close,
    # defect 1): the orders-service fixture reclassifies two SSE rows out of
    # `http`, so a root recorded before this line carried `http` while the
    # `endpoints` row it was copied from carried `sse` — one address, two
    # spellings, in one workspace. Nothing below writes any of the five
    # columns: `resolve_format` stamps format columns and MATCHES on the rest.
    with _timed("record_roots"):
        record_roots(workspace)
    # LAST, and the ordering is a property of the pass, not a preference (the
    # `_RUNS_LAST` precedent in `resolve/endpoints.py`): every rung of the
    # format ladder reads something an earlier pass wrote — the media columns
    # the config stamp filled, the payload columns the shape pass bound — so
    # a format stamped before them would be answered from a table that was
    # still being written. Anything that BINDS a payload belongs above this
    # line and below the reset.
    with _timed("resolve_format"):
        resolve_format(workspace, declared)
    # F8 §9.4 (W37), and AFTER everything: the walk reads `roots` and `call_edges`, so a
    # reachability recorded earlier would be a walk over a graph nobody else saw —
    # `record_roots` above writes the roots and `apply_protocol_hints` moves rows the
    # roots were copied from. It is the walk `query/trace.py` performs for the renderer,
    # kept rather than thrown away.
    with _timed("record_reachability"):
        record_reachability(workspace)
    # Spec 2026-09-22 §7a, and LAST — below even the pass that calls itself last —
    # because nothing reads what it writes and nothing it writes may be read. Its
    # position is therefore not a dependency but a STATEMENT: a pass that recorded
    # a candidate conversion higher up would sit above passes that could act on it,
    # and the one guarantee this pass makes is that none of them can. It reads facts
    # and the two tables the edge view is built from, all final long before here.
    #
    # Called UNCONDITIONALLY with the flag rather than guarded by it: the reset
    # inside it must run on an ordinary analysis too, or a workspace analysed once
    # with `--shadow` keeps that run's review list for ever (the pass says why).
    with _timed("record_value_resolutions"):
        recorded = record_value_resolutions(workspace, declared, shadow=shadow)
    return ResolveReport(
        facts_loaded=loaded,
        value_resolutions=recorded,
        endpoints=workspace.query("endpoints"),
        skipped_catalogs=skipped,
        catalogs_run=catalogs_run,
        coverage=coverage_of(workspace),
        shapes=workspace.query("shapes"),
        scheduled_work=workspace.query("scheduled_work"),
        error_handlers=workspace.query("error_handlers"),
        bean_conditions=workspace.query("bean_conditions"),
        bean_presence=workspace.query("bean_presence"),
        symbol_beans=workspace.query("symbol_beans"),
        candidate_presence=workspace.query("candidate_presence"),
        # Both passes root payload types and both expand what they root, so
        # both can meet a type nothing opens. Reported as one list, deduped:
        # the gap is in the type, not in how many passes walked into it —
        # the same rule `derive_endpoint_shapes` applies across catalogs.
        unexpanded_types=tuple(
            dict.fromkeys([*expanded.unexpanded_types, *bound.unexpanded_types])
        ),
    )
