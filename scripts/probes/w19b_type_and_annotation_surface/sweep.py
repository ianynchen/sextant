"""W19b — the enumeration pass for the three slices that are NOT about methods on an
owner type (F2 §3.8: G-47, G-45, G-41).

`w19_catalog_surface` answered "of the methods this framework declares on this owner,
how many does the catalog read?" Three of §3.8's six slices do not have that shape, and
calling them done by that table would be the "counted the wrong set" error this wave
keeps producing. Each is enumerated here against the question it actually asks:

1. **G-47, `spring-integration`** — which annotations in the framework's annotation
   package DECLARE A CHANNEL, and which of those does the catalog name? Measured from
   each annotation's own declared attributes rather than from a list, so an annotation
   added in a later release appears here by itself.
2. **G-45, `spring-data-rest`** — which repository CONTRACTS does Spring Data ship, and
   which does the catalog's roster name? A repository interface that reaches
   `CrudRepository` only through a jar this analysis never opens derives nothing, so the
   roster is the whole rule.
3. **G-41, `netflix-dgs`** — is `@DgsData` `@Inherited`? A one-annotation question with
   no set to enumerate, so it is answered directly and stated, not tabulated.

**What the attribute-name test can and cannot see (G-47).** An annotation is counted as
channel-declaring when it declares an attribute whose name says so — `inputChannel`,
`outputChannel`, `channel`, `discardChannel`, `requestChannel`, `replyChannel`,
`defaultRequestChannel`, `defaultReplyChannel`. `@BridgeFrom` and `@BridgeTo` carry the
channel in a bare `value()` and are invisible to that test; they are reported separately
rather than folded in, because "the framework named this attribute a channel" is a
measurement and "this `value()` means a channel" is a reading of the annotation's name.
"""

from __future__ import annotations

import re
import subprocess
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "src"))

from sextant.application.ports.catalogs import Catalog
from sextant.ingress.catalogs.yaml_source import YamlCatalogSource

M2 = Path.home() / ".m2" / "repository"
CATALOGS = REPO / "src" / "sextant" / "catalogs"

INTEGRATION = ("org.springframework.integration:spring-integration-core", "6.2.4")
ANNOTATION_PACKAGE = "org/springframework/integration/annotation/"
# Attribute names by which a framework says "this holds a channel".
# An attribute the framework NAMED for a channel. A rule, not a list: any attribute
# whose name CONTAINS "channel" in either case. Deliberately the broadest form: a
# narrower one written as an alternation missed `errorChannel` first and then
# `channelMappings`, and each miss removed a whole annotation or a whole destination
# from a table whose job is to say what is missing.
#
# The first version enumerated eight names by hand and missed `errorChannel`, so
# `@Poller` — which declares one and nothing else channel-shaped — was absent from the
# table, the count and the slice entirely. That is the "counted the wrong set" error
# this probe's own docstring says it exists to avoid, committed by the probe.
_CHANNEL_ATTRIBUTE = re.compile(r"\b(\w*[Cc]hannel\w*)\(\)")
# The two whose channel lives in a bare `value()`, which the test above cannot see.
_CHANNEL_IN_VALUE = ("BridgeFrom", "BridgeTo")

# The repository contracts, per artifact. `spring-data-commons` carries the shared ones;
# each store module ships its own. Artifacts this run cannot resolve are REPORTED, so a
# short list reads as a short list rather than as an absence of gaps.
DATA_ARTIFACTS = (
    ("org.springframework.data:spring-data-commons", "3.2.5"),
    ("org.springframework.data:spring-data-mongodb", "4.2.5"),
    ("org.springframework.data:spring-data-r2dbc", "3.2.5"),
    ("org.springframework.data:spring-data-cassandra", "4.2.5"),
    ("org.springframework.data:spring-data-elasticsearch", "5.2.5"),
    ("org.springframework.data:spring-data-neo4j", "7.2.5"),
    ("org.springframework.data:spring-data-jpa", "3.2.5"),
    # Added after review: the list was hand-picked from the gap analysis's own
    # sentence, so a store module nobody had thought of was not merely uncounted —
    # `UNRESOLVED`'s "this count is a LOWER BOUND" warning could not fire for it
    # either, because it was never asked for. `KeyValueRepository` is the base
    # contract for Redis `@RedisHash` repositories and Spring Data REST exposes them.
    ("org.springframework.data:spring-data-keyvalue", "3.2.5"),
    ("org.springframework.data:spring-data-redis", "3.2.5"),
    ("org.springframework.data:spring-data-ldap", "3.2.5"),
    ("org.springframework.data:spring-data-couchbase", "5.2.5"),
    ("org.springframework.data:spring-data-rest-core", "4.2.5"),
)
_REPOSITORY = re.compile(r"([\w/$]*Repository)\.class$")

