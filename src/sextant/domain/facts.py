"""The fact kinds of D00 §5. Validated at write time, per NFR-10."""

from typing import Annotated, Literal

from pydantic import BaseModel, Field

from sextant.domain.closed_sets import ConstructKind, OriginTier

# D00 §5a's literal model: string, number, boolean, enum reference, class
# reference (both spelled as symbol references) and arrays of these — plus,
# from capability 9.16, an ANNOTATION. An annotation-valued argument is not a
# new vocabulary: it is an `AnnotationUse`, exactly the shape the enclosing use
# already has, so `@RabbitListener(bindings = @QueueBinding(value = @Queue(…)))`
# nests the same way at every level. Recursive, and resolved lazily because
# `AnnotationUse` is defined below in terms of this alias.
type LiteralValue = str | int | float | bool | AnnotationUse | list["LiteralValue"]


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
    # Capability 9.16's own key, and set only on a NESTED use the scanner
    # declined to read to the bottom — the extractor bounds its recursion, and
    # names why here (`depth_limit`) rather than truncating. The annotation's
    # TYPE is real evidence read off the descriptor and is kept; its `args`
    # stay empty because they were never read, which is why this flag has to
    # exist: an empty `args` alone is indistinguishable from an annotation
    # genuinely written with no arguments (GUIDELINES §8). `None` on every use
    # the scanner read in full, which is every outermost one.
    unresolved: str | None = None


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
    # Which artifact outside this module's own output the document was read
    # from, as that artifact's coordinate (D00 §2). NULL — and, on disk,
    # absent — for the module's own output, which is what every document was
    # until libraries could be scanned at all.
    origin: str | None = None


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
    # The `groupId:artifactId` coordinates the module's BUILD declares (2O
    # design §2a, ruling R9), sorted. Its own field rather than `classpath`
    # above, because the two answer different questions and only this one can
    # be answered by both build systems today: a `ClasspathEntry` names a
    # resolved ARCHIVE and its tier, which the Gradle report carries and a
    # parsed POM does not, so filling `classpath` from Maven would mean
    # inventing a path. This field is the coordinate half alone — what the
    # build says it depends on — and it is what a catalog whose framework
    # rule is conditional on a dependency reads (`detect.coordinates`).
    #
    # **Reach differs by build system and the difference is not smoothed
    # over** (`application/ports/detector.py`'s own field states it in full):
    # Gradle reports the resolved compile classpath, transitives included;
    # Maven reports the POM's direct declarations only. Empty means "this
    # analysis recorded none", never "the classpath is empty".
    dependency_coordinates: list[str] = Field(default_factory=list)


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
    # Capability 9.14: mirrors `supertype`'s PTR-carrier rule one level over,
    # applied to `implements` instead of `extends`. `interfaces` above erases
    # `CrudRepository<Order, Long>` to a bare symbol; this is the only place
    # a generic superinterface's type arguments survive. Empty when nothing
    # declared here is generic — D00's "nothing generic, nothing captured"
    # rule, applied per interface.
    generic_interfaces: list[TypeRef] = Field(default_factory=list)
    # Capability 9.13: D00 §4's `relationship_kind: extends`, made real. The
    # erased symbol of a class's direct superclass, read straight off the
    # class file regardless of whether its `Signature` attribute is generic
    # (`supertype` above only fires when it is). None for the JVM's universal
    # root type — every interface carries this same class-file entry though
    # no interface "extends" it, and every root class gets it implicitly, so
    # writing it there would say nothing with it.
    superclass: str | None = None


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
        "field",
        # The caller's own parameter N — `value` is that index, never the
        # local slot a JVM happens to keep it in (D00 §5).
        "parameter",
        # Capability 9.15: ONE argument that happens to be an array, with its
        # own element arguments in `elements`. Never N arguments — unpacking
        # would renumber every slot after it and make arity unreadable.
        "array",
        "null",
        "unresolved",
    ]
    value: LiteralValue | None = None
    symbol: str | None = None
    source: int | None = None
    # Capability 9.15's own key, on the `array` kind alone: the argument list
    # a varargs call site's `ANEWARRAY`/`AASTORE` construction builds, each
    # element carrying the same kind it would carry as a single argument in
    # the same position. `None` on every other kind, and — the one place an
    # empty value says something an absent one would not — an EMPTY list for
    # a zero-length varargs call, which is a real call rather than a failure
    # to read one. An array the extractor could not read end to end stays
    # `unresolved`, so `elements` is never a partial list.
    elements: list["CallArgument"] | None = None


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


class FieldWriteFact(BaseModel):
    """A constructor assigns parameter N directly to field F (D00 §5):
    constructors only, direct traces only. A computed assignment —
    concatenation, a default expression, anything but a bare parameter load —
    emits no fact at all, and the field resolution ladder (2F) degrades
    honestly rather than guessing a source."""

    model_config = {"frozen": True}
    kind: Literal["field_write"] = "field_write"
    document_id: str
    field: str
    from_parameter: int


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


