"""The effective-annotations pre-pass (spec §2, §3): widens the set of
mapping annotations `annotation_driven` matches on from the catalog's own
declared fqns to those plus every MODULE-LOCAL annotation type transitively
meta-annotated with one of them.

Framework composition (`@GetMapping` = `@RequestMapping(method=GET)`) is
hand-copied catalog data, unaffected — those class files live in unscanned
jars, and stay out of reach until dependency scanning exists (D02 §7). What
this module adds is the OTHER half: a project's own composed annotation
(`@ApiGet` built from `@RequestMapping`) is scanned bytecode, so the
composition is already sitting in the `annotations` facts as an ordinary
annotation-on-a-type-symbol fact — this module follows it instead of asking
every catalog author to hand-copy it too.

**Merge semantics — the honest subset of `@AliasFor`, stated as such**: a
use site's own attributes win over the composition's declared values, which
win over whatever an earlier hop in the chain declared, base-outward. This
implements the common case (same-name attributes, one level or several) not
`@AliasFor`'s full generality — explicit cross-name aliasing and
`@AliasFor(annotation=...)` re-targeting are out of scope (COVERAGE, Task
10).

**Home, per spec §3**: deliberately NOT `annotation_driven.py`, which the 2D
architecture review rated deteriorating for absorbing exactly this kind of
growth. `annotation_driven.run` queries the facts, calls the pure function
here, and binds the result as one derivation parameter — this module never
touches a workspace.

**Scope note**: `annotation_driven._derive_replies`'s own `annotations_of`
lookup (a listener's `@SendTo`-like reply annotation) does not run through
this widened set — a composed REPLY annotation is out of 2E's fixture scope.
Left alone; a future phase widens that lookup the same way this one widens
`mapping_annotations`.
"""

import json
from dataclasses import dataclass
from typing import Any

from sextant.domain.symbols import bare_descriptor, member_name, method_name


def composed_mapping_rows(
    annotation_rows: list[dict[str, Any]],
    scanned_targets: set[str],
    mapping_fqns: set[str],
) -> list[dict[str, Any]]:
    """Synthesizes one row per use site of a module-local composed mapping
    annotation, `{target, annotation, args}` shaped exactly like a row the
    `annotations` view itself would carry — `annotation` always one of
    `mapping_fqns`, so the caller's SQL never has to know a composition
    happened.

    `annotation_rows` is every annotation fact in the workspace (each
    `{target, annotation, args}`, `annotation` in the view's own
    `type_descriptor` form, `args` already parsed into a dict).
    `scanned_targets` is the set of symbols (module-prefixed, exactly as the
    `symbols` facts carry them) this module's own bytecode declared — the
    module-local half of checkpoint item (2): an annotation TYPE's symbol
    fact exists with `construct_kind: "interface"`, so a composed
    annotation's own type is in this set exactly when its `.class` was
    scanned, never when it lives in an unscanned jar.

    Two passes:

    1. A fixpoint over annotation TYPES: seed the "active" identifier set
       with `mapping_fqns`; each round, every row whose `annotation` is
       active and whose `target` is a scanned type records that target's own
       bare descriptor as a newly composed identifier, folding its declared
       args on top of whatever the annotation it composed already folded
       (base-outward, so a nearer declaration's attribute wins — same-name
       union, the honest `@AliasFor` subset). A descriptor already recorded
       is never revisited, which is what stops a meta-annotation cycle from
       looping: the second time the fixpoint reaches an already-composed
       type through a different path, there is nothing left to add.
    2. One pass over every row whose `annotation` names a composed
       identifier — an ordinary USE of the composed annotation — folding the
       use site's own args on top (use-site wins) and emitting the row.

    Pass 2 does not distinguish a "declaration" row (round 1's own input,
    where a composing type names what it composes) from a "use" row: a
    composing type's own declaration row is itself a genuine use of the
    identifier it just became active, so it can ALSO synthesize a row
    targeting the composing type itself, not just downstream method-level
    uses (see the two-hop and cycle tests). Such a type-targeted row is
    inert everywhere the caller's SQL joins a mapping annotation to a
    handler method (`derive_endpoints.sql`'s `mappings`/`declared` chain,
    gated on `construct_kind IN ('method', 'function')`) — but when
    `prefix_annotation` is itself one of `mapping_fqns` (every shipped
    catalog), the same row's `annotation` also matches `prefix_annotation`,
    so it genuinely reaches `derive_endpoints.sql`'s `prefixes` CTE too. It
    stays harmless there only because of an invariant the SQL relies on but
    never states: an annotation TYPE symbol never encloses a handler method,
    so `prefixes.type_symbol` (this row's own type-targeted `target`) can
    never equal `s.enclosing` for a real handler — the prefix never joins,
    never leaks. `tests/application/test_effective_annotations.py` pins this
    at the SQL level, not just here.
    """
    composed: dict[str, tuple[str, dict[str, Any]]] = {}
    active = set(mapping_fqns)
    while True:
        newly_composed: dict[str, tuple[str, dict[str, Any]]] = {}
        for row in annotation_rows:
            annotation = str(row["annotation"])
            target = str(row["target"])
            if annotation not in active or target not in scanned_targets:
                continue
            descriptor = bare_descriptor(target)
            if descriptor in composed or descriptor in newly_composed:
                continue
            args = dict(row["args"] or {})
            if annotation in mapping_fqns:
                base_fqn, folded = annotation, args
            else:
                base_fqn, base_args = composed[annotation]
                folded = {**base_args, **args}
            newly_composed[descriptor] = (base_fqn, folded)
        if not newly_composed:
            break
        composed.update(newly_composed)
        active.update(newly_composed)

    synthetic = [
        {
            "target": str(row["target"]),
            "annotation": composed[str(row["annotation"])][0],
            "args": {**composed[str(row["annotation"])][1], **dict(row["args"] or {})},
        }
        for row in annotation_rows
        if str(row["annotation"]) in composed
    ]
    # NFR-1: deterministic order, sorted by (target, annotation).
    synthetic.sort(key=lambda row: (row["target"], row["annotation"]))
    return synthetic


