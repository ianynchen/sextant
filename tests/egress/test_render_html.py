"""`architecture.html` — the second serializer over Task 3's assembled
document (2K design §6b).

Reuses the fixtures `test_render_assembly.py` already built (the same
`MODULE`/`REPORT`, the same claim builders) rather than inventing a second
set: what is under test here is a second serializer over the SAME assembled
sections, and a second set of fixtures would leave that unchecked.
"""

import hashlib
from dataclasses import dataclass
from pathlib import Path

import pytest
from test_render_assembly import (
    MODULE,
    OPEN_QUESTIONS,
    REPORT,
    _component,
    _diagram,
    _overlay,
    _section,
    _verdict,
)

from sextant.egress.render.asset_pins import MERMAID_SHA256, MERMAID_VERSION
from sextant.egress.render.document import EnrichmentSection, assemble_module_document
from sextant.egress.render.html import html_document

ASSETS_DIR = Path(__file__).parents[2] / "src" / "sextant" / "egress" / "render" / "assets"
MERMAID_JS = (ASSETS_DIR / "mermaid.min.js").read_text(encoding="utf-8")
PANZOOM_JS = (ASSETS_DIR / "panzoom.js").read_text(encoding="utf-8")


# --- asset provenance (2K design §6b: pinned like a dependency) -----------


def test_the_vendored_mermaid_asset_matches_its_pinned_hash():
    """A swap of `assets/mermaid.min.js` for a different version — or a
    different library entirely — under the same file name must fail loudly
    here rather than silently shipping different rendering behaviour."""
    digest = hashlib.sha256((ASSETS_DIR / "mermaid.min.js").read_bytes()).hexdigest()
    assert digest == MERMAID_SHA256


def test_the_license_file_names_the_pinned_version_and_hash():
    license_text = (ASSETS_DIR / "LICENSE-mermaid").read_text(encoding="utf-8")
    assert MERMAID_VERSION in license_text
    assert MERMAID_SHA256 in license_text


# --- self-contained, offline, no CDN ---------------------------------------


def test_the_vendored_assets_are_inlined_exactly_once():
    """Self-contained (2K design §6b): the library and Sextant's own pan-zoom
    script each appear in the page's own bytes exactly once, however many
    diagrams the document draws — never fetched, never duplicated per
    diagram."""
    sections = assemble_module_document(MODULE, REPORT, "a3f91c")
    document = html_document(sections)
    assert document.count(MERMAID_JS) == 1
    assert document.count(PANZOOM_JS) == 1


def test_no_cdn_or_external_script_url_appears_anywhere():
    """The document must open airgapped (2K design §6b) — no `<script src=`
    at all, and none of the hosts a CDN build would have used."""
    sections = assemble_module_document(MODULE, REPORT, "a3f91c")
    document = html_document(sections)
    assert "<script src=" not in document
    for host in ("cdn.jsdelivr.net", "unpkg.com", "cdnjs.cloudflare.com"):
        assert host not in document


# --- diagrams, wrapped alike -------------------------------------------


def test_every_diagram_is_wrapped_with_pan_zoom_controls():
    """Machine and LLM-simplified diagrams alike (2K design §6b): the
    machine `## Structure` diagram REPORT's shapes produce, plus the claim's
    own `DiagramClaim`, both carry the three controls."""
    sections = assemble_module_document(MODULE, REPORT, "a3f91c", overlay=_overlay(_diagram()))
    document = html_document(sections)
    assert document.count('class="diagram"') == 2
    assert document.count('class="diagram-zoom-in"') == 2
    assert document.count('class="diagram-zoom-out"') == 2
    assert document.count('class="diagram-reset"') == 2
    assert document.count('class="mermaid"') == 2


def test_the_page_initializes_mermaid_against_the_pre_class():
    sections = assemble_module_document(MODULE, REPORT, "a3f91c")
    document = html_document(sections)
    assert 'querySelector: ".mermaid"' in document


