"""A payload type whose wire contract is in its ACCESSORS, not its fields (F4 §5.2, W26).

## What the empty shape cost

`Page<T>` and `Slice<T>` are interfaces. An interface declares no fields, and expansion
read fields only — so the most common paginated Spring response expanded to a shape with
zero fields however well the type was reached. Measured on the fixture before this:
`Page<OrderView>` was an open shape with no fields even with spring-data-commons named
in `extract_libraries`, so `OrderView` — the payload the reader wants — appeared nowhere
but inside the shape's own id string.

Measured after, with the jar in reach: eleven fields, `content` an **array of
`OrderView`**, and `pageable`/`sort` expanded in turn. That is the JSON Spring actually
sends, field for field.

## Why `Page` is not a `wrappers` entry

G-66 says these types are "declared as wrappers nowhere" and reads as if declaring them
were the fix. It is not, and the measurement says so: a `wrappers` entry means *this
type vanishes on the wire and the payload at `payload_arg` is what is serialised*, which
is true of `ResponseEntity` and `Optional` and false of `Page`. Spring serialises a page
as `{content: [...], totalElements: ...}`; its own `PagedModel<T>`, added in
spring-data-commons 3.5 for exactly this reason, is `{content: List<T>, metadata}`.
Rooting through `Page` would publish `OrderView` as the response body — a contract no
handler produces. G-66 itself calls today's behaviour "under-report rather than
fabrication"; the remedy it implies would trade that for a fabrication, which NFR-2
rates worse.

## The rule is Jackson's, read from Jackson

Every clause below is taken from jackson-databind 2.22.1's own
`DefaultAccessorNamingStrategy` bytecode, not from its documentation (§5.3) — the
`is`-must-be-boolean constraint in `findNameForIsGetter`, the bare-`get()` refusal and
the leading-run lowercasing in `legacyManglePropertyName`. A rule mirrored from what the
prefixes *look* like is the defect class that produced W13, W14 and six findings in
W19's probes alone, and here it would publish `hasNext()` and `nextPageable()` as fields
of every paged response.
"""

import dataclasses
import json
from pathlib import Path

from test_shapes import (
    _CATALOG,
    _MODULE,
    _document,
    _field,
    _ref,
    _string,
    _type,
    _write,
)

from sextant.application.resolve.shapes.expansion import derive_shapes
from sextant.storage.duckdb.workspace import DuckDbWorkspace

TOTALS = "com/acme/orders/Totals#"
HOLDER = "com/acme/orders/Holder#"
PAGE = "com/acme/orders/Page#"
SLICE = "com/acme/orders/Slice#"
RENAMED = "com/acme/orders/Renamed#"
ITEM = "com/acme/orders/Item#"
EMPTY = "com/acme/orders/Empty#"

# The shape model declaring which methods name a property (D02 §2f). The shared
# `_CATALOG` deliberately declares none, so a test can hold both answers.
_WITH_ACCESSORS = dataclasses.replace(
    _CATALOG,
    serialization={
        **_CATALOG.serialization,
        "accessors": [{"prefix": "get"}, {"prefix": "is", "wire_type": "boolean"}],
    },
)


def _method(
    document_id: str,
    owner: str,
    name: str,
    returns: dict | None,
    *,
    parameters: tuple[dict, ...] = (),
    visibility: str = "public",
    static: bool = False,
    synthetic: bool = False,
) -> dict:
    """One declared method fact, as `ClassScanner` emits it.

    **`returns` is always written, void included** — and the first version of this helper
    said the opposite, which made the void near-miss below assert its own fabricated
    input (W26 review). `ClassScanner` writes the key unconditionally and `WireTypes.of`
    maps `Type.VOID` to an empty `wire_type`, so a void method arrives as a JSON OBJECT,
    not as SQL NULL. `_void()` is what the scanner really emits; `returns=None` is kept
    for the one thing it does test — a signature with the key genuinely missing, which
    `_declared`'s own `isinstance(returns, dict)` guard drops.
    """
    signature: dict = {"parameters": list(parameters)}
    if returns is not None:
        signature["returns"] = returns
    return {
        "kind": "symbol",
        "document_id": document_id,
        "symbol": f"{_MODULE}{owner}{name}(sig_00000000).",
        "construct_kind": "method",
        "enclosing": _MODULE + owner,
        "signature": signature,
        "visibility": visibility,
        "modifiers": {"static": static, "synthetic": synthetic},
        "line_start": 0,
        "line_end": 0,
    }


