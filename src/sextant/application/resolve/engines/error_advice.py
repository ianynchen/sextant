"""`error_advice` engine (D02 §2's `error_advice` style, 2O design §4b).

The second NON-WIRE style, and it derives into `error_handlers` for the same
reason `scheduled_work` has its own table: an exception handler is not a
boundary anyone can address, it is what happens INSIDE one that already exists.
Publishing it as an endpoint would invent a route the framework does not serve.

**The container rule is the framework's, not an approximation of it.** A
handler method counts only where its declaring type is a handler CONTAINER, and
the framework knows two kinds:

* an ADVICE class, which applies to controllers other than itself — to every
  controller in the application when it declares no narrowing attributes, and
  to the subset its attributes name when it does;
* a CONTROLLER, whose own handler methods are scoped to that controller alone.

Those are different claims, so `declared_by` records which annotation made the
type a container. A single NULL `scope` cannot tell "advice with no narrowing
attributes" (every controller) from "a controller's own handler" (one
controller), and reporting the second as the first would widen a handler's
reach across the whole application.

**Meta-annotations are followed the way the framework follows them**, for
module-local types: the composition pre-pass (`resolve/effective_annotations.py`)
widens both the advice set and the controller set to every annotation type this
module declares that is transitively meta-annotated with one of them. That is
the same mechanism `annotation_driven` uses for its own type-level gate, and it
exists because the framework's own predicate is meta-annotation aware — a check
for a literal annotation name rejects a valid custom stereotype (§8.1 rule 1,
`A-C7`). A composed annotation whose type lives in an unscanned jar is a stated
boundary of the pre-pass, not of this engine.

**Exception types: the annotation's value, else the parameter type** (2O design
§4b). The second half is deliberately narrower than the framework's own test.
The framework asks whether a parameter is assignable to the language's throwable
root; this workspace can only answer that where the chain is READABLE — the
parameter type IS one of the roots the catalog names, or its own scanned
superclass chain reaches one. A handler whose exception parameter comes from an
unscanned jar therefore derives no row from that parameter, and COVERAGE says
so. The under-report is the safe direction and the only honest one: nothing but
a throwable reaches a throwable root, so this can never publish an ordinary
argument as a handled exception.

**Two stated boundaries of this phase**, both from 2O design §4b:

* a status computed inside a response-entity body is `fluent` territory — body
  analysis that derives no endpoint — and is not read here. `status` is NULL
  for such a handler, and NULL is an answer rather than a gap this column
  fills in.
* a status annotation on the EXCEPTION CLASS is readable only where that class
  is in this module's own facts. A third-party exception's own annotation lives
  in a jar this workspace never scanned.
"""

import json
from typing import Any

from sextant.application.ports.catalogs import Catalog, CatalogError
from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.effective_annotations import composed_mapping_rows
from sextant.application.resolve.shapes.rooting import _catalog_symbol, catalog_symbols, root_type
from sextant.domain.symbols import bare_descriptor, is_type_descriptor, owner_of

_HANDLER_ANNOTATION = "handler_annotation"
_ADVICE_ANNOTATIONS = "advice_annotations"
_CONTROLLER_ANNOTATIONS = "controller_annotations"
_SCOPE_FROM = "scope_from"
_STATUS_ANNOTATION = "status_annotation"
_STATUS_FROM = "status_from"
_EXCEPTION_ROOTS = "exception_roots"
_REQUIRED_MATCHES = (
    _HANDLER_ANNOTATION,
    _ADVICE_ANNOTATIONS,
    _CONTROLLER_ANNOTATIONS,
    _SCOPE_FROM,
    _STATUS_ANNOTATION,
    _STATUS_FROM,
    _EXCEPTION_ROOTS,
)
_LIST_MATCHES = (
    _ADVICE_ANNOTATIONS,
    _CONTROLLER_ANNOTATIONS,
    _SCOPE_FROM,
    _STATUS_FROM,
    _EXCEPTION_ROOTS,
)


