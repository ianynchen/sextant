import json
import subprocess
from pathlib import Path

import duckdb
from click.testing import CliRunner

from sextant.cli.app import cli
from sextant.domain.factfile import read_fact_file

REPO = Path(__file__).parents[2]
FIXTURE = REPO / "fixtures" / "orders-service"


def _run(workspace: Path) -> None:
    runner = CliRunner()
    for command in ("analyze", "render", "export"):
        result = runner.invoke(
            cli, ["module", command, str(FIXTURE), "--workspace", str(workspace)]
        )
        assert result.exit_code == 0, result.output


def _fingerprint(workspace: Path) -> dict[str, bytes]:
    captured = {}
    for path in sorted(workspace.rglob("*")):
        if path.is_file() and path.suffix in {".jsonl", ".json", ".md", ".parquet"}:
            captured[str(path.relative_to(workspace))] = path.read_bytes()
    return captured


def test_output_is_byte_identical_when_the_pipeline_runs_twice(tmp_path: Path):
    subprocess.run(["mvn", "-q", "-o", "compile"], cwd=FIXTURE, check=True)
    first, second = tmp_path / "one", tmp_path / "two"
    _run(first)
    _run(second)
    assert _fingerprint(first) == _fingerprint(second)


def test_the_document_names_every_fixture_endpoint_and_its_gaps(tmp_path: Path):
    subprocess.run(["mvn", "-q", "-o", "compile"], cwd=FIXTURE, check=True)
    _run(tmp_path)
    document = (tmp_path / "render" / "architecture.md").read_text()
    for route in ("POST", "GET", "/v1/orders", "/v1/orders/{id}"):
        assert route in document
    assert "Known gaps" in document
    assert "## Outbound endpoints" in document
    assert "/billing/invoices" in document
    assert "/billing/settlements" in document
    # InventoryWebClient#search builds its URL from a uriBuilder lambda: the
    # fluent engine follows only one hop, so path stays honestly NULL rather
    # than guessed, and the endpoint column says so instead of `GET None`.
    assert "GET (unresolved)" in document
    assert "classDiagram" in document
    # Phase 2D (Task 11): a verbless messaging row renders `protocol path`,
    # no method — `order-events` is now `direction: both` (merged with the
    # producer catalogs' own `KafkaTemplate.send`), so it appears once in
    # each of the inbound and outbound sections.
    assert "kafka order-events" in document
    # Phase 2D (Task 12): the @SendTo reply row keeps its own identity —
    # `order-return-receipts` never merges into `order-returns`, since the
    # reply topic is a distinct destination — and carries its own contract
    # (`onReturn`'s return type, ReceiptView) rather than the handler's.
    assert "kafka order-return-receipts" in document
    # A NULL-path outbound messaging row (no literal destination resolved —
    # here `sendDefault`) renders `{protocol} (unresolved)`, the same
    # honesty rule as the HTTP `GET (unresolved)` row above.
    assert "kafka (unresolved)" in document
    # 2E-prep Task 13: the raw-driver catalogs (Tasks 11-12) render like any
    # other messaging row — `kafka-consumer.yml`'s
    # `RawKafkaConsumers#subscribeToTopics` call derives both `raw-t1` and
    # `raw-t2` off the SAME caller.
    assert "kafka raw-t1" in document
    # `google-pubsub-subscriber.yml`'s `interface_implementation` style
    # resolves `raw-notify`'s instance receiver to its class's own declared
    # `MessageReceiver#receiveMessage` implementer — the handler renders
    # verbatim in the SAME row as the identity. The `(sig_...)` suffix is
    # there because the handler is the METHOD SYMBOL the facts carry, joined
    # out of `symbols` (final review, FIX 1), not a string built from the
    # receiver's type descriptor and the catalog's method name — the older,
    # suffix-free form named no symbol at all and joined to nothing.
    assert (
        "`pubsub raw-notify` | "
        "`com/acme/orders/messaging/raw/RawPubSubReceiver#receiveMessage(sig_bb1c3cf6).`"
    ) in document
    # 2F Task 9: the coverage section names environments resolved, every
    # unresolved `resolved_config` key with its reason and environment (the
    # fixture's own layering pin — `only.in.default` resolves in `default`,
    # is `missing_key` in `prod`), and every unresolved config_join row by
    # catalog and site (I-1) — `orphanConsumer`'s missing binding key has no
    # `resolved_config` row of its own (never declared in any file), so it
    # is named through its handler instead, and the composed `pipeA|pipeB`
    # entry through neither, since the composed expression is not a column
    # any row carries.
    assert "Environments resolved: `default`, `prod`." in document
    assert "only.in.default — missing_key in prod" in document
    # F2, review round 1: the disclosed lead-in — the list below spans
    # every engine's own unresolved rows (the fixture's own live proof:
    # non-config_join catalogs appear in it too), not config_join alone.
    assert (
        "Unresolved endpoint derivations — across every engine, whatever "
        "their evidence, not configuration alone:"
    ) in document
    assert (
        "Unresolved endpoint derivation: `spring-cloud-stream` — handler "
        "`com/acme/orders/streams/OrderStreamBindings#orphanConsumer(sig_b4c25d22).`."
    ) in document
    assert (
        "Unresolved endpoint derivation: `spring-cloud-stream` — a composed selection expression."
    ) in document


