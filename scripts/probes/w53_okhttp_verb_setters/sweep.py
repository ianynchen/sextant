"""W53 — every verb-setting method `okhttp3.Request$Builder` declares (`G-22`).

`okhttp.yml`'s `roots` entry defaults `http_method: GET`, because that is
OkHttp's own default for a `Request.Builder`. The default is only safe while the
catalog's verb-setter list is COMPLETE: a setter the list misses falls through as
an unmatched step (D02 §4), the default stands uncorrected, and the row publishes
a confidently wrong verb rather than an honest gap.

The file already said the list was "measured rather than remembered ... on okhttp
3.14.9 and 4.12.0". **CP-11 measured 4.12.0 alone**, and its own `measured:` block
recorded `["4.12.0"]`; `3.14.9` appeared nowhere else in the repository. An
unmeasured version presented as measured is `G-22`, and the remedy is to measure
it rather than to delete the claim — both jars resolve.

**Version scope (§5.4).** Read against **okhttp 3.14.9** and **okhttp 4.12.0**.
The 3.x line is Java and the 4.x line is Kotlin, which is exactly why reading both
matters: a Kotlin default argument compiles to extra overloads, so "the same eight"
is a claim about two different compilers' output and not one.
"""

import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
M2 = Path.home() / ".m2" / "repository"

ARTIFACTS = ("com.squareup.okhttp3:okhttp:3.14.9", "com.squareup.okhttp3:okhttp:4.12.0")
BUILDER = "okhttp3/Request$Builder"

# The eight the catalog encodes, by NAME and erased argument list — the pairing a
# `single_call`/`fluent` step matches on. Listed here so the probe can report a
# difference rather than only printing what it found, which is how a missing ninth
# would be noticed.
CLAIMED = (
    "get()",
    "head()",
    "post(okhttp3.RequestBody)",
    "put(okhttp3.RequestBody)",
    "patch(okhttp3.RequestBody)",
    "delete()",
    "delete(okhttp3.RequestBody)",
    "method(java.lang.String, okhttp3.RequestBody)",
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
    # OkHttp's own route, and CP-11's: the 4.x jars carry no maven metadata and no
    # `Implementation-Version`, but DO compile their version into a constant.
    # Measured: 4.12.0 states it only at `okhttp3.OkHttp.VERSION`, and 3.14.9
    # states it only in `pom.properties` — so a reader that knew just one of the
    # two would have to call one of these versions unmeasurable.
    try:
        constants = _javap(jar, "okhttp3/OkHttp", "-p", "-constants")
    except ProbeError:
        constants = ""
    for line in constants.splitlines():
        if "VERSION" in line and "=" in line:
            return line.split("=", 1)[1].strip().strip('";'), "okhttp3.OkHttp.VERSION"
    raise ProbeError(
        f"{jar.name} states no version in its pom.properties, its manifest, or "
        f"okhttp3.OkHttp.VERSION"
    )


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


def builder_methods(jar: Path) -> list[str]:
    """EVERY method on `Request$Builder` that returns the builder, as `name(args)`.

    Selected by return type alone, and deliberately not narrowed by name. The
    first version of this function filtered on the seven verb names the catalog
    already encodes, which made its headline result — "declared and not encoded:
    none" — true by construction: a ninth verb, or any overload the catalog does
    not carry, was excluded before the comparison ran. The one this file exists to
    read both compilers for is exactly such a case: at 4.12.0 the Kotlin default
    argument on `delete()` emits a static `delete$default(...)` bridge, which the
    name filter dropped while the document argued that the two compilers are why
    reading both matters. Caught in review of W53.

    So the table below carries `url`, `header`, `tag` and the rest too. That is
    noisier and it is the only way the comparison means anything: a method this
    probe never looked at cannot be reported as missing.
    """
    body = _javap(jar, BUILDER, "-p")
    found = []
    for line in body.splitlines():
        stripped = line.strip().rstrip(";")
        if "Request$Builder " not in stripped or "(" not in stripped:
            continue
        signature = stripped.split("Request$Builder ", 1)[1]
        if signature.startswith("("):  # the constructor, not a method
            continue
        found.append(signature)
    if not found:
        raise ProbeError(
            f"no method on {BUILDER} returns the builder in {jar.name} — the class or the "
            f"javap output shape moved, and an empty table here would read as 'OkHttp "
            f"declares no verb setters'"
        )
    return sorted(set(found))


def main() -> None:
    read = {artifact.split(":")[2]: checked(artifact) for artifact in ARTIFACTS}

    print("## Observations\n")
    print("Verbatim from `scripts/probes/w53_okhttp_verb_setters/run.sh`, which runs")
    print("`sweep.py`. **Every version in the headers below is the one the JAR itself")
    print("reported** — out of its own `pom.properties`, its manifest, or, where the 4.x")
    print("jars carry neither, the `ConstantValue` of `okhttp3.OkHttp.VERSION`; and")
    print("**not the version the coordinate list asked for**; `checked` compares the two")
    print("and ABORTS when they disagree, rather than printing a version it did not read.\n")
    versions = sorted(read)
    print("| what the run read | " + " | ".join(versions) + " |")
    print("|---|" + "---|" * len(versions))
    print("| artifact reporting this version | " + " | ".join(["okhttp"] * len(versions)) + " |")
    print(
        "| where the jar states that version | " + " | ".join(read[v][2] for v in versions) + " |\n"
    )

    print("### Every method that returns the builder, at both versions\n")
    print("Not only the seven verb names: filtering to those would make the last column's")
    print("`none` true by construction. A method this probe never opened cannot be reported")
    print("as missing.\n")
    print("| method | " + " | ".join(versions) + " | in the catalog |")
    print("|---|" + "---|" * (len(versions) + 1))
    declared = {version: builder_methods(read[version][0]) for version in versions}
    every = sorted({name for names in declared.values() for name in names})
    missing = []
    for name in every:
        cells = ["yes" if name in declared[v] else "—" for v in versions]
        if name in CLAIMED:
            verdict = "**encoded**"
        elif "$default" in name:
            # A Kotlin default-argument bridge, not a distinct verb: it forwards to
            # the method it defaults. `COVERAGE.md` files `$default` synthetics as
            # unsupported generally, so this is a stated boundary rather than a gap
            # this catalog opened — said outright instead of filtered away.
            verdict = "synthetic `$default` bridge — stated boundary"
        else:
            verdict = "not a verb setter"
            if name.split("(")[0] in {"get", "head", "post", "put", "patch", "delete", "method"}:
                verdict = "**A VERB SETTER THE CATALOG MISSES**"
                missing.append(name)
        print(f"| `{name}` | " + " | ".join(cells) + f" | {verdict} |")
    print()
    print(f"**Verb setters declared and not encoded:** {missing or 'none'}.")

    unread = sorted(set(CLAIMED) - set(every))
    print(f"**Encoded and not declared at either version:** {unread or 'none'}.")


if __name__ == "__main__":
    try:
        main()
    except ProbeError as error:
        print(f"probe aborted: {error}", file=sys.stderr)
        raise SystemExit(1) from error
