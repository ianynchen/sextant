import json
from pathlib import Path

from sextant.application.ports.scanner import ScanRequest
from sextant.cli.resources import extractor_jar
from sextant.ingress.extract.jvm.scanner import AsmScanner

REPO = Path(__file__).parents[2]
JAR = extractor_jar()
CLASSES = REPO / "fixtures" / "orders-service" / "target" / "classes"


def test_scanner_accepts_java_and_kotlin_but_not_python():
    scanner = AsmScanner(JAR)
    assert scanner.accepts({"java"}) and scanner.accepts({"kotlin"})
    assert not scanner.accepts({"python"})


def test_scan_writes_one_fact_file_per_class_file_when_run_on_the_fixture(tmp_path: Path):
    """One class file is one document (D00 §2), a nested class's own file
    included — so the file is named after the class, not after the source it
    was compiled from. Naming it after the source would put `OrderResult` and
    `OrderResult$Detail` on one path and leave only the last one written."""
    scanner = AsmScanner(JAR)
    report = scanner.scan(
        ScanRequest(
            module_id="com.acme:orders",
            coordinates="com.acme/orders",
            version="1.0.0",
            classes_dir=CLASSES,
            out_dir=tmp_path,
        )
    )
    written = sorted(p.name for p in tmp_path.rglob("*.jsonl"))
    assert written == [
        "ApiGet.jsonl",
        "AuditEvent$Builder.jsonl",
        "AuditEvent.jsonl",
        "AuditJmsListener.jsonl",
        "BillingClient.jsonl",
        "BillingClients$BillingProperties.jsonl",
        "BillingClients.jsonl",
        "BillingRestTemplate$1.jsonl",
        "BillingRestTemplate.jsonl",
        "ClassLevelListener.jsonl",
        "CommonProtos$Money$1.jsonl",
        "CommonProtos$Money$Builder.jsonl",
        "CommonProtos$Money.jsonl",
        "CommonProtos$MoneyOrBuilder.jsonl",
        "CommonProtos.jsonl",
        "ComposedController.jsonl",
        "ComposedListener.jsonl",
        "CustomerRef.jsonl",
        "DetailedOrderResult.jsonl",
        "DgsOrderFetcher.jsonl",
        "EventProducers.jsonl",
        "InventoryExchange.jsonl",
        "InventoryWebClient.jsonl",
        "KotlinOrder.jsonl",
        "KotlinOrderRoutes$ktRoutes$1$1$1.jsonl",
        "KotlinOrderRoutes$ktRoutes$1$1$2.jsonl",
        "KotlinOrderRoutes$ktRoutes$1$1$3$1.jsonl",
        "KotlinOrderRoutes.jsonl",
        "LegacyBillingApi.jsonl",
        "LegacyOkHttp.jsonl",
        "LegacyOrderController.jsonl",
        "LiveEndpoint.jsonl",
        "MpOrderApi.jsonl",
        "NotificationsSubscriber.jsonl",
        "OrderCommand.jsonl",
        "OrderController.jsonl",
        "OrderEvent.jsonl",
        "OrderEventsController.jsonl",
        "OrderEventsListener.jsonl",
        "OrderGraphqlController.jsonl",
        "OrderIngest.jsonl",
        "OrderPageController.jsonl",
        "OrderProtos$OrderReply$1.jsonl",
        "OrderProtos$OrderReply$Builder.jsonl",
        "OrderProtos$OrderReply.jsonl",
        "OrderProtos$OrderReplyOrBuilder.jsonl",
        "OrderProtos$OrderRequest$1.jsonl",
        "OrderProtos$OrderRequest$Builder.jsonl",
        "OrderProtos$OrderRequest$Line$1.jsonl",
        "OrderProtos$OrderRequest$Line$Builder.jsonl",
        "OrderProtos$OrderRequest$Line.jsonl",
        "OrderProtos$OrderRequest$LineOrBuilder.jsonl",
        "OrderProtos$OrderRequest$Status$1.jsonl",
        "OrderProtos$OrderRequest$Status.jsonl",
        "OrderProtos$OrderRequest$TagsDefaultEntryHolder.jsonl",
        "OrderProtos$OrderRequest.jsonl",
        "OrderProtos$OrderRequestOrBuilder.jsonl",
        "OrderProtos.jsonl",
        "OrderRelay.jsonl",
        "OrderRequest.jsonl",
        "OrderResult$Detail.jsonl",
        "OrderResult.jsonl",
        "OrderRoutes.jsonl",
        "OrderService.jsonl",
        "OrderStatus.jsonl",
        "OrderStompController.jsonl",
        "OrderStreamBindings.jsonl",
        "OrderTopicListener.jsonl",
        "OrderView.jsonl",
        "OrdersApi.jsonl",
        "OrdersApiController.jsonl",
        "OrdersLoopClient.jsonl",
        "OrdersRestClient.jsonl",
        "ParsedPayloadListeners.jsonl",
        "RawJmsBridge.jsonl",
        "RawKafkaConsumers.jsonl",
        "RawKafkaMessageSender.jsonl",
        "RawPubSubPublishers.jsonl",
        "RawPubSubReceiver.jsonl",
        "RawPubSubSubscribers.jsonl",
        "RawSqsClientSender.jsonl",
        "ReceiptView.jsonl",
        "RouteHandlers.jsonl",
        "ScopedRequest.jsonl",
        "ShipmentsSqsListener.jsonl",
        "package-info.jsonl",
    ]
    # 77 + 3: 2G Task 7's `messaging/parse` package — the listeners plus the
    # two delegation targets its rungs follow.
    # + 6: 2H Task 1's GraphQL, WebSocket/STOMP and SSE surfaces.
    assert report.documents == 86


