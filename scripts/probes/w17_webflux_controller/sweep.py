"""W17 — does a WebFlux `@Controller` derive, and if not, why not? (F2 §3.7.)

G-38 states a mechanism: *"`spring-mvc.yml` carries the `@Controller` gate behind
`detect.coordinates: [org.springframework:spring-webmvc]`, which a WebFlux module
does not have"*, and concludes that a WebFlux `@Controller` derives nothing. The
design turns that into a build item and says which fix to pick is *"decided by
measurement of the two gates"*.

Three questions, in the order that decides whether there is anything to build:

1. **Are the two frameworks' handler predicates the same?** If they are, no fact on
   the class can separate an MVC controller from a WebFlux one, and any fix that
   tries to tell them apart from the class is unbuildable. Read out of each jar's
   own `RequestMappingHandlerMapping.isHandler`, per version, rather than from
   documentation.
2. **Is `spring-mvc.yml`'s coordinate read at all?** A gate is only a gate if some
   consumer honours it. `resolve/dependencies.py` names the styles that read
   `detect.coordinates`, and W16 added `detect.required` for a catalog to opt in.
   Whether `annotation_driven` is on either list is a fact about the shipped code,
   not about the catalog file.
3. **What does a WebFlux-only module actually derive?** Asked by COMPILING the four
   shapes G-38 names against the real jars, scanning the real class files with the
   real extractor, and running the real derivation over a module fact whose only
   dependency coordinate is `org.springframework:spring-webflux`. Nothing here is
   hand-written bytecode or a hand-written fact: the whole point is that the
   mechanism G-38 describes lives between the module fact and the row, so every
   link in that chain has to be the shipped one.

The answer to (3) is the finding. A probe that only re-read the catalog file would
have reproduced G-38's own reasoning instead of testing it.
"""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import replace
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "src"))

from sextant.application.ports.catalogs import Catalog
from sextant.application.ports.scanner import ScanRequest
from sextant.application.resolve.dependencies import DEPENDENCY_GATED
from sextant.application.resolve.endpoints import derive_endpoints
from sextant.domain.closed_sets import OriginTier
from sextant.domain.factfile import write_fact_file
from sextant.domain.facts import Document, ModuleFact
from sextant.ingress.catalogs.yaml_source import YamlCatalogSource
from sextant.ingress.extract.jvm.scanner import AsmScanner
from sextant.resources import extractor_jar
from sextant.storage.duckdb.workspace import DuckDbWorkspace

M2 = Path.home() / ".m2" / "repository"
CATALOGS = REPO / "src" / "sextant" / "catalogs"

# The predicate each framework's handler mapping uses to decide which beans it
# scans. Same simple name in both artifacts, different packages.
HANDLER_MAPPING = {
    "org.springframework:spring-webmvc": (
        "org/springframework/web/servlet/mvc/method/annotation/RequestMappingHandlerMapping"
    ),
    "org.springframework:spring-webflux": (
        "org/springframework/web/reactive/result/method/annotation/RequestMappingHandlerMapping"
    ),
}
VERSIONS = ("6.1.6", "7.0.2")

# One `javap -c` instruction line: ordinal, mnemonic, then operands and any
# trailing `// comment`. Loose on operands for CP-11's reason — a pattern
# assuming exactly one silently ENDS the body at `invokeinterface #25,  2`.
_INSTRUCTION = re.compile(r"^\s*\d+:\s+(\S+)(.*)$")
_STEP = " ; "

# The compile-time classpath for the four shapes. Pinned to one minor so the
# class files this probe scans are the ones its own table names.
COMPILE_JARS = (
    "org/springframework/spring-context/6.1.6/spring-context-6.1.6.jar",
    "org/springframework/spring-core/6.1.6/spring-core-6.1.6.jar",
    "org/springframework/spring-web/6.1.6/spring-web-6.1.6.jar",
    "io/projectreactor/reactor-core/3.6.5/reactor-core-3.6.5.jar",
    # `Mono` implements `org.reactivestreams.Publisher`, and javac refuses a call
    # on a type whose supertype it cannot read. Reactor declares this coordinate
    # rather than shipping the interface.
    "org/reactivestreams/reactive-streams/1.0.4/reactive-streams-1.0.4.jar",
)

