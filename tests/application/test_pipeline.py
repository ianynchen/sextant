import json
import subprocess
from pathlib import Path

from shape_helpers import ORDER_REQUEST, ORDER_STATUS, shape_fields_of

from sextant.application.ports.catalogs import Catalog, CatalogSource
from sextant.application.ports.scanner import ScanRequest
from sextant.application.resolve.endpoints import SkippedCatalog
from sextant.application.resolve.pipeline import ResolveReport, resolve
from sextant.cli.resources import catalogs_dir, extractor_jar
from sextant.domain.closed_sets import OriginTier
from sextant.domain.factfile import write_fact_file
from sextant.domain.facts import Document
from sextant.ingress.catalogs.yaml_source import YamlCatalogSource
from sextant.ingress.extract.jvm.scanner import AsmScanner
from sextant.storage.duckdb.workspace import DuckDbWorkspace

REPO = Path(__file__).parents[2]
JAR = extractor_jar()
FIXTURE = REPO / "fixtures" / "orders-service"
CATALOGS = catalogs_dir()


class _Catalogs:
    """A CatalogSource over catalogs a test built by hand — the seam D02 §6
    exists for, used here so a test can put an invented catalog beside a
    shipped one without writing a YAML file."""

    def __init__(self, catalogs: list[Catalog]) -> None:
        self._catalogs = catalogs

    def load(self) -> list[Catalog]:
        return self._catalogs


def _resolved_fixture(
    tmp_path: Path, catalogs: CatalogSource | None = None
) -> tuple[DuckDbWorkspace, ResolveReport]:
    """Compile, scan and resolve the fixture — the whole path, on real
    bytecode. The workspace is handed back open: the rows the report points at
    are read from it, and closing it here would take them with it."""
    subprocess.run(["mvn", "-q", "-o", "compile"], cwd=FIXTURE, check=True)
    facts = tmp_path / "facts"
    AsmScanner(JAR).scan(
        ScanRequest(
            module_id="com.acme:orders-service",
            coordinates="com.acme/orders-service",
            version="1.0.0",
            classes_dir=FIXTURE / "target" / "classes",
            out_dir=facts,
        )
    )
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    report = resolve(
        workspace,
        facts,
        catalogs or YamlCatalogSource(CATALOGS),
        # Phase 2C: `call_site` and `string_constants` gate the RestTemplate
        # catalog (D02 §1's `single_call`); `chain_reconstruction` gates the
        # three `fluent` catalogs (WebClient/RestClient/OkHttp) — a real
        # subset of what `AsmScanner.capabilities()` actually declares, the
        # same way the other four capabilities here already are.
        {
            "annotation_args",
            "typed_signatures",
            "type_annotations",
            "call_site",
            "string_constants",
            "chain_reconstruction",
        },
    )
    return workspace, report


def _spring_web() -> Catalog:
    return next(c for c in YamlCatalogSource(CATALOGS).load() if c.id == "spring-web")


