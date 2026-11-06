"""One lookup order per type (spec 2026-11-06 §3b "Lookup through class parents").

`Dispatch.lookup_order(owner)` is the order a method is searched for on `owner`: the
JVM's own order (JVMS 5.4.3.3) for a module whose `lookup` is `jvm`, and Python's C3
linearization over the written parents, in written order, for one whose `lookup` is `c3`
(DR-6: two languages, two named rules). An unread parent ends the order, and a lookup
that reaches that end answers `external`.

Hand-built `Dispatch` values, as `test_method_resolution.py` builds them, plus one run
through the Python scanner and the workspace, so the rule is read from the module fact.
"""

from pathlib import Path

from sextant.application.ports.scanner import ScanRequest
from sextant.application.resolve.dispatch import Dispatch, dispatch_of
from sextant.domain.factfile import write_fact_file
from sextant.domain.facts import Document, ModuleFact
from sextant.domain.symbols import PY_SIGNATURE, method_descriptor
from sextant.ingress.extract.python.scanner import PythonScanner
from sextant.storage.duckdb.workspace import DuckDbWorkspace

VOID = "()V"
OBJECT = "builtins/object#"


def _dispatch(
    *,
    declares: dict[str, list[str]],
    ancestors: dict[str, list[tuple[str, str, bool]]],
    lookup: str = "c3",
    parents_unread: frozenset[str] = frozenset(),
    descriptor: str = PY_SIGNATURE,
) -> Dispatch:
    declared = {
        method_descriptor(owner, name, descriptor)
        for owner, names in declares.items()
        for name in names
    }
    scanned = set(declares) | set(ancestors)
    return Dispatch(
        bodies={},
        declared=declared,
        subtypes={},
        ancestors=ancestors,
        scanned=scanned,
        lookup=lookup,  # type: ignore[arg-type]
        parents_unread=parents_unread,
    )


def _python(*parents: str) -> list[tuple[str, str, bool]]:
    """Written parents as the scanner writes them: the first is `superclass`, the rest
    are `interfaces`, in written order."""
    return [
        (parent, "extends" if position == 0 else "implements", True)
        for position, parent in enumerate(parents)
    ]


def test_c3_diamond_reaches_the_first_parent():
    """Review Focus 4: `class D(B, C)`, both overriding `m`: `D().m()` runs `B.m`. And
    where `B` does not override it, C3 reaches `C.m` before the shared `A.m`, which a
    depth-first walk would not."""
    hierarchy = {"p/D#": _python("p/B#", "p/C#"), "p/B#": _python("p/A#"), "p/C#": _python("p/A#")}
    both = _dispatch(declares={"p/A#": ["m"], "p/B#": ["m"], "p/C#": ["m"]}, ancestors=hierarchy)
    only_c = _dispatch(declares={"p/A#": ["m"], "p/B#": [], "p/C#": ["m"]}, ancestors=hierarchy)

    assert both.lookup_order("p/D#") == ["p/D#", "p/B#", "p/C#", "p/A#", OBJECT]
    assert both.resolve("p/D#", "m", PY_SIGNATURE) == ("p/B#", None)
    assert only_c.resolve("p/D#", "m", PY_SIGNATURE) == ("p/C#", None)


def test_c3_inconsistent_hierarchy_is_not_readable():
    """`class Z(X, Y)` with `X(A, B)` and `Y(B, A)` has no C3 order: Python refuses to
    create it. A method `Z` does not declare itself is not looked up anywhere, and the
    answer is `not_readable` (no declaring type, no unread type), never one of the two
    orders picked."""
    dispatch = _dispatch(
        declares={"p/A#": ["m"], "p/B#": ["m"], "p/Z#": ["own"]},
        ancestors={
            "p/X#": _python("p/A#", "p/B#"),
            "p/Y#": _python("p/B#", "p/A#"),
            "p/Z#": _python("p/X#", "p/Y#"),
        },
    )

    assert dispatch.lookup_order("p/Z#") == ["p/Z#"]
    assert dispatch.resolve("p/Z#", "m", PY_SIGNATURE) == (None, None)
    assert dispatch.resolve("p/Z#", "own", PY_SIGNATURE) == ("p/Z#", None)


