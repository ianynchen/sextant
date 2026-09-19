"""Regenerate the COVERAGE.md matrices (section 2) from the checklist (section 5).

Section 5 is the source of truth: one row per (language, library). This derives the
per-cell tier spread so the matrices cannot drift from the checklist they summarise.

**And, since 2026-09-18, the per-framework rollup under each protocol heading.** §2 scores
a LANGUAGE per protocol and §5 lists FORMS; the question a reader asks — "is Spring REST
inbound complete? what is missing for Ktor?" — sits between the two and had no answer
anywhere in the document. Each `### 5.1`–`### 5.12` heading now carries a generated table:
one row per Java/Kotlin framework on the declared target list (`FRAMEWORKS`), its status
rolled up from the `Framework` column of the rows below it plus the open ids of
`java-kotlin-delivery-list.md`'s register (`ITEM_FRAMEWORKS`). `✅ full` means every row
shipped and no open id; `◐ partial` says what is missing; `✗ unsupported` is a framework on
the target list with no row at all — the line the document had no way to show before.

Usage: python scripts/coverage_matrix.py [--check]
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

DOC = Path(__file__).resolve().parent.parent / "docs" / "COVERAGE.md"

# Section 5 heading -> (matrix, column label). Order here is column order.
HTTP_COLUMNS = [
    ("REST inbound", "REST in"),
    ("REST outbound", "REST out"),
    ("SOAP", "SOAP"),
    ("GraphQL", "GraphQL"),
    ("WebSocket", "WebSocket"),
    ("Server-Sent Events", "SSE"),
]
MSG_COLUMNS = [
    ("gRPC", "gRPC"),
    ("Kafka", "Kafka"),
    ("JMS and AMQP", "JMS / AMQP"),
    ("AWS SQS", "SQS"),
    ("Google Cloud Pub/Sub", "Pub/Sub"),
    ("Async and internal boundaries", "Async"),
]

# Section 5 headings that are NOT on the protocol axis (F6 §7.2, W41), so they feed no
# matrix column and must not. Declared rather than inferred: `parse` reads every `### 5.x`
# heading, so a section nobody wired to a column is INDISTINGUISHABLE from one whose wiring
# was forgotten — and the failure mode of the second is silent, because `render` only emits
# the columns it was given and drops the rest on the floor. A new protocol section now
# fails this script until it is either given a column or declared here.
NON_PROTOCOL = {
    "Language construct",
    "Shape and contract",
    "Configuration source",
    "Trace and diagram",
    "Bundle and export",
    "Question ledger",
    "Rendered document",
    "Query and findings",
    # W42's enumerations. Not protocol rows and not language rows — each is a set the
    # design named that had to carry a support level: Q3's out-of-scope surfaces, F1's
    # deliberately-not-read attributes, and Q4's declared slices.
    "Out of scope for v1 (Q3)",
    "Class-file attributes deliberately not read (F1)",
    "Declared slices (Q4)",
}

# Row label in section 5 -> matrix rows it feeds.
LANGUAGES = ["Java / Kotlin", "Go", "TypeScript", "JavaScript", "Python", "Rust", "Swift"]
ALIASES = {
    "Java": ["Java / Kotlin"],
    "Kotlin": ["Java / Kotlin"],
    "Go": ["Go"],
    "TS": ["TypeScript", "JavaScript"],
    "Python": ["Python"],
    "Rust": ["Rust"],
    "Swift": ["Swift"],
}

# The Java/Kotlin frameworks each protocol section MUST account for — the target list the
# rollup renders, in this order. Declared rather than inferred from the rows, because a
# framework with no row is exactly the thing the rollup exists to show (`✗ unsupported`),
# and an inferred list can never contain one. A row tagged with a framework absent here
# fails the generator (`undeclared_frameworks`): the two are kept in step by refusal.
FRAMEWORKS: dict[str, list[str]] = {
    "REST inbound": [
        "Spring MVC / WebFlux (annotations)",
        "Spring functional routing (MVC + WebFlux, Java + Kotlin DSL)",
        "Spring @HttpExchange (server side)",
        "Spring error handling (@ControllerAdvice)",
        "Spring Boot Actuator",
        "Spring Data REST",
        "Spring Cloud Gateway",
        "Jakarta / javax Servlet",
        "JAX-RS (Quarkus REST, Jersey, RESTEasy, Helidon)",
        "Quarkus Reactive Routes",
        "Micronaut HTTP",
        "Ktor",
        "Javalin",
        "Vert.x Web",
        "Akka HTTP",
        "Helidon SE",
        "Spark Java",
        "Play Framework",
    ],
    "REST outbound": [
        "Spring RestTemplate",
        "RestClient / WebClient / OkHttp (fluent clients)",
        "Feign / Retrofit / @HttpExchange (annotated client interfaces)",
        "Spring @HttpExchange (client registration)",
        "Spring Cloud Gateway (forwarding)",
        "JDK / Apache HttpClient",
        "Micronaut HTTP client",
        "MicroProfile REST Client",
        "Apache Camel",
        "Ktor HttpClient",
        "Vert.x WebClient",
    ],
    "SOAP": [
        "JAX-WS (jakarta.jws / javax.jws)",
        "JAX-WS (Apache CXF)",
        "JAX-WS generated client stubs",
        "Spring Web Services",
    ],
    "GraphQL": [
        "Spring for GraphQL",
        "Netflix DGS",
        "MicroProfile GraphQL",
        "graphql-java (schema-first)",
        "GraphQL Kotlin (Expedia)",
    ],
    "WebSocket": [
        "Spring WebSocket",
        "Spring STOMP",
        "Jakarta / javax WebSocket",
        "Ktor WebSockets",
    ],
    "Server-Sent Events": [
        "Spring MVC",
        "Spring WebFlux",
        "JAX-RS (Quarkus REST, Jersey, RESTEasy, Helidon)",
        "Ktor SSE",
    ],
    "gRPC": [
        "grpc-java",
        "Spring gRPC",
        "net.devh grpc-spring-boot-starter",
        "Quarkus gRPC",
    ],
    "Kafka": [
        "Spring Kafka",
        "kafka-clients (raw)",
        "Kafka Streams",
        "Spring Cloud Stream",
        "Micronaut Kafka",
        "SmallRye Reactive Messaging (Quarkus)",
        "Pekko / Alpakka Connectors Kafka",
    ],
    "JMS and AMQP": [
        "Spring JMS",
        "Spring AMQP (RabbitMQ)",
        "Spring AMQP / Spring JMS templates",
        "Jakarta / javax JMS API (direct)",
        "Spring for Apache Pulsar",
        "Micronaut JMS",
    ],
    "AWS SQS": [
        "Spring Cloud AWS SQS 3.x / 4.x",
        "Spring Cloud AWS 1.x / 2.x (legacy)",
        "AWS SDK v2 (raw)",
        "Micronaut (raw AWS SDK; JMS over SQS)",
    ],
    "Google Cloud Pub/Sub": [
        "Spring Cloud GCP Pub/Sub (PubSubTemplate)",
        "Spring Cloud GCP Pub/Sub (Spring Integration)",
        "google-cloud-pubsub (raw client)",
        "Micronaut GCP Pub/Sub",
    ],
    "Async and internal boundaries": [
        "Spring scheduling (@Scheduled)",
        "Spring Integration",
        "Quartz",
        "Temporal / Cadence",
        "Vert.x EventBus",
        "Akka / Pekko actors",
    ],
}

# Rows whose `Framework` cell is one of these are engine-level or not-applicable rows and
# feed no framework line.
FRAMEWORK_NONE = {"any", "—", ""}

# Open register id -> the framework line(s) it appears under, in the section its
# ```delivery column names. Every id on a protocol column must be here (`unmapped_items`),
# or it would block the row while vanishing from every rollup. Kept in the generator
# rather than in the register because the register is about FEATURES and refuses to know
# frameworks (`test_feature_delivery.py`); this is presentation data.
ITEM_FRAMEWORKS: dict[str, list[str]] = {
    "conditional-controllers": ["Spring MVC / WebFlux (annotations)"],
    "kotlin-null-handler": ["Spring functional routing (MVC + WebFlux, Java + Kotlin DSL)"],
    "dsl-media-route": ["Spring functional routing (MVC + WebFlux, Java + Kotlin DSL)"],
    "ktor-route-extensions": [
        "Ktor",
        "Javalin",
        "Spring functional routing (MVC + WebFlux, Java + Kotlin DSL)",
    ],
    "ktor-selector-blocks": ["Ktor"],
    "gateway-properties-routes": ["Spring Cloud Gateway"],
    "kotlin-class-lambdas": ["Spring functional routing (MVC + WebFlux, Java + Kotlin DSL)"],
    "kotlin-default-bridge-calls": [
        "Spring functional routing (MVC + WebFlux, Java + Kotlin DSL)",
        "Ktor",
    ],
    "apache-camel": ["Apache Camel"],
    "pubsub-channel-adapter": ["Spring Cloud GCP Pub/Sub (Spring Integration)"],
    "smallrye-reactive-messaging": ["SmallRye Reactive Messaging (Quarkus)"],
    "temporal-cadence": ["Temporal / Cadence"],
    "vertx-eventbus": ["Vert.x EventBus"],
}

# Framework FAMILIES — the stack a reader picks — and the framework lines each one owns
# across every protocol. §2c's grid is one row per family, one column per protocol, each
# cell rolled up from the family's lines declared for that protocol; a family with no line
# declared for a protocol reads `—` (nothing to do with it), which is a different fact from
# `✗` (on the target list, nothing shipped). A line may belong to several families — the
# JAX-RS line is Quarkus's, Helidon's and the Jakarta standards' at once — and every line in
# `FRAMEWORKS` must belong to at least one (`orphan_lines`), or the grid would sum it away.
FAMILIES: dict[str, list[str]] = {
    "Spring Boot (Spring MVC / WebFlux, Cloud, Data, Integration, Kafka, AMQP, JMS, GCP, AWS)": [
        "Spring MVC / WebFlux (annotations)",
        "Spring functional routing (MVC + WebFlux, Java + Kotlin DSL)",
        "Spring @HttpExchange (server side)",
        "Spring error handling (@ControllerAdvice)",
        "Spring Boot Actuator",
        "Spring Data REST",
        "Spring Cloud Gateway",
        "Spring RestTemplate",
        "RestClient / WebClient / OkHttp (fluent clients)",
        "Feign / Retrofit / @HttpExchange (annotated client interfaces)",
        "Spring @HttpExchange (client registration)",
        "Spring Cloud Gateway (forwarding)",
        "Spring Web Services",
        "Spring for GraphQL",
        "Spring WebSocket",
        "Spring STOMP",
        "Spring MVC",
        "Spring WebFlux",
        "Spring gRPC",
        "net.devh grpc-spring-boot-starter",
        "Spring Kafka",
        "Spring Cloud Stream",
        "Spring JMS",
        "Spring AMQP (RabbitMQ)",
        "Spring AMQP / Spring JMS templates",
        "Spring for Apache Pulsar",
        "Spring Cloud AWS SQS 3.x / 4.x",
        "Spring Cloud AWS 1.x / 2.x (legacy)",
        "Spring Cloud GCP Pub/Sub (PubSubTemplate)",
        "Spring Cloud GCP Pub/Sub (Spring Integration)",
        "Spring scheduling (@Scheduled)",
        "Spring Integration",
    ],
    "Quarkus (Quarkus REST / JAX-RS, Reactive Routes, MicroProfile, SmallRye, gRPC)": [
        "JAX-RS (Quarkus REST, Jersey, RESTEasy, Helidon)",
        "Quarkus Reactive Routes",
        "MicroProfile REST Client",
        "MicroProfile GraphQL",
        "Quarkus gRPC",
        "SmallRye Reactive Messaging (Quarkus)",
    ],
    "Micronaut": [
        "Micronaut HTTP",
        "Micronaut HTTP client",
        "Micronaut Kafka",
        "Micronaut JMS",
        "Micronaut (raw AWS SDK; JMS over SQS)",
        "Micronaut GCP Pub/Sub",
    ],
    "Ktor": ["Ktor", "Ktor HttpClient", "Ktor WebSockets", "Ktor SSE"],
    "Javalin": ["Javalin"],
    "Vert.x": ["Vert.x Web", "Vert.x WebClient", "Vert.x EventBus"],
    "Helidon (MP via JAX-RS; SE)": [
        "JAX-RS (Quarkus REST, Jersey, RESTEasy, Helidon)",
        "Helidon SE",
    ],
    "Jakarta / Java EE standards (Servlet, JAX-RS, JAX-WS, JMS, WebSocket)": [
        "Jakarta / javax Servlet",
        "JAX-RS (Quarkus REST, Jersey, RESTEasy, Helidon)",
        "JAX-WS (jakarta.jws / javax.jws)",
        "JAX-WS (Apache CXF)",
        "JAX-WS generated client stubs",
        "Jakarta / javax JMS API (direct)",
        "Jakarta / javax WebSocket",
    ],
    "Raw clients and SDKs (JDK/Apache HTTP, kafka-clients, grpc-java, AWS, GCP, graphql-java)": [
        "JDK / Apache HttpClient",
        "kafka-clients (raw)",
        "grpc-java",
        "AWS SDK v2 (raw)",
        "google-cloud-pubsub (raw client)",
        "graphql-java (schema-first)",
    ],
    "Kafka Streams": ["Kafka Streams"],
    "Netflix DGS": ["Netflix DGS"],
    "GraphQL Kotlin (Expedia)": ["GraphQL Kotlin (Expedia)"],
    "Akka / Pekko (HTTP, Connectors, actors)": [
        "Akka HTTP",
        "Pekko / Alpakka Connectors Kafka",
        "Akka / Pekko actors",
    ],
    "Apache Camel": ["Apache Camel"],
    "Temporal / Cadence": ["Temporal / Cadence"],
    "Quartz": ["Quartz"],
    "Play Framework": ["Play Framework"],
    "Spark Java": ["Spark Java"],
}

_ESCAPED_PIPE = re.compile(r"(?<!\\)\|")


def cells_of(line: str) -> list[str]:
    r"""A table row's cells, splitting on unescaped pipes only — `\|` inside a cell is
    markdown's escape and stays in the cell."""
    return [c.strip() for c in _ESCAPED_PIPE.split(line.strip().strip("|"))]


