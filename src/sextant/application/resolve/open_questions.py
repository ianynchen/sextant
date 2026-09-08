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
