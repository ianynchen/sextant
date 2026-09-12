import json
import re
from pathlib import Path

from fixture_module import write_fixture_module_fact
from shape_helpers import ORDER_REQUEST, ORDER_STATUS, shape_fields_of

from fixture_build import compile_fixture
from sextant.application.ports.artifacts import ReadRequest, group_files_by_reader
from sextant.application.ports.catalogs import Catalog, CatalogSource
from sextant.application.ports.scanner import ScanRequest
from sextant.application.resolve.endpoints import SkippedCatalog
from sextant.application.resolve.pipeline import ResolveReport, resolve
from sextant.domain.closed_sets import OriginTier
from sextant.domain.factfile import config_fact_target, write_fact_file
from sextant.domain.facts import Document
from sextant.domain.ignorefile import IgnoreRules
from sextant.domain.resource_files import list_files
from sextant.ingress.catalogs.yaml_source import YamlCatalogSource
from sextant.ingress.extract.jvm.scanner import AsmScanner
from sextant.ingress.read.properties import PropertiesReader
from sextant.ingress.read.yaml_config import YamlConfigReader
from sextant.resources import catalogs_dir, extractor_jar
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
    """Compile, scan, READ and resolve the fixture — the whole path, on real
    bytecode and the fixture's own real configuration files. The workspace is
    handed back open: the rows the report points at are read from it, and
    closing it here would take them with it.

    2F Task 7: the read half is not decoration. `resolve()` runs M04's pass 2
    over whatever `config_entry` facts the workspace holds, and a
    `config_join` catalog then reads the `resolved_config` rows that pass
    produced — so a fixture resolved WITHOUT its configuration answers a
    genuinely different question ("this module declares no bindings at all"),
    and every row-level pin below would describe a pipeline nobody runs. The
    two lines mirror `stages/analyze.py`'s own read step exactly, with the
    resource root written out rather than re-detected (this helper already
    hard-codes the module's coordinates for the same reason)."""
    compile_fixture(FIXTURE)
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
    # `A-C5`: the dependency-gated styles need a module fact and this helper
    # runs no detector — see `conftest.write_fixture_module_fact` for which
    # coordinates it declares and why that list is a deliberate subset.
    write_fixture_module_fact(facts)
    root = FIXTURE / "src" / "main" / "resources"
    for reader, owned in group_files_by_reader(
        list_files(root, FIXTURE, IgnoreRules.load(FIXTURE)),
        [PropertiesReader(), YamlConfigReader()],
    ):
        request = ReadRequest(
            module_id="com.acme:orders-service", version="1.0.0", files=owned, root=root
        )
        for document, config_facts in reader.read(request):
            target = config_fact_target(facts, document.relative_path)
            write_fact_file(target, document, config_facts)
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    report = resolve(
        workspace,
        facts,
        catalogs or YamlCatalogSource(CATALOGS),
        # Phase 2C: `call_site` and `string_constants` gate the RestTemplate
        # catalog (D02 §1's `single_call`); `chain_reconstruction` gates the
        # `fluent` catalogs (WebClient/RestClient/OkHttp/aws-sqs-sdk/
        # google-pubsub-publisher/spring-kafka-message) AND, as of Phase 2E
        # Task 9, `spring-webflux-router.yml`'s own `combinator` style — the
        # SAME three capabilities (`call_site`, `string_constants`,
        # `chain_reconstruction`), no new one added; `implemented_interfaces`
        # (2E-prep Task 12) gates `google-pubsub-subscriber.yml`'s own
        # `interface_implementation` style; `superclass` (capability 9.13, 2O
        # design §1b, Task 5) gates `grpc-java.yml`'s own `supertype_derived`
        # style — a real subset of what `AsmScanner.capabilities()` actually
        # declares, the same way the other capabilities here already are.
        {
            "annotation_args",
            "typed_signatures",
            "type_annotations",
            "call_site",
            "string_constants",
            "chain_reconstruction",
            "implemented_interfaces",
            "superclass",
            # `array_arguments` (capability 9.15) is granted because the real scanner declares it and
            # these sets are a real SUBSET of that. *It was added when four catalogs briefly declared
            # it in `requires:`; that declaration is reverted (W46's review — it turned a graceful
            # degradation into a total skip), so nothing here depends on it now. Kept because the
            # varargs reads it feeds are real and a harness that withheld it would be measuring a
            # scanner nobody ships.*
            "array_arguments",
            # `nested_annotation_args` (capability 9.16, 2O design §4a, Task 8)
            # gates `spring-scheduling.yml`'s own `scheduled_work` style —
            # granted, like the rest, because `AsmScanner` declares it.
            "nested_annotation_args",
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
        # `SharedPathClients`: TWO callers on this one address, at two different hosts.
        # One route here, two ROWS below — which is the point of the fixture. W27's
        # outbound dedup keyed on wire identity alone and dropped the second caller
        # outright, and no fixture had the shape that would have shown it.
        ("GET", "/shared/path"),
        ("GET", "/v1/orders"),
        # The one endpoint whose request and response are both real payloads:
        # `OrderRequest` in, `ResponseEntity<OrderView>` out.
        ("POST", "/v1/orders/detailed"),
        # OrderPageController: a `@Controller`, not `@RestController` — the
        # spring-mvc catalog's own two routes, prefixed by its class-level
        # `@RequestMapping`.
        ("GET", "/orders"),
        ("POST", "/orders/new"),
        # The prefix seam, live (`spring-web.yml`'s `mapping.path_separator`).
        # SeamController's class prefix spells no trailing slash and its method
        # path no leading one; RootSeamController's `"/"` prefix meets a
        # slash-leading method path. Spring joins each with exactly one `/`,
        # and the bare concatenation these replaced derived
        # `/v1/seamowners/{ownerId}` and `//chat` — addresses nobody serves,
        # published at `resolved`/`compiler`. Both forms found live against
        # spring-petclinic-microservices before they were fixtures here.
        ("GET", "/v1/seam/owners/{ownerId}"),
        ("POST", "/chat"),
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
        # Phase 2E Task 6 (composed annotations — distinct from "2E-prep Task
        # 6" elsewhere in this file, a different plan's numbering): the
        # effective-annotations pre-pass's own fixture —
        # `ComposedController#composed`'s `@ApiGet`, a module-local
        # composition of `@RequestMapping(method=[GET], path=["/composed"])`
        # (the checkpoint's ratified deviation from `@GetMapping`, which
        # javac rejects as a meta-annotation — its own `@Target` is `METHOD`
        # only). `ComposedController` carries `@RestController` and no
        # class-level `@RequestMapping`, so no prefix applies.
        ("GET", "/composed"),
        # Phase 2E Task 7 (inherited mappings): the OpenAPI-generator
        # pattern — `OrdersApi` declares mappings, `OrdersApiController`
        # implements it with bare `@Override`s carrying none of their own.
        # `/api/orders`: the interface's own `@GetMapping("/orders")` on
        # `list()`, inherited onto the implementation and prefixed by the
        # interface's own class-level `@RequestMapping("/api")` — neither of
        # which `OrdersApiController` (only `@RestController`) repeats.
        # `/api/composed`: the composed-AND-inherited case — `@ApiGet` on
        # `OrdersApi#composed` composes to a real `@RequestMapping` (Task 6)
        # BEFORE this task's own inheritance walk has anything to resolve.
        ("POST", "/v1/orders/scoped"),
        # W28: three handlers on ONE path and verb, which Spring registers because
        # `params`/`headers` separate them — `RequestMappingInfo.equals` compares seven
        # conditions and these are two of them. They are one route in this set and three
        # rows in the table, and the routing-conflict detector reports nothing about
        # them. Six repositories contained zero uses of either attribute, so nothing
        # else here exercises the discriminators it reads.
        ("GET", "/v1/routing/orders"),
        # W29: the header-carrying WebClient chain. Its three headers are the
        # `endpoint_metadata` rows; the route itself is an ordinary outbound row.
        ("GET", "/v2/inventory/tagged"),
        # `OI-73`: both of these build their URL inside a `uri(Function)` lambda, and
        # `/v2/inventory/search` was ALREADY IN THIS FIXTURE deriving a row with `path`
        # NULL — a real outbound call with no address, invisible in this set. The lambda
        # body is now walked as a chain of its own, so both appear.
        ("GET", "/v2/inventory/lookup"),
        ("GET", "/v2/inventory/search"),
        # W26's four, and they are two different answers on purpose.
        # `/v1/paged/totals` returns `OrderTotals`, an interface: no fields at all, so
        # its wire contract is its bean accessors, and the shape carries real fields.
        # The three below return `Page`/`Slice`, which live in a jar this fixture names
        # in no `extract_libraries` — so their shapes stay open with zero fields and the
        # types are reported as ones nothing could expand. Reading a type's accessors
        # needs its class file exactly as reading its fields does, and pinning both
        # halves here is what keeps the first from being mistaken for a rule that
        # describes types the workspace never read.
        ("GET", "/v1/paged/orders"),
        ("GET", "/v1/paged/slice"),
        ("GET", "/v1/paged/totals"),
        ("GET", "/v1/paged/wrapped"),
        # `/api/orders/{id}`: the COVARIANT case, and it derives now (OI-47).
        # `OrdersApiController#find` returns `DetailedOrderResult`, so its
        # descriptor differs from the interface's `find` and it misses the
        # name+descriptor join outright. javac's bridge carries the interface's
        # exact descriptor and is the only thing that CAN match — so the mapping
        # is reachable only through it, and it is not the method anyone wrote.
        # The bridge used to be excluded and the mapping went with it; it is now
        # read from `modifiers.synthetic` and its mapping carried across to the
        # real override (handler asserted below).
        ("GET", "/api/orders/{id}"),
        ("GET", "/api/orders"),
        ("GET", "/api/composed"),
        # Phase 2E Task 9 (the `combinator` engine — the WebFlux router tree,
        # both DSLs through one core, spring-webflux-router.yml).
        # `OrderRoutes#routes`: `RouterFunctions.nest("/fn", ...)` prefixing a
        # chain of `route`/`andRoute` — `GET`+`POST /fn/orders` off the
        # method-ref and inline-lambda handlers, and the `or`'d
        # `GET`+`HEAD /fn/health` pair sharing the inline lambda's synthetic
        # body (checkpoint (1a)).
        ("GET", "/fn/orders"),
        ("POST", "/fn/orders"),
        ("GET", "/fn/health"),
        ("HEAD", "/fn/health"),
        # `OrderRoutes#composite`/`#other` (checkpoint (1a)'s cross-method
        # case): `composite()` derives `GET /extra` off its own predicate,
        # PLUS one unresolved row for `.and(other())` — the walk is
        # per-method by design, so the cross-method `RouterFunction`
        # reference is a visible unresolved row rather than a silent
        # absence (asserted by caller below). `other()` is itself an
        # argument-rooted entry, so `GET /other` ALSO derives, resolved,
        # from its own independent walk — two rows for one method, not one
        # (checkpoint (1a)'s frozen "consequence").
        ("GET", "/extra"),
        ("GET", "/other"),
        # `KotlinOrderRoutes#ktRoutes`'s `coRouter { }` DSL, nested under
        # `/kt`: `GET`+`POST /kt/orders` and `GET /kt/rich`, handler NULL on
        # all three (checkpoint (1b) Tier-0: the Kotlin compiler hands every
        # handler here as an `instance` of a generated class, never a method
        # reference — never fabricated into one).
        ("GET", "/kt/orders"),
        ("POST", "/kt/orders"),
        ("GET", "/kt/rich"),
        # Outbound (Phase 2B): the client interfaces' declared calls.
        ("POST", "/billing/invoices"),
        ("GET", "/billing/invoices"),
        ("GET", "/v1/inventory/levels"),
        ("POST", "/v1/inventory/reserve"),
        # `LegacyBillingApi`'s two Retrofit declarations, recorded WITHOUT a
        # leading separator because that is what they wrote. 2O Task 2's
        # canonical-address gate does NOT reach them (ruling R8): it applies
        # to inbound HTTP alone, and a CLIENT's slashless path resolves
        # against its base address's own path while a leading separator is
        # root-relative — two different URLs, so prefixing one here would
        # rewrite an address rather than normalize a spelling.
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
        # Phase 2E Task 6 (composed annotations): the messaging half of the
        # same fixture — `ComposedListener#onComposedEvent`'s
        # `@OrderTopicListener`, a
        # module-local composition of `@KafkaListener(topics =
        # ["composed-orders"])`. `spring-kafka.yml` declares no type-level
        # gate, so `ComposedListener` needs none; the handler returns `void`,
        # so no reply row derives (the pre-pass proving itself catalog-
        # generic — the same mechanism, a different catalog, for free).
        (None, "composed-orders"),
        # Outbound (Phase 2D, Task 10): `@SendTo`'s two reply shapes.
        # `onReturn`'s static `@SendTo("order-return-receipts")`.
        (None, "order-return-receipts"),
        # `escalate`'s dynamic reply: value-returning, no `@SendTo` at all —
        # `path` NULL, `unresolved` (asserted below). Also shared, from Task
        # 11 on, by `sendDefault`'s own NULL-path row and JmsTemplate's
        # destination-less `convertAndSend(event)` — every path-NULL messaging row renders the
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
        # Phase 2E Task 9 adds one more to this same shared tuple:
        # `OrderRoutes#composite`'s `.and(other())` — the combinator walk is
        # per-method by design, so this cross-method `RouterFunction`
        # reference derives its own unresolved row, sharing the identical
        # `(None, None)` shape every other unreadable-identity row does
        # (asserted on its own, by caller, below).
        (None, None),
        # Outbound (Phase 2D, Task 11): `kafka-clients.yml`'s raw
        # `KafkaProducer#send(ProducerRecord)` — `order-raw` has no inbound
        # counterpart, so it stays its own outbound row rather than merging.
        (None, "order-raw"),
        # Outbound (Phase 2D, Task 11): `SqsTemplate#send(queue, payload)` —
        # `shipments-outbound` is a different topic from the inbound
        # listener's own `shipments-inbound`, so no merge here either.
        (None, "shipments-outbound"),
        # W57 (`OI-74`): `SqsTemplate#send(to -> to.queue(...).payload(...))`.
        # This row used to be one of the `(None, None)` tuple's several
        # contributors — its queue name sat unread inside the builder lambda
        # since 2026-08-30 (`dacdf67`) — and it is now its own destination.
        (None, "shipments-lambda"),
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
        # 2E-prep Task 12 (driver catalogs B): the pubsub trio +
        # spring-kafka-message. `google-pubsub-publisher.yml`'s co-located
        # `Publisher.newBuilder(TopicName.of(project, "raw-events")).build()
        # .publish(message)` — resolved via the fluent engine's new
        # `channel`/`channel_via` ladder (this task's own precondition
        # commit), the literal read failing and falling back to the linked
        # `TopicName.of` call.
        (None, "raw-events"),
        # `google-pubsub-subscriber.yml`'s two `Subscriber.newBuilder`
        # registrations — a named `MessageReceiver` implementation and a
        # lambda, sharing no path with each other (asserted below).
        (None, "raw-notify"),
        (None, "raw-notify-lambda"),
        # `spring-kafka-message.yml`'s `MessageBuilder.withPayload(event)
        # .setHeader(KafkaHeaders.TOPIC, "raw-messages").build()` chain: the
        # topic identity resolves cleanly (this row), but the row's own
        # `resolution` reads `unresolved` (asserted below, a divergence from
        # the plan's own checkpoint shorthand, verified live). Its
        # DUPLICATE sibling — spec §4's ruling, already frozen from Task 6
        # on — is `spring-kafka-template.yml`'s own pre-existing
        # `record_arg` row for this SAME call, which shares the existing
        # `(None, None)` tuple, so the SET gains only this one new entry.
        (None, "raw-messages"),
        # 2F Task 3 (the configuration surface fixture): `AuditJmsListener
        # #onAudit`'s destination literal moves to the placeholder
        # `${orders.audit.topic}` (application.yml supplies the value) —
        # `@JmsListener.destination` is read as a string literal regardless
        # of its placeholder content, so the row still resolves, only under
        # a new identity. `(None, "audit.queue")` above stays in the set too
        # — `EventProducers#sendAuditMessage`'s own send no longer shares an
        # identity with the listener, so it now stands unmerged (asserted
        # below) rather than disappearing into `direction: both`.
        (None, "${orders.audit.topic}"),
        # 2F Task 8 (the field ladder and base composition, re-freezing Task
        # 3's own four rows exactly as that pin promised): `baseUrl` is now a
        # declared `base` capture, so each `BillingClients` chain composes
        # the address it really calls — the base its argument names plus its
        # own `.uri()` literal. Three rungs of the ladder answer, one per
        # caller, and each returns the SAME expression from a different
        # fact path: `fieldFedInvoice` off the field's own `@Value`,
        # `constructorFedInvoice` off the `field_write` back to the
        # annotated constructor parameter, `propertiesFedInvoice` off the
        # `@ConfigurationProperties(prefix)` bean read through its getter.
        # The whole expression stays in `path` with `peer` NULL —
        # unsplittable until `resolved_peers` substitutes it per environment
        # (asserted below). `computedBaseInvoice`'s concatenated base
        # defeats every rung, and its row FLIPS from Task 3's `resolved`
        # `/adjustments` to path NULL, `unresolved` (checkpoint D-4): a
        # captured base nobody could read poisons the address rather than
        # letting a relative path stand in for the whole URL.
        ("GET", "${billing.url}/invoices"),
        ("GET", "${billing.url}/refunds"),
        ("GET", "${billing.url}/statements"),
        # 2F Task 7 (the `config_join` engine): the two binding rows whose
        # destination the configuration actually names. `handleOrder`'s
        # `Consumer<OrderEvent>` binds `-in-0` (inbound) to `stream-orders`,
        # `auditTap`'s `Supplier<OrderEvent>` binds `-out-0` (outbound) to
        # `audit-tap`; neither destination is named by any other catalog in
        # this fixture, so neither merges and neither is suppressed by the
        # wire-identity guard. The other two selected entries —
        # `orphanConsumer` (no binding key declared anywhere) and the
        # composed `pipeA|pipeB` entry — both land on the existing
        # `(None, None)` tuple, so the SET gains nothing for them even
        # though the count does. `unselectedBean`, whose facts are
        # identical to `handleOrder`'s, derives NO row at all: only
        # selection excludes it, asserted explicitly below.
        (None, "stream-orders"),
        (None, "audit-tap"),
        # 2G Task 5 (declared shapes): OrderController#createProtoOrder's
        # generated-protobuf endpoint — its own new route; no client anywhere
        # in the fixture calls it, so no inbound/outbound merge.
        ("POST", "/v1/orders/proto-orders"),
        # 2G Task 7 (parse binding): five bytes-only channels, one per case
        # the binding rungs have to answer differently — rung A, rung B, a
        # second caller into that same rung-B callee, an ambiguous handler
        # and a two-hop one. Each destination is unique to those listeners on
        # purpose: two of them sharing a destination would merge into ONE row
        # and the five cases would stop being five rows to pin.
        (None, "parsed-orders-inbound"),
        (None, "parsed-audit-queue"),
        (None, "parsed-shared-inbound"),
        (None, "parsed-mixed-inbound"),
        (None, "parsed-relay-queue"),
        # 2H Task 1: `OrderEventsController`'s two SSE routes derive as
        # ordinary http endpoints today — `@GetMapping` is an
        # already-shipped annotation, and no engine exists yet to give SSE
        # its own handling (that is later 2H work; this fixture's GraphQL,
        # WebSocket and STOMP surfaces derive NO rows at all, by design —
        # nothing here catalogs those annotations yet). Neither route merges
        # with anything else in the fixture.
        ("GET", "/events/emitter"),
        ("GET", "/events/stream"),
        # 2H Task 2: the GraphQL surface — eight rows across three catalogs
        # and one engine, and the `method` column carries the OPERATION TYPE
        # rather than an HTTP verb (D01 identity `(graphql, query|mutation|
        # subscription, <field>)` for a root operation, `(graphql, NULL,
        # Type.field)` for a resolver). No graphql path collides with an HTTP
        # one, so the set still tells every row apart.
        #
        # `orderById` is the explicit-value case; `orders`, `placeOrder` and
        # `orderUpdates` are the DEFAULTED case, and they are the whole reason
        # `path_fallback: construct_name` exists — all three declare their
        # name attribute `default ""`, which never reaches the class file, so
        # before the form they derived `path: ''` at `resolved` (four wrong
        # rows, checkpoint answer 1). The empty-path regression below pins
        # that they cannot come back.
        ("query", "orderById"),
        ("query", "orders"),
        ("mutation", "placeOrder"),
        ("subscription", "orderUpdates"),
        # The non-root resolvers, composed from two attributes on ONE
        # method-level annotation: `@SchemaMapping(typeName = "Order", field =
        # "lines")` spells both halves, `@BatchMapping(typeName = "Order")`
        # spells only the first and takes `totals` from the method name — the
        # two forms composing, which is what makes them one mechanism rather
        # than two special cases. Verbless: a resolver is not a root
        # operation, so `method` is NULL.
        (None, "Order.lines"),
        (None, "Order.totals"),
        # `CustomerGraphqlController`, the CLASS-level scope shape: the type
        # states `typeName = "Customer"` once and `nickname` names only its
        # own field, so the scope is read one level out. `shipTo` spells its
        # own `typeName = "Order"` and that WINS over the class's — the nearer
        # declaration is the more specific, which is why it lands under
        # `Order.` and not `Customer.`.
        (None, "Customer.nickname"),
        (None, "Order.shipTo"),
        # NOT here, and asserted absent below: `OrderGraphqlController
        # #orphanField`'s `@SchemaMapping(field = "orphan")`. No scope on the
        # method, none on the class — Spring infers it from the parameter
        # type, a fact no annotation carries — so the row is REFUSED rather
        # than derived as the bare `orphan`, which would claim a
        # root-operation-shaped identity for a resolver.
        # The amended acceptance test (2H design §1): these rows come from
        # `netflix-dgs.yml` and `microprofile-graphql.yml`, which ride the two
        # forms `spring-graphql.yml` introduced with ZERO further engine
        # change. `Order.dgsLines` is the DGS spelling of the qualifier —
        # `parentType` where Spring says `typeName` — through the same form.
        # Asserted explicitly, by catalog, below.
        ("query", "dgsOrders"),
        (None, "Order.dgsLines"),
        ("query", "mpOrders"),
        # 2H Task 5: the WebSocket/STOMP surface — verbless like every other
        # messaging row (D02 §2, amended), `method` NULL. `LiveEndpoint`'s
        # `@ServerEndpoint("/live")` + `@OnMessage onFrame` is the
        # `@KafkaHandler` prefix shape (checkpoint answer 5): no HTTP or
        # messaging path collides with it.
        (None, "/live"),
        # `OrderStompController`: class-level `@MessageMapping("/orders")`
        # composes with `place`'s own `@MessageMapping("/place")` and
        # `board`'s `@SubscribeMapping("/board")` — bare `prefix || suffix`,
        # no separator, matching the fixture's own source comments exactly.
        (None, "/orders/place"),
        (None, "/orders/board"),
        # `place`'s own `@SendTo("/topic/order-placed")` — the reply block's
        # resolved row (D02 §2's `reply`, spring-kafka.yml's own precedent,
        # now serving a second protocol with zero engine change).
        (None, "/topic/order-placed"),
        # W43, `G-33`: `OrderStompPublisher#announce`'s own
        # `SimpMessagingTemplate.convertAndSend("/topic/order-announced", order)` — the
        # OUTBOUND half of this module's STOMP surface, which nothing read before it. The
        # destination resolves from the call's string literal even though the descriptor
        # types it `Object`, because `convertAndSend` is declared on
        # `MessageSendingOperations<D>` and `D` erases.
        #
        # `announceToDefault` takes no destination argument at all and shares the existing
        # `(None, None)` tuple, exactly as `board`'s dynamic reply does — the SET gains one
        # entry for two new rows, and the count below gains two.
        (None, "/topic/order-announced"),
        # W44, `G-29`: the three servlet functional routes under `/mvcfn`. Verbed, unlike
        # every websocket row above — a functional route declares an HTTP method the same
        # way an annotated one does, and the nested `path("/mvcfn")` prefix composes onto
        # each exactly as a class-level `@RequestMapping` would.
        ("GET", "/mvcfn/invoices"),
        ("POST", "/mvcfn/invoices"),
        ("PUT", "/mvcfn/invoices/{id}"),
        # W45, `G-42`: the URLs a STOMP client opens. Verbless, like every other websocket
        # row — a handshake path declares no HTTP method — and three of them from TWO
        # calls, because `addEndpoint("/ws-alt", "/ws-legacy")` registers both.
        (None, "/ws"),
        (None, "/ws-alt"),
        (None, "/ws-legacy"),
        # W46, `G-32`: the three URLs this module OPENS. Verbless like every websocket
        # row, and the whole URL is the path with `peer` NULL — one address shape across
        # every client row, because the `channel_via` rung that reads the two jakarta ones
        # is peerless by construction and splitting only the literal row would publish two.
        (None, "ws://feeds.example.com/orders"),
        (None, "ws://feeds.example.com/audit"),
        (None, "ws://feeds.example.com/stomp"),
        # `board` is ALSO value-returning (`OrderView`) and declares no
        # `@SendTo` — the SAME dynamic-reply shape `escalate`'s own kafka row
        # keeps (comment above, line ~285): a path-NULL, `unresolved` reply
        # row. It shares the existing `(None, None)` tuple already in this
        # set, so the SET gains no new entry for it even though the endpoint
        # count below does (asserted by caller below).
        #
        # 2I Task 2: the Spring-WS surface — verbless like every other
        # non-HTTP row (D02 §2, amended), `method` NULL, because a SOAP
        # operation declares no HTTP-style verb: the transport binding's own
        # POST is shared by every operation on the port and identifies none of
        # them.
        #
        # `OrderSoapEndpoint#placeOrder`'s `@PayloadRoot(namespace, localPart)`
        # — the QName identity form, composed by `qualifier_format: qname`
        # into ONE bracketed token. The braces are the notation, not
        # decoration: `{ns}local` is how a payload root is written everywhere
        # a human would read it back.
        (None, "{http://orders.example.com/ws}placeOrderRequest"),
        # `cancelOrder`'s `@SoapAction` — the SECOND identity form the same
        # catalog carries, and deliberately NOT a QName: a SOAPAction is an
        # opaque header URI, so it lands verbatim with no qualifier at all
        # (`@SoapAction` declares no `namespace` attribute, so the shared
        # `qualifier_from: [namespace]` reads NULL for it and composes no
        # braces). Two identity forms, one mapping block, no engine branch.
        (None, "http://orders.example.com/action/cancelOrder"),
        # `amendOrder` carries TWO `@PayloadRoot`, which is how Spring-WS routes two
        # message types to one handler — `@PayloadRoot` declares itself
        # `@Repeatable(PayloadRoots.class)` and
        # `PayloadRootAnnotationMethodEndpointMapping` resolves through
        # `getMergedRepeatableAnnotations`. Both derive because `spring-ws.yml` names the
        # container (`G-36`); before that the second message was served in production and
        # absent from the document. Proven independently by
        # `tests/e2e/test_soap_delivered.py`, which fails if either goes missing.
        (None, "{http://orders.example.com/ws}amendOrderRequest"),
        (None, "{http://orders.example.com/ws}reviseOrderRequest"),
        # Five features delivered 2026-09-11, each with an intention test in
        # `tests/e2e/test_*_delivered.py` that fails without it:
        # `G-39` — `@DgsData` is `@Repeatable`; one resolver serves two fields.
        (None, "Order.dgsTotal"),
        (None, "Order.dgsSubtotal"),
        # `G-40` — `@DgsEntityFetcher(name = "Order")`: Federation's entity path, keyed by TYPE.
        (None, "Order"),
        # `G-34` — `ServerEndpointConfig.Builder.create(Class, "/ws/tickets")`.
        (None, "/ws/tickets"),
        # `G-43` — the same `SendMessageRequest`, handed to `SqsAsyncClient`.
        (None, "/123456789012/async-queue"),
        #
        # 2I Task 2 (controller ruling): the JAX-WS surface, `jakarta-jws.yml`.
        # `BillingWebService#charge`'s own `@WebMethod(operationName)`, scoped
        # by the namespace its CLASS states once for every operation it holds.
        (None, "{http://billing.example.com/ws}chargeOrder"),
        # `refund` carries NO annotation at all — the DR-6 row, derived by the
        # class-gate member rule (`members: public_methods`) and named by
        # `path_fallback`, because JAX-WS exposes a public method whether or
        # not `@WebMethod` customizes it. A catalog deriving only the annotated
        # methods would report this service missing one of its own operations
        # while presenting the rest as complete.
        (None, "{http://billing.example.com/ws}refund"),
        # `LegacyBillingWebService` is the JAVAX spelling with a BARE
        # `@WebService`, so it pins two things at once: both gate spellings
        # reach the derivation through `mapping.annotations` (a list, where
        # `type_annotation` is one fqn), and the namespace is the
        # reversed-package default — `com.example.orders.soap` →
        # `http://soap.orders.example.com/`, trailing slash included, exactly
        # what both reference implementations compute (checkpoint item 2).
        (None, "{http://soap.orders.example.com/}legacyCharge"),
        # NOT here, and asserted absent below: `internalAudit`. Its
        # `@WebMethod(exclude = true)` is JAX-WS itself withdrawing the
        # operation, so the `unless` filter derives nothing — and the member
        # rule must not re-derive it under its construct name, which is why
        # that rule's override is keyed on carrying an annotation rather than
        # on having produced a row.
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
    #
    # 2E-prep Task 12 (driver catalogs B: the pubsub trio +
    # spring-kafka-message) adds 6 more, none merging with anything already
    # in the fixture: `google-pubsub-publisher.yml`'s own resolved
    # `raw-events` (outbound, the fluent engine's new `channel`/
    # `channel_via` ladder, this task's own precondition commit);
    # `google-pubsub-client.yml`'s two unresolved rows (outbound, spec §4's
    # deliberate duplicate — the SAME co-located call `raw-events` above
    # also resolves, plus the genuinely field-held `publish` call, both
    # `path` NULL); `google-pubsub-subscriber.yml`'s two resolved rows
    # (inbound, `raw-notify` + `raw-notify-lambda` — a named
    # `MessageReceiver` and a lambda receiver, the `interface_implementation`
    # style's own first shipped catalog); and `spring-kafka-message.yml`'s
    # one row (outbound, `raw-messages` — resolved identity, unresolved
    # overall resolution, standing beside `spring-kafka-template.yml`'s
    # pre-existing `record_arg` sibling, spec §4's ruling again). 62 + 6 =
    # 68.
    #
    # Phase 2E Task 6 (composed annotations, the effective-annotations
    # pre-pass) adds 2 more: `GET /composed` (http inbound,
    # `ComposedController#composed`'s `@ApiGet` resolving through
    # `@RequestMapping`) and `composed-orders` (kafka inbound,
    # `ComposedListener#onComposedEvent`'s `@OrderTopicListener` resolving
    # through `@KafkaListener`) — neither merges with anything already in
    # the fixture. 68 + 2 = 70.
    #
    # Phase 2E Task 7 (inherited mappings) adds 2 more: `GET /api/orders`
    # and `GET /api/composed`, neither merging with anything already in the
    # fixture. `GET /api/orders/{id}` — the naive join's target, per
    # checkpoint item (4) — is asserted absent below rather than merely
    # omitted from the route set above (the honesty pin: a join that DID
    # leak here would silently inflate this same count, and a set
    # comparison alone would not say which row was extra). 70 + 2 = 72.
    #
    # Phase 2E Task 9 (the `combinator` engine, spring-webflux-router.yml)
    # adds 10 more, none merging with anything already in the fixture: 4 off
    # `OrderRoutes#routes` (`GET`+`POST /fn/orders`, `GET`+`HEAD
    # /fn/health`), 3 off `OrderRoutes#composite`/`#other` (`GET /extra`
    # resolved, `GET /other` resolved from `other()`'s own walk, and one
    # unresolved row for `composite()`'s cross-method `.and(other())`
    # reference — sharing the existing `(None, None)` tuple above, so the
    # SET gains no new entry for it even though this count does), and 3 off
    # `KotlinOrderRoutes#ktRoutes`'s `coRouter` DSL (`GET`+`POST /kt/orders`,
    # `GET /kt/rich`, handler NULL on all three). 72 + 10 = 82 — exactly the
    # checkpoint's own frozen target (checkpoint item (5)). Verified live
    # against real bytecode, not computed from the brief alone.
    #
    # 2F Task 3 (the configuration surface fixture) adds 5 more. Four are
    # `BillingClients`' own half-2 WebClient chains (`fieldFedInvoice`/
    # `constructorFedInvoice`/`propertiesFedInvoice`/`computedBaseInvoice`),
    # each feeding its base address through `WebClient.builder().baseUrl(...)`
    # imperatively — a field, a constructor-injected `@Value` parameter, a
    # bound `@ConfigurationProperties` object, and a computed concatenation
    # respectively (fix round 1, review ruling: `baseUrl()` is NOT a
    # declared step in the shipped `spring-webclient.yml` catalog, so it is
    # never consulted — each row derives off its own DISTINCT `.uri()`
    # literal alone, `resolved`, peer NULL, four new tuples in the route
    # SET above). `OrderStreamBindings`' four `@Bean Consumer<OrderEvent>`/
    # `Supplier<OrderEvent>` methods derive nothing at all under the shipped
    # engines (no `single_call`/`fluent` root inside a trivial lambda body)
    # — `config_join` (Task 7) is what eventually reads them. The fifth new
    # row is `AuditJmsListener#onAudit` moving to `${orders.audit.topic}`:
    # its previous merge with `EventProducers#sendAuditMessage`'s own
    # `"audit.queue"` send no longer fires (different literal strings), so
    # the send stands unmerged — `(None, "audit.queue")` keeps its existing
    # tuple in the SET, but the table itself gains a genuine second row
    # (`onAudit`'s inbound row moves to its own new identity;
    # `sendAuditMessage`'s outbound row survives standalone rather than
    # being deleted by the merge). 82 + 5 = 87. Verified live against real
    # bytecode, not computed from the brief alone — this is Task 3's own
    # frozen baseline for Tasks 4-8. The four `BillingClients` rows are
    # expected to change again once Task 8's `base` capture lands
    # (re-freezing, not a bug) — see the review ruling above.
    #
    # 2F Task 7 (`config_join`, the eighth style) adds 4, exactly the
    # checkpoint's own frozen delta (item (5), as amended by its
    # falsification F-3): `spring.cloud.function.definition` selects four
    # entries, and each derives one row — `handleOrder` → `stream-orders`
    # (kafka inbound, resolved), `auditTap` → `audit-tap` (kafka outbound,
    # resolved), `orphanConsumer` → path NULL (the key is declared nowhere,
    # so the binding is recorded unresolved rather than dropped), and
    # `pipeA|pipeB` → path NULL with no bean named at all (the composition
    # degrade). None of the four merges: the two resolved destinations are
    # named by nothing else in the fixture, and a NULL path never dedups
    # (SQL's `NULL = NULL` is unknown). 87 + 4 = 91.
    #
    # 2G Task 5 (declared shapes) adds 1 more: `POST /v1/orders/proto-orders`
    # (`OrderController#createProtoOrder`, a generated-protobuf payload in
    # and out) — no merge, nothing else in the fixture calls it. 91 + 1 = 92.
    #
    # 2G Task 7 (parse binding) adds 5: the bytes-only listeners in
    # `messaging/parse` — two SQS and one JMS row that bind, plus the
    # ambiguous SQS row and the two-hop JMS row that refuse to. Every one of
    # the five destinations is unique to that file, so none merges with
    # anything and none of the existing 92 identities moves. 92 + 5 = 97.
    #
    # 2H Task 1 adds 2 more: `OrderEventsController`'s `/events/emitter` and
    # `/events/stream`, the only new rows the GraphQL/WebSocket/STOMP/SSE
    # fixture surfaces produce — the rest derive nothing under the shipped
    # engines. Neither merges with anything. 97 + 2 = 99.
    #
    # 2H Task 2 adds 11: the whole GraphQL surface, one row per mapped method
    # across three catalogs — 8 from `spring-graphql.yml`
    # (`orderById`/`orders`/`placeOrder`/`orderUpdates` root operations, the
    # `Order.lines`/`Order.totals` resolvers, and
    # `CustomerGraphqlController`'s class-level-scope pair
    # `Customer.nickname`/`Order.shipTo`), 2 from `netflix-dgs.yml`, 1 from
    # `microprofile-graphql.yml`. No two share a wire identity and none
    # collides with an HTTP or messaging row, so all 11 are new rows and none
    # of the existing 99 identities moves. 99 + 11 = 110.
    #
    # TWELVE annotated methods produce those 11 rows: `orphanField` names a
    # field of a type nothing states, so it derives none at all (pinned by
    # `test_a_resolver_whose_scope_no_annotation_states_derives_no_row`).
    # `schema_operations` (2H Task 4) adds nothing to THIS particular
    # count: its one new row (`query auditTrail`) comes from the SDL reader's
    # own `declared_shape`/schema facts, which this fixture never loads (this
    # test's own docstring precedent, `test_the_format_ladder_answers_every_
    # live_row`'s docstring: "this fixture resolves WITHOUT the descriptor
    # interpreter") — pinned instead in `tests/e2e/test_vertical_slice.py`,
    # where the interpreter runs. 110 stands unmoved through Task 4.
    #
    # 2H Task 5 adds 5: the WebSocket/STOMP surface — 3 inbound
    # (`jakarta-websocket.yml`'s `/live`, `spring-stomp.yml`'s
    # `/orders/place`/`/orders/board`) and 2 outbound (`place`'s own
    # `@SendTo`, resolved; `board`'s own dynamic reply, unresolved — the
    # `escalate` shape again, a different protocol). None merges with
    # anything already in the fixture: no messaging destination or HTTP path
    # collides with a WebSocket one, and a `direction: inbound` catalog never
    # meets an outbound row on its own. 110 + 5 = 115.
    #
    # The prefix-seam controllers add 2: `SeamController`'s one route and
    # `RootSeamController`'s one, both inbound http, neither colliding with
    # an existing identity. 115 + 2 = 117. The `path_separator` fix itself
    # adds no row anywhere — it changes the ADDRESS a row carries — which is
    # why every other identity in the set above is unmoved.
    #
    # 2I Task 2 adds 2: `spring-ws.yml`'s two inbound SOAP rows, one per
    # identity form (`@PayloadRoot`'s QName, `@SoapAction`'s header URI).
    # Neither collides with anything: `soap` is its own protocol, so a row
    # here could not merge with an HTTP one even if the strings matched.
    # 117 + 2 = 119.
    #
    # `jakarta-jws.yml` adds 3, one per operation JAX-WS actually exposes:
    # `chargeOrder` (annotated), `refund` (the DR-6 member row, no annotation
    # at all) and `legacyCharge` (javax spelling, reversed-package default).
    # FOUR public methods produce those 3: `internalAudit`'s
    # `@WebMethod(exclude = true)` is the framework withdrawing the operation,
    # so it derives nothing — asserted explicitly below rather than left to
    # this count, since a row lost for the wrong reason counts the same.
    # 119 + 3 = 122.
    #
    # `wsdl-schema.yml` (2I Task 4) adds nothing to THIS particular count, for
    # the exact reason `graphql-schema.yml` (2H Task 4) did not above: its one
    # new row (`{http://orders.example.com/ws}quoteOrderRequest`) comes from
    # the WSDL/XSD reader's own `declared_shape` facts, which this fixture
    # never loads (`resolved_fixture` runs no reader or interpret step —
    # `test_the_format_ladder_answers_every_live_row`'s own docstring) —
    # pinned instead in `tests/e2e/test_vertical_slice.py`, where the
    # interpreter runs. 122 stood unmoved through that task.
    #
    # OI-47 makes it 123. The one added row is `GET /api/orders/{id}` — a
    # mapping the fixture always declared and this pass always lost, because a
    # covariant override's descriptor cannot match its interface's and the only
    # method that can, javac's bridge, was excluded outright. Reading
    # `modifiers.synthetic` and carrying the bridge's mapping across to the
    # method it forwards to recovers it. 122 -> 123 was the whole effect of that.
    #
    # OI-48 makes it 124: `POST /v1/orders/scoped`, added because `ScopedRequest`
    # was referenced by NOTHING, so no endpoint rooted it, so the package-scope
    # nullability rule ran only in a hand-built unit test and never in the
    # pipeline. The fixture could not see the thing it was built to demonstrate.
    #
    # W26 makes it 128: the four `/v1/paged/*` routes. `/totals` is a payload type whose
    # wire contract is in its ACCESSORS — an interface has no fields at all — and the
    # three paged ones are the boundary beside it, returning an envelope whose jar this
    # fixture names in no `extract_libraries`.
    #
    # W27 makes it 134, and every one of the six is a row that ALREADY EXISTED and was
    # being folded away (F5 §6.1). A wire identity the module both serves and calls used
    # to collapse into one `direction: both` row; two of these six were fabrications —
    # a SOAP operation merged with a call to `${soap.billing.uri}`, and `POST /v1/orders`
    # merged with a call to `orders-loop` — and the other four are genuine
    # self-publish/self-consume. Nothing new is derived; six deletions stopped happening.
    # W28 makes it 137: `RoutingConditionsController`'s three handlers on one address.
    # W29 makes it 139: two WebClient chains — one carrying headers, one whose url is
    # built in a lambda and stays honestly pathless (`OI-73`).
    # W27's REVIEW makes it 145, and all six are rows that were being dropped outright.
    # The outbound dedup keyed on wire identity alone — `(protocol, direction, verb,
    # path)` — with a `seen` set spanning every caller in the module, so a second caller
    # on one address was `continue`d away with no row, no `peer` and no question. That is
    # F5 §6.1 rule 1 unmet ("one row per (caller, target)"), and strictly worse than the
    # `both` merge W27 deleted, which at least kept the caller. Two of the six are
    # `SharedPathClients`, added to give the fixture the shape it lacked; the other four
    # were already in the fixture and unseen — a second caller on `/v2/inventory/levels`,
    # another on `/v2/inventory/reserve`, `EventProducers#sendKeyed`'s `order-events`,
    # and a SOAP call to a different billing address.
    # 147 since W43: the two STOMP outbound rows that close `G-33`.
    # 150 since W44: the three `/mvcfn` servlet functional routes that close `G-29`.
    # 153 since W45: the three STOMP connect URLs that close `G-42`.
    # 156 since W46: the three client connects that close `G-32`.
    # 158 since `G-36`: `OrderSoapEndpoint#amendOrder` carries two `@PayloadRoot`,
    # which is how Spring-WS routes two message types to one handler, and the
    # container is now declared so both derive. +2 soap inbound.
    assert len(report.endpoints) == 163
    # 2O Task 6: `spring-data-rest.yml` is the first gated catalog, and this
    # fixture is exactly the module the gate exists for — a Spring module with
    # a repository-shaped interface (`OrderRepository extends
    # Repository<OrderResult, Long>`) and no Spring Data REST anywhere in its
    # build. Ungated it would mint a whole CRUD API here; gated, it is skipped
    # with its reason and the endpoint count above does not move.
    #
    # 2O Task 9 adds the second, and it is the same gate answering honestly
    # about a different framework: this fixture declares no Spring Integration,
    # writes no `@ServiceActivator`, and `spring-integration.yml` is therefore
    # skipped rather than silently finding nothing. The count above does not
    # move for it either — that catalog declares no `key` and mints no endpoint
    # row at all, by design (2O design §5).
    #
    # F2 §3.6 adds the third, and it is the gate doing the job it was extended
    # for: this fixture declares `spring-websocket` and no RSocket coordinate, so
    # `spring-rsocket.yml` is skipped while `spring-stomp.yml` runs. Before W16
    # neither was gated on anything that could tell them apart — `@MessageMapping`
    # is both frameworks' routing annotation, and Spring's own handlers scan for
    # it with the same `@Controller` predicate — so this fixture's five STOMP rows
    # were published on `websocket` with no evidence distinguishing them from
    # RSocket, and adding the RSocket catalog ungated derived five more on
    # `rsocket`. The count above does not move: the skip is what keeps it still.
    # ORDER is the engine ordering `derive_endpoints` sorts by, not the catalog
    # id: `spring-rsocket` is `annotation_driven` and runs before the two
    # dependency-gated styles, which is why it heads the list rather than
    # trailing it alphabetically.
    assert [entry.catalog_id for entry in report.skipped_catalogs] == [
        "spring-rsocket",
        "spring-data-rest",
        "spring-integration",
    ]

    # Task 7: `handler_signature` comes from the IMPLEMENTING method (spec
    # §3's own boundary sentence), never the interface's — shapes and
    # nullability derive from the real implementation types even when, as
    # here, both happen to declare the identical signature.
    inherited_handlers = {
        (e["method"], e["path"]): e["handler"]
        for e in report.endpoints
        if e["path"] in ("/api/orders", "/api/composed", "/api/orders/{id}")
    }
    assert inherited_handlers[("GET", "/api/orders")].endswith(
        "OrdersApiController#list(sig_3f061508)."
    )
    assert inherited_handlers[("GET", "/api/composed")].endswith(
        "OrdersApiController#composed(sig_d5afb768)."
    )
    # OI-47: the covariant case, which used to derive nothing at all. The
    # handler must be the method someone WROTE — `find` returning the covariant
    # `DetailedOrderResult` — never javac's bridge, which carries the
    # interface's own descriptor and is the only thing that can match the join.
    # OI-47's end-to-end proof, on a really compiled class file. `sig_95a78dff`
    # is `(J)Lcom/acme/orders/openapi/DetailedOrderResult;` — the override
    # someone wrote. javac's bridge is `(J)Lcom/acme/orders/OrderResult;`,
    # `sig_4cb6f523`, and it is the only method whose descriptor matches the
    # interface's, so it is what the join finds and what would be published if
    # the mapping were not carried across to the real one.
    assert inherited_handlers[("GET", "/api/orders/{id}")].endswith(
        "OrdersApiController#find(sig_95a78dff)."
    )

    directions: dict[tuple, set[str]] = {}
    for endpoint in report.endpoints:
        directions.setdefault((endpoint["method"], endpoint["path"]), set()).add(
            str(endpoint["direction"])
        )
    assert directions[("POST", "/billing/invoices")] == {"outbound"}
    # Two rows, not one `both` row (W27, F5 §6.1): the module serves `POST /v1/orders`
    # and `OrdersLoopClient` calls that path at `orders-loop`. The merge compared
    # `(protocol, method, path)` and could not see the different host, because `peer` is
    # not part of endpoint identity (RC-5).
    assert directions[("POST", "/v1/orders")] == {"inbound", "outbound"}
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

    # The `uri(uriBuilder -> …)` chain, and this assertion used to read the other way
    # round (`OI-73`, closed in W29): the row derived with `path` NULL and
    # `resolution: unresolved` — a real outbound call with no address at all.
    #
    # That was not a small loss. The address IS the row's identity, DR-5 matches on the
    # wire contract, and `uri(Function)` is the idiomatic way to build a URL with query
    # parameters — so the shape cost every such call its address. The comment here called
    # it "never a guess at the literal inside the builder lambda", and that framing was
    # the mistake: the lambda is ONE argument of ONE call, the fact stream names the
    # synthetic method it compiled to, and reading that method's own call sites is
    # reading rather than guessing.
    [search_row] = [
        e
        for e in report.endpoints
        if e["caller"] and e["caller"].endswith("InventoryWebClient#search(sig_e02a4703).")
    ]
    assert search_row["method"] == "GET"
    assert search_row["path"] == "/v2/inventory/search"
    assert search_row["resolution"] == "resolved"

    # The flatMap lambda's own chain derives `POST /v2/inventory/reserve` in its own
    # synthetic method — the dataflow pass has to scan the `lambda$reserveAfterLevels$N`
    # method, not just the enclosing method, to find it.
    #
    # **Two callers, two rows** (F5 §6.1 rule 1). Until W27's review this collapsed with
    # `reserve()`'s own identical row and the surviving one was "whichever caller sorts
    # first" — a real caller deleted, and this comment used to say so in as many words
    # while asserting the sort order rather than the rule. Both are genuine call sites and
    # both stand. The numeric suffix is javac's per-class lambda counter, which different
    # compiler versions assign in different orders, so only the stable stem is pinned.
    reserve_rows = [
        e for e in report.endpoints if (e["method"], e["path"]) == ("POST", "/v2/inventory/reserve")
    ]
    assert len(reserve_rows) == 2
    assert any("lambda$reserveAfterLevels$" in e["caller"] for e in reserve_rows)
    # The signature hash is javac's, so only the member name is pinned — the same reason
    # the lambda's counter above is not.
    assert any("InventoryWebClient#reserve(sig_" in e["caller"] for e in reserve_rows)

    # Task 5: OrderController's two media-declaring routes fill consumes/
    # produces off their own `@GetMapping`/`@PostMapping` attributes (spec §4
    # evidence kind (a)); every other row in the fixture — `create`'s own
    # bare `@PostMapping` among them — derives both NULL, the fixture's own
    # NULL-stays-NULL pin (no declaration is a guessed default, D01 §4).
    media = {(e["method"], e["path"]): (e["consumes"], e["produces"]) for e in report.endpoints}
    assert media[("GET", "/v1/orders/{id}")] == (None, '["application/json"]')
    assert media[("POST", "/v1/orders/detailed")] == (
        '["application/json"]',
        '["application/json"]',
    )
    assert media[("POST", "/v1/orders")] == (None, None)

    # Phase 2E Task 9 (the `combinator` engine): the WebFlux router tree's
    # own pins, verified live against real bytecode rather than hand-derived
    # (checkpoint item (5)).
    combinator_rows = {
        (e["method"], e["path"]): e
        for e in report.endpoints
        if e["catalog_id"] == "spring-webflux-router"
    }
    assert len(combinator_rows) == 10
    # Java: a bound method reference resolves to the real handler; the inline
    # lambda resolves to its synthetic body — both module-prefixed, joined
    # against the scanned symbol facts, never fabricated (checkpoint (1a)).
    assert combinator_rows[("GET", "/fn/orders")]["handler"].endswith(
        "RouteHandlers#listOrders(sig_a2451eb8)."
    )
    assert combinator_rows[("POST", "/fn/orders")]["handler"].endswith(
        "RouteHandlers#createOrder(sig_a2451eb8)."
    )
    assert (
        combinator_rows[("GET", "/fn/health")]["handler"]
        == combinator_rows[("HEAD", "/fn/health")]["handler"]
    )
    # The counter in `lambda$routes$N` is javac's private bookkeeping and the
    # two JDKs this project builds with disagree: javac 21 numbers per CLASS,
    # javac 26 per METHOD. `routes` happens to hold the first lambda in this
    # file, so both spell it `$0` today — and it stops being true the moment a
    # lambda is added to a method declared above it, as a JDK-21-only failure.
    # Matched rather than pinned for the same reason
    # `tests/ingress/test_asm_scanner.py` normalises it: the enclosing method
    # and the signature are what this asserts, never the counter.
    assert re.search(
        r"OrderRoutes#lambda\$routes\$\d+\(sig_a2451eb8\)\.$",
        combinator_rows[("GET", "/fn/health")]["handler"],
    )
    # `composite()`'s cross-method `.and(other())` reference derives one
    # unresolved row, `(None, None)` — asserted by caller, since its own
    # identity is unreadable by design (spec §1c: the walk is per-method,
    # and following the reference is a deliberate boundary, never silence);
    # `other()` derives `GET /other`, resolved, from its own independent
    # walk — two distinct facts about one method name (checkpoint (1a)'s
    # frozen "consequence").
    assert combinator_rows[("GET", "/extra")]["resolution"] == "resolved"
    assert combinator_rows[("GET", "/other")]["resolution"] == "resolved"
    assert combinator_rows[("GET", "/other")]["caller"].endswith("OrderRoutes#other(sig_2e6d7578).")
    composite_unresolved = combinator_rows[(None, None)]
    assert composite_unresolved["resolution"] == "unresolved"
    assert composite_unresolved["caller"].endswith("OrderRoutes#composite(sig_30e7fc92).")
    # Kotlin: `coRouter`'s own handlers arrive as `instance` of a generated
    # class, never a method reference — Tier-0, honestly NULL rather than
    # fabricated (checkpoint (1b)).
    kt_rows = [row for (m, p), row in combinator_rows.items() if p and p.startswith("/kt/")]
    assert {(row["method"], row["path"]) for row in kt_rows} == {
        ("GET", "/kt/orders"),
        ("POST", "/kt/orders"),
        ("GET", "/kt/rich"),
    }
    assert all(row["handler"] is None for row in kt_rows)
    # F1, and the boundary it named is CLOSED (2O Task 13). This assertion
    # read "every predicate-derived media column on every combinator row is
    # NULL — the vararg `accept`/`contentType` constants are unreadable
    # (checkpoint (3))". They are readable since extractor capability 9.15 put
    # the constants in the array slot's own `elements`, and the engine reads
    # them now. What F1 ruled is untouched and still pinned below: an
    # unreadable media constant never moves `resolution`.
    media = {(m, p): (row["consumes"], row["produces"]) for (m, p), row in combinator_rows.items()}
    assert media[("GET", "/fn/orders")] == (None, '["application/json"]')
    assert media[("POST", "/fn/orders")] == ('["application/json"]', None)
    assert media[("GET", "/kt/rich")] == (None, '["application/json"]')
    # Every OTHER combinator row declares no media predicate at all, so its
    # columns stay NULL — the read fires where a declaration exists and
    # nowhere else.
    assert {
        columns
        for (m, p), columns in media.items()
        if (m, p) not in {("GET", "/fn/orders"), ("POST", "/fn/orders"), ("GET", "/kt/rich")}
    } == {(None, None)}


# --- 2H Task 2: the GraphQL surface, live on real bytecode ---------------
#
# Pinned from the live run THAT task froze: 110 endpoints, extractor 9.9.
# The counts have moved with every task since (122 now); the extractor is
# 9.12 as of 2I Task 6's library origin tier. Both numbers are kept as the
# historical record of what this section was written against.


def _graphql_rows(report: ResolveReport) -> dict[tuple[str | None, str | None], dict]:
    """The graphql rows keyed by their D01 wire identity — `(method, path)`,
    where `method` is the OPERATION TYPE for a root operation and NULL for a
    resolver. One row per key: no two GraphQL declarations in the fixture
    share an identity."""
    rows = [e for e in report.endpoints if e["protocol"] == "graphql"]
    keyed = {(e["method"], e["path"]): e for e in rows}
    assert len(keyed) == len(rows), "two graphql rows shared one wire identity"
    return keyed


def test_the_graphql_surface_derives_its_eleven_operations(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """2H design §1, live: three catalogs, one `annotation_driven` engine,
    eleven rows — every one `resolved`/`compiler`, and each attributed to the
    catalog that derived it.

    The four root operations show both halves of form 1: `orderById` names its
    field explicitly, while `orders`, `placeOrder` and `orderUpdates` name
    nothing and take the method's own name. The resolvers show form 2 at both
    levels: `Order.lines` composes two attributes spelled on one annotation,
    `Order.totals` composes the first with form 1's fallback for the second,
    and `Customer.nickname` takes its scope from the enclosing type while
    naming only its own field — which is the point of writing them as two
    composable forms rather than one GraphQL-shaped rule.
    """
    _, report = resolved_fixture
    rows = _graphql_rows(report)

    assert set(rows) == {
        ("query", "orderById"),
        ("query", "orders"),
        ("mutation", "placeOrder"),
        ("subscription", "orderUpdates"),
        (None, "Order.lines"),
        (None, "Order.totals"),
        (None, "Customer.nickname"),
        (None, "Order.shipTo"),
        ("query", "dgsOrders"),
        # `G-39`/`G-40` — fourteen now; the name is kept because renaming a test to its
        # current count is the kind of drift a count in a name invites.
        (None, "Order.dgsTotal"),
        (None, "Order.dgsSubtotal"),
        (None, "Order"),
        (None, "Order.dgsLines"),
        ("query", "mpOrders"),
    }
    for row in rows.values():
        assert (row["direction"], row["resolution"], row["evidence"]) == (
            "inbound",
            "resolved",
            "compiler",
        )
        # A GraphQL operation is served by code in this module, never called
        # by it, so every row names a handler and no row names a caller.
        assert row["handler"] is not None
        assert row["caller"] is None

    handlers = {key: row["handler"] for key, row in rows.items()}
    assert handlers[("query", "orderById")].endswith("OrderGraphqlController#byId(sig_079d928d).")
    assert handlers[("query", "orders")].endswith("OrderGraphqlController#orders(sig_3f061508).")
    assert handlers[("mutation", "placeOrder")].endswith(
        "OrderGraphqlController#placeOrder(sig_079d928d)."
    )
    assert handlers[("subscription", "orderUpdates")].endswith(
        "OrderGraphqlController#orderUpdates(sig_ed469b30)."
    )
    assert handlers[(None, "Order.lines")].endswith(
        "OrderGraphqlController#orderLines(sig_f5672381)."
    )
    assert handlers[(None, "Order.totals")].endswith("OrderGraphqlController#totals(sig_5ed41d1a).")
    assert handlers[(None, "Customer.nickname")].endswith(
        "CustomerGraphqlController#nickname(sig_03276a7b)."
    )
    assert handlers[(None, "Order.shipTo")].endswith(
        "CustomerGraphqlController#shipTo(sig_03276a7b)."
    )
    assert handlers[("query", "dgsOrders")].endswith("DgsOrderFetcher#dgsOrders(sig_3f061508).")
    assert handlers[(None, "Order.dgsLines")].endswith("DgsOrderFetcher#dgsLines(sig_f5672381).")
    assert handlers[("query", "mpOrders")].endswith("MpOrderApi#mpOrders(sig_3f061508).")


def test_a_class_level_scope_reaches_a_resolver_that_names_only_its_field(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """2H design §1's class-level bullet, live.

    `CustomerGraphqlController` carries `@SchemaMapping(typeName = "Customer")`
    on the CLASS. `nickname` spells neither half — the scope comes from the
    type, the field name from the method — and `shipTo` spells its own
    `typeName = "Order"`, which WINS over the class's. Both cases sit on one
    fixture class deliberately: precedence is only observable where the two
    levels disagree.
    """
    _, report = resolved_fixture
    rows = _graphql_rows(report)

    assert (None, "Customer.nickname") in rows
    assert (None, "Order.shipTo") in rows
    # The class-level value did not leak onto the method that overrode it.
    assert (None, "Customer.shipTo") not in rows


def test_a_resolver_whose_scope_no_annotation_states_derives_no_row(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """`OrderGraphqlController#orphanField` carries
    `@SchemaMapping(field = "orphan")` with no `typeName`, on a class that
    states none either — Spring infers the parent type from the resolver's
    PARAMETER, which is a fact no annotation carries.

    So the row is refused. The alternative is not "a slightly vague row": a
    bare `orphan` is a DIFFERENT wire identity from the `Something.orphan` the
    code actually declares — a top-level shape for a declaration that is not
    one — published at `resolved`/`compiler` where nothing downstream could
    tell it from an observation. Silence is the honest answer.
    """
    _, report = resolved_fixture
    rows = _graphql_rows(report)

    assert (None, "orphan") not in rows
    assert not [key for key in rows if key[1] is not None and key[1].endswith("orphan")]
    # And the handler appears nowhere in the table at all — the row is not
    # derived-then-blanked, it is never derived.
    assert not [e for e in report.endpoints if e["handler"] and "orphanField" in str(e["handler"])]


def test_dgs_and_microprofile_ride_the_shared_vocabulary_with_no_rules_of_their_own(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """2H design §1's AMENDED acceptance test.

    The original claim — three catalogs on an unchanged engine — was falsified
    by this task's checkpoint: all three frameworks default their field-name
    attribute to `""`, which never reaches the class file, so an absent value
    derived `path: ''`. The ruling moved the zero-change proof to where it is
    meaningful: `spring-graphql.yml` motivated two framework-neutral forms,
    and DGS and MicroProfile must then be pure YAML.

    That is what `catalog_id` pins here: three rows derived by two catalogs
    that are pure YAML.

    What the rows prove, stated exactly. `dgsOrders` and `mpOrders` both SPELL
    their field names, so neither exercises form 1 — they prove the ordinary
    projection reaches a second and third framework unchanged. `Order.dgsLines`
    is the one that exercises a form: `@DgsData(parentType, field)` composes
    through `qualifier_from` reading `parentType`, where Spring's own catalog
    reads `typeName` — the same engine form, a different attribute name, which
    is the whole claim that the forms describe a declaration pattern rather
    than a library.

    (Form 1 still matters for both frameworks in general — `@DgsQuery.field()`
    and `@Query.value()` are declared `default ""` exactly like Spring's
    `name()` — it is simply not what THIS fixture's rows demonstrate.)
    """
    _, report = resolved_fixture
    rows = _graphql_rows(report)

    dgs = {
        ("query", "dgsOrders"),
        (None, "Order.dgsLines"),
        # `G-39`/`G-40`, 2026-09-11, and still pure YAML: `container:` is the shared
        # repeatable-annotation vocabulary five other catalogs use, and the entity
        # fetcher's `name` is one more alias in the same `path_from` list — no engine
        # branch either way, which is what this test exists to keep true.
        (None, "Order.dgsTotal"),
        (None, "Order.dgsSubtotal"),
        (None, "Order"),
    }
    assert {rows[key]["catalog_id"] for key in dgs} == {"netflix-dgs"}
    assert rows[("query", "mpOrders")]["catalog_id"] == "microprofile-graphql"
    assert {
        rows[key]["catalog_id"] for key in rows if key not in dgs | {("query", "mpOrders")}
    } == {"spring-graphql"}


def test_an_absent_annotation_attribute_never_derives_an_empty_path(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """The regression this task's two forms exist to make impossible.

    An empty `path` is not a small error. The row is still `resolved` with
    `compiler` evidence, so it publishes an endpoint that confidently
    addresses nothing, and D01 identity is `(protocol, direction, method,
    path)` — so several such rows collide with each other as well as being
    individually wrong. D02 §2 already names this failure mode for
    `path_from` ("wrong output rather than a missing one"); an unread default
    reached it by a second route.

    Framework-neutral and whole-table on purpose, rather than scoped to the
    graphql rows: no catalog shipped today has any business deriving an
    empty address, so the invariant is the pin. Verified to hold BEFORE this
    task as well — the four bad rows appeared only under a candidate
    `spring-graphql.yml` written without the forms, never under a shipped
    catalog — which is what makes it a regression pin and not a new rule.
    """
    _, report = resolved_fixture

    assert [
        (e["protocol"], e["method"], e["path"], e["catalog_id"])
        for e in report.endpoints
        if e["path"] == ""
    ] == []


# --- 2H Task 5: WebSocket/STOMP, end to end, on real bytecode ------------


def _websocket_row(report: ResolveReport, direction: str, path: str | None) -> dict:
    [row] = [
        e
        for e in report.endpoints
        if e["protocol"] == "websocket" and e["direction"] == direction and e["path"] == path
    ]
    return row


def test_a_jakarta_websocket_frame_handler_derives_a_verbless_row_with_no_shapes_or_format(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """`LiveEndpoint`'s class-level `@ServerEndpoint("/live")` + method-level
    `@OnMessage onFrame(String frame)` — checkpoint answer 5's `@KafkaHandler`
    prefix shape (a scalar type-level annotation doubling as
    `prefix_annotation`, an argless method-level one composing an empty
    suffix onto it), verified live rather than only unit-tested.

    Both shapes stay NULL (`jakarta-websocket.yml` deliberately declares no
    `request_body` block at all, and `onFrame` returns `void`) and format
    stays unresolved: a raw WebSocket frame is untyped by definition, and
    nothing in the ladder may narrow it — not even rung 5's Jackson-presence
    default, which requires a declared payload TYPE this row has none of.
    """
    _, report = resolved_fixture
    row = _websocket_row(report, "inbound", "/live")

    assert row["method"] is None
    assert row["handler"].endswith("LiveEndpoint#onFrame(sig_a7421bf5).")
    assert row["resolution"] == "resolved"
    assert row["catalog_id"] == "jakarta-websocket"
    assert row["request_shape"] is None
    assert row["response_shape"] is None
    assert row["format"] is None
    assert row["format_resolution"] == "unresolved"


def test_a_stomp_class_level_prefix_composes_with_both_its_method_mappings(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """`OrderStompController`'s class-level `@MessageMapping("/orders")`
    composes with `place`'s own `@MessageMapping("/place")` AND `board`'s
    `@SubscribeMapping("/board")` — bare `prefix || suffix`, no separator,
    exactly the fixture's own source comments (checkpoint answer 5) —
    proving `@MessageMapping` plays both the `prefix_annotation` role (class
    level) and an ordinary `mapping.annotations` entry (method level) in one
    catalog with no collision, the same double duty spring-kafka.yml's
    class-level `@KafkaListener` already plays for `@KafkaHandler`.

    `place`'s own bare, unannotated `OrderView order` parameter reaches
    `request_shape` through the `sole_unannotated` fallback (the same
    `@Payload` vocabulary spring-kafka.yml/spring-jms.yml already read);
    `board` declares no parameter at all, so it derives no request shape."""
    _, report = resolved_fixture
    place = _websocket_row(report, "inbound", "/orders/place")
    board = _websocket_row(report, "inbound", "/orders/board")

    assert place["method"] is None and board["method"] is None
    assert place["handler"].endswith("OrderStompController#place(sig_961974f8).")
    assert board["handler"].endswith("OrderStompController#board(sig_26be7569).")
    for row in (place, board):
        assert row["resolution"] == "resolved"
        assert row["catalog_id"] == "spring-stomp"
    assert json.loads(place["request_shape"])["shape_id"] == "com/acme/orders/contracts/OrderView#"
    assert json.loads(place["response_shape"])["shape_id"] == "com/acme/orders/contracts/OrderView#"
    assert board["request_shape"] is None
    assert json.loads(board["response_shape"])["shape_id"] == "com/acme/orders/contracts/OrderView#"


def test_a_stomp_handlers_sendto_reply_derives_a_resolved_outbound_row(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """`place`'s own `@SendTo("/topic/order-placed")` — D02 §2's `reply`
    block, spring-kafka.yml's own precedent, now pointed at a second
    protocol with zero engine change (the checkpoint's own ruling). The
    reply's payload is `place`'s own return type (`OrderView`), carried as
    the reply row's `request_shape` exactly as `annotation_driven.py::
    _reply_row` documents — a reply has no `response_shape` of its own."""
    _, report = resolved_fixture
    reply = _websocket_row(report, "outbound", "/topic/order-placed")

    assert reply["method"] is None
    assert reply["handler"] is None
    assert reply["caller"].endswith("OrderStompController#place(sig_961974f8).")
    assert reply["resolution"] == "resolved"
    assert reply["catalog_id"] == "spring-stomp"
    assert json.loads(reply["request_shape"])["shape_id"] == "com/acme/orders/contracts/OrderView#"
    assert reply["response_shape"] is None


def test_a_value_returning_stomp_handler_with_no_sendto_derives_an_unresolved_reply_row(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """`board`'s own `@SubscribeMapping` handler ALSO returns `OrderView` and
    declares no `@SendTo` at all — the SAME dynamic-reply shape kafka's own
    `escalate` listener already exercises (`test_a_value_returning_listener_
    with_no_sendto_derives_an_unresolved_reply_row`, above): the reply
    destination is real (a STOMP client that subscribed gets a reply) but
    unnamed anywhere this catalog's own annotations can see, so the row is
    `path` NULL, `unresolved` — never silently dropped (D02 §2's
    unresolved-is-an-answer). It shares the `caller`, but not the wire
    identity, with `board`'s own inbound row above."""
    _, report = resolved_fixture
    [reply] = [
        e
        for e in report.endpoints
        if e["protocol"] == "websocket"
        and e["direction"] == "outbound"
        and e["caller"] is not None
        and "OrderStompController#board(" in e["caller"]
    ]

    assert reply["path"] is None
    assert reply["method"] is None
    assert reply["resolution"] == "unresolved"
    assert reply["catalog_id"] == "spring-stomp"
    assert json.loads(reply["request_shape"])["shape_id"] == "com/acme/orders/contracts/OrderView#"


# --- 2H Task 6: `protocol_hint`, live on real bytecode -------------------
#
# Pinned from the live run THAT task froze: still 115 endpoints, extractor
# 9.9 (122 and 9.12 now — see the 2H Task 2 header above). Nothing here adds
# a row — every assertion below is about rows that already existed reading a
# different protocol.


def _soap_row(report: ResolveReport, path: str, direction: str = "inbound") -> dict:
    """One SOAP row by identity AND direction.

    The direction became necessary with W27 (F5 §6.1): a QName the module both serves and
    calls is two rows now, where the merge used to leave one. Naming the side is what
    these tests mean anyway — every one of them is about a served operation.
    """
    [row] = [
        e
        for e in report.endpoints
        if e["protocol"] == "soap" and e["path"] == path and e["direction"] == direction
    ]
    return row


def test_a_payload_root_derives_its_qname_identity_from_two_attributes_of_one_annotation(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """2I design §2, word 1, live. `OrderSoapEndpoint#placeOrder`'s
    `@PayloadRoot(namespace, localPart)` states BOTH halves of one QName on
    one annotation, and `qualifier_format: qname` composes them into the one
    bracketed token a human would read back — `{namespace}localPart`.

    The two attributes play different roles and are named exactly once each:
    `namespace` in `qualifier_from`, `localPart` in `path_from`. Listing
    `localPart` as a second `qualifier_from` alias would qualify the name with
    ITSELF wherever a `@PayloadRoot` stated only a local part, since that key
    is an alias list where the first present attribute wins.

    Verbless (`method` NULL) like every non-HTTP row: the transport binding's
    POST is shared by every operation on the port and identifies none of them.

    `request_shape` comes from the `@RequestPayload` parameter through the
    STRICT body rule (`fallback: none`) — Spring-WS's own
    `PayloadMethodArgumentResolver` binds a payload argument only where that
    annotation is actually present, so an unannotated parameter is not a
    payload here the way a messaging catalog's bare parameter is."""
    _, report = resolved_fixture
    row = _soap_row(report, "{http://orders.example.com/ws}placeOrderRequest")

    assert row["method"] is None
    # `inbound`, and it read `both` until W27 (F5 §6.1). `BillingSoapClient` calls an
    # operation whose payload type's `@XmlRootElement` states this same QName, and the
    # two rows were merged on that basis — publishing the module's own served operation
    # and a call to `${soap.billing.uri}` as ONE endpoint. They share a QName because
    # they share a payload TYPE, which is not identity. The call is still recorded, as
    # its own outbound row, with a `self_exchange` question naming both sides.
    assert row["direction"] == "inbound"
    assert row["handler"].endswith("OrderSoapEndpoint#placeOrder(sig_fd19bfc7).")
    assert row["resolution"] == "resolved"
    assert row["evidence"] == "compiler"
    assert row["catalog_id"] == "spring-ws"
    assert (
        json.loads(row["request_shape"])["shape_id"]
        == "com/example/orders/soap/payload/PlaceOrderRequest#"
    )
    assert json.loads(row["response_shape"])["shape_id"] == "com/acme/orders/contracts/OrderView#"


def test_a_soap_action_derives_its_header_uri_verbatim_beside_the_qname_rows(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """The SECOND identity form the same catalog carries, and the reason it
    needed no second mapping block: `@SoapAction` dispatches on the
    transport's SOAPAction header, so its address is that URI verbatim — NOT
    a QName, and NOT bracketed.

    That falls out of the shared vocabulary rather than a branch: the one
    `qualifier_from: [namespace]` list reads NULL on an annotation that
    declares no `namespace` attribute at all, and an absent qualifier composes
    no braces (the same "an empty half takes no separator with it" rule the
    2H seam keeps). The one `path_from: [localPart, value]` list likewise
    reads `value` here and `localPart` there, first present wins, because the
    two annotations' attribute names are disjoint.

    Same handler class, same catalog, same protocol as the QName row above —
    so a catalog that had collapsed the two forms would show up here as a
    bracketed action URI rather than as a missing row."""
    _, report = resolved_fixture
    row = _soap_row(report, "http://orders.example.com/action/cancelOrder")

    assert row["method"] is None
    assert row["direction"] == "inbound"
    assert row["handler"].endswith("OrderSoapEndpoint#cancelOrder(sig_fd19bfc7).")
    assert row["resolution"] == "resolved"
    assert row["catalog_id"] == "spring-ws"
    assert (
        json.loads(row["request_shape"])["shape_id"]
        == "com/example/orders/soap/payload/PlaceOrderRequest#"
    )


def test_a_jax_ws_class_exposes_its_bare_public_method_beside_its_annotated_one(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """DR-6, live: `@WebMethod` CUSTOMIZES an operation, it does not create
    one, so `BillingWebService#refund` — which carries no annotation at all —
    is exposed exactly as `charge` is. That is the class-gate member rule
    (`members: public_methods`), and `refund`'s name comes from
    `path_fallback`, since a member has no name attribute to read.

    Both take the namespace their CLASS states once, through the same
    type-level join a class-level scope has always reached methods by — so the
    annotated row and the member row are qualified identically, which is the
    point: they are the same kind of operation.

    `chargeOrder`, not `charge`: a public method that ALSO matches a
    member-level rule derives ONCE, with that rule's value. A member rule that
    did not defer would have published both spellings of one operation.
    """
    _, report = resolved_fixture
    charge = _soap_row(report, "{http://billing.example.com/ws}chargeOrder")
    refund = _soap_row(report, "{http://billing.example.com/ws}refund")

    for row in (charge, refund):
        assert row["method"] is None
        assert row["direction"] == "inbound"
        assert row["resolution"] == "resolved"
        assert row["evidence"] == "compiler"
        assert row["catalog_id"] == "jakarta-jws"
        # No `request_body` block: a JAX-WS request payload is the generated
        # wrapper element, not the method's own parameters.
        assert row["request_shape"] is None
        assert (
            json.loads(row["response_shape"])["shape_id"] == "com/acme/orders/contracts/OrderView#"
        )
    assert charge["handler"].endswith("BillingWebService#charge(sig_079d928d).")
    assert refund["handler"].endswith("BillingWebService#refund(sig_079d928d).")
    # `charge` derives ONCE — under the annotation's name, never also under
    # its own. Asserted by counting the class's rows rather than by absence,
    # so a second row under any spelling fails here.
    assert len([e for e in report.endpoints if "soap/BillingWebService#" in str(e["handler"])]) == 2


def test_the_javax_spelling_derives_with_the_reversed_package_namespace_default(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """Two facts in one row, and neither is expressible without this task's
    vocabulary.

    `LegacyBillingWebService` carries the PRE-JAKARTA `javax.jws.WebService`,
    a distinct fqn from the jakarta one (checkpoint item 4). It derives because
    both spellings sit in `mapping.annotations` — a LIST — rather than in
    `type_annotation`, which is a single fqn and would have discarded this
    whole class's rows. That closes, for a scope, the javax COVERAGE boundary
    `jakarta-websocket.yml` still carries for a prefix.

    Its `@WebService` is BARE, so the namespace is the framework's own default:
    `com.example.orders.soap` reversed, `http://` in front, trailing slash —
    `http://soap.orders.example.com/`, the exact string both
    `RuntimeModeler#getNamespace` and CXF's `PackageUtils#getNamespace`
    compute (checkpoint item 2). Not a guessed namespace: a spec that DEFINES
    the default is stating a fact about every class in it.
    """
    _, report = resolved_fixture
    row = _soap_row(report, "{http://soap.orders.example.com/}legacyCharge")

    assert row["method"] is None
    assert row["handler"].endswith("LegacyBillingWebService#charge(sig_079d928d).")
    assert row["resolution"] == "resolved"
    assert row["catalog_id"] == "jakarta-jws"


def test_an_excluded_web_method_derives_nothing_under_any_spelling(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """`@WebMethod(exclude = true)` is JAX-WS itself saying the method is NOT
    an operation, so the honest derivation is no row at all — not a row marked
    somehow.

    Asserted under BOTH spellings it could have appeared as, because the
    interesting failure is not the filter missing: it is the filter working and
    the MEMBER rule then re-deriving the same public method under its construct
    name. `internalAudit` is public, and its class is gated, so it is a member
    candidate — the override has to be keyed on carrying an annotation rather
    than on having produced a row, or every `unless` becomes a no-op on a gated
    class.

    `exclude` arrives as a real JSON boolean, never the string `"true"`
    (checkpoint item 4), so this also pins that the comparison reaches the
    value on one representation rather than guessing at its type.
    """
    _, report = resolved_fixture
    paths = {e["path"] for e in report.endpoints}

    assert "{http://billing.example.com/ws}internalAudit" not in paths
    assert "internalAudit" not in paths
    assert not [e for e in report.endpoints if "internalAudit" in str(e["handler"])]


def _route(report: ResolveReport, path: str) -> dict:
    [row] = [e for e in report.endpoints if e["path"] == path and e["handler"] is not None]
    return row


def test_the_two_sse_routes_reclassify_one_by_each_evidence_kind(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """2H design §6, live. Both of `OrderEventsController`'s `@GetMapping`
    routes derive as ordinary HTTP rows — nothing in the annotation says SSE —
    and the `protocol_hint` pass moves both, each on a DIFFERENT evidence
    kind, which is exactly why the fixture carries two:

    * `/events/stream` declares `produces = TEXT_EVENT_STREAM_VALUE`, so the
      MEDIA rung answers it off the row's own `produces` column. Its return
      type would have answered too — but the media rung runs first, and the
      column is there to be read.
    * `/events/emitter` declares NO `produces` at all. Its media column is
      NULL, so the media rung has nothing, and only the RETURN-TYPE rung can
      reach it. Without this row the return-type rung would have no live
      surface at all.

    The two return types are also the two ends of the "marker anywhere in the
    chain" rule (checkpoint answer 6, frozen off this same bytecode):
    `emitterEvents` returns `SseEmitter` FLAT — no type arguments, the marker
    IS the outer symbol — while `streamEvents` returns
    `Flux<ServerSentEvent<OrderView>>`, whose outer symbol is an ordinary
    reactive wrapper and whose marker sits in the MIDDLE link. A rule reading
    only `returns.symbol` would answer the first and miss the second.

    Everything else about both rows is untouched: same direction, same verb,
    same path, same handler, same catalog, same `resolution`. This pass
    writes one column."""
    _, report = resolved_fixture
    emitter, stream = _route(report, "/events/emitter"), _route(report, "/events/stream")

    assert (emitter["protocol"], stream["protocol"]) == ("sse", "sse")
    # Which evidence answered which, read off the rows' own columns.
    assert emitter["produces"] is None and emitter["consumes"] is None
    assert stream["produces"] == '["text/event-stream"]'
    assert (
        json.loads(emitter["handler_signature"])["returns"]["symbol"]
        == "org/springframework/web/servlet/mvc/method/annotation/SseEmitter#"
    )
    returns = json.loads(stream["handler_signature"])["returns"]
    assert returns["symbol"] == "reactor/core/publisher/Flux#"
    assert returns["arguments"][0]["symbol"] == "org/springframework/http/codec/ServerSentEvent#"

    for row in (emitter, stream):
        assert row["direction"] == "inbound"
        assert row["method"] == "GET"
        assert row["resolution"] == "resolved"
        # The catalog that DERIVED the row, unchanged: this pass reclassifies
        # a row, it does not re-attribute it, and `spring-web.yml` is both the
        # deriving catalog and the one whose `protocol_hint` block moved it.
        assert row["catalog_id"] == "spring-web"
    assert emitter["handler"].endswith("OrderEventsController#emitterEvents(sig_6e650372).")
    assert stream["handler"].endswith("OrderEventsController#streamEvents(sig_ed469b30).")


def test_nothing_but_the_two_sse_routes_moves(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """The pass's three promises, read off the whole live table rather than
    off the two rows it touched.

    *Scoped.* Only `spring-mvc.yml`/`spring-web.yml` declare a
    `protocol_hint`, and both are `protocol: http`, so an http row is the only
    thing that CAN move — the graphql, websocket and messaging rows are
    untouchable rather than merely untouched. Their counts are the same
    numbers their own tasks froze.

    *No row created or removed.* 122 before, 122 after: the two rows left the
    http bucket and arrived in the sse one, and nothing else changed size.

    *Every other http row stayed.* The http bucket is exactly two smaller,
    and the identities it lost are exactly the two SSE paths — pinned by
    subtracting them rather than by re-listing 30-odd routes, so a row moving
    for the wrong reason shows up as a missing identity here."""
    _, report = resolved_fixture
    counts: dict[object, int] = {}
    for row in report.endpoints:
        counts[row["protocol"]] = counts.get(row["protocol"], 0) + 1

    assert counts == {
        "graphql": 14,
        # 54 + 2: the prefix-seam controllers, one route each. They ride the
        # same `spring-web.yml` `protocol_hint` every other http row does and
        # are equally untouched by it.
        # 58 since OI-48 added `POST /v1/orders/scoped`; 57, not 56, since OI-47: `GET /api/orders/{id}` is the covariant
        # inherited mapping this pass used to lose with the bridge it was
        # reachable through. One row, and the only movement in this whole map.
        # 62 since W26: the four `/v1/paged/*` routes — one payload described from its
        # accessors, three left open because their envelope's jar is not in reach.
        # 63 since W27: `POST /v1/orders` is two rows, not one. The module serves it and
        # `OrdersLoopClient` calls it at `orders-loop` — a different host, which the
        # merge could not see because `peer` is not part of endpoint identity (RC-5).
        # 66 since W28: three handlers on `/v1/routing/orders`, separated by conditions
        # Spring compares and this table does not carry.
        # 68 since W29: `/v2/inventory/tagged` (the header-carrying chain) and
        # `searched`, whose url is built inside a `uri(Function)` lambda — that one
        # derives a row with `path` NULL and `resolution: unresolved`, which is the whole
        # of `OI-73`: the call is recorded and its address is honestly unread.
        # 72 since W27's REVIEW: four second callers the outbound dedup had been deleting
        # outright (F5 §6.1 rule 1) — `SharedPathClients`' two, a second caller on
        # `/v2/inventory/levels`, and the `reserve` lambda beside its enclosing method.
        "http": 75,
        # 75 since W44: the three `/mvcfn` servlet functional routes (`G-29`), which
        # ride `protocol_hint` exactly as every other http row does.
        "jms": 8,
        # three topics the module both publishes to and consumes — `order-events`,
        # `order-audit`, `order-returns` — each two rows since W27 rather than one merged `both`
        # row. Self-publish/self-consume is real, and so is a client calling somebody else's
        # copy of an address; `self_exchange` asks rather than deciding
        "kafka": 26,
        # `order-notifications`, published and subscribed here, is two rows since W27
        "pubsub": 7,
        "sqs": 8,
        # 2I Task 2: `spring-ws.yml`'s two inbound rows. Untouchable by this
        # pass for the same reason the graphql and messaging buckets are —
        # only an http row carries a `protocol_hint` to be reclassified by.
        # 2 from `spring-ws.yml` + 3 from `jakarta-jws.yml`. `wsdl-schema.yml`
        # (2I Task 4) adds nothing here — same reason `graphql-schema.yml`
        # adds nothing to `graphql` above: this fixture loads no
        # `declared_shape` facts at all (comment above `len(report.endpoints)
        # == 122`).
        # `{http://orders.example.com/ws}placeOrderRequest` is two rows since W27 — the served
        # operation, and `BillingSoapClient`'s call to `${soap.billing.uri}`. They share a QName
        # because they share a payload TYPE, which is not identity
        # 9 since `G-36`: `amendOrder` carries two `@PayloadRoot`, and Spring-WS routes both
        # message types to it. The container is now declared, so both derive rather than the
        # first one only — one handler, two served messages, two rows.
        "soap": 9,
        "sse": 2,
        # 7 since W43: `OrderStompPublisher`'s two `SimpMessagingTemplate.convertAndSend`
        # calls, which are `G-33`'s asymmetry — the module received STOMP and sent none.
        # 10 since W45: the three connect URLs `addEndpoint` registers.
        # 13 since W46: the three this module OPENS — `G-32`'s absent direction.
        "websocket": 14,
    }
    assert sum(counts.values()) == len(report.endpoints) == 163
    assert {e["path"] for e in report.endpoints if e["protocol"] == "sse"} == {
        "/events/emitter",
        "/events/stream",
    }
    # The http rows the reclassification did NOT take, by wire identity: every
    # inbound route the fixture still exposes over plain HTTP.
    assert not {e["path"] for e in report.endpoints if e["protocol"] == "http"} & {
        "/events/emitter",
        "/events/stream",
    }


def test_the_websocket_frame_row_is_untouched_by_the_reclassification(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """`/live` is the nearest neighbour this pass has — another streaming,
    long-lived, HTTP-adjacent channel — and it is out of reach: its protocol
    is `websocket`, which no catalog names as a hint SOURCE, so no evidence on
    it could move it even if it carried some.

    Re-pinned whole rather than by protocol alone (Task 5 froze these same
    values): a raw frame stays untyped and its format stays `unresolved`,
    which is the one live row in this fixture proving the SSE work put nothing
    new into the ladder's weakest rung."""
    _, report = resolved_fixture
    row = _websocket_row(report, "inbound", "/live")

    assert row["protocol"] == "websocket"
    assert (row["format"], row["format_resolution"]) == (None, "unresolved")
    assert row["request_shape"] is None and row["response_shape"] is None


def test_an_sse_rows_format_is_assumed_never_read_off_the_envelope(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """The format-honesty half of 2H design §6, live.

    `text/event-stream` is deliberately absent from `media_formats` — it is
    the ENVELOPE, not the payload — so `/events/stream` carries a declared
    MIME string that the format ladder's rung 2 maps to nothing at all, and
    falls past it. Both rows land on rung 5's framework default instead:
    `json`, at `narrowed`, because Jackson is on this module's classpath and
    NOTHING on either row states the wire.

    `narrowed` is the whole point. An SSE event's `data:` line is JSON in
    practice and by nobody's declaration, and `resolved` here would make that
    convention look like an observation. The rendered document says `json
    (assumed)`.

    Rung 1 is NOT what answers these: `sse` has no `format_fixed` entry on any
    catalog, because SSE's fixedness is the envelope only. The graphql rows
    beside them, which DO have one, are re-pinned here as the contrast — the
    same `(json, resolved)` Task 2 froze, unmoved by this pass."""
    _, report = resolved_fixture

    assert {
        (e["path"], e["format"], e["format_resolution"])
        for e in report.endpoints
        if e["protocol"] == "sse"
    } == {
        ("/events/emitter", "json", "narrowed"),
        ("/events/stream", "json", "narrowed"),
    }
    assert {
        (e["format"], e["format_resolution"])
        for e in report.endpoints
        if e["protocol"] == "graphql"
    } == {("json", "resolved")}


def test_a_streams_per_event_payload_unwraps_through_the_sse_envelope(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """2H design §6's payload sentence, live: `Flux<ServerSentEvent<T>>`
    reaches `T` through the existing PTR/generic machinery.

    Two envelopes peel, not one. `rooting.py` unwraps RECURSIVELY, so a single
    `wrappers` entry for `ServerSentEvent` (added on every catalog carrying the
    Flux/Mono family, verbatim, per that block's own duplication convention) is
    the whole remedy: `Flux` peels as `streaming`, `ServerSentEvent` peels as
    `http_envelope`, and the walk stops at `OrderView` — an ordinary declared
    type with field facts of its own. Before the entry existed the walk stopped
    at the envelope and published the ENVELOPE TYPE as the contract.

    `/events/emitter` does NOT and cannot follow: `SseEmitter` is a callback
    handle, not a generic container — its `TypeRef` carries no type arguments
    at all, so nothing in the signature names the events it will push and no
    unwrapping rule could reach a payload. It stays the honestly-open envelope
    type, which is the right answer rather than a missing one, and the rendered
    document discloses it under "Not expanded" rather than publishing an empty
    contract as a complete one (pinned in `tests/e2e/test_vertical_slice.py`).

    `OrderView` is itself `open` — its `HttpHeaders` field is third-party and
    unexpanded, which the fixture's own source comment says outright — and that
    is unchanged by this task: the point here is that the SSE row reaches the
    SAME shape every other `OrderView`-carrying row reaches."""
    workspace, report = resolved_fixture
    emitter, stream = _route(report, "/events/emitter"), _route(report, "/events/stream")

    assert emitter["request_shape"] is None and stream["request_shape"] is None
    assert (
        json.loads(stream["response_shape"])["shape_id"] == "com/acme/orders/contracts/OrderView#"
    )
    assert (
        json.loads(emitter["response_shape"])["shape_id"]
        == "org/springframework/web/servlet/mvc/method/annotation/SseEmitter#"
    )
    # The envelope type is no longer a shape at all: nothing references it, so
    # nothing rooted it, so it was never expanded — which is the difference
    # between "unwrapped" and "unwrapped and left behind as an open type".
    shapes = {str(row["shape_id"]) for row in workspace.query("shapes")}
    assert "org/springframework/http/codec/ServerSentEvent#" not in shapes
    assert "org/springframework/web/servlet/mvc/method/annotation/SseEmitter#" in shapes
    assert "com/acme/orders/contracts/OrderView#" in shapes


# --- Task 10: the three listener catalogs, end to end, on real bytecode ---


def _messaging_rows(
    report: ResolveReport, protocol: str, path: str, direction: str | None = None
) -> list[dict]:
    """Rows on one messaging address, optionally on one side of it.

    The side became sayable with W27 (F5 §6.1): a topic a module publishes to AND
    consumes is two rows now, where the merge used to leave one `both` row. That is the
    self-publish/self-consume case, and it is real — which is why these rows stand and a
    `self_exchange` question asks about them rather than a pass deciding.
    """
    return [
        e
        for e in report.endpoints
        if e["protocol"] == protocol
        and e["path"] == path
        and (direction is None or e["direction"] == direction)
    ]


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
    [events] = _messaging_rows(report, "kafka", "order-events", "inbound")
    [audit] = _messaging_rows(report, "kafka", "order-audit", "inbound")

    assert events["handler"] == audit["handler"]
    assert events["handler"].endswith("OrderEventsListener#onEvent(sig_cf042f06).")
    for row in (events, audit):
        assert json.loads(row["request_shape"])["shape_id"] == (
            "com/acme/orders/contracts/OrderEvent#"
        )
        assert row["response_shape"] is None


def test_a_package_scope_makes_an_unannotated_field_not_null(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """D02 §2e's scope rule, exercised end to end at last (OI-48).

    A package-level `@NullMarked` or `@NonNullApi` inverts Java's permissive
    default: a field with NO annotation of its own is not-null, and only the
    exceptions are marked. That is the whole point of the mechanism — measured on
    spring-web 6.1.6, `HttpHeaders` declares 68 fields and ZERO carry an
    annotation, because the package declares the rule once.

    The resolver has always implemented it; nothing reached it. `ScopedRequest`
    was referenced by no endpoint, so no shape was ever rooted at it and the rule
    ran only in a hand-built unit test. It is a request body now.

    Both spellings, because a Spring codebase writes Spring's: JSpecify's
    `@NullMarked` was declared in `shape-models/json.yml` and Spring's
    `@NonNullFields` was not — so every Spring package declaring itself non-null
    read as fully nullable. `SpringScopedDetail` is reached through the payload
    graph rather than a second endpoint.

    The two negative cases travel the same way, and both were wrong. A package
    declaring `@NonNullApi` and nothing else says nothing about FIELDS — Spring
    scopes parameters and returns with it — and 197 of 1,672 cached jars'
    packages declare it alone. A SUBpackage of a scoped package inherits nothing
    (JLS 7.4.1), and matching the parent's prefix by bare `startswith` claimed
    462 unmarked subpackages.
    """
    workspace, _ = resolved_fixture
    nullable_by_field = {
        (str(row["shape_id"]).split("/")[-1], str(row["wire_name"])): row["nullable"]
        for row in workspace.query("shape_fields")
        if "Scoped" in str(row["shape_id"])
    }

    # JSpecify's spelling.
    assert nullable_by_field[("ScopedRequest#", "code")] is False
    # Spring's, which is what a Spring codebase actually declares.
    assert nullable_by_field[("SpringScopedDetail#", "label")] is False
    # `@NonNullApi` alone scopes no field.
    assert nullable_by_field[("ApiScopedDetail#", "note")] is True
    # A subpackage of a scoped package is not scoped by it.
    assert nullable_by_field[("NestedScopedDetail#", "tag")] is True


def test_a_batch_listeners_request_shape_is_an_array(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """`onBatch(List<OrderEvent> events)`: `wire_type: array` carrying its
    element, which is the checkpoint's own expectation in full.

    This test used to assert `"item" not in descriptor`. That was an honest gap,
    recorded rather than guessed past: the extractor read the `Signature`
    attribute for a *return* type but not for a *parameter*, so a parameter's
    type arguments were erased before anything downstream could see them —
    `OrderController#list`'s `List<OrderResult>` return kept its element and this
    parameter could not. **W5 closed it**, and the element is now here, so the
    row states the element type a consumer of `order-batches` has to expect
    instead of an array of nothing in particular."""
    _, report = resolved_fixture
    [batch] = _messaging_rows(report, "kafka", "order-batches")

    descriptor = json.loads(batch["request_shape"])
    assert descriptor["wire_type"] == "array"
    assert descriptor["item"]["shape_id"] == "com/acme/orders/contracts/OrderEvent#"


def test_a_dead_letter_listeners_consumer_record_envelope_yields_no_request_shape(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """`onDeadLetter(ConsumerRecord<String, OrderEvent> record)`: the declared
    `{type: ..., payload_arg: 1, semantics: envelope}` wrapper rule reaches the
    payload at argument 1 and the row describes `OrderEvent`, not the envelope.

    This test used to assert `request_shape is None`, for the same cause as the
    batch row above: a parameter's type arguments were erased, so the envelope
    held nothing at its payload position, and D02 §2a says an envelope holding
    nothing is no payload — the row was therefore empty. **W5 closed it**, and
    the checkpoint's own expectation (`ConsumerRecord payload -> OrderEvent via
    payload_arg 1`) now holds against the scanner's real output, which it could
    not before."""
    _, report = resolved_fixture
    [dlq] = _messaging_rows(report, "kafka", "order-.*-dlq")

    assert dlq["path"] == "order-.*-dlq"  # the pattern lands on `path` verbatim
    assert json.loads(dlq["request_shape"])["shape_id"] == ("com/acme/orders/contracts/OrderEvent#")


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
    parameter resolves as the payload. 2F Task 3: the destination literal
    is now the placeholder `${orders.audit.topic}` — a `JmsListener`
    destination is always read as a string literal regardless of its
    placeholder content, so the row still resolves and its own identity is
    the expression verbatim (M04's rule: nothing here interprets it)."""
    _, report = resolved_fixture
    [audit] = _messaging_rows(report, "jms", "${orders.audit.topic}")

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


def test_two_producers_of_one_topic_stay_two_rows_beside_its_consumer(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """`EventProducers#send` and `#sendKeyed` both publish to `order-events`, and
    `OrderEventsListener#onEvent` consumes it: **three rows, two outbound and one
    inbound**, and getting to three took correcting two separate merges.

    This test used to be called `..._two_send_arities_dedup_into_one_outbound_row` and its
    docstring called that dedup "the collapse only within one caller half of F5 §6.1,
    which was already true". Both halves of that were wrong. `send` and `sendKeyed` are
    two DIFFERENT methods — two callers — so the collapse was ACROSS callers, which rule 1
    forbids outright, and W27's review measured it deleting a real producer here and in
    three other places. Within one caller the dedup is real and still runs
    (`test_call_engines.py::test_two_identical_calls_in_one_method_dedup_to_one_row`).

    The inbound row stays separate for W27's own reason: a module publishing to a topic it
    also consumes is self-publish/self-consume, which is REAL — and so is a client calling
    another service's copy of a shared address, which is why a pass cannot decide between
    them. `self_exchange` asks the question instead of a merge answering it.
    """
    _, report = resolved_fixture
    [inbound] = _messaging_rows(report, "kafka", "order-events", "inbound")
    outbounds = _messaging_rows(report, "kafka", "order-events", "outbound")
    assert sorted(row["caller"].split("#")[-1].split("(")[0] for row in outbounds) == [
        "send",
        "sendKeyed",
    ]
    outbound = next(row for row in outbounds if "#send(" in row["caller"])

    assert inbound["handler"].endswith("OrderEventsListener#onEvent(sig_cf042f06).")
    assert inbound["caller"] is None
    assert outbound["caller"].endswith("EventProducers#send(sig_b2a754d9).")
    assert outbound["handler"] is None
    # The handler's own request shape, off `onEvent`'s signature — no longer "the shape
    # the merge kept", just the shape its own row always had.
    assert json.loads(inbound["request_shape"])["shape_id"] == (
        "com/acme/orders/contracts/OrderEvent#"
    )


def test_the_producer_records_channel_and_payload_come_from_its_own_constructor(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """`kafkaTemplate.send(new ProducerRecord<>("order-audit", event))`: the
    `record_wrappers` one-hop reads the topic and payload off the
    `ProducerRecord`'s own constructor call, not off `send`'s single
    argument (the record itself). `order-audit` is also consumed here — it is `onEvent`'s
    second `@KafkaListener` topic, the SAME handler — so the module publishes to a topic
    it reads back. That is two rows since W27 (F5 §6.1), not one `both` row, with a
    `self_exchange` question naming both sides."""
    _, report = resolved_fixture
    [inbound] = _messaging_rows(report, "kafka", "order-audit", "inbound")
    [outbound] = _messaging_rows(report, "kafka", "order-audit", "outbound")

    assert inbound["handler"].endswith("OrderEventsListener#onEvent(sig_cf042f06).")
    assert outbound["caller"].endswith("EventProducers#sendAudit(sig_b2a754d9).")


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
    # `resolved` since `OI-77` and W43's review: BOTH captures this row declares were
    # read — the destination from its own string literal, and the payload's TYPE from
    # the caller's signature. It answered `unresolved` while the payload column was
    # NULL, which was the only place that fact could be said; the column says it now.
    assert row["resolution"] == "resolved"
    # `OI-77`: the payload is handed through from this method's own parameter, and its
    # TYPE is stated in that signature.
    assert "com/acme/orders/contracts/OrderEvent#" in str(row["request_shape"])


def test_the_replying_kafka_templates_send_and_receive_merges_with_its_listener(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """`replyingTemplate.sendAndReceive(new ProducerRecord<>("order-returns",
    event))` — `ReplyingKafkaTemplate` gets its own catalog file
    (`spring-kafka-replying.yml`), `matches.owner` being single-valued and
    `ReplyingKafkaTemplate` a different owner type from `KafkaTemplate`. No
    overload exposes the reply type at the call site, so this catalog
    declares no `response_arg` at all. `order-returns` is also consumed here (Task 10's
    `onReturn`), so the module sends to a topic it reads back — two rows since W27 (F5
    §6.1), each keeping its own contract, with a `self_exchange` question naming both.
    The handler's row carries `OrderEvent` request and `ReceiptView` response —
    `onReturn`'s RETURN type, never the reply the `@SendTo` row already covers."""
    _, report = resolved_fixture
    [inbound] = _messaging_rows(report, "kafka", "order-returns", "inbound")
    [outbound] = _messaging_rows(report, "kafka", "order-returns", "outbound")

    assert inbound["handler"].endswith("OrderEventsListener#onReturn(sig_160f6bce).")
    assert outbound["caller"].endswith("EventProducers#sendReturn(sig_b2a754d9).")
    assert json.loads(inbound["request_shape"])["shape_id"] == (
        "com/acme/orders/contracts/OrderEvent#"
    )
    assert json.loads(inbound["response_shape"])["shape_id"] == (
        "com/acme/orders/contracts/ReceiptView#"
    )
    # The catalog declares no `response_arg`, so the CALLING side states no reply type —
    # which used to be invisible, the merge having kept the handler's answer for both.
    assert outbound["response_shape"] is None


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
    # `OI-77`: the payload is handed through from this method's own parameter, and its
    # TYPE is stated in that signature.
    assert "com/acme/orders/contracts/OrderEvent#" in str(row["request_shape"])


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


def test_a_jms_templates_destination_no_longer_merges_once_its_listener_moves_to_a_placeholder(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """`jmsTemplate.convertAndSend("audit.queue", event)` used to merge with
    Task 10's own `AuditJmsListener#onAudit` inbound row into `direction:
    both`. 2F Task 3 moves `onAudit`'s own destination to the placeholder
    `${orders.audit.topic}` (application.yml supplies the value) — a
    different literal string from this call's own `"audit.queue"`, so the
    wire-identity merge no longer fires: this row now stands on its own,
    unmerged, `direction: outbound`. Its own `event` argument is a bare,
    pass-through parameter of `sendAuditMessage(OrderEvent event)` — D00
    §5's `unresolved` kind, the same capture failure Task 11's `order-raw`
    row already pins — so `resolution` reads `unresolved` even though the
    destination literal itself resolves the `path` cleanly; this was always
    true, just invisible under the merge before this task."""
    _, report = resolved_fixture
    [row] = _messaging_rows(report, "jms", "audit.queue")

    assert row["direction"] == "outbound"
    assert row["handler"] is None
    assert row["caller"].endswith("EventProducers#sendAuditMessage(sig_b2a754d9).")
    # `resolved` since `OI-77` and W43's review: BOTH captures this row declares were
    # read — the destination from its own string literal, and the payload's TYPE from
    # the caller's signature. It answered `unresolved` while the payload column was
    # NULL, which was the only place that fact could be said; the column says it now.
    assert row["resolution"] == "resolved"
    # `OI-77`: the payload is handed through from this method's own parameter, and its
    # TYPE is stated in that signature.
    assert "com/acme/orders/contracts/OrderEvent#" in str(row["request_shape"])


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
    # `resolved` since `OI-77` and W43's review: BOTH captures this row declares were
    # read — the destination from its own string literal, and the payload's TYPE from
    # the caller's signature. It answered `unresolved` while the payload column was
    # NULL, which was the only place that fact could be said; the column says it now.
    assert row["resolution"] == "resolved"
    # `OI-77`: the payload is handed through from this method's own parameter, and its
    # TYPE is stated in that signature.
    assert "com/acme/orders/contracts/OrderEvent#" in str(row["request_shape"])


def test_the_sqs_builder_lambda_derives_the_queue_inside_it(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """`OI-74`, closed in W57. `sqsTemplate.send(to -> to.queue("shipments-lambda")
    .payload(event))` derived an outbound SQS row with NO destination for four
    phases — `path` NULL, `resolution: unresolved` — while the queue name sat as
    a string literal in the lambda's own synthetic method the whole time.

    **The old behaviour was written down as a virtue**, and this docstring said
    so: the row was "an honest unresolved row, not a fabricated
    `shipments-lambda` path", and the catalog declared no position for arity 1
    because the two overloads were "indistinguishable by name+arity alone". Both
    halves stopped being true. Descriptors arrived and separate the two — the
    destination-less `send(T)` is `(Ljava/lang/Object;)` and this is
    `(Ljava/util/function/Consumer;)`, and `_matching_method` claims an arity
    once any candidate declares a descriptor — and reading a literal the fact
    stream records under the symbol this call's own argument names is reading,
    not guessing. It is `OI-73` one engine over, where the same framing cost a
    WebClient call its whole URL.

    The address IS the row's identity: DR-5 matches on the wire contract, so a
    destination-less outbound row links to nothing and tells a reader only that
    this method sends to SQS.

    Measured on the fixture, before and after: `path` NULL → `shipments-lambda`,
    `resolution` unresolved → resolved. `peer` stays NULL because a channel is
    peerless by construction, and the PAYLOAD comes back too — `lambda_steps`
    names `payload(arg0)` beside `queue(arg0)`, so the row gains its request
    shape rather than only its address."""
    _, report = resolved_fixture
    [row] = [
        e
        for e in report.endpoints
        if e["protocol"] == "sqs"
        and e["direction"] == "outbound"
        and "sendShipmentViaBuilder" in str(e["caller"])
    ]

    assert row["caller"].endswith("EventProducers#sendShipmentViaBuilder(sig_b2a754d9).")
    assert (row["path"], row["resolution"], row["peer"]) == ("shipments-lambda", "resolved", None)
    assert "OrderEvent" in str(row["request_shape"])
    # And no destination-less SQS row survives anywhere in the fixture: this
    # was the only one, so its disappearance is the defect's own measure.
    assert [e for e in report.endpoints if e["protocol"] == "sqs" and e["path"] is None] == []


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
    the same topic. They used to fold into ONE `both` row; since W27 (F5 §6.1) they are
    two, because a module publishing to a subscription it also consumes is real and so is
    a client calling somebody else's copy of one address — and the evidence does not
    separate them, so `self_exchange` asks. The typed subscribe's
    own payload capture is its trailing `OrderEvent.class` literal, read at
    `body_arg` (review round 1, finding 1: an earlier draft read it into
    `response_arg` instead, which put the SUBSCRIBER'S received payload in
    `response_shape` — backwards, since a subscriber RECEIVES a request, the
    same D01 §3 column every other inbound messaging row's own payload
    lands in) — so it lands in `request_shape`, matching
    `spring-kafka.yml`/`spring-jms.yml`/`spring-sqs.yml`'s own inbound rows,
    never `response_shape`, on the surviving inbound-owned row."""
    _, report = resolved_fixture
    [inbound] = _messaging_rows(report, "pubsub", "order-notifications", "inbound")
    [outbound] = _messaging_rows(report, "pubsub", "order-notifications", "outbound")

    assert inbound["handler"].endswith("NotificationsSubscriber#subscribe(sig_da8c82d5).")
    assert outbound["caller"].endswith("EventProducers#publishNotification(sig_b2a754d9).")
    assert inbound["resolution"] == "resolved"
    assert inbound["response_shape"] is None
    assert json.loads(inbound["request_shape"])["shape_id"] == (
        "com/acme/orders/contracts/OrderEvent#"
    )


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
    `_owned_directions` deleted): with only `spring-pubsub.yml` loaded, the row is this
    same catalog's, so ownership stays trivially true and `OrderEvent` keeps a real
    `shapes` row behind it — proving the collapse didn't quietly reintroduce the
    masked-by-luck gap.

    *The row read `direction: both` until W27 (F5 §6.1). The INBOUND row is the one this
    test is about — the per-row `direction: inbound` override inside an otherwise-outbound
    catalog is the whole subject — and it is now that row directly rather than a merged
    one carrying the override's side.*"""
    catalog = next(c for c in YamlCatalogSource(CATALOGS).load() if c.id == "spring-pubsub")
    workspace, report = _resolved_fixture(tmp_path, catalogs=_Catalogs([catalog]))
    [row] = [
        e
        for e in report.endpoints
        if e["path"] == "order-notifications" and e["direction"] == "inbound"
    ]
    shape_id = json.loads(row["request_shape"])["shape_id"]
    shapes = {s["shape_id"] for s in workspace.query("shapes")}
    workspace.close()

    assert row["direction"] == "inbound"
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
    # `resolved` since `OI-77` and W43's review: BOTH captures this row declares were
    # read — the destination from its own string literal, and the payload's TYPE from
    # the caller's signature. It answered `unresolved` while the payload column was
    # NULL, which was the only place that fact could be said; the column says it now.
    assert row["resolution"] == "resolved"
    # `OI-77`. A bare `String` body is a real contract and NULL keeps exactly one
    # meaning, so this reads `string` rather than nothing.
    assert '"wire_type":"string"' in str(row["request_shape"])


# --- 2E-prep Task 12: driver catalogs B — the pubsub trio +
# spring-kafka-message, end to end on real bytecode ---


def test_the_co_located_pubsub_publisher_chain_resolves_via_the_channel_ladder(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """`RawPubSubPublishers#publishToNewTopic`'s `Publisher.newBuilder(
    TopicName.of(project, "raw-events")).build().publish(message)`:
    `newBuilder`'s own arg0 is the compiler's `unresolved` kind (a linked
    call, not a literal), so `google-pubsub-publisher.yml`'s `channel`
    ladder (this task's own fluent precondition commit) falls back to its
    declared `channel_via` form, following `source` to `TopicName.of`'s own
    call site and reading its `arg: 1`.

    CHECKPOINT CORRECTION (live `javap`, this task's own checkpoint): the
    plan's own shorthand named `terminal_via_argument` for `build` →
    `publish`, modelled on `aws-sqs-sdk.yml`'s erased-builder join — but
    `Publisher.Builder#build()` returns the CONCRETE `Publisher` type, no
    `CHECKCAST`, and `publish` is called directly on that SAME stack value
    (`build().publish(message)`, one straight chain) — a plain
    receiver-linked terminal, the WebClient shape, not OkHttp's. The
    catalog ships with a bare `terminal: [publish]` instead, verified live.

    No `body` capture is declared at all (`publish`'s own argument is a
    bare method parameter, and `PubsubMessage` is a declared no-shape
    envelope), so — unlike `spring-kafka-message.yml`'s own row below — an
    undeclared capture never narrows this row's own resolution (I1): the
    channel alone decides it."""
    _, report = resolved_fixture
    [row] = _messaging_rows(report, "pubsub", "raw-events")

    assert row["direction"] == "outbound"
    assert row["method"] is None
    assert row["handler"] is None
    assert row["caller"].endswith("RawPubSubPublishers#publishToNewTopic(sig_4e598209).")
    assert row["peer"] is None
    assert row["resolution"] == "resolved"
    assert row["request_shape"] is None


def test_the_field_held_publisher_derives_two_honest_unresolved_duplicate_rows(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """`google-pubsub-client.yml` declares NO channel at all for `publish` —
    spec §4's ruling: without this row, a config-built `Publisher` field
    (`publishToFieldPublisher`) would be silent, since a fluent chain that
    never reaches its own terminal derives nothing. Two rows derive here,
    BOTH `path` NULL and `resolution: unresolved`, never merged (an
    unresolved wire identity never dedups, D02 §2/§5):

    - `publishToFieldPublisher` — the genuinely field-held case this row
      exists for.
    - `publishToNewTopic` — the SAME co-located call
      `google-pubsub-publisher.yml` already resolves as `raw-events`
      (asserted above). EXPECTED DUPLICATE (spec §4, asserted deliberately,
      not a bug): a `single_call` catalog matches by name+arity alone and
      cannot know which specific fluent chain produced its own receiver, so
      it matches this call too, degrading honestly rather than silently
      skipping it. One resolved fluent row plus one unresolved single_call
      row stand side by side for that one call."""
    _, report = resolved_fixture
    rows = [
        e
        for e in report.endpoints
        if e["catalog_id"] == "google-pubsub-client" and e["protocol"] == "pubsub"
    ]
    callers = {row["caller"].rpartition(" ")[2] for row in rows}

    assert len(rows) == 2
    assert callers == {
        "com/acme/orders/messaging/raw/RawPubSubPublishers#publishToFieldPublisher(sig_4e598209).",
        "com/acme/orders/messaging/raw/RawPubSubPublishers#publishToNewTopic(sig_4e598209).",
    }
    for row in rows:
        assert row["direction"] == "outbound"
        assert row["path"] is None
        assert row["peer"] is None
        assert row["resolution"] == "unresolved"
        # `OI-77`. The ENVELOPE, because that is what this overload takes: the
        # catalog captures `publish(PubsubMessage)`'s own argument, and a
        # `PubsubMessage` is what the caller declared. The same answer an
        # `instance` argument of that type already gave — what changed is that a
        # parameter now reads like one.
        assert "com/google/pubsub/v1/PubsubMessage#" in str(row["request_shape"])


def test_a_named_messagereceiver_and_a_lambda_receiver_each_derive_their_own_handler(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """`google-pubsub-subscriber.yml`, D02 §2's `interface_implementation`
    style's own worked example against the real fixture:
    `RawPubSubSubscribers#startNamedReceiver`'s
    `Subscriber.newBuilder(ProjectSubscriptionName.of(project,
    "raw-notify"), new RawPubSubReceiver())` resolves the `instance`
    receiver to `RawPubSubReceiver#receiveMessage` (its class's own
    declared `interfaces` includes `MessageReceiver`, D00 §5a's
    `implemented_interfaces` capability — direct implementers only);
    `startLambdaReceiver`'s own `Subscriber.newBuilder(...,
    (MessageReceiver) (m, c) -> c.ack())` resolves the `lambda` receiver to
    its own synthetic method symbol. Both channels read through
    the SAME `channel_via` form (`ProjectSubscriptionName.of`'s own
    `arg: 1`) that reaches every registration in this one caller class.

    Both handlers are the FULL method symbols the facts carry, joined out of
    `symbols` (final review, FIX 1): a receiver argument's own `symbol` is
    the bare descriptor, so a handler assembled from it named no symbol any
    document declared and joined to nothing at all."""
    _, report = resolved_fixture
    [named] = _messaging_rows(report, "pubsub", "raw-notify")
    [lambda_row] = _messaging_rows(report, "pubsub", "raw-notify-lambda")

    assert named["direction"] == "inbound"
    assert named["caller"] is None
    assert named["handler"] == (
        "sextant-jvm maven com.acme/orders-service 1.0.0 "
        "com/acme/orders/messaging/raw/RawPubSubReceiver#receiveMessage(sig_bb1c3cf6)."
    )
    assert named["resolution"] == "resolved"
    assert named["request_shape"] is None

    assert lambda_row["direction"] == "inbound"
    assert lambda_row["caller"] is None
    assert "lambda$startLambdaReceiver$" in lambda_row["handler"]
    assert lambda_row["resolution"] == "resolved"
    assert lambda_row["request_shape"] is None


def test_the_messagebuilder_kafka_chain_resolves_its_topic_but_not_its_bare_payload(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """`spring-kafka-message.yml`: `RawKafkaMessageSender#send`'s
    `kafkaTemplate.send(MessageBuilder.withPayload(event).setHeader(
    KafkaHeaders.TOPIC, "raw-messages").build())`. The `when`-guarded
    `setHeader` step resolves the topic cleanly (`path: raw-messages`), and
    `build`'s own result reaches `KafkaTemplate#send`'s own argument
    `source` through `terminal_via_argument` exactly as the checkpoint
    described (real `javap`-verified: `build()` returns the `Message`
    INTERFACE type here, consumed as `send`'s own ARGUMENT, unlike the
    co-located Pub/Sub chain above, which chains `build()`'s result
    straight into `publish` as a RECEIVER — two different real shapes, each
    catalog matching its own).

    DIVERGENCE FROM THE PLAN'S OWN CHECKPOINT SHORTHAND (live `javap`,
    investigated before freezing): `event` — `send(OrderEvent event)`'s own
    bare method parameter — is `aload`ed straight into `withPayload`, never
    `NEW`-constructed, so the scanner reads it as D00 §5's `unresolved`
    kind, not `instance` (the exact same parameter-passthrough shape
    `aws-sqs-sdk.yml`'s own SQS row and `order-raw`/`shipments-outbound`
    already hit in Task 11). Ruling I1: a DECLARED capture that reached but
    could not be read drops the whole row's own `resolution`, even though
    the topic identity resolves perfectly — so this row reads `path:
    raw-messages`, `resolution: unresolved`, NOT the `resolved` row the
    checkpoint's shorthand assumed. It stands beside (never merges with,
    since it carries a real `path` while the sibling's is NULL)
    `spring-kafka-template.yml`'s own pre-existing `record_arg` row for
    this SAME call (spec §4's duplicate-row ruling, already frozen from
    Task 6 on) — asserted here as two separate real rows."""
    _, report = resolved_fixture
    [message_row] = _messaging_rows(report, "kafka", "raw-messages")
    template_siblings = [
        e
        for e in report.endpoints
        if e["catalog_id"] == "spring-kafka-template"
        and e["caller"]
        and e["caller"].endswith("RawKafkaMessageSender#send(sig_b2a754d9).")
    ]

    assert message_row["direction"] == "outbound"
    assert message_row["method"] is None
    assert message_row["caller"].endswith("RawKafkaMessageSender#send(sig_b2a754d9).")
    assert message_row["catalog_id"] == "spring-kafka-message"
    # `resolved` since `OI-77` and W43's review: BOTH captures this row declares were
    # read — the destination from its own string literal, and the payload's TYPE from
    # the caller's signature. It answered `unresolved` while the payload column was
    # NULL, which was the only place that fact could be said; the column says it now.
    assert message_row["resolution"] == "resolved"
    # `OI-77`: the payload is handed through from this method's own parameter, and its
    # TYPE is stated in that signature.
    assert "com/acme/orders/contracts/OrderEvent#" in str(message_row["request_shape"])

    assert len(template_siblings) == 1
    [template_row] = template_siblings
    assert template_row["path"] is None
    assert template_row["resolution"] == "unresolved"


# --- 2F Task 7: the `config_join` engine, live ---------------------------
#
# Every assertion below is pinned from a live run —
# `uv run sextant module analyze fixtures/orders-service` (today 117
# endpoints total, per `test_resolve_finds_every_fixture_endpoint_exactly_
# once_when_run_end_to_end`'s own count; 91 when this task froze the
# assertions below, before later tasks grew the fixture), extractor 9.8 —
# not computed from the plan.

BEANS = "com/acme/orders/streams/OrderStreamBindings#"
ORDER_EVENT_PAYLOAD = {
    "nullable": True,
    "shape_id": "com/acme/orders/contracts/OrderEvent#",
    "wire_format": "",
    "wire_type": "object",
}


def _binding_rows(report: ResolveReport) -> list[dict]:
    return [e for e in report.endpoints if e["catalog_id"] == "spring-cloud-stream"]


def test_a_consumer_bean_binds_inbound_to_the_destination_its_key_names(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """`@Bean Consumer<OrderEvent> handleOrder()` — the style's whole point in
    one row: nothing in the bytecode names a destination at all. The bean's
    own RETURN type picks the `-in-0` suffix and `inbound` direction from the
    catalog's suffix rules, its own method name is the binding name, and
    `spring.cloud.stream.bindings.handleOrder-in-0.destination` (both
    environments agreeing on `stream-orders`) supplies the address.

    `handler`, not `caller`: D01 §3's direction rule, so an inbound binding
    reads like every other inbound row in this table. The payload roots from
    the functional interface's own type ARGUMENT (checkpoint item (1)) — the
    `Consumer` itself is machinery and never reaches a shape column."""
    _, report = resolved_fixture
    [row] = _messaging_rows(report, "kafka", "stream-orders")

    assert row["direction"] == "inbound"
    assert row["method"] is None
    assert row["handler"].endswith(BEANS + "handleOrder(sig_b4c25d22).")
    assert row["caller"] is None
    assert row["peer"] is None
    assert row["resolution"] == "resolved"
    assert row["evidence"] == "compiler"
    assert row["catalog_id"] == "spring-cloud-stream"
    assert json.loads(row["request_shape"]) == ORDER_EVENT_PAYLOAD
    assert row["response_shape"] is None
    # `handler_signature` stays NULL, exactly as every other pass-computed
    # row's does (`single_call`, `fluent`, `reply`): the row's payload is
    # already decided here, and `derive_endpoint_contracts.sql`'s owner-keyed
    # update is guarded on this column precisely so a row that answered for
    # itself is not answered again from its declared signature — which here
    # would root at `Consumer` and report the machinery as the wire payload.
    assert row["handler_signature"] is None


def test_a_supplier_bean_binds_outbound_with_its_bean_method_as_the_caller(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """`@Bean Supplier<OrderEvent> auditTap()` — the same mechanism through
    the other suffix rule: `-out-0`, `outbound`, and therefore `caller` set
    with `handler` NULL (D01 §3's direction rule again, which spec §3's own
    "handler is the bean's method symbol" wording predates). `audit-tap` has
    no inbound twin in this fixture, so the row stays outbound rather than
    merging."""
    _, report = resolved_fixture
    [row] = _messaging_rows(report, "kafka", "audit-tap")

    assert row["direction"] == "outbound"
    assert row["handler"] is None
    assert row["caller"].endswith(BEANS + "auditTap(sig_6898d13c).")
    assert row["resolution"] == "resolved"
    assert json.loads(row["request_shape"]) == ORDER_EVENT_PAYLOAD


def test_a_selected_bean_whose_binding_key_is_never_declared_still_derives_a_row(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """`orphanConsumer` is selected and its facts are identical to
    `handleOrder`'s, but `application.yml` declares no
    `…bindings.orphanConsumer-in-0.destination` — and none of the 20
    `resolved_config` rows carries that key in either environment.

    D02 §2d: "an unresolved address is not an absent endpoint". The bean
    exists and the binding was declared, so the row is recorded with its
    path NULL and `resolution: unresolved`; the handler is still named,
    because the bean method is a fact regardless of what configuration
    forgot."""
    _, report = resolved_fixture
    [row] = [
        e
        for e in _binding_rows(report)
        if e["handler"] and e["handler"].endswith("orphanConsumer(sig_b4c25d22).")
    ]

    assert row["direction"] == "inbound"
    assert row["path"] is None
    assert row["resolution"] == "unresolved"
    assert row["caller"] is None
    # The payload is read from the bean's own type argument regardless: the
    # destination is what configuration failed to name, not the contract.
    assert json.loads(row["request_shape"]) == ORDER_EVENT_PAYLOAD


def test_a_composed_definition_entry_derives_one_row_naming_nobody(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """`pipeA|pipeB` — the composition degrade (D02 §2d: the vocabulary
    "records the whole expression rather than guessing which function
    contributed which half"). ONE row, `path` NULL, `handler` AND `caller`
    NULL: there is no single bean to name, and no shape either, since no
    functional type was read. It is the first endpoint row in this repo that
    names no symbol at all — pinned here so a renderer or export that cannot
    tolerate that fails loudly rather than silently dropping it.

    It shares `(kafka, inbound, NULL, NULL)` with the orphan row above and
    stays a SECOND row: `derive_call_endpoints.sql` never dedups a NULL path
    (SQL's `NULL = NULL` is unknown), and this pass's own dedup follows the
    same rule."""
    _, report = resolved_fixture
    [row] = [e for e in _binding_rows(report) if e["handler"] is None and e["caller"] is None]

    assert row["protocol"] == "kafka"
    assert row["direction"] == "inbound"
    assert row["path"] is None
    assert row["resolution"] == "unresolved"
    assert row["request_shape"] is None


def test_a_bean_the_definition_does_not_select_derives_no_row_at_all(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """`unselectedBean`'s facts are byte-identical in shape to
    `handleOrder`'s — same annotation, same `Consumer<OrderEvent>` return
    type, same enclosing class — so ONLY selection can exclude it. Asserted
    as an absence rather than merely omitted from the route set: a
    selection that quietly stopped filtering would add a row this fixture's
    totals would absorb without any set comparison noticing which one was
    extra.

    The four binding rows are pinned as a whole for the same reason."""
    _, report = resolved_fixture

    assert not [e for e in report.endpoints if e["handler"] and "unselectedBean" in e["handler"]]
    assert not [e for e in report.endpoints if e["caller"] and "unselectedBean" in e["caller"]]
    assert len(_binding_rows(report)) == 4


def test_the_configured_serializer_stamps_media_on_every_matching_kafka_row(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """`media_from_config`, live and whole. Both serializer keys resolve to
    one class in BOTH environments (the agreement the stamp requires); the
    PRODUCER's class is in the catalog's `values` map, so one MIME string is
    computed for that rule and applied to every row its `(protocol,
    direction)` pair names.

    The whole stamped picture is pinned, not a sample: this is a
    module-level default reaching rows six other catalogs derived, and the
    only way to see that it stopped where it should is to assert where it
    did not land. Three things it must NOT do: touch a non-kafka row, touch
    a row that already declared its own media (the two `spring-web` HTTP
    rows), or fill the opposite direction's column.

    The `both` rows carry `produces` — and that column is **the live proof of
    the merge's media carry** (checkpoint falsification F-4). `config_join`
    stamps before the merge and matches direction EXACTLY, so a `both` row is
    never stamped: its `produces` can only have arrived from the outbound
    twin the merge deleted. Nothing else in this fixture exercises that path
    end to end.

    **The CONSUMER rule stamps nothing, live, and that is the second pin**
    (2G Task 6). Its configured class is a schema-registry deserializer with
    no MIME string anyone registered, so it is absent from `values` — and
    D02 §2d's "a class absent from `values` is a gap to grow the catalog
    from, not a guess" is now exercised against a real class in a real run,
    not only against `test_config_join.py`'s invented one. That class is in
    the catalog's `format_from` table instead, where it answers the format
    ladder's rung 3 (`test_the_format_ladder_answers_every_live_row` below):
    leaving `consumes` NULL on the inbound rows is exactly what makes rung 3
    reachable, since rung 2 reads the media this stamp writes and would
    otherwise have answered first, every time."""
    _, report = resolved_fixture
    kafka = [e for e in report.endpoints if e["protocol"] == "kafka"]
    json_media = '["application/json"]'

    # Every kafka row that produces carries the producer-side stamp — `both`
    # counted on that side, since a merged row is one the module both
    # exposes and calls, and its stamp survived only through the merge.
    assert {e["produces"] for e in kafka if e["direction"] in ("outbound", "both")} == {json_media}
    # And nothing bled across: an outbound-only row declares nothing it
    # consumes.
    assert {e["consumes"] for e in kafka if e["direction"] == "outbound"} == {None}
    # 10 rows produce (7 outbound + 3 both) — the checkpoint's own frozen
    # kafka metadata count. NOTHING consumes: the consumer rule resolved its
    # key, agreed across environments, and still stamped nothing, because
    # the class it named has no MIME to stamp.
    # 11 since W27's review: `EventProducers#sendKeyed`'s `order-events` row, a second
    # caller the outbound dedup had been deleting (F5 §6.1 rule 1).
    assert len([e for e in kafka if e["produces"] == json_media]) == 11
    assert {e["consumes"] for e in kafka} == {None}

    # Untouched: every non-kafka row, including the HTTP rows that declare
    # their own media through the annotations (first-writer discipline — a
    # stamp never overwrites). 2G Task 5 adds a third: `proto-orders`
    # declares `produces` only, `consumes` NULL (no `consumes` attribute on
    # its own `@PostMapping`) — these three are the only pre-existing
    # non-NULL media in the table.
    #
    # 2H Task 1 adds a fourth: `OrderEventsController#streamEvents`'s
    # `@GetMapping(produces = TEXT_EVENT_STREAM_VALUE)` declares its own
    # media, `consumes` NULL. `emitterEvents` declares neither (no
    # `produces` on its own `@GetMapping`), so it carries no row here at
    # all.
    #
    # That fourth row reads `sse` as of 2H Task 6, and the MEDIA is why: the
    # `protocol_hint` pass reclassified it off this very column. The MIME
    # string it kept is unchanged — a stamp that never fired here still never
    # fires — and it names a protocol, never a format (`spring-web.yml`'s
    # `media_formats` says at length why `text/event-stream` is absent from
    # that table).
    declared = {
        (e["protocol"], e["path"], e["consumes"], e["produces"])
        for e in report.endpoints
        if e["protocol"] != "kafka" and (e["consumes"] or e["produces"])
    }
    assert declared == {
        ("http", "/v1/orders/{id}", None, json_media),
        ("http", "/v1/orders/detailed", json_media, json_media),
        ("http", "/v1/orders/proto-orders", None, json_media),
        # W44's servlet functional routes: `accept` fills `produces` and `contentType`
        # fills `consumes`, read through the same `media_values` table the reactive twin
        # uses — one measured member, `APPLICATION_JSON`, and nothing guessed.
        ("http", "/mvcfn/invoices", None, json_media),
        ("http", "/mvcfn/invoices", json_media, None),
        ("sse", "/events/stream", None, '["text/event-stream"]'),
        # 2O Task 13, and NOT a stamp: these three are the functional-routing
        # rows' own `accept`/`contentType` predicates, read off the vararg
        # array's `elements` by the combinator engine. They belong in this set
        # for the same reason the mapping-annotation rows do — the media is
        # DECLARED at the route — and their presence here is what keeps the
        # kafka stamp's own claim below honest: the stamp fires on kafka rows
        # and nowhere else, which is only checkable if every non-kafka
        # declaration is enumerated.
        ("http", "/fn/orders", None, json_media),
        ("http", "/fn/orders", json_media, None),
        ("http", "/kt/rich", None, json_media),
    }


def test_an_outbound_payload_handed_through_from_a_parameter_carries_its_contract(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """`OI-77`, found while checking W43's new STOMP rows against their siblings.

    A payload passed straight through — `send(OrderEvent event)` calling
    `kafkaTemplate.send("order-events", event)` — arrives as `{"kind": "parameter"}`, which
    names no type of its own. `_reference_of` answered for a class literal, a scalar and an
    `instance` and returned None for everything else, so the row shipped without a
    contract; the type is stated in the CALLER's own signature and was simply not read.

    **Measured before and after**, on a full `module analyze` of this fixture: 3 of its 25
    outbound `single_call` rows carried a payload, and 19 do. The six that still do not are
    rows with no body capture at all — a `send(Message)` whose payload is inside the
    message.

    **Re-measured in W57**: 20 → 21. `OI-74` taught `single_call` to read a destination and
    a payload from inside a builder lambda, and the fixture's
    `sqsTemplate.send(to -> to.queue(…).payload(event))` is a `single_call` row in this very
    set — so it gains a carried contract, not just an address. The guard's own message says
    to re-measure rather than re-pin when this moves, and this is that.

    The guard below counts (21, 26) rather than those figures, and the difference is the
    SET, not the run: it omits `aws-sqs-sdk`, and `spring-kafka-message` and `aws-sqs-sdk`
    are `fluent` catalogs rather than `single_call` ones. *An earlier version of this
    docstring explained the gap as "this test's resolve writes one row fewer than the
    CLI's". That is true and is not the reason — the row it writes fewer is a SOAP call
    from a second fixture module, which is in neither set.*

    The value of a parameter really does live in whatever called the method, which is why
    `parameter` belongs in `_UNREAD_KINDS` and why a DESTINATION read from one stays
    `unresolved`. A payload is the other question: what a contract needs is the type.
    """
    workspace, _report = resolved_fixture
    # Read off the WORKSPACE rather than the report: the two differ by one outbound row on
    # this fixture, and the table is what the bundle and the document are built from.
    written = [row for row in workspace.query("endpoints") if row["direction"] == "outbound"]
    outbound = {(row["catalog_id"], row["path"]): row for row in written}

    # The plainest instance: one field, one call, the payload straight off the parameter.
    kafka = outbound[("spring-kafka-template", "order-events")]
    assert "com/acme/orders/contracts/OrderEvent#" in str(kafka["request_shape"])
    # A second catalog, a second protocol, the same shape of call — this is a class of
    # defect and not one catalog's.
    jms = outbound[("spring-jms-template", "audit.queue")]
    assert "com/acme/orders/contracts/OrderEvent#" in str(jms["request_shape"])
    # And W43's own rows, which is where it was found.
    stomp = outbound[("spring-stomp-template", "/topic/order-announced")]
    assert "com/acme/orders/contracts/OrderView#" in str(stomp["request_shape"])

    single_call = {
        "spring-resttemplate",
        "spring-kafka-template",
        "kafka-clients",
        "spring-jms-template",
        "spring-sqs-template",
        "google-pubsub-client",
        "spring-pubsub",
        "spring-ws-template",
        "spring-kafka-replying",
        "spring-stomp-template",
        "jakarta-jms",
        "javax-jms",
        "spring-kafka-message",
    }
    # Counted off the full list, not off the lookup above: two `order-events` rows share a
    # key there and so do the path-NULL default-destination rows, and collapsing them
    # would under-count exactly the rows this measures.
    rows = [row for row in written if row["catalog_id"] in single_call]
    carried = sum(1 for row in rows if row["request_shape"])
    assert (carried, len(rows)) == (21, 26), (
        "the outbound payload count moved — re-measure rather than re-pinning, because a "
        "handful of rows carrying a contract was the defect and this number is what closed it"
    )


def test_the_format_ladder_answers_every_live_row(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """The six-rung ladder (2G design §5), live and whole, against the
    shipped catalogs' own vocabulary and real bytecode.

    The invariant first: EVERY row leaves the pass with a resolution, and
    `format` is NULL exactly when that resolution is `unresolved`. A row the
    pass never reached would carry a NULL resolution, which is a different
    claim from "nothing described this channel" — and the whole design turns
    on those two staying distinguishable.

    Then the rungs that are reachable in this fixture, pinned by the rows
    they actually answered rather than by counts alone:

    * **rung 2** (declared media) on the three HTTP routes whose own mapping
      annotations declare a MIME type, and on every kafka row the producer
      stamp reached — the outbound rows directly, the merged `both` rows
      through the merge's media carry;
    * **rung 3** (serializer config) on exactly the inbound kafka rows —
      reachable only because the configured consumer class has no MIME to
      stamp, so rung 2 had nothing to say about them;
    * **rung 5** (framework default) on every remaining row carrying a
      declared payload type, at `narrowed`, because Jackson's package family
      is present in this module and nothing declared these channels;
    * **rung 6** on the rest.

    Rung 1 has no live surface (no shipped catalog declares a fixed-format
    protocol) and rung 4 has none *here*: this fixture resolves WITHOUT the
    descriptor interpreter (see `conftest.py` — no reader or interpret step),
    so no `declared_shape` fact exists for rung 4 to read, and the payload
    types 2G Task 7's parse binding lands on these rows are ordinary declared
    objects as far as this run can tell — which is what makes them rung 5's.
    The rung-4 answer those same rows carry in a FULL analyze is pinned in
    `tests/e2e/test_vertical_slice.py`, where the interpreter runs; the rung
    itself is unit-covered in `test_format_ladder.py`.
    """
    workspace, report = resolved_fixture
    answers = {
        (e["protocol"], e["direction"], e["method"], e["path"]): (
            e["format"],
            e["format_resolution"],
        )
        for e in report.endpoints
    }

    assert all(e["format_resolution"] is not None for e in report.endpoints)
    assert all(
        (e["format"] is None) == (e["format_resolution"] == "unresolved") for e in report.endpoints
    )

    # Rung 1 — FIRST LIVE SURFACE (2H Task 2). The mechanism shipped in 2G
    # with no catalog owning a fixed-format protocol, so it had never fired
    # outside a unit test; the three GraphQL catalogs each declare
    # `format_fixed: {graphql: json}` and every graphql row is answered by it.
    # `resolved`, not `narrowed`: GraphQL's payload envelope is JSON by
    # definition, so this is the protocol stating its own wire, not a
    # framework default being assumed.
    #
    # Three catalogs declare the identical entry and the ladder unions them —
    # a contradiction between two would be refused rather than resolved, which
    # is what keeps the three copies from drifting silently.
    assert {answer for key, answer in answers.items() if key[0] == "graphql"} == {
        ("json", "resolved")
    }
    # 14 since `G-39`/`G-40`: two fields from one repeatable `@DgsData` resolver, and the
    # `Order` entity fetcher — Federation's `_entities` path, keyed by type not field.
    assert len([e for e in report.endpoints if e["protocol"] == "graphql"]) == 14

    # Rung 1 — SECOND LIVE SURFACE (2I Task 2), and the one that proves the
    # rung is protocol-generic rather than a GraphQL special case: a different
    # protocol, a different format, one catalog instead of three, and no
    # engine change between them. `spring-ws.yml`'s `format_fixed: {soap: xml}`
    # answers BOTH identity forms alike — the QName row and the SOAPAction
    # row — because the rung reads the row's PROTOCOL and nothing else.
    # `resolved`, not `narrowed`, for GraphQL's own reason: a SOAP envelope IS
    # an XML document, so this is the protocol stating its wire rather than a
    # framework default being assumed.
    assert {answer for key, answer in answers.items() if key[0] == "soap"} == {("xml", "resolved")}
    # `wsdl-schema.yml` (2I Task 4) carries the identical `format_fixed: {soap:
    # xml}` entry and would answer a third live surface alike — but this
    # fixture loads no `declared_shape` facts (comment above `len(report.
    # endpoints) == 122`), so its one row never reaches this table; pinned
    # instead in `tests/e2e/test_vertical_slice.py`.
    # 6 since W27 (F5 §6.1): `{...}placeOrderRequest` is two rows — the operation this
    # module serves, and `BillingSoapClient`'s call to `${soap.billing.uri}`, which the
    # merge published as one endpoint because they compose the same QName off the same
    # payload type.
    # 7 since W27's review: a SOAP call to a different billing address, a second caller
    # the outbound dedup had been deleting (F5 §6.1 rule 1).
    # 9 since `G-36` — see the `"soap": 9` bucket above for the derivation.
    assert len([e for e in report.endpoints if e["protocol"] == "soap"]) == 9

    # Rung 2 — every HTTP route that declares a media type at all, in either
    # of the two ways a route can. THREE declare it on a mapping ANNOTATION;
    # five more declare it on a functional-routing PREDICATE
    # (`accept(...)`/`contentType(...)`), and those three arrived here in 2O
    # Task 13, when the combinator engine learned to read a vararg array's own
    # `elements`. Nothing about the rung changed — the media column those rows
    # were always entitled to simply stopped being NULL, which is exactly what
    # a ladder rung reading that column is supposed to notice.
    assert {
        key for key, answer in answers.items() if key[0] == "http" and answer[1] == "resolved"
    } == {
        ("http", "inbound", "GET", "/v1/orders/{id}"),
        ("http", "inbound", "POST", "/v1/orders/detailed"),
        # W44's two media-carrying servlet routes. FIVE functional-routing rows declare a
        # media predicate now, not three — the servlet twin reads `accept`/`contentType`
        # through the same table, so the rung sees them for the same reason.
        ("http", "inbound", "GET", "/mvcfn/invoices"),
        ("http", "inbound", "POST", "/mvcfn/invoices"),
        ("http", "inbound", "POST", "/v1/orders/proto-orders"),
        ("http", "inbound", "GET", "/fn/orders"),
        ("http", "inbound", "POST", "/fn/orders"),
        ("http", "inbound", "GET", "/kt/rich"),
    }
    # The three predicate-derived rows answer `json`, off `application/json`
    # and nothing else — the same table, the same rung, a different place the
    # declaration was written.
    assert {
        answers[key]
        for key in (
            ("http", "inbound", "GET", "/fn/orders"),
            ("http", "inbound", "POST", "/fn/orders"),
            ("http", "inbound", "GET", "/kt/rich"),
        )
    } == {("json", "resolved")}
    # **Rung 2 beats rung 4**, live: `proto-orders` takes a generated
    # protobuf type in and returns one out — Task 5 pinned both shapes
    # expanding from their descriptors — and is still `json`, because its
    # own `@PostMapping` declares the media. Proto3 has a JSON encoding;
    # reading the wire off the payload's TYPE would be a confident wrong
    # answer, and this row is the one place the fixture can catch it.
    assert answers[("http", "inbound", "POST", "/v1/orders/proto-orders")] == ("json", "resolved")

    # Rung 3 — the inbound kafka rows, and only those: the consumer's
    # configured class names a wire format and no MIME type, so it is
    # invisible to rung 2 and answered here.
    protobuf = {key for key, answer in answers.items() if answer[0] == "protobuf"}
    assert protobuf == {
        ("kafka", "inbound", None, "composed-orders"),
        ("kafka", "inbound", None, "order-.*-dlq"),
        ("kafka", "inbound", None, "order-batches"),
        ("kafka", "inbound", None, "order-escalations"),
        ("kafka", "inbound", None, "order-polymorphic"),
        ("kafka", "inbound", None, "raw-.*"),
        # The three W27 added, and they are the item's own point made twice over. This
        # fixture configures a JSON producer and a PROTOBUF consumer deliberately, and
        # these three topics are the ones it both publishes to and consumes. As merged
        # `both` rows they answered `json` at rung 2, off a `produces` the merge had
        # carried across from the outbound twin it deleted — so the consumer's configured
        # protobuf deserializer, which is a direct statement about the INBOUND side, was
        # never consulted. Each row now answers off its own evidence: the producer
        # declares JSON, the consumer reads protobuf, and the disagreement is visible
        # instead of laundered into one confident wrong answer.
        ("kafka", "inbound", None, "order-audit"),
        ("kafka", "inbound", None, "order-events"),
        ("kafka", "inbound", None, "order-returns"),
        ("kafka", "inbound", None, "raw-t1"),
        ("kafka", "inbound", None, "raw-t2"),
        ("kafka", "inbound", None, "stream-orders"),
        # Rows whose destination could not be read at all: the format of a
        # channel is knowable even where its address is not.
        ("kafka", "inbound", None, None),
    }
    # 15 rows, not 12 keys: `order-polymorphic` and the NULL-path identity each carry two
    # rows that differ only in their handler and payload. 12 became 15 with W27 (F5 §6.1)
    # — the inbound halves of the three self-published topics, which used to be merged
    # rows answering `json` off the producer's stamp.
    assert len([e for e in report.endpoints if e["format"] == "protobuf"]) == 15
    # Every other kafka row is rung 2's, off the producer stamp.
    assert {
        answer for key, answer in answers.items() if key[0] == "kafka" and key not in protobuf
    } == {("json", "resolved")}
    # The OUTBOUND halves of the three self-published topics, which do carry the
    # producer's `application/json` because it was stamped on their own rows rather than
    # carried onto somebody else's.
    assert {
        answers[("kafka", "outbound", None, path)]
        for path in ("order-audit", "order-events", "order-returns")
    } == {("json", "resolved")}

    # Rung 5 — assumed, never observed. `narrowed` is what keeps a framework
    # default from reading like a declaration.
    assert {e["format"] for e in report.endpoints if e["format_resolution"] == "narrowed"} == {
        "json"
    }
    # 39 + 3 with 2G Task 7: the three bytes-only listeners whose payload the
    # parse binding replaced with a real declared type now qualify for rung 5,
    # which reads a declared payload TYPE and finds none behind a byte array.
    # That is the binding observable in this run — before it, all five of the
    # new rows fell to rung 6.
    # + 2 with 2H Task 1: `/events/emitter` (no declared media at all, an
    # `SseEmitter` return carrying no payload type the ladder can read
    # either — rung 5's assumed default) and `/events/stream` (its declared
    # `text/event-stream` media matches no rung-2 MIME the ladder knows, so
    # it falls through to the same assumed default). Neither is a new rung
    # 3/4 answer — rung 3 stays kafka-only, and rung 4 has no live surface
    # here, per this test's own docstring.
    # + 4 with 2H Task 5: `/orders/place` (request AND response both
    # `OrderView`, but ONE row), `/orders/board` (response only), `place`'s
    # own resolved `@SendTo` reply, and `board`'s own UNRESOLVED reply —
    # rung 5 answers off the row's declared payload TYPE alone, which
    # `board`'s reply still carries (`OrderView`) even though its own
    # `resolution` is `unresolved` for a completely different reason (no
    # destination named); `endpoints.resolution` and `format_resolution` are
    # two different columns answering two different questions, and this row
    # is the fixture's own live proof they can disagree.
    # + 2: the two prefix-seam routes, which reach the same rung 5 default
    # every other json-bodied http row here does.
    # + 1 (OI-47): `GET /api/orders/{id}`, the recovered covariant mapping,
    # which is a json-bodied http row like any other and reaches the same rung.
    # + 1 (OI-48): `POST /v1/orders/scoped`, likewise.
    # + 4 (W26): the four `/v1/paged/*` routes. All four are json-bodied http rows and
    # reach the same rung, whether or not their payload TYPE could be expanded — which
    # is the point: the format ladder answers off the declared type, and three of these
    # four have a type nothing here can open.
    # + 1 (W27): `POST /v1/orders` is two rows, and the outbound half is a json-bodied
    # http row reaching the same rung its inbound twin does.
    # + 3 (W28): the three `/v1/routing/orders` handlers, json-bodied http rows reaching
    # the same rung every other one does.
    # + 2 (W29): the two new WebClient chains, which reach the same rung whether or not
    # their address resolved — the ladder answers off the declared payload type.
    # + 4 (W27's review): the four http second callers the outbound dedup had been
    # deleting. Each reaches the rung its surviving twin already reached — the ladder
    # answers off the declared payload type, which a second caller of one address shares.
    # + 9 (`OI-77`, W43): the rung answers off the row's DECLARED PAYLOAD TYPE, and nine
    # outbound rows had no declared payload to answer off — their body was handed through
    # from the caller's own parameter and its type was not being read. Nothing about the
    # ladder changed; it was being asked about rows with a NULL contract. `resolution` on
    # those rows is untouched and still `unresolved`, which is the other column.
    # + 1 (`OI-74`, W57): the SQS builder-lambda row gained a declared payload — read from
    # `payload(arg0)` inside the lambda — so the ladder now has a type to answer off for a
    # row that carried none. Same mechanism as the nine above, one catalog over.
    assert len([e for e in report.endpoints if e["format_resolution"] == "narrowed"]) == 76
    # 28 + 2: the two rows the binding REFUSED keep their byte-array payload,
    # so nothing described them and rung 6 is still the honest answer.
    # + 1 with 2H Task 5: `/live` — a raw WebSocket frame is untyped by
    # definition (`jakarta-websocket.yml` declares no `request_body` block at
    # all, and `onFrame` returns `void`), so this row carries no payload
    # shape for rung 5 to read either, and falls all the way to rung 6.
    # - 3 with 2O Task 13: `GET`/`POST /fn/orders` and `GET /kt/rich` had no
    # media to read and no payload type behind a Kotlin-generated or
    # method-ref handler, so all three fell to rung 6 with nothing described.
    # Their `accept`/`contentType` predicates are readable now, so rung 2
    # answers them — a row leaving rung 6 for a DECLARATION is the ladder
    # working, and the only three rows in the fixture that could move.
    # + 1 (W27): the SOAP call to `${soap.billing.uri}` is its own row now. It was
    # merged into the served operation's, and the merge took the WEAKER of the two
    # format markers — so the served row read `unresolved` on the strength of its
    # caller's silence. Both rows are `unresolved` here for their own reasons, which is
    # one more row and one less laundering.
    # 22 since `OI-77` closed (W43). NINE of these rows left this bucket in the same
    # commit that added two to it, and both movements are the same fact: the ladder answers
    # off a row's DECLARED PAYLOAD TYPE, and an outbound body handed through from the
    # caller's own parameter had no declared type recorded — so NINE rows, the two new
    # STOMP ones included, were asking the ladder about a NULL contract. The ladder was
    # right to say `unresolved`; the missing rung was one earlier, and it is there now.
    # 23 since W44: `PUT /mvcfn/invoices/{id}` declares no media predicate and its
    # handler returns a bare `ServerResponse`, so there is no declared payload type
    # for the ladder to answer off — the honest answer, and the same one every other
    # verb-only functional route gets.
    # 26 since W45: the three STOMP connect URLs. A handshake path carries no payload
    # declaration of any kind — there is no body to type — so the ladder has nothing to
    # answer off and says so, which is the same honest answer `/live`'s raw frame gets.
    # 29 since W46: the three client connects. A handshake carries no payload declaration
    # — there is no body to type — so the ladder has nothing to answer off, the same
    # honest answer the server-side connect URLs and `/live`'s raw frame already get.
    # 28 since W57 (`OI-74`): the SQS builder-lambda row LEFT this bucket for the
    # `narrowed` one above — the same single row, counted once on each side, which is
    # what makes these two assertions a pair rather than two numbers.
    # 30 since 2026-09-11: `/ws/tickets` (`G-34`) is a registration with no payload
    # declaration, the same honest answer `/live`'s raw frame gets; and the async SQS send
    # (`G-43`) carries a `String` body exactly as the synchronous one beside it does, and
    # the two read identically — measured, so a divergence between the clients would show.
    assert len([e for e in report.endpoints if e["format_resolution"] == "unresolved"]) == 30

    # No rung saw two answers for ONE ROW anywhere in this fixture, so the ledger holds
    # no `format_conflict` at all.
    #
    # `self_exchange` joins it with W27 (F5 §6.1) — the six identities this module both
    # serves and calls, which used to be merged away. Three of them are the kafka topics
    # above, and they are worth reading together: the producer declares JSON and the
    # consumer is configured for protobuf, so the question a reader now gets ("are these
    # the same endpoint?") sits beside two rows that visibly disagree about the wire.
    # The merged row had one format and no question.
    assert {str(row["question"]) for row in workspace.query("open_questions")} == {
        "payload_binding",
        "self_exchange",
    }


# --- 2F Task 8: the field ladder and base composition, live --------------
#
# Pinned from a live run — `uv run sextant module analyze
# fixtures/orders-service` (today 117 endpoints total, same as Task 7 above;
# still 91 when THIS task froze the assertions below), extractor 9.8. The
# total is unmoved by this task either way: these four rows CHANGE, none is
# added or removed.

BILLING_CLIENTS = "com/acme/orders/config/BillingClients#"


def _billing_row(report: ResolveReport, method: str) -> dict:
    [row] = [
        e
        for e in report.endpoints
        if e["caller"] is not None and f"{BILLING_CLIENTS}{method}(" in str(e["caller"])
    ]
    return row


def test_each_ladder_rung_composes_the_same_base_expression_off_a_different_fact_path(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """The three real `BillingClients` chains, one per rung — every one of
    them feeding `WebClient.builder().baseUrl(...)` a value no literal at the
    call site names, and every one of them deriving the SAME expression from
    a different set of facts:

    - `fieldFedInvoice` — rung 1: the `field`-kind argument's own field
      carries the `@Value` expression, returned verbatim;
    - `constructorFedInvoice` — rung 2: the field carries no annotation at
      all, and a `field_write` fact traces it to constructor parameter 0,
      whose annotation lives only inside the `<init>` signature;
    - `propertiesFedInvoice` — rung 3: the argument is not a field read but
      the RESULT of `billingProperties.getUrl()`, followed one hop to that
      call site, whose owner carries `@ConfigurationProperties(prefix =
      "billing")`; `getUrl` de-prefixes to `url` and relaxed-binds to the
      properties type's own declared `url` field.

    The expression is composed with each chain's own `.uri()` literal and
    kept WHOLE in `path`, `peer` NULL: `${billing.url}` matches no scheme,
    so there is no authority to split off until the per-environment join
    resolves it (the next test)."""
    _, report = resolved_fixture

    assert {
        (row["path"], row["peer"], row["resolution"], row["catalog_id"])
        for row in (
            _billing_row(report, name)
            for name in ("fieldFedInvoice", "constructorFedInvoice", "propertiesFedInvoice")
        )
    } == {
        ("${billing.url}/invoices", None, "resolved", "spring-webclient"),
        ("${billing.url}/refunds", None, "resolved", "spring-webclient"),
        ("${billing.url}/statements", None, "resolved", "spring-webclient"),
    }


def test_a_computed_base_poisons_its_row_rather_than_reporting_the_path_alone(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """`computedBaseInvoice`'s base is `this.fieldUrl + "/v2"` — a
    concatenation whose argument reaches the call site as `unresolved` with
    no property getter behind it, so every rung misses and the ladder answers
    nothing (rung 4).

    The row FLIPS from what Task 3 froze (`resolved`, path `/adjustments`):
    before this task `baseUrl` was captured by nobody, so the `.uri()`
    literal was the whole answer and the row read confident. Now the base IS
    a declared capture, and one that failed — path NULL, `unresolved`
    (checkpoint D-4). Reporting `/adjustments` as the address would state a
    URL the module never calls; the row still says "this method calls
    something over HTTP", which is true."""
    _, report = resolved_fixture
    row = _billing_row(report, "computedBaseInvoice")

    assert (row["path"], row["peer"], row["resolution"]) == (None, None, "unresolved")
    assert row["method"] == "GET"
    assert row["catalog_id"] == "spring-webclient"


def test_the_peer_join_answers_every_client_row_per_environment(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """`resolved_peers` — job 3, a join and never a write. Two environments
    resolve in this fixture, so every client-side row (outbound and `both`)
    is answered twice, and the endpoint rows themselves are untouched.

    Both halves are live now that Task 8's ladder puts real expressions in
    `path`: a literal address passes through unchanged in every environment,
    and the three `${billing.url}` rows substitute per environment — the
    same row, two answers, which is the whole reason peers resolve as a join
    rather than a write. `multi_placeholder` stays unit-tested
    (`test_config_join.py`): no live row carries two placeholders."""
    workspace, report = resolved_fixture
    rows = workspace.query("resolved_peers")
    client_side = [e for e in report.endpoints if e["direction"] != "inbound"]

    assert {row["environment"] for row in rows} == {"default", "prod"}
    assert len(rows) == len(client_side) * 2
    assert {row["unresolved_reason"] for row in rows} == {None}
    # A literal passes through unchanged, both halves of it.
    okhttp = [row for row in rows if row["path"] == "/legacy/exports"]
    assert {(row["resolved_peer"], row["resolved_path"]) for row in okhttp} == {
        ("legacy.acme.internal", "/legacy/exports")
    }
    # An expression resolves to a different real URL per environment.
    billing = [row for row in rows if str(row["path"]).startswith("${billing.url}")]
    assert {(row["environment"], row["resolved_path"]) for row in billing} == {
        ("default", "http://billing.internal/invoices"),
        ("default", "http://billing.internal/refunds"),
        ("default", "http://billing.internal/statements"),
        ("prod", "http://billing.prod.internal/invoices"),
        ("prod", "http://billing.prod.internal/refunds"),
        ("prod", "http://billing.prod.internal/statements"),
    }


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


def test_the_shipped_json_model_reads_an_interfaces_wire_contract_from_its_accessors(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """W26's shipped rule, end to end through `shape-models/json.yml` — which nothing
    checked until its review measured it: the whole `accessors:` block could be DELETED
    and the suite stayed green, because every assertion the wave added was a count and a
    count is identical whether `OrderTotals` expands to three fields or to none.

    `OrderTotals` is an interface, so it has no fields at all and its contract is entirely
    in its accessors. All three near-misses the fixture file names as deliberate are
    checked here too, against the SHIPPED entries rather than a hand-built catalog: `is`
    on a non-boolean return is not a getter (jackson-databind's `findNameForIsGetter`
    refuses it unless `isGettersNonBoolean` is on), `has` is not a declared prefix, and an
    accessor takes no arguments.
    """
    workspace, _report = resolved_fixture
    fields = [
        f["wire_name"] for f in shape_fields_of(workspace, "com/acme/orders/contracts/OrderTotals#")
    ]

    assert fields == ["currency", "lineCount", "settled"]
    # Each of these would appear under a rule one clause looser than Jackson's own.
    for absent in ("isoCode", "oCode", "discount", "hasDiscount", "recalculate"):
        assert absent not in fields
    # And the shape is CLOSED: three accessors describe it completely, so it is not a gap.
    [shape] = [
        row
        for row in workspace.query("shapes")
        if row["shape_id"] == "com/acme/orders/contracts/OrderTotals#"
    ]
    assert shape["open"] is False


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
      through, never a literal or a `NEW`, so the scanner records the
      argument `unresolved` (D00 §5) even though the url is a plain string —
      the row itself is therefore `unresolved` (I1), and `response_shape` — a
      *different*, independently resolved capture on the very same row —
      still carries its real descriptor.
    - `updateSettlement` (`put`) has the identical `settlement` failure on
      its body, and declares no `response_arg` at all: `unresolved` for the
      same reason, `response_shape` NULL for the ordinary reason (no capture
      ever named one).

    **`request_shape` on those two rows used to be NULL as well**, and this
    docstring called it "could-not-read, not no-payload" — which named `OI-77`
    exactly and read it as a designed limit. It was not: the parameter's own
    declared TYPE is in `submitSettlement`'s signature, and a contract needs
    the type, not the value. Both now carry `OrderRequest`, while `resolution`
    stays `unresolved` — those are two columns answering two different
    questions, and this pair is the fixture's live proof they can disagree.
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
    # `resolved` since `OI-77` and W43's review: BOTH captures this row declares were
    # read — the destination from its own string literal, and the payload's TYPE from
    # the caller's signature. It answered `unresolved` while the payload column was
    # NULL, which was the only place that fact could be said; the column says it now.
    assert settlements["resolution"] == "resolved"
    # `OI-77`: the body is the caller's own `settlement` parameter, and its type is
    # declared there.
    assert "com/acme/orders/contracts/OrderRequest#" in str(settlements["request_shape"])
    assert json.loads(settlements["response_shape"]) == {
        "wire_type": "object",
        "wire_format": "",
        "nullable": True,
        "shape_id": "com/acme/orders/contracts/OrderView#",
    }

    update = by_route[("PUT", "/billing/settlements/{id}")]
    # `resolved` since `OI-77` and W43's review, for the same reason as the row above: the
    # url is a plain string and the body's TYPE is declared on the caller's own parameter,
    # so both declared captures were read. `response_shape` stays NULL below because this
    # row declares no response capture at all — an absent capture never failed.
    assert update["resolution"] == "resolved"
    assert "com/acme/orders/contracts/OrderRequest#" in str(update["request_shape"])
    # Still NULL, and for the ordinary reason rather than the one above: this row declares
    # no `response_arg` at all, so nothing ever named a response payload.
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
    the same requirement, and this pins exactly that: two runs of the whole
    resolve agree, row for row.

    What it does NOT pin is *why* they agree. This fixture's rows reach the
    table caller-sorted already, so it would still pass with the `endpoints`
    query's own `caller` tiebreak (2D) removed — the tiebreak's own work is
    pinned directly instead, in `tests/storage/test_workspace.py`, by
    inserting two rows tied on every earlier column in reverse caller
    order."""
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
        fact_schema_version=2,
        scanner_id="asm",
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


def test_config_documents_with_colliding_basenames_both_survive_to_the_workspace(
    tmp_path: Path,
):
    """`application.properties` and `application.yml` — the exact pair
    spring-web.yml's `config_model.sources` declares side by side, and the
    most common real Spring layout — must not collide onto one fact-file
    target. Before `config_fact_target` appended `.jsonl` to the full
    relative path, `Path(...).with_suffix(".jsonl")` mapped both to
    `application.jsonl`; whichever document's `write_fact_file` ran second
    silently discarded the other's document record and every config entry
    it carried. This mirrors `stages/analyze.py`'s own read loop directly
    against a synthetic resource root, without the mvn/AsmScanner fixture
    the other config-read tests here need — cheap coverage for a bug that
    lives entirely in the read step's own path arithmetic."""
    root = tmp_path / "resources"
    root.mkdir()
    (root / "application.properties").write_text("server.port=8080\n", encoding="utf-8")
    (root / "application.yml").write_text("server:\n  host: localhost\n", encoding="utf-8")

    facts = tmp_path / "facts"
    for reader, owned in group_files_by_reader(
        list_files(root, tmp_path, IgnoreRules.load(tmp_path)),
        [PropertiesReader(), YamlConfigReader()],
    ):
        request = ReadRequest(
            module_id="com.acme:orders-service", version="1.0.0", files=owned, root=root
        )
        for document, config_facts in reader.read(request):
            target = config_fact_target(facts, document.relative_path)
            write_fact_file(target, document, config_facts)

    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(facts)
    documents = workspace.query("documents")
    entries = workspace.query("config_entries")
    workspace.close()

    assert {d["relative_path"] for d in documents} == {
        "application.properties",
        "application.yml",
    }
    assert {e["key_raw"] for e in entries} == {"server.port", "server.host"}


def test_the_reachability_table_is_written_by_the_pipeline(
    resolved_fixture: tuple[DuckDbWorkspace, ResolveReport],
):
    """F8 §9.4 (W37). Every test of the pass calls `record_reachability` DIRECTLY, so
    deleting the call from `resolve()` left the whole suite green — 2,631 passed, the exact
    number the commit quoted as its gate — while the table would be empty in every real
    bundle (W37 review).

    A pass nothing runs is a pass that does not exist, and no unit test of it can say
    otherwise. This asserts the pipeline runs it, over the real fixture.
    """
    workspace, _report = resolved_fixture
    rows = workspace._connection.execute(
        "SELECT root, symbol, depth, terminal FROM reachability"
    ).fetchall()

    assert rows, "the pipeline did not write the reachability table"
    # Every root the walk starts at records ITSELF at depth 0, so the table covers the
    # whole root set rather than whichever roots happened to call something.
    roots = {row["handler"] for row in workspace.query("roots")}
    assert {row[0] for row in rows} == roots
    assert {row[0] for row in rows if row[2] == 0} == roots
    # And the walk really walked: some root reaches something other than itself.
    assert any(row[2] > 0 for row in rows)
