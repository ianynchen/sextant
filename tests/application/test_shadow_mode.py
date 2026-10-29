"""Shadow mode on the path it is actually used through (spec 2026-09-22 §7a, §3d).

`test_values.py` pins the RECORDER against hand-built facts, where every symbol is
spelled the way a real scan spells it and one arm exists per rule. This file pins the
three things that file structurally cannot:

* **the flag reaches `resolve`, at every hop.** `--shadow` is five hops of a defaulted
  keyword — CLI, `api._analyze`, `_run_analyze`, `_analyzed`, the analyze stage — and a
  defaulted keyword dropped anywhere along it fails SILENTLY: `sextant module analyze
  --shadow` exits 0 with an empty table, and a reviewer reads "nothing would resolve" as
  good news. For a safety mechanism that is the worst failure available. Two tests, because
  one road does not cover the other: the stage test builds the stage itself and would stay
  green with the facade's own hop deleted (measured, 40 passed), so the facade is driven
  separately over a tiny fixture.
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

from fixture_build import compile_fixture
from sextant import api
from sextant.application.ports.catalogs import Catalog
from sextant.application.ports.detector import ModuleModel, RepositoryModel
from sextant.application.ports.progress import NullProgress
from sextant.application.ports.scanner import ScanReport, ScanRequest
from sextant.application.resolve.call_edges import record_call_edges
from sextant.application.resolve.effective_calls import effective_call_sites
from sextant.application.resolve.return_flow import record_return_flows
from sextant.application.resolve.shadow import (
    _every_identity,
    asks_of,
    positions_asked,
    record_value_resolutions,
)
from sextant.application.stages.analyze import analyze
from sextant.domain.closed_sets import OriginTier
from sextant.domain.factfile import write_fact_file
from sextant.domain.facts import CallArgument, CallSiteFact, CallTarget, Document
from sextant.ingress.catalogs.yaml_source import YamlCatalogSource
from sextant.ingress.extract.jvm.scanner import AsmScanner
from sextant.resources import catalogs_dir, extractor_jar
from sextant.storage.duckdb.workspace import DuckDbWorkspace

# Derived here rather than imported from `conftest`, which is the pattern every other
# module in this directory follows (`test_pipeline.py`): `tests/architecture/conftest.py`
# puts its OWN directory on `sys.path[0]`, so `from conftest import ...` resolves to
# whichever conftest that leaves first on the path — and `pytest tests/application
# tests/architecture` fails collection outright. The full-suite run and the reverse order
# both hide it.
REPO = Path(__file__).parents[2]
FIXTURE = REPO / "fixtures" / "orders-service"
JAR = extractor_jar()
CATALOGS = catalogs_dir()

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
# sees. Most of them are not call positions at all — `wrappers[].payload_arg` and
# `suffix[].payload_arg` are GENERIC TYPE-ARGUMENT indices, `serialization.name_from[].arg`
# and `annotation_arg` are attribute NAMES — and `resolve/shadow.py`'s own
# *Which blocks are read, and which are refused* section enumerates every one of them with
# the consuming line that settles it. That section is where those counts live; this comment
# cites it rather than keeping a second copy, because the copy it used to keep was stale and
# its example was false. Such a rule would need a hand-maintained allowlist, which is the
# re-audit wearing a test's clothes. Classifying the keys belongs to Task 10, where the hop
# declarations become invalid and the classification has to be made anyway.
#
# **Three entries moved on 2026-09-23, and the alarm is what said so.** `kafka-clients`
# (3, 4) -> (5, 8), `spring-kafka-replying` (2, 3) -> (4, 7) and `spring-kafka-template`
# (11, 16) -> (13, 20): each gained two `record_wrappers` rows naming one `ProducerRecord`
# constructor by `descriptor`, and each row is a node with two `_ctor_arg` positions
# (+2 asks, +4 slots). Nothing was re-spelled and no reader learned anything new — the
# `<init>` arm already read this shape. The rows exist because `payload_ctor_arg: "last"`
# read the record's HEADERS on the two overloads whose final parameter is
# `Iterable<Header>` (`scripts/probes/cp34_producer_record_ctors.md`, kafka-clients 3.6.2).
# **Two entries moved on 2026-10-16, and this alarm is what said so.** `jakarta-jms`
# (36, 36) -> (28, 28) and `javax-jms` the same: eight `channel_via` entries came off each
# catalog's `Topic`-typed rows, where they declared `createQueue` as the source of the
# destination. MEASURED, `javap -cp jakarta.jms-api-3.1.0.jar`: `jakarta.jms.Queue` and
# `jakarta.jms.Topic` both `extends jakarta.jms.Destination` and NEITHER extends the other,
# so a `Queue` cannot stand where a `Topic` is declared and
# `createDurableConsumer`/`createDurableSubscriber`/`createSharedConsumer`/
# `createSharedDurableConsumer` could never have been fed by `createQueue` in code that
# compiles. The entries were dead weight that no real call could reach, and Task 8's type
# gate is what surfaced them: the gate refuses a producer whose return type cannot be the
# declared parameter type, which made these sixteen rows visible as refusals rather than
# as rows nobody had looked at. No published row moves — a call that cannot compile
# produced none.
# **`spring-integration-kafka` moved 41 -> 43 on 2026-10-17** (Task 9, carry-forward (b)):
# its two `messageDrivenChannelAdapter` rows whose descriptor takes a `Pattern` gained a
# `channel_via` naming `Pattern.compile`, one ask each. The catalog had stated `Pattern`
# subscriptions as a BOUNDARY while `kafka-consumer.yml` and `spring-kafka.yml` both read
# the same shape verbatim — "a topic pattern lands on `path` verbatim, never expanded into
# real topic names" — so the two rows were aligned with the rule rather than the rule bent
# to them. One fixture row converts, `unresolved` -> `resolved`; the other row's overload
# no fixture exercises.
# **`ktor-routing` moved (33, 71) -> (49, 111) on 2026-10-26** (spec 2026-10-26 §3b): sixteen
# verb rules for Ktor's `webSocket`, `webSocketRaw` and `sse` routes and their `$default`
# bridges, one ask each — `receiver_arg` and `handler_arg` on every one, `path_arg` on the
# eight that carry a path (+16 asks, +40 slots). Nothing was re-spelled; the reader reads
# these positions as it reads `get`'s.
# **`ktor-client` joined at (3, 4) on 2026-10-26** (spec 2026-10-26 §3c), a new catalog rather
# than a moved one: its three steps each ask for one position — `url`'s address (`arg1`),
# `setMethod`'s verb and `setBody`'s body (`arg0` each) — and `url` names a fourth slot,
# `receiver_arg: 0`, the builder it extends.
# **`ktor-client` moved (3, 4) -> (7, 8) on 2026-10-26** (spec 2026-10-26 §3g item 3): its
# `client_base` key spells four calls, each one position — the three ladder rungs'
# `block_arg` (the configuration block of `HttpClient`, `config` and `defaultRequest`) and
# the setter's `value_arg` (`DefaultRequestBuilder.url`'s address). The reader reads them by
# shape, as it reads every `*_arg`; nothing else in the catalog moved.
# **`ktor-client` moved (7, 8) -> (8, 9) on 2026-10-26** (Task 10): one more ladder rung, the
# engine-less `HttpClient { … }` factory (CP-54 rows 87-88), whose `block_arg` is one more
# position read the same way.
# **`ktor-client` moved (8, 9) -> (10, 11) on 2026-10-26** (Task 10 fix round 1): two
# `may_set_base` entries name an argument position (`install`'s and `install$default`'s
# plugin, `arg: 0` and `arg: 1`), read by shape as every argument position is.
# **`ktor-websocket-client` joined at (23, 23) and `ktor-sse-client` at (39, 39) on 2026-10-26**
# (spec 2026-10-26 §3d), two new catalogs rather than moved ones: one address position per
# `methods` row — `channel_arg` on the sixteen WebSocket rows, `url_arg` on the thirty-two SSE
# rows — plus the seven positions of the `client_base` they take from `client-models/ktor.yml`
# (four rungs' `block_arg`, the setter's `value_arg`, two `may_set_base` `arg`s), exactly
# `ktor-client`'s seven. `address_parts` is not an ask: it reads whether a part is GIVEN, never
# its value. `ktor-client` is unchanged at (10, 11) although its ladder moved into the model,
# because the reader reads the merged catalog.
# **`quartz` joined at (3, 4) on 2026-10-29** (Quartz spec §3d), a new catalog: its three
# chain steps' and roots' `argN` captures read by shape — `withIdentity`'s `name: arg0` and
# `group: arg1`, `withSchedule`'s `schedule: arg0` — plus `literal_expression`'s `arg: 0`.
_ASKS_PER_CATALOG = {
    "apache-httpclient": (52, 52),
    "aws-sqs-sdk": (2, 2),
    "google-pubsub-client": (1, 1),
    "google-pubsub-publisher": (2, 2),
    "google-pubsub-subscriber": (2, 3),
    "jakarta-jms": (28, 28),
    "jakarta-servlet": (2, 2),
    "jakarta-websocket-client": (12, 12),
    "jakarta-websocket-programmatic": (1, 1),
    "javalin": (19, 19),
    "javalin-apibuilder": (26, 39),
    "javax-jms": (28, 28),
    "javax-servlet": (2, 2),
    "jdk-httpclient": (9, 10),
    "kafka-clients": (5, 8),
    "kafka-consumer": (12, 12),
    "kafka-streams": (22, 22),
    "kafka-streams-sink": (2, 2),
    "kafka-streams-topology": (5, 5),
    "ktor-client": (10, 11),
    "ktor-routing": (49, 111),
    "ktor-sse-client": (39, 39),
    "ktor-websocket-client": (23, 23),
    "okhttp": (5, 6),
    "pekko-connectors-kafka": (15, 15),
    "quartz": (3, 4),
    "spring-cloud-gateway": (14, 20),
    "spring-cloud-gateway-outbound": (4, 4),
    "spring-integration-amqp": (38, 38),
    "spring-integration-kafka": (43, 43),
    "spring-integration-pubsub": (25, 25),
    "spring-jms-template": (8, 11),
    "spring-kafka-message": (3, 3),
    "spring-kafka-replying": (4, 7),
    "spring-kafka-template": (13, 20),
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
    # `spring-web`'s five entries are its `parse_calls` block, not `matches` — the one
    # catalog whose positions the reader reaches outside `matches` (widened 2026-09-23).
    "spring-web": (5, 8),
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
    """The baseline above, asserted as an EQUALITY of dicts rather than a check of the
    fifty-one entries it holds — which is what covers the FIFTY catalogs that ask about
    nothing today, without storing a `(0, 0)` row for each of them. One that gains its
    first position adds a key this dict does not have; one that loses its last removes a
    key it does; either way the dicts differ and the test fails."""
    counted = {
        catalog.id: (len(asks), sum(len(ask.slots) for ask in asks))
        for catalog in YamlCatalogSource(CATALOGS).load()
        if (asks := asks_of(catalog))
    }
    assert counted == _ASKS_PER_CATALOG
    # 807 until 2026-09-23; +6 for the six `record_wrappers` rows the comment above
    # accounts for, three catalogs at two rows each. **-16 on 2026-10-16**: eight
    # `createQueue` entries off each JMS catalog's `Topic`-typed rows, for the reason the
    # comment above `_ASKS_PER_CATALOG` measures. **+2 on 2026-10-17**: the two
    # `spring-integration-kafka` `Pattern` rows, same comment. **+16 on 2026-10-26**: the
    # `ktor-routing` WebSocket and SSE rules, same comment. **+3 on 2026-10-26**: the new
    # `ktor-client` catalog's three steps, same comment. **+4 on 2026-10-26**: its
    # `client_base` ladder and setter, same comment. **+1 on 2026-10-26**: the engine-less
    # factory's rung, same comment. **+2 on 2026-10-26**: its two `may_set_base` plugin
    # positions, same comment. **+62 on 2026-10-26**: the two new Ktor WebSocket and SSE
    # client catalogs, 23 and 39, same comment. **+3 on 2026-10-29**: the new `quartz`
    # catalog, same comment.
    assert sum(asks for asks, _ in counted.values()) == 890


# A tiny compiled Maven fixture — two classes, thirteen endpoints, 0.6s through the whole
# facade. `orders-service` would prove the same thing and cost eight times as much: what
# the test below pins is a keyword argument's journey, not a corpus.
_FACADE_FIXTURE = FIXTURE.parent / "orders-javalin"


def test_the_shadow_flag_survives_the_facade_and_not_only_the_stage(tmp_path: Path):
    """**The hops ABOVE the stage, which the test at the top of this file does not reach.**

    `--shadow` crosses `api._analyze` -> `_run_analyze` -> `_analyzed` -> the stage, each a
    defaulted keyword. Deleting `shadow=shadow` at the FIRST of those left every test in
    this file and in `test_values.py` green — 40 passed — because the stage test builds
    the stage itself and never travels that road. The CLI's own printed count is a
    mitigation for the same failure, not a test of it.

    So this drives `api._analyze`, which is what `sextant module analyze` calls, and asserts
    the two things a reviewer acts on: rows were recorded, and the number the run REPORTS is
    the number it wrote. A flag lost at any hop leaves both at zero."""
    compile_fixture(_FACADE_FIXTURE)
    result, multi_module = api._analyze(
        _FACADE_FIXTURE, workspace_dir=tmp_path, allow_resolve=False, shadow=True
    )
    assert not multi_module
    workspace = DuckDbWorkspace(tmp_path / "workspace.duckdb")
    try:
        recorded = workspace.query("value_resolutions")
    finally:
        workspace.close()
    assert recorded, "the --shadow flag did not survive the facade"
    assert result.value_resolutions == len(recorded)


def test_the_facade_records_nothing_without_the_flag(tmp_path: Path):
    """The other direction, and the one that makes the assertion above mean something: the
    same call without `shadow=True` records no row and reports 0. A recorder that ran
    unconditionally would satisfy every "it recorded rows" test in this file."""
    compile_fixture(_FACADE_FIXTURE)
    result, _multi_module = api._analyze(
        _FACADE_FIXTURE, workspace_dir=tmp_path, allow_resolve=False, shadow=False
    )
    workspace = DuckDbWorkspace(tmp_path / "workspace.duckdb")
    try:
        assert workspace.query("value_resolutions") == []
    finally:
        workspace.close()
    assert result.value_resolutions == 0


def _reactor_module(root: Path) -> ModuleModel:
    return ModuleModel(
        module_id="com.acme:orders-javalin",
        coordinates="com.acme/orders-javalin",
        version="1.0.0",
        root=root,
        kind="undetermined",
        languages=frozenset({"java"}),
        source_roots=(),
        output_dirs=(root / "target" / "classes",),
    )


def _reactor_lines(tmp_path: Path, shadow: bool) -> tuple[list[str], Path]:
    """One reactor walk over a COPY of the tiny fixture, and the lines it echoed.

    A copy because `_analyze_reactor` writes each module's workspace into the module's own
    directory — `test_app.py`'s reactor test copies for the same reason, and states it: the
    real fixture's `.sextant/` is read by another worker for the whole session."""
    compile_fixture(_FACADE_FIXTURE)
    root = tmp_path / "javalin"
    shutil.copytree(_FACADE_FIXTURE, root, ignore=shutil.ignore_patterns(".sextant"))
    module = _reactor_module(root)
    lines: list[str] = []
    api._analyze_reactor(
        tmp_path,
        RepositoryModel(root=tmp_path, modules=(module,)),
        False,
        None,
        lines.append,
        shadow=shadow,
    )
    return lines, root


