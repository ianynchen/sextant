"""CP-22's measurement half: `@RegisterRestClient`'s declared attributes and
defaults (across the MP 6->7 platform boundary), whether `derive_endpoints
.sql`'s `prefixes` CTE reads `peer` off the same annotation row as `prefix`,
and Quarkus's own `RestClientCDIDelegateBuilder.configureBaseUrl` precedence
between the annotation's `baseUri` and `quarkus.rest-client.<key>.url`/`.uri`
config; and (row 4) which Quarkus client artifact names exist on Maven
Central across the 3.9.0 rename, read off the repository's own
`maven-metadata.xml` the way CP-19 row 5 reads the server-side relocation.

Called by `run.sh`, which resolves the jars; this script downloads nothing
but row 4's metadata files. Like CP-16/CP-17/CP-18/CP-19/CP-20/CP-21 it reads each jar's own
identity out of its own bytes before it measures anything and refuses to file
a cell under a version the artifact did not claim (GUIDELINES §5.4, and CP-5's
failure it exists to prevent).

Row 2 is not a jar read at all — it is a read of this repository's own SQL, so
its identity is the git commit `run.sh` resolves HEAD to.
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
        self, key: str, group: str, name: str, requested_identity: str, jar: Path, manifest_key: str
    ):
        self.key = key
        self.group = group
        self.name = name
        self.requested = requested_identity
        self.jar = jar
        self.observed = _identity(jar, "META-INF/MANIFEST.MF", manifest_key)
        if self.observed != requested_identity:
            raise ProbeError(
                f"{jar.name} reports version {self.observed!r} but was expected to report "
                f"{requested_identity!r} — a mislabelled column, which is CP-5's failure exactly"
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


def q1_register_rest_client(jar: Path) -> str:
    """Q1. `@RegisterRestClient`'s `@Target`, `@Retention`, `baseUri()`/
    `configKey()` and their defaults."""
    output = _javap(
        "-v", "org.eclipse.microprofile.rest.client.inject.RegisterRestClient", classpath=jar
    )
    target = re.search(r"java\.lang\.annotation\.Target\(\s*\n\s*value=(\S+)", output)
    retention = re.search(r"java\.lang\.annotation\.Retention\(\s*\n\s*value=(\S+)", output)
    defaults = {}
    for name in ("baseUri", "configKey"):
        match = re.search(
            rf"public abstract java\.lang\.String {name}\(\);.*?default_value: \S+\n(\s*\"[^\"]*\")?",
            output,
            re.DOTALL,
        )
        if not match:
            raise ProbeError(f"no {name}() attribute found")
        literal = match.group(1)
        defaults[name] = literal.strip() if literal else '""'
    return (
        f"@Target({target.group(1) if target else '?'}) ; @Retention({retention.group(1) if retention else '?'}) ; "
        f"baseUri(): String default {defaults['baseUri']} ; configKey(): String default {defaults['configKey']}"
    )


def q2_peer_off_prefix_row(repo: Path) -> str:
    """Q2. Whether `derive_endpoints.sql`'s `prefixes` CTE reads `peer` off
    the SAME row (single join to `prefix_gates`) as `prefix`."""
    path = repo / "src" / "sextant" / "storage" / "duckdb" / "derive_endpoints.sql"
    text = path.read_text(encoding="utf-8")
    match = re.search(r"^prefixes AS \($(.*?)^\),$", text, re.DOTALL | re.MULTILINE)
    if not match:
        raise ProbeError("no `prefixes AS (` CTE found in derive_endpoints.sql")
    cte = match.group(1)
    joins = re.findall(r"^\s*JOIN\s+(\w+)\s+\w+\s+ON\s+(.+)$", cte, re.MULTILINE)
    reads_prefix_from = "cp.prefix_from" in cte
    reads_peer_from = "cp.peer_from" in cte
    join_summary = _STEP.join(f"JOIN {table} ON {cond.strip()}" for table, cond in joins)
    return (
        f"joins: {join_summary} ; reads cp.prefix_from: {reads_prefix_from} ; "
        f"reads cp.peer_from: {reads_peer_from} ; distinct annotation joins: {len({t for t, _ in joins if 'catalog_params' not in t})}"
    )


def q3_quarkus_base_uri(jar: Path) -> str:
    """Q3. `RestClientCDIDelegateBuilder.configureBaseUrl`'s full bytecode —
    the precedence between the Quarkus config reload and the annotation's
    `baseUri`, and the two property names it names in its failure message."""
    output = _javap(
        "-c",
        "-p",
        "io.quarkus.rest.client.reactive.runtime.RestClientCDIDelegateBuilder",
        classpath=jar,
    )
    lines = output.splitlines()
    start = next(
        (i for i, line in enumerate(lines) if "private void configureBaseUrl(" in line), None
    )
    if start is None:
        raise ProbeError("no configureBaseUrl method found")
    steps = _instructions(lines[start + 1 :], until="return")
    kept = [
        s
        for s in steps
        if any(
            marker in s
            for marker in (
                "uriReload",
                "urlReload",
                "oneOf",
                "orElse",
                "baseUriFromAnnotation",
                "configKey",
                "quarkus.rest-client",
                "IllegalArgumentException",
                "baseUri",
                "jaxrsInterface",
            )
        )
    ]
    return _STEP.join(kept)


# The client-side artifact names a module may declare instead of, or beside,
# `io.quarkus:quarkus-rest-client`: the pre-3.9.0 reactive names and the
# RESTEasy-classic names, each with its Jackson facet. Row 4 asks Maven
# Central whether each exists and what it carries, so the catalog's
# `detect.coordinates` lists nothing that was never published.
_CLIENT_ARTIFACTS = (
    "quarkus-rest-client",
    "quarkus-rest-client-jackson",
    "quarkus-rest-client-reactive",
    "quarkus-rest-client-reactive-jackson",
    "quarkus-resteasy-client",
    "quarkus-resteasy-client-jackson",
)


def q4_client_artifacts() -> dict[str, str]:
    """Q4. Which Quarkus client artifact names exist on Maven Central, read
    off each artifact's own `maven-metadata.xml` (CP-19 row 5's method):
    the version count, the earliest GA `3.x.y` and the last version listed."""
    observed: dict[str, str] = {}
    for artifact in _CLIENT_ARTIFACTS:
        url = f"https://repo1.maven.org/maven2/io/quarkus/{artifact}/maven-metadata.xml"
        with urllib.request.urlopen(url, timeout=30) as response:
            text = response.read().decode("utf-8", "replace")
        versions = re.findall(r"<version>([^<]+)</version>", text)
        ga = [v for v in versions if re.fullmatch(r"3\.\d+\.\d+", v)]
        observed[artifact] = (
            f"maven-metadata.xml: {len(versions)} versions ; earliest GA 3.x: "
            f"{ga[0] if ga else 'none'} ; last listed: {versions[-1] if versions else 'none'}"
        )
    return observed


def main(specs: list[str]) -> int:
    artifacts: dict[str, Artifact] = {}
    repo = None
    for spec in specs:
        if spec.startswith("REPO="):
            repo = Path(spec.split("=", 1)[1])
            continue
        key, group, name, requested_identity, jar, manifest_key = spec.split("|")
        artifacts[key] = Artifact(key, group, name, requested_identity, Path(jar), manifest_key)
    if repo is None:
        raise ProbeError("no REPO= argument given")

    mp40 = artifacts["mp40"]
    mp301 = artifacts["mp301"]
    qrc = artifacts["qrc"]

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

    print(
        f"| 1a | @RegisterRestClient: @Target, @Retention, baseUri()/configKey() defaults | `{mp40.group}:{mp40.name}` | {mp40.observed} | `{q1_register_rest_client(mp40.jar)}` |"
    )
    print(
        f"| 1b | @RegisterRestClient: @Target, @Retention, baseUri()/configKey() defaults | `{mp301.group}:{mp301.name}` | {mp301.observed} | `{q1_register_rest_client(mp301.jar)}` |"
    )

    commit = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--short", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    print(
        f"| 2 | derive_endpoints.sql's prefixes CTE: peer off the prefix-gate row only? | `src/sextant/storage/duckdb/derive_endpoints.sql` | repo@{commit} | `{q2_peer_off_prefix_row(repo)}` |"
    )

    print(
        f"| 3 | Quarkus's configureBaseUrl: config vs. annotation baseUri precedence | `{qrc.group}:{qrc.name}` | {qrc.observed} | `{q3_quarkus_base_uri(qrc.jar)}` |"
    )

    for letter, (artifact, observed) in zip("abcdef", q4_client_artifacts().items(), strict=True):
        print(
            f"| 4{letter} | client artifact exists on Maven Central (metadata, not a jar) | `io.quarkus:{artifact}` | n/a | `{observed}` |"
        )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except ProbeError as error:
        print(f"CP-22 aborted: {error}", file=sys.stderr)
        raise SystemExit(1) from None
