"""`architecture.html` — the second serializer over the same assembled
document `markdown_document` writes as `architecture.md` (2K design §6/§6b).

**Same list, no second opinion.** This module reads the `AssembledDocument`
`document.assemble_module_document` produces — the same typed sections the
markdown emitter reads — and never the markdown text `markdown_document`
writes from it. Parsing that text back apart to find a fence or a claim
would be a second serializer disagreeing with the first about where things
are; consuming the same list instead makes that impossible by construction.

**Self-contained and offline** (2K design §6b). A pinned, vendored copy of
mermaid (`assets/mermaid.min.js`, pinned in `asset_pins.py`) and a small
pan-zoom script of Sextant's own (`assets/panzoom.js`) are both inlined into
the page verbatim, so the document opens with no network access. Determinism
holds: every asset is read from the same committed bytes, the template
around them is a fixed string, and section order is whatever
`assemble_module_document` already fixed (NFR-1) — nothing here reads a
clock.

**Structure is typed, never parsed back out of text.** `assemble_module_document`
builds `MachineHeading`/`MachineParagraph`/`MachineList`/`MachineTable`/
`MachineDetail` at the sites that already know the structure (2M design
§5b), so this module writes real `<h1>`-`<h3>`, `<table>`, `<ul>` and
definition-block markup straight from those types — never by scanning
markdown for `#`, `|` or `-` to guess what they meant. `MachineSection`
(opaque lines) remains the escape hatch for machine text with no typed shape
of its own: shown as escaped text in a monospaced block, exactly as before,
for whatever still reaches this emitter that way.

**Every diagram, wrapped alike.** A `MachineDiagram` and a claim's own
`DiagramClaim` both reach this module as mermaid *source* rather than a
fenced block buried in prose (`document.MachineDiagram`'s own docstring), so
both go through the one `_diagram_html` wrapper — pan-zoom controls, a
`<pre class="mermaid">` for the client-side library to render, and nothing
that distinguishes a machine diagram from an LLM one except which section it
arrived in.

**Enrichment is visibly badged.** `EnrichmentSection` and
`StaleNoticeSection` render inside a distinctly styled block carrying an
`LLM` badge — the visual mirror of the markdown emitter's
`> **Enrichment — evidence: llm**` blockquote — so a reader cannot mistake
model output for derived fact by skimming past a heading.

**Model prose renders literally.** A claim's own free-form text —
`SectionClaim.body`, a verdict's `because`/`searched`, a backtick an agent
wrote inline around a symbol name — is escaped and shown as plain text,
never reinterpreted as markdown. This is the same no-parse rule applied to a
second carrier of markdown-ish text: this module does not know what a
backtick means in a claim's prose any more than it knows what a `#` means in
`MachineSection.lines`, and treating one as syntax while leaving the other
alone would be an arbitrary distinction with no rule behind it.
"""

import html
from importlib import resources

from sextant.domain.enrichment import (
    UNANSWERED,
    Claim,
    ComponentClaim,
    DiagramClaim,
    Provenance,
    SectionClaim,
    VerdictClaim,
)
from sextant.egress.render.document import (
    AssembledDocument,
    EnrichmentSection,
    MachineDetail,
    MachineDiagram,
    MachineHeading,
    MachineList,
    MachineParagraph,
    MachineSection,
    MachineTable,
    Run,
    Section,
    StaleNoticeSection,
)

