"""What a call REACHES, where the call is a terminal (D00 §4's `terminal_kind`, F7 §8.2).

D00 declared this set and nothing produced one for two phases, and its own note said why:
three members "need framework knowledge no pass has applied at a call site — a data-access
call is `persistence` only to something that knows the callee is one". The knowledge is
catalog data now, so the classification is read rather than guessed.

**Everything here is invented** — invented owner types, an invented scan annotation, an
invented repository base — for the reason every engine test in this directory gives: a rule
read from catalog data is only proved to be read from catalog data if the data is not the
real spellings. `kind` and `target` are the exception, being written into closed columns.
The shipped catalogs' live answers are measured on three corpora and recorded in
COVERAGE §3a-viii.

## The two rules a name match would have broken

Neither `*Mapper` nor `*Repository` appears anywhere in the mechanism, and both would have
been the easy way to write it. `test_a_scanned_package_is_read_from_the_annotation` and
`test_a_supertype_is_matched_through_a_scanned_intermediate` are the cases that fail under
a name rule and pass under the framework's own.
"""

from pathlib import Path

import pytest
from test_shapes import _MODULE, _document, _type, _write

from sextant.application.ports.catalogs import Catalog, CatalogError
from sextant.application.resolve.terminals import TerminalRules, classify
from sextant.domain.facts import AnnotationFact, AnnotationUse
from sextant.storage.duckdb.workspace import DuckDbWorkspace

STORE = "com.acme.store.Store"
CACHE = "com.acme.store.Cache"
BASE_REPO = "com.acme.store.BaseRepository"
SCAN = "com.acme.store.StoreScan"


def _catalog(*rules: dict) -> Catalog:
    return Catalog(
        id="invented-store",
        style="annotation_driven",
        protocol="http",
        direction="inbound",
        requires=(),
        matches={},
        source=Path("tests/invented.yml"),
        terminals=list(rules),
    )


def _workspace(tmp_path: Path, facts: list) -> DuckDbWorkspace:
    _write(tmp_path / "facts" / "doc.jsonl", _document("doc", "Store.java"), facts)
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    return workspace


def _implements(document_id: str, owner: str, *interfaces: str) -> dict:
    fact = _type(document_id, owner, "interface")
    fact["interfaces"] = [_MODULE + name for name in interfaces]
    return fact


def _superclass(document_id: str, owner: str, parent: str) -> dict:
    """`owner extends parent`, the other half of the ancestry the walk reads. Its own
    helper rather than a flag on `_implements` because the two facts carry different
    fields, and 5.4.3.3 treats them differently."""
    fact = _type(document_id, owner)
    fact["superclass"] = _MODULE + parent
    return fact


def _annotation(target: str, annotation: str, args: dict) -> dict:
    return AnnotationFact(
        document_id="doc",
        target=_MODULE + target,
        retention="runtime",
        use=AnnotationUse(annotation=annotation.replace(".", "/") + "#", args=args),
    ).model_dump(mode="json")


def test_an_owner_type_names_the_kind_and_the_store(tmp_path: Path):
    """The simplest route (§10's positive): the call lands on a type a catalog names.

    `target` is what makes "does this hit a database or a cache" answerable at all, and it
    is a sub-field rather than two kinds so that splitting them later is a rendering
    choice rather than a re-index (D00 §4).
    """
    workspace = _workspace(tmp_path, [])
    rules = TerminalRules(
        workspace,
        [
            _catalog(
                {"owner": STORE, "kind": "persistence", "target": "database"},
                {"owner": CACHE, "kind": "persistence", "target": "cache"},
            )
        ],
    )
    workspace.close()

    assert classify(rules, "com/acme/store/Store#find(sig_1).", None) == {
        "terminal_kind": "persistence",
        "target_kind": "database",
    }
    assert classify(rules, "com/acme/store/Cache#get(sig_1).", None) == {
        "terminal_kind": "persistence",
        "target_kind": "cache",
    }


def test_an_edge_that_is_not_a_terminal_is_not_classified(tmp_path: Path):
    """The near-miss that separates the two NULLs. An edge whose callee's body was read is
    expanded by the walk, so there is nothing to classify — and `unresolved` there would
    say a terminal was examined and could not be named, which is a different and false
    statement."""
    workspace = _workspace(tmp_path, [])
    rules = TerminalRules(workspace, [_catalog({"owner": STORE, "kind": "persistence"})])
    workspace.close()

    assert classify(rules, "com/acme/store/Store#find(sig_1).", "com/acme/store/Store#find") == {
        "terminal_kind": None,
        "target_kind": None,
    }