def _void() -> dict:
    """A `void` return exactly as the scanner writes it: the key IS present, and its
    `wire_type` is empty because `WireTypes.of` maps `Type.VOID` to "" — D00 §5b's
    vocabulary has no member for "no payload", and projecting void as an `object` would
    be a shape claim about a method that returns nothing."""
    return _ref("void#", "")


def _interface(document_id: str, owner: str, *, extends: tuple[str, ...] = ()) -> dict:
    fact = _type(document_id, owner, "interface")
    if extends:
        fact["interfaces"] = [_MODULE + parent for parent in extends]
    return fact


def _generic(fact: dict, *names: str) -> dict:
    fact["type_parameters"] = [
        {"name": name, "bounds": [_ref("java/lang/Object#", "object")]} for name in names
    ]
    return fact


def _fields_of(workspace: DuckDbWorkspace, shape_id: str) -> dict[str, dict]:
    return {
        str(row["wire_name"]): dict(row)
        for row in workspace.query("shape_fields")
        if str(row["shape_id"]) == shape_id
    }


def _open_of(workspace: DuckDbWorkspace, shape_id: str) -> bool:
    return next(
        bool(row["open"]) for row in workspace.query("shapes") if str(row["shape_id"]) == shape_id
    )


def _totals_workspace(tmp_path: Path) -> DuckDbWorkspace:
    """One fieldless interface carrying every accessor shape the rule has to separate."""
    facts = tmp_path / "facts"
    _write(
        facts / "totals.jsonl",
        _document("totals", "Totals.java"),
        [
            _interface("totals", TOTALS),
            _method("totals", TOTALS, "getCurrency", _string()),
            _method("totals", TOTALS, "isSettled", _ref("boolean#", "boolean")),
            # Every one of the six below is NOT a wire field, and each fails a
            # different clause of the rule.
            _method("totals", TOTALS, "isoCode", _string()),
            _method("totals", TOTALS, "hasDiscount", _ref("boolean#", "boolean")),
            _method("totals", TOTALS, "get", _string()),
            _method("totals", TOTALS, "getScaled", _string(), parameters=(_string(),)),
            _method("totals", TOTALS, "getSecret", _string(), visibility="private"),
            _method("totals", TOTALS, "getRegistry", _string(), static=True),
            _method("totals", TOTALS, "getBridged", _string(), synthetic=True),
            _method("totals", TOTALS, "getNothing", _void()),
            # `java.lang.Void` reaches no wire type either — an uninstantiable
            # placeholder whose only value is null — so a rule testing the TYPE NAME
            # rather than the projection would publish this one.
            _method("totals", TOTALS, "getNothingBoxed", _ref("java/lang/Void#", "")),
            # The key genuinely absent, which is a different input from a void return
            # and the only one the old helper was actually exercising.
            _method("totals", TOTALS, "getUnwritten", None),
            # The mangling, which is the clause a reader is most likely to "simplify".
            _method("totals", TOTALS, "getURL", _string()),
            _method("totals", TOTALS, "getURLValue", _string()),
        ],
    )
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(facts)
    return workspace


