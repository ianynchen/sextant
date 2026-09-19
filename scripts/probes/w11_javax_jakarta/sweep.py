"""W11 — the javax/jakarta mechanical sweep (F2 §3.3).

Answers three questions per Jakarta EE type any shipped catalog names, and
answers the third by RUNNING the real derivation rather than reading the
catalog and reasoning about it:

1. does a catalog name the `javax` spelling as well as the `jakarta` one?
2. does the `javax` counterpart type actually exist, and does it declare the
   same methods under the same names (with, necessarily, different
   descriptors)?
3. when a codebase writes the unhandled spelling, WHICH failure mode applies —
   *renamed, nothing published*, or *renamed, partial data published*?

The third question is the one the design says must be classified separately,
because the two are not equally bad: silence reads as absence, while a row
with a hole in it reads as "we looked and could not resolve it".
"""

import json
import re
import subprocess
import sys
import tempfile
import zipfile
from collections import defaultdict
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "src"))

from sextant.application.ports.catalogs import Catalog
from sextant.application.resolve.endpoints import derive_endpoints
from sextant.domain.closed_sets import (
    ConstructKind,
    OriginTier,
)
from sextant.domain.factfile import write_fact_file
from sextant.domain.facts import (
    AnnotationFact,
    AnnotationUse,
    CallArgument,
    CallSiteFact,
    CallTarget,
    Document,
    Parameter,
    Signature,
    SymbolFact,
    TypeRef,
)
from sextant.ingress.catalogs.yaml_source import YamlCatalogSource
from sextant.storage.duckdb.workspace import DuckDbWorkspace

CATALOGS = REPO / "src" / "sextant" / "catalogs"
M2 = Path.home() / ".m2" / "repository"
_TYPE = re.compile(r"\b(jakarta|javax)((?:\.[a-zA-Z0-9_]+)+)")
# `group:artifact`, optionally `:version` — what `detect.coordinates` and
# `measured.artifact` hold. Anchored, so a sentence merely containing a colon is
# not mistaken for one.
_COORDINATE = re.compile(r"^[\w.\-]+:[\w.\-]+(?::[\w.\-]+)?$")


# --- 1. which spellings the catalogs name --------------------------------


def _values(node: object, path: tuple[str, ...] = ()) -> list[tuple[tuple[str, ...], str]]:
    """Every string VALUE in a parsed catalog, with the key path that reaches it.

    Values, not file text. The first version scanned raw YAML, so a type named in
    a COMMENT counted as named — and that is not a hypothetical: `jakarta-websocket.yml`
    names `javax.websocket.OnMessage` only inside a comment that says, in as many
    words, that the javax spelling derives no endpoint. The sweep reported the
    family as `both` and the verdict concluded websocket "already carries both
    spellings", while `docs/COVERAGE.md` said the opposite. A sweep that reads
    prose reports a gap as closed because someone wrote about it.
    """
    if isinstance(node, str):
        return [(path, node)]
    if isinstance(node, list):
        return [pair for item in node for pair in _values(item, path)]
    if isinstance(node, dict):
        return [pair for key, value in node.items() for pair in _values(value, (*path, str(key)))]
    return []


def spellings() -> dict[str, dict[str, dict[str, list[str]]]]:
    """Per type tail, which catalogs name each spelling, split by whether the name
    sits in a RULE or only in `detect.coordinates`.

    `detect.coordinates` names ARTIFACTS, not types — `javax.websocket:javax.websocket-api`
    is a jar to recognise, and recognising a module says nothing about matching a
    type inside it. Keeping it in a column of its own is what stops "we detect this
    library" from reading as "we handle this spelling"."""
    named: dict[tuple[str, str], dict[str, set[str]]] = defaultdict(
        lambda: {"rule": set(), "detect": set()}
    )
    for path in sorted(CATALOGS.rglob("*.yml")):
        # The path UNDER the catalogs directory, not the bare filename: the
        # nullability block lives in `shape-models/json.yml`, and a table citing
        # `json.yml` sends a reader to a path that does not exist. Two catalogs
        # sharing a basename would also have merged into one cell.
        label = str(path.relative_to(CATALOGS))
        try:
            loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as broken:
            raise ProbeError(f"{path.name} does not parse: {broken}") from broken
        for keys, value in _values(loaded, ()):
            # A Maven COORDINATE is never a type name. `jakarta.websocket:jakarta.
            # websocket-api` is a jar to recognise, and the group half of it looks
            # exactly like a package — which put four rows in this table
            # (`jms`, `jws`, `servlet`, `websocket`) that name no type at all.
            # Coordinates live in `detect.coordinates` and in `measured.artifact`,
            # and are counted as DETECTION rather than as a rule: recognising a
            # library says nothing about matching a type inside it.
            if _COORDINATE.match(value.strip()):
                for found in _TYPE.finditer(value):
                    named[(found.group(1), found.group(2))]["detect"].add(label)
                continue
            for found in _TYPE.finditer(value):
                named[(found.group(1), found.group(2))]["rule"].add(label)
    by_tail: dict[str, dict[str, dict[str, list[str]]]] = defaultdict(dict)
    for (family, tail), places in named.items():
        by_tail[tail][family] = {where: sorted(files) for where, files in places.items() if files}
    return dict(by_tail)


