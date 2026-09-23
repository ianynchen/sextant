"""Shadow mode on the path it is actually used through (spec 2026-09-22 §7a, §3d).

`test_values.py` pins the RECORDER against hand-built facts, where every symbol is
spelled the way a real scan spells it and one arm exists per rule. This file pins the
three things that file structurally cannot:

* **the flag reaches `resolve`.** `--shadow` is five hops of a defaulted keyword — CLI,
  `api._analyze`, `_run_analyze`, `_analyzed`, the analyze stage — and a defaulted keyword
  dropped anywhere along it fails SILENTLY: `sextant module analyze --shadow` exits 0 with
  an empty table, and a reviewer reads "nothing would resolve" as good news. For a safety
  mechanism that is the worst failure available. Deleting `shadow=shadow` at
  `stages/analyze.py` left the whole of `tests/application` green before this file existed.
* **every asked position is answered.** `resolve_site` returns NO binding when no path
  answers every slot of the site at once, and it requires that coherence across slots
  nobody asked about — so one unrelated slot can delete a review row with nothing saying
  so. The invariant is asked == answered, and it was unpinned.
* **the ask reader still sees every position the shipped catalogs spell.** It is an audit
  of 101 files, not a grammar (`resolve/shadow.py`'s own caveat), so a catalog that invents
  a new spelling is silently not shadowed. The baseline below is the alarm.

Against the REAL fixture and the REAL shipped catalogs, because all three questions are
about what the product does with the files it ships.
"""

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from conftest import CATALOGS, FIXTURE, JAR
from sextant.application.ports.detector import ModuleModel, RepositoryModel
from sextant.application.ports.progress import NullProgress
from sextant.application.ports.scanner import ScanReport, ScanRequest
from sextant.application.resolve.effective_calls import effective_call_sites
from sextant.application.resolve.shadow import asks_of, positions_asked
from sextant.application.stages.analyze import analyze
from sextant.ingress.catalogs.yaml_source import YamlCatalogSource
from sextant.ingress.extract.jvm.scanner import AsmScanner
from sextant.storage.duckdb.workspace import DuckDbWorkspace

# The three tables §3c diffs, and the three §7a promises shadow mode leaves alone.
_PUBLISHED = ("endpoints", "endpoint_metadata", "shapes")


class _FakeDetector:
    """The hand-built-module idiom `test_analyze_ignore.py` already uses: this file has no
    business reading a `pom.xml`, and what it exercises starts below detection."""

    def __init__(self, module: ModuleModel) -> None:
        self._module = module

    def accepts(self, path: Path) -> bool:
        return True

    def detect(self, path: Path, allow_resolve: bool = False) -> RepositoryModel:
        return RepositoryModel(root=path, modules=(self._module,))


class _PreparedScanner:
    """A scanner that hands back the fixture's own already-scanned facts.

    It is a real seam rather than a shortcut: the stage discards the module's class facts
    and then asks the scanner to write them, and this writes exactly what `AsmScanner`
    wrote into the session fixture. Two analyses in one test would otherwise scan the
    fixture twice for no new evidence, and the capabilities are the REAL jar's, so every
    catalog the product would run here runs here."""

    def __init__(self, prepared: Path) -> None:
        self._prepared = prepared
        self._capabilities = AsmScanner(JAR).capabilities()

    def accepts(self, languages: set[str]) -> bool:
        return True

    def capabilities(self) -> set[str]:
        return set(self._capabilities)

    def rank(self) -> int:
        return 1

    def scan(self, request: ScanRequest) -> ScanReport:
        shutil.copytree(self._prepared, request.out_dir, dirs_exist_ok=True)
        return ScanReport(documents=0, facts=0, scanner_id="prepared")


def _module(root: Path) -> ModuleModel:
    return ModuleModel(
        module_id="com.acme:orders-service",
        coordinates="com.acme/orders-service",
        version="1.0.0",
        root=root,
        kind="service",
        languages=frozenset({"java"}),
        source_roots=(),
        output_dirs=(FIXTURE / "target" / "classes",),
    )