def test_a_fieldless_interfaces_accessors_become_its_wire_fields(tmp_path: Path):
    """The positive half (§10): the two accessors that ARE bean getters, and nothing
    else."""
    workspace = _totals_workspace(tmp_path)

    derive_shapes(workspace, _WITH_ACCESSORS, [TOTALS])
    fields = _fields_of(workspace, TOTALS)
    closed = not _open_of(workspace, TOTALS)
    workspace.close()

    assert set(fields) == {"currency", "settled", "url", "urlvalue"}, (
        "a fieldless interface's wire contract is its bean accessors, and only those"
    )
    assert fields["currency"]["wire_type"] == "string"
    assert fields["settled"]["wire_type"] == "boolean"
    assert closed, "a type whose accessors were read is expanded, not a gap"


def test_the_leading_run_of_capitals_is_lowercased_whole(tmp_path: Path):
    """`getURL` is `url` and `getURLValue` is `urlvalue` — Jackson's
    `legacyManglePropertyName`, which lowercases the leading RUN and then appends the
    remainder whole.

    Pinned separately because it is the clause that looks wrong when it is right.
    Lowercasing only the first character gives `uRL`; stopping the run one character
    earlier gives `urlValue`, which reads like the obviously intended answer and is what
    `USE_STD_BEAN_NAMING` — a different strategy, off by default — would produce as
    `URLValue`. A test asserting only `currency` and `settled` passes under all three,
    which is how the first version of this file left the rule unmeasured.
    """
    workspace = _totals_workspace(tmp_path)

    derive_shapes(workspace, _WITH_ACCESSORS, [TOTALS])
    fields = _fields_of(workspace, TOTALS)
    workspace.close()

    assert "url" in fields and "uRL" not in fields
    assert "urlvalue" in fields and "urlValue" not in fields and "URLValue" not in fields


def test_the_eleven_near_misses_are_each_left_off_the_wire(tmp_path: Path):
    """The paired near-miss (§10). Each name here reaches the same pass as `currency`
    and is refused for its own reason — so a rule that widened by one clause would
    publish exactly one of them, and this names which.

    `isoCode` is the one worth stating twice: it is `is`-prefixed and returns a String,
    which Jackson refuses unless `isGettersNonBoolean` is enabled. Without the
    `wire_type` constraint the field would be called `oCode`, a name nothing on either
    side of the wire writes.

    Nine until W26's review, and the two it gained are the ones that were never being
    tested: `getNothing` was built with NO `returns` key, a shape the scanner does not
    emit, so the void clause it claimed to pin was dead for real facts while real void
    methods sailed through. `getNothingBoxed` is the near-miss for the fix itself — a
    `java.lang.Void` return reaches no wire type either, and a guard written against the
    type NAME would have published it.
    """
    workspace = _totals_workspace(tmp_path)

    derive_shapes(workspace, _WITH_ACCESSORS, [TOTALS])
    fields = _fields_of(workspace, TOTALS)
    workspace.close()

    for absent, why in (
        ("oCode", "`is` on a non-boolean return is not a getter"),
        ("isoCode", "nor is it a property under its own name"),
        ("discount", "`has` is not a declared prefix"),
        ("Discount", "nor under any other mangling of it"),
        ("scaled", "an accessor takes no arguments"),
        ("secret", "a private accessor is not introspected"),
        ("registry", "a static accessor belongs to the type, not the payload"),
        ("bridged", "a synthetic accessor is the compiler's, not the author's"),
        ("nothing", "a void accessor returns nothing to serialise"),
        ("nothingBoxed", "and neither does one returning java.lang.Void"),
        ("unwritten", "a signature with no return at all describes nothing"),
    ):
        assert absent not in fields, f"{absent} must not reach the wire: {why}"


