"""The configured path prefix, applied to the rows it moves (spec 2026-10-18, `OI-148`).

A module that sets `server.servlet.context-path=/petclinic` serves EVERY endpoint under it,
and until this pass existed the document published them without it — 44 wrong routes in a
pinned corpus, recorded in its own field expectation. COVERAGE §5.1 stated the cause in its
own words: *"`annotation_driven` never touches `resolved_config` … a module that overrides
the base path is published under `/actuator` regardless."*

**Why a pass and not a rung in each engine.** The prefix is a property of the module's
SERVER, so it moves rows every engine derived — annotation-driven controllers, a
`config_join` route, `spring-data-rest` repositories, Actuator. One pass applies it once,
and a catalog written next year is covered without remembering anything. The alternative —
the same declaration in ten catalogs — puts a fact in ten files that none of them owns.

**Where it runs, and why there.** Immediately after `derive_endpoints`, before any pass that
copies a path: `record_roots`, `record_routing_conflicts` and `record_self_exchange` all key
on the address, and a prefix applied after them would leave a root and a conflict keyed on a
path the module does not serve — `OI-28`'s shape.

**Two sources, one application.** A prefix is CONFIGURED — `server.servlet.context-path`
and its siblings, §2 — or INSTALLED, declared in code against the controller packages it
covers (§4):

    mapping.setPathPrefixes(prefixes);   // one prefix per controller package, and
                                         // `ruoyi-vue-pro` serves 480 endpoints this way

The two compose in that order, because `/admin-api` is served INSIDE the context path and not
beside it. Everything below the two readers is shared: one row match, one canonicalisation,
one write.

**What it will not do.** It never invents a prefix. A key no environment declares contributes
nothing; a key whose environments DISAGREE is refused outright and the row keeps the path it
had, because choosing one environment's value would publish an address the other does not
serve. That is the conservative half of the three outcomes `derived_resource._base_path`
already ships for `spring.data.rest.base-path`, and it is unexercised: no corpus has a
divergent prefix (CP-38's own scope note, and §5 of the spec measured all six pins).
"""

import re
from dataclasses import dataclass
from typing import Any

from sextant.application.ports.catalogs import Catalog
from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.dispatch import dispatch_of
from sextant.application.resolve.effective_calls import effective_call_sites
from sextant.application.resolve.values import (
    LITERAL,
    STRING,
    Answer,
    ValueIndex,
    cached_value_index,
    resolve_positions,
)
from sextant.domain.paths import canonical_http_path, is_path_shaped
from sextant.domain.symbols import bare_descriptor, dotted_package, names_a_type, owner_of

# What a row is matched on: its `row_id`, the one column that names exactly the row read
# (follow-the-object, Ruling 7). `prefix_endpoint_paths.sql` says why not its address.
_MATCH_COLUMNS = ("row_id",)

# The argument-grammar kind a lambda is spelled with (D00 §5), and the two labels §4 resolves
# its pair of values under.
_LAMBDA = "lambda"
# A slot holding a method PARAMETER, and one naming a class literal (D00 §5's argument
# grammar) — the two kinds §4's joins read off a slot rather than resolve through the walk.
_PARAMETER_KIND = "parameter"
_CLASS_KIND = "class"
_PREFIX = "prefix"
_PATTERN = "pattern"
# The Ant wildcard that spans SEGMENTS, as against the one that spans characters.
_ANY_SEGMENTS = "**"


