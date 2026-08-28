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


def test_fact_files_land_beside_their_sources_when_the_output_path_contains_java(
    tmp_path: Path,
):
    """A path is not a file extension. Swapping `.java` for `.jsonl` with a
    global substring replace rewrites every occurrence, so a workspace whose
    own directory happens to hold `.java` had its output paths corrupted
    mid-string — facts written somewhere nobody would look for them."""
    out = tmp_path / "work.java" / "facts"
    AsmScanner(JAR).scan(ScanRequest(
        module_id="com.acme:orders", coordinates="com.acme/orders", version="1.0.0",
        classes_dir=CLASSES, out_dir=out,
    ))
    assert sorted(p.name for p in out.rglob("*.jsonl")) == [
        "OrderCommand.jsonl", "OrderController.jsonl",
        "OrderResult.jsonl", "OrderService.jsonl",
    ]
