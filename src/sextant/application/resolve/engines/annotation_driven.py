"""Annotation-driven engine for endpoint derivation (D02 §2).

Framework knowledge — which annotation marks a controller, which annotation
maps to which HTTP method, where the path argument lives — is data, read
from `matches` and carried, unmodified, through to the derivation as bound
parameters. No framework name appears in this module's code.
"""

import json
from typing import Any

from sextant.application.ports.catalogs import Catalog, CatalogError
from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.effective_annotations import (
    composed_mapping_rows,
    inherited_rows,
)
from sextant.application.resolve.shapes.contracts import _payload_descriptor
from sextant.application.resolve.shapes.expansion import _enum_symbols, _rules_of
from sextant.application.resolve.shapes.rooting import _catalog_symbol
from sextant.domain.paths import serves_urls
from sextant.domain.symbols import bare_descriptor


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
    prefix_annotation = mapping["prefix_annotation"]
    # Optional too (Retrofit, spring-jms): no class-level prefix shape.
    prefix_fqn = None if prefix_annotation is None else _catalog_symbol(prefix_annotation)
    mapping_annotations = [
        {
            "fqn": _catalog_symbol(m["fqn"]),
            "methods": m.get("method"),
            # 2H design §1: this annotation names a member of a scope, so a
            # declaration under it has no address at all until the scope is
            # found. Absent (the default) on every annotation that names a
            # top-level identity, which is every annotation shipped before it.
            "requires_qualifier": bool(m.get("requires_qualifier", False)),
            # 2I design §2, word 4: the attribute this rule withdraws itself on,
            # and the value that withdraws it. Both NULL on every annotation
            # that withdraws nothing, which is every annotation shipped before
            # this word — the pair is read as "no filter" and the rule derives
            # exactly what it always did.
            "unless_attribute": _unless_attribute(m),
            "unless_equals": _unless_equals(m),
        }
        for m in mapping["annotations"]
    ]
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
        # 2E design §2, §3: the effective-annotations pre-pass widens
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
            workspace, mapping_annotations, prefix_fqn, type_annotation_fqn is not None
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
_PATH_FALLBACKS = frozenset({"construct_name"})

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
    mapping_annotations: list[dict[str, object]],
    prefix_fqn: str | None,
    run_inheritance: bool,
) -> list[dict[str, str]]:
    """The bound-parameter form `derive_endpoints.sql`'s `annotations_effective`
    CTE expects (D02 §2, §3): every row `composed_mapping_rows` and, where
    `run_inheritance`, `inherited_rows` derive, `args` re-serialized to JSON
    text — DuckDB's `STRUCT(... VARCHAR)` binding shape carries a string,
    not a nested JSON value, the same way every other JSON-typed bound
    parameter in this engine already does.

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
    the client, not a contract some unrelated implementer fulfills, and a
    messaging listener annotation is never interface-inherited by its own
    framework either. Left ungated, one declared route produced three rows
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
    scanned_targets = {str(row["symbol"]) for row in workspace.query("interface_symbols")}
    mapping_fqns = {str(m["fqn"]) for m in mapping_annotations}
    composed = composed_mapping_rows(annotation_rows, scanned_targets, mapping_fqns)
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
        for row in (*composed, *inherited)
    ]


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
    """`method_declarations`'s rows, `signature` decoded — the one named
    query 2E-prep's `method_symbols` cannot serve, since Task 7's bridge
    exclusion (checkpoint item (4)) needs a candidate's own parameter/return
    types, and its inheritance walk needs `enclosing` to place a method
    within its declaring type at all."""
    return [
        {
            "symbol": row["symbol"],
            "enclosing": row["enclosing"],
            "signature": (
                json.loads(str(row["signature"])) if row["signature"] is not None else None
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
