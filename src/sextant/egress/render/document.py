"""The module architecture document (M07). Adds no information: every row
comes from `report`, and every omission — the call graph, a Maven POM the
detector could not read correctly, a payload type nothing could expand, or a
catalog skipped by capability gating — is named rather than silently absent
(NFR-7)."""

import json
from collections.abc import Sequence

from sextant.application.ports.detector import ModuleModel
from sextant.application.resolve.pipeline import ResolveReport
from sextant.domain.closed_sets import Protocol
from sextant.egress.render.diagrams import class_diagram
from sextant.egress.render.viewmodel import ClassEdge, ClassNode, simple_name

_GAPS = [
    "An @HttpExchange interface implemented server-side is still reported outbound.",
    (
        "Outbound base addresses configured in builder code are not resolved: "
        "those endpoints carry no peer."
    ),
    "Sequence diagrams await the call graph.",
    "The structure diagram covers contract types only: inheritance edges are not extracted.",
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
        "Module classification reads only a container file and a declared main "
        "class: a module showing neither is reported `undetermined` rather than "
        "weighed against the rest of the evidence."
    ),
    (
        "A path the module both exposes and calls keeps only the handler's "
        "declared contract: where the client's declaration differs, that "
        "difference is not recorded."
    ),
    (
        "A payload type reachable from several catalogs is expanded under the "
        "first catalog's serialisation, wrapper and nullability rules, not "
        "necessarily the ones that produced its endpoint: the first outbound "
        "catalog's rules describe every outbound row. The shipped catalogs do "
        "not declare identical rules, so a wrapper type one of them unwraps "
        "and another does not can be named below as unexpanded even where the "
        "shape behind it was expanded correctly."
    ),
    (
        "Reactive and lambda flow is recorded but not traced: calls inside "
        "flatMap and map derive endpoints, but the sequence between them "
        "awaits the call graph."
    ),
]

# D00 §4 closed-set protocol names whose wire identity has no verb: a Kafka
# topic, a JMS destination, an SQS queue or a Pub/Sub topic is addressed, not
# called, so there is no method to render beside the path.
#
# Derived from D00's closed set by SUBTRACTING the verbed protocols, rather
# than hand-listing the verbless ones. Two sets naming halves of one closed
# set drift; one set and a subtraction cannot. Which half to hand-list is
# then the question of what an UNLISTED new protocol should default to, and
# verbless is the honest default: it renders `protocol path`, while the other
# way round renders `(unresolved) path` — a verb reported as unread when the
# protocol was never going to have one. The verbed half is also the stable
# half: growth in D00's set is broker families, not new request-response
# verbs.
_VERBED_PROTOCOLS = frozenset({"http", "soap", "grpc"})
_VERBLESS_PROTOCOLS = frozenset(p.value for p in Protocol) - _VERBED_PROTOCOLS


def _wire_identity(endpoint: dict[str, object]) -> str:
    """A row's wire identity as one string. A protocol in `_VERBLESS_PROTOCOLS`
    defines no verb, so it renders `protocol path` with no method at all;
    every other protocol renders `method path` as before. Either half of
    either shape may be NULL, and `(unresolved)` stays the marker for an
    identity the analysis could not read — never a bare `None`."""
    path = endpoint["path"]
    rendered_path = "(unresolved)" if path is None else str(path)
    if str(endpoint["protocol"]) in _VERBLESS_PROTOCOLS:
        return f"{endpoint['protocol']} {rendered_path}"
    method = endpoint["method"]
    rendered_method = "(unresolved)" if method is None else str(method)
    return f"{rendered_method} {rendered_path}"