def anchor(heading: str, number: str) -> str:
    slug = re.sub(r"[^a-z0-9 -]", "", f"{number} {heading}".lower()).replace(" ", "-")
    return f"#{slug}"


def classify(cell: str) -> str | None:
    """Reduce a tier cell to one of shipped / A / B / C / na / unknown."""
    text = cell.replace("*", "").replace("`", "").strip()
    if text.startswith("✅"):
        return "shipped"
    # W42's level vocabulary, which a few protocol rows use instead of the glyph (the Kafka
    # Streams row). Before 2026-09-18 these classified as None and were counted nowhere.
    if text.startswith("partially supported"):
        return "partial"
    if text.startswith("supported"):
        return "shipped"
    if text.startswith("◐"):
        return "partial"
    if text.startswith("⚠️"):
        return "unknown"
    if text.startswith("—") or text == "":
        return "na"
    m = re.match(r"([ABC])(?![A-Za-z])", text)
    return m.group(1) if m else None


def classify_rollup(cell: str) -> str | None:
    """`classify`, plus the one class the framework rollup reads and the matrix does not:
    a **stated boundary** — a row whose status begins `Boundary` or `Limitation`. The
    matrix ignores those rows (a boundary is what we cannot see and say so; it costs no
    `✅`). The rollup counts them, because a reader asking "what is Ktor missing?" is owed
    the number of places the answer is "this, and we say so"."""
    text = cell.replace("*", "").replace("`", "").strip()
    if text.startswith(("Boundary", "Limitation")):
        return "boundary"
    return classify(cell)


