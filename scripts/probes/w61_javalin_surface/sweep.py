"""W61 — Javalin's registration methods, and which argument position (if any)
carries the route.

`javalin.yml` (`javalin-routing`) reads `Javalin`/`JavalinDefaultRoutingApi`/
`JavalinDefaultRouting`'s flat verb methods — `get`, `post`, `put`, `delete`,
`patch`, `head`, `options` — each a `default` method on
`JavalinDefaultRoutingApi<API>`, an interface exactly two types implement:
`Javalin` (`app.get(...)`) and `public final class JavalinDefaultRouting`, reached
through `RouterConfig.mount(Consumer<JavalinDefaultRouting>)`
(`config.router.mount(router -> router.get(...))`) — found on review, the SECOND
flat registration form, no nesting, same descriptors. Before any row is written the
question is mechanical: of every method matching
`get|post|put|delete|patch|head|options|addHttpHandler|path|sse|ws` on
`JavalinDefaultRoutingApi`, `JavalinDefaultRouting`, `ApiBuilder` and `Javalin`
itself, which parameter position (if any) carries a value shaped like a route — a
plain `String` path?

**Version scope (§5.4).** Read against **javalin 6.4.0** — the version the jar
reports for itself, checked against the coordinate before any table is printed.
`fixtures/orders-javalin/pom.xml` pins the same version.
"""

import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
M2 = Path.home() / ".m2" / "repository"

# (coordinate, internal class, the method-name regex this class's registration
# methods are read through — the same pattern across all four types, per w61's
# brief).
_NAME_PATTERN = r"get|post|put|delete|patch|head|options|addHttpHandler|path|sse|ws"
CLASSES = (
    ("io.javalin:javalin:6.4.0", "io/javalin/router/JavalinDefaultRoutingApi"),
    ("io.javalin:javalin:6.4.0", "io/javalin/router/JavalinDefaultRouting"),
    ("io.javalin:javalin:6.4.0", "io/javalin/apibuilder/ApiBuilder"),
    ("io.javalin:javalin:6.4.0", "io/javalin/Javalin"),
)

# The one JVM parameter shape a route arrives as in this API — a plain path
# string. Unlike w60's four topic shapes, Javalin never takes a `Collection` or
# `Pattern` of routes, so this probe checks for exactly one.
_ROUTE_SHAPE = "Ljava/lang/String;"


class ProbeError(RuntimeError):
    """Anything that would otherwise put an unmeasured cell in a table."""


def resolve(artifact: str) -> Path:
    group, name, version = artifact.split(":")
    jar = M2 / Path(group.replace(".", "/")) / name / version / f"{name}-{version}.jar"
    if not jar.is_file():
        subprocess.run(
            ["mvn", "-q", "-B", "dependency:get", "-Dtransitive=false", f"-Dartifact={artifact}"],
            cwd=REPO,
            capture_output=True,
            check=False,
        )
    if not jar.is_file():
        raise ProbeError(f"{artifact} did not resolve; fix the coordinate in run.sh")
    return jar


def self_reported_version(jar: Path) -> tuple[str, str]:
    """The version the jar records about ITSELF (§5.4).

    Javalin writes BOTH a Maven `pom.properties` and a manifest
    `Implementation-Version:` (measured with `unzip -l` before this was written,
    unlike Kafka Streams — w60 — which writes neither). `pom.properties` is
    checked first, the same order CP-10's harness uses.
    """
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
        except KeyError:
            manifest = ""
        for line in manifest.splitlines():
            if line.lower().startswith("implementation-version:"):
                return line.split(":", 1)[1].strip(), "MANIFEST.MF"
    raise ProbeError(f"{jar.name} states no version in its pom.properties nor its manifest")


def checked(artifact: str) -> tuple[Path, str, str]:
    jar = resolve(artifact)
    reported, source = self_reported_version(jar)
    requested = artifact.split(":")[2]
    if reported != requested:
        raise ProbeError(
            f"{jar.name} reports {reported!r} in its own {source} while the coordinate asked "
            f"for {requested!r}."
        )
    return jar, reported, source


def _javap(jar: Path, internal: str, *flags: str) -> str:
    with tempfile.TemporaryDirectory() as into:
        try:
            with zipfile.ZipFile(jar) as archive:
                archive.extract(f"{internal}.class", into)
        except KeyError as missing:
            raise ProbeError(f"{jar.name} does not carry {internal}") from missing
        completed = subprocess.run(
            ["javap", *flags, str(Path(into) / f"{internal}.class")],
            capture_output=True,
            text=True,
            check=False,
        )
    if completed.returncode != 0:
        raise ProbeError(f"javap failed on {internal}: {completed.stderr.strip()}")
    return completed.stdout