def test_an_unclassified_terminal_says_so_rather_than_going_quiet(tmp_path: Path):
    """A terminal no catalog claims reads `unresolved`, not NULL.

    On the measured corpora that is ~95% of them — `StringBuilder`, `Object`, `List` — and
    that is the point rather than a shortfall: they are ordinary library calls, and
    `unresolved` says *this is a terminal we looked at and could not classify*.
    """
    workspace = _workspace(tmp_path, [])
    rules = TerminalRules(workspace, [_catalog({"owner": STORE, "kind": "persistence"})])
    workspace.close()

    assert classify(rules, "java/lang/StringBuilder#append(sig_1).", None) == {
        "terminal_kind": "unresolved",
        "target_kind": None,
    }


def test_a_scanned_package_is_read_from_the_annotation(tmp_path: Path):
    """The route MyBatis needs, and the one a name match would have faked.

    `mall-admin`'s mapper interfaces carry **no annotation at all** — `@MapperScan` on a
    config class is how MyBatis registers them, and its `value` is the package list. So the
    evidence is the scan's own argument, read here, and a type inside a scanned package
    qualifies however it is named.

    `com/acme/other/Thing` is the control: same module, not in a scanned package.
    """
    facts = [_annotation("com/acme/config/Config#", SCAN, {"value": ["com.acme.mapper"]})]
    workspace = _workspace(tmp_path, facts)
    rules = TerminalRules(
        workspace,
        [
            _catalog(
                {
                    "scanned_by": SCAN,
                    "packages_from": "value",
                    "kind": "persistence",
                    "target": "database",
                }
            )
        ],
    )
    workspace.close()

    assert classify(rules, "com/acme/mapper/AnythingAtAll#select(sig_1).", None) == {
        "terminal_kind": "persistence",
        "target_kind": "database",
    }
    assert classify(rules, "com/acme/other/Thing#select(sig_1).", None)["terminal_kind"] == (
        "unresolved"
    )


def test_a_scanned_package_does_not_claim_a_neighbour_that_starts_the_same_way(
    tmp_path: Path,
):
    """`com.acme.mapper` must not claim `com.acme.mappers`. A scan names a package and
    everything under it, never a sibling whose name merely shares a prefix — which a bare
    `startswith` would take."""
    facts = [_annotation("com/acme/config/Config#", SCAN, {"value": ["com.acme.mapper"]})]
    workspace = _workspace(tmp_path, facts)
    rules = TerminalRules(
        workspace, [_catalog({"scanned_by": SCAN, "kind": "persistence", "target": "database"})]
    )
    workspace.close()

    assert classify(rules, "com/acme/mappers/Other#select(sig_1).", None)["terminal_kind"] == (
        "unresolved"
    )
    # And the package's own subpackages ARE claimed, which is what a scan means.
    assert (
        classify(rules, "com/acme/mapper/deep/Inner#select(sig_1).", None)["terminal_kind"]
        == "persistence"
    )


def test_a_module_with_no_scan_annotation_gets_nothing_from_that_rule(tmp_path: Path):
    """The near-miss for the scan route: the rule contributes packages only where the
    annotation is actually written. A module that scans nothing classifies nothing by this
    route, rather than falling back to a convention about what its packages are called."""
    workspace = _workspace(tmp_path, [])
    rules = TerminalRules(
        workspace, [_catalog({"scanned_by": SCAN, "kind": "persistence", "target": "database"})]
    )
    workspace.close()

    assert classify(rules, "com/acme/mapper/Anything#select(sig_1).", None)["terminal_kind"] == (
        "unresolved"
    )


def test_a_supertype_is_matched_through_a_scanned_intermediate(tmp_path: Path):
    """The route Spring Data needs, and the transitivity that earns its keep.

    `OrderRepository` extends `BagRelationships`, which extends the declared base — the
    shape `jhipster-sample-app` has, where a user-defined interface sits between the
    repository and the framework's own. A direct-parent-only rule would miss it.
    """
    facts = [
        _implements("doc", "com/acme/store/OrderRepository#", "com/acme/store/BagRelationships#"),
        _implements("doc", "com/acme/store/BagRelationships#", "com/acme/store/BaseRepository#"),
    ]
    workspace = _workspace(tmp_path, facts)
    rules = TerminalRules(
        workspace,
        [_catalog({"supertype": BASE_REPO, "kind": "persistence", "target": "database"})],
    )
    workspace.close()

    assert classify(rules, "com/acme/store/OrderRepository#findAll(sig_1).", None) == {
        "terminal_kind": "persistence",
        "target_kind": "database",
    }


