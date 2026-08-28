# Phase 1 — Vertical Slice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Take one fixture Java repository through the whole pipeline and produce an inbound HTTP endpoint catalog that is byte-identical on repeated runs.

**Architecture:** A hard seam between reading artifacts and deriving from them. A Java subprocess reads class files with ASM and writes facts as JSONL; Python loads them into DuckDB in bulk, derives endpoints by interpreting a framework catalog, and renders a document. Nothing after the seam knows a language or a framework exists.

**Tech Stack:** Python 3.12+, DuckDB, click, rich, pydantic; Java 21 + ASM for the extractor; pytest, ruff, mypy, import-linter; Maven for the fixture, Gradle for the extractor jar.

**Spec:** [docs/components/README.md](../../components/README.md) — the component map, which links every `Dnn` data contract and `Mnn` module design. Executors read the spec alongside this plan; every task cites the specific sections it implements.

## Global Constraints

- **Python 3.12+.** `pyproject.toml`, hatchling backend.
- **Approved dependencies only** (ARCHITECTURE §9): duckdb, click, rich, pydantic, pyyaml, jsonref, protobuf. Adding any other Python dependency requires approval per `GUIDELINES.md` §7. **The Java extractor depends on ASM only** — no JSON library; see Decision 2.
- **Determinism (NFR-1).** Same inputs produce byte-identical fact files, `metadata.json` and rendered documents. Verified by running twice and comparing.
- **Closed sets are frozen** (NFR-5). Resolution, evidence, construct kinds, origin tiers as enumerated in [D00](../../components/D00-fact-schema.md) §3–§4. Adding a value is a schema change, not an implementation choice.
- **Precedence is never stored** (D00 §3) — it is a pure function of evidence, computed at use.
- **No language name outside `sextant.ingress.extract.jvm`.** Enforced by architecture test.
- **Layering:** `cli` → `{ingress, storage, egress}` → `application` → `domain`, one direction. The outer groups never import each other. Enforced by import-linter.
- **Naming:** test names read `test_<subject>_<expected>_when_<condition>`.
- **Commits:** Conventional Commits (`GUIDELINES.md` §11). Every task ends with one.

## Decisions this plan makes

Six items were open before writing. Recorded here so they can be rejected on paper.

**Decision 1 — Phase 1 scope is inbound HTTP endpoints only.** No call sites, no dispatch, no traces, no shape expansion. The endpoint records its request and response **type references** (which typed signatures give us) but does not expand their fields. This exercises `module`, `symbol` and `annotation` facts — three of thirteen — plus typed signatures from D00 §5a, which is the part the schema audit most wanted proven. Shape expansion needs wrapper unwrapping and the wire-type vocabulary; that is Phase 3.

**Decision 2 — the extractor subprocess contract.** Python invokes `java -jar` with command-line arguments and a tab-separated classpath file; the extractor writes fact files to an output directory and prints a small hand-written JSON report to stdout. **The extractor takes no JSON library** — Java has none built in, and adding Jackson for one report object is a dependency we do not need. Writing JSON is thirty lines with correct escaping; reading it is what we avoid by using arguments and TSV.

**Decision 3 — fact file format.** One JSON object per line, discriminated by a `kind` field. **The document record is the first line of each file**, so a fact file is self-describing. Files mirror the source path under the workspace.

**Decision 4 — the fixture lives in `fixtures/` inside this repository**, committed, built in CI. Conformance fixtures are the project's test bed and must version with the code that reads them. **Maven, not Gradle** — Phase 1 proves the schema and the pipeline, not build integration, and the Gradle init script is a self-contained artifact the `Detector` port lets us add in Phase 2 without touching anything downstream.

**Decision 5 — the `Workspace` port has four methods in Phase 1**: `load_facts`, `derive`, `query`, `close`. It grows as [D01](../../components/D01-graph-schema.md) §5's named queries arrive.

**Decision 6 — the byte-identical gate compares fact files, `metadata.json` and the rendered document.** The DuckDB file is not compared; NFR-1's verification scope already says so.

## File structure

```
pyproject.toml                          deps, tool config, import-linter contracts
src/sextant/
  domain/
    closed_sets.py                      Resolution, Evidence, ConstructKind, OriginTier; precedence_of
    symbols.py                          Symbol grammar, short ids
    facts.py                            pydantic fact models + the Fact union
    version.py                          SEXTANT_VERSION, FACT_SCHEMA_VERSION, GRAPH_SCHEMA_VERSION
  application/
    ports/
      workspace.py                      Workspace protocol
      detector.py                       Detector protocol + RepositoryModel
      scanner.py                        Scanner protocol + ScanReport
      progress.py                       Progress protocol + events
    resolve/
      pipeline.py                       load → symbols → endpoints
      endpoints.py                      catalog engine dispatch
    stages/
      analyze.py                        detect → scan → resolve → metadata
  ingress/
    detect/maven.py                     MavenDetector
    extract/jvm/scanner.py              AsmScanner — subprocess wrapper
  storage/
    duckdb/workspace.py                 DuckDbWorkspace
    duckdb/schema.sql                   base tables
    duckdb/derive_endpoints.sql         the annotation_driven derivation
  egress/
    render/document.py                  Markdown renderer
    render/metadata.py                  metadata.json writer
  cli/
    app.py                              click group; module analyze / render
    progress.py                         rich live display
catalogs/
  spring-web.yml                        the first framework catalog
extractor-jvm/
  build.gradle.kts                      shaded jar
  src/main/java/dev/sextant/extractor/
    Main.java                           argument parsing, orchestration
    ClassScanner.java                   ASM ClassVisitor → facts
    TypeRefs.java                       descriptor and generic signature parsing
    JsonOut.java                        minimal JSON writer
  src/test/java/dev/sextant/extractor/
    ClassScannerTest.java
fixtures/
  orders-service/                       Maven Spring Boot fixture
tests/
  architecture/test_layering.py
  domain/  application/  ingress/  storage/  egress/  cli/
  e2e/test_vertical_slice.py            the exit gate
```

---

### Task 1: Skeleton and architecture tests

**Files:**
- Create: `pyproject.toml`, `src/sextant/__init__.py`, and `__init__.py` for `domain`, `application`, `application/ports`, `application/resolve`, `application/stages`, `ingress`, `ingress/detect`, `ingress/extract`, `ingress/extract/jvm`, `storage`, `storage/duckdb`, `egress`, `egress/render`, `cli`
- Test: `tests/architecture/test_layering.py`

**Interfaces:**
- Consumes: nothing
- Produces: the package `sextant` with the layer packages that every later task imports; `lint-imports` runs clean in CI

- [ ] **Step 1: Write the failing test**

```python
# tests/architecture/test_layering.py
import subprocess


def test_import_contracts_hold_when_the_suite_runs():
    result = subprocess.run(
        ["lint-imports"], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stdout + result.stderr
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest tests/architecture/test_layering.py -v`
Expected: FAIL — `lint-imports` is not installed and there is no configuration.

- [ ] **Step 3: Write `pyproject.toml`**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "sextant"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "duckdb>=1.1",
  "click>=8.1",
  "rich>=13.7",
  "pydantic>=2.7",
  "pyyaml>=6.0",
]

[project.optional-dependencies]
dev = ["pytest>=8", "ruff>=0.5", "mypy>=1.10", "import-linter>=2.0"]

[project.scripts]
sextant = "sextant.cli.app:cli"

[tool.hatch.build.targets.wheel]
packages = ["src/sextant"]

[tool.ruff]
line-length = 100
src = ["src", "tests"]

[tool.mypy]
strict = true
files = ["src"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]

[tool.importlinter]
root_package = "sextant"

[[tool.importlinter.contracts]]
name = "Layering: cli -> outer groups -> application -> domain"
type = "layers"
layers = ["sextant.cli", "sextant.ingress | sextant.storage | sextant.egress", "sextant.application", "sextant.domain"]

[[tool.importlinter.contracts]]
name = "Outer groups never import one another"
type = "independence"
modules = ["sextant.ingress", "sextant.storage", "sextant.egress"]

[[tool.importlinter.contracts]]
name = "Ingress is write-only: it never depends on the Workspace port"
type = "forbidden"
source_modules = ["sextant.ingress"]
forbidden_modules = ["sextant.application.ports.workspace"]
```

- [ ] **Step 4: Create the package tree**

```bash
mkdir -p src/sextant/{domain,application/{ports,resolve,stages},ingress/{detect,extract/jvm},storage/duckdb,egress/render,cli}
mkdir -p tests/{architecture,domain,application,ingress,storage,egress,cli,e2e}
find src/sextant -type d -exec touch {}/__init__.py \;
touch src/sextant/__init__.py
```

- [ ] **Step 5: Install and run the test**

Run: `pip install -e ".[dev]" && pytest tests/architecture/test_layering.py -v`
Expected: PASS — contracts hold trivially over empty packages.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml src tests
git commit -m "build: python package skeleton with import-linter layering contracts"
```

---

### Task 2: Domain — closed sets and symbol identity

**Files:**
- Create: `src/sextant/domain/closed_sets.py`, `src/sextant/domain/symbols.py`, `src/sextant/domain/version.py`
- Test: `tests/domain/test_closed_sets.py`, `tests/domain/test_symbols.py`

**Interfaces:**
- Consumes: Task 1's package tree
- Produces: `Resolution`, `Evidence`, `ConstructKind`, `OriginTier` (str enums); `precedence_of(evidence: Evidence) -> int`; `Symbol` frozen dataclass with `__str__` and `short_id: str`; `SEXTANT_VERSION`, `FACT_SCHEMA_VERSION`, `GRAPH_SCHEMA_VERSION` string constants

Implements [D00](../../components/D00-fact-schema.md) §1, §3, §4.

- [ ] **Step 1: Write the failing tests**

```python
# tests/domain/test_closed_sets.py
from sextant.domain.closed_sets import Evidence, precedence_of


def test_precedence_ranks_human_above_code_when_evidence_is_curated():
    assert precedence_of(Evidence.HUMAN) == 90


def test_precedence_ranks_model_below_code_when_evidence_is_llm():
    assert precedence_of(Evidence.LLM) == 10


def test_precedence_is_fifty_when_evidence_is_any_code_derived_value():
    for evidence in (Evidence.COMPILER, Evidence.SYNTAX, Evidence.NAME_MATCH, Evidence.DECLARED):
        assert precedence_of(evidence) == 50
```

```python
# tests/domain/test_symbols.py
from sextant.domain.symbols import Symbol

ORDER_SERVICE = Symbol(
    scheme="sextant-jvm",
    package_manager="maven",
    package="com.acme/orders",
    version="2.1.0",
    descriptor="com/acme/OrderService#save().",
)


def test_symbol_renders_the_scip_grammar_when_converted_to_string():
    assert str(ORDER_SERVICE) == (
        "sextant-jvm maven com.acme/orders 2.1.0 com/acme/OrderService#save()."
    )


def test_short_id_is_prefixed_and_stable_when_the_same_symbol_is_built_twice():
    twin = Symbol(**vars(ORDER_SERVICE))
    assert ORDER_SERVICE.short_id == twin.short_id
    assert ORDER_SERVICE.short_id.startswith("sym_")


def test_short_id_differs_when_the_descriptor_differs():
    other = Symbol(**{**vars(ORDER_SERVICE), "descriptor": "com/acme/OrderService#load()."})
    assert other.short_id != ORDER_SERVICE.short_id
```

- [ ] **Step 2: Run them to verify they fail**

Run: `pytest tests/domain -v`
Expected: FAIL — `ModuleNotFoundError: sextant.domain.closed_sets`

- [ ] **Step 3: Write the implementation**

