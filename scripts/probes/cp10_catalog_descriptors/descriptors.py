"""CP-10's measurement half: resolve every catalog `descriptor:` against real
bytecode, and record the jar identity the run itself read.

Called by `run.sh`, which resolves the jars; this script never downloads
anything. It does three things and aborts on the first that fails:

1. **Reads each jar's own identity out of its own bytes** and refuses to file a
   single cell under a version the artifact did not claim (GUIDELINES §5.4, and
   CP-5's failure it exists to prevent). Where the self-report lives differs per
   artifact — Maven's `pom.properties`, the manifest's `Implementation-Version`,
   Kafka's own `kafka-version.properties` — so the LOCATION is passed in and the
   VALUE is always read from the archive. A jar carrying no self-report at all,
   or one whose self-report disagrees with the coordinate that resolved it, is a
   mislabelled column and stops the run.
2. **Indexes class -> jar** off the archives, so the jar a descriptor is
   attributed to is the jar the run actually opened, never a coordinate mapped
   to an owner by hand.
3. **Asks `javap -p -s`** for every method the owner declares, walking its
   superclasses while they are on the same classpath — `SqsTemplate.send(String,
   T)` is declared on `AbstractMessagingTemplate`, and a check that could not see
   an inherited method would report a real descriptor as missing.

Everything it prints is the table `cp10_catalog_descriptors.md` carries
verbatim and `tests/architecture/test_catalog_descriptors.py` pins the shipped
catalogs against.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[3]
CATALOGS = REPO / "src" / "sextant" / "catalogs"

# `<key>=<value>` in a `.properties` entry, and the manifest's own `Name: value`
# — the two spellings the self-reports below are written in.
_PROPERTY = re.compile(r"^\s*([\w.\-]+)\s*[:=]\s*(.+?)\s*$")
# `javap`'s own two lines: the declaration, then the erased descriptor under it.
_DECLARATION = re.compile(r"([\w$.]+)\s*\(")
_DESCRIPTOR_LINE = re.compile(r"^\s*descriptor:\s*(\S+)\s*$")
_GENERICS = re.compile(r"<[^<>]*>")


class ProbeError(RuntimeError):
    """A run that cannot label its own output. Fatal, never advisory."""


# The `entry`/`key` pair a coordinate writes when the archive states no version
# of its own ANYWHERE — no manifest `Implementation-Version`, no Maven
# `pom.properties`, no version file of its own making. `io.temporal:temporal-sdk`
# is the first such artifact this harness reads, and CP-30 measured the absence
# rather than assuming it: that jar's manifest carries only `Manifest-Version`
# and `Multi-Release`, it ships no `META-INF/maven/*/pom.properties`, and no
# class in it holds the literal version string.
#
# §5.4's mechanism — read the run's own output, never the parameter — has
# nothing to read for such an archive, so the fallback is the next
# self-verifying fact that exists: Maven wrote a `.jar.sha1` sidecar beside the
# jar when it resolved this exact coordinate, and that sidecar is a checksum of
# the archive's own bytes. `_verify_checksum` recomputes it from the jar this
# run actually opened and ABORTS on a mismatch, so a corrupted or
# hand-substituted local jar still fails loud. What is lost, and is stated in
# the write-up rather than smoothed over, is that the version COLUMN for such an
# artifact is the requested coordinate rather than something the archive says.
# This is CP-30's own fallback, applied here rather than reinvented.
_NO_SELF_REPORT = "-"


def self_reported_version(jar: Path, entry: str, key: str) -> str:
    """The version this ARCHIVE claims for itself, read out of its own bytes.

    `entry`/`key` say where the artifact writes it; the answer is always the
    file's. Raises rather than returning a default: a missing self-report is
    exactly the case where a hand-written column header would go unchallenged.

    An artifact whose coordinate declares `-`/`-` states no version anywhere at
    all (see `_NO_SELF_REPORT`); the SHA-1 check stands in, and the caller
    labels the column with the requested coordinate.
    """
    with zipfile.ZipFile(jar) as archive:
        names = [name for name in archive.namelist() if name == entry or name.endswith("/" + entry)]
        if not names:
            raise ProbeError(f"{jar.name} carries no `{entry}` — it reports no version of its own")
        text = archive.read(names[0]).decode("utf-8", "replace")
    for line in text.splitlines():
        match = _PROPERTY.match(line)
        if match and match.group(1).lower() == key.lower():
            return match.group(2)
    raise ProbeError(f"{jar.name}'s `{entry}` declares no `{key}`")


def _verify_checksum(jar: Path) -> None:
    """Recompute the jar's own SHA-1 from its bytes and abort if it disagrees
    with the `.jar.sha1` sidecar Maven wrote when it resolved this coordinate —
    the one self-verifying check left once the archive states no version.

    Byte-for-byte CP-30's own `_verify_checksum`, and deliberately so: two
    probes reading the same two version-less archives should fail the same way.
    """
    sidecar = jar.with_name(jar.name + ".sha1")
    if not sidecar.exists():
        raise ProbeError(
            f"no `{sidecar.name}` beside {jar.name} to verify the resolved jar against"
        )
    expected = sidecar.read_text().strip().split()[0]
    observed = hashlib.sha1(jar.read_bytes()).hexdigest()
    if observed != expected:
        raise ProbeError(
            f"{jar.name}'s SHA-1 {observed!r} disagrees with {sidecar.name}'s {expected!r} "
            "— the resolved jar is not the one Maven checksummed for this coordinate"
        )


def classes_of(jar: Path) -> set[str]:
    """Every top-level class the archive declares, in `javap`'s own spelling."""
    with zipfile.ZipFile(jar) as archive:
        return {
            name[: -len(".class")].replace("/", ".")
            for name in archive.namelist()
            if name.endswith(".class")
        }


