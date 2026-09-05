"""No catalog `known_types` entry contradicts the extractor's own projection
(GUIDELINES §8.1, §8.3; principles sweep `A-C3`).

## The claim twenty-eight catalogs make, and what falsified it

Twenty-eight shipped catalogs carry the same comment beside their
`known_types` block — that the block MIRRORS the extractor's projection rather
than repairing it. `okhttp.yml` states the sharper form as an invariant: every
outbound catalog's `wrappers`/`serialization`/`known_types` must agree, because
`derive_shapes` is a GLOBAL insert-if-absent pass keyed on the type symbol
alone, so whichever catalog reaches a shared payload type first describes it for
every other one.

`A-C3` falsified that for `java.lang.Void`. `WireTypes` mapped only the
primitive `void` to the empty string; `java/lang/Void` is an OBJECT sort and
fell through to `default -> "object"`. Thirty-three catalogs carried
`{type: java.lang.Void, wire: ""}` — a repair — and nine did not, so an endpoint
returning no body was published as returning an object and `java/lang/Void#` was
filed as an unexpanded type, a gap report pointing at a type with nothing to
expand. The projection is fixed at the source now, and this is the ratchet that
keeps the comment true.

## What it checks, and what it cannot

It compares each catalog entry against `WireTypes.objectLike`'s own switch,
read out of the Java source. Only entries for a type the projection ALREADY
names are compared: `java.time.Instant` is genuine catalog knowledge (the
extractor deliberately projects no date types) and is none of this rule's
business. What the rule refuses is a catalog silently disagreeing with the
language projection about a type both of them describe.

Reading the switch out of source is the same two-sides-pinned-together pattern
`domain/paths.py` keeps against `derive_endpoints.sql`'s own `$canonical_path`
gate, and for the same reason: the two live either side of a boundary neither
can import across.

It is OFFLINE and deterministic (NFR-1): it reads committed files and runs
nothing. It cannot tell whether the projection itself is RIGHT —
`extractor-jvm`'s own `WireTypesTest` is where that is asserted.
"""

import re
from pathlib import Path

import yaml

REPO = Path(__file__).parents[2]
CATALOGS = REPO / "src" / "sextant" / "catalogs"
WIRE_TYPES = (
    REPO
    / "extractor-jvm"
    / "src"
    / "main"
    / "java"
    / "dev"
    / "sextant"
    / "extractor"
    / "WireTypes.java"
)

# One `case "a", "b" -> "wire";` arm of a `javap`-free switch over internal
# names. The `default ->` arm is deliberately unmatched: "everything else is an
# open object" is not a projection of a named type, and treating it as one would
# make this rule refuse every legitimate `known_types` entry in the tree.
_ARM = re.compile(r'case\s+((?:"[\w/$]+"\s*,?\s*)+)->\s*"([^"]*)"\s*;')
_NAME = re.compile(r'"([\w/$]+)"')


def projected_wire_types() -> dict[str, str]:
    """`java.lang.X -> wire` for every type `WireTypes.objectLike` names.

    Read from the `objectLike` method only. `of()`'s own switch is over
    `getSort()` — primitives and arrays — and names no type this vocabulary
    could clash with.
    """
    source = WIRE_TYPES.read_text(encoding="utf-8")
    start = source.index("private static String objectLike(")
    body = source[start : source.index("\n    }", start)]
    projected: dict[str, str] = {}
    for names, wire in _ARM.findall(body):
        for internal in _NAME.findall(names):
            projected[internal.replace("/", ".")] = wire
    return projected


def declared_known_types() -> list[tuple[str, str, str]]:
    """`(catalog, type, wire)` for every `known_types` entry that ships."""
    declared = []
    for path in sorted(CATALOGS.glob("*.yml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for entry in document.get("known_types") or []:
            declared.append((path.stem, str(entry["type"]), str(entry.get("wire", ""))))
    return declared


def test_the_switch_is_readable_at_all():
    """A parse that finds nothing agrees with everything. Two pins, one per
    arm shape: a single-name arm and a multi-name one, so a regex that lost
    either would be caught here rather than by passing vacuously below."""
    projected = projected_wire_types()
    assert projected["java.lang.String"] == "string"
    assert projected["java.lang.Short"] == "integer"
    assert projected["java.util.Map"] == "map"
    assert len(projected) >= 10


def test_the_void_placeholder_reaches_no_wire_type_in_the_projection():
    """`A-C3`, at this end. The nine catalogs that declared no `known_types`
    repair for `java.lang.Void` published an endpoint returning nothing as
    returning an object — so the fix belongs in the projection, where it is
    true for every catalog including the ones nobody has written yet."""
    assert projected_wire_types()["java.lang.Void"] == ""


def test_no_catalog_contradicts_the_projection():
    """The rule. A catalog entry that disagrees with the extractor is not a
    local opinion: `derive_shapes` is global and insert-if-absent, so it
    describes the type for every catalog that later reaches it."""
    projected = projected_wire_types()
    disagreements = sorted(
        (catalog, name, wire, projected[name])
        for catalog, name, wire in declared_known_types()
        if name in projected and projected[name] != wire
    )
    assert disagreements == [], (
        "these `known_types` entries disagree with `WireTypes.objectLike`'s own projection:\n"
        + "\n".join(
            f"  - {catalog}: {name} declares wire {declared!r}, the extractor projects {actual!r}"
            for catalog, name, declared, actual in disagreements
        )
        + "\n\nThe `shapes` table is global and insert-if-absent, so whichever catalog reaches "
        "the type first describes it for all of them. Fix the projection, or the catalog."
    )
