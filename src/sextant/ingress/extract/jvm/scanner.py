import json
import subprocess
from pathlib import Path

from sextant.application.ports.scanner import ScanReport, ScanRequest

_LANGUAGES = {"java", "kotlin"}
_CAPABILITIES = {"annotation_args", "typed_signatures", "type_annotations", "kotlin_metadata"}


class AsmScanner:
    """One backend covering every JVM language. Phase 1 declares two
    capabilities; control flow and chain reconstruction arrive in Phase 2."""

    def __init__(self, jar: Path) -> None:
        self._jar = jar

    def accepts(self, languages: set[str]) -> bool:
        return bool(languages & _LANGUAGES)

    def capabilities(self) -> set[str]:
        return set(_CAPABILITIES)

    def rank(self) -> int:
        return 100

    def scan(self, request: ScanRequest) -> ScanReport:
        completed = subprocess.run(
            [
                "java",
                "-jar",
                str(self._jar),
                "--module-id",
                request.module_id,
                "--coordinates",
                request.coordinates,
                "--version",
                request.version,
                "--classes",
                str(request.classes_dir),
                "--out",
                str(request.out_dir),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(f"extractor failed: {completed.stderr.strip()}")
        report = json.loads(completed.stdout)
        return ScanReport(
            documents=report["documents"],
            facts=report["facts"],
            scanner_id=report["scanner_id"],
            scanner_version=report["scanner_version"],
            uncovered=tuple(report["uncovered"]),
        )
