"""`architecture.html` — the second serializer over Task 3's assembled
document (2K design §6b).

Reuses the fixtures `test_render_assembly.py` already built (the same
`MODULE`/`REPORT`, the same claim builders) rather than inventing a second
set: what is under test here is a second serializer over the SAME assembled
sections, and a second set of fixtures would leave that unchecked.
"""

import hashlib
import json
import re
from dataclasses import dataclass
from importlib import resources

import pytest
from test_render_assembly import (
    GOLDEN_MODULE,
    GOLDEN_REPORT,
    GOLDEN_SHAPE_FIELDS,
    MODULE,
    OPEN_QUESTIONS,
    REPORT,
    _claim,
    _component,
    _config_verdict,
    _diagram,
    _overlay,
    _section,
    _verdict,
)

from sextant.application.resolve.pipeline import ResolveReport
from sextant.egress.render.asset_pins import MERMAID_SHA256, MERMAID_VERSION
from sextant.egress.render.document import (
    DetailEntry,
    EnrichmentSection,
    MachineDetail,
    MachineHeading,
    MachineSection,
    _code,
    assemble_module_document,
)
from sextant.egress.render.html import _STYLE, html_document

# Read through the same `importlib.resources` mechanism `html._asset` uses
# (fix M-11) rather than a path relative to this file — the two must hash
# the same bytes under an editable install, and only `resources.files`
# resolves correctly under a non-editable one too: the test should hash what
# actually ships, not a source-tree path that happens to coincide with it
# today.
_ASSETS = resources.files("sextant.egress.render") / "assets"
MERMAID_JS = (_ASSETS / "mermaid.min.js").read_text(encoding="utf-8")
PANZOOM_JS = (_ASSETS / "panzoom.js").read_text(encoding="utf-8")


def _html(sections, module_id: str = MODULE.module_id) -> str:
    return html_document(sections, module_id)


# --- asset provenance (2K design §6b: pinned like a dependency) -----------


def test_the_vendored_mermaid_asset_matches_its_pinned_hash():
    """A swap of `assets/mermaid.min.js` for a different version — or a
    different library entirely — under the same file name must fail loudly
    here rather than silently shipping different rendering behaviour."""
    digest = hashlib.sha256((_ASSETS / "mermaid.min.js").read_bytes()).hexdigest()
    assert digest == MERMAID_SHA256


def test_the_license_file_names_the_pinned_version_and_hash():
    license_text = (_ASSETS / "LICENSE-mermaid").read_text(encoding="utf-8")
    assert MERMAID_VERSION in license_text
    assert MERMAID_SHA256 in license_text


# --- self-contained, offline, no CDN ---------------------------------------


def test_the_vendored_assets_are_inlined_exactly_once():
    """Self-contained (2K design §6b): the library and Sextant's own pan-zoom
    script each appear in the page's own bytes exactly once, however many
    diagrams the document draws — never fetched, never duplicated per
    diagram."""
    sections = assemble_module_document(MODULE, REPORT, "a3f91c")
    document = _html(sections)
    assert document.count(MERMAID_JS) == 1
    assert document.count(PANZOOM_JS) == 1


def test_no_cdn_or_external_script_url_appears_anywhere():
    """The document must open airgapped (2K design §6b) — no `<script src=`
    at all, and none of the hosts a CDN build would have used."""
    sections = assemble_module_document(MODULE, REPORT, "a3f91c")
    document = _html(sections)
    assert "<script src=" not in document
    for host in ("cdn.jsdelivr.net", "unpkg.com", "cdnjs.cloudflare.com"):
        assert host not in document


def test_an_asset_containing_a_closing_script_tag_is_refused_loudly():
    """M-5: every asset is inlined verbatim between `<script>`/`</script>`
    tags, so a future version bump that happens to embed `</script` would
    silently break the page rather than the diagram library — refused at the
    point of inlining instead. Exercised against the guard directly, rather
    than a real file swapped in for the test, so it needs no fixture asset of
    its own."""
    from sextant.egress.render.html import _refused_if_unsafe_to_inline

    with pytest.raises(ValueError, match=r"</script"):
        _refused_if_unsafe_to_inline("poisoned.js", "var x = 1; </SCRIPT><script>alert(1)")
    # The ordinary case goes through untouched.
    assert _refused_if_unsafe_to_inline("clean.js", "var x = 1;") == "var x = 1;"


