"""ArtifactReader implementations (D00 §5c). One scanner_id shared by every
format this facility reads — the same discipline the JVM scanner's own
scanner_id keeps across every source language it disassembles (D00 §2):
`scanner_id` names the facility, not the format, and `language` (carried per
Document) already says which format a given file was."""

import hashlib
from pathlib import Path

from sextant.domain.closed_sets import OriginTier
from sextant.domain.facts import Document
from sextant.domain.version import FACT_SCHEMA_VERSION, SEXTANT_VERSION

# This facility, named. It carries no version of its own: `ingress/read` ships
# inside the wheel, so it moves with `sextant_version` — which the document
# already stamps — and the `"0.1.0"` that used to sit here was a third copy of
# the tool's version, set when this module was written and never once moved.
SCANNER_ID = "sextant-config-reader"
# A document's own `redaction_set_hash` says which rule set was applied to THIS
# document's facts (D01 §7's cache key: "a new pattern cannot clean values
# already written"). Nothing is applied to them: 2K design §1 rules that the
# workspace stays verbatim — analysis needs real values, and the analyst's own
# disk is not the trust boundary — and masks at the EXITS instead, where the
# bundle's manifest names the rule set that masked it. So `none` is the honest
# answer here and stays one, the same literal the JVM extractor writes.
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
