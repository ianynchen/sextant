import json
import zipfile
from pathlib import Path

import pytest

from sextant.application.ports.scanner import ScanRequest
from sextant.ingress.extract.jvm.scanner import AsmScanner
from sextant.resources import extractor_jar

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
        "BillingSoapClient.jsonl",
        "BillingWebService.jsonl",
        "ClassLevelListener.jsonl",
        "CommonProtos$Money$1.jsonl",
        "CommonProtos$Money$Builder.jsonl",
        "CommonProtos$Money.jsonl",
        "CommonProtos$MoneyOrBuilder.jsonl",
        "CommonProtos.jsonl",
        "ComposedController.jsonl",
        "ComposedListener.jsonl",
        "CustomerGraphqlController.jsonl",
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
        "LegacyBillingWebService.jsonl",
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
        "OrderSoapEndpoint.jsonl",
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
        "PlaceOrderRequest.jsonl",
        "RawJmsBridge.jsonl",
        "RawKafkaConsumers.jsonl",
        "RawKafkaMessageSender.jsonl",
        "RawPubSubPublishers.jsonl",
        "RawPubSubReceiver.jsonl",
        "RawPubSubSubscribers.jsonl",
        "RawSqsClientSender.jsonl",
        "ReceiptView.jsonl",
        "RootSeamController.jsonl",
        "RouteHandlers.jsonl",
        "ScopedRequest.jsonl",
        "SeamController.jsonl",
        "ShipmentsSqsListener.jsonl",
        "package-info.jsonl",
    ]
    # 77 + 3: 2G Task 7's `messaging/parse` package — the listeners plus the
    # two delegation targets its rungs follow.
    # + 6: 2H Task 1's GraphQL, WebSocket/STOMP and SSE surfaces.
    # + 1: 2H Task 2's `CustomerGraphqlController`, the class-level-scope
    # resolver shape (2H design §1's class-level bullet).
    # + 2: the prefix-seam controllers (`SeamController`, `RootSeamController`)
    # — two class files, one document each. Two types rather than one because
    # a class states its prefix once, and the two seam forms need two
    # different prefixes.
    # + 5: 2I Task 1's SOAP surfaces — `OrderSoapEndpoint`, `BillingWebService`,
    # `LegacyBillingWebService`, `BillingSoapClient` and the `PlaceOrderRequest`
    # payload, each its own class file.
    assert report.documents == 94


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
        "BillingSoapClient.jsonl",
        "BillingWebService.jsonl",
        "ClassLevelListener.jsonl",
        "CommonProtos$Money$1.jsonl",
        "CommonProtos$Money$Builder.jsonl",
        "CommonProtos$Money.jsonl",
        "CommonProtos$MoneyOrBuilder.jsonl",
        "CommonProtos.jsonl",
        "ComposedController.jsonl",
        "ComposedListener.jsonl",
        "CustomerGraphqlController.jsonl",
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
        "LegacyBillingWebService.jsonl",
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
        "OrderSoapEndpoint.jsonl",
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
        "PlaceOrderRequest.jsonl",
        "RawJmsBridge.jsonl",
        "RawKafkaConsumers.jsonl",
        "RawKafkaMessageSender.jsonl",
        "RawPubSubPublishers.jsonl",
        "RawPubSubReceiver.jsonl",
        "RawPubSubSubscribers.jsonl",
        "RawSqsClientSender.jsonl",
        "ReceiptView.jsonl",
        "RootSeamController.jsonl",
        "RouteHandlers.jsonl",
        "ScopedRequest.jsonl",
        "SeamController.jsonl",
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


def _jar_of(target: Path, entries: dict[str, bytes]) -> Path:
    """A jar built here rather than by `jar`/`mvn package`: a zip of class
    files IS what a library ships as, and building it in the test keeps the
    entry ORDER under the test's control — which is the point of the
    determinism pin below."""
    with zipfile.ZipFile(target, "w") as archive:
        for name, payload in entries.items():
            archive.writestr(name, payload)
    return target


def _fixture_classes() -> dict[str, bytes]:
    names = ("com/acme/orders/contracts/OrderView.class", "com/acme/orders/OrderResult.class")
    return {name: (CLASSES / name).read_bytes() for name in names}


def test_scan_reads_the_class_files_inside_a_jar(tmp_path: Path):
    """A library ships as a jar, and until 2I Task 6 `--classes` pointed at one
    walked for loose `.class` files, found none, and reported a clean scan of
    nothing. Opt-in library extraction has no honest shape at all unless a jar
    is a scannable input, so this is the pin for the capability itself."""
    jar = _jar_of(tmp_path / "lib.jar", _fixture_classes())
    report = AsmScanner(JAR).scan(
        ScanRequest(
            module_id="com.acme:orders",
            coordinates="com.example/lib",
            version="1.0.0",
            classes_dir=jar,
            out_dir=tmp_path / "facts",
        )
    )
    assert report.documents == 2
    assert report.facts > 0
    assert report.uncovered == ()
    written = sorted(p.name for p in (tmp_path / "facts").rglob("*.jsonl"))
    assert written == ["OrderResult.jsonl", "OrderView.jsonl"]


