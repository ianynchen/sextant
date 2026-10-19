"""Guard check: does a declining test NOTICE when the guard it names is gone?

**Opt-in, its own command — never part of `scripts/check.sh`'s default run or
of `pytest`** (the `field_check.py` precedent, and for the same reason: its
failures mean something different from an ordinary test failure). Run it with
`scripts/check.sh --guards`, or directly:

    python scripts/guard_check.py                 # every registered guard
    python scripts/guard_check.py <guard id> ...  # one or a few
    python scripts/guard_check.py --list

## The defect this exists to close

`tests/architecture/test_catalog_near_miss_coverage.py` makes GUIDELINES §10's
near-miss rule countable per catalog by reading a marker a developer types:

    @pytest.mark.declines("jakarta-servlet")
    def test_a_class_overriding_service_and_declaring_no_verb_derives_nothing(): ...

That file says so itself — "the marker is a DECLARATION by the test's author,
not a proof". Nothing verified that the marked body discriminates, and a
near-miss can pass because its synthetic input is broken in some UNRELATED way:
the guard it claims to pin is then deletable with the test still green.

Twice now that has shipped. Sweep 1 hand-checked a sample of the marked tests
and found three that do not discriminate. The fix pass correcting those
findings wrote three more — `A-M2`'s servlet `bypassed_by` near-misses, where
deleting the branch (or writing `bypassed_by: []` in both shipped servlet
catalogs) leaves all thirty-nine tests in `test_supertype_dispatch.py` passing.
Under §13.8 that is a second occurrence whose cause violates a principle we had
already written, so the answer is a mechanism rather than a third correction.

## The mechanism, kept deliberately dumb

**One test names one guard; this disables that one guard; the test must fail.**

No mutant generation, no mutation operators, no coverage scoring, no third-party
mutation framework (§7 forbids the dependency in any case). The whole value is
in the single question "does this test notice when its guard is gone?", asked
once per guard against only the tests that name it — a full-suite run per
mutation would take hours for an answer no wider.

- **Guards are named by a second marker**, `@pytest.mark.pins("<guard id>")`,
  sitting beside the `declines` marker the coverage file already reads. A
  second marker rather than an argument on `declines` because the two say
  different things about different subjects — `declines` names the CATALOG
  covered, `pins` names the GUARD measured — and because one test may carry
  nine `declines` markers (`test_call_engines.py`'s claimed-arity near-miss
  does) while still measuring exactly one guard. It is typed deliberately, it
  is greppable, and `tests/architecture/test_guard_pins.py` refuses an id this
  file does not define, so a typo cannot declare coverage of nothing (the §5.3
  failure in miniature). The same guard may legitimately be named by several
  tests; each is measured on its own.

- **Disabling happens in a COPY of the tree, never in place.** `src/`, `tests/`
  and `pyproject.toml` are copied into a temporary directory, the guard's edits
  are applied there, and pytest runs with that directory as its rootdir — so
  the ini's own `pythonpath = ["src"]` and every test that resolves
  `Path(__file__).parents[2] / "src"` reach the mutated copy. The repository is
  read and never written, which is what makes a killed run harmless (NFR-1: no
  mutated state survives, because none was ever created here).

- **Both languages, one mechanism.** A guard is an exact string in a shipped
  file, and it does not matter whether that file is Python, SQL or YAML.
  `derive_endpoints.sql` is read through `Path(__file__).parent` and the
  catalogs through `sextant.resources`, both of which resolve inside the copy,
  so the SQL `WHERE` conjuncts and the catalog conjuncts are disabled exactly
  as an engine's `if` is. There is no SQL gap.

- **A positive control runs first.** Every named test is run against an
  UNMUTATED copy and must pass there. A test that fails in the control is
  reported as unmeasurable rather than counted as discriminating — otherwise a
  test broken by the copy (a missing fixture, say) would look like the strongest
  test in the suite, which is this file's own failure mode.

## What this CANNOT prove

**A test can bite the wrong guard and this will call it correct.** The harness
observes one bit — the test failed when a named edit was applied — and a test
that fails for a reason unrelated to the conjunct its docstring claims is
indistinguishable here from one that fails for the right reason. The naming
requirement is what narrows it: the guard id is chosen by the test's author to
match what the docstring says the near-miss negates, so a mismatch is visible
to a reader even where it is invisible to this file. That narrowing stops being
enough the day a guard id stops describing one conjunct — an id covering two
independent checks would let a test pin either and report both, at which point
the guard must be split rather than the check widened.

It also measures only tests that carry a `pins` marker. That is not a gap this
file can close by itself, and it is not left open either:
`tests/architecture/test_guard_pins.py` refuses a `declines`-marked test that
names no guard, so a near-miss can never reach the suite unmeasured.
"""

from __future__ import annotations

import argparse
import ast
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree

REPO = Path(__file__).resolve().parent.parent
TESTS = REPO / "tests"


@dataclass(frozen=True)
class Edit:
    """One exact-string substitution inside a shipped file.

    `path` is relative to `src/`. `find` must occur exactly `occurrences` times
    in the shipped file — checked by `tests/architecture/test_guard_pins.py`
    before any run, so a guard whose anchor text has been edited away fails as
    a stale registry entry rather than as a test that suddenly discriminates.
    """

    path: str
    find: str
    replace: str
    occurrences: int = 1


@dataclass(frozen=True)
class Guard:
    """A fabrication-prevention check, and the weakening that removes it.

    `what` names the check in one line. `why` states the fabrication it stops —
    what would be published if it were gone — because that is what makes the
    weakening below the RIGHT one: disabling a guard is not deleting a line, it
    is writing the specific mistake the line exists to prevent. A near-miss that
    survives that mistake is not measuring the guard it names.
    """

    what: str
    why: str
    edits: tuple[Edit, ...]


_SINGLE_CALL = "sextant/application/resolve/engines/single_call.py"
_SUPERTYPE_DISPATCH = "sextant/application/resolve/engines/supertype_dispatch.py"
_FLUENT = "sextant/application/resolve/engines/fluent.py"
_COMBINATOR = "sextant/application/resolve/engines/combinator.py"
_DERIVE_ENDPOINTS = "sextant/storage/duckdb/derive_endpoints.sql"
_ANNOTATION_DRIVEN = "sextant/application/resolve/engines/annotation_driven.py"
_ENDPOINTS_DRIVER = "sextant/application/resolve/endpoints.py"
_EFFECTIVE_ANNOTATIONS = "sextant/application/resolve/effective_annotations.py"
_SCHEDULED_WORK = "sextant/application/resolve/engines/scheduled_work.py"
_ERROR_ADVICE = "sextant/application/resolve/engines/error_advice.py"
_PATH_PREFIX = "sextant/application/resolve/path_prefix.py"
_SPRING_BOOT_SERVER_MODEL = "sextant/catalogs/server-models/spring-boot.yml"
_MAVEN = "sextant/ingress/detect/maven.py"
_ARGUMENTS = "sextant/application/resolve/shapes/arguments.py"
_CONTRACTS = "sextant/application/resolve/shapes/contracts.py"
_PROTOCOL_HINT = "sextant/application/resolve/protocol_hint.py"
_DISPATCH = "sextant/application/resolve/dispatch.py"
_ROOTS = "sextant/application/resolve/roots.py"
_PIPELINE = "sextant/application/resolve/pipeline.py"
_CALL_EDGES = "sextant/application/resolve/call_edges.py"
_TRACE = "sextant/application/query/trace.py"
_API = "sextant/api.py"
_DOCUMENT = "sextant/egress/render/document.py"
_VALUES = "sextant/application/resolve/values.py"