def _analyzed(tmp_path: Path, prepared: Path, shadow: bool) -> tuple[DuckDbWorkspace, int]:
    """One run of the ANALYZE STAGE — not of `resolve` — because the hop this pins is
    inside the stage. Returns the open workspace (the caller closes it) and the count the
    stage's own report carries, which is what a `--shadow` run prints."""
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    result = analyze(
        path=tmp_path,
        workspace=workspace,
        detectors=[_FakeDetector(_module(tmp_path))],
        scanners=[_PreparedScanner(prepared)],
        catalogs=YamlCatalogSource(CATALOGS),
        fact_root=tmp_path / "facts",
        progress=NullProgress(),
        shadow=shadow,
    )
    return workspace, result.report.value_resolutions


@dataclass(frozen=True)
class _Run:
    """One analysis: its shadow rows, the three published tables, and — for the shadow
    run — the positions the catalogs asked about, read off the same workspace."""

    rows: list[dict[str, Any]]
    published: dict[str, list[dict[str, object]]]
    asked: set[tuple[str, str, int, str]]
    reported: int


@pytest.fixture(scope="module")
def analyzed(tmp_path_factory: pytest.TempPathFactory, fixture_facts: Path) -> dict[bool, _Run]:
    """The fixture analysed twice through the stage, with the flag off and on. Built once
    for this file: the two runs are the comparison every test below reads, and running
    them per test would run them four times."""
    runs: dict[bool, _Run] = {}
    for shadow in (False, True):
        tmp_path = tmp_path_factory.mktemp(f"shadow_{shadow}")
        workspace, reported = _analyzed(tmp_path, fixture_facts, shadow)
        try:
            asks = [
                ask for catalog in YamlCatalogSource(CATALOGS).load() for ask in asks_of(catalog)
            ]
            runs[shadow] = _Run(
                rows=[dict(row) for row in workspace.query("value_resolutions")],
                published={name: workspace.query(name) for name in _PUBLISHED},
                asked={
                    (position.catalog, position.caller, position.ordinal, str(position.slot))
                    for position in positions_asked(effective_call_sites(workspace), asks)
                },
                reported=reported,
            )
        finally:
            workspace.close()
    return runs


def test_the_shadow_flag_reaches_the_walk_through_the_analyze_stage(analyzed):
    """**Spec §7a, on the path the feature is used through.** Both halves in one test,
    because either alone is satisfiable by a regression: a flag that never arrives leaves
    the table empty (and every "publishes nothing" assertion green), while a recorder that
    DERIVED its rows would fill the table and move `endpoints`.

    Measured: deleting `shadow=shadow` where the stage calls `resolve` left 122 of 122
    tests in this directory green before this test existed, and the user-visible result
    was `--shadow` exiting 0 with nothing recorded — silent, and reading as good news."""
    assert analyzed[False].rows == []
    assert analyzed[True].rows, "the --shadow flag did not reach resolve()"
    for name in _PUBLISHED:
        assert analyzed[True].published[name] == analyzed[False].published[name], name
    assert analyzed[False].published["endpoints"], "the fixture derived no endpoints at all"
    # The count the run REPORTS is the count it wrote. `--shadow` prints this number
    # beside the endpoint count for one reason: a flag that did not arrive prints 0, and
    # a reader who sees 0 asks a question instead of concluding one.
    assert analyzed[True].reported == len(analyzed[True].rows)
    assert analyzed[False].reported == 0


def test_every_position_a_catalog_asked_about_is_answered(analyzed):
    """**The invariant the whole mechanism rests on: asked equals answered.**

    A review list that quietly drops a position is worse than one that has none, because
    a reader takes the absence for "no catalog asks there". Two paths can drop one:
    `resolve_site` returns NO binding where no path answers every slot at once — and it
    demands that coherence across slots NOBODY ASKED ABOUT, so an unrelated argument can
    delete the row — and a slot the projected row does not have is skipped outright.
    Neither fires on this fixture, and an equality rather than a containment is what makes
    the day one starts a failure rather than a quietly smaller table."""
    recorded = {
        (row["catalog"], row["caller"], row["ordinal"], row["slot"]) for row in analyzed[True].rows
    }
    assert recorded == analyzed[True].asked
    assert analyzed[True].asked, "the shipped catalogs asked about nothing in the fixture"


