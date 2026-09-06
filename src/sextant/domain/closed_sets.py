"""The closed sets of D00 §4. Adding a value is a schema change, never an
implementation choice — see NFR-5."""

from enum import StrEnum


class Resolution(StrEnum):
    RESOLVED = "resolved"
    NARROWED = "narrowed"
    PARTIAL = "partial"
    UNRESOLVED = "unresolved"


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


_RANKS = {Evidence.HUMAN: 90, Evidence.LLM: 10}
_CODE_DERIVED_RANK = 50


def precedence_of(evidence: Evidence) -> int:
    """Precedence is derived, never stored (D00 §3, ARCHITECTURE DR-3).

    Storing it would admit states like human evidence at rank 10, and would
    freeze the rank table into every published bundle.
    """
    return _RANKS.get(evidence, _CODE_DERIVED_RANK)
