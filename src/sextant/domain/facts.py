"""The fact kinds of D00 §5. Validated at write time, per NFR-10."""

from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator

from sextant.domain.closed_sets import ConstructKind, OriginTier, Visibility

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
    # The DESCRIPTOR's own symbol for this position, beside `type`, which carries
    # the declared signature's answer where there is one (D00 §5a).
    #
    # The two differ only for a type VARIABLE — `type` then names the variable,
    # which is what a generic substitution binds, while this names what the
    # runtime actually erased it to. A variable's name is scoped to the
    # declaration that introduced it, so it can never be compared between two of
    # them; this can, and every consumer that keys or looks up by parameter type
    # reads it. Written on every parameter, so a positional read of the list is
    # always the same length as the parameter list itself.
    #
    # None only for a fact written before the field existed.
    erased_symbol: str | None = None
    annotations: list[AnnotationUse] = Field(default_factory=list)
    # This slot is the declaration's extension receiver: the runtime sees a
    # parameter, the author wrote a receiver (`fun String.shout()`). Published
    # so a consumer can drop it from the declared signature, and kept rather
    # than dropped here because a call site names the method by its full
    # descriptor and the receiver's type is real evidence. Absent means false,
    # as `bridge_of` is absent rather than null; only ever the first slot the
    # declaration owns. Unrelated to `CallSiteFact.receiver`, which is the
    # argument SLOT a call's target object came from.
    receiver: bool = False


class TypeParameter(BaseModel):
    """One formal type parameter a class or method declares, with its bounds
    (D00 §5a). `class Box<T extends Comparable<T>>` yields one of these.

    The NAME and the POSITION are the load-bearing half: a type reference's
    `symbol` may now be a bare type variable — `T`, read off the `Signature`
    attribute rather than erased to whatever the descriptor says — and this is
    what that variable refers back to.

    Bounds are recorded exactly as the class file states them, an explicit
    universal-root-type bound included: a compiler may write that bound for a
    parameter the source declared with none, in which case the two spellings are
    the same declaration and there is nothing to preserve by dropping it. An
    empty list would then mean either "unbounded" or "the scanner did not read
    the bound" (GUIDELINES §8). Which bound a given compiler writes is the
    extractor's knowledge, not this record's."""

    model_config = {"frozen": True}
    name: str
    bounds: list[TypeRef] = Field(default_factory=list)


