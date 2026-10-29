"""The SCIP symbol grammar as a string format (D00 §1). No indexer involved."""

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass

NOT_APPLICABLE = "."

# D00 §5a's type marker: the character a TYPE descriptor ends at, and the one a
# member descriptor carries its owner's name up to. Named here because this
# module is the seam that reads the symbol grammar
# (`tests/architecture/test_symbol_grammar_confinement.py`), and a literal
# spelled at a second site is a second copy of the grammar.
_TYPE_MARKER = "#"


@dataclass(frozen=True)
class Symbol:
    scheme: str
    package_manager: str
    package: str
    version: str
    descriptor: str

    def __str__(self) -> str:
        return (
            f"{self.scheme} {self.package_manager} {self.package} {self.version} {self.descriptor}"
        )

    @property
    def short_id(self) -> str:
        """A prefixed, content-derived handle. Never bare hexadecimal: these
        get pasted into YAML and spreadsheets, which coerce types."""
        digest = hashlib.sha256(str(self).encode("utf-8")).hexdigest()[:8]
        return f"sym_{digest}"


def bare_descriptor(symbol: str) -> str:
    """The descriptor half of a symbol (D00 §5a): a symbol is module
    coordinates then a descriptor, space-separated, and only the descriptor is
    ever compared. A bare descriptor carries no coordinates, so it is
    returned unchanged."""
    return symbol.rsplit(" ", 1)[-1]


def with_descriptor(symbol: str, descriptor: str) -> str:
    """`symbol`'s module coordinates carrying `descriptor` instead of its own —
    `bare_descriptor`'s inverse, for a member of the SAME module.

    A symbol is coordinates then a descriptor (D00 §5a), and a caller that has
    one member's full symbol and another's bare descriptor can build the
    second's full symbol only by knowing that split. The lambda entry of the
    argument grammar is exactly that caller: it names its synthetic body bare,
    while every index is keyed on full symbols, and the body is declared in the
    same class as the method that captured it. A bare `symbol` carries no
    coordinates, so the descriptor is returned as it stands.
    """
    return symbol[: len(symbol) - len(bare_descriptor(symbol))] + descriptor


def owner_of(descriptor: str) -> str | None:
    """The owning type's descriptor, trailing `#` included, or `None` for a
    free-function descriptor — SCIP spells those with no `#` at all, and an
    ownerless symbol is an answer here, never an exception (D00 §5a)."""
    index = descriptor.find("#")
    return None if index == -1 else descriptor[: index + 1]


def is_type_descriptor(descriptor: str) -> bool:
    """Whether `descriptor` names a TYPE rather than one of its members (D00
    §5a): a type descriptor ends at the type marker, a member descriptor
    carries a name after it.

    Here rather than at the call site because the marker is the symbol
    grammar, and `tests/architecture/test_symbol_grammar_confinement.py` keeps
    every reading of that grammar in this module — a second copy of "ends with
    the marker" elsewhere is exactly the ad hoc parsing the seam replaced. Two
    callers need the question rather than the split `owner_of` performs: an
    annotation whose target must be a type before it names a container, and an
    annotation argument that is a class reference only when it names one.
    """
    return descriptor.endswith(_TYPE_MARKER)


def names_a_type(symbol: str) -> bool:
    """Whether `symbol` names a real type at all, as against a TYPE VARIABLE
    (D00 §5a).

    A type reference read from a declared signature may carry a type variable
    rather than a type: `T`, or `T[]` for an array of one. Every real type
    carries the type marker somewhere — a type descriptor ends at it, and an
    array's descriptor is its component's plus a suffix — while a variable is a
    bare identifier the declaration invented, and never does.

    Here rather than at the call site for `is_type_descriptor`'s reason: the
    marker is the symbol grammar, and a second reading of it elsewhere is the ad
    hoc parsing the seam exists to prevent. Distinct from `is_type_descriptor`,
    which asks whether a descriptor names a type rather than a MEMBER of one —
    `X#m().` fails that and passes this, correctly, because it does name
    something real. The caller that needs this one roots a payload shape, and a
    shape is identified by its symbol: rooting at a variable's name mints an id
    that every unrelated variable of the same name collides onto.
    """
    return _TYPE_MARKER in symbol


