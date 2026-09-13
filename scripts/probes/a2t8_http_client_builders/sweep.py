"""A2 Task 8 — every request-building method the JDK `HttpRequest.Builder` and Apache
HttpClient 5's `ClassicRequestBuilder` declare, and every executing call that consumes
what they build (`jdk-httpclient`, `apache-httpclient`; spec §12).

Both catalogs are `okhttp.yml`'s shape: a static root, verb-setting steps, a `build`
terminal joined to the client's executing call through the argument `source` id. The
JDK root seeds `http_method: GET` — the platform's own documented default for a fresh
builder — and, exactly as for OkHttp, that seed is safe only while EVERY verb-setting
method on the builder is a declared step: an undeclared one passes through uncaptured
and leaves the seed standing as a confidently wrong verb. So the builder is enumerated
whole, by return type, and the catalog's claim compared against it.

**Version scope (§5.4).** Read against **JDK 21.0.12.1** (`java.net.http`, `java.base`;
Temurin 21.0.12.1+1), **httpcore5 5.2.4** and **httpclient5 5.2.3**. The JDK version is
the one `$JAVA_HOME/release` states and `javap -version` prints; the two jars state
theirs in `META-INF/MANIFEST.MF`. `httpclient5` 5.2.3 pins `httpcore5` 5.2.4 through its
parent POM's `httpcore.version`, which is why the core jar is measured at 5.2.4 and not at
a version sharing the client's number.
"""

import os
import re
import subprocess
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
M2 = Path.home() / ".m2" / "repository"

ARTIFACTS = (
    "org.apache.httpcomponents.core5:httpcore5:5.2.4",
    "org.apache.httpcomponents.client5:httpclient5:5.2.3",
)
JDK_MODULES = ("java.net.http", "java.base")

# What the catalogs encode, by NAME and erased argument list — the pairing a `fluent`
# root/step matches on. Listed so the probe can report a DIFFERENCE, not only print.
JDK_ENCODED = {
    "java.net.http.HttpRequest": ("newBuilder()", "newBuilder(java.net.URI)"),
    # `<init>(java.lang.String)` is encoded too, through the form's `arity: 1`; it is
    # verdict-ed by name in `jdk_verdict` so the multi-argument constructors beside it
    # read as the boundary they are.
    "java.net.http.HttpRequest$Builder": (
        "uri(java.net.URI)",
        "GET()",
        "HEAD()",
        "DELETE()",
        "POST(java.net.http.HttpRequest$BodyPublisher)",
        "PUT(java.net.http.HttpRequest$BodyPublisher)",
        "method(java.lang.String, java.net.http.HttpRequest$BodyPublisher)",
        "build()",
    ),
    "java.net.http.HttpClient": (
        "send(java.net.http.HttpRequest, java.net.http.HttpResponse$BodyHandler<T>)",
        "sendAsync(java.net.http.HttpRequest, java.net.http.HttpResponse$BodyHandler<T>)",
        (
            "sendAsync(java.net.http.HttpRequest, java.net.http.HttpResponse$BodyHandler<T>, "
            "java.net.http.HttpResponse$PushPromiseHandler<T>)"
        ),
    ),
    "java.net.URI": ("create(java.lang.String)",),
}
JDK_VERB_NAMES = {"GET", "HEAD", "DELETE", "POST", "PUT", "method"}
APACHE_ENCODED = {
    "org.apache.hc.core5.http.io.support.ClassicRequestBuilder": tuple(
        f"{verb}({args})"
        for verb in ("get", "head", "post", "put", "delete", "patch", "trace", "options")
        for args in ("", "java.lang.String", "java.net.URI")
    )
    + ("create(java.lang.String)", "setUri(java.lang.String)", "setUri(java.net.URI)", "build()"),
    "org.apache.hc.client5.http.impl.classic.CloseableHttpClient": ("execute", "executeOpen"),
    "org.apache.hc.client5.http.classic.HttpClient": ("execute", "executeOpen"),
}
APACHE_REQUEST_CLASSES = (
    "HttpGet",
    "HttpHead",
    "HttpPost",
    "HttpPut",
    "HttpDelete",
    "HttpPatch",
    "HttpOptions",
    "HttpTrace",
)


class ProbeError(RuntimeError):
    """Anything that would otherwise put an unmeasured cell in a table."""


def java_home() -> Path:
    home = os.environ.get("JAVA_HOME")
    if not home:
        raise ProbeError("JAVA_HOME is unset; the JDK measured must be the one named")
    return Path(home)