# --- the page title (M-6) --------------------------------------------------


def test_the_title_carries_the_module_id():
    sections = assemble_module_document(MODULE, REPORT, "a3f91c")
    document = _html(sections, module_id="com.acme:orders-service")
    assert "<title>Sextant — com.acme:orders-service</title>" in document


def test_the_title_escapes_the_module_id():
    sections = assemble_module_document(MODULE, REPORT, "a3f91c")
    document = _html(sections, module_id="<script>alert(1)</script>")
    assert "<title>Sextant — &lt;script&gt;alert(1)&lt;/script&gt;</title>" in document


# --- diagrams, wrapped alike -------------------------------------------


def test_every_diagram_is_wrapped_with_pan_zoom_controls():
    """Machine and LLM-simplified diagrams alike (2K design §6b): the
    machine `## Structure` diagram REPORT's shapes produce, plus the claim's
    own `DiagramClaim`, both carry the three controls."""
    sections = assemble_module_document(MODULE, REPORT, "a3f91c", overlay=_overlay(_diagram()))
    document = _html(sections)
    assert document.count('class="diagram"') == 2
    assert document.count('class="diagram-zoom-in"') == 2
    assert document.count('class="diagram-zoom-out"') == 2
    assert document.count('class="diagram-reset"') == 2
    assert document.count('class="mermaid"') == 2


def test_the_page_initializes_mermaid_against_the_pre_class():
    sections = assemble_module_document(MODULE, REPORT, "a3f91c")
    document = _html(sections)
    assert 'querySelector: ".mermaid"' in document


def test_diagram_source_is_escaped_without_being_corrupted():
    """`mermaid`'s client-side `run()` reads the element's decoded text
    content, so escaping the source for HTML must not change what a reader —
    or mermaid — sees once the browser parses it back out."""
    claim = _diagram()
    claim["mermaid"] = "classDiagram\n    class A\n    A --> B : uses <T> & more\n"
    sections = assemble_module_document(MODULE, REPORT, "a3f91c", overlay=_overlay(claim))
    document = _html(sections)
    assert "uses &lt;T&gt; &amp; more" in document
    assert "uses <T> & more" not in document


def test_the_render_announcement_reaches_panzoom_across_the_ordering_race():
    """The fit-to-viewport handshake (field defect: a 2500px-wide diagram
    painted at the SVG's 300px default in a corner). mermaid's completion is
    announced with a FLAG and an EVENT because promise microtasks can run
    between two DOMContentLoaded handlers — panzoom may set up before or
    after the announcement, and must catch it either way."""
    sections = assemble_module_document(MODULE, REPORT, "a3f91c")
    document = _html(sections)
    assert "window.sextantDiagramsRendered = true;" in document
    assert 'new Event("sextant:diagrams-rendered")' in document
    assert "if (window.sextantDiagramsRendered)" in PANZOOM_JS
    assert 'addEventListener("sextant:diagrams-rendered", fit)' in PANZOOM_JS


def test_the_initial_view_fits_and_centers_and_reset_returns_there():
    """fit() reads the diagram's natural size off its own viewBox (mermaid's
    width="100%" against a max-content canvas resolves to the 300px SVG
    default — the crowded-corner defect), pins the SVG to real pixels, scales
    DOWN to fit (never up), centers, and makes that the home reset() restores."""
    assert "function fit(" in PANZOOM_JS
    assert "svg.viewBox.baseVal" in PANZOOM_JS
    assert 'svg.style.maxWidth = "none"' in PANZOOM_JS
    # scale caps at 1: a small diagram is centered at natural size, not blown up
    assert "1,\n" in PANZOOM_JS or "          1," in PANZOOM_JS
    # reset restores the computed home, not the identity transform
    assert "scale = homeScale;" in PANZOOM_JS


# --- panzoom.js: the wheel convention and drag safety (I-2, M-2, M-3) -----


