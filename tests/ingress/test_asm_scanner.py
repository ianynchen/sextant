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
        "CatalogRepository.jsonl",
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
        "OrderRepository.jsonl",
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
        "Repository.jsonl",
        "RootSeamController.jsonl",
        "RouteHandlers.jsonl",
        "ScopedRequest.jsonl",
        "SeamController.jsonl",
        "SecretRepository.jsonl",
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
    # + 2: 2O Task 3's generic-superinterface fixture — `OrderRepository` and
    # the `Repository<T, ID>` contract it extends, each its own class file.
    # 96 + 2: 2O Task 6's Data REST fixture (`CatalogRepository`,
    # `SecretRepository`), one class file each.
    assert report.documents == 98


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
        "CatalogRepository.jsonl",
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
        "OrderRepository.jsonl",
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
        "Repository.jsonl",
        "RootSeamController.jsonl",
        "RouteHandlers.jsonl",
        "ScopedRequest.jsonl",
        "SeamController.jsonl",
        "SecretRepository.jsonl",
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


def test_scanner_declares_the_generic_interfaces_capability():
    """A class symbol fact's `generic_interfaces` field (capability 9.14) is
    only trustworthy for Spring Data REST's entity-type read once the scanner
    that wrote it says it produces them."""
    assert "generic_interfaces" in AsmScanner(JAR).capabilities()


def test_scanner_declares_the_superclass_capability():
    """A class symbol fact's `superclass` field (capability 9.13, D00 §4's
    `relationship_kind: extends` made real) is only trustworthy for a
    hierarchy-walking catalog once the scanner that wrote it says it produces
    it."""
    assert "superclass" in AsmScanner(JAR).capabilities()


def _scan(tmp_path: Path) -> Path:
    AsmScanner(JAR).scan(
        ScanRequest(
            module_id="com.acme:orders",
            coordinates="com.acme/orders",
            version="1.0.0",
            classes_dir=CLASSES,
            out_dir=tmp_path,
        )
    )
    return tmp_path


def _class_symbol(path: Path) -> dict:
    """The class-level `symbol` fact in a scanned `.jsonl` file — the one
    `visit` emits before any member's, so it carries no `enclosing`. Filtered
    rather than indexed: a class with members has more `symbol` lines after
    it, and indexing past the document line would break the moment one grew
    a field or a method."""
    for line in path.read_text().splitlines():
        fact = json.loads(line)
        if fact.get("kind") == "symbol" and fact.get("enclosing") is None:
            return fact
    raise AssertionError(f"no class symbol found in {path}")


def test_a_generic_superinterface_records_its_type_arguments(tmp_path: Path):
    """Capability 9.14 — D00 §5a's PTR-carrier rule, extended one level over
    to `implements`: `interfaces` alone erases `Repository<OrderResult, Long>`
    to a bare symbol, and Spring Data REST cannot derive a repository's entity
    type from that alone (2O design §2a). `generic_interfaces` is the only
    place the entity and id types survive, kept as full type references
    exactly like `supertype`."""
    out = _scan(tmp_path)
    fact = _class_symbol(out / "com" / "acme" / "orders" / "data" / "OrderRepository.jsonl")
    assert fact["generic_interfaces"] == [
        {
            "symbol": "com/acme/orders/data/Repository#",
            "arguments": [
                {
                    "symbol": "com/acme/orders/OrderResult#",
                    "arguments": [],
                    "wire_type": "object",
                    "wire_format": "",
                    "nullable": True,
                    "nullable_resolution": "resolved",
                },
                {
                    "symbol": "java/lang/Long#",
                    "arguments": [],
                    "wire_type": "integer",
                    "wire_format": "int64",
                    "nullable": True,
                    "nullable_resolution": "resolved",
                },
            ],
            "wire_type": "object",
            "wire_format": "",
            "nullable": True,
            "nullable_resolution": "resolved",
        }
    ]


def test_a_non_generic_interface_carries_no_generic_reference(tmp_path: Path):
    """Symmetry with D00's generic-superclass rule: nothing generic, nothing
    captured — the erased `interfaces` list already states the relationship
    for a plain interface like `MessageReceiver`."""
    out = _scan(tmp_path)
    fact = _class_symbol(
        out / "com" / "acme" / "orders" / "messaging" / "raw" / "RawPubSubReceiver.jsonl"
    )
    assert "generic_interfaces" not in fact


