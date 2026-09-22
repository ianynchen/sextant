"""Qualifying attributes an annotation states about an inbound endpoint (spec
2026-09-22 §1f): every attribute a catalog's `metadata_from` names, written as an
`endpoint_metadata` row against the endpoint that declaration minted.

**Why the key exists at all.** §1f splits a qualifying attribute into two classes.
A ROUTING attribute changes which endpoint a message arrives at; a BEHAVIOURAL one
changes what happens once it has arrived. The rule the section states is that a
routing fact enters the row's `path` only when BOTH sides of the wire can read it,
and where only one side can, it is an `endpoint_metadata` entry the linking tier may
later use as a refinement. Two rows whose stated values differ do not link; a row
that states nothing links as before. So an attribute one side declares and the other
cannot spell is recorded HERE rather than composed into an identity the other half of
the wire could never match — an identity half only one side can spell is not an
identity.

**Inbound only, and that is a claim rather than a limit nobody has lifted yet.**
§1f's rule is that a qualifying attribute belongs to the side of the wire that
DECLARES it, and every attribute this key reads sits on a listener or on an
implementation — the receiving side. An outbound catalog declaring the key would
state a peer's configuration as this module's own, so `_validate_metadata_from`
refuses it there (`engines/annotation_driven.py`). A catalog that reaches `inbound`
through a `resolves.direction` flip is not refused, and the pass reads each ROW's own
`direction` rather than the catalog's declared one, because by the time it runs the
flip has already happened and the column is final.

**What is read.** `effective_annotation_uses` — the same widened annotation set the
endpoint row was derived from, for `_from_mapping_attributes`'s own reason: the raw
`annotations` view differs from it in three ways (a module-local composed annotation,
a repeatable container javac folded, a declaration on an interface the class does not
repeat) and in each the row derives while its attributes read as absent. The named
annotation is looked for on the handler AND on the handler's ENCLOSING TYPE, because
the first consumer's attribute sits on a type-level annotation on the class that
implements a contract, while the row's handler is that class's own overriding method.

Runs AFTER `apply_protocol_hints`, the `record_request_requirements` reason: an entry
names its row by the row's identity columns and `protocol` is one of them.

Cost per resolve (GUIDELINES §8.7): one read of `endpoints`, and one
`effective_annotation_uses` walk per catalog that DECLARES the key and owns an
inbound row — no shipped catalog declares it yet, so today that is zero, and the
`endpoints` read itself is skipped where nothing declared the key. The annotation
lookup is built once per handler, so a verbless mapping's eight rows are one lookup.
"""

from typing import Any

from sextant.application.ports.catalogs import Catalog
from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.engines.annotation_driven import (
    effective_annotation_uses,
    metadata_from,
)
from sextant.domain.closed_sets import Direction
from sextant.domain.symbols import bare_descriptor, names_a_type, owner_of

# The one form of value this pass refuses to answer for, spelled as
# `engines/scheduled_work.py` spells it and for its reason: a property placeholder is
# resolved by the framework at startup out of configuration a repository cannot see
# (GUIDELINES §8.2), so the value is carried VERBATIM and the row says `unresolved`
# rather than guessing what was deployed.
_PLACEHOLDER = "${"


def record_endpoint_attributes(workspace: Workspace, catalogs: list[Catalog]) -> None:
    """Spec 2026-09-22 §1f. One `endpoint_metadata` row per attribute value a
    `metadata_from` entry names, against the inbound endpoints its own catalog minted.

    Every catalog is read, including those that derive no row here, because reading is
    what validates: a `metadata_from` block of the wrong shape is refused naming the
    file whether or not this module has a row to write from it.
    """
    declared = [(catalog, metadata_from(catalog)) for catalog in catalogs]
    declaring = [(catalog, entries) for catalog, entries in declared if entries]
    if not declaring:
        return
    endpoints = [
        row for row in workspace.query("endpoints") if row["direction"] == Direction.INBOUND.value
    ]
    rows: list[dict[str, Any]] = []
    for catalog, entries in declaring:
        rows.extend(_from_annotation_attributes(endpoints, catalog, entries, workspace))
    # An empty list writes nothing rather than a no-op statement — the
    # `record_open_questions` discipline `record_request_requirements` keeps.
    if rows:
        workspace.derive("endpoint_metadata_insert", rows=rows)


