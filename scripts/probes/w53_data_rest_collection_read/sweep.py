"""W53 — does every exposed Spring Data repository serve a collection GET?

`spring-data-rest.yml` derived `GET /<collection>` for every exposed repository
with no `needs:` at all, on a belief written into the file: *"the collection read
is the one route every exposed repository serves, whatever it extends."*

CP-2 observed that live on `CrudRepository`, `JpaRepository` and
`PagingAndSortingRepository` — all three of which DECLARE a `findAll` — and never
exercised a repository extending the bare marker `Repository<T, ID>`. A rule taken
from the cases a probe happened to cover is a prediction about the ones it did not
(GUIDELINES §8.1), so this probe reads the framework's own decision instead.

Three questions, each answered by opening a class file rather than by running an
application:

1. **What decides the collection's HTTP methods?**
   `CrudMethodsSupportedHttpMethods.getMethodsFor(ResourceType)` is the one place
   Spring Data REST assembles them. If GET is added unconditionally, the catalog
   was right; if it is guarded, the guard is the rule the catalog needs.
2. **What does that guard resolve to?** `exposesFindAll()` is a `Lazy<Boolean>`
   over `CrudMethods`, and `DefaultCrudMethods` is what populates it.
3. **Which repository interfaces actually declare a `findAll`?** That is the fact
   the catalog encodes, one row per contract — and it must be read off the
   interfaces, because an inherited method counts and a marker interface has none.
"""

import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
M2 = Path.home() / ".m2" / "repository"

# The artifact that DECIDES, and the two spring-data-commons versions the catalog
# already cites — read at both so the answer is not a property of one release.
REST_CORE = "org.springframework.data:spring-data-rest-core:5.0.1"
COMMONS = (
    "org.springframework.data:spring-data-commons:3.2.5",
    "org.springframework.data:spring-data-commons:4.0.1",
)
JPA = "org.springframework.data:spring-data-jpa:4.1.1"

SUPPORTED_METHODS = "org/springframework/data/rest/core/mapping/CrudMethodsSupportedHttpMethods"
EXPOSURE_AWARE = (
    "org/springframework/data/rest/core/mapping/"
    "CrudMethodsSupportedHttpMethods$DefaultExposureAwareCrudMethods"
)
DEFAULT_CRUD_METHODS = "org/springframework/data/repository/core/support/DefaultCrudMethods"

# Every contract `spring-data-rest.yml` enumerates, in the artifact that ships it.
CONTRACTS = (
    ("org/springframework/data/repository/Repository", "commons"),
    ("org/springframework/data/repository/CrudRepository", "commons"),
    ("org/springframework/data/repository/ListCrudRepository", "commons"),
    ("org/springframework/data/repository/PagingAndSortingRepository", "commons"),
    ("org/springframework/data/repository/ListPagingAndSortingRepository", "commons"),
    ("org/springframework/data/jpa/repository/JpaRepository", "jpa"),
)


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
    """The version the ARCHIVE states for itself, and where. Raises rather than
    defaulting: a missing self-report is where a hand-written column would go
    unchallenged (CP-5)."""
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


def checked(artifact: str) -> tuple[Path, str, str]:
    jar = resolve(artifact)
    reported, source = self_reported_version(jar)
    requested = artifact.split(":")[2]
    if reported != requested:
        raise ProbeError(
            f"{jar.name} reports {reported!r} in its own {source} while the coordinate asked "
            f"for {requested!r}. Fix run.sh rather than labelling a column with a version this "
            f"run did not read."
        )
    return jar, reported, source


def _javap(jar: Path, internal: str, *flags: str) -> str:
    """`javap` output for one class. ABORTS when the jar does not carry it: an
    empty string reaches these tables as the probe's own conclusions."""
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


