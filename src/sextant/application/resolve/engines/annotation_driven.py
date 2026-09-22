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
from sextant.application.resolve.dependencies import unmet_dependency
from sextant.application.resolve.effective_annotations import (
    TypeHierarchy,
    composed_mapping_rows,
    folded_rows,
    inherited_rows_over,
    type_hierarchy,
)
from sextant.application.resolve.shapes.contracts import _payload_descriptor
from sextant.application.resolve.shapes.expansion import _enum_symbols, _rules_of
from sextant.application.resolve.shapes.rooting import _catalog_symbol, catalog_symbols
from sextant.domain.closed_sets import Direction
from sextant.domain.paths import serves_urls
from sextant.domain.symbols import bare_descriptor, member_name, owner_of


def run(workspace: Workspace, catalog: Catalog) -> None:
    """One catalog on its own: `stage` for a batch of one, then `insert`.

    The per-catalog entry, kept for every caller that hands this engine one
    catalog — the tests that pin a single catalog's rows, and any caller that
    is not `derive_endpoints`. `derive_endpoints` itself does not call this: it
    stages every annotation-driven catalog of the resolve at once and then
    calls `insert` at each catalog's turn, which is what P-4 is."""
    stage(workspace, [catalog])
    insert(workspace, catalog)


def stage(workspace: Workspace, catalogs: list[Catalog]) -> None:
    """Derives every candidate row of every catalog in `catalogs` in ONE
    execution of `derive_endpoints.sql`, into the `endpoint_candidates` table
    `insert` then reads per catalog (P-4).

    Once per resolve rather than once per catalog, because the statement's
    cost is its size at bind time — ~50ms for its 1,300 lines whatever the
    values, measured — and 28 catalogs paid it 28 times: 1.4s of a 2.5s
    analyze. Every value is a pure function of the catalog and the FACT
    tables (`params_for`), so nothing about a catalog's rows depends on which
    other catalogs share the statement; the SQL carries `catalog_id` through
    every CTE so their rows never mix.

    A CORROBORATION-ONLY catalog is not in the batch (2O design §1b, fix
    round 2's I-2): it declares `corroborates` and no `mapping` because its
    annotation states that a class SERVES something without stating what —
    no address, no member rule, nothing this derivation could bind — so its
    whole contribution is the open question `gaps` files instead. Deriving a
    row from it would mint an endpoint with no address, which is precisely
    what the annotation cannot support. A batch with nothing in it runs
    nothing: `insert` is never asked for a catalog that was not staged.
    """
    params = [params_for(workspace, catalog) for catalog in catalogs if _derives(catalog)]
    if not params:
        return
    workspace.derive("endpoints", catalogs=params)


def insert(workspace: Workspace, catalog: Catalog) -> None:
    """This catalog's turn: its staged rows go into `endpoints` — every one
    whose wire identity no earlier turn minted (`insert_endpoints.sql` states
    the rule) — and then its declared replies.

    Runs at the catalog's own place in `derive_endpoints`'s order, never
    earlier: the other engines' catalogs run between annotation-driven ones,
    and which row survives for a wire identity two of them share is decided
    by whose turn came first. Asking the guard here, per turn, is what keeps
    that answer exactly what it was when the whole derivation ran per turn."""
    if not _derives(catalog):
        return
    workspace.derive("endpoints_insert", catalog_id=catalog.id)
    # Optional (D02 §2, amended): a catalog with no `reply` block declares no
    # second-row rule at all — the HTTP catalogs, which never see @SendTo.
    if "reply" in catalog.matches:
        _derive_replies(workspace, catalog)


def _derives(catalog: Catalog) -> bool:
    """Whether this catalog derives rows at all — false for a corroboration-only
    catalog, which `stage` and `insert` both leave alone for the reason `stage`
    states."""
    return _corroboration(catalog) is None or "mapping" in catalog.matches