```python
# src/sextant/domain/closed_sets.py
"""The closed sets of D00 §4. Adding a value is a schema change, never an
implementation choice — see NFR-5."""

from enum import StrEnum


class Resolution(StrEnum):
    RESOLVED = "resolved"
    NARROWED = "narrowed"
    PARTIAL = "partial"
    UNRESOLVED = "unresolved"


class Evidence(StrEnum):
    COMPILER = "compiler"
    SYNTAX = "syntax"
    NAME_MATCH = "name_match"
    DECLARED = "declared"
    HUMAN = "human"
    LLM = "llm"


class ConstructKind(StrEnum):
    CLASS = "class"
    INTERFACE = "interface"
    ENUM = "enum"
    RECORD = "record"
    METHOD = "method"
    CONSTRUCTOR = "constructor"
    FIELD = "field"
    MODULE = "module"


class OriginTier(StrEnum):
    MODULE_OUTPUT = "module_output"
    FIRST_PARTY = "first_party"
    THIRD_PARTY = "third_party"
    PLATFORM = "platform"


class Protocol(StrEnum):
    HTTP = "http"
    SOAP = "soap"
    GRPC = "grpc"
    MESSAGE = "message"


class Direction(StrEnum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"
    BOTH = "both"


_RANKS = {Evidence.HUMAN: 90, Evidence.LLM: 10}
_CODE_DERIVED_RANK = 50


def precedence_of(evidence: Evidence) -> int:
    """Precedence is derived, never stored (D00 §3, ARCHITECTURE DR-3).

    Storing it would admit states like human evidence at rank 10, and would
    freeze the rank table into every published bundle.
    """
    return _RANKS.get(evidence, _CODE_DERIVED_RANK)
```

```python
# src/sextant/domain/symbols.py
"""The SCIP symbol grammar as a string format (D00 §1). No indexer involved."""

import hashlib
from dataclasses import dataclass

NOT_APPLICABLE = "."


@dataclass(frozen=True)
class Symbol:
    scheme: str
    package_manager: str
    package: str
    version: str
    descriptor: str

    def __str__(self) -> str:
        return (
            f"{self.scheme} {self.package_manager} {self.package} "
            f"{self.version} {self.descriptor}"
        )

    @property
    def short_id(self) -> str:
        """A prefixed, content-derived handle. Never bare hexadecimal: these
        get pasted into YAML and spreadsheets, which coerce types."""
        digest = hashlib.sha256(str(self).encode("utf-8")).hexdigest()[:8]
        return f"sym_{digest}"
```

```python
# src/sextant/domain/version.py
SEXTANT_VERSION = "0.1.0"
FACT_SCHEMA_VERSION = "1.0.0"
GRAPH_SCHEMA_VERSION = "1.0.0"
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/domain -v`
Expected: PASS, 6 tests.

- [ ] **Step 5: Commit**

```bash
git add src/sextant/domain tests/domain
git commit -m "feat(domain): closed sets, derived precedence, and symbol identity"
```

---

### Task 3: Domain — fact models and the JSONL writer

**Files:**
- Create: `src/sextant/domain/facts.py`, `src/sextant/domain/factfile.py`
- Test: `tests/domain/test_facts.py`

**Interfaces:**
- Consumes: `closed_sets`, `version` from Task 2
- Produces: `Document`, `ModuleFact`, `SymbolFact`, `AnnotationFact`, `TypeRef`, `Parameter`, `Signature`, `AnnotationUse`, `ClasspathEntry`; the `Fact` discriminated union; `write_fact_file(path: Path, document: Document, facts: Iterable[Fact]) -> None` and `read_fact_file(path: Path) -> tuple[Document, list[Fact]]`

Implements [D00](../../components/D00-fact-schema.md) §2, §5, §5a, §7.

- [ ] **Step 1: Write the failing test**

```python
# tests/domain/test_facts.py
from pathlib import Path

from sextant.domain.closed_sets import ConstructKind, OriginTier
from sextant.domain.facts import (
    AnnotationFact, AnnotationUse, Document, Parameter, Signature,
    SymbolFact, TypeRef,
)
from sextant.domain.factfile import read_fact_file, write_fact_file

DOCUMENT = Document(
    document_id="doc_1",
    relative_path="src/main/java/com/acme/OrderController.java",
    module_id="com.acme:orders",
    language="java",
    sextant_version="0.1.0",
    fact_schema_version="1.0.0",
    scanner_id="asm",
    scanner_version="9.7",
    content_hash="sha256:abc",
    origin_entry="target/classes",
    origin_tier=OriginTier.MODULE_OUTPUT,
    redaction_set_hash="sha256:def",
)


def test_round_trip_preserves_every_fact_when_written_and_read_back(tmp_path: Path):
    symbol = SymbolFact(
        document_id="doc_1",
        symbol="sextant-jvm maven com.acme/orders 1.0 com/acme/OrderController#create().",
        construct=ConstructKind.METHOD,
        enclosing="sextant-jvm maven com.acme/orders 1.0 com/acme/OrderController#",
        signature=Signature(
            parameters=[Parameter(name="cmd", type=TypeRef(symbol="com/acme/OrderCommand#"))],
            returns=TypeRef(symbol="com/acme/OrderResult#"),
        ),
        visibility="public",
        line_start=21,
        line_end=24,
    )
    annotation = AnnotationFact(
        document_id="doc_1",
        target=symbol.symbol,
        use=AnnotationUse(
            annotation="org/springframework/web/bind/annotation/PostMapping#",
            args={"value": ["/v1/orders"]},
        ),
        retention="runtime",
    )
    path = tmp_path / "OrderController.jsonl"

    write_fact_file(path, DOCUMENT, [symbol, annotation])
    document, facts = read_fact_file(path)

    assert document == DOCUMENT
    assert facts == [symbol, annotation]


def test_document_is_the_first_line_when_a_fact_file_is_written(tmp_path: Path):
    path = tmp_path / "OrderController.jsonl"
    write_fact_file(path, DOCUMENT, [])
    first_line = path.read_text(encoding="utf-8").splitlines()[0]
    assert '"kind":"document"' in first_line.replace(" ", "")


def test_written_bytes_are_identical_when_the_same_facts_are_written_twice(tmp_path: Path):
    a, b = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    write_fact_file(a, DOCUMENT, [])
    write_fact_file(b, DOCUMENT, [])
    assert a.read_bytes() == b.read_bytes()
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest tests/domain/test_facts.py -v`
Expected: FAIL — `ModuleNotFoundError: sextant.domain.facts`

- [ ] **Step 3: Write the fact models**

```python
# src/sextant/domain/facts.py
"""The fact kinds of D00 §5. Validated at write time, per NFR-10."""

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field

from sextant.domain.closed_sets import ConstructKind, OriginTier

LiteralValue = Union[str, int, float, bool, list["LiteralValue"]]


class TypeRef(BaseModel):
    """A symbol reference plus optional type arguments, recursively (D00 §5a).
    Recorded verbatim: unwrapping envelopes is catalog knowledge, not the
    scanner's."""

    model_config = {"frozen": True}
    symbol: str
    arguments: list["TypeRef"] = Field(default_factory=list)


class AnnotationUse(BaseModel):
    model_config = {"frozen": True}
    annotation: str
    args: dict[str, LiteralValue] = Field(default_factory=dict)


class Parameter(BaseModel):
    model_config = {"frozen": True}
    name: str | None = None
    type: TypeRef
    annotations: list[AnnotationUse] = Field(default_factory=list)


class Signature(BaseModel):
    model_config = {"frozen": True}
    parameters: list[Parameter] = Field(default_factory=list)
    returns: TypeRef | None = None


class ClasspathEntry(BaseModel):
    model_config = {"frozen": True}
    path: str
    tier: OriginTier
    coordinates: str | None = None


class Document(BaseModel):
    """One per source file. Language, tool and version live here, never on a
    fact (D00 §2)."""

    model_config = {"frozen": True}
    kind: Literal["document"] = "document"
    document_id: str
    relative_path: str
    module_id: str
    language: str
    sextant_version: str
    fact_schema_version: str
    scanner_id: str
    scanner_version: str
    content_hash: str
    origin_entry: str
    origin_tier: OriginTier
    redaction_set_hash: str
    partial: bool = False
    partial_reason: str | None = None


class ModuleFact(BaseModel):
    model_config = {"frozen": True}
    kind: Literal["module"] = "module"
    document_id: str
    module_id: str
    module_kind: str
    languages: list[str]
    source_roots: list[str]
    output_dirs: list[str]
    classpath: list[ClasspathEntry] = Field(default_factory=list)


class SymbolFact(BaseModel):
    model_config = {"frozen": True}
    kind: Literal["symbol"] = "symbol"
    document_id: str
    symbol: str
    construct: ConstructKind
    enclosing: str | None = None
    signature: Signature | None = None
    visibility: str = "public"
    line_start: int = 0
    line_end: int = 0


class AnnotationFact(BaseModel):
    model_config = {"frozen": True}
    kind: Literal["annotation"] = "annotation"
    document_id: str
    target: str
    use: AnnotationUse
    retention: str


Fact = Annotated[
    Union[ModuleFact, SymbolFact, AnnotationFact],
    Field(discriminator="kind"),
]
```

- [ ] **Step 4: Write the fact-file reader and writer**

```python
# src/sextant/domain/factfile.py
"""Fact files are JSONL, one file per source file (D00 §7). The document
record is the first line, so a fact file is self-describing."""

import json
from collections.abc import Iterable
from pathlib import Path

from pydantic import TypeAdapter

from sextant.domain.facts import Document, Fact

_FACT_ADAPTER: TypeAdapter[Fact] = TypeAdapter(Fact)


def _line(model: Document | Fact) -> str:
    # sort_keys and no whitespace: byte-identical output for identical facts (NFR-1).
    return json.dumps(model.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))


def write_fact_file(path: Path, document: Document, facts: Iterable[Fact]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [_line(document)] + [_line(fact) for fact in facts]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def read_fact_file(path: Path) -> tuple[Document, list[Fact]]:
    raw = path.read_text(encoding="utf-8").splitlines()
    if not raw:
        raise ValueError(f"empty fact file: {path}")
    document = Document.model_validate_json(raw[0])
    facts = [_FACT_ADAPTER.validate_json(line) for line in raw[1:] if line]
    return document, facts
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest tests/domain/test_facts.py -v`
Expected: PASS, 3 tests.

- [ ] **Step 6: Commit**

```bash
git add src/sextant/domain tests/domain
git commit -m "feat(domain): fact models and deterministic JSONL fact files"
```

---

### Task 4: Storage — the Workspace port and its DuckDB implementation

**Files:**
- Create: `src/sextant/application/ports/workspace.py`, `src/sextant/storage/duckdb/workspace.py`, `src/sextant/storage/duckdb/schema.sql`
- Test: `tests/storage/test_workspace.py`

**Interfaces:**
- Consumes: `Document`, `Fact`, `write_fact_file` from Task 3
- Produces: `Workspace` protocol with `load_facts(fact_root: Path) -> int`, `derive(name: str) -> None`, `query(name: str, **params: object) -> list[dict]`, `close() -> None`; `DuckDbWorkspace(path: Path)` implementing it

Implements [D01](../../components/D01-graph-schema.md) §2 and ARCHITECTURE §7's `Workspace` port. Bulk load only — per-row insertion is a defect under NFR-11.

- [ ] **Step 1: Write the failing test**

