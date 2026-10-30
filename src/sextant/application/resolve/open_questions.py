"""The 2K hand-off ledger (2G design §6).

One row per question a programmatic pass could not answer and refused to
guess at: the endpoint's wire identity, which KIND of question it is, the
candidate answers that were on the table, and the trail of what was read to
reach the impasse. 2K's enrichment seat answers these at `evidence: llm` as
overlay claims; nothing in this codebase ever reads them back, because a pass
that read its own unanswered questions would be answering them.

The table lives here rather than inside any one pass because **more than one
pass writes it**: the format ladder records `format_conflict`, the
parse-binding pass records `payload_binding`. That is also why the reset is
its own function, called once from the pipeline ahead of every writer — a
reset owned by either pass would erase the other's rows depending on which
ran first, and the failure would be invisible (a ledger that is merely
shorter than it should be reads exactly like a run with fewer questions).
"""

from typing import Any

from sextant.application.ports.workspace import Workspace

# 2G design §6's closed question set, extended by 2O design §0. Adding a kind
# is a schema change — `egress/render/document.py`'s `_candidate_sentence`
# switches on it and raises for a kind it does not know — which is why all three
# of this phase's arrive together. *This read "both the renderer and the export
# switch on it" until the 2O documentation sweep (`A-Mi12`): only the renderer
# does. The export carries the rows through unread (`api.py:768`), so the cost
# of a new kind is one arm, not two.*
QUESTIONS = (
    "payload_binding",
    "format_conflict",
    # 2O §5: a Spring Integration channel whose destination no configuration
    # key carries. Candidates: the channel name and the handler symbol.
    "channel_destination",
    # 2O §1b: a class a gRPC catalog flagged whose service identity could not
    # be read. Candidates: the class symbol and the reason.
    "service_identity",
    # 2O §2b: a config key whose value differs between environments where one
    # identity needs one value. Candidates: the key and the per-environment values.
    "environment_divergence",
    # F2 §3.4: a configured binder name the catalog's `binder_protocols` does not
    # map, so the wire this binding speaks is UNREAD. Candidates: the binding and
    # the configured name.
    #
    # It earns a kind of its own rather than joining `channel_destination`
    # because the two ask different questions of the same row: that one asks
    # WHERE a known wire addresses, this one asks WHICH WIRE. Before it, an
    # unmapped name silently took the catalog's declared `protocol:` — and
    # protocol is identity, so DR-5 linked the row into another consumer's graph
    # against endpoints this module never speaks to.
    "binder_protocol",
    # F2 §3.4: a `sole` cardinality rule found several candidates and the selection
    # key named none, so WHICH of them the application binds is unread. Candidates:
    # the candidate names and the key that would answer it.
    #
    # It exists because the count taken here is not the count the framework takes:
    # the framework counts registered beans, `config_join._candidates` counts every
    # declared method returning one of the declared interfaces. Suppressing without
    # this question turned a known over-report into a silent under-report.
    "unselected_binding",
    # F2 §3.6: a class carrying a messaging handler annotation two frameworks
    # share, in a module whose build names neither framework's library. WHICH
    # wire it serves is unread. Candidates: the class and the annotation.
    #
    # It is not `service_identity`: that asks what a service is CALLED, this asks
    # what PROTOCOL it speaks — and protocol is the column DR-5 links on, so
    # answering it wrongly reaches other people's graphs while a wrong name does
    # not.
    "handler_protocol",
    # `OI-64`. A registration whose framework requires a later ACTIVATION call —
    # `Subscriber.newBuilder(...).build()` needs `startAsync()` before any message
    # arrives — where nothing in the building method activates it AND the built object
    # is returned. The construction alone used to derive a live inbound endpoint, so
    # this kind replaces a fabricated row. It is asked rather than answered because
    # chain reconstruction is within-method only (D00 §5): a factory handing a
    # subscriber back is ordinary code whose caller may well start it, and answering
    # "no boundary" would swap a fabrication for a silent false negative.
    "registration_activation",
    # F5 §6.1 (W27). One wire identity this module both SERVES and CALLS. Candidates:
    # the served side's handler, and each calling side's caller with the address it
    # reaches.
    #
    # It replaces a merge, not a silence. These two rows used to collapse into one
    # `direction: both` row, which asserts that the thing served and the thing called
    # are the same endpoint — a claim about the far end of a call, which is the one
    # thing a module's own bytecode cannot show. The merge keyed on
    # `(protocol, method, path)`, and `peer` is not part of endpoint identity (RC-5), so
    # the fixture's `${soap.billing.uri}` call collided with the module's own served
    # operation on a shared payload QName.
    #
    # It is asked rather than answered because BOTH answers are real and the evidence
    # does not separate them: a service that publishes to a topic and consumes it back
    # genuinely is one identity in both directions, while a client calling another
    # service's copy of a path this module also serves genuinely is two. Curation or the
    # linking tier decides; a pass that decided here would be guessing at the far end.
    "self_exchange",
    # F5 §6.1 (W28). Two handlers claiming one address, where the catalog that derived
    # them says the framework REFUSES that — Spring MVC throws `IllegalStateException` at
    # startup rather than choosing, so the application does not run. Candidates: the
    # handlers.
    #
    # A question rather than a silent drop, and rather than a finding of its own: it is
    # `format_conflict`'s shape one table over — a disagreement in the analysed code that
    # a person resolves, not something a pass could answer. It is catalog-declared
    # (`mapping.duplicate: conflict`) because several handlers on one address is ORDINARY
    # elsewhere: `@KafkaHandler` dispatches by payload type, and this repo's own fixture
    # has such a pair.
    "routing_conflict",
    # Spec 2026-09-19 §4a (A2). A routing body's module-local helper chain deeper than the
    # combinator's depth bound: the walk stopped following and read no address, so no
    # endpoint row is published for it — a row there would claim an address nobody read.
    # Candidates: one per chain — the first unread callee, the entry's caller and the
    # bound. Identity NULL on both halves, because both genuinely are unread — the verb
    # may be on any route or none — so one run files ONE row and every chain is a
    # candidate of it (the `service_identity._merged` shape).
    "routing_depth",
    # Ruling 3 of the 2026-10-30 object-identity design. A module that configures a path
    # prefix and has rows a dispatcher serves, where none of the server model's `stacks`
    # coordinates is among its dependencies — a build-file parse that lists neither a web
    # artifact nor a known starter. Which configured keys reach a row depends on the stack,
    # so none is applied. Candidates: one per stack, with the configured keys its entries
    # would have applied. Identity NULL on method and path: the question is the module's.
    "web_stack",
)