_STYLE = """
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
       margin: 2rem auto; max-width: 960px; padding: 0 1rem; line-height: 1.5; color: #1a1a1a; }
pre.machine { background: #f6f8fa; padding: 1rem; overflow-x: auto; border-radius: 6px;
              font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
              font-size: 0.85rem; }
.diagram { border: 1px solid #d0d7de; border-radius: 6px; margin: 1.5rem 0; }
.diagram-controls { display: flex; gap: 0.5rem; padding: 0.5rem; background: #f6f8fa;
                     border-bottom: 1px solid #d0d7de; }
.diagram-controls button { cursor: pointer; border: 1px solid #d0d7de; background: #fff;
                            border-radius: 4px; min-width: 2rem; padding: 0.15rem 0.5rem; }
.diagram-viewport { overflow: hidden; height: 420px; cursor: grab;
                     user-select: none; -webkit-user-select: none; }
.diagram-viewport.dragging { cursor: grabbing; }
.diagram-canvas { width: max-content; transform-origin: 0 0; }
.diagram-canvas pre.mermaid { margin: 0; background: transparent; padding: 1rem; }
.diagram-caption { padding: 0.5rem 1rem; font-style: italic; color: #57606a;
                    border-top: 1px solid #d0d7de; }
table { border-collapse: collapse; width: 100%; margin: 1rem 0; }
th, td { border: 1px solid #d0d7de; padding: 0.35rem 0.6rem; text-align: left; }
th { background: #f6f8fa; }
dl.detail { border-left: 2px solid #d0d7de; margin: 0.5rem 0 1rem; padding-left: 1rem; }
dl.detail dt { font-weight: 600; margin-top: 0.5rem; }
dl.detail dd { margin: 0.15rem 0 0.5rem; }
.enrichment { border-left: 4px solid #8250df; background: #faf5ff; padding: 0.25rem 1rem 0.75rem;
              margin: 1rem 0; border-radius: 0 6px 6px 0; }
.enrichment-header { padding-top: 0.5rem; font-weight: 600; }
.llm-badge { display: inline-block; background: #8250df; color: #fff; font-size: 0.72rem;
             font-weight: 700; padding: 0.1rem 0.5rem; border-radius: 999px;
             letter-spacing: 0.03em; text-transform: uppercase; }
.stale-notice { border-left-color: #9a6700; background: #fff8c5; }
.claim { margin: 0.75rem 0 0; }
.claim code { background: rgba(0, 0, 0, 0.06); border-radius: 4px; padding: 0 0.25rem; }
"""


def html_document(sections: AssembledDocument, module_id: str) -> str:
    """`architecture.html` from an assembled document. `module_id` names the
    module in the page `<title>` (`ModuleModel.module_id`, the same identity
    the markdown emitter opens the document with as `# {module_id}`) so two
    modules' documents are distinguishable by their browser tab — passed in
    explicitly rather than read back out of the assembled `MachineSection`
    lines, which stay opaque prose this module does not scan.

    Byte-identical across two calls over the same `sections`/`module_id`
    (NFR-1): every asset is read from the same committed file, the template
    around them is a fixed string, and nothing here iterates a dict whose
    order is not already fixed by `sections` itself."""
    body = "\n".join(_section_html(section) for section in sections)
    mermaid_js = _asset("mermaid.min.js")
    panzoom_js = _asset("panzoom.js")
    return (
        "<!doctype html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        f"<title>Sextant — {html.escape(module_id)}</title>\n"
        f"<style>{_STYLE}</style>\n"
        "</head>\n"
        "<body>\n"
        f"{body}\n"
        f"<script>{mermaid_js}</script>\n"
        "<script>\n"
        'mermaid.initialize({"startOnLoad": false, "securityLevel": "strict"});\n'
        'document.addEventListener("DOMContentLoaded", function () {\n'
        '  mermaid.run({ querySelector: ".mermaid" });\n'
        "});\n"
        "</script>\n"
        f"<script>{panzoom_js}</script>\n"
        "</body>\n"
        "</html>\n"
    )


def _asset(name: str) -> str:
    """One vendored or hand-written front-end asset's text, read from package
    data — the same reasoning `cli/resources.py` states for the catalogs and
    the extractor jar: resolved through the installed package rather than a
    path relative to this file's position on disk, so a wheel install finds
    it too."""
    text = (resources.files(__package__) / "assets" / name).read_text(encoding="utf-8")
    return _refused_if_unsafe_to_inline(name, text)


def _refused_if_unsafe_to_inline(name: str, text: str) -> str:
    """`text`, or a loud refusal if it contains `</script` in any case.

    Every asset is inlined verbatim between `<script>`/`</script>` tags, so
    that sequence would close the tag early and dump the rest of the asset
    into the page as markup rather than JavaScript. Today's mermaid build is
    clean; a future version bump that is not must fail this check rather
    than silently break the page it ships in. Its own function, rather than
    inline in `_asset`, so the refusal is testable directly against a
    fabricated string without reaching into how `_asset` finds its bytes."""
    if "</script" in text.lower():
        raise ValueError(
            f"asset {name!r} contains a `</script` sequence — inlining it verbatim "
            "would break out of its <script> tag; escape or otherwise neutralize it "
            "before vendoring"
        )
    return text


