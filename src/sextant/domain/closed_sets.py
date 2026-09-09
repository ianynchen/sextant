"""The closed sets of D00 §4. Adding a value is a schema change, never an
implementation choice — see NFR-5."""

from enum import StrEnum


class Resolution(StrEnum):
    RESOLVED = "resolved"
    NARROWED = "narrowed"
    PARTIAL = "partial"
    UNRESOLVED = "unresolved"


class MethodResolution(StrEnum):
    """Why a call site's target does or does not reach a body (F3 §4.2, JVMS 5.4.3.3).

    **One word did three jobs and that is what made it a fabrication.** A call whose
    body the workspace had not read, a call whose owner it had never scanned, and a
    call whose method is declared on a superclass it DID scan all produced the same
    answer: no callee, `resolved`, "the call IS the terminal". The third is false —
    the body is in the workspace, one hop up — 131 call sites in `spring-petclinic-rest`,
    whose rendered document goes from 1939 boundary steps to 1649, **15.0%**. (F3 §4.2
    states 21%; it names no corpus and reproduces on none — `mall-admin` does not move at
    all. §5.4 wants the corpus beside the number, which is why this one carries it.)

    The set is closed and each value states a different thing a reader can act on:

    * `declared_here` — the owner itself declares the method. The ordinary case.
    * `inherited` — a SCANNED ancestor declares it; `method_resolution.declaring_class`
      names which. A reader can follow the call.
    * `ancestor_not_scanned` — the owner was scanned, neither it nor any scanned
      ancestor declares the method, and it has at least one ancestor the workspace did
      not read. We know MORE than "external": we know the body is inherited from
      something we did not open, and which type that is.
    * `owner_not_scanned` — the owner is not in this workspace at all. The genuine
      third-party boundary, and the honest terminal.
    * `no_declaration_found` — the owner was scanned, every ancestor reachable from it
      was scanned too, and none of them declares the method. Rare, and it is NOT the
      same claim as `owner_not_scanned`: the first draft returned that word here, for an
      owner the code had just proven IS in the workspace, so the row said "third-party
      boundary" about a type we had read. A set with no member for "we looked everywhere
      we could and found nothing" invites exactly that reuse.
    """

    DECLARED_HERE = "declared_here"
    INHERITED = "inherited"
    ANCESTOR_NOT_SCANNED = "ancestor_not_scanned"
    OWNER_NOT_SCANNED = "owner_not_scanned"
    NO_DECLARATION_FOUND = "no_declaration_found"


class Evidence(StrEnum):
    COMPILER = "compiler"
    SYNTAX = "syntax"
    NAME_MATCH = "name_match"
    DECLARED = "declared"
    HUMAN = "human"
    LLM = "llm"


class ConstructKind(StrEnum):
    CLASS = "class"
    INTERFACE = "interface"
    # W7, ruled by the user in the design: an annotation TYPE is not an interface,
    # and the class file says so with `ACC_ANNOTATION`. Tested after `ACC_INTERFACE`
    # — which every `@interface` also carries — the whole estate reported them as
    # interfaces, and §8.1 rule 5 says to follow a distinction the provider makes.
    ANNOTATION = "annotation"
    ENUM = "enum"
    RECORD = "record"
    METHOD = "method"
    CONSTRUCTOR = "constructor"
    FIELD = "field"
    MODULE = "module"
    STRUCT = "struct"
    TRAIT = "trait"
    PROTOCOL = "protocol"
    ALIAS = "alias"
    FUNCTION = "function"
    ACCESSOR = "accessor"


class OriginTier(StrEnum):
    MODULE_OUTPUT = "module_output"
    # A declared dependency's own archive, read because the module asked for it
    # (D04 §2a's opt-in). A FACTUAL origin and never a trust judgement, which is
    # exactly why it is its own member rather than one of the two below: the
    # analysis knows the class came out of a dependency and does not know whose
    # dependency it is. `first_party`/`third_party` are that second question,
    # answered by the group patterns D04 §2 declares — unimplemented today, so
    # writing either here would be a guess, while writing `module_output` would
    # be a claim known to be false.
    DEPENDENCY = "dependency"
    FIRST_PARTY = "first_party"
    THIRD_PARTY = "third_party"
    PLATFORM = "platform"