def _from_annotation_attributes(
    endpoints: list[dict[str, object]],
    catalog: Catalog,
    entries: list[dict[str, Any]],
    workspace: Workspace,
) -> list[dict[str, Any]]:
    """This catalog's entries against the rows THIS catalog minted.

    `catalog_id` is the filter and it is load-bearing: two catalogs of one framework
    family routinely match the same handler class, and an entry written against another
    catalog's row would state one framework's attribute about another framework's
    endpoint. A row naming no handler is skipped: there is nothing to read an annotation
    off.
    """
    mine = [
        endpoint
        for endpoint in endpoints
        if endpoint.get("catalog_id") == catalog.id and endpoint.get("handler") is not None
    ]
    if not mine:
        return []
    annotations = effective_annotation_uses(workspace, catalog)
    out: list[dict[str, Any]] = []
    # One lookup per handler (GUIDELINES §8.7): a verbless mapping is one handler and
    # eight rows, and every one of them reads the same two declarations.
    args_of: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for endpoint in mine:
        handler = bare_descriptor(str(endpoint["handler"]))
        if handler not in args_of:
            args_of[handler] = _uses_by_annotation(annotations, handler)
        for entry in entries:
            for args in args_of[handler].get(entry["annotation"], []):
                for value in _values(args, entry):
                    out.append(_entry(endpoint, kind=entry["kind"], value=value))
    return out


def _uses_by_annotation(
    annotations: dict[str, list[dict[str, Any]]], handler: str
) -> dict[str, list[dict[str, Any]]]:
    """The annotation uses that qualify this handler: annotation descriptor -> the
    `args` mappings written at the NEAREST site carrying that annotation.

    Both sites are looked at, and both are required. A listener annotation carrying a
    consumer group sits on the handler METHOD; a starter annotation carrying a task
    queue sits on the CLASS that implements a contract interface, while the row's
    handler is that class's own overriding method. Reading only one site would silently
    drop a whole family of attributes, which is the quiet miss the key exists to close.

    **NEAREST WINS, per annotation: the enclosing type is read only where the handler
    does not carry that annotation at all.** A union would state both values, and both
    ways that goes are wrong rather than merely noisy. A class-level listener naming one
    consumer group and a method-level one naming another would put BOTH groups on one
    endpoint — one of them a group that endpoint is not in. And a class-level use with
    the attribute unwritten, beside a method-level use that writes it, would emit the
    entry's measured `absent_value` next to the explicit value contradicting it — a
    fabricated default, which is the exact failure `absent_value` is fenced against.

    Nearest-wins is also the only rule of the two this module can state without claiming
    something about frameworks it has not measured. `_from_mapping_attributes` unions its
    two sites and cites the framework method that performs the union
    (`ParamsRequestCondition.combine`); nothing here has such a citation, and a catalog
    whose framework really does union two sites can say so in a later key rather than
    have this one assume it.
    """
    owner = owner_of(handler)
    uses: dict[str, list[dict[str, Any]]] = {}
    for use in annotations.get(handler, []):
        uses.setdefault(str(use["annotation"]), []).append(use["args"])
    if owner is None:
        return uses
    # The handler's own fqns, fixed before the second site is read: `uses` grows while
    # the enclosing type is walked, so asking `fqn not in uses` inside the loop would
    # let a repeated class-level annotation past its own first use.
    nearest = frozenset(uses)
    for use in annotations.get(owner, []):
        fqn = str(use["annotation"])
        if fqn not in nearest:
            uses.setdefault(fqn, []).append(use["args"])
    return uses


