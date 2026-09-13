"""W19 — the per-catalog enumeration pass (F2 §3.8).

§3.8 ships six catalogs with a DECLARED SLICE, and says the cost is real and is part
of the work: *"you cannot write a slice without enumerating the framework's
surface."* This is that enumeration, for every catalog whose slice is a question
about METHODS ON AN OWNER TYPE — which is five of the six gaps (the sixth,
`netflix-dgs`, is a question about one annotation's `@Inherited` meta-annotation and
is answered in its own catalog).

The question, per catalog: **of the methods this framework declares on the owner
this catalog names, how many does the catalog read?** Both halves come from the
run — the framework's surface out of the jar's own bytecode, the catalog's coverage
out of the catalog as LOADED — so "reads 4 of 19" is a measurement rather than a
count someone maintained by hand and stopped maintaining.

**Why a shipped slice needs this and not a paragraph.** A catalog with no slice
claims its framework entire; a catalog with a slice written from memory claims
whatever its author last looked at. Both read the same to a consumer. The output
here is what a slice can cite, and `tests/architecture/test_catalog_slice_coverage.py`
is what stops the two drifting: a method the framework declares and the catalog does
not read must be named in the catalog's `slice.outside`, or the audit fails.

**What is deliberately NOT concluded here.** An unread method is not automatically a
gap — `JmsTemplate` declares plenty that name no destination, and a slice's job is to
say which absences are deliberate. This probe prints the surface and the coverage; it
does not decide which side of the line a method belongs on.
"""

from __future__ import annotations

import re
import subprocess
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "src"))

from sextant.application.ports.catalogs import Catalog
from sextant.ingress.catalogs.yaml_source import YamlCatalogSource

M2 = Path.home() / ".m2" / "repository"
CATALOGS = REPO / "src" / "sextant" / "catalogs"

# One `javap -s` signature line. The trailing `(?:\s+throws\s+[\w.,$ ]+)?` is not
# optional decoration: EVERY `JmsTemplate` method declares `throws JmsException`,
# and a pattern without it matched none of them — the probe printed "reads 0 of 27"
# for a catalog that reads `convertAndSend`, because the method it reads had been
# dropped from the denominator too. A filter that silently shrinks both sides of a
# ratio is the worst shape this probe could have, so `_members` below aborts on any
# `public` line this does not match rather than skipping it.
_SIGNATURE = re.compile(
    r"^\s+public\s+(?:(?:static|final|abstract|synchronized|native|default)\s+)*"
    r"(?:<[^>]+>\s+)?(.+?)\s+([\w$]+)\((.*)\)(?:\s+throws\s+[\w.,$ ]+)?;\s*$"
)
# A constructor, which `javap` prints with the declaring type's own name and NO
# return type — `public org.springframework.jms.core.JmsTemplate();`. Recognised
# rather than filtered by the `<init>` name in `_NOT_SURFACE`, because that name
# appears only on the `descriptor:` line below and the signature line above it would
# otherwise trip the unparsed-member abort.
_CONSTRUCTOR = re.compile(r"^\s+public\s+[\w.$]+\((.*)\)(?:\s+throws\s+[\w.,$ ]+)?;\s*$")
# A method whose single parameter is a request OBJECT — the AWS SDK's addressing
# style, where the queue URL lives inside the request rather than in an argument.
_REQUEST_OBJECT = re.compile(r"^\(L[\w/$]*Request;\)")
# A method that DECLARES A ROUTE by taking a predicate, or attaches one by taking a
# whole router function — WebFlux's functional style, where the address lives in the
# predicate object rather than in a string. Neither of the two tests above sees it,
# and `RouterFunctions$Builder.route`, `.nest`, `.add` and `.resource` all take this
# shape: four route-declaring methods that would have sat outside the slice AND
# outside the enumeration, which is the one place a reader could not find them.
_ROUTE_DECLARING = re.compile(r"^\((?:L[\w/$]*(?:RequestPredicate|RouterFunction);)")
# A `public` member line that is neither a method signature nor a field.
_PUBLIC = re.compile(r"^\s+public\s+")
_FIELD = re.compile(r"^\s+public\s+(?:(?:static|final)\s+)*[\w.$<>,\[\] ]+\s+\w+;\s*$")
_DESCRIPTOR = re.compile(r"^\s+descriptor:\s+(\S+)\s*$")


@dataclass(frozen=True)
class Surface:
    """One owner type a catalog names, and where its bytecode comes from."""

    catalog_id: str
    owner: str
    artifact: str
    version: str
    # The gap this owner's slice answers, for the write-up's own cross-reference.
    gap: str