def test_no_declared_accessor_prefix_reads_no_accessor(tmp_path: Path):
    """The shape model is what turns this on. `_CATALOG` declares no `accessors` block,
    and the same interface then expands exactly as it did before W26 — an open,
    zero-field shape.

    This is the guard against the rule becoming code: framework knowledge that lives in
    a catalog can be corrected by editing a catalog (§1b, the reason the three payload
    blocks moved out of forty-two files), and one that lives here cannot.
    """
    workspace = _totals_workspace(tmp_path)

    derive_shapes(workspace, _CATALOG, [TOTALS])
    fields = _fields_of(workspace, TOTALS)
    still_open = _open_of(workspace, TOTALS)
    workspace.close()

    assert fields == {}
    assert still_open


def test_fields_win_over_accessors_where_a_type_has_both(tmp_path: Path):
    """The fallback replaces an EMPTY answer, never a real one — which is what makes it
    additive: every shape that carried rows before W26 carries the same rows now.

    A class with a `total` field and a `getComputed()` accessor is described by the
    field alone. Reading both would put a derived value on the wire beside the stored
    one, and reading accessors instead would change the answer for every payload type
    in every existing workspace.
    """
    facts = tmp_path / "facts"
    _write(
        facts / "holder.jsonl",
        _document("holder", "Holder.java"),
        [
            _type("holder", HOLDER),
            _field("holder", HOLDER, "total", _ref("long#", "integer", "int64")),
            _method("holder", HOLDER, "getComputed", _string()),
        ],
    )
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(facts)

    derive_shapes(workspace, _WITH_ACCESSORS, [HOLDER])
    fields = _fields_of(workspace, HOLDER)
    workspace.close()

    assert set(fields) == {"total"}, "a type with fields keeps exactly the fields it had"


def _page_workspace(tmp_path: Path, *, variable: str) -> DuckDbWorkspace:
    """`Page<T> extends Slice<{variable}>`, where `Slice` holds the accessor that
    carries the payload — the shape `Page` really has, one level up."""
    facts = tmp_path / "facts"
    _write(
        facts / "slice.jsonl",
        _document("slice", "Slice.java"),
        [
            _generic(_interface("slice", SLICE), "T"),
            _method(
                "slice",
                SLICE,
                "getContent",
                _ref("java/util/List#", "array", arguments=[_ref("T", "object")]),
            ),
            _method("slice", SLICE, "getSize", _ref("int#", "integer", "int32")),
        ],
    )
    _write(
        facts / "page.jsonl",
        _document("page", "Page.java"),
        [
            _generic(_interface("page", PAGE, extends=(SLICE,)), variable),
            _method("page", PAGE, "getTotalElements", _ref("long#", "integer", "int64")),
        ],
    )
    _write(
        facts / "item.jsonl",
        _document("item", "Item.java"),
        [_type("item", ITEM), _field("item", ITEM, "label", _string())],
    )
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(facts)
    return workspace


def test_an_accessor_on_a_scanned_ancestor_reaches_the_subtypes_shape(tmp_path: Path):
    """The walk, which is the half that must not be skipped.

    `Page` declares `getTotalElements` and nothing else; `getContent()` — the accessor
    the payload travels in — is on `Slice`. A rule reading only the named type would
    publish a paged response whose page metadata is present and whose CONTENT is
    missing, which is a worse document than the empty shape it replaced. Not walking
    the supertypes is the same defect W19's review found in the catalog surface probe
    and W22's found one level deeper.

    The type argument is substituted through the ancestor too: `content` is an array of
    `Item`, not of an unbound `T`.
    """
    workspace = _page_workspace(tmp_path, variable="T")
    bound = f"{PAGE}<{ITEM}>"

    derive_shapes(workspace, _WITH_ACCESSORS, [bound])
    fields = _fields_of(workspace, bound)
    closed = not _open_of(workspace, bound)
    workspace.close()

    assert set(fields) == {"totalElements", "content", "size"}, (
        "the subtype's own accessors AND its scanned ancestors'"
    )
    assert fields["content"]["wire_type"] == "array"
    assert json.loads(str(fields["content"]["item"]))["shape_id"] == ITEM, (
        "the payload type must reach the reader — it is the whole point of the row"
    )
    assert closed