def test_a_plain_wheel_is_never_prevented():
    """I-2: a plain wheel over a diagram must scroll the page — the handler
    returns before calling `preventDefault` unless ctrl or cmd is held."""
    match = re.search(r'addEventListener\(\s*"wheel".*?\);\n\s*\},', PANZOOM_JS, re.DOTALL)
    assert match is not None
    body = match.group(0)
    assert "event.ctrlKey" in body
    assert "event.metaKey" in body
    guard = re.search(r"if \(!event\.ctrlKey && !event\.metaKey\) \{\s*return;", body)
    assert guard is not None, "plain wheel must return before any preventDefault"
    assert body.index(guard.group(0)) < body.index("preventDefault")


def test_zoom_is_anchored_at_a_point_not_the_origin():
    """M-2: the transform's translate is corrected by the scale ratio so the
    point under the cursor (or the viewport center, for the buttons) stays
    put — never a bare `transform-origin: 0 0` zoom."""
    assert "function zoomAt(" in PANZOOM_JS
    assert "getBoundingClientRect" in PANZOOM_JS
    assert "zoomAtCenter" in PANZOOM_JS


def test_a_pan_drag_does_not_start_a_text_selection():
    """M-3: `preventDefault` on `mousedown` stops a drag over the rendered
    SVG's text nodes from starting a native selection; the CSS side
    (`user-select: none`) is pinned separately below."""
    match = re.search(r'addEventListener\("mousedown".*?\}\);', PANZOOM_JS, re.DOTALL)
    assert match is not None
    assert "preventDefault" in match.group(0)


def test_the_diagram_viewport_disables_native_text_selection():
    sections = assemble_module_document(MODULE, REPORT, "a3f91c")
    document = _html(sections)
    assert "user-select: none" in document


# --- typed machine sections render real structure (2M design §5b) --------


def test_the_fixture_workspace_assembles_with_zero_untyped_machine_sections():
    """The emitter test the spec calls for by name: a document that exercises
    every region the assembler cuts at (the golden fixture — a structure
    diagram, both endpoint tables, an open question, the gap lists, a skipped
    catalog) carries no `MachineSection` at all. `MachineSection` is the
    escape hatch left behind for machine text with no typed shape of its own
    (`document.MachineSection`'s own docstring); a real document reaching it
    would be exactly the "0 headings, 0 tables" defect this task fixes."""
    sections = assemble_module_document(
        GOLDEN_MODULE,
        GOLDEN_REPORT,
        "0d17e2",
        ("com/example/golden/Newer.class: metadata unreadable",),
        shape_fields=GOLDEN_SHAPE_FIELDS,
        open_questions=OPEN_QUESTIONS,
    )
    assert not any(isinstance(section, MachineSection) for section in sections)


def test_every_markdown_heading_becomes_its_own_html_heading():
    """`<h2>` per `##`, `<h1>` for the module title — the golden fixture's own
    seven `##` sections (Coverage, Structure, Inbound endpoints, Outbound
    endpoints, Open questions, Known gaps, Catalogs skipped), pinned by count
    against the same golden markdown this fixture is proven byte-identical to
    (`test_render_assembly.test_a_module_with_no_overlay_renders_the_checked_in_golden_document`)."""
    sections = assemble_module_document(
        GOLDEN_MODULE,
        GOLDEN_REPORT,
        "0d17e2",
        ("com/example/golden/Newer.class: metadata unreadable",),
        shape_fields=GOLDEN_SHAPE_FIELDS,
        open_questions=OPEN_QUESTIONS,
    )
    document = _html(sections, module_id=GOLDEN_MODULE.module_id)
    # Scoped to the document's own body, before the vendored mermaid script:
    # the pinned asset's own minified text happens to contain a literal
    # `"## "` (an unrelated string constant), which is not this renderer's
    # markdown leaking through — and, coincidentally, no `<h1>`/`<h2>` of its
    # own, but the count assertions are scoped too now rather than relying on
    # that coincidence (fix round 1, MINOR 9).
    body = document.split("<script>", 1)[0]
    assert body.count("<h1>") == 1
    assert body.count("<h2>") == 7
    assert "## " not in body


