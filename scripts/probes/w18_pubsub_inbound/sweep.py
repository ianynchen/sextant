"""W18 — which `PubSubTemplate` methods consume, and which does the catalog read?
(F2 §3.9.)

`spring-pubsub.yml` read ONE inbound method. §3.9 says the class declares ten, so
every pull-based consumer in the estate derived nothing at all — not a partial row
and not a question, but silence, which a reader takes for "this module consumes no
Pub/Sub".

Three questions, and the first is asked of the JAR rather than of the design, so
that the count is generated and a release adding an eleventh method changes this
table rather than going unnoticed:

1. **Which methods take a subscription name?** Enumerated from the class's own
   declared methods — every one whose first parameter is a `String` — then split
   into consuming and publishing by a NAME-PREFIX test this file states
   (`_CONSUMING_PREFIXES`). The enumeration is the jar's; the split is a rule
   written here, and both halves are said plainly because the count "ten" is only
   as good as the weaker one. What that costs: a future `receive(String, …)` would
   be enumerated and then labelled `no (publishes)` — a wrong label rather than an
   omission — and an overload taking a `ProjectSubscriptionName` instead of a
   `String` would not be enumerated at all. Neither is true at 5.1.2, where every
   prefix-matching method really does consume and `ack`/`nack`/`modifyAckDeadline`
   take a `Collection` rather than a name.
2. **Which of them does the shipped catalog declare?** Read off
   `src/sextant/catalogs/spring-pubsub.yml` as loaded, not as written, so a row
   present in the file but rejected by the loader counts as absent.
3. **What does each actually derive?** By building the call each method would
   appear as and running the real derivation — so "reads one of ten" is a
   measurement of output rather than a reading of the catalog.

**Why every `pull*` is a boundary and `Subscriber.newBuilder` is not** (GUIDELINES
§8.6): the `pull*` call IS the consumption, so a trace reaching it is the whole
chain and there is no later terminal to require. Construction of a `Subscriber`
subscribes to nothing, and stays a separate question for
`google-pubsub-subscriber.yml`.
"""

from __future__ import annotations

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
from sextant.domain.closed_sets import ConstructKind, OriginTier
from sextant.domain.factfile import write_fact_file
from sextant.domain.facts import (
    CallArgument,
    CallSiteFact,
    CallTarget,
    Document,
    Signature,
    SymbolFact,
    TypeRef,
)
from sextant.ingress.catalogs.yaml_source import YamlCatalogSource
from sextant.storage.duckdb.workspace import DuckDbWorkspace

M2 = Path.home() / ".m2" / "repository"
CATALOGS = REPO / "src" / "sextant" / "catalogs"

ARTIFACT = "com.google.cloud:spring-cloud-gcp-pubsub"
VERSION = "5.1.2"
TEMPLATE = "com.google.cloud.spring.pubsub.core.PubSubTemplate"
OWNER = "com/google/cloud/spring/pubsub/core/PubSubTemplate#"
CATALOG_ID = "spring-pubsub"

# One `javap -s` signature line and the `descriptor:` line under it.
_SIGNATURE = re.compile(r"^\s+public\s+(?:<\w+>\s+)?(.+?)\s+(\w+)\((.*)\);\s*$")
_DESCRIPTOR = re.compile(r"^\s+descriptor:\s+(\S+)\s*$")

# A method whose name begins with one of these CONSUMES; `publish` does not. Kept
# as a prefix test rather than a list of the ten, so an eleventh method named in
# the same family appears in the table by itself.
_CONSUMING_PREFIXES = ("subscribe", "pull")


class ProbeError(RuntimeError):
    """A run that could not answer, told apart from a run that answered `no`."""


def jar() -> Path:
    group, name = ARTIFACT.split(":")
    found = M2 / group.replace(".", "/") / name / VERSION / f"{name}-{VERSION}.jar"
    if not found.exists():
        raise ProbeError(f"{found} is absent; `run.sh` resolves it — run this through run.sh")
    return found