GUARDS: dict[str, Guard] = {
    # --- the backward value walk and what it is allowed to answer ----------
    "values.a-construction-hands-nothing-back": Guard(
        what="a call site is read as the CONSTRUCTION of a value only when it produced no "
        "value of its own — a call that hands something back is `produced_by`'s business "
        "and is never read as what the receiver is",
        why='`session.createProducer(session.createQueue("raw-audit"))` holds its '
        "`Session` in a field, so that value has no producer edge and the first call it is "
        "the receiver of is `createQueue` — which an `identified_by` entry names. Without "
        "this conjunct the walk read that as the session's construction and answered "
        "`raw-audit` as what the SESSION is: a queue name published as the identity of a "
        "connection, at `resolved`, where nothing downstream can tell it from an "
        "observation. MEASURED on `orders-service`, which is where it was found. **It "
        'excludes a call that hands something back, which is narrower than "is an '
        'initialiser"** — a VOID ordinary method still passes, and `OI-133` carries that '
        "gap with its own measurement; this guard is the half that is closed",
        edits=(
            Edit(
                path=_VALUES,
                find="        site = self._index.sites.get((method, min(ordinals)))\n"
                '        return None if site is None or site.get("result") is not None '
                "else min(ordinals)",
                replace="        return min(ordinals)",
            ),
        ),
    ),
    "values.an-identity-entry-with-a-role-is-not-an-identity": Guard(
        what="only a ROLE-FREE `identified_by` entry answers what a produced value IS; an "
        "entry carrying a `role` is passed over",
        why="a role says something narrower — argument 0 of `new ProducerRecord(topic, …, "
        "payload)` is the CHANNEL and the last is the PAYLOAD, and the consuming row is "
        "what selects between them. Read as identities, those two entries answer ONE value "
        "twice, and the second answer is a payload slot published as the address of a "
        "destination: a wrong row at `resolved`, which spec §7 names as the one failure this "
        "whole work risks and which a migration diff cannot tell from a right one",
        edits=(
            Edit(
                path=_VALUES,
                # Re-anchored when the matching predicate moved into `_identity_matches`
                # so the two `arg` readers could share it. The mutation is now NARROWER
                # and the guard is stronger for it: the old anchor bundled the role skip
                # with the integer-slot skip, so disabling it removed both and a test
                # could have caught either. This one removes the role skip ALONE.
                find="            if entry.get(_ROLE) is not None:",
                replace="            if False:  # guard disabled by scripts/guard_check.py",
            ),
        ),
    ),
    "values.an-enumerating-identity-is-not-preserved-through-a-receiver": Guard(
        what="a `from_receiver` identity hands on its receiver's answer only where the "
        "receiver resolved to EXACTLY ONE; several answers are refused",
        why="an `identified_by` entry is read by every catalog at once, over every call in "
        "the estate, so the entry on element access (`java.util.List#get`) meets topic "
        "lists as well as a discovery lookup's instances. A single-valued identity "
        "propagates correctly — an element of a collection identified as ONE thing is that "
        'thing, and `Collections.singletonList("x").get(0)` IS `x`. An ENUMERATING one '
        'must not: `List.of("orders", "audit").get(0)` would answer both topics for one '
        "element, publishing every topic as the address of one call — a wrong row at "
        "`resolved`, which spec 2026-09-22 §7 names as the one failure this work risks. "
        "Weakening the count to `< 1` or dropping the check entirely is a one-word edit "
        "that no migration diff distinguishes from a right answer, and MEASURED over the "
        "shipped table all three enumerating entries are topic lists",
        edits=(
            Edit(
                path=_VALUES,
                # Two lines, because `_joined` carries the SAME count check for its own
                # operands and a one-line anchor matched both. Anchoring on the refusal
                # too keeps the mutation to this arm, which is what the guard is about.
                find="        if len(reached) != 1:\n"
                "            return _only(trail, _unresolved(NOT_READABLE))",
                replace="        if False:  # guard disabled by scripts/guard_check.py\n"
                "            return _only(trail, _unresolved(NOT_READABLE))",
            ),
        ),
    ),
    "arguments.only-a-string-literal-is-a-destination": Guard(
        what="a walk answer becomes a channel only when it is a `string` literal — a "
        "`symbol`, an `expression` and an `absent` each read as unresolved",
        why="the walk carries a declaration reference as a `symbol` literal (spec ruling "
        "T-3) precisely so a consumer can tell it from text. A channel reader that tested "
        "the answer KIND alone would write `com/acme/OrderWorker#` into `path` and publish a "
        "symbol as an address at `resolved`/`compiler`, where nothing downstream can tell it "
        "from an observation. The same one-word weakening admits an `int` and a `bool` "
        "literal as destinations, which `channel_of` has refused since it was written",
        edits=(
            Edit(
                path=_ARGUMENTS,
                find="    if answer is None or answer.kind != LITERAL or answer.literal_kind != STRING:",
                replace="    if answer is None or answer.kind != LITERAL:",
            ),
        ),
    ),
    "values.a-hole-is-NAMED-after-the-value-that-fills-it": Guard(
        what="a hole the walk could not fill prints the NAME of the parameter that fills it "
        "at runtime, where the facts name one",
        why="ruled by the user on 2026-10-18, one position over from `<host>`: a bare `{}` "
        'says *something here* about a value the signature names. `"/owners/" + ownerId + '
        '"/pets"` is the most ordinary outbound address there is, and `/owners/{}/pets` '
        "cannot be compared with the SERVER's own row for the same route, which is "
        "`/owners/{ownerId}/pets` — the two sides of one call read as different addresses. "
        "A hole with no name to take (a call's result) still prints `{}`, which is why this "
        "guard disables the NAMING rather than the hole",
        edits=(
            Edit(
                path=_VALUES,
                find='        if operand.get("kind") != _PARAMETER or operand.get("value") is None:\n'
                "            return _HOLE",
                replace="        if True:  # guard disabled by scripts/guard_check.py\n"
                "            return _HOLE",
            ),
        ),
    ),
    "arguments.a-template-with-no-read-text-is-not-partly-known": Guard(
        what="an assembled address publishes at `partial` only where text survives "
        "removing its holes — `{}{}` carries nothing the code states and stays unresolved",
        why="this is the one false positive the partly-known-address work can produce, and "
        "it was MEASURED rather than imagined: the first run of spec 2026-10-18 published "
        "Apollo's `parseHost(service) + path` as a partly-known address whose path is "
        "`{}{}`. That row claims part of the address was read when nothing was, in the one "
        "column a reader uses to decide whether an endpoint is known. Dropping the clause "
        "is a few characters and every other partly-known row keeps working, so no "
        "migration diff separates it from a right answer",
        edits=(
            Edit(
                path=_ARGUMENTS,
                find='    if argument.get("kind") == EXPRESSION and _holes(text) and _without_holes(text):',
                replace='    if argument.get("kind") == EXPRESSION and _holes(text):',
            ),
        ),
    ),
    "arguments.an-authority-holding-a-hole-is-not-a-peer": Guard(
        what="a partly-known address yields a peer only where the authority it would come "
        "from carries neither a hole nor a `${…}` placeholder",
        why="`split_url` answers an authority for anything matching `//host/path`, and a "
        "template is written scheme-relative exactly when its authority half came from a "
        "value (`OI-142`, ruling 2). Without the refusal, `//{}/owners` publishes `{}` in "
        "the `peer` column — a hostname no environment ever named, joined against by the "
        "per-environment peer resolution as though it were one. The placeholder half is "
        "`carries_expression`'s own long-standing rule in one more notation",
        edits=(
            Edit(
                path=_ARGUMENTS,
                find="        if peer is not None and (_holes(peer) or carries_expression(peer)):\n"
                "            peer = None",
                replace="        if False:  # guard disabled by scripts/guard_check.py\n"
                "            peer = None",
            ),
        ),
    ),
    "maven.a-climb-stops-at-the-aggregator-that-contains-this-module": Guard(
        what="the reactor walk climbs to an ancestor only where that ancestor declares "
        "`<modules>` AND its directory contains the module being analysed",
        why="a reactor root commonly inherits from a pom that is not its aggregator — "
        "`macrozheng/mall`'s root declares `spring-boot-starter-parent` with an empty "
        "`<relativePath/>`, which `_parent_pom` resolves out of the local repository. "
        "Without the containment half the climb replaced the real root with a directory "
        "inside `~/.m2`, found no siblings at all, and `mall-admin` fell from 629 shape "
        "fields to 73 — EVERY wire contract that module publishes, gone, with no error "
        "and no gap line. It was caught by a field pin rather than by the suite, which is "
        "precisely the kind of silent reduction a guard is for",
        edits=(
            Edit(
                path=_MAVEN,
                find='            if up_pom.find("m:modules", _POM_NS) is None or not module_dir.is_relative_to(\n'
                "                up_path.parent.resolve()\n"
                "            ):\n"
                "                break",
                replace="            if False:  # guard disabled by scripts/guard_check.py\n"
                "                break",
            ),
        ),
    ),
    "path_prefix.a-version-outside-the-measured-range-takes-no-prefix": Guard(
        what="a server-model entry applies only where the module's framework version is "
        "inside the range that entry was MEASURED on",
        why="the version is in the table because the key name rots: Boot 1 reads "
        "`server.context-path` where Boot 2+ reads `server.servlet.context-path`, and CP-38 "
        "measured only 2.7.18, 3.5.14 and 4.1.1. With the range check gone, a Boot 1 module "
        "would have the Boot 2 key applied to it and a 4.x reactive module would take a "
        "`spring.webflux.base-path` row that no jar in any local repository could confirm — "
        "in both cases a prefix asserted from a measurement that does not cover the module, "
        "on EVERY inbound row it has. Returning True unconditionally is a one-line edit and "
        "every corpus in the estate keeps passing, because all of them are in range",
        edits=(
            Edit(
                path=_PATH_PREFIX,
                find="    if not found:\n        return True\n    return any(",
                replace="    if not found:\n        return True\n    return True or any(",
            ),
        ),
    ),
    "path_prefix.a-prefix-pairs-with-the-pattern-on-ITS-OWN-path": Guard(
        what="an installed prefix and the package pattern it applies to are resolved "
        "TOGETHER, so a pair that chose differently on the way out is refused",
        why="`ruoyi` declares every prefix at ONE `put` site — `putPathPrefix`, called once "
        "per API group — so the walk answers `/admin-api` AND `/app-api` there, and both "
        "patterns beside them. Pairing by site is a cross product: two of the four pairings "
        "are wrong and each would prefix a whole package family with another family's "
        "prefix, at `resolved`, on every row that package serves. The pairs are separated by "
        "the path alone (the two `new Api(…)` sites they leave through), which is exactly "
        "what a per-site pairing cannot see",
        edits=(
            Edit(
                path=_PATH_PREFIX,
                find="    for answers in resolve_positions(\n"
                "        workspace, {_PREFIX: (entry_site, 0), _PATTERN: (matcher_site, 0)}, index\n"
                "    ):\n"
                "        prefix, pattern = _text(answers.get(_PREFIX)), _text(answers.get(_PATTERN))\n"
                "        if prefix and pattern and is_path_shaped(prefix):\n"
                "            pairs.append((prefix, pattern))",
                replace="    # guard disabled by scripts/guard_check.py: paired by SITE\n"
                "    prefixes = [\n"
                "        _text(answers.get(_PREFIX))\n"
                "        for answers in resolve_positions(workspace, {_PREFIX: (entry_site, 0)}, index)\n"
                "    ]\n"
                "    patterns = [\n"
                "        _text(answers.get(_PATTERN))\n"
                "        for answers in resolve_positions(workspace, {_PATTERN: (matcher_site, 0)}, index)\n"
                "    ]\n"
                "    for prefix in prefixes:\n"
                "        for pattern in patterns:\n"
                "            if prefix and pattern and is_path_shaped(prefix):\n"
                "                pairs.append((prefix, pattern))",
            ),
        ),
    ),
    "path_prefix.a-pattern-segment-matches-a-WHOLE-segment": Guard(
        what="an Ant pattern segment matches a package component end to end, never a prefix of one",
        why="`**.controller.admin.**` must not match `com.acme.controller.administration."
        "user`, and a prefix test says it does. The consequence is not a missing row but a "
        "wrong one: every endpoint in a package that merely STARTS with the named component "
        "is published under an address the server does not serve it at. The fixture's four "
        "packages all match their own pattern exactly, so no e2e row moves — this is the "
        "case only a near-miss can state",
        edits=(
            Edit(
                path=_PATH_PREFIX,
                find="    return re.fullmatch(expression, segment) is not None",
                replace="    return re.match(expression, segment) is not None  # guard disabled",
            ),
        ),
    ),
    "path_prefix.a-package-predicate-is-what-identifies-a-declaration": Guard(
        what="a `Map#put` entry is read as a prefix declaration only where its lambda "
        "matches the pattern against a CLASS'S PACKAGE NAME — `Package#getName` on "
        "`Class#getPackage`",
        why="that pair of facts is the whole discriminator. A module has other maps of "
        "strings to predicates and other `match` calls; without the check, any two-argument "
        "`match` inside any lambda handed to any `put` is read as a prefix rule, and its "
        "first argument becomes an address prefix applied to real endpoints. The shipped "
        "fixtures declare nothing but genuine prefix maps, so no e2e row can tell the "
        "difference",
        edits=(
            Edit(
                path=_PATH_PREFIX,
                find='    arguments = site["arguments"] or []\n'
                "    if len(arguments) < 2 or not isinstance(arguments[1], dict):\n"
                "        return None\n"
                '    caller = str(site["caller"])',
                replace="    return 0  # guard disabled by scripts/guard_check.py",
            ),
        ),
    ),
    "path_prefix.an-entry-belongs-to-the-map-the-installer-RECEIVES": Guard(
        what="a `put` is read as a prefix entry only where the map it writes into is the map "
        "an installer was handed, compared by the object's origin",
        why="**this is the whole difference between reading a declaration and guessing at "
        "one.** Every other test a prefix entry passes — a string key, a lambda, a package "
        "match — is passed just as well by any other map of classes to predicates, and a "
        "module that installs prefixes anywhere has such maps: measured, an `auditCategories` "
        "map handed to NOBODY published `GET /AUDIT/audit-logs/{id}` at `resolved`, an "
        "address the app does not serve, and the wrong path propagated into `roots`. Dropping "
        "the join is a one-line edit and every row the shipped fixture expects still derives",
        edits=(
            Edit(
                path=_PATH_PREFIX,
                find="        if not (_receiver_origins(index, site) & carries):\n"
                "            continue",
                replace="        if False:  # guard disabled by scripts/guard_check.py\n"
                "            continue",
            ),
        ),
    ),
    "path_prefix.a-prefix-reaches-only-the-classes-the-predicate-ADMITS": Guard(
        what="an installed prefix moves a row only where the handler's class carries the "
        "annotation the predicate tests, not merely because its package matches",
        why="the predicate has two conjuncts and the framework asks both — "
        "`clazz.isAnnotationPresent(RestController.class) && matcher.match(…)`. Reading the "
        "package alone prefixes rows the mapping does not serve: measured, a "
        '`RouterFunctions.route(GET("/fn/items"), …)` bean that merely SITS in a prefixed '
        "package was published at `/admin-api/fn/items`, while `javap` shows "
        "`RouterFunctionMapping` has no `pathPrefixes` field at all. An annotation test is "
        "also how a module says which of its own classes are handlers, so without it every "
        "config class, entity and helper in a prefixed package is a candidate",
        edits=(
            Edit(
                path=_PATH_PREFIX,
                find="        if one.annotation in carries and _ant_matches(one.pattern, package)",
                replace="        if _ant_matches(one.pattern, package)  # guard disabled",
            ),
        ),
    ),
    "path_prefix.an-UNRESOLVED-prefix-is-refused": Guard(
        what="a prefix that is not path-shaped — a `${…}` placeholder — is refused rather "
        "than published verbatim",
        why='`prefixes.put("${api.ext-prefix}", …)` is an ordinary spelling, and Spring '
        "passes the key through `embeddedValueResolver.resolveStringValue` before using it "
        "(`javap -c`, byte-identical at 5.3.39 and 7.0.9). Published verbatim it put "
        "`${api.ext-prefix}/ext/{id}` into `endpoints` AND into `roots` — a path that is not "
        "even path-shaped, which every downstream reader then carries",
        edits=(
            Edit(
                path=_PATH_PREFIX,
                find="        if prefix and pattern and is_path_shaped(prefix):",
                replace="        if prefix and pattern:  # guard disabled",
            ),
        ),
    ),
    "path_prefix.a-SUBCLASS-of-the-mapping-installs-prefixes-too": Guard(
        what="the installer gate accepts a call on a subclass of the framework's mapping, "
        "resolved through the module's own type hierarchy",
        why="`class MyMapping extends RequestMappingHandlerMapping` is ordinary Spring "
        "customisation, and javac emits `invokevirtual MyMapping.setPathPrefixes`, so an "
        "exact-owner gate reads such a module as installing nothing — measured, its admin "
        "controller published `/orders/{id}` where the app serves `/admin-api/orders/{id}`. "
        "That is the collapse this whole item exists to fix, reappearing one subclass away",
        edits=(
            Edit(
                path=_PATH_PREFIX,
                find='    found = [site for site in named if str(site["owner"]) in owners]\n'
                "    if len(found) == len(named):\n"
                "        return found",
                replace='    found = [site for site in named if str(site["owner"]) in owners]\n'
                "    if True:  # guard disabled by scripts/guard_check.py\n"
                "        return found",
            ),
        ),
    ),
    "path_prefix.the-ENTRY-is-not-matched-on-the-maps-static-type": Guard(
        what="a prefix entry is found whatever type the map VARIABLE was declared as — the "
        "model declares the method name and no owner",
        why="javac emits `put` against the declared type: `Map<…> prefixes` gives "
        "`java/util/Map#put` and `LinkedHashMap<…> prefixes` gives "
        "`java/util/LinkedHashMap#put`, and both are ordinary Java. Requiring the interface "
        "silently loses every module written the other way — measured, the fixture's own "
        "`/admin-api`, `/app-api` and `${…}` entries all disappear with the owner put back, "
        "and the identity join is what identifies the entry instead",
        edits=(
            Edit(
                path=_SPRING_BOOT_SERVER_MODEL,
                find="  entry:\n    method: put",
                replace="  entry:\n    type: java.util.Map\n    method: put",
            ),
        ),
    ),
    "values.a-lambda-body-reaches-the-values-it-CAPTURED": Guard(
        what="a lambda body's leading parameters resolve through the site that CAPTURED "
        "them, so a value closed over is read rather than answered `external`",
        why="this is the walk's seventh edge. A lambda body is a synthetic method and the "
        "values it closed over arrive as its first parameters; nothing in the "
        "`bound_to_parameter` facts binds those, so before this the walk answered "
        "`external` — *the values come from outside what was scanned* — about a literal in "
        "the same method. Measured, a prefix declaration holding its pattern as a captured "
        "`String` parameter resolved nothing and two controllers differing only by their "
        "prefix collapsed onto ONE published path, which is `OI-148`'s own symptom. Removing "
        "the pass is three lines and no other fixture notices, because every other lambda in "
        "the estate either captures nothing a catalog asks about or captures an OBJECT whose "
        "values the field and `<init>` edges reach instead",
        edits=(
            Edit(
                path=_VALUES,
                find="    for (method, _), site in sites.items():\n"
                '        for captured in _captures(site["arguments"]):',
                replace="    for (method, _), site in sites.items():\n"
                "        for captured in ():  # guard disabled by scripts/guard_check.py",
            ),
        ),
    ),
    "values.a-binding-written-from-a-CONSTANT-answers-that-constant": Guard(
        what="a field written from a constant resolves to that constant, with no crossing — "
        "the value is in the fact",
        why='`private String hostname = "http://visits-service/"` compiles to `ALOAD 0; '
        "LDC; PUTFIELD`, which names no parameter, so `field_writes` emitted nothing for it "
        "and the walk answered `no_writer` about a literal one line above the read. Measured "
        "on `spring-petclinic-microservices`: an outbound host held that way left "
        '`hostname + "pets/visits?petId={petId}"` with one unfillable hole and the row '
        "published no address at all, while its four siblings resolved. Dropping the arm "
        "leaves the sixth edge working, so no other fixture notices",
        edits=(
            Edit(
                path=_VALUES,
                find="        for entry in constants:",
                replace="        for entry in ():  # guard disabled by scripts/guard_check.py",
            ),
        ),
    ),
    "values.a-write-a-PRIVATE-uncalled-method-makes-is-not-a-value": Guard(
        what="a constant write by a `private` method nothing calls contributes no value — "
        "private is unreachable from outside its class, so an uncalled one cannot run",
        why="the parameter arm gets this for free (crossing to a writer's callers finds none "
        "and answers `external`) and the constant arm has to ask, because it needs no "
        "crossing. Without the test, `private void switchToBackup() { this.topic = "
        '"backup"; }` — called by nothing — published `backup` as a `resolved` outbound '
        "destination: a value the code cannot produce, which §8 rates the worst answer "
        "available. A PUBLIC uncalled method is deliberately still reported: something "
        "unscanned calls it, which is a different statement",
        edits=(
            Edit(
                path=_VALUES,
                find="    dead = private - called",
                replace="    dead = frozenset()  # guard disabled by scripts/guard_check.py",
            ),
        ),
    ),
    "values.an-UNREADABLE-constant-answers-not_readable-never-nothing": Guard(
        what="a constant entry the walk has no literal kind for answers `not_readable`, so "
        "the binding still has an answer",
        why="contributing nothing made `_binding` return an EMPTY tuple where there was no "
        "other writer, and `resolve_site` reads that as "
        "*no path answers every slot* — it drops EVERY SLOT of the call site. Measured on "
        "real bytecode: `getForObject(url, responseType)` lost its ADDRESS, which the sixth "
        "edge had resolved, because the field beside it held `Order.class`. The trigger is "
        "`private Class<X> t = X.class`, ordinary code, and the loss is silent",
        edits=(
            Edit(
                path=_VALUES,
                find="            else:\n"
                "                reached.append((trail, _unresolved(NOT_READABLE)))",
                replace="            elif False:  # guard disabled by scripts/guard_check.py\n"
                "                reached.append((trail, _unresolved(NOT_READABLE)))",
            ),
        ),
    ),
    "values.a-field-read-reaches-the-value-written-into-it": Guard(
        what="a binding read resolves through the WRITER the facts name — `written_by` — "
        "crossing into that method rather than stopping at the field",
        why="this is the walk's sixth edge, and without it a destination held in a field "
        "publishes no address at all: measured, `kafkaTemplate.send(topic, payload)` with "
        "`topic` assigned by the constructor derived ONE row with `path` NULL where the two "
        "constructions name `orders-v2` and `orders-audit`. Returning `no_writer` "
        "unconditionally is what the method did for a year and every other test in the suite "
        "passes with it back, because no other fixture holds a destination in a field — so "
        "the suite cannot tell the edge from its absence without this guard",
        edits=(
            Edit(
                path=_VALUES,
                find="        for method, index in written:\n"
                "            reached.extend(self._resolve((_PARAMETER, method, index), trail, frames))",
                replace="        for method, index in ():  # guard disabled by guard_check.py\n"
                "            reached.extend(self._resolve((_PARAMETER, method, index), trail, frames))",
            ),
        ),
    ),
    # --- shared argument readers ------------------------------------------
    "arguments.elements-are-an-array-kinds-own": Guard(
        what="an `elements` list is read off an `array`-kind argument and nothing else — "
        "every other argument is read as the value it is",
        why="the `array` kind is the extractor's own claim that it read the whole array end "
        "to end (capability 9.15's five rejection rules); an array it could not read stays "
        "`unresolved` and carries no `elements` at all. Reading an element list off any "
        "other slot asserts a completeness nobody measured — and, since a slot that is not "
        "an array has no elements to find, it turns every destination a compiler wrote down "
        "into an empty expansion: `unresolved`, silently, on every shipped messaging catalog "
        "and every media predicate at once",
        edits=(
            Edit(
                path=_ARGUMENTS,
                find='    if argument is None or argument.get("kind") != "array":',
                replace="    if argument is None:  # guard disabled by scripts/guard_check.py",
            ),
        ),
    ),
    # --- `single_call` -----------------------------------------------------
    "single_call.claimed-arity": Guard(
        what="once any candidate row declares a `descriptor`, that arity is CLAIMED and "
        "a call whose own descriptor matches none of them falls through to NO row",
        why="falling through to a descriptor-less sibling reads this overload's argument 0 "
        "as whatever that sibling declares — the live defect that published a message "
        "PAYLOAD as an AMQP destination, a JMS destination and a SOAP service address",
        edits=(
            Edit(
                path=_SINGLE_CALL,
                find="    if any(_DESCRIPTOR in row for row in candidates):",
                replace="    if False:  # guard disabled by scripts/guard_check.py",
            ),
        ),
    ),
    "single_call.call-site-owner": Guard(
        what="a call site matches only when its receiver's type is the `owner` the catalog "
        "declares",
        why="`convertAndSend` is not a name Spring AMQP owns — without the owner conjunct an "
        "application class's own method publishes an AMQP destination at "
        "`resolved`/`compiler`, and every JMS publication doubles",
        edits=(
            Edit(
                path=_SINGLE_CALL,
                # W9 widened this from one owner to the alternates a catalog may
                # name (§3.1) — the class and the interface a codebase declares its
                # field as. Still one conjunct, still the same guard: the receiver's
                # type must be one the catalog names, rather than any type at all.
                # A (`docs/performance.md`) turned the per-site test into a read of
                # the owners' own positions in the shared `CallSiteIndex`; the guard
                # is the same, and disabling it reads every position instead.
                find="            index.positions_by_owner.get(owner, []) for owner in "
                "dict.fromkeys(owners)",
                replace="            range(len(call_sites)) for _ in [None]"
                "  # guard disabled by scripts/guard_check.py",
            ),
        ),
    ),
    "single_call.lambda-step-is-the-declared-method": Guard(
        what="a position read INSIDE a builder lambda comes from the builder method the "
        "catalog names — `queue(arg0)` — and never from whichever call in the body "
        "happened to carry a literal",
        why="`OI-74`. The lambda is one argument of one call, which is what makes reading "
        "its body reading rather than guessing; the NAME is what keeps it so. "
        "`SqsSendOptions` declares seven methods and four of them take a string, so a "
        "reader that took the first literal in the body would publish a trace header or a "
        "message group id as an SQS QUEUE — at `resolved`/`compiler`, where nothing "
        "downstream can tell it from an observation, and DR-5 would link it against "
        "endpoints this module never speaks to",
        edits=(
            Edit(
                path=_SINGLE_CALL,
                find='        if (step := steps.get(str(site["name"]))) is not None',
                replace='        if (step := steps.get(str(site["name"]), next(iter(steps.values()))))'
                " is not None  # guard disabled",
            ),
        ),
    ),
    "single_call.lambda-step-owner-is-the-declared-type": Guard(
        what="a call inside a builder lambda is read only where its OWNER is the type the "
        "step declares — the builder itself, never another object the body happens to touch",
        why="W57's review measured this one: with the name alone as the conjunct, a body "
        'containing `metricsRecorder.queue("internal-metrics")` beside `to.payload(event)` '
        "published `internal-metrics` as this module's SQS QUEUE, at `resolved`/`compiler`. "
        "A lambda body is ordinary code and touches whatever it likes; what makes reading it "
        "reading rather than guessing is that every conjunct of the step holds, and the type "
        "the call is made ON is one of them",
        edits=(
            Edit(
                path=_SINGLE_CALL,
                find='        and str(site["owner"]) in step["owners"]',
                replace="        and True  # guard disabled by scripts/guard_check.py",
            ),
        ),
    ),
    # --- `fluent` ----------------------------------------------------------
    "fluent.root-is-a-declared-request-starter": Guard(
        what="a chain roots only on an owner AND method pair the catalog declares",
        why="rooting on any nullary call on the owner mints a request for a method the "
        "framework does not declare — `WebClient` has no `trace()`, and a row derived "
        "there is an outbound call nothing makes",
        edits=(
            Edit(
                path=_FLUENT,
                find='            and site["name"] == root["method"]\n',
                replace="            and True  # guard disabled by scripts/guard_check.py\n",
            ),
        ),
    ),
    "fluent.root-owner-is-the-declared-type": Guard(
        what="a chain roots only on a call whose OWNER is one the root declares — the "
        "other half of the pair above",
        why="rooting on a method name (and parameter types) alone would start a chain on "
        "any type that happens to declare the same member: a module's own helper named "
        "`messageDrivenChannelAdapter`, or the framework's polled `PubSubMessageSource` "
        "beside its `PubSubInboundChannelAdapter` — same `(operations, String)` "
        "constructor, a different registration — would publish a destination at "
        "`resolved`/`compiler` on evidence about a type the catalog never read",
        edits=(
            Edit(
                path=_FLUENT,
                find='            if site["owner"] in root["owners"]\n',
                replace="            if True  # guard disabled by scripts/guard_check.py\n",
            ),
        ),
    ),
    "fluent.a-built-request-is-not-an-issued-one": Guard(
        what="a `terminal_via_argument` terminal counts only where the value it produced is "
        "actually handed to the executing call — `build()`'s own `result` appearing as the "
        "`source` of an argument to `newCall`/`send`",
        why="a request BUILT and never issued is not a call anyone makes. OkHttp and the "
        "AWS SDK both split construction from execution, so `build()` is reached on every "
        "abandoned builder in a codebase; counting it as a terminal publishes an outbound "
        "boundary for a request that was assembled and dropped — at `resolved`/`compiler`, "
        "where nothing downstream can tell it from one the module really issues",
        edits=(
            Edit(
                path=_FLUENT,
                find="        and _has_execute_join(site, context.sites, "
                "context.via_argument_names[name])",
                replace="        and True  # guard disabled by scripts/guard_check.py",
            ),
        ),
    ),
    "fluent.no-terminal-no-row": Guard(
        what="a chain derives a row only where it REACHED a terminal — a builder that was "
        "constructed, configured and never executed derives nothing",
        why="D02 §4 states it and four `fluent.*` guards measured everything around it, so the "
        "one rule `vertx-eventbus-chain.yml` exists FOR was the one nothing pinned. "
        "MEASURED (CP-31 Q4, vertx-core 4.5.10 and 5.0.0, byte-identical): "
        "`EventBusImpl.consumer(String, Handler)` calls `consumer(String)` at offset 9 and "
        "`MessageConsumer.handler` at offset 15, so registration lives in `handler` and a "
        "`MessageConsumer` built but never handed one receives NO MESSAGE. Without this "
        "conjunct every `bus.consumer(addr)` in a codebase — including the ones a method "
        "builds and abandons — publishes an inbound endpoint at `resolved`/`compiler`, "
        "which is a served endpoint nothing serves. The same edit weakens every fluent "
        "catalog's terminal; this id is named for the near-miss that pins it",
        edits=(
            Edit(
                path=_FLUENT,
                find="    elif reached_terminal:\n        _derive(captures, context)",
                replace="    elif True:  # guard disabled by scripts/guard_check.py\n"
                "        _derive(captures, context)",
            ),
        ),
    ),
    "fluent.url-via-follows-only-a-declared-call": Guard(
        what="a `url_via` (or `channel_via`) form follows the argument's linked call only "
        "where that call's OWNER is the one the form declares — `URI.create`, never any "
        "`create` the value happens to come from",
        why="the ladder is the one place an address is read off a call OTHER than the one "
        "the catalog matched, and the owner is what vouches for that call; without it a "
        '`uri(Urls.create("…"))` on a helper the catalog knows nothing about publishes '
        "that helper's argument as the request's address at `resolved`/`compiler` — a "
        "resolved address on evidence about a different type. The anchor is the shared "
        "reader (`shapes/arguments.py`), so the same edit weakens `channel_via`; this id "
        "is named for the capture whose near-miss pins it",
        edits=(
            Edit(
                # **Re-anchored in Task 9, because the rule moved rather than
                # weakened.** It used to live in `_linked_constructor`'s owner
                # comparison, which every consuming engine reached through
                # `linked_channels`. All four call sites now resolve through the walk
                # — `single_call`'s channel ladder (Task 8) and `fluent`'s three
                # (Task 9) — so that comparison has no caller outside its own module
                # and the mutation became unobservable: the guard SURVIVED, which is
                # how this was noticed. What refuses `Urls.create` for a form naming
                # `java.net.URI` now is `_identity_matches`' own owner check, so the
                # guard follows the enforcement.
                path=_VALUES,
                find='            if owner is not None and row["owner"] != owner:\n',
                replace="            if False:  # guard disabled by scripts/guard_check.py\n",
            ),
        ),
    ),
    # --- `combinator` -------------------------------------------------------
    "combinator.unrecognised-overload-is-a-row": Guard(
        what="a call the vocabulary names but no overload rule accepts derives one unresolved row",
        why="the alternative is silence — the G-13 failure this engine's doctrine forbids: "
        "a router whose verb call happens to be an overload the catalog did not declare "
        "has its whole route absent from the export with nothing saying so",
        edits=(
            Edit(
                path=_COMBINATOR,
                find="        if verb is None:\n            # Spec §3, the G-13 guard",
                replace="        if verb is None and False:  # guard disabled by scripts/guard_check.py\n            # Spec §3, the G-13 guard",
            ),
        ),
    ),
    "combinator.media-with-a-handler-is-a-row": Guard(
        what="a media call handed a `lambda`-kind argument — the route-declaring overload "
        "of a media-contributing name; composers are excluded, no measured `and`/`or` "
        "carries a handler — derives one unresolved row",
        why="without it the call is claimed into the tree (its name is in the media "
        "vocabulary) and contributes nothing: a Kotlin DSL's `accept(JSON) { handler }` "
        "is a declared route absent from the export with nothing saying so — spec §3's "
        "G-13 failure, on a name the catalog does read",
        edits=(
            Edit(
                path=_COMBINATOR,
                find="        if _carries_a_handler(site):\n            return [_Route(poisons=_IDENTITY_POISON)]",
                replace="        if False:  # guard disabled by scripts/guard_check.py\n            return [_Route(poisons=_IDENTITY_POISON)]",
            ),
        ),
    ),
    "combinator.linked-body-never-roots": Guard(
        what="a method some linking call names as its body — a `body_arg`, a nest-shaped "
        "continuation's `subtree_arg` — is skipped by the root scan whole",
        why="without the skip a body holding a chain of its own roots it: a Supplier body's "
        '`route().GET("/x", h).build()` under `path("/api", …)` publishes `GET /api/x` '
        "from the prefix's fold AND a bare `GET /x` with the compiler-generated lambda as "
        "its declarer — the same route twice, the second at an address the framework "
        "never serves",
        edits=(
            Edit(
                path=_COMBINATOR,
                find="        if bare_descriptor(caller) in context.linked_bodies:",
                replace="        if False:  # guard disabled by scripts/guard_check.py",
            ),
        ),
    ),
    "combinator.origin-is-declared": Guard(
        what="a chain head contributes zero routes without poisoning ONLY when its producing "
        "call is a declared origin",
        why="without the check a helper's result — `base().POST(…)`, the one receiver the "
        "walk reaches but cannot read — would read as a clean chain start, and a router "
        "whose head the walk cannot see would publish every route to its right as resolved "
        "with nothing saying the head was not read",
        edits=(
            Edit(
                path=_COMBINATOR,
                find="    if extended is not None and _matching_rule(extended, scope.context.origins) is not None:",
                replace="    if extended is not None and not _routes_of(extended, scope):  # guard disabled by scripts/guard_check.py",
            ),
        ),
    ),
    "combinator.origin-parameter-is-the-chains-head": Guard(
        what="inside a body whose linking rule declares `origin_param`, a chain's head is "
        "clean only when it sits on the body's parameter `captures + k` — the one the "
        "framework handed the block",
        why="without the comparison every head with no producing call reads as the origin: "
        "a route registered on a field's builder, on another parameter, or on a value the "
        "extractor could not follow is published under this body's prefix as resolved, "
        "the fixed-index design's wrong row with nothing saying the receiver was not read",
        edits=(
            Edit(
                path=_COMBINATOR,
                find='    if site["receiver"] is None and site.get("receiver_parameter") == origin:',
                replace='    if site["receiver"] is None and True:  # guard disabled by scripts/guard_check.py',
            ),
        ),
    ),
    "combinator.receiver-arg-is-the-origin": Guard(
        what="a rule naming `receiver_arg` reads its route only when that argument is the "
        "enclosing body's origin parameter",
        why="without the comparison any parameter at that position passes: "
        '`get(someOtherRoute, "/x")` inside `route("/api") { }` is published as '
        "`GET /api/x`, an address the framework never serves, resolved",
        edits=(
            Edit(
                path=_COMBINATOR,
                find='        and argument.get("value") == scope.origin_parameter',
                replace="        and True  # guard disabled by scripts/guard_check.py",
            ),
        ),
    ),
    "combinator.helper-follows-the-origin-only": Guard(
        what="inside a body with an origin, a module-local helper call is followed only when "
        "the origin flows into it as an argument, and that argument's position is the "
        "callee's origin",
        why="without the check every module-local call in a routing body is followed with "
        "no origin at all, and a verb inside the callee on a builder this body never "
        "touched — a field's, another parameter's — is published under this body's prefix "
        "or as an unresolved row where spec 2026-09-19 §4a says silence",
        edits=(
            Edit(
                path=_COMBINATOR,
                find="        if origin is None:\n            return []\n    elif not scope.follow_all:",
                replace="        if False:  # guard disabled by scripts/guard_check.py\n            return []\n    elif not scope.follow_all:",
            ),
        ),
    ),
    "combinator.origin-less-following-is-opt-in": Guard(
        what="a body with no origin follows module-local calls only where its linking rule "
        "declared `follow_calls: all`",
        why="without the opt-in every origin-less body follows every helper it calls — a "
        "`Supplier<RouterFunction>` body's helper may build routers nobody returns, and "
        "following it attaches routes the framework never registered (spec 2026-09-19 "
        "§0b A1)",
        edits=(
            Edit(
                path=_COMBINATOR,
                find="    elif not scope.follow_all:\n        return []",
                replace="    elif False:  # guard disabled by scripts/guard_check.py\n        return []",
            ),
        ),
    ),
    "combinator.negator-poisons": Guard(
        what="a negator anywhere in the receiver chain a terminal folds poisons every "
        "branch of the route",
        why="without it the negation reads as a pass-through — nothing contributed, the "
        'chain folded on — and `path("/a").negate().uri(x)` is published as `/a`, '
        "resolved: the one path the route does NOT serve, presented as its address",
        edits=(
            Edit(
                path=_COMBINATOR,
                find="        if key in context.negators:\n"
                "            return [_Route(poisons=_IDENTITY_POISON)]",
                replace="        if key in context.negators:\n"
                "            continue  # guard disabled by scripts/guard_check.py",
            ),
        ),
    ),
    "combinator.entry-owner-is-the-declared-type": Guard(
        what="an entry of either shape — argument-rooted or body-linked — matches a call "
        "only on the owner AND method the catalog declares",
        why="the two functional-routing catalogs are one package apart and identical in "
        "every other cell — same `route(predicate, handler)` call, same verb factory "
        "names, same argument shapes. Matching on the method name alone roots the "
        "reactive router under the servlet catalog and vice versa, and each then derives "
        "an unresolved row for a tree its twin already derived correctly: a duplicate "
        "boundary with a wrong catalog id, and a gap row for a route that has none. A "
        "body-linked entry is the ONLY root an all-static nesting DSL has (A2 Task 3), so "
        "there the same slip roots any method of that name handed a lambda and publishes "
        "a router nobody registered",
        edits=(
            Edit(
                path=_COMBINATOR,
                find='            if site["owner"] == entry["owner"] and site["name"] in entry["methods"]',
                replace='            if site["name"] in entry["methods"]  # guard disabled',
            ),
            # The body-linked shape goes through `_matching_rule` (arity and arg_types
            # beside owner and name, A2 Task 7); the weakening hands each entry the
            # site re-owned as that entry's own type, so only the owner conjunct falls.
            Edit(
                path=_COMBINATOR,
                find="    return _matching_rule(site, context.body_entries)\n",
                replace="    return next(  # guard disabled by scripts/guard_check.py\n"
                "        (\n"
                "            match\n"
                "            for entry in context.body_entries\n"
                '            if (match := _matching_rule({**site, "owner": entry["owner"]}, (entry,)))\n'
                "            is not None\n"
                "        ),\n"
                "        None,\n"
                "    )\n",
            ),
        ),
    ),
    # --- `supertype_dispatch` ---------------------------------------------
    "supertype_dispatch.declared-supertype": Guard(
        what="a class matches only when it REACHES the descriptor the catalog names "
        "through scanned superclasses, package included",
        why="ordinary inheritance is not evidence of anything (the C-1 lesson). Comparing "
        "simple names alone would serve a `jakarta` module from the `javax` catalog and "
        "publish it under a rule measured against the other API. *Said DIRECT superclass "
        "until F3 §4.2: the one-hop test was a stated boundary — a class reaching "
        "`HttpServlet` through an intermediate base of its own derived nothing — and it "
        "was one only while the hierarchy was unavailable. What the guard protects is "
        "unchanged: the comparison is on the full descriptor, and widening the WALK does "
        "not weaken WHAT is compared*",
        edits=(
            Edit(
                path=_SUPERTYPE_DISPATCH,
                find="        if bare_descriptor(implementer) not in reaches:",
                replace="        if False:  # guard disabled by scripts/guard_check.py",
            ),
        ),
    ),
    "supertype_dispatch.address-is-required": Guard(
        what="a class registered at no readable address derives no row",
        why="the weakening is not deleting the check — with no address the row-minting loop "
        "simply iterates zero times — but publishing the class at the EMPTY address, "
        "which is what "
        '"no declaration" becomes the moment the requirement is relaxed: an endpoint '
        "addressing nothing, at `resolved`/`compiler`",
        edits=(
            Edit(
                path=_SUPERTYPE_DISPATCH,
                find="        addresses = addresses_by_class.get(implementer)",
                replace='        addresses = addresses_by_class.get(implementer) or ("",)',
            ),
        ),
    ),
    "supertype_dispatch.address-arg-is-a-declared-alias": Guard(
        what="only an argument the catalog names in `address.args` is read as an address",
        why='`@WebServlet(name = "orders")` carries a servlet NAME and no URL; reading '
        "whatever attribute happens to be written publishes the class at an address "
        "nothing serves",
        edits=(
            Edit(
                path=_SUPERTYPE_DISPATCH,
                find="        written = [key for key in keys if key in args]",
                replace="        written = [key for key in args][:1]  # guard disabled",
            ),
        ),
    ),
    "supertype_dispatch.address-args-are-an-alias-set": Guard(
        what="`address.args` is an alias SET — exactly one of its keys may be written",
        why="the spellings are one attribute, and a declaration writing both is one the "
        "container refuses to deploy, so the module serves nothing at all; "
        "first-alias-wins publishes whichever value the compiler happened to write first",
        edits=(
            Edit(
                path=_SUPERTYPE_DISPATCH,
                find="        if len(written) != 1:",
                replace="        if len(written) < 1:  # guard disabled",
            ),
        ),
    ),
    "supertype_dispatch.member-selector-is-name-and-parameter-types": Guard(
        what="a dispatch member is selected by name AND parameter types in order, never by "
        "name alone",
        why="GUIDELINES §8.1's language rule. `doGet(String, HttpServletResponse)` overrides "
        "nothing and the container answers 405; a name-keyed selector publishes "
        "`GET /orders` — an address nothing serves",
        edits=(
            Edit(
                path=_SUPERTYPE_DISPATCH,
                find="        selector = (method_name(bare_descriptor(symbol)), parameters)",
                replace="        selector = (method_name(bare_descriptor(symbol)), ())",
            ),
            Edit(
                path=_SUPERTYPE_DISPATCH,
                find="        tuple(type_descriptor(parameter) for parameter in "
                'entry["parameters"]),',
                replace="        (),  # guard disabled by scripts/guard_check.py",
            ),
        ),
    ),
    "supertype_dispatch.bypassed-by": Guard(
        what="a class overriding the dispatch entry point derives nothing unless that "
        "override DELEGATES back into the supertype's own implementation",
        why="a non-delegating override has replaced the lookup the table describes: measured, "
        "it serves GET 200, POST 200 and PUT 200 where the delegating twin refuses PUT with "
        "405 (CP-9 rows 41-43 against 35-40). Publishing the declared verbs and withholding "
        "one the container serves is a WRONG answer rather than a partial one",
        edits=(
            Edit(
                path=_SUPERTYPE_DISPATCH,
                find="        if not all(symbol in delegating for symbol in overridden):",
                replace="        if False:  # guard disabled by scripts/guard_check.py",
            ),
        ),
    ),
    "supertype_dispatch.registered-and-serving-nothing": Guard(
        what="a registered class overriding no dispatch member derives nothing",
        why='"the registration is the evidence" needs both conjuncts — such a class answers '
        "405 to every verb, and publishing its address invents a boundary. The weakening "
        "is the one that would make a row appear at all: the address published under the "
        "catalog's first declared verb",
        edits=(
            Edit(
                path=_SUPERTYPE_DISPATCH,
                find="        if not handlers:",
                replace='        handlers = handlers or ((str(next(iter(dispatch.values()))), ""),)'
                "\n        if False:  # guard disabled",
            ),
        ),
    ),
    # --- `annotation_driven`, whose guards are SQL ------------------------
    "derive_endpoints.mapping-annotation-fqn": Guard(
        what="a declaration matches a catalog's mapping annotation on the FULLY QUALIFIED "
        "name, never on the simple name",
        why="`SqsListener` moved package twice and kept its shape. A legacy catalog matching "
        "the current annotation claims a module declares an artifact it does not, and "
        "doubles every current listener's row",
        edits=(
            Edit(
                path=_DERIVE_ENDPOINTS,
                find="    JOIN mapping_catalog mc ON mc.fqn = a.annotation",
                replace="    JOIN mapping_catalog mc ON regexp_extract(mc.fqn, '[^/]*$')"
                " = regexp_extract(a.annotation, '[^/]*$')",
                # The same join, written at five places in the file (an
                # annotated declaration, the class gate, the DIRECT class gate
                # the second member word reads, the member rule's exclusion,
                # and the prefix scan). One guard, so all five move together —
                # disabling it at one site alone would measure a different
                # question from the one the catalogs' near-misses ask.
                occurrences=5,
            ),
        ),
    ),
    "derive_endpoints.type-annotation-gate": Guard(
        what="a catalog declaring `$type_annotation` derives only from a declaration whose "
        "enclosing type carries it",
        why="the operation annotations carry no address at all, so a row escaping the class "
        "gate could only ever be the discovery document itself — an endpoint this method "
        "does not serve",
        edits=(
            Edit(
                path=_DERIVE_ENDPOINTS,
                find="    WHERE (cp.type_annotation IS NULL OR c.type_symbol IS NOT NULL)",
                replace="    WHERE TRUE  -- guard disabled by scripts/guard_check.py",
            ),
        ),
    ),
    "derive_endpoints.declared-on-construct-kind": Guard(
        what="a catalog declaring `$declared_on` derives only from a declaration whose "
        "enclosing type is that CONSTRUCT KIND",
        why="2I design §4. The same annotation family means opposite things on a CLASS (a "
        "server resource JAX-RS or JAX-WS publishes) and an INTERFACE (a generated "
        "client stub or an MP REST Client) — `@RegisterRestClient`/`@Path` on a CLASS is "
        "not `microprofile-rest-client.yml`'s shape at all. Without this fence an "
        "outbound catalog gated on `declared_on: interface` would also derive from "
        "every annotated CLASS an inbound catalog already reports, publishing a served "
        "operation as one the module calls too",
        edits=(
            Edit(
                path=_DERIVE_ENDPOINTS,
                find="      AND (cp.declared_on IS NULL OR e.construct_kind = cp.declared_on)",
                replace="      AND TRUE  -- guard disabled by scripts/guard_check.py",
            ),
        ),
    ),
    "derive_endpoints.handler-is-a-method": Guard(
        what="a handler or caller is always a method (or a free function) — a TYPE-level use "
        "of a mapping annotation joins no declaration at all",
        why="pre-flight ruling R2. `@PulsarListener` is `@Target({TYPE, METHOD, ...})` and the "
        "framework ships no class-level handler for it to dispatch to, so a type-level use "
        "registers no listener; without this join a class-level mapping mints one phantom "
        "endpoint per entry in `all_methods`, giving every method of the class the class's "
        "own destination",
        edits=(
            Edit(
                path=_DERIVE_ENDPOINTS,
                find="    JOIN symbols s ON s.symbol = m.method_symbol AND s.construct_kind "
                "IN ('method', 'function')",
                replace="    JOIN symbols s ON s.symbol = m.method_symbol",
            ),
        ),
    ),
    "derive_endpoints.addresses-nothing": Guard(
        what="a derived row whose address is empty and whose `peer` is NULL names no endpoint, "
        "and is not inserted",
        why="mechanism 3 (`A-C1`). A method-level mapping annotation carrying no address of "
        "its own, on a class carrying none either, composes to the EMPTY address — and an "
        "empty address published at `resolved`/`compiler` is a boundary the running system "
        "does not serve, presented as observed. Three shipped catalogs reached it",
        edits=(
            Edit(
                path=_DERIVE_ENDPOINTS,
                find="WHERE NOT (d.path = '' AND d.peer IS NULL)",
                replace="WHERE TRUE  -- guard disabled by scripts/guard_check.py",
            ),
        ),
    ),
    "derive_endpoints.rows-land-at-the-catalogs-turn": Guard(
        what="an annotation-driven catalog's staged rows reach `endpoints` at that catalog's "
        "own turn in the sorted order, never as soon as the batch is derived",
        why="B (`docs/performance.md`). The call-site styles take turns BETWEEN the "
        "annotation-driven catalogs, and a wire identity belongs to whichever turn came "
        "first. Inserting every staged catalog's rows right after the one statement hands "
        "a route a call-site catalog registered to the annotation-driven catalog behind it "
        "— a different `catalog_id` on the same identity, and the call-site row refused or "
        "doubled — with no corpus in the repository able to tell",
        edits=(
            Edit(
                path=_ENDPOINTS_DRIVER,
                find="    annotation_driven.stage(\n"
                "        workspace, [catalog for catalog, _ in running if catalog.style == _STAGED]\n"
                "    )\n"
                "    for catalog, engine in running:\n"
                "        engine(workspace, catalog)\n",
                replace="    staged = [catalog for catalog, _ in running if catalog.style == _STAGED]\n"
                "    annotation_driven.stage(workspace, staged)\n"
                "    for catalog in staged:  # guard disabled by scripts/guard_check.py\n"
                "        annotation_driven.insert(workspace, catalog)\n"
                "    for catalog, engine in running:\n"
                "        if catalog.style != _STAGED:\n"
                "            engine(workspace, catalog)\n",
            ),
        ),
    ),
    "derive_endpoints.direction-flip-is-owner-scoped": Guard(
        what="a row takes the catalog's RESOLVED direction only where the type enclosing its "
        "declaration is one the catalog's own condition held for — never merely because the "
        "catalog declares a resolution rule",
        why="`@HttpExchange` is the one family whose direction is not a property of the "
        "annotation, and the flip's whole risk is scope: a rule keyed on the catalog rather "
        "than on the owner rewrites EVERY HTTP-interface client in the estate into an "
        "endpoint the module serves — a whole outbound surface inverted at "
        "`resolved`/`compiler`, which is the largest single fabrication this file can produce",
        edits=(
            Edit(
                path=_DERIVE_ENDPOINTS,
                find="        (fl.owner IS NOT NULL) AS flipped,",
                replace="        (cp.flip_direction IS NOT NULL) AS flipped,  -- guard disabled",
            ),
        ),
    ),
    "endpoints.superseded-catalog-does-not-run": Guard(
        what="a catalog declaring `detect.superseded_by` is SKIPPED, not merely deprioritised, "
        "on a module whose recorded build declares one of those coordinates",
        why="B/C Task 10 fix round 1. `jakarta-jaxrs.yml` and `quarkus-rest.yml` read the SAME "
        "`jakarta.ws.rs` annotations — Quarkus REST implements the specification with the "
        "specification's own classes — and derive the byte-identical wire identity for every "
        "resource method a Quarkus module declares, with genuinely different body rules "
        "(`request_body.implicit_bindings`, `excludes`). Without this gate the merge's "
        "insert-if-absent guard picks a winner by FILENAME alone, and `jakarta-jaxrs.yml` sorts "
        "first — so a Quarkus module's own `OrderResource#upload(Upload form)` publishes the "
        "parameter CONTAINER as the request body instead of excluding it, silently, on every "
        "row Jersey's rule and Quarkus's disagree about",
        edits=(
            Edit(
                path=_ENDPOINTS_DRIVER,
                find="        superseded = _superseded_by(workspace, catalog)\n"
                "        if superseded is not None:",
                replace="        superseded = _superseded_by(workspace, catalog)\n"
                "        if False:  # guard disabled by scripts/guard_check.py",
            ),
        ),
    ),
    # B/C Task 10b (CP-22 row 2, spec §3f). `peer_annotation`'s DEFAULT is
    # Python rather than SQL — `derive_endpoints.sql`'s `peer_gates` reads
    # whatever `$peer_annotation` already resolved to, so the fallback that
    # makes every catalog written before this word byte-identical is written
    # where the resolution happens.
    "derive_endpoints.peer-read-off-the-peer-annotation": Guard(
        what="`peer_from` is read off `mapping.peer_annotation` where a catalog declares one, "
        "not unconditionally off `mapping.prefix_annotation`",
        why="CP-22 row 2: MicroProfile REST Client's prefix (`@Path`) and peer "
        "(`@RegisterRestClient`'s `baseUri`/`configKey`) sit on two different annotations. "
        "Forcing the fallback unconditionally reads `peer_from` off `@Path`, which carries "
        "neither attribute, so every MP REST Client row's `peer` derives NULL instead of "
        "the config key or base URI Feign's own `peer_from` precedent says a client's "
        "peer should be",
        edits=(
            Edit(
                path=_ANNOTATION_DRIVEN,
                find='    peer_annotation = mapping.get("peer_annotation") or prefix_annotation',
                replace="    peer_annotation = prefix_annotation  # guard disabled by "
                "scripts/guard_check.py",
            ),
        ),
    ),
    # The flip's OTHER conjunct is Python rather than SQL, for the reason the
    # catalog guards below are YAML: what decides where a guard lives is where
    # the claim is written. This one is written where the framework's own
    # predicate is mirrored.
    "annotation_driven.flip-implementer-is-a-controller": Guard(
        what="a type is a flip OWNER only where the class implementing it carries one of the "
        "annotations the catalog's condition names — resolved through the composition "
        "pre-pass, so a module-local stereotype counts",
        why="this is exactly spec §6's `owner_implemented_in_module: true`, which is weaker "
        "than Spring's own rule and fabricates: `isHandler` is one "
        "`AnnotatedElementUtils.hasAnnotation(beanType, Controller.class)` call with no "
        "`@RequestMapping` disjunct on any minor CP-7 measured, so a `@Service` implementing "
        "an `@HttpExchange` interface is dispatched to by nothing and an inbound row for one "
        "is an endpoint nobody serves (§8.1 rule 4). The weakening below IS the condition the "
        "spec ordered",
        edits=(
            Edit(
                path=_ANNOTATION_DRIVEN,
                find="        if implementer not in handler_beans:",
                replace="        if False:  # guard disabled by scripts/guard_check.py",
            ),
        ),
    ),
    # --- the 2026-09-06 vocabulary pass (`OI-5`, `OI-35`, `OI-36`) ---------
    "annotation_driven.folded-uses-are-read": Guard(
        what="a repeatable container the catalog names is unfolded into one ordinary "
        "annotation row per use written inside it",
        why="`OI-36`, measured by CP-16 at six versions across three frameworks. javac writes "
        "the CONTAINER and not the annotation (JLS 9.7.5), so a method carrying two listeners "
        "carries no listener annotation at all and the mapping join matches nothing: BOTH "
        "destinations vanish from the export, silently, beside a single-listener neighbour "
        "that derives normally. A silent under-report is the harder of the two sins to notice, "
        "because there is no wrong row to see — and without this read the `container` key is a "
        "comment",
        edits=(
            Edit(
                path=_EFFECTIVE_ANNOTATIONS,
                find="    if not containers:\n        return []",
                replace="    if True:  # guard disabled by scripts/guard_check.py\n        return []",
            ),
        ),
    ),
    "annotation_driven.folded-entry-is-the-declared-annotation": Guard(
        what="each entry of a container's array counts only where it IS the annotation the "
        "catalog declared that container for — never merely because it sits in the array",
        why="a container is an ordinary annotation whose `value` happens to be an array, so "
        "without this conjunct any array-of-annotations argument contributes destinations. "
        "`@RabbitListener(bindings = @QueueBinding(...))` is exactly that shape one attribute "
        "over, and reading it would publish a binding's own attribute as a queue name at "
        "`resolved`/`compiler` — the `scheduled_work._folded` conjunct, one style over",
        edits=(
            Edit(
                path=_EFFECTIVE_ANNOTATIONS,
                find='            and entry.get("annotation") == member',
                replace='            and entry.get("annotation") is not None',
            ),
        ),
    ),
    "derive_endpoints.sibling-name-source-order": Guard(
        what="where several sibling name sources are present on one declaration, the FIRST in "
        "the order the catalog wrote supplies the name",
        why="`OI-35`. CP-15 rows 1a-1b show the framework building an array of name sources "
        "whose `iconst_N` indices ARE the order and taking the first WITH A VALUE, so a "
        "declaration carrying two of them is served under the earlier one. A vocabulary that "
        "could only name a SET would not say which — and picking the other one publishes a "
        "name the framework does not serve the operation at, which is the wrong address this "
        "key exists to remove, reached from the other side",
        edits=(
            Edit(
                path=_DERIVE_ENDPOINTS,
                find="           min_by(coalesce(TRY_CAST(a.args -> sp.arg AS VARCHAR[]),"
                " [a.args ->> sp.arg]),\n                  sp.ordinal) AS found",
                replace="           max_by(coalesce(TRY_CAST(a.args -> sp.arg AS VARCHAR[]),"
                " [a.args ->> sp.arg]),\n                  sp.ordinal) AS found",
            ),
        ),
    ),
    "annotation_driven.sibling-media-only-when-own-absent": Guard(
        what="`produces_from_siblings` (and its `consumes_from_siblings` twin) is consulted "
        "only where every `produces_from` alias on the matched annotation itself is absent — "
        "never merely because a catalog declares the sibling key",
        why="Spec 2026-09-18 §3b word 1. CP-18 row 1 puts `@GET`'s own attributes (none) ahead "
        "of the sibling `@Produces`/`@Consumes`, mirroring CP-15 row 1's order for "
        "`path_from_siblings` — a declaration that names its OWN media type is served under "
        "that type, not under whatever a differently-annotated sibling on the same method "
        "happens to carry. Preferring the sibling publishes the WRONG media type at "
        "`resolved`/`compiler` for every declaration that states its own",
        edits=(
            Edit(
                path=_DERIVE_ENDPOINTS,
                find="        coalesce(list_extract(list_filter(list_transform(\n"
                "            cp.produces_from,\n"
                "            n -> CASE WHEN coalesce(a.args -> n ->> 0, a.args ->> n)"
                " IS NOT NULL\n"
                "                      THEN coalesce(TRY_CAST(a.args -> n AS VARCHAR[]),\n"
                "                                    [a.args ->> n]) END\n"
                "        ), v -> v IS NOT NULL), 1), smp.found) AS produces_list,",
                replace="        coalesce(smp.found, list_extract(list_filter(list_transform(\n"
                "            cp.produces_from,\n"
                "            n -> CASE WHEN coalesce(a.args -> n ->> 0, a.args ->> n)"
                " IS NOT NULL\n"
                "                      THEN coalesce(TRY_CAST(a.args -> n AS VARCHAR[]),\n"
                "                                    [a.args ->> n]) END\n"
                "        ), v -> v IS NOT NULL), 1)) AS produces_list,  -- guard disabled",
            ),
        ),
    ),
    "effective_annotations.siblings-inherit-all-or-nothing": Guard(
        what="for a catalog declaring sibling lists, a method carrying ANY annotation of the "
        "catalog's own — a sibling as much as a mapping — inherits nothing from the ancestor "
        "method; never only a method carrying an own MAPPING",
        why="Spec 2026-09-18 §3b word 3, CP-18 row 8. JAX-RS §3.6's rule is all-or-nothing per "
        'method: "if a subclass or implementation method has any JAX-RS annotations then all '
        'of the annotations on the superclass or interface method are ignored". An implementor '
        "method carrying only its own `@Produces` is, to the framework, not a resource method "
        "at all. With the own-check narrowed to the mapping alone, the walk inherits the "
        "interface's `@GET` and `@Path` onto it and publishes a route the framework does not "
        "serve — a fabricated address, and Spring's per-annotation merge applied to a "
        "framework that measured the opposite",
        edits=(
            Edit(
                path=_EFFECTIVE_ANNOTATIONS,
                find="    own_fqns = mapping_fqns | set(sibling_fqns)",
                replace="    own_fqns = set(mapping_fqns)  # guard disabled",
            ),
        ),
    ),
    "effective_annotations.inherited-set-agreed-as-a-whole": Guard(
        what="two ancestors mapping one method agree only when their WHOLE inherited sets "
        "agree — the mapping and every declared sibling — never on the mapping alone",
        why="Spec 2026-09-18 §3b word 3 (Task 5 fix round 1). JAX-RS §3.6 inherits an ancestor "
        'method\'s annotation set whole, so an interface `@GET @Path("/a")` against a '
        'superclass `@GET @Path("/b")` on one covariantly-overridden method is the same '
        "ambiguous evidence two different verbs are (I1), one annotation over. Compared on the "
        "verb alone they agree, and the target is handed the verb with BOTH paths beside it; "
        "downstream `sibling_names` then picks between two same-annotation rows on a tied "
        "ordinal, and the published address is whichever DuckDB happened to keep — a wrong "
        "address half the time and an unpredictable one every time (NFR-1)",
        edits=(
            Edit(
                path=_EFFECTIVE_ANNOTATIONS,
                find="                    frozenset(\n"
                "                        (sib_annotation, json.dumps(sib_args, sort_keys=True))\n"
                "                        for sib_annotation, sib_args in siblings\n"
                "                    ),\n",
                replace="                    frozenset(),  # guard disabled\n",
            ),
        ),
    ),
    # --- the body rule (`shapes/contracts.py`) ------------------------------
    "contracts.sole-unbound-measures-bound-by": Guard(
        what="under `sole_unbound`, a parameter is bound by an annotation only when that "
        "annotation is on the catalog's `bound_by` list — any other annotation on it is "
        "invisible to the rule",
        why="Spec 2026-09-18 §4 (M2, M4). JAX-RS §3.3.2.1's entity parameter is the one carrying "
        "none of the SPECIFICATION's parameter annotations; kotlinc writes "
        "`@org.jetbrains.annotations.NotNull` on every non-null parameter and Bean Validation "
        "puts `@Valid` on the body. Widened back to 'any annotation binds' — the "
        "`sole_unannotated` reading — every Kotlin JAX-RS body and every `@Valid Order order` "
        "publishes NO request contract: a real payload the framework binds, silently missing "
        "from the endpoint's document",
        edits=(
            Edit(
                path=_CONTRACTS,
                find='    if any(use["annotation"] in binders for use in parameter.get("annotations", [])):',
                replace='    if parameter.get("annotations"):  # guard disabled',
            ),
        ),
    ),
    "contracts.implicit-path-variable-reads-the-composed-path": Guard(
        what="the `path_variable` implicit binding reads the parameter's name against the "
        "`{name}` variables of the row's composed path, and only where the catalog declares "
        "the word",
        why="Spec 2026-09-18 §4 predicate 2, `EndpointIndexer.java:1393-1399`: Quarkus REST "
        "treats a parameter named like a path variable as an implicit `@PathParam`, so "
        '`byId(String id)` beneath `@Path("/{id}")` has no body. With the variables read as '
        "empty, that `id` is the sole unbound parameter and is published as the request "
        "contract — a `String` body the framework never reads. The paired half, that Jersey "
        "does NOT do this and `jakarta-jaxrs.yml` declares no implicit binding, is what the "
        "pinning test's `plain` arm asserts",
        edits=(
            Edit(
                path=_CONTRACTS,
                find='        variables = _path_variables(paths) if "path_variable" in implicit else frozenset()',
                replace="        variables = frozenset()  # guard disabled",
            ),
        ),
    ),
    "contracts.conditional-wrapper-needs-its-condition": Guard(
        what="a conditional `wrappers` entry (`when`) is handed to `root_type` for an owner "
        "only where its condition actually holds for that owner",
        why='Spec 2026-09-18 §5a. A Spring Kafka `@KafkaListener(batch = "true")` handler '
        "takes `List<OrderEvent>` where the wire carries one `OrderEvent` per record; a "
        "non-batched listener on the same type takes the wire's own single `OrderEvent`. "
        "Dropping the filter unwraps `List` for BOTH — the non-batched handler's real "
        "`List<OrderEvent>` payload is reported as a bare `OrderEvent`, a wrong contract for "
        "a call the catalog never declared batched",
        edits=(
            Edit(
                path=_CONTRACTS,
                find="    return [\n"
                "        *rules.wrappers,\n"
                "        *(\n"
                "            wrapper\n"
                "            for condition, wrapper in rules.conditional_wrappers\n"
                "            if holds(condition, owner, index)\n"
                "        ),\n"
                "    ]",
                replace="    return [\n"
                "        *rules.wrappers,\n"
                "        *(wrapper for condition, wrapper in rules.conditional_wrappers),\n"
                "    ]  # guard disabled",
            ),
        ),
    ),
    "protocol_hint.hint-when-reads-the-owner": Guard(
        what="`hint_when` actually reads the catalog's `annotation_arg` condition against the "
        "row's owner (and its enclosing type) rather than treating any declared condition as "
        "satisfied",
        why="Spec 2026-09-18 §5b, CP-21 rows 1a/3a-3b. Micronaut's `@JMSListener` carries one "
        "`value()` naming a connection-factory bean, and `sqsJmsConnectionFactory` vs. "
        "`activeMqConnectionFactory` is the ONLY thing distinguishing an SQS listener from an "
        "ActiveMQ-classic one — both are plain `jms` rows to every other engine. Treating a "
        "declared `hint_when` as always-true reclassifies the ActiveMQ row to `sqs` right "
        "alongside the real SQS one, publishing a queue address for a broker the class was "
        "never wired to",
        edits=(
            Edit(
                path=_PROTOCOL_HINT,
                find="    return owner is not None and any(holds(c, owner, index) for c in hint.conditions)",
                replace="    return owner is not None and bool(hint.conditions)  # guard disabled",
            ),
        ),
    ),
    "protocol_hint.hint-annotations-yield-to-a-declared-produces": Guard(
        what="`hint_annotations` fires only when the row's OWNER carries none of the declaring "
        "catalog's `produces_from_siblings` annotations — never on the marker's presence alone "
        "beside a method-level media declaration",
        why="CP-19 row 2a (`EndpointIndexer.java:720-723`, the final review's Important 2). "
        "Quarkus reads the method-level `@Produces` FIRST and falls to `@RestStreamElementType` "
        "only when that read is empty, so `@GET @Produces(APPLICATION_STREAM_JSON) "
        "@RestStreamElementType(APPLICATION_JSON) Multi<Book>` serves an NDJSON stream, not "
        "SSE. On presence alone the pass would publish that row as `sse` — a protocol the "
        "framework never serves there, at `resolved`/`compiler` where nothing downstream can "
        "tell it from an observation",
        edits=(
            Edit(
                path=_PROTOCOL_HINT,
                find="    if any(annotation in hint.media_annotations for annotation, _ in index.get(owner, [])):\n"
                "        return False\n",
                replace="",
            ),
        ),
    ),
    "derive_endpoints.path-fallback-is-per-annotation": Guard(
        what="an annotated declaration takes the fallback word of the annotation that MATCHED "
        "it, not the catalog's own default",
        why="`OI-5`, measured by CP-15 rows 3-5 with row 5 compiled and run. The framework's "
        "un-named-operation fallback is direction-dependent and the direction is chosen by "
        "which operation annotation matched — one strips `get`/`is`, the other strips `set` — "
        "so a single catalog-level word makes one of the two annotations newly wrong. That is "
        "the approximation §8.1 rule 1 forbids, and it is why this defect shipped a measured "
        "wrong address rather than a plausible fix",
        edits=(
            Edit(
                path=_DERIVE_ENDPOINTS,
                find="        mc.path_fallback AS path_fallback,\n"
                "        mc.path_fallback_prefixes AS path_fallback_prefixes",
                replace="        cp.path_fallback AS path_fallback,\n"
                "        cp.path_fallback_prefixes AS path_fallback_prefixes",
            ),
        ),
    ),
    "derive_endpoints.accessor-strip-is-the-measured-one": Guard(
        what="the accessor strip fires only where the construct's name is LONGER than the "
        "prefix and carries an upper-case character AT THE SEAM",
        why="CP-15 row 5, compiled and run: `get -> get` is the length test and "
        "`gettotal -> gettotal` is the seam test. Without them a method named exactly `get` "
        "composes the EMPTY address and vanishes, and an ordinary lower-case name beginning "
        "with those three letters is republished under a property name the framework never "
        "derives. §8.1 rule 1 is that a framework's rule is mirrored rather than approximated, "
        "and the approximation here is the one that fits every example but the edges",
        edits=(
            Edit(
                path=_DERIVE_ENDPOINTS,
                find="                             x -> CASE WHEN starts_with(construct_name, x)\n"
                "                                            AND length(construct_name)"
                " > length(x)\n"
                "                                            AND regexp_matches(\n"
                "                                                substr(construct_name,"
                " length(x) + 1, 1), '[A-Z]')",
                replace="                             x -> CASE WHEN"
                " starts_with(construct_name, x)",
            ),
        ),
    ),
    "derive_endpoints.qualifier-scope": Guard(
        what="a declaration whose annotation only means anything INSIDE a scope, with no "
        "scope found at either level, derives no row",
        why="the bare member name would read as a top-level identity — a different endpoint "
        "from the one the code declares, presented as observed",
        edits=(
            Edit(
                path=_DERIVE_ENDPOINTS,
                find="      AND NOT (m.requires_qualifier AND coalesce(m.qualifier, q.qualifier)"
                " IS NULL)",
                replace="      AND TRUE  -- guard disabled by scripts/guard_check.py",
            ),
        ),
    ),
    # --- `derived_resource` -----------------------------------------------
    "derived_resource.inherited-interfaces-are-no-repository-beans": Guard(
        what="the query-method walk crosses a module-local superinterface only where it "
        "carries the catalog's `no_repository_bean` annotation — every other superinterface "
        "is a custom FRAGMENT",
        why="Spring Data REST serves no `/search/` route for a fragment method: "
        "`calculateQueryMethods` filters through `isCustomMethod`, which the fragment "
        "composition answers (CP-13 Q6/Q7). Crossing an unannotated superinterface publishes "
        "`GET /orders/search/searchByFullText` for a hand-written method whose body lives in "
        "an `…Impl` the framework never routes to",
        edits=(
            Edit(
                path="sextant/application/resolve/engines/derived_resource.py",
                find="        if not any(name in annotations.get(parent, {}) for name in no_repository_beans):",
                replace="        if False:  # guard disabled by scripts/guard_check.py",
            ),
        ),
    ),
    "derived_resource.a-route-needs-an-operation-the-contract-licenses": Guard(
        what="a route derives for a repository only where the repository reaches the CRUD "
        "operation that route requires — and since W53 every route requires one",
        why="`G-46`. The collection GET carried no `needs:` at all, on the belief that it is "
        "the one route every exposed repository serves whatever it extends. Measured in the "
        "framework: `CrudMethodsSupportedHttpMethods.getMethodsFor` adds GET only behind "
        "`exposesFindAll()`, which reduces to a `findMethod` lookup over the repository "
        "interface, and `org.springframework.data.repository.Repository` declares zero "
        "methods at spring-data-commons 3.2.5 and 4.0.1. Without this filter a bare "
        "`interface Foo extends Repository<Foo, Long>` publishes `GET /foos` for a collection "
        "that answers OPTIONS and nothing else",
        edits=(
            Edit(
                path="sextant/application/resolve/engines/derived_resource.py",
                find="            if needed is not None and needed not in repository.operations:",
                replace="            if False:  # guard disabled by scripts/guard_check.py",
            ),
        ),
    ),
    "derive_endpoints.one-exposed-member-per-signature": Guard(
        what="a gated class exposes ONE member per `(name, parameter types)` — the nearest "
        "declaration in its ancestry — and the exclusions and the annotation anti-join are "
        "asked of that one",
        why="`Class.getMethods()` returns one entry per signature (CP-13 Q5), so a walk that "
        "keeps every ancestor's declaration publishes an overridden operation TWICE, the "
        "second handled by a base class the framework never exposes — and republishes one "
        "an override's own `@WebMethod(exclude = true)` explicitly withdraws",
        edits=(
            Edit(
                path=_DERIVE_ENDPOINTS,
                find="    WHERE em.nearest = 1",
                replace="    WHERE TRUE  -- guard disabled by scripts/guard_check.py",
            ),
        ),
    ),
    "derive_endpoints.members-exclude-final": Guard(
        what="a `$members` row excludes a `final` method the same way it already excludes "
        "a `static` one",
        why="JAX-WS RI 4.0.2's `isWebMethodBySpec` excludes `static` AND `final` (CP-13 "
        "Q4), and the one catalog that declares `members: public_methods`, "
        "`jakarta-jws.yml`, is JAX-WS. Without "
        "this a `public final` helper method on a `@WebService` class — a common way to "
        "mark one non-overridable — is published as a SOAP operation nobody serves "
        "(`jaxws-public-final`)",
        edits=(
            Edit(
                path=_DERIVE_ENDPOINTS,
                find="      AND coalesce(s.modifiers ->> 'final', 'false') <> 'true'",
                replace="      AND TRUE  -- guard disabled by scripts/guard_check.py",
            ),
        ),
    ),
    "derive_endpoints.members-declaring-type-is-gated": Guard(
        what="a `$members` row is published only where the member's DECLARING class itself "
        "carries the catalog's gate annotation — the walk still continues past a plain "
        "ancestor, the filter is per declaring class",
        why="jaxws-rt 4.0.2's `isWebMethodBySpec` (offsets 124-147) and Apache CXF 4.0.5's "
        "`hasWebServiceAnnotation` (offsets 0-17) both read `@WebService` off "
        "`method.getDeclaringClass()`, never off the implementor class (w63, both runtimes "
        "run live: `charge` alone). Without this `gate_ancestry` publishes a public method "
        "inherited from a plain, unannotated superclass as a SOAP operation neither runtime "
        "serves (`jaxws-inherited-unannotated`)",
        edits=(
            Edit(
                path=_DERIVE_ENDPOINTS,
                find="      AND s.enclosing IN (SELECT type_symbol FROM gate_types\n"
                "                          WHERE gate_types.catalog_id = em.catalog_id)",
                replace="      AND TRUE  -- guard disabled by scripts/guard_check.py",
            ),
        ),
    ),
    # --- the two NON-WIRE styles (2O design §4) ----------------------------
    "scheduled_work.declaration-is-a-method": Guard(
        what="a schedule annotation counts only where its target is a METHOD — a use on an "
        "annotation TYPE is a composition, not scheduled work",
        why="`@Scheduled` is `@Target`-legal on an annotation type, which is how a module "
        "composes its own `@Nightly`. No method runs there, so publishing it reports work on "
        "a clock nobody set — `derive_endpoints.handler-is-a-method` is the same conjunct on "
        "the wire side, and the same fabrication when it is gone",
        edits=(
            Edit(
                path=_SCHEDULED_WORK,
                find="        if target not in methods:",
                replace="        if False:  # guard disabled by scripts/guard_check.py",
            ),
        ),
    ),
    "error_advice.container-gate": Guard(
        what="a handler method counts only where its declaring type is a handler CONTAINER — "
        "advice, or a controller",
        why="the framework finds handler methods by first finding the container, so a handler "
        "annotation on an ordinary service registers nothing. A row there reports an error "
        "contract the running system never answers with, and has to INVENT `declared_by` and "
        "`scope` to do it, since there is no container declaration to read either from",
        edits=(
            Edit(
                path=_ERROR_ADVICE,
                find="        return self.containers.get(owner)",
                replace='        return self.containers.get(owner) or _Container("", None)',
            ),
        ),
    ),
    "error_advice.handler-annotation-is-declared": Guard(
        what="a method of a container is a handler only where it carries the catalog's handler "
        "annotation",
        why="advice is a CONTAINER, not a claim that every method in it answers for an "
        "exception. Without the annotation conjunct an ordinary helper taking an exception "
        "argument — a logger, a mapper — is published as the module's error contract for that "
        "exception",
        edits=(
            Edit(
                path=_ERROR_ADVICE,
                find='            if row["annotation"] in handler_fqns and str(row["target"]) '
                "in methods",
                replace='            if str(row["target"]) in methods  # guard disabled',
            ),
        ),
    ),
    "error_advice.exception-is-required": Guard(
        what="a handler whose exception types could not be read derives no row",
        why="the weakening is not deleting a check — the row-minting loop simply iterates zero "
        "times — but publishing the handler at the EMPTY exception, which is what "
        '"we could not read it" becomes the moment the requirement is relaxed: an error '
        "contract for an exception nobody named, at `resolved`/`compiler`. The "
        "`supertype_dispatch.address-is-required` shape, one table over",
        edits=(
            Edit(
                path=_ERROR_ADVICE,
                find="        for exception in rules.exceptions_of(method):",
                replace='        for exception in rules.exceptions_of(method) or [""]:',
            ),
        ),
    ),
    # --- the call-site insert ---------------------------------------------
    "derive_call_endpoints.addresses-nothing": Guard(
        what="a `resolved` row whose address is empty and whose `peer` is NULL names no "
        "endpoint, and is not inserted — mechanism 3's twin on the call-site side",
        why="`combinator` stamps `resolved` whenever nothing poisoned the read and returns a "
        "NULL path when a folded route accumulated none, so a WebFlux route whose only "
        "predicate is a media constraint inserted an inbound-HTTP row with a NULL method AND "
        "a NULL path at `resolved`/`compiler` — and NULL paths skip the dedup key, so N such "
        "routes inserted N of them",
        edits=(
            Edit(
                path="sextant/storage/duckdb/derive_call_endpoints.sql",
                find="WHERE NOT (r.resolution = 'resolved' AND r.path IS NULL AND r.peer IS NULL)",
                replace="WHERE TRUE  -- guard disabled by scripts/guard_check.py",
            ),
        ),
    ),
    # --- guards that live in a shipped CATALOG rather than in an engine ----
    #
    # A conjunct a catalog states is a guard exactly as an engine's `if` is:
    # `A-M2`'s own mutation evidence disabled one either way round ("delete the
    # branch, or set `bypassed_by: []`"). What decides where a guard lives is
    # where the claim is written, not which language it is written in.
    "jakarta-jms.consuming-factories-only": Guard(
        what="`Session`'s factory list names the methods that CONSUME from a destination, "
        "and `createBrowser` is not one of them",
        why="`createBrowser` returns a `QueueBrowser`: it enumerates a queue without "
        "consuming from it, so an inbound row says the module receives messages the "
        "broker never delivers to it",
        edits=(
            Edit(
                path="sextant/catalogs/jakarta-jms.yml",
                find="    - name: createConsumer\n"
                "      arity: 1\n"
                '      descriptor: "(Ljakarta/jms/Destination;)Ljakarta/jms/MessageConsumer;"',
                replace="    - name: createBrowser\n"
                "      arity: 1\n"
                '      descriptor: "(Ljakarta/jms/Queue;)Ljakarta/jms/QueueBrowser;"\n'
                "      direction: inbound\n"
                "      channel_arg: 0\n"
                "      channel_via:\n"
                "        - { owner: jakarta.jms.Session, method: createQueue, arg: 0 }\n"
                "        - { owner: jakarta.jms.Session, method: createTopic, arg: 0 }\n"
                "    - name: createConsumer\n"
                "      arity: 1\n"
                '      descriptor: "(Ljakarta/jms/Destination;)Ljakarta/jms/MessageConsumer;"',
            ),
        ),
    ),
    # `spring-actuator.operations-are-the-mapping-annotations` WAS registered
    # here and is gone, and its removal is a finding rather than tidying. Its
    # weakening — declaring `@Endpoint` a mapping annotation of its own — mints
    # a declaration whose target is a CLASS, and `@Endpoint` is
    # `@Target(TYPE)`, so it can never sit anywhere else. Every such
    # declaration is dropped by `derive_endpoints.handler-is-a-method` on its
    # own account, whatever this catalog says. So the mistake this entry named
    # cannot produce a row while that join stands: it is a NO-OP mutation, and
    # §2.2 of the harness's own design forbids counting one — a no-op
    # manufactures a false finding in whichever direction it is read.
    #
    # The conjunct itself is real and stays in the catalog. What is not real is
    # the claim that a near-miss measures it, and the test that claimed to
    # (`test_an_endpoint_class_with_no_operation_annotation_derives_nothing`)
    # now says plainly that its emptiness has two independent causes and pins
    # neither.
    "spring-scheduling.triggers-are-the-schedule-attributes": Guard(
        what="`triggers` names the attributes that ARE a schedule, and nothing else",
        why="`initialDelay` is a real `@Scheduled` attribute, it is a duration, and it sits "
        "beside the rate it delays — it is not a schedule. Reading it publishes the wait "
        "before the FIRST run as the interval between EVERY run: a clock the framework never "
        "ticks on, at `resolved`/`compiler`",
        edits=(
            Edit(
                path="sextant/catalogs/spring-scheduling.yml",
                find="    fixedDelay: fixedDelay",
                replace="    fixedDelay: fixedDelay\n    initialDelay: fixedDelay",
            ),
        ),
    ),
    "spring-scheduling.the-disable-sentinel-is-the-frameworks-own": Guard(
        what="the value that withdraws a `cron` schedule is the one Spring's own "
        "post-processor compares against — `@Scheduled.CRON_DISABLED`, which is `-`",
        why="`OI-2`. A sentinel encoded from memory withdraws nothing: the framework "
        'registers no task for `cron = "-"` (CP-14 rows 1-3, three spring-context '
        "minors), so a catalog naming any other value publishes a `scheduled_work` row "
        "for work that will never run, at `resolved`/`compiler`, beside schedules that "
        "really do. The weakening is exactly the mistake §8.1 forbids — a plausible word "
        "in place of the measured one",
        edits=(
            Edit(
                path="sextant/catalogs/spring-scheduling.yml",
                find='  disabled:\n    cron: "-"',
                replace='  disabled:\n    cron: "disabled"',
            ),
        ),
    ),
    "scheduled_work.a-disabled-trigger-declares-no-task": Guard(
        what="a trigger attribute written with the value the catalog names as its disable "
        "sentinel derives no row",
        why="the engine half of the rule above, measured on its own so a catalog that "
        "states the right value and an engine that ignores it cannot pass for each other. "
        "Without the test the sentinel is a comment: every disabled schedule is published "
        "as live work again, and the catalog's `disabled` block reads as if it were doing "
        "something",
        edits=(
            Edit(
                path=_SCHEDULED_WORK,
                find="            if expression == disabled.get(attribute):",
                replace="            if False:  # guard disabled by scripts/guard_check.py",
            ),
        ),
    ),
    "spring-kafka.path-from-is-the-topic-attributes": Guard(
        what="`path_from` names the two attributes of `@KafkaListener` that ARE a topic, and "
        "nothing else",
        why="`groupId` is a real `@KafkaListener` attribute, it is a `String` exactly as "
        "`topicPattern` is, the post-processor reads it (CP-16 row 4), and it is a CONSUMER "
        "GROUP rather than a destination. Reading it publishes the group a service joins as a "
        "topic it consumes — a plausible-looking Kafka boundary at `resolved`/`compiler` that "
        "no broker carries",
        edits=(
            Edit(
                path="sextant/catalogs/spring-kafka.yml",
                find="    path_from: [topics, topicPattern]",
                replace="    path_from: [topics, topicPattern, groupId]",
            ),
        ),
    ),
    "spring-kafka.container-is-the-frameworks-own": Guard(
        what="`container` names the annotation javac ACTUALLY folds two `@KafkaListener` into",
        why="`OI-36`. A container named wrong matches nothing, and the failure is SILENT in the "
        "worst direction: a method carrying two listeners derives no row at all while its "
        "single-listener neighbour derives normally, so there is no wrong row to notice. "
        "CP-16 rows 2a/2b read `@Repeatable(KafkaListeners.class)` off the annotation's own "
        "class file at 3.1.4 and 4.1.1; the weakening below is a plausible name in place of "
        "the measured one, which is the mistake §8.1 forbids",
        edits=(
            Edit(
                path="sextant/catalogs/spring-kafka.yml",
                find="          container: org.springframework.kafka.annotation.KafkaListeners }",
                replace="          container: org.springframework.kafka.annotation.KafkaHandlers }",
            ),
        ),
    ),
    "spring-jms.container-is-the-frameworks-own": Guard(
        what="`container` names the annotation javac ACTUALLY folds two `@JmsListener` into",
        why="`OI-36`, and the same silent drop as the Kafka guard above. CP-16 rows 2c/2d read "
        "`@Repeatable(JmsListeners.class)` at 6.1.6 and 7.0.9, and rows 4c/4d show the "
        "post-processor naming both classes in one call",
        edits=(
            Edit(
                path="sextant/catalogs/spring-jms.yml",
                find="          container: org.springframework.jms.annotation.JmsListeners }",
                replace="          container: org.springframework.jms.annotation.JmsHandlers }",
            ),
        ),
    ),
    "spring-rabbit.container-is-the-frameworks-own": Guard(
        what="`container` names the annotation javac ACTUALLY folds two `@RabbitListener` into",
        why="`OI-36`, and the same silent drop again. CP-16 rows 2e/2f read "
        "`@Repeatable(RabbitListeners.class)` at 3.1.4 and 4.1.1",
        edits=(
            Edit(
                path="sextant/catalogs/spring-rabbit.yml",
                find="          container: org.springframework.amqp.rabbit.annotation."
                "RabbitListeners }",
                replace="          container: org.springframework.amqp.rabbit.annotation."
                "RabbitHandlers }",
            ),
        ),
    ),
    "spring-sqs.class-level-listener-is-the-prefix": Guard(
        what="a class-level `@SqsListener` is declared as the prefix annotation, so the queue "
        "it names reaches every `@SqsHandler` method of the class",
        why="`OI-40`. spring-cloud-aws-sqs 4.1.1 ships `@SqsHandler` and widens "
        "`@SqsListener`'s `@Target` to include `TYPE`, and its post-processor builds a "
        "`MultiMethodSqsEndpoint` from the class-level annotation's own `value()` (CP-17 rows "
        "2f, 4f and 6f). `@SqsHandler` carries no address of its own, so with no prefix "
        "annotation declared the composed address is empty and the addresses-nothing gate "
        "withholds the row — the handler is ABSENT from the export rather than present with a "
        "blank queue, which is the harder of the two for a reader to notice. The weakening "
        "restores the `null` this file shipped for a year",
        edits=(
            Edit(
                path="sextant/catalogs/spring-sqs.yml",
                find="    prefix_annotation: io.awspring.cloud.sqs.annotation.SqsListener",
                replace="    prefix_annotation: null",
            ),
        ),
    ),
    "spring-pulsar.container-is-the-frameworks-own": Guard(
        what="`container` names the annotation Spring for Apache Pulsar ACTUALLY reads a "
        "second `@PulsarListener` out of",
        why="`OI-38`, and the same silent drop as the three CP-16 guards above, reached by a "
        "different mechanism: `@PulsarListener` is NOT `@Repeatable` (CP-17 rows 2a/2b), so "
        "the container is one an AUTHOR writes and the post-processor registers the union of "
        "it and the direct use (rows 3a/3b, 6a/6b). A container named wrong matches nothing "
        "and every topic declared that way vanishes with no wrong row to notice. The "
        "weakening below is a plausible name — the `@KafkaHandler`/`@RabbitHandler` spelling, "
        "one framework over — that CP-17 rows 4a/4b measured ABSENT from this jar",
        edits=(
            Edit(
                path="sextant/catalogs/spring-pulsar.yml",
                find="          container: org.springframework.pulsar.annotation.PulsarListeners }",
                replace="          container: org.springframework.pulsar.annotation.PulsarHandlers }",
            ),
        ),
    ),
    "spring-pulsar.reader-is-a-second-inbound-surface": Guard(
        what="the `annotations` list names `@PulsarReader` as well as `@PulsarListener` — the "
        "framework's SECOND inbound annotation, with its own post-processor and its own "
        "endpoint type",
        why="`OI-39`. The two annotations live in one jar and one package and neither is "
        "reachable from the other: a module whose consumers are readers had its whole Pulsar "
        "surface absent from the export, which is a silent drop of an entire shape rather "
        "than one attribute of one. CP-17 rows 1c/1d read `topics(): java.lang.String[]` off "
        "the annotation and rows 5c/5d show the post-processor feeding it to "
        "`MethodPulsarReaderEndpoint.setTopics`. The weakening names the container spelling "
        "rows 3c/3d measured ABSENT, so the entry matches no annotation any class file "
        "carries — which is exactly what a missing entry does",
        edits=(
            Edit(
                path="sextant/catalogs/spring-pulsar.yml",
                find="      - { fqn: org.springframework.pulsar.annotation.PulsarReader }",
                replace="      - { fqn: org.springframework.pulsar.annotation.PulsarReaders }",
            ),
        ),
    ),
    "microprofile-graphql.fallback-direction-is-per-annotation": Guard(
        what="each operation annotation declares the accessor direction its OWN fallback strips "
        "— the read direction for `@Query`, the write direction for `@Mutation`",
        why="`OI-5`, and the catalog half of the engine guard `derive_endpoints.path-fallback-"
        "is-per-annotation`, measured separately so a file that states the wrong direction and "
        "an engine that ignores the right one cannot pass for each other. CP-15 row 3 switches "
        "on the operation type and row 5 shows both halves: `setStatus -> IN status` and "
        "`setStatus` unchanged under OUT. One direction written on both annotations publishes "
        "an operation under a name SmallRye does not serve it at",
        edits=(
            Edit(
                path="sextant/catalogs/microprofile-graphql.yml",
                find="          path_fallback: write_accessor_property }",
                replace="          path_fallback: read_accessor_property }",
            ),
        ),
    ),
    "microprofile-graphql.name-sources-are-the-measured-annotations": Guard(
        what="`path_from_siblings` names the annotation TYPES CP-15 read out of the framework's "
        "own source array, and not ones that merely look like renaming annotations",
        why="`OI-35`. `@Name` is the specification's own renaming annotation and the second "
        "source `getOperationName` consults (CP-15 rows 1-2), so a method carrying it is served "
        "under the name it gives. A sibling list naming the wrong type matches nothing and the "
        "operation is published under its method name instead — a wrong address at "
        "`resolved`/`compiler`, which is the defect this key closed",
        edits=(
            Edit(
                path="sextant/catalogs/microprofile-graphql.yml",
                find="      - { annotation: org.eclipse.microprofile.graphql.Name, arg: value }",
                replace="      - { annotation: org.eclipse.microprofile.graphql.Id, arg: value }",
            ),
        ),
    ),
    "spring-jms.path-from-is-the-destination-attribute": Guard(
        what="`path_from` names the one attribute of `@JmsListener` that IS a destination, and "
        "nothing else",
        why="`subscription` is a real `@JmsListener` attribute, it is a `String` exactly as "
        "`destination` is, it sits beside it, and the post-processor reads both (CP-16 row 4). "
        "It names the DURABLE SUBSCRIPTION a consumer registers under, not the queue or topic "
        "the message arrives on; reading it publishes a subscription name as a JMS "
        "destination, which is an address the broker does not route to",
        edits=(
            Edit(
                path="sextant/catalogs/spring-jms.yml",
                find="    path_from: [destination]",
                replace="    path_from: [destination, subscription]",
            ),
        ),
    ),
    "spring-sqs.path-from-is-the-destination-aliases": Guard(
        what="`path_from` names the destination attribute under both its spellings, and "
        "nothing else",
        why="`maxConcurrentMessages` is a real `@SqsListener` attribute and is not the "
        "destination under any spelling; reading it publishes a THREAD COUNT as a queue "
        "name",
        edits=(
            Edit(
                path="sextant/catalogs/spring-sqs.yml",
                find="    path_from: [value, queueNames]",
                replace="    path_from: [value, queueNames, maxConcurrentMessages]",
            ),
        ),
    ),
    "retrofit.declared-request-methods": Guard(
        what="Retrofit's seven request-method annotations are declared and `@HTTP` is not, "
        "because its verb is a plain `String` this engine cannot read",
        why="`$method_from` extracts a verb from an ENUM constant's symbol, so `@HTTP`'s "
        "plain-string `method` yields the empty string and the row ships with a verb no "
        "evidence supports — and its path lives in `path`, which `path_from` does not "
        "name. Half-implementing it is the failure; the weakening below is exactly that "
        "half-implementation",
        edits=(
            Edit(
                path="sextant/catalogs/retrofit.yml",
                find="      - { fqn: retrofit2.http.OPTIONS, method: [OPTIONS] }",
                replace="      - { fqn: retrofit2.http.OPTIONS, method: [OPTIONS] }\n"
                "      - { fqn: retrofit2.http.HTTP,    method: [REPORT] }",
            ),
            Edit(
                path="sextant/catalogs/retrofit.yml",
                find="    path_from: [value]",
                replace="    path_from: [value, path]",
            ),
        ),
    ),
    "javax-servlet.every-type-is-spelled-javax": Guard(
        what="every type `javax-servlet.yml` names is spelled `javax`, the API it describes",
        why="a `jakarta` name left anywhere in this catalog's `matches` block makes it match "
        "modules compiled against the OTHER API and publish them under a rule measured "
        "elsewhere — the half-applied substitution `test_the_two_spellings_declare_one_"
        "rule` names, seen from the deriving side",
        edits=(
            Edit(
                path="sextant/catalogs/javax-servlet.yml",
                find="javax.servlet",
                replace="jakarta.servlet",
                # 24 since spec 2026-09-19 §5d: the two `request_reads` owners.
                occurrences=24,
            ),
        ),
    ),
    "spring-integration.channels-are-the-channel-attributes": Guard(
        what="`channels` names the annotation arguments that ARE a channel, and nothing else",
        why="`sendTimeout` is a real `@ServiceActivator` attribute, it is a `String` exactly "
        "as the two channel attributes are, and it is not a channel. Reading it files a "
        "`channel_destination` question about a channel called `3000` — sending the "
        "enrichment seat after a destination for a send timeout, in the one table whose "
        "whole purpose is to be answered by a human",
        edits=(
            Edit(
                path="sextant/catalogs/spring-integration.yml",
                find="        - { annotation: org.springframework.integration.annotation."
                "ServiceActivator,\n            arg: inputChannel, direction: inbound }",
                replace="        - { annotation: org.springframework.integration.annotation."
                "ServiceActivator,\n            arg: inputChannel, direction: inbound }\n"
                "        - { annotation: org.springframework.integration.annotation."
                "ServiceActivator,\n            arg: sendTimeout, direction: inbound }",
            ),
        ),
    ),
    "config_join.channel-target-is-a-method": Guard(
        what="an `annotation_value` channel counts only where the annotation's target is a "
        "METHOD — a use on an annotation TYPE is a composition, not a wired handler",
        why="a channel annotation is `@Target`-legal on an annotation type, which is how a "
        "module composes its own stereotype. Nothing subscribes there, so the question "
        "carries a handler symbol that names no method — and the enrichment seat is asked "
        "for the destination of a channel nobody reads. "
        "`scheduled_work.declaration-is-a-method` is the same conjunct one table over",
        edits=(
            Edit(
                path="sextant/application/resolve/engines/config_join.py",
                find="        if target not in methods:",
                replace="        if False:  # guard disabled by scripts/guard_check.py",
            ),
        ),
    ),
    "dependencies.detect-required-is-a-conjunct": Guard(
        what="a catalog declaring `detect.required` derives NOTHING in a module whose build "
        "does not name one of its coordinates",
        why="F2 §3.6. `spring-stomp` and `spring-rsocket` both claim `@MessageMapping`, and "
        "Spring's own handlers scan for it with the SAME `@Controller` predicate — measured, "
        "byte for byte — so no fact about the class separates a STOMP controller from an "
        "RSocket one. The build is the only discriminator there is. Without this conjunct "
        "whichever catalog claims the annotation first publishes the class on ITS protocol, "
        "which is how every RSocket controller in the estate read as `websocket` — and "
        "`protocol` is identity, so DR-5 linked those rows into other consumers' graphs",
        edits=(
            Edit(
                path="sextant/application/resolve/dependencies.py",
                find="    if catalog.style not in DEPENDENCY_GATED and not catalog.detect_required:",
                replace="    if catalog.style not in DEPENDENCY_GATED:  # guard disabled",
            ),
        ),
    ),
    "dependencies.satisfied-by-answers-the-gate": Guard(
        what="a class carrying an annotation only ONE framework defines derives that "
        "framework's row even when the build names none of its coordinates",
        why="F2 §3.6 states it outright — `@ConnectMapping` anywhere is positive RSocket "
        "evidence regardless of the build — and the catalog, the probe and the plan all "
        "claimed it shipped. It had not: `detect.required` gates the WHOLE catalog before "
        "any matching runs, so a module whose build recorded no RSocket coordinate derived "
        "nothing from a `@ConnectMapping` class and asked no question either. Silent, in "
        "exactly the case the sentence was written for — and it is the ordinary Maven case, "
        "where a starter's own transitives never reach the module fact",
        edits=(
            Edit(
                path="sextant/application/resolve/dependencies.py",
                find="    if _carries_satisfying_annotation(workspace, catalog):\n        return None",
                replace="    if False:  # guard disabled by scripts/guard_check.py\n        return None",
            ),
        ),
    ),
    "config_join.indexed-item-exists-through-its-read-fields": Guard(
        what="an `indexed:` item is read into existence only by the fields the block "
        "declares — its predicate list and its peer field; a `<prefix>[N]` carrying only "
        "`id`, `order`, `filters[…]` or `metadata` is no item at all",
        why="spec 2026-09-21 §7b: an item naming no path serves every path, `/**`. Without "
        "this filter an entry whose only keys are the unread ones — an `id`, a filter "
        "list — becomes an item with no predicates and mints a resolved `/**` row for a "
        "route that declares no address and no target",
        edits=(
            Edit(
                path="sextant/application/resolve/engines/config_join.py",
                find="        if not (field.startswith(predicates) or field == peer):\n            continue",
                replace="        if False:  # guard disabled by scripts/guard_check.py\n            continue",
            ),
        ),
    ),
    "config_join.unmapped-binder-derives-no-row": Guard(
        what="a binding whose configured binder name the catalog maps to no protocol derives "
        "NO ROW — never one on the catalog's own declared `protocol:`",
        why="F2 §3.4, and the one defect in this analysis that leaves the bundle. `protocol` "
        "is IDENTITY and DR-5 gates linking on protocol equality, so a row published on a "
        "protocol nobody read links into ANOTHER consumer's graph against endpoints this "
        "module never speaks to, and fails to link to the ones it does. Measured before the "
        "fix (`scripts/probes/w13_stream_binding.md`): a module bound to `rocketmq` derived a "
        "row on `kafka`, complete and confident, with no question anywhere. The catalog "
        "called that 'a gap to grow this map from, never a guessed protocol' and a test "
        "pinned it. "
        "It is guarded HERE rather than in `test_defaulted_identity_values.py` because that "
        "audit reads shipped CATALOGS offline and this default lived in an engine's fallback "
        "— the ratchet hole §3.4 names in the same breath as the defect",
        edits=(
            Edit(
                path="sextant/application/resolve/engines/config_join.py",
                find="            if protocol is None:\n                # The configured binder maps to no protocol",
                replace="            if False:  # guard disabled by scripts/guard_check.py\n                # The configured binder maps to no protocol",
            ),
        ),
    ),
    "config_join.unselected-cardinality": Guard(
        what="where the selection key names nobody and the catalog declares "
        "`unselected_binds: sole`, two or more candidates bind NOTHING",
        why="F2 §3.4's cardinality conjunct, mirrored from the framework's own selection code: "
        "`SimpleFunctionRegistry.normalizeFunctionDefinition` opens its guard with "
        "`eligibleFunction.size() == 1`, so with two eligible functions the definition stays "
        "empty and nothing binds. The catalog claimed the opposite in prose — 'every "
        "candidate binds, the framework's own default' — and derived one endpoint per bean "
        "for an application that serves neither",
        edits=(
            Edit(
                path="sextant/application/resolve/engines/config_join.py",
                find="    if declared == _ALL or len(candidates) == 1:",
                replace="    if True:  # guard disabled by scripts/guard_check.py",
            ),
        ),
    ),
    "jakarta-servlet.every-type-is-spelled-jakarta": Guard(
        what="every type `jakarta-servlet.yml` names is spelled `jakarta`, the API it describes",
        why="the mirror leak: a `javax` name kept in the jakarta catalog would match legacy "
        "classes and publish them under a rule measured against the current API",
        edits=(
            Edit(
                path="sextant/catalogs/jakarta-servlet.yml",
                find="jakarta.servlet",
                replace="javax.servlet",
                # 25 since spec 2026-09-19 §5d: the two `request_reads` owners.
                occurrences=25,
            ),
        ),
    ),
    # --- 2Q `I1`, the root set ---------------------------------------------
    "roots.a-row-naming-no-handler-is-no-root": Guard(
        what="an endpoint row becomes a root only where it NAMES a handler — and an exposed "
        "row need not: a functional route's handler is a lambda no chain reader named",
        why="the missing value does not stay missing. Read anyway it becomes a root handler "
        "in its own right — a symbol no fact ever declared — and a walk starts at a method "
        "that does not exist, finding nothing and saying nothing about why. The compiled "
        "fixture carries five such rows, so this is one root in thirteen that would be a "
        "trace of nothing published beside traces that are real",
        edits=(
            Edit(
                path=_ROOTS,
                find='        if row["handler"] is not None and str(row["direction"]) != str(Direction.OUTBOUND)',
                replace='        if str(row["direction"]) != str(Direction.OUTBOUND)  # guard disabled',
            ),
        ),
    ),
    "roots.only-a-row-the-module-exposes-is-a-root": Guard(
        what="only an endpoint row the module EXPOSES becomes a root — a row the module "
        "calls is a call it makes, whatever method the row happens to name",
        why="`CONTEXT.md`'s definition, and the wire direction inverted when it is gone: a "
        "trace from an outbound row starts at whatever method built the REQUEST and reports "
        "a client-side call as a place work begins. The test that measures it stages a row "
        "no engine writes today (an outbound row naming a handler) on purpose — the rule has "
        "to hold on the day one does, rather than by accident of which column currently "
        "happens to be NULL",
        edits=(
            Edit(
                path=_ROOTS,
                find='        if row["handler"] is not None and str(row["direction"]) != str(Direction.OUTBOUND)',
                replace='        if row["handler"] is not None  # guard disabled',
            ),
        ),
    ),
    "roots.the-address-is-the-one-the-endpoint-row-ends-with": Guard(
        what="`record_roots` runs BELOW `apply_protocol_hints`, so the address it copies "
        "onto a root is the one the `endpoints` row finishes the resolve carrying",
        why="a root carries a wire address as of 2Q's close, and a copied fact that can "
        "drift from its source is exactly what D01 §6 forbids. Run above the "
        "reclassification and the copy is taken mid-write: the orders-service fixture "
        "moves its SSE routes out of `http`, so `roots` says `http /events/emitter` while "
        "`endpoints` says `sse /events/emitter` — one address spelled two ways in one "
        "workspace, with the document's own trace section quoting the stale half",
        # Each pass runs inside its own `with _timed(...)` block (b2bdbb9), so the anchor
        # is the whole block: removing the call alone left an empty block behind and
        # re-inserting it at the method's own indentation put it outside the other one —
        # `--guards` then failed to import the copied tree before it reached any guard.
        edits=(
            Edit(
                path=_PIPELINE,
                find='    with _timed("record_roots"):\n        record_roots(workspace)\n',
                replace="",
            ),
            Edit(
                path=_PIPELINE,
                find='    with _timed("apply_protocol_hints"):\n'
                "        apply_protocol_hints(workspace, declared)\n",
                replace='    with _timed("record_roots"):\n'
                "        record_roots(workspace)  # guard disabled\n"
                '    with _timed("apply_protocol_hints"):\n'
                "        apply_protocol_hints(workspace, declared)\n",
            ),
        ),
    ),
    # --- 2Q `G4`, the call graph and the walk over it ----------------------
    "call_edges.a-lambda-site-names-the-body-not-the-bootstrap": Guard(
        what="an `invokedynamic` edge names the body the site CREATES "
        "(`call_site.implementation`, capability 9.17), never the bootstrap factory its own "
        "target names",
        why="the target of every lambda site in every module is the same platform factory, "
        "so reading it makes each one a third-party terminal and a trace stops at the line "
        "that creates a lambda. The business logic inside is then invisible: a "
        "`forEach(x -> mapper.insert(x))` reports `forEach` and never the persistence. "
        "Measured on `macrozheng/mall`'s `mall-admin` — fifteen bodies reached this way, "
        "seven of them holding a terminal no other path reaches",
        edits=(
            Edit(
                path=_CALL_EDGES,
                find='    if str(site["invoke_kind"]) == DYNAMIC:',
                replace="    if False:  # guard disabled by scripts/guard_check.py",
            ),
        ),
    ),
    "call_edges.a-lambda-site-creating-no-body-is-no-edge": Guard(
        what="an `invokedynamic` that names no implementation contributes NO edge — the key "
        "is written only where the bootstrap creates a body",
        why="not every `invokedynamic` is a lambda: string concatenation compiles to one "
        "whose bootstrap is a compiler artifact rather than a call the program makes. The "
        "missing value does not stay missing — read anyway it becomes an edge to the "
        "four-character text `None`, a symbol no fact ever declared, once per concatenated "
        "string in the module (56 of `mall-admin`'s 74 `dynamic` sites)",
        edits=(
            Edit(
                path=_CALL_EDGES,
                find="        if implementation is None:\n            return None, []\n",
                replace="",
            ),
        ),
    ),
    "call_edges.a-callee-with-no-body-read-is-still-a-row": Guard(
        what="a call site whose callee's body this workspace never read is written as a row "
        "with a NULL `callee` — the boundary is a row, not an absence",
        why='"this call leaves the module here" and "this method makes no calls" are '
        "different answers, and dropping the row makes them identical. Every third-party "
        "terminal disappears from every trace — 1,966 of `mall-admin`'s 2,608 edges — and "
        "what is left reads as a service that reaches no database, no cache and no object "
        "store, which is the second sin at full volume",
        edits=(
            Edit(
                path=_CALL_EDGES,
                find="    reached: list[str | None] = list(callees) or [None]",
                replace="    reached: list[str | None] = list(callees)  # guard disabled",
            ),
        ),
    ),
    "trace.a-callee-on-the-current-path-is-a-cycle": Guard(
        what="a callee already on the path from the root is reported as a `cycle`, which is "
        "a different answer from a method shown elsewhere in the same trace",
        why="the walk still terminates without it — the expanded set catches the second "
        "visit — so the loss is not a hang but a WORD: a self-recursive method reports "
        '`revisited`, which says "shown elsewhere in this trace" about a method calling '
        "ITSELF. A reader looking for recursion finds none, on every recursive method in "
        "the module, and `mall-admin` has one reachable only through a lambda body",
        edits=(
            Edit(
                path=_TRACE,
                find="    if callee in path:\n        return TraceStop.CYCLE\n",
                replace="",
            ),
        ),
    ),
    # --- 2Q, the shared dispatch rule --------------------------------------
    "dispatch.callee-descriptor-is-stripped-to-bare": Guard(
        what="the method a return flow joins TO is keyed by its BARE descriptor, because "
        "the call-site side composes a bare one and a callee may live in a library",
        why="OI-4 on its third appearance, and the first two each shipped: one identity, two "
        "string spellings, a join across them matching nothing on a real module while every "
        "fixture that spells symbols bare stays green — round 1's `F6`, then 2O Task 10 with "
        "six green tests and zero rows. G1 and G2 discharged it in OPPOSITE directions on "
        "purpose (`call_site.implementation` bare, `method_return.method` module-prefixed), "
        "so this join strips exactly one side and getting it wrong is not a partial answer: "
        "it is an EMPTY table on every real module, and a trace that reports every service "
        "call as a terminal",
        edits=(
            Edit(
                path=_DISPATCH,
                find="        bodies[bare_descriptor(symbol)].append(symbol)",
                replace="        bodies[symbol].append(symbol)  # guard disabled",
            ),
        ),
    ),
    "dispatch.exact-dispatch-admits-no-override": Guard(
        what="only `invokevirtual` and `invokeinterface` admit an implementation as a "
        "candidate — a static, special or constructor call names the method that runs",
        why="the JVM's own rule, mirrored rather than approximated (DR-6). A static method "
        "is HIDDEN by a subclass's, never overridden, and a private or `super.` call is not "
        "dispatched at all. Without the conjunct every such call narrows to a set that "
        "includes a body the JVM will never reach there — a candidate for code that cannot "
        "run, published beside the one that does, with the site's own tier downgraded from "
        "`resolved` to `narrowed` to say so",
        edits=(
            Edit(
                path=_DISPATCH,
                find='        if site["invoke_kind"] not in VIRTUAL_DISPATCH:\n            return found\n',
                replace="",
            ),
        ),
    ),
    # --- the read gate ------------------------------------------------------
    "api.workspace-stamp-matches-the-running-build": Guard(
        what="`render`/`enrich`/`export` compare the three stamps `metadata.json` records "
        "against the build now running, and refuse a workspace that disagrees",
        why="D01 §7's re-derivation rule, which was documentation until 2Q gave the walk a "
        "reader (OI-24). A workspace derived before a table existed answers that table's "
        "query with NO ROWS, and an empty table is byte-identical to a module that genuinely "
        "has none — so a stale `.sextant` renders `## Traces` as `None found.` for a service "
        "with 160 endpoints, and the document says nothing about why. Every other member of "
        "the family is worse: the same facts through changed derivation logic publish rows "
        "that are wrong rather than missing",
        edits=(
            Edit(
                path=_API,
                find="        if found != running\n",
                replace="        if found != running and False  # guard disabled\n",
            ),
        ),
    ),
    # --- `## Traces`, the rendered walk -------------------------------------
    "render_trace.an-arrow-ends-at-the-body-that-was-expanded": Guard(
        what="a sequence-diagram arrow ends at the `callee` the walk expanded, falling back "
        "to the compiler-written `target` only where no body was read",
        why="drawing the DECLARED type breaks the diagram outright rather than merely "
        "reading oddly. On `/order/list` the arrow lands on `OmsOrderService`, and "
        "`OmsOrderServiceImpl` then sends four messages nobody ever sent it — a lifeline "
        "that appears from nowhere. A reader cannot follow it, and the one thing a sequence "
        "diagram exists to show, who calls whom, is the thing it stops showing",
        edits=(
            Edit(
                path=_DOCUMENT,
                find="    return step.target if step.callee is None else bare_descriptor(step.callee)",
                replace="    return step.target  # guard disabled",
            ),
        ),
    ),
    "render_trace.a-trace-is-named-by-the-address-that-reaches-it": Guard(
        what="a trace's summary row and its block header carry every wire address that "
        "reaches its root, where the root has one",
        why="this is the defect 2Q shipped with. A trace named by a handler descriptor and "
        "a kind puts `GET /order/list` NOWHERE in the section, so finding the trace for an "
        "endpoint requires already knowing the descriptor — the one thing a reader who "
        "knows a URL does not have. On `mall-admin` that is 160 traces a reader cannot "
        "navigate to, which is a section that is present and undeliverable",
        edits=(
            Edit(
                path=_DOCUMENT,
                find="    if not root.identities:\n        return _text(_NO_WIRE_ADDRESS)\n",
                replace="    if True:  # guard disabled\n        return _text(_NO_WIRE_ADDRESS)\n",
            ),
        ),
    ),
    "render_trace.two-types-one-simple-name-are-two-lifelines": Guard(
        what="two distinct owning types whose SIMPLE names collide both fall back to their "
        "full descriptors as lifeline labels",
        why="`_disambiguated_shape_names`' rule, and not a cosmetic one: two lifelines both "
        "labelled `Order` are read as one type, and the diagram then asserts a call between "
        "things that never touched. A package name is the only thing separating "
        "`a/one/Order` from `a/two/Order`, and dropping it publishes a relationship nobody "
        "measured",
        edits=(
            Edit(
                path=_DOCUMENT,
                find="            labels[participants[key]] = name if len(colliding) == 1 else without_type_marker(key)",
                replace="            labels[participants[key]] = name  # guard disabled",
            ),
        ),
    ),
    "render_trace.a-dynamic-step-says-the-body-is-created-not-called": Guard(
        what="a step whose `invoke_kind` is `dynamic` carries `(dynamic)` on its arrow",
        why="an `invokedynamic` site names the body it CREATES; the lambda runs later, "
        "elsewhere, if at all. Without the marker a `list.forEach(x -> mapper.insert(x))` "
        "draws as an insert happening at that line — an execution claim the graph does not "
        "make, on the 15 lambda bodies `mall-admin` alone reaches",
        edits=(
            Edit(
                path=_DOCUMENT,
                find='    if step.invoke_kind == "dynamic":\n        label = f"{label} (dynamic)"\n',
                replace="",
            ),
        ),
    ),
    "render_trace.an-arrow-says-where-the-walk-stopped": Guard(
        what="a step the walk did not expand carries its `TraceStop` in brackets on the arrow",
        why="where a trace ENDS is the single most important fact in its diagram. An "
        "unmarked arrow into a lifeline nobody entered is indistinguishable from one into a "
        "lifeline fully explored, so a diagram whose every branch stopped at the "
        "third-party boundary reads as a complete picture of a shallow system — 1,966 of "
        "`mall-admin`'s 2,608 edges are exactly that",
        edits=(
            Edit(
                path=_DOCUMENT,
                find='    if step.stop is not None:\n        label = f"{label} [{step.stop}]"\n',
                replace="",
            ),
        ),
    ),
    "render_trace.every-sequence-diagram-states-its-elision": Guard(
        what="every machine sequence diagram carries an `elides` statement",
        why="`DiagramClaim.elides`' own rule applied to the machine half — *a simplified "
        "diagram that does not say it is simplified is a diagram that lies about the "
        "system's size*. A trace diagram is simplified by construction: it draws no "
        "lifeline for a body the walk never entered, and no subtree for a method expanded "
        "elsewhere. Without the statement it claims to be the whole system",
        edits=(
            Edit(
                path=_DOCUMENT,
                find="                elides=_trace_elision(trace),",
                replace="                elides=None,  # guard disabled",
            ),
        ),
    ),
}


