"""CP-41: what does javac leave at a call whose argument was REASSIGNED on one branch, and
what does the extractor now write for it?

Prints the observation table `cp41_merge_candidates.md` carries. Every cell is read from a
process's own output: the JDK identity from `$JAVA_HOME/.../release` (falling back to
`javap -version`), never from the parameter this harness was handed — the CP-5 failure the
convention exists to prevent — and the argument JSON from the extractor jar run on the
compiled class, never typed.
"""

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HOME = Path(os.environ.get("JAVA_HOME", "/opt/homebrew/opt/openjdk@21"))
JAVA = HOME / "bin" / "java"
JAVAP = HOME / "bin" / "javap"
REPO = Path(__file__).resolve().parents[3]
JAR = REPO / "src" / "sextant" / "extractor-jvm" / "sextant-extractor.jar"
# The two classes measured: the fixture's wrapper, and the production code it mirrors.
CASES = [
    (
        "fixture",
        REPO / "fixtures/orders-service/target/classes",
        "com/acme/orders/clients/NormalisingBillingClient#send(",
    ),
    (
        "apollo",
        REPO / "examples/apollo/apollo-portal/target/classes",
        "com/ctrip/framework/apollo/portal/component/RetryableRestTemplate#execute(",
    ),
]


def reported_identity() -> tuple[str, str]:
    """The JDK as the INSTALLATION itself reports it, and how it was read."""
    for candidate in (HOME / "release", HOME / "libexec/openjdk.jdk/Contents/Home/release"):
        if candidate.is_file():
            for line in candidate.read_text(encoding="utf-8").splitlines():
                if line.startswith("JAVA_RUNTIME_VERSION="):
                    return line.split("=", 1)[1].strip().strip('"'), str(
                        candidate.relative_to(HOME)
                    )
    spoken = subprocess.run(
        [str(JAVAP), "-version"], capture_output=True, text=True, check=False
    ).stdout.strip()
    return spoken or "NOT READ", "javap -version"


def frame_shape(classes: Path, caller: str) -> str:
    """What javap shows between the branch and the consuming call: the reassignment's
    `astore` to the same slot the parameter arrived in, which is the merge."""
    owner = caller.split("#")[0]
    out = subprocess.run(
        [str(JAVAP), "-c", "-p", str(classes / f"{owner}.class")],
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    method = caller.split("#")[1].split("(")[0]
    block = re.search(rf"\b{method}\(.*?\n(.*?)\n\n", out, re.DOTALL)
    if block is None:
        return "METHOD NOT FOUND"
    body = block.group(1)
    stores = len(re.findall(r"\bastore", body))
    substrings = len(re.findall(r"String\.substring", body))
    # javac keeps a reassigned parameter in the SAME slot it arrived in, so the store after
    # `substring` is what makes the consuming load see two producers; the count is what the
    # table reports, and the merge the extractor writes (next row) is the verdict.
    return f"`substring` calls: {substrings}; `astore`s in the method: {stores}"


def merge_argument(classes: Path, caller: str) -> str:
    """The argument JSON the extractor writes for the merged slot in `caller`."""
    with tempfile.TemporaryDirectory() as scratch:
        out = Path(scratch) / "facts"
        subprocess.run(
            [
                str(JAVA),
                "-jar",
                str(JAR),
                "--module-id",
                "probe:cp41",
                "--coordinates",
                "probe/cp41",
                "--version",
                "0",
                "--classes",
                str(classes),
                "--out",
                str(out),
                "--fact-schema-version",
                "5",
                "--sextant-version",
                "probe",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        for path in sorted(out.rglob("*.jsonl")):
            for line in path.read_text(encoding="utf-8").splitlines():
                fact = json.loads(line)
                if fact.get("kind") != "call_site" or caller not in str(fact.get("caller", "")):
                    continue
                for argument in fact.get("arguments") or []:
                    if argument.get("kind") == "merge":
                        kinds = ", ".join(
                            c["kind"]
                            + (f"({c['value']})" if "value" in c else "")
                            + (f"[source {c['source']}]" if "source" in c else "")
                            for c in argument["candidates"]
                        )
                        return f"`merge` with candidates: {kinds} — at `{fact['target']['name']}`"
    return "NO MERGE ARGUMENT WRITTEN"


def main() -> int:
    version, how = reported_identity()
    print("| what the run read | " + version + " |")
    print("|---|---|")
    print(f"| JDK identity read from the installation itself (`{how}`) | yes |")
    print(f"| extractor | `{JAR.name}` |")
    print()
    print("| # | class | question | version | observed |")
    print("|---|---|---|---|---|")
    row = 1
    for label, classes, caller in CASES:
        if not classes.is_dir():
            print(
                f"| {row} | {label} | — | {version} | NOT BUILT HERE ({classes.relative_to(REPO)}) |"
            )
            row += 1
            continue
        print(
            f"| {row} | {label} | what javac emits around the reassignment | {version} | {frame_shape(classes, caller)} |"
        )
        row += 1
        print(
            f"| {row} | {label} | what the extractor writes at the consuming call | {version} | {merge_argument(classes, caller)} |"
        )
        row += 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
