from dataclasses import dataclass, field
from pathlib import Path

from sextant.application.ports.catalogs import CatalogSource
from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.call_edges import record_call_edges
from sextant.application.resolve.config import resolve_config
from sextant.application.resolve.endpoints import SkippedCatalog, derive_endpoints
from sextant.application.resolve.environment_divergence import record_environment_divergence
from sextant.application.resolve.format import resolve_format
from sextant.application.resolve.open_questions import reset_open_questions
from sextant.application.resolve.protocol_hint import apply_protocol_hints
from sextant.application.resolve.return_flow import record_return_flows
from sextant.application.resolve.roots import record_roots
from sextant.application.resolve.routing_conflicts import record_routing_conflicts
from sextant.application.resolve.self_exchange import record_self_exchange
from sextant.application.resolve.service_identity import record_service_identity_gaps
from sextant.application.resolve.shapes import derive_endpoint_shapes
from sextant.application.resolve.shapes.parse_binding import bind_parse_calls


@dataclass(frozen=True)
class ResolveReport:
    facts_loaded: int
    endpoints: list[dict[str, object]] = field(default_factory=list)
    skipped_catalogs: list[SkippedCatalog] = field(default_factory=list)
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
    # The types the expansion reached and could not open: no field facts and
    # no catalog entry describing them. Carried rather than counted, because a
    # count cannot be acted on and a catalog only grows from observation
    # (FR-17).
    unexpanded_types: tuple[str, ...] = ()


