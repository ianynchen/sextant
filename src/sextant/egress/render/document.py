"""The module architecture document (M07). Adds no information: every row
comes from `report`, and every omission — outbound endpoints, the call graph,
a Maven POM the detector could not read correctly, a payload type nothing
could expand, or a catalog skipped by capability gating — is named rather than
silently absent (NFR-7)."""

from sextant.application.ports.detector import ModuleModel
from sextant.application.resolve.pipeline import ResolveReport

_GAPS = [
    "Outbound endpoints are not implemented: this catalog is inbound only.",
    "The call graph is not implemented: there are no traces or sequence diagrams.",
    (
        "Maven parent POMs, profiles, and property interpolation are not resolved: "
        "the detector reads pom.xml directly instead of asking Maven to resolve it, "
        "so any POM that depends on a parent, an active profile, or a property "
        "placeholder will be misread — which is most real-world POMs."
    ),
    (
        "Catalogs are not matched to modules: every catalog's `detect.coordinates` "
        "is declared and read by nobody, so every catalog runs against every "
        "module whether or not the module depends on that framework."
    ),
    (
        "Nested and anonymous classes are not read: they are named below as "
        "uncovered, but their endpoints and annotations are absent from "
        "everything above. A non-empty uncovered list does not yet stop the run."
    ),
    (
        "Module classification reads only a container file and a declared main "
        "class: a module showing neither is reported `undetermined` rather than "
        "weighed against the rest of the evidence."
    ),
]


def render_module_document(
    module: ModuleModel,
    report: ResolveReport,
    commit: str,
    uncovered: tuple[str, ...] = (),
) -> str:
    """Adds no information. Every row comes from the graph, and every omission
    is stated (M07). Rendering the same report twice is byte-identical
    (NFR-1): nothing here reads a clock, and endpoint order is whatever the
    graph query already fixed."""
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
        lines += ["| Endpoint | Handler | Resolution |", "|---|---|---|"]
        for endpoint in report.endpoints:
            handler = str(endpoint["handler"]).rsplit(" ", 1)[-1]
            lines.append(
                f"| `{endpoint['method']} {endpoint['path']}` | "
                f"`{handler}` | {endpoint['resolution']} |"
            )
    else:
        lines.append("None found.")

    lines += ["", "## Known gaps", ""]
    lines += [f"- {gap}" for gap in _GAPS]
    # Named one by one, because a compiled source nothing read is the one gap
    # a reader can act on: it says which part of the module this document is
    # silent about (FR-17, M03).
    lines += [f"- Not read, so nothing above accounts for it: `{source}`." for source in uncovered]
    # Named one by one for the same reason: a payload type nothing could open
    # is the gap between "this shape is the contract" and "this shape is as
    # much of the contract as anyone could see", and only the name says which
    # catalog entry would close it (FR-17).
    lines += [
        f"- Not expanded, so the shapes referring to it are open: `{symbol}`."
        for symbol in report.unexpanded_types
    ]
    if report.skipped_catalogs:
        lines += ["", "## Catalogs skipped", ""]
        for skipped in report.skipped_catalogs:
            lines.append(
                f"- `{skipped.catalog_id}` requires {', '.join(skipped.missing_capabilities)}"
            )
    return "\n".join(lines) + "\n"