def test_a_jars_entries_are_scanned_in_sorted_order_whatever_order_the_archive_holds(
    tmp_path: Path,
):
    """A zip's entry order is whatever the archiver happened to write, so a
    scan that followed it would produce a different `raw_facts` load order —
    and `symbols.seq`, which IS declaration order in the workspace, is derived
    from that (NFR-1). Two jars holding the same classes in opposite orders
    must therefore write identical bytes.

    Both jars are written to ONE path, in turn, rather than to two: the jar's
    own location is recorded on every document as `origin_entry`, so two
    differently named archives would differ for a reason that has nothing to
    do with entry order and the pin would pass vacuously."""
    classes = _fixture_classes()
    orders = (dict(sorted(classes.items())), dict(sorted(classes.items(), reverse=True)))
    scanned = []
    for index, entries in enumerate(orders):
        jar = _jar_of(tmp_path / "lib.jar", entries)
        out = tmp_path / f"facts{index}"
        AsmScanner(JAR).scan(
            ScanRequest(
                module_id="com.acme:orders",
                coordinates="com.example/lib",
                version="1.0.0",
                classes_dir=jar,
                out_dir=out,
            )
        )
        scanned.append(
            {
                str(p.relative_to(out)): p.read_text(encoding="utf-8")
                for p in sorted(out.rglob("*.jsonl"))
            }
        )
    assert scanned[0] == scanned[1]


def test_a_classes_input_holding_no_class_file_is_named_rather_than_reported_as_a_clean_scan(
    tmp_path: Path,
):
    """The silent-success hole this task closed. An empty jar, and a directory
    holding only a jar, both used to answer `documents: 0, facts: 0` with an
    empty `uncovered` at exit 0 — a SUCCESS report for an extraction that
    happened not to happen. A library extraction built on that would publish an
    empty fact set as a complete one, so the input is named in `uncovered`
    (FR-17), which is the channel a finding about unread input already uses."""
    empty_jar = _jar_of(
        tmp_path / "empty.jar", {"META-INF/MANIFEST.MF": b"Manifest-Version: 1.0\n"}
    )
    jar_only = tmp_path / "jaronly"
    jar_only.mkdir()
    _jar_of(jar_only / "lib.jar", _fixture_classes())
    for index, classes in enumerate((empty_jar, jar_only)):
        report = AsmScanner(JAR).scan(
            ScanRequest(
                module_id="com.acme:orders",
                coordinates="com.example/lib",
                version="1.0.0",
                classes_dir=classes,
                out_dir=tmp_path / f"facts{index}",
            )
        )
        assert report.documents == 0
        assert report.uncovered == (f"{classes}: no class files found",)


def test_a_classes_input_the_scanner_cannot_read_fails_instead_of_scanning_nothing(
    tmp_path: Path,
):
    """The other half of the split: an input that cannot be READ is a failed
    request, not a finding about the input, so it exits non-zero and the
    adapter raises. A path that does not exist and a regular file that is not
    a jar are the same mistake — pointing the scanner somewhere there is no
    code — and neither may pass as an empty scan."""
    not_a_jar = tmp_path / "notes.txt"
    not_a_jar.write_text("not bytecode\n", encoding="utf-8")
    for classes in (not_a_jar, tmp_path / "absent"):
        with pytest.raises(RuntimeError, match="must name a directory of class files or a .jar"):
            AsmScanner(JAR).scan(
                ScanRequest(
                    module_id="com.acme:orders",
                    coordinates="com.example/lib",
                    version="1.0.0",
                    classes_dir=classes,
                    out_dir=tmp_path / "facts",
                )
            )


def test_a_scan_records_its_origin_coordinate_only_when_one_was_asked_for(tmp_path: Path):
    """`origin` names the library a document was extracted from (D00 §2). It is
    written only for a scan that names one: a module's own output carries no
    origin KEY at all, not an origin of null, so every fact file a module scan
    writes is byte-for-byte what it was before this option existed."""
    jar = _jar_of(tmp_path / "lib.jar", _fixture_classes())
    for out, origin in (
        (tmp_path / "with", "com.example:orders-soap-client"),
        (tmp_path / "without", None),
    ):
        AsmScanner(JAR).scan(
            ScanRequest(
                module_id="com.acme:orders",
                coordinates="com.example/lib",
                version="1.0.0",
                classes_dir=jar,
                out_dir=out,
                origin=origin,
            )
        )
    written = (
        tmp_path / "with" / "com" / "acme" / "orders" / "contracts" / "OrderView.jsonl"
    ).read_text(encoding="utf-8")
    assert json.loads(written.splitlines()[0])["origin"] == "com.example:orders-soap-client"
    plain = (
        tmp_path / "without" / "com" / "acme" / "orders" / "contracts" / "OrderView.jsonl"
    ).read_text(encoding="utf-8")
    assert "origin" not in json.loads(plain.splitlines()[0])