def test_a_reactor_walk_reports_what_each_module_recorded(tmp_path: Path):
    """**The one hop the two tests above cannot reach.** A reactor records shadow rows PER
    MODULE, into each module's own workspace, so no single number on the `AnalyzeResult`
    can name them and the per-module echo is the only place a reader learns a submodule
    recorded anything. That echo is fed by the same defaulted keyword as every other hop,
    and dropping `shadow=shadow` where `_analyze_reactor` calls `_run_analyze` would
    silence it with nothing failing.

    The count is read back out of the module's OWN workspace rather than trusted from the
    line, because a line that printed a plausible number from the wrong place would be
    exactly the failure this whole file exists to make impossible."""
    lines, root = _reactor_lines(tmp_path, shadow=True)
    workspace = DuckDbWorkspace(root / ".sextant" / "workspace.duckdb")
    try:
        recorded = len(workspace.query("value_resolutions"))
    finally:
        workspace.close()
    assert recorded, "the reactor walk recorded nothing"
    assert [line for line in lines if line.endswith(f", {recorded} shadow rows")] == lines


def test_a_reactor_walk_says_nothing_about_shadow_without_the_flag(tmp_path: Path):
    """The ordinary reactor line is byte-for-byte what it has always been — the existing
    reactor tests assert its text, and a count appended unconditionally would have moved
    output on every multi-module run."""
    lines, _root = _reactor_lines(tmp_path, shadow=False)
    assert lines
    assert not any("shadow" in line for line in lines)


