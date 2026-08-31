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


def inherited_rows(
    annotation_rows: list[dict[str, Any]],
    implementation_rows: list[dict[str, Any]],
    supertype_rows: list[dict[str, Any]],
    method_rows: list[dict[str, Any]],
    mapping_fqns: set[str],
    prefix_fqn: str | None,
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
    inherit. `implementation_rows`/`supertype_rows`/`method_rows` are each
    the plain-Python form of the same-named workspace query (`implementations`,
    `supertypes`, a new `method_declarations`) — JSON columns already
    decoded, the same convention `composed_mapping_rows` takes for `args`.

    Every symbol here — `implementations.symbol`, its `interfaces` entries,
    `method_rows.enclosing`, and every `annotations` `target` — shares one
    coordinate space: module-prefixed exactly as the fact wrote it (D00
    §5a), which is why none of them is stripped to a bare descriptor before
    a lookup. The one exception is a class's own generic supertype
    reference (`supertypes`, D00 §5a's PTR carrier): like every type
    reference inside a `signature`, its embedded `symbol` is bare even for a
    module-local ancestor (2E checkpoint item (4)), so `_prefixed_types`
    below is the one bare-to-prefixed lookback this module needs.

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
    override, is what the name+descriptor join actually finds. The only
    available discriminator is structural: within one class, a candidate
    whose name and parameter types match another of that class's own
    methods but whose return type does not is a bridge, and neither method
    in that pair is ever a synthesis target (`_is_bridge`). This is an
    honest miss for the fixture's own single-ancestor case (the real
    override's descriptor never matched the interface's anyway), but it is
    a real, checkpoint-mandated boundary, not merely a defensive no-op: a
    class that inherits the SAME-named method from both a mapped interface
    AND a generic superclass can grow two bridges (one exact-matching each
    ancestor's own descriptor) plus one real override, all three sharing
    one name and one parameter list — `_is_bridge` cannot tell which
    ancestor a given bridge belongs to, so it excludes all three, and BOTH
    ancestors' mappings are silently lost, not just the honest single one.
    See `_is_bridge`'s own docstring; documented as a COVERAGE boundary
    (Task 7 review, Important finding I1), not fixed — the structural rule
    is the only signal bytecode carries at all.
    """
    methods_by_type: dict[str, dict[str, str]] = {}
    signature_by_symbol: dict[str, dict[str, Any] | None] = {}
    for row in method_rows:
        symbol = str(row["symbol"])
        signature_by_symbol[symbol] = row.get("signature")
        enclosing = row.get("enclosing")
        if enclosing is None:
            continue
        key = member_name(bare_descriptor(symbol))
        methods_by_type.setdefault(str(enclosing), {})[key] = symbol

    interfaces_of: dict[str, list[str]] = {
        str(row["symbol"]): [str(entry) for entry in row["interfaces"]]
        for row in implementation_rows
    }

    supertype_of = _supertype_of(supertype_rows, interfaces_of, methods_by_type)

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

    # Every type this module has ANY evidence for as a subtype — declaring
    # its own methods, implementing interfaces, or extending a superclass.
    # A class needing only a prefix (no method of its own repeats or misses
    # a mapping — a class implementing an interface entirely through
    # inherited defaults, say) would otherwise never surface: prefix
    # resolution cannot be nested inside "types that own at least one
    # method" the way it read before this comment (Task 7 review,
    # mutation-caught).
    classes = set(methods_by_type) | set(interfaces_of) | set(supertype_of)

    # Final NFR-1 ordering comes from the explicit sort below; iteration
    # order here only has to be exhaustive, not deterministic.
    rows: list[dict[str, Any]] = []
    for type_symbol in classes:
        methods = methods_by_type.get(type_symbol, {})
        for key, candidate in methods.items():
            if _own_mapping(candidate, mapping_fqns, annotations_by_target) is not None:
                continue
            if _is_bridge(candidate, methods.values(), signature_by_symbol):
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
            if found is not None:
                annotation, args = found
                rows.append({"target": candidate, "annotation": annotation, "args": args})
        # Computed once per class, independent of the per-method loop above:
        # a class's inherited prefix applies to EVERY one of its methods
        # that ends up mapped, whether that mapping is itself inherited or
        # the class's own real `@GetMapping` — Spring resolves a
        # `@RequestMapping` prefix at the type level, once, never
        # separately per method (Task 7 review, M2).
        if (
            prefix_fqn is not None
            and _own_mapping(type_symbol, {prefix_fqn}, annotations_by_target) is None
        ):
            found_prefix = _resolve_prefix(
                interfaces_of.get(type_symbol, []),
                supertype_of.get(type_symbol),
                interfaces_of,
                supertype_of,
                annotations_by_target,
                prefix_fqn,
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
    walked up to find. `fqns` is `mapping_fqns` for a method-level check,
    `{prefix_fqn}` for a class's own type-level one; the same helper serves
    both "own wins outright" gates spec §3 states."""
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
) -> tuple[str, dict[str, Any]] | None:
    """Walks directly implemented interfaces (declaration order), then the
    superclass, checking each ancestor's OWN same-key method for a mapping
    annotation before recursing further up that same ancestor's own
    hierarchy — spec §3's resolution order, applied transitively."""
    for interface in interfaces:
        if interface in visited:
            continue
        visited.add(interface)
        method = methods_by_type.get(interface, {}).get(key)
        if method is not None:
            found = _own_mapping(method, mapping_fqns, annotations_by_target)
            if found is not None:
                return found
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
        found = _own_mapping(method, mapping_fqns, annotations_by_target)
        if found is not None:
            return found
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
    prefix_fqn: str,
    visited: set[str],
) -> tuple[str, dict[str, Any]] | None:
    """The type-level twin of `_resolve_method`: walks the same
    interfaces-then-superclass order looking for an ancestor TYPE's own
    `prefix_fqn` annotation rather than a same-key method's."""
    for interface in interfaces:
        if interface in visited:
            continue
        visited.add(interface)
        found = _own_mapping(interface, {prefix_fqn}, annotations_by_target)
        if found is not None:
            return found
        found = _resolve_prefix(
            interfaces_of.get(interface, []),
            supertype_of.get(interface),
            interfaces_of,
            supertype_of,
            annotations_by_target,
            prefix_fqn,
            visited,
        )
        if found is not None:
            return found
    if supertype is None or supertype in visited:
        return None
    visited.add(supertype)
    found = _own_mapping(supertype, {prefix_fqn}, annotations_by_target)
    if found is not None:
        return found
    return _resolve_prefix(
        interfaces_of.get(supertype, []),
        supertype_of.get(supertype),
        interfaces_of,
        supertype_of,
        annotations_by_target,
        prefix_fqn,
        visited,
    )