def test_the_endpoint_table_is_a_real_table_with_one_row_per_endpoint():
    """A real `<table>`, not a `<pre>` a reader has to squint at — one
    `<tbody>` row per endpoint the golden fixture's report carries: one
    inbound, one outbound (spec §5b/§7's "HTML table/heading presence for the
    fixture" pin)."""
    sections = assemble_module_document(
        GOLDEN_MODULE,
        GOLDEN_REPORT,
        "0d17e2",
        shape_fields=GOLDEN_SHAPE_FIELDS,
    )
    document = _html(sections, module_id=GOLDEN_MODULE.module_id)
    # Scoped before the vendored mermaid script, which happens to contain one
    # unrelated `<table>` literal of its own (an HTML template string buried
    # in the library, not this renderer's output).
    body = document.split("<script>", 1)[0]
    assert body.count("<table>") == 2
    inbound_body = re.search(
        r"<h2>Inbound endpoints</h2>.*?<tbody>(.*?)</tbody>", document, re.DOTALL
    )
    outbound_body = re.search(
        r"<h2>Outbound endpoints</h2>.*?<tbody>(.*?)</tbody>", document, re.DOTALL
    )
    assert inbound_body is not None and outbound_body is not None
    assert inbound_body.group(1).count("<tr>") == 1
    assert outbound_body.group(1).count("<tr>") == 1
    # The identity column is a code run, typeset as `<code>`, never plain text
    # a reader could mistake for prose.
    assert "<td><code>GET /v1/orders</code></td>" in document
    assert "<td><code>POST /billing/invoices</code></td>" in document


def test_an_endpoint_detail_renders_as_a_definition_block_with_a_nested_table():
    """`MachineDetail`'s HTML shape (fix round 1, IMPORTANT 2): the block's
    own header renders OUTSIDE the definition list as its own
    `<p class="detail-identity">`, never a sibling `<dt>` beside `Request`/
    `Response` where the content model would read the identity as just
    another name for the same table.

    2M §5c moved WHAT the header names: the full handler symbol, not the
    wire identity — and a `Request` whose payload is a NAMED shape with
    recorded fields no longer nests its own table here at all; it links to
    the shape's own entry under `### Shapes`, where the real `<table>` now
    lives exactly once (`test_a_named_shape_is_linked_from_its_endpoint_and_
    declared_once_under_shapes` below pins that block directly)."""
    report = ResolveReport(
        facts_loaded=1,
        endpoints=[
            {
                "protocol": "http",
                "direction": "inbound",
                "method": "POST",
                "path": "/v1/orders",
                "handler": "s maven c 1 com/acme/C#create().",
                "resolution": "resolved",
                "request_shape": json.dumps(
                    {
                        "wire_type": "object",
                        "wire_format": "",
                        "nullable": False,
                        "shape_id": "com/acme/orders/contracts/OrderRequest#",
                    }
                ),
            }
        ],
        coverage={"documents": 1, "partial_documents": 0},
    )
    shape_fields = [
        {
            "shape_id": "com/acme/orders/contracts/OrderRequest#",
            "ordinal": 0,
            "wire_name": "customer_id",
            "wire_type": "string",
            "wire_format": None,
            "field_number": None,
            "required": True,
            "nullable": False,
            "item": None,
        }
    ]
    sections = assemble_module_document(MODULE, report, "a3f91c", shape_fields=shape_fields)
    document = _html(sections)
    # Fix round 1, MEDIUM 1: the header carries BOTH the wire identity and
    # the full symbol, joined by " — " — one convention for inbound and
    # outbound alike, so a handler-less block still names its own endpoint.
    assert (
        '<p class="detail-identity"><code>POST /v1/orders</code> — '
        '<code>com/acme/C#create().</code></p><dl class="detail">'
    ) in document
    assert '<dt>Request</dt><dd><a href="#shape-OrderRequest">OrderRequest</a></dd>' in document
    assert "<td>customer_id</td>" in document
    assert "<td>string</td>" in document
    # The identity never leaks into the list itself as a `<dt>` of its own.
    assert "<dt><code>com/acme/C#create().</code></dt>" not in document