def run(workspace: Workspace, catalog: Catalog) -> None:
    """One row per `(handler, exception)` pair.

    A handler naming three exception types is three rows: each is a distinct,
    separately answerable fact, and an array in one cell joins against nothing.
    A handler whose exception types cannot be read at all is no rows — an
    error handler with no exception is a claim about nothing.
    """
    _validate_matches(catalog)
    rules = _Rules.of(workspace, catalog)
    rows: list[dict[str, Any]] = []
    for method in sorted(rules.handlers):
        owner = owner_of(bare_descriptor(method))
        if owner is None:
            # A free function declares no type at all, so there is no container
            # to find. Not reachable from a JVM scan — every handler is a
            # member — and answered rather than assumed away.
            continue
        container = rules.container_of(owner)
        if container is None:
            continue
        for exception in rules.exceptions_of(method):
            rows.append(
                {
                    "handler": method,
                    "advice": owner,
                    "declared_by": container.annotation,
                    "scope": container.scope,
                    "exception": exception,
                    "status": rules.status_of(method, exception),
                    "response_shape": rules.response_shape_of(method),
                    # Every column above is read off a declaration the compiler
                    # wrote into the class file, so there is nothing here that
                    # a later pass could settle differently. A value that could
                    # not be read is absent (NULL), never defaulted — the rule
                    # `tests/architecture/test_defaulted_identity_values.py`
                    # makes enforceable on the wire side.
                    "resolution": "resolved",
                    "evidence": "compiler",
                    "catalog_id": catalog.id,
                }
            )
    workspace.derive("error_handlers_insert", rows=rows)


class _Container:
    """One handler container: which annotation made it one, and the scope
    attributes that annotation declared, verbatim."""

    __slots__ = ("annotation", "scope")

    def __init__(self, annotation: str, scope: str | None) -> None:
        self.annotation = annotation
        self.scope = scope