def collection_get_is_guarded(jar: Path) -> tuple[bool, str]:
    """Whether `getMethodsFor` adds GET to a COLLECTION only behind a test, and the
    name of the test.

    Read off the bytecode rather than off a decompiled source: the switch arm for
    the collection resource calls one predicate, branches on it with `ifeq`, and
    only then adds `GET`. An unconditional add would have no `ifeq` between the
    predicate and the `HttpMethod.GET` field read.

    **Every failure to read that shape ABORTS.** The first version of this function
    returned `(False, "")` when it reached a `HttpMethod.GET` line having seen no
    predicate — which the document renders as "adds GET with no guard", the probe's
    own expectation row 1, *"the catalog was right"*. A parse that fell over would
    have published the conclusion this probe exists to test. It also never checked
    the `ifeq` its own docstring named, nor that the arm it had walked into was the
    COLLECTION one rather than the ITEM one; both are checked now, so a future
    release that emits the arms in the other order fails loudly instead of
    reporting `exposesFindOne` as the collection's guard. Caught in review of W53.
    """
    body = _javap(jar, SUPPORTED_METHODS, "-p", "-c")
    lines = [line.strip() for line in body.splitlines()]
    try:
        start = next(i for i, line in enumerate(lines) if "getMethodsFor" in line)
    except StopIteration as missing:
        raise ProbeError(f"{SUPPORTED_METHODS} declares no getMethodsFor") from missing

    # `ResourceType.COLLECTION` is the arm that adds POST; `ITEM` is the one that
    # adds DELETE. Identified by that rather than by position, so the check does not
    # rest on the order javac happened to emit.
    predicate = ""
    guarded = False
    seen_post = False
    for line in lines[start:]:
        if "exposes" in line and "InterfaceMethod" in line:
            predicate = f"exposes{line.split('exposes')[1].split(':')[0]}"
            guarded = False
        if line.split(":", 1)[-1].strip().startswith("ifeq") and predicate:
            guarded = True
        if "HttpMethod.POST" in line:
            seen_post = True
        if "HttpMethod.GET" in line:
            if not predicate:
                raise ProbeError(
                    f"{SUPPORTED_METHODS}'s getMethodsFor adds GET with no predicate read "
                    f"before it. That may mean the guard is gone — which would make the "
                    f"catalog's old unconditional route right — or that this parse no longer "
                    f"matches the bytecode. The two are not distinguishable here, so neither "
                    f"is published"
                )
            if not guarded:
                raise ProbeError(
                    f"{SUPPORTED_METHODS} calls {predicate} and adds GET with no `ifeq` "
                    f"between them; the branch shape this function reads has moved"
                )
            return True, predicate
    if seen_post:
        raise ProbeError(f"{SUPPORTED_METHODS}'s collection arm adds POST but never GET")
    raise ProbeError(f"{SUPPORTED_METHODS}'s getMethodsFor never adds GET")


def find_all_lookup(jar: Path) -> list[str]:
    """The method names `DefaultCrudMethods` looks up when populating the `findAll`
    slot — the concrete question `exposesFindAll` reduces to.

    The names are NOT in `selectMostSuitableFindAllMethod` itself: it builds two
    `Supplier`s with `invokedynamic` and hands them to `Optionals.firstNonEmpty`,
    so the string constants live in the synthetic `lambda$...` methods it captures
    into. Reading only the named method returns nothing at all, which is how the
    first run of this probe printed "none read" under a heading asserting the
    opposite — so the search covers every method whose name carries the lambda
    prefix, and ABORTS when it finds none rather than reporting an empty cell.
    """
    body = _javap(jar, DEFAULT_CRUD_METHODS, "-p", "-c")
    if "selectMostSuitableFindAllMethod" not in body:
        raise ProbeError("DefaultCrudMethods declares no selectMostSuitableFindAllMethod")
    reads: list[str] = []
    inside = False
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.endswith(");") and "(" in stripped:
            inside = "lambda$selectMostSuitableFindAllMethod" in stripped
        if inside and "// String " in stripped:
            name = stripped.split("// String ")[1].strip()
            if name not in reads:
                reads.append(name)
        # The ARGUMENT types the lookup pairs with that name. Reported because
        # "looks up `findAll`" alone does not say whether an inherited
        # `findAll(Pageable)` counts, which is the whole question for the two
        # paging contracts.
        if inside and "// class org/springframework/data/domain/" in stripped:
            argument = stripped.rsplit("/", 1)[1]
            if argument not in reads:
                reads.append(argument)
    if not reads:
        raise ProbeError(
            "no string constant read in any lambda$selectMostSuitableFindAllMethod — the "
            "lookup moved, and an empty cell here would read as 'the framework looks up "
            "nothing'"
        )
    return reads