# Every owner whose slice is a question about methods. Owners come from the
# catalogs themselves; artifacts and versions from each catalog's own `measured:`
# block, so this probe measures what the catalog already claims to have measured.
SURFACES = (
    Surface(
        "spring-jms-template",
        "org.springframework.jms.core.JmsTemplate",
        "org.springframework:spring-jms",
        "6.1.6",
        "G-44",
    ),
    Surface(
        "spring-jms-template",
        "org.springframework.jms.core.JmsOperations",
        "org.springframework:spring-jms",
        "6.1.6",
        "G-44",
    ),
    Surface(
        "spring-rabbit-template",
        "org.springframework.amqp.rabbit.core.RabbitTemplate",
        "org.springframework.amqp:spring-rabbit",
        "3.1.4",
        "G-44",
    ),
    Surface(
        "spring-rabbit-template",
        "org.springframework.amqp.core.AmqpTemplate",
        "org.springframework.amqp:spring-amqp",
        "3.1.4",
        "G-44",
    ),
    Surface(
        "spring-sqs-template",
        "io.awspring.cloud.sqs.operations.SqsTemplate",
        "io.awspring.cloud:spring-cloud-aws-sqs",
        "3.1.1",
        "G-44",
    ),
    Surface(
        "spring-sqs-template",
        "io.awspring.cloud.sqs.operations.SqsOperations",
        "io.awspring.cloud:spring-cloud-aws-sqs",
        "3.1.1",
        "G-44",
    ),
    # The receive half (A2 Task 2, `sqs-template-receive`): its own catalog because a
    # catalog has one direction, so its own enumeration — the same owner, and the four
    # unread names are the send half's, which the sibling file reads or names.
    Surface(
        "spring-sqs-template-receive",
        "io.awspring.cloud.sqs.operations.SqsTemplate",
        "io.awspring.cloud:spring-cloud-aws-sqs",
        "3.1.1",
        "G-44",
    ),
    Surface(
        "spring-pubsub",
        "com.google.cloud.spring.pubsub.core.PubSubTemplate",
        "com.google.cloud:spring-cloud-gcp-pubsub",
        "5.1.2",
        "G-44",
    ),
    # W43. The STOMP outbound half, enumerated for the same reason its siblings
    # are: a template class declares far more than a catalog reads, and "shipped"
    # must stop meaning "all of it".
    Surface(
        "spring-stomp-template",
        "org.springframework.messaging.simp.SimpMessagingTemplate",
        "org.springframework:spring-messaging",
        "6.1.6",
        "G-33",
    ),
    Surface(
        "spring-stomp-template",
        "org.springframework.messaging.simp.SimpMessageSendingOperations",
        "org.springframework:spring-messaging",
        "6.1.6",
        "G-33",
    ),
    # W44's servlet twin, enumerated for the same reason: the builder DSL is outside both
    # catalogs and a reader must be able to see how much.
    #
    # BOTH owners, and the reactive twin gains its own `RouterFunctions` row below for the
    # same reason. Only `RouterFunctions$Builder` was enumerated before, so the five
    # addressable methods `RouterFunctions` itself declares — `route()`, `resource`,
    # `resources`, `resourceLookupFunction`, `changeParser` — sat outside the slice AND
    # outside the enumeration, which is the one place a reader cannot find them.
    Surface(
        "spring-mvc-router",
        "org.springframework.web.servlet.function.RouterFunctions",
        "org.springframework:spring-webmvc",
        "6.1.6",
        "G-37",
    ),
    Surface(
        "spring-mvc-router",
        "org.springframework.web.servlet.function.RouterFunctions$Builder",
        "org.springframework:spring-webmvc",
        "6.1.6",
        "G-37",
    ),
    Surface(
        "spring-webflux-router",
        "org.springframework.web.reactive.function.server.RouterFunctions",
        "org.springframework:spring-webflux",
        "6.1.6",
        "G-37",
    ),
    # The KOTLIN halves, added in W44's review. Both catalogs read the DSL type and its
    # file facade, and neither was enumerated — so the three-argument verb overload and
    # `plus` sat outside the slice AND outside the enumeration.
    Surface(
        "spring-mvc-router",
        "org.springframework.web.servlet.function.RouterFunctionDsl",
        "org.springframework:spring-webmvc",
        "6.1.6",
        "G-37",
    ),
    Surface(
        "spring-mvc-router",
        "org.springframework.web.servlet.function.RouterFunctionDslKt",
        "org.springframework:spring-webmvc",
        "6.1.6",
        "G-37",
    ),
    Surface(
        "spring-webflux-router",
        "org.springframework.web.reactive.function.server.CoRouterFunctionDsl",
        "org.springframework:spring-webflux",
        "6.1.6",
        "G-37",
    ),
    Surface(
        "spring-webflux-router",
        "org.springframework.web.reactive.function.server.CoRouterFunctionDslKt",
        "org.springframework:spring-webflux",
        "6.1.6",
        "G-37",
    ),
    # The reactive NON-coroutine pair (`GAP-1b`, A1 Task 5): the catalog reads
    # `RouterFunctionDsl` and its `router` facade since that task, and an owner a catalog
    # reads and this probe does not enumerate is the one place a reader cannot find its
    # gaps — the same omission the Kotlin halves above closed.
    Surface(
        "spring-webflux-router",
        "org.springframework.web.reactive.function.server.RouterFunctionDsl",
        "org.springframework:spring-webflux",
        "6.1.6",
        "G-37",
    ),
    Surface(
        "spring-webflux-router",
        "org.springframework.web.reactive.function.server.RouterFunctionDslKt",
        "org.springframework:spring-webflux",
        "6.1.6",
        "G-37",
    ),
    Surface(
        "spring-webflux-router",
        "org.springframework.web.reactive.function.server.RouterFunctions$Builder",
        "org.springframework:spring-webflux",
        "6.1.6",
        "G-37",
    ),
    Surface(
        "aws-sqs-sdk",
        "software.amazon.awssdk.services.sqs.SqsClient",
        "software.amazon.awssdk:sqs",
        "2.25.31",
        "G-43",
    ),
    Surface(
        "aws-sqs-sdk",
        "software.amazon.awssdk.services.sqs.SqsAsyncClient",
        "software.amazon.awssdk:sqs",
        "2.25.31",
        "G-43",
    ),
    # `G-31` (w60). Split into three catalogs, one scalar owner each
    # (`kafka-streams.yml`'s own header comment carries the full rationale).
    # `KTable` is NOT enumerated: it names no method in any of the three
    # `matches.methods` lists at all — `KStream.to()`, not `KTable`, is the call
    # site `customers.toStream().to(...)` reaches — so it is not in any of the
    # three `matches.owner` either, and a slice measures a claimed surface, not
    # an owner mentioned in passing.
    Surface(
        "kafka-streams",
        "org.apache.kafka.streams.StreamsBuilder",
        "org.apache.kafka:kafka-streams",
        "3.6.2",
        "G-31",
    ),
    Surface(
        "kafka-streams-sink",
        "org.apache.kafka.streams.kstream.KStream",
        "org.apache.kafka:kafka-streams",
        "3.6.2",
        "G-31",
    ),
    Surface(
        "kafka-streams-topology",
        "org.apache.kafka.streams.Topology",
        "org.apache.kafka:kafka-streams",
        "3.6.2",
        "G-31",
    ),
    # `javalin-routing` (w61). Three spellings of the owner (§3.1): a call through a
    # `Javalin`-typed local records `Javalin` in the constant pool even though `get`/
    # `post`/etc. are `default` methods it never overrides (`javap -c` on the fixture
    # confirms the call site's own owner), a call through a
    # `JavalinDefaultRoutingApi`-typed one records the interface, and — added on
    # review, `config.router.mount(router -> router.get(...))` — a call through the
    # SECOND type implementing that interface, `JavalinDefaultRouting` (`public final
    # class ... implements JavalinDefaultRoutingApi<JavalinDefaultRouting>`), records
    # that class. `ApiBuilder` is enumerated too: none of its methods are in
    # `javalin.yml`'s `matches.owner`, so its whole addressable surface is "missing"
    # here — the mechanical measurement behind filing it `slice.outside` in full
    # (`javalin-apibuilder`, Category B).
    Surface(
        "javalin",
        "io.javalin.Javalin",
        "io.javalin:javalin",
        "6.4.0",
        "javalin-routing",
    ),
    Surface(
        "javalin",
        "io.javalin.router.JavalinDefaultRoutingApi",
        "io.javalin:javalin",
        "6.4.0",
        "javalin-routing",
    ),
    Surface(
        "javalin",
        "io.javalin.router.JavalinDefaultRouting",
        "io.javalin:javalin",
        "6.4.0",
        "javalin-routing",
    ),
    Surface(
        "javalin",
        "io.javalin.apibuilder.ApiBuilder",
        "io.javalin:javalin",
        "6.4.0",
        "javalin-routing",
    ),
    # The nested form (A2 Task 3, `javalin-apibuilder`): its own `combinator` catalog
    # on the same `ApiBuilder` owner, so its own enumeration — it reads the six verbs
    # and `path`; the unread names with a `String` at argument 0 are the filters, the
    # other protocols, `crud` and `prefixPath`, each named in that file's slice.
    Surface(
        "javalin-apibuilder",
        "io.javalin.apibuilder.ApiBuilder",
        "io.javalin:javalin",
        "6.4.0",
        "javalin-nested",
    ),
    # `alpakka-pekko` (w62). `Consumer` is the owner `pekko-connectors-kafka.yml`
    # declares in `matches.owner`; `Producer` is named nowhere in `matches` at all —
    # its inbound-only catalog reads none of it — and is enumerated here anyway so
    # the header comment's "no single call names both" claim about `plainSink`/
    # `committableSink`/`flexiFlow` is a MEASUREMENT rather than a paragraph nobody
    # checks. MEASURED (w62): neither owner declares a method taking a `String` at
    # argument 0, a single `*Request` argument, or a route predicate — every method
    # on both takes `ConsumerSettings`/`ProducerSettings`/`ActorRef`/a `Producer`/
    # `CommitterSettings` first — so section 3 below lists no candidate for either,
    # and `pekko-connectors-kafka.yml` ships with no `slice.outside` block at all,
    # the same shape `kafka-consumer.yml`'s own file keeps for the identical reason.
    Surface(
        "pekko-connectors-kafka",
        "org.apache.pekko.kafka.javadsl.Consumer",
        "org.apache.pekko:pekko-connectors-kafka_2.13",
        "1.1.0",
        "alpakka-pekko",
    ),
    Surface(
        "pekko-connectors-kafka",
        "org.apache.pekko.kafka.javadsl.Producer",
        "org.apache.pekko:pekko-connectors-kafka_2.13",
        "1.1.0",
        "alpakka-pekko",
    ),
    # `ktor-routing` (A2 Task 5). Both owners the catalog names: the file facade holding
    # the `routing` entry, and the one holding every verb and prefix. MEASURED: every
    # `RoutingBuilderKt` method is a Kotlin extension whose `Route` receiver is argument
    # 0 and whose path — where it takes one — is argument 1, so the arg-0 test sees no
    # candidate on either owner and section 3 lists none for this catalog; the unread
    # names (`route` with an `HttpMethod`, `method`, the selector blocks, the reified
    # `*Typed*` spellings) are stated in `ktor-routing.yml`'s header rather than in a
    # slice the audit would refuse. A fourth addressing style — a name at argument 1
    # behind an extension receiver — would count them, and would also count methods on
    # owners already enumerated (`Javalin.addHttpHandler(HandlerType, String, Handler)`),
    # so it is not added as a side effect of one catalog.
    Surface(
        "ktor-routing",
        "io.ktor.server.routing.RoutingRootKt",
        "io.ktor:ktor-server-core-jvm",
        "3.0.3",
        "ktor-routing",
    ),
    Surface(
        "ktor-routing",
        "io.ktor.server.routing.RoutingBuilderKt",
        "io.ktor:ktor-server-core-jvm",
        "3.0.3",
        "ktor-routing",
    ),
)