def test_a_type_declaring_no_accessor_of_its_own_still_presents_its_ancestors(
    tmp_path: Path,
):
    """The purest form of the shape, and the one a first version of this dropped.

    `Empty extends Slice<Item>` declares nothing at all. Keying the accessor map on the
    types that DECLARE an accessor gives it no entry, so the fallback never fires and it
    expands to zero fields — while `Slice` itself, which declares two, expands fine.

    This is the same mistake `scripts/corpus_shapes.py` records making about resolvable
    calls: "the owner declares at least one method of its own" dropped `PetType` and
    `Specialty`, which inherit everything, and understated the count by 27%. Membership
    in a declaring set is not the question; what the type PRESENTS is.
    """
    workspace = _page_workspace(tmp_path, variable="T")
    facts = tmp_path / "facts"
    _write(
        facts / "empty.jsonl",
        _document("empty", "Empty.java"),
        [_interface("empty", EMPTY, extends=(SLICE,))],
    )
    workspace.close()
    workspace = DuckDbWorkspace(tmp_path / "again.duckdb")
    workspace.load_facts(facts)

    derive_shapes(workspace, _WITH_ACCESSORS, [EMPTY])
    fields = _fields_of(workspace, EMPTY)
    workspace.close()

    assert set(fields) == {"content", "size"}, (
        "a type that declares no accessor of its own still presents its ancestors'"
    )


def test_a_renamed_variable_across_the_hierarchy_leaves_the_field_undescribed(
    tmp_path: Path,
):
    """Substitution is by variable NAME, and the honest failure when the names differ.

    `Page<P> extends Slice<T>` binds `P` to `Item`, and `Slice`'s `getContent(): List<T>`
    still holds `T`. An unbound variable gets no shape id at all, so `content` is
    undescribed and the shape stays OPEN — the answer degrades to what it was before
    W26 rather than binding `T` to whatever happened to sit at that position.

    Pinned because the safe direction to be wrong in is the one worth being able to
    prove: a later change that made this bind would be silently inventing a payload.
    """
    workspace = _page_workspace(tmp_path, variable="P")
    bound = f"{PAGE}<{ITEM}>"

    derive_shapes(workspace, _WITH_ACCESSORS, [bound])
    fields = _fields_of(workspace, bound)
    still_open = _open_of(workspace, bound)
    workspace.close()

    assert "shape_id" not in json.loads(str(fields["content"]["item"])), (
        "an unbound variable names no type, so the item points at no shape"
    )
    assert still_open, "a shape with an undescribed field is open"


def test_a_type_this_workspace_never_read_gains_no_accessors(tmp_path: Path):
    """The boundary F4 §5.2 states. Accessors come from class files this workspace read,
    exactly as fields do — so a payload type reachable through neither a sibling nor
    `extract_libraries` stays an open, zero-field shape, and the type is still reported
    as one nothing could expand.

    Measured on the fixture, which names spring-data-commons in no `extract_libraries`:
    its `Page<OrderView>` response is open with no fields, and only naming the jar
    turns it into the eleven-field contract this module's own interfaces already get.
    """
    facts = tmp_path / "facts"
    _write(
        facts / "holder.jsonl",
        _document("holder", "Holder.java"),
        [
            _type("holder", HOLDER),
            _field("holder", HOLDER, "totals", _ref(RENAMED, "object")),
        ],
    )
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(facts)

    unexpanded = derive_shapes(workspace, _WITH_ACCESSORS, [HOLDER]).unexpanded_types
    still_open = _open_of(workspace, HOLDER)
    workspace.close()

    assert RENAMED in unexpanded, "a type with no class file here is still a stated gap"
    assert still_open