def test_diagram_source_is_escaped_without_being_corrupted():
    """`mermaid`'s client-side `run()` reads the element's decoded text
    content, so escaping the source for HTML must not change what a reader —
    or mermaid — sees once the browser parses it back out."""
    claim = _diagram()
    claim["mermaid"] = "classDiagram\n    class A\n    A --> B : uses <T> & more\n"
    sections = assemble_module_document(MODULE, REPORT, "a3f91c", overlay=_overlay(claim))
    document = html_document(sections)
    assert "uses &lt;T&gt; &amp; more" in document
    assert "uses <T> & more" not in document


# --- machine and enrichment sections, the badge -----------------------


def test_machine_prose_appears_in_the_document():
    sections = assemble_module_document(MODULE, REPORT, "a3f91c", open_questions=OPEN_QUESTIONS)
    document = html_document(sections)
    assert "## Structure" in document
    assert "## Open questions" in document


def test_a_visible_badge_marks_every_enrichment_block():
    """ "Add-only, clearly marked" (2K design §6): a reader must see the badge
    before the words, not only a heading that is easy to skim past."""
    sections = assemble_module_document(MODULE, REPORT, "a3f91c", overlay=_overlay(_component()))
    document = html_document(sections)
    assert '<span class="llm-badge">LLM</span>' in document
    assert "Enrichment — evidence: llm" in document
    assert "Component: Ingestion edge" in document


def test_each_claim_kind_renders_in_html_as_what_it_is():
    sections = assemble_module_document(
        MODULE,
        REPORT,
        "a3f91c",
        open_questions=OPEN_QUESTIONS,
        overlay=_overlay(_component(), _section(), _diagram(), _verdict()),
    )
    document = html_document(sections)
    assert "Members: <code>com/acme/orders/Ingest#</code>" in document
    assert "Extending the edge" in document
    assert "Cites: <code>src/main/java/com/acme/orders/Ingest.java</code>" in document
    assert "Elides: showing 1 of 40 classes; error paths elided" in document
    assert "LLM assessment" in document
    assert "likely `com/acme/A#`" in document


def test_the_stale_notice_renders_with_its_own_badge_and_sentence():
    sections = assemble_module_document(
        MODULE,
        REPORT,
        "a3f91c",
        overlay=_overlay(_component(), _section()),
        stale=frozenset({1}),
    )
    document = html_document(sections)
    assert "1 enrichment claim stale, not shown." in document
    assert document.count('<span class="llm-badge">LLM</span>') == 2


# --- escaping ------------------------------------------------------------


def test_prose_containing_html_special_characters_is_escaped_not_executed():
    leaky = _component(name="<script>alert(1)</script>")
    sections = assemble_module_document(MODULE, REPORT, "a3f91c", overlay=_overlay(leaky))
    document = html_document(sections)
    assert "<script>alert(1)</script>" not in document
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in document


# --- determinism (NFR-1) --------------------------------------------------


def test_rendering_the_same_sections_twice_is_byte_identical():
    sections = assemble_module_document(
        MODULE,
        REPORT,
        "a3f91c",
        open_questions=OPEN_QUESTIONS,
        overlay=_overlay(_component(), _diagram(), _verdict(), _section()),
    )
    assert html_document(sections) == html_document(sections)


# --- the serializer's own edges: a hard error, never a skip ---------------


@dataclass(frozen=True)
class _UnknownSection:
    """Stands in for a section kind this emitter has fallen behind — never a
    real member of `document.Section`, which is exactly the point."""


def test_an_unrecognized_section_kind_is_a_hard_error_not_a_skip():
    with pytest.raises(ValueError, match="no rendering rule"):
        html_document((_UnknownSection(),))  # type: ignore[arg-type]


def test_an_unrecognized_claim_kind_is_a_hard_error_not_a_skip():
    provenance = _overlay(_component()).produced_by
    with pytest.raises(ValueError, match="no rendering rule"):
        html_document((EnrichmentSection(provenance, (object(),)),))  # type: ignore[arg-type]