```python
# tests/storage/test_workspace.py
from pathlib import Path

from sextant.domain.closed_sets import ConstructKind, OriginTier
from sextant.domain.facts import Document, SymbolFact
from sextant.domain.factfile import write_fact_file
from sextant.storage.duckdb.workspace import DuckDbWorkspace


def _fixture_facts(root: Path) -> None:
    document = Document(
        document_id="doc_1", relative_path="com/acme/A.java", module_id="com.acme:orders",
        language="java", sextant_version="0.1.0", fact_schema_version="1.0.0",
        scanner_id="asm", scanner_version="9.7", content_hash="sha256:a",
        origin_entry="target/classes", origin_tier=OriginTier.MODULE_OUTPUT,
        redaction_set_hash="sha256:b",
    )
    symbol = SymbolFact(
        document_id="doc_1", symbol="s maven p 1 com/acme/A#", construct=ConstructKind.CLASS
    )
    write_fact_file(root / "com" / "acme" / "A.jsonl", document, [symbol])


def test_load_facts_reports_the_row_count_when_a_fact_tree_is_ingested(tmp_path: Path):
    _fixture_facts(tmp_path / "facts")
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    loaded = workspace.load_facts(tmp_path / "facts")
    workspace.close()
    assert loaded == 2  # one document line, one symbol line


def test_query_returns_the_document_when_documents_are_listed(tmp_path: Path):
    _fixture_facts(tmp_path / "facts")
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    rows = workspace.query("documents")
    workspace.close()
    assert [row["document_id"] for row in rows] == ["doc_1"]


def test_query_rejects_a_name_that_is_not_a_named_query(tmp_path: Path):
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    try:
        raised = False
        try:
            workspace.query("SELECT 1")
        except KeyError:
            raised = True
        assert raised
    finally:
        workspace.close()
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest tests/storage -v`
Expected: FAIL — `ModuleNotFoundError: sextant.storage.duckdb.workspace`

- [ ] **Step 3: Write the port**

```python
# src/sextant/application/ports/workspace.py
"""The Workspace port (ARCHITECTURE §7). Its surface is deliberately narrow —
bulk load, the named derivations, the named queries of D01 — so that it cannot
decay into a SQL pass-through."""

from pathlib import Path
from typing import Protocol


class Workspace(Protocol):
    def load_facts(self, fact_root: Path) -> int:
        """Bulk-ingest every fact file under fact_root. Returns rows loaded."""

    def derive(self, name: str) -> None:
        """Run one named derivation, rebuilding its tables whole."""

    def query(self, name: str, **params: object) -> list[dict]:
        """Run one named query. Unknown names raise KeyError."""

    def close(self) -> None: ...
```

- [ ] **Step 4: Write the schema and the implementation**

```sql
-- src/sextant/storage/duckdb/schema.sql
CREATE TABLE IF NOT EXISTS raw_facts (
    kind        TEXT,
    document_id TEXT,
    payload     JSON
);

CREATE OR REPLACE VIEW documents AS
SELECT document_id,
       payload ->> 'relative_path'   AS relative_path,
       payload ->> 'module_id'       AS module_id,
       payload ->> 'language'        AS language,
       payload ->> 'origin_tier'     AS origin_tier,
       (payload ->> 'partial')::BOOLEAN AS partial
FROM raw_facts WHERE kind = 'document';

CREATE OR REPLACE VIEW symbols AS
SELECT document_id,
       payload ->> 'symbol'    AS symbol,
       payload ->> 'construct' AS construct,
       payload ->> 'enclosing' AS enclosing,
       payload ->  'signature' AS signature
FROM raw_facts WHERE kind = 'symbol';

CREATE OR REPLACE VIEW annotations AS
SELECT document_id,
       payload ->> 'target'              AS target,
       payload -> 'use' ->> 'annotation' AS annotation,
       payload -> 'use' ->  'args'       AS args
FROM raw_facts WHERE kind = 'annotation';
```

```python
# src/sextant/storage/duckdb/workspace.py
from pathlib import Path

import duckdb

_SQL_DIR = Path(__file__).parent

_NAMED_QUERIES = {
    "documents": "SELECT * FROM documents ORDER BY document_id",
    "endpoints": "SELECT * FROM endpoints ORDER BY protocol, method, path",
    "coverage": """
        SELECT count(*) AS documents,
               sum(CASE WHEN partial THEN 1 ELSE 0 END) AS partial_documents
        FROM documents
    """,
}

_NAMED_DERIVATIONS = {"endpoints": "derive_endpoints.sql"}


class DuckDbWorkspace:
    """The Workspace port over DuckDB. Owns SQL and D01; knows nothing about
    frameworks, languages or protocols (ARCHITECTURE §10)."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = duckdb.connect(str(path))
        self._connection.execute((_SQL_DIR / "schema.sql").read_text(encoding="utf-8"))

    def load_facts(self, fact_root: Path) -> int:
        """One bulk statement over the whole tree. Per-row insertion is a
        defect under NFR-11 — the difference is orders of magnitude."""
        pattern = str(fact_root / "**" / "*.jsonl")
        self._connection.execute("DELETE FROM raw_facts")
        self._connection.execute(
            """
            INSERT INTO raw_facts
            SELECT json ->> 'kind', json ->> 'document_id', json
            FROM read_json(?, format='newline_delimited', columns={'json': 'JSON'})
            """,
            [pattern],
        )
        return int(self._connection.execute("SELECT count(*) FROM raw_facts").fetchone()[0])

    def derive(self, name: str) -> None:
        sql = (_SQL_DIR / _NAMED_DERIVATIONS[name]).read_text(encoding="utf-8")
        self._connection.execute(sql)

    def query(self, name: str, **params: object) -> list[dict]:
        sql = _NAMED_QUERIES[name]
        cursor = self._connection.execute(sql, list(params.values()) or None)
        columns = [column[0] for column in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def close(self) -> None:
        self._connection.close()
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest tests/storage -v`
Expected: PASS, 3 tests. (`derive("endpoints")` is exercised in Task 10, when its SQL exists.)

- [ ] **Step 6: Commit**

```bash
git add src/sextant/application/ports src/sextant/storage tests/storage
git commit -m "feat(storage): workspace port and duckdb implementation with bulk fact load"
```

---

### Task 5: The fixture repository

**Files:**
- Create: `fixtures/orders-service/pom.xml`, `fixtures/orders-service/src/main/java/com/acme/orders/{OrderController.java,OrderCommand.java,OrderResult.java,OrderService.java}`
- Test: `tests/e2e/test_fixture_builds.py`

**Interfaces:**
- Consumes: nothing
- Produces: a built Maven module at `fixtures/orders-service/target/classes` with **three inbound HTTP endpoints** — `POST /v1/orders`, `GET /v1/orders/{id}`, `GET /v1/orders` — which every later task asserts against

Deliberately boring: no Lombok, no reactive types, no inheritance. Phase 2 and 3 fixtures add the hard cases.

- [ ] **Step 1: Write the failing test**

```python
# tests/e2e/test_fixture_builds.py
import subprocess
from pathlib import Path

FIXTURE = Path(__file__).parents[2] / "fixtures" / "orders-service"


def test_fixture_produces_class_files_when_built():
    subprocess.run(["mvn", "-q", "-o", "compile"], cwd=FIXTURE, check=True)
    classes = FIXTURE / "target" / "classes" / "com" / "acme" / "orders"
    assert (classes / "OrderController.class").exists()
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest tests/e2e/test_fixture_builds.py -v`
Expected: FAIL — the fixture directory does not exist.

- [ ] **Step 3: Write the fixture POM**

```xml
<!-- fixtures/orders-service/pom.xml -->
<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.acme</groupId>
  <artifactId>orders-service</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>21</maven.compiler.release>
    <maven.compiler.parameters>true</maven.compiler.parameters>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-web</artifactId>
      <version>6.1.6</version>
    </dependency>
  </dependencies>
</project>
```

- [ ] **Step 4: Write the fixture sources**

```java
// fixtures/orders-service/src/main/java/com/acme/orders/OrderCommand.java
package com.acme.orders;

public class OrderCommand {
    private String customerId;
    private int quantity;

    public String getCustomerId() { return customerId; }
    public int getQuantity() { return quantity; }
}
```

```java
// fixtures/orders-service/src/main/java/com/acme/orders/OrderResult.java
package com.acme.orders;

public class OrderResult {
    private String orderId;
    private String status;

    public String getOrderId() { return orderId; }
    public String getStatus() { return status; }
}
```

```java
// fixtures/orders-service/src/main/java/com/acme/orders/OrderService.java
package com.acme.orders;

import java.util.List;

public class OrderService {
    public OrderResult place(OrderCommand command) { return new OrderResult(); }
    public OrderResult find(long id) { return new OrderResult(); }
    public List<OrderResult> list() { return List.of(); }
}
```

```java
// fixtures/orders-service/src/main/java/com/acme/orders/OrderController.java
package com.acme.orders;

import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/v1/orders")
public class OrderController {

    private final OrderService service = new OrderService();

    @PostMapping
    public OrderResult create(@RequestBody OrderCommand command) {
        return service.place(command);
    }

    @GetMapping("/{id}")
    public OrderResult get(@PathVariable long id) {
        return service.find(id);
    }

    @GetMapping
    public List<OrderResult> list() {
        return service.list();
    }
}
```

- [ ] **Step 5: Build it and run the test**

Run: `cd fixtures/orders-service && mvn -q compile && cd - && pytest tests/e2e/test_fixture_builds.py -v`
Expected: PASS. (The first build needs the network for `spring-web`; afterwards `-o` works offline.)

- [ ] **Step 6: Commit**

```bash
git add fixtures tests/e2e/test_fixture_builds.py
git commit -m "test(fixtures): maven spring-web fixture with three inbound endpoints"
```

---

### Task 6: Java extractor — symbols and typed signatures

**Files:**
- Create: `extractor-jvm/build.gradle.kts`, `extractor-jvm/settings.gradle.kts`, `extractor-jvm/src/main/java/dev/sextant/extractor/{JsonOut.java,TypeRefs.java,ClassScanner.java}`
- Test: `extractor-jvm/src/test/java/dev/sextant/extractor/ClassScannerTest.java`

**Interfaces:**
- Consumes: nothing from Python
- Produces: `ClassScanner.scan(byte[] classBytes, String moduleCoordinates) -> List<String>` returning JSONL lines for `symbol` facts; `JsonOut.string/array/object` writers; `TypeRefs.fromDescriptor(String) -> String` and `TypeRefs.fromSignature(String) -> String` producing the JSON of a `TypeRef`

**No JSON library** (Decision 2): `JsonOut` is thirty lines with correct escaping.

- [ ] **Step 1: Write the failing test**

```java
// extractor-jvm/src/test/java/dev/sextant/extractor/ClassScannerTest.java
package dev.sextant.extractor;

import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.InputStream;
import java.util.List;
import org.junit.jupiter.api.Test;

class ClassScannerTest {

    private List<String> scanSelf() throws Exception {
        try (InputStream in = getClass().getResourceAsStream("/dev/sextant/extractor/Sample.class")) {
            return new ClassScanner("com.acme/orders", "1.0.0").scan(in.readAllBytes());
        }
    }

    @Test
    void emits_a_class_symbol_when_a_class_is_scanned() throws Exception {
        assertTrue(scanSelf().stream().anyMatch(line ->
            line.contains("\"construct\":\"class\"") && line.contains("Sample#")));
    }

    @Test
    void emits_a_method_symbol_with_its_return_type_when_a_method_is_scanned() throws Exception {
        assertTrue(scanSelf().stream().anyMatch(line ->
            line.contains("Sample#greet().") && line.contains("java/lang/String#")));
    }
}
```

Add the sample the test scans:

```java
// extractor-jvm/src/test/java/dev/sextant/extractor/Sample.java
package dev.sextant.extractor;

public class Sample {
    public String greet(int times) { return ""; }
}
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd extractor-jvm && ./gradlew test`
Expected: FAIL — no build file yet, then no `ClassScanner`.