def parse(md: str) -> tuple[dict, dict]:
    """Return {(language, heading): Counter} and {heading: number}."""
    counts: dict[tuple[str, str], Counter] = {}
    numbers: dict[str, str] = {}
    section = None
    for line in md.splitlines():
        h = re.match(r"### (5\.\d+) (.+)", line)
        if h:
            numbers[h.group(2)] = h.group(1)
            section = h.group(2)
            continue
        if section is None or not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 3 or set(cells[0]) <= {"-", ":"}:
            continue
        lang = cells[0].replace("*", "").strip()
        if lang not in ALIASES:
            continue  # header rows, "Any", and prose rows are skipped by construction
        tier = classify(cells[-1])
        if tier is None:
            continue
        for target in ALIASES[lang]:
            counts.setdefault((target, section), Counter())[tier] += 1
    return counts, numbers


def framework_rows(md: str) -> dict[tuple[str, str], Counter]:
    """{(section heading, framework): Counter of tiers} over the Java/Kotlin rows of every
    protocol section whose table carries a `Framework` column."""
    counts: dict[tuple[str, str], Counter] = {}
    section = None
    framework_col = False
    for line in md.splitlines():
        h = re.match(r"### (5\.\d+) (.+)", line)
        if h:
            section = h.group(2)
            framework_col = False
            continue
        if section is None or section in NON_PROTOCOL or not line.startswith("|"):
            framework_col = framework_col and line.startswith("|")
            continue
        cells = cells_of(line)
        if cells and cells[0] == "Language":
            framework_col = len(cells) > 1 and cells[1] == "Framework"
            continue
        if not framework_col or len(cells) < 4 or set(cells[0]) <= {"-", ":"}:
            continue
        lang = cells[0].replace("*", "").strip()
        if lang not in ("Java", "Kotlin"):
            continue
        framework = cells[1].strip()
        if framework in FRAMEWORK_NONE:
            continue
        tier = classify_rollup(cells[-1])
        if tier is None:
            continue
        counts.setdefault((section, framework), Counter())[tier] += 1
    return counts