def test_a_field_whose_type_is_described_only_by_accessors_does_not_open_its_owner(
    tmp_path: Path,
):
    """W26 added `and not accessors.of(held)` to the `open` computation and nothing
    tested it — measured by mutation in the wave's review: deleting the clause left the
    whole suite green.

    A shape is OPEN when a field of its own holds a type nothing here describes. Before
    the accessor fallback, "describes" meant bytecode fields or a declared shape, and an
    interface had neither — so `Page`'s `pageable` field, holding an interface this pass
    now expands in full, reported its owner open. A gap report pointing at a type that IS
    described is a reader sent to look at nothing.
    """
    facts = tmp_path / "facts"
    _write(
        facts / "slice.jsonl",
        _document("slice", "Slice.java"),
        [
            _interface("slice", SLICE),
            _method("slice", SLICE, "getSize", _ref("int#", "integer", "int32")),
        ],
    )
    _write(
        facts / "holder.jsonl",
        _document("holder", "Holder.java"),
        [_type("holder", HOLDER), _field("holder", HOLDER, "slice", _ref(SLICE, "object"))],
    )
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(facts)

    derive_shapes(workspace, _WITH_ACCESSORS, [HOLDER])
    held_by_accessors = _open_of(workspace, HOLDER)
    workspace.close()

    # And the control: the SAME facts with no accessor rule leave `Slice` undescribed,
    # so the owner is genuinely open. The difference is the whole clause.
    workspace = DuckDbWorkspace(tmp_path / "again.duckdb")
    workspace.load_facts(facts)
    derive_shapes(workspace, _CATALOG, [HOLDER])
    held_by_nothing = _open_of(workspace, HOLDER)
    workspace.close()

    assert held_by_accessors is False
    assert held_by_nothing is True


def test_the_superclass_chain_is_exhausted_before_any_interface(tmp_path: Path):
    """JVMS 5.4.3.3 order, which the commit message leads with and no test reached.

    A type can inherit one property name from two places at once. The JVM searches the
    class, then the SUPERCLASS CHAIN TO EXHAUSTION, then the interfaces — so a
    declaration two levels up the class chain beats one on a directly implemented
    interface, and a shape that took the nearer declaration would publish a different
    wire type for the same JSON key.

    **The depth is the test.** `Child extends Base implements Named`, `Base extends
    GrandBase`, and `getLabel` is declared on `GrandBase` (int) and on `Named` (String).
    A naive breadth-first walk reaches `Named` at depth 1 and answers `string`; 5.4.3.3
    reaches `GrandBase` first and answers `integer`. A first version of this test put the
    conflict at depth 1, where both walks agree — and passed under the mutation it was
    written to catch.
    """
    facts = tmp_path / "facts"
    grand = "com/acme/orders/GrandBase#"
    _write(
        facts / "grand.jsonl",
        _document("grand", "GrandBase.java"),
        [
            _type("grand", grand),
            _method("grand", grand, "getLabel", _ref("int#", "integer", "int32")),
        ],
    )
    base = _type("base", "com/acme/orders/Base#")
    base["superclass"] = _MODULE + grand
    _write(facts / "base.jsonl", _document("base", "Base.java"), [base])
    _write(
        facts / "iface.jsonl",
        _document("iface", "Named.java"),
        [
            _interface("iface", "com/acme/orders/Named#"),
            _method("iface", "com/acme/orders/Named#", "getLabel", _string()),
        ],
    )
    child = _type("child", "com/acme/orders/Child#")
    child["superclass"] = _MODULE + "com/acme/orders/Base#"
    child["interfaces"] = [_MODULE + "com/acme/orders/Named#"]
    _write(facts / "child.jsonl", _document("child", "Child.java"), [child])
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(facts)

    derive_shapes(workspace, _WITH_ACCESSORS, ["com/acme/orders/Child#"])
    fields = _fields_of(workspace, "com/acme/orders/Child#")
    workspace.close()

    assert fields["label"]["wire_type"] == "integer", (
        "a declaration two levels up the class chain beats one on a direct interface"
    )