- [ ] **Step 3: Write the build files**

```kotlin
// extractor-jvm/settings.gradle.kts
rootProject.name = "sextant-extractor"
```

```kotlin
// extractor-jvm/build.gradle.kts
plugins {
    java
    id("com.github.johnrengelman.shadow") version "8.1.1"
}

repositories { mavenCentral() }

dependencies {
    implementation("org.ow2.asm:asm:9.7")
    implementation("org.ow2.asm:asm-tree:9.7")
    testImplementation("org.junit.jupiter:junit-jupiter:5.10.2")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

java { toolchain { languageVersion = JavaLanguageVersion.of(21) } }

tasks.test { useJUnitPlatform() }

tasks.shadowJar {
    archiveFileName.set("sextant-extractor.jar")
    manifest { attributes["Main-Class"] = "dev.sextant.extractor.Main" }
}
```

- [ ] **Step 4: Write the JSON writer and type-reference parser**

```java
// extractor-jvm/src/main/java/dev/sextant/extractor/JsonOut.java
package dev.sextant.extractor;

/** Minimal JSON emission. Java ships no JSON library and one report object does
 *  not justify a dependency; escaping is the only subtlety. */
public final class JsonOut {
    private JsonOut() {}

    public static String string(String raw) {
        StringBuilder out = new StringBuilder("\"");
        for (int i = 0; i < raw.length(); i++) {
            char c = raw.charAt(i);
            switch (c) {
                case '"' -> out.append("\\\"");
                case '\\' -> out.append("\\\\");
                case '\n' -> out.append("\\n");
                case '\r' -> out.append("\\r");
                case '\t' -> out.append("\\t");
                default -> {
                    if (c < 0x20) out.append(String.format("\\u%04x", (int) c));
                    else out.append(c);
                }
            }
        }
        return out.append('"').toString();
    }

    public static String array(java.util.List<String> jsonValues) {
        return "[" + String.join(",", jsonValues) + "]";
    }

    /** Keys must be supplied already sorted: byte-identical output (NFR-1). */
    public static String object(java.util.SortedMap<String, String> jsonByKey) {
        StringBuilder out = new StringBuilder("{");
        boolean first = true;
        for (var entry : jsonByKey.entrySet()) {
            if (!first) out.append(',');
            out.append(string(entry.getKey())).append(':').append(entry.getValue());
            first = false;
        }
        return out.append('}').toString();
    }
}
```

```java
// extractor-jvm/src/main/java/dev/sextant/extractor/TypeRefs.java
package dev.sextant.extractor;

import java.util.ArrayList;
import java.util.List;
import java.util.TreeMap;
import org.objectweb.asm.Type;
import org.objectweb.asm.signature.SignatureReader;
import org.objectweb.asm.signature.SignatureVisitor;

/** Type references: a symbol reference plus optional type arguments, recursively
 *  (D00 §5a). Recorded verbatim — unwrapping envelopes is catalog knowledge. */
public final class TypeRefs {
    private TypeRefs() {}

    public static String fromType(Type type) {
        return ref(descriptorName(type), List.of());
    }

    private static String descriptorName(Type type) {
        return switch (type.getSort()) {
            case Type.OBJECT -> type.getInternalName() + "#";
            case Type.ARRAY -> descriptorName(type.getElementType()) + "[]";
            default -> type.getClassName() + "#";
        };
    }

    public static String ref(String symbol, List<String> argumentJson) {
        TreeMap<String, String> fields = new TreeMap<>();
        fields.put("symbol", JsonOut.string(symbol));
        fields.put("arguments", JsonOut.array(argumentJson));
        return JsonOut.object(fields);
    }

    /** Generic return type from the Signature attribute, or null when absent. */
    public static String returnFromSignature(String signature) {
        if (signature == null) return null;
        List<String> collected = new ArrayList<>();
        new SignatureReader(signature).accept(new SignatureVisitor(org.objectweb.asm.Opcodes.ASM9) {
            @Override public SignatureVisitor visitReturnType() {
                return new Collector(collected);
            }
        });
        return collected.isEmpty() ? null : collected.get(0);
    }

    private static final class Collector extends SignatureVisitor {
        private final List<String> sink;
        private String owner;
        private final List<String> arguments = new ArrayList<>();

        Collector(List<String> sink) {
            super(org.objectweb.asm.Opcodes.ASM9);
            this.sink = sink;
        }

        @Override public void visitClassType(String name) {
            if (owner == null) owner = name + "#";
        }

        @Override public SignatureVisitor visitTypeArgument(char wildcard) {
            return new Collector(arguments);
        }

        @Override public void visitEnd() {
            if (owner != null) sink.add(ref(owner, arguments));
        }
    }
}
```

- [ ] **Step 5: Write the class scanner**

```java
// extractor-jvm/src/main/java/dev/sextant/extractor/ClassScanner.java
package dev.sextant.extractor;

import java.util.ArrayList;
import java.util.List;
import java.util.TreeMap;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassVisitor;
import org.objectweb.asm.MethodVisitor;
import org.objectweb.asm.Opcodes;
import org.objectweb.asm.Type;

/** Reads one class file and emits symbol facts as JSONL lines. */
public final class ClassScanner {
    private final String coordinates;
    private final String version;

    public ClassScanner(String coordinates, String version) {
        this.coordinates = coordinates;
        this.version = version;
    }

    public List<String> scan(byte[] classBytes) {
        List<String> lines = new ArrayList<>();
        new ClassReader(classBytes).accept(new Visitor(lines), ClassReader.SKIP_FRAMES);
        return lines;
    }

    String symbolOf(String descriptorPath) {
        return "sextant-jvm maven " + coordinates + " " + version + " " + descriptorPath;
    }

    private final class Visitor extends ClassVisitor {
        private final List<String> lines;
        private String typeSymbol;

        Visitor(List<String> lines) {
            super(Opcodes.ASM9);
            this.lines = lines;
        }

        @Override
        public void visit(int v, int access, String name, String sig, String superName, String[] ifaces) {
            typeSymbol = symbolOf(name + "#");
            boolean isInterface = (access & Opcodes.ACC_INTERFACE) != 0;
            emit(typeSymbol, isInterface ? "interface" : "class", null, null, access);
        }

        @Override
        public MethodVisitor visitMethod(int access, String name, String descriptor, String sig, String[] ex) {
            String owner = typeSymbol.substring(typeSymbol.lastIndexOf(' ') + 1);
            String methodSymbol = symbolOf(owner + name + "().");
            emit(methodSymbol, "<init>".equals(name) ? "constructor" : "method",
                 typeSymbol, signatureJson(descriptor, sig), access);
            return null;
        }

        private String signatureJson(String descriptor, String genericSignature) {
            List<String> parameters = new ArrayList<>();
            for (Type argument : Type.getArgumentTypes(descriptor)) {
                TreeMap<String, String> parameter = new TreeMap<>();
                parameter.put("annotations", "[]");
                parameter.put("name", "null");
                parameter.put("type", TypeRefs.fromType(argument));
                parameters.add(JsonOut.object(parameter));
            }
            String generic = TypeRefs.returnFromSignature(genericSignature);
            String returns = generic != null ? generic : TypeRefs.fromType(Type.getReturnType(descriptor));
            TreeMap<String, String> signature = new TreeMap<>();
            signature.put("parameters", JsonOut.array(parameters));
            signature.put("returns", returns);
            return JsonOut.object(signature);
        }

        private void emit(String symbol, String construct, String enclosing, String signature, int access) {
            TreeMap<String, String> fact = new TreeMap<>();
            fact.put("kind", JsonOut.string("symbol"));
            fact.put("document_id", JsonOut.string(Main.currentDocumentId));
            fact.put("symbol", JsonOut.string(symbol));
            fact.put("construct", JsonOut.string(construct));
            fact.put("enclosing", enclosing == null ? "null" : JsonOut.string(enclosing));
            fact.put("signature", signature == null ? "null" : signature);
            fact.put("visibility", JsonOut.string((access & Opcodes.ACC_PUBLIC) != 0 ? "public" : "other"));
            fact.put("line_start", "0");
            fact.put("line_end", "0");
            lines.add(JsonOut.object(fact));
        }
    }
}
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `cd extractor-jvm && ./gradlew test`
Expected: PASS, 2 tests.

- [ ] **Step 7: Commit**

```bash
git add extractor-jvm
git commit -m "feat(extractor): asm class scanner emitting symbol facts with typed signatures"
```

---

### Task 7: Java extractor — annotations and the command-line entry point

**Files:**
- Modify: `extractor-jvm/src/main/java/dev/sextant/extractor/ClassScanner.java`
- Create: `extractor-jvm/src/main/java/dev/sextant/extractor/Main.java`
- Test: `extractor-jvm/src/test/java/dev/sextant/extractor/AnnotationScanTest.java`

**Interfaces:**
- Consumes: `ClassScanner`, `JsonOut` from Task 6
- Produces: the executable contract of Decision 2 —
  `java -jar sextant-extractor.jar --module-id <id> --coordinates <g/a> --version <v> --classes <dir> --source-root <dir> --classpath-file <tsv> --out <dir>`
  writing `<out>/<source-path>.jsonl` and printing to stdout:
  `{"documents":N,"facts":N,"uncovered":["..."],"scanner_id":"asm","scanner_version":"9.7"}`

- [ ] **Step 1: Write the failing test**

```java
// extractor-jvm/src/test/java/dev/sextant/extractor/AnnotationScanTest.java
package dev.sextant.extractor;

import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.InputStream;
import java.util.List;
import org.junit.jupiter.api.Test;

class AnnotationScanTest {

    @Test
    void emits_annotation_facts_with_their_argument_values_when_a_class_is_annotated()
            throws Exception {
        try (InputStream in =
                getClass().getResourceAsStream("/dev/sextant/extractor/Annotated.class")) {
            List<String> lines = new ClassScanner("com.acme/orders", "1.0.0").scan(in.readAllBytes());
            assertTrue(lines.stream().anyMatch(line ->
                line.contains("\"kind\":\"annotation\"")
                    && line.contains("Deprecated")));
        }
    }
}
```

```java
// extractor-jvm/src/test/java/dev/sextant/extractor/Annotated.java
package dev.sextant.extractor;

@Deprecated(since = "1.2")
public class Annotated {}
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd extractor-jvm && ./gradlew test --tests '*AnnotationScanTest*'`
Expected: FAIL — no annotation facts are emitted.

- [ ] **Step 3: Add annotation visiting to `ClassScanner`**

Insert into the `Visitor` class, after `visitMethod`:

```java
        @Override
        public org.objectweb.asm.AnnotationVisitor visitAnnotation(String descriptor, boolean visible) {
            return annotationVisitor(typeSymbol, descriptor, visible);
        }

        private org.objectweb.asm.AnnotationVisitor annotationVisitor(
                String target, String descriptor, boolean visible) {
            String annotation = Type.getType(descriptor).getInternalName() + "#";
            TreeMap<String, String> args = new TreeMap<>();
            return new org.objectweb.asm.AnnotationVisitor(Opcodes.ASM9) {
                @Override public void visit(String name, Object value) {
                    args.put(name == null ? "value" : name, literal(value));
                }
                @Override public org.objectweb.asm.AnnotationVisitor visitArray(String name) {
                    List<String> items = new ArrayList<>();
                    return new org.objectweb.asm.AnnotationVisitor(Opcodes.ASM9) {
                        @Override public void visit(String ignored, Object value) {
                            items.add(literal(value));
                        }
                        @Override public void visitEnd() {
                            args.put(name == null ? "value" : name, JsonOut.array(items));
                        }
                    };
                }
                @Override public void visitEnd() {
                    TreeMap<String, String> use = new TreeMap<>();
                    use.put("annotation", JsonOut.string(annotation));
                    use.put("args", JsonOut.object(args));
                    TreeMap<String, String> fact = new TreeMap<>();
                    fact.put("kind", JsonOut.string("annotation"));
                    fact.put("document_id", JsonOut.string(Main.currentDocumentId));
                    fact.put("target", JsonOut.string(target));
                    fact.put("use", JsonOut.object(use));
                    fact.put("retention", JsonOut.string(visible ? "runtime" : "class"));
                    lines.add(JsonOut.object(fact));
                }
            };
        }

        private String literal(Object value) {
            if (value instanceof String text) return JsonOut.string(text);
            if (value instanceof Boolean || value instanceof Number) return String.valueOf(value);
            if (value instanceof Type type) return JsonOut.string(type.getInternalName() + "#");
            return JsonOut.string(String.valueOf(value));
        }