def undeclared_frameworks(md: str) -> list[str]:
    """Java/Kotlin rows tagged with a framework the section's target list does not name."""
    found = []
    for (section, framework), _c in sorted(framework_rows(md).items()):
        if framework not in FRAMEWORKS.get(section, []):
            found.append(f"{section}: `{framework}`")
    return found


def open_items() -> dict[str, list[str]]:
    """`COVERAGE column -> open ids`, from the register's ```delivery block."""
    delivery = DOC.parent / "java-kotlin-delivery-list.md"
    if not delivery.exists():
        return {}
    match = re.search(r"```delivery\n(.*?)```", delivery.read_text(), re.DOTALL)
    if match is None:
        return {}
    items: dict[str, list[str]] = {}
    for line in match.group(1).split("\n"):
        if not line.strip():
            continue
        _, column, blockers = (part.strip() for part in line.split("|"))
        items[column] = blockers.split()
    return items


def unmapped_items() -> list[str]:
    """Open ids on a protocol column that `ITEM_FRAMEWORKS` cannot place, or places under a
    framework the column's section does not declare."""
    label_to_heading = {label: heading for heading, label in HTTP_COLUMNS + MSG_COLUMNS}
    found = []
    for column, ids in open_items().items():
        heading = label_to_heading.get(column)
        if heading is None:
            continue  # the register's non-protocol rows (Meridian) roll up nowhere
        for item in ids:
            frameworks = ITEM_FRAMEWORKS.get(item)
            if not frameworks:
                found.append(f"{column}: `{item}` is mapped to no framework")
                continue
            for framework in frameworks:
                if framework not in FRAMEWORKS[heading]:
                    found.append(
                        f"{column}: `{item}` -> `{framework}` is not declared for {heading}"
                    )
    return found