# --- §2's identity table, which the shadow walk resolves through (Task 7) ----------------
# The step-1 path for Tasks 8 and 9: they read this table before touching an engine, so what
# the recorder resolves through has to be the same thing a migrated engine resolves through.


_MODULE = "sextant-jvm maven com.acme/two-sources 1.0.0 "


def _two_source_document() -> Document:
    return Document(
        document_id="doc_two_sources",
        relative_path="com/acme/Helper.java",
        module_id="com.acme:two-sources",
        language="java",
        sextant_version="0.1.0",
        fact_schema_version=2,
        scanner_id="asm",
        content_hash="sha256:a",
        origin_entry="target/classes",
        origin_tier=OriginTier.MODULE_OUTPUT,
        redaction_set_hash="sha256:b",
    )


def _sourced(value_model: list[dict[str, Any]], identifier: str = "src") -> Catalog:
    """A catalog as ONE SOURCE builds it — every catalog of a source carries that source's
    whole table, which is what `Catalog.value_model` means (D02 §1f)."""
    return Catalog(
        id=identifier,
        style="single_call",
        protocol="kafka",
        direction="inbound",
        requires=(),
        matches={},
        source=Path(f"{identifier}.yml"),
        value_model=value_model,
    )


def test_two_sources_contribute_one_table_and_a_shared_producer_once():
    """**D02 §6 loads two catalog sets together and privileges neither**, and each hands its
    own catalogs its own identity table. Reading the FIRST catalog's would shadow one
    source's engines against another source's identities — silently, because every shipped
    analysis today has one source and nothing would fail.

    Deduplicated on what an entry MATCHES on, which is the loader's own rule
    (`yaml_source._matching_keys`): `by` is provenance, not part of the claim, so one
    producer declared by both sources is one entry and the first source's `by` travels with
    it. An entry the two sources DISCRIMINATE differently — one naming an `arity`, one not —
    is two claims and stays two, exactly as it does inside one source's table.
    """
    shared = {"owner": "a/B#", "method": "of", "arg": 0, "by": "probes/first.md"}
    shipped = _sourced([shared, {"owner": "c/D#", "method": "make", "arg": 1, "by": "p.md"}])
    theirs = _sourced(
        [
            {"owner": "a/B#", "method": "of", "arg": 0, "by": "probes/theirs.md"},
            {"owner": "a/B#", "method": "of", "arg": 0, "arity": 2, "by": "probes/theirs.md"},
            {"method": "connect", "arg": 0, "by": "probes/theirs.md"},
        ],
        "theirs",
    )

    table = _every_identity([shipped, shipped, theirs])

    assert table == [
        shared,
        {"owner": "c/D#", "method": "make", "arg": 1, "by": "p.md"},
        {"owner": "a/B#", "method": "of", "arg": 0, "arity": 2, "by": "probes/theirs.md"},
        {"method": "connect", "arg": 0, "by": "probes/theirs.md"},
    ]