def folded_rows(
    annotation_rows: list[dict[str, Any]],
    containers: dict[str, str],
) -> list[dict[str, Any]]:
    """Synthesizes one row per use held INSIDE a container annotation — the same
    `{target, annotation, args}` shape the other two passes synthesize, and
    `annotation` always the MEMBER fqn the catalog declared, so the caller's SQL
    never has to know a folding happened any more than it has to know a
    composition did (`OI-36`).

    `containers` maps a container fqn to the member fqn it folds, both in the
    `annotations` view's own symbol form. Empty for every catalog that declares
    none, in which case this returns an empty list without reading a row.

    **Two or more uses of one repeatable annotation on one declaration are not
    N annotations in the class file.** javac writes the CONTAINER and nothing
    else (JLS 9.7.5), so a method carrying two listener annotations carries no
    listener annotation at all and the mapping join matches nothing — both
    destinations vanish, silently, beside a single-use neighbour that derives
    normally. That is the under-report CP-16 measured at six versions across
    three frameworks, and this is the read that closes it.

    **A container the AUTHOR wrote is the same bytes and the same read.** CP-17
    rows 2a/2b, 3a/3b and 6a/6b measured `@PulsarListeners`: the container shape
    without the language mechanism, on an annotation that is not `@Repeatable`,
    whose post-processor registers the union of a direct use and every member of
    the container. This pass emits the members and the real annotation row
    survives untouched beside them, so the union is what the caller sees —
    which is the framework's own answer rather than a widening. Nothing here
    asks whose container it is, because a class file does not record that.

    **`value` is the LANGUAGE's word, not a framework's**, which is why it is
    spelled here and is not catalog data: JLS 9.6.3 requires a containing
    annotation type to declare exactly `value()`, returning an array of the
    repeatable type. A catalog key for it would let a file state something the
    language forbids. `scheduled_work._folded` spells it in the same place for
    the same reason.

    Every entry is checked against the declared member fqn rather than taken on
    position, `scheduled_work._folded`'s reason unchanged: a container is an
    ordinary annotation whose `value` happens to be an array, and reading
    whatever it holds would let some other array-valued annotation contribute
    declarations. An entry the extractor recorded as unread carries no `args`
    key and contributes nothing, rather than reading as an annotation genuinely
    written with no arguments — which is why the `args` type is checked and not
    defaulted.
    """
    if not containers:
        return []
    synthetic: list[dict[str, Any]] = []
    for row in annotation_rows:
        member = containers.get(str(row["annotation"]))
        if member is None:
            continue
        value = (row["args"] or {}).get("value")
        if not isinstance(value, list):
            continue
        synthetic.extend(
            {"target": str(row["target"]), "annotation": member, "args": dict(entry["args"])}
            for entry in value
            if isinstance(entry, dict)
            and entry.get("annotation") == member
            and isinstance(entry.get("args"), dict)
        )
    # NFR-1: deterministic order, sorted by (target, annotation) — the same
    # normalisation `composed_mapping_rows` ends with. The folded uses of ONE
    # container keep the array order javac wrote, which is the declaration
    # order the source had, because `sort` is stable and the key names neither.
    synthetic.sort(key=lambda row: (row["target"], row["annotation"]))
    return synthetic