def apply_path_prefixes(workspace: Workspace, catalogs: list[Catalog]) -> None:
    """Prefixes every inbound row the module's own server declares a prefix for.

    Reads the server model (hoisted onto every catalog, so the first non-empty one is the
    whole table), `resolved_config` and the module fact's `dependency_versions` for §2, and
    the call sites for §4; writes one column, on rows that already existed, and the
    `endpoint_metadata` entries bound to those rows follow them (ruling 7).

    **Cost (§8.7).** §2 is one fold of `resolved_config` — 100 rows on
    `spring-petclinic-rest` — and then one string join per inbound HTTP row. §4 adds ONE
    linear pass over `effective_call_sites`, which the pipeline has already built and cached,
    to answer whether the installer is called at all; a module that does not call it stops
    there, and `ruoyi`'s three modules are the only corpus in the estate that gets further.
    Past the gate it walks two positions per entry site — one site in `ruoyi`, two in the
    fixture — and nothing is walked per row.
    """
    model = next((catalog.server_model for catalog in catalogs if catalog.server_model), [])
    if not model:
        return
    config = _per_environment(workspace)
    versions = _framework_versions(workspace)

    prefixes: dict[str, str] = {}
    installed: dict[str, tuple[_Installed, ...]] = {}
    for entry in model:
        if entry.get("installed"):
            # §4's declaration names framework SYMBOLS rather than configuration keys, so
            # it is read from the call sites and not from `resolved_config` — and it carries
            # no version range, for the reason the shipped file states beside it.
            declared = _installed_prefixes(workspace, entry)
            if declared:
                for protocol in entry["protocols"]:
                    installed.setdefault(protocol, declared)
            continue
        if not config or not _version_admits(entry, versions):
            continue
        prefix = _composed(entry["keys"], config)
        if not prefix:
            continue
        for protocol in entry["protocols"]:
            # Two entries claiming one protocol would be a contradiction in the model
            # rather than in the module — one server, one prefix per wire — so the first
            # declaration wins and the second is ignored rather than concatenated. The
            # shipped file has no such pair: its two entries differ by stack and their
            # keys cannot both be present (a module is servlet or reactive, not both).
            prefixes.setdefault(protocol, prefix)
    if not prefixes and not installed:
        return
    # Read once, and only where an installed prefix exists to ask about it.
    annotated = _annotated_types(workspace) if installed else {}

    rows: list[dict[str, Any]] = []
    for endpoint in workspace.query("endpoints"):
        if str(endpoint.get("direction")) != "inbound":
            continue
        protocol = str(endpoint.get("protocol"))
        path = endpoint.get("path")
        if not isinstance(path, str) or not path.startswith("/"):
            # A row with no path has no address to prefix, and one that does not start at
            # the root is not a path this server dispatches — both keep what they had.
            continue
        # The CONFIGURED prefix covers every row the server dispatches; the INSTALLED one
        # covers the rows whose handler sits in a package it names. A row can take both,
        # one, or neither, and `""` from either reader is the neutral element.
        served_under = prefixes.get(protocol, "")
        by_package = _for_handler(endpoint.get("handler"), installed.get(protocol, ()), annotated)
        if not served_under and not by_package:
            continue
        rows.append(
            {column: endpoint.get(column) for column in _MATCH_COLUMNS}
            | {"prefixed": canonical_http_path(f"{served_under}{by_package}{path}")}
        )
    if rows:
        workspace.derive("prefix_endpoint_paths", rows=rows)
        # The entries bound to a moved row move with it (Ruling 7).
        workspace.derive("endpoint_rows_follow")


# ---------------------------------------------------------------------------
# §2: the prefix a module CONFIGURES
# ---------------------------------------------------------------------------


def _composed(keys: list[str], config: dict[str, dict[str, str | None]]) -> str:
    """The declared keys' values joined in declaration order, or `""`.

    `server.servlet.context-path=/petclinic/` with `spring.mvc.servlet.path=/api` composes
    to `/petclinic/api`. Separators are normalised here rather than assumed: the measured
    value in `spring-petclinic-rest` ends in `/` and the two must not join into `//`.
    """
    parts: list[str] = []
    for key in keys:
        value = _agreed(config, key)
        if value is None:
            continue
        trimmed = value.strip().strip("/")
        if trimmed:
            parts.append(trimmed)
    return "/" + "/".join(parts) if parts else ""


