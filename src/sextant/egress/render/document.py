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
from sextant.domain.symbols import bare_descriptor
from sextant.egress.render.diagrams import class_diagram
from sextant.egress.render.viewmodel import ClassEdge, ClassNode, simple_name

_GAPS = [
    "An @HttpExchange interface implemented server-side is still reported outbound.",
    (
        "Base addresses built by computation — concatenation, setter injection, "
        "a method's return value — are not traced; only a directly-read field or "
        "property reaches configuration."
    ),
    (
        "Configuration constructed in code — a settings module, a config "
        "factory — is not read; only configuration files reach resolution."
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
        "Endpoint request and response contracts are scoped to the catalog "
        "that produced them. Shape expansion itself is not: a payload type "
        "reachable from several catalogs is still expanded once, under "
        "whichever catalog's rules reach it first, not necessarily the ones "
        "that produced the endpoint referencing it. The shipped catalogs do "
        "not declare identical rules, so a wrapper type one of them unwraps "
        "and another does not can be named below as unexpanded even where the "
        "shape behind it was expanded correctly."
    ),
    (
        "Reactive and lambda flow is recorded but not traced: calls inside "
        "flatMap and map derive endpoints, and a functional route's handler "
        "resolves, but the sequence between reactive calls — and the "
        "payloads read inside a functional handler's body — await the call "
        "graph."
    ),
    (
        "A bytes-only channel whose payload is parsed further than one "
        "delegation hop from its handler is not bound: the parse is found "
        "and listed as an open question instead, because a flow followed "
        "further than it was observed is an assumption, not a fact."
    ),
    (
        "A bytes-only channel whose payload reaches two different parses "
        "binds neither: two answers about one wire is a question for a "
        "reader, and picking the one that sorts first would publish a "
        "coin toss as a contract."
    ),
]

# The protocols whose verb is not an HTTP method, so the protocol name is
# itself part of the identity a reader needs (D06, 2H design §1): `graphql
# query orders` names an operation, while a bare `query orders` names nothing
# in particular — `query` is not a word that implies its own protocol the way
# `GET` does. `sse` is qualified for the mirror-image reason (2H design §6):
# its verb IS an HTTP method, because an SSE stream is a route a client GETs,
# and a bare `GET /events/stream` therefore reads as an ordinary REST route
# and loses the one thing the reclassification established. HTTP and gRPC
# read correctly without the prefix, which is also what every pin written
# before this expects.
_PROTOCOL_QUALIFIED = frozenset({"graphql", "sse"})

# D00 §4 closed-set protocol names whose wire identity has no verb: a Kafka
# topic, a JMS destination, an SQS queue or a Pub/Sub topic is addressed, not
# called, so there is no method to render beside the path. SOAP belongs here
# too (spec §1, 2I Task 4 fix round 1, ruled) — an operation is addressed by
# its payload root or its SOAPAction URI, never a verb, the same 2D messaging
# shape as a Kafka topic. It sat in the verbed half from 2H (when no catalog
# owned the protocol, so the misclassification rendered nothing) through 2I
# Task 2's own live rows, which is what let every SOAP row render a phantom
# `(unresolved)` verb nobody ever failed to read.
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
#
# The qualified set is UNIONED in rather than repeated, so "every qualified
# protocol is a verbed one" is structural. Stating it twice is what let `sse`
# be added to one list and silently fall out of the other — a GET route
# reclassified into the verbless half renders `sse /events/stream` and drops
# the verb it does have.
_VERBED_PROTOCOLS = frozenset({"http", "grpc"}) | _PROTOCOL_QUALIFIED
_VERBLESS_PROTOCOLS = frozenset(p.value for p in Protocol) - _VERBED_PROTOCOLS

# The verbed protocols whose rows may legitimately carry NO verb. A GraphQL
# resolver is addressed by `Type.field` alone — it implements a field, it does
# not answer an operation — so its NULL method is an absence rather than a
# verb the analysis failed to read. Its own set, deliberately not
# `_PROTOCOL_QUALIFIED` reused: an SSE row is qualified and its verb is still
# an HTTP method, so a NULL there genuinely is unread and must render as such.
_VERB_OPTIONAL_PROTOCOLS = frozenset({"graphql"})