def test_every_fact_the_extractor_writes_validates_against_the_domain_model(tmp_path: Path):
    """The contract between the two halves of the fact stream (final review,
    M5). `load_facts` reads the JSONL straight into DuckDB — deliberately,
    for the bulk-load reason NFR-11 states — so nothing in the running
    pipeline ever puts the extractor's own output through the pydantic models
    that define D00 §5. A field the extractor renamed, a `kind` outside the
    closed set, an argument shape the model does not describe: all of it
    would flow through the pipeline and only surface as a column that reads
    NULL for no visible reason.

    So the whole fact tree the fixture produces is validated here, line by
    line, through the project's own reader — the document header as
    `Document`, every following line through `TypeAdapter(Fact)`, which
    raises on the first one the model refuses. The kind check keeps the test
    from passing vacuously on an empty or truncated tree; `module` is absent
    on purpose, being the detector's fact rather than the scanner's."""
    subprocess.run(["mvn", "-q", "-o", "compile"], cwd=FIXTURE, check=True)
    _run(tmp_path)

    files = sorted((tmp_path / "facts").rglob("*.jsonl"))
    validated = [read_fact_file(path) for path in files]
    kinds = {fact.kind for _, facts in validated for fact in facts}
    total = sum(len(facts) for _, facts in validated)

    assert files != []
    assert {"annotation", "call_site", "symbol"} <= kinds
    assert total >= len(files)


