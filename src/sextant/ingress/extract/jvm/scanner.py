import json
import subprocess
from pathlib import Path

from sextant.application.ports.scanner import ScanError, ScanReport, ScanRequest

_LANGUAGES = {"java", "kotlin"}
_CAPABILITIES = {
    "annotation_args",
    "typed_signatures",
    "type_annotations",
    "kotlin_metadata",
    # Phase 2C: a per-method dataflow pass over every invoke, which is what
    # makes a call literal a fact and a within-method value join possible.
    "call_site",
    "string_constants",
    "chain_reconstruction",
    # A class symbol fact's own `interfaces` — the erased interface symbols ASM's
    # `visit` hands over, in declaration order.
    "implemented_interfaces",
    # Capability 9.14: a class symbol fact's `generic_interfaces` — the
    # parameterized superinterface references `interfaces` above erases, kept
    # as full type references. Spring Data REST reads it for a repository's
    # entity type (2O design §2a).
    "generic_interfaces",
    # Capability 9.13: a class symbol fact's `superclass` — the erased symbol
    # of its direct superclass, read off the class file regardless of whether
    # its signature is generic. D00 §4's `relationship_kind: extends`, made
    # real (2O CP-3 found it absent from the fact stream).
    "superclass",
    # Capability 9.15: a call-site argument whose producer is an
    # `ANEWARRAY`/`AASTORE` construction reads as `{kind: array, elements:
    # […]}` rather than one opaque `unresolved`. Every `String...` API in the
    # estate depends on it — the measured defect is
    # `scripts/probes/spring-integration-destinations.md`.
    "array_arguments",
    # Capability 9.16: an annotation-valued annotation argument reads as a
    # nested `{annotation, args}` use of its own, recursively, rather than
    # being dropped with no key at all. `@Poller` inside `@InboundChannelAdapter`,
    # `@Queue` inside `@QueueBinding` inside `@RabbitListener`, and — the
    # sharpest case — every `@Scheduled` on a method carrying two of them,
    # which javac folds into one `@Schedules` array.
    "nested_annotation_args",
}


class AsmScanner:
    """One backend covering every JVM language, declaring twelve capabilities:
    the four Phase 1 read from declarations, the three Phase 2C's per-method
    dataflow pass added — the call sites themselves, the literals they carry,
    and the within-method value ids a chain is rebuilt from — plus a class
    symbol's own declared interfaces, its generic superinterface references,
    its erased superclass, the elements of an array-valued argument, and the
    arguments of an annotation nested inside another (2O capabilities 9.14,
    9.13, 9.15 and 9.16)."""

    def __init__(self, jar: Path) -> None:
        self._jar = jar

    def accepts(self, languages: set[str]) -> bool:
        return bool(languages & _LANGUAGES)

    def capabilities(self) -> set[str]:
        return set(_CAPABILITIES)

    def rank(self) -> int:
        return 100

    def scan(self, request: ScanRequest) -> ScanReport:
        # `--origin` is passed only when the request names one: the extractor
        # writes the key only when it is given, so a module's own scan stays
        # byte-for-byte what it was before library extraction existed.
        origin = ["--origin", request.origin] if request.origin is not None else []
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
                *origin,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            raise ScanError(f"extractor failed: {completed.stderr.strip()}")
        report = json.loads(completed.stdout)
        return ScanReport(
            documents=report["documents"],
            facts=report["facts"],
            scanner_id=report["scanner_id"],
            scanner_version=report["scanner_version"],
            uncovered=tuple(report["uncovered"]),
        )