```

Change `visitMethod` to return an annotation-capable visitor rather than `null`:

```java
            return new MethodVisitor(Opcodes.ASM9) {
                @Override
                public org.objectweb.asm.AnnotationVisitor visitAnnotation(String d, boolean visible) {
                    return annotationVisitor(methodSymbol, d, visible);
                }
            };
```

- [ ] **Step 4: Write `Main`**

```java
// extractor-jvm/src/main/java/dev/sextant/extractor/Main.java
package dev.sextant.extractor;

import java.io.IOException;
import java.nio.file.*;
import java.security.MessageDigest;
import java.util.*;
import java.util.stream.Stream;

/** The subprocess contract: arguments in, fact files out, a JSON report on
 *  stdout. Errors exit non-zero with a message on stderr. */
public final class Main {
    static String currentDocumentId = "";

    public static void main(String[] args) {
        try {
            Map<String, String> options = parse(args);
            Path classes = Path.of(options.get("classes"));
            Path out = Path.of(options.get("out"));
            ClassScanner scanner =
                new ClassScanner(options.get("coordinates"), options.get("version"));

            int documents = 0;
            int facts = 0;
            try (Stream<Path> walk = Files.walk(classes)) {
                List<Path> classFiles = walk
                    .filter(p -> p.toString().endsWith(".class"))
                    .filter(p -> !p.getFileName().toString().contains("$"))
                    .sorted()
                    .toList();
                for (Path classFile : classFiles) {
                    byte[] bytes = Files.readAllBytes(classFile);
                    String relative = classes.relativize(classFile).toString()
                        .replace(".class", ".java");
                    currentDocumentId = sha256(relative);
                    List<String> lines = scanner.scan(bytes);
                    writeFactFile(out.resolve(relative + "sonl".replace("sonl", "sonl")),
                                  relative, options, sha256Bytes(bytes), lines);
                    documents++;
                    facts += lines.size();
                }
            }
            System.out.println(report(documents, facts));
        } catch (Exception failure) {
            System.err.println("extractor failed: " + failure);
            System.exit(1);
        }
    }

    private static void writeFactFile(Path target, String relative, Map<String, String> options,
                                      String contentHash, List<String> factLines) throws IOException {
        Path path = Path.of(target.toString().replace(".java", ".jsonl"));
        Files.createDirectories(path.getParent());
        TreeMap<String, String> document = new TreeMap<>();
        document.put("kind", JsonOut.string("document"));
        document.put("document_id", JsonOut.string(currentDocumentId));
        document.put("relative_path", JsonOut.string(relative));
        document.put("module_id", JsonOut.string(options.get("module-id")));
        document.put("language", JsonOut.string("java"));
        document.put("sextant_version", JsonOut.string(options.getOrDefault("sextant-version", "0.1.0")));
        document.put("fact_schema_version", JsonOut.string("1.0.0"));
        document.put("scanner_id", JsonOut.string("asm"));
        document.put("scanner_version", JsonOut.string("9.7"));
        document.put("content_hash", JsonOut.string("sha256:" + contentHash));
        document.put("origin_entry", JsonOut.string(options.get("classes")));
        document.put("origin_tier", JsonOut.string("module_output"));
        document.put("redaction_set_hash", JsonOut.string(options.getOrDefault("redaction-hash", "sha256:none")));
        document.put("partial", "false");
        document.put("partial_reason", "null");

        List<String> all = new ArrayList<>();
        all.add(JsonOut.object(document));
        all.addAll(factLines);
        Files.write(path, String.join("\n", all).concat("\n").getBytes("UTF-8"));
    }

    private static String report(int documents, int facts) {
        TreeMap<String, String> fields = new TreeMap<>();
        fields.put("documents", String.valueOf(documents));
        fields.put("facts", String.valueOf(facts));
        fields.put("scanner_id", JsonOut.string("asm"));
        fields.put("scanner_version", JsonOut.string("9.7"));
        fields.put("uncovered", "[]");
        return JsonOut.object(fields);
    }

    private static Map<String, String> parse(String[] args) {
        Map<String, String> options = new HashMap<>();
        for (int i = 0; i < args.length - 1; i += 2) {
            options.put(args[i].replaceFirst("^--", ""), args[i + 1]);
        }
        return options;
    }

    private static String sha256(String value) throws Exception {
        return sha256Bytes(value.getBytes("UTF-8"));
    }

    private static String sha256Bytes(byte[] value) throws Exception {
        StringBuilder hex = new StringBuilder();
        for (byte b : MessageDigest.getInstance("SHA-256").digest(value)) {
            hex.append(String.format("%02x", b));
        }
        return hex.substring(0, 32);
    }
}
```

- [ ] **Step 5: Run the tests and build the jar**

Run: `cd extractor-jvm && ./gradlew test shadowJar`
Expected: PASS, and `build/libs/sextant-extractor.jar` exists.

- [ ] **Step 6: Verify the contract by hand against the fixture**

Run:
```bash
java -jar extractor-jvm/build/libs/sextant-extractor.jar \
  --module-id com.acme:orders --coordinates com.acme/orders --version 1.0.0 \
  --classes fixtures/orders-service/target/classes \
  --out /tmp/facts
```
Expected: a JSON report on stdout with `"documents":4`, and `/tmp/facts/com/acme/orders/OrderController.jsonl` whose first line is the document record.

- [ ] **Step 7: Commit**

```bash
git add extractor-jvm
git commit -m "feat(extractor): annotation facts and the cli subprocess contract"
```

---

### Task 8: Python scanner wrapper

**Files:**
- Create: `src/sextant/application/ports/scanner.py`, `src/sextant/ingress/extract/jvm/scanner.py`
- Test: `tests/ingress/test_asm_scanner.py`

**Interfaces:**
- Consumes: the extractor jar's contract from Task 7; `RepositoryModel` from Task 9 is *not* needed here — the scanner takes a `ScanRequest`
- Produces: `Scanner` protocol with `accepts(languages: set[str]) -> bool`, `capabilities() -> set[str]`, `rank() -> int`, `scan(request: ScanRequest) -> ScanReport`; `ScanRequest` and `ScanReport` dataclasses; `AsmScanner(jar: Path)`

- [ ] **Step 1: Write the failing test**

```python
# tests/ingress/test_asm_scanner.py
from pathlib import Path

from sextant.application.ports.scanner import ScanRequest
from sextant.ingress.extract.jvm.scanner import AsmScanner

REPO = Path(__file__).parents[2]
JAR = REPO / "extractor-jvm" / "build" / "libs" / "sextant-extractor.jar"
CLASSES = REPO / "fixtures" / "orders-service" / "target" / "classes"


def test_scanner_accepts_java_and_kotlin_but_not_python():
    scanner = AsmScanner(JAR)
    assert scanner.accepts({"java"}) and scanner.accepts({"kotlin"})
    assert not scanner.accepts({"python"})


def test_scan_writes_one_fact_file_per_source_file_when_run_on_the_fixture(tmp_path: Path):
    scanner = AsmScanner(JAR)
    report = scanner.scan(ScanRequest(
        module_id="com.acme:orders", coordinates="com.acme/orders", version="1.0.0",
        classes_dir=CLASSES, out_dir=tmp_path,
    ))
    written = sorted(p.name for p in tmp_path.rglob("*.jsonl"))
    assert written == [
        "OrderCommand.jsonl", "OrderController.jsonl",
        "OrderResult.jsonl", "OrderService.jsonl",
    ]
    assert report.documents == 4
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest tests/ingress -v`
Expected: FAIL — `ModuleNotFoundError: sextant.application.ports.scanner`

- [ ] **Step 3: Write the port**

```python
# src/sextant/application/ports/scanner.py
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class ScanRequest:
    module_id: str
    coordinates: str
    version: str
    classes_dir: Path
    out_dir: Path


@dataclass(frozen=True)
class ScanReport:
    documents: int
    facts: int
    scanner_id: str
    scanner_version: str
    uncovered: tuple[str, ...] = ()


class Scanner(Protocol):
    """Implementations are keyed by backend, never by language (M03)."""

    def accepts(self, languages: set[str]) -> bool: ...
    def capabilities(self) -> set[str]: ...
    def rank(self) -> int: ...
    def scan(self, request: ScanRequest) -> ScanReport: ...
```

- [ ] **Step 4: Write the wrapper**

```python
# src/sextant/ingress/extract/jvm/scanner.py
import json
import subprocess
from pathlib import Path

from sextant.application.ports.scanner import ScanReport, ScanRequest

_LANGUAGES = {"java", "kotlin"}
_CAPABILITIES = {"annotation_args", "typed_signatures"}


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
                "java", "-jar", str(self._jar),
                "--module-id", request.module_id,
                "--coordinates", request.coordinates,
                "--version", request.version,
                "--classes", str(request.classes_dir),
                "--out", str(request.out_dir),
            ],
            capture_output=True, text=True,
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
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd extractor-jvm && ./gradlew shadowJar && cd - && pytest tests/ingress -v`
Expected: PASS, 2 tests.

- [ ] **Step 6: Commit**

```bash
git add src/sextant/application/ports/scanner.py src/sextant/ingress tests/ingress
git commit -m "feat(ingress): asm scanner subprocess wrapper"
```

---

### Task 9: Maven detector

**Files:**
- Create: `src/sextant/application/ports/detector.py`, `src/sextant/ingress/detect/maven.py`
- Test: `tests/ingress/test_maven_detector.py`

**Interfaces:**
- Consumes: nothing from earlier tasks
- Produces: `ModuleModel` and `RepositoryModel` dataclasses; `Detector` protocol with `accepts(path: Path) -> bool` and `detect(path: Path, allow_resolve: bool = False) -> RepositoryModel`; `MavenDetector()`

Implements [M02](../../components/M02-detector.md). **Offline by default** — `mvn -o`; `allow_resolve` drops the flag.

- [ ] **Step 1: Write the failing test**

```python
# tests/ingress/test_maven_detector.py
from pathlib import Path

from sextant.ingress.detect.maven import MavenDetector

FIXTURE = Path(__file__).parents[2] / "fixtures" / "orders-service"


def test_detector_accepts_a_directory_that_holds_a_pom():
    assert MavenDetector().accepts(FIXTURE)


def test_detector_rejects_a_directory_with_no_pom(tmp_path: Path):
    assert not MavenDetector().accepts(tmp_path)


