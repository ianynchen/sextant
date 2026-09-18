"""CP-18's measurement half: the JAX-RS API jar's own declared shapes (verb
annotations, `@Path`/`@Produces`/`@Consumes`, the `@HttpMethod` custom-verb
boundary, `MediaType`'s literals, the binding/`@Context` vocabulary) and two
independent implementations' (Jersey, RESTEasy classic) resolution order for
`@Produces` and the root-resource inheritance walk.

Called by `run.sh`, which resolves the jars; this script never downloads
anything. Like CP-16/CP-17 it reads each jar's own identity out of its own
bytes before it measures anything and refuses to file a cell under a version
the artifact did not claim (GUIDELINES §5.4, and CP-5's failure it exists to
prevent).

Everything it prints is the table `cp18_jaxrs_api_and_implementations.md`
carries verbatim in its `## Observations` section.
"""

from __future__ import annotations

import re
import subprocess
import sys
import zipfile
from pathlib import Path

_PROPERTY = re.compile(r"^\s*([\w.\-]+)\s*[:=]\s*(.+?)\s*$")
_STEP = " ; "


class ProbeError(RuntimeError):
    """A run that cannot label its own output. Fatal, never advisory."""


class Artifact:
    """One resolved jar, and the identity it reported for itself."""

    def __init__(
        self,
        key: str,
        group: str,
        name: str,
        requested: str,
        jar: Path,
        entry: str,
        manifest_key: str,
    ):
        self.key = key
        self.group = group
        self.name = name
        self.requested = requested
        self.jar = jar
        self.observed = _identity(jar, entry, manifest_key)
        if self.observed != requested:
            raise ProbeError(
                f"{jar.name} reports version {self.observed!r} but was resolved as "
                f"{requested!r} — a mislabelled column, which is CP-5's failure exactly"
            )


def _identity(jar: Path, entry: str, key: str) -> str:
    """The version this ARCHIVE claims for itself, read out of its own bytes."""
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


def _unzip_l(jar: Path, pattern: str) -> list[str]:
    with zipfile.ZipFile(jar) as archive:
        return sorted(n for n in archive.namelist() if re.search(pattern, n))


def _step(line: str) -> str | None:
    match = re.match(r"^\s*\d+:\s+(\S+)(.*)$", line)
    if match is None:
        return None
    operands = match.group(2)
    comment = operands.split("//", 1)[1].strip() if "//" in operands else ""
    return f"{match.group(1)} {comment}".strip()


def q1_verb_attributes(artifact: Artifact, package: str) -> str:
    """Q1. Every verb annotation's declared body — empty, or not."""
    verbs = ["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"]
    classes = [f"{package}.{v}" for v in verbs]
    output = _javap(*classes, classpath=artifact.jar)
    bodies = re.findall(
        r"public interface [\w.]+ extends java\.lang\.annotation\.Annotation \{(.*?)\}",
        output,
        re.DOTALL,
    )
    if len(bodies) != len(verbs):
        raise ProbeError(f"expected {len(verbs)} verb interfaces, javap printed {len(bodies)}")
    return _STEP.join(
        f"{v}: {'0 attributes' if not b.strip() else b.strip()}"
        for v, b in zip(verbs, bodies, strict=True)
    )


def q2_target_and_value(artifact: Artifact, fqn: str) -> str:
    """Q2. `@Target` and `value()`'s declared type, for `@Path`/`@Produces`/`@Consumes`."""
    output = _javap("-v", fqn, classpath=artifact.jar)
    target = re.search(r"java\.lang\.annotation\.Target\(\s*\n\s*value=(\[[^\]]*\]|\S+)", output)
    value = re.search(r"public abstract (\S+) value\(\);", output)
    if not target or not value:
        raise ProbeError(f"{fqn}: could not read @Target/value() from javap -v output")
    return f"@Target({target.group(1)}) ; value(): {value.group(1)}"


def q3a_get_http_method(artifact: Artifact, fqn: str) -> str:
    """Q3a. `@GET`'s own `@HttpMethod(...)` meta-annotation value."""
    output = _javap("-v", fqn, classpath=artifact.jar)
    match = re.search(r"HttpMethod\(\s*\n\s*value=(\S+)\s*\n\s*\)", output)
    if not match:
        raise ProbeError(f"{fqn}: no @HttpMethod meta-annotation found")
    return f"@HttpMethod({match.group(1)})"


def q3b_http_method_itself(artifact: Artifact, fqn: str) -> str:
    """Q3b. `@HttpMethod`'s own `@Target` and `value()` — the custom-verb boundary."""
    return q2_target_and_value(artifact, fqn)


def q4_media_type_constants(artifact: Artifact, fqn: str) -> str:
    """Q4. `MediaType`'s `APPLICATION_JSON`/`SERVER_SENT_EVENTS` literals."""
    output = _javap("-constants", fqn, classpath=artifact.jar)
    found = {}
    for name in ("APPLICATION_JSON", "SERVER_SENT_EVENTS"):
        match = re.search(rf"{name} = (\"[^\"]*\")", output)
        if not match:
            raise ProbeError(f"{fqn}: no constant named {name}")
        found[name] = match.group(1)
    return _STEP.join(f"{k} = {v}" for k, v in found.items())


def q5_resolve_produced_types(artifact: Artifact, fqn: str) -> str:
    """Q5. Jersey's `IntrospectionModeller.resolveProducedTypes` — method vs. class order."""
    output = _javap("-c", "-p", fqn, classpath=artifact.jar)
    lines = output.splitlines()
    start = next(
        (i for i, line in enumerate(lines) if "resolveProducedTypes" in line and "()" not in line),
        None,
    )
    if start is None:
        raise ProbeError(f"{fqn}: no resolveProducedTypes method found")
    body = []
    for line in lines[start:]:
        step = _step(line)
        if step:
            body.append(step)
        if len(body) >= 8:
            break
    return _STEP.join(body)