@dataclass(frozen=True)
class TypeHierarchy:
    """What the inheritance walk reads of the module's own declarations, folded from
    the `implementations`, `superclasses` and `method_declarations` rows: which type
    declares which method under which name-and-descriptor key, each method's own
    signature and modifiers, each type's directly implemented interfaces in
    declaration order, each class's superclass, and every type any of those name.

    Catalog-independent, so `annotation_driven` builds it once per load
    (`Workspace.once`) and every catalog's walk reads the same one — on `mall-admin`
    the fold over 22,059 method rows ran once per catalog, nineteen times. Read by
    every walk, written by none."""

    methods_by_type: dict[str, dict[str, str]]
    signature_by_symbol: dict[str, dict[str, Any] | None]
    modifiers_by_symbol: dict[str, dict[str, Any] | None]
    interfaces_of: dict[str, list[str]]
    supertype_of: dict[str, str]
    classes: frozenset[str]


def type_hierarchy(
    implementation_rows: list[dict[str, Any]],
    superclass_rows: list[dict[str, Any]],
    method_rows: list[dict[str, Any]],
) -> TypeHierarchy:
    """`TypeHierarchy` over the plain-Python rows `inherited_rows` documents."""
    methods_by_type: dict[str, dict[str, str]] = {}
    signature_by_symbol: dict[str, dict[str, Any] | None] = {}
    # D00 §5a's method `modifiers`, which carry `synthetic` — `ACC_BRIDGE`
    # folded in, since javac sets the two together. Absent for a fact from a
    # scanner that reports no modifiers, which is what `_is_synthetic`'s
    # fallback exists for; NOT defaulted to `{}` here, because "no modifiers
    # reported" and "reported, and not synthetic" are different answers.
    modifiers_by_symbol: dict[str, dict[str, Any] | None] = {}
    for row in method_rows:
        symbol = str(row["symbol"])
        signature_by_symbol[symbol] = row.get("signature")
        modifiers_by_symbol[symbol] = row.get("modifiers")
        enclosing = row.get("enclosing")
        if enclosing is None:
            continue
        key = member_name(bare_descriptor(symbol))
        methods_by_type.setdefault(str(enclosing), {})[key] = symbol

    interfaces_of: dict[str, list[str]] = {
        str(row["symbol"]): [str(entry) for entry in row["interfaces"]]
        for row in implementation_rows
    }

    supertype_of = _superclass_of(superclass_rows)

    # Every type this module has ANY evidence for as a subtype — declaring
    # its own methods, implementing interfaces, or extending a superclass.
    # A class needing only a prefix (no method of its own repeats or misses
    # a mapping — a class implementing an interface entirely through
    # inherited defaults, say) would otherwise never surface: prefix
    # resolution cannot be nested inside "types that own at least one
    # method" the way it read before this comment (Task 7 review,
    # mutation-caught).
    classes = frozenset(methods_by_type) | frozenset(interfaces_of) | frozenset(supertype_of)
    return TypeHierarchy(
        methods_by_type=methods_by_type,
        signature_by_symbol=signature_by_symbol,
        modifiers_by_symbol=modifiers_by_symbol,
        interfaces_of=interfaces_of,
        supertype_of=supertype_of,
        classes=classes,
    )


