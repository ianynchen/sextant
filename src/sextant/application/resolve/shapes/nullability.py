from typing import TYPE_CHECKING, Any

from sextant.application.ports.workspace import Workspace

if TYPE_CHECKING:
    from sextant.application.resolve.shapes.expansion import _Rules

# The reserved file-class name the JVM compiles a package-level annotation
# onto — the only spelling `_scope_prefix` strips, so a scope declared on an
# actual type named that (impossible on the JVM) is not a concern.
_PACKAGE_FILE_CLASS = "package-info#"


def _scope_prefixes(workspace: Workspace, rules: "_Rules") -> list[tuple[str, bool]]:
    """Where each declared scope (D02 §2e) reaches, as the symbol prefix it
    claims and the `nullable` value it implies. Read once per pass, not once
    per field: a scope's target is a class or a package, never the field
    itself, so `annotations_of`'s per-field lookup cannot find it."""
    if not rules.scope_annotations:
        return []
    prefixes = []
    for row in workspace.query("annotations"):
        means = rules.scope_annotations.get(str(row["annotation"]))
        if means is None:
            continue
        prefixes.append((_scope_prefix(str(row["target"])), means))
    return prefixes


def _scope_prefix(target: str) -> str:
    """The symbol prefix one scope declaration claims (pre-flight ruling, Task
    11 brief). A type-level target is already a prefix of its own members
    (`…X#` prefixes `…X#code.`); a package-level one compiles onto a
    synthetic file-class, so that trailing segment is stripped to recover the
    package it was actually declared on."""
    if target.endswith(_PACKAGE_FILE_CLASS):
        return target[: -len(_PACKAGE_FILE_CLASS)]
    return target


def _scope_nullable(prefixes: list[tuple[str, bool]], field_symbol: str) -> bool | None:
    """`None` when no declared scope encloses this field. When more than one
    does — a package scope and a class scope inside it — the longer, more
    specific prefix wins, the same way a nearer declaration always overrides
    one further out."""
    claiming = [claim for claim in prefixes if field_symbol.startswith(claim[0])]
    if not claiming:
        return None
    return max(claiming, key=lambda claim: len(claim[0]))[1]


def _explicit_nullable(rules: "_Rules", annotations: list[dict[str, object]]) -> bool | None:
    """`None` when no annotation on the field's own type says anything.
    `type_path` NULL or `''` is what makes this the field's own type rather
    than a type argument's (D00 §5a): `List<@Nullable String>` must not flip
    the field's `nullable`, only its element's."""
    result: bool | None = None
    for use in annotations:
        if use["type_path"] not in (None, ""):
            continue
        if use["annotation"] in rules.not_null_annotations:
            result = False
        elif use["annotation"] in rules.nullable_annotations:
            result = True
    return result


def _nullability_of(
    rules: "_Rules",
    reference: dict[str, Any],
    described_nullable: bool,
    annotations: list[dict[str, object]],
    scope_prefixes: list[tuple[str, bool]],
    field_symbol: str,
) -> tuple[bool, str]:
    """`nullable` and its `resolution`, layered extractor -> scope -> explicit
    annotation (D02 §2e), last wins. `described_nullable` already carries a
    known type's own override where one applies (`_described`); that is
    catalog data too; so it resolves the same way as every later layer."""
    known = rules.known_types.get(reference["symbol"])
    nullable = described_nullable
    resolution = (
        "resolved"
        if known is not None and "nullable" in known
        else str(reference["nullable_resolution"])
    )

    scoped = _scope_nullable(scope_prefixes, field_symbol)
    if scoped is not None:
        nullable, resolution = scoped, "resolved"

    explicit = _explicit_nullable(rules, annotations)
    if explicit is not None:
        nullable, resolution = explicit, "resolved"

    return nullable, resolution
