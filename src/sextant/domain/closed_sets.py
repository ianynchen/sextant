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


class Direction(StrEnum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"
    BOTH = "both"


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


_RANKS = {Evidence.HUMAN: 90, Evidence.LLM: 10}
_CODE_DERIVED_RANK = 50


def precedence_of(evidence: Evidence) -> int:
    """Precedence is derived, never stored (D00 §3, ARCHITECTURE DR-3).

    Storing it would admit states like human evidence at rank 10, and would
    freeze the rank table into every published bundle.
    """
    return _RANKS.get(evidence, _CODE_DERIVED_RANK)
