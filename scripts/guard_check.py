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
# The chain walk `fluent` derives from (Quartz spec 2026-10-28 §3d), moved out of `_FLUENT`
# whole, with the guards on the walk's own rules.
_CHAINS = "sextant/application/resolve/shapes/chains.py"
# The stitcher (M06), whose guards arrived with the reactor linking spec.
_PARTICIPANTS = "sextant/application/stitch/participants.py"
_LINKS = "sextant/application/stitch/links.py"
_SYSTEM_RENDER = "sextant/egress/render/system.py"
_GATEWAY = "sextant/application/stitch/gateway.py"
_WORKSPACE = "sextant/storage/duckdb/workspace.py"
_COMBINATOR = "sextant/application/resolve/engines/combinator.py"
_DERIVE_ENDPOINTS = "sextant/storage/duckdb/derive_endpoints.sql"
_ANNOTATION_DRIVEN = "sextant/application/resolve/engines/annotation_driven.py"
_ENDPOINTS_DRIVER = "sextant/application/resolve/endpoints.py"
_EFFECTIVE_ANNOTATIONS = "sextant/application/resolve/effective_annotations.py"
_EFFECTIVE_CALLS = "sextant/application/resolve/effective_calls.py"
_CHAIN_TEXT = "sextant/application/resolve/shapes/chain_text.py"
_SCHEDULED_CHAIN = "sextant/application/resolve/engines/scheduled_chain.py"
_QUARTZ_CATALOG = "sextant/catalogs/quartz.yml"
_SCHEDULED_WORK = "sextant/application/resolve/engines/scheduled_work.py"
_RESOLVED_SCHEDULES = "sextant/application/resolve/resolved_schedules.py"
_CONFIG = "sextant/application/resolve/config.py"
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
_VOCABULARY = "sextant/application/boundary/vocabulary.py"
_DIFF = "sextant/application/boundary/diff.py"
_BOUNDARY_SOURCE = "sextant/application/boundary/source.py"
_OBSERVABILITY = "sextant/application/boundary/observability.py"
_QUESTIONS = "sextant/application/query/questions.py"