# Every position each SHIPPED catalog spells, as `asks_of` reads it today:
# `(asks, slots)` — one ask per node that names a method and at least one slot, and the
# slots those nodes name between them. Both numbers, because they move independently: a
# new NODE changes the first, and a new SPELLING on a node that already asks changes only
# the second.
#
# **This is a baseline, and its job is to fail.** `asks_of` is an audit of the 101 shipped
# files rather than a reader of a grammar (`resolve/shadow.py` says so at length), so a
# catalog that spells a position a seventh way is silently not shadowed — a safety
# mechanism with a blind spot and no alarm. Recording the counts is the alarm: any catalog
# that gains, loses or re-spells a position fails here, and whoever changed it decides
# whether the reader needs to learn the spelling or the number needs updating.
#
# It deliberately does NOT assert that every `*_arg`-shaped key is a position this reader
# sees. Audited 2026-09-23: about fifty arg-shaped occurrences are legitimately not call
# positions — `spring-cloud-stream.yml`'s `payload_arg: [0, 1]` is a GENERIC TYPE-ARGUMENT
# index, and the same key name means a call slot under `wrappers:` and a type-argument
# index under `suffix:`, which the reader cannot tell apart. Such a rule would need a
# hand-maintained allowlist, which is the re-audit wearing a test's clothes. Classifying
# the keys belongs to Task 10, where the hop declarations become invalid and the
# classification has to be made anyway.
_ASKS_PER_CATALOG = {
    "apache-httpclient": (52, 52),
    "aws-sqs-sdk": (2, 2),
    "google-pubsub-client": (1, 1),
    "google-pubsub-publisher": (2, 2),
    "google-pubsub-subscriber": (2, 3),
    "jakarta-jms": (36, 36),
    "jakarta-servlet": (2, 2),
    "jakarta-websocket-client": (12, 12),
    "jakarta-websocket-programmatic": (1, 1),
    "javalin": (19, 19),
    "javalin-apibuilder": (26, 39),
    "javax-jms": (36, 36),
    "javax-servlet": (2, 2),
    "jdk-httpclient": (9, 10),
    "kafka-clients": (3, 4),
    "kafka-consumer": (12, 12),
    "kafka-streams": (22, 22),
    "kafka-streams-sink": (2, 2),
    "kafka-streams-topology": (5, 5),
    "ktor-routing": (33, 71),
    "okhttp": (5, 6),
    "pekko-connectors-kafka": (15, 15),
    "spring-cloud-gateway": (14, 20),
    "spring-cloud-gateway-outbound": (4, 4),
    "spring-integration-amqp": (38, 38),
    "spring-integration-kafka": (41, 41),
    "spring-integration-pubsub": (25, 25),
    "spring-jms-template": (8, 11),
    "spring-kafka-message": (3, 3),
    "spring-kafka-replying": (2, 3),
    "spring-kafka-template": (11, 16),
    "spring-mvc-router": (99, 167),
    "spring-pubsub": (12, 17),
    "spring-rabbit-template": (12, 16),
    "spring-restclient": (5, 5),
    "spring-resttemplate": (25, 64),
    "spring-sqs-template": (5, 7),
    "spring-sqs-template-receive": (16, 16),
    "spring-stomp-client": (12, 12),
    "spring-stomp-endpoint": (1, 1),
    "spring-stomp-template": (11, 15),
    "spring-webclient": (8, 8),
    "spring-webflux-router": (110, 188),
    "spring-websocket": (1, 1),
    "spring-websocket-client": (4, 4),
    "spring-ws-template": (6, 6),
    "temporal-untyped": (3, 3),
    "vertx-eventbus": (12, 20),
    "vertx-eventbus-chain": (7, 7),
    "vertx-eventbus-mutiny": (8, 14),
}


def test_the_ask_reader_still_sees_every_position_the_shipped_catalogs_spell():
    """The baseline above, asserted over ALL the shipped catalogs and not only the fifty
    that ask — a catalog that asks about nothing today and gains a position tomorrow is
    exactly the case a dict of non-zero entries would miss, so the zero ones are checked
    too."""
    counted = {
        catalog.id: (len(asks), sum(len(ask.slots) for ask in asks))
        for catalog in YamlCatalogSource(CATALOGS).load()
        if (asks := asks_of(catalog))
    }
    assert counted == _ASKS_PER_CATALOG
    assert sum(asks for asks, _ in counted.values()) == 802