class _Rules:
    """Everything one catalog asks of one workspace, read once.

    A class rather than a bag of parameters because the reads are shared:
    the annotation universe (real rows plus the composition pre-pass's
    synthesized ones) answers the container question, the exception question
    and the status question, and querying it three times would let the three
    disagree about what this module declares.
    """

    def __init__(
        self,
        handlers: dict[str, dict[str, Any]],
        containers: dict[str, _Container],
        statuses: dict[str, str],
        signatures: dict[str, dict[str, Any]],
        exception_types: set[str],
        wrappers: list[dict[str, Any]],
    ) -> None:
        self.handlers = handlers
        self.containers = containers
        self._statuses = statuses
        self._signatures = signatures
        self._exception_types = exception_types
        self._wrappers = wrappers

    @classmethod
    def of(cls, workspace: Workspace, catalog: Catalog) -> "_Rules":
        matches = catalog.matches
        rows = _annotation_universe(workspace, catalog)
        # LISTS or scalars (§3.1). The asymmetry §3.1 names as the proof this was
        # accident rather than design lived in THIS file: the advice and controller
        # keys below already took plural lists while these two took one string.
        handler_fqns = catalog_symbols(
            matches[_HANDLER_ANNOTATION], f"{catalog.source}: {_HANDLER_ANNOTATION}"
        )
        status_fqns = catalog_symbols(
            matches[_STATUS_ANNOTATION], f"{catalog.source}: {_STATUS_ANNOTATION}"
        )
        advice = {_catalog_symbol(fqn) for fqn in matches[_ADVICE_ANNOTATIONS]}
        controllers = {_catalog_symbol(fqn) for fqn in matches[_CONTROLLER_ANNOTATIONS]}
        scope_keys = [str(key) for key in matches[_SCOPE_FROM]]
        status_keys = [str(key) for key in matches[_STATUS_FROM]]

        methods = {str(row["symbol"]) for row in workspace.query("method_symbols")}
        handlers = {
            str(row["target"]): row["args"]
            for row in rows
            if row["annotation"] in handler_fqns and str(row["target"]) in methods
        }
        containers: dict[str, _Container] = {}
        for row in rows:
            name = str(row["annotation"])
            if name not in advice and name not in controllers:
                continue
            target = bare_descriptor(str(row["target"]))
            if not is_type_descriptor(target):
                # The annotation sits on a member, not on a type. Both
                # container annotations are type-level in the framework, and a
                # member-level use could only come from a hand-built fact — it
                # names no container, so it contributes none.
                continue
            # An ADVICE annotation wins over a controller one on the same type.
            # A type carrying both is a controller that is also advice, and the
            # advice reading is the wider claim of the two — reporting the
            # narrower would say the handler answers for this controller alone
            # when the framework applies it to every one.
            existing = containers.get(target)
            if existing is not None and existing.annotation in advice:
                continue
            containers[target] = _Container(
                annotation=name,
                scope=_scope(row["args"], scope_keys) if name in advice else None,
            )
        statuses = {
            bare_descriptor(str(row["target"])): status
            for row in rows
            if row["annotation"] in status_fqns
            for status in [_status(row["args"], status_keys)]
            if status is not None
        }
        signatures = {
            str(row["symbol"]): json.loads(str(row["signature"]))
            for row in workspace.query("method_declarations")
            if row["signature"] is not None
        }
        return cls(
            handlers=handlers,
            containers=containers,
            statuses=statuses,
            signatures=signatures,
            exception_types=_exception_types(workspace, matches[_EXCEPTION_ROOTS]),
            wrappers=list(catalog.wrappers),
        )

    def container_of(self, owner: str) -> "_Container | None":
        """THE CONTAINER GATE. The declaring type's container record, or None
        where that type is neither advice nor a controller.

        A handler annotation on an ordinary class registers nothing: the
        framework finds handler methods by first finding the container, so such
        a method is ordinary code that happens to be annotated. Publishing it
        would report an error contract the running system never answers with —
        and it would have to invent `declared_by` and `scope` to do so, since
        there is no container declaration to read either from.
        """
        return self.containers.get(owner)

    def exceptions_of(self, method: str) -> list[str]:
        """The exception types this handler answers for, sorted.

        The declaration's own value first, which is the framework's own first
        answer and needs no hierarchy at all. Only where the declaration names
        none does the parameter list answer, and then only for a parameter this
        workspace can PROVE is a throwable.
        """
        declared = _class_references(self.handlers.get(method))
        if declared:
            return sorted(declared)
        return sorted(
            parameter
            for parameter in self._parameter_types(method)
            if parameter in self._exception_types
        )

    def status_of(self, method: str, exception: str) -> str | None:
        """The status the declaration names, on the handler or on the exception
        class — in that order, which is the framework's own precedence: a
        status written on the handler answers for this handler, while one on the
        exception class is the default for every handler that does not.

        NULL where neither carries one, and NULL is an answer: a status
        computed inside a response-entity body is a stated boundary of this
        phase, and an exception class from an unscanned jar carries its
        annotation where this workspace cannot read it.
        """
        return self._statuses.get(bare_descriptor(method)) or self._statuses.get(exception)

    def response_shape_of(self, method: str) -> str | None:
        """The symbol of the type this handler returns, unwrapped through the
        catalog's own declared envelopes — NULL where it returns nothing.

        `shapes/contracts.py`'s `_payload_descriptor` rule, followed rather than
        re-invented: rooting that stops ON a declared envelope is no payload (a
        raw envelope, and every envelope reached through an erased descriptor),
        and a reference carrying no wire type is the `void` return. Unwrapping
        past an envelope NOBODY declared is refused there too (D02 §2a) — the
        rooted reference is returned as it stands, which for an unfamiliar
        generic is the generic itself rather than a guess at what it holds.
        """
        returns = self._signatures.get(method, {}).get("returns")
        if not isinstance(returns, dict):
            return None
        rooted = root_type(returns, self._wrappers)
        if rooted.unmatched_wrapper:
            return None
        if rooted.reference.get("wire_type") in (None, ""):
            return None
        return rooted.symbol

    def _parameter_types(self, method: str) -> list[str]:
        parameters = self._signatures.get(method, {}).get("parameters")
        if not isinstance(parameters, list):
            return []
        # `erased_symbol` first: these are tested for membership in the set of
        # throwable types this workspace DECLARES, which is a comparison against other
        # declarations. A generic advice base — `handle(E ex)` where
        # `E extends BusinessException` — reads `E` from the signature and matches no
        # declared type, so the handler's exception list silently empties. The erasure
        # is the bound, which is a real declared type and is what this read before.
        return [
            str(entry.get("erased_symbol") or entry["type"]["symbol"])
            for entry in parameters
            if isinstance(entry, dict) and isinstance(entry.get("type"), dict)
        ]


def _annotation_universe(workspace: Workspace, catalog: Catalog) -> list[dict[str, Any]]:
    """Every annotation this module declares, plus the composition pre-pass's
    synthesized rows for module-local composed annotations, `args` decoded.

    `annotation_driven._synthetic_annotations`'s own read, kept here rather than
    shared: that function serializes its result back to JSON text for a bound
    SQL parameter, and this engine's rows never reach SQL as annotations. The
    seeds differ too — this pass composes the CONTAINER annotations, never a
    mapping — so sharing the function would mean sharing a parameter list that
    means something different on each side.
    """
    matches = catalog.matches
    rows = [
        {
            "target": str(row["target"]),
            "annotation": str(row["annotation"]),
            "args": json.loads(str(row["args"])) if row["args"] is not None else {},
        }
        for row in workspace.query("annotations")
    ]
    scanned = {str(row["symbol"]) for row in workspace.query("interface_symbols")}
    seeds = {
        _catalog_symbol(fqn)
        for key in (_ADVICE_ANNOTATIONS, _CONTROLLER_ANNOTATIONS)
        for fqn in matches[key]
    }
    return [*rows, *composed_mapping_rows(rows, scanned, seeds)]