def declares_find_all(jar: Path, internal: str) -> tuple[bool, int]:
    """Whether the interface declares any `findAll`, and how many methods it
    declares at all. The second number is what makes a marker interface visible as
    a marker rather than as an interface whose `findAll` this probe missed."""
    body = _javap(jar, internal, "-p")
    members = [
        line.strip()
        for line in body.splitlines()[2:]
        if line.strip() and not line.strip().startswith("}")
    ]
    return any("findAll" in member for member in members), len(members)


def main() -> None:
    rest_jar, rest_version, rest_source = checked(REST_CORE)
    jpa_jar, jpa_version, jpa_source = checked(JPA)
    commons = {artifact.split(":")[2]: checked(artifact) for artifact in COMMONS}

    print("## Observations\n")
    print("Verbatim from `scripts/probes/w53_data_rest_collection_read/run.sh`, which runs")
    print("`sweep.py`. **Every version in the headers below is the one the JAR itself")
    print("reported** — read out of its own `pom.properties` or manifest, and")
    print("**not the version the coordinate list asked for**; `checked` compares the two")
    print("and ABORTS when they disagree, rather than printing a version it did not read.\n")
    columns = [rest_version, *sorted(commons), jpa_version]
    print("| what the run read | " + " | ".join(columns) + " |")
    print("|---|" + "---|" * len(columns))
    artifacts = [
        "spring-data-rest-core",
        *["spring-data-commons"] * len(commons),
        "spring-data-jpa",
    ]
    print("| artifact reporting this version | " + " | ".join(artifacts) + " |")
    sources = [rest_source, *[commons[v][2] for v in sorted(commons)], jpa_source]
    print("| where the jar states that version | " + " | ".join(sources) + " |\n")

    # No `else` branch, deliberately. `collection_get_is_guarded` either finds the
    # predicate-then-`ifeq`-then-GET shape or raises, so there is no "unguarded"
    # value to render — the ambiguous case (guard genuinely gone vs. parse moved)
    # aborts the run rather than picking one of them to print.
    _, predicate = collection_get_is_guarded(rest_jar)
    print("### 1. What decides a COLLECTION's methods\n")
    print("`CrudMethodsSupportedHttpMethods.getMethodsFor` adds `GET` and `HEAD` to a")
    print(f"collection **only behind `{predicate}()`** — the predicate is called, the result")
    print("is branched on, and only then are the methods added.\n")

    print("### 2. What the guard reduces to\n")
    print("| spring-data-commons | what `DefaultCrudMethods` looks up for the findAll slot |")
    print("|---|---|")
    for version, (jar, _, _) in sorted(commons.items()):
        names = find_all_lookup(jar)
        print(f"| {version} | {', '.join(f'`{name}`' for name in names) or '**none read**'} |")
    print()

    print("### 3. Which contracts declare a `findAll`\n")
    versions = sorted(commons)
    columns = " | ".join(f"declares `findAll` ({version})" for version in versions)
    print(f"| interface | {columns} | methods it declares |")
    print("|---|" + "---|" * (len(versions) + 1))
    for internal, where in CONTRACTS:
        cells = []
        counts = []
        for version in versions:
            jar = jpa_jar if where == "jpa" else commons[version][0]
            found, total = declares_find_all(jar, internal)
            cells.append("yes" if found else "**no**")
            counts.append(str(total))
        name = internal.rsplit("/", 1)[1]
        # `JpaRepository` ships in one jar, so its two cells are one reading printed
        # twice; said here rather than left looking like two measurements.
        note = " *(one jar; spring-data-jpa 4.1.1)*" if where == "jpa" else ""
        print(f"| `{name}`{note} | {' | '.join(cells)} | {' / '.join(dict.fromkeys(counts))} |")


if __name__ == "__main__":
    try:
        main()
    except ProbeError as error:
        print(f"probe aborted: {error}", file=sys.stderr)
        raise SystemExit(1) from error