class Signature(BaseModel):
    model_config = {"frozen": True}
    parameters: list[Parameter] = Field(default_factory=list)
    returns: TypeRef | None = None
    # W7: the types a method DECLARES it can fail with (JVMS 4.7.5), in declaration
    # order. Part of the signature because it is part of what a caller must handle
    # to call it. Empty for the great majority, which declare none.
    throws: list[str] = Field(default_factory=list)


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
    # An integer, not a version string (Step 0): the stamp is compared for
    # equality and nothing else, and a text type is what let its four
    # producers hold two different values undetected.
    fact_schema_version: int
    # WHICH facility produced this document (D00 §2). There is no version
    # beside it: a facility Sextant ships moves with `sextant_version` above,
    # and the third-party libraries that CAN move on their own are recorded
    # once per workspace in `metadata.json` rather than repeated on every
    # document that one scanner wrote.
    scanner_id: str
    # The class-file format version this document was read from (JVMS 4.1's
    # `major_version`), or 0 where the source is not a class file at all — a
    # config or schema document has no such version, and 0 is outside every
    # real range (the format starts at 45) so it cannot be mistaken for one.
    class_major: int = 0
    # WHICH COPY of an overlaid class this is (JEP 238): `base` for the archive
    # root — and for every document that is not a class in a multi-release jar
    # at all — or the release its `META-INF/versions/N/` prefix declares, as a
    # decimal string. A TAG, never a selection: which copy actually loads
    # depends on the release the DEPENDING module targets, so one scan of a jar
    # serves modules that target different ones and the choice is made
    # downstream at resolve.
    class_release: str = "base"
    # The class-file's own name with any `META-INF/versions/N/` prefix removed
    # — the name the JVM knows the class BY. It is the key two copies of one
    # class are recognised as copies on, which `relative_path` cannot be: that
    # is the SOURCE path, and a nested class shares its outer's. Empty for a
    # document that is not a class file.
    class_name: str = ""
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
    # D00 §2 (2026-10-21): true on the ONE synthetic document per module that holds
    # every `type_header` fact — not a class file this module built, so every count
    # that means "class files read" leaves it out. Absent on disk, and so false,
    # for every real document.
    header_only: bool = False
    # On the header-only document: how many dependency types this module names were
    # found in NO archive on its classpath (spec 2026-10-21 §3e) — the JDK's, and every
    # one a classpath that is not the real one leaves out. 0 on every other document.
    type_headers_unlocated: int = 0


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
    # The compiler target release this module's BUILD declares (W3b), and
    # `None` where it declares none. Carried on the module fact because its
    # consumer runs at RESOLVE: which overlay of a class in a multi-release
    # dependency actually loads is a property of the module doing the
    # depending, so the answer has to travel with the module rather than with
    # the archive — one scan of a jar serves modules that target different
    # releases.
    declared_release: int | None = None
    # The reactor siblings this analysis scanned for their TYPES (F4 §5.2, W24), as
    # their coordinates, sorted. Carried on the module fact because its consumer runs at
    # RESOLVE and there is nothing else there that can tell them apart.
    #
    # **Why they need telling apart from any other dependency.** A sibling is scanned
    # AUTOMATICALLY — nobody asked for it, it is on the classpath and its types appear
    # in this module's signatures — so publishing its controllers as this module's API
    # would be a fabrication on the analysis's own initiative. `extract_libraries` is the
    # opposite: a coordinate a person wrote into `.sextant.yml`, which D04 §2a defines as
    # "scan this dependency's own bytecode as well as mine", and a shipped test asserts
    # that an opted-in library's SOAP operation DOES reach the endpoint table. Consent is
    # the whole difference, and it is not readable from the tier — both are `dependency`.
    sibling_coordinates: list[str] = Field(default_factory=list)
    # Who answered for `dependency_coordinates`/`dependency_versions` and why the build
    # tool did not, when it did not (`ModuleModel`'s own fields, spec 2026-10-21 §3c).
    # On the fact because its readers run at RESOLVE: `dependencies.py` must say
    # "could not tell" for a transitive only while the source is `declared`.
    dependency_source: str = "declared"
    dependency_source_reason: str | None = None
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
    # Maven reports what the pom declares plus what it inherits from every
    # ancestor pom the detector could open, and no transitives (F1). Empty
    # means "this analysis recorded none", never "the classpath is empty".
    dependency_coordinates: list[str] = Field(default_factory=list)
    # The version each of those coordinates resolved to, for the subset that
    # resolved (F1), in sorted key order (NFR-1). Written beside the
    # coordinates rather than folded into them because the coordinate is the
    # identity a catalog's `detect.coordinates` matches on.
    #
    # **A coordinate absent from this map is a version this analysis could not
    # read, never a dependency with no version** — the two build systems reach
    # differently and the Maven side needs the pom that states a managed or
    # property-held version to be readable. A rule scoped to a version range
    # must therefore treat an absent version as UNANSWERABLE, the same way the
    # dependency gate treats an absent coordinate list.
    dependency_versions: dict[str, str] = Field(default_factory=dict)


