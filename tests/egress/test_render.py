import json
from pathlib import Path

from sextant.application.ports.detector import ModuleModel
from sextant.application.resolve.pipeline import ResolveReport
from sextant.egress.render.document import _GAPS, render_module_document
from sextant.egress.render.metadata import PHASE_1_GAPS, write_metadata

MODULE = ModuleModel(
    module_id="com.acme:orders-service",
    coordinates="com.acme/orders-service",
    version="1.0.0",
    root=Path("fixtures/orders-service"),
    kind="service",
    languages=frozenset({"java"}),
    source_roots=(),
    output_dirs=(),
)
REPORT = ResolveReport(
    facts_loaded=42,
    endpoints=[
        {
            "protocol": "http",
            "direction": "inbound",
            "method": "GET",
            "path": "/v1/orders",
            "handler": "s maven c 1 com/acme/C#list().",
            "resolution": "resolved",
            "evidence": "compiler",
        }
    ],
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


def test_every_machine_readable_gap_has_a_sentence_a_person_can_read():
    """`metadata.json` lists gap keys and the document lists gap sentences, and
    the two are kept in correspondence by a comment alone. A key with no
    sentence is a gap the machine reports and the reader never sees — which is
    a document that reads as complete when it is not (M07)."""
    assert len(PHASE_1_GAPS) == len(_GAPS)