def test_fact_files_land_beside_their_sources_when_the_output_path_contains_java(
    tmp_path: Path,
):
    """A path is not a file extension. Swapping `.java` for `.jsonl` with a
    global substring replace rewrites every occurrence, so a workspace whose
    own directory happens to hold `.java` had its output paths corrupted
    mid-string — facts written somewhere nobody would look for them."""
    out = tmp_path / "work.java" / "facts"
    AsmScanner(JAR).scan(
        ScanRequest(
            module_id="com.acme:orders",
            coordinates="com.acme/orders",
            version="1.0.0",
            classes_dir=CLASSES,
            out_dir=out,
        )
    )
    assert sorted(p.name for p in out.rglob("*.jsonl")) == [
        "ApiGet.jsonl",
        "AuditEvent$Builder.jsonl",
        "AuditEvent.jsonl",
        "AuditJmsListener.jsonl",
        "BillingClient.jsonl",
        "BillingClients$BillingProperties.jsonl",
        "BillingClients.jsonl",
        "BillingRestTemplate$1.jsonl",
        "BillingRestTemplate.jsonl",
        "ClassLevelListener.jsonl",
        "CommonProtos$Money$1.jsonl",
        "CommonProtos$Money$Builder.jsonl",
        "CommonProtos$Money.jsonl",
        "CommonProtos$MoneyOrBuilder.jsonl",
        "CommonProtos.jsonl",
        "ComposedController.jsonl",
        "ComposedListener.jsonl",
        "CustomerRef.jsonl",
        "DetailedOrderResult.jsonl",
        "DgsOrderFetcher.jsonl",
        "EventProducers.jsonl",
        "InventoryExchange.jsonl",
        "InventoryWebClient.jsonl",
        "KotlinOrder.jsonl",
        "KotlinOrderRoutes$ktRoutes$1$1$1.jsonl",
        "KotlinOrderRoutes$ktRoutes$1$1$2.jsonl",
        "KotlinOrderRoutes$ktRoutes$1$1$3$1.jsonl",
        "KotlinOrderRoutes.jsonl",
        "LegacyBillingApi.jsonl",
        "LegacyOkHttp.jsonl",
        "LegacyOrderController.jsonl",
        "LiveEndpoint.jsonl",
        "MpOrderApi.jsonl",
        "NotificationsSubscriber.jsonl",
        "OrderCommand.jsonl",
        "OrderController.jsonl",
        "OrderEvent.jsonl",
        "OrderEventsController.jsonl",
        "OrderEventsListener.jsonl",
        "OrderGraphqlController.jsonl",
        "OrderIngest.jsonl",
        "OrderPageController.jsonl",
        "OrderProtos$OrderReply$1.jsonl",
        "OrderProtos$OrderReply$Builder.jsonl",
        "OrderProtos$OrderReply.jsonl",
        "OrderProtos$OrderReplyOrBuilder.jsonl",
        "OrderProtos$OrderRequest$1.jsonl",
        "OrderProtos$OrderRequest$Builder.jsonl",
        "OrderProtos$OrderRequest$Line$1.jsonl",
        "OrderProtos$OrderRequest$Line$Builder.jsonl",
        "OrderProtos$OrderRequest$Line.jsonl",
        "OrderProtos$OrderRequest$LineOrBuilder.jsonl",
        "OrderProtos$OrderRequest$Status$1.jsonl",
        "OrderProtos$OrderRequest$Status.jsonl",
        "OrderProtos$OrderRequest$TagsDefaultEntryHolder.jsonl",
        "OrderProtos$OrderRequest.jsonl",
        "OrderProtos$OrderRequestOrBuilder.jsonl",
        "OrderProtos.jsonl",
        "OrderRelay.jsonl",
        "OrderRequest.jsonl",
        "OrderResult$Detail.jsonl",
        "OrderResult.jsonl",
        "OrderRoutes.jsonl",
        "OrderService.jsonl",
        "OrderStatus.jsonl",
        "OrderStompController.jsonl",
        "OrderStreamBindings.jsonl",
        "OrderTopicListener.jsonl",
        "OrderView.jsonl",
        "OrdersApi.jsonl",
        "OrdersApiController.jsonl",
        "OrdersLoopClient.jsonl",
        "OrdersRestClient.jsonl",
        "ParsedPayloadListeners.jsonl",
        "RawJmsBridge.jsonl",
        "RawKafkaConsumers.jsonl",
        "RawKafkaMessageSender.jsonl",
        "RawPubSubPublishers.jsonl",
        "RawPubSubReceiver.jsonl",
        "RawPubSubSubscribers.jsonl",
        "RawSqsClientSender.jsonl",
        "ReceiptView.jsonl",
        "RouteHandlers.jsonl",
        "ScopedRequest.jsonl",
        "ShipmentsSqsListener.jsonl",
        "package-info.jsonl",
    ]