def test_a_named_shape_is_linked_from_its_endpoint_and_declared_once_under_shapes():
    """The `### Shapes` subsection itself: its own header carries the `id`
    a `shaperef` link targets, and the field table renders exactly once,
    under `<h3>Shapes</h3>` — never re-nested under the endpoint's own
    `Request`/`Response` entry (2M design §5c)."""
    report = ResolveReport(
        facts_loaded=1,
        endpoints=[
            {
                "protocol": "http",
                "direction": "inbound",
                "method": "POST",
                "path": "/v1/orders",
                "handler": "s maven c 1 com/acme/C#create().",
                "resolution": "resolved",
                "request_shape": json.dumps(
                    {
                        "wire_type": "object",
                        "wire_format": "",
                        "nullable": False,
                        "shape_id": "com/acme/orders/contracts/OrderRequest#",
                    }
                ),
            }
        ],
        coverage={"documents": 1, "partial_documents": 0},
    )
    shape_fields = [
        {
            "shape_id": "com/acme/orders/contracts/OrderRequest#",
            "ordinal": 0,
            "wire_name": "customer_id",
            "wire_type": "string",
            "wire_format": None,
            "field_number": None,
            "required": True,
            "nullable": False,
            "item": None,
        }
    ]
    sections = assemble_module_document(MODULE, report, "a3f91c", shape_fields=shape_fields)
    document = _html(sections)
    assert "<h3>Shapes</h3>" in document
    assert '<p class="detail-identity" id="shape-OrderRequest"><code>OrderRequest</code></p>' in (
        document
    )
    assert document.count("<td>customer_id</td>") == 1


def test_two_shapes_sharing_a_simple_name_get_distinct_anchors_and_links():
    """Fix round 1, MEDIUM 2: `shape-Order` twice would be an invalid,
    duplicate HTML id, and a citation's own link could no longer promise
    which of the two tables it lands on. Once `com/a/Order#` and
    `com/b/Order#` collide on the simple name `Order`, each disambiguates to
    its own full id (`document._disambiguated_shape_names`), which is what
    both the anchor and the display text are built from — so the two ids
    differ, and each citation's href targets the one table that actually
    carries its own field."""
    descriptor_a = json.dumps(
        {"wire_type": "object", "wire_format": "", "nullable": False, "shape_id": "com/a/Order#"}
    )
    descriptor_b = json.dumps(
        {"wire_type": "object", "wire_format": "", "nullable": False, "shape_id": "com/b/Order#"}
    )
    report = ResolveReport(
        facts_loaded=2,
        endpoints=[
            {
                "protocol": "http",
                "direction": "inbound",
                "method": "GET",
                "path": "/a/orders",
                "handler": "s maven c 1 com/acme/C#a().",
                "resolution": "resolved",
                "response_shape": descriptor_a,
            },
            {
                "protocol": "http",
                "direction": "inbound",
                "method": "GET",
                "path": "/b/orders",
                "handler": "s maven c 1 com/acme/C#b().",
                "resolution": "resolved",
                "response_shape": descriptor_b,
            },
        ],
        coverage={"documents": 1, "partial_documents": 0},
    )
    shape_fields = [
        {
            "shape_id": "com/a/Order#",
            "ordinal": 0,
            "wire_name": "a_field",
            "wire_type": "string",
            "wire_format": None,
            "field_number": None,
            "required": True,
            "nullable": False,
            "item": None,
        },
        {
            "shape_id": "com/b/Order#",
            "ordinal": 0,
            "wire_name": "b_field",
            "wire_type": "string",
            "wire_format": None,
            "field_number": None,
            "required": True,
            "nullable": False,
            "item": None,
        },
    ]
    sections = assemble_module_document(MODULE, report, "a3f91c", shape_fields=shape_fields)
    document = _html(sections)
    assert document.count('id="shape-com-a-Order"') == 1
    assert document.count('id="shape-com-b-Order"') == 1
    assert '<a href="#shape-com-a-Order">com/a/Order</a>' in document
    assert '<a href="#shape-com-b-Order">com/b/Order</a>' in document
    a_section = document.split('id="shape-com-a-Order"', 1)[1].split('id="shape-com-b-Order"', 1)[0]
    assert "<td>a_field</td>" in a_section
    assert "<td>b_field</td>" not in a_section