def _agreed(config: dict[str, dict[str, str | None]], key: str) -> str | None:
    """The one value every environment gives `key`, or None — including for a key no
    environment declares, and for one the environments DISAGREE about.

    `derived_resource._agreed`'s rule, restated rather than shared for the reason that
    function already records about `config_join`'s copy: it is private to another style, and
    the cases it collapses are the same cases this one needs. The disagreement answer is
    None on purpose — a prefix is refused rather than chosen, because one environment's
    value is an address the others do not serve.
    """
    per_environment = config.get(key)
    if not per_environment:
        return None
    distinct = {value for value in per_environment.values() if value is not None}
    if len(distinct) != 1:
        return None
    return distinct.pop()


def _version_admits(entry: dict[str, Any], versions: dict[str, str]) -> bool:
    """Whether this entry's framework and version range admit the module.

    **An UNRECORDED version admits every entry for that framework**, and that is the
    fallback the user ruled on 2026-10-18: a module configures one framework generation, so
    at most one spelling of a key can be present in its configuration, and the configuration
    then decides. `module_dependencies`' own comment states the same rule from the other
    side — *"a reader scoping a rule to a version must treat the absence as
    unanswerable"*.

    It matters because the absence is common and not exotic: `ruoyi-vue-pro` records no Boot
    version at all, its versions coming from an imported BOM and a `${revision}` property
    that the detector follows through neither (`OI-139`, `OI-8`). The direction there is to
    follow the chain rather than cap at a level — `OI-149`'s principle one layer out — and
    until it does, this fallback is what keeps such a module working.
    """
    framework = str(entry["framework"]) + ":"
    found = [
        version for coordinate, version in versions.items() if coordinate.startswith(framework)
    ]
    if not found:
        return True
    return any(_in_range(version, str(entry["versions"])) for version in found)


def _in_range(version: str, specification: str) -> bool:
    """`>=2.0`, `>=2.0 <4.0` — the two forms the shipped model uses, compared on the leading
    numeric components.

    Deliberately not a full version-range grammar: this file reads what
    `server-models/*.yml` declares, the shipped declarations use these two forms, and a
    richer syntax with no consumer is a mechanism nobody has measured. A clause this cannot
    parse raises rather than passing silently, because a range read as "everything" would
    apply a prefix measured on Boot 2 to a Boot 1 module.
    """
    for clause in specification.split():
        operator = clause[:2]
        if operator not in (">=", "<="):
            operator, bound = clause[:1], clause[1:]
            if operator not in ("<", ">"):
                raise ValueError(f"server model: unreadable version clause {clause!r}")
        else:
            bound = clause[2:]
        left, right = _numeric(version), _numeric(bound)
        if operator == ">=" and not left >= right:
            return False
        if operator == "<=" and not left <= right:
            return False
        if operator == ">" and not left > right:
            return False
        if operator == "<" and not left < right:
            return False
    return True


def _numeric(version: str) -> tuple[int, ...]:
    """A version as its leading numeric components — `4.1.1` as `(4, 1, 1)`, `2.7.18-RC1`
    as `(2, 7, 18)`. A component that is not a number ends the tuple, which is what makes a
    qualifier compare as the release it qualifies rather than raising."""
    parts: list[int] = []
    for piece in version.split("."):
        digits = ""
        for character in piece:
            if not character.isdigit():
                break
            digits += character
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts)


# ---------------------------------------------------------------------------
# §4: the prefix a module INSTALLS, per controller package
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Installed:
    """One entry of an installed prefix map, read off the code that declares it.

    `prefix` is the address prefix, `pattern` the Ant pattern over package names it applies
    to, and `annotation` the annotation the predicate requires the handler's class to carry
    — all three from the declaration, none of them assumed.
    """

    prefix: str
    pattern: str
    annotation: str