class SymbolFact(BaseModel):
    model_config = {"frozen": True}
    kind: Literal["symbol"] = "symbol"
    document_id: str
    symbol: str
    construct_kind: ConstructKind
    enclosing: str | None = None
    signature: Signature | None = None
    visibility: Visibility = Visibility.PUBLIC
    line_start: int = 0
    line_end: int = 0
    # D00 §5a: always written on a field fact — a value bound to the type
    # rather than an instance, and a declaration the language marks as not
    # serialized. Defaults empty for constructs that carry no modifiers.
    modifiers: dict[str, bool] = Field(default_factory=dict)
    # The name of the declared method this one stands for, on two shapes and
    # no other: a compiler-emitted default-argument bridge (`<fn>$default`,
    # `OI-81`), beside the `synthetic: true` its modifiers already carry; and
    # a static body inside a compiler-emitted holder of an interface's default
    # method bodies, whose own type fact carries `implements_default_of`
    # (the delivery register's `DefaultImpls` item). Absent on every other
    # fact.
    bridge_of: str | None = None
    # The interface whose default method bodies this TYPE holds, as a symbol
    # spelled the way `enclosing` is — the compiler-emitted nested class whose
    # every method is static with that interface at slot 0 and carries
    # `bridge_of`. Absent on every other fact. Read by `resolve/dispatch.py`,
    # which makes such a body the candidate for an interface method that
    # declares no body of its own.
    implements_default_of: str | None = None
    # The method holding a class-compiled lambda's body, on that lambda's TYPE
    # fact alone (D00 §5, spec 2026-09-19 §3b): spelled as a `lambda`
    # argument's `symbol` is — the bare descriptor, no module coordinates — so
    # it joins to the body's own method fact by descriptor suffix. Absent on
    # every other fact. Read by `resolve/effective_calls.py`, which hands every
    # engine an `instance` of such a class as the `lambda` it stands for.
    lambda_body: str | None = None
    # JVMS 4.7.22 `AnnotationDefault` (W4): the value an ANNOTATION TYPE's
    # element takes when a use omits it. Present only on such an element and
    # only where it has a default; absent everywhere else.
    #
    # Its consumer is the catalogs, which currently HARDCODE these — a
    # prediction §8.1 forbids, because it states what a framework does at a
    # version nobody measured. Reading it means a catalog can ask the jar
    # instead of asserting.
    #
    # A `LiteralValue`, the SAME grammar an annotation's arguments already use
    # at a use site — a default can be an array, an enum constant or a nested
    # annotation, and re-spelling that here would be a second vocabulary for
    # one thing.
    annotation_default: LiteralValue | None = None
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
    # W7: the complete set of types permitted to extend a SEALED one (JVMS 4.7.31).
    # The one case where "every implementation of this" is answerable outright
    # rather than approximated by whatever the scan happened to see. Empty for
    # every type that is not sealed.
    permits: list[str] = Field(default_factory=list)
    # W7: the top-level type whose nest this one belongs to (JVMS 4.7.28). Distinct
    # from `enclosing`, which names the IMMEDIATE encloser — for `A$B$C` that is
    # `A$B` where the nest host is `A`. The top-level answer is the one OI-45
    # records `outer_type_of` guessing at by splitting a name on `$`.
    nest_host: str | None = None
    # The same relationship from the host's side (JVMS 4.7.29): every type sharing
    # this one's nest. Only a host carries it.
    nest_members: list[str] = Field(default_factory=list)
    # Attributes this scanner SAW and did not read — a vendor's, or one from a
    # class-file version newer than the build. By name only: reading the bytes
    # would mean guessing at a layout nobody published. Recorded so §2.3's ledger
    # can say "seen, not read", which is a different claim from "not present".
    unread_attributes: list[str] = Field(default_factory=list)
    # `type_parameters` (W5): the formal type parameters this class or method
    # declares, in declaration order. Empty for the great majority of
    # declarations, which have none — the same "nothing generic, nothing
    # captured" rule `supertype` and `generic_interfaces` follow, so the key is
    # absent rather than an empty list on every fact.
    type_parameters: list[TypeParameter] = Field(default_factory=list)


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
        # W4: an address the code ASSEMBLES rather than states. javac does not
        # build `"/api/" + version + "/orders"` in the bytecode — it emits one
        # `invokedynamic` plus a recipe holding the literal parts — so `value`
        # is the TEMPLATE, `/api/{}/orders`, with a hole per runtime value.
        #
        # The hole is unnamed on purpose: a path variable's name was never part
        # of the address (a server routes `/api/owners/42` to
        # `/api/owners/{ownerId}` by POSITION and may rename it freely), so `{}`
        # is exactly what both sides share and naming it would invent one the
        # class file often does not carry. What FILLS the hole is the concat
        # site's own call-site fact, reached by `source` -> `result`.
        "concat",
        "null",
        # Capability 9.19 (spec 2026-10-21-merged-values-design.md): a value with SEVERAL
        # producers — a local reassigned on one branch — with each producer in `candidates`,
        # rendered in this same grammar. "One of these", chosen by nobody: the walk resolves
        # a merge whose candidates share a root, inexactly, and leaves every other one
        # `unresolved` exactly as the bare kind below used to say for all of them.
        "merge",
        "unresolved",
    ]
    value: LiteralValue | None = None
    symbol: str | None = None
    source: int | None = None
    # Capability 9.19's own key, on the `merge` kind alone.
    candidates: list["CallArgument"] | None = None
    # Capability 9.15's own key, on the `array` kind alone: the argument list
    # a varargs call site's `ANEWARRAY`/`AASTORE` construction builds, each
    # element carrying the same kind it would carry as a single argument in
    # the same position. `None` on every other kind, and — the one place an
    # empty value says something an absent one would not — an EMPTY list for
    # a zero-length varargs call, which is a real call rather than a failure
    # to read one. An array the extractor could not read end to end stays
    # `unresolved`, so `elements` is never a partial list.
    elements: list["CallArgument"] | None = None
    # How many of a lambda body's LEADING parameters are captured values (spec §10b):
    # the indy's argument count, minus one when the implementation handle is an
    # instance kind, because that first captured value becomes the body's receiver.
    # The metafactory lays the body's parameters out as captured values first, then
    # the interface's, so the interface's parameter k is the body's parameter
    # `captures + k`. `-1` means the interface's first parameter IS the receiver (an
    # unbound instance reference). Only a `lambda`-kind argument carries it — and
    # this one field covers every place the argument grammar appears, because a
    # call site's `arguments`, a `method_return`'s `value` and an `array`'s
    # `elements` are all entries of the same grammar, modelled by this class.
    captures: int | None = None