DGS = ("com.netflix.graphql.dgs:graphql-dgs", "8.7.1")
DGS_ANNOTATIONS = ("DgsData", "DgsQuery", "DgsMutation", "DgsSubscription", "DgsComponent")

UNRESOLVED: list[str] = []
# `(catalog, kind, container, name)` for every unread name, emitted as section 4 for
# `tests/architecture/test_catalog_slice_coverage.py` to hold the catalogs to.
UNREAD: list[tuple[str, str, str, str]] = []


class ProbeError(RuntimeError):
    """A run that could not answer, told apart from a run that answered `no`."""


def jar(artifact: str, version: str) -> Path | None:
    group, name = artifact.split(":")
    found = M2 / group.replace(".", "/") / name / version / f"{name}-{version}.jar"
    return found if found.exists() else None


def self_reported_version(archive: Path) -> str:
    with zipfile.ZipFile(archive) as zf:
        try:
            manifest = zf.read("META-INF/MANIFEST.MF").decode("utf-8", "replace")
        except KeyError:
            manifest = ""
        for line in manifest.splitlines():
            if line.startswith("Implementation-Version:"):
                return line.split(":", 1)[1].strip()
        for name in zf.namelist():
            if name.startswith("META-INF/maven/") and name.endswith("pom.properties"):
                for line in zf.read(name).decode("utf-8", "replace").splitlines():
                    if line.startswith("version="):
                        return line.split("=", 1)[1].strip()
    return "the archive records no version about itself"


def checked(artifact: str, version: str) -> Path | None:
    """The jar, with its self-report confirmed — or `None`, recorded, when this run
    could not resolve it."""
    archive = jar(artifact, version)
    if archive is None:
        UNRESOLVED.append(f"{artifact}:{version}")
        return None
    claimed = self_reported_version(archive)
    if claimed != version:
        raise ProbeError(
            f"{archive} was requested as {version} and claims {claimed!r} — every cell "
            f"below would be filed under a version the artifact did not report."
        )
    return archive


def catalog(catalog_id: str) -> Catalog:
    found = next((c for c in YamlCatalogSource(CATALOGS).load() if c.id == catalog_id), None)
    if found is None:
        raise ProbeError(f"no shipped catalog has id {catalog_id!r}")
    return found


def named_in(catalog_id: str, pattern: str) -> set[str]:
    """Every fully-qualified name matching `pattern` that the catalog FILE mentions.

    Read off the file rather than the loaded model: these names sit in several
    different keys (`annotations`, `contracts`, `excludes`) whose shapes differ per
    style, and the question here is only "does this catalog mention this type at all".
    """
    text = (CATALOGS / f"{catalog_id}.yml").read_text(encoding="utf-8")
    # Everything ABOVE the slice block. A `why` explaining why a contract is outside
    # the slice will often name that contract, and searching the whole file would then
    # count it as READ — dropping it from this table and making the entry that
    # disclosed it fail the staleness audit. So the more carefully an author explains
    # an omission, the more likely the audit is to punish them for it. Cutting at
    # `slice:` is exact because the block is always last in these files, and the
    # assertion below refuses to guess if that ever stops being true.
    head, marker, tail = text.partition("\nslice:\n")
    if marker and re.search(r"^\w", tail, re.MULTILINE):
        raise ProbeError(
            f"{catalog_id}.yml has content after its `slice:` block, so cutting there no "
            f"longer separates what the catalog READS from what it explains"
        )
    return set(re.findall(pattern, head))


def _is_interface(archive: Path, fqn: str) -> bool:
    """Whether the type is an interface — a repository CONTRACT rather than one of the
    framework's own implementations of one."""
    result = subprocess.run(
        ["javap", "-cp", str(archive), fqn], capture_output=True, text=True, check=False
    )
    return result.returncode == 0 and " interface " in result.stdout


def annotation_attributes(archive: Path, fqn: str) -> str:
    result = subprocess.run(
        ["javap", "-cp", str(archive), fqn], capture_output=True, text=True, check=False
    )
    return "" if result.returncode != 0 else result.stdout