def outer_type_of(descriptor: str) -> str:
    """A nested type's own top-level enclosing type, bare, dollar-nesting
    stripped entirely — `A$B#` -> `A#` (D00 §5a: the JVM's own nested-class
    notation, embedded in the path segment ahead of the trailing type
    marker). `owner_of`'s sibling: that function splits a MEMBER descriptor
    on its `#` to find the type that declares it; this one splits a TYPE
    descriptor on its `$` to find the type that ENCLOSES it — 2O design
    §1b/§1c's own read, where a generated class's identity-building call
    sites live on the OUTER type, never on a nested `ImplBase`/`*Stub` a
    catalog's own marker names. A descriptor naming no `$` at all (already
    top-level) is returned unchanged."""
    body = descriptor.removesuffix("#")
    index = body.find("$")
    return descriptor if index == -1 else body[:index] + "#"


def member_name(descriptor: str) -> str:
    """The segment after the last `#`, trailing `.` stripped — a descriptor
    with no `#` returns itself minus any trailing `.` (D00 §5a)."""
    return descriptor.rpartition("#")[2].removesuffix(".")


def method_name(descriptor: str) -> str:
    """The method's plain name, with its trailing signature-hash argument
    list stripped (D00 §5a's `sig_...` disambiguator) — the identifier a
    compiler bridge shares with the real, differently-descriptored override
    it stands in for (2E checkpoint item (4)). `member_name` alone cannot
    tell the two apart: both `find(sig_95a78dff)` and `find(sig_4cb6f523)`
    already differ there, by design, since the disambiguator is what makes
    the descriptor form join-safe. This strips one layer further, to the
    name a same-class same-name conflict actually shares. A descriptor with
    no parameter list (a field, a type) returns `member_name` unchanged."""
    name = member_name(descriptor)
    head, paren, _ = name.partition("(")
    return head if paren else name


# D00 §5a's member-descriptor punctuation, spelled once. A member descriptor is
# `owner#name(<disambiguator>).` — the owner already carries its own trailing
# type marker, so composing one needs only these three characters and never a
# second `#` literal.
_ARGUMENTS_OPEN = "("
_ARGUMENTS_CLOSE = ")."
# The JVM DESCRIPTOR's own close paren, which is NOT `_ARGUMENTS_CLOSE`. Two grammars
# meet in this module: a SCIP symbol closes its argument list `).`, a descriptor closes
# it `)`. Substituting one for the other here raised `ValueError: substring not found`
# on every descriptor in the tree — 177 test errors from one character.
_DESCRIPTOR_ARGUMENTS_CLOSE = ")"
# The `sig_` prefix and the four bytes of digest behind it, exactly as
# `ClassScanner.disambiguatorOf` writes them. Four bytes is eight hex
# characters; both halves are pinned against a real scan
# (`tests/domain/test_symbols.py`, `tests/application/test_return_flow.py`)
# rather than trusted, because a disagreement here is a join that matches
# nothing while every fixture that spells the hash by hand still passes.
_DISAMBIGUATOR_PREFIX = "sig_"
_DISAMBIGUATOR_BYTES = 4


def method_descriptor(owner: str, name: str, descriptor: str) -> str:
    """The bare member descriptor of the method a `call_site` target names —
    the one spelling that joins a call to the callee's own symbol fact (D00
    §5a).

    A `call_site` carries its callee in the JVM's spelling (owner, name, and a
    JVM type descriptor); a method's own symbol fact carries it in SCIP's
    (`com/x/Y#m(sig_1a2b3c4d).`). The bridge between them is
    `ClassScanner.disambiguatorOf` — the first four bytes of the SHA-256 of the
    JVM descriptor — so **caller to callee is arithmetic, not a lookup**: no
    index of every scanned method is needed to ask what one call site calls,
    and a callee outside the workspace produces a descriptor that simply
    matches nothing rather than an exception.

    Here rather than at the call site for the reason `type_descriptor` is: this
    is the symbol grammar, and a second place that composes one is a second
    place for it to disagree with the extractor that wrote the first. The
    result is BARE — coordinates are the writing module's to add, and the
    caller compares descriptors (`bare_descriptor`) exactly as every other
    join in this codebase does.
    """
    return owner + name + _ARGUMENTS_OPEN + disambiguator_of(descriptor) + _ARGUMENTS_CLOSE


