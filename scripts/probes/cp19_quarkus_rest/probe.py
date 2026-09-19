"""CP-19's measurement half: Quarkus REST's build-time scanner and endpoint
indexer — the root-resource gate, the SSE default-produces hint, the context
types a deployment processor adds, the parameter-resolution order, the
`quarkus-resteasy-reactive` -> `quarkus-rest` relocation, and whether
`AnnotationStore` implements JAX-RS §3.6's all-or-nothing rule or something
else.

Called by `run.sh`, which resolves the jars (main + `-sources` classifier);
this script never downloads anything itself except the Maven Central metadata
XML question 5 reads, which is a repository-metadata read rather than a jar
and has no `Implementation-Version` to check.

Rows 1, 2 and 4 read SOURCE (`sed`-shaped snippets, extracted by anchor text
rather than a fixed line count so a run is not silently reading the wrong
lines if the source reflows between versions); row 3 and the `AnnotationStore`
half of row 6 read BYTECODE. Row 6's `collectEndpoints`/`getInheritableAnnotation`
read SOURCE for the same reason CP-17's question 6 does: the combination of
branches is the rule, and guessing it off a disassembly is how a rule goes
unopened for a round.

Like CP-16/CP-17/CP-18 it reads each jar's own identity out of its own bytes
before it measures anything and refuses to file a cell under a version the
artifact did not claim (GUIDELINES §5.4, and CP-5's failure it exists to
prevent).
"""

from __future__ import annotations

import re
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

_PROPERTY = re.compile(r"^\s*([\w.\-]+)\s*[:=]\s*(.+?)\s*$")
_STEP = " ; "


class ProbeError(RuntimeError):
    """A run that cannot label its own output. Fatal, never advisory."""


class Artifact:
    def __init__(
        self, key: str, group: str, name: str, requested: str, jar: Path, sources: Path | None
    ):
        self.key = key
        self.group = group
        self.name = name
        self.requested = requested
        self.jar = jar
        self.sources = sources
        self.observed = _identity(jar, "META-INF/MANIFEST.MF", "Implementation-Version")
        if self.observed != requested:
            raise ProbeError(
                f"{jar.name} reports version {self.observed!r} but was resolved as "
                f"{requested!r} — a mislabelled column, which is CP-5's failure exactly"
            )


def _identity(jar: Path, entry: str, key: str) -> str:
    with zipfile.ZipFile(jar) as archive:
        names = [n for n in archive.namelist() if n == entry or n.endswith("/" + entry)]
        if not names:
            raise ProbeError(f"{jar.name} carries no `{entry}`")
        text = archive.read(names[0]).decode("utf-8", "replace")
    for line in text.splitlines():
        match = _PROPERTY.match(line)
        if match and match.group(1).lower() == key.lower():
            return match.group(2)
    raise ProbeError(f"{jar.name}'s `{entry}` declares no `{key}`")