def _installed_prefixes(workspace: Workspace, entry: dict[str, Any]) -> tuple[_Installed, ...]:
    """Every entry the module declares in code, measured.

    The shape, off `yudao-spring-boot-starter-web`'s facts rather than assumed:

        mapping.setPathPrefixes(prefixes);                      // 1. the installer
        pathPrefixes.put(api.getPrefix(),                       // 2. an entry, 3. the prefix
                clazz -> clazz.isAnnotationPresent(RestController.class)   // 6. the gate
                        && matcher.match(api.getController(),   // 4. the pattern
                                clazz.getPackage().getName()));            // 5. about a PACKAGE

    **Three independent tests, and each of them answers a question the others cannot.**

    1. **Which map.** An entry counts only where the map it writes into is the map an
       installer receives, compared by the object's ORIGIN (`_origins`) rather than by its
       static type or its method. Without this, a module that installs prefixes anywhere has
       EVERY package-keyed predicate map in it read as a prefix declaration — measured on a
       probe: an unrelated `categories.put("AUDIT", clazz -> matcher.match("**.controller.
       audit.**", clazz.getPackage().getName()))` published `GET /AUDIT/audit-logs/{id}` at
       `resolved`, an address the app does not serve.
    2. **That the predicate is about a package** (`_matches_a_package`): `match`'s second
       argument comes from `Package#getName` on `Class#getPackage`. A module has other
       `match` calls, and this is what tells a prefix rule from a request-path test.
    3. **Which classes the predicate admits** (`_required_annotation`): the framework asks
       the predicate only about the handlers that mapping serves, and the predicate itself
       asks for an annotation. A declaration that tests no annotation contributes nothing,
       because "every class this mapping serves" is not a set these facts can name.
    """
    sites = effective_call_sites(workspace)
    installers = _installer_sites(workspace, sites, entry["installer"])
    if not installers:
        return ()
    index = cached_value_index(workspace)
    # WHICH MAP carries prefixes: the origin of every installer's argument 0.
    carries: set[tuple[str, int]] = set()
    for site in installers:
        arguments = site["arguments"] or []
        if arguments:
            carries |= _origins(index, str(site["caller"]), arguments[0], frozenset())
    if not carries:
        return ()

    bodies: dict[str, list[dict[str, Any]]] = {}
    for site in sites:
        bodies.setdefault(bare_descriptor(str(site["caller"])), []).append(site)

    found: list[_Installed] = []
    for site in sites:
        if not _declares(site, entry["entry"]):
            continue
        arguments = site["arguments"] or []
        if len(arguments) < 2 or not isinstance(arguments[1], dict):
            continue
        body = arguments[1].get("symbol") if arguments[1].get("kind") == _LAMBDA else None
        if not isinstance(body, str):
            continue
        if not (_receiver_origins(index, site) & carries):
            continue
        lambda_body = bodies.get(body, [])
        for matcher in lambda_body:
            about = _matches_a_package(index, matcher, entry)
            if about is None:
                continue
            annotation = _required_annotation(lambda_body, about, entry)
            if annotation is None:
                continue
            found.extend(
                _Installed(prefix=prefix, pattern=pattern, annotation=annotation)
                for prefix, pattern in _paired(workspace, index, site, matcher)
            )
    return tuple(dict.fromkeys(found))


def _installer_sites(
    workspace: Workspace, sites: list[dict[str, Any]], declared: dict[str, Any]
) -> list[dict[str, Any]]:
    """The calls that INSTALL a prefix map — the gate, and nothing is read without one.

    An exact owner, or a SUBCLASS of one: `class MyMapping extends
    RequestMappingHandlerMapping` is an ordinary Spring customisation, javac emits
    `invokevirtual MyMapping.setPathPrefixes`, and an exact-owner gate reads such a module as
    installing nothing — measured on a probe, where the admin controller then published its
    unprefixed path. The hierarchy is the module's own (`dispatch_of`'s `subtypes`, which
    `routing_conflicts` already reads for the same question), and it is built only when a
    call NAMES the method, so a module with no such call pays nothing for it.
    """
    named = [site for site in sites if str(site["name"]) == declared["name"]]
    if not named:
        return []
    owners = frozenset(declared["owners"])
    found = [site for site in named if str(site["owner"]) in owners]
    if len(found) == len(named):
        return found
    subtypes = workspace.once(dispatch_of).subtypes
    descendants = frozenset(
        descendant for owner in owners for descendant in subtypes.get(owner, ())
    )
    return [
        site
        for site in named
        if str(site["owner"]) in owners or bare_descriptor(str(site["owner"])) in descendants
    ]


