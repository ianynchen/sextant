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
_DERIVE_ENDPOINTS = "sextant/storage/duckdb/derive_endpoints.sql"
_ANNOTATION_DRIVEN = "sextant/application/resolve/engines/annotation_driven.py"
_EFFECTIVE_ANNOTATIONS = "sextant/application/resolve/effective_annotations.py"
_SCHEDULED_WORK = "sextant/application/resolve/engines/scheduled_work.py"
_ERROR_ADVICE = "sextant/application/resolve/engines/error_advice.py"
_ARGUMENTS = "sextant/application/resolve/shapes/arguments.py"
_DISPATCH = "sextant/application/resolve/dispatch.py"
_ROOTS = "sextant/application/resolve/roots.py"
_PIPELINE = "sextant/application/resolve/pipeline.py"
_CALL_EDGES = "sextant/application/resolve/call_edges.py"
_TRACE = "sextant/application/query/trace.py"
_API = "sextant/api.py"
_DOCUMENT = "sextant/egress/render/document.py"


GUARDS: dict[str, Guard] = {
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
                find='        if site["owner"] not in owners:',
                replace="        if False:  # guard disabled by scripts/guard_check.py",
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
                find='            if site["owner"] in root["owners"] and site["name"] '
                '== root["method"]',
                replace='            if site["owner"] in root["owners"]  # guard disabled',
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
                # The same join, written at four places in the file (an
                # annotated declaration, the class gate, the member rule's
                # exclusion, and the prefix scan). One guard, so all four move
                # together — disabling it at one site alone would measure a
                # different question from the one the catalogs' near-misses ask.
                occurrences=4,
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
                find="    WHERE ($type_annotation IS NULL OR c.type_symbol IS NOT NULL)",
                replace="    WHERE TRUE  -- guard disabled by scripts/guard_check.py",
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
                replace="        ($flip_direction IS NOT NULL) AS flipped,  -- guard disabled",
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
                replace="        $path_fallback AS path_fallback,\n"
                "        $path_fallback_prefixes::VARCHAR[] AS path_fallback_prefixes",
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
        "Q4), and both catalogs that declare `members: public_methods` are JAX-WS. Without "
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
                occurrences=22,
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
                occurrences=23,
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
        edits=(
            Edit(path=_PIPELINE, find="    record_roots(workspace)\n", replace=""),
            Edit(
                path=_PIPELINE,
                find="    apply_protocol_hints(workspace, declared)\n",
                replace="    record_roots(workspace)  # guard disabled\n"
                "    apply_protocol_hints(workspace, declared)\n",
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
    shutil.copytree(
        REPO / "fixtures" / "orders-soap-client",
        destination / "fixtures" / "orders-soap-client",
        ignore=ignore,
    )
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