def jdk_version() -> str:
    """The version the JDK states about ITSELF, twice, and the two must agree: the
    `release` file's `JAVA_VERSION` and what `javap -version` prints."""
    release = (java_home() / "release").read_text(encoding="utf-8")
    match = re.search(r'^JAVA_VERSION="([^"]+)"', release, re.MULTILINE)
    if match is None:
        raise ProbeError("$JAVA_HOME/release states no JAVA_VERSION")
    stated = match.group(1)
    printed = subprocess.run(
        [str(java_home() / "bin" / "javap"), "-version"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    if printed != stated:
        raise ProbeError(f"javap -version printed {printed!r}; $JAVA_HOME/release says {stated!r}")
    return stated


def resolve(artifact: str) -> Path:
    group, name, version = artifact.split(":")
    jar = M2 / Path(group.replace(".", "/")) / name / version / f"{name}-{version}.jar"
    if not jar.is_file():
        raise ProbeError(f"{artifact} is absent; run this through run.sh")
    return jar


def checked(artifact: str) -> tuple[Path, str]:
    jar = resolve(artifact)
    with zipfile.ZipFile(jar) as archive:
        manifest = archive.read("META-INF/MANIFEST.MF").decode("utf-8", "replace")
    reported = next(
        (
            line.split(":", 1)[1].strip()
            for line in manifest.splitlines()
            if line.lower().startswith("implementation-version:")
        ),
        None,
    )
    requested = artifact.split(":")[2]
    if reported != requested:
        raise ProbeError(
            f"{jar.name} reports {reported!r} in its own manifest while the coordinate asked "
            f"for {requested!r}. Fix run.sh rather than labelling a column with a version this "
            f"run did not read."
        )
    return jar, reported


def javap(owner: str, *, jar: Path | None = None, module: str | None = None) -> str:
    command = [str(java_home() / "bin" / "javap"), "-p", "-s"]
    command += ["--module", module] if module else ["-cp", str(jar)]
    completed = subprocess.run([*command, owner], capture_output=True, text=True, check=False)
    if completed.returncode != 0 or not completed.stdout.strip():
        raise ProbeError(f"javap failed on {owner}: {completed.stderr.strip()}")
    return completed.stdout


_MEMBER = re.compile(
    r"^\s+public\s+(?:(?:static|final|abstract|default)\s+)*(?:<[^>]+>\s+)?(.*?)\s+([\w$]+)\((.*?)\)(?:\s+throws\s+[\w.,$ ]+)?;\s*$"
)
_CONSTRUCTOR = re.compile(r"^\s+public\s+([\w.$]+)\((.*?)\)(?:\s+throws\s+[\w.,$ ]+)?;\s*$")


def members(text: str) -> list[tuple[str, str]]:
    """`(name(args), returns)` for every public method and constructor javap printed."""
    found: list[tuple[str, str]] = []
    for line in text.splitlines():
        method = _MEMBER.match(line)
        if method is not None:
            found.append((f"{method.group(2)}({method.group(3)})", method.group(1)))
            continue
        constructor = _CONSTRUCTOR.match(line)
        if constructor is not None:
            found.append((f"<init>({constructor.group(2)})", constructor.group(1)))
    if not found:
        raise ProbeError("javap printed no public members; the output shape moved")
    return found


def table(
    title: str, owner: str, rows: list[tuple[str, str]], encoded: tuple[str, ...], verdict
) -> None:
    print(f"### `{owner}` — {title}\n")
    print("| member | returns | in the catalog |")
    print("|---|---|---|")
    for name, returns in sorted(set(rows)):
        print(f"| `{name}` | `{returns}` | {verdict(name, encoded)} |")
    print()


def main() -> None:
    jdk = jdk_version()
    jars = {artifact.split(":")[1]: checked(artifact) for artifact in ARTIFACTS}

    print("## Observations\n")
    print("Generated by `scripts/probes/a2t8_http_client_builders/run.sh`, which runs")
    print("`sweep.py` — every cell below is that script's own output. **Every version in the")
    print("headers is the one the archive itself reported** — the JDK's out of its own")
    print("`release` file, checked against what `javap -version` printed; each jar's out of its")
    print("own `META-INF/MANIFEST.MF` — and **not the version the coordinate asked for**;")
    print("`checked` compares the two and ABORTS when they disagree.\n")
    print(
        f"| what the run read | {jdk} | "
        + " | ".join(jars[n][1] for n in ("httpcore5", "httpclient5"))
        + " |"
    )
    print("|---|---|---|---|")
    print(
        "| artifact reporting this version | JDK (`java.net.http`, `java.base` jmods) | httpcore5 | httpclient5 |"
    )
    print(
        "| where it states that version | `$JAVA_HOME/release`, `javap -version` | MANIFEST.MF | MANIFEST.MF |\n"
    )

    missing: list[str] = []

    def jdk_verdict(name: str, encoded: tuple[str, ...]) -> str:
        if name in encoded:
            return "**encoded**"
        bare = name.split("(")[0]
        if bare in JDK_VERB_NAMES:
            missing.append(name)
            return "**A VERB SETTER THE CATALOG MISSES**"
        if bare == "newBuilder":
            return "stated boundary — copies another request; its verb is that request's, the seeded GET is wrong for it"
        if name == "<init>(java.lang.String)":
            return "**encoded** — the `<init>` form with `arity: 1`, so only this constructor"
        if bare == "<init>":
            return (
                "stated boundary — argument 0 is a scheme, not an address; excluded by the "
                "form's `arity: 1`"
            )
        return "not a verb setter, address, or executing call"

    print(f"## The JDK at {jdk}\n")
    table(
        "the roots",
        "java.net.http.HttpRequest",
        [
            m
            for m in members(javap("java.net.http.HttpRequest", module="java.net.http"))
            if m[0].startswith("newBuilder")
        ],
        JDK_ENCODED["java.net.http.HttpRequest"],
        jdk_verdict,
    )
    builder = [
        m for m in members(javap("java.net.http.HttpRequest$Builder", module="java.net.http"))
    ]
    table(
        "every method, by return type",
        "java.net.http.HttpRequest$Builder",
        builder,
        JDK_ENCODED["java.net.http.HttpRequest$Builder"],
        jdk_verdict,
    )
    client = [
        m
        for m in members(javap("java.net.http.HttpClient", module="java.net.http"))
        if m[0].startswith("send")
    ]
    table(
        "the executing calls",
        "java.net.http.HttpClient",
        client,
        JDK_ENCODED["java.net.http.HttpClient"],
        jdk_verdict,
    )
    uri = [
        m
        for m in members(javap("java.net.URI", module="java.base"))
        if m[0].startswith(("create", "<init>"))
    ]
    table(
        "the factories `url_via` follows",
        "java.net.URI",
        uri,
        JDK_ENCODED["java.net.URI"],
        jdk_verdict,
    )
    print(f"**JDK verb setters declared and not encoded:** {missing or 'none'}.\n")
    every = {m[0] for m in builder} | {m[0] for m in client} | {m[0] for m in uri}
    every |= {m[0] for m in members(javap("java.net.http.HttpRequest", module="java.net.http"))}
    unread = sorted(set(sum(JDK_ENCODED.values(), ())) - every)
    print(f"**Encoded and not declared by the JDK:** {unread or 'none'}.\n")

    def apache_verdict(name: str, encoded: tuple[str, ...]) -> str:
        if name in encoded or name.split("(")[0] in encoded:
            return "**encoded**"
        if name.startswith("copy("):
            return "stated boundary — copies another request; not a root"
        if name.startswith("<init>"):
            return "**encoded** — a `<init>` root that is itself the terminal via `execute`"
        return "not a verb, address, or executing call"

    core, core_version = jars["httpcore5"]
    client_jar, client_version = jars["httpclient5"]
    print(f"## Apache HttpClient 5 at httpcore5 {core_version}, httpclient5 {client_version}\n")
    owner = "org.apache.hc.core5.http.io.support.ClassicRequestBuilder"
    rows = [
        m
        for m in members(javap(owner, jar=core))
        if m[0].split("(")[0]
        in {
            v
            for v in (
                "get",
                "head",
                "post",
                "put",
                "delete",
                "patch",
                "trace",
                "options",
                "create",
                "copy",
                "setUri",
                "build",
            )
        }
    ]
    table(
        "roots, the address step, the terminal", owner, rows, APACHE_ENCODED[owner], apache_verdict
    )
    for short in APACHE_REQUEST_CLASSES:
        owner = f"org.apache.hc.client5.http.classic.methods.{short}"
        rows = [m for m in members(javap(owner, jar=client_jar)) if m[0].startswith("<init>")]
        table("the constructor form", owner, rows, (), apache_verdict)
    # BOTH owners the catalog names: the interface declares `executeOpen` as a `default`
    # method the concrete class inherits without redeclaring, so an enumeration of
    # `CloseableHttpClient` alone printed eight `execute` overloads and no `executeOpen`
    # — and a catalog claiming "every executing call" on that table missed one (fix
    # round 2, found by review).
    for owner in (
        "org.apache.hc.client5.http.classic.HttpClient",
        "org.apache.hc.client5.http.impl.classic.CloseableHttpClient",
    ):
        rows = [m for m in members(javap(owner, jar=client_jar)) if m[0].startswith("execute")]
        table(
            "the executing calls, every overload",
            owner,
            rows,
            APACHE_ENCODED[owner],
            apache_verdict,
        )


if __name__ == "__main__":
    try:
        main()
    except ProbeError as error:
        print(f"probe aborted: {error}", file=sys.stderr)
        raise SystemExit(1) from error