def disambiguator_of(descriptor: str) -> str:
    """The overload disambiguator D00 §5a's method descriptors carry, as
    `ClassScanner.disambiguatorOf` computes it: `sig_` and the first four
    bytes of the SHA-256 of the JVM descriptor, lower-case hex.

    It exists because a name alone does not identify a method — two overloads
    of `find` share one — and because the full JVM descriptor is unreadable in
    a rendered document. Truncation is deliberate and its collision risk is
    scoped: the pair must collide *within one type* to matter, and the
    extractor owns the same arithmetic on the writing side.
    """
    digest = hashlib.sha256(descriptor.encode("utf-8")).hexdigest()
    return _DISAMBIGUATOR_PREFIX + digest[: _DISAMBIGUATOR_BYTES * 2]


# D00 §5a: an array's symbol is its ELEMENT's descriptor with this suffix
# appended — `byte#[]`, never `byte[]#`. Written here because this is the seam
# that converts the catalogs' notation, and a catalog naming an array type
# (2G's bytes-shaped payload parameters) has to reach the very string the
# facts carry.
_ARRAY_SUFFIX = "[]"


def type_descriptor(dotted: str) -> str:
    """Converts a catalog's dotted type name to the SCIP symbol form the facts
    use.

    Two forms exist for the same type on purpose: D02's catalogs write a
    dotted name (`reactor.core.publisher.Mono`) because that is how the spec
    and every catalog author spells a fully qualified type; the scanner emits
    SCIP symbols (`reactor/core/publisher/Mono#`, D00 §5a) because that is the
    grammar the rest of the fact stream is keyed on. Neither side should
    change to suit the other — the catalog stays readable in its source
    notation, the facts stay one grammar — so the conversion happens once,
    here, at the point of comparison.

    A trailing `[]` (repeated for a nested array) is carried past the
    descriptor marker rather than into it: the facts spell `byte[]` as
    `byte#[]`, so a catalog writing `byte[]` and a scanned parameter of that
    type must compare equal. Inert for every name without one, which is
    every catalog value written before 2G.

    **Refuses anything that is not a string, rather than converting it.** Since
    §3.1 a catalog site may name a LIST of types, and only a few sites can honour
    one so far. At every other site the value reached here through `str(...)`,
    and `str(["a.B"])` is `"['a.B']"` — a perfectly well-formed conversion of
    nonsense, producing `"['a/B']#"`, which matches no fact, derives no row and
    says nothing. Even a ONE-element list did it, which is the slip an author
    makes first.

    Refusing here removes the cause instead of testing for it at twenty sites:
    a list written where it cannot yet be honoured stops the run with a message,
    which is the §8.1 rule that deriving nothing beats deriving the wrong thing.
    """
    if not isinstance(dotted, str):
        raise TypeError(
            f"a catalog type name must be a string, not {type(dotted).__name__} "
            f"({dotted!r}). A list of alternates is only honoured at the sites "
            f"converted for §3.1; elsewhere it must stay a single name."
        )
    depth = 0
    while dotted.endswith(_ARRAY_SUFFIX):
        dotted = dotted[: -len(_ARRAY_SUFFIX)]
        depth += 1
    return dotted.replace(".", "/") + "#" + _ARRAY_SUFFIX * depth


# JVMS 4.3.2's base types, by the name a catalog writes them in.
_BASE_TYPES = {
    "void": "V",
    "boolean": "Z",
    "byte": "B",
    "char": "C",
    "short": "S",
    "int": "I",
    "long": "J",
    "float": "F",
    "double": "D",
}