def test_python_init_is_inherited():
    """Python's `__init__` (`<init>`) is found on a parent; the JVM's constructor is not
    inherited (JLS 8.8), and its rule is unchanged."""
    hierarchy = {"p/Child#": _python("p/Base#")}
    python = _dispatch(declares={"p/Base#": ["<init>"]}, ancestors=hierarchy)
    jvm = _dispatch(
        declares={"p/Base#": ["<init>"]}, ancestors=hierarchy, lookup="jvm", descriptor=VOID
    )

    assert python.resolve("p/Child#", "<init>", PY_SIGNATURE) == ("p/Base#", None)
    assert jvm.resolve("p/Child#", "<init>", VOID) == (None, None)


def test_an_unread_parent_ends_the_c3_order_with_external():
    """`class C(A, <a value>)`: the scanner wrote `A` and `parents_unread`. `A` is the
    first parent whatever the unread one is, so `A.m` is found; past it the order is
    not known (the unread parent may come before `A`'s parents), so the lookup answers
    `external` at `C`, never "no parents" (`not_readable`)."""
    hierarchy = {"p/C#": _python("p/A#"), "p/A#": _python("p/P#")}
    unread = frozenset({"p/C#"})
    on_a = _dispatch(
        declares={"p/A#": ["m"], "p/P#": []}, ancestors=hierarchy, parents_unread=unread
    )
    on_p = _dispatch(
        declares={"p/A#": [], "p/P#": ["m"]}, ancestors=hierarchy, parents_unread=unread
    )
    nowhere = _dispatch(
        declares={"p/C#": [], "p/A#": []},
        ancestors={"p/C#": _python("p/A#")},
        parents_unread=unread,
    )

    assert on_a.lookup_order("p/C#") == ["p/C#", "p/A#"]
    assert on_a.resolve("p/C#", "m", PY_SIGNATURE) == ("p/A#", None)
    assert on_p.resolve("p/C#", "m", PY_SIGNATURE) == (None, "p/C#")
    assert nowhere.resolve("p/C#", "m", PY_SIGNATURE) == (None, "p/C#")


def test_jvm_lookup_order_is_unchanged():
    """JVMS 5.4.3.3: the class, its whole superclass chain, then the superinterfaces,
    then the platform's root type. `tests/application/test_method_resolution.py`, the
    order's own tests, run unmodified against the same rule."""
    dispatch = _dispatch(
        declares={"p/A#": [], "p/B#": [], "p/C#": [], "p/I#": [], "p/J#": []},
        ancestors={
            "p/A#": [("p/B#", "extends", True), ("p/I#", "implements", True)],
            "p/B#": [("p/C#", "extends", True)],
            "p/I#": [("p/J#", "extends", True)],
        },
        lookup="jvm",
        descriptor=VOID,
    )

    assert dispatch.lookup_order("p/A#") == [
        "p/A#",
        "p/B#",
        "p/C#",
        "p/I#",
        "p/J#",
        "java/lang/Object#",
    ]