# --- 2. does the counterpart exist, and declare the same methods ----------


class ProbeError(RuntimeError):
    """Something the run could not establish. ABORTS rather than warning."""


def resolve(artifact: str) -> Path | None:
    group, name, version = artifact.split(":")
    jar = M2 / Path(group.replace(".", "/")) / name / version / f"{name}-{version}.jar"
    if jar.is_file():
        return jar
    subprocess.run(
        ["mvn", "-q", "-B", "dependency:get", "-Dtransitive=false", f"-Dartifact={artifact}"],
        cwd=REPO,
        capture_output=True,
        # A failure here is not this call's to report: `checked` aborts on the jar
        # still being absent, with a message naming the coordinate to fix.
        check=False,
    )
    return jar if jar.is_file() else None


def self_reported_version(jar: Path) -> str:
    """The version this ARCHIVE states for itself, read out of its own bytes —
    Maven's `META-INF/maven/*/pom.properties`, which is the build's own record of
    what it produced.

    Not the manifest's `Implementation-Version`: `jaxb-api-2.3.1.jar` writes
    `2.3.0` there while its `pom.properties` says `2.3.1`, so the two disagree
    inside one file and a probe has to say which one it read.

    Raises rather than defaulting. A missing self-report is exactly the case
    where a hand-written column would go unchallenged (CP-5).
    """
    with zipfile.ZipFile(jar) as archive:
        entries = [n for n in archive.namelist() if n.endswith("META-INF/maven/pom.properties")]
        entries += [
            n
            for n in archive.namelist()
            if n.startswith("META-INF/maven/") and n.endswith("/pom.properties")
        ]
        if not entries:
            raise ProbeError(f"{jar.name} carries no pom.properties — it reports no version")
        text = archive.read(entries[0]).decode("utf-8", "replace")
    for line in text.splitlines():
        if line.strip().startswith("version="):
            return line.split("=", 1)[1].strip()
    raise ProbeError(f"{jar.name}'s pom.properties declares no `version`")


def checked(artifact: str) -> tuple[Path, str]:
    """The jar, and the version IT reports. ABORTS when that disagrees with the
    coordinate that resolved it, rather than printing a version it did not run —
    CP-5's failure, which labelled eight cells with a version the process never
    saw."""
    jar = resolve(artifact)
    if jar is None:
        # ABORTS rather than printing a dash. An unresolvable coordinate is the
        # case where a table would quietly claim "measured" over a cell nothing
        # answered — the same hole CP-10 closes by aborting on a wrong artifact
        # instead of leaving the column unfilled.
        raise ProbeError(
            f"{artifact} did not resolve. Fix the coordinate in run.sh rather than "
            f"leaving the row unmeasured."
        )
    reported = self_reported_version(jar)
    requested = artifact.split(":")[2]
    if reported != requested:
        raise ProbeError(
            f"{jar.name} reports version {reported!r} in its own pom.properties, but the "
            f"coordinate that resolved it asked for {requested!r}. Fix the coordinate in "
            f"run.sh rather than labelling a column with a version this run did not read."
        )
    return jar, reported


def declared_methods(jar: Path, internal_name: str) -> dict[str, list[str]]:
    """`{method name: [erased descriptors]}` for one class inside one jar, read
    with `javap` on the extracted class file — the jar's own statement, never a
    recollection of what the API looks like."""
    with tempfile.TemporaryDirectory() as into:
        try:
            with zipfile.ZipFile(jar) as archive:
                archive.extract(f"{internal_name}.class", into)
        except KeyError:
            return {}
        listed = subprocess.run(
            ["javap", "-p", "-s", str(Path(into) / f"{internal_name}.class")],
            capture_output=True,
            # An empty method map is what an unreadable class produces, and the
            # table prints a dash for it rather than claiming a descriptor.
            check=False,
            text=True,
        ).stdout
    methods: dict[str, list[str]] = defaultdict(list)
    name = None
    for line in listed.splitlines():
        signature = re.search(r"\b(\w+)\(", line)
        if "descriptor:" in line and name is not None:
            methods[name].append(line.split("descriptor:")[1].strip())
        elif signature is not None:
            name = signature.group(1)
    return dict(methods)


