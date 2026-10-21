"""The `type_header` read (D00 §5), end to end on `fixtures/orders-advice`.

Both `@ControllerAdvice` rows COVERAGE marked "narrower than the framework's rule" had one
cause: the handled exception lived in a jar this workspace never scanned, so its hierarchy and
its `@ResponseStatus` were not in the facts. The fixture has two bare `@ExceptionHandler`
methods — exception type from the PARAMETER, the framework's own rule — whose parameter types
are both classes the module never compiled.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from fixture_build import FIXTURES, compile_fixture
from sextant.cli.app import cli
from sextant.domain.version import FACT_SCHEMA_VERSION, SEXTANT_VERSION
from sextant.resources import extractor_jar
from sextant.storage.duckdb.workspace import DuckDbWorkspace

ADVICE = FIXTURES / "orders-advice"


@pytest.fixture(scope="module")
def analysed(tmp_path_factory: pytest.TempPathFactory):
    """`(metadata, error_handlers, endpoints, documents)` for a private copy of the fixture."""
    compile_fixture(ADVICE)
    root = tmp_path_factory.mktemp("advice") / "orders-advice"
    shutil.copytree(ADVICE, root)
    result = CliRunner().invoke(cli, ["module", "analyze", str(root)])
    assert result.exit_code == 0, result.output
    rendered = CliRunner().invoke(cli, ["module", "render", str(root)])
    assert rendered.exit_code == 0, rendered.output
    metadata = json.loads((root / ".sextant" / "metadata.json").read_text(encoding="utf-8"))
    metadata["_document"] = (root / ".sextant" / "render" / "architecture.md").read_text(
        encoding="utf-8"
    )
    workspace = DuckDbWorkspace(root / ".sextant" / "workspace.duckdb")
    try:
        handlers = {
            str(row["handler"]).split("#")[-1].split("(")[0]: (
                str(row["exception"]).rsplit("/", 1)[-1],
                row["status"],
            )
            for row in workspace.query("error_handlers")
        }
        endpoints = [
            (str(r["direction"]), str(r["path"]), str(r["handler"]))
            for r in workspace.query("endpoints")
        ]
        documents = [
            (bool(r["header_only"]), str(r["relative_path"])) for r in workspace.query("documents")
        ]
    finally:
        workspace.close()
    return metadata, handlers, endpoints, documents


@pytest.mark.pins("storage.a-TYPE-HEADER-joins-the-superclass-walk")
def test_a_handler_parameter_from_two_jars_is_proven_a_throwable(analysed):
    """Row 2412's case. `invalid(MethodArgumentNotValidException e)` — bare annotation, so the
    exception is the parameter, and the chain to a declared root crosses TWO jars:

        MethodArgumentNotValidException  extends  BindException      (spring-web)
        BindException                    extends  Exception          (spring-context)

    Neither class is in the module's output. Before the header read the walk stopped at the
    first and this handler derived nothing from its parameter; now both headers are facts and
    the walk reaches `Exception`. `status` is None and that is CORRECT: Spring's class carries
    no `@ResponseStatus` (measured off the jar) and the handler declares none.
    """
    _, handlers, _, _ = analysed
    assert handlers["invalid"] == ("MethodArgumentNotValidException#", None)


@pytest.mark.pins("error_advice.a-STATUS-on-a-library-exception-class-is-read")
def test_a_response_status_on_a_dependency_exception_class_reaches_the_handler(analysed):
    """Row 2414's case. `conflict(ConflictingOrderException e)`: the class lives in the stub
    jar, which this module depends on WITHOUT opting in through `extract_libraries`, and it
    carries `@ResponseStatus(HttpStatus.CONFLICT)` on the class. Spring's own exceptions never
    do (measured), so a dependency jar is the only place this shape exists.

    The status arrives as the facts spell an enum reference, exactly as a module-local
    `@ResponseStatus` would — same producer, same grammar.
    """
    _, handlers, _, _ = analysed
    assert handlers["conflict"] == (
        "ConflictingOrderException#",
        "org/springframework/http/HttpStatus#CONFLICT.",
    )


@pytest.mark.pins("storage.a-HEADER-ONLY-document-is-not-a-document-read")
def test_the_header_document_is_counted_as_headers_not_as_documents(analysed):
    """`coverage.documents` means class files this module BUILT. The one synthetic document
    holding every header fact is not one — its path is the label `<classpath>` — so it is
    left out of `documents` and counted as `type_headers`. Two classes plus the module's own
    `module` document is three; the headers are their own number.
    """
    metadata, _, _, documents = analysed
    coverage = metadata["coverage"]
    assert coverage["documents"] == 3
    assert coverage["type_headers"] >= 3
    assert (True, "<classpath>") in documents


def test_a_dependency_type_mints_no_endpoint(analysed):
    """The reason `type_header` is a fact kind of its own rather than `symbol`/`annotation`
    facts: the row-minting engines read those, and a dependency's class-level
    `@RestController` or `CrudRepository` would otherwise become this module's routes. Here
    the only inbound row is the module's own controller.

    No `pins` marker: the property is structural (a different `kind` string) and no single
    conjunct produces it, so a guard invented for it would measure nothing.
    """
    _, _, endpoints, _ = analysed
    assert len(endpoints) == 1
    assert endpoints[0][1] == "/orders"
    assert "com/acme/advice/OrderController" in endpoints[0][2]


@pytest.mark.pins("render.the-document-SAYS-how-many-named-types-the-header-read-found")
def test_the_document_says_how_many_named_types_the_read_found_and_who_answered(analysed):
    """Spec 2026-10-21 §3e — the document is the result. The read reached 15 dependency
    types — the 8 this module's classes name, plus the supertypes it discovered from the
    headers it read — found the header of 10, and 5 were in no archive (the JDK's own:
    `Object`, `RuntimeException`, `Exception`, `Throwable`, `String`). The classpath they were
    looked up on was MAVEN's own resolved one — `fixture_build` primes the file, `copytree`
    keeps its time, so it is current here. Measured, not predicted: the same 15/10/5 came out
    of the declared set on this small fixture, which is why the LABEL is on the line — it is
    the only thing that tells a reader which classpath those numbers describe."""
    metadata, _, _, _ = analysed
    assert (
        "- Dependency types the header read reached: 15 — header read for 10, found in no "
        "dependency archive 5 (dependencies: resolved by the build tool)."
    ) in metadata["_document"]


@pytest.mark.pins("storage.the-UNLOCATED-count-is-read-off-the-header-document")
def test_the_unlocated_count_travels_on_the_header_document(analysed):
    metadata, _, _, _ = analysed
    assert metadata["coverage"]["type_headers"] == 10
    assert metadata["coverage"]["type_headers_unlocated"] == 5
    assert metadata["module"]["dependency_source"] == "maven"


def test_a_read_that_locates_nothing_is_still_a_document_saying_so(tmp_path: Path):
    """The header document is written whenever a classpath was handed over, with ZERO headers
    as readily as with ten: an EMPTY classpath file against this fixture's classes locates
    none of the 8 types the classes name, and the document says `0` read and `8` in no
    archive — 8 and not 15, because the other 7 are supertypes the walk only discovers from
    a header it managed to read. A missing file would leave "no read was attempted" and "the
    read found nothing" indistinguishable — on `yudao-module-system`'s declared set that is
    0 of 445, the number OI-167 was measured by."""
    compile_fixture(ADVICE)
    classpath = tmp_path / "empty.tsv"
    classpath.write_text("", encoding="utf-8")
    out = tmp_path / "facts"
    completed = subprocess.run(
        [
            "java",
            "-jar",
            str(extractor_jar()),
            "--module-id",
            "com.example:orders-advice",
            "--coordinates",
            "com.example/orders-advice",
            "--version",
            "1.0.0",
            "--classes",
            str(ADVICE / "target" / "classes"),
            "--out",
            str(out),
            "--fact-schema-version",
            str(FACT_SCHEMA_VERSION),
            "--sextant-version",
            SEXTANT_VERSION,
            "--classpath-file",
            str(classpath),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    report = json.loads(completed.stdout.strip().splitlines()[-1])
    assert report["type_headers"] == "0" or report["type_headers"] == 0
    assert int(report["type_headers_unlocated"]) == 8
    lines = (out / "__type_headers__.jsonl").read_text(encoding="utf-8").splitlines()
    document = json.loads(lines[0])
    assert document["header_only"] is True
    assert document["type_headers_unlocated"] == 8
    assert lines[1:] == []