# A Kotlin compiler synthetic: `getX$annotations()` holds a property's annotations and
# `f$default(...)` carries a default-argument mask. Neither is API — no author writes a
# call to one — so counting them would inflate the denominator of every ratio this probe
# publishes about a Kotlin DSL. Excluded by SHAPE rather than by name, because the names
# are generated. Added when `RouterFunctionDsl` was first enumerated (W44's review): the
# probe ABORTED on `public static void getBuilder$annotations();` rather than shrink a
# denominator silently, which is the behaviour working.
_KOTLIN_SYNTHETIC = re.compile(r"\$(annotations|default)$")


# Methods every class inherits or the compiler generates, which say nothing about a
# framework's surface. Excluded by NAME and stated here rather than filtered
# silently, so a reader can see exactly what the denominator does not count.
_NOT_SURFACE = frozenset(
    {
        "equals",
        "hashCode",
        "toString",
        "clone",
        "finalize",
        "getClass",
        "notify",
        "notifyAll",
        "wait",
        "main",
        "<init>",
        "<clinit>",
    }
)


# Supertypes this run could not open, per owner. Collected rather than printed where
# they are found: they are discovered while a table is being emitted, and a note in
# the middle of a table breaks the table. They are reported under it instead, because
# each one means the surface counted for that owner is a LOWER BOUND — and a lower
# bound printed as a count is exactly how "no unread method addresses a wire" got
# published for a catalog whose whole inbound direction is unread.
UNOPENED: dict[str, list[str]] = {}