def params_for(workspace: Workspace, catalog: Catalog) -> dict[str, Any]:
    """The catalog's own protocol, direction, annotation identifiers and
    mapping declaration, as the one STRUCT row `derive_endpoints.sql` reads
    for it — every field a pure function of the catalog and the fact tables.
    The engine here is generic: it never names a framework or a protocol, only
    forwards what the catalog declares.

    Every field is filled, even where the catalog declares nothing (NULL, an
    empty list): the rows travel as one JSON value, and a struct key the
    statement declares that a row does not carry is the slow route
    `DuckDbWorkspace.derive` keeps for hand-built test rows, not one a
    production row may take."""
    mapping = catalog.matches["mapping"]
    _validate_naming(catalog, mapping)
    declared_on = _declared_on(catalog)
    type_annotation = catalog.matches.get("type_annotation")
    # A LIST or a scalar (§3.1), and optional — None where the catalog declares no
    # type-level gate at all, which the SQL still tests with `IS NULL`.
    type_annotation_fqns = (
        None
        if type_annotation is None
        else list(catalog_symbols(type_annotation, f"{catalog.source}: type_annotation"))
    )
    flip = _direction_flip(workspace, catalog)
    prefix_annotation = mapping["prefix_annotation"]
    # Optional too (Retrofit, spring-jms): no class-level prefix shape.
    prefix_fqns = (
        None
        if prefix_annotation is None
        else list(
            catalog_symbols(prefix_annotation, f"{catalog.source}: mapping.prefix_annotation")
        )
    )
    # CP-22 row 2 (spec §3f): `peer_from` used to be read off the SAME
    # annotation row `prefix_from` is — true for `@FeignClient`, where prefix
    # and peer share one annotation, but not for MicroProfile REST Client,
    # whose prefix sits on `@Path` and whose peer sits on `@RegisterRestClient`
    # — two different annotations. `peer_annotation` names the second one and
    # defaults to `prefix_annotation` where a catalog declares none, so every
    # catalog shipped before this word reads `peer_from` exactly where it
    # always did and derives byte-identically.
    peer_annotation = mapping.get("peer_annotation") or prefix_annotation
    peer_fqns = (
        None
        if peer_annotation is None
        else list(catalog_symbols(peer_annotation, f"{catalog.source}: mapping.peer_annotation"))
    )
    mapping_annotations = [_mapping_annotation(mapping, m) for m in mapping["annotations"]]
    return {
        "protocol": catalog.protocol,
        "direction": catalog.direction,
        # Optional (D02 §2, amended): absence means "no type-level gate".
        "type_annotation": type_annotation_fqns,
        # 2I design §4: WHICH KIND of construct this catalog's rules describe,
        # or NULL where the catalog describes declarations on any construct —
        # which is every catalog written before it. One annotation family can
        # mark both a service and the generated client stub of one, and the
        # two are opposite directions of the same wire; without this the two
        # catalogs would each derive both, and a module would be reported as
        # calling the very operations it serves.
        "declared_on": declared_on,
        # 2I design §4's SEI fence — `derive_endpoints.sql`'s own comment
        # states what it refuses and why it is scoped rather than universal.
        # Read only for the one catalog shape that can be wrong without it, so
        # every other catalog binds an empty list and the fence's own
        # `$direction`/`$declared_on` test already evaluates false for it.
        "locally_implemented": (
            _locally_implemented(workspace)
            if catalog.direction == "outbound" and declared_on == "interface"
            else []
        ),
        "prefix_annotation": prefix_fqns,
        # `peer_from` reads off THIS annotation, not `prefix_annotation` —
        # the two differ only for MicroProfile REST Client today (spec §3f).
        "peer_annotation": peer_fqns,
        # F2 §3.5's relationship conjunct. How a class-level annotation relates
        # to the methods inside it — `prefix` (compose, the HTTP shape) or
        # `sibling` (a method naming its own destination is its OWN
        # registration, the messaging shape). Defaults to `prefix`, which is
        # what every catalog written before it assumed.
        "class_level": _class_level(mapping, catalog),
        # `method` is absent for an annotation that pre-sets none, and the
        # derivation reads that absence as "every method in all_methods".
        "mapping_annotations": mapping_annotations,
        "path_from": list(mapping["path_from"]),
        # `OI-35`: the name sources that live on OTHER annotations of the same
        # declaration, consulted in the order the catalog lists them and only
        # where every `path_from` alias was absent. Empty for every catalog that
        # declares none, which is every catalog written before this word — an
        # empty list matches no annotation, so the lookup finds nothing and the
        # composed address is exactly what it was. The ordinal is attached HERE
        # rather than relied on in the query, because a list's order is not a
        # column and `min_by` needs one to be able to say "first present".
        "path_from_siblings": _sibling_sources(catalog, mapping),
        # Spec 2026-09-18 §3b word 1: the media siblings — `@Produces`/`@Consumes` on a
        # JAX-RS method sit beside a verb annotation that declares no attribute at
        # all (CP-18 row 1). Same closed shape and order rule as the path siblings;
        # read only where every `produces_from`/`consumes_from` alias is absent.
        "produces_from_siblings": _sibling_sources(catalog, mapping, "produces_from_siblings"),
        "consumes_from_siblings": _sibling_sources(catalog, mapping, "consumes_from_siblings"),
        # Spec 2026-09-18 §3b word 2: the class-level media DEFAULT — `@Produces`/
        # `@Consumes` on the resource TYPE, applied only where the method itself
        # (including its own siblings, above) declared none. A different word from
        # the two above it because the sibling being read sits on the TYPE rather
        # than the method, and `_type_media_sources` keys it by `produces`/
        # `consumes` rather than by ordinal position in a single list.
        "type_media_from_siblings": _type_media_sources(catalog, mapping),
        "prefix_from": list(mapping["prefix_from"]),
        "peer_from": list(mapping.get("peer_from", [])),
        "method_from": mapping["method_from"],
        "all_methods": list(mapping["all_methods"]),
        "catalog_id": catalog.id,
        # Optional (media evidence kind (a), spec §4): absent on every
        # catalog that declares neither, so it derives NULL with zero YAML
        # change — the HTTP catalogs are the only ones that declare these.
        "consumes_from": list(mapping.get("consumes_from", [])),
        "produces_from": list(mapping.get("produces_from", [])),
        # 2H design §1's two naming forms, both optional and both inert
        # unless declared. `path_fallback` says what the declared name is when
        # every `path_from` alias is absent; `qualifier_from`/
        # `qualifier_separator` compose a scope named on the SAME annotation
        # in front of that name. Absent on every catalog written before them,
        # which is what keeps their derivations byte-identical.
        "path_fallback": mapping.get("path_fallback"),
        # The catalog-level word's own prefix data, for the one row shape that
        # carries no mapping annotation to read a per-annotation word off — an
        # unannotated exposed member (`$members`). Empty where the catalog
        # declares no fallback at all, and empty for `construct_name`.
        "path_fallback_prefixes": list(_PATH_FALLBACKS.get(str(mapping.get("path_fallback")), ())),
        # Spec 2026-09-22 §2b: WHICH attribute of the declaring type's own
        # `type_annotation` use carries the prefix
        # `prefixed_capitalized_construct_name` composes. NULL for every
        # catalog that declares no such word — which is every catalog written
        # before it — so the derivation's own prefix read finds no row and the
        # composition is inert. `_validate_fallback_prefix_attr` above refuses
        # the word without the attribute and the attribute without the word, so
        # this is never NULL on a catalog whose fallback reads it.
        "fallback_prefix_attr": mapping.get(_FALLBACK_PREFIX_ATTR),
        # Spec 2026-09-22 §1d: the punctuation `declaring_type_scoped_name`
        # puts between the declaring type's simple name and the name that won.
        # NULL for every catalog that declares no such word, so the
        # derivation's branch is unreachable for them and their addresses are
        # byte-identical. `_validate_fallback_scope_separator` refuses the word
        # without it and it without the word, so this is never NULL on a
        # catalog whose fallback composes with it.
        "fallback_scope_separator": mapping.get(_FALLBACK_SCOPE_SEPARATOR),
        "qualifier_from": list(mapping.get("qualifier_from", [])),
        "qualifier_separator": mapping.get("qualifier_separator"),
        # 2I design §2's two QName forms, both optional and both inert unless
        # declared. `qualifier_format` names a composition that is not a
        # separator at all — `{scope}name` is one bracketed token, and its
        # closing brace has no separator equivalent — so it REPLACES
        # `qualifier_separator` rather than joining it. `namespace_default`
        # says what the scope is when the attribute carrying it is absent,
        # which for a spec that defines that default is a fact about the
        # framework rather than a guess.
        "qualifier_format": mapping.get("qualifier_format"),
        # The declared word's TEMPLATE, not the word: see `_NAMESPACE_DEFAULTS`.
        # NULL where the catalog declares no default, which is what keeps the
        # derivation below inert for every catalog but the ones that ask.
        "namespace_template": _NAMESPACE_DEFAULTS.get(str(mapping.get("namespace_default"))),
        # 2I design §2, word 3: the class-gate MEMBER rule. NULL where a
        # catalog declares none, which is every catalog whose framework
        # exposes only what an annotation marks.
        "members": mapping.get("members"),
        # What joins a TYPE-level prefix to the address it prefixes, and the
        # character deduped where both halves already spell it. Optional and
        # inert while absent, so a catalog composing a Kafka topic — which has
        # no segments to join — keeps the bare concatenation it always had.
        "path_separator": mapping.get("path_separator"),
        # 2O Task 7 Step 3: a CONSTANT prefix the framework itself puts in
        # front of every address this catalog derives — not read from any
        # annotation, because no annotation states it. It joins the front of
        # the type-level prefix under the same seam rule, so a catalog
        # declaring none composes exactly what it always did.
        "path_prefix": mapping.get("path_prefix"),
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
        "canonical_path": serves_urls(catalog.protocol, catalog.direction),
        # D02 §2c's `resolves.direction`, the ONE resolution rule that shipped:
        # what a row's direction becomes where the catalog's condition holds,
        # NULL where the catalog declares no rule — which is every catalog but
        # the one whose annotation family genuinely faces both ways, and what
        # keeps their derivations byte-identical.
        "flip_direction": flip.direction,
        # Which OWNERS the condition holds for, and what handles each flipped
        # declaration. Both empty where there is no rule.
        "flip_owners": flip.owners,
        "flip_handlers": flip.handlers,
        # `$canonical_path`'s twin for a FLIPPED row, decided the same way from
        # the same seam (`serves_urls`) — the resolved direction is the row's
        # direction, so it is the direction the address question is asked of.
        # Without this a flipped row's address would be canonicalized under the
        # rule for the direction the catalog DECLARED rather than the one the
        # row took, and an inbound route the module serves would keep a
        # spelling the framework does not answer at — which also splits it from
        # the identical route a controller's own mapping derives, and stops the
        # two merging (ruling R12).
        "flip_canonical_path": flip.canonical_path,
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
        "synthetic_annotations": _synthetic_annotations(
            workspace, catalog, mapping_annotations, prefix_fqns, type_annotation_fqns
        ),
    }


