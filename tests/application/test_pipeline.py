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


def test_resolve_finds_every_fixture_endpoint_exactly_once_when_run_end_to_end(tmp_path: Path):
    workspace, report = _resolved_fixture(tmp_path)
    workspace.close()

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
        # `path` NULL, `unresolved` (asserted below).
        (None, None),
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
    assert len(report.endpoints) == 49
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


def test_a_kafka_listeners_two_topics_derive_two_rows_off_one_handler(tmp_path: Path):
    """`@KafkaListener(topics = {"order-events", "order-audit"})` on `onEvent`
    — a `String[]` in bytecode even though the fixture's own multi-topic
    listener is written with braces (CHECKPOINT FACT) — derives one row per
    topic, both sharing `onEvent`'s own handler symbol and its excludes-
    filtered request shape (`OrderEvent`, not `Acknowledgment` — the second,
    bare parameter `sole_unannotated` would otherwise have matched too, had
    it not been excluded)."""
    workspace, report = _resolved_fixture(tmp_path)
    workspace.close()
    [events] = _messaging_rows(report, "kafka", "order-events")
    [audit] = _messaging_rows(report, "kafka", "order-audit")

    assert events["handler"] == audit["handler"]
    assert events["handler"].endswith("OrderEventsListener#onEvent(sig_cf042f06).")
    for row in (events, audit):
        assert json.loads(row["request_shape"])["shape_id"] == (
            "com/acme/orders/contracts/OrderEvent#"
        )
        assert row["response_shape"] is None


def test_a_batch_listeners_request_shape_is_an_array(tmp_path: Path):
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
    workspace, report = _resolved_fixture(tmp_path)
    workspace.close()
    [batch] = _messaging_rows(report, "kafka", "order-batches")

    descriptor = json.loads(batch["request_shape"])
    assert descriptor["wire_type"] == "array"
    assert "item" not in descriptor


