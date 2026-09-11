"""One wire identity a module both SERVES and CALLS, filed as a question (F5 §6.1, W27).

## What this replaces

These two rows used to be one. `merge_endpoints.sql` collapsed an inbound row and an
outbound row sharing `(protocol, method, path)` into a single `direction: both` row,
keeping the handler and carrying the caller onto it. That is a claim about the FAR END of
a call — that the thing this module calls is the thing this module serves — and the far
end is the one thing a module's own bytecode cannot show. Worse, the merge keyed on the
wire identity alone, and `peer` is not part of endpoint identity (RC-5), so a path this
module serves collided with the same path anywhere in the world.

**Measured on this repo's own fixture, where two of the six merged rows were wrong:**

* `{http://orders.example.com/ws}placeOrderRequest` — the module serves this operation
  AND `BillingSoapClient` calls it at `${soap.billing.uri}`. One row, carrying that peer,
  said the module's own served operation and a call to the billing service were one
  endpoint. They share a QName because they share a payload type, which is not identity.
* `POST /v1/orders` — served here, and called by `OrdersLoopClient` at `orders-loop`.

The other four are the case that made the merge look right: the module publishes to a
Kafka topic or a Pub/Sub subscription and consumes it back, with no peer on either side.

## Why a question and not a rule

Both readings are real and the evidence does not separate them. A service that publishes
to a topic and reads it back genuinely is one identity in both directions; a client
calling another service's copy of a path this module also serves genuinely is two. A pass
that chose would be guessing at the far end — the thing NFR-2 rates worst — so the two
rows stand and the reader (or the linking tier, where a schema match or curation can
justify it) decides. `Direction.BOTH` stays in D00 §4 for that tier and is produced by
nothing here.

## A separate pass, and where it sits

`open_questions` is reset once, in the pipeline, AFTER `derive_endpoints` runs — the
ledger-ownership discipline `service_identity.py` and `bind_parse_calls` already follow,
so a write from inside the engine that used to merge would be erased by that reset.

It runs after `apply_protocol_hints` for a reason the roots pass already learned the hard
way: that pass RECLASSIFIES `protocol` on rows other engines minted (the fixture moves two
rows out of `http` and into `sse`), and `protocol` is part of the identity this question
names. Filed earlier, a question would name a wire the endpoint no longer speaks.
"""

import json

from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.open_questions import record_open_questions
from sextant.domain.closed_sets import Direction
from sextant.domain.symbols import bare_descriptor


def _bare(symbol: object) -> str | None:
    """A handler or caller as the document spells it everywhere else: the descriptor
    alone, without the module coordinates a fact carries (D00 §5a).

    Consistency is the whole reason. The endpoint tables, the roots table and the trace
    list all render the bare descriptor, so a reader who follows a question back to the
    row it is about has to be able to match the two strings by eye — and the coordinate
    prefix is 46 characters of identical text in front of every symbol on the page.
    Provenance is recovered from the document a symbol was declared in (D06 §4), never
    by reading the prefix off the symbol.
    """
    return None if symbol is None else bare_descriptor(str(symbol))


def record_self_exchange(workspace: Workspace) -> None:
    """Files one question per wire identity present in both directions."""
    served: dict[tuple[str, str | None, str | None], list[dict[str, object]]] = {}
    called: dict[tuple[str, str | None, str | None], list[dict[str, object]]] = {}
    for row in workspace.query("endpoints"):
        direction = str(row["direction"])
        # The identity, and only it: `peer` is deliberately absent (RC-5), which is
        # exactly what makes this a question rather than a match.
        identity = (
            str(row["protocol"]),
            None if row["method"] is None else str(row["method"]),
            None if row["path"] is None else str(row["path"]),
        )
        if identity[2] is None:
            # An unresolved row names no address, so it shares an identity with every
            # other unresolved row on its protocol. Pairing those would ask about a
            # coincidence of two absences.
            continue
        if direction == Direction.INBOUND:
            served.setdefault(identity, []).append(
                # A served row may name no handler at all — a schema-first operation is
                # declared by a `.wsdl` or a `.proto` and by no method here (D02 §5's
                # `schema_operations` mints rows with neither handler nor caller). The
                # question is still worth asking about such a row, and a candidate whose
                # symbol was the empty string would render as "served here by " with
                # nothing after it.
                {"side": "served", "symbol": _bare(row["handler"]), "peer": None}
            )
        elif direction == Direction.OUTBOUND:
            called.setdefault(identity, []).append(
                {
                    "side": "called",
                    "symbol": _bare(row["caller"]),
                    "peer": None if row["peer"] is None else str(row["peer"]),
                }
            )
    rows: list[dict[str, object]] = []
    # Sorted, so two runs file the ledger in one order (NFR-1). `endpoints` is already
    # ordered, but the identities are collected into a dict on the way here.
    for identity in sorted(served.keys() & called.keys(), key=lambda key: tuple(map(str, key))):
        protocol, method, path = identity
        rows.append(
            {
                "protocol": protocol,
                "method": method,
                "path": path,
                "question": "self_exchange",
                # The served side first: it is the half this module can see whole.
                "candidates": json.dumps(served[identity] + called[identity]),
                # Prose, not a tier — the column is the TRAIL a reader follows
                # (schema.sql: "an unanswered question has no tier"). It names the
                # column that would settle this and is not compared, because `peer` is
                # not part of endpoint identity and never becomes part of it here.
                "evidence": (
                    "one wire identity in both directions; `peer` is not part of "
                    "endpoint identity (RC-5), so the two rows were not compared on it"
                ),
            }
        )
    record_open_questions(workspace, rows)