# The build a WebFlux application declares, and nothing else. `spring-webmvc` is
# deliberately absent: it is the coordinate G-38 says the gate demands.
WEBFLUX_ONLY = ("org.springframework:spring-webflux",)
# The control. Same four classes, a build that declares the MVC coordinate.
WEBMVC_ONLY = ("org.springframework:spring-webmvc",)

# The four shapes, named by the sentence in G-38 that each one stands for.
SHAPES = {
    "PlainController": (
        "@Controller + @GetMapping, returning a view name",
        """
package com.acme;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
public class PlainController {
    @GetMapping("/plain")
    public String plain() { return "view"; }
}
""",
    ),
    "ResponseBodyController": (
        "@Controller + @ResponseBody (G-38's first named shape)",
        """
package com.acme;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ResponseBody;

@Controller
public class ResponseBodyController {
    @GetMapping("/responsebody")
    @ResponseBody
    public String body() { return "payload"; }
}
""",
    ),
    "ReactiveController": (
        "@Controller returning Mono<String> (G-38's second named shape)",
        """
package com.acme;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import reactor.core.publisher.Mono;

@Controller
public class ReactiveController {
    @GetMapping("/reactive")
    public Mono<String> reactive() { return Mono.just("payload"); }
}
""",
    ),
    "RestControllerShape": (
        "@RestController (the shape spring-web.yml names)",
        """
package com.acme;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class RestControllerShape {
    @GetMapping("/rest")
    public String rest() { return "payload"; }
}
""",
    ),
}

# The two catalogs whose `type_annotation` is `@Controller` and `@RestController`.
HTTP_CATALOGS = ("spring-mvc", "spring-web")


class ProbeError(RuntimeError):
    """A run that could not answer, told apart from a run that answered `no`."""


def jar(relative: str) -> Path:
    found = M2 / relative
    if not found.exists():
        raise ProbeError(f"{found} is absent; `run.sh` resolves it — run this through run.sh")
    return found


def self_reported_version(archive: Path) -> str:
    """The version the jar's own manifest claims (GUIDELINES §5.4). A cell filed
    under a version the artifact did not claim is a cell filed under the path it
    was downloaded to, which is a claim about this machine's cache."""
    with zipfile.ZipFile(archive) as zf:
        try:
            manifest = zf.read("META-INF/MANIFEST.MF").decode("utf-8", "replace")
        except KeyError:
            return "no manifest"
    for line in manifest.splitlines():
        if line.startswith("Implementation-Version:"):
            return line.split(":", 1)[1].strip()
    return "manifest states no version"