def _values(args: dict[str, Any], entry: dict[str, Any]) -> list[str]:
    """The values one entry reads off one annotation use, in the order written.

    An attribute written as an array is one value per element (the queue list a
    starter annotation carries); a scalar is one value. An element this pass cannot
    spell — a nested annotation, or a SYMBOL REFERENCE (D00 §5a's literal model spells
    both a class reference and an enum reference as one) — is dropped rather than
    rendered, the `scheduled_work._verbatim` rule: an attribute that was written and
    could not be read must never become a stated value with an invented one. A symbol
    is not a wire name: `com/acme/OrderFactory#` in a `value` column would read as the
    queue, group or selector a peer should look for.

    An ABSENT attribute writes the entry's `absent_value` where the catalog declares
    one and NOTHING otherwise. A default never reaches the annotation use — the
    framework applies it after the class file is written — so a catalog that has
    measured the annotation's own `AnnotationDefault` states it and cites the probe
    beside the line, and a catalog that has not measured one says nothing. Silence is
    the honest answer where nobody measured the default (GUIDELINES §8.2).
    """
    if entry["attribute"] not in args:
        absent = entry["absent_value"]
        return [] if absent is None else [absent]
    written = args[entry["attribute"]]
    elements = written if isinstance(written, list) else [written]
    return [text for text in (_text(element) for element in elements) if text]


def _text(value: object) -> str | None:
    """One attribute value as the column spells it, or None where it is not a value
    this pass can spell.

    `bool` is checked before `int` deliberately — Python's `bool` IS an `int`, so an
    `isinstance(value, int)` test alone would spell `True` as `1` — and a boolean is
    written lowercase, which is the text a JSON boolean reads back as and the spelling
    `annotation_driven._unless_equals` already compares against. An EMPTY string is
    dropped by the caller: a row whose `value` is empty states a queue, a group or a
    selector named by nothing, and the absence of a row is the statement that the
    declaration named none.

    A string carrying the SYMBOL GRAMMAR's type marker is a class or enum reference the
    scanner recorded as a symbol (D00 §5a spells both that way), not a name anything
    puts on a wire, so it is dropped here rather than published as one. The question is
    asked through `names_a_type` because the marker is the grammar and
    `tests/architecture/test_symbol_grammar_confinement.py` keeps every reading of it in
    `domain/symbols.py`. The cost is stated: a literal that merely CONTAINS the marker —
    a selector expression quoting a `#` — is dropped with it. That is a miss rather than
    a wrong row, which is the direction NFR-2 asks for, and no wire name in any
    vocabulary this key serves today carries one.
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return None if names_a_type(value) else value
    if isinstance(value, int | float):
        return str(value)
    return None


def _entry(endpoint: dict[str, object], *, kind: str, value: str) -> dict[str, Any]:
    """One `endpoint_metadata` row against an inbound endpoint: the row's own identity
    columns as they stand now, `caller` the handler — `request_requirements._entry`'s
    column shape, a second literal dict rather than a shared helper, which is what this
    codebase already does across passes.

    `name` is NULL because a qualifying attribute has a KIND and a value and no name of
    its own — the catalog's `kind` is the name of the thing, the way a partition key's
    row carries a value and no name. `requirement` is NULL because a qualifying
    attribute states nothing about what the framework demands of a request. `direction`
    is the ROW's, not a constant: the row is inbound by the filter above, and reading
    it is what keeps that true rather than assumed.
    """
    return {
        "protocol": endpoint["protocol"],
        "direction": endpoint["direction"],
        "method": endpoint["method"],
        "path": endpoint["path"],
        "caller": endpoint["handler"],
        "kind": kind,
        "name": None,
        "value": value,
        "resolution": "unresolved" if _PLACEHOLDER in value else "resolved",
        "evidence": "compiler",
        "requirement": None,
    }