# Tests measured to survive the guard they name, and the direction this list
# travels.
#
# An ALLOWLIST in the sense §8.3 requires of a rule made enforceable: the audit
# of every site the rule governs on the day it landed, enumerated so that a
# NEWLY-ADDED non-discriminating test fails immediately and an existing one is a
# deliberate entry a reader can see in a diff. It is not an exemption — every
# entry is a near-miss counted as §10 coverage that measures nothing, which is
# more dangerous than no test at all, because the coverage file counts it.
#
# Listed rather than counted, and it does not travel in the direction of getting
# longer. Retiring an entry means the test was rewritten to negate its guard's
# conjunct alone; `--check`'s second half refuses an entry that has quietly
# started to discriminate, so the list cannot rot into a record of nothing.
#
# **It is EMPTY, and that is the shrink-only half having reached zero rather
# than a list nobody wrote.** The six entries the harness's first audit
# recorded are all closed: `A-M2`'s three servlet near-misses and sweep 1's
# `GenericServlet` one now declare a dispatch member, so there is an outcome
# for the guard's absence to change; the `spring-rabbit` handler near-miss
# names the addresses-nothing gate that was actually holding it up, which is
# also one of sweep 1's S1-MAJ-1 unnamed guards closed; and the
# `spring-actuator` one carries no marker at all, because its emptiness has two
# independent causes and pins neither (see the registry note above it).
#
# An entry that has started to discriminate fails the run, so this cannot rot
# into a record of nothing — and an addition to it is a deliberate edit a
# reader sees in a diff, which is the whole point of listing rather than
# counting.
_DOES_NOT_DISCRIMINATE_YET: frozenset[tuple[str, str]] = frozenset()