def reset_open_questions(workspace: Workspace) -> None:
    """Empties the ledger for one resolve. Called once, from the pipeline,
    before any pass writes — never from a writing pass, for the reason the
    module docstring gives.

    Unconditional: a resolve in which every pass answered everything still
    leaves an empty table rather than the previous run's rows, the same
    degrade-visibly discipline `reset_endpoints.sql` /
    `reset_resolved_config.sql` keep."""
    workspace.derive("open_questions_reset")


def record_open_questions(workspace: Workspace, rows: list[dict[str, Any]]) -> None:
    """Appends one resolve pass's questions to the ledger.

    `rows` carry `{protocol, method, path, question, candidates, evidence}`
    with `candidates` already serialized as JSON text by the pass that built
    it — the pass knows what a candidate of ITS kind looks like, and a
    generic shape here would either be empty or wrong. An empty list writes
    nothing rather than a no-op statement.

    Raises `ValueError` naming the offending value when `question` is outside
    `QUESTIONS`: the value is bound straight into a published artifact, where
    a typo is indistinguishable from a kind of question nobody implemented.
    """
    for row in rows:
        question = row.get("question")
        if question not in QUESTIONS:
            raise ValueError(
                f"open question `{question!r}` is not one of {', '.join(QUESTIONS)} "
                f"— 2G design §6's question set is closed (NFR-5)"
            )
    if rows:
        workspace.derive("open_questions_insert", rows=rows)
