"""The fact kinds of D00 §5. Validated at write time, per NFR-10."""

from typing import Annotated, Literal

from pydantic import BaseModel, Field

from sextant.domain.closed_sets import ConstructKind, OriginTier

type LiteralValue = str | int | float | bool | list["LiteralValue"]


class TypeRef(BaseModel):
    """A symbol reference plus optional type arguments, recursively (D00 §5a).
    Recorded verbatim: unwrapping envelopes is catalog knowledge, not the
    scanner's.

    `wire_type`/`wire_format`/`nullable`/`nullable_resolution` are the 2B wire
    projection (D00 §5a/§5b), carried at every level of the reference.
    Optional because older hand-built facts may not carry them."""

    model_config = {"frozen": True}
    symbol: str
    arguments: list["TypeRef"] = Field(default_factory=list)
    wire_type: str | None = None
    wire_format: str | None = None
    nullable: bool | None = None
    nullable_resolution: str | None = None


class AnnotationUse(BaseModel):
    model_config = {"frozen": True}
    annotation: str
    args: dict[str, LiteralValue] = Field(default_factory=dict)


class Parameter(BaseModel):
    model_config = {"frozen": True}
    name: str | None = None
    type: TypeRef
    annotations: list[AnnotationUse] = Field(default_factory=list)


class Signature(BaseModel):
    model_config = {"frozen": True}
    parameters: list[Parameter] = Field(default_factory=list)
    returns: TypeRef | None = None


class ClasspathEntry(BaseModel):
    model_config = {"frozen": True}
    path: str
    tier: OriginTier
    coordinates: str | None = None


class Document(BaseModel):
    """One per source file. Language, tool and version live here, never on a
    fact (D00 §2)."""

    model_config = {"frozen": True}
    kind: Literal["document"] = "document"
    document_id: str
    relative_path: str
    module_id: str
    language: str
    sextant_version: str
    fact_schema_version: str
    scanner_id: str
    scanner_version: str
    content_hash: str
    origin_entry: str
    origin_tier: OriginTier
    redaction_set_hash: str
    partial: bool = False
    partial_reason: str | None = None


class ModuleFact(BaseModel):
    model_config = {"frozen": True}
    kind: Literal["module"] = "module"
    document_id: str
    module_id: str
    module_kind: str
    languages: list[str]
    source_roots: list[str]
    output_dirs: list[str]
    classpath: list[ClasspathEntry] = Field(default_factory=list)


class SymbolFact(BaseModel):
    model_config = {"frozen": True}
    kind: Literal["symbol"] = "symbol"
    document_id: str
    symbol: str
    construct_kind: ConstructKind
    enclosing: str | None = None
    signature: Signature | None = None
    visibility: str = "public"
    line_start: int = 0
    line_end: int = 0
    # D00 §5a: always written on a field fact — a value bound to the type
    # rather than an instance, and a declaration the language marks as not
    # serialized. Defaults empty for constructs that carry no modifiers.
    modifiers: dict[str, bool] = Field(default_factory=dict)
    # D00 §5a's PTR carrier: a class symbol's generic supertype reference,
    # when the superclass signature is generic.
    supertype: TypeRef | None = None
    # `implemented_interfaces`: erased interface symbols a class declares,
    # in declaration order. Empty for a class implementing none.
    interfaces: list[str] = Field(default_factory=list)


class AnnotationFact(BaseModel):
    model_config = {"frozen": True}
    kind: Literal["annotation"] = "annotation"
    document_id: str
    target: str
    use: AnnotationUse
    retention: str
    # D00 §5a: locates a type-use annotation within the type reference it
    # annotates (a field or a type). Absent for a declaration-level annotation.
    type_path: str | None = None


class CallArgument(BaseModel):
    model_config = {"frozen": True}
    kind: Literal[
        "string",
        "int",
        "long",
        "boolean",
        "enum",
        "class",
        "lambda",
        "instance",
        "null",
        "unresolved",
    ]
    value: LiteralValue | None = None
    symbol: str | None = None
    source: int | None = None


class CallTarget(BaseModel):
    model_config = {"frozen": True}
    owner: str
    name: str
    descriptor: str


class CallSiteFact(BaseModel):
    """D00 §5's load-bearing fact kind: caller, target, dispatch form, the v1
    control-flow position, and the resolved argument slots."""

    model_config = {"frozen": True}
    kind: Literal["call_site"] = "call_site"
    document_id: str
    caller: str
    target: CallTarget
    invoke_kind: str
    ordinal: int
    receiver: int | None = None
    result: int | None = None
    arguments: list[CallArgument] = Field(default_factory=list)


class ConfigEntryFact(BaseModel):
    """One key read from a configuration file (D00 §5c). Neutral pieces
    only: a reader never layers, resolves a placeholder, or interprets a
    profile — that is M04 pass 2's job, reading catalog data this fact
    knows nothing about."""

    model_config = {"frozen": True}
    kind: Literal["config_entry"] = "config_entry"
    document_id: str
    key_raw: str
    key_path: str
    # Verbatim, always a string, never coerced: a value is a claim to
    # resolve, not a typed answer (D00 §5c).
    value: str
    # The source file's document index for a multi-document YAML file
    # (`---`-separated); always 0 for a single-document format such as
    # properties. Needed to tell a multi-document file's on-profile
    # activations apart.
    doc_index: int = 0


Fact = Annotated[
    ModuleFact | SymbolFact | AnnotationFact | CallSiteFact | ConfigEntryFact,
    Field(discriminator="kind"),
]