def rollup_status(c: Counter, items: list[str]) -> tuple[str, str]:
    """(status glyph, what is missing) for one framework line.

        ✅ full          every row shipped, no open register id (stated boundaries allowed, and counted)
        ◐ partial       rows not shipped (by tier), limited rows, open ids — whichever apply
        ✗ unsupported   the target list names it and no row exists

    A row marked `—` (not applicable) or `⚠️` is neither shipped nor missing here. `Rows
    shipped` counts rows that claim a tier or a glyph; boundary rows are counted apart.
    """
    live = c - Counter({"na": c["na"], "unknown": c["unknown"]})
    if not live:
        return "✗ unsupported", "no row yet"
    missing: list[str] = []
    gaps = ", ".join(f"{c[t]} at {t}" for t in "ABC" if c[t])
    if gaps:
        missing.append(f"not shipped: {gaps}")
    if c["partial"]:
        missing.append(f"{c['partial']} limited")
    if items:
        missing.append(", ".join(f"`{item}`" for item in items))
    # A stated boundary costs no `✅` (COVERAGE §1: a boundary is what we cannot see AND
    # say so), but the count is part of the honest answer, so it is shown either way.
    boundaries = (
        f"{c['boundary']} stated boundar{'ies' if c['boundary'] > 1 else 'y'}"
        if c["boundary"]
        else ""
    )
    if not missing:
        return "✅ full", boundaries or "—"
    return "◐ partial", "; ".join([*missing, *([boundaries] if boundaries else [])])


