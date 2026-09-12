import hashlib
import json
from pathlib import Path

import duckdb
import pytest
from click.testing import CliRunner

from fixture_build import compile_fixture
from sextant.application.enrich.validate import validate_overlay
from sextant.cli.app import cli
from sextant.domain.enrichment import load_overlay
from sextant.domain.factfile import read_fact_file
from sextant.domain.ignorefile import IgnoreRules
from sextant.domain.redaction import REDACTED, Redactor
from sextant.ingress.detect.sextant_config import read_redaction_rules
from sextant.resources import instructions_path
from sextant.storage.duckdb.workspace import DuckDbWorkspace

REPO = Path(__file__).parents[2]
FIXTURE = REPO / "fixtures" / "orders-service"
COORDINATE = "com.example:orders-soap-client"


@pytest.fixture(scope="module")
def full_run(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """`analyze` + `render` + `export` over the fixture, ONCE, for the tests that only
    read the result.

    MEASURED 2026-09-11: `_run` was called sixteen times in this file, each a full
    pipeline over a fixture whose source does not change during a run. The file sits at
    76% of the suite, which is one of the two places a CI progress bar visibly stops.

    Three tests keep their own run and must: one compares two runs byte for byte (NFR-1's
    only enforcement), one re-reads the bundle after mutating the workspace, and one plants
    credentials to check they are masked on the way out.
    """
    workspace = tmp_path_factory.mktemp("full-run")
    _run(workspace)
    return workspace


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
    compile_fixture(FIXTURE)
    first, second = tmp_path / "one", tmp_path / "two"
    _run(first)
    _run(second)
    assert _fingerprint(first) == _fingerprint(second)
    # NFR-1 over the two non-wire tables (2O design §4, Task 8 step 5). The
    # fingerprint above already globs every `.parquet` in the workspace, so
    # both files were compared — but "compared" and "present" are different
    # claims, and a table that stopped being exported would make the first
    # hold vacuously while the second failed. Named here so the coverage is a
    # claim rather than a glob's side effect.
    #
    # This fixture schedules nothing and declares no advice, so both exports
    # are EMPTY, and that is what is being pinned: the empty file must be
    # byte-identical too. A pre-declared table that shipped no parquet at all
    # would leave a bundle consumer unable to tell "this module runs no
    # background work" from "this bundle does not carry that answer".
    exported = {
        path.name for workspace in (first, second) for path in workspace.rglob("graph/*.parquet")
    }
    for table in ("scheduled_work", "error_handlers"):
        assert f"{table}.parquet" in exported, (
            f"`{table}` did not reach the bundle, so the byte-identity comparison above "
            f"held over a file that was never written"
        )


def test_the_document_names_every_fixture_endpoint_and_its_gaps(full_run: Path):
    document = (full_run / "render" / "architecture.md").read_text()
    for route in ("POST", "GET", "/v1/orders", "/v1/orders/{id}"):
        assert route in document
    # The prefix seam, live through `spring-web.yml` (`mapping.path_separator`).
    # Both forms are ordinary Spring, both derived a wrong address while the
    # seam was a bare concatenation, and both were found live against
    # spring-petclinic-microservices before they were fixtures here:
    # `SeamController`'s prefix spells no trailing slash and its method path no
    # leading one (was `/v1/seamowners/{ownerId}`), and `RootSeamController`'s
    # `"/"` prefix meets a slash-leading method path (was `//chat`). Pinned
    # with the surrounding backticks so the doubled-slash form cannot pass as
    # a substring of the fixed one.
    assert "`GET /v1/seam/owners/{ownerId}`" in document
    assert "`POST /chat`" in document
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
    # verbatim in the SAME row as the identity, human-spelled in the table
    # (2M design §5c). The `(sig_...)` suffix — the handler is the METHOD
    # SYMBOL the facts carry, joined out of `symbols` (final review, FIX 1),
    # not a string built from the receiver's type descriptor and the
    # catalog's method name — now lives in the endpoint's own detail block,
    # every endpoint's own row in the document below the table.
    assert "`pubsub raw-notify` | `RawPubSubReceiver#receiveMessage`" in document
    # The detail header carries both the wire identity and the full symbol
    # (fix round 1, MEDIUM 1) — one convention regardless of direction.
    assert (
        "- `pubsub raw-notify` — "
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
        "`websocket /live` | `LiveEndpoint#onFrame` | — → — | unresolved | resolved |" in document
    )
    assert (
        "`websocket /orders/place` | `OrderStompController#place` | — → — | json (assumed) | resolved |"
        in document
    )
    assert (
        "`websocket /orders/board` | `OrderStompController#board` | — → — | json (assumed) | resolved |"
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
    # F8 §9.5 (W38), and the half that had NO test: `coverage_of` is called on the RENDER
    # path as well as the resolve one, because `render` reads the workspace back rather
    # than re-resolving — so a summary composed only in `resolve/pipeline.py` reached
    # `metadata.json` and never the document a person opens. Reverting that call to
    # `workspace.query("coverage")[0]` passed 348 tests across `tests/api`, `tests/e2e`,
    # `tests/cli` and `tests/egress` while these three lines silently vanished; the two
    # unit tests that exist hand-build the coverage dict and cannot see the composition.
    # Pinned HERE, at the end of the whole pipeline, because that is where the path is.
    # 1485 since the four features delivered 2026-09-11 — SOAP's repeatable `@PayloadRoot`,
    # GraphQL's repeatable `@DgsData` and entity fetcher, the programmatic WebSocket
    # registration and the async SQS send — each adding a fixture class and the calls it
    # makes. The NUMERATOR is unmoved at 468: none of those reads a new callee BODY, so the
    # percentage is flat at 32% while the denominator grows, which is the honest shape of
    # "more of the module is visible and none of it is newly expanded".
    # 1486 and 31%: `ShipmentRepository$Shipment`'s constructor adds one edge (its
    # `Object.<init>` call); the numerator stays 468 and the rounding tips 32 -> 31.
    assert "Calls whose callee body this workspace read: 468 of 1486 (31%)" in document
    assert "Dispatch, by outcome (call edges): narrowed 2, resolved 1484." in document
    assert (
        "Method lookup, by outcome (methods): ancestor_not_scanned 33, declared_here 191, "
        "inherited 2, owner_not_scanned 345."
    ) in document

    # W43 closes G-33's asymmetry: this module RECEIVED STOMP and sent none, so half
    # its messaging surface was missing with nothing saying which half. The destination
    # resolves from the call's own string literal even though the descriptor types it
    # `Object` — `convertAndSend` is declared on `MessageSendingOperations<D>` and `D`
    # erases, which is why a rule mirrored from `KafkaTemplate.send(String, V)` would
    # have matched nothing at all.
    # Two columns moved with `OI-77`, and they are different questions. The FORMAT reads
    # `json (assumed)` because the payload is handed through from `announce`'s own
    # parameter, so the row carries `OrderView` and the ladder has a declared type to
    # answer off. The row's own RESOLUTION reads `resolved` because both captures this row
    # declares were read — the destination from its string literal, the payload's type from
    # the caller's signature. It answered `unresolved` while the payload column was NULL,
    # which was then the only place that fact could be stated.
    assert (
        "`websocket /topic/order-announced` | unresolved | "
        "`com/example/orders/ws/OrderStompPublisher#announce(sig_7cebbae5).` | "
        "json (assumed) | resolved |"
    ) in document
    # The default-destination overload takes no destination argument at all, so the
    # boundary is published with its address stated as unresolved rather than dropped —
    # `KafkaTemplate.sendDefault`'s own answer, one framework along.
    # And the default-destination row stays `unresolved`, which is the pair that makes the
    # distinction legible: it takes NO destination argument at all, so a capture really did
    # fail here — the template's configuration carries the address and nothing in this
    # module states it.
    assert (
        "`websocket (unresolved)` | unresolved | "
        "`com/example/orders/ws/OrderStompPublisher#announceToDefault(sig_7cebbae5).` | "
        "json (assumed) | unresolved |"
    ) in document
    # 2H Task 6: an SSE row is the first VERBED, protocol-qualified row whose
    # verb is an ordinary HTTP method — `sse GET /events/stream`, not the
    # verbless `sse /events/stream` a derived-set membership would have given
    # it, and not the unqualified `GET /events/stream` that reads as an
    # ordinary REST route. Both halves of that identity are load-bearing, and
    # both rows are pinned because they arrive by different evidence (media
    # for `/stream`, return type for `/emitter`).
    #
    # `— → text/event-stream` is the Media column: the MIME string is still
    # there and still declared, and the Format column beside it reads `json
    # (assumed)` rather than anything derived from it — the envelope names the
    # protocol, never the format.
    assert (
        "`sse GET /events/emitter` | `OrderEventsController#emitterEvents` | — → — | json (assumed) | resolved |"
        in document
    )
    assert (
        "`sse GET /events/stream` | `OrderEventsController#streamEvents` | — → text/event-stream | json (assumed) | resolved |"
        in document
    )
    # The per-event payload unwraps through BOTH envelopes (2H design §6's
    # payload sentence; `rooting.py` peels recursively, so the one
    # `ServerSentEvent` `wrappers` entry reaches `OrderView` under `Flux`).
    # `OrderView`'s own two fields are what the row publishes — its
    # `HttpHeaders` field is third-party, so the shape stays open, which the
    # fixture's own source comment says outright.
    assert "| id | string | yes | yes |" in document
    # And the envelope type is gone from the open-type disclosure entirely:
    # nothing references it any more, so nothing rooted it.
    assert "org/springframework/http/codec/ServerSentEvent#" not in document
    # `/events/emitter` is the half that cannot follow and says so.
    # `SseEmitter` is a callback handle with no type argument to unwrap, so it
    # is disclosed open rather than published as an empty contract.
    assert (
        "Not expanded, so the shapes referring to it are open: "
        "`org/springframework/web/servlet/mvc/method/annotation/SseEmitter#`."
    ) in document


def test_every_fact_the_extractor_writes_validates_against_the_domain_model(full_run: Path):
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

    files = sorted((full_run / "facts").rglob("*.jsonl"))
    validated = [read_fact_file(path) for path in files]
    kinds = {fact.kind for _, facts in validated for fact in facts}
    total = sum(len(facts) for _, facts in validated)

    assert files != []
    assert {"annotation", "call_site", "symbol"} <= kinds
    assert total >= len(files)


def test_the_bundle_answers_what_the_workspace_answered(tmp_path: Path):
    compile_fixture(FIXTURE)
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
    # 2H Task 6 (`protocol_hint`): the FIRST change here that adds no row at
    # all. `GET /events/emitter` and `GET /events/stream` MOVE out of `http`
    # into a new `sse` bucket — 34 becomes 32, `sse` becomes 2 — and the
    # total is unchanged at 116, which is the pass's own second promise
    # (it reclassifies; it never creates or removes an endpoint) read off
    # the published metadata rather than asserted in a comment. Nothing
    # outbound moves: the two rows are inbound routes, and this pass never
    # touches direction.
    # The prefix-seam controllers add 2 inbound http rows (`GET
    # /v1/seam/owners/{ownerId}`, `POST /chat`) — 32 becomes 34. The
    # `path_separator` fix itself moved no row between buckets and created
    # none; it changed the ADDRESS two rows carry.
    # 2I Task 2 (`spring-ws.yml`): +2 soap INBOUND — `OrderSoapEndpoint`'s
    # two identity forms, `@PayloadRoot`'s QName
    # (`{http://orders.example.com/ws}placeOrderRequest`) and `@SoapAction`'s
    # header URI (`http://orders.example.com/action/cancelOrder`). A NEW
    # protocol bucket, and nothing outbound: `spring-ws.yml` is
    # `direction: inbound` and declares no `reply` block, since a SOAP
    # response travels back down the same request the operation arrived on
    # rather than to a destination the code names.
    # 2I Task 2 (controller ruling), `jakarta-jws.yml`: +3 soap inbound —
    # `{…billing…}chargeOrder` (annotated), `{…billing…}refund` (the DR-6 row,
    # no annotation at all, derived by the class-gate member rule) and
    # `{http://soap.orders.example.com/}legacyCharge` (the javax spelling with
    # a bare `@WebService`, taking the reversed-package default). FOUR public
    # methods produce those three: `internalAudit`'s
    # `@WebMethod(exclude = true)` is JAX-WS withdrawing the operation, so it
    # derives nothing. `soap` becomes 5.
    # 2I Task 4 (`wsdl-schema.yml`, `schema_operations`'s SOAP analog of 2H
    # Task 4's `graphql-schema.yml`): +1 soap inbound —
    # `{http://orders.example.com/ws}quoteOrderRequest`, the one WSDL input
    # element in `orders.wsdl` that no `@PayloadRoot`/`@SoapAction` implements.
    # `placeOrderRequest` shares its identity with `spring-ws.yml`'s own row
    # (2I Task 2) and the insert-if-absent guard keeps THAT one — the same
    # first-writer agreement `auditTrail`'s own comment above states, now live
    # on a second protocol. `soap` becomes 6.
    # 2I Task 5 (`spring-ws-template.yml`): +1 soap OUTBOUND and NO new row.
    # `BillingSoapClient` calls `marshalSendAndReceive` twice, and both calls
    # hand over a `PlaceOrderRequest`, whose `@XmlRootElement` names the very
    # QName `OrderSoapEndpoint#placeOrder` already serves — so the outbound row
    # merges into that inbound one (D02 §3) and the identity becomes
    # `direction: both`, counted once in each bucket. The total stays 116 + 6
    # and `soap` stays 6 inbound; only the outbound side gains its 1.
    # 2I Task 6 (opt-in library extraction): +1 soap OUTBOUND, `stubCharge` —
    # an operation declared in a jar and in no source file here. `soap`
    # outbound becomes 2; inbound is untouched, because a stub declares calls
    # and never a service.
    # 2O Task 4 (`grpc-schema.yml`, `schema_operations`'s gRPC analog of 2H
    # Task 4's `graphql-schema.yml` and 2I Task 4's `wsdl-schema.yml`): +2 grpc
    # inbound — `sextant.orders.OrderService/GetOrder` (unary) and
    # `sextant.orders.OrderService/StreamOrders` (server-streaming), the two
    # methods `order.proto`'s new `service OrderService` block declares. A NEW
    # protocol bucket — the fifth D00's closed set gains live in this fixture
    # (`graphql`, `sse`, `websocket`, `soap`, now `grpc`) — and nothing
    # outbound: no annotation catalog implements either method here, so
    # neither row has a bytecode twin to merge with or a caller to derive.
    # `soap` stays 6/2; `grpc` is new at 2/0.
    metadata = json.loads((tmp_path / "metadata.json").read_text())
    assert metadata["endpoints"]["inbound"] == {
        "graphql": 15,
        "grpc": 2,
        # + 8: 2O Task 6's Spring Data REST rows (`test_app.py`'s own note
        # carries the breakdown).
        # 43 since OI-47: the covariant inherited mapping
        # (`GET /api/orders/{id}`) that used to be lost with the bridge it was
        # reachable through. The bundle answers what the workspace answers, so
        # this moves with `tests/cli/test_app.py`'s own count.
        # 44 since OI-48: `POST /v1/orders/scoped`, which roots the package-scope
        # nullability case the fixture previously declared and never reached.
        # 48 since W26: the four `/v1/paged/*` routes — `/totals`, whose payload is an
        # interface described from its bean accessors, and three paged ones whose
        # envelope lives in a jar this fixture opts into scanning nowhere.
        # 51 since W28: `RoutingConditionsController`'s three handlers on one path and
        # verb, which Spring registers because `params`/`headers` separate them.
        # 54 since W44: the three `/mvcfn` Spring MVC functional routes (`G-29`).
        "http": 60,
        "jms": 5,
        "kafka": 15,
        "pubsub": 3,
        # 8 since `G-36` — `amendOrder`'s two `@PayloadRoot` both derive now.
        "soap": 8,
        "sqs": 4,
        "sse": 2,
        # 6 since W45: the three connect URLs `addEndpoint` registers.
        "websocket": 7,
    }
    assert metadata["endpoints"]["outbound"] == {
        # 25 since W29: `InventoryWebClient#tagged`, whose three headers are the fixture's
        # `endpoint_metadata` rows, and `#searched`, whose url is built inside a
        # `uri(Function)` lambda and therefore derives with `path` NULL and
        # `resolution: unresolved` — the call recorded, its address honestly unread
        # (`OI-73`).
        # 29 since W27's review: four second callers the outbound dedup had been
        # deleting outright (F5 §6.1 rule 1).
        "http": 29,
        "jms": 3,
        "kafka": 11,
        "pubsub": 4,
        # 3: `BillingSoapClient#placeAt` calls a DIFFERENT host with the same payload
        # QName, and was being dropped as a duplicate of `#place`.
        "soap": 3,
        "sqs": 4,
        # 4 since W43: `OrderStompPublisher`'s two `SimpMessagingTemplate.convertAndSend`
        # calls beside the two `@SendTo`/dynamic replies `spring-stomp` already derived.
        # Before it the module was published receiving STOMP and never sending any.
        # 7 since W46: the three client connects that close `G-32`.
        "websocket": 7,
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
    # The prefix-seam controllers: +2 inbound (`GET /v1/seam/owners/{ownerId}`,
    # `POST /chat`) — inbound 71 + 2 = 73 — the 118-endpoint total
    # (5 + 73 + 40 = 118).
    # 2I Task 2: +5 inbound soap — 2 from `spring-ws.yml` (one per identity
    # form) and 3 from `jakarta-jws.yml` (one per exposed operation) —
    # inbound 73 + 5 = 78 — the 123-endpoint total (5 + 78 + 40 = 123).
    # Nothing outbound and nothing `both`: the catalog is `direction: inbound`
    # with no `reply` block, and no soap row can merge with an http one
    # because wire identity is protocol-scoped (D01 §3).
    # 2I Task 4 (`wsdl-schema.yml`): +1 inbound soap —
    # `{http://orders.example.com/ws}quoteOrderRequest`, the schema's own
    # unimplemented operation (comment above, `metadata["endpoints"]`) —
    # inbound 78 + 1 = 79 — the 124-endpoint total (5 + 79 + 40 = 124).
    # Nothing outbound and nothing `both`, for the same reason Task 2's own
    # row is neither.
    # 2I Task 5 (`spring-ws-template.yml`): the SIXTH `both` row, and the first
    # one on a non-http protocol that was not already a messaging destination.
    # `BillingSoapClient` calls the very operation `OrderSoapEndpoint` serves —
    # the payload type's own `@XmlRootElement` states the same QName
    # `@PayloadRoot` does — so D02 §3's merge fires exactly as designed: the
    # inbound row becomes `both` and keeps its handler, the outbound row is
    # deleted and its caller and peer are carried onto the survivor. Inbound
    # 79 - 1 = 78 and `both` 5 + 1 = 6, outbound unchanged at 40 — the total
    # stays 124 (6 + 78 + 40), because a merge moves a row rather than adding
    # one.
    #
    # BOTH of the fixture's `marshalSendAndReceive` calls carry that one
    # identity (they hand over the same payload type), so the two collapse to
    # ONE outbound row before the merge — D02 §5's insert-if-absent on wire
    # identity, which does not compare `peer`. The surviving row is `place`'s,
    # in `call_sites` order, so the `peer` recorded is the config-fed
    # `${soap.billing.uri}` and `placeAt`'s literal
    # `http://billing.example.com/ws/direct` is the one dropped. Pinned as it
    # is rather than worked around: two addresses for one operation are two
    # peers on one identity, and the identity is what this table is keyed on.
    # 2I Task 6 (opt-in library extraction): +1 outbound soap —
    # `{http://billing.example.com/ws}stubCharge`, derived by
    # `jakarta-jws-client.yml` from a `@WebService` interface that exists in NO
    # source file of this module. It is the first row in this fixture whose
    # evidence came out of a jar rather than out of `target/classes`, and it
    # appears here only because `.sextant.yml` names the library — outbound
    # 40 + 1 = 41 — the 125-endpoint total (6 + 78 + 41 = 125). Nothing merges:
    # `stubCharge` is an operation nothing in this module serves.
    # 2O Task 4 (`grpc-schema.yml`): +2 inbound grpc — `order.proto`'s new
    # `service OrderService` block (comment above, `metadata["endpoints"]`) —
    # inbound 78 + 2 = 80 — the 127-endpoint total (6 + 80 + 41 = 127).
    # Nothing outbound and nothing `both`: the catalog is `direction: inbound`
    # with no reply mechanism, and a grpc row cannot merge with anything else
    # in the fixture — wire identity is protocol-scoped (D01 §3), and no
    # annotation catalog implements either method here.
    # 2O Task 6 (`spring-data-rest.yml`): +8 inbound http — the CRUD and search
    # routes `CatalogRepository` earns, derived from a framework rule rather
    # than from any declaration in this module — inbound 80 + 8 = 88. Nothing
    # merges: no controller in this fixture serves `/orderViews`.
    # OI-47: +1 inbound http — `GET /api/orders/{id}`, the covariant inherited
    # mapping that used to be discarded along with the bridge it was reachable
    # through — 88 + 1 = 89, for a 136-endpoint total (6 + 89 + 41 = 136).
    # OI-48: +1 inbound http — `POST /v1/orders/scoped` — 89 + 1 = 90, for a
    # 137-endpoint total (6 + 90 + 41 = 137).
    # W27 (F5 §6.1): the six `both` rows are gone, and each is two rows again — 94 + 6
    # inbound is 100, 41 + 6 outbound is 47, for a 147-endpoint total. Nothing new is
    # derived here; six deletions stopped happening, and two of the six were joining a
    # served operation to a call at a different address.
    # W28: +3 inbound — 100 + 3 = 103. W29: +2 outbound — 47 + 2 = 49, for a
    # 152-endpoint total.
    # 55 outbound since W27's review: six second callers the dedup had been deleting
    # (F5 §6.1 rule 1). Inbound is untouched — that key always carried the handler.
    # W43: +2 outbound — 57 — the two `SimpMessagingTemplate.convertAndSend` calls
    # that close G-33's asymmetry.
    # W44: +3 inbound — 106 — the three `/mvcfn` Spring MVC functional routes that close
    # G-29.
    # W45: +3 inbound — 109 — the three STOMP connect URLs that close G-42.
    # W46: +3 OUTBOUND — 60 — the three client connects that close G-32, for a
    # 169-endpoint total.
    # 111 inbound since `G-36`: `amendOrder`'s two `@PayloadRoot` both derive now, where
    # only the first did. Outbound is untouched — a repeatable mapping annotation says
    # nothing about the direction of anything.
    assert (
        rows
        == [  # 115 = 111 + 3 GraphQL (`Order.dgsTotal`, `Order.dgsSubtotal`, the `Order` entity
            # fetcher) + 1 WebSocket (`/ws/tickets`, programmatic registration); 61 = 60 + 1
            # SQS (the async client's send). Each is a feature delivered 2026-09-11 and each
            # has an intention test in `tests/e2e/test_*_delivered.py` that fails without it.
            ("inbound", 121),
            ("outbound", 61),
        ]
    )


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
    compile_fixture(FIXTURE)
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
        # This test is about the PARSE binding's questions. `self_exchange` (W27, F5
        # §6.1) files six of its own against this fixture — the identities it both
        # serves and calls — and they are pinned in `test_self_exchange.py` and in the
        # rendered-document test below rather than here.
        questions = [
            (str(row["path"]), str(row["question"]), json.loads(str(row["candidates"])))
            for row in workspace.query("open_questions")
            if str(row["question"]) == "payload_binding"
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
    compile_fixture(FIXTURE)
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


def test_the_repository_interfaces_derive_their_rest_api_in_a_full_analyze(tmp_path: Path):
    """2O Task 6, live and whole, through the REAL command — the only path that
    builds the module fact the gate reads, so this is the only place the whole
    chain runs: the POM declares `spring-data-rest-core`, the detector records
    that coordinate, the analyze stage writes it as a `module` fact, the gate
    reads it back, and the engine derives a REST API from three interfaces that
    declare no path, no verb and no HTTP anything.

    Three claims, and the two that DECLINE matter at least as much as the one
    that fires — this style mints an entire API from ordinary-looking code, so
    a suite that only proved it can fire would not tell us it declines
    correctly (GUIDELINES §10):

    * `CatalogRepository` derives eight routes: the six-route CRUD table plus
      `/search/findByStatus` and `/search/by-customer` (renamed by
      `@RestResource`). It carries NO `@RepositoryRestResource` at all, which
      is the case §2 exists for;
    * `SecretRepository` is `exported = false` and derives NOTHING — not even a
      collection route;
    * `OrderRepository` extends the fixture's OWN `Repository<T, ID>`
      stand-in, which is not one of the Spring Data contracts the catalog
      enumerates, and derives NOTHING either. Real bytecode, shipped catalog,
      ordinary generic interface: the near-miss that a synthetic test can only
      approximate.
    """
    compile_fixture(FIXTURE)
    runner = CliRunner()
    result = runner.invoke(cli, ["module", "analyze", str(FIXTURE), "--workspace", str(tmp_path)])
    assert result.exit_code == 0, result.output

    workspace = DuckDbWorkspace(tmp_path / "workspace.duckdb")
    try:
        rows = [
            row for row in workspace.query("endpoints") if row["catalog_id"] == "spring-data-rest"
        ]
        every_path = {str(row["path"]) for row in workspace.query("endpoints")}
    finally:
        workspace.close()

    assert {(str(row["method"]), str(row["path"])) for row in rows} == {
        ("GET", "/orderViews"),
        # `G-45`: `ShipmentRepository`, a `MongoRepository` — the same six routes Spring
        # Data REST exposes for any store, once the roster names the store contract.
        ("GET", "/shipments"),
        ("POST", "/shipments"),
        ("GET", "/shipments/{id}"),
        ("PUT", "/shipments/{id}"),
        ("PATCH", "/shipments/{id}"),
        ("DELETE", "/shipments/{id}"),
        ("POST", "/orderViews"),
        ("GET", "/orderViews/{id}"),
        ("PUT", "/orderViews/{id}"),
        ("PATCH", "/orderViews/{id}"),
        ("DELETE", "/orderViews/{id}"),
        ("GET", "/orderViews/search/findByStatus"),
        ("GET", "/orderViews/search/by-customer"),
    }
    # The entity's own name, uncapitalized in its first character and then
    # pluralized by the ported Evo Inflector rules — never the repository's.
    assert not any("catalog" in path.lower() for path in every_path)
    # `exported = false` and the non-Spring-Data supertype: nothing, from
    # either.
    assert not any("orderRequest" in path for path in every_path)
    assert not any("orderResult" in path for path in every_path)

    by_identity = {(str(row["method"]), str(row["path"])): row for row in rows}
    crud = by_identity[("GET", "/orderViews")]
    search = by_identity[("GET", "/orderViews/search/findByStatus")]
    # D02's `default_produces`, live: the framework serves HAL and does not
    # negotiate its own representation.
    assert crud["produces"] == '["application/hal+json"]'
    assert (crud["resolution"], crud["evidence"]) == ("resolved", "declared")
    # No code in this module serves the CRUD route; the query method DOES serve
    # its own search route, and that is the difference the handler column
    # carries.
    assert crud["handler"] is None
    assert str(search["handler"]).endswith("CatalogRepository#findByStatus(sig_b9c62fe1).")


def test_a_schema_first_operation_reaches_the_rendered_document(full_run: Path):
    """The same row at the document a reader actually sees. `none recorded`
    rather than `unresolved`: the schema addressed this operation outright and
    names no code, which is an absence rather than a failed read — and the
    response the reader gets is the schema's own type, by its schema name.

    2M design §5c: the row's own detail block names the endpoint by its wire
    identity and then reads the same `none recorded` fallback the Handler
    column shows — there is no full symbol to move for a row with no
    handler (fix round 1, MEDIUM 1: the identity stays in the header even
    where there is no symbol to append after it)."""
    _run(full_run)  # analyze + render + export
    document = (full_run / "render" / "architecture.md").read_text()

    assert "| `graphql query auditTrail` | none recorded | — → — | json | resolved |" in document
    assert (
        "- `graphql query auditTrail` — none recorded\n  - Response: array of object AuditEntry"
    ) in document


def test_the_wsdl_schemas_own_root_operation_reaches_the_endpoint_table_in_a_full_analyze(
    tmp_path: Path,
):
    """2I Task 4 (`schema_operations`'s SOAP branch), live and whole, through
    the REAL command — the only path that reads `orders.wsdl` at all. The
    SOAP mirror of `test_the_schemas_own_root_operations_reach_the_endpoint_
    table_in_a_full_analyze` above, and the one that proves the per-SHAPE
    branch this task adds is live, not just unit-tested.

    Three claims:

    * the per-shape pin — `quoteOrderRequest` is the one WSDL input element
      in the fixture that no `@PayloadRoot`/`@SoapAction` implements, so it
      is the one new row, at `declared` with no handler and no caller, and
      its own FIELDS (`sku`/`count`/`status`/`cancelledAt`) derive no rows of
      their own — the per-shape-not-per-field pin, live;
    * first-writer agreement — `placeOrderRequest` already had an annotation
      row (`spring-ws.yml`, 2I Task 2) when this style ran, and the
      insert-if-absent guard kept it, handler and all — the exact live case
      2I Task 3's own fixture note names;
    * the wrapper is wire-true (2I design §4) — `quoteOrderRequest`'s
      `request_shape` self-references its own shape, unlike a GraphQL root
      field's NULL (whose arguments are never projected). Its
      `response_shape` stays NULL and gets no stamp at all: 2I Task 3 marks
      INPUT elements only, so there is no output linkage to honestly
      coalesce a response from — this task's own stated boundary.
    """
    compile_fixture(FIXTURE)
    runner = CliRunner()
    result = runner.invoke(cli, ["module", "analyze", str(FIXTURE), "--workspace", str(tmp_path)])
    assert result.exit_code == 0, result.output

    workspace = DuckDbWorkspace(tmp_path / "workspace.duckdb")
    try:
        # Keyed on the DIRECTION as well as the path since W27 (F5 §6.1):
        # `{...}placeOrderRequest` is two rows — the operation this module serves, and
        # `BillingSoapClient`'s call to `${soap.billing.uri}` — where the merge used to
        # leave one. Keyed on the path alone, whichever row came second would silently
        # replace the other.
        soap = {
            (str(row["path"]), str(row["direction"])): row
            for row in workspace.query("endpoints")
            if row["protocol"] == "soap"
        }
        quote_fields = [
            (str(row["wire_name"]), row["wire_type"], row["nullable"])
            for row in workspace.query("shape_fields")
            if row["shape_id"] == "{http://orders.example.com/ws}quoteOrderRequest"
        ]
    finally:
        workspace.close()

    # The whole SOAP surface: 2I Task 2's five annotation-driven rows, this
    # task's one schema-first row, and — since Task 6 — the one operation that
    # reaches the graph from a jar rather than from a source file.
    assert set(soap) == {
        ("{http://orders.example.com/ws}placeOrderRequest", "inbound"),
        # W27: the call `BillingSoapClient#place` makes to `${soap.billing.uri}`. It was
        # merged into the served row above on the strength of a shared QName — which the
        # two compose from the same payload TYPE, not from a shared identity.
        ("{http://orders.example.com/ws}placeOrderRequest", "outbound"),
        ("{http://orders.example.com/ws}quoteOrderRequest", "inbound"),
        ("http://orders.example.com/action/cancelOrder", "inbound"),
        # `G-36`: `amendOrder` declares two `@PayloadRoot`, which is how Spring-WS routes
        # two message types to one handler — the annotation is
        # `@Repeatable(PayloadRoots.class)` and the container is now declared, so the
        # second message stops being served in production and absent from the document.
        ("{http://orders.example.com/ws}amendOrderRequest", "inbound"),
        ("{http://orders.example.com/ws}reviseOrderRequest", "inbound"),
        ("{http://billing.example.com/ws}chargeOrder", "inbound"),
        ("{http://billing.example.com/ws}refund", "inbound"),
        ("{http://billing.example.com/ws}stubCharge", "outbound"),
        ("{http://soap.orders.example.com/}legacyCharge", "inbound"),
    }
    schema_first = [key for key, row in soap.items() if row["catalog_id"] == "wsdl-schema"]
    assert schema_first == [("{http://orders.example.com/ws}quoteOrderRequest", "inbound")]

    quote = soap[("{http://orders.example.com/ws}quoteOrderRequest", "inbound")]
    assert (quote["method"], quote["direction"]) == (None, "inbound")
    assert (quote["evidence"], quote["resolution"]) == ("declared", "resolved")
    assert quote["handler"] is None and quote["caller"] is None
    assert (quote["format"], quote["format_resolution"]) == ("xml", "resolved")
    assert json.loads(str(quote["request_shape"])) == {
        "wire_type": "object",
        "wire_format": None,
        "nullable": False,
        "shape_id": "{http://orders.example.com/ws}quoteOrderRequest",
    }
    assert quote["response_shape"] is None
    # None of the request shape's own FIELDS derives a row of its own.
    assert not {"sku", "count", "status", "cancelledAt"} & {path for path, _ in soap}

    # The annotated identity kept the annotation's row — the handler symbol
    # is the thing only that side knows.
    place = soap[("{http://orders.example.com/ws}placeOrderRequest", "inbound")]
    assert place["catalog_id"] == "spring-ws"
    assert place["handler"] is not None
    # And the call keeps its own provenance, which the merge discarded with the row it
    # deleted: `catalog_id` names the catalog whose rules produced THIS row (D01 §3).
    called = soap[("{http://orders.example.com/ws}placeOrderRequest", "outbound")]
    assert called["catalog_id"] == "spring-ws-template"
    assert called["caller"] is not None and called["handler"] is None

    # The shape `request_shape` self-references, expanded from the schema's
    # own field declarations (2I Task 3) — pinned once more here as the live
    # cross-check that the shape this row points at is real.
    assert quote_fields == [
        ("sku", "string", False),
        ("count", "integer", False),
        ("status", "enum", False),
        ("cancelledAt", "string", True),
    ]


def test_the_soap_client_call_stands_beside_the_operation_it_names_and_carries_its_address(
    tmp_path: Path,
):
    """2I Task 5 (`spring-ws-template.yml`), live and whole through the real
    command — the outbound half of this phase's SOAP surface.

    Four claims, each of which was a separate piece of machinery:

    * THE OPERATION IS READ OFF THE PAYLOAD TYPE. `marshalSendAndReceive`'s
      argument is a bare `parameter` and its own declared descriptor is the
      erased `(Ljava/lang/Object;)…`, so the call site names no payload at
      all. `path_from_argument_type` follows the one hop the facts already
      support — caller → declared signature → parameter type — and reads
      `@XmlRootElement(name, namespace)` off that type, deriving the same
      `{http://orders.example.com/ws}placeOrderRequest` QName the handler's
      `@PayloadRoot` states and `orders.wsdl` declares. Three independent
      statements of one identity, meeting.
    * THE ADDRESS IS READ OFF THE CONFIGURATION. `place` passes no URI: the
      template's `defaultUri` was set in `BillingSoapClient`'s own
      constructor from a `@Value("${soap.billing.uri}")` parameter, and
      `default_address` plus the field ladder's parameter rung name that
      expression. It lands in `peer` whole — a SOAP address is not the wire
      identity here, and half of an expression is not an address — where the
      per-environment join resolves it to a real URL per profile.
    * THE TWO ROWS, and this claim used to read "THE MERGE". The module serves that
      QName and also calls it, and the two used to fold into one `direction: both` row
      carrying `peer: ${soap.billing.uri}` — the module's own served operation and a call
      to the BILLING service, published as one endpoint. They compose the same QName from
      the same payload TYPE, which is not identity, and the merge could not tell because
      `peer` is not part of endpoint identity (RC-5). Since W27 (F5 §6.1) both rows stand,
      each keeping its own handler-or-caller, contract and `catalog_id`, and
      `resolve/self_exchange.py` files the question a reader answers.
    * `jakarta-jws-client.yml` derives nothing FROM THIS MODULE'S OWN CODE,
      which is what `declared_on` is for: every `@WebService` written in this
      fixture is a CLASS, so the stub catalog claims none of them and no
      served operation is republished as one the module calls. Since Task 6
      it does derive one row — from the `@WebService` INTERFACE inside
      `com.example:orders-soap-client`, which is the shape the word exists to
      claim — and the assertion below is keyed on the deriving coordinate for
      exactly that reason: "the stub catalog is inert" was only ever a claim
      about local declarations.
    """
    compile_fixture(FIXTURE)
    runner = CliRunner()
    result = runner.invoke(cli, ["module", "analyze", str(FIXTURE), "--workspace", str(tmp_path)])
    assert result.exit_code == 0, result.output

    # "Selected and derived nothing" is a different claim from "never
    # selected", and only this distinguishes them: a catalog whose `requires`
    # were unmet would be reported here by name, and the assertion below would
    # then be proving nothing about `declared_on`. Asserted EXACTLY, not
    # emptily, since 2O Task 9: this fixture's build declares no Spring
    # Integration, so the dependency gate skips that catalog by name — which
    # is the gate working and leaves every claim below unaffected.
    #
    # `spring-rsocket` joins it in F2 §3.6, for the same reason one framework
    # over: this fixture's POM declares `spring-websocket` and no RSocket
    # library, so the catalog that would publish its `@MessageMapping` methods on
    # `rsocket` is skipped and the one that publishes them on `websocket` runs.
    # Before W16 neither was gated on anything that could tell them apart — the
    # annotation belongs to both frameworks, and Spring's own handlers scan for
    # it with the same predicate — so these rows were `websocket` on no evidence.
    metadata = json.loads((tmp_path / "metadata.json").read_text())
    assert [entry["catalog_id"] for entry in metadata["skipped_catalogs"]] == [
        "spring-rsocket",
        "spring-integration",
    ]

    workspace = DuckDbWorkspace(tmp_path / "workspace.duckdb")
    try:
        soap = [row for row in workspace.query("endpoints") if row["protocol"] == "soap"]
        peers = [
            (str(row["environment"]), row["resolved_peer"], row["unresolved_reason"])
            for row in workspace.query("resolved_peers")
            if row["protocol"] == "soap"
        ]
    finally:
        workspace.close()

    # The stub catalog is loaded and selected (the fixture depends on both
    # `jakarta.jws` spellings) and claims interfaces only — so its every row
    # comes from the extracted library, and none from the `@WebService`
    # CLASSES this module writes. Keyed on the caller's coordinate, which is
    # the only thing that tells the two apart in this table.
    stubbed = [row for row in soap if row["catalog_id"] == "jakarta-jws-client"]
    assert [row["path"] for row in stubbed] == ["{http://billing.example.com/ws}stubCharge"]
    assert all("com.example/orders-soap-client" in str(row["caller"]) for row in stubbed)
    # TWO soap rows written in this module carry a caller, and until W27's review there
    # was one. `BillingSoapClient` calls `marshalSendAndReceive` twice — `place()` on the
    # template's default URI, `placeAt()` on a literal `http://billing.example.com/ws/
    # direct` — same payload QName, DIFFERENT HOSTS. The outbound dedup keyed on wire
    # identity without `caller` or `peer`, so `placeAt` was dropped outright: a call to
    # another host, gone from the bundle with nothing saying so. F5 §6.1 rule 1 is one row
    # per (caller, target), and `peer` is what makes the target of an outbound row.
    called = [
        row
        for row in soap
        if row["caller"] is not None and "com.acme/orders-service" in str(row["caller"])
    ]
    assert len(called) == 2
    assert sorted(str(row["peer"]) for row in called) == [
        "${soap.billing.uri}",
        "http://billing.example.com/ws/direct",
    ]
    [place] = [row for row in called if row["peer"] == "${soap.billing.uri}"]
    assert place["path"] == "{http://orders.example.com/ws}placeOrderRequest"
    assert place["direction"] == "outbound"
    assert place["method"] is None
    assert place["resolution"] == "resolved"
    assert str(place["caller"]).endswith(
        "com/example/orders/soap/BillingSoapClient#place(sig_b5d0d855)."
    )
    assert place["handler"] is None
    # The served operation is its own row, and the two are asked about rather than
    # joined (W27, F5 §6.1).
    [served] = [
        row
        for row in soap
        if row["path"] == "{http://orders.example.com/ws}placeOrderRequest"
        and row["direction"] == "inbound"
    ]
    assert str(served["handler"]).endswith(
        "com/example/orders/soap/OrderSoapEndpoint#placeOrder(sig_fd19bfc7)."
    )
    # `peer` is the expression whole, never split: `${soap.billing.uri}` has
    # no authority half to take.
    assert place["peer"] == "${soap.billing.uri}"
    # ... and it resolves per environment, both profiles, no gap.
    #
    # The library's `stubCharge` row rides along in each environment with a
    # NULL peer and NO `unresolved_reason`, and that pair is the honest
    # reading rather than a gap: `@WebService` names no address at all
    # (`jakarta-jws-client.yml` says so in as many words), so there is no
    # expression for the join to substitute — which is a different thing from
    # an expression it substituted nothing into. It sorts first on `path`.
    # `placeAt`'s literal peer rides along in BOTH environments unchanged, which is what
    # a literal means: there is no expression for the join to substitute. It was invisible
    # here until W27's review, dropped as a duplicate of `place` on wire identity alone.
    #
    # It sorts AFTER the resolved one though its value sorts before — `resolved_peers`
    # orders on the raw `peer` column, where `${soap.billing.uri}` beats
    # `http://billing.example.com/ws/direct` on the leading `$`. Written out rather than
    # sorted here, because the ordering is the query's promise (NFR-1) and a test that
    # re-sorted would stop checking it.
    assert peers == [
        ("default", None, None),
        ("default", "http://billing.internal.example.com/ws", None),
        ("default", "http://billing.example.com/ws/direct", None),
        ("prod", None, None),
        ("prod", "http://billing.prod.internal.example.com/ws", None),
        ("prod", "http://billing.example.com/ws/direct", None),
    ]


def test_a_wsdl_schema_first_operation_reaches_the_rendered_document(full_run: Path):
    """The same row at the document a reader actually sees — 2I's mirror of
    `test_a_schema_first_operation_reaches_the_rendered_document` above.
    `none recorded` rather than `unresolved`: the schema addressed this
    operation outright and names no code, an absence rather than a failed
    read. The request table is the schema's own fields, by its schema name;
    there is no Response section at all, because no stamp reaches this row.

    The identity itself renders `soap {ns}quoteOrderRequest`, no
    `(unresolved)` marker — fix round 1's own ruling (spec §1): SOAP is
    verbless, the same D02 §2/2D messaging shape as a Kafka topic, so its rows
    belong in `document.py`'s VERBLESS set, not the verbed one. They sat in
    the verbed half since 2H (when no catalog owned the protocol, so the
    misclassification rendered nothing live) through 2I Task 2's own rows,
    which is what let this row's first live pin carry the wrong,
    `(unresolved)`-prefixed form until this fix."""
    _run(full_run)  # analyze + render + export
    document = (full_run / "render" / "architecture.md").read_text()

    assert (
        "| `soap {http://orders.example.com/ws}quoteOrderRequest` | "
        "none recorded | — → — | xml | resolved |"
    ) in document
    # 2M design §5c: a NAMED shape's table is emitted once, under
    # `### Shapes`, and the endpoint's own entry names it instead of
    # repeating it — the boundary this docstring describes (no Response
    # section) is visible in the per-endpoint reference below, not in a
    # nested table any more. The header carries the wire identity too (fix
    # round 1, MEDIUM 1) — one convention regardless of direction.
    #
    # `_shape_display_name` (fix round 1, LOW) reads a QName shape id — this
    # WSDL element's own `{uri}local` wire identity — by its own grammar
    # (whatever follows the LAST `}`), not `simple_name`'s slash-splitting
    # convention (still used, unchanged, by the class diagram's own node
    # names, which is why `## Structure` still draws this same shape as
    # `ws}quoteOrderRequest` — out of this task's scope, a background task
    # owns that fix). The `### Shapes` subsection and this citation both
    # read the honest `quoteOrderRequest` instead.
    identity = "- `soap {http://orders.example.com/ws}quoteOrderRequest` — none recorded"
    assert f"{identity}\n  - Request: quoteOrderRequest" in document
    assert (
        "- `quoteOrderRequest`\n"
        "  - Fields:\n"
        "\n"
        "    | Field | Type | Required | Nullable |\n"
        "    |---|---|---|---|\n"
        "    | sku | string | yes | no |\n"
        "    | count | integer (int32) | yes | no |\n"
        "    | status | enum | yes | no |\n"
        "    | cancelledAt | string (date-time) | yes | yes |\n"
    ) in document
    # No Response reference at all: 2I Task 3 marks INPUT elements only, so
    # nothing coalesces a response here.
    assert (
        "- Response:" not in document.split(f"{identity}\n  - Request:", 1)[1].split("\n\n", 1)[0]
    )
    # 2I Task 5: the merged row appears in BOTH sections, and the outbound
    # one carries the configuration expression as its peer — the address a
    # reader needs, verbless like every other soap row. The Caller column is
    # untouched by 2M §5c (only the inbound Handler column shortens) so it
    # still carries the full symbol.
    assert (
        "| `soap {http://orders.example.com/ws}placeOrderRequest` | ${soap.billing.uri} | "
        "`com/example/orders/soap/BillingSoapClient#place(sig_b5d0d855).` | xml | resolved |"
    ) in document
    assert (
        "| `soap {http://orders.example.com/ws}placeOrderRequest` | "
        "`OrderSoapEndpoint#placeOrder` | "
    ) in document


def test_format_field_number_and_open_questions_reach_the_rendered_document(full_run: Path):
    """2G Task 8, live and whole: the format ladder's three tiers each reach
    the document's Format column beside Media, the two refused parse-binding
    rows reach the "Open questions" section with their candidates, and a
    declared-shape field's `field_number` rides beside its name — the same
    invariant `test_a_bound_parse_reaches_the_format_ladders_payload_rung_in_a_full_analyze`
    pins at the workspace level, pinned here at the document a reader
    actually sees."""
    _run(full_run)  # analyze + render + export
    document = (full_run / "render" / "architecture.md").read_text()

    # Rung 2 (declared media, `resolved`) — plain, no hedge. Human-spelled in
    # the table now (2M design §5c); the full symbol lives in the endpoint's
    # own detail block below (pinned via the `sig_...` open-question line
    # further down, which quotes the same handler whole).
    assert (
        "| `POST /v1/orders/proto-orders` | `OrderController#createProtoOrder` | "
        "— → application/json | json | resolved |"
    ) in document
    # Rung 3 (serializer config, `resolved`) — plain, no hedge.
    assert (
        "| `kafka composed-orders` | `ComposedListener#onComposedEvent` | "
        "— → — | protobuf | resolved |"
    ) in document
    # Rung 4 (payload hierarchy, `narrowed`) — one of the three rows the
    # parse-binding pass bound: an assumed format must never look observed
    # (2G design §5's first rule), so it carries `(assumed)`.
    assert (
        "| `jms parsed-audit-queue` | `ParsedPayloadListeners#onDelegated` | "
        "— → — | protobuf (assumed) | resolved |"
    ) in document
    # Rung 6 (nothing) — one of the two rows the same pass refused: the
    # endpoint itself derived cleanly (`resolved`), but nothing describes
    # what is on its wire.
    assert (
        "| `jms parsed-relay-queue` | `ParsedPayloadListeners#onRelayed` | "
        "— → — | unresolved | resolved |"
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
    metadata = json.loads((full_run / "metadata.json").read_text())
    assert metadata["schema_sources_not_compiled"] == []
    assert metadata["descriptors_not_interpreted"] == []

    # `open_questions` joined the D06 bundle and its manifest (2G design §8).
    runner = CliRunner()
    result = runner.invoke(cli, ["module", "export", str(FIXTURE), "--workspace", str(full_run)])
    assert result.exit_code == 0, result.output
    bundle = Path(result.output.strip())
    manifest = json.loads((bundle / "manifest.json").read_text())
    assert "open_questions" in manifest["contents"]["tables"]
    # Two `payload_binding` questions and, since W27 (F5 §6.1), six `self_exchange` ones
    # — the identities this module both serves and calls, which used to be merged into a
    # single row that asked nothing.
    rows = duckdb.sql(
        "SELECT question, count(*) FROM read_parquet("
        f"'{bundle / 'graph' / 'open_questions.parquet'}') GROUP BY 1 ORDER BY 1"
    ).fetchall()
    assert rows == [("payload_binding", 2), ("self_exchange", 6)]


def test_a_library_operation_reaches_the_document_and_leaves_with_the_config(tmp_path: Path):
    _run(tmp_path)
    """2I Task 6, end to end through the real commands — and the only test in
    this suite whose evidence comes from a jar.

    `com.example:orders-soap-client` ships ONE `@WebService` interface, in no
    source file of this module. With `.sextant.yml` naming it, the extractor
    reads the archive, `jakarta-jws-client.yml` derives the operation it
    declares, and the rendered document says which library it came from. With
    the file moved away, the same commands on the same compiled module derive
    nothing of the sort — which is the whole assertion: the row exists BECAUSE
    of the opt-in, not because the dependency is on the classpath.

    Both halves run into ONE workspace, and the module is NOT recompiled
    between them. Both are deliberate, and the workspace is the load-bearing
    one: a fact file is written whole, so a library that is no longer scanned
    OVERWRITES NOTHING, and a second run into a fresh directory would prove
    only that a fresh directory is empty. Re-analyzing the same workspace is
    what shows that opting out actually RETRACTS — the property a reader needs
    if the opt-in is to be a decision they can reverse.
    """
    document = (tmp_path / "render" / "architecture.md").read_text()

    # The row itself: verbless, address-less peer, and its caller a symbol
    # whose identity carries the LIBRARY's coordinates rather than this
    # module's — the operation `wsimport` would have generated a stub for.
    assert "| `soap {http://billing.example.com/ws}stubCharge` | unresolved |" in document
    assert "`com/example/billing/BillingPort#charge(sig_7b622a99).`" in document
    # And the attribution, which is what tells a reader that no file in this
    # repository declares the operation above.
    assert "- `soap {http://billing.example.com/ws}stubCharge`" in document
    assert "  - Via: `com.example:orders-soap-client`" in document
    assert (tmp_path / "facts" / "lib" / "com.example" / "orders-soap-client").is_dir()

    # The document record carries the coordinate into the EXPORTED table too,
    # not only into the rendered page: opting a library in is the reader's own
    # assertion, and an assertion invisible in the published bundle is exactly
    # where it would be laundered into module-observed evidence.
    bundle = Path(
        CliRunner()
        .invoke(cli, ["module", "export", str(FIXTURE), "--workspace", str(tmp_path)])
        .output.strip()
    )
    origins = duckdb.sql(
        "SELECT origin, count(*) FROM read_parquet("
        f"'{bundle / 'graph' / 'documents.parquet'}') GROUP BY origin ORDER BY origin"
    ).fetchall()
    assert (COORDINATE, 1) in origins
    # 105 + 2: 2O Task 3's generic-superinterface fixture (`Repository<T, ID>`,
    # `OrderRepository`) — module-output documents, same reason `test_app.py`'s
    # count moved.
    # + 1: 2O Task 6's `module` fact document (D00 §5), the detector's own
    # conclusions travelling as facts; it carries no `origin`, like every other
    # document this module produced itself. + 2: the same task's Data REST
    # repositories (`CatalogRepository`, `SecretRepository`).
    # + 7: 2Q `G3`'s dispatch fixture (`com/acme/orders/trace/`) — `Refiner`,
    # `SoleRefiner`, `StrictRefiner`, `Splitter`, `FirstSplitter`,
    # `SecondSplitter`, `TraceProbe`, one class file and one document each.
    # Annotated by nothing and referenced by nothing, so they move this count
    # and no other row in this test.
    # + 2: OI-48's `com/acme/orders/springscoped/` — `SpringScopedDetail` and its
    # `package-info`, a package declaring itself non-null in SPRING's spelling.
    # + 3: that entry's own review — `apiscoped/package-info` declaring
    # `@NonNullApi` ALONE (which scopes parameters and returns, never fields) plus
    # its `ApiScopedDetail`, and `springscoped/nested/NestedScopedDetail`, a
    # SUBpackage of a scoped package, which inherits no scope from its parent.
    # Both fields must come out nullable, and both were coming out not-null.
    # + 3: W21's `com/acme/orders/model/` — `BaseEntity`, `Customer` and
    # `CustomerRegistry`, which give the always-on corpus the superclass-call shape it
    # scored ZERO of. `spring-petclinic-rest` makes 96 such calls and this fixture made
    # none, so the suite could pass while Wave 3's resolution work had nowhere to fail.
    # + 2: W26's `contracts/OrderTotals` and `PayloadShapeController` — a payload type
    # with no fields at all, and the controller that returns it beside three paged
    # responses whose envelope nothing here can expand.
    # + 1: W28's `RoutingConditionsController`.
    # + 1: W43's `ws/OrderStompPublisher` — the outbound half of the STOMP surface.
    # + 2: W44's `mvcroutes/` pair — Spring MVC functional routing.
    # + 1: W45's `ws/StompBrokerConfig` — the URL a STOMP client opens.
    # + 1: W46's `ws/OrderFeedClient` — the client direction, which opens one.
    # 136 since 2026-09-11: `ws/ProgrammaticWsConfig` and its nested `TicketEndpoint`,
    # the fixture for the programmatic WebSocket registration (`G-34`).
    # 138: + `ShipmentRepository` and its nested `Shipment` (`G-45`).
    assert (None, 138) in origins

    # This test MUTATES the fixture — it moves `.sextant.yml` aside and re-runs — so it
    # cannot use the shared run and must not leave the shared fixture altered for whatever
    # runs next. Its own workspace, and the rename undone in `finally`.
    config = FIXTURE / ".sextant.yml"
    moved = tmp_path / "sextant.yml.moved"
    config.rename(moved)
    try:
        _run(tmp_path)
    finally:
        moved.rename(config)
    plain = (tmp_path / "render" / "architecture.md").read_text()
    assert "stubCharge" not in plain
    assert "Via:" not in plain
    # The library's whole fact subtree is discarded before the scan, so nothing
    # is left for the resolve to read back as if it were still configured.
    assert not (tmp_path / "facts" / "lib").exists()


def test_the_planted_credentials_leave_masked_and_stay_verbatim_in_the_workspace(tmp_path: Path):
    """2K design §1, live and end to end: the exposure this phase closes is
    `resolved_config` values EXPORTING verbatim. The fixture plants two fake
    credentials — one a built-in key pattern reaches, one only its own
    `.sextant.yml` addition reaches — and one address (`soap.billing.uri`) no
    rule names, which must survive untouched. The workspace keeps all three as
    written, because resolution and peer substitution read the real values and
    the analyst's own disk is not the trust boundary."""
    compile_fixture(FIXTURE)
    _run(tmp_path)
    bundle = next((tmp_path / "bundles").iterdir())
    exported = dict(
        duckdb.sql(
            "SELECT key, value FROM read_parquet("
            f"'{bundle / 'graph' / 'resolved_config.parquet'}') WHERE environment = 'default'"
        ).fetchall()
    )
    assert exported["orders.db.password"] == REDACTED
    assert exported["orders.internal.dsn"] == REDACTED
    assert exported["soap.billing.uri"] == "http://billing.internal.example.com/ws"

    workspace = DuckDbWorkspace(tmp_path / "workspace.duckdb")
    in_workspace = {
        str(row["key"]): row["value"]
        for row in workspace.query("resolved_config")
        if row["environment"] == "default"
    }
    workspace.close()
    assert in_workspace["orders.db.password"] == "hunter2-fixture"
    assert "hunter2-fixture" in str(in_workspace["orders.internal.dsn"])

    # The rendered document names the expression a row carries and the KEYS
    # pass 2 could not resolve — never a resolved value — so no planted
    # credential reaches it at all. Pinned rather than assumed: the day a
    # config-value line is added, this fails and the redactor is wired into it.
    document = (tmp_path / "render" / "architecture.md").read_text()
    assert "hunter2-fixture" not in document

    # And the bundle's FACT files, which carry the same values one derivation
    # earlier (D00 §5c). Everything that leaves is masked: a masked
    # `resolved_config.parquet` beside a `facts/` holding the plaintext would
    # mask nothing. Read back through the parquet rather than grepped — zstd
    # would hide the string from a byte search either way.
    fact_values = set(
        duckdb.sql(
            "SELECT payload ->> 'key_path', payload ->> 'value' FROM read_parquet("
            f"'{bundle / 'facts' / '*.parquet'}') WHERE kind = 'config_entry'"
        ).fetchall()
    )
    assert ("orders.db.password", REDACTED) in fact_values
    assert ("orders.internal.dsn", REDACTED) in fact_values
    # Two facts, one per profile file — a key declared twice is two entries,
    # so this is a set of pairs rather than a dict keyed on the key alone.
    assert ("soap.billing.uri", "http://billing.internal.example.com/ws") in fact_values
    assert ("soap.billing.uri", "http://billing.prod.internal.example.com/ws") in fact_values
    leaked = duckdb.sql(
        "SELECT count(*) FROM read_parquet("
        f"'{bundle / 'facts' / '*.parquet'}') WHERE payload::VARCHAR LIKE '%hunter2-fixture%'"
    ).fetchone()
    assert leaked == (0,)

    # The workspace's own fact rows are untouched, which is why a document's
    # `redaction_set_hash` still reads `sha256:none`: it describes READ time,
    # and nothing was applied then. The manifest's hash names the set that
    # masked this bundle — two hashes, two moments (D06 §3).
    local = (tmp_path / "facts").rglob("*.jsonl")
    assert any("hunter2-fixture" in path.read_text(encoding="utf-8") for path in local)


def test_the_manifest_names_the_rule_set_that_masked_the_bundle(full_run: Path):
    """D06 §3 reserved `redaction_set_hash` and left it unwritten while nothing
    redacted. It has a producer now, and what it names is the EFFECTIVE set —
    the built-ins widened by this module's `redact:` — so a bundle masked under
    one set is distinguishable from a bundle masked under another. The fixture
    adds a rule, so its hash must differ from the built-in-only one; editing
    that section changes the hash, and re-running without editing it does not
    (the byte-identity test above covers the second half)."""
    bundle = next((full_run / "bundles").iterdir())
    manifest = json.loads((bundle / "manifest.json").read_text())
    effective = Redactor.from_rules(read_redaction_rules(FIXTURE)).rule_set_hash
    assert manifest["producer"]["redaction_set_hash"] == effective
    assert effective != Redactor.from_rules().rule_set_hash


def test_the_planted_decoy_config_file_never_reaches_resolved_config(full_run: Path):
    """2K design §2, live: the fixture's `.sextantignore` names
    `src/main/resources/application-secret.yml` — an ordinary, valid Spring
    config source (`application{-profile}.yml` names it the "secret"
    profile, exactly like `application-prod.yml`) that would otherwise
    resolve its own key into its own environment. Ignoring it means the
    file never reaches `YamlConfigReader` at all: not merely unresolved or
    masked, its key and its whole profile are simply never there."""

    workspace = DuckDbWorkspace(full_run / "workspace.duckdb")
    rows = workspace.query("resolved_config")
    keys = {str(row["key"]) for row in rows}
    environments = {str(row["environment"]) for row in rows}
    workspace.close()
    assert "decoy.should-never-resolve" not in keys
    assert "secret" not in environments


def test_a_planted_dotenv_is_excluded_by_the_builtin_layer_alone(tmp_path: Path):
    """The fixture's `.sextantignore` names no `.env` pattern anywhere in
    it — `BUILTIN_PATTERNS` is what excludes the planted `.env` at the
    fixture root, proven against the real fixture root, which DOES carry a
    `.sextantignore` of its own (so this also proves the built-in layer
    keeps applying alongside a repo file that never mentions it)."""
    assert (FIXTURE / ".env").is_file()
    ignorefile_patterns = [
        line.strip()
        for line in (FIXTURE / ".sextantignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    assert not any(".env" in pattern for pattern in ignorefile_patterns)
    assert IgnoreRules.load(FIXTURE).matches(FIXTURE / ".env") is True


# --- 2K Task 3: the golden overlay, live ----------------------------------


def test_every_claim_in_the_golden_overlay_is_grounded_in_the_live_workspace(full_run: Path):
    """The fixture overlay is hand-authored (fixture JSON is fine — it is a
    program format, 2K design §9), which is exactly why it has to be checked
    against a REAL analysis rather than a hand-built one: a golden file whose
    symbols, files and question drifted out of the fixture would still parse,
    still render, and pin nothing. Every one of the four claim kinds validates
    against the workspace `analyze` just produced, or this fails.

    2K Task 7 ruling 2: `produced_by` is genuine, not the placeholder
    `sha256:0000...` this file carried through Task 3 — regenerated through
    the real `--ingest` door against this same fixture, `--agent
    fixture-agent --model fixture-model` to keep both pinned above
    (`test_the_golden_overlay_assembles_into_the_rendered_document`).
    `instructions_hash`/`workspace_fingerprint` are the real sha256 of
    `enrich/INSTRUCTIONS.md`/`metadata.json` from that run; `run_at` is
    wall-clock at ingest time and is hand-pinned to a fixed value afterward —
    informational only, never compared, the same way every other field here
    is checked by what it grounds rather than by its own bytes."""
    overlay = load_overlay(FIXTURE)
    assert overlay is not None
    assert {claim.kind for claim in overlay.claims} == {
        "component",
        "diagram",
        "section",
        "verdict",
    }

    workspace = DuckDbWorkspace(full_run / "workspace.duckdb")
    try:
        accepted, refusals = validate_overlay(overlay, workspace, FIXTURE)
    finally:
        workspace.close()
    assert refusals == ()
    assert len(accepted) == len(overlay.claims)


def test_the_golden_overlays_instructions_hash_matches_the_shipped_instructions_file():
    """2K Task 7 fix round 1, Important I2: pin genuine provenance to the
    LIVE file rather than merely "some sha256-shaped string" — the next
    edit to `enrich/INSTRUCTIONS.md` must fail this test loudly (a stale
    golden overlay silently misreporting what produced it) rather than
    pass by coincidence. No `analyze`/`render` needed: the overlay is
    already checked into the fixture."""
    overlay = load_overlay(FIXTURE)
    assert overlay is not None
    digest = hashlib.sha256(instructions_path().read_bytes()).hexdigest()
    assert overlay.produced_by.instructions_hash == f"sha256:{digest}"


def test_instructions_teach_cite_paths_are_module_root_relative():
    """2N Task 3 (flight-1 ambiguity 1): a `section` claim's `cites` names a
    path in the same spelling `find`/`grep` printed it in — module-root-
    relative — never an absolute path or a different root. A substring pin,
    not the full sentence: wording can breathe, but this teaching may not
    quietly vanish from the shipped prompt the way it was absent before
    flight-1."""
    text = instructions_path().read_text(encoding="utf-8")
    assert "That path is module-root-relative" in text


def test_instructions_teach_members_use_the_short_pkg_class_form():
    """2N Task 3 (flight-1 ambiguity 2): a `component` claim's `members`
    are written in the short `pkg/Class#` form the example already shows,
    never a fully qualified dotted name."""
    text = instructions_path().read_text(encoding="utf-8")
    assert "Write each one in the short `pkg/Class#` form" in text


def test_instructions_teach_a_how_to_sections_anchor_rule():
    """2N Task 3 (flight-1 ambiguity 3): a how-to `section` (an extension
    guide) anchors `after-endpoint-table` when it concerns the module's
    endpoints, and `end-of-document` otherwise — closing the ambiguity
    between those two anchors for exactly the claim shape most likely to
    straddle them."""
    text = instructions_path().read_text(encoding="utf-8")
    assert "A how-to `section` — a guide for extending or adding to something — anchors" in text


def test_instructions_teach_the_config_verdict_shape_both_forms():
    """2N Task 3: the config-shaped `verdict` (2N design §2) gets its own
    worked example beside the endpoint one, answered and `unanswered`, plus
    the sentence distinguishing the two identity shapes and stating that a
    verdict's `question` is copied from the brief's printed rows while
    `cites`/`members` come from the tools instead."""
    text = instructions_path().read_text(encoding="utf-8")
    assert "endpoint shape (`protocol`, `method`, `path`, `kind`) or the config shape" in text
    assert '"key": "spring.config.import"' in text
    assert '"environment": "docker"' in text
    assert (
        '"assessment": "unanswered"'
        in text.split("A `question` can also identify an unresolved configuration row")[1]
    )


def test_the_golden_overlay_assembles_into_the_rendered_document(full_run: Path):
    """Add-only assembly, end to end (2K design §6): every claim reaches the
    document under a provenance header, at its own anchor, and the machine
    rows the rest of this suite pins are still exactly where they were —
    `test_format_field_number_and_open_questions_reach_the_rendered_document`
    asserts those same lines against this same document."""
    document = (full_run / "render" / "architecture.md").read_text()

    header = "**Enrichment — evidence: llm** (model fixture-model, agent fixture-agent)"
    assert document.count(header) == 3  # two anchors plus the verdict's own question
    assert "**Component: Legacy billing edge**" in document
    assert "Members: `com/example/orders/soap/OrderSoapEndpoint#`" in document
    assert "**Extending the legacy billing edge**" in document
    assert "Cites: `src/main/java/com/example/orders/soap/OrderSoapEndpoint.java`" in document
    assert "Elides: showing 3 of the module's types" in document

    # The verdict renders directly under the question it answers — the row
    # itself stays `unresolved`, because the graph is immutable (design §7).
    question = "- `jms parsed-relay-queue` — payload_binding:"
    verdict = "**LLM assessment** for `jms parsed-relay-queue` (payload_binding): likely"
    assert document.index(question) < document.index(verdict)
    assert document.index(verdict) < document.index(
        "- `sqs parsed-mixed-inbound` — payload_binding:"
    )

    # Nothing is stale: every referent of every claim exists in the workspace
    # this render read, so the notice is absent rather than reporting zero.
    assert "stale, not shown" not in document

    # Add-only, live: the machine rows this suite has always pinned are still
    # exactly where they were. Every other test in this module asserts against
    # this same enriched document — the overlay adds beside them and edits
    # none of them, which is what makes those pins the regression guard.
    assert "## Known gaps" in document
    assert (
        "| `jms parsed-relay-queue` | `ParsedPayloadListeners#onRelayed` | "
        "— → — | unresolved | resolved |"
    ) in document