def _origins(
    index: ValueIndex, method: str, argument: Any, seen: frozenset[tuple[str, int]]
) -> frozenset[tuple[str, int]]:
    """WHERE the object a slot holds came from, as `(method, value id)` — the test that
    answers "is this the same map?".

    Object identity is not something the value walk answers: it resolves what a value IS,
    and two maps are two objects holding the same nothing. So this walks the object BACKWARD
    to the frame it was created in and compares that:

    * a value a callee RETURNED is followed into the callee's own returned value — this is
      what makes `ruoyi` work, where the installer's argument is
      `buildPathPrefixes()`'s return and the `put` happens one frame deeper still;
    * a PARAMETER is followed to each caller's argument at that position, which is the other
      half of the same case — `putPathPrefix(pathPrefixes, …)` receives the map;
    * anything else is terminal, and the frame plus the value id IS the identity. A `new
      LinkedHashMap()` carries no producer edge at all (the value is the `new`, the call is
      the `<init>` made on it), which is why this is keyed on the value rather than on the
      call that made it.

    `seen` stops a cycle. The answer is a SET because a map can arrive from several callers,
    and an entry counts where any origin is shared with an installer — a map reaching the
    installer down one path and the `put` down another is still one map.
    """
    if not isinstance(argument, dict):
        return frozenset()
    source = argument.get("source")
    if source is not None:
        return _from_value(index, method, int(str(source)), seen)
    if argument.get("kind") == _PARAMETER_KIND and argument.get("value") is not None:
        return _from_parameter(index, method, int(str(argument["value"])), seen)
    return frozenset()


def _from_value(
    index: ValueIndex, method: str, value: int, seen: frozenset[tuple[str, int]]
) -> frozenset[tuple[str, int]]:
    here = (method, value)
    if here in seen:
        return frozenset()
    seen = seen | {here}
    found: set[tuple[str, int]] = set()
    for _, callee in index.returns.get(here, ()):
        for _, returned in index.returned_values.get(callee, ()):
            found |= _origins(index, callee, returned, seen)
    # A value nothing deeper explains is its own origin: the frame it lives in and the id the
    # extractor gave it. Two `put`s on one local map agree here; two maps never do.
    return frozenset(found) or frozenset({here})


def _from_parameter(
    index: ValueIndex, method: str, position: int, seen: frozenset[tuple[str, int]]
) -> frozenset[tuple[str, int]]:
    found: set[tuple[str, int]] = set()
    for caller, ordinal in index.callers.get((method, position), ()):
        site = index.sites.get((caller, ordinal))
        arguments = (site or {}).get("arguments") or []
        if position < len(arguments):
            # The walk's own convention (`_Walk._parameter`): parameter N is the argument at
            # the same index of the site that bound it.
            found |= _origins(index, caller, arguments[position], seen)
    return frozenset(found)


def _receiver_origins(index: ValueIndex, site: dict[str, Any]) -> frozenset[tuple[str, int]]:
    """The origin of the object a call was made ON — the map a `put` writes into."""
    receiver = site.get("receiver")
    caller = str(site["caller"])
    if receiver is not None:
        return _from_value(index, caller, int(str(receiver)), frozenset())
    position = site.get("receiver_parameter")
    if position is not None:
        return _from_parameter(index, caller, int(str(position)), frozenset())
    return frozenset()


