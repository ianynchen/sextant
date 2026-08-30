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
        "AuditJmsListener.jsonl",
        "BillingClient.jsonl",
        "BillingRestTemplate$1.jsonl",
        "BillingRestTemplate.jsonl",
        "ClassLevelListener.jsonl",
        "CustomerRef.jsonl",
        "EventProducers.jsonl",
        "InventoryExchange.jsonl",
        "InventoryWebClient.jsonl",
        "KotlinOrder.jsonl",
        "LegacyBillingApi.jsonl",
        "LegacyOkHttp.jsonl",
        "LegacyOrderController.jsonl",
        "NotificationsSubscriber.jsonl",
        "OrderCommand.jsonl",
        "OrderController.jsonl",
        "OrderEvent.jsonl",
        "OrderEventsListener.jsonl",
        "OrderPageController.jsonl",
        "OrderRequest.jsonl",
        "OrderResult$Detail.jsonl",
        "OrderResult.jsonl",
        "OrderService.jsonl",
        "OrderStatus.jsonl",
        "OrderView.jsonl",
        "OrdersLoopClient.jsonl",
        "OrdersRestClient.jsonl",
        "RawJmsBridge.jsonl",
        "RawKafkaConsumers.jsonl",
        "RawKafkaMessageSender.jsonl",
        "RawPubSubPublishers.jsonl",
        "RawPubSubReceiver.jsonl",
        "RawPubSubSubscribers.jsonl",
        "RawSqsClientSender.jsonl",
        "ReceiptView.jsonl",
        "ScopedRequest.jsonl",
        "ShipmentsSqsListener.jsonl",
        "package-info.jsonl",
    ]
    assert report.documents == 38


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
        "AuditJmsListener.jsonl",
        "BillingClient.jsonl",
        "BillingRestTemplate$1.jsonl",
        "BillingRestTemplate.jsonl",
        "ClassLevelListener.jsonl",
        "CustomerRef.jsonl",
        "EventProducers.jsonl",
        "InventoryExchange.jsonl",
        "InventoryWebClient.jsonl",
        "KotlinOrder.jsonl",
        "LegacyBillingApi.jsonl",
        "LegacyOkHttp.jsonl",
        "LegacyOrderController.jsonl",
        "NotificationsSubscriber.jsonl",
        "OrderCommand.jsonl",
        "OrderController.jsonl",
        "OrderEvent.jsonl",
        "OrderEventsListener.jsonl",
        "OrderPageController.jsonl",
        "OrderRequest.jsonl",
        "OrderResult$Detail.jsonl",
        "OrderResult.jsonl",
        "OrderService.jsonl",
        "OrderStatus.jsonl",
        "OrderView.jsonl",
        "OrdersLoopClient.jsonl",
        "OrdersRestClient.jsonl",
        "RawJmsBridge.jsonl",
        "RawKafkaConsumers.jsonl",
        "RawKafkaMessageSender.jsonl",
        "RawPubSubPublishers.jsonl",
        "RawPubSubReceiver.jsonl",
        "RawPubSubSubscribers.jsonl",
        "RawSqsClientSender.jsonl",
        "ReceiptView.jsonl",
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
    assert "VALUES" not in written


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