@dataclass
class Outcome:
    """What one guard's run measured, per test."""

    guard_id: str
    killed: list[str] = field(default_factory=list)
    survived: list[str] = field(default_factory=list)
    uncontrolled: list[str] = field(default_factory=list)


def pinned_tests() -> dict[str, list[str]]:
    """Guard id -> the `pins`-marked tests naming it, as `path::function`.

    Read statically off the AST, exactly as `test_catalog_near_miss_coverage.py`
    reads `declines`: the marker is a decorator, which the AST answers for
    without importing a thousand fixtures.

    A parametrized test contributes its FUNCTION node id, so pytest runs every
    case and this file judges the function as a whole — a guard is killed only
    when the function fails, and one case surviving a mutation the others catch
    is not a fact about the guard.
    """
    found: dict[str, list[str]] = {}
    for path in sorted(TESTS.rglob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            for guard_id in _pinned_ids(node):
                node_id = f"{path.relative_to(REPO).as_posix()}::{node.name}"
                found.setdefault(guard_id, []).append(node_id)
    return found


def _pinned_ids(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    """The guard ids a `@pytest.mark.pins("...")` decorator names."""
    ids = []
    for decorator in node.decorator_list:
        if not isinstance(decorator, ast.Call):
            continue
        target = decorator.func
        if not (isinstance(target, ast.Attribute) and target.attr == "pins"):
            continue
        for argument in decorator.args:
            if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                ids.append(argument.value)
    return ids


def apply_edits(tree: Path, guard: Guard) -> None:
    """Disable `guard` inside the copied tree at `tree`.

    Raises `LookupError` when an anchor does not occur exactly as many times as
    the registry declares — a stale entry must stop the run, never silently
    apply nothing and report every test as non-discriminating.
    """
    for edit in guard.edits:
        path = tree / "src" / edit.path
        text = path.read_text(encoding="utf-8")
        actual = text.count(edit.find)
        if actual != edit.occurrences:
            raise LookupError(
                f"{edit.path}: expected {edit.occurrences} occurrence(s) of the anchor, "
                f"found {actual} — the guard registry in scripts/guard_check.py is stale"
            )
        path.write_text(text.replace(edit.find, edit.replace), encoding="utf-8")


def copy_tree(destination: Path) -> Path:
    """`src/`, `tests/` and the pytest ini, copied so the original is never written.

    Enough for a targeted run and nothing more: `pyproject.toml` carries
    `pythonpath = ["src"]` and the marker registrations, and both the SQL
    (`Path(__file__).parent`) and the catalogs (`sextant.resources`) resolve
    inside whichever `src` is imported. Tests reading
    `Path(__file__).parents[2] / "src"` land in the copy too, which is why
    `tests/` is copied rather than run from the repository.
    """
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc")
    shutil.copytree(REPO / "src", destination / "src", ignore=ignore)
    shutil.copytree(REPO / "tests", destination / "tests", ignore=ignore)
    shutil.copy2(REPO / "pyproject.toml", destination / "pyproject.toml")
    # The stub library `tests/conftest.py`'s session fixture reads, and NOT the
    # rest of `fixtures/` (37MB of compiled modules no declining test touches).
    # `copy2` preserves mtimes, so `fixture_stub.is_current` answers the same
    # here as it does in the repository and the offline `mvn` build is skipped.
    #
    # Copying this little is safe because the control run is what catches the
    # mistake: a pinned test needing some other fixture fails unmutated and is
    # reported unmeasurable, never counted as though it had discriminated. That
    # stops being true if the control is ever removed.
    (destination / "fixtures").mkdir()
    shutil.copy2(REPO / "fixtures" / "pom.xml", destination / "fixtures" / "pom.xml")
    for named in (
        "orders-soap-client",
        "orders-pathprefixes",
        "orders-fieldheld",
        "orders-pathvars",
    ):
        # `orders-pathprefixes` is here for one guard: the prefix/pattern PAIRING, whose
        # failure shape is two real packages served under each other's prefix. Nothing
        # synthetic can state it — the two values are paired by the path they left through,
        # which exists only in real facts — so the test that pins it is an e2e one, and an
        # e2e test needs its fixture. 90 KB of sources and classes, and the stamp's mtime
        # survives `copy2`, so no `mvn` runs here either.
        shutil.copytree(REPO / "fixtures" / named, destination / "fixtures" / named, ignore=ignore)
    return destination


def run_tests(tree: Path, node_ids: list[str]) -> dict[str, bool]:
    """`{node id: passed}` for every named test, run inside `tree`.

    Outcomes are read from pytest's own JUnit XML rather than from its exit
    code, because one run answers for several tests at once and the exit code
    answers for none of them individually. A parametrized function passes only
    when every one of its cases did.
    """
    report = tree / "guard-check.xml"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "--no-header",
            "-p",
            "no:cacheprovider",
            f"--junit-xml={report}",
            *node_ids,
        ],
        cwd=tree,
        capture_output=True,
        text=True,
        check=False,
    )
    if not report.is_file():
        raise RuntimeError(f"pytest wrote no report for {node_ids}")
    passed = dict.fromkeys(node_ids, True)
    for case in ElementTree.parse(report).iter("testcase"):
        node_id = _node_id_of(case)
        if node_id in passed and _case_failed(case):
            passed[node_id] = False
    report.unlink()
    return passed