def inherited_rows(
    annotation_rows: list[dict[str, Any]],
    implementation_rows: list[dict[str, Any]],
    superclass_rows: list[dict[str, Any]],
    method_rows: list[dict[str, Any]],
    mapping_fqns: set[str],
    prefix_fqns: list[str] | None,
) -> list[dict[str, Any]]:
    """Synthesizes one row per method that carries no mapping annotation of
    its own but implements or overrides one that does (spec §3): the same
    `{target, annotation, args}` shape `composed_mapping_rows` synthesizes,
    `target` always the IMPLEMENTING method (or, for a type-level prefix,
    the implementing CLASS), so the caller's SQL never has to know an
    inheritance happened any more than it has to know a composition did.

    `annotation_rows` is the COMPOSED UNIVERSE — every real `annotations`
    row plus `composed_mapping_rows`'s own output — because the fixture's
    own worst case (`OrdersApi#composed`'s `@ApiGet`) must resolve through
    both passes at once: §2 composes it to a real `@RequestMapping` on the
    interface method first, and only then does this pass have anything to
    inherit. `implementation_rows`/`superclass_rows`/`method_rows` are each
    the plain-Python form of the same-named workspace query (`implementations`,
    `superclasses`, a new `method_declarations`) — JSON columns already
    decoded, the same convention `composed_mapping_rows` takes for `args`.

    **The class-inheritance edge is `superclasses`, not `supertypes`
    (`A-C4`).** `supertypes` carries D00 §5a's parameterized-type reference,
    emitted ONLY where the superclass carries type ARGUMENTS — so reading it
    as the superclass edge gave `class Child extends Base` no edge at all,
    and `derive_endpoints.sql`'s `LEFT JOIN prefixes` then composed the
    absent prefix as the empty string and published the child's methods at an
    address the framework does not serve. JLS 8.1.4/8.2 is that a class has
    exactly one direct superclass and inherits its members, generic or not,
    and capability 9.13's erased `superclass` field is that sentence in the
    fact stream: written for every non-`Object` superclass, off the class
    file's own `super_class` entry.

    Every symbol here — `implementations.symbol`, its `interfaces` entries,
    `method_rows.enclosing`, `superclass_rows`' own two columns, and every
    `annotations` `target` — shares one coordinate space: module-prefixed
    exactly as the fact wrote it (D00 §5a), which is why none of them is
    stripped to a bare descriptor before a lookup. The `supertypes` edge was
    the one exception and needed a bare-to-prefixed lookback, which could
    only recover an ancestor this module had seen SOMEWHERE ELSE — so an
    abstract base declaring nothing but a type-level prefix was unreachable
    (`A-M11`). Both go away with the edge.

    Resolution order (spec §3, exact), applied per candidate method
    (`_resolve_method`) and, separately, per implementing class's own
    type-level prefix (`_resolve_prefix`): a method's or a class's own
    mapping annotation wins outright, checked before either walk starts;
    failing that, the first match among the type's own directly implemented
    interfaces, in declaration order; failing that, the superclass;
    reapplied transitively up the scanned chain (each ancestor gets the same
    own-then-interfaces-then-superclass treatment) until either a match or
    scanned facts run out. A `visited` set per top-level candidate stops a
    diamond or cyclic hierarchy from looping, the same guard
    `composed_mapping_rows` keeps for a meta-annotation cycle.

    Bridge exclusion (checkpoint item (4), the controller's ruling that this
    is PRIMARY, not a fallback): the compiler's covariant-return bridge is
    an ordinary method symbol carrying the interface method's EXACT
    descriptor, with no distinguishing key at all — so it, not the real
    override, is what the name+descriptor join actually finds — because the
    ancestor lookup is by name AND descriptor, and a covariant or generic
    override's descriptor is by definition not its ancestor's.

    So the bridge is the only thing that CAN resolve, and it is the wrong
    target: it names a method nobody wrote. It is treated as evidence
    instead, and the mapping is carried across to the method it forwards to
    (`_synthesis_target`). Which method that is comes from the fact, not
    from a guess: D00 §5a's `modifiers.synthetic` folds in `ACC_BRIDGE`.

    *This was a structural guess until OI-47 — same class, same name, same
    parameters, different return — and it was wrong in both directions. A
    COVARIANT override matched it, so the real method was excluded along
    with its bridge and the mapping was lost. A GENERIC-PARAMETER override
    did not match it at all (the parameters differ, the return does not),
    so the row was published naming the synthetic bridge as the handler.*

    A class inheriting the SAME-named method from both a mapped interface
    AND a mapped superclass grows two bridges that redirect to one method,
    and still derives nothing — now because two ancestors give it two
    different answers and the framework's own annotation search order is
    not read here, so §8 says produce none. That is finding I1, restated as
    a rule for an ambiguity rather than a consequence of discarding every
    bridge.

    The three row lists are folded into a `TypeHierarchy` first; a caller running
    many catalogs over one module folds them once and calls `inherited_rows_over`.
    """
    return inherited_rows_over(
        type_hierarchy(implementation_rows, superclass_rows, method_rows),
        annotation_rows,
        mapping_fqns,
        prefix_fqns,
    )


