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


class Direction(StrEnum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"
    BOTH = "both"


_RANKS = {Evidence.HUMAN: 90, Evidence.LLM: 10}
_CODE_DERIVED_RANK = 50


def precedence_of(evidence: Evidence) -> int:
    """Precedence is derived, never stored (D00 §3, ARCHITECTURE DR-3).

    Storing it would admit states like human evidence at rank 10, and would
    freeze the rank table into every published bundle.
    """
    return _RANKS.get(evidence, _CODE_DERIVED_RANK)
