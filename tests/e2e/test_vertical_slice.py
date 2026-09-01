import json
import subprocess
from pathlib import Path

import duckdb
from click.testing import CliRunner

from sextant.cli.app import cli
from sextant.domain.factfile import read_fact_file
from sextant.storage.duckdb.workspace import DuckDbWorkspace

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
    # 2H Task 5: websocket rows ride the verbless, messaging-style rendering
    # (kafka precedent) — `_VERBLESS_PROTOCOLS` derives from D00's whole
    # protocol set minus the verbed ones, so `websocket` lands in it with no
    # renderer change at all (only `graphql` joined the verbed/qualified
    # sets in this phase). `/live`'s frame is untyped, so its own format
    # column reads `unresolved`, never a guess; `/orders/place` and
    # `/orders/board` both read `json (assumed)` — rung 5's framework
    # default, the ladder's own live answer today (Task 6 re-pins this if
    # its own work moves it, per the checkpoint).
    assert (
        "`websocket /live` | `com/example/orders/ws/LiveEndpoint#onFrame(sig_a7421bf5).` | - → - | unresolved | resolved |"
        in document
    )
    assert (
        "`websocket /orders/place` | `com/example/orders/ws/OrderStompController#place(sig_961974f8).` | - → - | json (assumed) | resolved |"
        in document
    )
    assert (
        "`websocket /orders/board` | `com/example/orders/ws/OrderStompController#board(sig_26be7569).` | - → - | json (assumed) | resolved |"
        in document
    )
    # `place`'s own resolved `@SendTo` reply, and `board`'s own dynamic
    # reply — the SAME `escalate`-shaped unresolved row (D02 §2's reply
    # block), rendered `websocket (unresolved)` exactly as every other
    # path-NULL outbound row already is.
    assert (
        "`websocket /topic/order-placed` | unresolved | `com/example/orders/ws/OrderStompController#place(sig_961974f8).` | json (assumed) | resolved |"
        in document
    )
    assert (
        "`websocket (unresolved)` | unresolved | `com/example/orders/ws/OrderStompController#board(sig_26be7569).` | json (assumed) | unresolved |"
        in document
    )
    assert (
        "Unresolved endpoint derivation: `spring-stomp` — caller "
        "`com/example/orders/ws/OrderStompController#board(sig_26be7569).`."
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
    # 2G Task 7 (parse binding): +2 jms inbound and +3 sqs inbound — the
    # bytes-only listeners in `messaging/parse`, whose destinations are
    # unique to that file and merge with nothing. The pass binds a payload
    # onto three of them and refuses two; both outcomes are still endpoint
    # rows, so all five count. `92 + 5 = 97` total.
    # 2H Task 1 (GraphQL, WebSocket/STOMP and SSE surfaces): +2 http inbound —
    # `GET /events/emitter`, `GET /events/stream`. `OrderEventsController`
    # uses the already-shipped `@GetMapping`/`@RestController` annotations,
    # so both derive as ordinary http endpoints today (a later 2H task
    # reclassifies them to SSE); neither merges with anything. The GraphQL,
    # WebSocket and STOMP surfaces this task also adds derive NO rows at
    # all — nothing catalogs those annotations yet. `97 + 2 = 99` total.
    # 2H Task 2 (the three GraphQL catalogs): +11 graphql inbound — a NEW
    # protocol bucket, which is the visible half of D00's closed set gaining
    # `graphql`. Nothing outbound: a GraphQL operation is served by this
    # module, never called by it, so the outbound map is untouched and no
    # existing bucket moves. TWELVE annotated methods produce those 11 rows:
    # `orphanField` names a field of a type nothing states, so it derives none
    # at all rather than a bare, wrongly-shaped `orphan`. `99 + 11 = 110`.
    # 2H Task 4 (`schema_operations`): +1 graphql inbound — `query auditTrail`,
    # the ONE root field in `schema.graphqls` that no annotation implements
    # (the RuntimeWiring pin, 2H design §3). The schema declares seven root
    # fields in all; the other six share a wire identity with an annotation row
    # that already exists when this style runs, and the insert-if-absent guard
    # keeps that row — which is the whole of how first-writer agreement works
    # here. Still nothing outbound, and no existing bucket moves.
    # `110 + 1 = 111` total.
    # 2H Task 5 (WebSocket/STOMP catalogs): +3 websocket inbound —
    # `jakarta-websocket.yml`'s `/live` (checkpoint answer 5's
    # `@KafkaHandler` prefix shape) and `spring-stomp.yml`'s
    # `/orders/place`/`/orders/board` (class-level `@MessageMapping` prefix
    # composition) — and +2 websocket outbound — `place`'s own resolved
    # `@SendTo("/topic/order-placed")` reply, and `board`'s own dynamic
    # reply (value-returning, no `@SendTo`, the `escalate` shape again —
    # `path` NULL, `unresolved`, still counted here: metadata buckets every
    # row regardless of `resolution`). A NEW protocol bucket, the third the
    # 2H phase adds (`graphql`, then `sse` at Task 6, now `websocket`); no
    # existing bucket moves. `111 + 5 = 116` total.
    metadata = json.loads((tmp_path / "metadata.json").read_text())
    assert metadata["endpoints"]["inbound"] == {
        "graphql": 12,
        "http": 34,
        "jms": 5,
        "kafka": 15,
        "pubsub": 3,
        "sqs": 4,
        "websocket": 3,
    }
    assert metadata["endpoints"]["outbound"] == {
        "http": 23,
        "jms": 3,
        "kafka": 10,
        "pubsub": 4,
        "sqs": 3,
        "websocket": 2,
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
    # 2G Task 7 (parse binding): +5 inbound, all unmerged — the bytes-only
    # listeners in `messaging/parse`: inbound 49 + 5 = 54 — the 97-endpoint
    # total (5 + 54 + 38 = 97).
    # 2H Task 1: +2 inbound, unmerged — `GET /events/emitter`,
    # `GET /events/stream`: inbound 54 + 2 = 56 — the 99-endpoint total
    # (5 + 56 + 38 = 99).
    # 2H Task 2: +11 inbound, all unmerged — the GraphQL surface. Every one is
    # inbound and none has an outbound twin anywhere in the fixture (a
    # GraphQL operation is served, never called, by the module that declares
    # it), so `both` and `outbound` are both untouched: inbound 56 + 11 = 67 —
    # the 110-endpoint total (5 + 67 + 38 = 110).
    # 2H Task 4: +1 inbound, the schema-first `query auditTrail` — inbound
    # 67 + 1 = 68, the 111-endpoint total (5 + 68 + 38 = 111). It is inbound
    # and unmerged for the same reason every other GraphQL row is.
    # 2H Task 5: +3 inbound (`/live`, `/orders/place`, `/orders/board`) and
    # +2 outbound (`place`'s resolved `@SendTo` reply, `board`'s own
    # unresolved dynamic reply) — inbound 68 + 3 = 71, outbound 38 + 2 = 40,
    # `both` untouched (a `direction: inbound` catalog's own rows never meet
    # an outbound row on any protocol nothing else in the fixture names) —
    # the 116-endpoint total (5 + 71 + 40 = 116).
    assert rows == [("both", 5), ("inbound", 71), ("outbound", 40)]


def test_a_bound_parse_reaches_the_format_ladders_payload_rung_in_a_full_analyze(
    tmp_path: Path,
):
    """2G Task 7's binding, end to end through the REAL command — and the one
    place rung 4 of the format ladder (2G design §5) has a live surface.

    `test_pipeline.py` resolves without the descriptor interpreter, so no
    `declared_shape` fact exists there and the same rows read `json`/
    `narrowed` off rung 5. Here the whole `analyze` runs: the interpreter
    turns the fixture's embedded protobuf descriptor into declared shapes,
    the parse binding puts one of those types on three bytes-only channels,
    and rung 4 reads it back as the schema format at `narrowed` — never
    `resolved`, because proto3 has a JSON encoding and a payload's TYPE is
    not a statement about the bytes.

    The two rows the binding REFUSED are pinned in the same breath: they keep
    the byte array their signature declares, answer `unresolved`, and appear
    in `open_questions` with the candidates the pass would not choose between.
    A test that only pinned the successes could not tell a refusal from a
    miss.
    """
    subprocess.run(["mvn", "-q", "-o", "compile"], cwd=FIXTURE, check=True)
    runner = CliRunner()
    result = runner.invoke(cli, ["module", "analyze", str(FIXTURE), "--workspace", str(tmp_path)])
    assert result.exit_code == 0, result.output

    workspace = DuckDbWorkspace(tmp_path / "workspace.duckdb")
    try:
        answers = {
            str(row["path"]): (row["request_shape"], row["format"], row["format_resolution"])
            for row in workspace.query("endpoints")
            if row["path"] is not None and str(row["path"]).startswith("parsed-")
        }
        questions = [
            (str(row["path"]), str(row["question"]), json.loads(str(row["candidates"])))
            for row in workspace.query("open_questions")
        ]
    finally:
        workspace.close()

    proto = json.dumps(
        {
            "nullable": True,
            "shape_id": "com/example/orders/proto/OrderProtos$OrderRequest#",
            "wire_format": "",
            "wire_type": "object",
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    bytes_payload = json.dumps(
        {
            "item": {"nullable": False, "wire_format": "int32", "wire_type": "integer"},
            "nullable": True,
            "wire_format": "",
            "wire_type": "array",
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    assert answers == {
        # Rung A — the parse is in the handler itself.
        "parsed-orders-inbound": (proto, "protobuf", "narrowed"),
        # Rung B — one delegation hop, and the same callee reached from a
        # second channel: multi-caller is not ambiguity.
        "parsed-audit-queue": (proto, "protobuf", "narrowed"),
        "parsed-shared-inbound": (proto, "protobuf", "narrowed"),
        # Refused: two parses of one payload, and a parse two hops out.
        "parsed-mixed-inbound": (bytes_payload, None, "unresolved"),
        "parsed-relay-queue": (bytes_payload, None, "unresolved"),
    }
    assert [(path, question) for path, question, _ in questions] == [
        ("parsed-relay-queue", "payload_binding"),
        ("parsed-mixed-inbound", "payload_binding"),
    ]
    # The ambiguous row carries BOTH answers, and one of them comes through
    # the relocated parser package — the Jackson-3-shaped catalog row,
    # exercised against real bytecode rather than an invented owner.
    assert [candidate["payload_type"] for candidate in questions[1][2]] == [
        "com/acme/orders/contracts/OrderView#",
        "com/example/orders/proto/OrderProtos$OrderRequest#",
    ]
    assert questions[1][2][0]["why"] == "tools/jackson/databind/json/JsonMapper#readValue"
    # And the beyond-horizon row names the parse it refused, two hops out.
    assert questions[0][2] == [
        {
            "hops": "2",
            "payload_type": "com/example/orders/proto/OrderProtos$OrderRequest#",
            "seen_in": "com/acme/orders/messaging/parse/OrderIngest#process(sig_2fd69fe6).",
            "why": "com/example/orders/proto/OrderProtos$OrderRequest#parseFrom",
        }
    ]


def test_the_schemas_own_root_operations_reach_the_endpoint_table_in_a_full_analyze(
    tmp_path: Path,
):
    """2H Task 4 (`schema_operations`), live and whole, through the REAL
    command — the only path that reads `src/main/resources/graphql` at all.

    Four claims, and each is a different half of the mechanism:

    * the RuntimeWiring pin — `auditTrail` is the one root field in the
      fixture's schema that no annotation implements, so it is the one new
      row, at `declared` with no handler and no caller;
    * first-writer agreement — the other six root fields already had
      annotation rows when this style ran, and the insert-if-absent guard kept
      them, handler and all. Six annotation twins, not six duplicates;
    * the shape universes stay apart (2H design §4) — `orders` keeps the
      compiled type its handler really serializes, and `auditTrail` points at
      a schema NAME that resolves inside the declared universe, with its own
      shape and fields expanded from the schema's field declarations. No
      simple-name join is made in either direction;
    * the format ladder's rung 1 outranks its rung 4 — the row's payload is a
      schema-described shape, which rung 4 would report as the schema's own
      format at `narrowed`; `format_fixed` answers first, so the row reads
      `json`/`resolved` and the column never receives a value D00's format set
      does not contain.
    """
    subprocess.run(["mvn", "-q", "-o", "compile"], cwd=FIXTURE, check=True)
    runner = CliRunner()
    result = runner.invoke(cli, ["module", "analyze", str(FIXTURE), "--workspace", str(tmp_path)])
    assert result.exit_code == 0, result.output

    workspace = DuckDbWorkspace(tmp_path / "workspace.duckdb")
    try:
        roots = {
            str(row["path"]): row
            for row in workspace.query("endpoints")
            if row["protocol"] == "graphql" and row["method"] is not None
        }
        shapes = {str(row["shape_id"]): row for row in workspace.query("shapes")}
        audit_fields = [
            (str(row["wire_name"]), row["wire_type"], row["nullable"], row["evidence"])
            for row in workspace.query("shape_fields")
            if row["shape_id"] == "AuditEntry"
        ]
    finally:
        workspace.close()

    # The schema declares seven root fields; six of them are also annotated.
    assert set(roots) == {
        "orderById",
        "orders",
        "dgsOrders",
        "mpOrders",
        "auditTrail",
        "placeOrder",
        "orderUpdates",
    }
    schema_first = [path for path, row in roots.items() if row["catalog_id"] == "graphql-schema"]
    assert schema_first == ["auditTrail"]

    audit = roots["auditTrail"]
    assert (audit["method"], audit["direction"]) == ("query", "inbound")
    assert (audit["evidence"], audit["resolution"]) == ("declared", "resolved")
    assert audit["handler"] is None and audit["caller"] is None
    # A root field's ARGUMENTS are what the operation takes, and the
    # interpreter does not project them — so there is nothing to carry, and
    # NULL says exactly that. `auditTrail(id: ID!)` really does take one.
    assert audit["request_shape"] is None
    assert (audit["format"], audit["format_resolution"]) == ("json", "resolved")
    # `[AuditEntry!]` — the declared universe's own name, reached through the
    # `item` chain, never a compiled class.
    assert json.loads(str(audit["response_shape"])) == {
        "wire_type": "array",
        "wire_format": None,
        "nullable": True,
        "item": {
            "wire_type": "object",
            "wire_format": None,
            "nullable": False,
            "shape_id": "AuditEntry",
        },
    }
    assert shapes["AuditEntry"]["open"] is False
    assert audit_fields == [
        ("at", "string", False, "declared"),
        ("actor", "string", True, "declared"),
    ]

    # The six annotated ones kept the annotation's row — the handler symbol is
    # the thing only that side knows — and `orders` kept the compiled response
    # type its handler declares, never overwritten by the schema's own.
    assert all(
        roots[path]["handler"] is not None and roots[path]["evidence"] == "compiler"
        for path in set(roots) - {"auditTrail"}
    )
    assert roots["orders"]["catalog_id"] == "spring-graphql"
    assert (
        json.loads(str(roots["orders"]["response_shape"]))["item"]["shape_id"]
        == "com/acme/orders/contracts/OrderView#"
    )


def test_a_schema_first_operation_reaches_the_rendered_document(tmp_path: Path):
    """The same row at the document a reader actually sees. `none recorded`
    rather than `unresolved`: the schema addressed this operation outright and
    names no code, which is an absence rather than a failed read — and the
    response the reader gets is the schema's own type, by its schema name."""
    subprocess.run(["mvn", "-q", "-o", "compile"], cwd=FIXTURE, check=True)
    _run(tmp_path)  # analyze + render + export
    document = (tmp_path / "render" / "architecture.md").read_text()

    assert "| `graphql query auditTrail` | none recorded | - → - | json | resolved |" in document
    assert "- `graphql query auditTrail`\n  - Response: array of object AuditEntry" in document


def test_format_field_number_and_open_questions_reach_the_rendered_document(tmp_path: Path):
    """2G Task 8, live and whole: the format ladder's three tiers each reach
    the document's Format column beside Media, the two refused parse-binding
    rows reach the "Open questions" section with their candidates, and a
    declared-shape field's `field_number` rides beside its name — the same
    invariant `test_a_bound_parse_reaches_the_format_ladders_payload_rung_in_a_full_analyze`
    pins at the workspace level, pinned here at the document a reader
    actually sees."""
    subprocess.run(["mvn", "-q", "-o", "compile"], cwd=FIXTURE, check=True)
    _run(tmp_path)  # analyze + render + export
    document = (tmp_path / "render" / "architecture.md").read_text()

    # Rung 2 (declared media, `resolved`) — plain, no hedge.
    assert (
        "| `POST /v1/orders/proto-orders` | "
        "`com/acme/orders/OrderController#createProtoOrder(sig_0bf859c2).` | "
        "- → application/json | json | resolved |"
    ) in document
    # Rung 3 (serializer config, `resolved`) — plain, no hedge.
    assert (
        "| `kafka composed-orders` | "
        "`com/acme/orders/composed/ComposedListener#onComposedEvent(sig_b2a754d9).` | "
        "- → - | protobuf | resolved |"
    ) in document
    # Rung 4 (payload hierarchy, `narrowed`) — one of the three rows the
    # parse-binding pass bound: an assumed format must never look observed
    # (2G design §5's first rule), so it carries `(assumed)`.
    assert (
        "| `jms parsed-audit-queue` | "
        "`com/acme/orders/messaging/parse/ParsedPayloadListeners#onDelegated(sig_cb303bd1).` | "
        "- → - | protobuf (assumed) | resolved |"
    ) in document
    # Rung 6 (nothing) — one of the two rows the same pass refused: the
    # endpoint itself derived cleanly (`resolved`), but nothing describes
    # what is on its wire.
    assert (
        "| `jms parsed-relay-queue` | "
        "`com/acme/orders/messaging/parse/ParsedPayloadListeners#onRelayed(sig_cb303bd1).` | "
        "- → - | unresolved | resolved |"
    ) in document

    # The two refused rows reach "Open questions" with their candidates —
    # never silently absorbed into the tables above.
    assert "## Open questions" in document
    assert (
        "- `jms parsed-relay-queue` — payload_binding: "
        "com/example/orders/proto/OrderProtos$OrderRequest# in "
        "com/acme/orders/messaging/parse/OrderIngest#process(sig_2fd69fe6). "
        "via com/example/orders/proto/OrderProtos$OrderRequest#parseFrom at 2 hop(s)"
    ) in document
    assert (
        "- `sqs parsed-mixed-inbound` — payload_binding: "
        "com/acme/orders/contracts/OrderView# in "
        "com/acme/orders/messaging/parse/ParsedPayloadListeners#onMixed(sig_cb303bd1). "
        "via tools/jackson/databind/json/JsonMapper#readValue at 0 hop(s); "
        "com/example/orders/proto/OrderProtos$OrderRequest# in "
        "com/acme/orders/messaging/parse/ParsedPayloadListeners#onMixed(sig_cb303bd1). "
        "via com/example/orders/proto/OrderProtos$OrderRequest#parseFrom at 0 hop(s)"
    ) in document

    # The protobuf-generated request shape's own field numbers, unobtrusive
    # beside the field name (2G design §8).
    assert "| totalAmount (1) | string | yes | no |" in document

    # metadata.json carries Task 4's two analyze-side gap lists the same way
    # `uncovered` already surfaces its own (FR-17) — empty here because the
    # fixture's schema sources all compile and interpret cleanly, which is
    # itself the honest answer, not an omission.
    metadata = json.loads((tmp_path / "metadata.json").read_text())
    assert metadata["schema_sources_not_compiled"] == []
    assert metadata["descriptors_not_interpreted"] == []

    # `open_questions` joined the D06 bundle and its manifest (2G design §8).
    runner = CliRunner()
    result = runner.invoke(cli, ["module", "export", str(FIXTURE), "--workspace", str(tmp_path)])
    assert result.exit_code == 0, result.output
    bundle = Path(result.output.strip())
    manifest = json.loads((bundle / "manifest.json").read_text())
    assert "open_questions" in manifest["contents"]["tables"]
    rows = duckdb.sql(
        f"SELECT count(*) FROM read_parquet('{bundle / 'graph' / 'open_questions.parquet'}')"
    ).fetchone()
    assert rows == (2,)