def _paired(
    workspace: Workspace,
    index: ValueIndex,
    entry_site: dict[str, Any],
    matcher_site: dict[str, Any],
) -> list[tuple[str, str]]:
    """The prefix and the pattern, paired BY PATH rather than by site.

    **Pairing by site is not enough, and this is the measurement that says so.** `ruoyi`'s
    declaration has ONE `put` site, called twice from `buildPathPrefixes` with two different
    `Api` objects, so the prefix resolves to `/admin-api` AND `/app-api` and the pattern to
    `**.controller.admin.**` AND `**.controller.app.**`. Four pairings exist and two of them
    would publish a wrong address at `resolved`.

    `resolve_positions` refuses those two: both values leave through the same context — the
    two `new Api(…)` sites in `WebProperties#<init>`, reached through the walk's sixth edge —
    and a pair that chose differently there is incoherent. Measured 2026-10-18: the crossed
    pairs are refused, the two true ones survive.

    A pair is kept only when both answers are string literals AND the prefix is path-shaped.
    `prefixes.put("${api.ops-prefix}", …)` is a real spelling — `getPathPrefix` passes the key
    through `embeddedValueResolver.resolveStringValue` before using it (`javap -c`, 5.3.39 and
    7.0.9 byte-identical) — and publishing the placeholder verbatim put `${api.ops-prefix}/
    ops/{id}` in `endpoints` and in `roots` on a probe. A prefix nobody has resolved is
    refused here rather than published; what Spring would resolve it to is `resolved_config`'s
    question, and no corpus has asked it yet.
    """
    pairs: list[tuple[str, str]] = []
    for answers in resolve_positions(
        workspace, {_PREFIX: (entry_site, 0), _PATTERN: (matcher_site, 0)}, index
    ):
        prefix, pattern = _text(answers.get(_PREFIX)), _text(answers.get(_PATTERN))
        if prefix and pattern and is_path_shaped(prefix):
            pairs.append((prefix, pattern))
    return pairs


def _text(answer: Answer | None) -> str | None:
    """The string an answer states, or None for everything else — an unresolved reason, an
    expression carrying a hole, a number, or one branch of several literals (`narrowed`,
    ruling 7: a prefix table holds the prefix, and "one of these" is not one)."""
    if answer is None or answer.kind != LITERAL or answer.literal_kind != STRING:
        return None
    if answer.narrowed:
        return None
    value = str(answer.value).strip()
    return value or None


def _declares(site: dict[str, Any], declared: dict[str, Any]) -> bool:
    """Whether `site` calls the `{owners, name}` the model names.

    An entry declaring NO owner matches on the method name alone, which is the loader's third
    case and the one `entry` uses: `put` against whatever type the map variable was declared
    as. Every other symbol in the model names its owner and is matched on both.
    """
    if str(site["name"]) != declared["name"]:
        return False
    return not declared["owners"] or str(site["owner"]) in declared["owners"]


def _matches_a_package(
    index: ValueIndex, site: dict[str, Any], entry: dict[str, Any]
) -> int | None:
    """WHICH PARAMETER of the lambda `site` matches a package name against, or None.

    Read through `produced_by`: the argument names the value it came from, that value's
    producer must be `Package#getName`, and the receiver that call was made on must itself
    come from `Class#getPackage`. Two hops, both of them facts, and neither of them the
    walk — the walk answers what a value IS, and the question here is where it came FROM.

    The parameter is returned rather than a bare yes, because the OTHER conjunct must be
    about the same class: a predicate that matches one class's package while testing another
    class's annotations is not the shape this reads (`_required_annotation`).
    """
    if not _declares(site, entry["matcher"]):
        return None
    arguments = site["arguments"] or []
    if len(arguments) < 2 or not isinstance(arguments[1], dict):
        return None
    caller = str(site["caller"])
    for named in _produced_by(index, caller, arguments[1].get("source"), entry["package_name"]):
        for inner in _produced_by(index, caller, named.get("receiver"), entry["package_of"]):
            about = inner.get("receiver_parameter")
            if about is not None:
                return int(str(about))
    return None