def test_a_supertype_rule_may_name_several_bases(tmp_path: Path):
    """The LIST form of `supertype:` (§3.1), which is the form `spring-web.yml` actually
    ships — all nine Spring Data bases in one rule — and which no test reached (W30
    review). Only `JpaRepository` is ever hit on the corpora, so the other eight are
    unmeasured; that the list form is READ at all is what this pins.
    """
    facts = [
        _implements("doc", "com/acme/store/Mongo#", "com/acme/store/MongoBase#"),
        _implements("doc", "com/acme/store/Jpa#", "com/acme/store/BaseRepository#"),
    ]
    workspace = _workspace(tmp_path, facts)
    rules = TerminalRules(
        workspace,
        [
            _catalog(
                {
                    "supertype": [BASE_REPO, "com.acme.store.MongoBase"],
                    "kind": "persistence",
                    "target": "database",
                }
            )
        ],
    )
    workspace.close()

    for owner in ("Mongo", "Jpa"):
        assert classify(rules, f"com/acme/store/{owner}#find(sig_1).", None) == {
            "terminal_kind": "persistence",
            "target_kind": "database",
        }


def test_the_supertype_walk_stops_at_a_type_this_workspace_did_not_scan(tmp_path: Path):
    """The boundary that decides what a catalog must name, and it cost a measurement to
    find: naming only the framework's BASE interface classified 2 of jhipster's 75.

    The walk follows the `superclasses`/`implementations` facts, and an UNSCANNED type has
    none of its own — so the chain ends there and never sees what that type extends. A
    catalog must therefore name the level a USER actually writes: `JpaRepository`, not
    `Repository`.

    **Both halves in one test, because the negative alone proves nothing.** `OrderRepo`
    reaches the declared base through an unscanned intermediate and must NOT classify;
    `AuditRepo` reaches it through a scanned one and must. The first assertion on its own
    passed with the entire supertype route deleted — nothing in it linked the intermediate
    to the base either way, so it was measuring the absence of a fact, not the stop.
    """
    facts = [
        # Unscanned intermediate: `FrameworkRepo` declares nothing here.
        _implements("doc", "com/acme/store/OrderRepo#", "com/acme/store/FrameworkRepo#"),
        # Scanned intermediate: the same shape, one fact further.
        _implements("doc", "com/acme/store/AuditRepo#", "com/acme/store/Scanned#"),
        _implements("doc", "com/acme/store/Scanned#", "com/acme/store/BaseRepository#"),
    ]
    workspace = _workspace(tmp_path, facts)
    rules = TerminalRules(
        workspace,
        [_catalog({"supertype": BASE_REPO, "kind": "persistence", "target": "database"})],
    )
    workspace.close()

    assert classify(rules, "com/acme/store/OrderRepo#findAll(sig_1).", None)["terminal_kind"] == (
        "unresolved"
    )
    assert classify(rules, "com/acme/store/AuditRepo#findAll(sig_1).", None)["terminal_kind"] == (
        "persistence"
    )


def test_two_declared_supertypes_resolve_in_the_jvm_search_order(tmp_path: Path):
    """NFR-1, and it was a coin toss the hash seed decided.

    A type reaching two declared supertypes with DIFFERENT answers used to be resolved by
    iterating a `set`: six `PYTHONHASHSEED` values produced `database` three times and
    `cache` three times for one input. The order is JVMS 5.4.3.3's — the superclass chain
    to exhaustion, then the interfaces — so a superclass's answer wins over an interface's
    however the facts were written down.

    Today's catalog cannot reach it: all nine Spring Data bases carry one answer. The
    first rule that ships a different `target` can, and this file's own comments already
    name the candidates.
    """
    facts = [
        _superclass("doc", "com/acme/store/Repo#", "com/acme/store/Cached#"),
        _implements("doc", "com/acme/store/Repo#", "com/acme/store/Stored#"),
    ]
    workspace = _workspace(tmp_path, facts)
    rules = TerminalRules(
        workspace,
        [
            _catalog(
                {"supertype": "com.acme.store.Stored", "kind": "persistence", "target": "database"},
                {"supertype": "com.acme.store.Cached", "kind": "persistence", "target": "cache"},
            )
        ],
    )
    workspace.close()

    # The SUPERCLASS, not the interface — 5.4.3.3 exhausts the class chain first.
    assert classify(rules, "com/acme/store/Repo#get(sig_1).", None)["target_kind"] == "cache"


def test_an_owner_rule_wins_over_a_scanned_package(tmp_path: Path):
    """Routes are tried most specific first. A type named outright is a stronger statement
    than membership of a scanned package, so a catalog can carve one type out of a scan
    without the scan overriding it."""
    facts = [_annotation("com/acme/config/Config#", SCAN, {"value": ["com.acme.mapper"]})]
    workspace = _workspace(tmp_path, facts)
    rules = TerminalRules(
        workspace,
        [
            _catalog(
                {"owner": "com.acme.mapper.Special", "kind": "persistence", "target": "cache"},
                {"scanned_by": SCAN, "kind": "persistence", "target": "database"},
            )
        ],
    )
    workspace.close()

    assert classify(rules, "com/acme/mapper/Special#get(sig_1).", None)["target_kind"] == "cache"
    assert classify(rules, "com/acme/mapper/Plain#get(sig_1).", None)["target_kind"] == "database"