def q6_hierarchy_walk(artifact: Artifact, fqn: str, method: str) -> str:
    """Q6. The `class -> interfaces -> superclass` walk, in whichever
    implementation's helper method carries it."""
    output = _javap("-c", "-p", fqn, classpath=artifact.jar)
    lines = output.splitlines()
    start = next((i for i, line in enumerate(lines) if method in line and "(" in line), None)
    if start is None:
        raise ProbeError(f"{fqn}: no {method} method found")
    seen: list[str] = []
    for line in lines[start:]:
        step = _step(line)
        if step is None:
            if seen and line.strip() == "":
                break
            continue
        if "isAnnotationPresent" in step or "getInterfaces" in step or "getSuperclass" in step:
            seen.append(step)
    if not seen:
        raise ProbeError(f"{fqn}.{method}: no class/interfaces/superclass markers found")
    return _STEP.join(seen)


def q7a_binding_annotations(artifact: Artifact) -> str:
    """Q7a. The binding-param and `@Context`/`@Suspended` annotation vocabulary."""
    names = _unzip_l(
        artifact.jar,
        r"jakarta/ws/rs/(Path|Query|Header|Cookie|Form|Matrix|Bean)Param\.class|DefaultValue\.class|core/Context\.class|container/Suspended\.class",
    )
    return _STEP.join(sorted(names))


def q7b_context_types(artifact: Artifact) -> str:
    """Q7b. The `@Context`-injectable type vocabulary, JAX-RS §9.2."""
    names = _unzip_l(
        artifact.jar,
        r"core/(UriInfo|HttpHeaders|Request|SecurityContext|Configuration|Application)\.class"
        r"|ext/Providers\.class|container/ResourceContext\.class|sse/(Sse|SseEventSink)\.class",
    )
    return _STEP.join(sorted(names))


def main(specs: list[str]) -> int:
    artifacts: dict[str, Artifact] = {}
    for spec in specs:
        key, group, name, version, entry, mkey, jar = spec.split("|")
        artifacts[key] = Artifact(key, group, name, version, Path(jar), entry, mkey)

    jakarta40 = artifacts["jakarta40"]
    jakarta31 = artifacts["jakarta31"]
    javax211 = artifacts["javax211"]
    jersey40 = artifacts["jersey40"]
    resteasy = artifacts["resteasy"]

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

    rows: list[tuple[str, str, Artifact, str]] = [
        (
            "1a",
            "verb annotations' declared attributes",
            jakarta40,
            q1_verb_attributes(jakarta40, "jakarta.ws.rs"),
        ),
        (
            "1b",
            "verb annotations' declared attributes",
            jakarta31,
            q1_verb_attributes(jakarta31, "jakarta.ws.rs"),
        ),
        (
            "1c",
            "verb annotations' declared attributes",
            javax211,
            q1_verb_attributes(javax211, "javax.ws.rs"),
        ),
        (
            "2a",
            "@Target and value()'s type",
            jakarta40,
            q2_target_and_value(jakarta40, "jakarta.ws.rs.Path"),
        ),
        (
            "2b",
            "@Target and value()'s type",
            jakarta40,
            q2_target_and_value(jakarta40, "jakarta.ws.rs.Produces"),
        ),
        (
            "2c",
            "@Target and value()'s type",
            jakarta40,
            q2_target_and_value(jakarta40, "jakarta.ws.rs.Consumes"),
        ),
        (
            "3a",
            "@GET's own meta-annotation",
            jakarta40,
            q3a_get_http_method(jakarta40, "jakarta.ws.rs.GET"),
        ),
        (
            "3b",
            "@HttpMethod itself: @Target and value()",
            jakarta40,
            q3b_http_method_itself(jakarta40, "jakarta.ws.rs.HttpMethod"),
        ),
        (
            "4",
            "MediaType's constants",
            jakarta40,
            q4_media_type_constants(jakarta40, "jakarta.ws.rs.core.MediaType"),
        ),
        (
            "5",
            "Jersey's resolveProducedTypes: method-over-class",
            jersey40,
            q5_resolve_produced_types(
                jersey40, "org.glassfish.jersey.server.model.IntrospectionModeller"
            ),
        ),
        (
            "6a",
            "class -> interfaces -> superclass walk",
            jersey40,
            q6_hierarchy_walk(
                jersey40,
                "org.glassfish.jersey.server.model.internal.ModelHelper",
                "getAnnotatedResourceClass",
            ),
        ),
        (
            "6b",
            "class -> interfaces -> superclass walk",
            resteasy,
            q6_hierarchy_walk(
                resteasy, "org.jboss.resteasy.util.AnnotationResolver", "getClassWithAnnotation"
            ),
        ),
        (
            "7a",
            "binding-param/@Context/@Suspended vocabulary",
            jakarta40,
            q7a_binding_annotations(jakarta40),
        ),
        ("7b", "@Context-injectable type vocabulary", jakarta40, q7b_context_types(jakarta40)),
    ]
    for number, question, artifact, observed in rows:
        print(
            f"| {number} | {question} | `{artifact.group}:{artifact.name}` | {artifact.observed} | `{observed}` |"
        )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except ProbeError as error:
        print(f"CP-18 aborted: {error}", file=sys.stderr)
        raise SystemExit(1) from None