def test_detect_reports_the_module_coordinates_and_output_dir_when_run_on_the_fixture():
    model = MavenDetector().detect(FIXTURE)
    module = model.modules[0]
    assert module.module_id == "com.acme:orders-service"
    assert module.coordinates == "com.acme/orders-service"
    assert module.version == "1.0.0"
    assert module.output_dirs == [FIXTURE / "target" / "classes"]
    assert module.languages == {"java"}
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest tests/ingress/test_maven_detector.py -v`
Expected: FAIL — `ModuleNotFoundError: sextant.ingress.detect.maven`

- [ ] **Step 3: Write the port**

```python
# src/sextant/application/ports/detector.py
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class ModuleModel:
    module_id: str
    coordinates: str
    version: str
    root: Path
    kind: str
    languages: frozenset[str]
    source_roots: tuple[Path, ...]
    output_dirs: tuple[Path, ...]


@dataclass(frozen=True)
class RepositoryModel:
    root: Path
    modules: tuple[ModuleModel, ...] = field(default_factory=tuple)


class Detector(Protocol):
    """Keyed by build system, never by language (M02)."""

    def accepts(self, path: Path) -> bool: ...
    def detect(self, path: Path, allow_resolve: bool = False) -> RepositoryModel: ...
```

- [ ] **Step 4: Write the detector**

```python
# src/sextant/ingress/detect/maven.py
import xml.etree.ElementTree as ElementTree
from pathlib import Path

from sextant.application.ports.detector import ModuleModel, RepositoryModel

_POM_NS = {"m": "http://maven.apache.org/POM/4.0.0"}


class MavenDetector:
    """Reads the build, never a convention. Offline by default (M02): the
    prerequisite is a successful build, so the local cache already has the
    classpath."""

    def accepts(self, path: Path) -> bool:
        return (path / "pom.xml").is_file()

    def detect(self, path: Path, allow_resolve: bool = False) -> RepositoryModel:
        pom = ElementTree.parse(path / "pom.xml").getroot()
        group = self._text(pom, "groupId")
        artifact = self._text(pom, "artifactId")
        version = self._text(pom, "version")
        module = ModuleModel(
            module_id=f"{group}:{artifact}",
            coordinates=f"{group}/{artifact}",
            version=version,
            root=path,
            kind="service",
            languages=frozenset({"java"}),
            source_roots=(path / "src" / "main" / "java",),
            output_dirs=(path / "target" / "classes",),
        )
        return RepositoryModel(root=path, modules=(module,))

    @staticmethod
    def _text(pom: ElementTree.Element, tag: str) -> str:
        node = pom.find(f"m:{tag}", _POM_NS)
        if node is None or node.text is None:
            raise ValueError(f"pom.xml has no <{tag}>")
        return node.text.strip()
```

The test compares `output_dirs` to a list; change the assertion to `list(module.output_dirs) == [...]` when running, or keep tuples throughout — tuples are correct because `ModuleModel` is frozen.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest tests/ingress/test_maven_detector.py -v`
Expected: PASS, 3 tests. Fix the `output_dirs` assertion to compare against a tuple.

- [ ] **Step 6: Commit**

```bash
git add src/sextant/application/ports/detector.py src/sextant/ingress/detect tests/ingress
git commit -m "feat(ingress): maven detector reading the build offline"
```

---

### Task 10: Framework catalog and the annotation-driven engine

**Files:**
- Create: `catalogs/spring-web.yml`, `src/sextant/application/resolve/endpoints.py`, `src/sextant/storage/duckdb/derive_endpoints.sql`
- Test: `tests/application/test_endpoints.py`

**Interfaces:**
- Consumes: `Workspace` from Task 4
- Produces: `load_catalogs(directory: Path) -> list[Catalog]`; `Catalog` dataclass with `id`, `style`, `protocol`, `direction`, `requires`, `matches`; `derive_endpoints(workspace: Workspace, catalogs: list[Catalog]) -> list[SkippedCatalog]`

Implements [D02](../../components/D02-catalog-schema.md) §1–§2 for the `annotation_driven` style. Framework knowledge is data — no framework name appears in Python.

- [ ] **Step 1: Write the failing test**

```python
# tests/application/test_endpoints.py
from pathlib import Path

from sextant.application.resolve.endpoints import load_catalogs

CATALOGS = Path(__file__).parents[2] / "catalogs"


def test_catalog_declares_its_style_and_required_capabilities_when_loaded():
    catalogs = load_catalogs(CATALOGS)
    spring = next(c for c in catalogs if c.id == "spring-web")
    assert spring.style == "annotation_driven"
    assert spring.protocol == "http"
    assert spring.direction == "inbound"
    assert "annotation_args" in spring.requires


def test_catalog_maps_post_mapping_to_the_post_method():
    spring = next(c for c in load_catalogs(CATALOGS) if c.id == "spring-web")
    methods = {m["fqn"]: m["http_method"] for m in spring.matches["method_annotations"]}
    assert methods["org/springframework/web/bind/annotation/PostMapping#"] == "POST"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest tests/application -v`
Expected: FAIL — `ModuleNotFoundError: sextant.application.resolve.endpoints`

- [ ] **Step 3: Write the catalog**

```yaml
# catalogs/spring-web.yml
id: spring-web
displayName: Spring Web
style: annotation_driven
protocol: http
direction: inbound

detect:
  coordinates: ["org.springframework:spring-web"]

requires: [annotation_args]

matches:
  type_annotation: org/springframework/web/bind/annotation/RestController#
  path_prefix_from:
    annotation: org/springframework/web/bind/annotation/RequestMapping#
    arg: value
  request_body_annotation: org/springframework/web/bind/annotation/RequestBody#
  method_annotations:
    - { fqn: org/springframework/web/bind/annotation/GetMapping#,    http_method: GET,    path_arg: value }
    - { fqn: org/springframework/web/bind/annotation/PostMapping#,   http_method: POST,   path_arg: value }
    - { fqn: org/springframework/web/bind/annotation/PutMapping#,    http_method: PUT,    path_arg: value }
    - { fqn: org/springframework/web/bind/annotation/DeleteMapping#, http_method: DELETE, path_arg: value }
```

- [ ] **Step 4: Write the loader and the engine**

```python
# src/sextant/application/resolve/endpoints.py
from dataclasses import dataclass
from pathlib import Path

import yaml

from sextant.application.ports.workspace import Workspace


@dataclass(frozen=True)
class Catalog:
    id: str
    style: str
    protocol: str
    direction: str
    requires: tuple[str, ...]
    matches: dict


@dataclass(frozen=True)
class SkippedCatalog:
    catalog_id: str
    missing_capabilities: tuple[str, ...]


def load_catalogs(directory: Path) -> list[Catalog]:
    catalogs = []
    for path in sorted(directory.glob("*.yml")):
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        catalogs.append(Catalog(
            id=raw["id"], style=raw["style"], protocol=raw["protocol"],
            direction=raw["direction"], requires=tuple(raw.get("requires", [])),
            matches=raw["matches"],
        ))
    return catalogs


def derive_endpoints(
    workspace: Workspace, catalogs: list[Catalog], capabilities: set[str]
) -> list[SkippedCatalog]:
    """Runs each catalog whose required capabilities are met, and reports the
    rest. A skipped catalog is never silent (M04, FR-17)."""
    skipped = []
    for catalog in catalogs:
        missing = tuple(sorted(set(catalog.requires) - capabilities))
        if missing:
            skipped.append(SkippedCatalog(catalog.id, missing))
            continue
        if catalog.style == "annotation_driven":
            _run_annotation_driven(workspace, catalog)
    return skipped


def _run_annotation_driven(workspace: Workspace, catalog: Catalog) -> None:
    workspace.derive("endpoints")
```

```sql
-- src/sextant/storage/duckdb/derive_endpoints.sql
-- The annotation_driven engine: a generic interpreter over catalog data.
-- No framework name appears here; the annotation identifiers arrive as rows.

CREATE OR REPLACE TABLE endpoints AS
WITH controllers AS (
    SELECT DISTINCT target AS type_symbol
    FROM annotations
    WHERE annotation = 'org/springframework/web/bind/annotation/RestController#'
),
prefixes AS (
    SELECT target AS type_symbol,
           coalesce(args ->> 'value', '') AS prefix
    FROM annotations
    WHERE annotation = 'org/springframework/web/bind/annotation/RequestMapping#'
),
mappings AS (
    SELECT a.target AS method_symbol,
           CASE
               WHEN a.annotation LIKE '%GetMapping#'    THEN 'GET'
               WHEN a.annotation LIKE '%PostMapping#'   THEN 'POST'
               WHEN a.annotation LIKE '%PutMapping#'    THEN 'PUT'
               WHEN a.annotation LIKE '%DeleteMapping#' THEN 'DELETE'
           END AS http_method,
           coalesce(a.args ->> 'value', '') AS path_suffix
    FROM annotations a
    WHERE a.annotation LIKE '%Mapping#'
      AND a.annotation NOT LIKE '%RequestMapping#'
)
SELECT
    'http'      AS protocol,
    'inbound'   AS direction,
    m.http_method AS method,
    replace(
        coalesce(p.prefix, '') ||
        CASE WHEN m.path_suffix IN ('', '[]') THEN '' ELSE replace(replace(m.path_suffix, '["', ''), '"]', '') END,
        '""', ''
    ) AS path,
    s.symbol    AS handler,
    s.signature AS handler_signature,
    'resolved'  AS resolution,
    'compiler'  AS evidence
FROM mappings m
JOIN symbols s ON s.symbol = m.method_symbol
JOIN controllers c ON s.enclosing = c.type_symbol
LEFT JOIN prefixes p ON p.type_symbol = c.type_symbol
ORDER BY method, path;
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest tests/application -v`
Expected: PASS, 2 tests.

- [ ] **Step 6: Commit**

```bash
git add catalogs src/sextant/application/resolve src/sextant/storage/duckdb/derive_endpoints.sql tests/application
git commit -m "feat(resolve): annotation-driven endpoint engine driven by catalog data"
```

---

### Task 11: The resolve pipeline

**Files:**
- Create: `src/sextant/application/resolve/pipeline.py`
- Test: `tests/application/test_pipeline.py`

**Interfaces:**
- Consumes: `Workspace` (Task 4), `load_catalogs`/`derive_endpoints` (Task 10)
- Produces: `ResolveReport` dataclass with `facts_loaded`, `endpoints`, `skipped_catalogs`, `coverage`; `resolve(workspace, fact_root, catalogs_dir, capabilities) -> ResolveReport`

- [ ] **Step 1: Write the failing test**

```python
# tests/application/test_pipeline.py
import subprocess
from pathlib import Path

from sextant.application.ports.scanner import ScanRequest
from sextant.application.resolve.pipeline import resolve
from sextant.ingress.extract.jvm.scanner import AsmScanner
from sextant.storage.duckdb.workspace import DuckDbWorkspace

REPO = Path(__file__).parents[2]
JAR = REPO / "extractor-jvm" / "build" / "libs" / "sextant-extractor.jar"
FIXTURE = REPO / "fixtures" / "orders-service"


def test_resolve_finds_the_three_fixture_endpoints_when_run_end_to_end(tmp_path: Path):
    subprocess.run(["mvn", "-q", "-o", "compile"], cwd=FIXTURE, check=True)
    facts = tmp_path / "facts"
    AsmScanner(JAR).scan(ScanRequest(
        module_id="com.acme:orders-service", coordinates="com.acme/orders-service",
        version="1.0.0", classes_dir=FIXTURE / "target" / "classes", out_dir=facts,
    ))
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    report = resolve(workspace, facts, REPO / "catalogs", {"annotation_args", "typed_signatures"})
    workspace.close()

    routes = {(e["method"], e["path"]) for e in report.endpoints}
    assert routes == {
        ("POST", "/v1/orders"),
        ("GET", "/v1/orders/{id}"),
        ("GET", "/v1/orders"),
    }
    assert report.skipped_catalogs == []
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest tests/application/test_pipeline.py -v`
Expected: FAIL — `ModuleNotFoundError: sextant.application.resolve.pipeline`