def render_rollup(heading: str, number: str, counts: dict[tuple[str, str], Counter]) -> str:
    label = {h: lbl for h, lbl in HTTP_COLUMNS + MSG_COLUMNS}[heading]
    open_by_framework: dict[str, list[str]] = {}
    for item in open_items().get(label, []):
        for framework in ITEM_FRAMEWORKS.get(item, []):
            open_by_framework.setdefault(framework, []).append(item)
    lines = [
        f"<!-- BEGIN GENERATED: frameworks {number} -->",
        (
            "**Java / Kotlin, by framework** — rolled up from the rows below and the register's "
            "open ids by `scripts/coverage_matrix.py`; do not edit by hand. `✅ full`: every row "
            "shipped and no open id. `◐ partial`: the last column says what is missing. "
            "`✗ unsupported`: on the target list, no row yet."
        ),
        "",
        "| Framework | Status | Rows shipped | Missing |",
        "|---|---|---|---|",
    ]
    for framework in FRAMEWORKS[heading]:
        c = counts.get((heading, framework), Counter())
        status, missing = rollup_status(c, open_by_framework.get(framework, []))
        total = sum(v for k, v in c.items() if k not in ("na", "unknown", "boundary"))
        lines.append(f"| {framework} | {status} | {c['shipped']}/{total} | {missing} |")
    lines.append(f"<!-- END GENERATED: frameworks {number} -->")
    return "\n".join(lines)


def with_rollups(md: str) -> str:
    """The document with every protocol section's rollup block regenerated, or inserted
    directly under the heading where none exists yet."""
    counts = framework_rows(md)
    _, numbers = parse(md)
    new = md
    for heading, _label in HTTP_COLUMNS + MSG_COLUMNS:
        number = numbers[heading]
        block = render_rollup(heading, number, counts)
        begin = f"<!-- BEGIN GENERATED: frameworks {number} -->"
        end = f"<!-- END GENERATED: frameworks {number} -->"
        if begin in new:
            start = new.index(begin)
            stop = new.index(end, start) + len(end)
            new = new[:start] + block + new[stop:]
        else:
            heading_line = f"### {number} {heading}\n"
            at = new.index(heading_line) + len(heading_line)
            new = new[:at] + "\n" + block + "\n" + new[at:]
    return new


def orphan_lines() -> list[str]:
    """Framework lines declared in `FRAMEWORKS` that no family owns — §2c would sum them away."""
    owned = {line for lines in FAMILIES.values() for line in lines}
    return sorted({line for lines in FRAMEWORKS.values() for line in lines} - owned)


def grid_cell(
    heading: str, family_lines: list[str], counts, open_by_line: dict[str, list[str]]
) -> str:
    """One §2c cell: the family's lines declared for this protocol, rolled up.

    ✅            every line full
    ◐ (…)        the bracket: N open ids · N rows not shipped · N limited · N lines unsupported
    ✗            every declared line unsupported (on the list, nothing shipped)
    —            the family declares no line for this protocol
    """
    lines = [line for line in FRAMEWORKS[heading] if line in family_lines]
    if not lines:
        return "—"
    statuses = []
    open_ids: list[str] = []
    not_shipped = limited = unsupported = 0
    for line in lines:
        c = counts.get((heading, line), Counter())
        status, _missing = rollup_status(c, open_by_line.get(line, []))
        statuses.append(status)
        open_ids.extend(i for i in open_by_line.get(line, []) if i not in open_ids)
        not_shipped += sum(c[t] for t in "ABC")
        limited += c["partial"]
        unsupported += status == "✗ unsupported"
    if all(st == "✅ full" for st in statuses):
        return "✅"
    if all(st == "✗ unsupported" for st in statuses):
        return "✗"
    parts = []
    if open_ids:
        parts.append(f"{len(open_ids)} open")
    if not_shipped:
        parts.append(f"{not_shipped} not shipped")
    if limited:
        parts.append(f"{limited} limited")
    if unsupported:
        parts.append(f"{unsupported} line{'s' if unsupported > 1 else ''} unsupported")
    return f"◐ ({', '.join(parts)})" if parts else "◐"


def render_grid(counts, numbers) -> str:
    """§2c — Java / Kotlin, framework family × protocol."""
    columns = HTTP_COLUMNS + MSG_COLUMNS
    open_by_line: dict[str, list[str]] = {}
    for ids in open_items().values():
        for item in ids:
            for line in ITEM_FRAMEWORKS.get(item, []):
                open_by_line.setdefault(line, []).append(item)
    head = ["Framework family"] + [f"[{label}]({anchor(h, numbers[h])})" for h, label in columns]
    out = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for family, lines in FAMILIES.items():
        row = [f"**{family}**"] + [
            grid_cell(h, lines, counts, open_by_line) for h, _label in columns
        ]
        out.append("| " + " | ".join(row) + " |")
    return "\n".join(out)