def _node_id_of(case: ElementTree.Element) -> str:
    """`tests/a/test_b.py::test_c` from a JUnit `testcase`'s dotted classname
    and its possibly-parametrized name."""
    path = (case.get("classname") or "").replace(".", "/") + ".py"
    return f"{path}::{(case.get('name') or '').split('[')[0]}"


def _case_failed(case: ElementTree.Element) -> bool:
    return any(case.find(kind) is not None for kind in ("failure", "error"))


def check(guard_ids: list[str]) -> tuple[list[Outcome], list[str]]:
    """Measure each guard, returning its outcomes and any registry complaints."""
    pinned = pinned_tests()
    complaints = [
        f"{guard_id}: no test names this guard"
        for guard_id in guard_ids
        if not pinned.get(guard_id)
    ]
    outcomes = []
    with tempfile.TemporaryDirectory(prefix="sextant-guard-check-") as scratch:
        tree = copy_tree(Path(scratch) / "tree")
        originals = {
            edit.path: (tree / "src" / edit.path).read_text(encoding="utf-8")
            for guard_id in guard_ids
            for edit in GUARDS[guard_id].edits
        }
        for guard_id in guard_ids:
            node_ids = pinned.get(guard_id, [])
            if not node_ids:
                continue
            outcome = Outcome(guard_id=guard_id)
            control = run_tests(tree, node_ids)
            outcome.uncontrolled = sorted(node for node, ok in control.items() if not ok)
            measurable = [node for node in node_ids if control[node]]
            if measurable:
                apply_edits(tree, GUARDS[guard_id])
                mutated = run_tests(tree, measurable)
                for path, text in originals.items():
                    (tree / "src" / path).write_text(text, encoding="utf-8")
                outcome.killed = sorted(node for node, ok in mutated.items() if not ok)
                outcome.survived = sorted(node for node, ok in mutated.items() if ok)
            outcomes.append(outcome)
    return outcomes, complaints


