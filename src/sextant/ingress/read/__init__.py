"""ArtifactReader implementations (D00 §5c). One scanner_id shared by every
format this facility reads — the same discipline the JVM scanner's own
scanner_id keeps across every source language it disassembles (D00 §2):
`scanner_id` names the facility, not the format, and `language` (carried per
Document) already says which format a given file was."""

import hashlib
from pathlib import Path

from sextant.domain.closed_sets import OriginTier
from sextant.domain.facts import Document

SCANNER_ID = "sextant-config-reader"
SCANNER_VERSION = "0.1.0"
FACT_SCHEMA_VERSION = "1.0.0"
SEXTANT_VERSION = "0.1.0"
# D04 redaction has no producer reaching readers yet (egress/export/manifest.py
# carries the same absence) — this is the literal the JVM extractor writes for
# the same reason: an honest "none", not a fabricated hash.
NO_REDACTION_HASH = "sha256:none"


def build_document(
    *,
    file: Path,
    root: Path,
    module_id: str,
    language: str,
    content: bytes,
    partial: bool = False,
    partial_reason: str | None = None,
) -> Document:
    """One Document per config file, fields mirroring what a scanner emits
    (D00 §2). `document_id` is the sha256 of the file's path relative to its
    resource root — there is no class-file/source-file split to disambiguate
    here, so unlike the JVM scanner's class-relative id, one path is already
    unique per document."""
    relative_path = file.relative_to(root).as_posix()
    return Document(
        document_id=hashlib.sha256(relative_path.encode("utf-8")).hexdigest(),
        relative_path=relative_path,
        module_id=module_id,
        language=language,
        sextant_version=SEXTANT_VERSION,
        fact_schema_version=FACT_SCHEMA_VERSION,
        scanner_id=SCANNER_ID,
        scanner_version=SCANNER_VERSION,
        content_hash="sha256:" + hashlib.sha256(content).hexdigest(),
        # The resource root this file was read from — the neutral analogue
        # of the classpath entry a scanner records here (D00 §2).
        origin_entry=root.as_posix(),
        # A config file under a module's own resource root is the module's
        # own source, the same standing a compiled class from this module's
        # own output directory has — never a dependency's (D00 §2's tiering
        # exists to tell those apart; this reader never reads anyone else's
        # resources).
        origin_tier=OriginTier.MODULE_OUTPUT,
        redaction_set_hash=NO_REDACTION_HASH,
        partial=partial,
        partial_reason=partial_reason,
    )