def open_blockers() -> dict[str, int]:
    """`COVERAGE column -> open blocker count`, from `java-kotlin-delivery-list.md`.

    **Why the matrix reads a second document.** A cell's counters answer *how many
    libraries are catalogued*, and for a week `✅` was written from that alone — so SOAP,
    GraphQL and WebSocket all read "shipped, nothing outstanding" while each carried an
    open Major inside a library that WAS catalogued. The word in the legend is
    "outstanding", and a defect is outstanding; nothing in these counters can see one.

    Read for the Java/Kotlin row only, which is the row that register covers.
    """
    import re as _re

    delivery = DOC.parent / "java-kotlin-delivery-list.md"
    if not delivery.exists():
        return {}
    match = _re.search(r"```delivery\n(.*?)```", delivery.read_text(), _re.DOTALL)
    if match is None:
        return {}
    counts: dict[str, int] = {}
    for line in match.group(1).split("\n"):
        if not line.strip():
            continue
        _, column, blockers = (part.strip() for part in line.split("|"))
        counts[column] = len(blockers.split())
    return counts


def cell(c: Counter | None, blocked: int = 0) -> str:
    """One matrix cell, in a notation a reader can take at face value.

        ✅                        shipped, nothing outstanding
        ◐ (2 limited)             every library catalogued, 2 with stated limits
        ◐ (4A 3B 4C)              4+3+4 libraries not catalogued at all
        ◐ (2 limited, 4A 3B 4C)   both
        4A 3B                     nothing shipped, these outstanding
        —                         not applicable to this language
        ·                         not enumerated in §5 yet

    **`◐` can never appear alone**, and that is a rule rather than an accident of
    the data: a partial cell is one with something missing, so the bracket carries
    whichever kind of incompleteness caused the glyph. A row that is itself
    partial — "shipped, narrower than the framework's rule" — counts as `limited`;
    a library nobody has catalogued counts in its tier.

    **What this replaces, and why it was wrong.** The lead used to be
    `"◐ " if c["partial"] or c["shipped"]`, which collapsed two different states
    into one glyph: a cell with every row shipped rendered `◐ —` exactly like a
    cell with partial rows. Three Java cells — SOAP, GraphQL, WebSocket — are
    7/7, 5/5 and 3/3 shipped with no gaps at any tier, and all three read `◐ —`.
    The file then carried a paragraph telling readers to take `◐ —` as "the
    stronger of the two markings, not the weaker", which is a defect report
    written as a legend: `◐` is a half-filled circle and reads as half-done to
    anyone, and `—` reads as not-applicable to anyone, so the pair read as
    neither of the things it meant.

    The information needed to write `✅` was in the counter the whole time and
    was thrown away one line before it was used.
    """
    if not c:
        return "·"  # no rows in section 5 at all: not yet enumerated, not known-absent
    if not (c - Counter({"na": c["na"], "unknown": c["unknown"]})):
        return "⚠️" if c["unknown"] else "—"
    tail = " ⚠️" if c["unknown"] else ""
    gaps = " ".join(f"{c[t]}{t}" for t in "ABC" if c[t])
    if not (c["partial"] or c["shipped"]):
        # Nothing shipped: the tiers stand alone, unbracketed, because there is
        # no shipped half for them to qualify.
        return f"{gaps}{tail}"
    if not c["partial"] and not gaps:
        # Every library catalogued — but `✅` claims nothing outstanding, and an open
        # Critical or Major is outstanding. `tests/architecture/test_feature_delivery.py`
        # enforces the same rule from the other side.
        if blocked:
            return f"◐ ({blocked} open){tail}"
        return f"✅{tail}"
    if blocked:
        missing = [f"{c['partial']} limited"] if c["partial"] else []
        if gaps:
            missing.append(gaps)
        missing.append(f"{blocked} open")
        return f"◐ ({', '.join(missing)}){tail}"
    missing = [f"{c['partial']} limited"] if c["partial"] else []
    if gaps:
        missing.append(gaps)
    return f"◐ ({', '.join(missing)}){tail}"


def render(counts, numbers, columns, first_col=None) -> str:
    head = ["Language"] + ([first_col] if first_col else [])
    head += [f"[{label}]({anchor(h, numbers[h])})" for h, label in columns]
    out = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for lang in LANGUAGES:
        row = [f"**{lang}**"]
        if first_col:
            row.append("✅ ASM" if lang == "Java / Kotlin" else "none")
        blocked = open_blockers() if lang == "Java / Kotlin" else {}
        row += [cell(counts.get((lang, h)), blocked.get(label, 0)) for h, label in columns]
        out.append("| " + " | ".join(row) + " |")
    return "\n".join(out)