def method_type_descriptor(parameters: Sequence[str], returns: str) -> str:
    """A catalog's dotted parameter and return types as the JVM method descriptor a call
    site carries (JVMS 4.3.3): `([org.quartz.JobExecutionContext], void)` is
    `(Lorg/quartz/JobExecutionContext;)V`. The JVM resolves a method by its name AND this
    whole descriptor, return type included, so a reader asking `dispatch.py` which body
    runs needs it; a nested type keeps its binary `$` name, and a trailing `[]` is an array
    of the element type."""

    def field(dotted: str) -> str:
        if dotted.endswith(_ARRAY_SUFFIX):
            return "[" + field(dotted[: -len(_ARRAY_SUFFIX)])
        return _BASE_TYPES.get(dotted) or f"L{dotted.replace('.', '/')};"

    return "(" + "".join(field(parameter) for parameter in parameters) + ")" + field(returns)


def parameter_types(descriptor: str) -> str:
    """A JVM method descriptor's parameter list, `(` and `)` included, with the return
    type dropped — the part that is method IDENTITY.

    JLS 8.4.2 identifies a method by its name and its parameter types; the return type
    is in the JVM descriptor and is not part of the signature. A catalog comparing whole
    descriptors was therefore version-dependent by accident: a library that changes a
    return type changes nothing in its callers' source, and the descriptor entirely.
    Ten `spring-kafka-template` rows declare `send`/`sendDefault` returning
    `CompletableFuture`, which is Spring Kafka 3.x — the same call in a 2.x module
    returns `ListenableFuture` and matched nothing at all (F2 §4.1).

    Lives here because it is symbol-grammar parsing, which happens in this module and
    nowhere else (`test_symbol_grammar_confinement`).
    """
    return descriptor[: descriptor.index(_DESCRIPTOR_ARGUMENTS_CLOSE) + 1]


_PRIMITIVES = {
    "B": "byte",
    "C": "char",
    "D": "double",
    "F": "float",
    "I": "int",
    "J": "long",
    "S": "short",
    "Z": "boolean",
}


def descriptor_parameter_types(descriptor: str) -> tuple[str, ...]:
    """A JVM method descriptor's parameter types, one dotted name each — the form a
    catalog spells a type in (`com.example.web.Predicate`, `int`, `byte[]`), so a
    rule's `arg_types` compares to a call's own erased descriptor without either side
    learning the other's spelling.

    Reads the parameter list `parameter_types` isolates, one type at a time: a
    primitive letter, `L…;` for a class, and any number of `[` before either for an
    array. The return type is not read — it is not part of method identity (JLS 8.4.2).
    """
    inside = parameter_types(descriptor)[1:-1]
    types: list[str] = []
    position = 0
    while position < len(inside):
        dimensions = 0
        while inside[position] == "[":
            dimensions += 1
            position += 1
        if inside[position] == "L":
            end = inside.index(";", position)
            name = inside[position + 1 : end].replace("/", ".")
            position = end + 1
        else:
            name = _PRIMITIVES[inside[position]]
            position += 1
        types.append(name + "[]" * dimensions)
    return tuple(types)


def descriptor_slots(descriptor: str) -> tuple[tuple[str, ...], str]:
    """A JVM method descriptor split into its parameter slots and its return, each in
    the JVM's OWN spelling (`Ljava/lang/String;`, `I`, `[B`) — the form a caller needs
    to compose another descriptor from some of the slots, which is what re-targeting a
    compiler-emitted default-argument bridge to the function it stands for does
    (`resolve/effective_calls.py`, spec 2026-09-19 §3a): the sibling's descriptor is the
    bridge's minus its receiver, mask and marker slots, and only the slots as written can
    be joined back into one.

    Reads the parameter list exactly as `descriptor_parameter_types` does and keeps the
    text rather than translating it; the return is kept too, because the sibling shares
    it. Lives here because it is symbol-grammar parsing, which happens in this module and
    nowhere else (`test_symbol_grammar_confinement`).
    """
    inside = parameter_types(descriptor)[1:-1]
    slots: list[str] = []
    position = 0
    while position < len(inside):
        start = position
        while inside[position] == "[":
            position += 1
        if inside[position] == "L":
            position = inside.index(";", position) + 1
        else:
            position += 1
        slots.append(inside[start:position])
    return tuple(slots), descriptor[descriptor.index(_DESCRIPTOR_ARGUMENTS_CLOSE) + 1 :]


