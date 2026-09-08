"""W13 — what binds when a Spring Cloud Stream application declares more than
one function bean, and what a binder nobody mapped is spoken over (F2 §3.4).

Two questions, and the second is the one whose wrong answer leaves this bundle
and lands in another consumer's data:

1. **Cardinality.** `spring-cloud-stream.yml` says that when the selection key is
   absent, "every candidate binds — the framework's own default". Is it? The
   framework's own normalisation code is the answer, read verbatim out of the
   sources jar, which is CP-17's convention for a rule that is an ALGORITHM.
2. **The protocol default.** A binder name absent from `binder_protocols` leaves
   the row on the catalog's declared `protocol:`. Protocol is IDENTITY — DR-5
   gates linking on protocol equality — so a defaulted one does not merely
   under-report here, it merges rows in a consumer's graph that name different
   wires.

Both are then asked of Sextant itself, by running the real derivation.
"""

import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "src"))

from sextant.application.ports.catalogs import Catalog
from sextant.application.resolve.endpoints import derive_endpoints
from sextant.application.resolve.open_questions import reset_open_questions
from sextant.application.resolve.service_identity import record_service_identity_gaps
from sextant.domain.closed_sets import ConstructKind, OriginTier
from sextant.domain.factfile import write_fact_file
from sextant.domain.facts import (
    Document,
    ModuleFact,
    Signature,
    SymbolFact,
    TypeRef,
)
from sextant.ingress.catalogs.yaml_source import YamlCatalogSource
from sextant.storage.duckdb.workspace import DuckDbWorkspace

CATALOGS = REPO / "src" / "sextant" / "catalogs"
M2 = Path.home() / ".m2" / "repository"

ARTIFACT = "org.springframework.cloud:spring-cloud-function-context:4.1.2"
# The class and method that decide a default when no definition is configured.
NORMALISER = "org/springframework/cloud/function/context/catalog/SimpleFunctionRegistry.java"


class ProbeError(RuntimeError):
    """Something the run could not establish. ABORTS rather than warning."""


def resolve(artifact: str, classifier: str | None = None) -> Path:
    group, name, version = artifact.split(":")
    tail = f"-{classifier}" if classifier else ""
    jar = M2 / Path(group.replace(".", "/")) / name / version / f"{name}-{version}{tail}.jar"
    if not jar.is_file():
        target = f"{artifact}:jar:{classifier}" if classifier else artifact
        subprocess.run(
            ["mvn", "-q", "-B", "dependency:get", "-Dtransitive=false", f"-Dartifact={target}"],
            cwd=REPO,
            capture_output=True,
            check=False,
        )
    if not jar.is_file():
        raise ProbeError(
            f"{artifact}{tail} did not resolve. Fix the coordinate in run.sh rather than "
            f"leaving the row unmeasured."
        )
    return jar


def self_reported_version(jar: Path) -> tuple[str, str]:
    """The version the ARCHIVE states for itself, and where it states it.

    Raises rather than defaulting: a missing self-report is exactly where a
    hand-written column would go unchallenged (CP-5)."""
    with zipfile.ZipFile(jar) as archive:
        entries = [
            name
            for name in archive.namelist()
            if name.startswith("META-INF/maven/") and name.endswith("/pom.properties")
        ]
        if entries:
            for line in archive.read(entries[0]).decode("utf-8", "replace").splitlines():
                if line.strip().startswith("version="):
                    return line.split("=", 1)[1].strip(), "pom.properties"
        try:
            manifest = archive.read("META-INF/MANIFEST.MF").decode("utf-8", "replace")
        except KeyError as missing:
            raise ProbeError(f"{jar.name} reports no version of its own") from missing
    for line in manifest.splitlines():
        if line.lower().startswith("implementation-version:"):
            return line.split(":", 1)[1].strip(), "MANIFEST.MF"
    raise ProbeError(f"{jar.name} states no version in its pom.properties or its manifest")


def checked(artifact: str, classifier: str | None = None) -> tuple[Path, str, str]:
    jar = resolve(artifact, classifier)
    reported, source = self_reported_version(jar)
    requested = artifact.split(":")[2]
    if reported != requested:
        raise ProbeError(
            f"{jar.name} reports {reported!r} in its own {source} while the coordinate asked "
            f"for {requested!r}. Fix run.sh rather than labelling a column with a version "
            f"this run did not read."
        )
    return jar, reported, source