def inherited_rows_over(
    hierarchy: TypeHierarchy,
    annotation_rows: list[dict[str, Any]],
    mapping_fqns: set[str],
    prefix_fqns: list[str] | None,
    sibling_fqns: frozenset[str] = frozenset(),
) -> list[dict[str, Any]]:
    """`inherited_rows` over an already-folded `TypeHierarchy` — the same rows, the
    same order; the hierarchy is read and never written into.

    `sibling_fqns` is the catalog's declared SIBLING annotations — the ones its
    `path_from_siblings`/`produces_from_siblings`/`consumes_from_siblings` lists
    and its `protocol_hint.hint_annotations` name — and it is empty for every
    catalog that declares none, which leaves the walk exactly as it was. Where
    it is non-empty the walk follows JAX-RS §3.6 rather than Spring's per-
    annotation merge (spec 2026-09-18 §3b word 3, CP-18 row 8): a method with
    NO annotation of the catalog's — mapping or sibling — inherits the ancestor
    method's mapping AND every sibling that ancestor method carries, and a
    method with ANY of its own inherits nothing at all. JAX-RS puts the path
    and the media BESIDE the verb (`@GET @Path("/{id}") @Produces(...)`), so a
    `@GET` inherited alone would be a wrong address; and its own text is *"if a
    subclass or implementation method has any JAX-RS annotations then all of
    the annotations on the superclass or interface method are ignored"*, which
    is why an implementor method carrying only its own `@Produces` gets no
    mapping row here — to the framework it is not a resource method. The
    synthesized siblings are ordinary annotation rows downstream, so the SQL
    that reads siblings never learns an inheritance happened."""
    methods_by_type = hierarchy.methods_by_type
    signature_by_symbol = hierarchy.signature_by_symbol
    modifiers_by_symbol = hierarchy.modifiers_by_symbol
    interfaces_of = hierarchy.interfaces_of
    supertype_of = hierarchy.supertype_of

    annotations_by_target: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for row in annotation_rows:
        annotations_by_target.setdefault(str(row["target"]), []).append(
            (str(row["annotation"]), dict(row["args"] or {}))
        )
    # Deterministic per-target order (NFR-1): a target carrying two mapping
    # candidates (not a fixture case, but not this module's rule to assume
    # away) reads the same way twice.
    for entries in annotations_by_target.values():
        entries.sort(key=lambda entry: entry[0])

    # §3.6: any own annotation of the catalog's — mapping or sibling — blocks
    # inheritance for that method; with no siblings declared this is
    # `mapping_fqns` itself, today's check.
    own_fqns = mapping_fqns | set(sibling_fqns)

    # Final NFR-1 ordering comes from the explicit sort below; iteration
    # order here only has to be exhaustive, not deterministic.
    rows: list[dict[str, Any]] = []
    for type_symbol in hierarchy.classes:
        methods = methods_by_type.get(type_symbol, {})
        # Keyed by the method the mapping BELONGS to, which is not always the
        # candidate that resolved it — see `_synthesis_target`. Insertion order
        # follows `methods`, which follows the query's `ORDER BY symbol` (NFR-1).
        #
        # Each resolution is the ancestor method's WHOLE inherited set: the
        # mapping, plus that SOURCE method's declared siblings (empty when the
        # catalog declares none), because §3.6 inherits one method's set whole
        # and never one annotation of it — so agreement below is measured on
        # the set, not on the mapping alone.
        resolved: dict[str, list[tuple[str, dict[str, Any], list[tuple[str, dict[str, Any]]]]]] = {}
        for key, candidate in methods.items():
            if _own_mapping(candidate, own_fqns, annotations_by_target) is not None:
                continue
            found = _resolve_method(
                key,
                interfaces_of.get(type_symbol, []),
                supertype_of.get(type_symbol),
                methods_by_type,
                interfaces_of,
                supertype_of,
                annotations_by_target,
                mapping_fqns,
                {type_symbol},
            )
            if found is None:
                continue
            source, annotation, args = found
            target = _synthesis_target(
                candidate, methods.values(), signature_by_symbol, modifiers_by_symbol
            )
            if target is None:
                continue
            # A redirected mapping must not land on a method that declares its
            # own: the candidate loop skips a method with an own mapping, but
            # the BRIDGE that forwards to it has none of its own to skip on.
            if target != candidate and (
                _own_mapping(target, own_fqns, annotations_by_target) is not None
            ):
                continue
            # `annotations_by_target` is sorted per target above, so the
            # sibling list reads the same way twice (NFR-1).
            siblings = [
                (sib_annotation, sib_args)
                for sib_annotation, sib_args in annotations_by_target.get(source, [])
                if sib_annotation in sibling_fqns
            ]
            resolved.setdefault(target, []).append((annotation, args, siblings))
        for target, resolutions in resolved.items():
            # Two ancestors mapping one method — the shape a class carrying two
            # bridges has (I1). Which one the framework serves depends on its own
            # annotation search order, which is not read here, so a target with
            # two DIFFERENT answers gets none: §8's ambiguous evidence, and the
            # same nothing this shape produced before, now stated rather than a
            # side effect of excluding every bridge.
            #
            # The answer compared is the whole set. Two ancestors agreeing on the
            # verb but not on a sibling (`@GET @Path("/a")` against `@GET
            # @Path("/b")`) are the same ambiguity one annotation over, and
            # emitting the verb with both paths beside it would hand downstream
            # two same-annotation rows to pick between on a tied ordinal — an
            # address nobody can predict. With no siblings declared every set is
            # empty and this is the mapping-only comparison it always was.
            distinct = {
                (
                    annotation,
                    json.dumps(args, sort_keys=True),
                    frozenset(
                        (sib_annotation, json.dumps(sib_args, sort_keys=True))
                        for sib_annotation, sib_args in siblings
                    ),
                )
                for annotation, args, siblings in resolutions
            }
            if len(distinct) != 1:
                continue
            annotation, args, siblings = resolutions[0]
            rows.append({"target": target, "annotation": annotation, "args": args})
            # The siblings ride with the mapping and only with it: a target
            # that got no mapping row above gets no sibling row either, so an
            # ambiguous set never leaves a lone `@Path` behind.
            for sib_annotation, sib_args in siblings:
                rows.append({"target": target, "annotation": sib_annotation, "args": sib_args})
        # Computed once per class, independent of the per-method loop above:
        # a class's inherited prefix applies to EVERY one of its methods
        # that ends up mapped, whether that mapping is itself inherited or
        # the class's own real `@GetMapping` — Spring resolves a
        # `@RequestMapping` prefix at the type level, once, never
        # separately per method (Task 7 review, M2).
        if (
            prefix_fqns is not None
            and _own_mapping(type_symbol, set(prefix_fqns), annotations_by_target) is None
        ):
            found_prefix = _resolve_prefix(
                interfaces_of.get(type_symbol, []),
                supertype_of.get(type_symbol),
                interfaces_of,
                supertype_of,
                annotations_by_target,
                prefix_fqns,
                {type_symbol},
            )
            if found_prefix is not None:
                annotation, args = found_prefix
                rows.append({"target": type_symbol, "annotation": annotation, "args": args})

    # NFR-1: deterministic order, sorted by (target, annotation) — the same
    # ordering `composed_mapping_rows` sorts its own output by, so the
    # caller's concatenation of the two lists stays predictable regardless
    # of which pass produced which row.
    rows.sort(key=lambda row: (row["target"], row["annotation"]))
    return rows