def route_methods(jar: Path, internal: str, name_pattern: str) -> list[tuple[str, str]]:
    """`(method name, descriptor)` for every public method on `internal` whose name
    matches `name_pattern` — `javap -p -s`'s own output, a signature line then its
    `descriptor:` line directly below (the `w60` precedent's own parse)."""
    text = _javap(jar, internal, "-p", "-s")
    pattern = re.compile(rf"public .*? ({name_pattern})\(.*?\n\s+descriptor: (\S+)")
    return [(name, descriptor) for name, descriptor in re.findall(pattern, text)]


def _parameter_types(descriptor: str) -> list[str]:
    """The parameter portion of a JVM descriptor, split into one erased type per
    slot — `domain/symbols.parameter_types`'s own algorithm, restated here so this
    probe has no import dependency on the shipped engine it is measuring against."""
    params = descriptor[1 : descriptor.index(")")]
    types = []
    i = 0
    while i < len(params):
        start = i
        while params[i] == "[":
            i += 1
        if params[i] == "L":
            i = params.index(";", i) + 1
        else:
            i += 1
        types.append(params[start:i])
    return types


def route_argument(descriptor: str) -> int | None:
    """The position of the first parameter shaped like a route — a plain `String`
    — or `None` when no parameter carries one at all (`addHttpHandler`'s answer,
    whose first parameter is the verb ENUM, not a route)."""
    for index, parameter in enumerate(_parameter_types(descriptor)):
        if parameter == _ROUTE_SHAPE:
            return index
    return None


def main() -> None:
    coordinates = list(dict.fromkeys(coordinate for coordinate, _ in CLASSES))
    read = {c: checked(c) for c in coordinates}

    print("## Observations\n")
    print("Verbatim from `scripts/probes/w61_javalin_surface/run.sh`, which runs")
    print("`sweep.py`. **Every version in the headers below is the one the JAR itself")
    print("reported** — out of its own `META-INF/maven/.../pom.properties` or its")
    print("manifest's `Implementation-Version` — and **not the version the coordinate")
    print("list asked for**; `checked` compares the two and ABORTS when they disagree.\n")
    versions: list[str] = []
    for coordinate in read:
        version = coordinate.split(":")[2]
        if version not in versions:
            versions.append(version)
    print("| what the run read | " + " | ".join(versions) + " |")
    print("|---|" + "---|" * len(versions))
    for label, pick in (("artifacts reporting this version", 1), ("where the jar states it", 2)):
        cells = []
        for version in versions:
            names = [
                (c.split(":")[1] if pick == 1 else read[c][2])
                for c in read
                if c.split(":")[2] == version
            ]
            cells.append(", ".join(dict.fromkeys(names)))
        print(f"| {label} | " + " | ".join(cells) + " |")
    print()

    print("### Every method matching `get|post|put|delete|patch|head|options|")
    print("### addHttpHandler|path|sse|ws`, and which position (if any) carries a route\n")
    for coordinate, internal in CLASSES:
        jar = read[coordinate][0]
        methods = route_methods(jar, internal, _NAME_PATTERN)
        print(f"**`{internal.replace('/', '.')}`** ({coordinate})\n")
        print("| # | method | descriptor | route argument |")
        print("|---|---|---|---|")
        if not methods:
            # `_NAME_PATTERN` itself contains `|`, and inside a table ROW every
            # unescaped `|` divides a cell — even inside backticks
            # (`tests/architecture/test_markdown_tables.py`'s own rule). `\|` is the
            # only thing that protects one.
            escaped_pattern = _NAME_PATTERN.replace("|", r"\|")
            print(f"| — | *(no `{escaped_pattern}` method found)* | — | — |")
            print()
            continue
        for n, (name, descriptor) in enumerate(methods, start=1):
            position = route_argument(descriptor)
            cell = str(position) if position is not None else "*(none)*"
            print(f"| {n} | `{name}` | `{descriptor}` | {cell} |")
        print()


if __name__ == "__main__":
    try:
        main()
    except ProbeError as error:
        print(f"probe aborted: {error}", file=sys.stderr)
        raise SystemExit(1) from error