GUARDS: dict[str, Guard] = {
    "values.a-branch-of-calls-on-one-receiver-passes-through": Guard(
        what="for the chain reader, a merge whose every candidate is a declared call on one "
        "shared receiver passes through to that receiver's chain",
        why="RuoYi, aurora and NBlog pass the cron builder through a misfire helper that "
        "branches between two builder calls on its parameter; without the pass-through the "
        "walk stops at the branch and the trigger names no source for its runtime cron",
        edits=(
            Edit(
                path=_VALUES,
                find="        if not self._along_receivers:\n            return None\n",
                replace="        if True:  # guard disabled by scripts/guard_check.py\n"
                "            return None\n",
            ),
        ),
    ),
    "values.a-passed-through-branch-keeps-its-calling-context": Guard(
        what="the pass-through resolves the shared receiver on the same path and frames, so "
        "a helper's parameter is the argument at the call the walk came through",
        why="`misfire` is called from `createJob` and from `updateJob`; resolved with no "
        "calling context its parameter reaches both callers' builders, and the rebuilt "
        "trigger's schedule would be attached to the new trigger's entry",
        edits=(
            Edit(
                path=_VALUES,
                find="                (_SLOT, sites[0][0], sites[0][1], RECEIVER), trail, frames\n",
                replace="                (_SLOT, sites[0][0], sites[0][1], RECEIVER), (), ()\n",
            ),
        ),
    ),
    "quartz.a-REBUILT-trigger-is-not-an-entry": Guard(
        what="only a `newTrigger()` root is a trigger entry; `trigger.getTriggerBuilder()` "
        "rebuilds an existing trigger and starts none",
        why="NBlog's and RuoYi's update method rebuilds the trigger it already scheduled for "
        "`rescheduleJob`; reading that chain as a root would publish one schedule twice, as "
        "two triggers, contradicting ruling 3's one entry per new trigger",
        edits=(
            Edit(
                path=_QUARTZ_CATALOG,
                find="    - { owner: org.quartz.TriggerBuilder, method: newTrigger }\n",
                replace="    - { owner: org.quartz.TriggerBuilder, method: newTrigger }\n"
                "    - { owner: [org.quartz.Trigger, org.quartz.CronTrigger], "
                "method: getTriggerBuilder }\n",
            ),
        ),
    ),
    "quartz.KIND-from-the-declared-return-type": Guard(
        what="where the walk to the schedule builder ends before a root, the kind is the type "
        "the producing call is declared to return",
        why="RuoYi, aurora and NBlog pass the cron builder through a misfire helper that "
        "branches; without the declared type their one trigger has no kind and no job here, "
        "and is not derived at all",
        edits=(
            Edit(
                path=_SCHEDULED_CHAIN,
                find='    return context.kinds.get(returned_type(str(producer["descriptor"])) or "")',
                replace="    return None  # guard disabled by scripts/guard_check.py",
            ),
        ),
    ),
    "quartz.a-runtime-cron-is-PARTIAL-not-dropped": Guard(
        what="a cron argument the walk reads no value for keeps its entry, `partial`, naming "
        "the call it stopped at",
        why="every real Quartz application reads its cron off a database row (ruling 2); "
        "dropping those entries would report no schedule for any of them",
        edits=(
            Edit(
                path=_SCHEDULED_CHAIN,
                find="            expression, resolution, source = _expression(answers.get(_VALUE), "
                "root, slot, context)\n",
                replace="            expression, resolution, source = _expression(answers.get(_VALUE), "
                "root, slot, context)\n            if expression is None:\n                continue"
                "  # guard disabled by scripts/guard_check.py\n",
            ),
        ),
    ),
    "quartz.forJob-DEFAULT-group-only": Guard(
        what="`forJob(name)` names the job whose key is that name in the default group, and "
        "no other group's job of the same name",
        why="Quartz's `Key` puts a key written with no group in `DEFAULT` (CP-55 rows 10-18); "
        "matching by name alone would pair a trigger with a job in another group, which "
        "Quartz never runs for it",
        edits=(
            Edit(
                path=_SCHEDULED_CHAIN,
                find="        found.extend((job, path) for job in (context.jobs_by_key or {})"
                ".get(named, ()))",
                replace="        found.extend((job, path) for key, jobs in (context.jobs_by_key "
                'or {}).items() if key.rsplit(".", 1)[-1] == named.rsplit(".", 1)[-1] for job in '
                "jobs)  # guard disabled by scripts/guard_check.py",
            ),
        ),
    ),
    "quartz.QUARTZJOBBEAN-runs-executeInternal": Guard(
        what="where the job's `execute` body is in a jar type the catalog's "
        "`supertype_dispatch` names, the handler is the method that template calls",
        why="every Spring Boot Quartz job extends `QuartzJobBean` and writes "
        "`executeInternal`; without the template every one has no handler and starts no "
        "trace (CP-55 row 19)",
        edits=(
            Edit(
                path=_SCHEDULED_CHAIN,
                find="        template = context.rules.templates.get(",
                replace="        template = {}.get(  # guard disabled by scripts/guard_check.py",
            ),
        ),
    ),
    "quartz.a-JAR-base-gives-NO-handler": Guard(
        what="a job whose `execute` body is in a jar type the catalog does NOT name gets no "
        "handler",
        why="what an unread base class's `execute` does is not known; assuming it calls a "
        "subclass method would name a handler the framework may never run",
        edits=(
            Edit(
                path=_SCHEDULED_CHAIN,
                find="        template = context.rules.templates.get(",
                replace="        template = next(iter(context.rules.templates.values())) or "
                "context.rules.templates.get(  # guard disabled by scripts/guard_check.py",
            ),
        ),
    ),
    "quartz.equal-HANDLERS-collapse": Guard(
        what="several job classes reaching one body are one row",
        why="RuoYi, aurora and NBlog pick between two classes that inherit one `execute`; "
        "without collapsing, one trigger reads as two schedules of the same work",
        edits=(
            Edit(
                path=_SCHEDULED_CHAIN,
                find="        key = (row.name, row.trigger, row.expression, row.source, row.handler, "
                "row.untied)",
                replace="        key = (row.name, row.trigger, row.expression, row.source, row.handler, "
                "row.untied, id(row))  # guard disabled by scripts/guard_check.py",
            ),
        ),
    ),
    "quartz.several-PATHS-are-exact": Guard(
        what="job classes reaching the job on SEPARATE paths (several callers) are a row each "
        "at their own resolution, not `narrowed`",
        why="a closed set of paths is exact (§3c, the walk's multiplicity); marking each "
        "narrowed would say only one of them runs, when every caller's job does",
        edits=(
            Edit(
                path=_SCHEDULED_CHAIN,
                find="                narrowed=narrowed,\n            )\n        )\n    return found\n",
                replace="                narrowed=True,  # guard disabled by scripts/guard_check.py\n"
                "            )\n        )\n    return found\n",
            ),
        ),
    ),
    "quartz.different-BODIES-are-narrowed": Guard(
        what="job classes on one branch reaching different bodies are a row each, `narrowed`",
        why="one of them runs and which is not known; publishing each at `resolved` would "
        "claim both run",
        edits=(
            Edit(
                path=_SCHEDULED_CHAIN,
                find="row.narrowed and len(branched) > 1",
                replace="False",
            ),
        ),
    ),
    "quartz.one-PATH-ties-the-cron-to-its-job": Guard(
        what="the trigger's key, the literal cron and the job's class are read together on "
        "each path, so a value stays with the values its own path gives",
        why="the `QuartzManager.addJob(jobClass, cron)` helper is called with a job and a cron "
        "per caller; read apart, every cron pairs with every job, and two callers publish "
        "four `resolved` rows, two of them a job at a time nobody scheduled it",
        edits=(
            Edit(
                path=_SCHEDULED_CHAIN,
                find="        resolve_positions(context.workspace, positions, context.index, "
                "within=anchor)\n",
                replace="        [dict(zip(positions, combo)) for combo in __import__('itertools')"
                ".product(*([answers[label] for answers in resolve_positions(context.workspace, "
                "{label: at}, context.index)] for label, at in positions.items()))]"
                "  # guard disabled by scripts/guard_check.py\n",
            ),
        ),
    ),
    "quartz.a-row-is-RESOLVED-only-from-one-binding": Guard(
        what="a row's key, cron and job class are read within the path its trigger and job "
        "took to the call that paired them, so every part comes from one binding",
        why="a trigger built in `trigger(cron)` and scheduled by several callers, each with "
        "its own job, reaches every caller's cron; read without the pairing's path, every "
        "cron is published `resolved` beside every job (R19: seven rows, four false)",
        edits=(
            Edit(
                path=_SCHEDULED_CHAIN,
                find="        resolve_positions(context.workspace, positions, context.index, "
                "within=anchor)\n",
                replace="        resolve_positions(context.workspace, positions, context.index)"
                "  # guard disabled by scripts/guard_check.py\n",
            ),
        ),
    ),
    "quartz.a-NAME-is-read-on-its-schedules-path": Guard(
        what="the trigger's key and cron are read within the path the schedule builder took "
        "to `withSchedule`",
        why="`trigger(name, sb)` called with `(n1, cronSchedule(c1))` and `(n2, "
        "cronSchedule(c2))`: read apart from the schedule's path, every name is published "
        "`resolved` beside every cron, two of four rows false",
        edits=(
            Edit(
                path=_SCHEDULED_CHAIN,
                find="            anchor = schedule.path.joined(path)",
                replace="            anchor = path  # guard disabled by scripts/guard_check.py",
            ),
        ),
    ),
    "quartz.an-UNTIED-name-is-NULL": Guard(
        what="in a row no one binding holds, the name is the one every path agrees on, or NULL",
        why="a name read on one path, beside a cron and a job read on others, states a "
        "pairing of name and schedule nothing in the code makes",
        edits=(
            Edit(
                path=_SCHEDULED_CHAIN,
                find="            name=names.pop() if len(names) == 1 else None,",
                replace="            name=next(iter(names), None),"
                "  # guard disabled by scripts/guard_check.py",
            ),
        ),
    ),
    "quartz.an-UNTIED-part-is-NAMED": Guard(
        what="a part of a row read apart that is NULL because the paths disagree on it is "
        "named in the row's `untied`",
        why="without it the NULL reads as `not in the code`, and a reader who looks finds "
        "the value in the code and stops trusting the table (ruled 2026-10-29)",
        edits=(
            Edit(
                path=_SCHEDULED_CHAIN,
                find="            untied=tuple(part for part, varies in untied.items() if varies),",
                replace="            untied=(),  # guard disabled by scripts/guard_check.py",
            ),
        ),
    ),
    "quartz.a-KEYED-job-is-paired-on-its-keys-path": Guard(
        what="a job named by a key a `job_key` call builds is paired on the path the walk "
        "took to that call",
        why="`t(JobKey k, String cron)` called with `(jobKey(a), c1)` and `(jobKey(b), c2)`: "
        "paired on any path, each keyed job is published `resolved` beside each caller's "
        "cron, two of four rows false (R20)",
        edits=(
            Edit(
                path=_SCHEDULED_CHAIN,
                find="    for named, path in keys:\n        found.extend((job, path) for job in "
                "(context.jobs_by_key or {}).get(named, ()))",
                replace="    for named, path in keys:\n        found.extend((job, _ANY_PATH) for job "
                "in (context.jobs_by_key or {}).get(named, ()))  # guard disabled by "
                "scripts/guard_check.py",
            ),
        ),
    ),
    "quartz.an-UNTIED-part-is-kept-only-where-every-path-agrees": Guard(
        what="in a row no one binding holds, the cron is kept only where every path gives "
        "the same one; otherwise it is NULL",
        why="`scheduleJob(id(job), id(trigger(cron)))` in two callers: each cron published "
        "beside each job states pairings no execution builds, even at `partial` (R20)",
        edits=(
            Edit(
                path=_SCHEDULED_CHAIN,
                find="            if len(expressions) == 1\n",
                replace="            if True  # guard disabled by scripts/guard_check.py\n",
            ),
        ),
    ),
    "quartz.paths-through-DIFFERENT-callers-pair-nothing": Guard(
        what="a job and a trigger whose paths to a pairing call disagree on a caller they "
        "crossed out to are no pairing; only two calls of one helper are read apart",
        why="`sched(JobDetail j, Trigger t)` called by x with (A, c1) and y with (B, c2): "
        "treating every failed join as untied publishes A@c2 and B@c1, pairings no "
        "execution builds, callers-squared of them (R21: four callers, twelve false rows)",
        edits=(
            Edit(
                path=_SCHEDULED_CHAIN,
                find="trigger.two_calls_of_one_helper(path) for trigger in triggers",
                replace="True for trigger in triggers  # guard disabled by scripts/guard_check.py",
            ),
        ),
    ),
    "quartz.no-withSchedule-is-the-DEFAULT-schedule": Guard(
        what="a trigger built with no `withSchedule` is an entry on the catalog's "
        "`default_schedule`",
        why="Quartz's `TriggerBuilder.build()` uses `simpleSchedule()` where no schedule was "
        "handed to it, and `newTrigger().withIdentity(..).startNow().build()` is its own "
        "first example; without the default that trigger, and the job it runs, is missing",
        edits=(
            Edit(
                path=_SCHEDULED_CHAIN,
                find="        return [context.default_schedule]",
                replace="        return []  # guard disabled by scripts/guard_check.py",
            ),
        ),
    ),
    "quartz.a-call-ON-the-value-names-where-it-came-from": Guard(
        what="a no-argument call handing back its own receiver's type is read past, and the "
        "call that produced its receiver is the named source",
        why="`cronSchedule(row.getCron().trim())` would name `String#trim()` as where the cron "
        "is read at runtime, which says nothing about where it comes from",
        edits=(
            Edit(
                path=_SCHEDULED_CHAIN,
                find='        if not (call["arguments"] or []) and returned_type(',
                replace='        if False and not (call["arguments"] or []) and returned_type(  '
                "# guard disabled by scripts/guard_check.py",
            ),
        ),
    ),
    "quartz.one-HANDLER-is-one-row-at-the-weaker-word": Guard(
        what="one body reached exactly on one path and through a branch on another is one "
        "row, at the weaker resolution",
        why="two rows for one handler, `resolved` and `narrowed`, state the one trigger twice "
        "and claim the body both certainly and possibly runs",
        edits=(
            Edit(
                path=_SCHEDULED_CHAIN,
                find="            resolution if key not in rows_by_key else "
                "_weaker(rows_by_key[key], resolution)\n",
                replace="            resolution  # guard disabled by scripts/guard_check.py\n",
            ),
        ),
    ),
    "schedules.an-enum-constant-is-written-as-its-type-and-name": Guard(
        what="an `enum` argument (a named constant of its own type) is written as "
        "`Type.CONSTANT` rather than leaving the chain without text",
        why="`withInterval(1, IntervalUnit.HOUR)` is a constant the source wrote; without "
        "the branch the whole chain of the Spring Boot smoke test has no text and its row "
        "goes `partial`, contradicting ruling 4's constants-as-literal-text",
        edits=(
            Edit(
                path=_CHAIN_TEXT,
                find='    if kind == "enum":',
                replace="    if False:  # guard disabled by scripts/guard_check.py",
            ),
        ),
    ),
    "schedules.a-chain-with-a-non-constant-argument-has-no-text": Guard(
        what="a builder chain with an argument that is neither a constant nor a nested call "
        "of constants has no text at all",
        why="a chain written with one hole filled in or skipped reads as a complete "
        "schedule: `withIntervalInSeconds(<read from a row>)` published as "
        "`withIntervalInSeconds()` states a schedule nobody wrote, at a confidence the "
        "reader cannot tell from a real one (ruling 4)",
        edits=(
            Edit(
                path=_CHAIN_TEXT,
                find="\n    return None\n",
                replace="\n    return ''  # guard disabled by scripts/guard_check.py\n",
            ),
        ),
    ),
    "schedules.a-nested-call-is-written-WITH-its-receiver": Guard(
        what="a nested call is written with what it was called on (its type for a static "
        "call, a constant of its own type, a nested call written too), else the chain has "
        "no text",
        why="`withIntervalInMilliseconds(TimeUnit.MINUTES.toMillis(5))` written without its "
        "receiver reads `TimeUnit.toMillis(5)`, a call nobody wrote, published `resolved`",
        edits=(
            Edit(
                path=_CHAIN_TEXT,
                find='    return None if receiver is None else f"{receiver}.{name}({written})"',
                replace="    return f\"{short_class_name(str(site['owner']))}.{name}({written})\""
                "  # guard disabled by scripts/guard_check.py",
            ),
        ),
    ),
    "schedules.a-construction-is-written-as-NEW": Guard(
        what="a nested constructor call is written `new Type(args)`",
        why="`startingDailyAt(new TimeOfDay(9, 0))` written as `TimeOfDay.<init>(9, 0)` is "
        "no code anyone wrote",
        edits=(
            Edit(
                path=_CHAIN_TEXT,
                find="        return f\"new {short_class_name(str(site['owner']))}({written})\"",
                replace="        return f\"{short_class_name(str(site['owner']))}.{name}({written})\""
                "  # guard disabled by scripts/guard_check.py",
            ),
        ),
    ),
    "schedules.a-NESTED-type-is-written-with-a-dot": Guard(
        what="a nested type in a written chain reads `Outer.Inner`, as the source writes it",
        why="the Spring Boot smoke test's row read `DateBuilder$IntervalUnit.HOUR`, the "
        "binary name, which no source spells (OI-223)",
        edits=(
            Edit(
                path=_CHAIN_TEXT,
                find="from sextant.domain.symbols import bare_descriptor, member_name, owner_of, "
                "short_class_name\n",
                replace="from sextant.domain.symbols import bare_descriptor, member_name, owner_of, "
                "simple_name\n\n\ndef short_class_name(symbol):  # guard disabled by "
                "scripts/guard_check.py\n    return simple_name(bare_descriptor(symbol))\n",
            ),
        ),
    ),
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
    "values.an-ACCESSOR-is-not-a-write": Guard(
        what="for a producer-identity reader (`past_accessors`), a call on the value that "
        "takes no argument and hands back an object of another type than its owner does not "
        "open the `escapes` window: it cannot change which call built the value",
        why="RuoYi-Vue, NBlog and aurora all write `jobDetail.getJobDataMap().put(KEY, job)` "
        "between building the job and scheduling it. Without this the accessor is read as "
        "a possible write, the job argument answers `escapes`, and the Quartz handler is "
        "NULL on 3 of the 6 real corpora measured (Quartz Task 11, finding F1)",
        edits=(
            Edit(
                path=_VALUES,
                find="                if self._accessor((method, ordinal)):\n"
                "                    continue\n",
                replace="",
            ),
        ),
    ),
    "values.past-ACCESSORS-is-a-readers-switch": Guard(
        what="only a reader that passes `past_accessors` lets an accessor past the `escapes` "
        "window; the value walk and every other `producers_of` reader keep refusing it",
        why='an accessor can hand back a LIVE view: `topics = Arrays.asList("a", "b"); '
        'topics.listIterator().set("c"); subscribe(topics)` writes into the list through '
        "it. As the default (Quartz fix round 2), the `identified_by` reader published "
        "`a`, `b` as exact topics. Whether that write matters depends on the question: "
        "it cannot change which call BUILT the value, and it can change what it HOLDS",
        edits=(
            Edit(
                path=_VALUES,
                find="        ancestors = self._past_accessors\n",
                replace="        ancestors = self._past_accessors if self._past_accessors is not None "
                "else {}\n",
            ),
        ),
    ),
    "values.an-accessor-of-a-SUPERTYPE-is-not-one": Guard(
        what="a no-argument call handing back a SUPERTYPE of its owner, read off the "
        "hierarchy the reader hands in, stays in the `escapes` window",
        why="an inherited fluent step or an erased self-type bound returns the receiver "
        "itself typed as its supertype, so the call may have replaced the value; only the "
        "owner's own type was excluded before (Quartz fix round 3)",
        edits=(
            Edit(
                path=_VALUES,
                find="            for parent, _, _ in ancestors.get(frontier.pop(), ()):\n",
                replace="            for parent, _, _ in ancestors.get(frontier.pop() + '!', ()):\n",
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
    "arguments.an-unreadable-HOST-is-NAMED-not-a-bare-hole": Guard(
        what="a partly-known address whose LEADING hole is the unread authority publishes "
        "`<host>`, not a bare `{}`",
        why="ruled by the user on 2026-10-18, against the bare hole this shipped with: *"
        "\"I don't think it should be a general purpose holder as {}, since this can mean "
        "anything. It probably should be specific, like {host}, indicating we can't find the "
        'host rather than something else"*. A reader seeing `{}/services/admin` cannot tell '
        "which half was unread, nor tell the hole from a defect in this reader — and "
        "`apollo-portal` publishes eight such rows. Angle brackets rather than braces "
        "because `{name}` is URI-template syntax in every framework modelled here and "
        "`derive_endpoints` reads variable names out of `{…}`, so a `{host}` would be "
        "indistinguishable from a path variable called host",
        edits=(
            Edit(
                path=_ARGUMENTS,
                find="        leading = _holes(path)[:1] if path is not None else ()\n"
                "        if path is not None and leading and path.startswith(leading[0]):",
                replace="        leading = ()  # guard disabled by scripts/guard_check.py\n"
                "        if False:",
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
    "fluent.an-assembled-address-is-read-with-the-URL-reader": Guard(
        what="an address a fluent chain ASSEMBLES is read with the url reader, and the row "
        "carries that reader's own word — so a partly-known address publishes the half it "
        "read, as `single_call` already does",
        why="`OI-144`, and it was two engines giving two answers about one piece of "
        "evidence, which is the disease the shared walk was built to end. The arm asked "
        "`channel_of_answer`, which refuses a template ON PURPOSE — a broker resolves a "
        "destination it is GIVEN and half of one is not a destination — and the row then "
        "recomputed `resolved`/`unresolved`, which threw away `partial` even when the reader "
        "answered it. Measured on one address written once each way: `single_call` published "
        "`<host>/owners` at `partial` while the fluent row published `path` NULL at "
        "`unresolved`, with the peer and the path both sitting in the facts",
        edits=(
            Edit(
                path=_FLUENT,
                find="        assembled = _walked_with(argument, context, (), reader=_assembled_text)",
                replace="        assembled = _walked_with(argument, context, ())  # guard disabled",
            ),
        ),
    ),
    "arguments.a-PEER-is-asked-of-its-own-evidence": Guard(
        what="an address whose host went unread takes its PEER from the identity table, "
        "asked of the first operand alone and only where the answer yields an AUTHORITY",
        why='`OI-138` cause 3. `discoveryClient.getInstances("customers-service")'
        '.get(0).getUri() + "/owners"` states no address anywhere — the host comes from a '
        "registry at runtime — so without this the row says only that something at "
        "`/owners` is called, and `petclinic-genai`'s three calls carry no arrow at all. "
        "**It must stay a SEPARATE question from the join**, which is what `OI-142` "
        "recorded as unclosable the other way: an identity's text is not an address (for a "
        'destination identified as `"orders"` the rendering is a vendor debug string), so '
        "the join is still handed no identities and only an AUTHORITY-yielding answer may "
        "fill the peer column",
        edits=(
            Edit(
                path=_ARGUMENTS,
                find="    named = authority_of(argument, caller, workspace, index, identities)",
                replace="    named = None  # guard disabled by scripts/guard_check.py",
            ),
        ),
    ),
    "stitch.a-route-restricted-to-some-VERBS-composes-only-those": Guard(
        what="a gateway route declaring a `Method` predicate composes links only for those "
        "verbs; one declaring none forwards every verb",
        why="MEASURED as a false fact in the review of PR #56: `Method=GET` in front of a "
        "service serving `GET` and `POST /orders` composed BOTH, and `POST /o/orders` is an "
        "address the gateway rejects before it forwards. The catalog declares the predicate "
        "for exactly this and the first version ignored it",
        edits=(
            Edit(
                path=_GATEWAY,
                find='            if verbs and str(row["method"]).upper() not in verbs:',
                replace="            if False:  # guard disabled by scripts/guard_check.py",
            ),
        ),
    ),
    "stitch.a-COLLIDING-artifact-id-is-named-by-its-coordinate": Guard(
        what="two modules sharing an artifactId are named by their full coordinates, with "
        "the bare artifactId an alias on both",
        why="MEASURED as silent data loss in the review of PR #56: the federation is a map "
        "keyed by `name`, so two participants both called `svc` collapsed to one and the "
        "other's graph was never attached — with nothing to say so. Unique names key the "
        "federation; the shared alias makes a client stating `svc` hit the ambiguity "
        "refusal instead of being linked to whichever the dict kept",
        edits=(
            Edit(
                path=_PARTICIPANTS,
                find="        unique = module_id if short in collided else short",
                replace="        unique = short  # guard disabled by scripts/guard_check.py",
            ),
        ),
    ),
    "stitch.a-gateway-ROUTE-PREFIX-joins-the-paths-the-service-serves": Guard(
        what="a gateway route's literal prefix is joined to each inbound path of the service "
        "its `uri` names, publishing the gateway's own address for that route",
        why="a route declaring `Path=/api/customer/**` in front of `customers-service`'s "
        "`GET /owners/{ownerId}` serves `GET /api/customer/owners/{ownerId}`, and nothing "
        "joined those two halves — the gateway's dependencies read as a destination with no "
        "routes. It is the same join a class-level `@RequestMapping` in front of a method "
        "path already makes, with the halves in two MODULES. Measured: `petclinic`'s four "
        "routes publish 13 endpoint links and `mall-swarm`'s five publish 245, every one "
        "`resolved`",
        edits=(
            Edit(
                path=_GATEWAY,
                find="        for row in served.get(target, ()):",
                replace="        for row in ():  # guard disabled by scripts/guard_check.py",
            ),
        ),
    ),
    "stitch.a-STRIP-that-disagrees-with-the-prefix-REFUSES-the-composition": Guard(
        what="the composition is refused unless the route's strip count equals its prefix's "
        "segment count",
        why="`StripPrefix=N` must remove exactly the prefix being composed. With "
        "`Path=/a/b/**` and `StripPrefix=1` a request to `/a/b/orders` arrives as "
        "`/b/orders`, which the service does not serve — so composing anyway publishes an "
        "address no request takes, which is `M06`'s fabrication rather than imprecision. "
        "Measured off the jar (CP-40, two releases either side of the module rename): the "
        "filter keeps every segment whose index is >= `parts`. The dependency is not lost by "
        "refusing — the `lb://` row still links the two participants",
        edits=(
            Edit(
                path=_GATEWAY,
                find="        if strip is None or strip != len(segments):",
                replace="        if False:  # guard disabled by scripts/guard_check.py",
            ),
        ),
    ),
    "stitch.a-refused-route-composes-NO-endpoint-link": Guard(
        what="a route the gate refused contributes no endpoint link at all",
        why="the refusal has to BE a refusal: a route whose prefix cannot be composed must "
        "leave the participant-level link standing and add nothing, rather than publish a "
        "composed address beside a note saying it could not be composed",
        edits=(
            Edit(
                path=_GATEWAY,
                find="            continue\n        for row in served.get(target, ()):",
                replace="        for row in served.get(target, ()):  # guard disabled",
            ),
        ),
    ),
    "stitch.the-SYSTEM-DOCUMENT-carries-the-link-not-only-the-table": Guard(
        what="every link reaches the system document, naming the caller, the service, the "
        "route and how much the match is worth",
        why="**the document is the result, not the table** (user ruling 2026-10-17). A green "
        "`links` table behind a blank document is a failed delivery, and this tier exists "
        "entirely to state something no module document can: that one module's "
        "`POST /owners/{ownerId}/pets` reaches another's `@PostMapping` of the same route",
        edits=(
            Edit(
                path=_SYSTEM_RENDER,
                find='        lines.append(f"| {source} | `{link.to_participant}` | {endpoint} | {resolution} |")',
                replace="        pass  # guard disabled by scripts/guard_check.py",
            ),
        ),
    ),
    "stitch.the-document-names-every-REFUSAL-with-its-reason": Guard(
        what="an outbound endpoint that matched nothing is in the document WITH the reason "
        "it matched nothing",
        why="`M06`'s honesty obligation, and a count alone cannot carry it: a client naming "
        "a service outside the system is a dependency leaving it, while an address whose "
        "authority went unread is a limit of this analysis. A reader who cannot tell those "
        "apart cannot act on either",
        edits=(
            Edit(
                path=_SYSTEM_RENDER,
                find='            lines.append(f"| `{u.participant}` | {call} | {redactor.redact_text(u.reason)} |")',
                replace='            lines.append(f"| `{u.participant}` | {call} | |")',
            ),
        ),
    ),
    "stitch.UNCALLED-inbound-endpoints-are-a-section-of-their-own": Guard(
        what="an inbound endpoint a link reaches is NOT reported as uncalled",
        why="`M06` requires unmatched outbound and uncalled inbound reported separately "
        "because they are different questions. Reporting a reached endpoint among them "
        "makes the section an inventory rather than a finding, and a reader chasing dead "
        "routes would be handed live ones",
        edits=(
            Edit(
                path=_LINKS,
                find="        if key in reached:\n            continue",
                replace="        if False:  # guard disabled by scripts/guard_check.py\n            continue",
            ),
        ),
    ),
    "stitch.the-document-names-the-ENVIRONMENT-it-resolved-for": Guard(
        what="the system document states which environment its comparisons resolved "
        "configuration values for",
        why="a module's registered name and a gateway's routes are both configuration, so "
        "every link is a statement about ONE environment (`M06` step 0). A document that "
        "did not say which becomes unreadable the first time two environments disagree, and "
        "silently wrong rather than visibly partial",
        edits=(
            Edit(
                path=_SYSTEM_RENDER,
                find='            f"resolving configuration for the `{environment}` environment."',
                replace='            "resolving configuration."  # guard disabled',
            ),
        ),
    ),
    "stitch.a-PEER-the-client-states-settles-who-before-the-path-picks-the-route": Guard(
        what="a peer the client states resolves through the participants' names AND aliases, "
        "settling WHO is called before any path is compared",
        why="`M06`'s key table calls a stated service name the strong HTTP case, and it is "
        "what makes a second module serving the same path harmless. The alias half is "
        "load-bearing and measured: of the distinct names clients state, "
        "`spring-petclinic-microservices` matches 4 of 4 by the registered name and 0 by the "
        "artifactId, while `mall-swarm` matches 5 of 5 the other way — neither source alone "
        "covers both systems, and without aliases petclinic links nothing at all",
        edits=(
            Edit(
                path=_LINKS,
                find="        for name in participant.answers_to():",
                replace="        for name in (participant.name,):  # guard disabled",
            ),
        ),
    ),
    "stitch.a-peer-OUTSIDE-the-system-is-a-finding-not-a-fallback": Guard(
        what="a client naming a service this system does not contain produces NO link — "
        "never a fall through to matching the path instead",
        why="the dangerous failure is not refusing, it is falling through: a module serving "
        "that path would be linked to a call that does not reach it, which is `M06`'s "
        'fabrication rather than imprecision — "and an agent will then reason from it". '
        "The honest row is `M06`'s own finding: a service outside the system, a participant "
        "nobody added, or a dependency nobody documented",
        edits=(
            Edit(
                path=_LINKS,
                find='            return refuse(f"the client names {peer!r}, which is not a participant")',
                replace="            target = None  # guard disabled by scripts/guard_check.py",
            ),
        ),
    ),
    "stitch.an-UNREAD-authority-is-never-matched-by-path-alone": Guard(
        what="an outbound row whose authority went unread mints no link, even where exactly "
        "one participant serves that path",
        why="the user's decision 6, refused 2026-10-19. Uniqueness INSIDE the participant set "
        "cannot rule out a target outside it, so the only key that would link such a row "
        "rests on the half of the address nobody read. Measured cost: 5 of "
        "`apollo-portal`'s 10 outbound rows and 0 elsewhere — and for Apollo the link would "
        "have been correct, which is evidence for the rule rather than proof of it",
        edits=(
            Edit(
                path=_LINKS,
                find="    if path.startswith(UNREADABLE_HOST):",
                replace="    if False:  # guard disabled by scripts/guard_check.py",
            ),
        ),
    ),
    "stitch.a-REGISTERED-name-becomes-an-alias-and-an-equal-one-does-not": Guard(
        what="a module's registered service name becomes an alias, and one equal to the "
        "artifactId does not",
        why="a build coordinate is not a service name — `spring-petclinic-customers-service` "
        "against the `customers-service` every client writes — and the registered name is "
        "what closes that gap. An alias equal to the name says nothing and would restate "
        "every participant beside itself; `mall-swarm`'s six modules are all that case",
        edits=(
            Edit(
                path=_PARTICIPANTS,
                find="        if name is None or name in participant.answers_to():",
                replace="        if name is None:  # guard disabled by scripts/guard_check.py",
            ),
        ),
    ),
    # --- Maven's own classpath (spec 2026-10-21) --------------------------------------
    "detect.mavens-OWN-classpath-answers-for-the-dependency-set": Guard(
        what="where Maven wrote a classpath file, the dependency set is what MAVEN resolved "
        "— transitives included, the version it chose — not what the POM parse declares",
        why="`dependencies.py` says `could not tell` for every framework reached through a "
        "starter while the set is the declared one; the Data REST row and every "
        "version-scoped rule read the same list. Dropping the assignment leaves the file "
        "read and the weaker set published under the stronger label",
        edits=(
            Edit(
                path="sextant/ingress/detect/maven.py",
                find="            coordinates = tuple(sorted(resolved.versions))",
                replace="            pass  # guard disabled by scripts/guard_check.py",
            ),
        ),
    ),
    "detect.mavens-FILE-feeds-archives-coordinates-and-siblings": Guard(
        what="a current classpath file beside the module's classes is READ — jars to "
        "archives and coordinates, directories to sibling roots, the rest named",
        why="without the read the header walk sees the direct declarations only, which on "
        "Spring Boot is nearly nothing (`OI-167`: 9 of 89 named types on genai), and the "
        "module still claims nothing is wrong",
        edits=(
            Edit(
                path="sextant/ingress/detect/maven.py",
                find="        return MavenDetector._classpath_entries(path / _CLASSPATH_FILE), None",
                replace='        return None, "guard disabled by scripts/guard_check.py"',
            ),
        ),
    ),
    "detect.a-POM-with-nothing-built-starts-no-process": Guard(
        what="a single module with nothing under `target/classes` is never asked of Maven",
        why="a classpath is read FOR compiled classes; without the gate every temporary POM "
        "the unit suite writes starts a JVM, and an unbuilt checkout pays a build it did "
        "not ask for",
        edits=(
            Edit(
                path="sextant/ingress/detect/maven.py",
                find="        if not built:\n",
                replace="        if False:  # guard disabled by scripts/guard_check.py\n",
            ),
        ),
    ),
    "detect.a-STALE-file-asks-maven-offline-and-online-only-under-the-flag": Guard(
        what="Maven's offline refusal is retried online ONLY under `allow_resolve`",
        why="M02: Sextant never reaches the network on its own. Without the condition every "
        "offline refusal goes online unflagged, which is the one thing the flag exists to "
        "withhold",
        edits=(
            Edit(
                path="sextant/ingress/detect/maven.py",
                find="        if not (allow_resolve and _OFFLINE_REFUSAL_SUBSTRING in combined):",
                replace="        if True:  # guard disabled by scripts/guard_check.py",
            ),
        ),
    ),
    "detect.a-reactor-CHILD-is-asked-from-the-root-with-compile-attached": Guard(
        what="a module inside a reactor is asked from the reactor ROOT with `-pl` and `-am`",
        why="from its own directory the goal cannot resolve the sibling import-POMs and "
        "fails every time (measured on ruoyi), so the module would carry a failure reason "
        "forever and never the classpath Maven can in fact produce",
        edits=(
            Edit(
                path="sextant/ingress/detect/maven.py",
                find='*(["-pl", selected, "-am"] if selected is not None and in_reactor else []),',
                replace="            *([]),  # guard disabled by scripts/guard_check.py",
            ),
        ),
    ),
    "render.the-document-SAYS-how-many-named-types-the-header-read-found": Guard(
        what="the coverage section carries one line: dependency types named, headers read, "
        "in no archive, and who answered for the classpath",
        why="the document is the result (ruling 2026-10-17). `type_headers` in metadata "
        "alone leaves a reader of the document unable to tell a read that found 9 of 89 "
        "from one that found 9 of 9 — the whole of OI-167 was invisible that way",
        edits=(
            Edit(
                path="sextant/egress/render/document.py",
                find="    coverage_items += _type_header_items(report.coverage, module)\n",
                replace="",
            ),
        ),
    ),
    "storage.the-UNLOCATED-count-is-read-off-the-header-document": Guard(
        what="`coverage.type_headers_unlocated` is the count the header document carries",
        why="without it the only number is the headers READ, and a classpath that was not the "
        "real one looks identical to the real one — 9 headers either way",
        edits=(
            Edit(
                path=_WORKSPACE,
                find="               (SELECT coalesce(max(type_headers_unlocated), 0) FROM documents\n"
                "                WHERE header_only)                                    AS type_headers_unlocated\n",
                replace="               0 AS type_headers_unlocated\n",
            ),
        ),
    ),
    # --- a merged value with a common root (spec 2026-10-21) --------------------------
    "values.a-MERGE-is-read-not-skipped": Guard(
        what="the walk reads capability 9.19's `merge` kind rather than falling through to "
        "the sourceless `not_readable` the bare kind used to get",
        why="without the branch every merged value is a wall again, and `apollo-portal`'s 68 "
        "outgoing calls with their paths written at the call publish as two unknown "
        "destinations — OI-143 as it stood for a month",
        edits=(
            Edit(
                path="sextant/application/resolve/values.py",
                find='        if kind == "merge":\n            return self._merged(argument, method, origin, trail, frames)\n',
                replace="        if False:  # guard disabled by scripts/guard_check.py\n            return self._merged(argument, method, origin, trail, frames)\n",
            ),
        ),
    ),
    "values.a-merge-without-a-ROOT-is-never-picked-from": Guard(
        what="a merge whose candidates share no root is never picked from: `non_enumerable`, "
        "or every literal candidate `narrowed` (ruling 7)",
        why="ruling 1 of the value-resolution design: two literals on two branches are two "
        "possible values and no single one, and publishing the first would be a confident "
        "wrong address at `resolved` — the one fabrication this whole work risks",
        edits=(
            Edit(
                path="sextant/application/resolve/values.py",
                find="        return None\n\n    def _is_a_call_on(\n",
                replace="        return candidates[0]  # guard disabled by scripts/guard_check.py\n\n    def _is_a_call_on(\n",
            ),
        ),
    ),
    "values.a-rooted-merge-is-INEXACT-never-exact": Guard(
        what="every answer a rooted merge yields is marked `inexact`",
        why="the root is `x` and the other branch is `f(x)` for an unread `f`; without the "
        "mark the url reader publishes the literal at `resolved`, claiming a rendering nobody "
        "checked — on Apollo, 68 rows asserting the slash the wrapper strips",
        edits=(
            Edit(
                path="sextant/application/resolve/values.py",
                find="                replace(answer, inexact=True) if answer.kind in (LITERAL, EXPRESSION) else answer,\n",
                replace="                answer,  # guard disabled by scripts/guard_check.py\n",
            ),
        ),
    ),
    "shapes.a-field-borrows-an-annotation-only-from-its-CONSTRUCTOR-write": Guard(
        what="field-ladder rung 2 lends a constructor parameter's annotation to a field only "
        "where that constructor wrote the field from that parameter",
        why="`OI-214`: a field written by a SETTER from its own parameter N — `static void "
        "setHost(String h) { Client.host = h; }`, a field write since `PUTSTATIC` became one "
        'on 2026-10-26 — beside a constructor whose parameter N carries `@Value("${…}")` '
        "published that constructor's expression as the address at `resolved`. Nothing ties "
        "the setter's value to the constructor's parameter; trying every constructor whatever "
        "the writer is the mistake this guard writes back",
        edits=(
            Edit(
                path=_ARGUMENTS,
                find="        if writer is None:\n"
                "            candidates = facts.constructor_parameters.get(owner, [])",
                replace="        if True:  # guard disabled by scripts/guard_check.py\n"
                "            candidates = facts.constructor_parameters.get(owner, [])",
            ),
        ),
    ),
    "shapes.an-INEXACT-address-publishes-at-partial": Guard(
        what="`url_of_answer` publishes an inexact literal at `partial`, never `resolved`",
        why="`partial` is the word D00 §4 has for 'part of this address was read'; `resolved` "
        "would promise the exact text sent, which the walk never read",
        edits=(
            Edit(
                path="sextant/application/resolve/shapes/arguments.py",
                find="        if answer.inexact and resolution == str(Resolution.RESOLVED):\n            resolution = str(Resolution.PARTIAL)\n",
                replace="        if False:  # guard disabled by scripts/guard_check.py\n            resolution = str(Resolution.PARTIAL)\n",
            ),
        ),
    ),
    "shapes.an-INEXACT-channel-is-refused": Guard(
        what="`channel_of_answer` refuses an inexact literal as a destination",
        why="a broker resolves a destination it is GIVEN; a topic name some call may have "
        "re-rendered is not one, and publishing it would address a queue that may not exist",
        edits=(
            Edit(
                path="sextant/application/resolve/shapes/arguments.py",
                find='    if answer.inexact:\n        return None, None, "unresolved"\n',
                replace='    if False:  # guard disabled by scripts/guard_check.py\n        return None, None, "unresolved"\n',
            ),
        ),
    ),
    "values.a-BRANCH-between-literals-is-narrowed": Guard(
        what="a merge with no root whose candidates are all literals answers every candidate, "
        "each `narrowed`, one path per branch choice",
        why="ruling 7 (2026-10-29): `c ? A.class : B.class` is one of two values, the set "
        "complete — D00's `narrowed`. Answering `non_enumerable` hides a closed set the code "
        "states, and RuoYi's job-class ternary is exactly that set",
        edits=(
            Edit(
                path="sextant/application/resolve/values.py",
                find="            return self._branched(candidates, method, origin, trail, frames)\n",
                replace="            return _only(trail, _unresolved(NON_ENUMERABLE))  # guard disabled by scripts/guard_check.py\n",
            ),
        ),
    ),
    "values.a-BRANCH-is-one-choice-per-path": Guard(
        what="each candidate of a branch is a crossing on the path, so one branch read twice "
        "pairs only with itself",
        why='fix round 1 of ruling 7 (M-1): `p + "/x" + p` with `p = c ? "/a" : "/b"` '
        "minted `/a/x/b`, which no execution builds; the path is the unit of resolution",
        edits=(
            Edit(
                path="sextant/application/resolve/values.py",
                find='            merged = _combine(trail, (_Step(branch, f"branch {index}"),))\n',
                replace="            merged = trail  # guard disabled by scripts/guard_check.py\n",
            ),
        ),
    ),
    "values.a-template-filled-from-a-branch-is-NARROWED": Guard(
        what="`_joined` marks a template filled from a narrowed literal `narrowed`",
        why="ruling 7: a template built from one branch of several is one of several "
        "templates; unmarked it is a whole literal the url reader publishes at `resolved`",
        edits=(
            Edit(
                path="sextant/application/resolve/values.py",
                find="            narrowed = any(narrowed for _, _, _, _, narrowed, _ in combination)\n",
                replace="            narrowed = False  # guard disabled by scripts/guard_check.py\n",
            ),
        ),
    ),
    "values.a-BRANCH-with-an-unreadable-candidate-stays-non-enumerable": Guard(
        what="a branch is `narrowed` only where every candidate answers a literal on this "
        "path; otherwise it is ONE `non_enumerable`",
        why="ruling 7 lists a COMPLETE set; a candidate that reads no literal, or a value "
        "reached by crossing out of the method, leaves it incomplete, and a `narrowed` list "
        "carrying an unresolved member claims a set nobody read",
        edits=(
            Edit(
                path="sextant/application/resolve/values.py",
                find="        if any(answer.kind != LITERAL or crossed != trail for _, crossed, answer in reached):\n",
                replace="        if False:  # guard disabled by scripts/guard_check.py\n",
            ),
        ),
    ),
    "values.a-BRANCH-of-one-value-is-that-value-exactly": Guard(
        what="a branch whose candidates answer one value answers it exactly, unmarked",
        why="`c ? 1 : 1L` is `1` on every branch; `narrowed` would call a known value one of "
        "several",
        edits=(
            Edit(
                path="sextant/application/resolve/values.py",
                find="        if len(distinct) == 1:\n",
                replace="        if False:  # guard disabled by scripts/guard_check.py\n",
            ),
        ),
    ),
    "fluent.a-BRANCHED-assembled-address-keeps-its-unfilled-template": Guard(
        what="a fluent chain whose assembled url answers only branch literals keeps the "
        "template it published before ruling 7, its hole unfilled, at `partial`",
        why="the engine carries ONE address per chain (OI-134) and the walk may never take an "
        "answer away: without this the chain fell from `partial` to `unresolved`",
        edits=(
            Edit(
                path=_FLUENT,
                find="            if address is None and any(\n",
                replace="            if False and any(  # guard disabled by scripts/guard_check.py\n",
            ),
        ),
    ),
    "shapes.a-NARROWED-address-publishes-at-narrowed": Guard(
        what="`url_of_answer` publishes a narrowed literal at `narrowed`, never `resolved`",
        why="ruling 7: one of several branch literals is sent and which one is not known; "
        "`resolved` would publish each as THE address",
        edits=(
            Edit(
                path="sextant/application/resolve/shapes/arguments.py",
                find="        if answer.narrowed and resolution == str(Resolution.RESOLVED):\n",
                replace="        if False:  # guard disabled by scripts/guard_check.py\n",
            ),
        ),
    ),
    "shapes.a-NARROWED-channel-is-refused": Guard(
        what="`channel_of_answer` refuses a narrowed literal as a destination",
        why="ruling 7: consumers that refuse an inexact answer keep refusing a narrowed one — a "
        "broker resolves the destination it is GIVEN, and 'one of these' is not one",
        edits=(
            Edit(
                path="sextant/application/resolve/shapes/arguments.py",
                find='    if answer.narrowed:\n        return None, None, "unresolved"\n',
                replace='    if False:  # guard disabled by scripts/guard_check.py\n        return None, None, "unresolved"\n',
            ),
        ),
    ),
    "single_call.a-NARROWED-slot-makes-the-row-narrowed": Guard(
        what="a row whose walked verb or path is narrowed says `narrowed`, never `resolved`",
        why="ruling 7: `exchange(url, c ? GET : POST, …)` lists both verbs; the address alone "
        "reads `resolved`, and without this each verb's row would claim to be THE call",
        edits=(
            Edit(
                path=_SINGLE_CALL,
                find="    if narrowed and resolution == str(Resolution.RESOLVED):\n        return peer, path, str(Resolution.NARROWED)\n",
                replace="    if False:  # guard disabled by scripts/guard_check.py\n        return peer, path, str(Resolution.NARROWED)\n",
            ),
        ),
    ),
    "path_prefix.a-NARROWED-prefix-is-refused": Guard(
        what="a narrowed prefix key is refused, as the `non_enumerable` it replaced was",
        why="ruling 7: a prefix table maps ONE prefix to its pattern; publishing each branch's "
        "literal as a resolved prefix would put endpoints under a prefix that may never apply",
        edits=(
            Edit(
                path="sextant/application/resolve/path_prefix.py",
                find="    if answer.narrowed:\n        return None\n",
                replace="    if False:  # guard disabled by scripts/guard_check.py\n        return None\n",
            ),
        ),
    ),
    "fluent.a-NARROWED-assembled-address-is-never-resolved": Guard(
        what="`fluent`'s assembled-address reader answers a narrowed literal at `narrowed`",
        why="ruling 7: the arm hands on a single `resolved` text as the chain's whole address; "
        "counting branch literals as resolved changes which address a chain publishes",
        edits=(
            Edit(
                path=_FLUENT,
                find="    if answer.narrowed and (\n",
                replace="    if False and (  # guard disabled by scripts/guard_check.py\n",
            ),
        ),
    ),
    "single_call.the-VERB-rides-the-same-binding-as-the-path": Guard(
        what="where the verb argument is a parameter, the row's verb is read from the same "
        "walked binding as its path",
        why="measured on `apollo-portal`: 51 of the wrapper's 61 rows carried a path and no "
        "verb, `unresolved` for a declared capture that had failed, when the verb was the enum "
        "the wrapper's own `post()`/`put()`/`delete()` handed in on that very path",
        edits=(
            Edit(
                path="sextant/application/resolve/engines/single_call.py",
                find="                            else _verb_from_answer(binding.slots.get(verb_slot)),\n",
                replace="                            else None,  # guard disabled by scripts/guard_check.py\n",
            ),
        ),
    ),
    # --- a controller that exists in one environment only (spec 2026-10-21) ------------
    "conditions.the-PASS-writes-a-row-per-condition-and-environment": Guard(
        what="`record_bean_conditions` runs in the pipeline and writes `bean_conditions`, which "
        "the `endpoint_conditions` view reads",
        why='without it a `@Profile("prod")` controller publishes its endpoints as if they '
        "always existed — the cell as it stood for a month, and the one real instance "
        "(Apollo's `HomePageController`) read `resolved` in the two environments where it 404s",
        edits=(
            Edit(
                path="sextant/application/resolve/bean_conditions.py",
                find='    if rows:\n        workspace.derive("bean_conditions_insert", rows=rows)\n',
                replace='    if False:  # guard disabled by scripts/guard_check.py\n        workspace.derive("bean_conditions_insert", rows=rows)\n',
            ),
        ),
    ),
    "conditions.a-NEGATED-profile-holds-everywhere-but-that-environment": Guard(
        what="`!prod` holds in every environment but `prod` (CP-42 row 3)",
        why="`@Profile(\"!prod\")` is the ordinary spelling of 'not in production'; read as a "
        "name it would hold in NO environment the module resolves, and the document would say "
        "the endpoint exists nowhere",
        edits=(
            Edit(
                path="sextant/application/resolve/bean_conditions.py",
                find="            state = FAILS if negated else HOLDS\n",
                replace="            state = HOLDS  # guard disabled by scripts/guard_check.py\n",
            ),
            Edit(
                path="sextant/application/resolve/bean_conditions.py",
                find="            state = HOLDS if negated else FAILS\n",
                replace="            state = FAILS  # guard disabled by scripts/guard_check.py\n",
            ),
        ),
    ),
    "conditions.an-ABSENT-key-is-decided-by-match-if-missing": Guard(
        what="a `property` whose key an environment never defines holds exactly when "
        "`match_if_missing` is true (CP-43 row 3)",
        why="the framework's own rule; without it an absent key would read as holding, and a "
        "controller gated on a key the deployment never sets would be published as served there",
        edits=(
            Edit(
                path="sextant/application/resolve/bean_conditions.py",
                find='                if not expression["match_if_missing"]:\n                    return FAILS, "resolved"\n',
                replace='                if False:  # guard disabled by scripts/guard_check.py\n                    return FAILS, "resolved"\n',
            ),
        ),
    ),
    "conditions.a-COMPOSED-profile-expression-is-stated-not-evaluated": Guard(
        what="a profile expression with `&`, `|` or parentheses is `unresolved`, never a verdict",
        why="only a bare name and its negation are decided against an environment's active "
        "profiles (CP-45); evaluating a composition over several active profiles would be a "
        "verdict about a deployment this analysis does not see (CP-42 row 3)",
        edits=(
            Edit(
                path="sextant/application/resolve/bean_conditions.py",
                find="        if any(char in _COMPOSITION for char in text):\n            composed = True\n            continue\n",
                replace="        if False:  # guard disabled by scripts/guard_check.py\n            composed = True\n            continue\n",
            ),
        ),
    ),
    "conditions.a-LINK-states-where-its-inbound-endpoint-exists": Guard(
        what="a link to an inbound endpoint under a condition states, beside the link, the "
        "environments the endpoint exists in — read from the participant's own "
        "`endpoint_conditions` through the federated view (ruling 2)",
        why="matching never reads a condition — an endpoint is an endpoint — so the condition "
        "travels with the inbound endpoint as data and the link is where a reader of the "
        "system document learns `billing-api`'s `/balances` exists in `prod` only; without "
        "this the link reads as served everywhere, which is the published-as-if-it-always-"
        "existed failure one tier up",
        edits=(
            Edit(
                path="sextant/api.py",
                find='            inbound.setdefault((participant, method, path), set()).add(str(row["bean"]))\n',
                replace="            pass  # guard disabled by scripts/guard_check.py\n",
            ),
        ),
    ),
    "conditions.a-LINK-states-where-its-outbound-caller-exists": Guard(
        what="a link from a calling bean under a condition states, beside the calling side, "
        "the environments the call exists in — read from the participant's own "
        "`endpoint_conditions` and `bean_presence` through the federated views (spec "
        "2026-10-22-conditional-beans §3)",
        why="matching never reads a condition, so the condition travels with the outbound "
        "endpoint as data and the link is where a reader of the system document learns "
        "`orders-api` calls `billing` in `prod` only; without this the link reads as a call "
        "made everywhere, the published-as-if-it-always-existed failure on the calling side",
        edits=(
            Edit(
                path="sextant/api.py",
                find='            outbound.setdefault((participant, method, path, caller), set()).add(str(row["bean"]))\n',
                replace="            pass  # guard disabled by scripts/guard_check.py\n",
            ),
        ),
    ),
    "conditions.a-DECLARED-placeholder-nobody-filled-is-unresolved": Guard(
        what="a `property` key an environment DECLARES as `${REF}` that nothing fills is "
        "`unresolved` there, never decided by `match_if_missing`",
        why="the config layer resolves that row `missing_key` too, but WITH its file as "
        "`source`; dropped like a never-declared key, `orders.legacy: ${ORDERS_LEGACY}` read "
        "as absent and the controller as `false · resolved` — a verdict about a value the "
        "framework would see and this analysis does not (review fix, 2026-10-22)",
        edits=(
            Edit(
                path="sextant/application/resolve/bean_conditions.py",
                find='        if value is None and reason == "missing_key" and row.get("source") is None:\n',
                replace='        if value is None and reason == "missing_key":  # guard disabled\n',
            ),
        ),
    ),
    "conditions.an-UNEVALUATED-condition-still-writes-its-row": Guard(
        what="a controller under a condition this analysis does not evaluate (`other`: "
        "`@ConditionalOnExpression`, `@Conditional(X.class)`, …) writes its rows verbatim "
        "with `holds = unresolved`",
        why="without the `other` kind the catalog could not name them and the endpoint read "
        "as unconditional in both documents — exactly the pre-change behaviour the cell "
        "closes, for sixteen of the nineteen conditions CP-43 row 5 enumerates",
        edits=(
            Edit(
                path="sextant/application/resolve/bean_conditions.py",
                find="            for name in names:\n                symbol = type_descriptor(str(name))\n",
                replace="            for name in ():  # guard disabled by scripts/guard_check.py\n                symbol = type_descriptor(str(name))\n",
            ),
        ),
    ),
    "conditions.a-DEPLOYMENT-set-condition-is-decided-only-by-its-environment": Guard(
        what="a condition whose kind the bean model marks `set_by: deployment` is decided only "
        "by the environment's own definition, the module's own reading kept as evidence "
        "(spec 2026-10-23-deployment-set-conditions §3b)",
        why='spring-petclinic-rest\'s `@Profile("jdbc")` repositories were published as absent '
        "in all five environments, though `SPRING_PROFILES_ACTIVE=jdbc` activates them "
        "(CP-47): the repository's files state a default, never what production activates",
        edits=(
            Edit(
                path="sextant/application/resolve/bean_conditions.py",
                find='    if model.members.get("set_by") == "deployment":\n',
                replace="    if False:  # guard disabled by scripts/guard_check.py\n",
            ),
        ),
    ),
    "conditions.the-RESERVED-default-profile-is-no-activation-the-module-makes": Guard(
        what="a module naming no profile reads `this module activates none` in a deployment-set "
        "profile's evidence: the reserved `default` profile, active in its base environment only "
        "because it names none (CP-45 row 5), is not stated as an activation",
        why="every module without `spring.profiles.active` (the orders-service fixture, most "
        "services) had its documents say it `activates `default``, a claim about the module "
        "that is the framework's fallback, not anything the module configures (ruled at review)",
        edits=(
            Edit(
                path="sextant/application/resolve/bean_conditions.py",
                find="    if names == [default_profile]:\n",
                replace="    if False:  # guard disabled by scripts/guard_check.py\n",
            ),
        ),
    ),
    "conditions.a-QUOTED-configured-value-is-masked-by-its-key": Guard(
        what="the value a property condition's evidence quotes is masked by its own key where "
        "it is written (`redact_value`), as every origin of a configured value is",
        why="`bean_conditions` is exported whole and its evidence is masked only by "
        '`redact_text`, which cannot see the key: `@ConditionalOnProperty("billing.api-token")` '
        "would ship the token the module's own file sets in the clear",
        edits=(
            Edit(
                path="sextant/application/resolve/bean_conditions.py",
                find='else f"`{_REDACTOR.redact_value(key, str(config[key]))}`"',
                replace='else f"`{config[key]}`"  # guard disabled by scripts/guard_check.py',
            ),
        ),
    ),
    "conditions.a-reading-keeps-BOTH-a-placeholder-and-the-profiles-named-beside-it": Guard(
        what="a module's profile reading that names a placeholder nothing fills and literal "
        "profiles beside it states both: the placeholder's reason and the module's own default",
        why="`spring.profiles.active: [${APP_PROFILE}, prod]` activates `prod` itself; a "
        "reading stating only the placeholder drops what the module does activate",
        edits=(
            Edit(
                path="sextant/application/resolve/bean_conditions.py",
                find='        return prefix + base.otherwise + (f"; {own}" if own else "")\n',
                replace="        return prefix + base.otherwise  # guard disabled by "
                "scripts/guard_check.py\n",
            ),
        ),
    ),
    "conditions.a-QUOTED-value-is-masked-by-the-modules-own-rules-at-every-exit": Guard(
        what="every exit printing a condition's evidence — the module document's conditions "
        "and candidate lines (and through them the enrichment brief), and the bundle — "
        "re-masks each value a property condition quotes by its key under the module's own "
        "rules (`redact_condition_evidence`)",
        why="the writer masks with the built-ins only (no module redactor reaches a resolve "
        "pass, `OI-71`), and `redact_text` cannot see a key: a `.sextant.yml` naming "
        "`billing` a secret key would see `billing.enabled`'s configured value in the "
        "document, the brief and the bundle in the clear",
        edits=(
            Edit(
                path="sextant/application/resolve/bean_conditions.py",
                find='            + redactor.redact_value(found["key"], found["value"])\n',
                replace='            + found["value"]  # guard disabled by scripts/guard_check.py\n',
            ),
        ),
    ),
    # --- a bean that exists in some environments only (spec 2026-10-22-conditional-beans) -
    "beans.a-FACTORY-conditions-only-the-class-it-returns": Guard(
        what="a factory method conditions the classes its body constructs that are assignable "
        "to its declared return type, and no helper the body builds and hands to the bean",
        why='a `@Profile("prod") Client client()` builds an `HttpClient` and returns a '
        "`Client` over it; without the rule the helper is a conditional bean too, and every "
        "row of the helper's class is published as existing in `prod` only — a condition on "
        "code the factory merely uses",
        edits=(
            Edit(
                path="sextant/application/resolve/bean_conditions.py",
                find="                and _assignable(bare_descriptor(built), factory.erased_return, ancestors)\n",
                replace="                and True  # guard disabled by scripts/guard_check.py\n",
            ),
        ),
    ),
    "beans.registration-ROUTES-combine-by-OR": Guard(
        what="a bean exists in an environment where ANY of its registration routes holds — OR "
        "across routes, AND within one — in `bean_presence`",
        why="two exclusive `@Profile` factories register the same class, each in its own "
        "environment; read as one list of conditions the class would exist nowhere, and every "
        "endpoint of it would be published as served in no environment at all",
        edits=(
            Edit(
                path="sextant/storage/duckdb/schema.sql",
                find="SELECT bean, environment,\n       CASE WHEN bool_or(holds = 'true') THEN 'true'\n            WHEN bool_and(holds = 'false') THEN 'false'\n",
                replace="SELECT bean, environment,\n       CASE WHEN bool_and(holds = 'true') THEN 'true'\n            WHEN bool_and(holds = 'false') THEN 'false'\n",
            ),
        ),
    ),
    "beans.a-COMPOSED-stereotype-or-condition-is-followed": Guard(
        what="an annotation meta-annotated by a stereotype or a condition (a composed "
        "annotation, in the module or from a dependency's recorded header) counts as that "
        "stereotype or condition on its users",
        why='a `@ProdService` composed of `@Service` and `@Profile("prod")` is the ordinary '
        "way a team writes the condition once; unfollowed, the class is no bean or an "
        "unconditional one, and its endpoints read as served everywhere",
        edits=(
            Edit(
                path="sextant/application/resolve/bean_conditions.py",
                find="        for row in composed_mapping_rows(rows, composing, {seed}):\n",
                replace="        for row in ():  # guard disabled by scripts/guard_check.py\n",
            ),
        ),
    ),
    "beans.a-LAMBDA-a-factory-creates-is-the-factorys-code": Guard(
        what="a lambda body a factory method creates is that factory's code: a bean it "
        "constructs is the factory's construction, and the lambda's own rows carry the "
        "factory's conditions",
        why="a router function or a `@Bean`-returned handler is written as a lambda; without "
        "the rule its `new` is a plain construction outside any factory, the bean is left "
        'open, and a `@Profile("prod")` factory\'s routes are published as existing everywhere',
        edits=(
            Edit(
                path="sextant/application/resolve/bean_conditions.py",
                find="        for body in _created_from(creating, created):\n",
                replace="        for body in ():  # guard disabled by scripts/guard_check.py\n",
            ),
        ),
    ),
    "beans.MISSING-BEAN-reads-the-modules-competitors": Guard(
        what="`@ConditionalOnMissingBean` / `@ConditionalOnBean` are judged against the "
        "module's other bean definitions that register a different class",
        why='a default `@ConditionalOnMissingBean` client beside a `@Profile("prod")` '
        "override exists everywhere but `prod`; with no competitors read, the default holds "
        "everywhere and the override's environment is published as having both",
        edits=(
            Edit(
                path="sextant/application/resolve/bean_conditions.py",
                find="                if holder not in (other.symbol, other.owner) and not (other.beans & same)\n",
                replace="                if False  # guard disabled by scripts/guard_check.py\n",
            ),
        ),
    ),
    "beans.a-SAME-CLASS-route-is-never-a-competitor": Guard(
        what="a bean's own other registration routes are no competitor of its presence condition",
        why="two `@ConditionalOnMissingBean` factories for one class would each find the "
        "other registering it and fail; the class would be published as existing nowhere "
        "though the container registers it through whichever route runs",
        edits=(
            Edit(
                path="sextant/application/resolve/bean_conditions.py",
                find="                if holder not in (other.symbol, other.owner) and not (other.beans & same)\n",
                replace="                if holder not in (other.symbol, other.owner)  # guard disabled\n",
            ),
        ),
    ),
    "beans.every-presence-verdict-is-PARTIAL": Guard(
        what="a bean-presence verdict is `partial`, never `resolved`: it is decided from the "
        "module's own beans only",
        why="a dependency's auto-configuration can register the bean this analysis does not "
        "see, so `resolved` would assert a fact about the deployment's container that only "
        "the module's classes support",
        edits=(
            Edit(
                path="sextant/application/resolve/bean_conditions.py",
                find="                stated[environment] = (str(final), PARTIAL, reason + listed)\n",
                replace='                stated[environment] = (str(final), "resolved", reason + listed)  # guard disabled\n',
            ),
        ),
    ),
    "beans.an-INHERITED-body-takes-the-OR-of-the-beans-that-run-it": Guard(
        what="an inherited body (an abstract class's method, an interface default) exists "
        "wherever any bean that resolves to it does — each heir's routes kept distinct under "
        "the body",
        why="two beans inherit one body, each in its own profile; folded into one route the "
        "body would need both profiles at once, and its endpoints would be published as "
        "existing in neither",
        edits=(
            Edit(
                path="sextant/application/resolve/bean_conditions.py",
                find='{**row, "bean": body, "via": row["via"] or heir}',
                replace='{**row, "bean": body, "via": row["via"]}',
            ),
        ),
    ),
    "beans.ACTIVE-PROFILES-are-read-from-configuration": Guard(
        what="a `@Profile` condition is judged against the profiles the base configuration's "
        "active keys list (CP-45), not the environment's file name alone",
        why="spring-petclinic-rest sets `spring.profiles.active=h2,spring-data-jpa`; read off "
        "the file names alone, every Spring Data JPA repository was published as existing in "
        "no environment although the container registers them wherever the module runs",
        edits=(
            Edit(
                path="sextant/application/resolve/bean_conditions.py",
                find='    actives, active_open = listed(profiles.get("active_keys"))\n',
                replace="    actives, active_open = [], []  # guard disabled by scripts/guard_check.py\n",
            ),
        ),
    ),
    "beans.a-PROFILE-GROUP-expands-an-active-profile": Guard(
        what="a profile `spring.profiles.group.<name>` lists is active wherever `<name>` is, "
        "transitively (CP-45 row 8, `expandProfiles`)",
        why="Apollo's portal sets `spring.profiles.group.github = mysql`; with groups unread, a "
        '`@Profile("mysql")` bean was published as absent in the `github` environment, where '
        "the container activates `mysql` and registers it",
        edits=(
            Edit(
                path="sextant/application/resolve/bean_conditions.py",
                find="                pending.extend(groups.get(name, ()))\n",
                replace="                pass  # guard disabled by scripts/guard_check.py\n",
            ),
        ),
    ),
    "beans.a-FACTORY-methods-own-body-is-the-factorys-code": Guard(
        what="a `@Bean` method under a condition is a bean of its own, `via` itself, so a row "
        "whose code symbol is the method (an inline adapter flow it builds and returns) states "
        "the factory's condition",
        why="a row made in the factory's own body maps through `symbol_beans` to the "
        "configuration class, which has no rows unless it is conditional: the row read "
        "as existing everywhere though the factory registers nothing outside its profile "
        "(OI-108's own case)",
        edits=(
            Edit(
                path="sextant/application/resolve/bean_conditions.py",
                find="        if own:\n            routes.setdefault(declared, []).append(_Route(FACTORY, declared, own))\n",
                replace="        if False:  # guard disabled by scripts/guard_check.py\n            routes.setdefault(declared, []).append(_Route(FACTORY, declared, own))\n",
            ),
        ),
    ),
    "beans.an-INTERFACE-the-framework-implements-is-a-route": Guard(
        what="an interface the framework registers and implements at run time (CP-46) is a "
        "registration route with its own conditions, and its implementation answers calls "
        "naming a type it is assignable to",
        why='spring-petclinic-rest\'s `@Profile("spring-data-jpa")` Spring Data repositories '
        "are interfaces; without the route every repository call was published as answered by "
        "nothing in any environment, though the active profile makes the framework implement it",
        edits=(
            Edit(
                path="sextant/application/resolve/bean_conditions.py",
                find="    for interface in _registered_interfaces(\n        interfaces, interface_registrations, annotated, ancestors\n    ):\n",
                replace="    for interface in ():  # guard disabled by scripts/guard_check.py\n",
            ),
        ),
    ),
    "render.OUTBOUND-rows-and-schedules-state-their-condition": Guard(
        what="an outbound call and a scheduled job of a conditional bean get the two lines "
        "saying where it exists, read through the same index the inbound rows use",
        why="the first cut of the rule stated a condition on inbound endpoints only; an "
        'outbound call and a nightly job of a `@Profile("prod")` bean read as running '
        "everywhere in the document",
        edits=(
            Edit(
                path="sextant/egress/render/document.py",
                find='            conditions = _condition_entries(endpoint.get("caller"), beans)\n',
                replace="            conditions = []  # guard disabled by scripts/guard_check.py\n",
            ),
            Edit(
                path="sextant/egress/render/document.py",
                find='        entries = _condition_entries(row["handler"], beans)\n',
                replace="        entries = []  # guard disabled by scripts/guard_check.py\n",
            ),
        ),
    ),
    "render.a-NARROWED-site-states-its-candidates-per-environment": Guard(
        what="a narrowed call site with a conditional candidate states, per environment, "
        "which candidates exist, from `candidate_presence`",
        why="the step table lists every candidate of a narrowed call, so a reader sees "
        "`ldap` and `oidc` both answering; without the per-environment lines nothing says "
        "that only one of them exists where the module runs",
        edits=(
            Edit(
                path="sextant/egress/render/document.py",
                find="    entries.extend(_candidate_entries(trace, candidates))\n",
                replace="    entries.extend([])  # guard disabled by scripts/guard_check.py\n",
            ),
        ),
    ),
    "render.existence-is-read-from-PRESENCE-only": Guard(
        what="the line `holds in N of M environments` is read from `bean_presence`, never "
        "from the per-condition rows",
        why="two exclusive factories each hold somewhere; counted from the condition rows "
        "the bean would read as holding in half the environments it exists in, or in none",
        edits=(
            Edit(
                path="sextant/egress/render/document.py",
                find="    verdict = _presence_verdict(index.presence.get(bean, []))\n",
                replace="    verdict = _presence_verdict([row for rows in routes.values() for row in rows])  # guard disabled\n",
            ),
        ),
    ),
    "stitch.a-participant-derived-by-an-OLDER-build-is-refused-by-name": Guard(
        what="`federate` refuses a participant workspace lacking a federated table, naming "
        "the participant and the command to run",
        why="a view binds at creation, so without the check the first system query raised a "
        "bare `Catalog Error: Table with name endpoint_conditions does not exist` on any "
        "reactor whose modules were analysed before the table existed",
        edits=(
            Edit(
                path="sextant/storage/duckdb/workspace.py",
                find="            if missing:\n                raise StaleParticipantError(\n",
                replace="            if False:  # guard disabled by scripts/guard_check.py\n                raise StaleParticipantError(\n",
            ),
        ),
    ),
    "redaction.a-PEER-never-carries-url-userinfo": Guard(
        what="`split_url` drops `user:password@` from the authority it returns as the peer",
        why="the peer is the service a call reaches; kept, a credential written into a literal "
        "URL sat in `endpoints.peer` without its scheme, where the exits' `scheme://` "
        "userinfo rule never matched it — the workspace, the document and the bundle all "
        "carried the password (found 2026-10-23)",
        edits=(
            Edit(
                path="sextant/application/resolve/shapes/arguments.py",
                find='    return authority_without_userinfo(match.group("authority")), '
                'match.group("path") or ""\n',
                replace='    return match.group("authority"), match.group("path") or ""  # guard disabled\n',
            ),
        ),
    ),
    "redaction.open-question-CANDIDATES-are-masked-at-every-exit": Guard(
        what="`redact_candidates` masks a candidate's `peer` (and a key's per-environment "
        "values) before the document, the brief or the bundle prints it",
        why="the ledger's `path` was masked and its candidates beside it were not, so a "
        "`self_exchange` question printed the called side's peer verbatim",
        edits=(
            Edit(
                path="sextant/domain/redaction.py",
                find='                out["peer"] = self.redact_text(str(out["peer"]))\n',
                replace='                out["peer"] = str(out["peer"])  # guard disabled\n',
            ),
        ),
    ),
    "redaction.endpoint-METADATA-masks-the-endpoints-path": Guard(
        what="the export masks `endpoint_metadata.path` by the address map `endpoints.path` takes",
        why="it carries its endpoint's path as the key it joins by, and an outbound path may "
        "be a whole address: shipped verbatim, the bundle carried the credential and a "
        "reader's join on `path` missed every row (OI-169)",
        edits=(
            Edit(
                path="sextant/storage/duckdb/workspace.py",
                find="        SELECT m.* REPLACE (coalesce(a.masked, m.path) AS path)\n",
                replace="        SELECT m.*  -- guard disabled\n",
            ),
        ),
    ),
    "redaction.USERINFO-is-stripped-to-the-authoritys-last-at": Guard(
        what="`_USERINFO` strips a URL's userinfo up to the LAST `@` of its authority",
        why="a password may carry an unencoded `@`; stopping at the first left part of the "
        "password in every path, argument and constant (found 2026-10-23)",
        edits=(
            Edit(
                path="sextant/domain/redaction.py",
                find='_USERINFO = re.compile(r"(?P<scheme>[A-Za-z][A-Za-z0-9+.\\-]*://)[^/?#\\s]*@")\n',
                replace='_USERINFO = re.compile(r"(?P<scheme>[A-Za-z][A-Za-z0-9+.\\-]*://)[^/?#\\s@]*@")\n',
            ),
        ),
    ),
    "stitch.a-STALE-participant-is-refused": Guard(
        what="`system analyze` refuses a participant whose workspace stamps differ from this "
        "build's, as `render` refuses a module's own",
        why="the system tier reads workspaces as they are, so one derived by another build — "
        "a pre-2026-10-23 one holding credential peers — reached the system document",
        edits=(
            Edit(
                path="sextant/api.py",
                find="            if stale:\n                raise NotAnalyzedError(\n"
                '                    f"participant `{participant.name}`',
                replace="            if False:  # guard disabled\n                raise NotAnalyzedError(\n"
                '                    f"participant `{participant.name}`',
            ),
        ),
    ),
    "stitch.an-LB-target-is-an-authority-without-its-userinfo": Guard(
        what="the matcher drops userinfo from an `lb://` target before looking the name up",
        why="the target is an authority; kept, a credential made the call match nothing and "
        "the refusal quoted it into the system document with no scheme in front",
        edits=(
            Edit(
                path="sextant/application/stitch/links.py",
                find="        stated = authority_without_userinfo(path[len(_LOAD_BALANCED) :])\n",
                replace="        stated = path[len(_LOAD_BALANCED) :]  # guard disabled\n",
            ),
        ),
    ),
    "stitch.the-system-document-masks-gateway-REFUSALS": Guard(
        what="the system document passes a gateway refusal's route and reason through the redactor",
        why="both are configuration read verbatim from a participant's workspace",
        edits=(
            Edit(
                path="sextant/egress/render/system.py",
                find="        route = redactor.redact_text(refusal.route)\n"
                "        reason = redactor.redact_text(refusal.reason)\n",
                replace="        route = refusal.route  # guard disabled\n"
                "        reason = refusal.reason\n",
            ),
        ),
    ),
    "stitch.the-LINKS-legend-says-what-not-evaluated-means-once": Guard(
        what='where any link end renders "not evaluated", the Links section carries one fixed '
        "sentence saying what it means and that the participant's module document says why",
        why="a deployment-set condition leaves most ends not evaluated in every environment, "
        "and the system document states no reason: without the legend a reader takes it for "
        "a failure of the analysis, or for the end not existing",
        edits=(
            Edit(
                path="sextant/egress/render/system.py",
                find='        lines += [_NOT_EVALUATED, ""]\n',
                replace="        pass  # guard disabled by scripts/guard_check.py\n",
            ),
        ),
    ),
    "redaction.the-SYSTEM-document-masks-by-every-participants-rules": Guard(
        what="the system document's redactor is the union of every present participant's rule set",
        why="the document prints every participant's rows in one place, so a value one "
        "participant's `redact:` rule hides must be hidden wherever it appears",
        edits=(
            Edit(
                path="sextant/api.py",
                find="            redactor = redactor.union("
                "_redactor_for(participant.location.parent.parent))\n",
                replace="            redactor = redactor  # guard disabled\n",
            ),
        ),
    ),
    "storage.a-TYPE-HEADER-joins-the-superclass-walk": Guard(
        what="`type_header` facts are unioned into the `superclasses` query, so a module "
        "class extending a library class — or a handler parameter typed as one — reaches a "
        "declared throwable root",
        why="the walk proving a type is a throwable stops at the first class not in the "
        "facts. `MethodArgumentNotValidException extends BindException extends Exception` "
        "crosses two jars; without the union the handler taking that parameter derives "
        "nothing from it — the COVERAGE row `@ControllerAdvice` carried as ◐ for a month",
        edits=(
            Edit(
                path=_WORKSPACE,
                find="        WHERE kind = 'type_header' AND (payload ->> 'superclass') IS NOT NULL",
                replace="        WHERE false  -- guard disabled by scripts/guard_check.py",
            ),
        ),
    ),
    "error_advice.a-STATUS-on-a-library-exception-class-is-read": Guard(
        what="`error_advice` reads class-level annotations off `type_header` facts, so "
        "`@ResponseStatus` on a handled exception living in a dependency jar reaches the "
        "handler's `status`",
        why="a third-party exception class carries its annotation in a jar this workspace "
        "never scanned, so its handler's `status` was NULL — the other ◐ row. Only this "
        "engine reads header annotations; the row-minting engines must never see a "
        "library's class-level annotations",
        edits=(
            Edit(
                path="sextant/application/resolve/engines/error_advice.py",
                find='        for query in ("annotations", "type_header_annotations")',
                replace='        for query in ("annotations",)  # guard disabled',
            ),
        ),
    ),
    "storage.a-HEADER-ONLY-document-is-not-a-document-read": Guard(
        what="the synthetic `type_header` document is excluded from `coverage.documents`",
        why="`documents` means class files this module built; a header read of two "
        "thousand referenced types would otherwise report as a document opened, and every "
        "field pin asserting that count would move for a file nobody read",
        edits=(
            Edit(
                path=_WORKSPACE,
                find="        SELECT count(*) FILTER (WHERE NOT header_only)                AS documents,",
                replace="        SELECT count(*)                                              AS documents,",
            ),
        ),
    ),
    "stitch.a-participant-is-MATCHED-by-its-artifact-id": Guard(
        what="a participant's matching NAME is its module's artifactId, with the full "
        "coordinate carried beside it",
        why="a client names a service the way service discovery does, and on a Spring "
        "module that is `spring.application.name`, which defaults to the artifactId — "
        "every `lb://` in the two pinned gateways names exactly that. The coordinate is "
        "carried too because an artifactId is not unique in principle: two groups may ship "
        "one, and without `module_id` those are one participant in the table and a link "
        "could be minted against the wrong half of a collision",
        edits=(
            Edit(
                path=_PARTICIPANTS,
                find='    bare = [module_id.rsplit(":", 1)[-1] for module_id in ids]',
                replace="    bare = list(ids)  # guard disabled by scripts/guard_check.py",
            ),
        ),
    ),
    "stitch.an-ABSENT-participant-is-a-row-not-an-omission": Guard(
        what="a module whose graph could not be read is a `participants` ROW marked absent "
        "with a reason, never a module left out of the table",
        why="`M06`'s rule is that an unmatched call into a participant nobody could read is "
        "attributed to the GAP rather than reported as an architectural finding, and a "
        "missing row cannot carry that distinction: *nothing calls this service* and *we "
        "could not read this service* are different statements about a system, and a reader "
        "acting on the first while the second is true deletes a dependency that exists",
        edits=(
            Edit(
                path=_PARTICIPANTS,
                find="        out.append(\n            Participant(",
                replace="        if entry.get('location') is None:  # guard disabled\n"
                "            continue\n"
                "        out.append(\n            Participant(",
            ),
        ),
    ),
    "stitch.a-federated-view-READS-a-participants-graph-and-copies-nothing": Guard(
        what="the system workspace reads each participant's graph through a view over its "
        "workspace and imports none of it",
        why="`D01`'s system scope: two native tables, everything else federated, because "
        '"federating them costs no import stage and cannot drift from the bundle". Copying '
        "would reintroduce exactly the drift the rule exists to prevent, and measured it "
        "would also be pointless — `ATTACH` reads a header, so 18 workspaces totalling "
        "432 MB attach in 45 ms and one scan of all 484 endpoint rows takes 2 ms",
        edits=(
            Edit(
                path=_WORKSPACE,
                find='            self._connection.execute(f"CREATE OR REPLACE VIEW {view} AS {union}")',
                replace="            self._connection.execute(\n"
                '                f"CREATE OR REPLACE TABLE {view} AS SELECT * FROM ({union}) WHERE false"\n'
                "            )  # guard disabled by scripts/guard_check.py",
            ),
        ),
    ),
    "stitch.a-reactor-entry-with-no-coordinate-names-no-participant": Guard(
        what="a reactor entry carrying no build coordinate yields no participant",
        why="its matching name would be the empty string, and a participants row whose "
        "name is empty claims to be a service while matching nothing meaningfully. The "
        "same refusal every reader in this project makes about a value it cannot name",
        edits=(
            Edit(
                path=_PARTICIPANTS,
                find="        if not module_id:",
                replace="        if False:  # guard disabled by scripts/guard_check.py",
            ),
        ),
    ),
    "stitch.NO-participant-leaves-an-EMPTY-view-never-a-missing-one": Guard(
        what="a system with no readable participant still has the views, empty",
        why="a missing view makes a system query raise a catalog error that says nothing "
        "about why, where an empty one answers and leaves the reason where a reader can act "
        "on it — per participant in `participants`, with its own sentence. A reactor every "
        "module of which was skip-listed is the live case",
        edits=(
            Edit(
                path=_WORKSPACE,
                find="            if not aliases:",
                replace="            if False:  # guard disabled by scripts/guard_check.py",
            ),
        ),
    ),
    "stitch.FEDERATING-again-replaces-the-previous-set": Guard(
        what="federating a second set detaches the first, so one process may analyze two "
        "reactors without the first one's participants staying readable",
        why="a link minted against a participant that is not in THIS system is a dependency "
        "this system does not have — the same fabrication `M06` refuses heuristics to avoid, "
        "arriving through stale state instead of through a guess",
        edits=(
            Edit(
                path=_WORKSPACE,
                find='            self._connection.execute(f"DETACH DATABASE IF EXISTS {alias}")',
                replace="            pass  # guard disabled by scripts/guard_check.py",
            ),
        ),
    ),
    "arguments.a-QUERY-STRING-is-not-part-of-the-address": Guard(
        what="an outbound row's query string is lifted off `path` into one "
        "`endpoint_metadata` entry per parameter, so the address is the one the server "
        "publishes for the same route",
        why='`OI-151`. A server declaring `@RequestParam("petId")` on '
        '`@GetMapping("pets/visits")` publishes `/pets/visits` plus an entry; a client '
        'writing `.uri(host + "pets/visits?petId={petId}")` published '
        "`/pets/visits?petId={petId}` and no entry at all. Nothing is wrong at runtime — it "
        "is the same contract from both ends — but the two rows could not be compared on the "
        "address, so the linking tier (`GAP-2`) would miss a link that is exact in the code "
        "and a reader diffing the columns saw a mismatch that is not one. Both engines ask "
        "one function at the same point in their own loop, BEFORE the dedup key, which is "
        "built from the path the row publishes",
        edits=(
            Edit(
                path=_ARGUMENTS,
                find='    if path is None or "?" not in path:\n        return path, ()',
                replace="    if True:  # guard disabled by scripts/guard_check.py\n"
                "        return path, ()",
            ),
        ),
    ),
    "arguments.a-QUERY-parameters-value-is-masked-by-its-own-name": Guard(
        what="a query parameter's value is redacted at the ORIGIN, keyed on the parameter's "
        "own name, in each engine that writes the entry",
        why="`schema.sql`'s `value` column states that a metadata value is masked at the "
        "origin, because nothing downstream masks one and `endpoint_metadata` is exported "
        "whole. `?access_token=sk-live-…` is an ordinary way to write an outbound call. "
        "`OI-151` made `single_call` a writer of this table for the first time, and the "
        "first draft built the row in a shared helper that held the only redactor — which "
        "`test_every_origin_writing_endpoint_metadata_holds_a_redactor` refused, correctly: "
        "it would have let an engine write values it never read",
        edits=(
            Edit(
                path=_SINGLE_CALL,
                find='"value": None if value is None else _REDACTOR.redact_value(name, value),',
                replace='"value": value,  # guard disabled by scripts/guard_check.py',
            ),
        ),
    ),
    "arguments.a-PEER-is-refused-where-ANY-path-did-not-answer-one": Guard(
        what="the peer question refuses unless EVERY path through the first operand answers "
        "an authority literal, and they all agree — one unread path is one call to "
        "somewhere this analysis cannot name",
        why="the first version FILTERED to the authority answers, so it could refuse "
        "nothing: the paths it was meant to refuse were the ones it removed, and its own "
        'docstring\'s promise to return None for "several answers" was unreachable. '
        "MEASURED as a false fact on the most ordinary shape there is — a private "
        "`fetch(URI host)` whose concat is the address, called once with a discovery lookup "
        "and once with a `URI` its own caller supplied: the row published peer "
        "`customers-service` for a helper half of whose calls go somewhere the code never "
        "states, and the document drew an arrow that does not exist. A field with two "
        "writers and a two-branch helper reach it by two other routes",
        edits=(
            Edit(
                path=_ARGUMENTS,
                find="            or answer.yields != _AUTHORITY\n        ):\n            return None",
                replace="            or answer.yields != _AUTHORITY\n        ):\n"
                "            continue  # guard disabled by scripts/guard_check.py",
            ),
        ),
    ),
    "values.a-concat-hole-REPLACES-what-it-cannot-fill-never-drops-it": Guard(
        what="a concatenation hole gives one candidate per calling context its operand "
        "reached, and the context that read no text keeps the hole's spelling instead of "
        "vanishing",
        why="the filter kept only string literals whenever any path read one, so a helper "
        'called with `"svc-a"` and with a parameter nothing supplies published ONE address '
        "and a peer for it — a fact the code does not state, found by the same multiplicity "
        "checks that the `preserves` arm above feeds",
        edits=(
            Edit(
                path=_VALUES,
                find="                for crossed, answer in reached\n            )\n"
                "            per_hole.append(settled or",
                replace="                for crossed, answer in reached\n"
                "                if answer.kind == LITERAL and answer.literal_kind == STRING\n"
                "            )\n            per_hole.append(settled or",
            ),
        ),
    ),
    "values.a-hole-filled-by-a-PLACEHOLDER-expression-is-never-a-literal": Guard(
        what="a concatenation hole filled with the text of an expression that carries a "
        "`${key}` makes an `expression`, never a `literal`",
        why="`${key}` is the deployment's to set, and `channel_of_answer` refuses an "
        "expression on purpose: a `literal` holding an unresolved placeholder would be read "
        "as a destination by a messaging catalog",
        edits=(
            Edit(
                path=_VALUES,
                find="            whole = all(value is not None for _, value, _, _, _, _ in combination) and not any(\n"
                "                keyed for _, _, _, _, _, keyed in combination\n            )\n",
                replace="            whole = all(value is not None for _, value, _, _, _, _ in combination)\n",
            ),
        ),
    ),
    "values.a-path-a-RENDERING-cannot-carry-is-replaced-never-dropped": Guard(
        what="an identity a `preserves` entry cannot carry becomes an UNRESOLVED answer on "
        "its own path, so a reader of the result still sees that the code had two paths",
        why="filtering the pairs let a second path vanish, and every multiplicity check "
        "downstream then saw ONE answer where the code had two — which is how the peer "
        "question's refusal was defeated without ever being reached. The two arms beside "
        "this one return ALL of `identified` for the same reason",
        edits=(
            Edit(
                path=_VALUES,
                find="                    (crossed, answer if answer.yields == preserved else unreadable)\n"
                "                    for crossed, answer in identified\n",
                replace="                    (crossed, answer)  # guard disabled\n"
                "                    for crossed, answer in identified\n"
                "                    if answer.yields == preserved\n",
            ),
        ),
    ),
    "values.a-RENDERING-carries-an-authority-and-nothing-else": Guard(
        what="an identity entry declaring `preserves` propagates an identity of that kind "
        "and mints none — so crossing `String.valueOf` carries an authority and drops an "
        "address",
        why="javac inserts `String.valueOf` around every non-String concat operand, so the "
        "walk meets it in every address assembled from an object. `OI-142` refused an "
        "identity entry over it outright, and was right about the danger: read off the "
        "platform's own bytecode (CP-39 Q1) it returns `arg.toString()`, which for a JMS "
        'destination identified as `"orders"` is a vendor debug string — carrying that as '
        "an identity would publish an address that never existed, at `resolved`. The gate "
        "is what makes the entry shippable, and without it the entry is exactly the defect "
        "that was refused",
        edits=(
            Edit(
                path=_VALUES,
                find="            preserved = self._preserved_kind(site)",
                replace="            preserved = None  # guard disabled by guard_check.py",
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
                find="        for _, entry in constants:",
                replace="        for _, entry in ():  # guard disabled by scripts/guard_check.py",
            ),
        ),
    ),
    "values.a-field-read-on-an-UNSEEN-object-borrows-no-other-objects-writes": Guard(
        what="a field read through a getter on an object every answer for which is "
        "`external` keeps only what the field's own constructors write without a parameter, "
        "with `external` beside it where anything was dropped",
        why="OI-222: DolphinScheduler's trigger read `schedule.getCrontab()` off a database "
        "row and published, as a second schedule, the default cron `CronUtils` set on a "
        "`Schedule` it built for itself; in the Quartz fixture the same shape published it "
        "`resolved`",
        edits=(
            Edit(
                path=_VALUES,
                find="            if self._unseen_object(str(symbol), frames, method):\n",
                replace="            if False:  # guard disabled by scripts/guard_check.py\n",
            ),
        ),
    ),
    "values.an-object-a-LIBRARY-call-hands-back-is-not-from-outside": Guard(
        what="the unseen-object rule declares every unscanned call to the producer reader, "
        "so an object a library call hands back ends at that call, not at `external`",
        why="review of OI-222's fix, Major 1: `List.of(new Row()).get(0).getCron()` lost the "
        "cron its own code set, because `List.get`'s body was not scanned",
        edits=(
            Edit(
                path=_VALUES,
                find="        ends = producers_of(self._index, site, RECEIVER, self._index.unscanned)\n",
                replace="        ends = producers_of(self._index, site, RECEIVER, frozenset())  # guard disabled\n",
            ),
        ),
    ),
    "values.a-STATIC-field-is-never-read-as-an-unseen-objects": Guard(
        what="the unseen-object rule never applies to a field the facts mark `static`",
        why="review of OI-222's fix, Major 2: a static field set by a static method and read "
        "through an instance getter lost the value every reader shares",
        edits=(
            Edit(
                path=_VALUES,
                find="        if not frames or reader is None or symbol in self._index.static_fields:\n",
                replace="        if not frames or reader is None:  # guard disabled\n",
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
    "values.a-field-written-from-a-CALL-is-followed": Guard(
        what="a binding written from a call's result is resolved in the WRITING method's "
        "frame, through the call that produced it",
        why="Kotlin's top-level `val client = HttpClient(CIO) { … }` is `invokestatic; "
        "putstatic` in `<clinit>`, and a class property `private val c = HttpClient { … }` "
        "is `aload_0; invoke…; putfield` — measured on the CP-54 probe module, every read of "
        "such a client answered `no_writer`, so the walk could not reach the client a Ktor "
        "call is made on. Reading the write's value as a constant instead answers "
        "`not_readable` about a value whose producer is a fact, and reading its `source` in "
        "the READER's frame would answer whatever that id names there — a wrong value at "
        "`resolved`",
        edits=(
            Edit(
                path=_VALUES,
                find='        if entry.get("source") is not None and row.get("written_by") is not None:',
                replace="        if False:  # guard disabled by scripts/guard_check.py",
            ),
        ),
    ),
    "values.the-PRODUCER-reader-stops-at-a-declared-call": Guard(
        what="the producer reader ends a path at a producing call whose (owner, method) the "
        "caller declared, and names that call",
        why="a reader that must read the block a client was BUILT with needs the call itself, "
        "and the value walk answers only values — measured on the CP-54 probe module, every "
        "read of `ProbeKt#client` answers `external` at the unscanned factory. Without the "
        "stop, every path ends where the value walk ends it, so the reader names no call for "
        "a client whose construction is a fact, and the base its block sets is never read",
        edits=(
            Edit(
                path=_VALUES,
                find="        if identity not in self._declared:",
                replace="        if True:  # guard disabled by scripts/guard_check.py",
            ),
        ),
    ),
    "values.a-STATIC-FIELD-receiver-is-followed-to-its-writer": Guard(
        what="a call receiver read by `getstatic` is resolved as the field D00 §5's "
        "`receiver_field` names",
        why="the receiver's own value id is the `getstatic` instruction, which no other fact "
        "names, so `val derived = client.config { }` at file level reaches no parent: the "
        "derived client's relative call loses the base Ktor sends it to (CP-54 row 80)",
        edits=(
            Edit(
                path=_VALUES,
                find='            field = site.get("receiver_field")\n',
                replace="            field = None  # guard disabled by scripts/guard_check.py\n",
            ),
        ),
    ),
    "values.a-declared-CONSTRUCTOR-is-a-producer": Guard(
        what="a value BUILT by a declared constructor ends the producer reader's path at that "
        "construction, as a declared factory call does",
        why="a construction carries no `produced_by` edge (`call_sites.result` is null for an "
        "initialiser), so the factory stop never sees it. Without the construction stop, a "
        "client built with `new` reaches the value walk's answer, the constructed TYPE, and "
        "the reader names no call for a construction that is a fact; a declared `<init>` "
        "would silently never match",
        edits=(
            Edit(
                path=_VALUES,
                find="        if self._identified(site) is None and self._declared_producer(site) "
                "is None:",
                replace="        if self._identified(site) is None:  "
                "# guard disabled by scripts/guard_check.py",
            ),
            Edit(
                path=_VALUES,
                find="""            if constructed is not None:
                stopped = self._declared_producer((method, constructed))
                if stopped is not None:
                    return _only(trail, stopped)
""",
                replace="            pass  # guard disabled by scripts/guard_check.py\n",
            ),
        ),
    ),
    "values.the-producer-stop-comes-BEFORE-the-returns": Guard(
        what="the producer reader stops at a declared call BEFORE reading that call's returns",
        why="a declared call whose body is in this module would otherwise be crossed, and the "
        "path would end at whatever the body hands back: a literal, or a call inside the "
        "body. The reader then names no call, or a call the caller never declared, for the "
        "one it asked about, and the block that set the client's base is not the one read",
        edits=(
            Edit(
                path=_VALUES,
                find="""        if producers:
            stopped = self._declared_producer((method, min(producers)))
            if stopped is not None:
                return self._along(stopped, trail, frames)
        reached: list[_Reached] = []
""",
                replace="        reached: list[_Reached] = []\n",
            ),
            Edit(
                path=_VALUES,
                find="""        if reached:
            return tuple(reached)
        if not producers:
""",
                replace="""        if reached:
            return tuple(reached)
        if producers:  # guard disabled by scripts/guard_check.py: the stop moved down
            stopped = self._declared_producer((method, min(producers)))
            if stopped is not None:
                return _only(trail, stopped)
        if not producers:
""",
            ),
        ),
    ),
    "values.the-PRODUCER-reader-matches-the-declared-OWNER": Guard(
        what="a producing call is the declared one only where its owner matches as well as "
        "its method name",
        why="method names repeat across types — `config`, `create`, `build`, `of` — so a stop "
        "matched on the name alone names a call on some other type as the client's producer, "
        "and the reader then reads a base out of a block that configures something else: a "
        "wrong address at `resolved`",
        edits=(
            Edit(
                path=_VALUES,
                find="        if identity not in self._declared:",
                replace='        if row["name"] not in {name for _, name in self._declared}:  '
                "# guard disabled by scripts/guard_check.py",
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
                path=_CHAINS,
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
                path=_CHAINS,
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
                path=_CHAINS,
                find="        name in context.via_argument_names and _has_execute_join(site, context)",
                replace="        name in context.via_argument_names  # guard disabled by scripts/guard_check.py",
            ),
        ),
    ),
    "chains.a-MODULE-call-never-stops-the-join-walk": Guard(
        what="the execute-join's producer walk stops only at a terminal-named call whose body "
        "is NOT in the module; the module's own `build()` is crossed to the library call inside",
        why="a module helper or class named like the terminal — `sendMessage(build())`, "
        "dolphinscheduler's `QuartzJobDetailBuilder.build()` wrapping `newJob(…)…build()` — "
        "would end the walk at the module call, pairing the executing call with a site no chain "
        "walk reaches as a terminal; the real chain inside then derives nothing, and nothing "
        "reports the missing boundary",
        edits=(
            Edit(
                path=_CHAINS,
                find="    terminals -= in_module\n",
                replace="    pass  # guard disabled by scripts/guard_check.py\n",
            ),
        ),
    ),
    "chains.the-EXECUTE-JOIN-crosses-methods": Guard(
        what="the execute-join pairs a built value with a declared executing call wherever "
        "the value walk (`values.producers_of`) traces that call's argument back to the "
        "terminal site — in the same method, or across returns and parameters",
        why="a request built in a helper and returned to the method that sends it is a "
        "request the module issues. Matching only an argument's own `source` in the same "
        "method drops it: `sqs.sendMessage(request())` and `client.send(deleteRequest(), …)` "
        "publish no outbound row at all, and a Quartz trigger built in a helper never pairs "
        "with the `scheduleJob` that registers it — a missing boundary nothing reports",
        edits=(
            Edit(
                path=_CHAINS,
                find="    for consumer in context.joined.get(_site_key(site), ()):\n",
                replace="    for consumer in ():  # guard disabled by scripts/guard_check.py\n",
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
                path=_CHAINS,
                find="    elif terminal is not None:\n        context.ends.append(",
                replace="    elif True:  # guard disabled by scripts/guard_check.py\n"
                "        context.ends.append(",
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
    "endpoints.a-rewrite-matches-a-row-by-its-ROW-ID": Guard(
        what="a pass that rewrites an `endpoints` row after it was minted finds that row by its "
        "`row_id`, never by its address (follow-the-object, ruling 7)",
        why="`(protocol, direction, method, path)` is not unique and the address is what the "
        "rewrites change. Matched by path, the configured prefix moves every row at the chosen "
        "row's address — a call the module makes to `/x` on another service is published at "
        "`/shop/x`, an address that service does not serve",
        edits=(
            Edit(
                path="sextant/storage/duckdb/prefix_endpoint_paths.sql",
                find="WHERE e.row_id = h.row_id;",
                replace="WHERE e.path IS NOT DISTINCT FROM "
                "(SELECT x.path FROM endpoints x WHERE x.row_id = h.row_id);  -- guard disabled",
            ),
        ),
    ),
    "endpoints.a-stashed-requirement-is-joined-by-ROW-ID": Guard(
        what="the requirements pass joins the combinator's stash to its rows by the `row_id` the "
        "stash bound when it was written, never by the columns the route was minted with",
        why="the requirements pass runs after the configured path prefix, which rewrites `path`. "
        "Joined on the minted path, every requirement of a prefixed route finds no row and is "
        "dropped: in any module with a context path, every functional route published with no "
        "requirements at all (measured on `orders-contextpath` before ruling 7)",
        edits=(
            Edit(
                path="sextant/application/resolve/request_requirements.py",
                find='    by_row = {e["row_id"]: e for e in endpoints}',
                replace="    by_row = {  # guard disabled by scripts/guard_check.py\n"
                '        (e["caller"], e["handler"], e["method"], e["path"], e["catalog_id"]): e\n'
                "        for e in endpoints\n"
                "    }",
            ),
            Edit(
                path="sextant/application/resolve/request_requirements.py",
                find='        e = by_row.get(r["row_id"])',
                replace='        e = by_row.get((r["caller"], r["handler"], r["method"], r["path"], '
                'r["catalog_id"]))',
            ),
        ),
    ),
    "endpoints.an-attached-entry-follows-its-row-by-ROW-ID": Guard(
        what="an `endpoint_metadata` entry follows the row it was bound to, by `row_id`, when a "
        "pass moves that row",
        why="`fluent` and `single_call` write an entry in the pass that mints its row, before the "
        "path prefix runs. Matched to its row by address, the entry stays at `/x` while the row "
        "moves to `/shop/x`: the bundle publishes a header for an address nothing serves, and a "
        "reader joining the two tables on the address loses it (review focus 4 of the "
        "2026-10-30 plan)",
        edits=(
            Edit(
                path="sextant/storage/duckdb/follow_endpoint_rows.sql",
                find="WHERE m.row_id = e.row_id\n  AND (",
                replace="WHERE m.row_id = e.row_id AND m.path IS NOT DISTINCT FROM e.path  "
                "-- guard disabled\n  AND (",
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
    "effective-calls.AUTOBOXING-reads-as-its-constant": Guard(
        what="an argument produced by one of the eight javac boxing calls (`<Wrapper>.valueOf"
        "(<prim>)`) handed a constant is read by every engine as that constant, in an array's "
        "elements as much as in a single slot",
        why="Quartz spec 2026-10-28, CP-55 rows 20-22. javac wraps `onDaysOfTheWeek(3, 5)` as an "
        "`Integer[]` of `valueOf` results, each an `unresolved` the value walk cannot read. "
        "With the projection skipped, a weekday set and every boxed constant handed to a "
        "builder is a hole in the schedule the source states plainly: the entry publishes no "
        "days, or marks a fully constant schedule unresolved",
        edits=(
            Edit(
                path=_EFFECTIVE_CALLS,
                find="        if boxed:\n            row = _with_unboxed(row, boxed)",
                replace="        if False:  # guard disabled by scripts/guard_check.py\n"
                "            row = _with_unboxed(row, boxed)",
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
    "schedules.a-PLACEHOLDER-expression-is-read-per-environment": Guard(
        what="a scheduled job whose expression holds a placeholder gets one "
        "`resolved_schedules` row per environment of `resolved_config`, its value read "
        "from that environment's configuration (spec 2026-10-23-configured-schedules §3b)",
        why="without it `scheduled_work` is the only answer, `unresolved` with the "
        "expression verbatim, and a job whose cron the module's own files set in every "
        "environment reads as a schedule nothing in the repository says — COVERAGE §5.12's "
        "one limited `@Scheduled` row",
        edits=(
            Edit(
                path=_RESOLVED_SCHEDULES,
                find='    if rows:\n        workspace.derive("resolved_schedules_insert", rows=rows)\n',
                replace="    # guard disabled by scripts/guard_check.py\n",
            ),
        ),
    ),
    "schedules.an-ANNOTATION-default-applies-where-no-environment-sets-the-key": Guard(
        what="`${key:default}` in a scheduled expression resolves to the default in an "
        "environment whose configuration sets no `key`, through the config model's own "
        "`default_separator` — the one placeholder rule `resolve_config` applies",
        why="read without the separator, the default is part of the key, so the ordinary "
        '`@Scheduled(cron = "${orders.sweep.cron:0 0 * * * *}")` — a schedule the '
        "annotation itself fixes wherever configuration is silent — reads `missing_key` in "
        "every environment",
        edits=(
            Edit(
                path=_RESOLVED_SCHEDULES,
                find='                str(job["expression"]), placeholders, _recording(lookup, asked)\n',
                replace='                str(job["expression"]), {**placeholders, "default_separator": ""}, '
                "_recording(lookup, asked)  # guard disabled\n",
            ),
        ),
    ),
    "schedules.the-DOCUMENT-states-a-schedules-configured-values": Guard(
        what="the document states, under a placeholder job's row, what this repository "
        "configures for it per environment, from `resolved_schedules` (spec "
        "2026-10-23-configured-schedules §3c)",
        why="the table is the end of the feature: without the line, `resolved_schedules` is "
        "written and exported and the document a person opens still shows only "
        "`${orders.sweep.cron}` `unresolved` — the answer reaches every exit but the one read",
        edits=(
            Edit(
                path="sextant/egress/render/document.py",
                find="_scheduled_work_sections(report.scheduled_work, report.resolved_schedules, "
                "beans, redactor)",
                replace="_scheduled_work_sections(report.scheduled_work, [], beans, redactor)",
            ),
        ),
    ),
    "schedules.a-configured-VALUE-is-masked-on-export": Guard(
        what="`resolved_schedules.value` leaves the bundle through `redact_schedule_value`, "
        "joined from the map staged on (keys, value)",
        why="the column is configuration read into the bundle; unjoined, a value the module "
        "configured with a credential in it ships in the clear while the workspace's every "
        "other exit masks it — the one-exit-forgot defect `field_writes.value` shipped",
        edits=(
            Edit(
                path=_WORKSPACE,
                find="               s.environment, s.keys, coalesce(v.masked, s.value) AS value,\n",
                replace="               s.environment, s.keys, s.value AS value,  -- guard disabled\n",
            ),
        ),
    ),
    "schedules.an-EXPRESSION-is-masked-on-export": Guard(
        what="`scheduled_work.expression` and `resolved_schedules.expression` leave the "
        "bundle through `redact_text`, staged into the address map",
        why="the expression is the annotation literal `annotations.args` masks on the way "
        "out; unstaged, the same literal ships in the clear in two files beside the one "
        "that hides it",
        edits=(
            Edit(
                path=_WORKSPACE,
                find='            "UNION SELECT DISTINCT expression FROM scheduled_work WHERE expression IS NOT NULL "\n'
                '            "UNION SELECT DISTINCT expression FROM resolved_schedules "\n'
                '            "WHERE expression IS NOT NULL "\n',
                replace='            ""  # guard disabled\n',
            ),
        ),
    ),
    "schedules.an-EXPRESSION-is-masked-in-the-document": Guard(
        what="the document prints a schedule's expression through the render redactor, in "
        "the scheduled-work table and in a placeholder job's detail header",
        why="the bundle masks the expression in three files; a document printing it raw "
        "hands a reader the literal the bundle withheld",
        edits=(
            Edit(
                path="sextant/egress/render/document.py",
                find='                row["expression"],\n                lambda value: redactor.redact_text(str(value)),\n',
                replace='                row["expression"],\n                str,  # guard disabled\n',
            ),
            Edit(
                path="sextant/egress/render/document.py",
                find='        header += _code(redactor.redact_text(str(row["expression"])))\n',
                replace='        header += _code(str(row["expression"]))  # guard disabled\n',
            ),
        ),
    ),
    "schedules.a-NAME-is-masked-at-every-exit": Guard(
        what="a trigger's `name` leaves the bundle, the document and the diff through "
        "`redact_text`, as `expression` does",
        why="the name is a `withIdentity(name, group)` literal, which the bundle masks in "
        "`call_sites.arguments`; printed raw by any exit it ships the literal another file "
        "withheld",
        edits=(
            Edit(
                path="sextant/storage/duckdb/workspace.py",
                find="        SELECT w.handler, w.trigger, coalesce(n.masked, w.name) AS name,\n",
                replace="        SELECT w.handler, w.trigger, w.name AS name,  -- guard disabled\n",
            ),
            Edit(
                path="sextant/egress/render/document.py",
                find='                row["name"],\n                lambda value: redactor.redact_text(str(value)),\n',
                replace='                row["name"],\n                str,  # guard disabled\n',
            ),
            Edit(
                path="sextant/application/boundary/diff.py",
                find='            projected["name"] = redactor.redact_text(str(projected["name"]))\n',
                replace='            projected["name"] = projected["name"]  # guard disabled\n',
            ),
        ),
    ),
    "schedules.an-EMPTY-cell-says-why-it-is-empty": Guard(
        what="the document reads an empty `scheduled_work` part as `—` and an untied NULL as "
        "`not tied down`, never `not in the code`",
        why="`not in the code` is false for a name the framework never gives and for a value "
        "the code states but no path ties to the row (ruled 2026-10-29)",
        edits=(
            Edit(
                path="sextant/egress/render/document.py",
                find="    return isinstance(untied, (list, tuple)) and part in untied\n",
                replace="    return False  # guard disabled\n",
            ),
            Edit(
                path="sextant/egress/render/document.py",
                find='    if value == "":\n        return _text(_DOES_NOT_APPLY)\n',
                replace="    # guard disabled\n",
            ),
        ),
    ),
    "schedules.an-EXPRESSION-is-masked-in-the-DIFF": Guard(
        what="the boundary diff passes a schedule's `expression` through `redact_text`, the "
        "call the bundle export makes on `scheduled_work.expression`",
        why="the bundle masks the expression; a diff reading a workspace verbatim reports "
        "every masked schedule as changed between a bundle and the workspace it came from, "
        "and prints the literal the bundle withheld",
        edits=(
            Edit(
                path="sextant/application/boundary/diff.py",
                find='    if kind.name == "schedule":\n',
                replace="    if False:  # guard disabled by scripts/guard_check.py\n",
            ),
        ),
    ),
    "placeholders.a-DEFAULT-holding-a-placeholder-is-resolved": Guard(
        what="a placeholder's default is resolved through the same lookup as its key, so "
        "`${a:${b}}` is `b`'s value where `a` is unset (CP-48 row 7)",
        why="Spring's `NestedPlaceholderPart.resolve` resolves the default's parts; taken as "
        'text, `@Scheduled(cron = "${jobs.sweep.cron:${jobs.default.cron}}")` and a '
        "configuration value written the same way read as a literal `${…}` in every "
        "environment that sets only the shared default",
        edits=(
            Edit(
                path=_CONFIG,
                find="    return _resolved_parts(default_parts, separator, lookup)\n",
                replace='    return "".join(p for p in default_parts if isinstance(p, str)), None'
                "  # guard disabled\n",
            ),
        ),
    ),
    "placeholders.a-placeholder-ENDS-at-the-closer-that-balances-it": Guard(
        what="a placeholder ends at the closer at depth zero, each `nest` opener passed "
        "raising the depth (CP-48 row 3, `nextValidEndPrefix`)",
        why="ended at the first closer, `${missing:${a}}` reads the inside `missing:${a` and "
        "keeps the trailing `}` — the literal `${a}` the branch shipped before its final "
        "review, where Spring substitutes `a`",
        edits=(
            Edit(
                path=_CONFIG,
                find="            if depth == 0:\n                return index\n",
                replace="            if True:  # guard disabled by scripts/guard_check.py\n"
                "                return index\n",
            ),
        ),
    ),
    "spring-web.the-placeholder-NEST-opener-is-the-frameworks-own": Guard(
        what='Spring\'s config model declares `placeholders.nest: "{"`, the opener '
        "`PlaceholderParser` counts for depth (CP-48 row 2)",
        why="without it the depth is counted by the whole opener `${`, and a bare brace inside "
        "a placeholder (`${k{x}:d}`) ends it early — a key and default Spring never reads",
        edits=(
            Edit(
                path="sextant/catalogs/spring-web.yml",
                find='    nest: "{"\n',
                replace="",
            ),
        ),
    ),
    "schedules.a-value-whose-KEY-names-a-secret-is-masked-whole": Guard(
        what="a configured schedule masks WHOLE where a key its expression was read through "
        "names a secret, at the bundle and the document alike (`redact_schedule_value`)",
        why='`@Scheduled(cron = "${app.token.cleanup.cron}")`: `resolved_config` masks the '
        "key's value by the key rule, and without the test the schedule that IS that value "
        "ships in the clear beside it — one exit undoing the mask the other applied",
        edits=(
            Edit(
                path=_RESOLVED_SCHEDULES,
                find="    if any(redactor.masks_key(key) for key in keys):\n",
                replace="    if False:  # guard disabled by scripts/guard_check.py\n",
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
    "messaging.an-ORPHAN-channel-takes-the-sole-connector": Guard(
        what="a SmallRye channel no connector manages and only one direction carries takes "
        "its direction's connector when exactly ONE is on the classpath",
        why="spec 2026-10-24 ruling 2, Quarkus's own rule (CP-50 rows 7, 17): "
        "`autoConfigureConnectorForOrphansAndProduceManagedChannels` attaches the sole "
        "connector of a direction to every orphan as a run-time configuration default. 13 of "
        "the 15 measured quickstart modules configure no connector at all and rely on it, so "
        'without the attachment the kafka quickstart\'s own processor — `@Incoming("requests") '
        '@Outgoing("quotes")` beside `quarkus-messaging-kafka` — is two real Kafka '
        "boundaries the document does not show",
        edits=(
            Edit(
                path="sextant/application/resolve/engines/config_join.py",
                find="        elif len(serving) == 1:\n            wired.append(_destined(",
                replace="        elif False:  # guard disabled by scripts/guard_check.py\n"
                "            wired.append(_destined(",
            ),
        ),
    ),
    "messaging.every-CONNECTOR-counts-toward-the-sole-one": Guard(
        what="every connector in the module's dependency set counts toward the sole-connector "
        "test — a COUNTED entry (no protocol: MQTT, Camel, in-memory) as much as a read one",
        why="CP-50 rows 6, 16: Quarkus's `discoverConnectors` collects every bean carrying "
        "`@Connector`, whatever it speaks. Counting only the connectors the table reads a "
        "wire for makes Kafka the 'sole' connector of a module that also carries MQTT, so "
        "every unconfigured orphan is published as a Kafka topic Quarkus never attaches — a "
        "fabricated boundary DR-5 then links into Kafka consumers' graphs — and leaves a "
        "module whose only connector is MQTT silent where Quarkus does attach it",
        edits=(
            Edit(
                path="sextant/application/resolve/engines/config_join.py",
                find="        for connector in wiring[_CONNECTORS]\n"
                "        if not declared.isdisjoint(",
                replace="        for connector in wiring[_CONNECTORS]\n"
                "        if _READ_BY_PROTOCOL in connector and not declared.isdisjoint(",
            ),
        ),
    ),
    "messaging.an-ORPHAN-with-no-TABLED-connector-asks": Guard(
        what="a SmallRye orphan with no connector of its direction from the connector table "
        "in the dependency set is a `binder_protocol` question with no binder, never silence",
        why="final review finding 1: the engine sees zero TABLED connectors, not zero "
        "connectors. A Quarkiverse connector (NATS JetStream, Solace) as a module's only one "
        "is the sole connector Quarkus attaches (CP-50 row 7) and its coordinates are in no "
        "entry, so dropping the orphan removes a broker boundary from the document with no "
        "row, gap or question saying one was there",
        edits=(
            Edit(
                path="sextant/application/resolve/engines/config_join.py",
                find="        else:\n            reason = _NO_TABLED_CONNECTOR",
                replace="        elif False:  # guard disabled by scripts/guard_check.py\n"
                "            reason = _NO_TABLED_CONNECTOR",
            ),
        ),
    ),
    "messaging.an-IN-MEMORY-channel-is-no-boundary": Guard(
        what="a SmallRye channel name the module both produces and consumes is never an "
        "orphan, takes no connector and gives no row",
        why="CP-50 rows 1, 11: `detectOrphanChannels` keys each direction's channels by name "
        "and `removeAll`s the other direction's, so a name both directions carry is an "
        "in-process pipe. Without the check the sole connector is attached to both halves "
        "and the document publishes a broker topic, inbound and outbound, for a hand-off "
        "that never leaves the process — two fabricated boundaries that DR-5 then links "
        "into any other service using the same topic name",
        edits=(
            Edit(
                path="sextant/application/resolve/engines/config_join.py",
                find="        if channel.name in carried[other]:\n            continue",
                replace="        if False:  # guard disabled by scripts/guard_check.py\n"
                "            continue",
            ),
        ),
    ),
    "messaging.the-CONNECTOR-table-names-the-protocol": Guard(
        what="a wired SmallRye channel speaks the protocol of the connector that wires it — "
        "the connector table's entry, never one fixed value",
        why="spec 2026-10-24 ruling 1: one catalog reads six connectors, and `protocol` is "
        "identity — DR-5 links on it. A fixed protocol publishes every AMQP, RabbitMQ, "
        "Pulsar, JMS and SQS channel as Kafka, linking each into Kafka consumers' graphs it "
        "never speaks to; the catalog's own `protocol:` line exists only because "
        "`resolve/endpoints.py` requires one of a row-minting file",
        edits=(
            Edit(
                path="sextant/application/resolve/engines/config_join.py",
                find='    protocol = str(connector["protocol"])',
                replace='    protocol = "kafka"  # guard disabled by scripts/guard_check.py',
            ),
        ),
    ),
    "messaging.wired-questions-ride-the-dependency-gate": Guard(
        what="the wiring's questions are filed only for a module whose build names a "
        "SmallRye artifact — the gate `run` passed through",
        why="the `service_identity` seam re-checks neither `requires` nor the dependency gate, "
        "and the wiring reads `resolved_config`, which a module without SmallRye still has. "
        "Ungated, a module whose build declares no messaging at all files a question "
        "asserting a channel wired to `smallrye-mqtt` exists, for a catalog the run "
        "declined — `_bean_name_questions`' own defect, one mode over",
        edits=(
            Edit(
                path="sextant/application/resolve/engines/config_join.py",
                find="    if unmet_dependency(workspace, catalog) is not None:\n        return []\n"
                "    rows: list[dict[str, Any]] = []\n    for wired in _wired(",
                replace="    if False:  # guard disabled by scripts/guard_check.py\n        return []\n"
                "    rows: list[dict[str, Any]] = []\n    for wired in _wired(",
            ),
        ),
    ),
    "grpc.the-QUARKUS-service-annotation-corroborates": Guard(
        what="`io.quarkus.grpc.GrpcService` is on `grpc-spring.yml`'s corroboration list, "
        "beside the Spring and net.devh spellings",
        why="spec 2026-10-24 ruling 3, CP-52 rows 1, 7: Quarkus REQUIRES the annotation on "
        "every service bean, so it flags every served class. For a service built against "
        "a PUBLISHED stubs jar the supertype match derives nothing and the annotation is "
        "the only evidence a gRPC service is served at all; without the entry that class "
        "is silence, which 2O design §1b rules out",
        edits=(
            Edit(
                path="sextant/catalogs/grpc-spring.yml",
                find="      - io.quarkus.grpc.GrpcService\n",
                replace="",
            ),
        ),
    ),
    "grpc.a-WRAPPER-takes-the-one-identity-it-delegates-to": Guard(
        what="an outer class whose nest reaches TWO different marked classes has no "
        "delegated identity; only a nest that reaches exactly one takes it",
        why="spec 2026-10-25 §3a: a facade over two generated services, or a base class "
        "that calls both, does not state which service it is. Taking the first one "
        "reached would file its RPCs under a service it only half belongs to — a "
        "fabricated service identity, in the same place `_correlated` refuses a guess",
        edits=(
            Edit(
                path="sextant/application/resolve/shapes/identity_calls.py",
                find="        if len(reached) == 1:\n",
                replace="        if reached:  # guard disabled by scripts/guard_check.py\n",
            ),
        ),
    ),
    "grpc.a-QUARKUS-client-field-is-an-outbound-service": Guard(
        what="a field annotated `io.quarkus.grpc.GrpcClient` derives the outbound service-"
        "level row of the stub it is declared as, and net.devh's annotation of the same "
        "simple name does not",
        why="spec 2026-10-24 ruling 3, CP-52 rows 2, 4: a wrong FQN in an `injected_client` "
        "catalog is SILENT (W53) — the annotation never matches, nothing is derived and "
        "no skip or gap says a name was wrong, so every Quarkus gRPC client is missing "
        "from the document. The weakening is the other framework's FQN, the mistake a "
        "copy of `grpc-net-devh.yml` makes: the Quarkus fields stop deriving and "
        "net.devh's start deriving under a catalog that claims Quarkus",
        edits=(
            Edit(
                path="sextant/catalogs/grpc-quarkus-client.yml",
                find="  field_annotation: io.quarkus.grpc.GrpcClient",
                replace="  field_annotation: net.devh.boot.grpc.client.inject.GrpcClient",
            ),
        ),
    ),
    "grpc.a-QUARKUS-service-implementing-its-interface-is-the-handler": Guard(
        what="a `@GrpcService` class implementing the interface a generated Mutiny bean's "
        "`delegate` field is declared as is the handler of that bean's RPCs, under the "
        "identity the bean's base delegates to",
        why="spec 2026-10-25 §3b, CP-53 rows 8-11: `@GrpcService class X implements Greeter` "
        "is the form both Quarkus quickstarts write. Without the delegate form its RPCs keep "
        "the `.proto`'s handler-less row plus a `service_identity` question, so the service "
        "a Quarkus module serves has no handler in the document and no trace reaches it",
        edits=(
            Edit(
                path="sextant/application/resolve/engines/supertype_derived.py",
                find='    bean = catalog.matches.get("delegating_bean")\n',
                replace="    bean = None  # guard disabled by scripts/guard_check.py\n",
            ),
        ),
    ),
    "grpc.the-GENERATED-bean-is-never-a-handler": Guard(
        what="under a catalog naming `served_by_annotation`, an implementer that does not "
        "declare that annotation itself matches no form, so the generated Mutiny bean "
        "(which carries none) is never a handler",
        why="CP-52 row 7, CP-53 row 9: Quarkus serves only `@GrpcService` classes and reads "
        "the annotation declared on the class. `GreeterBean` extends the delegating base and "
        "declares every RPC method, so without the check it is published as the handler of "
        "every RPC, ahead of the user's class, and a bean with no service behind it is "
        "published as a served service",
        edits=(
            Edit(
                path="sextant/application/resolve/engines/supertype_derived.py",
                find="        if served is not None and implementer not in served:\n",
                replace="        if False:  # guard disabled by scripts/guard_check.py\n",
            ),
        ),
    ),
    "grpc.a-user-base-calling-a-stub-is-not-a-SERVICE": Guard(
        what="under `service_supertype`, a supertype whose outer class only DELEGATES to a "
        "marked class matches only if it implements the named service type",
        why="spec 2026-10-25 §3a: a user base class that calls `GreeterGrpc.newBlockingStub` "
        "delegates to `GreeterGrpc` exactly as the Mutiny base does. Without the "
        "`BindableService` conjunct every subclass of it overriding a method is published "
        "as an inbound gRPC handler of a service it only calls — the C-1 fabrication again",
        edits=(
            Edit(
                path="sextant/application/resolve/engines/supertype_derived.py",
                find="        if not _reaches(supertype, _catalog_symbol(self.service_supertype), "
                "self.parents):\n            return None\n",
                replace="",
            ),
        ),
    ),
    "grpc.the-DELEGATE-form-is-off-when-the-base-has-another-subclass": Guard(
        what="a delegating bean whose base has a subclass other than the bean serves nothing",
        why="CP-53 row 10: Quarkus skips such a bean, and the class extending the base "
        "directly is the one served. Without the check the interface's implementor is "
        "published as a second handler of the same RPC, one Quarkus never serves",
        edits=(
            Edit(
                path="sextant/application/resolve/engines/supertype_derived.py",
                find="    if subclasses != {bare_descriptor(bean_class)}:\n",
                replace="    if False:  # guard disabled by scripts/guard_check.py\n",
            ),
        ),
    ),
    "grpc.the-DELEGATE-form-is-off-when-a-module-extends-the-delegated-nest": Guard(
        what="a delegating bean serves nothing when a module class outside the marked class "
        "its base delegates to extends a class nested in that marked class",
        why="CP-53 row 10's second condition: Quarkus skips the bean when the module extends "
        "the plain generated base (the base's name with `Mutiny` removed), and that class is "
        "served by the extends form. Without the check the interface's implementor is "
        "published as a second handler of the same RPC, one Quarkus never serves",
        edits=(
            Edit(
                path="sextant/application/resolve/engines/supertype_derived.py",
                find="    return not any(\n"
                "        outer_of(parent, hosts) == outer and outer_of(child, hosts) != outer\n"
                "        for child, parent in superclass_of.items()\n"
                "    )\n",
                replace="    return True  # guard disabled by scripts/guard_check.py\n",
            ),
        ),
    ),
    "grpc.two-ANNOTATED-implementors-serve-neither": Guard(
        what="two or more annotated implementors of a bean's delegate type name no handler; "
        "the question names them all",
        why="CP-53 row 9: Quarkus delegates to the first its index yields, an order nothing "
        "in the facts fixes. Taking the first in sort order publishes a handler that is "
        "right only by chance, with no question saying it was a guess",
        edits=(
            Edit(
                path="sextant/application/resolve/engines/supertype_derived.py",
                find="            if len(handlers) > 1:\n",
                replace="            if False:  # guard disabled by scripts/guard_check.py\n",
            ),
        ),
    ),
    "grpc.an-UNANNOTATED-implementor-of-the-delegate-is-not-served": Guard(
        what="a class implementing a bean's delegate type is its handler only if it declares "
        "the catalog's serving annotation",
        why="CP-53 row 9: Quarkus delegates only to an implementor carrying `@GrpcService`. "
        "The generated `GreeterClient` implements the same interface, so without the filter "
        "every Quarkus service is contended with its own client and loses its handler",
        edits=(
            Edit(
                path="sextant/application/resolve/engines/supertype_derived.py",
                find="        pool &= served\n",
                replace="        pass  # guard disabled by scripts/guard_check.py\n",
            ),
        ),
    ),
    "grpc.a-SELF-call-is-not-an-outbound-row": Guard(
        what="an outbound `grpc` row for a service the module serves (an inbound row with a "
        "handler) and whose peer is absent or this module is removed",
        why="spec 2026-10-25 ruling 1: a service that calls its own inbound endpoints is a "
        "traceable hop, not an outbound call. Without the pass, a Quarkus or Spring service "
        "that injects a client of the service it serves publishes a call to a far end that "
        "is itself",
        edits=(
            Edit(
                path="sextant/application/resolve/self_calls.py",
                find="    if not served:\n        return\n",
                replace="    if True:  # guard disabled by scripts/guard_check.py\n        return\n",
            ),
        ),
    ),
    "grpc.a-DESCRIPTOR-only-inbound-row-serves-nothing": Guard(
        what="only an inbound `grpc` row with a handler names a service this module serves; a "
        "row the `.proto` alone derives (handler NULL) serves nothing",
        why="spec 2026-10-25 §3c: a client-only module compiles the `.proto` too, so it has "
        "an inbound descriptor row for every RPC it calls. Counted as served, every client "
        "row of such a module is dropped as a self-call, and the services it calls vanish "
        "from the document",
        edits=(
            Edit(
                path="sextant/application/resolve/self_calls.py",
                find='            or row["handler"] is None\n',
                replace="",
            ),
        ),
    ),
    "grpc.a-call-naming-ANOTHER-host-stays-outbound": Guard(
        what="an outbound row whose peer names a host that is not this module is kept",
        why="spec 2026-10-25 ruling 3: the same service name at another address is another "
        "deployment's copy, and a pass that dropped every row would erase a real outbound "
        "call",
        edits=(
            Edit(
                path="sextant/application/resolve/self_calls.py",
                find="    return host.lower() in _LOOPBACK\n",
                replace="    return True  # guard disabled by scripts/guard_check.py\n",
            ),
        ),
    ),
    "grpc.a-SERVED-identity-matches-exactly": Guard(
        what="an outbound row is dropped only when its path IS a served service identity, "
        "not when it merely starts with one",
        why="spec 2026-10-25 §3c: `helloworld.GreeterAdmin` and `helloworld.Greeter.v2` are "
        "other services than `helloworld.Greeter`. A prefix match would erase a real "
        "outbound call to a service this module does not serve",
        edits=(
            Edit(
                path="sextant/application/resolve/self_calls.py",
                find='        and str(row["path"]) in served\n',
                replace='        and any(str(row["path"]).startswith(k) for k in served)  # guard disabled by scripts/guard_check.py\n',
            ),
        ),
    ),
    "grpc.a-STUB-call-to-a-served-rpc-is-a-hop": Guard(
        what="a generated client stub's call to an RPC this module serves is written as an "
        "`rpc_hops` row naming the handler it lands on",
        why="spec 2026-10-25 ruling 2: a self-call is a traceable hop. Without the row the "
        "trace from a REST method through `GreeterBlockingStub#sayHello` stops at "
        "`ClientCalls#blockingUnaryCall`, and with the outbound row fenced the call is "
        "lost from the document altogether",
        edits=(
            Edit(
                path="sextant/application/resolve/rpc_hops.py",
                find='    if rows:\n        workspace.derive("rpc_hops_insert", rows=rows)\n',
                replace="    if False:  # guard disabled by scripts/guard_check.py\n"
                '        workspace.derive("rpc_hops_insert", rows=rows)\n',
            ),
        ),
    ),
    "grpc.only-a-STUB-method-gets-a-hop": Guard(
        what="only a method of a class whose ancestry reaches `client_stub_supertype` is "
        "read for a hop",
        why="spec 2026-10-25 §3d: the caller is a client stub method. Without the filter, a "
        "generated server-side `AsyncService` default method, or a hand-written method "
        "calling `ClientCalls` with a generated accessor directly, gets a hop the stub "
        "classes alone are evidence for",
        edits=(
            Edit(
                path="sextant/application/resolve/rpc_hops.py",
                find='        if caller_outer_class(str(row["caller"])) in stubs\n',
                replace="        if True  # guard disabled by scripts/guard_check.py\n",
            ),
        ),
    ),
    "grpc.a-stub-naming-TWO-wire-methods-gets-no-hop": Guard(
        what="a stub method whose accessors name more than one wire method gets no hop",
        why="spec 2026-10-25 §3d: exactly one wire method, or no row. Taking the first would "
        "land a call on the handler of an RPC it may not make, a hop the code does not take",
        edits=(
            Edit(
                path="sextant/application/resolve/rpc_hops.py",
                find="        if len(named) != 1:\n",
                replace="        if not named:  # guard disabled by scripts/guard_check.py\n",
            ),
        ),
    ),
    "grpc.a-stub-of-a-service-NOT-served-gets-no-hop": Guard(
        what="a stub call gets a hop only when its service identity is one this module "
        "serves, not whenever the module serves some service",
        why="spec 2026-10-25 §3d: a module serving `Hello` that calls `Greeter` through its "
        "stub makes an outbound call. A hop there lands on no handler and replaces the "
        "`ClientCalls` boundary with a wire path into a service the module does not have",
        edits=(
            Edit(
                path="sextant/application/resolve/rpc_hops.py",
                find="        if identity is None or identity not in served:\n",
                replace="        if identity is None:  # guard disabled by scripts/guard_check.py\n",
            ),
            Edit(
                path="sextant/application/resolve/rpc_hops.py",
                find="served[identity].get(path, set())",
                replace="served.get(identity, {}).get(path, set())",
            ),
        ),
    ),
    "grpc.no-CLIENT-CALL-site-means-no-hop": Guard(
        what="a stub method gets a hop only at a call site whose target belongs to the "
        "catalog's `client_call_owner`",
        why="spec 2026-10-25 §3d: the hop is keyed by the call site where the call leaves for "
        "the wire. A stub method that never calls `ClientCalls` has no such site, and a row "
        "with no ordinal joins no `call_edges` row: a hop the walk can never take",
        edits=(
            Edit(
                path="sextant/application/resolve/rpc_hops.py",
                find="        if ordinal is None:\n            continue\n",
                replace="",
            ),
        ),
    ),
    "grpc.an-UNHANDLED-rpc-of-a-served-service-gets-a-hop": Guard(
        what="a stub call to an RPC of a served service that has no handler here still gets "
        "one `rpc_hops` row, its handler NULL",
        why="spec 2026-10-25 §3d: the outbound row of a served service is fenced, so without "
        "the row the step carries no wire path and the call's destination is nowhere in the "
        "document",
        edits=(
            Edit(
                path="sextant/application/resolve/rpc_hops.py",
                find="        for handler in handlers or [None]:\n",
                replace="        for handler in handlers:  # guard disabled by scripts/guard_check.py\n",
            ),
        ),
    ),
    "injected_client.a-PARAMETER-is-an-injection-point": Guard(
        what="an `injected_client` annotation on a method or constructor PARAMETER is joined "
        "to that parameter's declared type, as a field's is",
        why="OI-187: `io.quarkus.grpc.GrpcClient` and net.devh's both target PARAMETER, and "
        "`injected_client` joined fields alone, so a constructor-injected client hit the "
        "`stub_type is None` branch and vanished — no row, no gap, no question. Every "
        "constructor-injected gRPC client is then an outbound call the document does not "
        "show, and nothing says one was dropped",
        edits=(
            Edit(
                path="sextant/application/resolve/engines/injected_client.py",
                find="    injected.extend(_annotated_parameters(workspace, field_annotations))\n",
                replace="",
            ),
        ),
    ),
    "supertype_derived.a-supertypes-members-are-what-it-INHERITS": Guard(
        what="the methods an implementer can override are those its supertype declares plus "
        "those of every type above it, interfaces and their default methods included",
        why="protoc-gen-grpc-java puts every handler as a DEFAULT method on the nested "
        "`<Service>Grpc$AsyncService` interface; `<Service>ImplBase` implements it and declares "
        "only `<init>` and `bindService` (`fixtures/grpc-probe`, 1.62.2). Read on the base class "
        "alone, no override of real generated code matches: every grpc-java, Spring gRPC, "
        "net.devh and Quarkus service loses its handler, and an annotated one gets a false "
        "`service_identity` question",
        edits=(
            Edit(
                path="sextant/application/resolve/engines/supertype_derived.py",
                find="        pending.extend(parents.get(current, []))\n",
                replace="",
            ),
        ),
    ),
    "injected_client.a-GENERATED-class-own-nesting-does-not-fence": Guard(
        what="an `extends` edge whose both ends are nested in one outer class does not fence "
        "that outer class's injected stubs",
        why="protoc emits `<Service>FileDescriptorSupplier extends <Service>BaseDescriptorSupplier` "
        "(and the method supplier likewise) inside every full-protobuf `<Service>Grpc` — "
        "measured on both quarkus-quickstarts gRPC modules. Counted as an implementation, "
        "every stub a module compiles itself is fenced, so a client-only module's resolved "
        "gRPC client rows vanish with no question, net.devh and Quarkus alike",
        edits=(
            Edit(
                path="sextant/application/resolve/engines/injected_client.py",
                find='        if outer_of(bare_descriptor(str(row["symbol"])), hosts) == target:\n'
                "            continue\n",
                replace="",
            ),
        ),
    ),
    "grpc.an-INTERFACE-client-resolves-through-the-generated-client": Guard(
        what="under `interface_client`, an injected interface is read as the one module class "
        "implementing it and the named client type, and takes that class's identity",
        why="spec 2026-10-25 §3b, CP-53 rows 3, 6: `@GrpcClient Greeter` is the client form both "
        "Quarkus quickstarts write, and Quarkus injects the generated `GreeterClient` for it. "
        "Read as the interface itself, the row is `examples/Greeter#`, unresolved, with a "
        "`service_identity` question, so the service the module calls is not named",
        edits=(
            Edit(
                path="sextant/application/resolve/engines/injected_client.py",
                find='    clients = _interface_clients(workspace, catalog.matches.get("interface_client"))\n',
                replace="    clients = _interface_clients(workspace, None)  # guard disabled by "
                "scripts/guard_check.py\n",
            ),
        ),
    ),
    "grpc.an-UNANNOTATED-generated-bean-does-not-fence": Guard(
        what="under `served_by_annotation`, an `extends` edge fences an injected stub's outer "
        "class only when the subclass declares that annotation itself",
        why="CP-52 row 7, CP-53 row 9: Quarkus serves only `@GrpcService` classes. Its generated "
        "`GreeterBean` extends `MutinyGreeterGrpc$GreeterImplBase` in every module that "
        "compiles the `.proto`, so counted, it fences the Mutiny stub and a client-only "
        "module's Mutiny stub client vanishes with no row and no question",
        edits=(
            Edit(
                path="sextant/application/resolve/engines/injected_client.py",
                find='    fenced = _fenced_outer_classes(workspace, catalog.matches.get("served_by_annotation"))\n',
                replace="    fenced = _fenced_outer_classes(workspace, None)  # guard disabled by "
                "scripts/guard_check.py\n",
            ),
        ),
    ),
    "grpc.an-ANNOTATED-descendant-makes-its-base-a-fence": Guard(
        what="under `served_by_annotation`, an `extends` edge fences when a module class "
        "BELOW its subclass declares the annotation, not only the subclass itself",
        why="CP-52 row 7: an abstract base is not a bean, so `abstract BaseGreeter extends "
        "GreeterGrpc.GreeterImplBase` with `@GrpcService Impl extends BaseGreeter` serves the "
        "service through BaseGreeter's edge, the only one naming `GreeterGrpc`. Read on the "
        "subclass alone, the module's client of its own service is published as a resolved "
        "outbound call, and no later pass removes it",
        edits=(
            Edit(
                path="sextant/application/resolve/engines/injected_client.py",
                find="            current = parent.get(current)\n",
                replace="            current = None  # guard disabled by scripts/guard_check.py\n",
            ),
        ),
    ),
    "grpc.an-injected-WRAPPER-stub-takes-the-identity-it-delegates-to": Guard(
        what="an injected type whose outer class makes no marker call takes the identity of the "
        "one marked class its nest's code reaches",
        why="spec 2026-10-25 §3a: `MutinyGreeterGrpc` states no identity, and its stub's "
        "constructor builds `GreeterGrpc`'s stub. Read on the injected type's own outer "
        "class alone, every Mutiny stub client and every interface client is an unresolved "
        "row plus a question, though the service it calls is in the module's own facts",
        edits=(
            Edit(
                path="sextant/application/resolve/engines/injected_client.py",
                find="                service_name=service_names.get(delegated.get(outer, outer)),\n",
                replace="                service_name=service_names.get(outer),  # guard disabled\n",
            ),
        ),
    ),
    "grpc.two-INTERFACE-clients-resolve-neither": Guard(
        what="an injected interface answered by two or more client classes is read as no class",
        why="CP-53 row 3: Quarkus's map keeps one of them, in an order nothing in the facts "
        "fixes. Taking the first in sort order names a service that is right only by chance, "
        "with no question saying it was a guess",
        edits=(
            Edit(
                path="sextant/application/resolve/engines/injected_client.py",
                find="        if len(answered) == 1:\n",
                replace="        if answered:  # guard disabled by scripts/guard_check.py\n",
            ),
        ),
    ),
    "grpc.a-MUTINY-client-is-keyed-by-its-first-other-interface": Guard(
        what="a class implementing `interface_client.implements` answers only the FIRST other "
        "interface it declares",
        why="CP-53 row 3: Quarkus keys the client by its first interface other than "
        "`MutinyClient` and reads no further. Keyed by every interface, a client declaring a "
        "second one answers an injection point Quarkus does not wire to it, and the row "
        "names a service that injection point is never given",
        edits=(
            Edit(
                path="sextant/application/resolve/engines/injected_client.py",
                find="        keyed = next((entry for entry in declared if entry != implements), None)\n"
                "        if keyed is not None:\n",
                replace="        for keyed in [entry for entry in declared if entry != implements]:\n",
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
    "roots.a-NULL-handler-is-NOT-a-root": Guard(
        what="a `scheduled_work` row becomes a root only where it NAMES a handler — a "
        "schedule declared whose job was not found has none",
        why="the missing value does not stay missing. Read anyway it becomes a root handler "
        "named for no symbol any fact declared, and a walk starts at a method that does not "
        "exist, finding nothing and saying nothing about why",
        edits=(
            Edit(
                path=_ROOTS,
                find='        if row["handler"] is not None\n    }',
                replace="        if True  # guard disabled\n    }",
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
    "trace.the-walk-CROSSES-a-hop-into-the-handler": Guard(
        what="at a call site `rpc_hops` names, the walk steps into the hop's handler, with "
        "the wire path in `via`, instead of stopping at the client-call library",
        why="spec 2026-10-25 §3d, ruling 2: a call to the module's own service is a call hop "
        "that is traceable. Ignoring the hops ends every trace through a gRPC stub at "
        "`ClientCalls#blockingUnaryCall`, and with the outbound row fenced the handler the "
        "call lands on is in no trace and the call in no section of the document",
        edits=(
            Edit(
                path=_TRACE,
                find='        hops = index.hops.get((method, int(str(row["ordinal"]))))\n',
                replace="        hops = None  # guard disabled by scripts/guard_check.py\n",
            ),
        ),
    ),
    "trace.a-HOP-onto-a-handler-is-not-a-terminal": Guard(
        what="a hop step that lands on a handler drops the `ClientCalls` row's "
        "`terminal_kind` and `target_kind`",
        why="D01: both are NULL on a row that is not a terminal. Kept, the step reads "
        "`unresolved` for a library the walk no longer stops at, and a reader is told the "
        "call ends somewhere it does not",
        edits=(
            Edit(
                path=_TRACE,
                find='                landed |= {"terminal_kind": None, "target_kind": None}\n',
                replace="                pass  # guard disabled by scripts/guard_check.py\n",
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
    "render_trace.a-HOP-arrow-names-the-wire-path": Guard(
        what="a step with `via` carries `via <protocol> <path>` on its arrow",
        why="spec 2026-10-25 §3d: the arrow ends at this module's own handler while "
        "`(declared ClientCalls)` says the code called a library. Without the wire path the "
        "diagram shows a library call landing on a handler, with nothing saying how",
        edits=(
            Edit(
                path=_DOCUMENT,
                find="    if step.via is not None:\n"
                '        label = f"{label} via {redactor.redact_text(step.via)}"\n',
                replace="",
            ),
        ),
    ),
    "render_trace.a-HOP-step-reaches-its-wire-path": Guard(
        what="a step with `via` reads `via <protocol> <path>` in the step table's `Reaches` column",
        why="spec 2026-10-25 §3d: what a hop reaches is the wire path to this module's own "
        "handler. Without it the column shows the `ClientCalls` classification, or nothing, "
        "for a call the diagram draws into a handler",
        edits=(
            Edit(
                path=_DOCUMENT,
                find="    if step.via is not None:\n"
                '        return f"via {redactor.redact_text(step.via)}"\n',
                replace="",
            ),
        ),
    ),
    "render_trace.a-HOP-arrow-passes-the-redactor": Guard(
        what="a hop's wire path passes the render redactor in the sequence-diagram arrow label",
        why="2K design §1: it is the inbound path the endpoint table masks, so a credential "
        "or a repo value pattern in it would be printed in clear in the trace's diagram "
        "while the endpoint table hides it",
        edits=(
            Edit(
                path=_DOCUMENT,
                find='        label = f"{label} via {redactor.redact_text(step.via)}"\n',
                replace='        label = f"{label} via {step.via}"  # guard disabled by scripts/guard_check.py\n',
            ),
        ),
    ),
    "render_trace.a-HOP-reaches-cell-passes-the-redactor": Guard(
        what="a hop's wire path passes the render redactor in the step table's `Reaches` cell",
        why="2K design §1: it is the inbound path the endpoint table masks, so a credential "
        "or a repo value pattern in it would be printed in clear in the trace's step table "
        "while the endpoint table hides it",
        edits=(
            Edit(
                path=_DOCUMENT,
                find='        return f"via {redactor.redact_text(step.via)}"\n',
                replace='        return f"via {step.via}"  # guard disabled by scripts/guard_check.py\n',
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
    # --- the boundary vocabulary, the diff and the observability map (spec 2026-10-22) ---
    "boundary.the-HANDLER-is-evidence-never-identity": Guard(
        what="an endpoint is identified by its wire address (`protocol`, `method`, `path`); "
        "the handler symbol is evidence",
        why="every controller in petclinic-rest moved into `v1/` and was renamed between two "
        "commits (spec §1b). With the handler in the identity, the diff reports every route "
        "removed and re-added — a rewrite of the whole boundary where the wire did not move, "
        "which buries the one route that did",
        edits=(
            Edit(
                path=_VOCABULARY,
                find='        identity=("protocol", "method", "path"),\n',
                replace='        identity=("protocol", "method", "path", "handler"),  # guard disabled\n',
            ),
        ),
    ),
    "vocabulary.schedule-identity-includes-NAME": Guard(
        what="a schedule is identified by its handler, its trigger kind AND its own name "
        "(spec 2026-10-28-quartz, ruling 5)",
        why="two Quartz triggers of one kind on one job differ only by name. With the name "
        "out of the identity they are one entry whose expression and resolution agree, so a "
        "second trigger added to a job is reported as no change at all",
        edits=(
            Edit(
                path=_VOCABULARY,
                find='        identity=("handler", "trigger", "name"),\n',
                replace='        identity=("handler", "trigger"),  # guard disabled\n',
            ),
        ),
    ),
    "boundary.a-REQUIRED-request-field-added-is-breaking": Guard(
        what="a request field that is required on the new side and was not on the old is a "
        "`breaking` change (M06 step 3 read forwards in time)",
        why="an old client never sent it, so its next call is refused. Labelled `compatible` it "
        "is the one change a consumer most needs to be warned about, reported as safe",
        edits=(
            Edit(
                path=_DIFF,
                find='        return "breaking" if newly_required else "compatible"\n',
                replace='        return "compatible"  # guard disabled by scripts/guard_check.py\n',
            ),
        ),
    ),
    "boundary.both-sides-pass-through-the-REDACTOR": Guard(
        what="each side's `path`/`peer` and `boundary-property` value pass through the redactor "
        "the exporter uses before they are joined or printed",
        why="a bundle was masked at export and a workspace is verbatim, so read raw the same "
        "address is a removal and an addition; and the diff's own output would print a secret "
        "the bundle was masked to hide",
        edits=(
            Edit(
                path=_DIFF,
                find="            projected[column] = redactor.redact_text(str(projected[column]))\n",
                replace="            projected[column] = str(projected[column])  # guard disabled\n",
            ),
            Edit(
                path=_DIFF,
                find='        projected["value"] = _each(projected["value"], lambda v: redactor.redact_value(key, v))\n',
                replace='        projected["value"] = _each(projected["value"], lambda v: v)  # guard disabled\n',
            ),
        ),
    ),
    "boundary.a-STALE-side-refuses-and-allowed-masks-its-peers-whole": Guard(
        what="the diff refuses two sides older than this build's graph schema unless allowed, "
        "and then, for sides older than graph schema 5, masks each scheme-less peer with an "
        "`@` whole",
        why="before graph schema 5 a split peer kept a URL's password with no scheme in "
        "front; two such analyses agree with each other, so the diff printed it",
        edits=(
            Edit(
                path=_DIFF,
                find='    if userinfo_in_peers and isinstance(peer, str) and "@" in peer and "://" not in '
                "peer:\n",
                replace="    if False:  # guard disabled\n",
            ),
        ),
    ),
    "boundary.a-STALE-side-from-schema-5-on-keeps-its-peers": Guard(
        what="an allowed stale side masks a scheme-less peer with an `@` whole only when its "
        "graph schema is older than 5, the first whose `split_url` drops the userinfo",
        why="keyed on any schema but this build's, every bump hides a `mailto:ops@billing` "
        "peer of a schema-5 side for a hazard that side cannot hold, so the diff reports a "
        "masked marker where the peer it names is",
        edits=(
            Edit(
                path=_DIFF,
                find='    userinfo_in_peers = int(str(stamps_a["graph_schema_version"])) < '
                "_USERINFO_IN_PEERS_BEFORE\n",
                replace='    userinfo_in_peers = stamps_a["graph_schema_version"] != '
                "GRAPH_SCHEMA_VERSION  # guard disabled\n",
            ),
        ),
    ),
    "boundary.a-PRODUCER-mismatch-refuses-unless-allowed": Guard(
        what="two analyses whose Sextant version, catalog hash or redaction rule set differ "
        "are refused unless the caller allows it",
        why="a fixed dispatch bug or a new catalog changes rows with no code change; a diff "
        "that mixed the two would report the tool's change as the module's, with nothing to "
        "tell the reader which it was looking at",
        edits=(
            Edit(
                path=_DIFF,
                find="    if producer and not allow_producer_change:\n",
                replace="    if False:  # guard disabled by scripts/guard_check.py\n",
            ),
        ),
    ),
    "boundary.the-static-GAP-list-is-stated-never-a-verdict": Guard(
        what="`gaps`, the static list of what Sextant does not read, is listed as "
        "`stated_boundaries` and is never folded into a kind's verdict or reasons",
        why="the list is identical on every manifest, so folded in it would make every kind "
        "`partial` on every module and the verdict would stop saying anything about THIS "
        "analysis — the measurement the map exists to carry",
        edits=(
            Edit(
                path=_OBSERVABILITY,
                find="    shared: list[str] = []\n",
                replace="    shared: list[str] = list(stated)  # guard disabled by scripts/guard_check.py\n",
            ),
            Edit(
                path=_OBSERVABILITY,
                find='            kinds[name] = Verdict("observable", ())\n            continue\n',
                replace='            kinds[name] = Verdict("partial", stated) if stated else Verdict("observable", ())\n            continue\n',
            ),
        ),
    ),
    "boundary.every-kind-is-in-the-summary-at-zero": Guard(
        what="the diff's summary carries all seven kinds, at zero where nothing changed",
        why="a summary that omits a kind it found nothing in reads as a kind it did not look "
        "at; a consumer counting `error-handler` changes cannot tell zero from not-measured",
        edits=(
            Edit(
                path=_DIFF,
                find="    summary: dict[str, dict[str, int]] = {name: dict.fromkeys(_CHANGES, 0) for name in KINDS}\n",
                replace="    summary: dict[str, dict[str, int]] = {}  # guard disabled\n",
            ),
            Edit(
                path=_DIFF,
                find="        summary[entry.kind][entry.change] += 1\n",
                replace="        summary.setdefault(entry.kind, dict.fromkeys(_CHANGES, 0))[entry.change] += 1\n",
            ),
        ),
    ),
    # --- vocabulary 2: a dependency's conditions, compared as declared (spec 2026-10-23) ---
    "boundary.a-DEPENDENCY-carries-its-callers-conditions": Guard(
        what="the `dependency` kind's attributes include `conditions`, so a diff compares the "
        "conditions of the bean an outbound call is made from (ruling 2, vocabulary 2)",
        why="conditions belong to beans, and a bean's outbound calls exist only where it "
        "does: without the attribute a call that gained `@ConditionalOnProperty` — and so "
        "stops being made in a deployment that leaves the property off — is no change at all",
        edits=(
            Edit(
                path=_VOCABULARY,
                find='            "headers",\n            "conditions",\n',
                replace='            "headers",  # guard disabled: no conditions\n',
            ),
        ),
    ),
    "boundary.a-DEPENDENCY-condition-is-matched-on-its-CALLER": Guard(
        what="a dependency's conditions are matched on its `endpoints` row plus its `caller`",
        why="an outbound row has no handler, so two calls to one address from two callers "
        "share a NULL handler: matched without the caller, a call from an unconditional class "
        "carries another class's `@ConditionalOnProperty` and reads as switched off with it",
        edits=(
            Edit(
                path=_BOUNDARY_SOURCE,
                find='_DEPENDENCY_CONDITION_KEY = (*_CONDITION_KEY, "caller")\n',
                replace="_DEPENDENCY_CONDITION_KEY = _CONDITION_KEY  # guard disabled\n",
            ),
        ),
    ),
    "boundary.CONDITIONS-diff-as-declared-expressions": Guard(
        what="an endpoint's or dependency's `conditions` is the declared `{kind, expression}` "
        "set; each environment's `environment`/`holds` is evidence (ruling 3)",
        why="a verdict follows the configuration, so with it in the attribute one flipped "
        "property in the prod file reads twice — a `boundary-property` change and a "
        "`conditions` change on every route and call the bean produces — and a reader cannot "
        "tell a code change from a config change",
        edits=(
            Edit(
                path=_BOUNDARY_SOURCE,
                find='            entry = {"kind": row["kind"], "expression": row["expression"]}\n',
                replace='            entry = {"kind": row["kind"], "expression": row["expression"], '
                '"environment": row["environment"], "holds": row["holds"]}  # guard disabled\n',
            ),
        ),
    ),
    "boundary.a-CONDITION-expression-is-masked-as-the-exporter-masks-it": Guard(
        what="each condition's `expression` passes through `redact_json` before the diff "
        "joins or prints it, the call the exporter makes on `endpoint_conditions.expression`",
        why="an expression quotes annotation arguments verbatim — a `havingValue` URL with its "
        "password — so a workspace against its own bundle reads every conditioned route and "
        "call as changed, and the diff's JSON prints the credential the bundle masked",
        edits=(
            Edit(
                path=_DIFF,
                find='            {**entry, "expression": _redacted_json(entry["expression"], redactor)}\n',
                replace="            {**entry}  # guard disabled by scripts/guard_check.py\n",
            ),
        ),
    ),
    "query.impact-returns-THREE-partitions": Guard(
        what="`impact` answers `definite`, `possible` and `unknown_regions` apart, never as "
        "one list or one count",
        why="D01 §5: a caller reached only through a narrowed dispatch may not run the "
        "subject, and a region the walk cannot see past is not a caller at all. Folded into "
        "one list, a reader changing a method is told it certainly breaks everything that "
        "merely might, and is never told where the walk stopped",
        edits=(
            Edit(
                path=_QUESTIONS,
                find='        "definite": [item for item in ordered if definite[str(item["symbol"])]],\n'
                '        "possible": [item for item in ordered if not definite[str(item["symbol"])]],\n'
                '        "unknown_regions": [\n'
                '            {"symbol": symbol, "reason": reason} for symbol, reason in sorted(regions)\n'
                "        ],\n",
                replace='        "definite": ordered,  # guard disabled by scripts/guard_check.py\n'
                '        "possible": [],\n'
                '        "unknown_regions": [],\n',
            ),
        ),
    ),
    # --- a verb written as a static field (spec 2026-10-26 §3a) ------------
    "ktor.an-UNLISTED-member-of-a-declared-verb-field-owner-is-no-verb": Guard(
        what="in `combinator`, an `enum`-kind verb argument whose owner the "
        "`verb_values.fields` table declares, naming a member it does not list, is no verb",
        why="D02 §2: a field the table does not name reads as nothing, the same poisoned verb "
        "`fluent` gives. Read as its own member name, an unlisted `HttpMethod` field becomes "
        "a verb word Ktor never sends, and the routes inside `method(…) { … }` are dropped "
        "where they should stay unresolved rows",
        edits=(
            Edit(
                path=_COMBINATOR,
                find="        if any(declared == owner for declared, _ in scope.context.verb_fields):\n",
                replace="        if False:  # guard disabled by scripts/guard_check.py\n",
            ),
        ),
    ),
    "ktor.a-VERB-read-from-a-static-field": Guard(
        what="a verb argument that is a static field (`enum`-kind where the field is typed "
        "as its own owner, as `HttpMethod.Get` is, `field`-kind otherwise) is read through "
        "the catalog's `verb_values.fields` table, in `combinator` and in `fluent`'s "
        "`http_method: argN` capture",
        why="Ktor 3.6.0 compiles `HttpMethod.Get` to a `getstatic`, never a getter call. "
        "Ignoring `fields` reads that verb as nothing: `method(HttpMethod.Get) { get(...) }` "
        "poisons `method` and every route inside it is one unresolved row (the shipped "
        "routing gap, `ktor-samples`' `Login.kt:50`), and a client `setMethod(HttpMethod.Put)` "
        "reads `unresolved` with `method` NULL, where the evidence says PUT",
        edits=(
            Edit(
                path=_COMBINATOR,
                find="    field_verb = static_field_value(argument, scope.context.verb_fields)\n",
                replace="    field_verb = None  # guard disabled by scripts/guard_check.py\n",
            ),
            Edit(
                path=_FLUENT,
                find="        else _string_value(declared_verb) or static_field_value(declared_verb, context.verb_fields)\n",
                replace="        else _string_value(declared_verb)  # guard disabled by scripts/guard_check.py\n",
            ),
        ),
    ),
    # --- the Ktor HTTP client, inlined (spec 2026-10-26 §3c) -------------------
    "fluent.an-EXTENSION-step-joins-through-its-receiver-argument": Guard(
        what="a step declaring `receiver_arg: N` joins the chain through argument N's value "
        "id, not through its own `receiver`",
        why="a Kotlin extension function compiles to a static method whose receiver is "
        "argument 0 and whose own `receiver` is null. Joined by `receiver` alone, the walk "
        'never reaches it: Ktor\'s `HttpRequestKt.url(builder, "…")` is never folded and '
        "every inlined client call derives with `path` NULL at `unresolved`",
        edits=(
            Edit(
                path=_CHAINS,
                find="            by_receiver.setdefault(_receiver_of(site, extension_steps), []).append(site)\n",
                replace='            by_receiver.setdefault(site["receiver"], []).append(site)  # guard disabled by scripts/guard_check.py\n',
            ),
        ),
    ),
    "ktor.an-INLINED-client-call-is-an-outbound-row": Guard(
        what="`ktor-client.yml`'s `url` step names `receiver_arg: 0`: the address of an "
        "inlined client call is read off the static `HttpRequestKt.url(builder, …)`",
        why="Kotlin inlines `client.get(u)` into a builder sequence whose address is set by "
        "an extension call on the builder. Without the word that call is not part of the "
        "chain, and every Ktor client call is an outbound row with no address",
        edits=(
            Edit(
                path="sextant/catalogs/ktor-client.yml",
                find="        receiver_arg: 0, captures: { url: arg1 } }\n",
                replace="        captures: { url: arg1 } }\n",
            ),
        ),
    ),
    "ktor.the-url-step-reads-only-the-STRING-overload": Guard(
        what="`ktor-client.yml`'s `url` step is narrowed by `descriptor` to "
        "`url(HttpRequestBuilder, String)`",
        why="`HttpRequestKt` declares three `url` overloads, and the parts form "
        "`url(builder, scheme, host, port, path, block)` carries the SCHEME at argument 1. "
        "Matched by name alone, a call built from parts publishes a request to `https`",
        edits=(
            Edit(
                path="sextant/catalogs/ktor-client.yml",
                find='        descriptor: "(Lio/ktor/client/request/HttpRequestBuilder;Ljava/lang/String;)V",\n',
                replace="",
            ),
        ),
    ),
    "fluent.a-RELATIVE-address-off-a-client-base-is-unresolved": Guard(
        what="under a declared `client_base`, a relative address read in full is "
        "`unresolved`, its path kept and its peer NULL",
        why="Ktor joins a relative address onto the client's `defaultRequest` base, or onto "
        "`http://localhost`, and where the client's construction is not reached that base "
        'cannot be read. Published at `resolved`, `client.get("relative/path")` claims the '
        "path it states is the whole address the module calls",
        edits=(
            Edit(
                path=_FLUENT,
                find="        context.client_base is None\n",
                replace="        True  # guard disabled by scripts/guard_check.py\n",
            ),
        ),
    ),
    "ktor.a-SCHEME-without-a-host-is-not-joined": Guard(
        what="`join_url` declines an address with a scheme and no host (`gemini-pro:x`), "
        "where Ktor's early return tests for a HOST",
        why="Ktor sends `gemini-pro:generateContent` over a `…/models/` base as "
        "`gemini-pro://…:443/v1beta/models/generateContent` (CP-54 rows 81-82). Returned "
        "unchanged because it carries a scheme, the row publishes `gemini-pro:generateContent` "
        "as an absolute address Ktor never sends",
        edits=(
            Edit(
                path="sextant/application/resolve/shapes/client_base.py",
                find="    if scheme is not None:\n        return None\n",
                replace="    if scheme is not None:  # guard disabled by scripts/guard_check.py\n"
                "        return relative\n",
            ),
        ),
    ),
    "ktor.the-join-follows-KTORS-rule-not-concatenation": Guard(
        what="`join_url`'s `replace_last_segment` is Ktor's `DefaultRequest` merge, not "
        "the base and the relative address concatenated",
        why="Ktor replaces a base's last segment unless it ends in `/`, lets a path starting "
        "with `/` replace the whole base path, and puts the call's query before the base's "
        "(CP-54 rows 51-60). Concatenated, `https://api.example.com/v1` plus `orders` "
        "publishes `/v1orders`, an address the module never calls",
        edits=(
            Edit(
                path="sextant/application/resolve/shapes/client_base.py",
                find="    return _replace_last_segment(base, relative)\n",
                replace="    return base + relative  # guard disabled by scripts/guard_check.py\n",
            ),
        ),
    ),
    # --- A client's base, read through the declared ladder (Task 10) -------------------
    "ktor.a-RELATIVE-call-joins-its-clients-default-request-base": Guard(
        what="a relative client call is joined onto the base the client it is issued on "
        "holds, read through the catalog's `client_base` ladder",
        why='Ktor sends `client.get("quotes")` on a client built with `defaultRequest { '
        'url("https://pricing.example.com/") }` to `https://pricing.example.com/quotes` '
        "(CP-54 rows 51, 88). Without the join the row publishes `quotes` with no peer, a "
        "path that names no service, for a call whose service the code states",
        edits=(
            Edit(
                path=_FLUENT,
                find="    client = _client_of(captures, context)\n",
                replace="    client = None  # guard disabled by scripts/guard_check.py\n",
            ),
        ),
    ),
    "ktor.each-client-joins-its-OWN-base": Guard(
        what="a client derived by `config { … }` joins its OWN block's base, and inherits "
        "its parent's only where its block sets none",
        why="Ktor sends a derived client's relative call to the derived client's own "
        "`defaultRequest` base (CP-54 row 79) and to the parent's only without one (row 80). "
        "Read parent-first, every derived client publishes its parent's service — "
        "`parent.example.com` for a call Ktor sends to `child.example.com`",
        edits=(
            Edit(
                path="sextant/application/resolve/shapes/client_base.py",
                find="        base, reason = self._block_base(site, rung)\n",
                replace='        if rung.get("parent") == _FROM_RECEIVER:  # guard disabled by '
                "scripts/guard_check.py\n"
                "            return self.base_of(site, RECEIVER, seen)\n"
                "        base, reason = self._block_base(site, rung)\n",
            ),
        ),
    ),
    "ktor.the-ENGINE-LESS-factory-is-a-ladder-rung": Guard(
        what="`client-models/ktor.yml` declares the engine-less `HttpClient { … }` factory, "
        "`HttpClientJvmKt.HttpClient(Function1)`, as a rung with its block at argument 0",
        why="the engine-less factory is its own JVM function (CP-54 row 87), and koog builds "
        "its clients with it. Undeclared, a relative call on such a client keeps a bare "
        "path where Ktor sends it to the block's `defaultRequest` base (row 88)",
        edits=(
            Edit(
                path="sextant/catalogs/client-models/ktor.yml",
                find="    - { owner: io.ktor.client.HttpClientJvmKt, method: HttpClient, block_arg: 0,\n",
                replace="    - { owner: io.ktor.client.HttpClientJvmKt, method: HttpClientDisabledByGuard, "
                "block_arg: 0,\n",
            ),
        ),
    ),
    "ktor.only-a-DECLARED-factory-overload-is-read": Guard(
        what="a ladder rung matches a construction only under the descriptor it declares",
        why="`HttpClient(engine) { … }` over an engine instance shares the measured "
        "factory's owner and name. Matched on those alone, its block is read as the "
        "measured overload's, and a base no probe row measured is published at `resolved`",
        edits=(
            Edit(
                path="sextant/application/resolve/shapes/client_base.py",
                find='        and ("descriptor" not in call or site.get("descriptor") == '
                'call["descriptor"])\n',
                replace="        and True  # guard disabled by scripts/guard_check.py\n",
            ),
        ),
    ),
    "ktor.a-RELATIVE-setter-after-an-absolute-one-declines": Guard(
        what="a `defaultRequest` block whose setter is handed a relative address declines",
        why='a relative `url("b/")` after `url("https://first.example.com/a/")` MOVES '
        "the base to `…/a/b/` (CP-54 row 86), which is not modelled. Taken as the base "
        "itself, the join publishes an address built on `b/`, which Ktor never sends",
        edits=(
            Edit(
                path="sextant/application/resolve/shapes/client_base.py",
                find="                if address is None or not (_has_host(address) or carries_expression(address)):\n",
                replace="                if address is None:  # guard disabled by "
                "scripts/guard_check.py\n",
            ),
        ),
    ),
    "ktor.a-client-with-no-DECLARED-base-is-not-assumed-localhost": Guard(
        what="a construction reached with no declared setter reached gives no base, as an "
        "unreached one does",
        why="Ktor sends a client with no base to `http://localhost` (CP-54 rows 50, 57), but "
        "that a client has none cannot be proven from the bytecode: `install(DefaultRequest)`, "
        "a caller-supplied `block()` or a helper the block calls may each set one, and the set "
        "is open. Assumed, the row publishes `localhost` for a call Ktor sends elsewhere",
        edits=(
            Edit(
                path="sextant/application/resolve/shapes/client_base.py",
                find="        # bytecode, so the base is unread, as for an unreached construction.\n"
                "        return None, UNTRACED\n",
                replace="        # bytecode, so the base is unread, as for an unreached construction.\n"
                '        return "http://localhost", None  # guard disabled by scripts/guard_check.py\n',
            ),
        ),
    ),
    "ktor.a-rung-or-setter-under-ANOTHER-descriptor-declines": Guard(
        what="a call in a reached block that matches a rung or the setter on owner and name "
        "under an undeclared descriptor declines the block",
        why="`defaultRequest(replace = true) { … }` and `url { … }` set a base through an "
        "overload the ladder does not read (CP-54 rows 46, 48). Skipped, the block reads as "
        "setting only the base the declared setter read, and the row publishes that base at "
        "`resolved` for a call Ktor sends where the other overload pointed it",
        edits=(
            Edit(
                path="sextant/application/resolve/shapes/client_base.py",
                find="        if any(_same_name(site, call) for call in (*self._rungs, self._setter)):\n",
                replace="        if False:  # guard disabled by scripts/guard_check.py\n",
            ),
        ),
    ),
    "ktor.any-other-call-on-the-SETTERS-owner-declines": Guard(
        what="any call on the setter's owner type other than the declared setter declines "
        "the block it is in",
        why="`defaultRequest { host = … }` and `url.takeFrom(…)` move the base through members "
        "of `DefaultRequestBuilder` the reader does not model. Skipped, the row publishes the "
        "base `url(…)` set at `resolved`, for a call Ktor sends to the host set after it",
        edits=(
            Edit(
                path="sextant/application/resolve/shapes/client_base.py",
                find='        if site.get("owner") == self._setter["owner"]:\n',
                replace="        if False:  # guard disabled by scripts/guard_check.py\n",
            ),
        ),
    ),
    "ktor.a-LISTED-call-that-may-set-the-base-declines": Guard(
        what="a call the catalog's `may_set_base` lists declines the block it is in",
        why="`install(DefaultRequest) { url(…) }` sets the base as `defaultRequest { }` does "
        "(CP-54 rows 92-93), through a generic installer. Unlisted, the row publishes the "
        "`defaultRequest` base beside it at `resolved`, for a call Ktor sends to the installed "
        "base",
        edits=(
            Edit(
                path="sextant/application/resolve/shapes/client_base.py",
                find="        return any(_listed(site, entry) for entry in self._may_set)\n",
                replace="        return False  # guard disabled by scripts/guard_check.py\n",
            ),
        ),
    ),
    "fluent.a-request-executed-TWICE-holds-no-client": Guard(
        what="a built request is held against a client only where exactly one call executes it",
        why="a builder handed to two `HttpStatement`s on two clients has two bases; holding "
        "the first publishes that client's service for a row that may be the other's",
        edits=(
            Edit(
                path=_CHAINS,
                find="    if len(executing) != 1:\n",
                replace="    if not executing:  # guard disabled by scripts/guard_check.py\n",
            ),
        ),
    ),
    "ktor.a-block-handing-its-receiver-to-MODULE-code-declines": Guard(
        what="a block that hands its receiver to a method of this module, whose body is "
        "scanned and not followed, declines",
        why="`HttpClient(CIO) { configure(this) }` may set the base inside `configure`. Read "
        "as silence, the row publishes the block's own declared base at `resolved`, for a "
        "call Ktor sends wherever `configure` pointed it",
        edits=(
            Edit(
                path="sextant/application/resolve/shapes/client_base.py",
                find="            if self._may_move_base(inner) or self._hands_off(inner, receiver):\n",
                replace="            if self._may_move_base(inner):  # guard disabled by "
                "scripts/guard_check.py\n",
            ),
        ),
    ),
    "ktor.a-block-handing-its-receiver-to-SUPPLIED-code-declines": Guard(
        what="a block that hands its receiver to an instance call made on any value other "
        "than the receiver itself (a captured value, a parameter, a field read, a local) "
        "declines",
        why="`fun mk(block) = HttpClient(CIO) { defaultRequest { url(a) }; block() }` runs "
        "the caller's `block` on the configuration, and the caller's block may set its own "
        "base. Skipped, the row publishes `a` at `resolved` for a call Ktor sends wherever "
        "the caller's block pointed it (measured on kotlinc 2.2's output)",
        edits=(
            Edit(
                path="sextant/application/resolve/shapes/client_base.py",
                find="            if _hands_to_supplied_code(inner, receiver):\n",
                replace="            if False:  # guard disabled by scripts/guard_check.py\n",
            ),
        ),
    ),
    "ktor.a-base-from-ANOTHER-path-is-never-paired": Guard(
        what="a setter whose value the walk resolves to several bases gives no base",
        why="the producer reader records no path, so where `madeClient(base)` is called "
        "with two bases nothing says which one a given client was built with. Taking one "
        'pairs the client with a base from another call (ruling M-1): `a.get("orders")` '
        "published at `b.example.com`",
        edits=(
            Edit(
                path="sextant/application/resolve/shapes/client_base.py",
                find="        if len(distinct) > 1:\n            return None, NON_ENUMERABLE\n"
                "        return distinct[0], None\n\n    def _rung_of",
                replace="        return distinct[0], None  # guard disabled by "
                "scripts/guard_check.py\n\n    def _rung_of",
            ),
        ),
    ),
    # --- WebSocket and SSE client calls (spec 2026-10-26 §3d, §3g items 2 and 4) -------
    "ktor.a-WEBSOCKET-client-call-is-an-outbound-row": Guard(
        what="`ktor-websocket-client.yml` matches the client `BuildersKt` WebSocket functions "
        "on their own owner",
        why='`client.webSocket("ws://…") { }` is one static call, '
        '`websocket.BuildersKt.webSocket$default(client, "ws://…", …)` (CP-54 row 36). '
        "Unmatched, a module that opens a WebSocket has that connection in no export",
        edits=(
            Edit(
                path="sextant/catalogs/ktor-websocket-client.yml",
                find="  owner: io.ktor.client.plugins.websocket.BuildersKt\n",
                replace="  owner: io.ktor.client.plugins.websocket.BuildersKtDisabledByGuard\n",
            ),
        ),
    ),
    "ktor.an-SSE-client-call-is-an-outbound-row": Guard(
        what="`ktor-sse-client.yml` matches the client `BuildersKt` SSE functions on their own "
        "owner",
        why='`client.sse("https://…") { }` is one static call, '
        '`sse.BuildersKt."sse-Mswn-_c$default"(client, "https://…", …)` (CP-54 row 42). '
        "Unmatched, a module subscribing to an event stream has that call in no export",
        edits=(
            Edit(
                path="sextant/catalogs/ktor-sse-client.yml",
                find="  owner: io.ktor.client.plugins.sse.BuildersKt\n",
                replace="  owner: io.ktor.client.plugins.sse.BuildersKtDisabledByGuard\n",
            ),
        ),
    ),
    "ktor.a-relative-WS-call-joins-the-base": Guard(
        what="a `single_call` row whose catalog declares `client_base` joins a relative "
        "address onto the base of the client at `client_arg`",
        why='`client.ws("/opentelemetry/websocket")` on a client whose `defaultRequest` base '
        "is `https://api.example.com/` is sent to `ws://api.example.com:443/…` (CP-54 rows 61, "
        "95). Without the client the row keeps `/opentelemetry/websocket` unresolved, a path "
        "naming no service, for a call whose service the code states",
        edits=(
            Edit(
                path=_SINGLE_CALL,
                find="    address, resolution = against_client_base(\n"
                "        workspace, values, client, declared, path, method.get(_REQUEST_URL), "
                "path_only\n",
                replace="    address, resolution = against_client_base(  # guard disabled by "
                "scripts/guard_check.py\n"
                "        workspace, values, None, declared, path, method.get(_REQUEST_URL), "
                "path_only\n",
            ),
        ),
    ),
    "ktor.a-WEBSOCKET-call-sends-with-its-OWN-scheme-and-port": Guard(
        what="a call's `request_url` sets the joined address's scheme, and its port where it "
        "sets one, written only where it differs from the scheme's default",
        why='Ktor sends `ws("/chat")` over `https://api.example.com/v1/` to '
        '`ws://api.example.com:443/chat` and `wss("/chat")` to `wss://api.example.com/chat` '
        "(CP-54 rows 94-108). Joined as an HTTP call, both rows publish "
        "`https://api.example.com/chat`, a URL no WebSocket call reaches",
        edits=(
            Edit(
                path="sextant/application/resolve/shapes/client_base.py",
                find="    if request is None:\n        if path_only:\n"
                "            return _path_onto(base, relative)\n"
                "        return _replace_last_segment(base, relative)\n"
                "    return _with_request_scheme(base, relative, request, default_ports or {}, "
                "path_only)\n",
                replace="    return _replace_last_segment(base, relative)  # guard disabled by "
                "scripts/guard_check.py\n",
            ),
        ),
    ),
    "ktor.a-HOST-in-the-parts-form-is-not-assembled": Guard(
        what="an address whose other parts (`address_parts`) are given is kept, `unresolved`, "
        "and never joined",
        why='`client.webSocket(host = "chat.example.com", path = "/parts")` is sent to '
        "`ws://chat.example.com/parts` (CP-54 row 109): the host replaces the base's. Joined, "
        "the row publishes `ws://api.example.com:443/parts`, the base's service for a call "
        "Ktor sends elsewhere",
        edits=(
            Edit(
                path=_SINGLE_CALL,
                find="        if any(_given(_arg_at(arguments, position)) for position in "
                "method[_ADDRESS_PARTS]):\n"
                "            return None, path, str(Resolution.UNRESOLVED)\n",
                replace="        pass  # guard disabled by scripts/guard_check.py\n",
            ),
        ),
    ),
    "ktor.a-PARTS-path-is-a-path-never-an-address": Guard(
        what="a parts-form row reads its `path` as the text the code states and joins it as "
        "segments, never as an address",
        why="Ktor hands the parts form's `path` to `setEncodedPath` and never parses it: "
        '`sse(path = "https://e.example.com/s")` over `https://api.example.com/v1/` is sent '
        "to `https://api.example.com/v1/https://e.example.com/s` (CP-54 row 130). Read as an "
        "address, the row publishes `e.example.com` `/s`, a service the call never reaches",
        edits=(
            Edit(
                path=_SINGLE_CALL,
                find="    path_only = _ADDRESS_PARTS in method\n",
                replace="    path_only = False  # guard disabled by scripts/guard_check.py\n",
            ),
        ),
    ),
    "ktor.a-PROTOCOL-RELATIVE-address-under-a-call-scheme-declines": Guard(
        what="under a call's `request_url`, an address with two or more leading slashes "
        "declines the join",
        why="it takes the CALL's scheme (CP-54 row 113, measured for `ws` alone), where the "
        "HTTP join gives it the base's. Joined by the HTTP rule and rewritten, "
        '`ws("//other.example.com/x")` publishes `ws://other.example.com:443/x`, a port '
        "Ktor never writes for it",
        edits=(
            Edit(
                path="sextant/application/resolve/shapes/client_base.py",
                find='        if len(relative) - len(relative.lstrip("/")) >= 2:\n'
                "            return None\n",
                replace="        pass  # guard disabled by scripts/guard_check.py\n",
            ),
        ),
    ),
    "ktor.a-base-carrying-USER-INFO-under-a-call-scheme-declines": Guard(
        what="under a call's `request_url`, a base whose authority carries user info declines",
        why="the scheme rewrite rebuilds the authority from the base's host and port, and "
        "Ktor's handling of user info there is not measured. Rebuilt as written, the row "
        "publishes `ws://user@api.example.com:443/chat` as a fact",
        edits=(
            Edit(
                path="sextant/application/resolve/shapes/client_base.py",
                find='    if joined is None or "@" in origin.netloc:\n',
                replace="    if joined is None:  # guard disabled by scripts/guard_check.py\n",
            ),
        ),
    ),
    "single_call.a-malformed-request-url-or-address-parts-is-refused": Guard(
        what="`_validate_client_rows` refuses a `request_url` with no base or no default port, "
        "a malformed `request_url`, and `address_parts` that names no positions",
        why="each loads silently otherwise: a `request_url` nothing can render, or "
        "`address_parts: 2`, which reads no part and so joins a host-bearing call onto the "
        "base — the base's service published for a call Ktor sends elsewhere",
        edits=(
            Edit(
                path=_SINGLE_CALL,
                find="    for row in rows:\n"
                "        where = f\"loading catalog {catalog.source}: `{row['name']}`\"\n",
                replace="    for row in []:  # guard disabled by scripts/guard_check.py\n"
                "        where = f\"loading catalog {catalog.source}: `{row['name']}`\"\n",
            ),
        ),
    ),
    "ktor.a-client-model-key-cannot-be-COPIED-into-a-catalog": Guard(
        what="a catalog naming `client_model` may not declare a `client_base` key the model "
        "declares",
        why="the merge would let the catalog's copy win silently, so a ladder, join or "
        "`may_set_base` edited in the model would stop reaching the catalog that copied it — "
        "the drift one declaration exists to end",
        edits=(
            Edit(
                path="sextant/ingress/catalogs/yaml_source.py",
                find="    twice = sorted(set(own) & set(shared))\n    if twice:\n",
                replace="    twice = sorted(set(own) & set(shared))\n"
                "    if False:  # guard disabled by scripts/guard_check.py\n",
            ),
        ),
    ),
    "ktor.the-client-BASE-is-declared-once-for-every-catalog": Guard(
        what="a catalog naming `client_model` takes the model's `client_base` ladder, merged "
        "into its own `client_arg`",
        why="the HTTP, WebSocket and SSE catalogs read one client's base through one ladder "
        "(`client-models/ktor.yml`). Unmerged, each catalog's `client_base` is a lone "
        "`client_arg`, and a copy of the ladder per catalog is the drift the model exists to end",
        edits=(
            Edit(
                path="sextant/ingress/catalogs/yaml_source.py",
                find='    return {**matches, "client_base": {**shared, **own}}\n',
                replace="    return matches  # guard disabled by scripts/guard_check.py\n",
            ),
        ),
    ),
    # --- WebSocket and SSE routes in Ktor's routing tree (spec 2026-10-26 §3b) ------
    "ktor.a-WEBSOCKET-route-is-a-verbless-inbound-row": Guard(
        what="a `combinator` row carries its verb rule's own `protocol`",
        why="Ktor's `webSocket` routes nest through the same prefixes as its HTTP verbs. "
        'Without the rule\'s protocol, `route("/api") { webSocket("/chat") }` publishes an '
        "`http` row at `/api/chat`, and a WebSocket client calling it is matched against an "
        "HTTP endpoint",
        edits=(
            Edit(
                path=_COMBINATOR,
                find='        "protocol": route.protocol or catalog.protocol,\n',
                replace='        "protocol": catalog.protocol,  # guard disabled by scripts/guard_check.py\n',
            ),
        ),
    ),
    "ktor.an-SSE-route-is-a-get-sse-row": Guard(
        what="`ktor-routing.yml`'s `sse(path, …)` rules name `protocol: sse` beside `verb: GET`",
        why='`sse("/events") { }` is `route(path, HttpMethod.Get)` around an event stream. '
        "Without the protocol it is published as an ordinary `http` GET route, and an SSE "
        "client calling it is matched against an HTTP endpoint it does not speak to",
        edits=(
            Edit(
                path="sextant/catalogs/ktor-routing.yml",
                find="method: sse, protocol: sse, verb: GET,",
                replace="method: sse, verb: GET,",
                occurrences=2,
            ),
        ),
    ),
    "ktor.a-websocket-under-a-verb-scope-is-NOT-expanded": Guard(
        what="a route from a `verb: none` rule is never fanned out through `all_methods`",
        why='`route("/api") { webSocket("/ws") { } }` reads no verb because a WebSocket route '
        "has none. Fanned out like a verb-less `handle { }`, it is seven HTTP-verbed rows "
        "(`GET` … `OPTIONS`) at `/api/ws` where one verbless WebSocket row is the truth",
        edits=(
            Edit(
                path=_COMBINATOR,
                find="    if route.verb is not None or route.verbless or route.poisons or not context.all_methods:\n",
                replace="    if route.verb is not None or route.poisons or not context.all_methods:  # guard disabled by scripts/guard_check.py\n",
            ),
        ),
    ),
    "ktor.the-row-protocol-is-part-of-the-dedup-key": Guard(
        what="`combinator`'s `_emitted` deduplicates on the ROW's protocol, not the catalog's",
        why='`route("/api") { sse("/events") { }; get("/events") { } }` is an `sse` and an `http` '
        "`GET /api/events` with one handler. Keyed on the catalog's `http`, the two are one "
        "identity and whichever came second is silently discarded",
        edits=(
            Edit(
                path=_COMBINATOR,
                find='                row["protocol"],\n                catalog.direction,\n',
                replace="                catalog.protocol,  # guard disabled by scripts/guard_check.py\n"
                "                catalog.direction,\n",
            ),
        ),
    ),
    "ktor.a-GET-bound-websocket-under-a-disagreeing-scope-is-dropped": Guard(
        what="a verbless route meets a scope's verb by its `registered_verb` and never takes "
        "the scope's verb: `_verbs_disagree` compares the registered verb, and `_merged` "
        "keeps `method` NULL",
        why="Ktor wraps a WebSocket route with a path in `route(path, HttpMethod.Get)`, so "
        '`method(HttpMethod.Post) { webSocket("/ws") { } }` is a node Ktor never dispatches. '
        "Comparing nothing publishes a row for it; taking the scope's verb publishes "
        "`GET`/`POST` WebSocket rows, and the path-less form under POST as `POST /`",
        edits=(
            Edit(
                path=_COMBINATOR,
                find="    own = route.registered_verb if route.verbless else route.verb\n",
                replace="    own = route.verb  # guard disabled by scripts/guard_check.py\n",
            ),
            Edit(
                path=_COMBINATOR,
                find="    if verbless:\n        verb = None\n",
                replace="    if False:  # guard disabled by scripts/guard_check.py\n        verb = None\n",
            ),
        ),
    ),
    "chains.a-LIFTED-argument-carries-its-own-method": Guard(
        what="every argument lifted out of a lambda body is stamped with that body's own "
        "method, whatever its kind, so its value id and parameter index are read there",
        why="a lambda body's value id 20 is the lambda's call 20, and the enclosing method has "
        "a call 20 of its own; read there, a destination that came from `other.compute(k)` "
        "is published as the enclosing method's `properties.getUrl()` key at `resolved`, and "
        "a lambda's parameter is typed as the enclosing method's",
        edits=(
            Edit(
                path=_CHAINS,
                find='    stamped = {**argument, "caller": site["caller"]}\n',
                replace='    stamped = {**argument, **({"caller": site["caller"]} if argument.get("kind") == "parameter" else {})}  # guard disabled by scripts/guard_check.py\n',
            ),
        ),
    ),
    "arguments.a-lifted-parameter-is-typed-by-its-own-signature": Guard(
        what="a payload read from a parameter is typed by the signature of the method the "
        "argument was lifted from, not the chain's enclosing method",
        why="a lambda's parameter 0 is a captured variable of ITS signature; typed against "
        "the enclosing method's parameter 0 the row publishes a contract type this send "
        "never carries, at `resolved`",
        edits=(
            Edit(
                path=_ARGUMENTS,
                find="    return reads.parameters_by_caller.get(str(caller), ())\n",
                replace="    return reads.caller_parameters  # guard disabled by scripts/guard_check.py\n",
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
        "orders-fluentaddress",
        "orders-discovery",
        # The two-module REACTOR the stitcher's guards are measured on. It is the only
        # fixture here that is a reactor rather than a module, and it has to be: the
        # participant set is read from the `modules.json` an analysis at a reactor ROOT
        # writes, so a single module cannot state the shape at all.
        "reactor-twoservice",
        # The gateway reactor CP-40's gate is measured on.
        "reactor-gateway",
        # The `type_header` read's fixture: two handlers whose exceptions live in jars.
        "orders-advice",
        # Quarkus's SmallRye channels and gRPC client (spec 2026-10-24): the orphan
        # attachment and the in-memory pair are read off one module's whole channel set,
        # and the gRPC fence off protoc's nesting in its compiled classes, so their pins
        # are e2e and need the module.
        "orders-quarkus",
        # protoc's own generated gRPC classes, which the inherited-member read is pinned on:
        # only real generated code puts the handlers on `<Service>Grpc$AsyncService`.
        "grpc-probe",
        # Quartz's triggers (spec 2026-10-28): the shapes its guards are pinned on cross
        # methods — a cron read off a getter in the caller, a builder through a helper — and
        # only the value walk over real facts crosses them.
        "orders-quartz",
    ):
        # `orders-pathprefixes` is here for one guard: the prefix/pattern PAIRING, whose
        # failure shape is two real packages served under each other's prefix. Nothing
        # synthetic can state it — the two values are paired by the path they left through,
        # which exists only in real facts — so the test that pins it is an e2e one, and an
        # e2e test needs its fixture. 90 KB of sources and classes, and the stamp's mtime
        # survives `copy2`, so no `mvn` runs here either.
        # `grpc-probe`'s `target/protobuf-maven-plugin` is 16MB of downloaded protoc binaries,
        # a build cache the stamped `target/classes` no longer needs.
        shutil.copytree(
            REPO / "fixtures" / named,
            destination / "fixtures" / named,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "protobuf-maven-plugin"),
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