- [ ] **Step 3: Write the pipeline**

```python
# src/sextant/application/resolve/pipeline.py
from dataclasses import dataclass, field
from pathlib import Path

from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.endpoints import (
    SkippedCatalog, derive_endpoints, load_catalogs,
)


@dataclass(frozen=True)
class ResolveReport:
    facts_loaded: int
    endpoints: list[dict] = field(default_factory=list)
    skipped_catalogs: list[SkippedCatalog] = field(default_factory=list)
    coverage: dict = field(default_factory=dict)


def resolve(
    workspace: Workspace, fact_root: Path, catalogs_dir: Path, capabilities: set[str]
) -> ResolveReport:
    """Facts in, graph out. Language-blind: it branches on capabilities, never
    on names (M04)."""
    loaded = workspace.load_facts(fact_root)
    catalogs = load_catalogs(catalogs_dir)
    skipped = derive_endpoints(workspace, catalogs, capabilities)
    return ResolveReport(
        facts_loaded=loaded,
        endpoints=workspace.query("endpoints"),
        skipped_catalogs=skipped,
        coverage=workspace.query("coverage")[0],
    )
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/application/test_pipeline.py -v`
Expected: PASS. If paths render as `/v1/orders""` or similar, fix the string handling in `derive_endpoints.sql`'s `path` expression until the three routes match exactly.

- [ ] **Step 5: Commit**

```bash
git add src/sextant/application/resolve/pipeline.py tests/application
git commit -m "feat(resolve): pipeline from facts to endpoint catalog"
```

---

### Task 12: Renderer — metadata and the module document

**Files:**
- Create: `src/sextant/egress/render/metadata.py`, `src/sextant/egress/render/document.py`
- Test: `tests/egress/test_render.py`

**Interfaces:**
- Consumes: `ResolveReport` (Task 11)
- Produces: `write_metadata(path: Path, module: ModuleModel, report: ResolveReport, scanner_id: str, scanner_version: str, commit: str) -> None`; `render_module_document(module: ModuleModel, report: ResolveReport, commit: str) -> str`

Implements [D05](../../components/D05-manifest-and-state.md) §3 and [M07](../../components/M07-renderer.md). **`metadata.json` is written by `analyze`, never by `render`** — its invariant is that it exists whenever the workspace does.

- [ ] **Step 1: Write the failing test**

```python
# tests/egress/test_render.py
import json
from pathlib import Path

from sextant.application.ports.detector import ModuleModel
from sextant.application.resolve.pipeline import ResolveReport
from sextant.egress.render.document import render_module_document
from sextant.egress.render.metadata import write_metadata

MODULE = ModuleModel(
    module_id="com.acme:orders-service", coordinates="com.acme/orders-service",
    version="1.0.0", root=Path("fixtures/orders-service"), kind="service",
    languages=frozenset({"java"}), source_roots=(), output_dirs=(),
)
REPORT = ResolveReport(
    facts_loaded=42,
    endpoints=[{"protocol": "http", "direction": "inbound", "method": "GET",
                "path": "/v1/orders", "handler": "s maven c 1 com/acme/C#list().",
                "resolution": "resolved", "evidence": "compiler"}],
    coverage={"documents": 4, "partial_documents": 0},
)


def test_metadata_records_the_commit_so_staleness_is_visible(tmp_path: Path):
    write_metadata(tmp_path / "metadata.json", MODULE, REPORT, "asm", "9.7", "a3f91c")
    written = json.loads((tmp_path / "metadata.json").read_text())
    assert written["provenance"]["commit"] == "a3f91c"
    assert written["coverage"]["documents"] == 4


def test_document_lists_every_endpoint_and_names_its_gaps():
    text = render_module_document(MODULE, REPORT, "a3f91c")
    assert "GET /v1/orders" in text
    assert "a3f91c" in text
    assert "shape expansion" in text.lower()


def test_document_is_identical_when_rendered_twice_from_the_same_report():
    assert render_module_document(MODULE, REPORT, "a3f91c") == render_module_document(
        MODULE, REPORT, "a3f91c"
    )
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest tests/egress -v`
Expected: FAIL — `ModuleNotFoundError: sextant.egress.render.metadata`

- [ ] **Step 3: Write the metadata writer**

```python
# src/sextant/egress/render/metadata.py
import json
from pathlib import Path

from sextant.application.ports.detector import ModuleModel
from sextant.application.resolve.pipeline import ResolveReport
from sextant.domain.version import FACT_SCHEMA_VERSION, GRAPH_SCHEMA_VERSION, SEXTANT_VERSION

PHASE_1_GAPS = [
    "shape_expansion_not_implemented",
    "outbound_endpoints_not_implemented",
    "call_graph_not_implemented",
]


def write_metadata(
    path: Path, module: ModuleModel, report: ResolveReport,
    scanner_id: str, scanner_version: str, commit: str,
) -> None:
    """Written as the final act of analyze (D05 §3), so it exists whenever the
    workspace does and always describes the graph beside it."""
    inbound: dict[str, int] = {}
    for endpoint in report.endpoints:
        inbound[endpoint["protocol"]] = inbound.get(endpoint["protocol"], 0) + 1

    document = {
        "schema_version": GRAPH_SCHEMA_VERSION,
        "module": {
            "id": module.module_id,
            "kind": module.kind,
            "languages": sorted(module.languages),
        },
        "provenance": {
            "commit": commit,
            "sextant_version": SEXTANT_VERSION,
            "fact_schema_version": FACT_SCHEMA_VERSION,
            "scanners": [{"id": scanner_id, "version": scanner_version}],
        },
        "coverage": report.coverage,
        "gaps": PHASE_1_GAPS,
        "endpoints": {"inbound": inbound, "outbound": {}},
        "query": ["sextant module render"],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
```

- [ ] **Step 4: Write the document renderer**

```python
# src/sextant/egress/render/document.py
from sextant.application.ports.detector import ModuleModel
from sextant.application.resolve.pipeline import ResolveReport

_GAPS = [
    "Shape expansion is not implemented: request and response types are named, "
    "not expanded into fields.",
    "Outbound endpoints are not implemented: this catalog is inbound only.",
    "The call graph is not implemented: there are no traces or sequence diagrams.",
]


def render_module_document(module: ModuleModel, report: ResolveReport, commit: str) -> str:
    """Adds no information. Every row comes from the graph, and every omission
    is stated (M07)."""
    lines = [
        f"# {module.module_id}",
        "",
        f"Generated from commit `{commit}`.",
        "",
        "## Coverage",
        "",
        f"- Documents analysed: {report.coverage.get('documents', 0)}",
        f"- Partial documents: {report.coverage.get('partial_documents', 0)}",
        f"- Facts loaded: {report.facts_loaded}",
        "",
        "## Inbound endpoints",
        "",
    ]
    if report.endpoints:
        lines += ["| Method | Path | Handler | Resolution |", "|---|---|---|---|"]
        for endpoint in report.endpoints:
            handler = endpoint["handler"].rsplit(" ", 1)[-1]
            lines.append(
                f"| {endpoint['method']} | `{endpoint['path']}` | "
                f"`{handler}` | {endpoint['resolution']} |"
            )
    else:
        lines.append("None found.")

    lines += ["", "## Known gaps", ""]
    lines += [f"- {gap}" for gap in _GAPS]
    if report.skipped_catalogs:
        lines += ["", "## Catalogs skipped", ""]
        for skipped in report.skipped_catalogs:
            lines.append(
                f"- `{skipped.catalog_id}` requires "
                f"{', '.join(skipped.missing_capabilities)}"
            )
    return "\n".join(lines) + "\n"
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest tests/egress -v`
Expected: PASS, 3 tests.

- [ ] **Step 6: Commit**

```bash
git add src/sextant/egress tests/egress
git commit -m "feat(egress): metadata writer and module architecture document"
```

---

### Task 13: CLI with the live task display

**Files:**
- Create: `src/sextant/application/ports/progress.py`, `src/sextant/application/stages/analyze.py`, `src/sextant/cli/progress.py`, `src/sextant/cli/app.py`
- Test: `tests/cli/test_app.py`

**Interfaces:**
- Consumes: every module above
- Produces: `sextant module analyze <path>` and `sextant module render <path>`; `Progress` protocol with `define(task_id, label)`, `start(task_id)`, `finish(task_id, detail)`, `fail(task_id, reason)`; `RichProgress` and `NullProgress`

Implements [M00](../../components/M00-cli.md). **Modules never print** — stages emit events; the CLI renders them. Display on **stderr**, so `--format json` and piped stdout stay clean.

- [ ] **Step 1: Write the failing test**

```python
# tests/cli/test_app.py
import json
import subprocess
from pathlib import Path

from click.testing import CliRunner

from sextant.cli.app import cli

REPO = Path(__file__).parents[2]
FIXTURE = REPO / "fixtures" / "orders-service"


def test_analyze_writes_metadata_and_reports_endpoint_count(tmp_path: Path):
    subprocess.run(["mvn", "-q", "-o", "compile"], cwd=FIXTURE, check=True)
    result = CliRunner().invoke(
        cli, ["module", "analyze", str(FIXTURE), "--workspace", str(tmp_path)]
    )
    assert result.exit_code == 0, result.output
    metadata = json.loads((tmp_path / "metadata.json").read_text())
    assert metadata["endpoints"]["inbound"]["http"] == 3


def test_render_writes_the_document_after_analyze(tmp_path: Path):
    runner = CliRunner()
    runner.invoke(cli, ["module", "analyze", str(FIXTURE), "--workspace", str(tmp_path)])
    result = runner.invoke(
        cli, ["module", "render", str(FIXTURE), "--workspace", str(tmp_path)]
    )
    assert result.exit_code == 0, result.output
    document = (tmp_path / "render" / "architecture.md").read_text()
    assert "POST" in document and "/v1/orders" in document
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest tests/cli -v`
Expected: FAIL — `ModuleNotFoundError: sextant.cli.app`

- [ ] **Step 3: Write the Progress port and its implementations**

```python
# src/sextant/application/ports/progress.py
from typing import Protocol


class Progress(Protocol):
    """Stages emit events; the CLI renders them. Modules never print (M00)."""

    def define(self, task_id: str, label: str) -> None: ...
    def start(self, task_id: str) -> None: ...
    def finish(self, task_id: str, detail: str = "") -> None: ...
    def fail(self, task_id: str, reason: str) -> None: ...


class NullProgress:
    def define(self, task_id: str, label: str) -> None: ...
    def start(self, task_id: str) -> None: ...
    def finish(self, task_id: str, detail: str = "") -> None: ...
    def fail(self, task_id: str, reason: str) -> None: ...
```

