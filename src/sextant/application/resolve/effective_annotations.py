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

from sextant.domain.symbols import bare_descriptor


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
