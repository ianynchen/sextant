"""The JSON shape model is declared ONCE, and no catalog holds a copy
(GUIDELINES §8.1, §8.3; D02 §1b; principles sweep `A-C3`).

## The defect this makes impossible, rather than fixed

Three of D02's blocks describe a PAYLOAD TYPE rather than a framework boundary:
§2f's `serialization` (which annotation carries the wire name), §2e's
`nullability` (which one means "may be null") and §2g's `known_types` (which
types the serialiser turns into a scalar). They were duplicated across
**forty-two catalogs**.

That duplication is not cosmetic, because `derive_shapes` is a GLOBAL,
insert-if-absent pass keyed on the type symbol alone
(`resolve/shapes/expansion.py`), entirely outside `_owns`'s catalog scoping. A
payload type an HTTP endpoint and a Kafka listener both reach is described
ONCE, by whichever catalog reached it first — and catalogs are read in filename
order. So two copies that disagree do not produce two answers; they produce one
arbitrary answer selected by a filename.

`A-C3` is that, live: thirty-three catalogs carried
`{type: java.lang.Void, wire: ""}` and **nine did not**, so
`ResponseEntity<Void>` published an `object` response shape and filed
`java/lang/Void#` as an unexpanded type — a gap report pointing at a type with
nothing to expand, surviving for every catalog that later reached the symbol.

**F2's claim is that this class of defect is now unreachable, not that this
instance is repaired.** Three things carry that claim, and this file is one:

1. There is one declaration. `catalogs/shape-models/json.yml` holds the three
   blocks and forty-two catalogs say `shape_model: json`. A missing entry
   cannot be missing from one copy, because there are no copies.
2. The LOADER refuses a catalog that names a model and declares one of the
   blocks beside it (`ingress/catalogs/yaml_source.py::_shape_model_of`) — so
   a copy cannot be reintroduced by adding a block to a file that already
   references the model, which is the cheapest way back in.
3. This file refuses a shipped catalog that declares one of the blocks with NO
   `shape_model` at all — the other way back in, and the one the loader cannot
   judge, because a repository's own catalog set (D02 §6) may legitimately
   declare its own knowledge and ship no model at all.

## Why the allowlist is EMPTY, and stays empty

§8.3 requires a new enforceable rule to ship with the audit list of the sites it
governs. Here the audit came out empty: every shipped catalog that declares any
of the three now names the model instead, and the list below exists so that an
exception is a deliberate, reviewable edit rather than a silent one. An entry
would be a catalog whose payload-type knowledge genuinely differs from every
other catalog's — and the answer to that is a SECOND shape model it names, not
a private copy, because a private copy is `A-C3` again with a different symbol.

That second model is also what Jackson 2 vs Jackson 3 (Stage 6, F7) becomes:
`@JsonProperty` kept its exact FQN across the split, so the two cannot be told
apart by annotation spelling, but `tools.jackson.core:jackson-databind` and
`com.fasterxml.jackson.core:jackson-databind` are different coordinates. On the
estate this file governs, that is one new file in `shape-models/` — not
eighty-four edited blocks. **What it is NOT is a two-file change end to end**:
choosing between two models per module is a selection rule that does not exist
yet, and this file makes no claim that it does.

It is OFFLINE and deterministic (NFR-1): it reads committed files and runs
nothing.
"""

from pathlib import Path

import yaml

REPO = Path(__file__).parents[2]
CATALOGS = REPO / "src" / "sextant" / "catalogs"
SHAPE_MODELS = CATALOGS / "shape-models"

# D02 §1b's payload-type blocks, spelled once. The loader names the same three
# in `_SHAPE_MODEL_BLOCKS`; a fourth block joining the model has to be added in
# both places, and adding it here alone fails
# `test_the_model_declares_every_block_this_rule_governs` below.
_BLOCKS = ("serialization", "nullability", "known_types")

# Shipped catalogs allowed to declare a payload-type block of their own. EMPTY,
# and the docstring above says why an entry is almost always the wrong answer:
# a catalog whose knowledge really differs names a second model, it does not
# keep a private copy.
_DECLARES_ITS_OWN: frozenset[str] = frozenset()


def _document(path: Path) -> dict[str, object]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def catalogs() -> dict[str, dict[str, object]]:
    """Every shipped catalog by id, read off the directory rather than listed:
    a hand-maintained roster drifts, and the one thing this rule must not do is
    stop seeing a catalog."""
    return {path.stem: _document(path) for path in sorted(CATALOGS.glob("*.yml"))}