# --- 3. what a codebase writing the unhandled spelling actually derives ---

_DOC = Document(
    document_id="doc_1",
    relative_path="com/acme/Client.java",
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
CAPABILITIES = {
    "call_site",
    "string_constants",
    "annotation_args",
    "typed_signatures",
    "type_annotations",
}


def catalog(catalog_id: str) -> Catalog:
    """One shipped catalog by id, ABORTING like every other failure here rather
    than raising `StopIteration` as a bare traceback."""
    found = next((c for c in YamlCatalogSource(CATALOGS).load() if c.id == catalog_id), None)
    if found is None:
        raise ProbeError(
            f"no shipped catalog has id {catalog_id!r}. This probe measures the "
            f"catalogs as shipped; add it or fix the id rather than skipping the row."
        )
    return found


def derived(facts: list, catalog_ids: tuple[str, ...]) -> list[dict]:
    """The rows a fact set derives under a SET of catalogs.

    A set rather than one, because a twin is a second FILE: `javax-jms.yml` is
    what answers the `javax` spelling and `jakarta-jms.yml` is what answers the
    other, and running only one of them would show the twin's own gap as if it
    were the estate's."""
    with tempfile.TemporaryDirectory() as into:
        root = Path(into)
        write_fact_file(root / "facts" / "Client.jsonl", _DOC, facts)
        workspace = DuckDbWorkspace(root / "ws.duckdb")
        workspace.load_facts(root / "facts")
        derive_endpoints(
            workspace,
            [catalog(catalog_id) for catalog_id in catalog_ids],
            capabilities=CAPABILITIES,
        )
        rows = workspace.query("endpoints")
        workspace.close()
    return rows


def jms_facts(family: str) -> list:
    """`session.createProducer(session.createQueue("raw-audit"))`, in one
    spelling. The shape `jakarta-jms.yml` matches: the destination is not
    `createProducer`'s own argument, it is the RESULT of a separate
    `createQueue` call, followed through `channel_via`."""
    caller = "com/acme/Client#publish()."
    session = f"{family}/jms/Session#"
    return [
        SymbolFact(document_id="doc_1", symbol=caller, construct_kind=ConstructKind.METHOD),
        CallSiteFact(
            document_id="doc_1",
            caller=caller,
            target=CallTarget(
                owner=session,
                name="createQueue",
                descriptor=f"(Ljava/lang/String;)L{family}/jms/Queue;",
            ),
            invoke_kind="interface",
            ordinal=0,
            receiver=5,
            result=7,
            arguments=[CallArgument(kind="string", value="raw-audit")],
        ),
        CallSiteFact(
            document_id="doc_1",
            caller=caller,
            target=CallTarget(
                owner=session,
                name="createProducer",
                descriptor=f"(L{family}/jms/Destination;)L{family}/jms/MessageProducer;",
            ),
            invoke_kind="interface",
            ordinal=1,
            receiver=3,
            result=8,
            arguments=[CallArgument(kind="unresolved", source=7)],
        ),
    ]


def soap_facts(family: str) -> list:
    """`template.marshalSendAndReceive("http://billing/ws", request)` where
    `request`'s declared type carries `@XmlRootElement(name=..., namespace=...)`,
    in one spelling. `spring-ws-template.yml` reads the OPERATION off that
    annotation; the URI is the row's `peer` either way.

    The symbols carry the module-coordinates prefix a real symbol fact's own
    `symbol` carries (D00 5a) — the call site's `caller` and the annotation's
    `target` both — because that is what the shipped test for this catalog
    builds and what the join actually matches on. Getting it wrong makes the
    JAKARTA control derive an unresolved row too, which would have read as
    "both spellings are equally broken" when nothing was broken but the facts.
    """
    module = "sextant-jvm maven com.acme/orders-service 1.0.0 "
    client = "com/acme/orders/soap/BillingSoapClient#"
    payload = "com/acme/orders/soap/PlaceOrderRequest#"
    caller = module + client + "place(sig_a)."
    return [
        SymbolFact(
            document_id="doc_1",
            symbol=caller,
            construct_kind=ConstructKind.METHOD,
            enclosing=module + client,
            signature=Signature(
                parameters=[Parameter(name="request", type=TypeRef(symbol=payload))],
                returns=TypeRef(symbol="java/lang/Object#"),
            ),
        ),
        AnnotationFact(
            document_id="doc_1",
            target=module + payload,
            retention="runtime",
            use=AnnotationUse(
                annotation=f"{family}/xml/bind/annotation/XmlRootElement#",
                args={"name": "placeOrderRequest", "namespace": "http://acme.example/orders"},
            ),
        ),
        CallSiteFact(
            document_id="doc_1",
            caller=caller,
            target=CallTarget(
                owner="org/springframework/ws/client/core/WebServiceTemplate#",
                name="marshalSendAndReceive",
                descriptor="(Ljava/lang/String;Ljava/lang/Object;)Ljava/lang/Object;",
            ),
            invoke_kind="virtual",
            ordinal=0,
            receiver=3,
            result=9,
            arguments=[
                CallArgument(kind="string", value="http://billing.internal/ws"),
                CallArgument(kind="parameter", value=0),
            ],
        ),
    ]


# --- 4. the third failure mode: an EXCLUDE list naming one spelling --------


def excluded_body(family: str) -> str:
    """What `spring-jms.yml`'s `request_body` rule picks as the payload when a
    `@JmsListener` method's only parameter is a raw JMS `Message`, in one
    spelling.

    This is not one of the two failure modes the design names. `excludes` is a
    NEGATIVE list: naming only the `jakarta` spelling means the `javax` one is
    not excluded, so the `sole_unannotated` fallback picks it and the opaque
    envelope is described AS the payload. Not silence and not a hole — a wrong
    contract, published.
    """
    from sextant.application.resolve.shapes.contracts import _body_parameter

    signature = {
        "parameters": [
            {"name": "message", "type": {"symbol": f"{family}/jms/Message#"}, "annotations": []}
        ]
    }
    picked = _body_parameter(
        signature, catalog("spring-jms"), owner="", paths=frozenset(), index={}, members={}
    )
    return "nothing (excluded)" if picked is None else picked[1]["type"]["symbol"]


def main() -> None:
    print("## Observations\n")
    print(
        "Verbatim from `scripts/probes/w11_javax_jakarta/run.sh`, which runs `sweep.py`. **Every version below is the one the JAR "
        "itself reported** — read out of its own `META-INF/maven/*/pom.properties` — and "
        "**not the version the coordinate list asked for**. `sweep.py` compares the two and "
        "ABORTS the whole run when they disagree, rather than printing a version it did not "
        "read: that is CP-5's failure, which labelled eight cells with a version the process "
        "never saw. `jaxb-api-2.3.1.jar` is why the manifest is not the source — it prints "
        "`Implementation-Version: 2.3.0` while its own `pom.properties` says `2.3.1`, so the "
        "two disagree inside one file.\n"
    )

    pairs = (
        (
            "javax.jms:javax.jms-api:2.0.1",
            "jakarta.jms:jakarta.jms-api:3.1.0",
            "jms/Session",
            ("createProducer", "createConsumer", "createQueue", "createTopic"),
        ),
        (
            "javax.xml.bind:jaxb-api:2.3.1",
            "jakarta.xml.bind:jakarta.xml.bind-api:4.0.1",
            "xml/bind/annotation/XmlRootElement",
            ("name", "namespace"),
        ),
    )
    columns: dict[str, dict[str, object]] = {}
    for javax_artifact, jakarta_artifact, internal, names in pairs:
        for artifact, family in ((javax_artifact, "javax"), (jakarta_artifact, "jakarta")):
            jar, reported = checked(artifact)
            methods = declared_methods(jar, f"{family}/{internal}")
            other_family = "jakarta" if family == "javax" else "javax"
            other = declared_methods(
                checked(jakarta_artifact if family == "javax" else javax_artifact)[0],
                f"{other_family}/{internal}",
            )
            differing = sum(
                1 for name in names if methods.get(name, ["?"])[:1] != other.get(name, ["!"])[:1]
            )
            columns[reported] = {
                "artifact": artifact.split(":")[1],
                "types": 1,
                "methods": len(names),
                "differing": differing,
            }

    order = sorted(columns)
    print("| what the run read | " + " | ".join(order) + " |")
    print("|---" * (len(order) + 1) + "|")
    print(
        "| artifact reporting this version | "
        + " | ".join(str(columns[v]["artifact"]) for v in order)
        + " |"
    )
    print(
        "| types resolved out of it | " + " | ".join(str(columns[v]["types"]) for v in order) + " |"
    )
    print(
        "| methods compared against the other spelling | "
        + " | ".join(str(columns[v]["methods"]) for v in order)
        + " |"
    )
    print(
        "| of those, descriptors that DIFFER | "
        + " | ".join(str(columns[v]["differing"]) for v in order)
        + " |"
    )
    print()

    print("### 1. Every Jakarta EE type a shipped catalog names\n")
    print(
        "Read from parsed catalog VALUES, never from file text — a type named in a comment "
        "is not a type a catalog matches. DOTTED names only: a type named solely inside a "
        "`descriptor:` (`Ljakarta/jms/Queue;`) is invisible here, and today nothing is "
        "slash-named without also being dotted somewhere, so this under-reports nothing "
        "yet. A Maven coordinate is not a type; its column is `detected only`.\n"
    )
    print("| type | named in a RULE by | detected only, by | state |")
    print("|---|---|---|---|")
    gaps = []
    for tail, families in sorted(spellings().items()):
        jakarta = families.get("jakarta", {})
        javax = families.get("javax", {})
        rules = {"jakarta": jakarta.get("rule", []), "javax": javax.get("rule", [])}
        detect_only = sorted(
            set(jakarta.get("detect", []) + javax.get("detect", []))
            - set(rules["jakarta"] + rules["javax"])
        )
        if rules["jakarta"] and rules["javax"]:
            state = "both"
        elif rules["jakarta"]:
            state = "**JAKARTA ONLY**"
            gaps.append((tail, rules["jakarta"]))
        elif rules["javax"]:
            state = "javax only"
        else:
            state = "detected, never matched"
        named = ", ".join(
            f"`{f}` ({family})" for family in ("jakarta", "javax") for f in rules[family]
        )
        print(
            f"| `{tail.lstrip('.')}` | {named or '—'} "
            f"| {', '.join(f'`{f}`' for f in detect_only) or '—'} | {state} |"
        )

    print("\n### 2. Does the unhandled counterpart exist, and declare the same methods?\n")
    print(
        "| javax artifact | version IT reports | type | method "
        "| jakarta descriptor | javax descriptor |"
    )
    print("|---|---|---|---|---|---|")
    for artifact, jakarta_artifact, internal, names in pairs:
        javax_jar, javax_version = checked(artifact)
        jakarta_jar, _ = checked(jakarta_artifact)
        javax_methods = declared_methods(javax_jar, f"javax/{internal}") if javax_jar else {}
        jakarta_methods = (
            declared_methods(jakarta_jar, f"jakarta/{internal}") if jakarta_jar else {}
        )
        for name in names:
            here = javax_methods.get(name, [])
            there = jakarta_methods.get(name, [])
            print(
                f"| `{artifact.rsplit(':', 1)[0]}` | **{javax_version}** | `{internal}` | `{name}` "
                f"| `{there[0] if there else '—'}` | `{here[0] if here else '—'}` |"
            )

    print("\n### 3. What each unhandled spelling actually derives\n")
    print("| catalogs run | spelling written | rows | derived by | path | peer | resolution |")
    print("|---|---|---|---|---|---|---|")
    for label, catalog_ids, build in (
        ("jakarta-jms + javax-jms", ("jakarta-jms", "javax-jms"), jms_facts),
        ("spring-ws-template", ("spring-ws-template",), soap_facts),
    ):
        for family in ("jakarta", "javax"):
            rows = derived(build(family), catalog_ids)
            if not rows:
                print(f"| `{label}` | `{family}` | **0** | — | — | — | — |")
                continue
            for row in rows:
                print(
                    f"| `{label}` | `{family}` | {len(rows)} | {row['catalog_id']} "
                    f"| `{row['path']}` | {row['peer']} | {row['resolution']} |"
                )

    print("\n### 4. An `excludes` list that names one spelling\n")
    print("| catalog | rule | spelling written | what becomes the payload |")
    print("|---|---|---|---|")
    for family in ("jakarta", "javax"):
        print(
            f"| `spring-jms` | `request_body.excludes` | `{family}` | `{excluded_body(family)}` |"
        )

    print(f"\n<!-- gaps found: {json.dumps([tail for tail, _ in gaps])} -->")


if __name__ == "__main__":
    try:
        main()
    except ProbeError as error:
        print(f"W11 ABORTED: {error}", file=sys.stderr)
        raise SystemExit(1) from error
