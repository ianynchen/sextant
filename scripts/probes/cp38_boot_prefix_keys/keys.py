"""CP-38 — what Spring Boot itself calls its path-prefix properties, per version.

Spec `docs/superpowers/specs/2026-10-18-configured-path-prefixes-design.md` §3, whose table
pairs a KEY with a framework and a version range. This probe is where those rows get their
evidence, and it reads the framework's own bytes rather than documentation: Boot ships
`META-INF/spring-configuration-metadata.json` in its jars, naming every property it binds,
with deprecations and their replacements.

**Why a probe and not a check at analysis time.** Reading the module's Boot jar would put a
JSON parse in the resolve path to answer a question whose answer has been stable since 2018,
and `extract_libraries` is opt-in so the jar is often not read at all. Here the measurement is
re-runnable and its output IS the record (GUIDELINES §5.4).

Run: `.venv/bin/python scripts/probes/cp38_boot_prefix_keys/keys.py [version ...]`
Jars come from the local Maven repository; a version not present is reported and skipped.
"""

import json
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
REPOSITORY = Path.home() / ".m2" / "repository" / "org" / "springframework" / "boot"
METADATA = "META-INF/spring-configuration-metadata.json"

# The properties the spec's table declares, plus the two the servlet path was renamed from and
# Actuator's, which composes after them. Asked by NAME so the answer can be "absent".
ASKED = (
    "server.servlet.context-path",
    "spring.mvc.servlet.path",
    "spring.webflux.base-path",
    "management.endpoints.web.base-path",
    "server.servlet.path",
    "server.context-path",
)


def declared(version: str) -> tuple[dict[str, tuple[str, str]], tuple[str, ...]]:
    """`{property: (jar, replacement)}` for every asked property any Boot jar at `version`
    declares. The JAR is kept because WHICH artifact declares a property is exactly what moved
    between 2.x and 4.x, while the names did not — and because an absence can only be read
    against the artifacts that were actually opened (see `main`)."""
    found: dict[str, tuple[str, str]] = {}
    opened: list[str] = []
    for jar in sorted(REPOSITORY.rglob(f"*-{version}.jar")):
        if "sources" in jar.name or "javadoc" in jar.name:
            continue
        try:
            with zipfile.ZipFile(jar) as archive:
                if METADATA not in archive.namelist():
                    continue
                payload = json.loads(archive.read(METADATA))
        except (zipfile.BadZipFile, KeyError, json.JSONDecodeError):
            continue
        opened.append(artifact_of(jar.name, version))
        for entry in payload.get("properties", []):
            name = entry.get("name")
            if name not in ASKED:
                continue
            deprecation = entry.get("deprecation") or {}
            replacement = deprecation.get("replacement") or ("deprecated" if deprecation else "")
            found.setdefault(name, (jar.name, replacement))
    return found, tuple(sorted(set(opened)))


def artifact_of(jar: str, version: str) -> str:
    """`spring-boot-web-server-4.1.1.jar` -> `spring-boot-web-server`."""
    return jar[: -len(f"-{version}.jar")]


def has_jar(artifact: str, version: str) -> bool:
    """Whether the local repository holds that artifact at that version."""
    directory = REPOSITORY / artifact / version
    return any("sources" not in jar.name for jar in directory.glob(f"*-{version}.jar"))


def main(argv: list[str]) -> int:
    versions = argv or ["2.7.18", "3.5.14", "4.1.1"]
    for version in versions:
        rows, opened = declared(version)
        print(f"== spring-boot {version}")
        print(f"   artifacts read, carrying property metadata: {len(opened)}")
        for name in ASKED:
            if name in rows:
                jar, replacement = rows[name]
                note = f"  DEPRECATED -> {replacement}" if replacement else ""
                print(f"   {name:38s} {jar}{note}")
            else:
                # **"Absent from what was READ", never "absent from the framework."** Which
                # artifact declares a property is itself version-dependent — Boot 4 split
                # `spring-boot-autoconfigure` into 118 — so a reader needs the denominator to
                # judge the cell. The first draft of this probe printed a bare "absent" for
                # `spring.webflux.base-path` at 4.1.1, where the artifact that would plausibly
                # declare it is simply not in this repository. That is the CP-5 failure in
                # miniature: a cell that reads as a measurement and is not one. Drawing the
                # bound belongs in the write-up, with the denominator in hand.
                print(f"   {name:38s} absent from those {len(opened)}")
        if opened:
            print(f"   read: {', '.join(opened)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
