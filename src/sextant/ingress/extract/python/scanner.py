"""The Python scanner backend (M03, spec 2026-11-06 §3a): reads `.py` source with the
standard library's `ast` and writes the facts the JVM scanner writes, one fact file per
source file. It never imports or runs the code it reads, and it downloads nothing.
"""

import ast
import hashlib
import json
import os
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from sextant.application.ports.detector import LibraryRoot
from sextant.application.ports.scanner import ReuseRecord, ScanReport, ScanRequest
from sextant.domain.closed_sets import OriginTier
from sextant.domain.factfile import read_document, write_fact_file
from sextant.domain.facts import Document, Fact, SymbolFact
from sextant.domain.ignorefile import IgnoreRules
from sextant.domain.symbols import NOT_APPLICABLE, PYTHON_SCHEME, bare_descriptor
from sextant.domain.version import FACT_SCHEMA_VERSION, SEXTANT_VERSION
from sextant.ingress.detect.python import is_skipped_folder
from sextant.ingress.extract.python.calls import FileContext
from sextant.ingress.extract.python.imports import ModuleIndex, module_path
from sextant.ingress.extract.python.libraries import (
    Libraries,
    record_files,
    referenced_types,
)
from sextant.ingress.extract.python.structure import file_facts
from sextant.resources import code_identity, typeshed_dir

_LANGUAGE = "python"
_SCANNER_ID = "sextant-python-scanner"
_PACKAGE_MANAGER = "pypi"
_SUFFIX = ".py"
_NO_REDACTION_HASH = "sha256:none"
# The header document's file, the JVM scanner's own name, and its path label.
_HEADER_FILE = "__type_headers__.jsonl"
_HEADER_LABEL = "<environment>"
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
        if request.origin is None:
            files = [
                (root, relative)
                for root in roots
                for relative in _python_files(root, request.ignore)
            ]
        else:
            # An opted-in library (D04 §2a) is handed its environment's `site-packages`:
            # its files are exactly the ones its `RECORD` lists, never a folder walk, so a
            # namespace folder another distribution shares gives none of the other's. The
            # detector does not hand over a library whose `RECORD` it could not read.
            listed = record_files(LibraryRoot(request.origin, request.version, request.classes_dir))
            files = [(request.classes_dir, relative) for relative in listed or ()]
        # The libraries are read from the module's own scan only: an opted-in library's
        # scan reads that library's files whole (D04 §2a).
        libraries = (
            Libraries(request.dependency_archives, typeshed_dir(), request.environment)
            if request.origin is None
            else None
        )
        index = ModuleIndex(
            frozenset(_module_paths(relative for _, relative in files)), libraries, asked=set()
        )
        manager = NOT_APPLICABLE if request.coordinates == NOT_APPLICABLE else _PACKAGE_MANAGER
        prefix = f"{PYTHON_SCHEME} {manager} {request.coordinates} {request.version} "
        documents = facts = reused = 0
        uncovered: list[str] = []
        # The library notes, each file's in file order: one line per note however many
        # files lead to it, in the order a scan of every file first meets it.
        library_notes: list[str] = []
        # The module's types, and every type its facts name: what the header read starts
        # from (D00 §5 `type_header`).
        own: set[str] = set()
        referenced: set[str] = set()
        # Only the module's own scan keeps documents (OI-325): an opted-in library's is read
        # whole into a subtree the stage discards before every run (D04 §2a).
        previous = {record.target: record for record in request.previous}
        inputs = _inputs(request, prefix, libraries) if request.origin is None else None
        records: list[ReuseRecord] = []
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
            target = f"{relative}.jsonl"
            kept = (
                _kept(previous.get(target), document, inputs, index, request.out_dir / target)
                if inputs is not None
                else None
            )
            if kept is not None:
                # The previous scan's document is what this one would write: its fact file
                # stays, and what it added to the report is added again.
                documents += 1
                reused += 1
                facts += kept.facts
                uncovered.extend(kept.notes)
                library_notes.extend(kept.library_notes)
                own.update(kept.declared)
                referenced.update(kept.referenced)
                records.append(kept.record)
                continue
            try:
                tree = ast.parse(content, filename=relative)
            except (SyntaxError, ValueError, RecursionError) as failure:
                uncovered.append(f"{relative}: not readable as Python: {_reason(failure)}")
                continue
            assert index.asked is not None
            index.asked.clear()
            if libraries is not None:
                libraries.notes = []
            context = FileContext(here, is_package, index, prefix, document.document_id)
            read = file_facts(tree, context, len(content.splitlines()) or 1)
            notes = [f"{relative}: {note}" for note in read.notes]
            uncovered.extend(notes)
            file_library_notes = list(libraries.notes) if libraries is not None else []
            library_notes.extend(file_library_notes)
            if read.not_read:
                document = document.model_copy(
                    update={"partial": True, "partial_reason": "\n".join(read.not_read)}
                )
            write_fact_file(request.out_dir / target, document, read.facts)
            documents += 1
            facts += len(read.facts)
            declared = _declared(read.facts)
            types = referenced_types(read.facts)
            if libraries is not None:
                own.update(declared)
                referenced |= types
            if inputs is not None:
                asked = sorted(index.asked)
                records.append(
                    ReuseRecord(
                        target=target,
                        key=_key(inputs, document, asked, index),
                        detail=json.dumps(
                            {
                                "asked": asked,
                                "facts": len(read.facts),
                                "notes": notes,
                                "library_notes": file_library_notes,
                                "declared": sorted(declared),
                                "referenced": sorted(types),
                            },
                            separators=(",", ":"),
                        ),
                    )
                )
        if libraries is not None:
            # After every module file, as the JVM scanner reads its classpath: the one
            # synthetic document of every library type's header. It is not a file this
            # module holds, so `documents` does not count it.
            libraries.notes = []
            document_id = hashlib.sha256(f"type-headers:{request.module_id}".encode()).hexdigest()
            headers, unlocated, not_read = libraries.headers(referenced, own, document_id)
            write_fact_file(
                request.out_dir / _HEADER_FILE,
                _header_document(request, document_id, libraries.identity, unlocated),
                list(headers),
            )
            facts += len(headers)
            uncovered.extend(dict.fromkeys([*library_notes, *libraries.notes]))
            uncovered.extend(not_read)
        return ScanReport(
            documents=documents,
            facts=facts,
            scanner_id=_SCANNER_ID,
            capabilities=tuple(sorted(_CAPABILITIES)),
            uncovered=tuple(uncovered),
            records=tuple(records),
            reused=reused,
        )