def is_handler_body(archive: Path, internal_name: str) -> str:
    """`isHandler`'s instruction sequence, verbatim from the jar."""
    result = subprocess.run(
        ["javap", "-p", "-c", "-cp", str(archive), internal_name.replace("/", ".")],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise ProbeError(f"javap failed on {internal_name} in {archive}:\n{result.stderr}")
    steps: list[str] = []
    inside = False
    for line in result.stdout.splitlines():
        if "isHandler" in line and line.strip().endswith(";"):
            inside = True
            continue
        if not inside:
            continue
        matched = _INSTRUCTION.match(line)
        if matched is None:
            if steps:
                break
            continue
        mnemonic, operands = matched.group(1), matched.group(2)
        comment = operands.split("//", 1)
        steps.append(f"{mnemonic}{(' ' + comment[1].strip()) if len(comment) > 1 else ''}")
    if not steps:
        raise ProbeError(f"no isHandler body found in {internal_name} ({archive})")
    return _STEP.join(steps)


def catalog(catalog_id: str) -> Catalog:
    found = next((c for c in YamlCatalogSource(CATALOGS).load() if c.id == catalog_id), None)
    if found is None:
        raise ProbeError(f"no shipped catalog has id {catalog_id!r}")
    return found


def compile_shapes(into: Path) -> Path:
    """The four shapes, compiled by javac against the real jars. Real bytecode
    rather than hand-written facts, because the mechanism under test lives
    between the module fact and the row and every link has to be the shipped one."""
    sources = into / "src" / "com" / "acme"
    sources.mkdir(parents=True)
    for name, (_, body) in SHAPES.items():
        (sources / f"{name}.java").write_text(body.lstrip())
    classes = into / "classes"
    classes.mkdir()
    classpath = ":".join(str(jar(relative)) for relative in COMPILE_JARS)
    result = subprocess.run(
        ["javac", "-cp", classpath, "-d", str(classes), *[str(p) for p in sources.glob("*.java")]],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise ProbeError(f"javac failed:\n{result.stdout}\n{result.stderr}")
    return classes


def write_module_fact(facts: Path, coordinates: tuple[str, ...]) -> None:
    write_fact_file(
        facts / "module.jsonl",
        Document(
            document_id="doc_module",
            relative_path="pom.xml",
            module_id="com.acme:webflux-service",
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
                module_id="com.acme:webflux-service",
                module_kind="service",
                languages=["java"],
                source_roots=["src/main/java"],
                output_dirs=["target/classes"],
                dependency_coordinates=list(coordinates),
            )
        ],
    )


def derived(
    classes: Path, coordinates: tuple[str, ...], override: Catalog | None = None
) -> tuple[list[dict], list]:
    """The rows and the skips a build declaring `coordinates` produces, from the
    real scanner over the real class files.

    `override` replaces the `spring-mvc` catalog with a modified copy, so a run
    can ask what the NARROWED list would have derived without editing the shipped
    file. `spring-web` is loaded as shipped either way."""
    scanner = AsmScanner(extractor_jar())
    with tempfile.TemporaryDirectory() as into:
        root = Path(into)
        facts = root / "facts"
        facts.mkdir()
        scanner.scan(
            ScanRequest(
                module_id="com.acme:webflux-service",
                coordinates="com.acme/webflux-service",
                version="1.0.0",
                classes_dir=classes,
                out_dir=facts,
            )
        )
        write_module_fact(facts, coordinates)
        workspace = DuckDbWorkspace(root / "ws.duckdb")
        workspace.load_facts(facts)
        loaded = [
            override
            if (override is not None and catalog_id == "spring-mvc")
            else catalog(catalog_id)
            for catalog_id in HTTP_CATALOGS
        ]
        skipped = derive_endpoints(workspace, loaded, capabilities=set(scanner.capabilities()))
        rows = workspace.query("endpoints")
        workspace.close()
    return rows, skipped


def main() -> None:
    print("## Observations\n")
    print(
        "Generated by `scripts/probes/w17_webflux_controller/run.sh` — every cell below is "
        "that run's own output, and this document pastes it verbatim.\n"
    )
    print(
        "**Each column header is the version the JAR ITSELF reported**, read out of its own "
        "`META-INF/MANIFEST.MF` `Implementation-Version` — not the version the loop asked "
        "for, which is only the path this machine cached the artifact at. The run ABORTS "
        "when the two disagree rather than printing a row, which is the CP-5 failure this "
        "rule exists for: eight cells labelled with a version the process never ran.\n"
    )

    print("### 1. The two handler predicates\n")
    # Columns ARE the configurations (§5.4), so a cell cannot be read without the
    # identity it was measured under. Built before anything prints, because a
    # version mismatch has to abort ahead of the header rather than under it.
    measured: dict[str, dict[str, str]] = {}
    for version in VERSIONS:
        for artifact, internal in HANDLER_MAPPING.items():
            group, name = artifact.split(":")
            archive = jar(f"{group.replace('.', '/')}/{name}/{version}/{name}-{version}.jar")
            claimed = self_reported_version(archive)
            if claimed != version:
                raise ProbeError(
                    f"{archive} was requested as {version} and its own manifest claims "
                    f"{claimed!r}. Every cell would be filed under a version the artifact "
                    f"did not report. Fix the cache or the artifact list; do not print it."
                )
            measured.setdefault(artifact, {})[claimed] = is_handler_body(archive, internal)
    columns = sorted({v for row in measured.values() for v in row})
    print("| artifact | " + " | ".join(columns) + " |")
    print("| --- |" + " --- |" * len(columns))
    for artifact, row in sorted(measured.items()):
        print(f"| `{artifact}` | " + " | ".join(f"`{row[c]}`" for c in columns) + " |")
    print()
    for column in columns:
        seen = {row[column] for row in measured.values()}
        verdict = "IDENTICAL" if len(seen) == 1 else "DIFFERENT"
        print(f"- At {column} the two predicates are **{verdict}**.")
    # Computed, not asserted: the sentence that follows is only true while every
    # verdict above says IDENTICAL, and a probe that prints DIFFERENT and then
    # this paragraph would be its own contradiction.
    if all(len({row[c] for row in measured.values()}) == 1 for c in columns):
        print(
            "\nSo nothing on the class separates an MVC controller from a WebFlux one. Any fix "
            "that tried to read the difference off the class is unbuildable, which is what "
            "makes the question a question about the BUILD.\n"
        )
    else:
        print(
            "\n**The predicates DIVERGE at one of the versions above.** A fact on the class "
            "can separate the two stacks at that version, and every conclusion below — which "
            "assumes it cannot — has to be re-derived before it is used.\n"
        )

    print("### 2. Is `spring-mvc.yml`'s coordinate read at all?\n")
    print(
        "| catalog | style | `detect.coordinates` | style is dependency-gated | `detect.required` | coordinate honoured |"
    )
    print("| --- | --- | --- | --- | --- | --- |")
    for catalog_id in HTTP_CATALOGS:
        loaded = catalog(catalog_id)
        gated = loaded.style in DEPENDENCY_GATED
        required = bool(getattr(loaded, "detect_required", False))
        honoured = "yes" if (gated or required) else "**no**"
        coordinates = ", ".join(f"`{c}`" for c in loaded.detect_coordinates) or "—"
        print(
            f"| `{catalog_id}` | `{loaded.style}` | {coordinates} | "
            f"{'yes' if gated else 'no'} | {'yes' if required else 'no'} | {honoured} |"
        )
    print(f"\n- `DEPENDENCY_GATED` is `{sorted(DEPENDENCY_GATED)}`.\n")

    print("### 3. What a WebFlux-only build actually derives\n")
    print(
        "Four runs, not two. The shipped catalog now names BOTH coordinates, so a run "
        "against it alone can no longer tell an inert list from an honoured one — the "
        "table would look the same either way. The last two runs narrow the list back to "
        "`spring-webmvc` in memory, which is the state G-38 read, so this section carries "
        "its own control rather than depending on section 2 to interpret it.\n"
    )
    narrowed = replace(catalog("spring-mvc"), detect_coordinates=(WEBMVC_ONLY[0],))
    with tempfile.TemporaryDirectory() as workdir:
        classes = compile_shapes(Path(workdir))
        runs = (
            ("WebFlux only, catalog as shipped", WEBFLUX_ONLY, None),
            ("MVC only, catalog as shipped", WEBMVC_ONLY, None),
            (
                "WebFlux only, list narrowed to `spring-webmvc` (G-38's reading)",
                WEBFLUX_ONLY,
                narrowed,
            ),
            ("MVC only, list narrowed to `spring-webmvc`", WEBMVC_ONLY, narrowed),
        )
        for label, coordinates, override in runs:
            rows, skipped = derived(classes, coordinates, override)
            print(f"**Build declares {', '.join(f'`{c}`' for c in coordinates)} — {label}.**\n")
            print("| shape | path | method | protocol | derived by |")
            print("| --- | --- | --- | --- | --- |")
            by_path = {row["path"]: row for row in rows}
            for name, (description, _) in SHAPES.items():
                path = {
                    "PlainController": "/plain",
                    "ResponseBodyController": "/responsebody",
                    "ReactiveController": "/reactive",
                    "RestControllerShape": "/rest",
                }[name]
                row = by_path.get(path)
                if row is None:
                    print(f"| {description} | `{path}` | — | — | **NOTHING DERIVED** |")
                else:
                    print(
                        f"| {description} | `{row['path']}` | {row['method']} | "
                        f"{row['protocol']} | `{row['catalog_id']}` |"
                    )
            names = sorted({s.catalog_id for s in skipped})
            print(f"\nCatalogs skipped: {names if names else 'none'}\n")


if __name__ == "__main__":
    try:
        main()
    except ProbeError as error:
        print(f"PROBE COULD NOT ANSWER: {error}", file=sys.stderr)
        raise SystemExit(2) from error