def test_a_plain_class_records_its_erased_superclass_symbol(tmp_path: Path):
    """Capability 9.13 — D00 §4's `relationship_kind: extends`, made real. CP-3
    found no fact anywhere naming a plain superclass: `interfaces` erases
    every implemented type, and `supertype` only fires when the signature is
    generic. `DetailedOrderResult extends OrderResult` carries no `Signature`
    attribute at all — neither class is generic — so `superclass`, read
    straight off the class file's own `super_class` entry, is the only place
    the relationship survives."""
    out = _scan(tmp_path)
    fact = _class_symbol(out / "com" / "acme" / "orders" / "openapi" / "DetailedOrderResult.jsonl")
    assert (
        fact["superclass"] == "sextant-jvm maven com.acme/orders 1.0.0 com/acme/orders/OrderResult#"
    )


def test_a_root_class_carries_no_superclass_reference(tmp_path: Path):
    """Null for `java.lang.Object`: every class with no declared superclass
    gets this same constant-pool entry implicitly, so writing it would put a
    superclass reference on nearly every class in a module and say nothing
    with any of them."""
    out = _scan(tmp_path)
    fact = _class_symbol(out / "com" / "acme" / "orders" / "OrderResult.jsonl")
    assert "superclass" not in fact


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


def _call_sites(path: Path, name: str) -> list[dict]:
    """Every `call_site` fact in a scanned file whose target method has this
    name — filtered by name rather than indexed, for the same reason
    `_class_symbol` filters: an ordinal is a property of the method body and
    moves the moment the fixture grows a statement."""
    return [
        fact
        for line in path.read_text().splitlines()
        if (fact := json.loads(line)).get("kind") == "call_site" and fact["target"]["name"] == name
    ]


def test_a_varargs_argument_carries_its_elements_rather_than_one_unresolved(tmp_path: Path):
    """Capability 9.15 against real compiled bytecode. `RequestPredicates
    .accept(MediaType...)` is the shape `spring-webflux-router.yml`'s own
    `media_values` table was written for and could never read: the value
    reaching the slot is the array the `ANEWARRAY` produced, so before this
    capability every media predicate was a bare `{"kind": "unresolved"}` with
    no `source` and no `symbol`, and `MediaType.APPLICATION_JSON` was absent
    from the fact stream entirely.

    The element keeps the `enum` kind it would have carried as a single
    argument — which is the whole point: the probe's control arm showed a
    single-`String` sink discriminating eight destination spellings while the
    varargs sink collapsed them to one byte-identical `unresolved`
    (`scripts/probes/spring-integration-destinations.md`)."""
    out = _scan(tmp_path)
    accepts = _call_sites(
        out / "com" / "acme" / "orders" / "routes" / "OrderRoutes.jsonl", "accept"
    )
    assert accepts, "the WebFlux router fixture declares an accept predicate"
    assert accepts[0]["arguments"] == [
        {
            "kind": "array",
            "elements": [
                {"kind": "enum", "symbol": "org/springframework/http/MediaType#APPLICATION_JSON."}
            ],
        }
    ]


def test_a_zero_length_varargs_argument_is_an_empty_element_list(tmp_path: Path):
    """`uri(String, Object...)` called with no URI variables — the ordinary
    WebClient spelling — compiles to an empty `ANEWARRAY`. The empty list is
    the fact: "called with no URI variables" is a different statement from
    "the array could not be read", and it is what makes the argument's arity
    readable at all. The slot count is the assertion beside it: an array is
    ONE argument, and unpacking it would have renumbered the path literal's
    neighbour out of position."""
    out = _scan(tmp_path)
    uris = _call_sites(
        out / "com" / "acme" / "orders" / "clients" / "InventoryWebClient.jsonl", "uri"
    )
    assert uris, "the WebClient fixture declares a uri call"
    assert uris[0]["arguments"] == [
        {"kind": "string", "value": "/v2/inventory/levels"},
        {"kind": "array", "elements": []},
    ]