# D02 §2's `corroborates` block: an optional, catalog-declared list of
# CLASS-LEVEL annotations that mark a class as serving something without
# naming what it serves (2O design §1b, fix round 2's I-2). Absent on every
# catalog written before it, and inert while absent — `gaps` returns an empty
# list and `run` is untouched.
_HANDLER_PROTOCOL = "handler_protocol"
_UNRESOLVABLE_FRAMEWORK = (
    "this module's build does not settle whether it declares one of {coordinates}, so the "
    "annotation this class carries — claimed by more than one framework — leaves which wire "
    "it serves unread"
)
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
    unresolvable = _unresolvable_framework_questions(workspace, catalog)
    declared = _corroboration(catalog)
    if declared is None:
        return unresolvable
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


def _unresolvable_framework_questions(
    workspace: Workspace, catalog: Catalog
) -> list[dict[str, Any]]:
    """One `handler_protocol` question per class this catalog would have claimed,
    where the module's build cannot say whether this catalog's framework is the
    one serving it (F2 §3.6).

    **Both failing branches of the gate, not just one.** An earlier version fired
    only where NO module fact was recorded, reasoning that "a build that records
    coordinates and names neither library has said something". It has not, and
    `dependencies.py`'s own `_NOT_DECLARED` message says so in the same breath:
    on Maven a dependency reaching this module only as another artifact's own
    transitive is absent from the recorded set and *cannot be told apart from
    real absence here*. The case that reasoning lost is ordinary — a Maven module
    whose STOMP dependency arrives through a company aggregate artifact derived
    its five rows before W16 and afterwards derived nothing and asked nothing.

    **Only classes this catalog's match would actually have claimed.** The
    mapping annotation is not the whole rule: `A-C1` added the
    `type_annotation` conjunct precisely so a bare `@MessageMapping` method could
    not mint a declaration, and a question filed without it asks which wire is
    served by a class neither framework's handler would scan.

    **Only classes nothing derived a row for.** Where the sibling catalog's gate
    WAS satisfied the class is already published on a protocol, and a question
    asking which wire it serves is noise beside an answer. This is a property of
    the finished `endpoints` table, which is why `record_service_identity_gaps`
    runs every `gaps` after `derive_endpoints` rather than during it.

    The question's `protocol` is NULL. Naming one would answer the question the
    row exists to ask.
    """
    if not catalog.detect_required:
        return []
    if unmet_dependency(workspace, catalog) is None:
        return []
    mapping = catalog.matches.get("mapping") or {}
    wanted = {_catalog_symbol(str(entry["fqn"])) for entry in mapping.get("annotations") or []}
    if not wanted:
        return []
    # The `type_annotation` conjunct, in the same form `run` reads it.
    declared_type_annotation = catalog.matches.get("type_annotation")
    gate = (
        None
        if declared_type_annotation is None
        # `catalog_symbols` already returns the `a/b/C#` form the table holds.
        else set(catalog_symbols(declared_type_annotation, f"{catalog.source}: type_annotation"))
    )
    # `method_declarations`, not `method_symbols`: the latter selects the symbol
    # alone, and the enclosing TYPE is what a question about a handler class has
    # to name.
    enclosing = {
        str(row["symbol"]): str(row["enclosing"] or "")
        for row in workspace.query("method_declarations")
    }
    annotations = list(workspace.query("annotations"))
    gated_classes = (
        None
        if gate is None
        else {str(row["target"]) for row in annotations if str(row["annotation"]) in gate}
    )
    # A class already published on some wire is answered, not open.
    # `owner_of` rather than slicing the symbol here: the grammar lives in one
    # module (`test_symbol_grammar_confinement.py`, which matches the offending
    # spelling in comments too, so this one describes it instead of writing it).
    # It answers `None` for an ownerless
    # descriptor, which is a real answer here — a free function is not a handler
    # class — so those drop out rather than being coerced.
    published = {
        owner
        for row in workspace.query("endpoints")
        if row["handler"] is not None
        for owner in [owner_of(str(row["handler"]))]
        if owner is not None
    }
    found: dict[str, str] = {}
    for row in annotations:
        annotation = str(row["annotation"])
        if annotation not in wanted:
            continue
        target = str(row["target"])
        owner = enclosing.get(target) or target
        if gated_classes is not None and owner not in gated_classes:
            continue
        if owner in published:
            continue
        found.setdefault(owner, annotation)
    return [
        {
            "protocol": None,
            "method": None,
            "path": owner,
            "question": _HANDLER_PROTOCOL,
            "candidates": json.dumps(
                # The catalog's own `protocol` is what makes two catalogs' rows
                # for one class distinguishable to a reader: the question is
                # "which of these wires", and without them both rows render as
                # the same sentence twice.
                [{"class": owner, "annotation": annotation, "protocol": catalog.protocol}],
                sort_keys=True,
                separators=(",", ":"),
            ),
            "evidence": _UNRESOLVABLE_FRAMEWORK.format(
                coordinates=", ".join(catalog.detect_coordinates)
            ),
        }
        for owner, annotation in sorted(found.items())
    ]


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
#
# **THE THREE DECLARING-TYPE WORDS** (spec 2026-09-22 §2b, CP-30 rows 1-3) bind
# an EMPTY tuple, and the empty tuple says something different for them than it
# does for `construct_name`: they do not read the construct's own name the way
# the accessor words do, so there is no prefix to strip off it. The derivation
# branches on the WORD for these three, which is why they live in this mapping
# rather than in a second one beside it — a second vocabulary would let a typo
# be refused by one check and read as "no fallback" by the other, and the
# refusal is the whole reason this is a closed set.
#
# `declaring_type_simple_name` — the simple name of the type that DECLARED the
# annotated member, which is NOT the handler's own class. Under the inheritance
# walk the declaration sits on the interface while the row's handler is the
# implementor's override, and the two coming apart is the whole of the rule:
# CP-30 Q1 disassembles the constructor that takes `getSimpleName()` of the
# INTERFACE on one branch (offset 101) and the reflected method's own name on
# every other (offset 122). Reading the handler's class instead would publish
# the implementor's name, which is a type no caller ever names.
#
# `declaring_type_qualified_name` — the same type, fully qualified, nothing
# stripped (CP-30's row 3 framework has no simple-name step at all).
#
# `prefixed_capitalized_construct_name` — the declaring type's own prefix
# attribute (named by `mapping.fallback_prefix_attr`, read off that type's
# `type_annotation` use) in front of the construct name with its first
# character upper-cased. Both halves are measured: CP-30 Q2 shows the
# empty-name test at offset 50 GUARDING the prefix composition at offset 66,
# and Q3 shows the default name is `substring(0, 1).toUpperCase()` appended to
# `substring(1)`. Composing the prefix INSIDE the fallback is what makes the
# named-member edge free — a member carrying its own name never reaches a
# fallback, so it skips the prefix BY CONSTRUCTION rather than by a flag, and a
# member named `Charge` under the prefix `billing_` is `Charge` and never
# `billing_Charge`. That edge is what tells this rule from every paraphrase of
# it, and it is asserted.
#
# What a misread costs here is the accessor words' cost one step worse: read as
# `construct_name`, a declaring-type word publishes a MEMBER name where a TYPE
# name belongs — an identity nothing answers, at `resolved`/`compiler` where
# nothing downstream can tell it from an observation.
# `declaring_type_scoped_name` — the declaring type's simple name, a
# catalog-stated separator, and THE NAME THAT WON: the declaration's own name
# where it wrote one, the construct's name where it did not.
#
# **IT IS THE ONE ENTRY IN THIS VOCABULARY THAT ALSO COMPOSES AROUND A NAME THE
# DECLARATION DID WRITE**, and that is the rule rather than an inconsistency.
# Every other word answers "what is the name when the annotation carries none";
# this one answers a different question, because the SCOPE is not a framework
# default at all. Temporal's own name for a signal IS the bare member name
# (CP-30 Q1, offset 122) or the annotation's own (`Optional.orElse`, offset 81)
# — the workflow type in front of it is spec 2026-09-22 §1d's IDENTITY rule,
# which exists so that two workflows' `cancel` are two endpoints. A scope
# applied only to the members that named nothing would leave
# `@SignalMethod(name = "Abort")` publishing a bare `Abort` — the colliding
# identity §2f refuses for `WorkflowStub.signal("cancel", …)`, reached by the
# other route. So the word composes either way and the derivation hoists it out
# of the named-nothing branch; the composition is still written INSIDE the
# fallback expression, so every catalog that does not declare it derives
# byte-identically.
#
# The separator is CATALOG DATA (`mapping.fallback_scope_separator`), never a
# literal in the engine, for the reason `$path_separator` and
# `$qualifier_separator` already state: which punctuation joins two halves of an
# address is a framework's convention, and an engine that picked one would be
# naming a framework in code. `_validate_fallback_scope_separator` refuses the
# word without it and it without the word.
_SCOPED_FALLBACK = "declaring_type_scoped_name"
_FALLBACK_SCOPE_SEPARATOR = "fallback_scope_separator"