def unwired(numbers: dict[str, str]) -> list[str]:
    """Section 5 headings that feed no matrix column and are not declared non-protocol.

    Half the check: `render` iterates the column lists, so a heading missing from them
    produces no output and no error. Before this, adding `### 5.13 gRPC-Web` would have
    left §2 silently unchanged and the matrices quietly wrong about what §5 holds.
    """
    wired = {heading for heading, _label in HTTP_COLUMNS + MSG_COLUMNS}
    return sorted(set(numbers) - wired - NON_PROTOCOL)


def misfiled(md: str) -> list[str]:
    """Rows in a NON_PROTOCOL section whose first cell names a language.

    The OTHER half, and the one the first version claimed and did not have. `parse` counts
    a row by its first cell wherever that cell is in `ALIASES`, and it does that in every
    `### 5.x` section including the non-protocol ones — so a row written `| Java | some
    Kotlin construct | … |` under §5.13 is counted into a cell §2 has no column for, and
    `render` drops it on the floor. Declaring the SECTION non-protocol does not stop that;
    only looking at the row does.

    Found by W41's own review, which added such a row and watched `--check` print
    "matrices are current" while the row vanished.
    """
    section = None
    found: list[str] = []
    for number, line in enumerate(md.splitlines(), start=1):
        heading = re.match(r"### (5\.\d+) (.+)", line)
        if heading:
            section = heading.group(2)
            continue
        if section not in NON_PROTOCOL or not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 3 or set(cells[0]) <= {"-", ":"}:
            continue
        language = cells[0].replace("*", "").strip()
        if language in ALIASES:
            found.append(f"{number}: {section} — first cell is `{language}`")
    return found


def main() -> int:
    md = DOC.read_text()
    counts, numbers = parse(md)
    orphans = unwired(numbers)
    if orphans:
        print(
            "section 5 headings with no matrix column and no NON_PROTOCOL declaration: "
            + ", ".join(orphans),
            file=sys.stderr,
        )
        return 1
    stray = misfiled(md)
    if stray:
        print(
            "rows in a non-protocol section whose first cell names a language — they are "
            "counted into a matrix cell that has no column and are then dropped:\n  "
            + "\n  ".join(stray),
            file=sys.stderr,
        )
        return 1
    untagged = undeclared_frameworks(md)
    if untagged:
        print(
            "Java/Kotlin rows tagged with a framework the section's FRAMEWORKS list does not "
            "declare — declare it, or retag the row:\n  " + "\n  ".join(untagged),
            file=sys.stderr,
        )
        return 1
    homeless = unmapped_items()
    if homeless:
        print(
            "open register ids the rollup cannot place under a framework (ITEM_FRAMEWORKS):\n  "
            + "\n  ".join(homeless),
            file=sys.stderr,
        )
        return 1
    orphans_2c = orphan_lines()
    if orphans_2c:
        print(
            "framework lines no FAMILIES entry owns — §2c would sum them away:\n  "
            + "\n  ".join(orphans_2c),
            file=sys.stderr,
        )
        return 1
    http = render(counts, numbers, HTTP_COLUMNS, first_col="Scanner")
    msg = render(counts, numbers, MSG_COLUMNS)
    grid = render_grid(framework_rows(md), numbers)

    new = with_rollups(md)
    for marker, table in (
        ("2a. Application protocols over HTTP", http),
        ("2b. Messaging and RPC", msg),
    ):
        start = new.index(f"### {marker}")
        tbl_start = new.index("| Language", start)
        tbl_end = new.index("\n\n", tbl_start)
        new = new[:tbl_start] + table + new[tbl_end:]
    grid_marker = "### 2c. Java / Kotlin — framework family × protocol"
    start = new.index(grid_marker)
    tbl_start = new.index("| Framework family", start)
    tbl_end = new.index("\n\n", tbl_start)
    new = new[:tbl_start] + grid + new[tbl_end:]

    if "--check" in sys.argv:
        print("matrices are current" if new == md else "STALE — rerun without --check")
        return 0 if new == md else 1
    DOC.write_text(new)
    print(f"regenerated from {sum(sum(c.values()) for c in counts.values())} checklist rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