def test_an_argument_that_is_not_an_array_carries_no_elements_key(tmp_path: Path):
    """The near miss on the emission side: `elements` belongs to the `array`
    kind alone, so every other argument in the estate must be byte-identical
    to what it was before 9.15. A key written on every argument would change
    every fact file in the fixture and every assertion pinned to one."""
    out = _scan(tmp_path)
    for line in (
        (out / "com" / "acme" / "orders" / "clients" / "BillingRestTemplate.jsonl")
        .read_text()
        .splitlines()
    ):
        fact = json.loads(line)
        if fact.get("kind") != "call_site":
            continue
        for argument in fact["arguments"]:
            assert ("elements" in argument) == (argument["kind"] == "array"), argument


def test_scanner_declares_the_array_arguments_capability():
    """A call-site argument's `elements` (capability 9.15) is only trustworthy
    for a catalog reading a `String...` destination once the scanner that
    wrote it says it produces them — the same gate `generic_interfaces` and
    `superclass` pass through."""
    assert "array_arguments" in AsmScanner(JAR).capabilities()


def test_a_returned_lambdas_body_is_named_by_the_site_that_creates_it(tmp_path: Path):
    """Capability 9.17 against real framework code. `OrderStreamBindings`'
    four `@Bean` methods each RETURN a lambda, so the body fills no argument
    slot and the `lambda` argument kind — the only thing that named a body
    before — never fires. The site itself now carries it, which is what makes
    a Spring Cloud Stream handler's code reachable from the bean that declares
    it rather than an orphaned synthetic method."""
    out = _scan(tmp_path)
    facts = [
        json.loads(line)
        for line in (out / "com" / "acme" / "orders" / "streams" / "OrderStreamBindings.jsonl")
        .read_text()
        .splitlines()
    ]
    sites = [fact for fact in facts if fact.get("kind") == "call_site"]
    dynamic = [site for site in sites if site["invoke_kind"] == "dynamic"]
    assert len(dynamic) == 4, "four @Bean methods, each returning one lambda"
    assert [site["implementation"] for site in dynamic] == [
        "com/acme/orders/streams/OrderStreamBindings#lambda$handleOrder$0(sig_b2a754d9).",
        "com/acme/orders/streams/OrderStreamBindings#lambda$auditTap$0(sig_7f15bbda).",
        "com/acme/orders/streams/OrderStreamBindings#lambda$orphanConsumer$0(sig_b2a754d9).",
        "com/acme/orders/streams/OrderStreamBindings#lambda$unselectedBean$0(sig_b2a754d9).",
    ]
    # The near-miss on the emission side, and the reason it is checked here
    # too: `implementation` belongs to a bootstrap that names a method, so the
    # constructor's plain `invokespecial` beside these four must be
    # byte-identical to what it was before 9.17.
    assert all("implementation" not in site for site in sites if site["invoke_kind"] != "dynamic")


def test_a_lambda_body_is_bare_where_the_method_it_names_is_module_prefixed(tmp_path: Path):
    """OI-4, proven on a MODULE-PREFIXED scan rather than on a fixture that
    spells everything bare. One identity, two spellings: a method's own symbol
    fact carries the full SCIP form and `implementation` carries the bare
    descriptor path, deliberately — D00 §1 requires `String::trim` to be one
    symbol in every module, which stamping the caller's coordinates on it
    would break.

    So the join is bare-against-stripped, and this test states it as a
    measurement rather than an assumption: on the orders-service fixture the
    direct join matches **nothing at all**, which is exactly the failure mode
    OI-4 records — six green tests and no match on any real module."""
    out = _scan(tmp_path)
    methods: set[str] = set()
    bodies: set[str] = set()
    for path in out.rglob("*.jsonl"):
        for line in path.read_text().splitlines():
            fact = json.loads(line)
            if fact.get("kind") == "symbol" and fact.get("construct_kind") == "method":
                methods.add(fact["symbol"])
            if fact.get("kind") == "call_site" and fact.get("implementation"):
                bodies.add(fact["implementation"])
    assert bodies, "the fixture declares lambdas"
    assert all(symbol.startswith("sextant-jvm maven com.acme/orders 1.0.0 ") for symbol in methods)
    assert not (bodies & methods), "the direct join is the OI-4 trap and must match nothing"
    assert bodies <= {symbol.split(" ")[-1] for symbol in methods}


