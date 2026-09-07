"""Annotation-driven engine for endpoint derivation (D02 §2).

Framework knowledge — which annotation marks a controller, which annotation
maps to which HTTP method, where the path argument lives — is data, read
from `matches` and carried, unmodified, through to the derivation as bound
parameters. No framework name appears in this module's code.
"""

import json
from dataclasses import dataclass
from typing import Any

from sextant.application.ports.catalogs import Catalog, CatalogError
from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.effective_annotations import (
    composed_mapping_rows,
    folded_rows,
    inherited_rows,
)
from sextant.application.resolve.shapes.contracts import _payload_descriptor
from sextant.application.resolve.shapes.expansion import _enum_symbols, _rules_of
from sextant.application.resolve.shapes.rooting import _catalog_symbol
from sextant.domain.closed_sets import Direction
from sextant.domain.paths import serves_urls
from sextant.domain.symbols import bare_descriptor, member_name


def run(workspace: Workspace, catalog: Catalog) -> None:
    """Passes the catalog's own protocol, direction, annotation identifiers and
    mapping declaration through to the derivation as bound parameters. The
    engine here is generic: it never names a framework or a protocol, only
    forwards what the catalog declares.

    A CORROBORATION-ONLY catalog derives nothing here and returns at once
    (2O design §1b, fix round 2's I-2): it declares `corroborates` and no
    `mapping` because its annotation states that a class SERVES something
    without stating what — no address, no member rule, nothing this
    derivation could bind — so its whole contribution is the open question
    `gaps` files instead. Deriving a row from it would mint an endpoint with
    no address, which is precisely what the annotation cannot support."""
    if _corroboration(catalog) is not None and "mapping" not in catalog.matches:
        return
    mapping = catalog.matches["mapping"]
    _validate_naming(catalog, mapping)
    declared_on = _declared_on(catalog)
    type_annotation = catalog.matches.get("type_annotation")
    type_annotation_fqn = None if type_annotation is None else _catalog_symbol(type_annotation)
    flip = _direction_flip(workspace, catalog)
    prefix_annotation = mapping["prefix_annotation"]
    # Optional too (Retrofit, spring-jms): no class-level prefix shape.
    prefix_fqn = None if prefix_annotation is None else _catalog_symbol(prefix_annotation)
    mapping_annotations = [_mapping_annotation(mapping, m) for m in mapping["annotations"]]
    workspace.derive(
        "endpoints",
        protocol=catalog.protocol,
        direction=catalog.direction,
        # Optional (D02 §2, amended): absence means "no type-level gate".
        type_annotation=type_annotation_fqn,
        # 2I design §4: WHICH KIND of construct this catalog's rules describe,
        # or NULL where the catalog describes declarations on any construct —
        # which is every catalog written before it. One annotation family can
        # mark both a service and the generated client stub of one, and the
        # two are opposite directions of the same wire; without this the two
        # catalogs would each derive both, and a module would be reported as
        # calling the very operations it serves.
        declared_on=declared_on,
        # 2I design §4's SEI fence — `derive_endpoints.sql`'s own comment
        # states what it refuses and why it is scoped rather than universal.
        # Read only for the one catalog shape that can be wrong without it, so
        # every other catalog binds an empty list and the fence's own
        # `$direction`/`$declared_on` test already evaluates false for it.
        locally_implemented=(
            _locally_implemented(workspace)
            if catalog.direction == "outbound" and declared_on == "interface"
            else []
        ),
        prefix_annotation=prefix_fqn,
        # `method` is absent for an annotation that pre-sets none, and the
        # derivation reads that absence as "every method in all_methods".
        mapping_annotations=mapping_annotations,
        path_from=list(mapping["path_from"]),
        # `OI-35`: the name sources that live on OTHER annotations of the same
        # declaration, consulted in the order the catalog lists them and only
        # where every `path_from` alias was absent. Empty for every catalog that
        # declares none, which is every catalog written before this word — an
        # empty list matches no annotation, so the lookup finds nothing and the
        # composed address is exactly what it was. The ordinal is attached HERE
        # rather than relied on in the query, because a list's order is not a
        # column and `min_by` needs one to be able to say "first present".
        path_from_siblings=_sibling_sources(catalog, mapping),
        prefix_from=list(mapping["prefix_from"]),
        peer_from=list(mapping.get("peer_from", [])),
        method_from=mapping["method_from"],
        all_methods=list(mapping["all_methods"]),
        catalog_id=catalog.id,
        # Optional (media evidence kind (a), spec §4): absent on every
        # catalog that declares neither, so it derives NULL with zero YAML
        # change — the HTTP catalogs are the only ones that declare these.
        consumes_from=list(mapping.get("consumes_from", [])),
        produces_from=list(mapping.get("produces_from", [])),
        # 2H design §1's two naming forms, both optional and both inert
        # unless declared. `path_fallback` says what the declared name is when
        # every `path_from` alias is absent; `qualifier_from`/
        # `qualifier_separator` compose a scope named on the SAME annotation
        # in front of that name. Absent on every catalog written before them,
        # which is what keeps their derivations byte-identical.
        path_fallback=mapping.get("path_fallback"),
        # The catalog-level word's own prefix data, for the one row shape that
        # carries no mapping annotation to read a per-annotation word off — an
        # unannotated exposed member (`$members`). Empty where the catalog
        # declares no fallback at all, and empty for `construct_name`.
        path_fallback_prefixes=list(_PATH_FALLBACKS.get(str(mapping.get("path_fallback")), ())),
        qualifier_from=list(mapping.get("qualifier_from", [])),
        qualifier_separator=mapping.get("qualifier_separator"),
        # 2I design §2's two QName forms, both optional and both inert unless
        # declared. `qualifier_format` names a composition that is not a
        # separator at all — `{scope}name` is one bracketed token, and its
        # closing brace has no separator equivalent — so it REPLACES
        # `qualifier_separator` rather than joining it. `namespace_default`
        # says what the scope is when the attribute carrying it is absent,
        # which for a spec that defines that default is a fact about the
        # framework rather than a guess.
        qualifier_format=mapping.get("qualifier_format"),
        # The declared word's TEMPLATE, not the word: see `_NAMESPACE_DEFAULTS`.
        # NULL where the catalog declares no default, which is what keeps the
        # derivation below inert for every catalog but the ones that ask.
        namespace_template=_NAMESPACE_DEFAULTS.get(str(mapping.get("namespace_default"))),
        # 2I design §2, word 3: the class-gate MEMBER rule. NULL where a
        # catalog declares none, which is every catalog whose framework
        # exposes only what an annotation marks.
        members=mapping.get("members"),
        # What joins a TYPE-level prefix to the address it prefixes, and the
        # character deduped where both halves already spell it. Optional and
        # inert while absent, so a catalog composing a Kafka topic — which has
        # no segments to join — keeps the bare concatenation it always had.
        path_separator=mapping.get("path_separator"),
        # 2O Task 7 Step 3: a CONSTANT prefix the framework itself puts in
        # front of every address this catalog derives — not read from any
        # annotation, because no annotation states it. It joins the front of
        # the type-level prefix under the same seam rule, so a catalog
        # declaring none composes exactly what it always did.
        path_prefix=mapping.get("path_prefix"),
        # 2O design §8: this catalog's addresses are URLs THIS MODULE SERVES,
        # so the derivation composes the URL the framework serves rather than
        # the characters the two annotations happened to spell (CP-1). Decided
        # here, from the catalog's own protocol and direction, because
        # `storage/` may name no protocol (ARCHITECTURE §10) — the same reason
        # the rule itself is mirrored there rather than imported from
        # `domain/paths.py`, which `combinator`/`single_call`/`fluent` call
        # directly. The gate is `serves_urls`, spelled once so this bind and
        # those calls cannot answer differently. This engine's OTHER minting
        # site, `_reply_row`, asks it nowhere: that row's direction is a
        # literal `outbound`, so the seam can never reach it (R8).
        canonical_path=serves_urls(catalog.protocol, catalog.direction),
        # D02 §2c's `resolves.direction`, the ONE resolution rule that shipped:
        # what a row's direction becomes where the catalog's condition holds,
        # NULL where the catalog declares no rule — which is every catalog but
        # the one whose annotation family genuinely faces both ways, and what
        # keeps their derivations byte-identical.
        flip_direction=flip.direction,
        # Which OWNERS the condition holds for, and what handles each flipped
        # declaration. Both empty where there is no rule.
        flip_owners=flip.owners,
        flip_handlers=flip.handlers,
        # `$canonical_path`'s twin for a FLIPPED row, decided the same way from
        # the same seam (`serves_urls`) — the resolved direction is the row's
        # direction, so it is the direction the address question is asked of.
        # Without this a flipped row's address would be canonicalized under the
        # rule for the direction the catalog DECLARED rather than the one the
        # row took, and an inbound route the module serves would keep a
        # spelling the framework does not answer at — which also splits it from
        # the identical route a controller's own mapping derives, and stops the
        # two merging (ruling R12).
        flip_canonical_path=flip.canonical_path,
        # 2E design §2, §3: the effective-annotations pre-pass UNFOLDS every
        # repeatable container the catalog names (`OI-36`, first, so the two
        # passes below see a folded use as an ordinary one) and widens
        # this catalog's own mapping fqns to every module-local annotation
        # type transitively meta-annotated with one of them PLUS, for a
        # catalog that declares its own type-level gate, every mapping a
        # scanned interface/superclass method declares that an implementing
        # method doesn't repeat (Task 7, spec §3 — see `_synthetic_annotations`
        # for why the inheritance half is gated), computed once per catalog
        # (its own mapping fqns seed a different closure and a different
        # inheritance walk each time) and handed to the SQL as synthetic
        # `annotations` rows rather than as a second code path there.
        synthetic_annotations=_synthetic_annotations(
            workspace, catalog, mapping_annotations, prefix_fqn, type_annotation_fqn
        ),
    )
    # Optional (D02 §2, amended): a catalog with no `reply` block declares no
    # second-row rule at all — the HTTP catalogs, which never see @SendTo.
    if "reply" in catalog.matches:
        _derive_replies(workspace, catalog)