def _exception_types(workspace: Workspace, roots: object) -> set[str]:
    """Every type this workspace can PROVE is a throwable: the catalog's own
    declared roots, plus every scanned class whose `superclass` chain reaches
    one.

    The roots are catalog data rather than engine data because they are NAMES —
    the language's own throwable hierarchy is knowledge about a platform, and
    D02's rule is that a name a rule keys on lives in a catalog file (§8.1's
    "a language's rules bind exactly as a framework's do" cuts the same way:
    read the rule, encode the rule, and keep the name out of the engine).

    The walk is a fixpoint over the scanned `superclass` edges and terminates:
    each round adds only classes not already in the set, and the set is bounded
    by the number of scanned classes. A chain that leaves this module's own
    facts — `extends` a class from an unscanned jar — simply stops, and the
    class is not proven. That is the under-report COVERAGE names.
    """
    proven = {_catalog_symbol(root) for root in roots} if isinstance(roots, list) else set()
    edges = {
        bare_descriptor(str(row["symbol"])): bare_descriptor(str(row["superclass"]))
        for row in workspace.query("superclasses")
    }
    while True:
        found = {
            symbol
            for symbol, superclass in edges.items()
            if superclass in proven and symbol not in proven
        }
        if not found:
            return proven
        proven |= found


def _class_references(raw: object) -> set[str]:
    """The class references an annotation argument names — one, or an array of
    them, which is how the same attribute arrives depending on how it was
    written. A value that is not a class reference contributes nothing: only a
    string ending in the type marker is one (D00 §5a), so a number or a nested
    annotation written at that position names no exception."""
    if not isinstance(raw, dict):
        return set()
    value = raw.get("value")
    candidates = value if isinstance(value, list) else [value]
    return {entry for entry in candidates if isinstance(entry, str) and is_type_descriptor(entry)}


def _scope(raw: object, keys: list[str]) -> str | None:
    """The scope attributes the declaration wrote, VERBATIM, as canonical JSON —
    or None where it wrote none, which for an advice class means "every
    controller".

    Only the keys the catalog names are read, and only those the declaration
    actually carries are written. Reading whatever attribute happens to be
    present would publish an unrelated one as a scope: the annotation carries
    attributes that are not scopes at all, and a scope is what decides WHICH
    controllers a handler answers for.
    """
    if not isinstance(raw, dict):
        return None
    written = {key: raw[key] for key in keys if key in raw}
    if not written:
        return None
    return json.dumps(written, sort_keys=True, separators=(",", ":"))


def _status(raw: object, keys: list[str]) -> str | None:
    """The status the declaration names, verbatim as the literal was read — an
    enum reference stays the symbol the facts carry, because the mapping from a
    framework's status constant to a number is framework knowledge nothing here
    has measured.

    The catalog's own key order decides, and it is an ALIAS ORDER rather than a
    set: the annotation spells one status under more than one attribute name,
    and the first the declaration writes is the one it means.
    """
    if not isinstance(raw, dict):
        return None
    for key in keys:
        value = raw.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _validate_matches(catalog: Catalog) -> None:
    """Refuses a broken catalog before any declaration is read — the
    `injected_client._validate_matches` precedent."""
    matches = catalog.matches
    missing = [key for key in _REQUIRED_MATCHES if key not in matches]
    if missing:
        raise CatalogError(
            f"loading catalog {catalog.source}: `matches` is missing "
            f"{', '.join(missing)} — `error_advice` needs "
            f"{', '.join(_REQUIRED_MATCHES)} (2O design §4b)"
        )
    for key in _LIST_MATCHES:
        declared = matches[key]
        valid = (
            isinstance(declared, list)
            and bool(declared)
            and all(isinstance(entry, str) for entry in declared)
        )
        if not valid:
            raise CatalogError(
                f"loading catalog {catalog.source}: `{key}` must be a non-empty list of "
                f"strings, got {declared!r} (2O design §4b)"
            )