def returned_type(descriptor: str) -> str | None:
    """The SCIP type descriptor a JVM method descriptor RETURNS, or `None` when it
    returns a primitive, `void` or an array.

    Lives here rather than beside its one caller because it is symbol-grammar parsing,
    and this module is the only place that happens (`test_symbol_grammar_confinement`).
    `None` for the non-object cases is an answer, not a gap: a method returning `void`
    or an `int` cannot be handing a constructed object back to its caller, which is the
    only question anyone asks this. Arrays answer `None` for the same reason — nothing
    in the tree needs an array's element type here, and inventing one would be a
    grammar rule with no consumer.
    """
    returned = descriptor[descriptor.index(_DESCRIPTOR_ARGUMENTS_CLOSE) + 1 :]
    if not returned.startswith("L"):
        return None
    return returned[1:].removesuffix(";") + _TYPE_MARKER


def package_path(dotted: str) -> str:
    """Converts a catalog's dotted PACKAGE name to the path form the facts
    use — `type_descriptor`'s prefix-only sibling.

    A package is not a type: it has no descriptor suffix, so a caller
    matching one (2G design §5's `json_default_markers`, which ask whether
    anything from a package family appears at all) cannot use
    `type_descriptor` without also asserting that the prefix names a type.
    Here rather than at the call site for the reason `type_descriptor` is:
    the two notations meet in one seam, never in every pass that compares
    them."""
    return dotted.replace(".", "/")


def dotted_package(symbol: str) -> str | None:
    """The DOTTED package the type `symbol` names a member of — `package_path`'s
    inverse, read off a symbol rather than off a catalog.

    `… com/acme/pp/controller/admin/AdminOrderController#get(sig_1).` answers
    `com.acme.pp.controller.admin`, and a type in the default package answers
    `""`. `None` means there is no owning type to take a package from, which
    is a free-function descriptor's answer (`owner_of` above).

    Here rather than at the call site because it reads two notations at once —
    the module-coordinates/descriptor split and the type marker — and a pass
    that compared a package against an author's pattern would otherwise spell
    both (`resolve/path_prefix.py`, spec 2026-10-18 §4).
    """
    owner = owner_of(bare_descriptor(symbol))
    if owner is None:
        return None
    path = without_type_marker(owner)
    package, separator, _ = path.rpartition("/")
    return package.replace("/", ".") if separator else ""


def simple_name(symbol: str) -> str:
    """The display name for a SCIP symbol (D00 §5a): the last path segment,
    with the trailing `#` a type descriptor always carries stripped."""
    return symbol.rsplit("/", 1)[-1].rstrip("#")


def short_class_name(symbol: str) -> str:
    """A class's short name as the JVM's class utilities spell it (CP-44 row 6,
    `ClassUtils.getShortName`): the simple name, cut at a `$$` generated-class suffix,
    with a nested class's `$` read as `.` — `Outer$Inner#` is `Outer.Inner`."""
    return simple_name(bare_descriptor(symbol)).split("$$", 1)[0].replace("$", ".")


def without_type_marker(symbol: str) -> str:
    """`symbol` with its trailing SCIP type marker (`#`) removed, if it
    carries one — everything else about it, package coordinates included,
    left exactly as written. `simple_name`'s one-character sibling: that
    function ALSO drops everything before the last `/`, which is wrong for a
    caller that needs the WHOLE id kept (still unique) with only the
    trailing marker's redundant punctuation gone — a shape id disambiguated
    by falling back to itself (`egress/render/document.py`,
    `_disambiguated_shape_names`) is exactly this case."""
    return symbol.rstrip("#")