def resolve(
    workspace: Workspace,
    fact_root: Path,
    catalogs: CatalogSource,
    capabilities: set[str],
) -> ResolveReport:
    """Facts in, graph out. Language-blind: it branches on capabilities, never
    on names (M04)."""
    loaded = workspace.load_facts(fact_root)
    declared = catalogs.load()
    # M04 pass 2 (D01, D02 §2i): the generic config-model interpreter, run
    # before endpoint derivation — the `config_join` engine (2F design §3)
    # that will consume `resolved_config` runs as an endpoint style, so its
    # capability has to exist before `derive_endpoints` gates the catalogs.
    # Unconditional, empty in and empty out (`resolve_config`'s own
    # contract), so a config-less run still leaves the table's earlier
    # contents cleared rather than stale.
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
    record_return_flows(workspace)
    # 2Q `G4`, beside `G3` and for the same reason: it reads `call_sites` and
    # the type hierarchy — compiler facts, all loaded — takes no catalog and
    # gates on no capability. The two are independent (disjoint tables, one
    # shared reader in `resolve/dispatch.py` that each builds for itself), so
    # this order is the order they were written and nothing depends on it.
    # `declared` for D00 §4's `terminal_kind` alone (F7 §8.2, W30): the edges themselves
    # are compiler facts, and only the classification of what a terminal REACHES needs a
    # catalog to have said what the callee is.
    record_call_edges(workspace, declared)
    # F5 §6.2 (W29): emptied once, here, ahead of every engine that writes it — the
    # `open_questions`/`resolved_config` discipline. More than one catalog contributes
    # entries, so a reset owned by an engine would erase whichever ran first, and a
    # resolve whose calls carry no metadata leaves an empty table rather than the previous
    # run's rows.
    workspace.derive("endpoint_metadata_reset")
    skipped = derive_endpoints(workspace, declared, capabilities)
    # After the endpoints, never beside them: an endpoint's payload types come
    # off its handler's signature, which is a column on the row derive_endpoints
    # just wrote.
    expanded = derive_endpoint_shapes(workspace, declared, capabilities)
    # The 2K hand-off ledger (2G design §6) is emptied once, here, ahead of
    # every pass that writes to it rather than inside one of them — the
    # `resolved_config` reset discipline, lifted out of the writing pass
    # because more than one pass writes these rows. A resolve whose passes
    # had nothing to ask still leaves an empty table rather than the previous
    # run's rows.
    reset_open_questions(workspace)
    # Above the ladder and below the reset, which is exactly where the
    # comment on that line asks a payload-binding pass to go (2G design §6):
    # it WRITES `open_questions` rows, so it must run after the reset, and
    # the format ladder's rung 4 READS the payload column it binds — a bound
    # schema-described parse is what lifts a NULL format to that schema's own
    # format at `narrowed`.
    bound = bind_parse_calls(workspace, declared)
    # 2O design §1b/§1c: `supertype_derived`/`injected_client`'s own
    # `service_identity` gaps, filed here for the same reason
    # `bind_parse_calls` sits here rather than inside `derive_endpoints` —
    # `service_identity.py`'s own module docstring states it in full. Order
    # against `bind_parse_calls` itself does not matter (disjoint tables,
    # disjoint question kinds); it sits below it only because it was added
    # after it.
    record_service_identity_gaps(workspace, declared)
    # 2O design §2b, and it sits here for the same reason the two passes above
    # do: it WRITES `open_questions`, so it must run after the reset. Its order
    # against them does not matter — disjoint question kinds, disjoint tables.
    record_environment_divergence(workspace, declared, capabilities)
    # Between the binding and the ladder, and both sides of that are the
    # pass's own contract (2H design §6). AFTER every engine: this pass
    # reclassifies rows others minted, so they must all exist. BEFORE
    # `resolve_format`: the ladder's rung 1 reads `protocol` directly, so a
    # row answered before it was reclassified would carry the format of a
    # protocol it no longer has. (The "and its merge" half of the first
    # condition went with the merge in W27; two passes run BELOW this line
    # now instead, and each says why on its own call.)
    apply_protocol_hints(workspace, declared)
    # F5 §6.1 (W27), and BELOW `apply_protocol_hints` rather than beside the other
    # question-filing passes: `protocol` is part of the identity this question names,
    # and that pass reclassifies it on rows other engines minted. Filed above this line,
    # a question would name a wire the endpoint no longer speaks — the same defect the
    # roots pass was moved down to fix. Above the reset it would simply be erased.
    record_self_exchange(workspace)
    # F5 §6.1 (W28), and below `apply_protocol_hints` — but NOT for the reason above.
    # Spring's registry knows nothing about SSE versus plain HTTP; `protocol` is in this
    # question's identity because a detector must not compare rows two different engines
    # minted, and it makes the detector NARROWER than the framework: an `SseEmitter`-
    # returning `@GetMapping("/events")` is moved to `sse` and so is never compared with
    # a plain `@GetMapping("/events")` that Spring genuinely refuses. That is an
    # under-report, which is the direction NFR-2 asks for, and running below the pass
    # that moves it is what keeps the identity stable within one run.
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
    record_roots(workspace)
    # LAST, and the ordering is a property of the pass, not a preference (the
    # `_RUNS_LAST` precedent in `resolve/endpoints.py`): every rung of the
    # format ladder reads something an earlier pass wrote — the media columns
    # the config stamp filled, the payload columns the shape pass bound — so
    # a format stamped before them would be answered from a table that was
    # still being written. Anything that BINDS a payload belongs above this
    # line and below the reset.
    resolve_format(workspace, declared)
    return ResolveReport(
        facts_loaded=loaded,
        endpoints=workspace.query("endpoints"),
        skipped_catalogs=skipped,
        coverage=workspace.query("coverage")[0],
        shapes=workspace.query("shapes"),
        scheduled_work=workspace.query("scheduled_work"),
        error_handlers=workspace.query("error_handlers"),
        # Both passes root payload types and both expand what they root, so
        # both can meet a type nothing opens. Reported as one list, deduped:
        # the gap is in the type, not in how many passes walked into it —
        # the same rule `derive_endpoint_shapes` applies across catalogs.
        unexpanded_types=tuple(
            dict.fromkeys([*expanded.unexpanded_types, *bound.unexpanded_types])
        ),
    )