def test_qname_shapes_colliding_only_after_sanitizing_get_distinct_anchors_too():
    """2M Task 7 ride-along: `{uri}order.request` and `{uri}order-request`
    read as two DIFFERENT display names (`order.request` != `order-request`),
    so MEDIUM 2's fix — which grouped on display-name EQUALITY — never
    caught this collision at all: `_shape_anchor_id` replaces the dot with
    `-` the same character the hyphen already is, so both sanitize to the
    identical `shape-order-request`. Disambiguation now groups on the
    SANITIZED anchor id instead, catching this pair — and since even their
    own full ids collide the same way once sanitized (the `{uri}` prefix and
    the dot-vs-hyphen both wash out identically), a second disambiguation
    level breaks the tie so each still gets its own anchor and its own
    citation link, never a duplicate, invalid HTML id."""
    descriptor_dot = json.dumps(
        {
            "wire_type": "object",
            "wire_format": "",
            "nullable": False,
            "shape_id": "{uri}order.request",
        }
    )
    descriptor_dash = json.dumps(
        {
            "wire_type": "object",
            "wire_format": "",
            "nullable": False,
            "shape_id": "{uri}order-request",
        }
    )
    report = ResolveReport(
        facts_loaded=2,
        endpoints=[
            {
                "protocol": "http",
                "direction": "inbound",
                "method": "GET",
                "path": "/dot/orders",
                "handler": "s maven c 1 com/acme/C#a().",
                "resolution": "resolved",
                "response_shape": descriptor_dot,
            },
            {
                "protocol": "http",
                "direction": "inbound",
                "method": "GET",
                "path": "/dash/orders",
                "handler": "s maven c 1 com/acme/C#b().",
                "resolution": "resolved",
                "response_shape": descriptor_dash,
            },
        ],
        coverage={"documents": 1, "partial_documents": 0},
    )
    shape_fields = [
        {
            "shape_id": "{uri}order.request",
            "ordinal": 0,
            "wire_name": "dot_field",
            "wire_type": "string",
            "wire_format": None,
            "field_number": None,
            "required": True,
            "nullable": False,
            "item": None,
        },
        {
            "shape_id": "{uri}order-request",
            "ordinal": 0,
            "wire_name": "dash_field",
            "wire_type": "string",
            "wire_format": None,
            "field_number": None,
            "required": True,
            "nullable": False,
            "item": None,
        },
    ]
    sections = assemble_module_document(MODULE, report, "a3f91c", shape_fields=shape_fields)
    document = _html(sections)
    ids = re.findall(r'id="(shape-[^"]+)"', document)
    assert len(ids) == 2
    assert len(set(ids)) == 2, f"anchors collided: {ids!r}"
    dot_id, dash_id = ids
    assert f'<a href="#{dot_id}">' in document
    assert f'<a href="#{dash_id}">' in document
    dot_section = document.split(f'id="{dot_id}"', 1)[1].split(f'id="{dash_id}"', 1)[0]
    assert "<td>dot_field</td>" in dot_section
    assert "<td>dash_field</td>" not in dot_section


def test_a_header_only_detail_block_renders_as_just_the_identity_paragraph():
    """The orphan-`<dt>` case IMPORTANT 2 also fixes: a `MachineDetail` whose
    entries are ONLY the bare header (now reachable directly — 2M §5c makes
    every endpoint emit one, even with nothing else to say) renders as the
    `<p>` alone — never an empty `<dl class="detail"></dl>` sitting under
    it."""
    detail = MachineDetail((DetailEntry(_code("GET /v1/orders"), None, None),))
    document = _html((detail,))
    body = document.split("<script>", 1)[0]
    assert body.endswith('<p class="detail-identity"><code>GET /v1/orders</code></p>\n')
    assert "<dl" not in body


def test_a_detail_block_with_no_entries_at_all_is_a_domain_worded_error():
    """`assemble_module_document` never builds a `MachineDetail` with zero
    entries — every block it produces carries at least its own header — but
    the html emitter is not this module's alone to trust blind (2M §5c ride-
    along): `header, *rest = ()` would otherwise raise Python's own generic
    unpacking error, naming neither the section nor what is missing from
    it."""
    with pytest.raises(ValueError, match="no entries"):
        _html((MachineDetail(()),))


def test_enrichment_sections_render_unchanged_alongside_typed_machine_structure():
    """The typed-section refactor touches only the machine half: an
    enrichment block sitting beside a real `<table>`/`<h2>` still carries its
    badge and its claim text exactly as the pre-existing enrichment pins
    already prove in isolation — checked here TOGETHER, so a future change to
    machine typing that somehow broke the enrichment path would fail beside
    the structure it broke, not in a separate file that might not be run."""
    sections = assemble_module_document(
        GOLDEN_MODULE,
        GOLDEN_REPORT,
        "0d17e2",
        shape_fields=GOLDEN_SHAPE_FIELDS,
        overlay=_overlay(_component()),
    )
    document = _html(sections, module_id=GOLDEN_MODULE.module_id)
    assert "<h2>Inbound endpoints</h2>" in document
    assert "<table>" in document
    assert '<span class="llm-badge">LLM</span>' in document
    assert "Component: Ingestion edge" in document