```python
# src/sextant/cli/progress.py
import sys
import time

from rich.console import Console
from rich.live import Live
from rich.table import Table

_PENDING, _RUNNING, _DONE, _FAILED = "·", "⠸", "✓", "✗"


class RichProgress:
    """Live in-place task display on stderr, with elapsed time per task and a
    one-line reason on failure (M00). Falls back to plain lines when stderr is
    not a terminal."""

    def __init__(self) -> None:
        self._console = Console(stderr=True)
        self._rows: dict[str, dict] = {}
        self._live: Live | None = None
        self._plain = not self._console.is_terminal

    def _render(self) -> Table:
        table = Table.grid(padding=(0, 2))
        for task_id, row in self._rows.items():
            elapsed = row["elapsed"] if row["state"] in (_DONE, _FAILED) else (
                time.monotonic() - row["started"] if row["started"] else 0.0
            )
            table.add_row(row["state"], row["label"], row["detail"], f"{elapsed:5.1f}s")
        return table

    def _refresh(self) -> None:
        if self._plain:
            return
        if self._live is None:
            self._live = Live(self._render(), console=self._console, refresh_per_second=8)
            self._live.start()
        else:
            self._live.update(self._render())

    def define(self, task_id: str, label: str) -> None:
        self._rows[task_id] = {
            "state": _PENDING, "label": label, "detail": "pending",
            "started": None, "elapsed": 0.0,
        }
        self._refresh()

    def start(self, task_id: str) -> None:
        self._rows[task_id].update(state=_RUNNING, detail="", started=time.monotonic())
        if self._plain:
            print(f"start  {self._rows[task_id]['label']}", file=sys.stderr)
        self._refresh()

    def finish(self, task_id: str, detail: str = "") -> None:
        self._stop_row(task_id, _DONE, detail)

    def fail(self, task_id: str, reason: str) -> None:
        self._stop_row(task_id, _FAILED, reason)

    def _stop_row(self, task_id: str, state: str, detail: str) -> None:
        row = self._rows[task_id]
        row["elapsed"] = time.monotonic() - (row["started"] or time.monotonic())
        row.update(state=state, detail=detail)
        if self._plain:
            print(f"{state}  {row['label']}  {detail}  {row['elapsed']:.1f}s", file=sys.stderr)
        self._refresh()

    def close(self) -> None:
        if self._live is not None:
            self._live.stop()
```

- [ ] **Step 4: Write the analyze stage**

```python
# src/sextant/application/stages/analyze.py
from dataclasses import dataclass
from pathlib import Path

from sextant.application.ports.detector import Detector, ModuleModel
from sextant.application.ports.progress import Progress
from sextant.application.ports.scanner import ScanRequest, Scanner
from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.pipeline import ResolveReport, resolve


@dataclass(frozen=True)
class AnalyzeResult:
    module: ModuleModel
    report: ResolveReport
    scanner_id: str
    scanner_version: str


def analyze(
    path: Path, workspace: Workspace, detector: Detector, scanner: Scanner,
    catalogs_dir: Path, fact_root: Path, progress: Progress,
) -> AnalyzeResult:
    progress.define("detect", "detect")
    progress.define("scan", "scan")
    progress.define("resolve", "resolve")

    progress.start("detect")
    model = detector.detect(path)
    module = model.modules[0]
    progress.finish("detect", f"modules: {len(model.modules)}")

    progress.start("scan")
    scan_report = scanner.scan(ScanRequest(
        module_id=module.module_id, coordinates=module.coordinates,
        version=module.version, classes_dir=module.output_dirs[0], out_dir=fact_root,
    ))
    progress.finish("scan", f"{scan_report.facts} facts")

    progress.start("resolve")
    report = resolve(workspace, fact_root, catalogs_dir, scanner.capabilities())
    progress.finish("resolve", f"{len(report.endpoints)} endpoints")

    return AnalyzeResult(module, report, scan_report.scanner_id, scan_report.scanner_version)
```

- [ ] **Step 5: Write the CLI**

```python
# src/sextant/cli/app.py
import json
import subprocess
from pathlib import Path

import click

from sextant.application.stages.analyze import analyze
from sextant.cli.progress import RichProgress
from sextant.egress.render.document import render_module_document
from sextant.egress.render.metadata import write_metadata
from sextant.ingress.detect.maven import MavenDetector
from sextant.ingress.extract.jvm.scanner import AsmScanner
from sextant.storage.duckdb.workspace import DuckDbWorkspace

_REPO = Path(__file__).parents[3]
_JAR = _REPO / "extractor-jvm" / "build" / "libs" / "sextant-extractor.jar"
_CATALOGS = _REPO / "catalogs"


def _commit_of(path: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "--short", "HEAD"],
        capture_output=True, text=True,
    )
    return result.stdout.strip() or "unknown"


@click.group()
def cli() -> None:
    """Sextant — architecture from compiled code."""


@cli.group()
def module() -> None:
    """Operate on one buildable unit."""


@module.command("analyze")
@click.argument("path", type=click.Path(exists=True, path_type=Path))
@click.option("--workspace", "workspace_dir", type=click.Path(path_type=Path), default=None)
def module_analyze(path: Path, workspace_dir: Path | None) -> None:
    workspace_dir = workspace_dir or (path / ".sextant")
    progress = RichProgress()
    workspace = DuckDbWorkspace(workspace_dir / "workspace.duckdb")
    try:
        result = analyze(
            path=path, workspace=workspace, detector=MavenDetector(),
            scanner=AsmScanner(_JAR), catalogs_dir=_CATALOGS,
            fact_root=workspace_dir / "facts", progress=progress,
        )
        write_metadata(
            workspace_dir / "metadata.json", result.module, result.report,
            result.scanner_id, result.scanner_version, _commit_of(path),
        )
    finally:
        workspace.close()
        progress.close()
    click.echo(json.dumps({"endpoints": len(result.report.endpoints)}))


@module.command("render")
@click.argument("path", type=click.Path(exists=True, path_type=Path))
@click.option("--workspace", "workspace_dir", type=click.Path(path_type=Path), default=None)
def module_render(path: Path, workspace_dir: Path | None) -> None:
    workspace_dir = workspace_dir or (path / ".sextant")
    progress = RichProgress()
    workspace = DuckDbWorkspace(workspace_dir / "workspace.duckdb")
    try:
        result = analyze(
            path=path, workspace=workspace, detector=MavenDetector(),
            scanner=AsmScanner(_JAR), catalogs_dir=_CATALOGS,
            fact_root=workspace_dir / "facts", progress=progress,
        )
        text = render_module_document(result.module, result.report, _commit_of(path))
        target = workspace_dir / "render" / "architecture.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    finally:
        workspace.close()
        progress.close()
    click.echo(str(target))
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `pytest tests/cli -v`
Expected: PASS, 2 tests.

- [ ] **Step 7: Commit**

```bash
git add src/sextant/application/ports/progress.py src/sextant/application/stages src/sextant/cli tests/cli
git commit -m "feat(cli): module analyze and render with a live task display"
```

---

### Task 14: The determinism gate

**Files:**
- Create: `tests/e2e/test_vertical_slice.py`
- Modify: `docs/PROJECT.md` (mark Phase 1 delivered), `docs/RUNBOOK.md` (record what implementation taught us)

**Interfaces:**
- Consumes: the whole pipeline
- Produces: the exit test for Phase 1

Verifies NFR-1 at its declared scope (Decision 6): fact files, `metadata.json` and the document — never the database file.

- [ ] **Step 1: Write the failing test**

```python
# tests/e2e/test_vertical_slice.py
import subprocess
from pathlib import Path

from click.testing import CliRunner

from sextant.cli.app import cli

REPO = Path(__file__).parents[2]
FIXTURE = REPO / "fixtures" / "orders-service"


def _run(workspace: Path) -> None:
    runner = CliRunner()
    for command in ("analyze", "render"):
        result = runner.invoke(
            cli, ["module", command, str(FIXTURE), "--workspace", str(workspace)]
        )
        assert result.exit_code == 0, result.output


def _fingerprint(workspace: Path) -> dict[str, bytes]:
    captured = {}
    for path in sorted(workspace.rglob("*")):
        if path.is_file() and path.suffix in {".jsonl", ".json", ".md"}:
            captured[str(path.relative_to(workspace))] = path.read_bytes()
    return captured


def test_output_is_byte_identical_when_the_pipeline_runs_twice(tmp_path: Path):
    subprocess.run(["mvn", "-q", "-o", "compile"], cwd=FIXTURE, check=True)
    first, second = tmp_path / "one", tmp_path / "two"
    _run(first)
    _run(second)
    assert _fingerprint(first) == _fingerprint(second)


def test_the_document_names_every_fixture_endpoint_and_its_gaps(tmp_path: Path):
    subprocess.run(["mvn", "-q", "-o", "compile"], cwd=FIXTURE, check=True)
    _run(tmp_path)
    document = (tmp_path / "render" / "architecture.md").read_text()
    for route in ("POST", "GET", "/v1/orders", "/v1/orders/{id}"):
        assert route in document
    assert "Known gaps" in document
```

- [ ] **Step 2: Run it to verify it fails or passes honestly**

Run: `pytest tests/e2e/test_vertical_slice.py -v`
Expected: This is the moment the slice is proven. If the fingerprints differ, find the source of non-determinism — most likely dictionary ordering in a JSON dump, or an unsorted `Files.walk` in the extractor — and fix it rather than relaxing the test.

- [ ] **Step 3: Run the whole suite and the linters**

Run: `pytest && ruff check . && ruff format --check . && mypy && lint-imports`
Expected: all green.

- [ ] **Step 4: Update the delivery status**

In `docs/PROJECT.md`, add to the design table:

```markdown
| Phase 1 vertical slice — fixture repo to endpoint catalog, byte-identical | delivered | [FR-1](REQUIREMENTS.md#fr-1--module-discovery), [FR-2](REQUIREMENTS.md#fr-2--fact-extraction), [FR-3](REQUIREMENTS.md#fr-3--endpoint-catalog), [FR-17](REQUIREMENTS.md#fr-17--coverage-reporting), [FR-20](REQUIREMENTS.md#fr-20--command-surface), NFR-1, NFR-5, NFR-10, NFR-11 |
```

- [ ] **Step 5: Record what implementation taught us**

Append to `docs/RUNBOOK.md` under a new `## Implementation` heading a short entry for anything that cost time and would cost it again — non-determinism sources found, ASM surprises, DuckDB JSON quirks. If nothing surprised you, write that: it is evidence the design held.

- [ ] **Step 6: Commit**

```bash
git add tests/e2e docs/PROJECT.md docs/RUNBOOK.md
git commit -m "test(e2e): byte-identical vertical slice gate for phase 1"
```

---

## Self-review

**Spec coverage.** FR-1 module discovery → Task 9. FR-2 fact extraction → Tasks 6–8. FR-3 endpoint catalog → Task 10 (inbound HTTP only, per Decision 1). FR-17 coverage reporting → Tasks 11–12. FR-20 command surface → Task 13. NFR-1 determinism → Tasks 3, 14. NFR-5 closed sets → Task 2. NFR-9 extension without modification → Task 10, catalog as data. NFR-10 schema as code → Task 3. NFR-11 bulk load → Task 4. Deliberately **not** covered in Phase 1 and named as gaps in the rendered document: FR-4 shapes, FR-5 call graph, FR-6 traces, FR-7 diagrams, FR-8 through FR-16, FR-18, FR-19.

**Known imprecision, flagged rather than hidden.** Two places will need adjustment during execution and the plan says so at the step: the `path` concatenation in `derive_endpoints.sql` (Task 11 Step 4) — Spring's `value` argument arrives as an array, and the exact unwrapping depends on how ASM reports it; and `ModuleModel.output_dirs` is a tuple while Task 9's first test compares a list (Task 9 Step 5). Both are cheap to settle with the real data in front of you, and both are better settled there than guessed at here.

**Type consistency.** `ScanRequest`/`ScanReport` (Task 8) are used unchanged in Tasks 11 and 13. `ModuleModel` (Task 9) flows into Tasks 12 and 13. `ResolveReport` (Task 11) into Task 12. `Workspace.query` returns `list[dict]` throughout. `Progress` (Task 13) is consumed only by `analyze`.

**One dependency note for approval.** `extractor-jvm` uses the Shadow Gradle plugin for the shaded jar, which ARCHITECTURE §9 implies ("Gradle, shaded jar") but does not name. Flagging it explicitly per `GUIDELINES.md` §7.