class Protocol(StrEnum):
    HTTP = "http"
    SOAP = "soap"
    GRPC = "grpc"
    KAFKA = "kafka"
    JMS = "jms"
    SQS = "sqs"
    PUBSUB = "pubsub"
    # 2H design §1. The three HTTP-adjacent protocols, added in one edit
    # because the set is closed (NFR-5): a member the phase has not reached
    # yet costs one line here, while adding them one task at a time costs
    # three schema changes to the same set. `graphql` is consumed this task;
    # `websocket` and `sse` by later ones.
    #
    # Each is its own protocol rather than a flavour of `http` because D01's
    # wire identity is protocol-scoped and none of the three IS an HTTP route:
    # a GraphQL schema is N boundaries behind one POST path, a WebSocket
    # connection fans into N destinations, and an SSE stream is a route whose
    # return type turned it into something a request/response comparison
    # cannot match against.
    GRAPHQL = "graphql"
    WEBSOCKET = "websocket"
    SSE = "sse"
    # 2O design §3a. Two broker families in one edit, for the reason the 2H
    # block above states: the set is closed, so a member a later task needs
    # costs one line here and a schema change if it arrives alone. Each is its
    # own protocol because linking gates on protocol equality (DR-5) — an AMQP
    # exchange can never be answered by a Pulsar topic, and neither is a JMS
    # queue, which is why Stream's `rabbit: jms` stopgap MIGRATED in Task 2
    # (`spring-cloud-stream.yml` now maps `rabbit: amqp`).
    AMQP = "amqp"
    PULSAR = "pulsar"
    # F2 §3.6. Its own protocol on the same DR-5 argument: an RSocket route can
    # never be answered by a STOMP destination — different framing over a
    # different transport — and publishing one as the other is the wrong-PROTOCOL
    # fabrication this member exists to end.
    #
    # It arrives alone rather than beside a sibling, which the comment above says
    # costs a schema change; this is that change. `docs/COVERAGE.md` had stated
    # the defect in place since `A-C1`, with the reason it stayed open: "separating
    # them needs a fact that tells an RSocket registration from a STOMP one, and
    # neither catalog reads one". Measured
    # (`scripts/probes/w16_rsocket_versus_stomp.md`): Spring does not distinguish
    # them ON THE CLASS at all — both handler predicates test `@Controller`
    # identically — and the fact that does is which handler auto-configuration
    # would register, gated on a library being present.
    RSOCKET = "rsocket"