# D02 §2's `corroborates` block: an optional, catalog-declared list of
# CLASS-LEVEL annotations that mark a class as serving something without
# naming what it serves (2O design §1b, fix round 2's I-2). Absent on every
# catalog written before it, and inert while absent — `gaps` returns an empty
# list and `run` is untouched.
_CORROBORATES = "corroborates"
_CLASS_ANNOTATIONS = "class_annotations"

# Why a corroborated class earns an open question rather than a row. Stated
# in terms of what is MISSING — an identity — rather than of any framework:
# the annotation is real evidence that this class serves something, and it is
# the only evidence, because whatever else would have named the address was
# not readable in this workspace (2O design §1b's published-dependency case).
_UNCORROBORATED = (
    "the annotation marks this class as serving a declared contract but names "
    "no address of its own, and no endpoint of this protocol names any of its "
    "methods as a handler — the identity the other style reads off the "
    "generated supertype's own facts never reached this workspace, so the "
    "class is visible and its wire identity is not"
)


def gaps(workspace: Workspace, catalog: Catalog) -> list[dict[str, Any]]:
    """The `service_identity` open questions a CORROBORATION catalog earns
    (2O design §1b, fix round 2's I-2) — one per annotated class that no
    endpoint of this catalog's protocol names as a handler.

    **Corroboration cannot mint identity, and that is the whole design.** The
    annotation carries no address, so a class it flags is either already
    derived by the style that CAN read one — in which case this adds nothing
    and files nothing — or it is not, in which case the honest answer is a
    question naming the class, not an endpoint row with an invented address
    and not silence. Silence is what the unshipped version of this cost: a
    class whose generated supertype lives in a dependency the workspace never
    scanned produced no row and no question at all (2O design §1b: "silence is
    not an outcome").

    Read back off `endpoints` rather than by re-walking another engine's
    match, unlike `supertype_derived.gaps`/`injected_client.gaps`: the
    question this asks is literally "did ANY style derive this class's
    methods", which is a property of the finished table and of no single
    engine's own walk. `resolve/service_identity.py` runs this after
    `derive_endpoints`, so the table is complete when it is read.
    """
    declared = _corroboration(catalog)
    if declared is None:
        return []
    flagged = {_catalog_symbol(fqn) for fqn in declared}
    served = [
        str(row["handler"])
        for row in workspace.query("endpoints")
        if row["handler"] is not None and str(row["protocol"]) == catalog.protocol
    ]
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for annotation in workspace.query("annotations"):
        if str(annotation["annotation"]) not in flagged:
            continue
        target = str(annotation["target"])
        if target in seen:
            continue
        seen.add(target)
        # A handler symbol is `<class symbol><method>(<signature>).` (D00
        # §5a), so a class this protocol already serves through is a prefix of
        # at least one of them. Prefix rather than an owner split: the symbol
        # grammar's own parsing lives in `domain/symbols.py` and a prefix test
        # needs none of it.
        if any(handler.startswith(target) for handler in served):
            continue
        rows.append(
            {
                "protocol": catalog.protocol,
                "method": None,
                "path": bare_descriptor(target),
                "question": "service_identity",
                "candidates": json.dumps(
                    [{"class": target, "reason": _UNCORROBORATED}],
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                "evidence": _UNCORROBORATED,
            }
        )
    return rows


def _corroboration(catalog: Catalog) -> list[str] | None:
    """This catalog's declared corroboration annotations, or `None` where it
    declares none — which is every catalog but the one this block was added
    for. Refused rather than ignored when malformed, the
    `_validate_naming` precedent: an unread key is indistinguishable from a
    typo, and a typo here would silently restore the silence I-2 removes."""
    declared = catalog.matches.get(_CORROBORATES)
    if declared is None:
        return None
    annotations = declared.get(_CLASS_ANNOTATIONS) if isinstance(declared, dict) else None
    if (
        not isinstance(annotations, list)
        or not annotations
        or not all(isinstance(fqn, str) and fqn for fqn in annotations)
    ):
        raise CatalogError(
            f"loading catalog {catalog.source}: `{_CORROBORATES}.{_CLASS_ANNOTATIONS}` must be "
            f"a non-empty list of class-level annotation fqns (2O design §1b), got {annotations!r}"
        )
    return [str(fqn) for fqn in annotations]


# The sources a declared name may fall back to when the annotation carries
# none (2H design §1, form 1). A closed vocabulary rather than a boolean, so
# a second source is a new word here instead of a second catalog key — and so
# a typo is refused rather than read as "no fallback", which would silently
# restore the empty path this form exists to remove.
#
# A MAPPING rather than a set since `OI-5`, and for `_NAMESPACE_DEFAULTS`'
# reason: each word owes the derivation a rule as well as a name, and the rule
# here is WHICH bean-accessor prefixes the word strips off the construct's own
# name before publishing it. `construct_name` strips none, which is what it
# always did.
#
# **The two accessor words are MEASURED, not conventional** (CP-15 rows 3a-5b,
# smallrye-graphql-schema-builder 2.0.0 and 2.18.5, row 5 compiled and RUN).
# The framework's un-named-operation fallback is direction-dependent and the
# direction is chosen by which operation annotation matched: the read direction
# strips `get` and `is`, the write direction strips `set` and nothing else.
# That is why the word sits on an ANNOTATION ENTRY as well as on the catalog —
# one word for the file would make one of the two annotations newly wrong.
#
# The prefixes are engine data rather than catalog data because they are the
# accessor convention of the LANGUAGE these facts come from, not any one
# framework's naming choice; what a catalog states is which direction an
# annotation faces, which is the framework's own fact. The strip's three
# conditions — the prefix, a name longer than it, and an upper-case character
# AT THE SEAM — and the lowercasing of that single character are spelled in
# `derive_endpoints.sql`, because that is where the construct's own name is
# read. `getURL -> uRL` is the edge that tells this rule apart from every
# plausible paraphrase of it, and it is asserted.
_PATH_FALLBACKS: dict[str, tuple[str, ...]] = {
    "construct_name": (),
    "read_accessor_property": ("get", "is"),
    "write_accessor_property": ("set",),
}


def _mapping_annotation(mapping: dict[str, Any], entry: dict[str, Any]) -> dict[str, object]:
    """One `mapping.annotations` entry as the STRUCT row the derivation binds.

    Every field but `fqn` answers "what differs about THIS annotation", which is
    the section's own statement of the shape (D02 §2) — and each is the inert
    value on an entry that declares nothing, so a catalog written before any of
    these words binds exactly what it always did.
    """
    fallback = _entry_fallback(mapping, entry)
    return {
        "fqn": _catalog_symbol(entry["fqn"]),
        "methods": entry.get("method"),
        # 2H design §1: this annotation names a member of a scope, so a
        # declaration under it has no address at all until the scope is
        # found. Absent (the default) on every annotation that names a
        # top-level identity, which is every annotation shipped before it.
        "requires_qualifier": bool(entry.get("requires_qualifier", False)),
        # 2I design §2, word 4: the attribute this rule withdraws itself on,
        # and the value that withdraws it. Both NULL on every annotation
        # that withdraws nothing, which is every annotation shipped before
        # this word — the pair is read as "no filter" and the rule derives
        # exactly what it always did.
        "unless_attribute": _unless_attribute(entry),
        "unless_equals": _unless_equals(entry),
        # `OI-5`: the fallback name rule, resolved to ONE word for this
        # annotation — the entry's own where it states one, the catalog's
        # otherwise. Resolved here rather than coalesced in the query, so the
        # SQL reads one value and never has to know which level wrote it.
        "path_fallback": fallback,
        "path_fallback_prefixes": list(_PATH_FALLBACKS[fallback]) if fallback else [],
    }


def _entry_fallback(mapping: dict[str, Any], entry: dict[str, Any]) -> str | None:
    """This annotation's own fallback word, or the catalog's where it declares
    none — `None` where neither does, which is every catalog that declares no
    fallback at all."""
    declared = entry.get("path_fallback", mapping.get("path_fallback"))
    return None if declared is None else str(declared)


def _sibling_sources(catalog: Catalog, mapping: dict[str, Any]) -> list[dict[str, object]]:
    """`mapping.path_from_siblings` as `{ordinal, annotation, arg}` rows, the
    ordinal counting from the order the catalog wrote (`OI-35`).

    The ORDER is the rule and not a presentation detail: CP-15 rows 1a-1b show
    `getOneOfTheseMethodAnnotationsValue` taking the FIRST source with a value
    out of an array whose `iconst_N` indices ARE that order, so a set would not
    say which name a declaration carrying two of them is served under. It is
    carried as a column because a list's order is not one, and the query's
    "first present wins" is a `min_by` over it.

    Refused rather than ignored when malformed, the `_validate_naming`
    discipline: an unread entry is indistinguishable from a typo, and a typo
    here leaves the operation published under the name the framework does not
    serve it at — a wrong address, which is what this key exists to remove.
    """
    declared = mapping.get("path_from_siblings")
    if declared is None:
        return []
    valid = isinstance(declared, list) and bool(declared)
    if valid:
        valid = all(
            isinstance(source, dict)
            and set(source) == _SIBLING_KEYS
            and isinstance(source.get("annotation"), str)
            and source["annotation"]
            and isinstance(source.get("arg"), str)
            and source["arg"]
            for source in declared
        )
    if not valid:
        raise CatalogError(
            f"loading catalog {catalog.source}: `mapping.path_from_siblings` must be a non-empty "
            f"list of `{{{', '.join(sorted(_SIBLING_KEYS))}}}` entries naming an annotation and "
            f"one of its attributes, in the order the framework consults them — got {declared!r} "
            f"(`OI-35`)"
        )
    return [
        {
            "ordinal": ordinal,
            "annotation": _catalog_symbol(str(source["annotation"])),
            "arg": str(source["arg"]),
        }
        for ordinal, source in enumerate(declared, start=1)
    ]


# The two keys a `path_from_siblings` entry may carry, and no others — a closed
# SHAPE rather than a closed vocabulary, for `_UNLESS_KEYS`' reason: which
# annotation names an operation and which of its attributes carries the name is
# the framework's own convention, and an engine naming one would be naming a
# framework in code.
_SIBLING_KEYS = frozenset({"annotation", "arg"})

# The `mapping.annotations` entry key naming the container annotation whose
# `value` array holds uses of that annotation (`OI-36`). Read in Python only —
# the folded uses reach the query as ordinary synthetic annotation rows, so
# there is no container in the SQL at all.
#
# Usually javac's, and not necessarily: CP-17 rows 2a/2b, 3a/3b and 6a/6b
# measured `@PulsarListeners`, an author-written container for an annotation
# that is NOT `@Repeatable`, whose post-processor registers the union of the
# direct use and every member. The class file is the same shape either way, so
# this reads them the same way and asks whose it is nowhere.
_CONTAINER = "container"

# How a scope composes with the name it qualifies, where a single separator
# cannot say it (2I design §2, word 1). Today's one word is 'qname': the
# XML-namespace notation `{scope}name`, one bracketed token whose closing
# brace has no separator equivalent at all — which is exactly why it is a
# format word and not a two-character `qualifier_separator`, a value
# `_validate_naming` refuses outright because the seam dedupe trims a SET of
# characters. Absent means the separator composition, which is what every
# catalog written before this word already gets.
_QUALIFIER_FORMATS = frozenset({"qname"})

# What the scope IS when the attribute carrying it is absent (2I design §2,
# word 2). Today's one word is 'reversed_package': the JAX-WS default
# `targetNamespace`, `"http://"` + the declaring type's package tokens
# reversed and dot-joined + a trailing `"/"` — pinned against BOTH reference
# implementations (Phase 2I Task 2 checkpoint item 2:
# `com.sun.xml.ws.model.RuntimeModeler#getNamespace` and Apache CXF's
# independent `PackageUtils#getNamespace`, which agree character for
# character, trailing slash included).
#
# A closed vocabulary rather than a boolean for `_PATH_FALLBACKS`'s reason,
# and the stakes are higher here: a typo read as "no default" still derives
# every row, just without the namespace the framework gives them — a wrong
# address that looks like a right one, at `resolved`/`compiler` where nothing
# downstream can tell it from an observation.
#
# A MAPPING rather than a set, because each word owes the derivation a
# template as well as a name — and the template is where the scheme lives.
# That is not a stylistic choice: `storage/` may not name a protocol
# (ARCHITECTURE §10, `tests/architecture/test_source_rules.py::
# test_storage_names_no_framework_language_or_protocol`), and a scheme IS one,
# so the SQL composes the package half and this layer supplies the wrapper it
# goes in. The `%s` is DuckDB's `printf` placeholder, filled with the reversed
# dot-joined package.
_NAMESPACE_DEFAULTS = {"reversed_package": "http://%s/"}

# What a CLASS GATE exposes on its own, with no member-level annotation
# anywhere (2I design §2, word 3). Today's one word is 'public_methods': the
# framework exposes the gated construct's public members, and a member-level
# rule overrides the member rule for the member it names — one row per member,
# never two.
#
# A closed vocabulary for `_PATH_FALLBACKS`'s reason, and an especially sharp
# one here: this is the only word in the mapping vocabulary that derives rows
# for declarations carrying NO annotation at all, so a word read as something
# it is not mints endpoints out of ordinary methods.
_MEMBER_RULES = frozenset({"public_methods"})

# The two keys a `unless` filter may carry, and no others (2I design §2,
# word 4). A closed SHAPE rather than a closed vocabulary, because the values
# are catalog data: which attribute withdraws a declaration, and at which
# value, is the framework's own convention.
_UNLESS_KEYS = frozenset({"attribute", "equals"})


# WHICH construct kinds a catalog may confine itself to (2I design §4). A
# subset of D00's own ConstructKind set rather than the whole of it, because
# only a TYPE can enclose the methods this engine derives from — naming a
# method kind here would gate every row out and read as "this catalog derives
# nothing", which is not something a file should be able to say by accident.
_DECLARED_ON = frozenset({"class", "interface"})


def _declared_on(catalog: Catalog) -> str | None:
    """The construct kind this catalog's declarations sit on, checked against
    the closed set — the `_validate_naming` discipline, at the one place the
    value is still cheap to fix (NFR-5, `yaml_source.py`'s own reason for
    checking `protocol`/`direction` at the edge).

    An unrecognised word read as "no gate" is the dangerous direction: a
    catalog written to describe generated client stubs would derive an
    OUTBOUND row for every server class carrying the same annotations, and a
    module would be published as calling the operations it serves."""
    declared = catalog.matches.get("declared_on")
    if declared is not None and declared not in _DECLARED_ON:
        raise CatalogError(
            f"loading catalog {catalog.source}: `declared_on: {declared}` is not one of "
            f"{', '.join(sorted(_DECLARED_ON))} (2I design §4)"
        )
    return None if declared is None else str(declared)


def _locally_implemented(workspace: Workspace) -> list[str]:
    """Every interface this module's own classes declare they implement (D00
    §5a's `implemented_interfaces`), as BARE descriptors.

    The same strip `interface_implementation._implemented_interfaces` and
    `config_join._implemented_interfaces` make, for the same reason: each
    entry in the fact is itself module-prefixed, and only the descriptor is
    ever compared (D00 §5a). Sorted and deduped so the bound parameter is one
    value for one workspace regardless of read order (NFR-1).
    """
    found = {
        bare_descriptor(str(entry))
        for row in workspace.query("implementations")
        for entry in json.loads(str(row["interfaces"]))
    }
    return sorted(found)


# D02 §2c's `resolves` block, and the ONE key of it that shipped. `format` is
# named in the same section and explicitly did NOT ship — it "turned out not to
# be resolvable per match at all" and is answered by a late pass over the
# finished table — so a catalog writing it here would be declaring a rule
# nothing runs. Refused rather than ignored, the `_validate_naming` discipline.
_RESOLVES = frozenset({"direction"})

# WHICH conditions a `resolves.direction` rule may test (NFR-5). One word today,
# and its estate cost is one line in one catalog: `spring-http-interface.yml` is
# the only shipped file that declares `resolves` at all, and every other catalog
# keeps a constant direction. A closed vocabulary for `_MEMBER_RULES`' reason,
# and the stakes are the same shape: a condition read as something it is not
# would publish a served route as an outbound dependency, or the reverse.
#
# `owner_implemented_by_type_annotated` reads: the type ENCLOSING this
# declaration is implemented, inside this module, by a class carrying one of the
# annotations listed beside the word. Deliberately NOT spec §6's
# `owner_implemented_in_module` — that condition is weaker than the framework's
# own and fabricates (CP-7 Q1, GUIDELINES §8.1 rule 4): a class implementing the
# interface is dispatched to only where it is a handler bean, and a plain
# service implementation is served by nothing at all.
_DIRECTION_CONDITIONS = frozenset({"owner_implemented_by_type_annotated"})

_WHEN, _THEN = "when", "then"


@dataclass(frozen=True)
class _DirectionFlip:
    """What `resolves.direction` resolved to, as the four bound parameters
    `derive_endpoints.sql` reads.

    All four are inert together: `direction` NULL, both lists empty and
    `canonical_path` false is what every catalog declaring no rule binds, and
    the SQL's own flip predicate is then false for every row.

    `owners` are BARE type descriptors, and each `handlers` entry pairs a bare
    DECLARATION descriptor with the module-prefixed symbol that handles it —
    the `{declaration, handler}` STRUCT shape the SQL unnests. The same strip
    `_locally_implemented` makes, for the same reason: an interface's own
    symbols and the `implemented_interfaces` entries naming it are prefixed by
    whichever module's scan wrote them, and only the descriptor is ever
    compared (D00 §5a).
    """

    direction: str | None
    owners: list[str]
    handlers: list[dict[str, str]]
    canonical_path: bool


def _direction_flip(workspace: Workspace, catalog: Catalog) -> _DirectionFlip:
    """This catalog's `resolves.direction` rule, evaluated against the facts.

    Returns the inert flip for a catalog that declares none, which is every
    catalog but one — and the workspace is not queried at all in that case, so
    the pass costs nothing where nothing asked for it.
    """
    rule = _direction_rule(catalog)
    if rule is None:
        return _DirectionFlip(None, [], [], False)
    resolved, annotations = rule
    owners, handlers = _served_owners(workspace, annotations)
    return _DirectionFlip(resolved, owners, handlers, serves_urls(catalog.protocol, resolved))


def _direction_rule(catalog: Catalog) -> tuple[str, list[str]] | None:
    """The declared `(then, condition annotations)` pair, or `None` where this
    catalog declares no direction resolution.

    Refused rather than ignored at every step, for the reason the loader checks
    `protocol`/`direction` at the edge (NFR-5): this value decides which way
    round a wire identity is published, and a rule read as absent republishes a
    served API as an outbound dependency the module does not have — a wrong row
    at `resolved`/`compiler`, not a missing one.
    """
    declared = catalog.resolves
    if not declared:
        return None
    if not isinstance(declared, dict) or set(declared) - _RESOLVES:
        raise CatalogError(
            f"loading catalog {catalog.source}: `resolves` must be a mapping declaring only "
            f"{', '.join(sorted(_RESOLVES))} — got {declared!r}. D02 §2c's `format` half did "
            f"not ship (the ladder answers format over the finished table), so a rule written "
            f"here would be one nothing runs"
        )
    rules = declared["direction"]
    # ONE rule, not a list D02 §2c evaluates in order. First-match-wins over
    # several conditions is the section's stated semantics and no shipped
    # catalog needs it; an engine implementing one rule while accepting a list
    # of them would silently drop every rule after the first, which is the
    # quiet-wrong-answer failure this whole file is checked for.
    if not isinstance(rules, list) or len(rules) != 1 or not isinstance(rules[0], dict):
        raise CatalogError(
            f"loading catalog {catalog.source}: `resolves.direction` must be a list of exactly "
            f"one `{{{_WHEN}, {_THEN}}}` rule — got {rules!r}. D02 §2c's first-match-wins over "
            f"several is unimplemented, and accepting a second rule would silently drop it"
        )
    rule = rules[0]
    if set(rule) != {_WHEN, _THEN}:
        raise CatalogError(
            f"loading catalog {catalog.source}: a `resolves.direction` rule declares exactly "
            f"`{_WHEN}` and `{_THEN}` — got {sorted(rule)}"
        )
    return _resolved_direction(catalog, rule[_THEN]), _condition_annotations(catalog, rule[_WHEN])


def _resolved_direction(catalog: Catalog, declared: Any) -> str:
    """The direction a matching row takes — one of D00's closed set, and never
    the catalog's own default.

    A rule resolving to the declared direction resolves nothing, so it is a file
    that says it faces both ways and does not. Refused rather than accepted as a
    no-op: a reader of the catalog would believe the flip exists."""
    allowed = sorted(member.value for member in Direction)
    if declared not in allowed:
        raise CatalogError(
            f"loading catalog {catalog.source}: `resolves.direction[0].{_THEN}: {declared}` is "
            f"not one of {', '.join(allowed)} — D00's closed sets are closed (NFR-5)"
        )
    if declared == catalog.direction:
        raise CatalogError(
            f"loading catalog {catalog.source}: `resolves.direction[0].{_THEN}: {declared}` is "
            f"the catalog's own declared direction, so the rule resolves nothing"
        )
    return str(declared)


def _condition_annotations(catalog: Catalog, declared: Any) -> list[str]:
    """The annotation fqns a `when` clause tests the owner's implementers for.

    The FQNs are catalog data on purpose and are never spelled in this module:
    which annotation marks a framework's handler bean is that framework's
    convention, and an engine naming one would be naming a framework in code
    (ARCHITECTURE §10). They are the same values `spring-mvc.yml` and
    `spring-web.yml` declare as their own `type_annotation`.
    """
    condition = set(declared) if isinstance(declared, dict) else set()
    if condition - _DIRECTION_CONDITIONS or len(condition) != 1:
        raise CatalogError(
            f"loading catalog {catalog.source}: a `resolves.direction` rule's `{_WHEN}` declares "
            f"exactly one of {', '.join(sorted(_DIRECTION_CONDITIONS))} — got {declared!r} "
            f"(D02 §2c)"
        )
    annotations = declared[next(iter(condition))]
    if (
        not isinstance(annotations, list)
        or not annotations
        or not all(isinstance(fqn, str) and fqn for fqn in annotations)
    ):
        raise CatalogError(
            f"loading catalog {catalog.source}: `{next(iter(condition))}` must name a non-empty "
            f"list of annotation fqns — got {annotations!r}. An empty list is a condition that "
            f"never holds, which reads as "
            f"'this catalog never flips' while looking like a rule that does"
        )
    return [str(fqn) for fqn in annotations]


def _served_owners(
    workspace: Workspace, declared: list[str]
) -> tuple[list[str], list[dict[str, str]]]:
    """Every type this module implements with a class carrying one of
    `declared`, and what handles each of those types' declared methods.

    **The annotation test runs through the composition pre-pass** (`A-C7`), not
    as string equality against the declared fqns: the framework predicate this
    mirrors is meta-annotation aware, so a class wearing a module-local
    stereotype composed from one of these is a handler and a literal compare
    would leave that module's whole implemented API published as an outbound
    dependency it does not have.

    **The type-hierarchy half of that predicate is NOT mirrored**, and the
    boundary is stated rather than approximated (`docs/COVERAGE.md`, the
    inherited-stereotype row): a class whose only stereotype comes from a
    superclass or an interface derives nothing here, because whether the
    framework's own component scan admits such a bean is unmeasured, and
    deriving on half a predicate adds rows on the framework's behalf under
    conditions nobody checked (§8.1 rule 4).

    **The handler is matched by name AND descriptor**, never by name alone: the
    JVM identifies a method by its name and parameter types in order (§8.1's
    language rule) and `member_name` carries the descriptor's own disambiguator,
    so two overloads of one operation bind to their own implementations rather
    than to whichever came first. A declared method the implementing class does
    not itself declare — an interface `default` the framework still serves
    (CP-7 Q3) — contributes no entry, and the SQL leaves the declaring method as
    that row's handler, which is the method the container really invokes.

    Both reads are DIRECT: `implemented_interfaces` names the interfaces a class
    declares itself, never the ones it inherits through a superclass or through
    one of those interfaces' own superinterfaces (D00 §5a). Those two shapes
    derive nothing here and are COVERAGE boundaries rather than silent misses.

    Sorted throughout, and `setdefault` over implementers in symbol order, so
    two classes implementing one interface resolve the same handler twice
    (NFR-1) — a shape the framework itself refuses to start on, since two beans
    would register one mapping.
    """
    condition = {_catalog_symbol(fqn) for fqn in declared}
    annotation_rows = [
        {
            "target": row["target"],
            "annotation": row["annotation"],
            "args": json.loads(str(row["args"])) if row["args"] is not None else {},
        }
        for row in workspace.query("annotations")
    ]
    composed = composed_mapping_rows(
        annotation_rows,
        {str(row["symbol"]) for row in workspace.query("interface_symbols")},
        condition,
    )
    handler_beans = {
        bare_descriptor(str(row["target"]))
        for row in (*annotation_rows, *composed)
        if str(row["annotation"]) in condition
    }
    methods = _methods_by_bare_type(workspace)

    owners: set[str] = set()
    handlers: dict[str, str] = {}
    for row in sorted(workspace.query("implementations"), key=lambda row: str(row["symbol"])):
        implementer = bare_descriptor(str(row["symbol"]))
        if implementer not in handler_beans:
            continue
        own = methods.get(implementer, {})
        for entry in json.loads(str(row["interfaces"])):
            owner = bare_descriptor(str(entry))
            owners.add(owner)
            for key, declaration in methods.get(owner, {}).items():
                if key in own:
                    # The KEY is bare and the VALUE is not, and the asymmetry is
                    # the join: the SQL looks this up by the declaring method's
                    # own bare descriptor (a declaration scanned out of an
                    # opted-in jar carries that jar's coordinates, the class
                    # implementing it carries the module's), while the handler
                    # is published exactly as its fact wrote it (D00 §5a).
                    handlers.setdefault(bare_descriptor(declaration), own[key])
    return sorted(owners), [
        {"declaration": declaration, "handler": handlers[declaration]}
        for declaration in sorted(handlers)
    ]


def _methods_by_bare_type(workspace: Workspace) -> dict[str, dict[str, str]]:
    """Bare enclosing-type descriptor -> `name(descriptor)` -> the method's own
    symbol, exactly as the fact wrote it.

    Keyed bare on the OUTER level and module-prefixed in the VALUE on purpose:
    the lookup crosses a coordinate boundary (an interface scanned out of an
    opted-in dependency jar carries that jar's coordinates while the class
    implementing it carries the module's), and the value is a handler symbol
    that has to be published exactly as emitted.
    """
    found: dict[str, dict[str, str]] = {}
    for row in workspace.query("method_declarations"):
        enclosing = row["enclosing"]
        if enclosing is None:
            continue
        symbol = str(row["symbol"])
        key = member_name(bare_descriptor(symbol))
        found.setdefault(bare_descriptor(str(enclosing)), {})[key] = symbol
    return found


def _validate_naming(catalog: Catalog, mapping: dict[str, Any]) -> None:
    """Refuses a mapping block whose naming vocabulary cannot be honoured.

    Every check here catches a file that would otherwise derive a quietly
    WRONG address rather than fail — and a wrong address is worse than a
    missing one, because it is published at `resolved`/`compiler` where
    nothing downstream can tell it from something observed. That is the same
    reason the loader checks `protocol`/`direction` at the edge (NFR-5).
    """
    separator = mapping.get("path_separator")
    # `derive_endpoints.sql` dedupes the prefix seam with `rtrim`/`ltrim`,
    # which trim a SET of characters: a two-character separator would strip
    # each of its characters individually from either half, composing an
    # address the framework does not serve. An explicitly EMPTY one declares a
    # composition with nothing between the halves, which is what a catalog
    # declaring no separator at all already gets — omitting the key is the
    # supported way to say that, so the key spelled empty is refused instead
    # of silently doing the same thing. A non-string YAML scalar (an int, a
    # bool) is refused for the same reason: `len(str(5))` coerces to `"5"`
    # and would pass a naive length check, joining paths with a character
    # nobody wrote. All three are refused here rather than read as something
    # they are not.
    if separator is not None and (not isinstance(separator, str) or len(separator) != 1):
        raise CatalogError(
            f"loading catalog {catalog.source}: `mapping.path_separator: {separator!r}` is not a "
            f"single character — the prefix seam is deduped character-wise, so a separator that "
            f"isn't exactly one character would compose an address the framework does not serve"
        )
    prefix = mapping.get("path_prefix")
    if prefix is not None:
        # A constant the derivation binds straight into the composed address,
        # so an unusable value is a wrong address rather than a missing one —
        # `yaml_source.py`'s own reason for checking at the edge. A non-string
        # scalar would compose whatever `str()` made of it; an empty one
        # declares a prefix with nothing in it, which is what omitting the key
        # already says, so it is refused rather than silently doing the same
        # thing (the `path_separator` precedent).
        if not isinstance(prefix, str) or prefix == "":
            raise CatalogError(
                f"loading catalog {catalog.source}: `mapping.path_prefix: {prefix!r}` is not a "
                f"non-empty string — it is bound into every address this catalog composes, and "
                f"a value that is not one would prefix characters nobody wrote"
            )
        # A prefix and the address it prefixes are two SEGMENTED halves, and
        # what joins them is the same seam `path_separator` governs. Without
        # one they concatenate bare — `/actuator` + `health` is
        # `/actuatorhealth`, an address the framework does not serve,
        # published at `resolved`/`compiler`. Declared together or not at all.
        # This stays right for as long as every constant prefix is segmented;
        # a framework prefixing an OPAQUE name (a broker destination, which
        # has no segments to join) would need this pair relaxed rather than
        # a separator invented for it.
        if mapping.get("path_separator") is None:
            raise CatalogError(
                f"loading catalog {catalog.source}: `mapping.path_prefix: {prefix}` is declared "
                f"with no `mapping.path_separator` — the two halves would concatenate bare into "
                f"an address the framework does not serve"
            )
    fallback = mapping.get("path_fallback")
    if fallback is not None and fallback not in _PATH_FALLBACKS:
        # An unrecognised word would fall through to the empty default,
        # silently restoring the empty path the form exists to remove.
        raise CatalogError(
            f"loading catalog {catalog.source}: `mapping.path_fallback: {fallback}` is not one "
            f"of {', '.join(sorted(_PATH_FALLBACKS))} (2H design §1)"
        )
    members = mapping.get("members")
    if members is not None:
        if members not in _MEMBER_RULES:
            # An unrecognised word read as "no member rule" loses every
            # unannotated member silently; read as a member rule it does not
            # mean would mint endpoints out of ordinary methods. Both are
            # worse than a refused file.
            raise CatalogError(
                f"loading catalog {catalog.source}: `mapping.members: {members}` is not one of "
                f"{', '.join(sorted(_MEMBER_RULES))} (2I design §2)"
            )
        # A member carries NO annotation, so it carries no name attribute
        # either — every alias is absent by construction, which is exactly the
        # case `path_fallback` exists for. Without it every member row composes
        # the EMPTY path: a resolved endpoint addressing nothing, the failure
        # `path_from` and `qualifier_from` are both already checked for,
        # reached by a third route.
        if mapping.get("path_fallback") is None:
            raise CatalogError(
                f"loading catalog {catalog.source}: `mapping.members: {members}` is declared with "
                f"no `mapping.path_fallback` — a member carries no annotation and so no name "
                f"attribute at all, and every member row would compose an empty address "
                f"(2I design §2)"
            )
        # THE CLASS GATE. A member rule enumerates the members OF something,
        # so something has to gate the class — and where nothing does, the
        # rule is not inert, it is catastrophic: every public method in the
        # module becomes an endpoint. The gate may be the single
        # `type_annotation`, or — for a framework whose gate has two spellings,
        # which `type_annotation` cannot carry (it is one fqn) — one of this
        # catalog's own `mapping.annotations` found on a TYPE, the same
        # type-level join `qualifier_scopes` reads a class-level scope through.
        # A catalog declaring neither names no class at all.
        if catalog.matches.get("type_annotation") is None and not mapping["annotations"]:
            raise CatalogError(
                f"loading catalog {catalog.source}: `mapping.members: {members}` is declared with "
                f"no class gate — neither `type_annotation` nor any `mapping.annotations` entry "
                f"that could mark one, so the rule names no class to enumerate (2I design §2)"
            )
    for entry in mapping["annotations"]:
        _validate_unless(catalog, entry)
        _validate_entry_fallback(catalog, entry)
        _validate_container(catalog, entry)
    _sibling_sources(catalog, mapping)
    qualifier_format = mapping.get("qualifier_format")
    if qualifier_format is not None and qualifier_format not in _QUALIFIER_FORMATS:
        # An unrecognised word would fall through to the separator
        # composition — and for a catalog that declares no separator (which
        # every catalog reaching for a format does, since the two are
        # exclusive below) that is the un-composed bare name, silently
        # restoring the un-scoped address the form exists to remove.
        raise CatalogError(
            f"loading catalog {catalog.source}: `mapping.qualifier_format: {qualifier_format}` is "
            f"not one of {', '.join(sorted(_QUALIFIER_FORMATS))} (2I design §2)"
        )
    namespace_default = mapping.get("namespace_default")
    if namespace_default is not None and namespace_default not in _NAMESPACE_DEFAULTS:
        raise CatalogError(
            f"loading catalog {catalog.source}: `mapping.namespace_default: {namespace_default}` "
            f"is not one of {', '.join(sorted(_NAMESPACE_DEFAULTS))} (2I design §2)"
        )
    if qualifier_format is not None and mapping.get("qualifier_separator") is not None:
        # Two composition rules for one seam is one too many: which of them
        # the engine applied would decide the address, and a file declaring
        # both states no preference. Refused rather than resolved by a
        # precedence nobody wrote down. `is not None` rather than a truth
        # test, so an explicitly EMPTY separator is caught here too — it is
        # still the key spelled, still a second rule declared.
        raise CatalogError(
            f"loading catalog {catalog.source}: `mapping.qualifier_format: {qualifier_format}` and "
            f"`mapping.qualifier_separator: {mapping.get('qualifier_separator')!r}` are mutually "
            f"exclusive — a format states the WHOLE composition (`{{scope}}name` has no single "
            f"joining character), so a separator beside it declares a second rule for one seam "
            f"(2I design §2)"
        )
    if not mapping.get("qualifier_from"):
        # Both new words describe the SCOPE — how it composes, and what it is
        # when unstated — so neither means anything on a catalog that reads no
        # scope at all. Refused rather than accepted and silently ignored: a
        # file whose author believed they had asked for the framework's own
        # default would otherwise get nothing, with nothing saying so.
        for word, value in (
            ("qualifier_format", qualifier_format),
            ("namespace_default", namespace_default),
        ):
            if value is not None:
                raise CatalogError(
                    f"loading catalog {catalog.source}: `mapping.{word}: {value}` is declared "
                    f"with no `mapping.qualifier_from` — it describes a scope this catalog "
                    f"never reads (2I design §2)"
                )
        return
    separator = mapping.get("qualifier_separator")
    # A format states the whole composition, so the separator checks below —
    # which exist to refuse a scope joined by nothing or by the wrong number
    # of characters — have nothing to rule on. `path_fallback` is still
    # required past this branch: a format composing onto an EMPTY name yields
    # a dangling `{scope}`, which is the same confidently-wrong address a
    # dangling `Parent.` is.
    if qualifier_format is None:
        # An ABSENT separator joins a scope to a name with nothing between
        # them (`Parentmember`); an explicitly EMPTY one does exactly the same
        # thing while passing an `is None` check, so both are refused by the
        # same message here. An empty separator has no honest use: a framework
        # that concatenates the two halves with nothing between them has no
        # composition to declare.
        if separator is None or separator == "":
            raise CatalogError(
                f"loading catalog {catalog.source}: `mapping.qualifier_from` is declared with no "
                f"usable `mapping.qualifier_separator` (got {separator!r}) — what joins a scope "
                f"to the name it qualifies is catalog data, and this engine names no punctuation "
                f"of its own (2H design §1)"
            )
        # Anything else that isn't exactly one STRING character (a YAML
        # int/bool, a multi-character string) would compose an address nobody
        # serves — the same failure mode `path_separator` is checked for, and
        # the same reason.
        if not isinstance(separator, str) or len(separator) != 1:
            raise CatalogError(
                f"loading catalog {catalog.source}: `mapping.qualifier_separator: {separator!r}` "
                f"is not a single character — what joins a scope to the name it qualifies is a "
                f"single piece of punctuation, and a value that isn't exactly one character "
                f"would compose an address the framework does not serve"
            )
    # Without a fallback, an annotation carrying a scope and no name composes
    # the scope and the separator onto nothing — a dangling `Parent.`, which
    # is the confidently-wrong-address class again. The two forms are declared
    # together or not at all.
    if mapping.get("path_fallback") is None:
        raise CatalogError(
            f"loading catalog {catalog.source}: `mapping.qualifier_from` is declared with no "
            f"`mapping.path_fallback` — a scoped declaration that names no member would compose "
            f"a scope and a separator onto an empty name (2H design §1)"
        )


def _validate_unless(catalog: Catalog, entry: dict[str, Any]) -> None:
    """Refuses an `unless` filter whose shape the derivation cannot honour.

    Exactly `attribute` (a string) and `equals` (present, any scalar), and
    nothing else. A misspelled or missing key would leave the filter reading
    NULL and matching nothing — the rule would derive every declaration
    including the ones the framework itself withdraws, which is a published
    endpoint nobody serves rather than a missing one.
    """
    declared = entry.get("unless")
    if declared is None:
        return
    valid = (
        isinstance(declared, dict)
        and set(declared) == _UNLESS_KEYS
        and isinstance(declared.get("attribute"), str)
        and declared.get("equals") is not None
    )
    if not valid:
        raise CatalogError(
            f"loading catalog {catalog.source}: `unless` on `{entry.get('fqn')}` must name "
            f"exactly `attribute` (a string) and `equals`, got {declared!r} (2I design §2)"
        )


def _validate_entry_fallback(catalog: Catalog, entry: dict[str, Any]) -> None:
    """Refuses an annotation entry whose own fallback word is not one this
    engine knows (`OI-5`).

    The catalog-level word is checked in `_validate_naming` above and this is
    the same check one level down, for the same reason and with higher stakes:
    an unrecognised word read as "no fallback" restores the empty path the form
    exists to remove, and one read as a fallback it does not mean publishes the
    method's own name where the framework serves a stripped one. Both are a
    wrong address at `resolved`/`compiler`, and both are worse than a refused
    file.
    """
    declared = entry.get("path_fallback")
    if declared is not None and declared not in _PATH_FALLBACKS:
        raise CatalogError(
            f"loading catalog {catalog.source}: `path_fallback: {declared}` on "
            f"`{entry.get('fqn')}` is not one of {', '.join(sorted(_PATH_FALLBACKS))} (`OI-5`)"
        )


def _validate_container(catalog: Catalog, entry: dict[str, Any]) -> None:
    """Refuses a `container` that is not a usable annotation fqn (`OI-36`).

    Read as absent, a malformed value restores exactly the silent under-report
    this key exists to remove — a method carrying two of this annotation derives
    NOTHING, beside a single-use neighbour that derives normally — and an
    absence is the harder of the two failures to notice, because there is no
    wrong row to see. So it is refused rather than ignored, the
    `_validate_naming` discipline.
    """
    declared = entry.get(_CONTAINER)
    if declared is not None and not (isinstance(declared, str) and declared):
        raise CatalogError(
            f"loading catalog {catalog.source}: `{_CONTAINER}: {declared!r}` on "
            f"`{entry.get('fqn')}` is not a non-empty annotation fqn — it names the container "
            f"annotation whose `value` array holds uses of that annotation (`OI-36`)"
        )


def _unless_attribute(entry: dict[str, Any]) -> str | None:
    declared = entry.get("unless")
    return None if declared is None else str(declared["attribute"])


def _unless_equals(entry: dict[str, Any]) -> str | None:
    """The withdrawing value, spelled the way `json ->> key` reads it back.

    A JSON boolean reads back as the lowercase text `true`/`false`, a number
    as its digits, a string as itself — so the comparison happens on ONE
    representation and a YAML `equals: true` matches the boolean checkpoint
    item 4 pins in the bytecode (`@WebMethod(exclude = true)` emits a real
    JSON boolean, never the string `"true"`). `str(True)` is `'True'`, which
    would match nothing at all, so the bool case is spelled out first — bools
    are ints in Python, and the order of these branches is load-bearing.
    """
    declared = entry.get("unless")
    if declared is None:
        return None
    value = declared["equals"]
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _synthetic_annotations(
    workspace: Workspace,
    catalog: Catalog,
    mapping_annotations: list[dict[str, object]],
    prefix_fqn: str | None,
    type_annotation_fqn: str | None,
) -> list[dict[str, str]]:
    """The bound-parameter form `derive_endpoints.sql`'s `annotations_effective`
    CTE expects (D02 §2, §3): every row `folded_rows`, `composed_mapping_rows`
    and, where `run_inheritance`, `inherited_rows` derive, `args` re-serialized
    to JSON text — DuckDB's `STRUCT(... VARCHAR)` binding shape carries a
    string, not a nested JSON value, the same way every other JSON-typed bound
    parameter in this engine already does.

    **The FOLDING pass runs first, and everything downstream reads its output**
    (`OI-36`). A repeated annotation reaches the class file as its container and
    not as N annotations (JLS 9.7.5), so unfolding is not a widening of what the
    catalog matches — it is reading the shape javac actually wrote. Running it
    ahead of the other two is what lets a folded use compose and inherit exactly
    as a written one does, and it is why there is no container in the SQL at
    all: by the time the query runs, a folded use IS an ordinary annotation row.

    It is NOT restricted to method targets, and that is the framework's answer
    rather than a widening: the two listener annotations CP-16 measured are
    `@Target`-legal on a TYPE as well (rows 2a/2e), so a class carrying two
    class-level listeners folds identically and the prefix join composes both.
    `derive_endpoints.handler-is-a-method` is still what stops a type-level use
    minting a row of its own.

    Task 7's inheritance walk runs over the COMPOSED universe (real rows
    plus Task 6's own synthetic ones), not just the real `annotations`
    table — the fixture's composed-and-inherited case
    (`OrdersApi#composed`'s `@ApiGet`) only has anything to inherit once §2
    has already turned it into a real `@RequestMapping` on the interface
    method.

    `run_inheritance` is `True` exactly when the catalog declares its own
    `type_annotation` (Task 7 review, Critical finding C1). Spec §3's own
    scope is the handler-side OpenAPI-generator pattern — mappings on an
    interface, `@RestController` on the class that implements it — and
    every gated HTTP catalog matches that shape. A GATELESS catalog
    (Retrofit, `spring-http-interface`, `spring-jms`, `spring-kafka`,
    `spring-sqs`) has no such implementer role at all: the annotated
    interface method IS the client call or the listener identity `mappings`
    already joins on directly, so synthesizing a row onto some OTHER class
    that merely happens to implement that interface mints a caller/handler
    for a type nobody declared as a client — a Retrofit interface is itself
    the client, not a contract some unrelated implementer fulfills.
    *This paragraph also said "and a messaging listener annotation is never
    interface-inherited by its own framework either", and CP-16 row 4e
    FALSIFIES that: spring-rabbit 3.1.4 searches
    `MergedAnnotations.from(element, SearchStrategy.TYPE_HIERARCHY)`, with the
    strategy arriving as a constant the probe could read. The claim is deleted
    rather than corrected in place, because the gate does not rest on it — the
    reason above stands on its own — and because a rationale that has quietly
    become false is worse than none (§9). What the falsification costs is
    `OI-37`, which stays open: the OTHER two searches carry no strategy
    constant and are unmeasured, and the rule needs a second answer nobody has
    measured (whether the ancestor's own declaration still derives, and which
    symbol handles it), so a walk here would be deriving on half a measured
    rule.* Left ungated, one declared route produced three rows
    (the real interface row plus a synthesized row per implementer in the
    hierarchy) in the reviewer's own repro; `test_a_gateless_catalog_never_
    synthesizes_onto_an_implementing_class` (`test_endpoints.py`) pins the
    fix. `composed_mapping_rows` carries no such scope limit — meta-annotation
    composition is a same-target rewrite, never a cross-type join, so it
    still runs for every catalog regardless of `run_inheritance`."""
    annotation_rows = [
        {
            "target": row["target"],
            "annotation": row["annotation"],
            "args": json.loads(str(row["args"])) if row["args"] is not None else {},
        }
        for row in workspace.query("annotations")
    ]
    folded = folded_rows(annotation_rows, _containers(catalog))
    annotation_rows = [*annotation_rows, *folded]
    scanned_targets = {str(row["symbol"]) for row in workspace.query("interface_symbols")}
    mapping_fqns = {str(m["fqn"]) for m in mapping_annotations}
    # The type-level GATE composes exactly as a method-level mapping does
    # (`A-C7`), so it seeds the same closure rather than a second one. Spring's
    # own handler test is `AnnotatedElementUtils.hasAnnotation(beanType,
    # Controller.class)` — measured identical across four Spring minors, CP-11
    # Q2 — and that predicate is meta-annotation aware, so a controller wearing
    # a module-local `@MyApi` composed from `@RestController` IS a handler. The
    # catalogs encoded string equality against one FQN, which matched it not at
    # all and deleted the controller's whole surface.
    #
    # The synthesized row targets the CLASS and carries the gate's own fqn, so
    # `derive_endpoints.sql`'s `controllers` CTE finds it with no second code
    # path — the same trick the mapping half already uses. It cannot leak into
    # `mappings`, which joins `construct_kind IN ('method', 'function')`.
    composed = composed_mapping_rows(
        annotation_rows,
        scanned_targets,
        mapping_fqns | ({type_annotation_fqn} if type_annotation_fqn is not None else set()),
    )
    run_inheritance = type_annotation_fqn is not None
    inherited = (
        inherited_rows(
            [*annotation_rows, *composed],
            _implementation_rows(workspace),
            _superclass_rows(workspace),
            _method_declaration_rows(workspace),
            mapping_fqns,
            prefix_fqn,
        )
        if run_inheritance
        else []
    )
    return [
        {"target": row["target"], "annotation": row["annotation"], "args": json.dumps(row["args"])}
        for row in (*folded, *composed, *inherited)
    ]


def _containers(catalog: Catalog) -> dict[str, str]:
    """Container fqn -> the member fqn it folds, for every `mapping.annotations`
    entry that declares one (`OI-36`).

    Empty for every catalog that declares none, which is every catalog written
    before the word — and `folded_rows` then reads no annotation row at all, so
    the pass costs nothing where nothing asked for it. Both sides are converted
    to the `annotations` view's own symbol form here, once, so nothing
    downstream compares a catalog spelling against a fact spelling.
    """
    return {
        _catalog_symbol(str(entry[_CONTAINER])): _catalog_symbol(str(entry["fqn"]))
        for entry in catalog.matches["mapping"]["annotations"]
        if entry.get(_CONTAINER) is not None
    }


def _implementation_rows(workspace: Workspace) -> list[dict[str, object]]:
    """`implementations`'s rows, `interfaces` decoded — Task 7's own read of
    D00 §5a's `implemented_interfaces` capability (`resolve/effective_annotations.py`)."""
    return [
        {"symbol": row["symbol"], "interfaces": json.loads(str(row["interfaces"]))}
        for row in workspace.query("implementations")
    ]


def _superclass_rows(workspace: Workspace) -> list[dict[str, object]]:
    """`superclasses`'s rows — capability 9.13's erased `superclass` field,
    two plain string columns, module-prefixed on both sides.

    This replaced a read of `supertypes` (`A-C4`). That query carries D00
    §5a's parameterized-type reference, which the extractor emits only where
    the superclass declares type ARGUMENTS, so an ordinary `class Child
    extends Base` produced no inheritance edge at all and the child published
    its methods without the base's prefix. `supertypes` is still the right
    read for what it IS — `shapes/arguments.py`'s `supertypes_of` keeps it —
    just never for "does this class have a superclass".
    """
    return [
        {"symbol": row["symbol"], "superclass": row["superclass"]}
        for row in workspace.query("superclasses")
    ]


def _method_declaration_rows(workspace: Workspace) -> list[dict[str, object]]:
    """`method_declarations`'s rows, `signature` and `modifiers` decoded — the
    one named query 2E-prep's `method_symbols` cannot serve, since the
    inheritance walk needs `enclosing` to place a method within its declaring
    type at all, and needs a candidate's own parameter/return types.

    `modifiers` carries D00 §5a's `synthetic`, which is how the walk tells a
    method a human wrote from the bridge javac generates beside it (OI-47).
    **This function is the only producer of `inherited_rows`' method rows**, so
    a column added to the query and not rebuilt here reaches nothing: the walk
    falls back to inferring a bridge from its shape, silently, and every
    assertion about the fixed behaviour still passes because they hand-build
    their own rows. That is exactly what happened.

    Decoded, not passed through: DuckDB returns a JSON column as TEXT, and a
    string answers `"synthetic" in modifiers` by SUBSTRING — True, and then
    subscripting it raises. `signature` above is decoded for the same reason."""
    return [
        {
            "symbol": row["symbol"],
            "enclosing": row["enclosing"],
            "signature": (
                json.loads(str(row["signature"])) if row["signature"] is not None else None
            ),
            "modifiers": (
                json.loads(str(row["modifiers"])) if row["modifiers"] is not None else None
            ),
        }
        for row in workspace.query("method_declarations")
    ]


def _derive_replies(workspace: Workspace, catalog: Catalog) -> None:
    """D02 §2's `reply` block: a listener's declared reply (`@SendTo` and
    its like) derives a second, OUTBOUND row per listed destination —
    `caller` the handler, payload the handler's own return type — plus one
    `path`-NULL `unresolved` row for a value-returning handler whose reply
    destination this catalog cannot name: the annotation absent altogether
    (the destination exists, just not where the annotations can see it — a
    `ReplyingKafkaTemplate` caller, say), or present but bare, listing no
    destination. A `void` handler (its return type's own `_payload_descriptor` is
    `None`) derives no reply row at all: there is nothing to reply with.

    Restricted to the handlers THIS catalog's own rows produced: `catalog_id`
    (2E-prep design §1a) names the derivation that produced each row, so
    filtering `endpoints` on `catalog_id == catalog.id` is already exactly
    this catalog's own handler set — no annotations re-scan needed.

    The return type comes off `handler_signature` on the matching endpoint
    row — the same signature `derive_endpoints.sql` already read for it
    (`s.signature`) and the same column `shapes/contracts.py`'s own
    `_contracts_of` reads for the *response* half of an inbound row's
    contract — rather than a fresh lookup, since a reply row's payload IS
    that response type.
    """
    reply = catalog.matches["reply"]
    reply_annotation = _catalog_symbol(reply["annotation"])
    destination_attr = reply["destination_from"]
    rules = _rules_of(catalog)
    enums = _enum_symbols(workspace)
    # `_payload_descriptor` requires an accumulator, and this one is
    # DISCARDED: nothing reads it after `_derive_replies` returns, so it is
    # not what carries a reply payload into shape expansion. What does is the
    # inbound row this reply belongs to — a reply's payload IS its handler's
    # return type, which `shapes/contracts.py` roots as that same handler's
    # `response_shape` off `handler_signature`. That, not this list, is why
    # a reply payload is expanded today.
    referenced: list[str] = []

    # A dict first, then its keys sorted (NFR-1): one inbound row per
    # listened destination already means the same handler symbol can sit on
    # several endpoint rows (a multi-topic listener), and this pass owes
    # each handler exactly one reply decision, not one per inbound row it
    # happens to appear on. `setdefault` keeps the first-seen signature,
    # which is the same value every row for one handler carries regardless.
    signatures: dict[str, object] = {}
    for endpoint in workspace.query("endpoints"):
        if endpoint.get("catalog_id") == catalog.id and endpoint.get("handler"):
            signatures.setdefault(str(endpoint["handler"]), endpoint["handler_signature"])

    rows: list[dict[str, Any]] = []
    for handler in sorted(signatures):
        declared = signatures[handler]
        if declared is None:
            continue
        signature = json.loads(str(declared))
        descriptor = _payload_descriptor(signature.get("returns"), rules, enums, referenced)
        if descriptor is None:
            continue
        uses = workspace.query("annotations_of", target=handler)
        reply_use = next((use for use in uses if use["annotation"] == reply_annotation), None)
        if reply_use is None:
            rows.append(_reply_row(catalog, handler, None, "unresolved", descriptor))
            continue
        args = json.loads(str(reply_use["args"])) if reply_use["args"] is not None else {}
        destinations = _destinations_of(args, destination_attr)
        # A BARE reply annotation — declared, but naming no destination at
        # all — lands on the very same path-NULL `unresolved` row the
        # no-annotation branch above emits (final review, CRITICAL). It used
        # to derive nothing: the loop below simply never ran, so a handler
        # that *declares* it replies produced strictly LESS than one that
        # declares nothing, inverting the evidence. Both bytecode forms of
        # bare reach here — `@SendTo`'s `value` defaults to `{}`, recorded
        # either as the attribute key absent or as an explicit empty array —
        # and neither is a fact about the handler, so neither may change the
        # answer.
        if not destinations:
            rows.append(_reply_row(catalog, handler, None, "unresolved", descriptor))
            continue
        # Destinations in listed order (NFR-1).
        for destination in destinations:
            rows.append(_reply_row(catalog, handler, destination, "resolved", descriptor))

    workspace.derive("call_endpoints", rows=rows)


def _destinations_of(args: dict[str, Any], name: str) -> list[str]:
    """The reply annotation's destination attribute, read scalar-or-array —
    the Python mirror of `derive_endpoints.sql`'s own alias-reading pattern
    for `path_from`. CHECKPOINT FACT: the reply annotation's own destination
    attribute (`@SendTo`'s `value`) always arrives as a `String[]` in
    bytecode, even for a bare-string source declaration — but the scalar
    form is still read here, for a reply annotation on a framework not yet
    catalogued that might not share that emission quirk."""
    value = args.get(name)
    if isinstance(value, list):
        return [str(entry) for entry in value]
    if value is not None:
        return [str(value)]
    return []


def _reply_row(
    catalog: Catalog,
    handler: str,
    destination: str | None,
    resolution: str,
    request_shape: str,
) -> dict[str, Any]:
    """One reply row's fixed shape (D01 §3, amended): a reply is always
    outbound and verbless; the handler that produced the payload lands in
    `caller`, never `handler` — a reply row has no consuming method of its
    own for this pass to see — and `response_shape` is always absent (a
    reply carries no response of its own).

    **No path seam here, and that is the rule rather than an omission**
    (2O design §8 as narrowed by ruling R8). The seam canonicalizes the
    address of a route the module SERVES; this row's `direction` is the
    literal `outbound` two lines below, whatever the catalog declares, so the
    seam could never apply to it. The catalog's own direction is the wrong
    question to ask at this site precisely because this row does not take it:
    an inbound HTTP catalog that declared a `reply` block would otherwise
    canonicalize a client-side address, which is the rewrite R8 forbids.
    `destination` is therefore recorded exactly as the reply annotation
    wrote it."""
    return {
        "protocol": catalog.protocol,
        "direction": "outbound",
        "method": None,
        "path": destination,
        "handler": None,
        "caller": handler,
        "peer": None,
        "handler_signature": None,
        "resolution": resolution,
        "evidence": "compiler",
        "catalog_id": catalog.id,
        "request_shape": request_shape,
        "response_shape": None,
        "consumes": None,
        "produces": None,
    }