def report(outcomes: list[Outcome], complaints: list[str]) -> int:
    """Print the run and return the process exit code."""
    surviving: set[tuple[str, str]] = set()
    uncontrolled: list[str] = []
    for outcome in outcomes:
        guard = GUARDS[outcome.guard_id]
        print(f"\n\033[1m{outcome.guard_id}\033[0m — {guard.what}")
        for node in outcome.killed:
            print(f"  \033[32mkilled  \033[0m {node}")
        for node in outcome.survived:
            print(f"  \033[31mSURVIVED\033[0m {node}")
            surviving.add((node, outcome.guard_id))
        for node in outcome.uncontrolled:
            print(f"  \033[33mNO CONTROL\033[0m {node} (fails unmutated — unmeasurable)")
            uncontrolled.append(f"{node} ({outcome.guard_id})")

    new = sorted(surviving - _DOES_NOT_DISCRIMINATE_YET)
    fixed = sorted(_DOES_NOT_DISCRIMINATE_YET - surviving - _unmeasured(outcomes))
    print(
        f"\n{sum(len(o.killed) for o in outcomes)} killed, "
        f"{len(surviving)} survived, {len(uncontrolled)} unmeasurable"
    )
    for node, guard_id in new:
        print(
            f"\n\033[31mNOT DISCRIMINATING\033[0m {node}\n"
            f"  names guard `{guard_id}`, which was disabled, and still passed.\n"
            f"  {GUARDS[guard_id].why}."
        )
    for node, guard_id in fixed:
        print(
            f"\n\033[31mSTALE ALLOWLIST ENTRY\033[0m {node} / {guard_id}\n"
            "  now discriminates — remove it from _DOES_NOT_DISCRIMINATE_YET."
        )
    if uncontrolled:
        print("\n\033[31mUNMEASURABLE\033[0m — these fail with NO guard disabled:")
        for entry in uncontrolled:
            print(f"  - {entry}")
    if new or fixed or uncontrolled or complaints:
        for complaint in complaints:
            print(f"\n\033[31mREGISTRY\033[0m {complaint}")
        return 1
    print("\n\033[32mevery pinned test discriminates, or is a listed entry\033[0m")
    return 0


def _unmeasured(outcomes: list[Outcome]) -> set[tuple[str, str]]:
    """Allowlist entries this run did not measure — a partial run must not
    report an untouched entry as fixed."""
    measured = {
        (node, outcome.guard_id)
        for outcome in outcomes
        for node in (*outcome.killed, *outcome.survived)
    }
    return {entry for entry in _DOES_NOT_DISCRIMINATE_YET if entry not in measured}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("guard_id", nargs="*", help="guards to measure (default: all)")
    parser.add_argument("--list", action="store_true", help="print the registry and exit")
    arguments = parser.parse_args(argv)
    if arguments.list:
        for guard_id, guard in sorted(GUARDS.items()):
            print(f"{guard_id}\n  {guard.what}")
        return 0
    unknown = sorted(set(arguments.guard_id) - set(GUARDS))
    if unknown:
        parser.error(f"no such guard: {', '.join(unknown)}")
    return report(*check(sorted(arguments.guard_id or GUARDS)))


if __name__ == "__main__":
    raise SystemExit(main())