_PATH_FALLBACKS: dict[str, tuple[str, ...]] = {
    "construct_name": (),
    "read_accessor_property": ("get", "is"),
    "write_accessor_property": ("set",),
    "declaring_type_simple_name": (),
    "declaring_type_qualified_name": (),
    "prefixed_capitalized_construct_name": (),
    _SCOPED_FALLBACK: (),
}

# The one word above that composes a prefix, and the mapping key naming WHICH
# attribute of the declaring type's `type_annotation` use carries it.
#
# A key of its own rather than `mapping.prefix_from`, and the two must not be
# conflated: `derive_endpoints.sql` feeds a `prefix_from` value into
# `type_prefix`, which joins the FRONT of every address the catalog composes —
# so a catalog naming the prefix there would compose it a SECOND time onto
# every row, including the explicitly-named member that must not carry it at
# all. A catalog reaching for this word therefore leaves the ordinary prefix
# machinery inert (`prefix_from: []`, no `path_prefix`/`path_separator`) and
# states the attribute here instead.
_PREFIXED_FALLBACK = "prefixed_capitalized_construct_name"
_FALLBACK_PREFIX_ATTR = "fallback_prefix_attr"


# F2 §3.5. How a class-level annotation relates to the methods inside it.
#
# `prefix` composes the two, which is right where composition is real: an HTTP
# `@RequestMapping("/api")` on the class and `@GetMapping("/orders")` on the
# method address `/api/orders`, and a WebSocket `@ServerEndpoint("/live")` whose
# `@OnMessage` methods carry no address of their own take the class's unchanged.
#
# `sibling` is right where it is not. Measured per framework in
# `scripts/probes/w14_listener_registration.md`: `@KafkaListener` and
# `@RabbitListener` are both `@Target(TYPE, METHOD)`, both declare a destination
# attribute, and both registrars declare TWO paths — `findListenerAnnotations`
# taking a `Class` beside one taking a `Method`, feeding
# `processMultiMethodListeners` beside `processKafkaListener` — with neither
# excluding the other. A class carrying both therefore registers TWO containers
# on two topics, and composing them produced `orderspayments`, a destination no
# broker carries, at `resolved`.
_CLASS_LEVEL = "class_level"
_PREFIX = "prefix"
_SIBLING = "sibling"
_CLASS_LEVEL_VALUES = (_PREFIX, _SIBLING)


def _class_level(mapping: dict[str, Any], catalog: Catalog) -> str:
    """The declared relationship, defaulting to `prefix`.

    Defaulted rather than required, and this is the one decision here worth
    stating: every catalog written before §3.5 assumed composition, so requiring
    the key would refuse ten shipped files to describe a rule nine of them
    already follow. The default is the OLD behaviour, so adding the key changes
    only the catalogs that declare it.

    What the default is NOT is a claim that composition is right for an
    undeclared catalog — it is a claim that this key is how a catalog says
    otherwise. A messaging catalog that declares neither still composes, which
    is why `spring-kafka.yml` and `spring-rabbit.yml` declare it explicitly
    rather than relying on anything.
    """
    declared = mapping.get(_CLASS_LEVEL, _PREFIX)
    if declared not in _CLASS_LEVEL_VALUES:
        # Unreachable through `derive_endpoints`, which refuses this in its
        # pre-flight before `endpoints_reset` — kept because this function is
        # also the one a future caller would reach first, and a reader should
        # not have to know the pre-flight exists to know the value is closed.
        raise CatalogError(
            f"loading catalog {catalog.source}: `mapping.{_CLASS_LEVEL}: {declared!r}` is not "
            f"one of {list(_CLASS_LEVEL_VALUES)} (F2 §3.5)"
        )
    return str(declared)


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


