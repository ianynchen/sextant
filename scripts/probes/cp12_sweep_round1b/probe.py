"""CP-12's measurement half: the framework surfaces the round-1b sweep fix pass
mirrors, read off the frameworks' own bytecode.

Called by `run.sh`, which resolves the jars; this script never downloads
anything. It is CP-11's harness aimed at a different family of findings, and it
keeps CP-11's two pre-flight guarantees, aborting on the first that fails:

1. **Reads each jar's own identity out of its own bytes** and refuses to file a
   cell under a version the artifact did not claim (GUIDELINES §5.4, and CP-5's
   failure it exists to prevent). Where the self-report lives differs per
   artifact — the manifest's `Implementation-Version` for the Spring, Jakarta
   and Spring Cloud AWS jars, `kafka/kafka-version.properties` for
   kafka-clients, which writes none into its manifest. An artifact that writes
   it NOWHERE is declared `-` in `run.sh` and prints as `assumed`.
2. **Indexes class -> jar** off the archives, so a class is attributed to the
   jar the run opened.

**Every question CP-12 asks is a completeness question**, because that is what
the eight Class A Majors it serves have in common: `A-M3`/`A-M4` (five of eight
request-starting methods, a terminal set that is wrong at both measured Spring
minors at once), `A-M5` (six of eight Retrofit annotations), `A-M6` (the
callback and rebalance-listener overloads), `A-M7` (one of eleven JMS consumer
factories), `A-M8` (one half of an `@AliasFor` pair), `A-M9` (three of seven
router verbs). CP-10 asks the converse — *does every descriptor a catalog
declares name a real method?* — and every one of these findings lives on the
side CP-10 does not ask about (`A-Mi5`). So each answer below is **the
framework's whole set**, printed, and the offline half
(`tests/architecture/test_sweep_round1b_framework_surfaces.py`) asserts the
catalog covers it.

Every question answers PER RESOLVED ARTIFACT rather than once, so a surface read
against two Spring minors prints two rows and §5.4's scope is the rows
themselves rather than a sentence about them.
"""

from __future__ import annotations

import re
import subprocess
import sys
import zipfile
from collections.abc import Callable
from pathlib import Path

# `<key>=<value>` in a `.properties` entry, and the manifest's own `Name: value`.
_PROPERTY = re.compile(r"^\s*([\w.\-]+)\s*[:=]\s*(.+?)\s*$")
# `javap -p -s`'s two lines: the declaration, then the erased descriptor.
_DECLARATION = re.compile(r"^\s{2}\S.*?([\w$]+)\s*\(")
_DESCRIPTOR_LINE = re.compile(r"^\s*descriptor:\s*(\S+)\s*$")
_ASSUMED = "-"


class ProbeError(RuntimeError):
    """A run that cannot label its own output. Fatal, never advisory."""


class Artifact:
    """One resolved jar, and the identity it reported for itself."""

    __slots__ = ("classes", "jar", "name", "observed", "requested", "self_reported")

    def __init__(self, name: str, requested: str, jar: Path, entry: str, key: str) -> None:
        self.name = name
        self.requested = requested
        self.jar = jar
        self.self_reported = entry != _ASSUMED
        self.observed = _identity(jar, entry, key) if self.self_reported else requested
        if self.self_reported and self.observed != requested:
            raise ProbeError(
                f"{jar.name} reports version {self.observed!r} but was resolved as "
                f"{requested!r} — a mislabelled column, which is CP-5's failure exactly"
            )
        self.classes = _classes_of(jar)


def _identity(jar: Path, entry: str, key: str) -> str:
    """The version this ARCHIVE claims for itself, read out of its own bytes."""
    with zipfile.ZipFile(jar) as archive:
        names = [name for name in archive.namelist() if name == entry or name.endswith("/" + entry)]
        if not names:
            raise ProbeError(f"{jar.name} carries no `{entry}` — it reports no version of its own")
        text = archive.read(names[0]).decode("utf-8", "replace")
    for line in text.splitlines():
        match = _PROPERTY.match(line)
        if match and match.group(1).lower() == key.lower():
            return match.group(2)
    raise ProbeError(f"{jar.name}'s `{entry}` declares no `{key}`")


def _classes_of(jar: Path) -> set[str]:
    with zipfile.ZipFile(jar) as archive:
        return {
            name[: -len(".class")].replace("/", ".")
            for name in archive.namelist()
            if name.endswith(".class")
        }