def models() -> dict[str, dict[str, object]]:
    return {path.stem: _document(path) for path in sorted(SHAPE_MODELS.glob("*.yml"))}


def test_no_shipped_catalog_declares_a_payload_type_block_of_its_own():
    """The rule. A catalog holding its own copy is how one `known_types` entry
    came to be present in thirty-three files and absent from nine."""
    offenders = sorted(
        (catalog_id, block)
        for catalog_id, document in catalogs().items()
        for block in _BLOCKS
        if block in document and catalog_id not in _DECLARES_ITS_OWN
    )
    assert offenders == [], (
        "these shipped catalogs declare a payload-type block instead of naming a shape "
        "model (D02 §1b):\n"
        + "\n".join(f"  - {catalog_id}: {block}" for catalog_id, block in offenders)
        + "\n\nAdd `shape_model: <id>` and delete the block. If this catalog's knowledge "
        "genuinely differs, add a second file to `catalogs/shape-models/` and name that — a "
        "private copy is `A-C3` waiting to happen, and the whole estate reads whichever copy "
        "sorts first."
    )


def test_the_allowlist_is_empty_and_only_ever_shrinks():
    """An entry naming a catalog that no longer declares a block, or no shipped
    catalog at all, must go in the same commit — and the list is empty today,
    which is the state worth making permanent."""
    shipped = catalogs()
    stale = sorted(
        catalog_id
        for catalog_id in _DECLARES_ITS_OWN
        if catalog_id in shipped and not any(block in shipped[catalog_id] for block in _BLOCKS)
    )
    unknown = sorted(set(_DECLARES_ITS_OWN) - set(shipped))
    assert (stale, unknown) == ([], []), (
        "_DECLARES_ITS_OWN is out of date — "
        f"declares no block any more, so remove them: {stale or 'none'}; "
        f"not a shipped catalog at all: {unknown or 'none'}"
    )


def test_every_shape_model_reference_names_a_model_that_ships():
    """A reference is only as good as its target. The loader refuses an unknown
    one at load time; this says the same thing about the committed estate, so a
    rename inside `shape-models/` fails here with the list of catalogs it broke
    rather than as one `CatalogError` on the first file that happens to be
    read."""
    known = set(models())
    phantom = sorted(
        (catalog_id, str(document["shape_model"]))
        for catalog_id, document in catalogs().items()
        if "shape_model" in document and str(document["shape_model"]) not in known
    )
    assert phantom == [], (
        f"`shape_model` references naming no file in `shape-models/` (known: {sorted(known)}):\n"
        + "\n".join(f"  - {catalog_id}: {named}" for catalog_id, named in phantom)
    )


def test_the_model_declares_every_block_this_rule_governs():
    """A model that supplies only two of the three would silently strip the
    third from all forty-two catalogs — the `A-C3` shape at the largest possible
    scale, arriving through an omission in one file rather than through drift
    between many.

    This is also the pin that keeps the rule above from going vacuous: if the
    blocks were renamed, `_BLOCKS` would match nothing, no catalog would offend,
    and `test_no_shipped_catalog_declares_a_payload_type_block_of_its_own` would
    pass while governing nothing at all.
    """
    shipped = models()
    assert shipped, "no shape model ships — `catalogs/shape-models/` is empty"
    for model_id, document in sorted(shipped.items()):
        missing = [block for block in _BLOCKS if not document.get(block)]
        assert missing == [], f"shape model {model_id} declares no {', '.join(missing)}"


def test_the_estate_actually_uses_the_model():
    """A rule about copies is worth nothing if nobody references the original.
    Forty-two catalogs carried the blocks before F2; a scan that found a handful
    would mean the extraction had quietly stopped part-way."""
    referencing = [
        catalog_id for catalog_id, document in catalogs().items() if "shape_model" in document
    ]
    assert len(referencing) >= 40, (
        f"only {len(referencing)} catalogs name a shape model — forty-two carried the "
        "payload-type blocks when F2 extracted them, and a number this far below that means "
        "catalogs lost their shape knowledge rather than shared it"
    )
    assert "spring-mvc" in referencing and "spring-resttemplate" in referencing, (
        "the two catalogs the sweep quoted `A-C3` from and to — one of the nine missing the "
        "`Void` entry and one of the thirty-three that had it — must both read the one model"
    )