def _sibling_sources(
    catalog: Catalog,
    mapping: dict[str, Any],
    key: str = "path_from_siblings",
    shown: str | None = None,
) -> list[dict[str, object]]:
    """`mapping.<key>` as `{ordinal, annotation, arg}` rows, the ordinal counting
    from the order the catalog wrote (`OI-35`). `key` defaults to the name
    word, `path_from_siblings`; `produces_from_siblings`/`consumes_from_siblings`
    (Spec 2026-09-18 §3b word 1) read the identical shape through the same
    function, for the same reason — the framework's media types sit on a
    sibling exactly the way its name does.

    `shown`, where given, names the mapping key printed in the refusal instead
    of `key` — for `_type_media_sources` (Spec 2026-09-18 §3b word 2), which
    reuses this function's shape check under a synthetic one-key mapping
    (`{"_": [...]}`) so it does not have to duplicate the check, and needs the
    refusal to name the real key (`type_media_from_siblings.produces`) rather
    than the synthetic one (`_`).

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
    declared = mapping.get(key)
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
            f"loading catalog {catalog.source}: `mapping.{shown or key}` must be a non-empty "
            f"list of `{{{', '.join(sorted(_SIBLING_KEYS))}}}` entries naming an annotation and "
            f"one of its attributes, in the order the framework consults them — got {declared!r} "
            f"(`OI-35`)"
        )
    return [
        {
            "ordinal": ordinal,
            "annotation": _catalog_symbol(source["annotation"]),
            "arg": str(source["arg"]),
        }
        for ordinal, source in enumerate(declared, start=1)
    ]


def _type_media_sources(catalog: Catalog, mapping: dict[str, Any]) -> list[dict[str, object]]:
    """`mapping.type_media_from_siblings` flattened to `{column, ordinal, annotation, arg}`
    rows — the class-level media default read off a TYPE-level sibling (spec 2026-09-18
    §3b word 2). Refused unless a mapping of `produces`/`consumes` to sibling lists."""
    declared = mapping.get("type_media_from_siblings")
    if declared is None:
        return []
    if (
        not isinstance(declared, dict)
        or not declared
        or not set(declared) <= {"produces", "consumes"}
    ):
        raise CatalogError(
            f"loading catalog {catalog.source}: `mapping.type_media_from_siblings` must be a "
            f"mapping of `produces`/`consumes` to sibling-source lists — got {declared!r}"
        )
    rows: list[dict[str, object]] = []
    for column in ("produces", "consumes"):
        if column in declared:
            for source in _sibling_sources(
                catalog, {"_": declared[column]}, "_", shown=f"type_media_from_siblings.{column}"
            ):
                rows.append({"column": column, **source})
    return rows


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
#
# `declared_type_methods` is the second word (spec 2026-09-22 §2c, M-3), and it
# exists because `public_methods` is WRONG for a framework whose contract lives
# on a type the implementor inherits. The gate annotation is inherited onto the
# implementing class — that is what makes the class a gate type at all — so
# `public_methods` enumerates the implementor's OWN declarations too, and a
# public helper beside the contract methods publishes as an operation nothing
# calls. §2c's example is a class implementing a two-method contract and
# declaring a `reloadRates()` of its own: `public_methods` publishes it.
#
# The new word is `public_methods` plus one conjunct — the member's DECLARING
# type must carry the gate as a REAL annotation row, never the synthetic one
# the inheritance walk wrote — so only members declared where the contract is
# declared are enumerated. CP-30 Q4 is why such a catalog needs a member rule
# at all: the qualification predicate returns true at offset 73 for an
# UNANNOTATED non-static, non-synthetic method, so the contract's members are
# operations whether or not anything marks them.
#
# Read as `public_methods` this word costs exactly what M-3 costs: one endpoint
# per helper method on every implementing class, at `resolved`/`compiler`.
# Read as "no member rule" it costs the whole contract — every member of it,
# silently, because none of them carries an annotation to derive from.
_MEMBER_RULES = frozenset({"public_methods", "declared_type_methods"})

# Whether the inheritance walk carries a catalog's declared SIBLINGS along
# with an inherited mapping (spec 2026-09-18 §3b word 3, amended after the
# final review: OPT-IN). Today's one word is 'all_or_nothing': JAX-RS §3.6's
# rule, quoted at CP-18 row 8 — a method carrying none of the catalog's
# annotations inherits the ancestor method's mapping and every declared
# sibling beside it, and one carrying ANY of its own inherits nothing.
#
# Opt-in rather than implied by the sibling lists, because naming a sibling
# says where a NAME lives and nothing about how the framework inherits:
# `microprofile-graphql.yml` declares `path_from_siblings` (`OI-35`) and a
# type gate, and SmallRye GraphQL has no §3.6 — an implementor method carrying
# only its own `@Name` must still inherit the interface's `@Query`. A catalog
# declaring no word keeps the mapping-only own-check and Spring's
# per-annotation merge, exactly as before the word existed.
#
# A closed vocabulary for `_PATH_FALLBACKS`'s reason: a typo read as "no
# rule" silently restores the wrong address (an inherited `@GET` with no
# `@Path` beside it) the word exists to remove.
_INHERIT_SIBLINGS = frozenset({"all_or_nothing"})

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
        # module becomes an endpoint. The gate may be `type_annotation` — one
        # name or, since §3.1, a list of spellings — or one of this catalog's
        # own `mapping.annotations` found on a TYPE, which is how a framework
        # that gates on the mapping annotation itself and declares no separate
        # type-level annotation still names a class. That is the same
        # type-level join `qualifier_scopes` reads a class-level scope through.
        # (The reason recorded here used to be that `type_annotation` was one
        # fqn and could not carry two spellings; it carries a list now.)
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
    # AFTER the entry loop, and the order is the rule rather than a placement:
    # this check READS every entry's own fallback word, so a misspelled one
    # reaches it as an unrecognised word and would be reported as "the
    # attribute names a rule nothing runs" — a refusal naming the wrong key,
    # which sends a catalog author to fix a line that is correct. The
    # closed-set check above says what is actually wrong, so it runs first.
    _validate_fallback_prefix_attr(catalog, mapping)
    _validate_fallback_scope_separator(catalog, mapping)
    _sibling_sources(catalog, mapping)
    inherit_siblings = mapping.get("inherit_siblings")
    if inherit_siblings is not None and inherit_siblings not in _INHERIT_SIBLINGS:
        # An unrecognised word read as "no rule" keeps the mapping-only walk,
        # and an inherited verb then lands on the implementor WITHOUT the
        # `@Path` beside it — the wrong address the word exists to remove.
        raise CatalogError(
            f"loading catalog {catalog.source}: `mapping.inherit_siblings: {inherit_siblings}` "
            f"is not one of {', '.join(sorted(_INHERIT_SIBLINGS))} (spec 2026-09-18 §3b word 3)"
        )
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


def metadata_from(catalog: Catalog) -> list[dict[str, Any]]:
    """The catalog's `metadata_from` entries, validated and converted to the
    descriptor form the `annotations` view spells, or empty where it declares
    none (spec 2026-09-22 §1f).

    Read here rather than in `endpoint_attributes.py` because the key is this
    engine's — a `metadata_from` entry names an ANNOTATION and one of its
    attributes, which is the same vocabulary `mapping.annotations` is written
    in — and because the one check that needs the catalog's direction rule
    (`_direction_rule`) lives in this module.
    """
    declared = catalog.matches.get("metadata_from")
    if declared is None:
        return []
    where = f"loading catalog {catalog.source}: `metadata_from`"
    if not isinstance(declared, list) or not declared:
        raise CatalogError(
            f"{where} must be a non-empty list of entries, got {declared!r} — a catalog that "
            f"declares the key and names no attribute records nothing while reading as though "
            f"it did"
        )
    _validate_metadata_from(catalog, where)
    return [_metadata_entry(entry, where) for entry in declared]


def _validate_metadata_from(catalog: Catalog, where: str) -> None:
    """Refuses `metadata_from` on a catalog whose rows can only ever be
    OUTBOUND, and that is a claim rather than a limit nobody has lifted yet.

    Spec 2026-09-22 §1f rules that a qualifying attribute belongs to the side
    of the wire that DECLARES it. Every attribute this key reads sits on a
    listener or on an implementation — the receiving side — so an outbound
    catalog declaring it would be stating a peer's configuration as its own:
    a row saying "this call is made under consumer group X" when X is a fact
    about whoever answers.

    A catalog's DECLARED direction is not the test, because one of the first
    consumers declares `outbound` and reaches `inbound` through a
    `resolves.direction` flip (the flip is what keeps a contract's own
    declaration as the row while rebinding the handler to the implementor's
    override). So the question asked here is the honest one: can this catalog
    own an inbound row at all? Its declared direction, or the direction its
    flip resolves to, must be inbound. The PASS then reads each row's own
    `direction` column, which is final by the time it runs.
    """
    # The key reads an annotation's ARGUMENTS and nothing else, so a catalog that does
    # not require the capability producing them is one whose every `args` map is empty
    # on a scanner that does not read them. Every attribute would then read as ABSENT,
    # and an entry declaring `absent_value` would write its measured default against
    # every endpoint the catalog owns — a default attributed to declarations nobody
    # looked at, which is the exact fabrication `absent_value` is fenced against (D02 §1:
    # a catalog states what it needs, and the gate skips it VISIBLY where a scan cannot
    # supply it). Refused here rather than left to the gate because the gate only skips a
    # catalog that ASKED; one that never asked is the silent case.
    if _ANNOTATION_ARGS not in catalog.requires:
        raise CatalogError(
            f"{where} reads annotation arguments, so the catalog must declare "
            f"`requires: [{_ANNOTATION_ARGS}]` — without it a scanner that does not read "
            f"arguments leaves every attribute reading as absent, and a declared "
            f"`absent_value` would be written against every endpoint as though the default "
            f"had been measured there"
        )
    rule = _direction_rule(catalog)
    reachable = {catalog.direction} | ({rule[0]} if rule is not None else set())
    if Direction.INBOUND.value in reachable:
        return
    raise CatalogError(
        f"{where} is declared on a catalog whose rows are {'/'.join(sorted(reachable))} — a "
        f"qualifying attribute belongs to the side of the wire that declares it (spec "
        f"2026-09-22 §1f), and every attribute this key reads sits on the receiving side, so "
        f"an outbound entry would state a peer's configuration as this module's own"
    )


# D02 §1's capability id for "the scanner reads annotation arguments". A capability name,
# not a framework's: it names what a SCAN produces, which is why `requires` is spelled in
# the same vocabulary on every catalog that reads an attribute at all.
_ANNOTATION_ARGS = "annotation_args"


def _metadata_entry(entry: object, where: str) -> dict[str, Any]:
    """One `{annotation, attribute, kind}` triple, with an optional
    `absent_value`.

    The SHAPE is checked and the vocabulary is not: `endpoint_metadata.kind`'s
    own comment says the set of kinds is per protocol and the catalog names it,
    exactly as `semantics` on a wrapper is — so `task_queue`,
    `consumer_group`, `selector` are the catalog's words and this engine has no
    list to check them against. What IS checked is that each is a non-empty
    string, because an empty `kind` or `attribute` read as written would put a
    nameless row in a published table.

    `absent_value` is a STRING and a YAML boolean is refused rather than
    coerced: the value lands in a TEXT column beside values read off the class
    file, where `true` is the text a JSON boolean reads back as (`_unless_equals`
    states the same rule), and `str(True)` is `'True'` — a spelling nothing
    else in this repository writes. Quoting it in the catalog is one character
    and removes the question.
    """
    if not isinstance(entry, dict) or not set(entry) <= _METADATA_FROM_KEYS:
        raise CatalogError(
            f"{where} entries carry only {'/'.join(sorted(_METADATA_FROM_KEYS))}, got {entry!r}"
        )
    for key in ("annotation", "attribute", "kind"):
        value = entry.get(key)
        if not isinstance(value, str) or not value:
            raise CatalogError(f"{where} `{key}` must be a non-empty string: {entry!r}")
    absent = entry.get("absent_value")
    if absent is not None and (not isinstance(absent, str) or not absent):
        raise CatalogError(
            f"{where} `absent_value` must be a non-empty string — quoted, so a YAML `true` is "
            f"the text the value reads back as rather than a boolean: {entry!r}"
        )
    return {
        "annotation": _catalog_symbol(str(entry["annotation"])),
        "attribute": str(entry["attribute"]),
        "kind": str(entry["kind"]),
        "absent_value": None if absent is None else str(absent),
    }


# Every key a `metadata_from` entry may carry (spec 2026-09-22 §1f). `absent_value` is
# the one optional: an attribute the declaration did not write reaches the class file
# nowhere at all, so a catalog that has MEASURED the annotation's own `AnnotationDefault`
# states it here and cites the probe beside the line. A catalog that has not measured one
# writes nothing for an absent attribute — silence is the honest answer, and a default
# nobody measured must never be invented (GUIDELINES §8.2).
_METADATA_FROM_KEYS = frozenset({"annotation", "attribute", "kind", "absent_value"})


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


def _validate_fallback_prefix_attr(catalog: Catalog, mapping: dict[str, Any]) -> None:
    """Refuses a mapping that declares the prefix-composing fallback word
    without naming the attribute carrying the prefix or without the type gate
    that attribute is read off, and one that names the attribute with no word
    reading it (spec 2026-09-22 §2b).

    None of the three is symmetry for its own sake. WITHOUT the attribute, or
    without a `type_annotation` to read it off, the word composes an empty
    prefix onto every row it names — an address that is a fragment of the one
    the framework serves, published at `resolved`/`compiler`, which is the
    confidently-wrong-address failure the whole naming vocabulary is checked
    for. WITH the attribute and no word reading it, the catalog states a rule
    nothing runs, and a reader of the file believes the prefix is composed
    somewhere: the `_RESOLVES` discipline, and the one this engine applies to
    every key it would otherwise ignore.

    Both LEVELS are consulted, because either can name the word (`OI-5`): the
    attribute belongs to the FILE, since the type it is read off is the file's
    own gate, but the word that needs it may sit on one annotation entry.
    """
    declared = {mapping.get("path_fallback")}
    declared |= {
        entry.get("path_fallback") for entry in mapping["annotations"] if isinstance(entry, dict)
    }
    attribute = mapping.get(_FALLBACK_PREFIX_ATTR)
    if _PREFIXED_FALLBACK in declared:
        # A non-string scalar or an empty name is refused rather than read as
        # absent, the `path_prefix` precedent: `str()` of a YAML int is an
        # attribute name nobody wrote, and an empty one reads every row's
        # prefix as absent while looking like a file that states one.
        if not isinstance(attribute, str) or attribute == "":
            raise CatalogError(
                f"loading catalog {catalog.source}: `path_fallback: {_PREFIXED_FALLBACK}` is "
                f"declared with no `mapping.{_FALLBACK_PREFIX_ATTR}` naming a non-empty "
                f"attribute — got {attribute!r}. The word composes the declaring type's own "
                f"prefix, and with nothing to read it from every row would carry the bare "
                f"member name the framework does not serve (spec 2026-09-22 §2b)"
            )
        # AND THE TYPE GATE, the `members` class-gate check's shape one key
        # over. The attribute is read off the declaring type's
        # `type_annotation` USE and nowhere else, so a catalog that declares no
        # `type_annotation` has no annotation row to read it from — every
        # address the word composes is then the bare member name, which is a
        # FRAGMENT of the one the framework serves and exactly what the two
        # refusals above exist to prevent. It is refused rather than left
        # inert, because a fragment published at `resolved`/`compiler` is
        # indistinguishable downstream from an address that was observed.
        if catalog.matches.get("type_annotation") is None:
            raise CatalogError(
                f"loading catalog {catalog.source}: `path_fallback: {_PREFIXED_FALLBACK}` is "
                f"declared with no `type_annotation` — `mapping.{_FALLBACK_PREFIX_ATTR}: "
                f"{attribute}` is read off the declaring type's own `type_annotation` use, so "
                f"with no such gate every row would compose the bare member name without the "
                f"prefix in front of it (spec 2026-09-22 §2b)"
            )
    elif attribute is not None:
        raise CatalogError(
            f"loading catalog {catalog.source}: `mapping.{_FALLBACK_PREFIX_ATTR}: {attribute}` is "
            f"declared with no `path_fallback: {_PREFIXED_FALLBACK}` to read it — no other word "
            f"composes a prefix, so the attribute names a rule nothing runs "
            f"(spec 2026-09-22 §2b)"
        )


def _validate_fallback_scope_separator(catalog: Catalog, mapping: dict[str, Any]) -> None:
    """Refuses a mapping that declares the type-scoping fallback word without
    the separator it composes with, and one that names the separator with no
    word reading it (spec 2026-09-22 §1d).

    `_validate_fallback_prefix_attr`'s two refusals, one key over, and they are
    the same two failures rather than symmetry. WITHOUT the separator the word
    composes `OrderWorkflowcancel` — one token that is neither half, published
    at `resolved`/`compiler` where nothing downstream can tell it from an
    address somebody observed. WITH the separator and no word reading it, the
    catalog states a punctuation rule nothing runs, and a reader of the file
    believes the scope is composed somewhere.

    There is no third refusal here, and the absence is deliberate: unlike
    `prefixed_capitalized_construct_name`, this word reads no ANNOTATION at all
    — the declaring type comes off the declaration's own symbol — so there is
    no `type_annotation` for it to be missing.

    Both LEVELS are consulted for the word, because either can name it
    (`OI-5`), while the separator belongs to the FILE: a catalog whose
    operations are scoped by their declaring type scopes all of them the same
    way, and a per-entry separator would let one annotation's rows carry a
    punctuation the others do not.
    """
    declared = {mapping.get("path_fallback")}
    declared |= {
        entry.get("path_fallback") for entry in mapping["annotations"] if isinstance(entry, dict)
    }
    separator = mapping.get(_FALLBACK_SCOPE_SEPARATOR)
    if _SCOPED_FALLBACK in declared:
        # A non-string scalar and an empty string are refused rather than read
        # as absent, `_validate_fallback_prefix_attr`'s own reading: an empty
        # separator composes the two halves into one token that is neither.
        if not isinstance(separator, str) or separator == "":
            raise CatalogError(
                f"loading catalog {catalog.source}: `path_fallback: {_SCOPED_FALLBACK}` is "
                f"declared with no `mapping.{_FALLBACK_SCOPE_SEPARATOR}` naming a non-empty "
                f"separator — got {separator!r}. The word joins the declaring type's simple "
                f"name to the declared name, and with nothing between them every row would "
                f"carry one token that is neither half (spec 2026-09-22 §1d)"
            )
    elif separator is not None:
        raise CatalogError(
            f"loading catalog {catalog.source}: `mapping.{_FALLBACK_SCOPE_SEPARATOR}: "
            f"{separator!r}` is declared with no `path_fallback: {_SCOPED_FALLBACK}` to read "
            f"it — no other word composes a scope, so the separator names a rule nothing runs "
            f"(spec 2026-09-22 §1d)"
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
    prefix_fqns: list[str] | None,
    type_annotation_fqns: list[str] | None,
) -> list[dict[str, Any]]:
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
    # Decoded once per load and shared (`Workspace.once`): every row below is
    # read from the shared list, and the lists built from it are new lists.
    annotation_rows = workspace.once(_annotation_rows)
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
        mapping_fqns | (set(type_annotation_fqns) if type_annotation_fqns is not None else set()),
    )
    run_inheritance = type_annotation_fqns is not None
    inherited = (
        inherited_rows_over(
            workspace.once(_type_hierarchy),
            [*annotation_rows, *composed],
            mapping_fqns,
            prefix_fqns,
            sibling_fqns=_inherited_sibling_fqns(catalog),
        )
        if run_inheritance
        else []
    )
    # `inherited` says WHICH pass wrote a row, and it is carried because one
    # rule has to tell them apart (spec 2026-09-22 §2c): a gate carried across
    # a type boundary by the INHERITANCE walk is a gate the type does not
    # declare, while a folded or composed row is the very annotation the author
    # wrote on that type, read out of the shape javac stored it in (`OI-36`) or
    # through the stereotype it was composed into (`A-C7`). `catalog_id` cannot
    # answer this: all three passes write it. Every consumer but the one that
    # asks reads this column not at all, so the other rules are unchanged.
    return [
        {
            "target": row["target"],
            "annotation": row["annotation"],
            "args": json.dumps(row["args"]),
            "inherited": inherited_pass,
        }
        for rows, inherited_pass in ((folded, False), (composed, False), (inherited, True))
        for row in rows
    ]


def _inherited_sibling_fqns(catalog: Catalog) -> frozenset[str]:
    """The catalog's declared SIBLINGS — every annotation its sibling lists and
    its `protocol_hint.hint_annotations` name — for the walk to carry with an
    inherited mapping, all or nothing (spec 2026-09-18 §3b word 3); and EMPTY
    unless the catalog opts in with `mapping.inherit_siblings: all_or_nothing`
    (`_INHERIT_SIBLINGS`), which leaves the walk mapping-only for every other
    catalog — a sibling list alone says where a name lives, not how the
    framework inherits. `hint_annotations` counts as a sibling here because
    §3.6's own-check is "any JAX-RS annotation", and `quarkus-rest.yml` writes
    the key; the hint pass itself reads raw facts only (`OI-92`)."""
    mapping = catalog.matches["mapping"]
    if mapping.get("inherit_siblings") is None:
        return frozenset()
    return frozenset(
        _catalog_symbol(str(source["annotation"]))
        for key in ("path_from_siblings", "produces_from_siblings", "consumes_from_siblings")
        for source in (mapping.get(key) or [])
    ) | frozenset(
        _catalog_symbol(name) for name in (catalog.protocol_hint.get("hint_annotations") or [])
    )


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
        _catalog_symbol(entry[_CONTAINER]): _catalog_symbol(entry["fqn"])
        for entry in catalog.matches["mapping"]["annotations"]
        if entry.get(_CONTAINER) is not None
    }


def _annotation_rows(workspace: Workspace) -> list[dict[str, Any]]:
    """`annotations`'s rows with `args` decoded — the form `folded_rows`,
    `composed_mapping_rows` and `inherited_rows` read. Built once per load
    (`Workspace.once`): the decode ran once per catalog, thirty times over the same
    text on `mall-admin`. Shared, so read and never written into."""
    return [
        {
            "target": row["target"],
            "annotation": row["annotation"],
            "args": json.loads(str(row["args"])) if row["args"] is not None else {},
        }
        for row in workspace.query("annotations")
    ]


def _type_hierarchy(workspace: Workspace) -> TypeHierarchy:
    """The inheritance walk's `TypeHierarchy`, from the three reads below — built
    once per load (`Workspace.once`) and read by every catalog's walk."""
    return type_hierarchy(
        _implementation_rows(workspace),
        _superclass_rows(workspace),
        _method_declaration_rows(workspace),
    )


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
    This function used to rebuild each row column by column, and a column added
    to the query and not rebuilt here reached nothing: the walk fell back to
    inferring a bridge from its shape, silently, and every assertion about the
    fixed behaviour still passed because they hand-build their own rows. That is
    exactly what happened, and passing the rows through is what closes it.

    Both columns arrive decoded from the workspace (`_DECODED_COLUMNS`), which is
    what lets `"synthetic" in modifiers` mean membership rather than substring
    search over JSON text. They arrived as text and were decoded HERE, once per
    catalog, until P-1b measured that as 2.6 million `json.loads` calls on
    `mall-admin`; the rows are now shared across every catalog and read only."""
    return workspace.query("method_declarations")


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
    # A LIST or a scalar (§3.1); plural so a stale `==` cannot survive.
    reply_annotations = catalog_symbols(reply["annotation"], f"{catalog.source}: reply.annotation")
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
        descriptor = _payload_descriptor(
            signature.get("returns"), rules, enums, referenced, rules.wrappers
        )
        if descriptor is None:
            continue
        uses = workspace.query("annotations_of", target=handler)
        reply_use = next((use for use in uses if use["annotation"] in reply_annotations), None)
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


def effective_annotation_uses(
    workspace: Workspace, catalog: Catalog
) -> dict[str, list[dict[str, Any]]]:
    """Every annotation use one catalog's endpoint derivation actually MATCHED
    ON, keyed by bare target — the `annotations` view widened by exactly the
    pre-pass `derive_endpoints.sql`'s `annotations_effective` CTE reads.

    A pass that asks a question ABOUT a derived endpoint row must read the same
    annotation set the row was derived from, and W28 shipped reading the raw
    view instead. The two differ in three ways that all point the same
    direction — a module-local composed annotation (`@ApiGet` meta-annotated
    `@GetMapping(params = "v=1")`), a repeatable container javac folded, and a
    mapping declared on an interface method the class does not repeat — and in
    each the endpoint row derives while its attributes read as absent. For a
    conflict detector that is a finding named against code the framework starts
    happily, which NFR-2 rates the worst outcome available.

    Recomputed per catalog rather than cached, because the closure is seeded by
    THIS catalog's own mapping fqns and there is no set that serves two: the
    same walk `run` performs, over the same rows, through the same functions.
    """
    real = [
        {
            "target": bare_descriptor(str(row["target"])),
            "annotation": bare_descriptor(str(row["annotation"])),
            "args": {} if row["args"] is None else json.loads(str(row["args"])),
        }
        for row in workspace.query("annotations")
    ]
    mapping = catalog.matches.get("mapping")
    synthetic: list[dict[str, Any]] = []
    if mapping is not None:
        type_annotation = catalog.matches.get("type_annotation")
        synthetic = _synthetic_annotations(
            workspace,
            catalog,
            [_mapping_annotation(mapping, m) for m in mapping["annotations"]],
            None
            if mapping["prefix_annotation"] is None
            else list(
                catalog_symbols(
                    mapping["prefix_annotation"], f"{catalog.source}: mapping.prefix_annotation"
                )
            ),
            None
            if type_annotation is None
            else list(catalog_symbols(type_annotation, f"{catalog.source}: type_annotation")),
        )
    uses: dict[str, list[dict[str, Any]]] = {}
    for row in (
        *real,
        *(
            {
                "target": bare_descriptor(str(row["target"])),
                "annotation": bare_descriptor(str(row["annotation"])),
                "args": json.loads(str(row["args"])),
            }
            for row in synthetic
        ),
    ):
        uses.setdefault(str(row["target"]), []).append(row)
    return uses