def self_reported_version(archive: Path) -> str:
    """The version the jar's own manifest claims (§5.4)."""
    with zipfile.ZipFile(archive) as zf:
        try:
            manifest = zf.read("META-INF/MANIFEST.MF").decode("utf-8", "replace")
        except KeyError:
            return "no manifest"
    for line in manifest.splitlines():
        if line.startswith("Implementation-Version:"):
            return line.split(":", 1)[1].strip()
    return "manifest states no version"


def declared_methods(archive: Path) -> list[tuple[str, str, str]]:
    """`(name, descriptor, java signature)` for every public method the class
    declares, read out of the jar rather than from any list here."""
    result = subprocess.run(
        ["javap", "-p", "-s", "-cp", str(archive), TEMPLATE],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise ProbeError(f"javap failed on {TEMPLATE}:\n{result.stderr}")
    found: list[tuple[str, str, str]] = []
    pending: tuple[str, str] | None = None
    for line in result.stdout.splitlines():
        signature = _SIGNATURE.match(line)
        if signature is not None:
            returns, name, parameters = signature.groups()
            pending = (name, f"{returns} {name}({parameters})")
            continue
        descriptor = _DESCRIPTOR.match(line)
        if descriptor is not None and pending is not None:
            found.append((pending[0], descriptor.group(1), pending[1]))
            pending = None
    if not found:
        raise ProbeError(f"javap printed no method descriptors for {TEMPLATE}")
    return found


def takes_a_subscription(descriptor: str) -> bool:
    """Whether argument 0 is a `String` — the position every method in this family
    puts the subscription (or topic) name at."""
    return descriptor.startswith("(Ljava/lang/String;")


def catalog() -> Catalog:
    found = next((c for c in YamlCatalogSource(CATALOGS).load() if c.id == CATALOG_ID), None)
    if found is None:
        raise ProbeError(f"no shipped catalog has id {CATALOG_ID!r}")
    return found


def derived(calls: list[tuple[str, str, int]]) -> list[dict]:
    """The rows the shipped catalog derives for one call to each method.

    Real facts through the real engine: the question "does the catalog read this
    method" is a question about OUTPUT, and reading the catalog to answer it is how
    §3.9's own count came to be stated without being run."""
    document = Document(
        document_id="d1",
        relative_path="com/acme/Puller.java",
        module_id="com.acme:orders",
        language="java",
        sextant_version="0.1.0",
        fact_schema_version=2,
        scanner_id="asm",
        content_hash="sha256:a",
        origin_entry="target/classes",
        origin_tier=OriginTier.MODULE_OUTPUT,
        redaction_set_hash="sha256:b",
    )
    facts: list[object] = []
    for ordinal, (name, descriptor, arity) in enumerate(calls):
        caller = f"com/acme/Puller#call{ordinal}()."
        facts.append(
            SymbolFact(
                document_id="d1",
                symbol=caller,
                construct_kind=ConstructKind.METHOD,
                signature=Signature(parameters=[], returns=TypeRef(symbol="V")),
            )
        )
        arguments = [CallArgument(kind="string", value=f"sub-{name}")]
        arguments += [CallArgument(kind="parameter", value=p) for p in range(1, arity)]
        facts.append(
            CallSiteFact(
                document_id="d1",
                caller=caller,
                target=CallTarget(owner=OWNER, name=name, descriptor=descriptor),
                invoke_kind="virtual",
                ordinal=ordinal,
                arguments=arguments,
            )
        )
    with tempfile.TemporaryDirectory() as into:
        root = Path(into)
        write_fact_file(root / "facts" / "Puller.jsonl", document, facts)
        workspace = DuckDbWorkspace(root / "ws.duckdb")
        workspace.load_facts(root / "facts")
        derive_endpoints(workspace, [catalog()], capabilities={"call_site", "string_constants"})
        rows = workspace.query("endpoints")
        workspace.close()
    return rows


def arity_of(descriptor: str) -> int:
    """Parameter count, from the descriptor's own argument list."""
    arguments = descriptor[1 : descriptor.index(")")]
    count, index = 0, 0
    while index < len(arguments):
        while arguments[index] == "[":
            index += 1
        if arguments[index] == "L":
            index = arguments.index(";", index) + 1
        else:
            index += 1
        count += 1
    return count


def main() -> None:
    archive = jar()
    claimed = self_reported_version(archive)
    if claimed != VERSION:
        raise ProbeError(
            f"{archive} was requested as {VERSION} and its own manifest claims {claimed!r}. "
            f"Every cell below would be filed under a version the artifact did not report."
        )

    print("## Observations\n")
    print(
        "Generated by `scripts/probes/w18_pubsub_inbound/run.sh` — every cell below is that "
        "run's own output, and this document pastes it verbatim.\n"
    )
    print(
        "**The column header is the version the JAR ITSELF reported**, read out of its own "
        "`META-INF/MANIFEST.MF` `Implementation-Version` — not the version the loop asked "
        "for, which is only the path this machine cached the artifact at. The run ABORTS "
        "when the two disagree rather than printing a row.\n"
    )

    methods = [m for m in declared_methods(archive) if takes_a_subscription(m[1])]
    consuming = sorted(m for m in methods if m[0].startswith(_CONSUMING_PREFIXES))
    publishing = sorted(m for m in methods if not m[0].startswith(_CONSUMING_PREFIXES))

    print("### 1. Every `PubSubTemplate` method that takes a name at argument 0\n")
    print("Cells are the erased JVM descriptor, under the version that reported it.\n")
    # The header cell is the identity ALONE — `test_probe_provenance.py` reads the
    # column header as the configuration a cell is attributable to, and a header
    # carrying anything besides the version is not one.
    print(f"| method | consumes? | {claimed} |")
    print("| --- | --- | --- |")
    for name, descriptor, _ in consuming:
        print(f"| `{name}` | **yes** | `{descriptor}` |")
    for name, descriptor, _ in publishing:
        print(f"| `{name}` | no (publishes) | `{descriptor}` |")
    print(
        f"\n- **{len(consuming)} consuming methods** and {len(publishing)} publishing ones, "
        f"enumerated from the class rather than from a list written in this probe.\n"
    )

    print("### 2. Which of them the shipped catalog declares\n")
    rows = catalog().matches["methods"]
    declared = {(str(row["name"]), str(row["descriptor"])) for row in rows if "descriptor" in row}
    print("| consuming method | declared by `spring-pubsub.yml` | captures a payload type |")
    print("| --- | --- | --- |")
    missing = 0
    for name, descriptor, _ in consuming:
        present = (name, descriptor) in declared
        row = next(
            (r for r in rows if str(r["name"]) == name and str(r.get("descriptor")) == descriptor),
            None,
        )
        captures = "—" if row is None or row.get("body_arg") is None else f"arg {row['body_arg']}"
        missing += 0 if present else 1
        print(f"| `{name}` | {'yes' if present else '**NO**'} | {captures} |")
    print(f"\n- **{len(consuming) - missing} of {len(consuming)} declared.**\n")

    print("### 3. What each consuming call actually derives\n")
    calls = [(name, descriptor, arity_of(descriptor)) for name, descriptor, _ in consuming]
    produced = {str(row["path"]): row for row in derived(calls)}
    print("| consuming method | row derived | path | direction |")
    print("| --- | --- | --- | --- |")
    for name, _, _ in calls:
        row = produced.get(f"sub-{name}")
        if row is None:
            print(f"| `{name}` | **NOTHING** | — | — |")
        else:
            print(f"| `{name}` | yes | `{row['path']}` | {row['direction']} |")
    print(f"\n- **{len(produced)} of {len(calls)} calls derived a row.**\n")


if __name__ == "__main__":
    try:
        main()
    except ProbeError as error:
        print(f"PROBE COULD NOT ANSWER: {error}", file=sys.stderr)
        raise SystemExit(2) from error