def _section_html(section: Section) -> str:
    if isinstance(section, MachineHeading):
        return _heading_html(section)
    if isinstance(section, MachineParagraph):
        return f"<p>{_runs_html(section.runs)}</p>"
    if isinstance(section, MachineList):
        return _list_html(section)
    if isinstance(section, MachineTable):
        return _table_html(section)
    if isinstance(section, MachineDetail):
        return _detail_html(section)
    if isinstance(section, MachineSection):
        return _machine_html(section)
    if isinstance(section, MachineDiagram):
        return _diagram_html(section.mermaid)
    if isinstance(section, EnrichmentSection):
        return _enrichment_html(section)
    if isinstance(section, StaleNoticeSection):
        return _stale_html(section)
    # `Section` is the closed set `document.py` itself defines. A kind
    # reaching here means this emitter has fallen behind that set, and the
    # honest answer is a loud failure rather than a section silently missing
    # from the page (brief: "a kind you don't recognize is a hard error, not
    # a skip").
    raise ValueError(f"html emitter has no rendering rule for section {section!r}")


def _runs_html(runs: tuple[Run, ...]) -> str:
    """Runs, escaped and typeset — a code run as `<code>`, a text run as
    plain escaped text — which is the whole reason machine text carries runs
    now (2M design §5b): this never has to parse a backtick to know where a
    `<code>` tag belongs."""
    return "".join(
        f"<code>{html.escape(content)}</code>" if kind == "code" else html.escape(content)
        for kind, content in runs
    )


def _heading_html(section: MachineHeading) -> str:
    level = section.level
    return f"<h{level}>{html.escape(section.text)}</h{level}>"


def _list_html(section: MachineList) -> str:
    items = "".join(f"<li>{_runs_html(item)}</li>" for item in section.items)
    return f"<ul>{items}</ul>"


def _table_html(table: MachineTable) -> str:
    head = "".join(f"<th>{html.escape(header)}</th>" for header in table.headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{_runs_html(cell)}</td>" for cell in row) + "</tr>"
        for row in table.rows
    )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _detail_html(section: MachineDetail) -> str:
    """A definition block: the header entry (`entries[0]`, never carrying a
    body or a table) is a bare `<dt>`; every entry after it is a `<dt>`/`<dd>`
    pair, the `<dd>` holding either the inline body or a real nested
    `<table>` — never the indented markdown block this used to be scanned out
    of a `<pre>`."""
    parts = ['<dl class="detail">']
    for entry in section.entries:
        parts.append(f"<dt>{_runs_html(entry.title)}</dt>")
        if entry.table is not None:
            parts.append(f"<dd>{_table_html(entry.table)}</dd>")
        elif entry.body is not None:
            parts.append(f"<dd>{_runs_html(entry.body)}</dd>")
    parts.append("</dl>")
    return "".join(parts)


def _machine_html(section: MachineSection) -> str:
    """A run of machine prose, escaped and shown as text — never parsed. See
    the module docstring for why interpreting the markdown syntax these
    lines carry is out of scope for this emitter."""
    if not section.lines:
        return ""
    text = html.escape("\n".join(section.lines))
    return f'<pre class="machine">{text}</pre>'


def _diagram_html(mermaid_source: str, caption: str | None = None) -> str:
    """One diagram, machine or claimed alike, wrapped in pan-zoom controls
    (2K design §6b). `panzoom.js` finds it by this structure — applying its
    transform to `.diagram-canvas`, the element mermaid replaces with the
    rendered SVG once `mermaid.run()` reaches it.

    The source goes into a `<pre class="mermaid">` escaped through
    `html.escape`: mermaid's client-side `run()` reads the element's decoded
    text content, so escaping keeps the surrounding markup well-formed
    without corrupting a single character of the diagram itself."""
    source = html.escape(mermaid_source)
    caption_html = f'<div class="diagram-caption">{html.escape(caption)}</div>' if caption else ""
    return (
        '<div class="diagram">'
        '<div class="diagram-controls">'
        '<button type="button" class="diagram-zoom-in">+</button>'
        '<button type="button" class="diagram-zoom-out">−</button>'
        '<button type="button" class="diagram-reset">reset</button>'
        "</div>"
        '<div class="diagram-viewport"><div class="diagram-canvas">'
        f'<pre class="mermaid">{source}</pre>'
        "</div></div>"
        f"{caption_html}"
        "</div>"
    )