class ProbeError(RuntimeError):
    """A run that could not answer, told apart from a run that answered `no`."""


def jar(artifact: str, version: str) -> Path:
    group, name = artifact.split(":")
    found = M2 / group.replace(".", "/") / name / version / f"{name}-{version}.jar"
    if not found.exists():
        raise ProbeError(f"{found} is absent; `run.sh` resolves it — run this through run.sh")
    return found


def self_reported_version(archive: Path) -> str:
    """The version the jar records about ITSELF (§5.4).

    THREE places, because different publishers use different ones and none is
    universal — the same set CP-10's harness reads. The Spring artifacts write
    `Implementation-Version:` into the manifest; the AWS SDK writes none at all and
    records its version only in Maven's `pom.properties`, which is still the
    archive's own statement about itself rather than the path it was cached at.
    Kafka Streams (`G-31`, w60) writes neither: its own version lives in
    `kafka/kafka-streams-version.properties`, at a DIFFERENT path than the raw
    client's `kafka/kafka-version.properties` — measured with `unzip -l` rather
    than assumed from the sibling artifact."""
    with zipfile.ZipFile(archive) as zf:
        try:
            manifest = zf.read("META-INF/MANIFEST.MF").decode("utf-8", "replace")
        except KeyError:
            manifest = ""
        for line in manifest.splitlines():
            if line.startswith("Implementation-Version:"):
                return line.split(":", 1)[1].strip()
        properties = [
            n
            for n in zf.namelist()
            if n.endswith("META-INF/maven/") is False
            and n.startswith("META-INF/maven/")
            and n.endswith("pom.properties")
        ]
        for name in properties:
            for line in zf.read(name).decode("utf-8", "replace").splitlines():
                if line.startswith("version="):
                    return line.split("=", 1)[1].strip()
        try:
            kafka_properties = zf.read("kafka/kafka-streams-version.properties").decode(
                "utf-8", "replace"
            )
        except KeyError:
            kafka_properties = ""
        for line in kafka_properties.splitlines():
            if line.startswith("version="):
                return line.split("=", 1)[1].strip()
    return "the archive records no version about itself"