def _wire_identity(endpoint: dict[str, object]) -> str:
    """A row's wire identity as one string. A protocol in `_VERBLESS_PROTOCOLS`
    defines no verb, so it renders `protocol path` with no method at all;
    every other protocol renders `method path`, prefixed by the protocol where
    its verb does not imply one. Any half of any shape may be NULL, and
    `(unresolved)` stays the marker for an identity the analysis could not
    read — never a bare `None`."""
    protocol = str(endpoint["protocol"])
    path = endpoint["path"]
    rendered_path = "(unresolved)" if path is None else str(path)
    if protocol in _VERBLESS_PROTOCOLS:
        return f"{protocol} {rendered_path}"
    method = endpoint["method"]
    # A verbed protocol whose row carries no verb *by design*
    # (`_VERB_OPTIONAL_PROTOCOLS`, above): rendering `(unresolved)` there
    # would report a gap that does not exist. Every other verbed protocol —
    # HTTP and the SSE routes reclassified out of it alike — has a method it
    # was supposed to read, so a NULL genuinely is unread.
    if method is None and protocol in _VERB_OPTIONAL_PROTOCOLS:
        return f"{protocol} {rendered_path}"
    rendered_method = "(unresolved)" if method is None else str(method)
    prefix = f"{protocol} " if protocol in _PROTOCOL_QUALIFIED else ""
    return f"{prefix}{rendered_method} {rendered_path}"


def _handler(endpoint: dict[str, object]) -> str:
    """The Handler column: the owner's bare descriptor, or one of the two
    different things a NULL `handler` can mean.

    Until 2H every inbound row with no handler was a row whose address could
    not be read either, so one word covered both. `schema_operations` (2H
    design §3) makes the second case real: a schema declares an operation
    outright — `resolution` is `resolved`, the identity is complete — and
    names no code at all, because a schema never does and the wiring that
    would is explicitly not read (COVERAGE). Printing `unresolved` there would
    report a gap that does not exist, the same mistake `_wire_identity`
    already refuses to make for a GraphQL resolver's NULL verb.

    `none recorded` rather than `none`: the claim is about what this evidence
    carries, never that the service implements nothing — that would be a
    statement about code this analysis deliberately did not read. The
    discriminator is the row's own two columns, not its protocol or catalog: a
    row that names neither a handler nor a caller and still resolved its
    address is one whose evidence had no symbol to give.
    """
    handler = endpoint.get("handler")
    if handler is not None:
        return f"`{bare_descriptor(str(handler))}`"
    if endpoint.get("caller") is None and endpoint.get("resolution") == "resolved":
        return "none recorded"
    return "unresolved"


def _media(value: object) -> str:
    """One side of the Media column: the JSON list's comma-joined members, or
    `-` when the side is NULL — never a bare blank cell, so a row with both
    sides NULL still says so rather than reading as an omission."""
    if value is None:
        return "-"
    return ", ".join(json.loads(str(value)))


def _format(endpoint: dict[str, object]) -> str:
    """The Format column beside Media: `protobuf` at `resolved`, `protobuf
    (assumed)` at anything else, `unresolved` where the ladder left `format`
    NULL — the same NULL-renders-`unresolved` rule `rendered_handler` already
    keeps below (2E precedent).

    `format_resolution` is the authority on trust (schema.sql's own comment),
    and this column is the ONLY place a reader sees it — the rendered
    document carries no separate trust column. So `resolved` is the only
    marker that ever prints unhedged; every other non-NULL marker hedges,
    including `narrowed` and a value schema-valid but off today's live
    surface like `partial`, and including the `merge_endpoints.sql` exception
    where a merged row keeps a non-NULL format beside the WEAKER of its two
    halves' markers (schema.sql's own note) — a merged row may read
    `(protobuf, unresolved)`. Printing that plain would make an
    unresolved-trust value typographically identical to a resolved one,
    which is exactly what "an assumed format must never look observed" (2G
    design §5) forbids (task 8 review round 1)."""
    value = endpoint.get("format")
    if value is None:
        return "unresolved"
    if endpoint.get("format_resolution") != "resolved":
        return f"{value} (assumed)"
    return str(value)


def _origin_lines(endpoint: dict[str, object], origin_by_symbol: dict[str, str]) -> list[str]:
    """The `Via:` detail line for a row an extracted LIBRARY contributed, or
    nothing at all for the ordinary case.

    A library-contributed row is otherwise indistinguishable from one the
    module's own code declares — same table, same columns, same resolution —
    and the difference matters to a reader: the operation is real, but nothing
    in this repository declares it, so the place to go and look is the
    library's. The attribution is keyed on the row's own handler or caller
    symbol, whose document is what carries the coordinate (D00 §2); a row
    naming neither is a row nothing can attribute, and it is left unmarked
    rather than guessed at.
    """
    for column in ("handler", "caller"):
        symbol = endpoint.get(column)
        if symbol is not None and str(symbol) in origin_by_symbol:
            return [f"  - Via: `{origin_by_symbol[str(symbol)]}`"]
    return []