def _enrichment_html(section: EnrichmentSection) -> str:
    claims = "".join(_claim_html(claim) for claim in section.claims)
    return f'<div class="enrichment">{_badge(section.provenance)}{claims}</div>'


def _stale_html(section: StaleNoticeSection) -> str:
    sentence = _stale_sentence(section.count)
    return (
        f'<div class="enrichment stale-notice">{_badge(section.provenance)}'
        f"<p>{html.escape(sentence)}</p></div>"
    )


def _stale_sentence(count: int) -> str:
    """The visible count of what is not shown (2K design §6) — the same
    wording `document._stale_sentence` renders as markdown, kept as its own
    copy rather than an import of that private helper: this module owns its
    own HTML fragment, and the two are pinned by their own suites."""
    return f"{count} enrichment claim{'' if count == 1 else 's'} stale, not shown."


def _badge(provenance: Provenance) -> str:
    """The visible marker every enrichment block carries (2K design §6,
    "add-only, clearly marked") — the HTML mirror of the markdown emitter's
    `> **Enrichment — evidence: llm**` blockquote, so a reader of either
    output sees the same claim about what produced the words before reading
    them."""
    model = html.escape(provenance.model)
    agent = html.escape(provenance.agent)
    return (
        '<div class="enrichment-header"><span class="llm-badge">LLM</span> '
        f"Enrichment — evidence: llm (model {model}, agent {agent})</div>"
    )


def _claim_html(claim: Claim) -> str:
    """One claim as HTML — mirrors `document._claim_lines`'s per-kind switch,
    each kind rendering as what it is rather than as generic prose."""
    if isinstance(claim, ComponentClaim):
        return _component_claim_html(claim)
    if isinstance(claim, SectionClaim):
        return _section_claim_html(claim)
    if isinstance(claim, DiagramClaim):
        return _diagram_claim_html(claim)
    if isinstance(claim, VerdictClaim):
        return _verdict_claim_html(claim)
    # `Claim` is the closed, discriminated union `domain/enrichment.py`
    # defines. A fifth kind reaching here means this emitter has fallen
    # behind that set — the same hard-error rule `_section_html` keeps above.
    raise ValueError(f"html emitter has no rendering rule for claim {claim!r}")


def _component_claim_html(claim: ComponentClaim) -> str:
    members = ", ".join(f"<code>{html.escape(member)}</code>" for member in claim.members)
    return (
        '<div class="claim claim-component">'
        f"<strong>Component: {html.escape(claim.name)}</strong>"
        f"<p>{html.escape(claim.purpose)}</p>"
        f"<p>Members: {members}</p>"
        "</div>"
    )


def _section_claim_html(claim: SectionClaim) -> str:
    paragraphs = "".join(f"<p>{html.escape(line)}</p>" for line in claim.body.split("\n") if line)
    cites = ", ".join(f"<code>{html.escape(cite)}</code>" for cite in claim.cites)
    return (
        '<div class="claim claim-section">'
        f"<strong>{html.escape(claim.title)}</strong>"
        f"{paragraphs}"
        f"<p>Cites: {cites}</p>"
        "</div>"
    )


def _diagram_claim_html(claim: DiagramClaim) -> str:
    return _diagram_html(claim.mermaid.rstrip("\n"), caption=f"Elides: {claim.elides}")


def _verdict_claim_html(claim: VerdictClaim) -> str:
    question = claim.question
    identity = " ".join(
        part for part in (question.protocol, question.method, question.path) if part
    )
    label = (
        f"<strong>LLM assessment</strong> for <code>{html.escape(identity)}</code> "
        f"({html.escape(question.kind)}): {html.escape(claim.assessment)}"
    )
    if claim.assessment == UNANSWERED:
        # The schema's own validator (`domain/enrichment.py`,
        # `_carries_the_half_its_assessment_requires`) guarantees `searched`
        # is set on this branch and `because` on the other — asserted here so
        # a claim that somehow violated that invariant fails loudly instead
        # of silently rendering the literal word "None".
        assert claim.searched is not None
        tail = f" — searched: {html.escape(claim.searched)}"
    else:
        assert claim.because is not None
        tail = f" — because {html.escape(claim.because)}"
    return f'<div class="claim claim-verdict"><p>{label}{tail}</p></div>'