def test_a_dead_letter_listeners_consumer_record_envelope_yields_no_request_shape(
    tmp_path: Path,
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
    workspace, report = _resolved_fixture(tmp_path)
    workspace.close()
    [dlq] = _messaging_rows(report, "kafka", "order-.*-dlq")

    assert dlq["path"] == "order-.*-dlq"  # the pattern lands on `path` verbatim
    assert dlq["request_shape"] is None


def test_a_class_level_kafka_listener_derives_one_row_per_handler_sharing_the_topic(
    tmp_path: Path,
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
    workspace, report = _resolved_fixture(tmp_path)
    workspace.close()
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


def test_a_kafka_listeners_sendto_reply_derives_a_resolved_outbound_row(tmp_path: Path):
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
    workspace, report = _resolved_fixture(tmp_path)
    workspace.close()
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
    tmp_path: Path,
):
    """`escalate`: value-returning, no `@SendTo` at all — the reply
    destination is resolved at runtime (a `ReplyingKafkaTemplate` caller,
    off the record's own reply-topic header), never visible to the
    annotations this catalog reads. D02 §2's `reply` block still derives the
    row — `path` NULL, `unresolved` — rather than deriving nothing, because
    "this handler replies" is true and useful on its own even when the
    destination cannot be named."""
    workspace, report = _resolved_fixture(tmp_path)
    workspace.close()
    [reply] = [
        e
        for e in report.endpoints
        if e["protocol"] == "kafka" and e["direction"] == "outbound" and e["path"] is None
    ]

    assert reply["caller"].endswith("OrderEventsListener#escalate(sig_160f6bce).")
    assert reply["resolution"] == "unresolved"
    assert json.loads(reply["request_shape"])["shape_id"] == (
        "com/acme/orders/contracts/ReceiptView#"
    )
    assert reply["response_shape"] is None


def test_a_jms_listener_resolves_its_converted_payload(tmp_path: Path):
    """`onAudit(OrderEvent event)`: `@JmsListener.destination` is genuinely
    scalar in bytecode (unlike Kafka's `topics`), and the sole bare
    parameter resolves as the payload."""
    workspace, report = _resolved_fixture(tmp_path)
    workspace.close()
    [audit] = _messaging_rows(report, "jms", "audit.queue")

    assert json.loads(audit["request_shape"])["shape_id"] == (
        "com/acme/orders/contracts/OrderEvent#"
    )


def test_a_jms_listeners_raw_message_envelope_yields_no_request_shape(tmp_path: Path):
    """`onRaw(Message message)`: unlike Kafka's generic `ConsumerRecord<K,
    V>`, a raw `jakarta.jms.Message` carries no compile-time-typed payload
    at all — no wrapper rule could ever unwrap it to one. `spring-jms.yml`
    excludes `jakarta.jms.Message` alongside `jakarta.jms.Session` so its own
    `sole_unannotated` fallback never treats the opaque envelope itself as
    though it were the payload; the row still derives (the listener exists),
    only the request shape is honestly absent."""
    workspace, report = _resolved_fixture(tmp_path)
    workspace.close()
    [raw] = _messaging_rows(report, "jms", "audit.raw")

    assert raw["request_shape"] is None


def test_an_sqs_listener_resolves_its_payload(tmp_path: Path):
    """`onShipment(OrderEvent event)`: `@SqsListener.value` is always a
    `String[]` in bytecode, even for the fixture's own bare-string
    declaration (CHECKPOINT FACT) — same shape family as Kafka's `topics`."""
    workspace, report = _resolved_fixture(tmp_path)
    workspace.close()
    [shipment] = _messaging_rows(report, "sqs", "shipments-inbound")

    assert json.loads(shipment["request_shape"])["shape_id"] == (
        "com/acme/orders/contracts/OrderEvent#"
    )


def test_a_bare_unannotated_http_parameter_is_never_claimed_by_a_messaging_catalog(
    tmp_path: Path,
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
    workspace, report = _resolved_fixture(tmp_path)
    workspace.close()
    amend_rows = [
        e
        for e in report.endpoints
        if e["path"] == "/v1/legacy/orders/{id}" and e["method"] in ("PUT", "PATCH")
    ]

    assert len(amend_rows) == 2
    assert all(row["request_shape"] is None for row in amend_rows)


def test_an_endpoint_carries_the_request_and_response_shapes_it_declares(tmp_path: Path):
    workspace, report = _resolved_fixture(tmp_path)
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
    workspace.close()


def test_an_endpoint_whose_response_is_a_collection_records_its_element_shape(tmp_path: Path):
    """List<OrderResult> was 2A's parked gap: the endpoint said nothing at
    all. The descriptor keeps the array-ness — it IS the wire contract — and
    points at the element's shape, all the way through on real bytecode."""
    workspace, report = _resolved_fixture(tmp_path)
    workspace.close()
    listing = next(
        e for e in report.endpoints if e["path"] == "/v1/orders" and e["method"] == "GET"
    )

    descriptor = json.loads(listing["response_shape"])
    assert descriptor["wire_type"] == "array"
    assert descriptor["item"]["shape_id"] == "com/acme/orders/OrderResult#"


def test_an_outbound_endpoints_collection_response_resolves_to_the_real_client_interface(
    tmp_path: Path,
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
    workspace, report = _resolved_fixture(tmp_path)
    workspace.close()
    invoices = next(
        e for e in report.endpoints if e["method"] == "GET" and e["path"] == "/billing/invoices"
    )

    descriptor = json.loads(invoices["response_shape"])
    assert descriptor["wire_type"] == "array"
    assert descriptor["item"]["shape_id"] == "com/acme/orders/contracts/OrderView#"


def test_the_resttemplate_exchange_row_carries_the_http_entity_and_ptr_descriptors(
    tmp_path: Path,
):
    """`single_call` (Task 9), on real bytecode: `exchange`'s verb is an
    `enum` argument, never a string (D00 §5), its body is built inline as
    `new HttpEntity<>(new OrderRequest())` — D02 §2h's one-hop follow — and
    its response is a `ParameterizedTypeReference<List<OrderView>>` anonymous
    subclass — D02 §2h's PTR follow through the type's own declared
    supertype. All three resolve off the call site's own arguments; nothing
    here comes from a handler signature, because this row has none."""
    workspace, report = _resolved_fixture(tmp_path)
    workspace.close()
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
    tmp_path: Path,
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
    workspace, report = _resolved_fixture(tmp_path)
    workspace.close()
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


def test_a_scalar_response_is_recorded_rather_than_dropped(tmp_path: Path):
    """A server-rendered view name has no field list to compare, but NULL is
    reserved for exactly one meaning — no payload — so a scalar response is a
    real contract, recorded rather than silently dropped (D01 §5)."""
    workspace, report = _resolved_fixture(tmp_path)
    workspace.close()
    rendered = next(e for e in report.endpoints if e["path"] == "/orders" and e["method"] == "GET")

    assert json.loads(rendered["response_shape"])["wire_type"] == "string"
    # Nothing annotated the request body either, so there is no root at all.
    assert rendered["request_shape"] is None


def test_only_the_fixtures_payload_fields_reach_the_request_contract(tmp_path: Path):
    """On real bytecode, the whole way through. Every field of the fixture's
    request class is public and typed; what separates a contract term from a
    constant bound to the type or a field declared not serialized is nothing
    the shape pass can see for itself — so a regression anywhere along the
    chain publishes a contract nobody wrote, and D02 §4 makes the fixture the
    place that is caught."""
    workspace, _ = _resolved_fixture(tmp_path)
    names = [f["wire_name"] for f in shape_fields_of(workspace, ORDER_REQUEST)]
    workspace.close()

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


def test_an_enumeration_typed_field_is_mapped_rather_than_expanded(tmp_path: Path):
    """`OrderStatus` is scanned like any other contract type, and expanding it
    structurally would put `NEW` and `DONE` on the wire as payload fields.
    D00 §5b keeps `enum` in the vocabulary so the whole type is one value."""
    workspace, report = _resolved_fixture(tmp_path)
    status = next(
        f for f in shape_fields_of(workspace, ORDER_REQUEST) if f["wire_name"] == "status"
    )
    shapes = [s["shape_id"] for s in workspace.query("shapes")]
    workspace.close()

    assert status["wire_type"] == "enum"
    assert ORDER_STATUS not in shapes
    # Nothing is missing from the catalog, so nothing is reported: the gap list
    # is only useful while everything on it is actionable.
    assert ORDER_STATUS not in report.unexpanded_types


def test_the_report_names_the_types_expansion_could_not_open(tmp_path: Path):
    """A catalog grows from observation, so a type nothing could expand is
    reported by name (FR-17) — a count cannot be acted on."""
    workspace, report = _resolved_fixture(tmp_path)
    workspace.close()

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
    (NFR-1) — and DR-5 compares the answer, not the type."""
    first, second = _resolved_fixture(tmp_path / "one"), _resolved_fixture(tmp_path / "two")

    assert first[0].query("shapes") == second[0].query("shapes")
    assert first[0].query("shape_fields") == second[0].query("shape_fields")
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