class CallTarget(BaseModel):
    """What a call site names. `name` and `descriptor` on every site that dispatches
    to a method — which is every one except a THROW — and `owner` on all but a rethrow
    whose type this pass could not read.

    The invariant is enforced on `CallSiteFact` rather than here, because it is stated
    in terms of `invoke_kind`, which lives there. A validator on this model can only see
    three optional fields and would accept a bare `CallTarget()` — which is what the
    first version of it did, while its own docstring claimed it stopped exactly that.

    `G-52`: a throw site is call-site-shaped and its target is the thrown
    exception TYPE (D00 §5), so the owner is the whole of it. There is no
    method, and the two keys that name one are absent rather than empty — the
    same rule `implementation` states below for the opposite case, and for the
    same reason: an empty name matches nothing while looking like a name, so a
    consumer joining `target` to method symbols would be reading a claim about
    code that does not exist. `schema.sql`'s `->>` already yields NULL for an
    absent key, so the projection needed no change.
    """

    model_config = {"frozen": True}
    owner: str | None = None
    name: str | None = None
    descriptor: str | None = None


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
    # Which of the enclosing method's parameters the receiver is, when it is one (D00 §5
    # numbering: `this` is not a parameter). `receiver` is the producing call's id and is
    # null for a parameter, a field and an unreadable receiver alike; this is the half of
    # that answer the argument grammar has carried as `{"kind": "parameter"}` since 9.8,
    # for the receiver slot. Absent everywhere else.
    receiver_parameter: int | None = None
    # The static field the receiver was read from, as the argument grammar's `field` kind
    # names one (`owner#name.`), where it is a `getstatic` (D00 §5). `receiver` still
    # carries the read's own value id, which no other fact names, so without this a call on
    # a file-level `val` joins to nothing. Absent everywhere else.
    receiver_field: str | None = None
    result: int | None = None
    # Capability 9.17: the function this site's dispatch will run, where
    # `target` names the mechanism instead of the code — a JVM
    # `invokedynamic` bootstrapped by `LambdaMetafactory`, whose second
    # bootstrap argument is the lambda body javac lifted out. A **bare**
    # symbol, like the `lambda` argument kind beside it (D00 §1's stability
    # rule), so an in-module body joins to its own method fact by stripping
    # that fact's module prefix. `None` everywhere the target already is the
    # answer, a `StringConcatFactory` site included: there is no
    # implementation method to name there, and naming one would assert a call
    # to code that does not exist.
    implementation: str | None = None
    arguments: list[CallArgument] = Field(default_factory=list)

    @model_validator(mode="after")
    def _only_a_throw_names_no_method(self) -> "CallSiteFact":
        """`G-52`: a throw site names a TYPE and no method; every other site names both.

        Enforced here and not on `CallTarget`, because both halves are only visible
        together: the model that holds `name` and `descriptor` cannot see `invoke_kind`,
        so a validator there accepts a bare target and guarantees nothing. Stated as an
        equivalence rather than one implication, so neither a dispatching call that lost
        its method nor a throw that acquired one can pass.
        """
        # A throw names NEITHER half and a dispatching call names BOTH — two tests, not
        # one comparison of "names a method": under that, a throw carrying a `name` and no
        # `descriptor` did not "name a method" and passed, half a claim about code that
        # does not exist.
        names_a_method = self.target.name is not None and self.target.descriptor is not None
        names_half_of_one = self.target.name is not None or self.target.descriptor is not None
        if names_half_of_one if self.invoke_kind == "throw" else not names_a_method:
            raise ValueError(
                "a `throw` site names a thrown type and no method; every other site names "
                f"both — got invoke_kind={self.invoke_kind!r} with "
                f"name={self.target.name!r}, descriptor={self.target.descriptor!r}"
            )
        if self.invoke_kind != "throw" and self.target.owner is None:
            raise ValueError("a dispatching call site must name an owner")
        return self