def test_the_lookup_rule_is_read_from_the_module_fact(tmp_path: Path):
    """End to end: the scanner writes the diamond, the module fact says `c3`, and the
    workspace's `Dispatch` answers by C3."""
    source = tmp_path / "src"
    (source / "app").mkdir(parents=True)
    (source / "app" / "shapes.py").write_text(
        "class A:\n    def m(self): return 1\n"
        "class B(A):\n    pass\n"
        "class C(A):\n    def m(self): return 3\n"
        "class D(B, C):\n    pass\n",
        encoding="utf-8",
    )
    facts = tmp_path / "facts"
    PythonScanner().scan(
        ScanRequest(
            module_id="shop",
            coordinates="shop",
            version="1",
            classes_dir=source,
            out_dir=facts,
        )
    )
    module = Document(
        document_id="module",
        relative_path="pyproject.toml",
        module_id="shop",
        language="python",
        sextant_version="0",
        fact_schema_version="0",
        scanner_id="module",
        content_hash="sha256:none",
        origin_entry="shop",
        origin_tier="module_output",
        redaction_set_hash="sha256:none",
    )
    write_fact_file(
        facts / "module.jsonl",
        module,
        [
            ModuleFact(
                document_id="module",
                module_id="shop",
                module_kind="pyproject",
                languages=["python"],
                source_roots=["src"],
                output_dirs=["src"],
                lookup="c3",
            )
        ],
    )
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(facts)
    dispatch = dispatch_of(workspace)
    workspace.close()

    assert dispatch.lookup == "c3"
    assert dispatch.resolve("app/shapes/D#", "m", PY_SIGNATURE) == ("app/shapes/C#", None)


def test_an_f_string_site_is_not_a_lambda_once_typeshed_names_str_format(tmp_path: Path):
    """Ruling R19(b): an f-string is a `dynamic` `builtins/str#format` site with no
    `implementation`. With typeshed read, `builtins/str#` is a type in the workspace (a
    `type_header`, fix round 2), and `lambda_edges` still holds no row for the site: a
    dynamic site is followed only through the body it creates, and an f-string creates
    none."""
    from sextant.application.resolve.call_edges import record_call_edges
    from sextant.domain.symbols import bare_descriptor

    source = tmp_path / "src"
    (source / "app").mkdir(parents=True)
    (source / "app" / "text.py").write_text(
        "import builtins\nTEXT = builtins.str\ndef label(n):\n    return f'item {n}'\n",
        encoding="utf-8",
    )
    facts = tmp_path / "facts"
    PythonScanner().scan(
        ScanRequest(
            module_id="shop", coordinates="shop", version="1", classes_dir=source, out_dir=facts
        )
    )
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(facts)
    record_call_edges(workspace)
    headers = {bare_descriptor(str(row["symbol"])) for row in workspace.query("type_headers")}
    sites = [
        row
        for row in workspace.query("call_sites")
        if bare_descriptor(str(row["caller"])).startswith("app/text#label")
    ]
    lambda_edges = workspace.query("lambda_edges")
    workspace.close()

    assert "builtins/str#" in headers
    assert [(row["owner"], row["name"], row["invoke_kind"]) for row in sites] == [
        ("builtins/str#", "format", "dynamic")
    ]
    assert lambda_edges == []


def test_c3_reads_library_parents_from_headers_and_ends_external_at_a_library_type():
    """Fix round 2 (ruling A): a library class is a `type_header`, so its parents are
    known and its methods are not. `class D(LibBase, Mine)`: C3 places the module's
    `Mine` after `LibBase` and `LibBase`'s own parent, and the lookup ends at `LibBase`,
    the first type it cannot read, with `external` — never `Mine.m` past it."""
    dispatch = Dispatch(
        bodies={},
        declared={method_descriptor("p/Mine#", "m", PY_SIGNATURE)},
        subtypes={},
        ancestors={
            "p/D#": _python("lib/LibBase#", "p/Mine#"),
            "lib/LibBase#": _python("lib/LibRoot#"),
        },
        scanned={"p/D#", "p/Mine#"},
        lookup="c3",
        headers=frozenset({"lib/LibBase#", "lib/LibRoot#"}),
    )

    assert dispatch.lookup_order("p/D#") == ["p/D#", "lib/LibBase#"]
    assert dispatch.resolve("p/D#", "m", PY_SIGNATURE) == (None, "lib/LibBase#")
    assert dispatch.resolve("p/Mine#", "m", PY_SIGNATURE) == ("p/Mine#", None)