# The `class X extends Y` line `javap` prints first, and the interfaces after it.
_DECLARATION = re.compile(
    r"^(?:public\s+)?(?:abstract\s+|final\s+)*(?:class|interface)\s+([\w.$<>,\s]+?)"
    r"(?:\s+extends\s+([\w.$<>,\s]+?))?(?:\s+implements\s+([\w.$<>,\s]+?))?\s*\{"
)
# Types whose members are not a framework's surface: the platform's own roots.
_NOT_A_FRAMEWORK = ("java.", "javax.lang.", "kotlin.")


def declared_methods(archive: Path, owner: str) -> list[tuple[str, str]]:
    """`(name, descriptor)` for every public method the type OFFERS — its own and
    every one it inherits from a supertype that is not the platform's.

    **Inheritance is not a detail here, it is most of the answer for one owner.**
    An earlier version ran `javap` on the named class alone. `SqsTemplate` declares
    ten methods and inherits its entire messaging surface — `receive`, `receiveMany`,
    `receiveAsync`, `receiveManyAsync`, `sendMany`, `sendAsync`, `sendManyAsync`, all
    taking the queue name at argument 0 — from `AbstractMessagingTemplate`. So the
    probe published *"no unread method addresses a wire"* for a catalog whose entire
    INBOUND direction is unread, and `docs/COVERAGE.md` printed that zero in the
    column it calls the number that matters.

    The repository already knew: `spring-sqs-template.yml`'s own comment records that
    three of its four `send` descriptors are declared on `AbstractMessagingTemplate`
    and that CP-10's harness "walks superclasses for exactly this reason". This is the
    third time in this wave a rule was applied to a set that was not the framework's
    set, and the first where the technique to avoid it was already in the tree.

    Platform supertypes are not walked: `Object`'s members say nothing about a
    framework, and neither do `java.*` collection interfaces a template may implement.
    """
    seen: dict[tuple[str, str], None] = {}
    pending = [owner]
    walked: set[str] = set()
    while pending:
        current = pending.pop()
        if current in walked or current.startswith(_NOT_A_FRAMEWORK):
            continue
        walked.add(current)
        text = _javap(archive, current)
        if text is None:
            # A supertype in another artifact this run did not resolve. Reported
            # rather than skipped silently: it means the surface below is a LOWER
            # bound, and a lower bound presented as a count is how the zero above
            # got published.
            UNOPENED.setdefault(owner, []).append(current)
            continue
        for name, descriptor in _members(text, current):
            seen.setdefault((name, descriptor), None)
        pending.extend(_supertypes(text))
    found = [
        pair
        for pair in seen
        if pair[0] not in _NOT_SURFACE and not _KOTLIN_SYNTHETIC.search(pair[0])
    ]
    if not found:
        raise ProbeError(f"javap printed no public methods for {owner}")
    return found