def test_machine_prose_appears_in_the_document():
    """2M design §5b: a machine heading is real markup now, not markdown text
    escaped into a `<pre>` — so the section reads as `<h2>Structure</h2>`,
    never the literal `## Structure` a reader would have had to already know
    markdown to recognize."""
    sections = assemble_module_document(MODULE, REPORT, "a3f91c", open_questions=OPEN_QUESTIONS)
    document = _html(sections)
    assert "<h2>Structure</h2>" in document
    assert "<h2>Open questions</h2>" in document
    assert "## Structure" not in document


def test_a_visible_badge_marks_every_enrichment_block():
    """ "Add-only, clearly marked" (2K design §6): a reader must see the badge
    before the words, not only a heading that is easy to skim past."""
    sections = assemble_module_document(MODULE, REPORT, "a3f91c", overlay=_overlay(_component()))
    document = _html(sections)
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
    document = _html(sections)
    assert "Members: <code>com/acme/orders/Ingest#</code>" in document
    assert "Extending the edge" in document
    assert "Cites: <code>src/main/java/com/acme/orders/Ingest.java</code>" in document
    assert "Elides: showing 1 of 40 classes; error paths elided" in document
    assert "LLM assessment" in document
    assert "likely `com/acme/A#`" in document


def test_an_unanswered_verdict_renders_as_the_honest_answer_it_is():
    """M-4: the markdown emitter already has this pin
    (`test_render_assembly.test_an_unanswered_verdict_renders_as_the_honest_answer_it_is`);
    the HTML emitter takes the `searched` branch through its own `assert`,
    not `because`, and that branch had no test of its own until now."""
    unanswered = _claim(
        "verdict",
        "beside-open-question",
        question={
            "protocol": "sqs",
            "method": None,
            "path": "order-intake",
            "kind": "payload_binding",
        },
        assessment="unanswered",
        searched="read every listener; none names a payload type",
    )
    sections = assemble_module_document(
        MODULE, REPORT, "a3f91c", open_questions=OPEN_QUESTIONS, overlay=_overlay(unanswered)
    )
    document = _html(sections)
    assert (
        "LLM assessment</strong> for <code>sqs order-intake</code> (payload_binding): "
        "unanswered — searched: read every listener; none names a payload type"
    ) in document


def test_a_config_shaped_verdict_renders_in_html_too():
    """2N design §2. The second serializer reads the same claim
    `document._verdict_lines`
    does (module docstring, "the HTML emitter consumes the SAME list") — a
    config-shaped `question` must render its own identity here exactly as it
    does in markdown, not raise on the endpoint shape's `protocol`/`path`
    attributes a `ConfigQuestionRef` does not carry."""
    sections = assemble_module_document(
        MODULE,
        REPORT,
        "a3f91c",
        resolved_config=[
            {
                "key": "spring.config.import",
                "value": None,
                "source": "application.yml",
                "environment": "default",
                "unresolved_reason": "remote_source",
            }
        ],
        overlay=_overlay(_config_verdict()),
    )
    document = _html(sections)
    assert (
        "LLM assessment</strong> for <code>spring.config.import application.yml "
        "default</code> (remote_source): likely a Config Server import"
    ) in document


def test_the_stale_notice_renders_with_its_own_badge_and_sentence():
    sections = assemble_module_document(
        MODULE,
        REPORT,
        "a3f91c",
        overlay=_overlay(_component(), _section()),
        stale=frozenset({1}),
    )
    document = _html(sections)
    assert "1 enrichment claim stale, not shown." in document
    assert document.count('<span class="llm-badge">LLM</span>') == 2


# --- claim body formatting (2M design §5d) --------------------------------


def _section_body(body: str):
    return _claim(
        "section",
        "end-of-document",
        title="Extending the edge",
        body=body,
        cites=["src/main/java/com/acme/orders/Ingest.java"],
    )