@dataclass(frozen=True)
class _Kept:
    """A previous scan's document this scan keeps, and what it added to that scan's report."""

    record: ReuseRecord
    facts: int
    notes: list[str]
    library_notes: list[str]
    declared: list[str]
    referenced: list[str]


def _inputs(request: ScanRequest, prefix: str, libraries: Libraries | None) -> str:
    """What every document of the module's own scan is read from beyond its own file: this
    reader's code and stamps, the Python that parses, the module's identity, and the
    libraries (OI-325). `.sextantignore` and the other files reach a document only through
    the module index, whose answers each document's key holds."""
    return json.dumps(
        [
            _SCANNER_ID,
            SEXTANT_VERSION,
            FACT_SCHEMA_VERSION,
            code_identity(),
            sys.version,
            request.module_id,
            prefix,
            libraries.fingerprint if libraries is not None else None,
        ]
    )


def _key(inputs: str, document: Document, asked: list[tuple[str, str]], index: ModuleIndex) -> str:
    """One document's key: the scan's inputs, its document record before it is read (the
    file's content hash, its import root and path), and the module index's answer to every
    question the file asked of it."""
    stamped = document.model_copy(update={"partial": False, "partial_reason": None})
    text = json.dumps([inputs, stamped.model_dump(mode="json"), asked, index.answers(asked)])
    return "sha256:" + hashlib.sha256(text.encode()).hexdigest()


def _kept(
    record: ReuseRecord | None,
    document: Document,
    inputs: str,
    index: ModuleIndex,
    path: Path,
) -> _Kept | None:
    """The previous scan's document for this file, where a fresh read would write the same:
    the key is the same under this scan's inputs and index, and the fact file still holds
    the document that scan wrote (D00 §2's stamps, the content hash among them)."""
    if record is None:
        return None
    try:
        detail = json.loads(record.detail)
        asked = [(str(question), str(path)) for question, path in detail["asked"]]
        kept = _Kept(
            record,
            int(detail["facts"]),
            [str(note) for note in detail["notes"]],
            [str(note) for note in detail["library_notes"]],
            [str(symbol) for symbol in detail["declared"]],
            [str(symbol) for symbol in detail["referenced"]],
        )
    except (ValueError, TypeError, KeyError):
        # A record this build cannot read — a damaged row, or one an older build wrote in
        # another shape — keeps nothing: the file is read again (OI-325 fix round 1).
        return None
    if record.key != _key(inputs, document, asked, index):
        return None
    written = read_document(path)
    if written is None or written.model_copy(
        update={"partial": False, "partial_reason": None}
    ) != document.model_copy(update={"partial": False, "partial_reason": None}):
        return None
    return kept


def _declared(facts: list[Fact]) -> set[str]:
    return {bare_descriptor(fact.symbol) for fact in facts if isinstance(fact, SymbolFact)}


def _header_document(
    request: ScanRequest, document_id: str, identity: str, unlocated: int
) -> Document:
    """The one `header_only` document (D00 §2), shaped as the JVM scanner's: the dependency
    tier, no `origin` of its own (each header names its own), and a label for a path,
    `<environment>`, because there is no file: the content hash is of what was read (the
    environment's distributions and the typeshed commit). The JVM's label is
    `<classpath>`; a Python module has an environment, not a classpath."""
    return Document(
        document_id=document_id,
        relative_path=_HEADER_LABEL,
        module_id=request.module_id,
        language=_LANGUAGE,
        sextant_version=SEXTANT_VERSION,
        fact_schema_version=FACT_SCHEMA_VERSION,
        scanner_id=_SCANNER_ID,
        content_hash="sha256:" + hashlib.sha256(identity.encode()).hexdigest(),
        origin_entry=_HEADER_LABEL,
        origin_tier=OriginTier.DEPENDENCY,
        redaction_set_hash=_NO_REDACTION_HASH,
        header_only=True,
        type_headers_unlocated=unlocated,
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