def _required_annotation(
    body: list[dict[str, Any]], about: int, entry: dict[str, Any]
) -> str | None:
    """The annotation the predicate requires of the class at parameter `about`, or None.

    `clazz.isAnnotationPresent(RestController.class)` is the conjunct that says WHICH rows
    the mapping this prefix is installed on actually serves. Reading the package match alone
    prefixed a functional-routing row on a probe — `RouterFunctions.route(GET("/fn/items"))`
    in a class that happened to sit in a prefixed package — and `RouterFunctionMapping` has
    no `pathPrefixes` field at all (`javap`, spring-webmvc 7.0.9), so the published address
    was one the app does not serve.

    A declaration that tests NO annotation contributes nothing: what it means is "every
    handler this mapping serves", and which rows those are is not a question these facts
    answer without naming a framework. That is an under-report with a boundary stated in
    COVERAGE, which is the side of the line this repository stays on.
    """
    for site in body:
        if not _declares(site, entry["annotation_test"]):
            continue
        if site.get("receiver_parameter") is None or int(str(site["receiver_parameter"])) != about:
            # A test about some OTHER class says nothing about the one being matched.
            continue
        arguments = site["arguments"] or []
        named = arguments[0] if arguments and isinstance(arguments[0], dict) else {}
        if named.get("kind") == _CLASS_KIND and isinstance(named.get("symbol"), str):
            return bare_descriptor(str(named["symbol"]))
    return None


def _produced_by(
    index: ValueIndex, caller: str, value: Any, declared: dict[str, Any]
) -> list[dict[str, Any]]:
    """The call sites in `caller` that produced `value` AND call `declared`."""
    if value is None:
        return []
    found = []
    for ordinal in index.producers.get((caller, int(str(value))), ()):
        site = index.sites.get((caller, ordinal))
        if site is not None and _declares(dict(site), declared):
            found.append(dict(site))
    return found


def _for_handler(
    handler: Any, installed: tuple[_Installed, ...], annotated: dict[str, frozenset[str]]
) -> str:
    """The installed prefix a row's HANDLER CLASS takes, or `""`.

    Both halves of the declaration are asked, because the framework asks both: the class
    carries the annotation the predicate tests, and its package matches the pattern. A
    handler whose class does neither takes nothing, which is the common case in a module
    that prefixes one package family — Actuator's own handlers, a framework error controller,
    a functional route.

    A package that SEVERAL prefixes claim takes nothing either: the framework applies the
    first entry of a `LinkedHashMap` and the facts do not record that order, so a prefix is
    refused rather than chosen — `_agreed`'s rule one source over.
    """
    if not installed or not isinstance(handler, str):
        return ""
    package = dotted_package(handler)
    if package is None:
        return ""
    owner = owner_of(bare_descriptor(handler))
    carries = annotated.get(owner, frozenset()) if owner is not None else frozenset()
    matched = {
        one.prefix
        for one in installed
        if one.annotation in carries and _ant_matches(one.pattern, package)
    }
    return matched.pop() if len(matched) == 1 else ""


def _annotated_types(workspace: Workspace) -> dict[str, frozenset[str]]:
    """`bare type -> the annotations it carries ITSELF`, which is what
    `Class#isAnnotationPresent` answers.

    Its own, not a hierarchy or meta-annotation search, and that is mirroring rather than
    laziness: `isAnnotationPresent` reads the class's own declared annotations (plus
    `@Inherited` ones, which `@RestController` and `@Controller` are not), so a
    `@MyRestController` composed from `@RestController` answers FALSE in Spring too. A
    composed read here would prefix rows the framework leaves alone.
    """
    carried: dict[str, set[str]] = {}
    for row in workspace.query("annotations"):
        target = bare_descriptor(str(row["target"]))
        if names_a_type(target):
            carried.setdefault(target, set()).add(bare_descriptor(str(row["annotation"])))
    return {target: frozenset(found) for target, found in carried.items()}


