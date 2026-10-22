"""Shared by CP-42 and CP-43: a Spring jar out of the local Maven repository, with the version
the jar ITSELF states in its manifest — never the directory name this harness found it under,
which is the CP-5 failure the convention exists to prevent."""

import os
import subprocess
import zipfile
from pathlib import Path

HOME = Path(os.environ.get("JAVA_HOME", "/opt/homebrew/opt/openjdk@21"))
JAVAP = HOME / "bin" / "javap"
REPOSITORY = Path.home() / ".m2" / "repository"


def newest_jar(group: str, artifact: str) -> Path | None:
    base = REPOSITORY.joinpath(*group.split("."), artifact)
    if not base.is_dir():
        return None
    candidates = sorted(
        (p for p in base.glob(f"*/{artifact}-*.jar") if not p.name.endswith("-sources.jar")),
        key=lambda p: [
            int(x) if x.isdigit() else x for x in p.parent.name.replace("-", ".").split(".")
        ],
    )
    return candidates[-1] if candidates else None


def manifest_version(jar: Path) -> str:
    with zipfile.ZipFile(jar) as archive:
        for line in archive.read("META-INF/MANIFEST.MF").decode("utf-8", "replace").splitlines():
            if line.startswith("Implementation-Version:"):
                return line.split(":", 1)[1].strip()
    return "NOT STATED"


def javap(jar: Path, class_name: str, *flags: str) -> str:
    return subprocess.run(
        [str(JAVAP), *flags, "-cp", str(jar), class_name],
        capture_output=True,
        text=True,
        check=False,
    ).stdout