def normalisation_rule(sources: Path) -> str:
    """The framework's own default-selection code, verbatim.

    Verbatim because the rule is an ALGORITHM and a paraphrase of one is a
    prediction (CP-17's convention, and §8.1's). The `if` is the whole answer:
    what it tests decides whether a lone function binds by default and whether
    several do."""
    with zipfile.ZipFile(sources) as archive:
        try:
            text = archive.read(NORMALISER).decode("utf-8", "replace")
        except KeyError as missing:
            raise ProbeError(
                f"{sources.name} does not carry {NORMALISER}. Fix the path or the coordinate "
                f"rather than reading its absence as an answer."
            ) from missing
    body = re.search(r"(\s*if \(eligibleFunction\.size\(\).*?\n\s*\}\n)", text, re.DOTALL)
    if body is None:
        raise ProbeError(
            f"{sources.name}'s {NORMALISER.rsplit('/', 1)[-1]} no longer contains the "
            f"`eligibleFunction.size()` branch this probe reads. Re-read the class and "
            f"re-anchor rather than reporting the old answer."
        )
    return " ".join(body.group(1).split())


# --- what Sextant derives -------------------------------------------------

_MODULE = "sextant-jvm maven com.acme/orders-service 1.0.0 "
_DOC = Document(
    document_id="doc_1",
    relative_path="com/acme/Streams.java",
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
_CONFIG_DOC = Document(
    document_id="doc_cfg",
    relative_path="application.yml",
    module_id="com.acme:orders-service",
    language="yaml",
    sextant_version="0.1.0",
    fact_schema_version=2,
    scanner_id="yaml",
    content_hash="sha256:c",
    origin_entry="src/main/resources",
    origin_tier=OriginTier.MODULE_OUTPUT,
    redaction_set_hash="sha256:b",
)
CAPABILITIES = {"resolved_config", "typed_signatures", "implemented_interfaces"}


def function_facts(beans: tuple[str, ...]) -> list:
    """One `@Bean`-shaped declared method per name, each returning
    `java.util.function.Consumer` — the shape `spring-cloud-stream.yml`'s
    `when.implements` rule matches."""
    owner = _MODULE + "com/acme/Streams#"
    facts: list = [
        SymbolFact(document_id="doc_1", symbol=owner, construct_kind=ConstructKind.CLASS)
    ]
    for name in beans:
        facts.append(
            SymbolFact(
                document_id="doc_1",
                symbol=f"{owner}{name}(sig_{name}).",
                construct_kind=ConstructKind.METHOD,
                enclosing=owner,
                signature=Signature(
                    parameters=[],
                    returns=TypeRef(symbol="java/util/function/Consumer#"),
                ),
            )
        )
    return facts


def stage_config(workspace: DuckDbWorkspace, entries: dict[str, str]) -> None:
    """`resolved_config` rows written directly, the way the shipped
    `config_join` tests stage them.

    Directly rather than through `resolve_config`: that pass layers profiles and
    substitutes placeholders, which is a different subject from the two questions
    here, and staging the resolved rows is what the engine actually reads."""
    workspace.derive(
        "resolved_config_insert",
        rows=[
            {
                "key": key,
                "value": value,
                "source": "application.yml",
                "environment": None,
                "unresolved_reason": None,
            }
            for key, value in entries.items()
        ],
    )


def module_fact(root: Path) -> None:
    """The build declaration `resolve/dependencies.py` reads. `spring-cloud-stream.yml`
    is dependency-gated (`detect.coordinates`), so without this the catalog is
    SKIPPED and every row below would read zero for a reason that has nothing to
    do with the questions asked here."""
    write_fact_file(
        root / "module.jsonl",
        Document(
            document_id="doc_module",
            relative_path="pom.xml",
            module_id="com.acme:orders-service",
            language="java",
            sextant_version="0.1.0",
            fact_schema_version=2,
            scanner_id="asm",
            content_hash="sha256:module",
            origin_entry="target/classes",
            origin_tier=OriginTier.MODULE_OUTPUT,
            redaction_set_hash="sha256:none",
        ),
        [
            ModuleFact(
                document_id="doc_module",
                module_id="com.acme:orders-service",
                module_kind="service",
                languages=["java"],
                source_roots=["src/main/java"],
                output_dirs=["target/classes"],
                dependency_coordinates=["org.springframework.cloud:spring-cloud-stream"],
            )
        ],
    )


def catalog(catalog_id: str) -> Catalog:
    found = next((c for c in YamlCatalogSource(CATALOGS).load() if c.id == catalog_id), None)
    if found is None:
        raise ProbeError(f"no shipped catalog has id {catalog_id!r}")
    return found


def derived(beans: tuple[str, ...], entries: dict[str, str]) -> tuple[list[dict], list[dict]]:
    with tempfile.TemporaryDirectory() as into:
        root = Path(into)
        write_fact_file(root / "facts" / "Streams.jsonl", _DOC, function_facts(beans))
        module_fact(root / "facts")
        workspace = DuckDbWorkspace(root / "ws.duckdb")
        workspace.load_facts(root / "facts")
        stage_config(workspace, entries)
        skipped = derive_endpoints(
            workspace, [catalog("spring-cloud-stream")], capabilities=CAPABILITIES
        )
        if skipped:
            raise ProbeError(
                f"the catalog was SKIPPED ({skipped[0].missing_capabilities}), so every row "
                f"would read zero for a reason unrelated to the question asked."
            )
        # The question ledger is emptied once per resolve and every `gaps`
        # writer runs AFTER that reset, from the pipeline's own seam — never
        # inside `derive_endpoints`. Calling both here is what makes the
        # `questions` column measure anything at all; without the seam it read
        # zero for every row, including the one whose whole point is a question.
        reset_open_questions(workspace)
        record_service_identity_gaps(workspace, [catalog("spring-cloud-stream")])
        rows = workspace.query("endpoints")
        questions = workspace.query("open_questions")
        workspace.close()
    return rows, questions


def main() -> None:
    print("## Observations\n")
    print(
        "Verbatim from `scripts/probes/w13_stream_binding/run.sh`, which runs `sweep.py`. "
        "**The version below is the one the JAR itself reported** — and **not the version "
        "the coordinate list asked for**; `sweep.py` compares the two and ABORTS when they "
        "disagree, rather than printing a version it did not read.\n"
    )
    jar, version, source = checked(ARTIFACT)
    sources = resolve(ARTIFACT, "sources")

    print(f"| what the run read | {version} |")
    print("|---|---|")
    print(f"| artifact reporting this version | {jar.name.rsplit('-', 1)[0]} |")
    print(f"| where the jar states that version | {source} |")
    print(f"| class the rule was read from | `{NORMALISER.rsplit('/', 1)[-1]}` |")
    print()

    print("### 1. The framework's own rule, verbatim\n")
    print("| what decides the default function | the code |")
    print("|---|---|")
    print(f"| `normalizeFunctionDefinition` | `{normalisation_rule(sources)}` |")
    print()

    print("### 2. What Sextant derives, per shape (`spring-cloud-stream.yml`)\n")
    print(
        "| function beans | `spring.cloud.function.definition` | binder | rows | paths | questions |"
    )
    print("|---|---|---|---|---|---|")
    for beans, definition, binder in (
        (("orders",), None, "kafka"),
        (("orders", "payments"), None, "kafka"),
        (("orders", "payments"), "orders", "kafka"),
        (("orders",), None, "rocketmq"),
    ):
        entries: dict[str, str] = {}
        if definition is not None:
            entries["spring.cloud.function.definition"] = definition
        entries["spring.cloud.stream.default-binder"] = binder
        # A destination per bean, so the rows carry a real address rather than
        # NULL: the questions here are "how many rows" and "on what protocol",
        # and an address of NULL makes both harder to read for no reason.
        for bean in beans:
            entries[f"spring.cloud.stream.bindings.{bean}-in-0.destination"] = f"{bean}.topic"
        rows, questions = derived(beans, entries)
        paths = ", ".join(sorted(f"`{r['protocol']}:{r['path']}`" for r in rows)) or "—"
        print(
            f"| {', '.join(f'`{b}`' for b in beans)} | {f'`{definition}`' if definition else '—'} "
            f"| `{binder}` | {len(rows)} | {paths} | {len(questions)} |"
        )


if __name__ == "__main__":
    try:
        main()
    except ProbeError as error:
        print(f"W13 ABORTED: {error}", file=sys.stderr)
        raise SystemExit(1) from error