def test_no_fact_is_written_for_a_compiler_synthesized_field(tmp_path: Path):
    """`$VALUES` is the array javac writes behind an enumeration's constants —
    the fixture's `OrderStatus` has one. Nobody declared it, so there is
    nothing to record: a fact for it puts a member no source file contains into
    the symbol graph, and the shape pass downstream turns that into a field of
    a payload nobody sends."""
    AsmScanner(JAR).scan(
        ScanRequest(
            module_id="com.acme:orders",
            coordinates="com.acme/orders",
            version="1.0.0",
            classes_dir=CLASSES,
            out_dir=tmp_path,
        )
    )
    written = "".join(p.read_text(encoding="utf-8") for p in tmp_path.rglob("*.jsonl"))
    # Narrowed to the synthesized `$VALUES` array: protobuf's generated enum
    # also declares an explicit, non-synthetic `VALUES` field, whose fact is
    # correct and must not trip this pin.
    assert "$VALUES" not in written


def test_a_nested_class_is_scanned_under_the_outer_sources_path_and_its_own_id(
    tmp_path: Path,
):
    """A nested class used to be skipped and named in `uncovered`; it is now
    read like any other class file. D00 §2 splits the two fields that used to
    move together: `document_id` is the sha256 of the *class*-relative path, so
    `OrderResult` and `OrderResult$Detail` never collide on one id, while
    `relative_path` names the outer *source*, because that is the file a human
    edited. Nothing is left uncovered, which is now the truth rather than a
    silence."""
    report = AsmScanner(JAR).scan(
        ScanRequest(
            module_id="com.acme:orders",
            coordinates="com.acme/orders",
            version="1.0.0",
            classes_dir=CLASSES,
            out_dir=tmp_path,
        )
    )
    assert report.uncovered == ()

    nested, outer = (
        json.loads((tmp_path / "com" / "acme" / "orders" / name).read_text().splitlines()[0])
        for name in ("OrderResult$Detail.jsonl", "OrderResult.jsonl")
    )
    assert nested["relative_path"] == outer["relative_path"] == "com/acme/orders/OrderResult.java"
    assert nested["document_id"] != outer["document_id"]

    facts = (tmp_path / "com" / "acme" / "orders" / "OrderResult$Detail.jsonl").read_text()
    assert "com/acme/orders/OrderResult$Detail#getNote(" in facts


def test_scan_emits_a_field_write_fact_for_a_real_constructor_injected_client(tmp_path: Path):
    """`OrdersRestClient(RestClient restClient) { this.restClient = restClient; }`
    is real fixture bytecode, not a hand-built pin — the exact {@code ALOAD 0;
    ALOAD 1; PUTFIELD} shape D00 §5's `field_write` names. Task 8's field
    resolution ladder is the eventual consumer; this only proves the extractor
    half of the additive amendment reaches a real class file."""
    AsmScanner(JAR).scan(
        ScanRequest(
            module_id="com.acme:orders",
            coordinates="com.acme/orders",
            version="1.0.0",
            classes_dir=CLASSES,
            out_dir=tmp_path,
        )
    )
    facts = (tmp_path / "com" / "acme" / "orders" / "clients" / "OrdersRestClient.jsonl").read_text(
        encoding="utf-8"
    )
    assert '"kind":"field_write"' in facts
    assert '"field":"com/acme/orders/clients/OrdersRestClient#restClient."' in facts
    assert '"from_parameter":0' in facts


def test_scanner_declares_the_capabilities_phase_2a_implements():
    assert {"type_annotations", "kotlin_metadata"} <= AsmScanner(JAR).capabilities()


def test_scanner_declares_the_call_site_capabilities_phase_2c_implements():
    """A catalog that needs call sites is skipped unless a scanner says it
    produces them, so the declaration is what makes the pass reachable — not
    the pass itself."""
    assert {
        "call_site",
        "string_constants",
        "chain_reconstruction",
    } <= AsmScanner(JAR).capabilities()


def test_scanner_declares_the_implemented_interfaces_capability():
    """A class symbol fact's `interfaces` field is only trustworthy for a
    catalog to key off of once the scanner that wrote it says it produces
    them."""
    assert "implemented_interfaces" in AsmScanner(JAR).capabilities()