def catalog_descriptors() -> list[dict[str, object]]:
    """Every `methods` row in every shipped catalog that declares a descriptor.

    Read off the directory rather than listed, for `shipped_catalogs`' reason:
    a hand-maintained roster stops seeing a catalog exactly when it matters.
    """
    rows: list[dict[str, object]] = []
    for path in sorted(CATALOGS.glob("*.yml")):
        catalog = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        matches = catalog.get("matches") or {}
        # A catalog may name ONE library under several names (§3.1) — the class and
        # the interface a codebase more often declares its field as. Every one is a
        # row of its own here, because the question this probe asks is per owner:
        # an interface that declares a SUBSET of the class's methods would match
        # some call sites and silently miss the rest, and a check that looked only
        # at the first name would never see it.
        declared_owner = matches.get("owner")
        owners = (
            [declared_owner]
            if isinstance(declared_owner, str) or declared_owner is None
            else list(declared_owner)
        )
        for method in matches.get("methods") or []:
            if isinstance(method, dict) and "descriptor" in method:
                for owner in owners:
                    rows.append(
                        {
                            "catalog": path.stem,
                            "owner": str(owner),
                            "name": str(method["name"]),
                            "arity": method.get("arity"),
                            "descriptor": str(method["descriptor"]),
                        }
                    )
    return rows