def _own_mapping(
    target: str,
    fqns: set[str],
    annotations_by_target: dict[str, list[tuple[str, dict[str, Any]]]],
) -> tuple[str, dict[str, Any]] | None:
    """The first (deterministically, by annotation fqn) mapping-shaped
    annotation a target carries directly — never one this pass itself
    walked up to find. `fqns` is `own_fqns` — `mapping_fqns` plus the catalog's
    declared siblings, which is `mapping_fqns` itself where none are declared —
    for a method-level check (spec 2026-09-18 §3b word 3), `mapping_fqns` alone
    where `_resolve_method` reads an ANCESTOR method's own mapping, and
    `set(prefix_fqns)` for a class's own type-level one; the same helper serves
    every "own wins outright" gate spec §3 states."""
    for annotation, args in annotations_by_target.get(target, []):
        if annotation in fqns:
            return annotation, args
    return None


def _resolve_method(
    key: str,
    interfaces: list[str],
    supertype: str | None,
    methods_by_type: dict[str, dict[str, str]],
    interfaces_of: dict[str, list[str]],
    supertype_of: dict[str, str],
    annotations_by_target: dict[str, list[tuple[str, dict[str, Any]]]],
    mapping_fqns: set[str],
    visited: set[str],
) -> tuple[str, str, dict[str, Any]] | None:
    """Walks directly implemented interfaces (declaration order), then the
    superclass, checking each ancestor's OWN same-key method for a mapping
    annotation before recursing further up that same ancestor's own
    hierarchy — spec §3's resolution order, applied transitively.

    Answers `(source, annotation, args)`: the ancestor method the mapping was
    found ON comes back with it, because the caller reads that method's
    declared siblings (spec 2026-09-18 §3b word 3) and no other level's."""
    for interface in interfaces:
        if interface in visited:
            continue
        visited.add(interface)
        method = methods_by_type.get(interface, {}).get(key)
        if method is not None:
            own = _own_mapping(method, mapping_fqns, annotations_by_target)
            if own is not None:
                return method, own[0], own[1]
        found = _resolve_method(
            key,
            interfaces_of.get(interface, []),
            supertype_of.get(interface),
            methods_by_type,
            interfaces_of,
            supertype_of,
            annotations_by_target,
            mapping_fqns,
            visited,
        )
        if found is not None:
            return found
    if supertype is None or supertype in visited:
        return None
    visited.add(supertype)
    method = methods_by_type.get(supertype, {}).get(key)
    if method is not None:
        own = _own_mapping(method, mapping_fqns, annotations_by_target)
        if own is not None:
            return method, own[0], own[1]
    return _resolve_method(
        key,
        interfaces_of.get(supertype, []),
        supertype_of.get(supertype),
        methods_by_type,
        interfaces_of,
        supertype_of,
        annotations_by_target,
        mapping_fqns,
        visited,
    )


