import json
import subprocess
from pathlib import Path

from sextant.application.ports.scanner import ScanError, ScanReport, ScanRequest
from sextant.domain.version import FACT_SCHEMA_VERSION, SEXTANT_VERSION

_LANGUAGES = {"java", "kotlin"}


class AsmScanner:
    """One backend covering every JVM language.

    **It does not declare what it can read — it ASKS the jar.** The list lived
    here as a fourteen-name constant until Step 1, and it was a claim about a
    binary this package does not build: `./gradlew build` is a separate step,
    so a jar could be older than the constant describing it. Capabilities gate
    which catalogs run (`analyze`), so a wrong answer does not fail — it runs a
    catalog against a fact kind that jar never emitted, and the module reports
    an absence nothing distinguishes from a real one.

    A jar that is behind now reports FEWER capabilities and the workspace says
    so through `skipped_catalogs`, which is the channel D02 §2 already defines
    for a weaker scanner degrading visibly. `scanner_version: "9.18"` was the
    previous, accidental carrier of this information — a CAPABILITY number in a
    field named for a library version, which is why it read as a version nobody
    could resolve.
    """

    def __init__(self, jar: Path) -> None:
        self._jar = jar
        self._capabilities: frozenset[str] | None = None

    def accepts(self, languages: set[str]) -> bool:
        return bool(languages & _LANGUAGES)

    def capabilities(self) -> set[str]:
        """Asked once per instance, before any scan — catalogs are gated on the
        answer, so it must be available without paying for an extraction."""
        if self._capabilities is None:
            completed = subprocess.run(
                ["java", "-jar", str(self._jar), "--capabilities"],
                capture_output=True,
                text=True,
                check=False,
            )
            if completed.returncode != 0:
                raise ScanError(f"extractor failed: {completed.stderr.strip()}")
            self._capabilities = frozenset(json.loads(completed.stdout)["capabilities"])
        return set(self._capabilities)

    def rank(self) -> int:
        return 100

    def scan(self, request: ScanRequest) -> ScanReport:
        # `--origin` is passed only when the request names one: the extractor
        # writes the key only when it is given, so a module's own scan stays
        # byte-for-byte what it was before library extraction existed.
        origin = ["--origin", request.origin] if request.origin is not None else []
        # The classpath goes in a FILE, one `coordinate<TAB>version<TAB>archive` per line:
        # `ruoyi`'s largest module resolves hundreds of jars, and a command line is the
        # wrong place for a list that long. Written beside the fact root rather than inside
        # it — everything under `out_dir` is read back as facts — and removed afterwards.
        classpath: list[str] = []
        classpath_file: Path | None = None
        if request.dependency_archives:
            classpath_file = request.out_dir.parent / f".{request.out_dir.name}.classpath.tsv"
            classpath_file.write_text(
                "".join(
                    f"{root.coordinate}\t{root.version}\t{root.archive}\n"
                    for root in request.dependency_archives
                ),
                encoding="utf-8",
            )
            classpath = ["--classpath-file", str(classpath_file)]
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
                # Handed over rather than held in Java (Step 0). The extractor
                # used to carry its own literal for the fact-schema stamp and a
                # default for this one, so both were copies of a Python
                # constant nothing in that repository can see — which is how
                # four producers of one stamp came to hold two values. Both are
                # required there now: absent is a refusal, never a default.
                "--fact-schema-version",
                str(FACT_SCHEMA_VERSION),
                "--sextant-version",
                SEXTANT_VERSION,
                *origin,
                *classpath,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if classpath_file is not None:
            classpath_file.unlink(missing_ok=True)
        if completed.returncode != 0:
            raise ScanError(f"extractor failed: {completed.stderr.strip()}")
        report = json.loads(completed.stdout)
        # The scan's own answer becomes the cache. Two consequences, both
        # wanted: a later `capabilities()` needs no second subprocess, and the
        # two answers cannot drift apart — a jar replaced mid-run is refused
        # rather than silently gating catalogs on a set it no longer reports.
        reported = tuple(report["capabilities"])
        if self._capabilities is not None and self._capabilities != frozenset(reported):
            raise ScanError(
                f"the extractor reported {sorted(reported)} on this scan but "
                f"{sorted(self._capabilities)} when asked — the jar changed mid-run"
            )
        self._capabilities = frozenset(reported)
        return ScanReport(
            documents=report["documents"],
            facts=report["facts"],
            scanner_id=report["scanner_id"],
            scanner_libraries=tuple(report["scanner_libraries"]),
            capabilities=reported,
            uncovered=tuple(report["uncovered"]),
        )
