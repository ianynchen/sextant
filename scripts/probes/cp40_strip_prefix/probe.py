"""CP-40 — what `StripPrefix=N` removes from a path.

Prints the Observations table of `scripts/probes/cp40_strip_prefix.md`. Nothing in that
section is typed by hand.

**The version is read from the JAR, never from a parameter** (GUIDELINES §5.4, and the CP-5
failure the convention exists to prevent): the artifact's own `MANIFEST.MF` states its
`Implementation-Version`, and that string is the column header. A harness that printed the
version it was *handed* once carried eight cells from a build nobody ran.

The method is `javap -c` over the filter's own class, which is the CP-39 precedent and the
right instrument here: the rule is a loop over path segments, and the loop is in the
bytecode. Running it instead would need a reactor, a mock exchange and a servlet container
to observe four arithmetic facts.
"""

import re
import subprocess
import sys
import zipfile
from pathlib import Path

# BOTH artifacts, because Spring Cloud renamed the module at 5.0 and a rule measured on one
# side of a rename says nothing about the other. The class is the same name in both.
ARTIFACTS = (
    "org.springframework.cloud:spring-cloud-gateway-server",
    "org.springframework.cloud:spring-cloud-gateway-server-webflux",
)
FILTER = "org/springframework/cloud/gateway/filter/factory/StripPrefixGatewayFilterFactory$1"

# What the disassembly must contain for each verdict, and the verdict it supports. Each is a
# call or constant the loop cannot do its job without, so a release that changed the rule
# would drop one and this probe would report it rather than restate yesterday's answer.
EVIDENCE = (
    (
        "the path it reads",
        "URI.getRawPath",
        "the RAW path — percent-escapes are not decoded before the split",
    ),
    (
        "how it splits",
        "StringUtils.tokenizeToStringArray",
        (
            "on `/`, discarding empty tokens, so `//a//b` is two segments and a trailing "
            "slash makes none"
        ),
    ),
    (
        "how many it drops",
        "Config.getParts",
        "the `parts` value: a segment is kept only where its index is >= parts",
    ),
    (
        "what it rebuilds",
        'StringBuilder."<init>":(Ljava/lang/String;)V',
        "a builder seeded with `/`, so the result always has a leading slash",
    ),
    (
        "the trailing slash",
        "String.endsWith",
        "re-appended only when something was kept (`length() > 1`)",
    ),
)


def _jars() -> "list[tuple[str, Path]]":
    """Every cached jar of either artifact that actually CONTAINS the filter.

    The 4.x `spring-cloud-gateway-server-webflux` jar does not — the filter lives in
    `spring-cloud-gateway-server` until 5.0 — so membership is tested rather than assumed,
    and an artifact that ships no filter is left out instead of reported absent.
    """
    found = []
    for coordinate in ARTIFACTS:
        group, artifact = coordinate.split(":")
        root = Path.home() / ".m2" / "repository" / group.replace(".", "/") / artifact
        for jar in sorted(root.glob("*/*.jar")):
            try:
                with zipfile.ZipFile(jar) as archive:
                    if f"{FILTER}.class" not in archive.namelist():
                        continue
            except zipfile.BadZipFile:
                continue
            found.append((artifact, jar))
    if not found:
        raise SystemExit(f"no cached jar of {ARTIFACTS} contains {FILTER}")
    return found


def _version(jar: Path) -> str:
    """The version the ARTIFACT states about itself, read from its manifest."""
    with zipfile.ZipFile(jar) as archive:
        manifest = archive.read("META-INF/MANIFEST.MF").decode("utf-8", "replace")
    stated = re.search(r"(?m)^Implementation-Version:\s*(\S+)", manifest)
    if stated:
        return stated.group(1)
    # Some Spring Cloud releases ship no Implementation-Version; the Bundle-Version is the
    # same string there. Reported as whichever the jar actually states, never assembled
    # from the path, because a path is what someone typed.
    bundle = re.search(r"(?m)^Bundle-Version:\s*(\S+)", manifest)
    if bundle:
        return bundle.group(1)
    raise SystemExit(f"{jar.name} states no version in its own manifest")


def _disassembly(jar: Path) -> str:
    return subprocess.run(
        ["javap", "-p", "-c", "-cp", str(jar), FILTER.replace("/", ".")],
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def main() -> int:
    measured = [(artifact, _version(jar), _disassembly(jar)) for artifact, jar in _jars()]
    # The column header is the VERSION alone, which is what makes each cell attributable to
    # a configuration rather than to prose (`test_probe_provenance`'s own rule). Which
    # artifact each version came from is stated on its own line above the table, because
    # Spring Cloud renamed the module and the pair is the point.
    for artifact, version, _ in measured:
        print(f"- `{artifact}` **{version}**")
    print()
    columns = [version for _, version, _ in measured]
    print("| Question | Instruction found | " + " | ".join(columns) + " |")
    print("|---|---|" + "---|" * len(columns))
    missing = 0
    for question, needle, verdict in EVIDENCE:
        cells = []
        for _, _, code in measured:
            if needle in code:
                cells.append(verdict)
            else:
                missing += 1
                cells.append("**ABSENT — this release does not do this**")
        print(f"| {question} | `{needle}` | " + " | ".join(cells) + " |")
    print()
    # Every column agreeing is the claim the version scope rests on, so it is computed
    # rather than asserted: one disagreeing release makes the scope a lie.
    agree = (
        len(
            {
                tuple(needle in code for needle, *_ in [(n,) for n, _, _ in EVIDENCE])
                for _, _, code in measured
            }
        )
        == 1
    )
    print(f"**All {len(measured)} measured releases agree:** {'yes' if agree else 'NO'}")
    print()
    version = " · ".join(columns)
    code = measured[0][2]
    # The two derived answers, each a consequence of the loop above rather than a separate
    # observation — stated here so the document never has to restate them by hand.
    kept = "Config.getParts" in code and "StringUtils.tokenizeToStringArray" in code
    caveat = "" if kept else " **(UNVERIFIED — the loop above is not intact)**"
    print(f"| Derived | {version} |")
    print("|---|---|")
    print(
        "| `StripPrefix=N` on `/a/b/c` with N=2 | `/c` — the first N segments are dropped "
        f"and the rest rejoined{caveat} |"
    )
    print(
        "| a path with FEWER than N segments | `/` — the loop keeps nothing and the "
        f"builder holds only its seed{caveat} |"
    )
    print(
        "| `N` equal to the predicate prefix's segment count | the service receives exactly "
        f"the path it serves, so the gateway's address is that prefix plus it{caveat} |"
    )
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