def _javap(archive: Path, owner: str) -> str | None:
    """`javap -s` output for one type, or `None` when this artifact does not carry
    it — a supertype living in a dependency is an answer, not a crash."""
    result = subprocess.run(
        ["javap", "-s", "-cp", str(archive), owner],
        capture_output=True,
        text=True,
        check=False,
    )
    return None if result.returncode != 0 else result.stdout


def _supertypes(text: str) -> list[str]:
    """Every type the declaration line extends or implements, erased of generics."""
    for line in text.splitlines():
        declaration = _DECLARATION.match(line.strip())
        if declaration is None:
            continue
        found: list[str] = []
        for group in (declaration.group(2), declaration.group(3)):
            if not group:
                continue
            depth, current = 0, ""
            for character in group:
                if character == "<":
                    depth += 1
                elif character == ">":
                    depth -= 1
                elif character == "," and depth == 0:
                    found.append(current)
                    current = ""
                    continue
                if depth == 0 and character not in "<>":
                    current += character
            found.append(current)
        return [t.strip() for t in found if t.strip()]
    return []


def _members(text: str, owner: str) -> list[tuple[str, str]]:
    """`(name, descriptor)` for the public methods one `javap` output declares."""
    found: list[tuple[str, str]] = []
    pending: str | None = None
    for line in text.splitlines():
        signature = _SIGNATURE.match(line)
        if signature is not None:
            pending = signature.group(2)
            continue
        if _CONSTRUCTOR.match(line):
            pending = None
            continue
        if _PUBLIC.match(line) and not _FIELD.match(line) and "(" in line:
            raise ProbeError(
                f"could not parse this public member of {owner}, and skipping it would "
                f"shrink the denominator of a ratio this probe publishes:\n  {line}"
            )
        descriptor = _DESCRIPTOR.match(line)
        if descriptor is not None and pending is not None:
            found.append((pending, descriptor.group(1)))
            pending = None
    return found


def catalog(catalog_id: str) -> Catalog:
    found = next((c for c in YamlCatalogSource(CATALOGS).load() if c.id == catalog_id), None)
    if found is None:
        raise ProbeError(f"no shipped catalog has id {catalog_id!r}")
    return found


def read_names(loaded: Catalog, owner: str) -> set[str]:
    """Every method name the catalog reads ON THIS OWNER.

    **Owner-aware, and the first version was not.** A flat walk collecting every
    `method:`/`name:` in the file said `spring-webflux-router` reads 9 of
    `RouterFunctions$Builder`'s 20 methods — because that catalog names `GET`, `POST`
    and the rest on `RequestPredicates`, a different type entirely. G-37's whole
    finding is that the BUILDER DSL derives nothing, and the flat walk reported it as
    half covered. Same defect class as the arg-0 test applied to the AWS SDK, and as
    W13's and W14's: a name compared against the wrong set.

    A method name is attributed to the nearest `owner:` above it, falling back to
    `matches.owner` — which is how the catalogs are shaped, and both spellings of
    `owner` (scalar and list, §3.1) are read.
    """
    wanted = _owner_forms(owner)
    names: set[str] = set()

    def walk(node: object, scope: frozenset[str]) -> None:
        if isinstance(node, dict):
            here = scope
            if "owner" in node:
                declared = node["owner"]
                spellings = declared if isinstance(declared, list) else [declared]
                here = frozenset(str(o) for o in spellings if isinstance(o, str))
            for key, value in node.items():
                if key in ("method", "name") and isinstance(value, str):
                    if here & wanted:
                        names.add(value)
                elif key != "owner":
                    walk(value, here)
        elif isinstance(node, list):
            for item in node:
                walk(item, scope)

    top = loaded.matches.get("owner")
    spellings = top if isinstance(top, list) else [top]
    walk(loaded.matches, frozenset(str(o) for o in spellings if isinstance(o, str)))
    return names


def _owner_forms(owner: str) -> frozenset[str]:
    """The spellings a catalog may use for one owner. A nested type is `Outer$Inner`
    in bytecode and `Outer.Inner` in a catalog, and both name the same class."""
    return frozenset({owner, owner.replace("$", ".")})