def render_module_document(
    module: ModuleModel,
    report: ResolveReport,
    commit: str,
    uncovered: tuple[str, ...] = (),
    shape_fields: Sequence[dict[str, object]] = (),
) -> str:
    """Adds no information. Every row comes from the graph, and every omission
    is stated (M07). Rendering the same report twice is byte-identical
    (NFR-1): nothing here reads a clock, and endpoint and shape order is
    whatever the graph query already fixed."""
    fields_by_shape = _fields_by_shape(shape_fields)
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
        "## Structure",
        "",
    ]
    if report.shapes:
        nodes, edges = _contract_nodes(report.shapes, shape_fields)
        lines += ["```mermaid"]
        lines += class_diagram(nodes, edges).rstrip("\n").split("\n")
        lines += ["```"]
    else:
        lines.append("None derived.")

    lines += ["", "## Inbound endpoints", ""]
    inbound = [e for e in report.endpoints if str(e["direction"]) in ("inbound", "both")]
    if inbound:
        lines += ["| Endpoint | Handler | Resolution |", "|---|---|---|"]
        for endpoint in inbound:
            handler = str(endpoint["handler"]).rsplit(" ", 1)[-1]
            lines.append(
                f"| `{_wire_identity(endpoint)}` | `{handler}` | {endpoint['resolution']} |"
            )
        for endpoint in inbound:
            request = _descriptor_lines("Request", endpoint.get("request_shape"), fields_by_shape)
            response = _descriptor_lines(
                "Response", endpoint.get("response_shape"), fields_by_shape
            )
            if request or response:
                lines += ["", f"- `{_wire_identity(endpoint)}`"]
                lines += request
                lines += response
    else:
        lines.append("None found.")

    # An empty section is now a real statement rather than a stand-in for
    # "not implemented" — outbound derivation exists (NFR-7).
    lines += ["", "## Outbound endpoints", ""]
    outbound = [e for e in report.endpoints if str(e["direction"]) in ("outbound", "both")]
    if outbound:
        lines += ["| Endpoint | Peer | Caller | Resolution |", "|---|---|---|---|"]
        for endpoint in outbound:
            peer = endpoint.get("peer")
            caller = str(endpoint["caller"]).rsplit(" ", 1)[-1]
            lines.append(
                f"| `{_wire_identity(endpoint)}` | "
                f"{'unresolved' if peer is None else peer} | "
                f"`{caller}` | {endpoint['resolution']} |"
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


def _fields_by_shape(
    shape_fields: Sequence[dict[str, object]],
) -> dict[str, list[dict[str, object]]]:
    """`shape_fields` grouped by owning shape, in the ordinal order the
    `shape_fields` query already fixed (NFR-1)."""
    grouped: dict[str, list[dict[str, object]]] = {}
    for field in shape_fields:
        grouped.setdefault(str(field["shape_id"]), []).append(field)
    return grouped


def _contract_nodes(
    shapes: list[dict[str, object]], shape_fields: Sequence[dict[str, object]]
) -> tuple[list[ClassNode], list[ClassEdge]]:
    """`shapes`/`shape_fields` projected into the view model the emitter draws
    (M07 "Structure — contract class diagram"): one node per shape with its
    own wire fields, one edge per field whose `item` descriptor points at
    another shape."""
    grouped = _fields_by_shape(shape_fields)
    nodes: list[ClassNode] = []
    edges: list[ClassEdge] = []
    for shape in shapes:
        shape_id = str(shape["shape_id"])
        rows = grouped.get(shape_id, [])
        fields = tuple((str(row["wire_name"]), str(row["wire_type"])) for row in rows)
        nodes.append(ClassNode(shape_id, fields, bool(shape["open"])))
        for row in rows:
            item = row.get("item")
            if not item:
                continue
            target = json.loads(str(item)).get("shape_id")
            if target:
                edges.append(ClassEdge(shape_id, str(target)))
    return nodes, edges


def _inline_descriptor(descriptor: dict[str, object]) -> str:
    """The payload label for a descriptor with no shape at its own level —
    a scalar, or a collection of one — since there is no shape to tabulate
    (`array of object OrderView`, `string`)."""
    wire_type = str(descriptor.get("wire_type"))
    shape_id = descriptor.get("shape_id")
    if shape_id:
        return f"{wire_type} {simple_name(str(shape_id))}"
    item = descriptor.get("item")
    if isinstance(item, dict):
        return f"{wire_type} of {_inline_descriptor(item)}"
    return wire_type


def _descriptor_lines(
    label: str,
    descriptor_json: object,
    fields_by_shape: dict[str, list[dict[str, object]]],
) -> list[str]:
    """One endpoint's request or response, indented under its summary row: a
    contract table of the referenced shape's fields when the payload is
    itself a shape, or an inline label when it is a scalar or a collection of
    one. `None` (no descriptor) contributes nothing."""
    if descriptor_json is None:
        return []
    descriptor = json.loads(str(descriptor_json))
    shape_id = descriptor.get("shape_id")
    if not shape_id:
        return [f"  - {label}: {_inline_descriptor(descriptor)}"]
    lines = [
        f"  - {label}:",
        "",
        "    | Field | Type | Required | Nullable |",
        "    |---|---|---|---|",
    ]
    for row in fields_by_shape.get(str(shape_id), []):
        wire_format = row.get("wire_format")
        field_type = f"{row['wire_type']} ({wire_format})" if wire_format else str(row["wire_type"])
        required = "yes" if row["required"] else "no"
        nullable = "yes" if row["nullable"] else "no"
        lines.append(f"    | {row['wire_name']} | {field_type} | {required} | {nullable} |")
    return lines