def _javap(*arguments: str, classpath: Path) -> str:
    result = subprocess.run(
        ["javap", "-cp", str(classpath), *arguments], capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        raise ProbeError(f"javap {' '.join(arguments)} failed: {result.stderr.strip()}")
    return result.stdout


def _step(line: str) -> str | None:
    match = re.match(r"^\s*\d+:\s+(\S+)(.*)$", line)
    if match is None:
        return None
    operands = match.group(2)
    comment = operands.split("//", 1)[1].strip() if "//" in operands else ""
    return f"{match.group(1)} {comment}".strip()


def _instructions(lines: list[str], until: str | None = None) -> list[str]:
    """`javap -c`'s numbered instructions following a method signature —
    skipping the `Code:` header line (and any other non-instruction line)
    BEFORE the first instruction, then stopping at the first non-instruction
    line once instructions have actually started, or at the step matching
    `until` (inclusive)."""
    steps: list[str] = []
    started = False
    for line in lines:
        step = _step(line)
        if step is None:
            if started:
                break
            continue
        started = True
        steps.append(step)
        if until is not None and until in step:
            break
    return steps


def _source(sources: Path, path: str) -> str:
    with zipfile.ZipFile(sources) as archive:
        try:
            return archive.read(path).decode("utf-8", "replace")
        except KeyError:
            raise ProbeError(f"{sources.name} carries no `{path}`") from None


def _between(text: str, start: str, end: str, include_end: bool = True) -> str:
    """Raw source lines from the first line containing `start` to the first
    line containing `end` at or after it. Anchored on text rather than a line
    number, so a reflow in the source moves the window with it instead of
    silently reading the wrong lines."""
    lines = text.splitlines()
    start_idx = next((i for i, line in enumerate(lines) if start in line), None)
    if start_idx is None:
        raise ProbeError(f"anchor not found: {start!r}")
    end_idx = next((i for i, line in enumerate(lines) if end in line and i >= start_idx), None)
    if end_idx is None:
        raise ProbeError(f"end anchor not found after {start!r}: {end!r}")
    if include_end:
        end_idx += 1
    return "\n".join(lines[start_idx:end_idx])


def _brace_block(text: str, anchor: str) -> str:
    """One balanced `{ ... }` block, starting at the first line containing
    `anchor` and ending where the brace depth it opens returns to zero —
    brace-matched rather than a fixed line count, CP-17's `_method_body`
    reason: a method or block that grows between versions is printed whole."""
    lines = text.splitlines()
    start_idx = next((i for i, line in enumerate(lines) if anchor in line), None)
    if start_idx is None:
        raise ProbeError(f"anchor not found: {anchor!r}")
    depth = 0
    seen_open = False
    body: list[str] = []
    for line in lines[start_idx:]:
        body.append(line)
        depth += line.count("{") - line.count("}")
        if "{" in line:
            seen_open = True
        # Only a line that itself CLOSED a brace is a candidate stopping
        # point — a multi-line condition contributes lines with no braces at
        # all while depth is already (still) zero, and checking every line
        # rather than only the ones that just closed something stops on the
        # first such line. And a closing brace that dangles into an
        # `else`/`else if` has not actually closed the construct this anchor
        # opened — javac's own if/else-if/else chain closes one clause's
        # brace before the next clause's condition (and eventual `{`) even
        # appear, so a naive "depth returned to zero" stop cuts the chain off
        # at its first clause.
        if seen_open and depth == 0 and "}" in line and not re.match(r"^\s*\}\s*else\b", line):
            break
    else:
        raise ProbeError(f"block starting at {anchor!r} never closes its brace")
    return "\n".join(body)


def q1_root_resource_gate(scanner_src: str) -> dict[str, str]:
    """Q1. `ResteasyReactiveScanner.scanResources`: class-`@Path` root
    resources, `@Path`-interface implementors, and HTTP-verb-only
    `clientInterfaces`/`possibleSubResources`."""
    class_path = _brace_block(
        scanner_src, "if (annotation.target().kind() == AnnotationTarget.Kind.CLASS) {"
    )
    implementors = _brace_block(
        scanner_src, "for (ClassInfo clazz : index.getAllKnownImplementors(i.getKey())) {"
    )
    clients = _between(
        scanner_src,
        "// for clients, it is also enough to only have @GET, @POST, etc on methods and no PATH whatsoever",
        "Map<DotName, ClassInfo> possibleSubResources = new HashMap<>();",
    )
    return {
        "1a": re.sub(r"\s+", " ", class_path).strip(),
        "1b": re.sub(r"\s+", " ", implementors).strip(),
        "1c": re.sub(r"\s+", " ", clients).strip(),
    }


def q2_sse_hint(indexer_src: str) -> dict[str, str]:
    """Q2. The SSE default-produces hint: element type, then the
    `@RestStreamElementType` -> `@RestSseElementType` fallback."""
    produces_block = _between(
        indexer_src,
        "String[] produces = extractProducesConsumesValues(getAnnotationStore().getAnnotation(currentMethodInfo, PRODUCES));",
        "produces = applyDefaultProducesAndAddCharsets(httpMethod, nonAsyncReturnType, produces);",
        include_end=False,
    )
    stream_value = _brace_block(
        indexer_src, "private String getStreamAnnotationValue(AnnotationTarget target) {"
    )
    return {
        "2a": re.sub(r"\s+", " ", produces_block).strip(),
        "2b": re.sub(r"\s+", " ", stream_value).strip(),
    }


def q3_context_types(indexer_src: str, deployment_jar: Path) -> dict[str, str]:
    """Q3. `DEFAULT_CONTEXT_TYPES` (source) and the deployment processor's own
    additions (bytecode: the one caller of `addContextTypes` and its static
    initializer)."""
    default_types = _between(
        indexer_src,
        "private static final Set<DotName> DEFAULT_CONTEXT_TYPES = Set.of(",
        "RESOURCE_INFO);",
    )
    output = _javap(
        "-c",
        "-p",
        "io.quarkus.resteasy.reactive.server.deployment.ResteasyReactiveProcessor",
        classpath=deployment_jar,
    )
    lines = output.splitlines()
    call_idx = next((i for i, line in enumerate(lines) if "addContextTypes" in line), None)
    if call_idx is None:
        raise ProbeError("no addContextTypes caller found in ResteasyReactiveProcessor")
    caller = _step(lines[call_idx]) or lines[call_idx].strip()
    static_start = next(i for i, line in enumerate(lines) if line.strip() == "static {};")
    static_body = _instructions(lines[static_start + 1 :], until="Field CONTEXT_TYPES")
    return {
        "3a": re.sub(r"\s+", " ", default_types).strip(),
        "3b": f"caller: {caller} ; static init: " + _STEP.join(static_body),
    }


def q4_parameter_order(indexer_src: str, container_src: str, dotnames_src: str) -> dict[str, str]:
    """Q4. The parameter-resolution order (context -> container -> path-name
    -> body) and the container-detection rule and its annotation set."""
    resolution = _brace_block(indexer_src, "// auto context parameters")
    container = _brace_block(container_src, "public static Set<DotName> scanParameterContainers(")
    field_annotations = _between(
        dotnames_src,
        "JAX_RS_ANNOTATIONS_FOR_FIELDS = new HashSet<>(",
        "SUSPENDED));",
    )
    return {
        "4a": re.sub(r"\s+", " ", resolution).strip(),
        "4b": re.sub(r"\s+", " ", container).strip(),
        "4c": re.sub(r"\s+", " ", field_annotations).strip(),
    }


def q5_relocation() -> dict[str, str]:
    """Q5. The `quarkus-resteasy-reactive` -> `quarkus-rest` relocation
    boundary, read off Maven Central's own metadata rather than a jar."""

    def versions(group: str, artifact: str) -> list[str]:
        url = f"https://repo1.maven.org/maven2/{group.replace('.', '/')}/{artifact}/maven-metadata.xml"
        with urllib.request.urlopen(url, timeout=30) as response:
            text = response.read().decode("utf-8", "replace")
        return re.findall(r"<version>([^<]+)</version>", text)

    rest_versions = versions("io.quarkus", "quarkus-rest")
    rr_versions = versions("io.quarkus", "quarkus-resteasy-reactive")
    ga_rest = [v for v in rest_versions if re.fullmatch(r"3\.\d+\.\d+", v)]
    return {
        "5a": f"quarkus-rest earliest GA versions: {', '.join(ga_rest[:3])}",
        "5b": f"quarkus-resteasy-reactive last versions: {', '.join(rr_versions[-10:])}",
    }


def q6_annotation_store(processor_jar: Path, indexer_src: str) -> dict[str, str]:
    """Q6. `AnnotationStore.getAnnotation` (a thin Jandex delegate, bytecode)
    versus `EndpointIndexer.collectEndpoints`'s own hierarchy walk (source,
    full method body) and `getInheritableAnnotation`'s narrow use (source)."""
    store_output = _javap(
        "-c",
        "-p",
        "org.jboss.resteasy.reactive.common.processor.transformation.AnnotationStore",
        classpath=processor_jar,
    )
    lines = store_output.splitlines()
    method_start = next(
        i
        for i, line in enumerate(lines)
        if "getAnnotation(org.jboss.jandex.AnnotationTarget" in line
    )
    steps = _instructions(lines[method_start + 1 :], until="areturn")
    collect_endpoints = _brace_block(
        indexer_src, "private static List<FoundEndpoint> collectEndpoints("
    )
    get_inheritable = _brace_block(
        indexer_src,
        "private Map.Entry<AnnotationTarget, AnnotationInstance> getInheritableAnnotation(",
    )
    inheritable_callers = sorted(
        set(re.findall(r"getInheritableAnnotation\(\w+,\s*(\w+)\)", indexer_src))
    )
    return {
        "6a": "AnnotationStore.getAnnotation: " + _STEP.join(steps),
        "6b": re.sub(r"\s+", " ", collect_endpoints).strip(),
        "6c": re.sub(r"\s+", " ", get_inheritable).strip(),
        "6d": f"getInheritableAnnotation is called only for: {', '.join(inheritable_callers)}",
    }


def main(specs: list[str]) -> int:
    artifacts: dict[str, Artifact] = {}
    for spec in specs:
        parts = spec.split("|")
        key, group, name, version, jar = parts[0], parts[1], parts[2], parts[3], parts[4]
        sources = Path(parts[5]) if len(parts) > 5 and parts[5] else None
        artifacts[key] = Artifact(key, group, name, version, Path(jar), sources)

    columns = sorted({a.observed for a in artifacts.values()})
    print("| what the run read | " + " | ".join(columns) + " |")
    print("|---" * (len(columns) + 1) + "|")
    print(
        "| artifacts reporting this version | "
        + " | ".join(
            ", ".join(sorted(f"{a.group}:{a.name}" for a in artifacts.values() if a.observed == v))
            for v in columns
        )
        + " |"
    )
    print("| identity read from the archive itself | " + " | ".join(["yes"] * len(columns)) + " |")
    print()
    print("| # | question | artifact | version | observed |")
    print("|---|---|---|---|---|")

    rows: list[tuple[str, str, str, str, str]] = []

    for a_key, d_key, version_label in (
        ("processor39", "deploy39", "3.39.4"),
        ("processor17", "deploy17", "3.17.5"),
    ):
        processor = artifacts[a_key]
        deploy = artifacts[d_key]
        scanner_src = _source(
            processor.sources,
            "org/jboss/resteasy/reactive/common/processor/scanning/ResteasyReactiveScanner.java",
        )
        indexer_src = _source(
            processor.sources, "org/jboss/resteasy/reactive/common/processor/EndpointIndexer.java"
        )
        container_src = _source(
            processor.sources,
            "org/jboss/resteasy/reactive/common/processor/scanning/ResteasyReactiveParameterContainerScanner.java",
        )
        dotnames_src = _source(
            processor.sources,
            "org/jboss/resteasy/reactive/common/processor/ResteasyReactiveDotNames.java",
        )

        q1 = q1_root_resource_gate(scanner_src)
        q2 = q2_sse_hint(indexer_src)
        q3 = q3_context_types(indexer_src, deploy.jar)
        q4 = q4_parameter_order(indexer_src, container_src, dotnames_src)

        rows.append(
            ("1a", "root-resource gate: class-level @Path", processor, version_label, q1["1a"])
        )
        rows.append(
            (
                "1b",
                "root-resource gate: @Path-interface implementors",
                processor,
                version_label,
                q1["1b"],
            )
        )
        rows.append(
            (
                "1c",
                "root-resource gate: HTTP-verb-only clientInterfaces/subResources",
                processor,
                version_label,
                q1["1c"],
            )
        )
        rows.append(
            (
                "2a",
                "SSE default-produces: the @Produces/stream-type resolution",
                processor,
                version_label,
                q2["2a"],
            )
        )
        rows.append(
            (
                "2b",
                "SSE default-produces: getStreamAnnotationValue",
                processor,
                version_label,
                q2["2b"],
            )
        )
        rows.append(("3a", "DEFAULT_CONTEXT_TYPES (source)", processor, version_label, q3["3a"]))
        rows.append(
            (
                "3b",
                "addContextTypes caller + Vert.x CONTEXT_TYPES (bytecode)",
                deploy,
                version_label,
                q3["3b"],
            )
        )
        rows.append(
            (
                "4a",
                "parameter-resolution order: context -> container -> path-name -> body",
                processor,
                version_label,
                q4["4a"],
            )
        )
        rows.append(
            (
                "4b",
                "ParamContainerScanner.scanParameterContainers",
                processor,
                version_label,
                q4["4b"],
            )
        )
        rows.append(("4c", "JAX_RS_ANNOTATIONS_FOR_FIELDS", processor, version_label, q4["4c"]))

    q5 = q5_relocation()
    rows.append(
        (
            "5a",
            "relocation: quarkus-rest earliest GA versions (Maven Central metadata)",
            artifacts["rest39"],
            "n/a",
            q5["5a"],
        )
    )
    rows.append(
        (
            "5b",
            "relocation: quarkus-resteasy-reactive last versions (Maven Central metadata)",
            artifacts["rest39"],
            "n/a",
            q5["5b"],
        )
    )

    processor39 = artifacts["processor39"]
    indexer_src_39 = _source(
        processor39.sources, "org/jboss/resteasy/reactive/common/processor/EndpointIndexer.java"
    )
    q6 = q6_annotation_store(processor39.jar, indexer_src_39)
    rows.append(
        (
            "6a",
            "AnnotationStore.getAnnotation (bytecode, no hierarchy walk)",
            processor39,
            "3.39.4",
            q6["6a"],
        )
    )
    rows.append(
        (
            "6b",
            "EndpointIndexer.collectEndpoints, full body (source)",
            processor39,
            "3.39.4",
            q6["6b"],
        )
    )
    rows.append(
        (
            "6c",
            "EndpointIndexer.getInheritableAnnotation, full body (source)",
            processor39,
            "3.39.4",
            q6["6c"],
        )
    )
    rows.append(("6d", "getInheritableAnnotation's only callers", processor39, "3.39.4", q6["6d"]))

    for number, question, artifact, version, observed in rows:
        print(
            f"| {number} | {question} | `{artifact.group}:{artifact.name}` | {version} | `{observed}` |"
        )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except ProbeError as error:
        print(f"CP-19 aborted: {error}", file=sys.stderr)
        raise SystemExit(1) from None