def _resolve_prefix(
    interfaces: list[str],
    supertype: str | None,
    interfaces_of: dict[str, list[str]],
    supertype_of: dict[str, str],
    annotations_by_target: dict[str, list[tuple[str, dict[str, Any]]]],
    prefix_fqns: list[str],
    visited: set[str],
) -> tuple[str, dict[str, Any]] | None:
    """The type-level twin of `_resolve_method`: walks the same
    interfaces-then-superclass order looking for an ancestor TYPE's own
    `prefix_fqns` annotation rather than a same-key method's."""
    for interface in interfaces:
        if interface in visited:
            continue
        visited.add(interface)
        found = _own_mapping(interface, set(prefix_fqns), annotations_by_target)
        if found is not None:
            return found
        found = _resolve_prefix(
            interfaces_of.get(interface, []),
            supertype_of.get(interface),
            interfaces_of,
            supertype_of,
            annotations_by_target,
            prefix_fqns,
            visited,
        )
        if found is not None:
            return found
    if supertype is None or supertype in visited:
        return None
    visited.add(supertype)
    found = _own_mapping(supertype, set(prefix_fqns), annotations_by_target)
    if found is not None:
        return found
    return _resolve_prefix(
        interfaces_of.get(supertype, []),
        supertype_of.get(supertype),
        interfaces_of,
        supertype_of,
        annotations_by_target,
        prefix_fqns,
        visited,
    )


def _is_synthetic(
    symbol: str,
    siblings: Any,
    signature_by_symbol: dict[str, dict[str, Any] | None],
    modifiers_by_symbol: dict[str, dict[str, Any] | None],
) -> bool:
    """Whether the compiler generated `symbol`, rather than a person writing it.

    **The fact says so.** D00 §5a: a method carries `modifiers.synthetic`, with
    `ACC_BRIDGE` folded in because javac sets the two together. This is read
    rather than inferred, and reading it is the whole of OI-47.

    `_is_bridge` below is the fallback, taken when nothing was reported about
    this method — no `modifiers` key at all, or an EMPTY one, which is what
    `SymbolFact.modifiers` defaults to and therefore what every hand-built fact
    in the tests carries. `"synthetic" in modifiers` is the test rather than
    `modifiers.get(...)` because "reported, and false" and "not reported" are
    different answers and only the second may fall back; an empty dict reports
    nothing and so falls back too.

    A MIXED set — the bridge reporting modifiers and its sibling not — answers
    incoherently: the sibling falls back, `_is_bridge` is symmetric, and it
    reports the real method synthetic as well, so the redirect finds no target
    and the mapping is dropped. Unreachable today, since siblings come from one
    scan of one class file and this scanner writes both keys on every method.
    """
    modifiers = modifiers_by_symbol.get(symbol)
    if modifiers is not None and "synthetic" in modifiers:
        return bool(modifiers["synthetic"])
    return _is_bridge(symbol, siblings, signature_by_symbol)


def _synthesis_target(
    candidate: str,
    siblings: Any,
    signature_by_symbol: dict[str, dict[str, Any] | None],
    modifiers_by_symbol: dict[str, dict[str, Any] | None],
) -> str | None:
    """The method a mapping resolved through `candidate` actually belongs to.

    Usually `candidate` itself. The exception is the whole of this fix.

    **A bridge is the only thing that can resolve, and it is the wrong target.**
    `_resolve_method` joins an ancestor's method by name AND descriptor, and a
    covariant or generic override's descriptor is by definition not its
    ancestor's — the forwarder javac generates beside it is. So the mapping is
    reachable only through the bridge, and publishing it there names a method
    nobody wrote as the handler.

    Both directions of getting that wrong shipped, and they were one cause:

    * a COVARIANT override (differs in return type) was recognised by the old
      structural rule, and excluded together with the real method — so the
      mapping was **lost**;
    * a GENERIC-PARAMETER override (differs in parameter types, same return) was
      not recognised at all, so the row was published **naming the bridge**.

    So a bridge is evidence, not a target: the mapping is carried across to the
    method it forwards to — the same class, the same plain name, not synthetic.
    Exactly one, or nothing at all: several same-named real overloads leave no
    way to say which one this bridge stands for, and §8 says produce nothing
    rather than pick.
    """
    if not _is_synthetic(candidate, siblings, signature_by_symbol, modifiers_by_symbol):
        return candidate
    name = method_name(bare_descriptor(candidate))
    # A bridge has its target's ARITY — it forwards the same argument list, only
    # more weakly typed. Matching on the name alone picks an unrelated overload:
    # measured on javac 26, `class Sub extends Base implements IGet<String>`
    # where `Base` declares `get()` and `Sub` declares only an unrelated
    # `get(int)` emits a bridge `get()` in `Sub` forwarding to `Base.get()`, and
    # the one same-name method in `Sub` is the `get(int)` that has nothing to do
    # with it. Publishing the mapping there swaps one fabrication for another.
    #
    # The arity guard also declines that case outright rather than reaching for
    # the superclass: the method a bridge forwards to is not always in the same
    # class, and this rule cannot see there. Nothing, per §8.
    arity = len(_parameter_types(signature_by_symbol.get(candidate)))
    declared = [
        sibling
        for sibling in siblings
        if sibling != candidate
        and method_name(bare_descriptor(sibling)) == name
        and len(_parameter_types(signature_by_symbol.get(sibling))) == arity
        and not _is_synthetic(sibling, siblings, signature_by_symbol, modifiers_by_symbol)
    ]
    return declared[0] if len(declared) == 1 else None