def test_a_returned_call_result_names_the_site_that_produced_it(tmp_path: Path):
    """Capability 9.18 against real compiled bytecode, and the link it exists
    to close. `BillingRestTemplate#getBalance` returns what `RestTemplate
    #getForObject` produced; every other hop of that round trip was already a
    fact, and nothing said which of this method's call results the method
    hands back. The join is one number — the return's `source` against the
    site's own `result` — and it is asserted as a join here rather than as two
    separate values, because a fact that named a value id joining to nothing
    is the failure this is meant to be checked against."""
    out = _scan(tmp_path)
    path = out / "com" / "acme" / "orders" / "clients" / "BillingRestTemplate.jsonl"
    facts = [json.loads(line) for line in path.read_text().splitlines()]
    method = next(
        fact["method"]
        for fact in facts
        if fact.get("kind") == "method_return" and "#getBalance(" in fact["method"]
    )
    returns = [fact for fact in facts if fact.get("kind") == "method_return"]
    balance = [fact for fact in returns if fact["method"] == method]
    assert len(balance) == 1, "one return statement, one fact"
    produced = balance[0]["value"]["source"]
    producer = next(
        fact
        for fact in facts
        if fact.get("kind") == "call_site"
        and fact["caller"] == method
        and fact.get("result") == produced
    )
    assert producer["target"]["name"] == "getForObject"
    # `updateSettlement` returns nothing, and that is an answer: a `void`
    # return pops nothing, so its `value` is null rather than an `unresolved`
    # standing in for a value that was never there.
    void = [fact for fact in returns if "#updateSettlement(" in fact["method"]]
    assert void and all(fact["value"] is None for fact in void)


def test_a_method_return_names_its_method_the_way_a_call_site_names_its_caller(
    tmp_path: Path,
):
    """OI-4 again, on the other new symbol. `method_return.method` is a
    DECLARATION this module made, so it carries the module-prefixed spelling —
    the same one `call_site.caller` uses, and the same one the method's own
    `symbol` fact uses. Asserted as an equality against the caller spelling
    rather than as a prefix check alone: the failure mode OI-4 records is two
    spellings of one identity that never meet, and the way to pin it is to
    show the join succeeds."""
    out = _scan(tmp_path)
    path = out / "com" / "acme" / "orders" / "clients" / "BillingRestTemplate.jsonl"
    facts = [json.loads(line) for line in path.read_text().splitlines()]
    callers = {fact["caller"] for fact in facts if fact.get("kind") == "call_site"}
    # `constructor` alongside `method`: a `<init>` body ends in a void RETURN
    # like any other, so it has a `method_return` too, and its own symbol fact
    # carries the other construct kind. Narrowing this to `method` made the
    # assertion fail on the constructor, which is how the pair got noticed.
    methods = {
        fact["symbol"]
        for fact in facts
        if fact.get("kind") == "symbol" and fact.get("construct_kind") in {"method", "constructor"}
    }
    returned_by = {fact["method"] for fact in facts if fact.get("kind") == "method_return"}
    assert returned_by
    assert all(
        symbol.startswith("sextant-jvm maven com.acme/orders 1.0.0 ") for symbol in returned_by
    )
    assert returned_by <= methods
    assert returned_by & callers


def test_scanner_declares_the_method_returns_capability():
    """Capability 9.18 passes the same gate. `method_return` is a fact KIND an
    older jar does not write at all, so a consumer reading none of them from a
    stale scan would conclude the module's methods return nothing — the
    silent degradation capability gating exists to make visible."""
    assert "method_returns" in AsmScanner(JAR).capabilities()


def test_scanner_declares_the_lambda_body_capability():
    """Capability 9.17 passes the same gate as 9.15 and 9.16. A traversal that
    followed `implementation` against an older extractor would find the key
    absent on every site and conclude the module contains no lambdas — the
    silent degradation capability gating exists to make visible."""
    assert "lambda_body" in AsmScanner(JAR).capabilities()


def test_scanner_declares_the_nested_annotation_args_capability():
    """Capability 9.16 passes the same gate. A catalog reading `@Poller` inside
    `@InboundChannelAdapter`, or a `@Scheduled` folded into a `@Schedules`
    array, is reading a key that simply did not exist in an older extractor's
    output — absent, not wrong — so the declaration is what tells the two
    apart. The extractor-side evidence is
    `extractor-jvm/src/test/java/dev/sextant/extractor/NestedAnnotationScanTest.java`
    against `NestedAnnotated`, and the real-bytecode arm is
    `fixtures/spring-integration-probe/…/NestedAnnotationShapes.java`."""
    assert "nested_annotation_args" in AsmScanner(JAR).capabilities()