class MethodReturnFact(BaseModel):
    """What a method hands back, one fact per return instruction (D00 §5,
    capability 9.18).

    The value chain a round trip needs is already extracted — an argument
    carries the `source` id of the call that produced it — and this is the
    last link: that the value a given call produced is the one the METHOD
    returns. Its consumer is 2Q's cross-method propagation, which joins this
    to the caller's own `result` id.

    `value` is an entry of §5's argument grammar rather than a bare id, and
    that is what keeps two different answers apart: `None` means the return
    pops nothing (a void return — an answer, not a failure), while
    `CallArgument(kind="unresolved")` means it pops something this pass could
    not name. A returned literal, field, parameter or lambda reads exactly as
    it would in an argument slot in the same position.

    A method with several `return` statements has several of these facts, each
    with its own `ordinal`. That is deliberate: two returns are two possible
    answers and no single one, and picking either would be a fact about code
    that may never run.
    """

    model_config = {"frozen": True}
    kind: Literal["method_return"] = "method_return"
    document_id: str
    method: str
    # The return instruction's index among this method's returns, in
    # instruction order — deterministic by construction (NFR-1), and the same
    # role `call_site.ordinal` plays.
    ordinal: int
    value: CallArgument | None = None


class FieldWriteFact(BaseModel):
    """A method assigns a parameter, a constant or a call's result directly to field F
    (D00 §5) — a `PUTFIELD` on `this`, or since 2026-10-26 a `PUTSTATIC` — and
    `written_by` names the method that did it. A computed assignment — concatenation,
    a default expression, a value built with `new` — emits no fact at all, and both
    consumers degrade honestly rather than guessing a source.

    **Constructors only until 2026-10-18**, and the guard was never a soundness
    rule: a setter's assignment is the same `ALOAD 0; ALOAD k; PUTFIELD` triple,
    measured as CP-33 row 1, and lifting it roughly TRIPLED the writes found on
    real code — `spring-petclinic-rest` 86 to 237, `apollo-portal` 553 to 1,638
    (spec `2026-10-18-the-sixth-edge-design.md` §0). A static method's `PUTFIELD`
    is still refused, which IS a soundness rule: slot 0 is its first parameter rather
    than `this`, so it writes another object's field.

    `written_by` is OPTIONAL and absent by default, so a fact written before it
    reads exactly as it did and no schema version moves — the property
    `CallSiteFact.receiver_parameter` and `CallArgument.captures` established
    (`scripts/probes/fact_additivity/run.py` proves it per release). A row
    reaching a consumer without it names no method, and the walk's sixth edge
    skips such a row rather than guessing which method wrote the field."""

    model_config = {"frozen": True}
    kind: Literal["field_write"] = "field_write"
    document_id: str
    field: str
    # **Exactly one of these two says where the value came from.** `from_parameter` is the
    # write the fact was born for — `this.f = parameter` — and `value` is the one added on
    # 2026-10-18 (`OI-138` cause 2): `private String f = "literal"`, which javac compiles
    # into the constructor as `ALOAD 0; LDC; PUTFIELD`. That write has no parameter to point
    # at, so it emitted NO fact and the walk answered `no_writer` about a literal one line
    # above the read. Since 2026-10-26 `value` also carries a CALL'S RESULT — `this.c =
    # Factory.make()`, or a file-level `val client = HttpClient(CIO) { … }` stored in
    # `<clinit>` — as the entry a call argument fed by a call already is: `unresolved` with the
    # call's `source`, a value id in the WRITER's frame. Both are optional, so a fact written
    # before either reads exactly as it did and no schema version moves.
    from_parameter: int | None = None
    value: CallArgument | None = None
    # The writing method's own symbol, in the form `call_sites.caller` carries, so a write
    # and a call name their method identically and the walk needs no reconstruction.
    written_by: str | None = None

    @model_validator(mode="after")
    def _one_source(self) -> "FieldWriteFact":
        """EXACTLY ONE of `from_parameter` and `value`, enforced rather than described.

        Both keys are optional so the fact stays additive, which made "exactly one" a
        sentence in a docstring that nothing checked: neither set, and both set, each
        validated. A fact with neither says a write happened and names no source; a fact with
        both leaves a reader to guess which source the value came from. GUIDELINES §8's rule
        about architecture rules applies to a fact-stream contract (§7) — it is enforceable,
        so it is enforced.
        """
        if (self.from_parameter is None) == (self.value is None):
            raise ValueError(
                "field_write names exactly one source: `from_parameter` for "
                "`this.f = parameter`, or `value` for `this.f = <constant or call result>`"
            )
        return self