class Direction(StrEnum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"
    BOTH = "both"


class RootKind(StrEnum):
    """What kind of thing a trace starts from (D00 §4, 2Q `I1`).

    `CONTEXT.md` settles the modelling: a root is "an inbound endpoint, a
    scheduled job, or a program entry point" — three kinds, and the set is
    those three.

    **It was six, and four of them were one member spelled per protocol.**
    D00 §4 documented `http_inbound`, `soap_inbound`, `grpc_inbound` and
    `message_inbound` beside `scheduled` and `cli_entry`, with no producer for
    any of them. Collapsing the four is not a narrowing: protocol is a property
    of an endpoint (`CONTEXT.md`), an inbound endpoint row already carries it,
    and a second copy on the root would be the same value in two places with
    nothing keeping them equal. `message_inbound` was worse than redundant —
    it named a `message` protocol family this schema RETIRED, so the one root
    kind a broker listener could take named nothing in `Protocol` at all.
    `cli_entry` becomes `ENTRY_POINT` for the reason `CONTEXT.md` writes it
    that way: a `main` is a program entry point whether or not anything about
    it is a command-line interface, and `cli` claimed a surface nobody
    measured.

    **`ENTRY_POINT` has no producer, and that is stated rather than glossed**
    (§5.3, GUIDELINES §2). Which signature starts a program is knowledge about
    a LANGUAGE, and ARCHITECTURE §10 keeps language knowledge out of the
    language-blind half — so its producer is a catalog, and no catalog declares
    one yet (`docs/open-issues.md`, OI-22). The member is here anyway because
    the traversal that reads this table branches on no kind at all: it takes a
    root, and a root of this kind traces exactly as the other two do the day
    something writes one.
    """

    INBOUND_ENDPOINT = "inbound_endpoint"
    SCHEDULED = "scheduled"
    ENTRY_POINT = "entry_point"


class Format(StrEnum):
    """What is on a channel's wire (2G design §4). A property of the channel,
    inferred, never a protocol and never a property of a payload *type*: a
    protobuf-typed payload under a JSON media declaration is `JSON`.

    `endpoints.format` holds one of these or NULL, and NULL is an answer —
    the ladder (2G design §5) reached no rung, and `format_resolution` says
    `unresolved` beside it.
    """

    JSON = "json"
    PROTOBUF = "protobuf"
    AVRO = "avro"
    XML = "xml"
    STRING = "string"
    BYTES = "bytes"


# Reserved: named by the design so a catalog cannot quietly claim it, and
# refused where a catalog writes it (2G design §4, §11 — JSON Schema and XSD
# are out of scope this phase). The 2F `from_key_prefix` precedent: a value
# the design names but nothing implements must fail loudly rather than be
# silently read as something else.
RESERVED_FORMATS = frozenset({"json_schema"})


class Anchor(StrEnum):
    """Where render is allowed to place an enrichment claim (2K design §6).

    Not a D00 §4 fact-stream set like the rest of this module — an anchor is a
    position in a rendered document, and it is the DOCUMENT that says which
    positions exist. It lives here anyway, and deliberately: NFR-5's rule is
    that a closed set has exactly one definition, and
    `test_closed_sets_are_defined_only_where_the_schema_defines_them` enforces
    that by file. A second home for closed sets would make the rule a
    convention again.

    Adding a value here is half a change: the other half is a placement rule
    in `egress/render/document.py`'s `_Anchors`, without which render has an
    anchor it cannot put anywhere.
    """

    AFTER_ENDPOINT_TABLE = "after-endpoint-table"
    AFTER_COMPONENT_OVERVIEW = "after-component-overview"
    BESIDE_OPEN_QUESTION = "beside-open-question"
    END_OF_DOCUMENT = "end-of-document"


class TraceStop(StrEnum):
    """Why a walk did not expand a step (2Q `G4`, D01 §3's Traces).

    Not a D00 §4 fact-stream set — the `Anchor` precedent, and here for the same
    reason: NFR-5's rule is that a closed set has exactly one definition, and
    `test_closed_sets_are_defined_only_where_the_schema_defines_them` enforces
    that by file.

    **It is deliberately NOT D00 §4's `terminal_kind`, and the difference is the
    whole reason it exists.** `terminal_kind` classifies what a call REACHES —
    `persistence`, `async_handoff`, an `outbound_call` in D01's sense of a
    matched outbound endpoint — and three of its members need framework
    knowledge no pass has applied at a call site: a data-access call is
    `persistence` only to something that knows the callee is one, and nothing
    here does. Publishing a guess under that name would be a classification a
    reader takes as measured. These four members answer a question the walk can
    answer entirely from what it did: it is a property of the WALK, never of the
    callee, and every one of them is decided without reading a catalog.

    A step with no stop reason was expanded. A step that was expanded and has no
    children is a method whose body this workspace read and which calls nothing
    — that needs no member, because the absence of children says it exactly.
    """

    # The workspace read no body for the callee. The ruled third-party
    # boundary: a mapper, a repository, a driver, anything in the JDK — the call
    # IS the terminal, and the row names it.
    BOUNDARY = "boundary"
    # The callee is already on the path from the root to this step. Recursion is
    # real code; the walk states it and stops rather than following it forever.
    CYCLE = "cycle"
    # The callee was expanded elsewhere in THIS trace, on a path that is not
    # this one. Its subtree is shown at its first occurrence; repeating it would
    # copy a shared subtree once per route that reaches it, which is the cost
    # D01 gives as the reason a trace is a walk rather than a stored table.
    REVISITED = "revisited"
    # The walk's depth bound was reached. **The one member that reports a limit
    # rather than the code**, and it exists so that a bound is never applied
    # silently: a truncated trace that looked complete would be an under-report
    # with nothing saying so.
    DEPTH_LIMIT = "depth_limit"


_RANKS = {Evidence.HUMAN: 90, Evidence.LLM: 10}
_CODE_DERIVED_RANK = 50


def precedence_of(evidence: Evidence) -> int:
    """Precedence is derived, never stored (D00 §3, ARCHITECTURE DR-3).

    Storing it would admit states like human evidence at rank 10, and would
    freeze the rank table into every published bundle.
    """
    return _RANKS.get(evidence, _CODE_DERIVED_RANK)