def _javap(classpath: str, owner: str) -> str:
    result = subprocess.run(
        ["javap", "-p", "-s", "-cp", classpath, owner],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise ProbeError(f"javap could not read {owner}: {result.stderr.strip()}")
    return result.stdout


def _supertypes(header: str) -> list[str]:
    """Every `extends`/`implements` target on `javap`'s own class header,
    generics stripped, both walked — a concrete class need not redeclare a
    `default` interface method at all (measured for `javalin.yml`,
    `javalin-routing`: `io.javalin.Javalin implements
    JavalinDefaultRoutingApi<Javalin>` and `javap -p -s` on `Javalin.class`
    alone shows no `get`/`post`/etc — they exist only as `default` methods on
    the interface), so a walk that followed `extends` alone would report every
    one of them `NOT DECLARED` for a call site whose receiver IS the class.
    W19's `declared_methods` already walks both edges for the same reason
    (`scripts/probes/w19_catalog_surface/sweep.py::_supertypes`); this mirrors
    it rather than inventing a second technique for the same fact.

    Stripped of generics first and repeatedly, because a type parameter may
    itself say `extends` (`class Foo<T extends Bar> extends Baz`) and a split
    on the bare word would then name a bound rather than a supertype.
    """
    previous = None
    while previous != header:
        previous, header = header, _GENERICS.sub("", header)
    found: list[str] = []
    for keyword in (" extends ", " implements "):
        if keyword not in header:
            continue
        tail = header.split(keyword, 1)[1].strip()
        tail = tail.split(" implements ", 1)[0] if keyword == " extends " else tail
        for name in tail.rstrip("{").split(","):
            name = name.strip()
            if name:
                found.append(name)
    return found


def declared_descriptors(classpath: str, owner: str) -> dict[str, set[str]]:
    """Method name -> every erased descriptor reachable on `owner`, inherited
    ones included while the supertype (superclass OR interface) is on this
    classpath.

    A supertype the classpath does not carry ends that branch of the walk
    silently: the run can only speak for what it read, and a descriptor it
    could not see is reported as NOT DECLARED rather than assumed present.
    """
    found: dict[str, set[str]] = defaultdict(set)
    seen: set[str] = set()
    pending: list[str] = [owner]
    while pending:
        current = pending.pop()
        if current in seen or current == "java.lang.Object":
            continue
        seen.add(current)
        try:
            output = _javap(classpath, current)
        except ProbeError:
            if current == owner:
                raise
            continue
        header = ""
        name = None
        for line in output.splitlines():
            if not header and (" class " in line or " interface " in line):
                header = line
                continue
            descriptor = _DESCRIPTOR_LINE.match(line)
            if descriptor is not None:
                if name is not None:
                    found[name].add(descriptor.group(1))
                name = None
                continue
            declaration = _DECLARATION.search(line)
            name = declaration.group(1) if declaration is not None else None
        pending.extend(_supertypes(header))
    return found


def _cell(value: object) -> str:
    return "—" if value is None else str(value)


def main(specs: list[str]) -> int:
    jars: dict[str, Path] = {}
    versions: dict[str, str] = {}
    owners_of_jar: dict[str, set[str]] = defaultdict(set)
    index: dict[str, str] = {}

    for spec in specs:
        group, artifact, requested, entry, key, path = spec.split("|")
        jar = Path(path)
        if not jar.is_file():
            raise ProbeError(f"{group}:{artifact}:{requested} did not resolve to a jar at {jar}")
        if (entry, key) == (_NO_SELF_REPORT, _NO_SELF_REPORT):
            _verify_checksum(jar)
            reported = requested
        else:
            reported = self_reported_version(jar, entry, key)
        if reported != requested:
            # ABORTS, never warns. CP-5 printed the version it believed beside
            # output from the version it ran and the two disagreed in plain
            # sight for a full review cycle.
            raise ProbeError(
                f"{jar.name} reports version {reported!r} at {entry}#{key}, but the coordinate "
                f"list asked for {requested!r} — every cell filed under it would be mislabelled"
            )
        jars[artifact] = jar
        versions[artifact] = reported
        for class_name in classes_of(jar):
            index.setdefault(class_name, artifact)

    classpath = ":".join(str(jar) for jar in jars.values())
    rows = catalog_descriptors()
    if not rows:
        raise ProbeError("no shipped catalog declares a `descriptor:` — nothing to measure")

    results = []
    cache: dict[str, dict[str, set[str]]] = {}
    for row in rows:
        owner = str(row["owner"])
        artifact = index.get(owner)
        if artifact is None:
            raise ProbeError(
                f"{row['catalog']} declares descriptors on {owner}, which none of the resolved "
                f"jars carries — add its coordinate to run.sh rather than leaving it unmeasured"
            )
        owners_of_jar[artifact].add(owner)
        if owner not in cache:
            cache[owner] = declared_descriptors(classpath, owner)
        declared = cache[owner].get(str(row["name"]), set())
        results.append({**row, "artifact": artifact, "declared": row["descriptor"] in declared})

    by_version: dict[str, list[str]] = defaultdict(list)
    for artifact, version in versions.items():
        by_version[version].append(artifact)
    columns = sorted(by_version)

    print("| what the run read | " + " | ".join(columns) + " |")
    print("|---" * (len(columns) + 1) + "|")
    print(
        "| artifacts reporting this version | "
        + " | ".join(", ".join(sorted(by_version[column])) for column in columns)
        + " |"
    )
    print(
        "| owner classes resolved out of them | "
        + " | ".join(
            str(sum(len(owners_of_jar[artifact]) for artifact in by_version[column]))
            for column in columns
        )
        + " |"
    )
    print(
        "| catalog descriptors checked against them | "
        + " | ".join(
            str(sum(1 for r in results if versions[str(r["artifact"])] == column))
            for column in columns
        )
        + " |"
    )
    print(
        "| of those, NOT declared by the jar | "
        + " | ".join(
            str(
                sum(
                    1
                    for r in results
                    if versions[str(r["artifact"])] == column and not r["declared"]
                )
            )
            for column in columns
        )
        + " |"
    )
    print()
    print("| # | catalog | owner | method | arity | descriptor | artifact | version | verdict |")
    print("|---|---|---|---|---|---|---|---|---|")
    for number, result in enumerate(results, start=1):
        artifact = str(result["artifact"])
        print(
            f"| {number} | `{result['catalog']}` | `{result['owner']}` | `{result['name']}` "
            f"| {_cell(result['arity'])} | `{result['descriptor']}` | `{artifact}` "
            f"| {versions[artifact]} | {'declared' if result['declared'] else 'NOT DECLARED'} |"
        )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except ProbeError as error:
        print(f"CP-10 ABORTED: {error}", file=sys.stderr)
        raise SystemExit(1) from error
