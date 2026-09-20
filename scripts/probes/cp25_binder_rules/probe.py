"""CP-25's measurement half. Row 1, here now: Javalin 6.4.0's `ApiBuilder` guard —
what `staticInstance()` throws when no block is open (the exception class and the
message literal) and one verb's first instructions showing every static verb goes
through it — the measured fact `javalin-apibuilder.yml`'s `follow_calls: all` rests
on (spec 2026-09-19 §4a). The binder rows the request-requirements work adds (spec
§5b–§5d: spring-web, micronaut-http, RESTEasy Reactive, reactive-routes, Javalin's
`Validator.get()`, `jakarta.servlet`) join this same script as further questions.

Called by `run.sh`, which resolves the jar; this script downloads nothing. Like
CP-16 through CP-24 it reads the jar's own identity out of its own bytes before it
measures anything and refuses to file a cell under a version the archive did not
claim (GUIDELINES §5.4, and CP-5's failure it exists to prevent).
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
    def __init__(self, key: str, group: str, name: str, requested: str, jar: Path):
        self.key = key
        self.group = group
        self.name = name
        self.requested = requested
        self.jar = jar
        self.observed = _identity(jar, "META-INF/MANIFEST.MF", "Implementation-Version")
        if self.observed != requested:
            raise ProbeError(
                f"{jar.name} reports version {self.observed!r} but was expected to report "
                f"{requested!r} — a mislabelled column, which is CP-5's failure exactly"
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


def _method_body(output: str, header: str) -> list[str]:
    """The instruction lines of the first method whose declaration line contains
    `header`, up to the blank line that ends it."""
    lines = output.splitlines()
    start = next((i for i, line in enumerate(lines) if header in line), None)
    if start is None:
        raise ProbeError(f"no method matching {header!r}")
    body: list[str] = []
    for line in lines[start + 1 :]:
        if not line.strip():
            break
        body.append(line)
    return body


def _step(line: str) -> str | None:
    match = re.match(r"^\s*\d+:\s+(\S+)(.*)$", line)
    if match is None:
        return None
    operands = match.group(2)
    comment = operands.split("//", 1)[1].strip() if "//" in operands else ""
    return f"{match.group(1)} {comment}".strip()


def _steps(body: list[str]) -> list[str]:
    return [s for s in (_step(line) for line in body) if s is not None]


# --- Q1: the ApiBuilder guard (spec 2026-09-19 §4a, `follow_calls: all`) -------


def q1_api_builder_guard(javalin: Path) -> str:
    output = _javap("-c", "-p", "io.javalin.apibuilder.ApiBuilder", classpath=javalin)
    field = next(
        (
            line.strip()
            for line in output.splitlines()
            if "staticJavalin;" in line and "static" in line
        ),
        "?",
    )
    guard = _steps(_method_body(output, "staticInstance();"))
    verb = _steps(
        _method_body(output, "public static void get(java.lang.String, io.javalin.http.Handler);")
    )
    return _STEP.join(
        [
            f"field: {field}",
            "staticInstance(): " + _STEP.join(guard),
            "get(String, Handler) opens with: " + _STEP.join(verb[:1]),
        ]
    )


def main(specs: list[str]) -> int:
    artifacts: dict[str, Artifact] = {}
    for spec in specs:
        key, group, name, requested, jar = spec.split("|")
        artifacts[key] = Artifact(key, group, name, requested, Path(jar))
    javalin = artifacts["javalin"]

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
    print(
        "| identity read from the archive itself (`Implementation-Version`) | "
        + " | ".join(["yes"] * len(columns))
        + " |"
    )
    print()
    print("| # | question | artifact | version | observed |")
    print("|---|---|---|---|---|")
    print(
        f"| 1 | ApiBuilder.staticInstance(): the thread-local field, what it throws with no block open, and a verb's first instruction | "
        f"`{javalin.group}:{javalin.name}` | {javalin.observed} | `{q1_api_builder_guard(javalin.jar)}` |"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except ProbeError as error:
        print(f"CP-25 aborted: {error}", file=sys.stderr)
        raise SystemExit(1) from None