def test_resolve_finds_every_fixture_endpoint_exactly_once_when_run_end_to_end(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    _, report = resolved_fixture

    routes = {(e["method"], e["path"]) for e in report.endpoints}
    assert routes == {
        ("POST", "/v1/orders"),
        ("GET", "/v1/orders/{id}"),
        ("GET", "/v1/orders/{id}/{view}"),
        ("GET", "/v1/orders"),
        # The one endpoint whose request and response are both real payloads:
        # `OrderRequest` in, `ResponseEntity<OrderView>` out.
        ("POST", "/v1/orders/detailed"),
        # OrderPageController: a `@Controller`, not `@RestController` — the
        # spring-mvc catalog's own two routes, prefixed by its class-level
        # `@RequestMapping`.
        ("GET", "/orders"),
        ("POST", "/orders/new"),
        # LegacyOrderController: the pre-4.3 form, invisible until the mapping
        # declaration replaced one-annotation-per-method (D02 §2). The `path`
        # alias is read here too — reading `value` alone gave an empty path.
        ("GET", "/v1/legacy/orders"),
        ("PUT", "/v1/legacy/orders/{id}"),
        ("PATCH", "/v1/legacy/orders/{id}"),
        # `@RequestMapping` naming no method accepts every one of them, and each
        # is its own wire contract, so each is its own endpoint.
        *(
            (verb, "/v1/legacy/orders/any")
            for verb in ("GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "TRACE")
        ),
        # Outbound (Phase 2B): the client interfaces' declared calls.
        ("POST", "/billing/invoices"),
        ("GET", "/billing/invoices"),
        ("GET", "/v1/inventory/levels"),
        ("POST", "/v1/inventory/reserve"),
        ("GET", "legacy/invoices/{id}"),
        ("POST", "legacy/invoices"),
        # Outbound (Phase 2C): BillingRestTemplate's `single_call` surface —
        # one route per verb shape the spring-resttemplate catalog's
        # `methods` rows match on its own.
        ("GET", "/billing/balances/{id}"),
        ("POST", "/billing/settlements"),
        ("PUT", "/billing/settlements/{id}"),
        ("POST", "/billing/batch"),
        # Outbound (Phase 2C): the three `fluent` catalogs' reconstructed
        # chains. InventoryWebClient's `getLevels`/`history`/`search` each
        # derive their own row; `reserve` and `reserveAfterLevels`'s own
        # flatMap-lambda chain both derive `POST /v2/inventory/reserve` — the
        # same wire identity, so wire-identity dedup collapses them into one
        # row (asserted below); `reserveAfterLevels`'s own outer chain
        # reaches `bodyToMono` too, so it dedups into `getLevels`'s own
        # `GET /v2/inventory/levels` row rather than adding a tenth route.
        ("GET", "/v2/inventory/levels"),
        ("POST", "/v2/inventory/reserve"),
        ("GET", "/v2/inventory/history"),
        # `uri(uriBuilder -> …)`: the engine follows one hop from the lambda
        # argument and stops honestly rather than guessing the literal
        # inside the builder — `resolution`/`path` asserted below.
        ("GET", None),
        # OrdersRestClient — RestClient's synchronous twin.
        ("GET", "/v2/orders/mirror"),
        ("POST", "/v2/orders/mirror"),
        # LegacyOkHttp — `Request.Builder` split from `OkHttpClient.newCall`,
        # joined only through `terminal_via_argument`; both URLs are
        # absolute, so CP-2 splits them into `peer`+`path` (asserted below).
        ("GET", "/legacy/exports"),
        ("POST", "/legacy/exports"),
        # Inbound (Phase 2D, Task 10): the three listener catalogs.
        # `method` is always NULL — a listener declares no HTTP-style verb
        # (D02 §2, amended) — so every messaging route below shares that
        # first tuple element; no two of them share a `path` with each other
        # or with an HTTP route, so the set still tells every row apart.
        # OrderEventsListener's `onEvent` carries two topics in one
        # `@KafkaListener(topics = {...})` — two rows, one handler.
        (None, "order-events"),
        (None, "order-audit"),
        # `onReturn`: the reply-carrying listener (its own outbound row is
        # asserted separately below).
        (None, "order-returns"),
        # `onDeadLetter`: `topicPattern`, not `topics` — the pattern lands on
        # `path` verbatim, never expanded into real topic names.
        (None, "order-.*-dlq"),
        # `onBatch`: `List<OrderEvent>` — asserted below for its `wire_type`.
        (None, "order-batches"),
        # `escalate`: value-returning, no `@SendTo` — the dynamic-reply
        # listener; its own `unresolved` outbound row is `(None, None)`,
        # asserted separately below.
        (None, "order-escalations"),
        # `ClassLevelListener`: a class-level `@KafkaListener(topics =
        # "order-polymorphic")` plus two `@KafkaHandler` methods — TWO rows
        # share this one path (asserted below); the set still shows one
        # tuple, same as the two `get` overloads below share no path at all
        # but this pair does.
        (None, "order-polymorphic"),
        # AuditJmsListener: a converted payload and a raw `jakarta.jms.Message`
        # envelope (asserted below).
        (None, "audit.queue"),
        (None, "audit.raw"),
        # ShipmentsSqsListener.
        (None, "shipments-inbound"),
        # Outbound (Phase 2D, Task 10): `@SendTo`'s two reply shapes.
        # `onReturn`'s static `@SendTo("order-return-receipts")`.
        (None, "order-return-receipts"),
        # `escalate`'s dynamic reply: value-returning, no `@SendTo` at all —
        # `path` NULL, `unresolved` (asserted below). Also shared, from Task
        # 11 on, by `sendDefault`'s own NULL-path row, JmsTemplate's
        # destination-less `convertAndSend(event)`, and SqsTemplate's
        # builder-lambda `send` — every path-NULL messaging row renders the
        # same `(None, None)` tuple, so the SET gains no new entry for any
        # of them even though `len(report.endpoints)` does (asserted below).
        # 2E-prep Task 6 adds one more to this same tuple:
        # `RawKafkaMessageSender#send`'s `kafkaTemplate.send(Message<?>)` —
        # `spring-kafka-template.yml`'s pre-existing `send, arity: 1,
        # record_arg: 0` row matches it by name+arity alone (never argument
        # type) and degrades honestly to `(None, None)` since `Message`
        # carries no `record_wrappers` entry — checkpoint ruling after Task
        # 6 (spec §4, `docs/superpowers/plans/2026-08-31-2e-prep-hardening.md`:
        # "unresolved is an answer, never an omission"; duplicate
        # fluent-resolved + single_call-degraded rows for one call are
        # accepted and documented). Asserted on its own, by caller, below.
        (None, None),
        # Outbound (Phase 2D, Task 11): `kafka-clients.yml`'s raw
        # `KafkaProducer#send(ProducerRecord)` — `order-raw` has no inbound
        # counterpart, so it stays its own outbound row rather than merging.
        (None, "order-raw"),
        # Outbound (Phase 2D, Task 11): `SqsTemplate#send(queue, payload)` —
        # `shipments-outbound` is a different topic from the inbound
        # listener's own `shipments-inbound`, so no merge here either.
        (None, "shipments-outbound"),
        # Both (Phase 2D, Task 11): Pub/Sub's `publish`/`subscribeAndConvert`
        # share this identity — the ONLY messaging path Task 11 introduces on
        # both sides of the merge in the same task (every other Task 11
        # merge target — `order-events`/`order-audit`/`order-returns`/
        # `audit.queue` — already existed as an inbound row from Task 10).
        (None, "order-notifications"),
        # 2E-prep Task 11 (driver catalogs A): the raw-client sibling
        # catalogs — `jakarta-jms.yml`, `kafka-consumer.yml`,
        # `aws-sqs-sdk.yml` — none of whose routes merge with anything else
        # in the fixture (each is a genuinely new destination). JMS:
        # `RawJmsBridge#createAuditProducer`/`createIntakeConsumer`, read off
        # `Session#createQueue`'s own linked-call argument (`channel_via`).
        (None, "raw-audit"),
        (None, "raw-intake"),
        # Kafka: `RawKafkaConsumers#subscribeToTopics`'s one
        # `consumer.subscribe(List.of("raw-t1", "raw-t2"))` call derives two
        # rows off one handler — `channel_via`'s own `all_strings` form.
        (None, "raw-t1"),
        (None, "raw-t2"),
        # `subscribeToPattern`'s `consumer.subscribe(Pattern.compile(
        # "raw-.*"))` — the pattern lands on `path` verbatim, never expanded,
        # same rule every other `topicPattern`/`topic_pattern` row keeps.
        (None, "raw-.*"),
        # SQS: `RawSqsClientSender#send`'s fluent
        # `SendMessageRequest.builder().queueUrl(...).messageBody(body)
        # .build()` chain — the FIRST fluent catalog to derive a verbless
        # row (this task's own precondition commit). The queue URL is
        # absolute, so CP-2 splits it into peer + path exactly as OkHttp's
        # own absolute `Request.Builder#url` does — asserted below — a
        # deliberate contrast with every `channel_arg` destination
        # elsewhere in this file, which stays whole (`aws-sqs-sdk.yml`'s own
        # catalog comment states why: the fluent engine's `url` capture is
        # an HTTP-style URL by AWS's own builder API design, never an opaque
        # destination expression to keep verbatim).
        (None, "/123456789012/raw-queue"),
    }
    # One row per mapped method, not one per (method, same-named sibling) pair:
    # the fixture's two `get` overloads share a name, and a symbol that does not
    # disambiguate them (D00 §1) makes this join multiply instead of match.
    # POST /v1/orders is both a handler and a caller (OrdersLoopClient's
    # self-call): the outbound engine derives its own row for it, and the
    # D02 §3 merge folds that into the existing inbound row (direction
    # `both`) rather than keeping both, so the count is 18 inbound + 7
    # annotation-driven outbound + 4 single_call outbound rows + 8 fluent
    # outbound rows derived, minus the 1 that merges away — 36 — plus Task
    # 10's 13 messaging rows: 8 kafka inbound (`onEvent` on two topics,
    # `onDeadLetter`, `onBatch`, `escalate`, `onReturn`, and
    # `ClassLevelListener`'s two `@KafkaHandler` methods) + 2 jms inbound +
    # 1 sqs inbound + 2 kafka outbound replies — 49. `ClassLevelListener`'s
    # `onEvent`/`onDefault` share one wire identity (kafka, inbound, NULL,
    # `order-polymorphic`) and do NOT dedup to one row: `derive_endpoints.sql`'s
    # own insert-if-absent guard (D02 §5) only checks a new row against what
    # the table already held *before* this statement began — it was written
    # for cross-catalog duplicates, never for two method symbols the SAME
    # catalog's own single `INSERT ... SELECT` maps to one identity in one
    # pass — so both handlers' rows survive (asserted below). This is a real
    # divergence from an original expectation that they would dedup to one;
    # verified live against real bytecode rather than assumed.
    #
    # Task 11 adds 11 raw derived rows (5 kafka outbound — the two `send`
    # arities deduped to one `order-events` row, `order-audit` via the record
    # wrapper, `order-raw` via `kafka-clients.yml`'s own owner,
    # `order-returns` via `ReplyingKafkaTemplate`, and `sendDefault`'s
    # NULL-path row; 2 jms outbound — `audit.queue` and the destination-less
    # NULL-path row; 2 sqs outbound — `shipments-outbound` and the
    # builder-lambda NULL-path row; 1 pubsub outbound `publish` +
    # 1 pubsub inbound `subscribeAndConvert`), of which 5 immediately merge
    # into an ALREADY-EXISTING Task 10 inbound row (`order-events`,
    # `order-audit`, `order-returns`, `audit.queue`) or into a row derived in
    # this SAME pass (`order-notifications`, the one merge where both sides
    # are new) — `merge_endpoints.sql` deletes the outbound duplicate on
    # every one of those five, so the net gain is 11 - 5 = 6 rows: 49 + 6 =
    # 55. Verified live against real bytecode, not computed from the brief
    # alone.
    #
    # 2E-prep Task 6 (checkpoint ruling, 2026-08-30) adds a 56th: the fixture
    # gained `RawKafkaMessageSender#send`, whose `kafkaTemplate.send(
    # MessageBuilder.withPayload(event).setHeader(KafkaHeaders.TOPIC,
    # "raw-messages").build())` call is arity-1 `KafkaTemplate.send` — the
    # SAME shape `spring-kafka-template.yml`'s `send, arity: 1, record_arg:
    # 0` row already declared (predating this task) for
    # `send(ProducerRecord<K,V>)`. That row's own comment already
    # anticipated a `send(Message<?>)` caller landing here one day: matched
    # by name+arity alone, degraded to `(None, None)` since `Message` has no
    # `record_wrappers` entry. This is a NEW, distinct unresolved row (own
    # `caller`, doesn't merge with `sendDefault`'s) — spec §4's ruling is
    # that a call deriving more than one honest row (here: this
    # single_call-degraded one now, and Task 12's fluent-resolved
    # `"raw-messages"` sibling later) is accepted and documented, never
    # collapsed or suppressed. 55 + 1 = 56 is the TRUE frozen baseline for
    # this fixture from Task 6 on — the dispatch's original "count must stay
    # 55" was the controller's own error, corrected at the Task 6 checkpoint.
    #
    # 2E-prep Task 11 (driver catalogs A) adds 6 more, none of which merges
    # with anything already in the fixture — every one of these six routes
    # is a destination nothing else in the fixture ever names, so each is a
    # genuinely new row rather than a new caller/handler joining an existing
    # one: `jakarta-jms.yml`'s `raw-audit` (outbound) and `raw-intake`
    # (inbound), `kafka-consumer.yml`'s `raw-t1` + `raw-t2` (two rows off one
    # `subscribe(List.of(...))` call) and `raw-.*` (the pattern overload),
    # and `aws-sqs-sdk.yml`'s own verbless fluent row (the queue URL's own
    # path, after CP-2 splits off the peer). 56 + 6 = 62.
    assert len(report.endpoints) == 62
    assert report.skipped_catalogs == []

    directions = {(e["method"], e["path"]): e["direction"] for e in report.endpoints}
    assert directions[("POST", "/billing/invoices")] == "outbound"
    assert directions[("POST", "/v1/orders")] == "both"  # the self-call merged
    peers = {e["path"]: e["peer"] for e in report.endpoints if e["direction"] != "inbound"}
    assert peers["/billing/invoices"] == "billing"
    assert peers["/v1/inventory/levels"] is None  # base URL is builder code
    # CP-2: OkHttp's `url()` API forces an absolute URL, so its fixture rows
    # split into peer (the authority) and path (asserted in the route set
    # above), unlike every other outbound catalog's builder-code base URL.
    assert peers["/legacy/exports"] == "legacy.acme.internal"
    # 2E-prep Task 11: `aws-sqs-sdk.yml`'s `queueUrl(...)` capture is the
    # SAME CP-2 split — AWS's own builder API takes a full HTTP-style queue
    # URL, unlike every `channel_arg` destination elsewhere in this file.
    assert peers["/123456789012/raw-queue"] == "sqs.us-east-1.amazonaws.com"

    # The `uri(uriBuilder -> …)` chain: the engine only follows one hop off
    # the lambda argument, so the row still derives (a call was made) but
    # honestly as unresolved, path NULL — never a guess at the literal
    # inside the builder lambda.
    [search_row] = [
        e
        for e in report.endpoints
        if e["caller"] and e["caller"].endswith("InventoryWebClient#search(sig_e02a4703).")
    ]
    assert search_row["method"] == "GET"
    assert search_row["path"] is None
    assert search_row["resolution"] == "unresolved"

    # The flatMap lambda's own chain derives `POST /v2/inventory/reserve` in
    # its own synthetic method — the dataflow pass has to scan the
    # `lambda$reserveAfterLevels$N` method, not just the enclosing method, to
    # find it. Wire-identity dedup collapses it with `reserve()`'s own
    # identical row (D02 §5's `derive_call_endpoints.sql` contract); the row
    # that survives is whichever caller sorts first (`call_sites`' own
    # `caller, ordinal` order), which is the lambda's — asserted here rather
    # than assumed, so a resort silently changing this is caught. The numeric
    # suffix is javac's per-class lambda counter, which different compiler
    # versions assign in different orders, so only the stable stem is pinned.
    [reserve_row] = [
        e for e in report.endpoints if (e["method"], e["path"]) == ("POST", "/v2/inventory/reserve")
    ]
    assert "lambda$reserveAfterLevels$" in reserve_row["caller"]


# --- Task 10: the three listener catalogs, end to end, on real bytecode ---


def _messaging_rows(report: ResolveReport, protocol: str, path: str) -> list[dict]:
    return [e for e in report.endpoints if e["protocol"] == protocol and e["path"] == path]


def test_a_kafka_listeners_two_topics_derive_two_rows_off_one_handler(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """`@KafkaListener(topics = {"order-events", "order-audit"})` on `onEvent`
    — a `String[]` in bytecode even though the fixture's own multi-topic
    listener is written with braces (CHECKPOINT FACT) — derives one row per
    topic, both sharing `onEvent`'s own handler symbol and its excludes-
    filtered request shape (`OrderEvent`, not `Acknowledgment` — the second,
    bare parameter `sole_unannotated` would otherwise have matched too, had
    it not been excluded)."""
    _, report = resolved_fixture
    [events] = _messaging_rows(report, "kafka", "order-events")
    [audit] = _messaging_rows(report, "kafka", "order-audit")

    assert events["handler"] == audit["handler"]
    assert events["handler"].endswith("OrderEventsListener#onEvent(sig_cf042f06).")
    for row in (events, audit):
        assert json.loads(row["request_shape"])["shape_id"] == (
            "com/acme/orders/contracts/OrderEvent#"
        )
        assert row["response_shape"] is None


def test_a_batch_listeners_request_shape_is_an_array(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """`onBatch(List<OrderEvent> events)`: the checkpoint's own expectation is
    `wire_type: array`, exactly what this asserts — no `item` (which would
    name the array's own element shape) survives, because the extractor does
    not capture a *parameter*'s own generic type arguments the way it does a
    *return* type's (`OrderController#list`'s `List<OrderResult>` return, by
    contrast, does carry its element — see
    `test_an_endpoint_whose_response_is_a_collection_records_its_element_shape`
    above). A real, pre-existing scanner limitation this task's fixture is
    the first to expose (no earlier fixture ever put a generic type on a
    *parameter*), not something a catalog's own rules can work around —
    verified live rather than assumed, and left as an honest gap rather than
    worked around."""
    _, report = resolved_fixture
    [batch] = _messaging_rows(report, "kafka", "order-batches")

    descriptor = json.loads(batch["request_shape"])
    assert descriptor["wire_type"] == "array"
    assert "item" not in descriptor


def test_a_dead_letter_listeners_consumer_record_envelope_yields_no_request_shape(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """`onDeadLetter(ConsumerRecord<String, OrderEvent> record)`: the same
    erased-parameter-generics limitation as the batch row above means
    `ConsumerRecord`'s own type arguments never reach the signature, so the
    declared `{type: ..., payload_arg: 1, semantics: envelope}` wrapper rule
    finds nothing at its payload position — D02 §2a's "a declared envelope
    holding nothing at the payload position... is no payload either:
    describing the envelope would report a type the catalog already declares
    as one nobody could expand." The checkpoint's own expectation
    (`ConsumerRecord payload -> OrderEvent via payload_arg 1`) does not hold
    against this scanner's real output; this is that divergence, verified
    live and frozen honestly rather than guessed past."""
    _, report = resolved_fixture
    [dlq] = _messaging_rows(report, "kafka", "order-.*-dlq")

    assert dlq["path"] == "order-.*-dlq"  # the pattern lands on `path` verbatim
    assert dlq["request_shape"] is None


def test_a_class_level_kafka_listener_derives_one_row_per_handler_sharing_the_topic(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """`ClassLevelListener`'s class-level `@KafkaListener(topics =
    "order-polymorphic")` doubles as the `prefix_annotation`; each
    `@KafkaHandler` method (no path attribute of its own — path suffix '')
    picks up that prefix whole as its `path`. `onEvent` and `onDefault` (the
    `isDefault = true` handler) both derive, and do NOT dedup to one row —
    see the divergence note on the module-level row count above — so both
    survive as genuinely separate rows sharing one wire identity, each
    keeping its own handler and its own request shape (`OrderEvent` for the
    typed handler, `Object` for the default one)."""
    _, report = resolved_fixture
    rows = _messaging_rows(report, "kafka", "order-polymorphic")

    assert len(rows) == 2
    by_handler = {row["handler"].rsplit("#", 1)[1]: row for row in rows}
    assert set(by_handler) == {"onEvent(sig_b2a754d9).", "onDefault(sig_f286d6bd)."}
    assert json.loads(by_handler["onEvent(sig_b2a754d9)."]["request_shape"])["shape_id"] == (
        "com/acme/orders/contracts/OrderEvent#"
    )
    assert json.loads(by_handler["onDefault(sig_f286d6bd)."]["request_shape"])["shape_id"] == (
        "java/lang/Object#"
    )


def test_a_kafka_listeners_sendto_reply_derives_a_resolved_outbound_row(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """`onReturn`'s static `@SendTo("order-return-receipts")`: D02 §2's
    `reply` block derives a second, OUTBOUND row, `caller` the handler,
    `direction` outbound, payload the handler's own RETURN type
    (`ReceiptView`) — never its request shape, and never `None`, even though
    `onReturn`'s own method symbol is ALSO `handler` on the INBOUND
    `order-returns` row asserted above. Task 10 fix (`derive_endpoint_contracts.sql`):
    before it, the owner-keyed contracts update — keyed on
    `coalesce(handler, caller)`, a bare symbol — could not tell this row's
    own already-correct values apart from the SAME symbol's unrelated
    inbound contract, and silently overwrote them with it (`request_shape`
    became `onReturn`'s received `OrderEvent`, `response_shape` gained a
    value it should never carry at all). Pinned here against the real,
    resolved pipeline rather than only the hand-built facts `test_reply.py`
    uses, because that gap only exists once a reply row and its own
    handler's inbound row coexist in one real resolve."""
    _, report = resolved_fixture
    [reply] = [
        e
        for e in report.endpoints
        if e["protocol"] == "kafka"
        and e["direction"] == "outbound"
        and e["path"] == "order-return-receipts"
    ]

    assert reply["handler"] is None
    assert reply["caller"].endswith("OrderEventsListener#onReturn(sig_160f6bce).")
    assert reply["resolution"] == "resolved"
    assert json.loads(reply["request_shape"])["shape_id"] == (
        "com/acme/orders/contracts/ReceiptView#"
    )
    assert reply["response_shape"] is None


def test_a_value_returning_listener_with_no_sendto_derives_an_unresolved_reply_row(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """`escalate`: value-returning, no `@SendTo` at all — the reply
    destination is resolved at runtime (a `ReplyingKafkaTemplate` caller,
    off the record's own reply-topic header), never visible to the
    annotations this catalog reads. D02 §2's `reply` block still derives the
    row — `path` NULL, `unresolved` — rather than deriving nothing, because
    "this handler replies" is true and useful on its own even when the
    destination cannot be named."""
    _, report = resolved_fixture
    # Task 11 adds a second kafka outbound, path-NULL row (`sendDefault`'s
    # own unresolved-channel row) — both share `(kafka, outbound, NULL)`,
    # so `caller` alone (never wire identity, which is identical) tells this
    # reply row apart from that one.
    [reply] = [
        e
        for e in report.endpoints
        if e["protocol"] == "kafka"
        and e["direction"] == "outbound"
        and e["path"] is None
        and e["caller"] is not None
        and e["caller"].endswith("OrderEventsListener#escalate(sig_160f6bce).")
    ]

    # `caller` is not re-asserted here: the filter above already selects on
    # it, which would make a repeated assertion tautological (review round
    # 1, minor 9) — `resolution`/`request_shape`/`response_shape` below are
    # this test's own, non-guaranteed claims.
    assert reply["resolution"] == "unresolved"
    assert json.loads(reply["request_shape"])["shape_id"] == (
        "com/acme/orders/contracts/ReceiptView#"
    )
    assert reply["response_shape"] is None


def test_a_jms_listener_resolves_its_converted_payload(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """`onAudit(OrderEvent event)`: `@JmsListener.destination` is genuinely
    scalar in bytecode (unlike Kafka's `topics`), and the sole bare
    parameter resolves as the payload."""
    _, report = resolved_fixture
    [audit] = _messaging_rows(report, "jms", "audit.queue")

    assert json.loads(audit["request_shape"])["shape_id"] == (
        "com/acme/orders/contracts/OrderEvent#"
    )


def test_a_jms_listeners_raw_message_envelope_yields_no_request_shape(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """`onRaw(Message message)`: unlike Kafka's generic `ConsumerRecord<K,
    V>`, a raw `jakarta.jms.Message` carries no compile-time-typed payload
    at all — no wrapper rule could ever unwrap it to one. `spring-jms.yml`
    excludes `jakarta.jms.Message` alongside `jakarta.jms.Session` so its own
    `sole_unannotated` fallback never treats the opaque envelope itself as
    though it were the payload; the row still derives (the listener exists),
    only the request shape is honestly absent."""
    _, report = resolved_fixture
    [raw] = _messaging_rows(report, "jms", "audit.raw")

    assert raw["request_shape"] is None


def test_an_sqs_listener_resolves_its_payload(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """`onShipment(OrderEvent event)`: `@SqsListener.value` is always a
    `String[]` in bytecode, even for the fixture's own bare-string
    declaration (CHECKPOINT FACT) — same shape family as Kafka's `topics`."""
    _, report = resolved_fixture
    [shipment] = _messaging_rows(report, "sqs", "shipments-inbound")

    assert json.loads(shipment["request_shape"])["shape_id"] == (
        "com/acme/orders/contracts/OrderEvent#"
    )


def test_a_bare_unannotated_http_parameter_is_never_claimed_by_a_messaging_catalog(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """`LegacyOrderController#amend(long id)`: a bare, unannotated HTTP
    parameter that predates this task — `spring-mvc.yml` declares
    `fallback: none`, so it never claimed a body here. Task 10 fix (`_owns`,
    shapes/contracts.py): before scoping ownership by `protocol` as well as
    `direction`, whichever inbound messaging catalog sorted first
    (`spring-jms.yml`, alphabetically before `spring-mvc.yml`) matched this
    bare `long` as its OWN `sole_unannotated` body — an `http` row nothing
    in `spring-jms.yml`'s mapping ever produced. The 36 pre-Task-10 routes
    must be byte-identical; this is the row that would have silently
    diverged first."""
    _, report = resolved_fixture
    amend_rows = [
        e
        for e in report.endpoints
        if e["path"] == "/v1/legacy/orders/{id}" and e["method"] in ("PUT", "PATCH")
    ]

    assert len(amend_rows) == 2
    assert all(row["request_shape"] is None for row in amend_rows)


# --- Task 11: the producer catalogs, end to end, on real bytecode ---


def test_kafka_templates_two_send_arities_dedup_and_merge_into_the_listeners_row(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """`kafkaTemplate.send("order-events", event)` (arity 2) and
    `kafkaTemplate.sendKeyed("order-events", key, event)` (arity 3) both
    target the same topic: the two `methods` rows' own dedup key
    (`protocol, direction, verb or "", path`) collapses them to one derived
    outbound row before merging ever runs. That one row then merges with
    Task 10's own `order-events` INBOUND row (`OrderEventsListener#onEvent`)
    into `direction: both` — `merge_endpoints.sql` keeps the handler's own
    request shape (`OrderEvent`, from `onEvent`'s signature), not whatever
    the single_call engine derived off `event`'s own pass-through capture,
    and gains the caller from whichever of the two send calls sorts first."""
    _, report = resolved_fixture
    [row] = _messaging_rows(report, "kafka", "order-events")

    assert row["direction"] == "both"
    assert row["handler"].endswith("OrderEventsListener#onEvent(sig_cf042f06).")
    assert row["caller"].endswith("EventProducers#send(sig_b2a754d9).")
    assert json.loads(row["request_shape"])["shape_id"] == ("com/acme/orders/contracts/OrderEvent#")


def test_the_producer_records_channel_and_payload_come_from_its_own_constructor(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """`kafkaTemplate.send(new ProducerRecord<>("order-audit", event))`: the
    `record_wrappers` one-hop reads the topic and payload off the
    `ProducerRecord`'s own constructor call, not off `send`'s single
    argument (the record itself). `order-audit` also merges with Task 10's
    `onEvent` row (the SAME handler, its second `@KafkaListener` topic) —
    both, handler + caller, on the merged row."""
    _, report = resolved_fixture
    [row] = _messaging_rows(report, "kafka", "order-audit")

    assert row["direction"] == "both"
    assert row["handler"].endswith("OrderEventsListener#onEvent(sig_cf042f06).")
    assert row["caller"].endswith("EventProducers#sendAudit(sig_b2a754d9).")


def test_the_raw_kafka_producer_derives_its_own_unmerged_outbound_row(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """`rawProducer.send(new ProducerRecord<>("order-raw", key, event))`
    (`kafka-clients.yml`, owner `KafkaProducer` — a different owner type and
    a different detect coordinate from `KafkaTemplate`): `order-raw` has no
    inbound counterpart anywhere in the fixture, so it stays a genuine,
    standalone outbound row rather than merging. Both the record
    constructor's `key` and `event` arguments are themselves bare,
    pass-through parameters of `sendRaw(String key, OrderEvent event)` —
    D00 §5's `unresolved` kind, the same "passed straight through" capture
    failure `test_every_resttemplate_route_carries_its_own_resolution_and_descriptors`
    already pins for `BillingRestTemplate#submitSettlement` — so the
    row's own `resolution` is `unresolved` (I1: the declared payload capture
    failed) even though the topic itself, a literal in the constructor call,
    resolves the `path` cleanly. This is a genuine divergence from the
    brief's own shorthand ("resolved"), verified live rather than assumed —
    the SAME parameter-passthrough rule Phase 2C already established, not a
    new one."""
    _, report = resolved_fixture
    [row] = _messaging_rows(report, "kafka", "order-raw")

    assert row["direction"] == "outbound"
    assert row["handler"] is None
    assert row["caller"].endswith("EventProducers#sendRaw(sig_086ab63d).")
    assert row["resolution"] == "unresolved"
    assert row["request_shape"] is None


def test_the_replying_kafka_templates_send_and_receive_merges_with_its_listener(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """`replyingTemplate.sendAndReceive(new ProducerRecord<>("order-returns",
    event))` — `ReplyingKafkaTemplate` gets its own catalog file
    (`spring-kafka-replying.yml`), `matches.owner` being single-valued and
    `ReplyingKafkaTemplate` a different owner type from `KafkaTemplate`. No
    overload exposes the reply type at the call site, so this catalog
    declares no `response_arg` at all; merged with Task 10's own
    `order-returns` inbound row (`onReturn`), the surviving row keeps the
    handler's own contract (`OrderEvent` request, `ReceiptView` response —
    `onReturn`'s RETURN type, never the reply the `@SendTo` row already
    covers), plus the new caller from this task."""
    _, report = resolved_fixture
    [row] = _messaging_rows(report, "kafka", "order-returns")

    assert row["direction"] == "both"
    assert row["handler"].endswith("OrderEventsListener#onReturn(sig_160f6bce).")
    assert row["caller"].endswith("EventProducers#sendReturn(sig_b2a754d9).")
    assert json.loads(row["request_shape"])["shape_id"] == ("com/acme/orders/contracts/OrderEvent#")
    assert json.loads(row["response_shape"])["shape_id"] == (
        "com/acme/orders/contracts/ReceiptView#"
    )


def test_kafka_templates_send_default_derives_an_unresolved_null_path_row(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """`kafkaTemplate.sendDefault(event)`: no channel argument at the call
    site at all — the topic is the template's own config-borne default,
    2F's territory — so `sendDefault`'s `methods` row declares no
    `channel_arg`, and `url_of` reads the missing capture as `path: NULL,
    resolution: unresolved` (I1). The row still derives: "this method
    produces a message" is true and useful on its own."""
    _, report = resolved_fixture
    [row] = [
        e
        for e in report.endpoints
        if e["protocol"] == "kafka"
        and e["direction"] == "outbound"
        and e["path"] is None
        and e["caller"] is not None
        and e["caller"].endswith("EventProducers#sendDefault(sig_b2a754d9).")
    ]

    assert row["resolution"] == "unresolved"
    assert row["request_shape"] is None


def test_a_kafka_templates_message_send_derives_a_second_distinct_unresolved_row(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """`RawKafkaMessageSender#send`'s `kafkaTemplate.send(MessageBuilder
    .withPayload(event).setHeader(KafkaHeaders.TOPIC, "raw-messages")
    .build())` (2E-prep Task 6): `send(Message<?>)` is a THIRD arity-1
    `KafkaTemplate.send` overload, alongside `send(ProducerRecord<K,V>)` —
    `spring-kafka-template.yml`'s existing `send, arity: 1, record_arg: 0`
    row matches it by name+arity alone (never argument type), and
    `_record_arguments` degrades honestly to `(None, None)` since `Message`
    carries no `record_wrappers` entry of its own — `path` NULL,
    `resolution: unresolved` (I1), exactly as that row's own comment
    anticipated before this call existed anywhere in the fixture.

    This is a DIFFERENT row from `sendDefault`'s (test above): same wire
    identity (kafka, outbound, NULL path) but a different `caller`, so
    `derive_endpoints.sql`'s insert-if-absent guard does not fold them —
    both survive (checkpoint ruling after Task 6: 55 + 1 = 56 total
    endpoints). Spec §4's duplicate-row ruling
    (`docs/superpowers/plans/2026-08-31-2e-prep-hardening.md`: "unresolved
    is an answer, never an omission"; fluent-resolved + single_call-degraded
    rows for one call are accepted and documented) is why this is correct
    rather than a bug to paper over — Task 12's fluent catalog will later
    derive this SAME call's RESOLVED sibling row, reading `"raw-messages"`
    directly off the `MessageBuilder.setHeader(KafkaHeaders.TOPIC, ...)`
    chain; that row does not exist yet, only this degraded one does."""
    _, report = resolved_fixture
    [row] = [
        e
        for e in report.endpoints
        if e["protocol"] == "kafka"
        and e["direction"] == "outbound"
        and e["path"] is None
        and e["caller"] is not None
        and e["caller"].endswith("RawKafkaMessageSender#send(sig_b2a754d9).")
    ]

    assert row["resolution"] == "unresolved"
    assert row["request_shape"] is None


def test_a_jms_templates_destination_derives_and_merges_with_its_listener(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """`jmsTemplate.convertAndSend("audit.queue", event)` merges with Task
    10's own `AuditJmsListener#onAudit` inbound row into `direction: both`,
    keeping the handler's own converted-payload contract."""
    _, report = resolved_fixture
    [row] = _messaging_rows(report, "jms", "audit.queue")

    assert row["direction"] == "both"
    assert row["handler"].endswith("AuditJmsListener#onAudit(sig_b2a754d9).")
    assert row["caller"].endswith("EventProducers#sendAuditMessage(sig_b2a754d9).")
    assert json.loads(row["request_shape"])["shape_id"] == ("com/acme/orders/contracts/OrderEvent#")


def test_a_destination_less_jms_send_derives_an_unresolved_null_path_row(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """`jmsTemplate.convertAndSend(event)`: the destination-less overload
    targets the template's own configured default destination — no
    `channel_arg` declared for its `methods` row, same NULL-path shape as
    Kafka's `sendDefault`."""
    _, report = resolved_fixture
    [row] = [
        e
        for e in report.endpoints
        if e["protocol"] == "jms" and e["direction"] == "outbound" and e["path"] is None
    ]

    assert row["caller"].endswith("EventProducers#sendToDefaultDestination(sig_b2a754d9).")
    assert row["resolution"] == "unresolved"


def test_an_sqs_templates_send_derives_its_own_unmerged_outbound_row(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """`sqsTemplate.send("shipments-outbound", event)`: no inbound listener
    targets this topic (`ShipmentsSqsListener` listens on the different
    `shipments-inbound` queue), so the row stays outbound, unmerged. `event`
    is again a bare, pass-through parameter — the same `unresolved`-kind
    capture failure `order-raw` hits above — so the row's own `resolution`
    is `unresolved` (I1) even though the literal queue name resolves `path`
    cleanly. A genuine, live-verified divergence from the brief's own
    shorthand ("resolved"), frozen as observed."""
    _, report = resolved_fixture
    [row] = _messaging_rows(report, "sqs", "shipments-outbound")

    assert row["direction"] == "outbound"
    assert row["caller"].endswith("EventProducers#sendShipment(sig_b2a754d9).")
    assert row["resolution"] == "unresolved"
    assert row["request_shape"] is None


def test_the_sqs_builder_lambda_derives_an_honest_unresolved_row_not_a_fabricated_path(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """`sqsTemplate.send(to -> to.queue("shipments-lambda").payload(event))`:
    `SqsTemplate.send` has two arity-1 overloads (the destination-less
    `send(T)` and this builder-consumer `send(Consumer<SqsSendOptions<T>>)`)
    indistinguishable by name+arity alone, so the catalog declares NO
    `channel_arg` at all for arity 1 (review round 1, finding 3: declaring
    `channel_arg: 0` would be safe for THIS call — its arg 0 is a lambda —
    but would fabricate a resolved queue name for `send(T)`'s own
    destination-less form the moment some other caller passes a plain
    string payload, since arg 0 there genuinely IS the payload). The row
    still MATCHES (name+arity) and still derives — `_arg_at(arguments,
    None)` is `None` regardless of what kind arg 0 actually carries — `path:
    NULL, resolution: unresolved` unconditionally, for either overload.
    Verified directly against the real `call_sites` fact that THIS call
    site's own arg 0 carries `kind: lambda` (not assumed) — confirming the
    row derives the same honest answer either way, never the literal
    `"shipments-lambda"` string sitting inside the lambda body."""
    _, report = resolved_fixture
    [row] = [
        e
        for e in report.endpoints
        if e["protocol"] == "sqs" and e["direction"] == "outbound" and e["path"] is None
    ]

    assert row["caller"].endswith("EventProducers#sendShipmentViaBuilder(sig_b2a754d9).")
    assert row["resolution"] == "unresolved"
    assert row["request_shape"] is None


def test_pubsubs_publish_and_subscribe_share_one_file_and_merge_into_both(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """Pub/Sub's inbound and outbound rows ride the SAME `single_call` file
    (`spring-pubsub.yml`), unlike Kafka/JMS/SQS's separate listener/template
    catalogs — there is no standard Pub/Sub listener annotation, so the
    typed `subscribeAndConvert` row carries a per-row `direction: inbound`
    override inside an otherwise-outbound catalog. Both
    `pubSubTemplate.publish("order-notifications", event)` and
    `NotificationsSubscriber#subscribe`'s `subscribeAndConvert(...)` target
    the same topic, so they merge into ONE `both` row — the only Task 11
    merge where BOTH sides are new in this same task (every other merge
    target already existed as a Task 10 inbound row). The typed subscribe's
    own payload capture is its trailing `OrderEvent.class` literal, read at
    `body_arg` (review round 1, finding 1: an earlier draft read it into
    `response_arg` instead, which put the SUBSCRIBER'S received payload in
    `response_shape` — backwards, since a subscriber RECEIVES a request, the
    same D01 §3 column every other inbound messaging row's own payload
    lands in) — so it lands in `request_shape`, matching
    `spring-kafka.yml`/`spring-jms.yml`/`spring-sqs.yml`'s own inbound rows,
    never `response_shape`, on the surviving inbound-owned row."""
    _, report = resolved_fixture
    [row] = _messaging_rows(report, "pubsub", "order-notifications")

    assert row["direction"] == "both"
    assert row["handler"].endswith("NotificationsSubscriber#subscribe(sig_da8c82d5).")
    assert row["caller"].endswith("EventProducers#publishNotification(sig_b2a754d9).")
    assert row["resolution"] == "resolved"
    assert row["response_shape"] is None
    assert json.loads(row["request_shape"])["shape_id"] == ("com/acme/orders/contracts/OrderEvent#")


def test_a_catalogs_row_level_direction_override_is_still_owned_with_no_other_catalog_present(
    tmp_path: Path,
):
    """Review round 1, finding 2 (historical): `_owns` (shapes/contracts.py)
    used to check only `catalog.direction`, never a `single_call` row's own
    `direction` override — so `spring-pubsub.yml` (catalog-level `outbound`)
    never owned its OWN `order-notifications` `both` row, and harvested zero
    shape roots for it. In the real, full-catalog fixture run this bug
    produced no visible symptom: `OrderEvent` is already expanded by the
    time `spring-pubsub.yml`'s own turn comes, because Kafka/JMS/SQS's
    listener catalogs (sorted earlier among inbound catalogs) already
    reached it — masked by luck, exactly the review's own finding. Loading
    `spring-pubsub.yml` as the ONLY catalog removes that luck: `OrderEvent`
    has nowhere else to be expanded from, so a regression in ownership shows
    up as a dangling `request_shape` reference (Task 9 review, Finding C1)
    rather than staying hidden.

    Kept as a pin after 2E-prep's `catalog_id` collapse (`_owns` now reads
    `endpoint["catalog_id"] == catalog.id`, no direction reasoning at all,
    `_owned_directions` deleted): the merged `both` row keeps the inbound
    side's `catalog_id`, which with only `spring-pubsub.yml` loaded is this
    same catalog, so ownership stays trivially true and `OrderEvent` keeps a
    real `shapes` row behind it — proving the collapse didn't quietly
    reintroduce the masked-by-luck gap."""
    catalog = next(c for c in YamlCatalogSource(CATALOGS).load() if c.id == "spring-pubsub")
    workspace, report = _resolved_fixture(tmp_path, catalogs=_Catalogs([catalog]))
    [row] = [e for e in report.endpoints if e["path"] == "order-notifications"]
    shape_id = json.loads(row["request_shape"])["shape_id"]
    shapes = {s["shape_id"] for s in workspace.query("shapes")}
    workspace.close()

    assert row["direction"] == "both"
    assert shape_id in shapes


# --- 2E-prep Task 11: driver catalogs A — sqs-sdk, jakarta-jms,
# kafka-consumer, end to end, on real bytecode. None of these six rows
# merges with anything else in the fixture (each targets a destination
# nothing else in the fixture names), so every assertion below is about a
# genuinely new, standalone row.


def test_a_raw_jms_producer_registration_derives_a_resolved_outbound_row_with_no_payload(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """`RawJmsBridge#createAuditProducer`'s `session.createProducer(
    session.createQueue("raw-audit"))`: `jakarta-jms.yml`'s `channel_via`
    follows the queue instance back to its own creating `createQueue` call
    to read the destination, the same linked-call follow Task 7's
    `channel_via` already established. `Session#send` is deliberately not
    declared — a raw `jakarta.jms.Message` is as opaque here as it is to
    `spring-jms.yml`'s own listener-side `excludes` — so the PRODUCER
    REGISTRATION itself is the evidence a route exists, and the row's own
    payload is honestly absent rather than guessed."""
    _, report = resolved_fixture
    [row] = _messaging_rows(report, "jms", "raw-audit")

    assert row["direction"] == "outbound"
    assert row["handler"] is None
    assert row["caller"].endswith("RawJmsBridge#createAuditProducer(sig_ca3b0a33).")
    assert row["resolution"] == "resolved"
    assert row["request_shape"] is None


def test_a_raw_jms_consumer_registration_derives_a_resolved_inbound_row_with_no_payload(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """`RawJmsBridge#createIntakeConsumer`'s `session.createConsumer(
    session.createQueue("raw-intake"))` — the SAME `channel_via` form as the
    producer row above, only this row's own `methods` entry declares
    `direction: inbound`, so the deriving method lands in `handler`, not
    `caller` (D02 §2's per-row direction override, applied here for the
    first time on a catalog that is not otherwise entirely one direction)."""
    _, report = resolved_fixture
    [row] = _messaging_rows(report, "jms", "raw-intake")

    assert row["direction"] == "inbound"
    assert row["caller"] is None
    assert row["handler"].endswith("RawJmsBridge#createIntakeConsumer(sig_69833420).")
    assert row["resolution"] == "resolved"
    assert row["request_shape"] is None


def test_a_raw_kafka_consumers_topic_list_derives_two_rows_off_one_subscribe_call(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """`RawKafkaConsumers#subscribeToTopics`'s `consumer.subscribe(List.of(
    "raw-t1", "raw-t2"))`: `kafka-consumer.yml`'s `channel_via` reads the
    linked `List.of(...)` call's own `all_strings` positional arguments —
    one resolved row per topic, both sharing this one call's own handler.
    `subscribe` carries no payload capture, so, unlike `@KafkaListener`'s
    typed `ConsumerRecord<K, V>` parameter, the raw registration's own
    request shape is honestly absent."""
    _, report = resolved_fixture
    t1 = _messaging_rows(report, "kafka", "raw-t1")
    t2 = _messaging_rows(report, "kafka", "raw-t2")

    assert len(t1) == 1 and len(t2) == 1
    for row in (*t1, *t2):
        assert row["direction"] == "inbound"
        assert row["caller"] is None
        assert row["handler"].endswith("RawKafkaConsumers#subscribeToTopics(sig_da8c82d5).")
        assert row["resolution"] == "resolved"
        assert row["request_shape"] is None


def test_a_raw_kafka_consumers_pattern_subscribe_lands_the_pattern_on_path_verbatim(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """`RawKafkaConsumers#subscribeToPattern`'s `consumer.subscribe(
    Pattern.compile("raw-.*"))`: the `channel_via` form tried in this case is
    `Pattern.compile`'s own single `arg: 0`, never `all_strings` — the
    pattern reads onto `path` exactly as written, never expanded into real
    topic names, the same rule every `topicPattern`/`topic_pattern` row in
    this file already keeps."""
    _, report = resolved_fixture
    [row] = _messaging_rows(report, "kafka", "raw-.*")

    assert row["direction"] == "inbound"
    assert row["handler"].endswith("RawKafkaConsumers#subscribeToPattern(sig_da8c82d5).")
    assert row["resolution"] == "resolved"
    assert row["request_shape"] is None


def test_the_raw_sqs_sdk_builder_chain_splits_its_absolute_queue_url_but_reads_unresolved(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """`RawSqsClientSender#send`'s `SendMessageRequest.builder().queueUrl(
    "https://sqs.us-east-1.amazonaws.com/123456789012/raw-queue")
    .messageBody(body).build()`, joined to `SqsClient#sendMessage` through
    `terminal_via_argument` (the same CHECKCAST-linked join OkHttp's own
    `build()` → `newCall()` split established, `Builder.build()` erasing to
    `()Ljava/lang/Object;`): the FIRST verbless fluent row this codebase
    derives (this task's own precondition commit) — `method` is NULL, and
    the queue URL, an absolute HTTP-style URL by AWS's own builder API
    design, splits via CP-2 into peer (asserted separately, in the main
    end-to-end test above) and this row's own `path`.

    `messageBody(body)` captures `body` off `send`'s OWN parameter — a bare,
    pass-through `String`, D00 §5's `unresolved` kind, the exact same
    parameter-passthrough shape `order-raw`/`shipments-outbound` already hit
    in Task 11's producer catalogs. So even though the url itself resolves
    cleanly, the row's own `resolution` reads `unresolved` (I1: a DECLARED
    capture — `messageBody` was reached — that failed to read drops the
    row), and `request_shape` stays honestly absent: a genuine, live-verified
    divergence from the brief's own shorthand, frozen as observed rather
    than assumed."""
    _, report = resolved_fixture
    [row] = _messaging_rows(report, "sqs", "/123456789012/raw-queue")

    assert row["direction"] == "outbound"
    assert row["method"] is None
    assert row["handler"] is None
    assert row["caller"].endswith("RawSqsClientSender#send(sig_a7421bf5).")
    assert row["peer"] == "sqs.us-east-1.amazonaws.com"
    assert row["resolution"] == "unresolved"
    assert row["request_shape"] is None


def test_an_endpoint_carries_the_request_and_response_shapes_it_declares(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    workspace, report = resolved_fixture
    endpoint = next(
        e for e in report.endpoints if e["method"] == "POST" and e["path"] == "/v1/orders/detailed"
    )

    assert json.loads(endpoint["request_shape"]) == {
        "nullable": True,
        "shape_id": "com/acme/orders/contracts/OrderRequest#",
        "wire_format": "",
        "wire_type": "object",
    }
    fields = shape_fields_of(workspace, json.loads(endpoint["request_shape"])["shape_id"])
    assert "customer_id" in [f["wire_name"] for f in fields]
    # The response is a declared envelope around the payload; the shape must
    # root at what the envelope holds, or the wrapper declarations did nothing.
    assert json.loads(endpoint["response_shape"])["shape_id"] == (
        "com/acme/orders/contracts/OrderView#"
    )


def test_an_endpoint_whose_response_is_a_collection_records_its_element_shape(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """List<OrderResult> was 2A's parked gap: the endpoint said nothing at
    all. The descriptor keeps the array-ness — it IS the wire contract — and
    points at the element's shape, all the way through on real bytecode."""
    _, report = resolved_fixture
    listing = next(
        e for e in report.endpoints if e["path"] == "/v1/orders" and e["method"] == "GET"
    )

    descriptor = json.loads(listing["response_shape"])
    assert descriptor["wire_type"] == "array"
    assert descriptor["item"]["shape_id"] == "com/acme/orders/OrderResult#"


def test_an_outbound_endpoints_collection_response_resolves_to_the_real_client_interface(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """BillingClient's `List<OrderView> ...` is Phase 2B's outbound payoff:
    the Feign catalog derives the *route* — on real bytecode, no other
    catalog's annotations match `@FeignClient`/`@GetMapping` here. Which
    outbound catalog's rules go on to compute the *descriptor* is not
    pinned down by this route (Task 7 review, Finding 1: ownership is
    direction-scoped, not catalog-scoped, so any outbound catalog may
    answer any outbound row) — moot for this one, since a bare `List` needs
    no wrapper any of the three outbound catalogs declares differently. What
    this test actually exercises end to end is the collection-descriptor
    path itself, on an outbound row, on real bytecode — the same path that
    already serves inbound endpoints, now proven to reach one the module
    calls rather than exposes."""
    _, report = resolved_fixture
    invoices = next(
        e for e in report.endpoints if e["method"] == "GET" and e["path"] == "/billing/invoices"
    )

    descriptor = json.loads(invoices["response_shape"])
    assert descriptor["wire_type"] == "array"
    assert descriptor["item"]["shape_id"] == "com/acme/orders/contracts/OrderView#"


def test_the_resttemplate_exchange_row_carries_the_http_entity_and_ptr_descriptors(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """`single_call` (Task 9), on real bytecode: `exchange`'s verb is an
    `enum` argument, never a string (D00 §5), its body is built inline as
    `new HttpEntity<>(new OrderRequest())` — D02 §2h's one-hop follow — and
    its response is a `ParameterizedTypeReference<List<OrderView>>` anonymous
    subclass — D02 §2h's PTR follow through the type's own declared
    supertype. All three resolve off the call site's own arguments; nothing
    here comes from a handler signature, because this row has none."""
    _, report = resolved_fixture
    batch = next(
        e for e in report.endpoints if e["method"] == "POST" and e["path"] == "/billing/batch"
    )

    assert batch["direction"] == "outbound"
    assert batch["handler"] is None
    assert batch["resolution"] == "resolved"
    assert json.loads(batch["request_shape"])["shape_id"] == (
        "com/acme/orders/contracts/OrderRequest#"
    )
    response = json.loads(batch["response_shape"])
    assert response["wire_type"] == "array"
    assert response["item"]["shape_id"] == "com/acme/orders/contracts/OrderView#"


def test_every_resttemplate_route_carries_its_own_resolution_and_descriptors(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """Task 9 review, Finding I3: `/billing/batch` was the only RestTemplate
    row with an asserted descriptor; the other three routes' live-run
    listings were pinned by no test at all. On real bytecode, respecting
    checkpoint ruling I1 (Finding I1):

    - `getBalance`'s response is a bare class literal (`OrderView.class`) —
      `resolved`, no body declared at all (a genuine no-body call, not a
      failure), a real response descriptor.
    - `submitSettlement`'s `settlement` parameter is passed straight
      through, never a literal or a `NEW`, so the scanner records it
      `unresolved` (D00 §5) even though the url is a plain string — the row
      itself is therefore `unresolved` (I1), `request_shape` stays NULL
      (could-not-read, not no-payload), and `response_shape` — a
      *different*, independently resolved capture on the very same row —
      still carries its real descriptor.
    - `updateSettlement` (`put`) has the identical `settlement` failure on
      its body, and declares no `response_arg` at all: `unresolved` for the
      same reason, `request_shape` NULL (could-not-read), `response_shape`
      NULL for the ordinary reason (no capture ever named one).
    """
    _, report = resolved_fixture
    by_route = {(e["method"], e["path"]): e for e in report.endpoints}

    balances = by_route[("GET", "/billing/balances/{id}")]
    assert balances["resolution"] == "resolved"
    assert balances["request_shape"] is None
    assert json.loads(balances["response_shape"]) == {
        "wire_type": "object",
        "wire_format": "",
        "nullable": True,
        "shape_id": "com/acme/orders/contracts/OrderView#",
    }

    settlements = by_route[("POST", "/billing/settlements")]
    assert settlements["resolution"] == "unresolved"
    assert settlements["request_shape"] is None
    assert json.loads(settlements["response_shape"]) == {
        "wire_type": "object",
        "wire_format": "",
        "nullable": True,
        "shape_id": "com/acme/orders/contracts/OrderView#",
    }

    update = by_route[("PUT", "/billing/settlements/{id}")]
    assert update["resolution"] == "unresolved"
    assert update["request_shape"] is None
    assert update["response_shape"] is None


def test_a_scalar_response_is_recorded_rather_than_dropped(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """A server-rendered view name has no field list to compare, but NULL is
    reserved for exactly one meaning — no payload — so a scalar response is a
    real contract, recorded rather than silently dropped (D01 §5)."""
    _, report = resolved_fixture
    rendered = next(e for e in report.endpoints if e["path"] == "/orders" and e["method"] == "GET")

    assert json.loads(rendered["response_shape"])["wire_type"] == "string"
    # Nothing annotated the request body either, so there is no root at all.
    assert rendered["request_shape"] is None


def test_only_the_fixtures_payload_fields_reach_the_request_contract(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """On real bytecode, the whole way through. Every field of the fixture's
    request class is public and typed; what separates a contract term from a
    constant bound to the type or a field declared not serialized is nothing
    the shape pass can see for itself — so a regression anywhere along the
    chain publishes a contract nobody wrote, and D02 §4 makes the fixture the
    place that is caught."""
    workspace, _ = resolved_fixture
    names = [f["wire_name"] for f in shape_fields_of(workspace, ORDER_REQUEST)]

    assert "SOURCE" not in names
    assert "cachedSummary" not in names
    # The fields that are on the wire are all still there, in declaration order.
    assert names == [
        "reference",
        "note",
        "customer_id",
        "note2",
        "customer",
        "alternates",
        "total",
        "total_amount",
        "status",
    ]


def test_an_enumeration_typed_field_is_mapped_rather_than_expanded(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """`OrderStatus` is scanned like any other contract type, and expanding it
    structurally would put `NEW` and `DONE` on the wire as payload fields.
    D00 §5b keeps `enum` in the vocabulary so the whole type is one value."""
    workspace, report = resolved_fixture
    status = next(
        f for f in shape_fields_of(workspace, ORDER_REQUEST) if f["wire_name"] == "status"
    )
    shapes = [s["shape_id"] for s in workspace.query("shapes")]

    assert status["wire_type"] == "enum"
    assert ORDER_STATUS not in shapes
    # Nothing is missing from the catalog, so nothing is reported: the gap list
    # is only useful while everything on it is actionable.
    assert ORDER_STATUS not in report.unexpanded_types


def test_the_report_names_the_types_expansion_could_not_open(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """A catalog grows from observation, so a type nothing could expand is
    reported by name (FR-17) — a count cannot be acted on."""
    _, report = resolved_fixture

    assert "org/springframework/http/HttpHeaders#" in report.unexpanded_types
    assert [s["shape_id"] for s in report.shapes]


def test_a_catalog_skipped_by_capability_gating_contributes_no_shapes(tmp_path: Path):
    """The shape pass gates on exactly what the endpoint pass gates on. This
    catalog runs first and would rename nothing and ignore nothing, so if it
    reached the payload at all it would settle `OrderRequest` with its source
    field names — a shape produced by a catalog the run already reported as
    skipped."""
    ungated = Catalog(
        **{
            **vars(_spring_web()),
            "id": "invented-demanding",
            "requires": ("constant_propagation",),
            "serialization": {},
        }
    )
    workspace, report = _resolved_fixture(tmp_path, _Catalogs([ungated, _spring_web()]))
    names = [f["wire_name"] for f in shape_fields_of(workspace, ORDER_REQUEST)]
    workspace.close()

    assert SkippedCatalog("invented-demanding", ("constant_propagation",)) in (
        report.skipped_catalogs
    )
    assert "customer_id" in names
    assert "internalTrace" not in names


def test_a_catalog_that_names_no_request_body_rule_claims_no_request_shape(
    tmp_path: Path,
):
    """Which annotation marks the request payload is framework knowledge, so a
    catalog that declares none contributes no request shapes — inferring one
    from a parameter's position would be a guess presented as an observation."""
    silent = Catalog(
        **{
            **vars(_spring_web()),
            "matches": {
                key: value for key, value in _spring_web().matches.items() if key != "request_body"
            },
        }
    )
    workspace, report = _resolved_fixture(tmp_path, _Catalogs([silent]))
    workspace.close()
    endpoint = next(e for e in report.endpoints if e["path"] == "/v1/orders/detailed")

    assert endpoint["request_shape"] is None
    # The response is rooted from the return type, which no catalog field
    # names, so it is unaffected.
    assert json.loads(endpoint["response_shape"])["shape_id"] == (
        "com/acme/orders/contracts/OrderView#"
    )


def test_two_runs_agree_on_every_shape_and_every_field(tmp_path: Path):
    """`content_hash` is derived from the ordered field list, so two runs that
    disagree on field order are two different answers about the same type
    (NFR-1) — and DR-5 compares the answer, not the type. `endpoints` carries
    the same requirement: the `endpoints` query's own ORDER BY (2D's `caller`
    tiebreak) is what makes two ties-full runs agree on row order, not
    happenstance insert order."""
    first, second = _resolved_fixture(tmp_path / "one"), _resolved_fixture(tmp_path / "two")

    assert first[0].query("shapes") == second[0].query("shapes")
    assert first[0].query("shape_fields") == second[0].query("shape_fields")
    assert first[0].query("endpoints") == second[0].query("endpoints")
    assert first[1].unexpanded_types == second[1].unexpanded_types
    first[0].close()
    second[0].close()


def test_resolve_reports_the_skip_instead_of_crashing_when_no_catalog_is_satisfied(
    tmp_path: Path,
):
    """A weaker scanner must degrade visibly: when capability gating skips
    every catalog, resolve() still returns a ResolveReport naming what was
    skipped and why, rather than raising because the endpoints table was
    never derived (the one path capability gating exists to protect)."""
    facts = tmp_path / "facts"
    document = Document(
        document_id="doc_1",
        relative_path="com/acme/orders/OrderController.java",
        module_id="com.acme:orders-service",
        language="java",
        sextant_version="0.1.0",
        fact_schema_version="1.0.0",
        scanner_id="asm",
        scanner_version="9.7",
        content_hash="sha256:a",
        origin_entry="target/classes",
        origin_tier=OriginTier.MODULE_OUTPUT,
        redaction_set_hash="sha256:b",
    )
    write_fact_file(facts / "OrderController.jsonl", document, [])
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    report = resolve(workspace, facts, YamlCatalogSource(CATALOGS), {"typed_signatures"})
    workspace.close()

    assert report.endpoints == []
    assert (
        SkippedCatalog("spring-web", ("annotation_args", "type_annotations"))
        in report.skipped_catalogs
    )