class EmbeddedDescriptorFact(BaseModel):
    """One schema payload an artifact carries verbatim (2G design §1). The
    emitter never parses it: a protobuf descriptor arrives base64-encoded and
    an Avro schema as its JSON text, exactly as the class embedded it, so no
    extractor in any language has to link a schema runtime to produce this.

    `symbol` is the schema holder — the generated class for a compiled
    payload, the record's own name for one read off a source file — and it is
    what a gap names when the payload cannot be interpreted."""

    model_config = {"frozen": True}
    kind: Literal["embedded_descriptor"] = "embedded_descriptor"
    document_id: str
    symbol: str
    # `wsdl` covers both `.wsdl` and `.xsd`: a WSDL declares its payload types
    # by embedding XSD in `<types>`, so the two extensions are one type
    # universe rather than two formats.
    schema_format: Literal["protobuf", "avro", "graphql", "wsdl"]
    payload: str
    # Compiled unless a source-file reader says otherwise: the artifact that
    # runs is the authority (DR-4), and it is also the common case.
    origin: Literal["compiled", "source"] = "compiled"


class DeclaredFieldFact(BaseModel):
    """One field of a declared shape, already in D00 §5b's wire vocabulary —
    which is what schema formats natively say, so nothing is projected here
    that the schema did not state.

    `name` is the schema's own spelling and `wire_name` the encoded one (a
    protobuf `json_name`); they differ, so both are kept. `item` is D01 §5's
    recursive `{wire_type, wire_format, nullable, shape_id?, item?}`
    descriptor for what a collection holds, and `shape_ref` the shape a
    singular object field points at."""

    model_config = {"frozen": True}
    name: str
    wire_name: str
    # NULL for a format with no field numbers — Avro, and every
    # annotation-derived shape.
    field_number: int | None = None
    wire_type: str
    wire_format: str | None = None
    required: bool
    nullable: bool
    default: str | None = None
    item: dict[str, object] | None = None
    shape_ref: str | None = None
    enum_symbols: list[str] | None = None


class OperationRecord(BaseModel):
    """What a service operation declares beyond its name (2O design §1a).

    Optional on `DeclaredShapeFact`, populated only when `role == "operation"`
    — a fact-schema amendment (`fact_schema_version` bumped, D00 §5's own
    amendment note records the estate cost). Added for gRPC, whose methods
    carry a request AND a response type plus the two streaming flags; 2I's
    SOAP operations may fill the same record later — today their output side
    is honestly NULL and nothing changes for them, because `wsdl_xsd.py`
    never constructs one."""

    model_config = {"frozen": True}
    # The descriptor's own fully-qualified message names — an intra-descriptor
    # join to the SAME descriptor's `declared_shape` universe (2O design §1a),
    # never a guess across universes. `None` for a format that has not filled
    # this record's output side yet (SOAP, today).
    input_ref: str | None
    output_ref: str | None
    client_streaming: bool
    server_streaming: bool


class DeclaredShapeFact(BaseModel):
    """One message or record type, as its schema declares it (D00 §5,
    D01 §3). Never emitted by an extractor: it is the interpreter's output,
    which keeps schema-format knowledge in one place (2G design §3)."""

    model_config = {"frozen": True}
    kind: Literal["declared_shape"] = "declared_shape"
    document_id: str
    symbol: str
    # The schema's own full name (`sextant.orders.OrderRequest`), written for
    # both origins. `symbol` cannot serve as the identity across them — a
    # compiled shape is named by the class it travels as and a source shape by
    # the schema — so this is what DR-4's compiled-beats-source precedence
    # compares, and the one field on which the two origins can meet.
    schema_name: str
    schema_format: Literal["protobuf", "avro", "graphql", "wsdl"]
    origin: Literal["compiled", "source"]
    # A schema compiled into the artifact is compiler evidence (COVERAGE
    # §4.1's strongest tier); a schema file in the repository is a
    # declaration, and says nothing about what the build actually shipped.
    evidence: Literal["compiler", "declared"]
    # The operation root this type serves, where its schema names one: a
    # schema format may declare that one of its types is the entry point every
    # query (or mutation, or subscription) is addressed against, and which
    # type that is can be renamed, so it cannot be recovered from the type's
    # own name downstream. `operation` is the fourth word and the one that
    # names the type as an operation itself rather than as a root operations
    # hang off, which a schema format may equally state. NULL for every type
    # that is an ordinary payload, which is nearly all of them.
    role: Literal["query", "mutation", "subscription", "operation"] | None = None
    # What a `role == "operation"` shape declares beyond its name — a gRPC
    # method's request/response refs and streaming flags (2O design §1a).
    # NULL for every shape `role` does not mark `"operation"`, and NULL today
    # even for a WSDL one (2I's own boundary, restated on `OperationRecord`
    # itself): a fact-schema amendment gains a field, never fills it
    # retroactively for a format that does not populate it.
    operation: OperationRecord | None = None
    fields: list[DeclaredFieldFact] = Field(default_factory=list)


Fact = Annotated[
    ModuleFact
    | SymbolFact
    | AnnotationFact
    | CallSiteFact
    | FieldWriteFact
    | ConfigEntryFact
    | EmbeddedDescriptorFact
    | DeclaredShapeFact,
    Field(discriminator="kind"),
]