def _candidate_line(question: str, candidate: dict[str, object]) -> str:
    """One open question's candidate, in the same prose the writing pass
    already puts in its own `evidence` trail (`resolve/format.py`,
    `resolve/shapes/parse_binding.py`) — so the fact reads the same way in
    the trail and in this list. `payload_binding` and `format_conflict`
    candidates carry different keys (2G design §6), so this switches on
    `question` rather than guessing a common shape out of the JSON — the same
    discipline `open_questions.py`'s own docstring asks of "the renderer"."""
    if question == "format_conflict":
        return f"{candidate['format']} from {candidate['seen_in']} ({candidate['why']})"
    if question == "payload_binding":
        return (
            f"{candidate['payload_type']} in {candidate['seen_in']} "
            f"via {candidate['why']} at {candidate['hops']} hop(s)"
        )
    # Unreached while `open_questions.py`'s QUESTIONS stays the two-kind
    # closed set it enforces at write time — a new kind is a schema change,
    # never a rendering guess (NFR-5).
    raise ValueError(f"open question `{question!r}` has no rendering rule")


def render_module_document(
    module: ModuleModel,
    report: ResolveReport,
    commit: str,
    uncovered: tuple[str, ...] = (),
    shape_fields: Sequence[dict[str, object]] = (),
    resolved_config: Sequence[dict[str, object]] = (),
    open_questions: Sequence[dict[str, object]] = (),
    library_symbols: Sequence[dict[str, object]] = (),
) -> str:
    """Adds no information. Every row comes from the graph, and every omission
    is stated (M07). Rendering the same report twice is byte-identical
    (NFR-1): nothing here reads a clock, and endpoint and shape order is
    whatever the graph query already fixed."""
    fields_by_shape = _fields_by_shape(shape_fields)
    origin_by_symbol = {str(row["symbol"]): str(row["origin"]) for row in library_symbols}
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
    ]
    lines += _config_coverage_lines(resolved_config)
    lines += _unresolved_derivation_lines(report.endpoints)
    lines += [
        # Per-environment peer AUTHORITIES — one substituted address per
        # environment for a resolved outbound row — are the system-scope
        # document's material (M06 stitcher, M07 system scope): this module
        # document names the expression a row carries (`path`/`peer`), never
        # the per-environment values `resolved_peers` joins them against.
        (
            "- Per-environment peer resolution is the system architecture "
            "document's material, not repeated per module here."
        ),
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
        lines += ["| Endpoint | Handler | Media | Format | Resolution |", "|---|---|---|---|---|"]
        for endpoint in inbound:
            media = f"{_media(endpoint.get('consumes'))} → {_media(endpoint.get('produces'))}"
            lines.append(
                f"| `{_wire_identity(endpoint)}` | {_handler(endpoint)} | {media} | "
                f"{_format(endpoint)} | {endpoint['resolution']} |"
            )
        for endpoint in inbound:
            request = _descriptor_lines("Request", endpoint.get("request_shape"), fields_by_shape)
            response = _descriptor_lines(
                "Response", endpoint.get("response_shape"), fields_by_shape
            )
            via = _origin_lines(endpoint, origin_by_symbol)
            if request or response or via:
                lines += ["", f"- `{_wire_identity(endpoint)}`"]
                lines += via
                lines += request
                lines += response
    else:
        lines.append("None found.")

    # An empty section is now a real statement rather than a stand-in for
    # "not implemented" — outbound derivation exists (NFR-7).
    lines += ["", "## Outbound endpoints", ""]
    outbound = [e for e in report.endpoints if str(e["direction"]) in ("outbound", "both")]
    if outbound:
        lines += ["| Endpoint | Peer | Caller | Format | Resolution |", "|---|---|---|---|---|"]
        for endpoint in outbound:
            peer = endpoint.get("peer")
            caller = bare_descriptor(str(endpoint["caller"]))
            lines.append(
                f"| `{_wire_identity(endpoint)}` | "
                f"{'unresolved' if peer is None else peer} | "
                f"`{caller}` | {_format(endpoint)} | {endpoint['resolution']} |"
            )
        # The outbound half has no request/response detail to hang under, so
        # this is its whole detail block — written only where there is
        # something to say, which is the same rule the inbound one keeps.
        for endpoint in outbound:
            via = _origin_lines(endpoint, origin_by_symbol)
            if via:
                lines += ["", f"- `{_wire_identity(endpoint)}`"]
                lines += via
    else:
        lines.append("None found.")

    # Rendered only when the ledger holds rows (2G design §8): a run with
    # nothing to ask leaves the section absent, the `## Catalogs skipped`
    # precedent below rather than the NFR-7 "looked and found nothing" one —
    # this is a hand-off inbox for 2K, and an empty inbox is not a finding.
    if open_questions:
        lines += ["", "## Open questions", ""]
        for row in open_questions:
            question = str(row["question"])
            candidates = json.loads(str(row["candidates"]))
            rendered = "; ".join(_candidate_line(question, c) for c in candidates)
            lines.append(f"- `{_wire_identity(row)}` — {question}: {rendered}")

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
    # Named one by one for the same reason again: a library this module asked
    # to extract and nobody could resolve is the difference between "nothing
    # is called through it" and "nobody looked", and only the coordinate says
    # which dependency to build or install to close it (FR-17, M02).
    lines += [
        f"- Not resolved, so nothing above accounts for it: library `{coordinate}`."
        for coordinate in module.libraries_not_resolved
    ]
    if report.skipped_catalogs:
        lines += ["", "## Catalogs skipped", ""]
        for skipped in report.skipped_catalogs:
            lines.append(
                f"- `{skipped.catalog_id}` requires {', '.join(skipped.missing_capabilities)}"
            )
    return "\n".join(lines) + "\n"


def _config_coverage_lines(resolved_config: Sequence[dict[str, object]]) -> list[str]:
    """Coverage's own view of pass 2 (2F design §2): which profiles resolved,
    and which declared keys did not — named with their reason and
    environment, never just counted, so a reader can act on the same row
    `resolved_config` itself carries (spec §5). An empty answer is stated,
    never a section that silently has nothing to say (NFR-7)."""
    environments = list(dict.fromkeys(str(row["environment"]) for row in resolved_config))
    if environments:
        rendered = ", ".join(f"`{e}`" for e in environments)
        lines = [f"- Environments resolved: {rendered}."]
    else:
        lines = ["- Environments resolved: none."]
    unresolved = [row for row in resolved_config if row.get("value") is None]
    if not unresolved:
        lines.append("- Configuration keys unresolved: none.")
        return lines
    for row in unresolved:
        lines.append(
            f"- Configuration key unresolved: {row['key']} — "
            f"{row['unresolved_reason']} in {row['environment']}."
        )
    return lines


def _unresolved_derivation_lines(endpoints: Sequence[dict[str, object]]) -> list[str]:
    """Every endpoint row a catalog derived but could not address (`path`
    NULL, `resolution: unresolved`) — named by the catalog that derived it
    and the site it read, since neither is visible from the wire-identity
    tables below. Covers every `config_join` row this way (I-1, Task 7
    review): a missing binding key derives with `handler` set (the bean
    method exists) and no key to name, since the key was never declared in
    any file and so carries no `resolved_config` row of its own; a composed
    `pipeA|pipeB` selection names no single bean at all, and the composed
    expression itself is not a column any row carries — there is no
    engine-to-report channel, so it renders as what it is, not what it said.
    The same filter also catches an unresolved row from any OTHER engine
    (a computed base address, Task 8 D-4): the row carries no marker naming
    its deriving STYLE, only its catalog, so this is deliberately a superset
    rather than a filter this data cannot make honestly — and the lead-in
    line below says so on the page itself, not only in this docstring."""
    rows = [e for e in endpoints if e.get("path") is None and e.get("resolution") == "unresolved"]
    lines = [
        (
            "- Unresolved endpoint derivations — across every engine, whatever "
            "their evidence, not configuration alone:"
        )
    ]
    if not rows:
        lines.append("- None.")
        return lines
    for row in rows:
        catalog_id = row.get("catalog_id")
        catalog = "unresolved" if catalog_id is None else str(catalog_id)
        handler = row.get("handler")
        caller = row.get("caller")
        if handler is not None:
            site = f"handler `{bare_descriptor(str(handler))}`"
        elif caller is not None:
            site = f"caller `{bare_descriptor(str(caller))}`"
        else:
            site = "a composed selection expression"
        lines.append(f"- Unresolved endpoint derivation: `{catalog}` — {site}.")
    return lines


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
        # The schema's own field number (protobuf), shown the same
        # unobtrusive way `wire_format` already rides beside `wire_type` —
        # NULL for Avro and every annotation-derived field, which render
        # unchanged (2G design §8, Task 5).
        field_number = row.get("field_number")
        wire_name = (
            f"{row['wire_name']} ({field_number})"
            if field_number is not None
            else str(row["wire_name"])
        )
        wire_format = row.get("wire_format")
        field_type = f"{row['wire_type']} ({wire_format})" if wire_format else str(row["wire_type"])
        required = "yes" if row["required"] else "no"
        nullable = "yes" if row["nullable"] else "no"
        lines.append(f"    | {wire_name} | {field_type} | {required} | {nullable} |")
    return lines
