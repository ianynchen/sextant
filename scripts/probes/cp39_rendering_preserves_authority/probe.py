"""CP-39: does a RENDERING call preserve an authority, and what does javac emit?

Prints the observation table `cp39_rendering_preserves_authority.md` carries. Every cell is
read from a process's own output: the JDK identity comes from `$JAVA_HOME/.../release` and
`javap -version` rather than from the parameter this harness was handed, which is the CP-5
failure the convention exists to prevent.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

HOME = Path(os.environ.get("JAVA_HOME", "/opt/homebrew/opt/openjdk@21"))
JAVAP = HOME / "bin" / "javap"
FIXTURE = (
    Path(__file__).resolve().parents[3]
    / "fixtures/orders-discovery/target/classes/com/acme/dc/OwnerClient.class"
)


def reported_identity() -> tuple[str, str]:
    """The JDK as the INSTALLATION itself reports it, and how it was read."""
    for candidate in (
        HOME / "release",
        HOME / "libexec/openjdk.jdk/Contents/Home/release",
    ):
        if candidate.is_file():
            for line in candidate.read_text(encoding="utf-8").splitlines():
                if line.startswith("JAVA_RUNTIME_VERSION="):
                    return line.split("=", 1)[1].strip().strip('"'), str(
                        candidate.relative_to(HOME)
                    )
    spoken = subprocess.run(
        [str(JAVAP), "-version"], capture_output=True, text=True, check=False
    ).stdout.strip()
    return spoken or "unknown", "javap -version"


def valueOf_body() -> str:
    out = subprocess.run(
        [str(JAVAP), "-c", "-p", "java.lang.String"], capture_output=True, text=True, check=False
    ).stdout
    block = re.search(
        r"public static java\.lang\.String valueOf\(java\.lang\.Object\);\n(.*?)\n\n",
        out,
        re.DOTALL,
    )
    body = block.group(1) if block else "NOT READ"
    calls = re.findall(r"// Method ([^\s]+)", body)
    return f"returns `{'`, `'.join(calls) or 'no call'}` ; literal for null: " + (
        "yes" if "String null" in body else "no"
    )


def concat_emission() -> str:
    if not FIXTURE.is_file():
        return "FIXTURE NOT BUILT"
    out = subprocess.run(
        [str(JAVAP), "-c", "-p", str(FIXTURE)], capture_output=True, text=True, check=False
    ).stdout
    block = out[out.index("public java.lang.String owners()") :]
    calls = re.findall(r"// (?:Method|InvokeDynamic) ([^\s]+)", block[: block.index("areturn")])
    return " -> ".join(calls)


def main() -> int:
    version, how = reported_identity()
    print("| what the run read | " + version + " |")
    print("|---|---|")
    print(f"| JDK identity read from the installation itself (`{how}`) | yes |")
    print(f"| fixture measured | {FIXTURE.name} |")
    print()
    print("| # | question | artifact | version | observed |")
    print("|---|---|---|---|---|")
    print(
        f"| 1 | what `String.valueOf(Object)` does | `java.base` | {version} | `{valueOf_body()}` |"
    )
    print(
        f"| 2 | what javac emits for `URI + String` | `java.base` (javac) | {version} | "
        f"`{concat_emission()}` |"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