class ConstantFact(BaseModel):
    """D00 §5's `constant`: a compile-time constant field and the value the
    class file records for it.

    **A declared fact kind that had no producer until W4.** Its stated consumer
    is topic and URL resolution — `static final String TOPIC = "orders"` is how
    a great many real listeners name their destination, and without this the
    address resolves to nothing readable and the endpoint carries an
    unresolved reference instead of a wire identity.

    The value comes from JVMS 4.7.2's `ConstantValue`, which the class file
    carries only for a `static final` field of a primitive or `String` type —
    exactly the shape that can be a constant expression. A field initialised in
    `<clinit>` has no such attribute and produces no fact here: that is a
    different question (what a static initialiser computes) and answering it
    from this attribute would be a guess.
    """

    model_config = {"frozen": True}
    kind: Literal["constant"] = "constant"
    document_id: str
    # The field's own symbol, exactly as the `symbol` fact spells it, so the
    # two join without a transformation in between.
    symbol: str
    # The literal the class file records. Kept as its JSON-native type — a
    # string, integer, float or boolean — rather than stringified, because a
    # consumer resolving an address needs the string and a consumer reading a
    # port needs the number, and re-parsing text would put a guess between
    # them and the class file.
    value: str | int | float | bool


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


class TypeHeaderFact(BaseModel):
    """D00 §5's `type_header`: the class-file HEADER of a type a module depends on
    but did not build — superclass, interfaces and class-level annotations, never a
    member — read from the resolved dependency archives and followed up `extends`
    until the chain leaves every archive for the platform's own types.

    A fact kind of its own rather than a `symbol` in the dependency tier, on the
    user's ruling (2026-10-21, option A): an endpoint engine must never see a
    library's `@RestController` and mint an endpoint this module does not serve.
    Only `superclasses`, `implementations` and the advice engine's annotation
    lookup read it. `symbol` is spelled under the LIBRARY's own coordinate, so
    `MethodArgumentNotValidException` has one spelling however many modules
    depend on the jar that holds it.
    """

    model_config = {"frozen": True}
    kind: Literal["type_header"] = "type_header"
    document_id: str
    symbol: str
    construct_kind: ConstructKind
    # None where the superclass is the platform's root type or the type is an
    # interface: the walk's end, not an unread value.
    superclass: str | None = None
    interfaces: list[str] = Field(default_factory=list)
    annotations: list[AnnotationUse] = Field(default_factory=list)
    # The jar the header was read from, as its coordinate and the version the
    # classpath resolved — the `origin` a real document carries, here per fact
    # because one document holds headers from every jar.
    origin: str
    version: str


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
    | MethodReturnFact
    | FieldWriteFact
    | ConfigEntryFact
    | ConstantFact
    | EmbeddedDescriptorFact
    | TypeHeaderFact
    | DeclaredShapeFact,
    Field(discriminator="kind"),
]