def is_inherited(archive: Path, fqn: str) -> bool | None:
    """Whether the annotation carries `@Inherited`, or `None` when it cannot be read."""
    result = subprocess.run(
        ["javap", "-v", "-cp", str(archive), fqn], capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        return None
    return "java/lang/annotation/Inherited" in result.stdout


def main() -> None:
    print("## Observations\n")
    print(
        "Generated by `scripts/probes/w19b_type_and_annotation_surface/run.sh` — every "
        "cell below is that run's own output, and this document pastes it verbatim.\n"
    )
    print(
        "**Each column header is the version the JAR ITSELF reported**, read out of its "
        "own `META-INF/MANIFEST.MF` or Maven `pom.properties` — not the version the loop "
        "asked for, which is only the path this machine cached the artifact at. The run "
        "ABORTS when the two disagree.\n"
    )

    # --- 1. G-47 ---
    archive = checked(*INTEGRATION)
    if archive is None:
        raise ProbeError(f"{INTEGRATION[0]} is required for section 1 and did not resolve")
    with zipfile.ZipFile(archive) as zf:
        simple = sorted(
            {
                n[len(ANNOTATION_PACKAGE) : -len(".class")]
                for n in zf.namelist()
                if n.startswith(ANNOTATION_PACKAGE) and n.endswith(".class") and "$" not in n
            }
        )
    read = named_in("spring-integration", r"org\.springframework\.integration\.annotation\.(\w+)")
    print("### 1. G-47 — channel-declaring annotations (`spring-integration`)\n")
    print(
        "Cells are the channel-naming attributes the annotation declares, under the "
        "version that reported them.\n"
    )
    # The header cell is the identity ALONE — `test_probe_provenance.py` reads a column
    # header as the configuration its cells are attributable to, and a header carrying
    # anything besides the version is not one.
    print(f"| annotation | {INTEGRATION[1]} | read by the catalog |")
    print("|---|---|---|")
    declaring: list[str] = []
    for name in simple:
        attributes = sorted(
            set(
                _CHANNEL_ATTRIBUTE.findall(
                    annotation_attributes(
                        archive, f"org.springframework.integration.annotation.{name}"
                    )
                )
            )
        )
        if not attributes:
            continue
        declaring.append(name)
        if name not in read:
            UNREAD.append(
                (
                    "spring-integration",
                    "annotation",
                    "org.springframework.integration.annotation",
                    name,
                )
            )
        print(
            f"| `{name}` | {', '.join(f'`{a}`' for a in attributes)} | "
            f"{'yes' if name in read else '**NO**'} |"
        )
    # The two the attribute-name test cannot see, emitted into section 4 anyway when
    # the catalog does not name them. Otherwise a slice could not declare them without
    # failing the staleness check, and the honest entry would be the one the audit
    # refused — a rule that punishes disclosure is worse than no rule.
    for name in _CHANNEL_IN_VALUE:
        # Measured, not asserted. This tuple used to be appended blind, so a name the
        # framework does not ship — or one that ships without a `value()` — would have
        # been laundered into the slice through the one mechanism that keeps this table
        # honest, and the staleness guard would never fire on its removal.
        if name not in simple:
            raise ProbeError(
                f"`{name}` is named as carrying a channel in `value()` but "
                f"{INTEGRATION[0]} {INTEGRATION[1]} ships no such annotation"
            )
        if "java.lang.String value()" not in annotation_attributes(
            archive, f"org.springframework.integration.annotation.{name}"
        ):
            raise ProbeError(
                f"`{name}` is named as carrying a channel in `value()` and declares no "
                f"`String value()` at {INTEGRATION[1]}"
            )
        if name not in read:
            UNREAD.append(
                (
                    "spring-integration",
                    "annotation (channel in `value()`)",
                    "org.springframework.integration.annotation",
                    name,
                )
            )
    unread = [n for n in declaring if n not in read]
    print(
        f"\n- **{len(declaring) - len(unread)} of {len(declaring)}** channel-declaring "
        f"annotations are read; {len(unread)} are not."
    )
    annotations_only = [
        n
        for n in simple
        if " interface "
        in annotation_attributes(archive, f"org.springframework.integration.annotation.{n}")
    ]
    print(
        f"- The package holds {len(annotations_only)} annotations in total (of "
        f"{len(simple)} classes — the difference is `AnnotationConstants`, a plain final "
        f"class); the rest declare no channel attribute."
    )
    print(
        f"- Invisible to the attribute-name test, and carrying a channel in a bare "
        f"`value()`: {', '.join(f'`{n}`' for n in _CHANNEL_IN_VALUE)}. Counted "
        f"separately because 'the framework named this attribute a channel' is a "
        f"measurement and 'this `value()` means a channel' is a reading of the name.\n"
    )

    # --- 2. G-45 ---
    print("### 2. G-45 — repository contracts (`spring-data-rest`)\n")
    roster = named_in("spring-data-rest", r"(org\.springframework\.data\.[\w.]*\w*Repository)")
    print("| artifact | version | repository contracts it ships | named by the roster |")
    print("|---|---|---|---|")
    for artifact, version in DATA_ARTIFACTS:
        found = checked(artifact, version)
        if found is None:
            print(f"| `{artifact}` | {version} | **not resolved by this run** | — |")
            continue
        with zipfile.ZipFile(found) as zf:
            candidates = sorted(
                {
                    n[: -len(".class")].replace("/", ".")
                    for n in zf.namelist()
                    if _REPOSITORY.search(n) and "$" not in n
                }
            )
        # INTERFACES only. `SimpleMongoRepository` and its siblings are the
        # framework's own implementations of these contracts, not contracts a user's
        # interface extends, and counting them would inflate both halves of the ratio
        # with types no roster should ever name.
        contracts = [c for c in candidates if _is_interface(found, c)]
        named = [c for c in contracts if c in roster]
        print(f"| `{artifact}` | {version} | {len(contracts)} | **{len(named)}** |")
        for contract in contracts:
            if contract not in roster:
                UNREAD.append(("spring-data-rest", "type", artifact, contract.rsplit(".", 1)[-1]))
                print(f"| | | `{contract.rsplit('.', 1)[-1]}` | **NO** |")
    print()

    # --- 3. G-41 ---
    print("### 3. G-41 — is `@DgsData` inherited? (`netflix-dgs`)\n")
    archive = checked(*DGS)
    if archive is None:
        print("> `graphql-dgs` did not resolve; this section could not run.\n")
    else:
        print(f"| annotation | {DGS[1]} `@Inherited` |")
        print("|---|---|")
        for name in DGS_ANNOTATIONS:
            answer = is_inherited(archive, f"com.netflix.graphql.dgs.{name}")
            rendered = "not readable" if answer is None else ("**yes**" if answer else "no")
            print(f"| `{name}` | {rendered} |")
        print(
            "\n- All five carry `@Inherited` — three more than the gap analysis recorded. "
            "**And on four of them that bit is INERT.** `java.lang.annotation.Inherited` "
            '"has no effect if the annotated type is used to annotate anything other '
            'than a class", and it inherits from superclasses, never through methods; '
            "`@DgsData`, `@DgsQuery`, `@DgsMutation` and `@DgsSubscription` all declare "
            "`@Target(METHOD)`. So this table measures a real bit that does not do the "
            "job it was cited for.\n"
        )
        print(
            "- **The outcome it was cited for is nonetheless true, by a different and now "
            "measured mechanism.** `DgsSchemaProvider$Companion$DgsBean` calls "
            "`ReflectionUtils.getUniqueDeclaredMethods(clazz, USER_DECLARED_METHODS)`, and "
            "`ReflectionUtils.doWithMethods` calls `Class.getSuperclass()` and "
            "`Class.getInterfaces()` (`javap -c`, spring-core 6.1.6) — so DGS enumerates "
            "the whole hierarchy's methods. A fetcher on a superclass method registers on "
            "every subclass bean, and we read annotations only where they are written. "
            "The fix is a superclass METHOD walk, not `@Inherited` resolution.\n"
        )

    print("### 4. Every unread name, one per row\n")
    print(
        "Prose is what a reader needs and a table is what a test can hold to; this is the "
        "second. `tests/architecture/test_catalog_slice_coverage.py` requires every row "
        "here to be named in its catalog's `slice.outside`, the same way it does for the "
        "method table `w19_catalog_surface.md` emits.\n"
    )
    print("| catalog | kind | container | name |")
    print("|---|---|---|---|")
    for catalog_id, kind, container, name in UNREAD:
        print(f"| `{catalog_id}` | `{kind}` | `{container}` | `{name}` |")
    print()
    print(
        "**G-41 is deliberately absent from this table.** `netflix-dgs`'s gap is not a set "
        "of names the catalog fails to read — it names all five annotations. It is a USE "
        "SITE we cannot see: an `@Inherited` annotation on a superclass method registers a "
        "fetcher the subclass never declares, and this analysis reads annotations where "
        "they are written. `slice.outside`'s vocabulary is \"names this catalog does not "
        'read", and forcing a use-site gap into it would make the key mean two different '
        "things. It is stated in the catalog and in COVERAGE instead.\n"
    )

    if UNRESOLVED:
        print(
            "**Artifacts this run could not resolve**, so any count above that depended "
            "on them is a LOWER BOUND:\n"
        )
        for name in UNRESOLVED:
            print(f"- `{name}`")
        print()


if __name__ == "__main__":
    try:
        main()
    except ProbeError as error:
        print(f"PROBE COULD NOT ANSWER: {error}", file=sys.stderr)
        raise SystemExit(2) from error
