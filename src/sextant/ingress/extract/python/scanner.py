"""The Python scanner backend (M03, spec 2026-11-06 §3a): reads `.py` source with the
standard library's `ast` and writes the facts the JVM scanner writes, one fact file per
source file. It never imports or runs the code it reads, and it downloads nothing.
"""

import ast
import hashlib
import os
import sys
from collections.abc import Iterable
from pathlib import Path

from sextant.application.ports.scanner import ScanReport, ScanRequest
from sextant.domain.closed_sets import OriginTier
from sextant.domain.factfile import write_fact_file
from sextant.domain.facts import Document
from sextant.domain.symbols import NOT_APPLICABLE, PYTHON_SCHEME
from sextant.domain.version import FACT_SCHEMA_VERSION, SEXTANT_VERSION
from sextant.ingress.extract.python.imports import ModuleIndex, module_path
from sextant.ingress.extract.python.structure import FileContext, file_facts

_LANGUAGE = "python"
_SCANNER_ID = "sextant-python-scanner"
_PACKAGE_MANAGER = "pypi"
_SUFFIX = ".py"
_NO_REDACTION_HASH = "sha256:none"
# What this backend reads (M03 "Capabilities"). `control_flow` joins when the flow
# fields are written.
_CAPABILITIES = frozenset({"typed_signatures", "annotation_args", "type_annotations", "value_ids"})
# Folders that hold no code of the module: tool caches, version control, installed
# packages. A folder that holds `pyvenv.cfg` is an environment and is skipped too.
_SKIPPED_FOLDERS = frozenset(
    {".git", ".sextant", "__pycache__", "node_modules", "site-packages", ".tox", ".nox"}
)
_ENVIRONMENT_MARKER = "pyvenv.cfg"


class PythonScanner:
    """One backend for Python source. The import roots arrive as `classes_dir` and
    `more_classes_dirs`: Python runs from source, so the source is what is read."""

    def accepts(self, languages: set[str]) -> bool:
        return _LANGUAGE in languages

    def capabilities(self) -> set[str]:
        return set(_CAPABILITIES)

    def rank(self) -> int:
        return 0

    def scan(self, request: ScanRequest) -> ScanReport:
        roots = [request.classes_dir, *request.more_classes_dirs]
        files = [(root, relative) for root in roots for relative in _python_files(root)]
        index = ModuleIndex(frozenset(_module_paths(relative for _, relative in files)))
        manager = NOT_APPLICABLE if request.coordinates == NOT_APPLICABLE else _PACKAGE_MANAGER
        prefix = f"{PYTHON_SCHEME} {manager} {request.coordinates} {request.version} "
        documents = facts = 0
        uncovered: list[str] = []
        for root, relative in files:
            here, is_package = module_path(relative)
            if not here:
                uncovered.append(f"{relative}: a package file at an import root has no name")
                continue
            content = (root / relative).read_bytes()
            try:
                tree = ast.parse(content, filename=relative)
            except (SyntaxError, ValueError, RecursionError) as failure:
                uncovered.append(f"{relative}: not readable as Python: {_reason(failure)}")
                continue
            document = Document(
                document_id=hashlib.sha256(relative.encode()).hexdigest(),
                relative_path=relative,
                module_id=request.module_id,
                language=_LANGUAGE,
                sextant_version=SEXTANT_VERSION,
                fact_schema_version=FACT_SCHEMA_VERSION,
                scanner_id=_SCANNER_ID,
                content_hash="sha256:" + hashlib.sha256(content).hexdigest(),
                origin_entry=str(root),
                origin_tier=OriginTier.DEPENDENCY
                if request.origin is not None
                else OriginTier.MODULE_OUTPUT,
                redaction_set_hash=_NO_REDACTION_HASH,
                origin=request.origin,
            )
            context = FileContext(here, is_package, index, prefix, document.document_id)
            written = file_facts(tree, context, len(content.splitlines()) or 1)
            write_fact_file(request.out_dir / f"{relative}.jsonl", document, written)
            documents += 1
            facts += len(written)
        return ScanReport(
            documents=documents,
            facts=facts,
            scanner_id=_SCANNER_ID,
            capabilities=tuple(sorted(_CAPABILITIES)),
            uncovered=tuple(uncovered),
        )


def _python_files(root: Path) -> list[str]:
    """Every `.py` file under `root`, relative and `/`-separated, in sorted order."""
    found: list[str] = []
    for current, folders, files in os.walk(root):
        folders[:] = sorted(
            folder
            for folder in folders
            if folder not in _SKIPPED_FOLDERS
            and not folder.startswith(".")
            and not os.path.isfile(os.path.join(current, folder, _ENVIRONMENT_MARKER))
        )
        base = Path(current).relative_to(root)
        found.extend((base / name).as_posix() for name in sorted(files) if name.endswith(_SUFFIX))
    return sorted(found)


def _module_paths(relatives: Iterable[str]) -> set[str]:
    """Every module path the files make importable: each file's own, and each folder
    above it, as a package or a namespace package."""
    paths: set[str] = set()
    for relative in relatives:
        here, _ = module_path(relative)
        while here:
            paths.add(here)
            here = here.rpartition("/")[0]
    return paths


def _reason(failure: Exception) -> str:
    """Why a file was not read. The grammar is the one of the Python that runs Sextant,
    so the reason names that version: a file written for a newer Python is not read."""
    running = f"read with Python {sys.version_info.major}.{sys.version_info.minor}"
    if isinstance(failure, SyntaxError):
        return f"{failure.msg} (line {failure.lineno}, {running})"
    return f"{str(failure) or type(failure).__name__} ({running})"