def main() -> None:
    print("## Observations\n")
    print(
        "Generated by `scripts/probes/w19_catalog_surface/run.sh` — every cell below is that "
        "run's own output, and this document pastes it verbatim.\n"
    )
    print(
        "**Each column header is the version the JAR ITSELF reported**, read out of its own "
        "`META-INF/MANIFEST.MF` `Implementation-Version` — not the version the loop asked "
        "for, which is only the path this machine cached the artifact at. The run ABORTS "
        "when the two disagree rather than printing a row.\n"
    )
    print(
        f"Methods every class carries are excluded from both sides of every count: "
        f"{', '.join(sorted(_NOT_SURFACE))}. Kotlin's own compiler synthetics — "
        f"`getX$annotations` and `f$default` — are excluded too: neither is API, and no "
        f"author writes a call to one.\n"
    )

    versions = sorted({s.version for s in SURFACES})

    print("### 1. How much of each owner's surface the catalog reads\n")
    print("| gap | catalog | owner | " + " | ".join(versions) + " | reads |")
    print("| --- | --- | --- |" + " --- |" * (len(versions) + 1))
    unread: dict[tuple[str, str], list[str]] = {}
    candidate_boundaries: dict[tuple[str, str], list[str]] = {}
    request_boundaries: dict[tuple[str, str], list[str]] = {}
    route_boundaries: dict[tuple[str, str], list[str]] = {}
    for surface in SURFACES:
        archive = jar(surface.artifact, surface.version)
        claimed = self_reported_version(archive)
        if claimed != surface.version:
            raise ProbeError(
                f"{archive} was requested as {surface.version} and its own manifest claims "
                f"{claimed!r}. Every cell would be filed under a version it did not report."
            )
        methods = declared_methods(archive, surface.owner)
        names = sorted({name for name, _ in methods})
        read = read_names(catalog(surface.catalog_id), surface.owner)
        missing = [name for name in names if name not in read]
        unread[(surface.catalog_id, surface.owner)] = missing
        # A destination-carrying method takes the name at argument 0 — the position
        # every such method in these ten owners uses. Read off the DESCRIPTOR, so an
        # overload taking a name counts its name in even when a sibling does not.
        addressed = {
            name for name, descriptor in methods if descriptor.startswith("(Ljava/lang/String;")
        }
        candidate_boundaries[(surface.catalog_id, surface.owner)] = [
            name for name in missing if name in addressed
        ]
        # The SECOND addressing style, and leaving it out would have published a
        # confident zero for the one gap G-43 names. `SqsClient.receiveMessage`
        # carries its queue URL inside a `ReceiveMessageRequest`, so it takes no
        # `String` at argument 0 and the test above cannot see it — the same "a rule
        # mirrored onto a set it does not fit" shape W13 and W14 hit. A method whose
        # only parameter is a type named `*Request` addresses the wire through that
        # object, which is measurable from the descriptor.
        by_request = {name for name, descriptor in methods if _REQUEST_OBJECT.match(descriptor)}
        request_boundaries[(surface.catalog_id, surface.owner)] = [
            name for name in missing if name in by_request
        ]
        by_route = {name for name, descriptor in methods if _ROUTE_DECLARING.match(descriptor)}
        route_boundaries[(surface.catalog_id, surface.owner)] = [
            name for name in missing if name in by_route
        ]
        cells = [str(len(names)) if v == claimed else "—" for v in versions]
        simple = surface.owner.rsplit(".", 1)[-1]
        print(
            f"| {surface.gap} | `{surface.catalog_id}` | `{simple}` | "
            + " | ".join(cells)
            + f" | **{len(names) - len(missing)} of {len(names)}** |"
        )
    print(
        "\n- A version column holds the count of public methods that owner OFFERS at that "
        "version — its own and every one it inherits from a non-platform supertype; `—` "
        "means this owner was not measured there.\n"
    )
    if UNOPENED:
        print(
            "**Supertypes this run could not open, so the surfaces below them are LOWER "
            "BOUNDS.** Each lives in an artifact this probe does not resolve. None of them "
            "is a messaging or routing type — they are the Spring and AWS lifecycle "
            "interfaces (`InitializingBean`, `Lifecycle`, `AwsClient` and the like) — so no "
            "addressable method is expected to be hiding behind one. That expectation is "
            "stated rather than measured, and it is the same kind of statement that was "
            "wrong about `AbstractMessagingTemplate`.\n"
        )
        for owner, missing in sorted(UNOPENED.items()):
            print(f"- `{owner}`: " + ", ".join(f"`{m}`" for m in sorted(set(missing))))
        print()

    print("### 2. Of the unread, which could carry a destination\n")
    # The count is the table's own, read from the same dict the rows print — it was
    # once a literal, and the literal stayed at 83 after the receive half shipped
    # and the row beneath it said 84.
    rabbit_unread = sum(
        len(missing) for (_, owner), missing in unread.items() if owner.endswith(".RabbitTemplate")
    )
    print(
        "A raw ratio overstates every gap here: most of what a template class declares is "
        f"configuration and lifecycle, not boundaries. `RabbitTemplate`'s {rabbit_unread} include "
        "`setChannelTransacted`, `afterPropertiesSet` and every getter. So the unread half "
        "is split by a MEASURED property rather than by judgement — **does the method take a "
        "`String` at argument 0**, the position every destination-carrying method in these "
        "APIs uses (measured across all ten owners; it is the position "
        "`spring-pubsub.yml`, `spring-jms-template.yml` and `spring-sqs-template.yml` "
        "already read). A method that takes no name cannot address a wire, so it is not a "
        "candidate boundary and its absence needs no slice.\n"
    )
    print(
        "**This split does not decide the slice**, it bounds the work of writing one: a "
        "candidate may still be deliberately outside (a `receive` with no payload capture, "
        "a batch form), and a non-candidate may still be a boundary reached another way (a "
        "destination-less `send` on a template configured with a default). Those are "
        "judgements a catalog states; this table says which methods the judgement is about.\n"
    )
    print(
        "| catalog | owner | unread | name at arg 0 | single `*Request` argument | "
        "declares a route | distinct |"
    )
    print("| --- | --- | --- | --- | --- | --- | --- |")
    # The three style columns OVERLAP: a `RouterFunctions$Builder` verb has both a
    # path-string overload and a predicate overload, so it is counted under two of
    # them. `distinct` is the number of METHODS a slice has to account for, and
    # without it the styles summed to more candidates than there were unread methods.
    for surface in SURFACES:
        missing = unread[(surface.catalog_id, surface.owner)]
        simple = surface.owner.rsplit(".", 1)[-1]
        named = candidate_boundaries[(surface.catalog_id, surface.owner)]
        requested = request_boundaries[(surface.catalog_id, surface.owner)]
        routed = route_boundaries[(surface.catalog_id, surface.owner)]
        distinct = len(set(named) | set(requested) | set(routed))
        print(
            f"| `{surface.catalog_id}` | `{simple}` | {len(missing)} | "
            f"**{len(named)}** | **{len(requested)}** | **{len(routed)}** | **{distinct}** |"
        )
    print()
    for surface in SURFACES:
        simple = surface.owner.rsplit(".", 1)[-1]
        named = candidate_boundaries[(surface.catalog_id, surface.owner)]
        requested = request_boundaries[(surface.catalog_id, surface.owner)]
        routed = route_boundaries[(surface.catalog_id, surface.owner)]
        if not named and not requested and not routed:
            print(
                f"**`{surface.catalog_id}` / `{simple}`** — no unread method addresses a "
                f"wire by either style.\n"
            )
            continue
        print(f"**`{surface.catalog_id}` / `{simple}`**\n")
        if named:
            print(
                f"> by name at argument 0 ({len(named)}): "
                + ", ".join(f"`{n}`" for n in named)
                + "\n"
            )
        if requested:
            print(
                f"> by a `*Request` object ({len(requested)}): "
                + ", ".join(f"`{n}`" for n in requested)
                + "\n"
            )
        if routed:
            print(
                f"> by declaring a route ({len(routed)}): "
                + ", ".join(f"`{n}`" for n in routed)
                + "\n"
            )

    _emit_slice_table(candidate_boundaries, request_boundaries, route_boundaries)