def test_the_recorder_resolves_through_EVERY_sources_identities(tmp_path: Path):
    """The same rule at the CALL SITE, which the unit test above cannot reach: reverting
    `_every_identity(catalogs)` to `catalogs[0].value_model` passes every other test in this
    repository, because every shipped analysis loads one source.

    Here the catalog that ASKS carries an empty table and the identity that answers its
    question belongs to a SECOND source — D02 §6's shape, one repository's own catalogs
    beside the shipped ones. Read from the first catalog alone, the position stays a miss.
    """
    facts = [
        CallSiteFact(
            document_id="doc_two_sources",
            caller=_MODULE + "com/acme/Helper#use().",
            target=CallTarget(owner="com/acme/Name#", name="of", descriptor="(...)V"),
            invoke_kind="static",
            ordinal=0,
            result=1,
            arguments=[CallArgument(kind="string", value="from-the-second-source")],
        ),
        CallSiteFact(
            document_id="doc_two_sources",
            caller=_MODULE + "com/acme/Helper#use().",
            target=CallTarget(owner="com/acme/Sink#", name="take", descriptor="(...)V"),
            invoke_kind="static",
            ordinal=1,
            arguments=[CallArgument(kind="unresolved", source=1)],
        ),
    ]
    write_fact_file(tmp_path / "facts" / "two.jsonl", _two_source_document(), facts)
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    try:
        workspace.load_facts(tmp_path / "facts")
        record_return_flows(workspace)
        record_call_edges(workspace)
        asking = _sourced([], "asks-and-knows-nothing")
        asking.matches["methods"] = [{"owner": "com.acme.Sink", "method": "take", "arg": 0}]
        knowing = _sourced(
            [{"owner": "com/acme/Name#", "method": "of", "arg": 0, "by": "p.md"}], "theirs"
        )
        assert record_value_resolutions(workspace, [asking, knowing], shadow=True) == 1
        [row] = workspace.query("value_resolutions")
    finally:
        workspace.close()

    assert (str(row["outcome"]), str(row["value"])) == ("would_resolve", "from-the-second-source")


