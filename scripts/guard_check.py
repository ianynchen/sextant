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
_SCHEDULED_WORK = "sextant/application/resolve/engines/scheduled_work.py"
_ERROR_ADVICE = "sextant/application/resolve/engines/error_advice.py"


GUARDS: dict[str, Guard] = {
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
                find='        if site["owner"] != owner:',
                replace="        if False:  # guard disabled by scripts/guard_check.py",
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
                find='            if site["owner"] == root["owner"] and site["name"] '
                '== root["method"]',
                replace='            if site["owner"] == root["owner"]  # guard disabled',
            ),
        ),
    ),
    # --- `supertype_dispatch` ---------------------------------------------
    "supertype_dispatch.declared-supertype": Guard(
        what="a class matches only when its DIRECT `superclass` is the descriptor the "
        "catalog names, package included",
        why="ordinary inheritance is not evidence of anything (the C-1 lesson). Comparing "
        "simple names alone would serve a `jakarta` module from the `javax` catalog and "
        "publish it under a rule measured against the other API",
        edits=(
            Edit(
                path=_SUPERTYPE_DISPATCH,
                find='        if bare_descriptor(str(row["superclass"])) != supertype:',
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
                find="        tuple(type_descriptor(str(parameter)) for parameter in "
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
                find="        if no_repository_bean not in annotations.get(parent, {}):",
                replace="        if False:  # guard disabled by scripts/guard_check.py",
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
                find='            if row["annotation"] == handler_fqn and str(row["target"]) '
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