def _emit_slice_table(
    candidate_boundaries: dict[tuple[str, str], list[str]],
    request_boundaries: dict[tuple[str, str], list[str]],
    route_boundaries: dict[tuple[str, str], list[str]],
) -> None:
    """Section 3: one row per unread candidate boundary, for the audit to read.

    Prose is what a reader needs and a table is what a test can hold to. This is
    the second — the same division `cp10_catalog_descriptors.md` uses, whose
    generated table `tests/architecture/test_catalog_descriptors.py` parses in
    full. `tests/architecture/test_catalog_slice_coverage.py` parses this one and
    requires every row here to be named in its catalog's `slice.outside`, so a
    framework release that adds an addressable method fails the audit until
    someone declares it in or out.
    """
    print("### 3. Every unread candidate, one per row\n")
    print("| catalog | owner | method | addressed by |")
    print("|---|---|---|---|")
    for surface in SURFACES:
        key = (surface.catalog_id, surface.owner)
        for name in candidate_boundaries[key]:
            print(f"| `{surface.catalog_id}` | `{surface.owner}` | `{name}` | `argument 0` |")
        for name in request_boundaries[key]:
            print(f"| `{surface.catalog_id}` | `{surface.owner}` | `{name}` | `request object` |")
        for name in route_boundaries[key]:
            print(
                f"| `{surface.catalog_id}` | `{surface.owner}` | `{name}` | `route declaration` |"
            )
    print()


if __name__ == "__main__":
    try:
        main()
    except ProbeError as error:
        print(f"PROBE COULD NOT ANSWER: {error}", file=sys.stderr)
        raise SystemExit(2) from error