def test_the_shadow_walk_resolves_through_the_identity_table(analyzed):
    """**The recorder resolves through §2's table, on the real corpus and through the real
    stage** — the unit tests above reach the helper and one hand-built call; this is the
    shipped catalogs against shipped bytecode, which is what Tasks 8 and 9 will read.

    **Asserted at the CONSUMING position and nowhere else, which is the whole of what makes
    it a pin.** `jakarta-jms.yml` asks about both calls of
    `session.createProducer(session.createQueue("raw-audit"))`: ordinal 0 slot 0 is
    `createQueue`'s own string literal, which resolves with or without any identity, and
    ordinal 1 slot 0 is the `Queue` OBJECT, which answers `external` unless the table says
    argument 0 of `createQueue` is what that object is. *An earlier version of this test
    asserted that the value set contained `raw-audit` and `raw-intake`; the literal rows
    satisfied that on their own, so it passed with the identity table emptied and pinned
    nothing (round 3).*
    """
    consuming = {
        (str(row["caller"]).rsplit("/", 1)[-1].partition("(")[0], int(str(row["ordinal"]))): (
            str(row["outcome"]),
            row["value"],
        )
        for row in analyzed[True].rows
        if str(row["catalog"]) == "jakarta-jms" and str(row["slot"]) == "0"
    }

    assert consuming[("RawJmsBridge#createAuditProducer", 1)] == ("would_resolve", "raw-audit")
    assert consuming[("RawJmsBridge#createIntakeConsumer", 1)] == ("would_resolve", "raw-intake")