def _is_bridge(
    candidate: str,
    siblings: Any,
    signature_by_symbol: dict[str, dict[str, Any] | None],
) -> bool:
    """Checkpoint item (4)'s structural bridge rule, kept as the FALLBACK
    (OI-47): within the SAME class, a same-name method whose parameter types
    match `candidate`'s exactly but whose return type does not is the
    compiler-generated bridge (or, from that method's own perspective,
    `candidate` is).

    It used to say bytecode carries no other marker — "no `modifiers`, no
    `access`, identical `visibility` — so this is the only signal there is".
    That stopped being true when the method `modifiers` slot shipped: D00 §5a
    writes `synthetic` with `ACC_BRIDGE` folded in, and `_is_synthetic` reads
    it. This runs only for a fact carrying no `modifiers` key at all, and
    inherits the limits below wherever it does.

    Boundary (Task 7 review, Important finding I1 — NOT "this only ever
    suppresses the bridge itself"): the rule is purely structural and
    per-class, blind to WHICH ancestor relationship produced a given
    same-name sibling. A class overriding one method that is simultaneously
    covariant against a mapped interface AND a generic superclass can carry
    two bridges (one exact-matching each ancestor's own descriptor) plus one
    real override — three methods sharing a name and parameter list. Every
    pairing among the three trips this rule, so ALL three are excluded, not
    only the genuine bridge(s): the real override, even where its own
    descriptor happens to equal one ancestor's exactly (a direct match, not
    a covariant one), never gets the chance to synthesize that ancestor's
    mapping. `inherited_rows`'s own docstring carries the same note; this is
    shipped as-is (checkpoint-mandated, and bytecode gives no richer
    signal), recorded as a COVERAGE boundary rather than silently assumed
    away."""
    name = method_name(bare_descriptor(candidate))
    params = _parameter_types(signature_by_symbol.get(candidate))
    returns = _return_type(signature_by_symbol.get(candidate))
    for sibling in siblings:
        if sibling == candidate:
            continue
        if method_name(bare_descriptor(sibling)) != name:
            continue
        if _parameter_types(signature_by_symbol.get(sibling)) != params:
            continue
        if _return_type(signature_by_symbol.get(sibling)) != returns:
            return True
    return False


def _parameter_types(signature: dict[str, Any] | None) -> list[Any]:
    """The parameters as the DESCRIPTOR names them, which is what makes them
    comparable between two declarations.

    `type.symbol` is the signature's answer where the method has one, so a
    parameter declared `T` reads `T` — and a type variable's name means nothing
    outside the declaration that introduced it. It matters here specifically: a
    covariant override carries a `Signature` and reads `T`, while the bridge
    beside it carries none and reads the erasure, so the rule below — same
    parameters, different return — stops recognising the pair it exists to find.
    `erased_symbol` is the same string for both. Falls back for a fact written
    before the field existed."""
    if not signature:
        return []
    return [
        p.get("erased_symbol") or (p.get("type") or {}).get("symbol")
        for p in signature.get("parameters") or []
    ]


def _return_type(signature: dict[str, Any] | None) -> Any:
    if not signature:
        return None
    return (signature.get("returns") or {}).get("symbol")


def _superclass_of(superclass_rows: list[dict[str, Any]]) -> dict[str, str]:
    """Each class's own direct superclass, module-prefixed on both sides
    (capability 9.13, `ClassScanner.erasedSuperclassJson` writing through
    `symbolOf`).

    A plain comprehension because there is nothing to resolve: the fact
    already names both ends in the coordinate space every other lookup here
    works in. A superclass the module never scanned — a framework base class
    living in a jar — matches no annotation target and contributes nothing,
    which is the honest answer rather than a case to defend against.
    """
    return {
        str(row["symbol"]): str(row["superclass"])
        for row in superclass_rows
        if row.get("superclass")
    }