def _is_bridge(
    candidate: str,
    siblings: Any,
    signature_by_symbol: dict[str, dict[str, Any] | None],
) -> bool:
    """Checkpoint item (4)'s structural bridge rule: within the SAME class,
    a same-name method whose parameter types match `candidate`'s exactly but
    whose return type does not is the compiler-generated bridge (or, from
    that method's own perspective, `candidate` is). Bytecode carries no
    other marker — no `modifiers`, no `access`, identical `visibility` — so
    this is the only signal there is.

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
    if not signature:
        return []
    return [(p.get("type") or {}).get("symbol") for p in signature.get("parameters") or []]


def _return_type(signature: dict[str, Any] | None) -> Any:
    if not signature:
        return None
    return (signature.get("returns") or {}).get("symbol")


def _supertype_of(
    supertype_rows: list[dict[str, Any]],
    interfaces_of: dict[str, list[str]],
    methods_by_type: dict[str, dict[str, str]],
) -> dict[str, str]:
    """Each class's own generic superclass reference, module-prefixed on
    BOTH sides (unlike the raw `supertypes` query, whose inner `symbol` is
    bare — see `inherited_rows`'s docstring). `_prefixed_types` recovers the
    prefixed form from every module-local type symbol this module has
    otherwise seen; an ancestor this module never saw any other evidence for
    (not itself an implementer, an interface, or a method's own enclosing
    type) resolves to nothing here, honestly — 2E checkpoint Falsification
    F3: a generic supertype edge is only ever emitted for a scanned
    ancestor, and a scanned ancestor always encloses at least its own
    inherited `Object` methods... in practice, its own declared ones."""
    prefixed_types = _prefixed_types(interfaces_of, methods_by_type, supertype_rows)
    supertype_of: dict[str, str] = {}
    for row in supertype_rows:
        supertype = row.get("supertype")
        if not supertype:
            continue
        target = prefixed_types.get(bare_descriptor(str(supertype.get("symbol"))))
        if target is not None:
            supertype_of[str(row["symbol"])] = target
    return supertype_of


def _prefixed_types(
    interfaces_of: dict[str, list[str]],
    methods_by_type: dict[str, dict[str, str]],
    supertype_rows: list[dict[str, Any]],
) -> dict[str, str]:
    """Every module-prefixed type symbol this module has independent
    evidence for, keyed by its own bare descriptor — the lookback
    `_supertype_of` needs to cross from a supertype reference's bare
    `symbol` (D00 §5a) back into the module-prefixed space every other
    lookup here works in."""
    prefixed: dict[str, str] = {}
    known = (
        *interfaces_of.keys(),
        *methods_by_type.keys(),
        *(str(row["symbol"]) for row in supertype_rows),
    )
    for symbol in known:
        prefixed.setdefault(bare_descriptor(symbol), symbol)
    for interfaces in interfaces_of.values():
        for symbol in interfaces:
            prefixed.setdefault(bare_descriptor(symbol), symbol)
    return prefixed