def _javap(*arguments: str, classpath: Path) -> str:
    result = subprocess.run(
        ["javap", "-cp", str(classpath), *arguments],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise ProbeError(f"javap {' '.join(arguments)} failed: {result.stderr.strip()}")
    return result.stdout


def _methods(output: str) -> list[tuple[str, str]]:
    """`(name, erased descriptor)` for every method `javap -p -s` printed."""
    found: list[tuple[str, str]] = []
    pending: str | None = None
    for line in output.splitlines():
        descriptor = _DESCRIPTOR_LINE.match(line)
        if descriptor and pending is not None:
            found.append((pending, descriptor.group(1)))
            pending = None
            continue
        declaration = _DECLARATION.match(line)
        pending = declaration.group(1) if declaration else pending
    return found


def _declared(artifact: Artifact, fqn: str) -> list[tuple[str, str]]:
    if fqn not in artifact.classes:
        raise ProbeError(f"{artifact.jar.name} declares no {fqn}")
    return _methods(_javap("-p", "-s", fqn, classpath=artifact.jar))


def _signature(name: str, descriptor: str) -> str:
    """`name(Largs;)` — the erased argument list, which is the whole identity a
    catalog row has to match on. The return type is dropped because no catalog
    grammar keys on it."""
    return f"{name}{descriptor.split(')')[0]})"


def _named(artifacts: list[Artifact], name: str) -> list[Artifact]:
    found = [artifact for artifact in artifacts if artifact.name == name]
    if not found:
        raise ProbeError(f"no resolved artifact named {name}")
    return found


# --- the questions, in the order `cp12_sweep_round1b.md` states them ---------
#
# Each returns one `(artifact, version, observed)` row per artifact it applies
# to. The answers are whole strings rather than booleans, for CP-11's reason: a
# boolean records the reader's conclusion, a string records what the jar said,
# and only the second can be re-checked by somebody who disagrees.


def _request_starters(artifact: Artifact, client: str) -> str:
    """Every method on a fluent HTTP client that STARTS a request — measured as
    "declared on the client type and returning one of its own request specs",
    never as a list of verb names, because the whole finding is that the encoded
    list was shorter than the framework's."""
    spec = f"L{client.replace('.', '/')}$Request"
    return ", ".join(
        sorted(
            _signature(name, descriptor)
            for name, descriptor in _declared(artifact, client)
            if descriptor.split(")")[1].startswith(spec)
        )
    )


def q1_webclient_request_starters(artifacts: list[Artifact]) -> list[tuple[str, str, str]]:
    """Q1 (`A-M3`). `WebClient`'s request-starting surface. The catalog declares
    five roots; a chain rooted on an undeclared one is never rooted at all and
    derives NO outbound row (`fluent.py:21`) — a silent drop, not a wrong
    row."""
    client = "org.springframework.web.reactive.function.client.WebClient"
    return [
        (artifact.name, artifact.observed, _request_starters(artifact, client))
        for artifact in _named(artifacts, "spring-webflux")
    ]


def q2_webclient_terminals(artifacts: list[Artifact]) -> list[tuple[str, str, str]]:
    """Q2 (`A-M4`). Which methods of `WebClient$RequestHeadersSpec` OBTAIN a
    response, as against continuing the chain.

    The discriminator is the framework's own and not a name: every header,
    cookie and attribute setter returns the spec type itself (`S`, erased to
    the interface), so a method declaring any other return type is one that
    executes the request. That is what makes "the terminal set" measurable
    rather than remembered — and remembered is how `exchange` came to be
    declared at a version that does not have it while `exchangeToMono`, the
    recommended form since 5.3, was in the list at no version at all."""
    spec = "org.springframework.web.reactive.function.client.WebClient$RequestHeadersSpec"
    rows = []
    for artifact in _named(artifacts, "spring-webflux"):
        returns_the_spec = f"L{spec.replace('.', '/')};"
        rows.append(
            (
                artifact.name,
                artifact.observed,
                ", ".join(
                    sorted(
                        _signature(name, descriptor)
                        for name, descriptor in _declared(artifact, spec)
                        if not descriptor.endswith(returns_the_spec)
                    )
                ),
            )
        )
    return rows


def q3_restclient_request_starters(artifacts: list[Artifact]) -> list[tuple[str, str, str]]:
    """Q3 (`A-M3`). `RestClient`'s request-starting surface — WebClient's
    synchronous twin, and the same five-of-eight gap."""
    client = "org.springframework.web.client.RestClient"
    return [
        (artifact.name, artifact.observed, _request_starters(artifact, client))
        for artifact in _named(artifacts, "spring-web")
    ]


def q4_restclient_terminals(artifacts: list[Artifact]) -> list[tuple[str, str, str]]:
    """Q4 (`A-M3`/`A-M4`). `RestClient$RequestHeadersSpec`'s response-obtaining
    methods, by Q2's own discriminator."""
    spec = "org.springframework.web.client.RestClient$RequestHeadersSpec"
    rows = []
    for artifact in _named(artifacts, "spring-web"):
        returns_the_spec = f"L{spec.replace('.', '/')};"
        rows.append(
            (
                artifact.name,
                artifact.observed,
                ", ".join(
                    sorted(
                        _signature(name, descriptor)
                        for name, descriptor in _declared(artifact, spec)
                        if not descriptor.endswith(returns_the_spec)
                    )
                ),
            )
        )
    return rows


def q5_retrofit_request_method_annotations(
    artifacts: list[Artifact],
) -> list[tuple[str, str, str]]:
    """Q5 (`A-M5`). Every Retrofit annotation that names a REQUEST METHOD, with
    the attributes each declares.

    Measured in two halves, and both are needed. The `retrofit2.http` package
    also holds parameter annotations (`@Path`, `@Query`, `@Body`) and method
    modifiers (`@Headers`, `@Multipart`), so membership of the package is not
    the question. The set printed here is the intersection of two facts the jar
    states: the annotation is `@Target(METHOD)`, and `RequestFactory$Builder` —
    the class that turns a method's annotations into a request — tests for it
    with an `instanceof`. The attribute list is what separates a verb
    annotation from a modifier: `@GET` declares `String value()`, `@HTTP`
    declares `method()`/`path()`/`hasBody()`, and `@Multipart` declares
    nothing."""
    rows = []
    for artifact in _named(artifacts, "retrofit"):
        builder = _javap("-p", "-c", "retrofit2.RequestFactory$Builder", classpath=artifact.jar)
        tested = sorted(
            set(re.findall(r"instanceof\s+#\d+\s+// class retrofit2/http/(\w+)", builder))
        )
        parts = []
        for simple in tested:
            fqn = f"retrofit2.http.{simple}"
            targets = _targets_of(artifact, fqn)
            if targets != "METHOD":
                continue
            # The RETURN type is carried here where `_signature` drops it
            # everywhere else, and it is the discriminator: `@GET` declares a
            # scalar `String value()` naming a path, `@Headers` declares a
            # `String[] value()` naming header lines, and neither is
            # distinguishable from the other by name.
            attributes = ",".join(
                sorted(
                    f"{_signature(name, descriptor)}:{descriptor.split(')')[1]}"
                    for name, descriptor in _declared(artifact, fqn)
                )
            )
            parts.append(f"{simple}[{attributes or 'no attributes'}]")
        rows.append((artifact.name, artifact.observed, ", ".join(parts)))
    return rows


def _targets_of(artifact: Artifact, fqn: str) -> str:
    output = _javap("-v", "-p", fqn, classpath=artifact.jar)
    return ",".join(sorted(set(re.findall(r"ElementType;\.(\w+)", output))))


def _overloads(artifact: Artifact, fqn: str, *names: str) -> str:
    wanted = frozenset(names)
    return ", ".join(
        sorted(
            _signature(name, descriptor)
            for name, descriptor in _declared(artifact, fqn)
            if name in wanted
        )
    )


def q6_kafka_producer_send(artifacts: list[Artifact]) -> list[tuple[str, str, str]]:
    """Q6 (`A-M6`). Every `KafkaProducer.send` overload. `single_call`'s
    `_matching_method` filters candidates by `row.get("arity") in (None,
    len(arguments))` BEFORE consulting descriptors, so a 2-argument call never
    sees an arity-1 row — and `send(record, callback)` is the idiomatic async
    producer call."""
    return [
        (
            artifact.name,
            artifact.observed,
            _overloads(artifact, "org.apache.kafka.clients.producer.KafkaProducer", "send"),
        )
        for artifact in _named(artifacts, "kafka-clients")
    ]


def q7_kafka_consumer_subscribe(artifacts: list[Artifact]) -> list[tuple[str, str, str]]:
    """Q7 (`A-M6`). Every `KafkaConsumer` overload that names the topics this
    consumer reads — `subscribe` in its four forms, and `assign`, whose topic
    travels inside a `TopicPartition` and is a separate statable boundary."""
    return [
        (
            artifact.name,
            artifact.observed,
            _overloads(
                artifact,
                "org.apache.kafka.clients.consumer.KafkaConsumer",
                "subscribe",
                "assign",
            ),
        )
        for artifact in _named(artifacts, "kafka-clients")
    ]


def q8_kafka_template_send(artifacts: list[Artifact]) -> list[tuple[str, str, str]]:
    """Q8 (`A-M6`). Every `KafkaTemplate.send`/`sendDefault` overload."""
    return [
        (
            artifact.name,
            artifact.observed,
            _overloads(
                artifact,
                "org.springframework.kafka.core.KafkaTemplate",
                "send",
                "sendDefault",
            ),
        )
        for artifact in _named(artifacts, "spring-kafka")
    ]


def q9_jms_session_consumer_factories(artifacts: list[Artifact]) -> list[tuple[str, str, str]]:
    """Q9 (`A-M7`). Every `jakarta.jms.Session` factory that creates a receiver
    on a destination.

    Measured as "declared on `Session` and returning a `MessageConsumer`, a
    `TopicSubscriber` or a `QueueBrowser`" — the return type is the framework's
    own statement that the call opens a receiver, and it is what makes the set
    complete without a list of names somebody remembered. Every one takes its
    destination as argument 0, which is the position the catalog already
    reads."""
    receivers = (
        "Ljakarta/jms/MessageConsumer;",
        "Ljakarta/jms/TopicSubscriber;",
        "Ljakarta/jms/QueueBrowser;",
    )
    rows = []
    for artifact in _named(artifacts, "jakarta.jms-api"):
        rows.append(
            (
                artifact.name,
                artifact.observed,
                ", ".join(
                    sorted(
                        _signature(name, descriptor)
                        for name, descriptor in _declared(artifact, "jakarta.jms.Session")
                        if descriptor.endswith(receivers)
                    )
                ),
            )
        )
    return rows


def q10_sqs_listener_destination_attributes(
    artifacts: list[Artifact],
) -> list[tuple[str, str, str]]:
    """Q10 (`A-M8`). `@SqsListener`'s attributes, and which of them are one
    attribute under two spellings.

    `@AliasFor` is Spring's own declaration that two attribute names are the
    same attribute, so it is read out of the annotation's own
    `RuntimeVisibleAnnotations` rather than inferred from the types matching.
    The catalog reads `value` only, so `@SqsListener(queueNames = …)` — the
    spelling AWS's own documentation uses — reads as absent, and the
    addresses-nothing gate then withholds the row entirely."""
    rows = []
    for artifact in _named(artifacts, "spring-cloud-aws-sqs"):
        fqn = "io.awspring.cloud.sqs.annotation.SqsListener"
        output = _javap("-v", "-p", fqn, classpath=artifact.jar)
        parts = []
        for name, descriptor in _methods(_javap("-p", "-s", fqn, classpath=artifact.jar)):
            alias = _alias_for(output, name)
            returns = descriptor.split(")")[1]
            parts.append(f"{name}:{returns}" + (f"=AliasFor({alias})" if alias else ""))
        rows.append((artifact.name, artifact.observed, ", ".join(sorted(parts))))
    return rows


def _alias_for(output: str, attribute: str) -> str | None:
    """The `@AliasFor` target declared on one annotation attribute, read off
    `javap -v`'s rendering of its `RuntimeVisibleAnnotations`.

    The block is delimited by the NEXT declaration rather than by a fixed
    window: `javap -v` prints `AnnotationDefault` before
    `RuntimeVisibleAnnotations`, and an attribute with a default pushes its
    `@AliasFor` far enough down that a fixed lookahead reads as "no alias" —
    which is the answer this whole question exists to refuse.
    """
    lines = output.splitlines()
    start = next(
        (
            i
            for i, line in enumerate(lines)
            if re.search(rf"\b{re.escape(attribute)}\(\);\s*$", line)
        ),
        None,
    )
    if start is None:
        return None
    block: list[str] = []
    for line in lines[start + 1 :]:
        if _DECLARATION.match(line):
            break
        block.append(line)
    window = "\n".join(block)
    if "AliasFor" not in window:
        return None
    match = re.search(r'value="([^"]+)"', window)
    return match.group(1) if match else "?"


def _static_predicates(artifact: Artifact, fqn: str, returns: str) -> str:
    return ", ".join(
        sorted(
            _signature(name, descriptor)
            for name, descriptor in _declared(artifact, fqn)
            if descriptor.endswith(returns) and name.isupper()
        )
    )


def q11_request_predicates_verbs(artifacts: list[Artifact]) -> list[tuple[str, str, str]]:
    """Q11 (`A-M9`). `RequestPredicates`' per-verb factories.

    Measured as "declared on the class, returning a `RequestPredicate`, and
    named in upper case" — the framework's own naming of the verb factories,
    which distinguishes them from `all()`, `path()`, `accept()` and the two
    generic `method`/`methods` forms without a list anybody typed. The catalog
    encodes GET/POST/HEAD, which is exactly the fixture's verb vocabulary."""
    return [
        (
            artifact.name,
            artifact.observed,
            _static_predicates(
                artifact,
                "org.springframework.web.reactive.function.server.RequestPredicates",
                "Lorg/springframework/web/reactive/function/server/RequestPredicate;",
            ),
        )
        for artifact in _named(artifacts, "spring-webflux")
    ]


def q12_co_router_dsl_verbs(artifacts: list[Artifact]) -> list[tuple[str, str, str]]:
    """Q12 (`A-M9`). `CoRouterFunctionDsl`'s per-verb route functions — the
    Kotlin coroutine DSL, where the catalog encodes GET/POST alone.

    The route-declaring overloads return `void`; the same names also declare a
    predicate-building overload returning a `RequestPredicate`. Both are
    printed, because which of the two a catalog row must match is a question
    about the fact stream and not about the framework."""
    return [
        (
            artifact.name,
            artifact.observed,
            ", ".join(
                sorted(
                    _signature(name, descriptor)
                    for name, descriptor in _declared(
                        artifact,
                        "org.springframework.web.reactive.function.server.CoRouterFunctionDsl",
                    )
                    if name.isupper()
                )
            ),
        )
        for artifact in _named(artifacts, "spring-webflux")
    ]


_QUESTIONS: list[tuple[str, str, Callable[[list[Artifact]], list[tuple[str, str, str]]]]] = [
    ("1", "`WebClient` request-starting methods", q1_webclient_request_starters),
    ("2", "`WebClient$RequestHeadersSpec` response-obtaining methods", q2_webclient_terminals),
    ("3", "`RestClient` request-starting methods", q3_restclient_request_starters),
    ("4", "`RestClient$RequestHeadersSpec` response-obtaining methods", q4_restclient_terminals),
    ("5", "Retrofit request-method annotations", q5_retrofit_request_method_annotations),
    ("6", "`KafkaProducer.send` overloads", q6_kafka_producer_send),
    ("7", "`KafkaConsumer.subscribe`/`assign` overloads", q7_kafka_consumer_subscribe),
    ("8", "`KafkaTemplate.send`/`sendDefault` overloads", q8_kafka_template_send),
    ("9", "`jakarta.jms.Session` receiver factories", q9_jms_session_consumer_factories),
    ("10", "`@SqsListener` attributes and their aliases", q10_sqs_listener_destination_attributes),
    ("11", "`RequestPredicates` verb factories", q11_request_predicates_verbs),
    ("12", "`CoRouterFunctionDsl` verb functions", q12_co_router_dsl_verbs),
]


def main(specs: list[str]) -> int:
    artifacts = []
    for spec in specs:
        _, name, version, entry, key, jar = spec.split("|")
        artifacts.append(Artifact(name, version, Path(jar), entry, key))

    columns = sorted({artifact.observed for artifact in artifacts})
    print("| what the run read | " + " | ".join(columns) + " |")
    print("|---" * (len(columns) + 1) + "|")
    print(
        "| artifacts reporting this version | "
        + " | ".join(
            ", ".join(sorted(a.name for a in artifacts if a.observed == version))
            for version in columns
        )
        + " |"
    )
    print(
        "| identity read from the archive itself | "
        + " | ".join(
            "yes" if all(a.self_reported for a in artifacts if a.observed == version) else "assumed"
            for version in columns
        )
        + " |"
    )
    print()
    print("| # | question | artifact | version | observed |")
    print("|---|---|---|---|---|")
    for number, question, answer in _QUESTIONS:
        rows = answer(artifacts)
        for index, (where, version, observed) in enumerate(rows):
            suffix = "" if len(rows) == 1 else chr(ord("a") + index)
            print(f"| {number}{suffix} | {question} | `{where}` | {version} | `{observed}` |")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except ProbeError as error:
        print(f"CP-12 aborted: {error}", file=sys.stderr)
        raise SystemExit(1) from None
