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
from sextant.domain.ignorefile import IgnoreRules
from sextant.domain.symbols import NOT_APPLICABLE, PYTHON_SCHEME
from sextant.domain.version import FACT_SCHEMA_VERSION, SEXTANT_VERSION
from sextant.ingress.detect.python import is_skipped_folder
from sextant.ingress.extract.python.calls import FileContext
from sextant.ingress.extract.python.imports import ModuleIndex, module_path
from sextant.ingress.extract.python.structure import file_facts

_LANGUAGE = "python"
_SCANNER_ID = "sextant-python-scanner"
_PACKAGE_MANAGER = "pypi"
_SUFFIX = ".py"
_NO_REDACTION_HASH = "sha256:none"
# What this backend reads (M03 "Capabilities"). The rule 9 flow fields are written, as
# by the JVM scanner, which does not declare `control_flow` either: that capability is the
# regions a sequence diagram needs (M03 "The hard part: control flow").
_CAPABILITIES = frozenset({"typed_signatures", "annotation_args", "type_annotations", "value_ids"})


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
        files = [
            (root, relative) for root in roots for relative in _python_files(root, request.ignore)
        ]
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
            try:
                content = (root / relative).read_bytes()
            except OSError as failure:
                # A broken link, or a file this process may not read.
                uncovered.append(f"{relative}: not readable: {failure.strerror or failure}")
                continue
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
            read = file_facts(tree, context, len(content.splitlines()) or 1)
            if read.not_read:
                document = document.model_copy(
                    update={"partial": True, "partial_reason": "\n".join(read.not_read)}
                )
            write_fact_file(request.out_dir / f"{relative}.jsonl", document, read.facts)
            documents += 1
            facts += len(read.facts)
        return ScanReport(
            documents=documents,
            facts=facts,
            scanner_id=_SCANNER_ID,
            capabilities=tuple(sorted(_CAPABILITIES)),
            uncovered=tuple(uncovered),
        )


def _python_files(root: Path, ignore: IgnoreRules | None) -> list[str]:
    """Every `.py` file under `root` that `ignore` does not exclude, relative and
    `/`-separated, in sorted order. Folders are skipped by the detector's own rule. A
    git-ignored file is read: generated code (`*_pb2.py`) is often git-ignored and is
    part of the module."""
    found: list[str] = []
    for current, folders, files in os.walk(root):
        folders[:] = sorted(
            folder
            for folder in folders
            if not is_skipped_folder(current, folder)
            and not _ignored(Path(current) / folder, root, ignore)
        )
        base = Path(current).relative_to(root)
        found.extend(
            (base / name).as_posix()
            for name in sorted(files)
            if name.endswith(_SUFFIX) and not _ignored(Path(current) / name, root, ignore)
        )
    return sorted(found)


def _ignored(path: Path, root: Path, ignore: IgnoreRules | None) -> bool:
    """`.sextantignore`'s answer for `path`, matched against the repository root as
    `resource_files.list_files` matches it. A root outside the repository root is
    matched by its path from `root`, so the built-in layer still applies."""
    if ignore is None:
        return False
    repo_root = ignore.repo_root
    if path.is_relative_to(repo_root):
        return ignore.matches(path.relative_to(repo_root))
    return ignore.matches(path.relative_to(root))


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