def test_no_catalog_declares_terminals_and_every_terminal_is_unresolved(tmp_path: Path):
    """The whole mechanism is catalog-driven: with nothing declared, every terminal reads
    what it read before this existed. The classification comes from the data, never from
    the engine knowing a framework."""
    workspace = _workspace(tmp_path, [])
    rules = TerminalRules(workspace, [_catalog()])
    workspace.close()

    assert classify(rules, "com/acme/store/Store#find(sig_1).", None)["terminal_kind"] == (
        "unresolved"
    )


def test_the_rules_read_a_json_shaped_annotation_argument(tmp_path: Path):
    """A scan naming ONE package writes a bare string where naming several writes a list,
    and both are ordinary. Reading only the list form would classify nothing for the
    commonest case."""
    facts = [_annotation("com/acme/config/Config#", SCAN, {"value": "com.acme.solo"})]
    workspace = _workspace(tmp_path, facts)
    rules = TerminalRules(
        workspace, [_catalog({"scanned_by": SCAN, "kind": "persistence", "target": "database"})]
    )
    workspace.close()

    assert classify(rules, "com/acme/solo/Mapper#get(sig_1).", None)["terminal_kind"] == (
        "persistence"
    )


# ---------------------------------------------------------------------------
# What the CATALOG LOADER refuses (D02 §2j) — the half `classify` cannot check,
# because by the time a rule reaches this module it has already been believed.
# ---------------------------------------------------------------------------


def _catalog_file(tmp_path: Path, terminals: str) -> Path:
    """One minimal loadable catalog with the `terminals` block under test."""
    path = tmp_path / "invented.yml"
    path.write_text(
        "id: invented\nstyle: annotation_driven\nprotocol: http\ndirection: inbound\n"
        "matches: {}\n" + terminals,
        encoding="utf-8",
    )
    return path


def _load(tmp_path: Path, terminals: str) -> list:
    from sextant.ingress.catalogs.yaml_source import YamlCatalogSource

    _catalog_file(tmp_path, terminals)
    return YamlCatalogSource(tmp_path).load()


def test_a_terminal_kind_outside_the_closed_set_is_refused_at_load(tmp_path: Path):
    """`kind` and `target` are written straight into closed columns of `call_edges` and
    out into the exported bundle, so they take the check `protocol` and `direction` take.

    Unchecked, `kind: persistance` reached the column, the rendered `Reaches` cell and
    the bundle with no error anywhere — the catalog file being the last place naming it
    is cheap (W30 review).
    """
    with pytest.raises(CatalogError, match="persistance"):
        _load(tmp_path, "terminals:\n  - {owner: a.B, kind: persistance}\n")

    with pytest.raises(CatalogError, match="databse"):
        _load(tmp_path, "terminals:\n  - {owner: a.B, kind: persistence, target: databse}\n")


def test_a_terminal_rule_naming_no_route_or_two_is_refused_at_load(tmp_path: Path):
    """Exactly one of `owner`, `supertype`, `scanned_by` (D02 §2j).

    A rule naming NONE matched nothing and said so nowhere; a rule naming two says two
    different things about one answer. A missing `kind` used to raise a bare `KeyError`
    at resolve time with no catalog path in the message.
    """
    with pytest.raises(CatalogError, match="none"):
        _load(tmp_path, "terminals:\n  - {kind: persistence}\n")

    with pytest.raises(CatalogError, match="owner, supertype"):
        _load(tmp_path, "terminals:\n  - {owner: a.B, supertype: c.D, kind: persistence}\n")

    with pytest.raises(CatalogError, match="kind"):
        _load(tmp_path, "terminals:\n  - {owner: a.B}\n")


def test_the_shipped_rules_load_and_every_one_is_persistence(tmp_path: Path):
    """The shipped block, read off the file — and the measured claim that only two of
    `TerminalKind`'s eight members have a producer (`OI-74`) rests on this.

    What the twelve rules NAME is not checkable offline; a typo in
    `org.mybatis.spring.annotation.MapperScan` is inert rather than invalid, and the
    corpus pins' `terminal_kinds` are what catch it (COVERAGE §3a-viii).
    """
    from sextant.ingress.catalogs.yaml_source import YamlCatalogSource
    from sextant.resources import catalogs_dir

    rules = [rule for c in YamlCatalogSource(catalogs_dir()).load() for rule in c.terminals]

    assert len(rules) == 12
    assert {str(rule["kind"]) for rule in rules} == {"persistence"}
    assert {str(rule.get("target")) for rule in rules} == {"database", "cache"}