def test_a_claim_bodys_inline_code_span_becomes_a_code_tag():
    claim = _section_body("See `Foo#bar()` for the entry point.")
    sections = assemble_module_document(MODULE, REPORT, "a3f91c", overlay=_overlay(claim))
    document = _html(sections)
    assert "<p>See <code>Foo#bar()</code> for the entry point.</p>" in document


def test_a_claim_bodys_fenced_block_becomes_pre_code_escaped():
    body = "Configure it like:\n```\nfoo<bar>\nbaz\n```\nThen restart."
    claim = _section_body(body)
    sections = assemble_module_document(MODULE, REPORT, "a3f91c", overlay=_overlay(claim))
    document = _html(sections)
    assert "<p>Configure it like:</p>" in document
    assert "<pre><code>foo&lt;bar&gt;\nbaz</code></pre>" in document
    assert "<p>Then restart.</p>" in document


def test_a_claims_unpaired_backtick_renders_literally_with_no_half_open_tag():
    """2M design §5d: only a PAIRED backtick span is code — a stray one, with
    no partner on the same line, is just a character the model happened to
    type, not the start of something this emitter must close for it."""
    claim = _section_body("It uses a ` mark with no partner.")
    sections = assemble_module_document(MODULE, REPORT, "a3f91c", overlay=_overlay(claim))
    document = _html(sections)
    # A fully-formed `<p>...</p>` carrying the literal backtick is the proof
    # of "no half-open tag": a mis-parsed unpaired backtick would either
    # break this exact string or leave an unmatched `<code>` dangling in it.
    assert "<p>It uses a ` mark with no partner.</p>" in document


def test_a_claims_markdown_links_and_bold_stay_literal():
    """2M design §5d draws the line at inline code and fenced blocks —
    nothing else is markdown here, so a link or bold marker is exactly as
    literal as any other punctuation in the model's prose."""
    body = "See [the doc](https://example.com) and **do not** skip it."
    claim = _section_body(body)
    sections = assemble_module_document(MODULE, REPORT, "a3f91c", overlay=_overlay(claim))
    document = _html(sections)
    assert "<p>See [the doc](https://example.com) and **do not** skip it.</p>" in document


# --- escaping ------------------------------------------------------------


def test_prose_containing_html_special_characters_is_escaped_not_executed():
    leaky = _component(name="<script>alert(1)</script>")
    sections = assemble_module_document(MODULE, REPORT, "a3f91c", overlay=_overlay(leaky))
    document = _html(sections)
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
    assert _html(sections) == _html(sections)


# --- fix round 1 minors -----------------------------------------------


def test_a_heading_level_outside_the_shared_bound_is_a_hard_error():
    """MINOR 4: `<h4>` is syntactically valid HTML, so without a bound of its
    own this emitter would happily render a level markdown's
    `_HEADING_MARKERS` has no marker for at all — the two serializers must
    fail on the SAME bound (`document.HEADING_LEVELS`) rather than one
    `KeyError`-ing in markdown while HTML stays silently permissive."""
    with pytest.raises(ValueError, match="heading level"):
        _html((MachineHeading(4, "Too deep"),))


def test_a_bare_code_style_rule_gives_every_code_run_the_same_chip():
    """MINOR 5: one typography per meaning — a machine code run (a table
    cell, a detail identity) must carry the same chip a claim's own `<code>`
    already does, from ONE rule both share rather than a class-scoped one
    that only some code runs happen to sit inside."""
    assert (
        "\ncode { background: rgba(0, 0, 0, 0.06); border-radius: 4px; padding: 0 0.25rem; }\n"
        in _STYLE
    )


# --- the serializer's own edges: a hard error, never a skip ---------------


@dataclass(frozen=True)
class _UnknownSection:
    """Stands in for a section kind this emitter has fallen behind — never a
    real member of `document.Section`, which is exactly the point."""


def test_an_unrecognized_section_kind_is_a_hard_error_not_a_skip():
    with pytest.raises(ValueError, match="no rendering rule"):
        _html((_UnknownSection(),))  # type: ignore[arg-type]


def test_an_unrecognized_claim_kind_is_a_hard_error_not_a_skip():
    provenance = _overlay(_component()).produced_by
    with pytest.raises(ValueError, match="no rendering rule"):
        _html((EnrichmentSection(provenance, (object(),)),))  # type: ignore[arg-type]