# ---------------------------------------------------------------------------
# Ant matching over a PACKAGE name, `.` as the separator
# ---------------------------------------------------------------------------
#
# Spring reads these patterns with `new AntPathMatcher(".")` — the author's own code above —
# so the separator is the dot and a segment is a package component. `**` is zero or more
# segments, `*` is zero or more characters within one, `?` is exactly one character.
#
# Implemented rather than approximated by a prefix test, because the approximation is wrong
# in a way that publishes wrong addresses: `**.controller.admin.**` must NOT match
# `com.acme.controller.administration.user`, and a `startswith` on the literal part does.
#
# Checked against the real thing: a differential harness ran 14.4 MILLION pattern/name pairs
# against `AntPathMatcher(".")` out of `spring-core-7.0.9.jar` with ZERO disagreements over
# every shape a package name can take. The only divergences found need something a package
# name cannot contain — a `{…}` URI template (where this is strictly narrower), an empty
# segment, a leading or trailing separator — so each is an under-report and none can publish
# a wrong address.


def _ant_matches(pattern: str, name: str) -> bool:
    """Whether the Ant `pattern` matches the dotted `name`."""
    return _segments_match(tuple(pattern.split(".")), tuple(name.split(".") if name else ()))


def _segments_match(pattern: tuple[str, ...], name: tuple[str, ...]) -> bool:
    if not pattern:
        return not name
    head, rest = pattern[0], pattern[1:]
    if head == _ANY_SEGMENTS:
        # Zero or more, so every split is tried. A TRAILING `**` matches the empty remainder,
        # which is Spring's own reading — `a.b.**` matches `a.b` — and the reason
        # `**.controller.admin.**` covers the package it names as well as its children.
        return not rest or any(_segments_match(rest, name[at:]) for at in range(len(name) + 1))
    return bool(name) and _segment_matches(head, name[0]) and _segments_match(rest, name[1:])


def _segment_matches(pattern: str, segment: str) -> bool:
    """One segment against one component: `*` any characters, `?` exactly one, everything
    else literal. Translated here rather than handed to `fnmatch`, which also reads `[…]`
    as a character class — a bracket in a package pattern is a literal to Ant."""
    expression = "".join(
        ".*" if character == "*" else "." if character == "?" else re.escape(character)
        for character in pattern
    )
    return re.fullmatch(expression, segment) is not None


def _per_environment(workspace: Workspace) -> dict[str, dict[str, str | None]]:
    """`resolved_config` as `key -> {environment: value}` — `config_join._config_values`'
    shape, read the same way for the same reason: the whole table is one small answer and
    every lookup here is a membership test against it."""
    values: dict[str, dict[str, str | None]] = {}
    for row in workspace.query("resolved_config"):
        environments = values.setdefault(str(row["key"]), {})
        value = row["value"]
        environments[str(row["environment"])] = None if value is None else str(value)
    return values


def _framework_versions(workspace: Workspace) -> dict[str, str]:
    """`coordinate -> version` from the module fact, which records it already (F1).

    A coordinate absent from the map is a version this analysis could not read, which is a
    different answer from a dependency with no version — so the absence travels to
    `_version_admits` as unanswerable rather than as a refusal.
    """
    import json

    versions: dict[str, str] = {}
    for row in workspace.query("module_dependencies"):
        recorded = row.get("dependency_versions")
        if recorded is None:
            continue
        parsed = json.loads(str(recorded)) if isinstance(recorded, str) else recorded
        if isinstance(parsed, dict):
            versions.update(
                {str(key): str(value) for key, value in parsed.items() if value is not None}
            )
    return versions