def test_the_bundle_answers_what_the_workspace_answered(tmp_path: Path):
    subprocess.run(["mvn", "-q", "-o", "compile"], cwd=FIXTURE, check=True)
    _run(tmp_path)  # analyze + render + export
    # Phase 2D (Task 12): metadata.json's own direction/protocol buckets
    # (written by analyze, D05 §3) count every messaging protocol too, a
    # `both` row counting on both sides (metadata.py's own rule) — the same
    # 82-endpoint fixture as the endpoints.parquet check below, viewed
    # through the other artifact. (2E-prep Task 6, checkpoint ruling
    # 2026-08-30: kafka outbound is 8, not 7 — `RawKafkaMessageSender#send`'s
    # `kafkaTemplate.send(Message<?>)` derives its own unresolved NULL-path
    # row off `spring-kafka-template.yml`'s pre-existing arity-1 `record_arg`
    # rule; see `test_pipeline.py`'s dedicated row-level test for the full
    # explanation.)
    #
    # 2E-prep Task 11 (driver catalogs A): `jakarta-jms.yml`,
    # `kafka-consumer.yml` and `aws-sqs-sdk.yml` add 6 more rows, none
    # merging with anything else in the fixture — jms +1 inbound (
    # `raw-intake`) +1 outbound (`raw-audit`), kafka +3 inbound (`raw-t1`,
    # `raw-t2`, `raw-.*`), sqs +1 outbound (the queue URL's own path). See
    # `test_pipeline.py`'s own dedicated row-level tests for the full
    # per-row breakdown.
    #
    # 2E-prep Task 12 (driver catalogs B): the pubsub trio +
    # spring-kafka-message add 6 more rows, none merging with anything else
    # — pubsub inbound +2 (`raw-notify`, `raw-notify-lambda`,
    # `google-pubsub-subscriber.yml`'s own `interface_implementation` rows),
    # pubsub outbound +3 (`google-pubsub-publisher.yml`'s resolved
    # `raw-events` plus `google-pubsub-client.yml`'s two deliberate
    # unresolved duplicates, spec §4's ruling), kafka outbound +1
    # (`spring-kafka-message.yml`'s own `raw-messages` row, resolved
    # identity but unresolved overall — a divergence from this task's own
    # checkpoint shorthand, verified live, see `test_pipeline.py`). See
    # `test_pipeline.py`'s own dedicated row-level tests for the full
    # per-row breakdown.
    #
    # Phase 2E Task 6 (composed annotations — a different plan's numbering
    # from the "2E-prep Task" comments above): +1 http inbound (`GET
    # /composed`) and +1 kafka inbound (`composed-orders`), the
    # effective-annotations pre-pass's own fixture. See
    # `test_pipeline.py`'s own dedicated row-level test for the full
    # explanation.
    #
    # Phase 2E Task 7 (inherited mappings): +2 more http inbound
    # (`GET /api/orders`, `GET /api/composed`) — the OpenAPI-generator
    # interface/implementation pair's own fixture. See `test_pipeline.py`'s
    # own dedicated row-level test for the full explanation.
    #
    # Phase 2E Task 9 (the `combinator` engine, spring-webflux-router.yml):
    # +10 more http inbound — the WebFlux functional-routing tree, both
    # DSLs, none merging with anything already in the fixture. See
    # `test_pipeline.py`'s own dedicated row-level test for the full
    # per-row breakdown.
    #
    # 2F Task 3 (the configuration surface fixture): +4 http outbound —
    # `BillingClients`' own four half-2 WebClient chains, each feeding
    # `baseUrl(...)` a value no call-site literal names (a field read, a
    # properties-getter call result, a computed concatenation) and each
    # carrying its own distinct `.uri()` literal. Task 8's field ladder then
    # composed base and path: three now carry `${billing.url}/...`, the
    # computed one carries path NULL and reads `unresolved` (checkpoint D-4)
    # — four rows either way, which is why this count is unchanged by it.
    # jms/kafka/pubsub/sqs are unchanged: `onAudit`'s own
    # move to `${orders.audit.topic}` splits its previous `both`-direction
    # merge with `sendAuditMessage`'s send into two standalone rows (one
    # inbound, one outbound) rather than changing either bucket's total —
    # see `test_pipeline.py`'s own dedicated row-level test. `82 + 5 = 87`
    # total, Task 3's own frozen baseline for Tasks 4-8.
    #
    # 2F Task 7 (the `config_join` engine): +3 kafka inbound and +1 kafka
    # outbound — the four rows `spring.cloud.function.definition` selects
    # (`handleOrder` → `stream-orders`, `orphanConsumer` and the composed
    # `pipeA|pipeB` entry both path-NULL, `auditTap` → `audit-tap`). Nothing
    # else moves: no other protocol has a `config_join` catalog, and neither
    # resolved destination has a twin to merge with. Metadata counts a
    # `both` row in BOTH buckets, so kafka reads 12 + 3 = 15 inbound and
    # 6 + 1 = 7 outbound, plus the 3 unchanged `both` rows on each side —
    # 15 and 10. `87 + 4 = 91` total.
    # 2G Task 5 (declared shapes): +1 http inbound —
    # `POST /v1/orders/proto-orders`, unmerged. `91 + 1 = 92` total.
    metadata = json.loads((tmp_path / "metadata.json").read_text())
    assert metadata["endpoints"]["inbound"] == {
        "http": 32,
        "jms": 3,
        "kafka": 15,
        "pubsub": 3,
        "sqs": 1,
    }
    assert metadata["endpoints"]["outbound"] == {
        "http": 23,
        "jms": 3,
        "kafka": 10,
        "pubsub": 4,
        "sqs": 3,
    }
    # 2F Task 9: metadata.json's own "environments" (D06 §3), populated from
    # `resolved_config`'s distinct environments — the fixture's own
    # `default`/`application-prod.yml` pair.
    assert metadata["environments"] == ["default", "prod"]
    runner = CliRunner()
    result = runner.invoke(cli, ["module", "export", str(FIXTURE), "--workspace", str(tmp_path)])
    assert result.exit_code == 0, result.output
    bundle = Path(result.output.strip())
    manifest = json.loads((bundle / "manifest.json").read_text())
    assert manifest["producer"]["catalog_hash"].startswith("sha256:")
    assert "reactive_flow_not_traced" in manifest["gaps"]
    assert "endpoints" in manifest["contents"]["tables"]
    # The bundle manifest's own sibling field, carried from metadata.json
    # rather than re-derived (M08 "never re-analyzes").
    assert manifest["environments"] == ["default", "prod"]
    rows = duckdb.sql(
        f"SELECT direction, count(*) AS n FROM read_parquet('{bundle / 'graph' / 'endpoints.parquet'}') "
        "GROUP BY direction ORDER BY direction"
    ).fetchall()
    # Phase 2C: the spring-resttemplate catalog's four `single_call` routes
    # (BillingRestTemplate), plus the three `fluent` catalogs' eight
    # reconstructed-chain routes (WebClient/RestClient/OkHttp), join the
    # outbound side, real end to end.
    # Phase 2D (Task 10): the three listener catalogs add 11 inbound rows
    # (kafka 8, jms 2, sqs 1 — see test_pipeline.py for the full breakdown)
    # and 2 kafka outbound `@SendTo` reply rows.
    # Phase 2D (Task 11): the five producer catalogs (six files —
    # `ReplyingKafkaTemplate` gets its own, `matches.owner` being
    # single-valued) add 11 raw derived rows, five of which immediately
    # merge into an inbound row — four already existing from Task 10
    # (`order-events`, `order-audit`, `order-returns`, `audit.queue`) plus
    # one new on both sides in this same task (pubsub `order-notifications`,
    # the only Task 11 merge where neither side pre-existed). Each merge
    # converts one inbound + one outbound row into one `both` row, so five
    # merges: inbound 28+1-5=24, outbound 20+10-5=25, both 1+5=6 — see
    # test_pipeline.py for the full row-by-row breakdown.
    # 2E-prep Task 6 (checkpoint ruling, 2026-08-30) adds one more outbound
    # row: `RawKafkaMessageSender#send`'s `kafkaTemplate.send(Message<?>)`
    # matches `spring-kafka-template.yml`'s existing arity-1 `record_arg`
    # rule (predating this task) and derives its own unresolved NULL-path
    # row, distinct from `sendDefault`'s (different caller, no merge target)
    # — spec §4's duplicate-row ruling: 25 + 1 = 26.
    # 2E-prep Task 11 (driver catalogs A): 6 more rows, none merging with
    # anything else — inbound +4 (jms `raw-intake`, kafka `raw-t1`/`raw-t2`/
    # `raw-.*`), outbound +2 (jms `raw-audit`, sqs the queue URL's own
    # path), `both` unchanged: 24 + 4 = 28, 26 + 2 = 28.
    # 2E-prep Task 12 (driver catalogs B): 6 more rows, none merging with
    # anything else — inbound +2 (pubsub `raw-notify`, `raw-notify-lambda`),
    # outbound +4 (pubsub `raw-events` resolved + the two deliberate
    # `google-pubsub-client.yml` duplicates, kafka `raw-messages`), `both`
    # unchanged: 28 + 2 = 30, 28 + 4 = 32.
    # Phase 2E Task 6 (composed annotations — a different plan's numbering
    # from the "2E-prep Task" comments above): +2 inbound (`GET /composed`,
    # `composed-orders`), outbound and `both` unchanged: 30 + 2 = 32.
    # Phase 2E Task 7 (inherited mappings): +2 more inbound
    # (`GET /api/orders`, `GET /api/composed`), outbound and `both`
    # unchanged: 32 + 2 = 34.
    # Phase 2E Task 9 (the `combinator` engine): +10 more inbound (the
    # WebFlux functional-routing tree, both DSLs), outbound and `both`
    # unchanged: 34 + 10 = 44 — the checkpoint's own frozen 82-endpoint
    # total (6 + 44 + 32 = 82).
    # 2F Task 3 (the configuration surface fixture): `BillingClients`' four
    # half-2 WebClient chains add 4 outbound rows (each unresolved,
    # `.uri()`'s own argument never a string literal — see
    # `test_pipeline.py`). `AuditJmsListener#onAudit`'s destination moves to
    # `${orders.audit.topic}`, a different literal from
    # `EventProducers#sendAuditMessage`'s own `"audit.queue"` — the wire-
    # identity merge that used to fold both into one `both` row no longer
    # fires, so it splits into one standalone inbound row (`onAudit`) and
    # one standalone outbound row (`sendAuditMessage`): `both` 6 - 1 = 5,
    # inbound 44 + 1 = 45, outbound 32 + 1 + 4 = 37 — Task 3's own frozen
    # 87-endpoint total (5 + 45 + 37 = 87).
    # 2F Task 7 (`config_join`): +3 inbound and +1 outbound binding rows,
    # `both` unchanged (neither resolved destination has a twin, and a
    # path-NULL row never merges): inbound 45 + 3 = 48, outbound 37 + 1 = 38
    # — the 91-endpoint total (5 + 48 + 38 = 91).
    # 2G Task 5 (declared shapes): +1 inbound, unmerged —
    # `POST /v1/orders/proto-orders`: inbound 48 + 1 = 49 — the 92-endpoint
    # total (5 + 49 + 38 = 92).
    assert rows == [("both", 5), ("inbound", 49), ("outbound", 38)]