def test_a_subtypes_own_accessor_wins_over_the_one_it_overrides(tmp_path: Path):
    """First declaration of a property name wins, which is what an override IS.

    `of()` walks the closure and keeps the first declaration per property name. Drop that
    dedup and a subtype narrowing its ancestor's accessor publishes the property twice —
    two rows for one JSON key. Measured by mutation in W26's review: dropping the `seen`
    set left the suite green.
    """
    facts = tmp_path / "facts"
    _write(
        facts / "base.jsonl",
        _document("base", "Base.java"),
        [
            _interface("base", "com/acme/orders/Base#"),
            _method("base", "com/acme/orders/Base#", "getLabel", _ref("int#", "integer", "int32")),
        ],
    )
    _write(
        facts / "child.jsonl",
        _document("child", "Child.java"),
        [
            _interface("child", "com/acme/orders/Child#", extends=("com/acme/orders/Base#",)),
            _method("child", "com/acme/orders/Child#", "getLabel", _string()),
        ],
    )
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(facts)

    derive_shapes(workspace, _WITH_ACCESSORS, ["com/acme/orders/Child#"])
    rows = [
        row
        for row in workspace.query("shape_fields")
        if str(row["shape_id"]) == "com/acme/orders/Child#"
    ]
    workspace.close()

    assert len(rows) == 1, "one property name is one field, however many declare it"
    assert rows[0]["wire_type"] == "string", "the type's own declaration is the first found"


def test_an_undescribed_object_nested_two_levels_deep_still_opens_its_owner(
    tmp_path: Path,
):
    """W25's element-chain fix, at the depth its own docstring names as the reason it
    recurses — and the recursion was untested (W26 review, mutation: stopping after one
    level left the suite green; the single-level `List<T>` case is covered).

    A `List<List<T>>` whose `T` is bound to nothing describes no object at any level, and
    a shape holding it is OPEN. Checking only the outer reference reports a payload
    complete while saying nothing about what it carries.
    """
    facts = tmp_path / "facts"
    inner = _ref("java/util/List#", "array", arguments=[_ref("T", "object")])
    _write(
        facts / "holder.jsonl",
        _document("holder", "Holder.java"),
        [
            _type("holder", HOLDER),
            _field(
                "holder",
                HOLDER,
                "rows",
                _ref("java/util/List#", "array", arguments=[inner]),
            ),
        ],
    )
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(facts)

    derive_shapes(workspace, _WITH_ACCESSORS, [HOLDER])
    is_open = _open_of(workspace, HOLDER)
    workspace.close()

    assert is_open is True


def test_a_raw_collection_field_leaves_its_owner_open(tmp_path: Path):
    """A field declared `List` with NO type argument names no element type, so its owner
    is not a complete description of the payload (W26 review, minor 7).

    The same over-claim W25 fixed one level in: `List<T>` on a raw type reported its
    owner CLOSED while saying nothing about what the list carried. A raw `List` is the
    degenerate case of it — there is not even a variable to fail to bind — and it read
    closed because a missing `item` was taken for "holds nothing" rather than "holds
    something unnamed". Only `array` changes: a `string` field genuinely holds no element.
    """
    facts = tmp_path / "facts"
    _write(
        facts / "holder.jsonl",
        _document("holder", "Holder.java"),
        [
            _type("holder", HOLDER),
            _field("holder", HOLDER, "rows", _ref("java/util/List#", "array")),
            _field("holder", HOLDER, "label", _string()),
        ],
    )
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(facts)

    derive_shapes(workspace, _WITH_ACCESSORS, [HOLDER])
    is_open = _open_of(workspace, HOLDER)
    fields = _fields_of(workspace, HOLDER)
    workspace.close()

    # The field is still PUBLISHED — the row says `array` with no element, which is what
    # was read. Open is about the shape's completeness, not about dropping the field.
    assert set(fields) == {"rows", "label"}
    assert is_open is True
