"""Where a registered endpoint row exists, when the calls that register it run only under tests
the analysis does not decide (OI-368; the user's ruling of 2026-10-23, "deployment decides what
it can set"; plan 2026-11-08-python-fastapi-inbound Task 10b, design approved 2026-11-09).

A route, a router include or a mount is made by a call. That call runs where every test it is
under went its way: the tests of its own body (`call_site.guards`, D00 §5), and, where every call
that runs its function is itself under one, those of each such call, followed up the call graph
(`call_edges`) to a body nothing in the module calls. A function some call runs under no test
runs wherever the module runs. Sextant decides none of these tests: which way a settings value,
a file's presence or the interpreter's version goes is the deployment's. So a row whose calls
are all under tests exists "not evaluated" — never decided from the repository, never dropped.

The answer is a set of ALTERNATIVES, each a conjunction of guards: the row exists where every
guard of one alternative holds. Two callers under two tests are two alternatives; a call under
two nested tests is one alternative of two guards. An alternative with no guard means the row
exists unconditionally, and then nothing is written. A write to a name under a test
(`field_write.guards`, ruling R1 of 2026-11-25) that a row's lists were read through
(`Path.written_under`) counts as one of the row's calls: a route list added under a test, a
root setting written under one. So does a `return` under a test not decided that a value of
the row was read through (`method_return.guards`): the path names the tests still open. A row's calls are its registration (the
route's root and terminal calls) and every include or mount its router is served through, all
of which must run, so their alternatives are combined (each choice of one alternative per call,
joined). Where the row was derived through one call of a helper (its path chose that call,
`Path.calls_into`), the helper runs by that call alone: a helper called once under a test and
once not gives each row its own call's tests (task 10b review, Major 1), the calls that gave
its prefix value included (re-review R1-1). Where one registration gives several rows and a
row's paths do not tie it to one call, a call under no test does not make it "served"
(`Existence.untied`, re-review ruling part 2). A guard keeps its place
in the alternative, outermost first (`endpoint_existence.position`).

Each guard of each alternative is one `endpoint_existence` row per environment the module
resolves (D01): kind `test`, its expression the test as the code writes it with the arm it is
in, `holds = unresolved`. Names no framework: the calls are the engine's, the tests the facts'.

A guard every one of whose reads is a read of a settings field (`call_site.guards[].fields`,
the scanner's typed reads, R27; the field's key by `settings_fields`, plan 3 Task 5) is kind
`property` instead, as a bean's property condition is: its expression names the keys, the verdict
stays "not evaluated" (the deployment sets a key, ruled 2026-10-23), and the repository's value
for each key is evidence: what the module's environment configuration sets, else the field's
class-body default. A guard with any read that is not such a field stays `test`: the part no
key explains cannot be called a property condition. A read of an attribute of an object a
value model states is read by key (`key_reads`: `settings.DEBUG` on Django's settings object)
and of a name of a settings module (an environment, `settings_modules`) is a read of a key
the same way (ruling R3 of 2026-11-25): never decided, each environment's value as evidence.
A condition a reader states itself on the value of a key (`having_value`: the routes of a
root exist where the root setting names it, `shapes/mounts.py`) is a guard like the others.

**The seam for deciding a test on a setting** (the approved note's last step, NOT built): in
`existence_rows`, a `property` guard on one key whose value in an environment is one literal
could be decided there (`holds` true or false, `resolution` `resolved`) where nothing a
deployment sets is in the chain. Whether a settings module takes a name from code outside
the repository (a star import of an absent module) is the mark on the write since ruling R10
(`field_write.replaceable`, `ValueIndex.replaceable`). OI-570.

**A test on a value the code fixes is decided** (ruling R2 of 2026-11-25). Where a test is
one name (`if x:`), its negation, or its comparison with `None` by `is` (`guards[].value`,
`when`), and the value walk gives that name exactly one written literal on the row's path
(`values.Tests`, per caller, rule 1), the test is true or false there, and no deployment can
change it: decided true, the guard is no condition of the row on that path; decided false,
the call does not run on that path, and a row no path registers is not written (as under
`if False:`). A name an environment read, a configuration key or a settings field gives, a
name with several values on the path, and every other form of test (`==`, `in`,
`isinstance`, `and`, `or`) are not decided: "not evaluated", as before. The JVM writes no
guards, so nothing is decided there (OI-553).

**Stated limits.** A function in a cycle of calls is taken to run unconditionally while the
cycle is being followed (the old answer, never a dropped row). A read the scanner cannot type is not linked to a
settings field, so its guard stays `test`. A class body's statements are read with no test the module body puts them
under.

Cost (GUIDELINES §8.7): per inbound catalog run, one read of the guarded call sites and one of the
guarded field writes (fact queries, cached per load) and, only where some is guarded, one read of the call edges; each
method's alternatives are computed once.
"""

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from sextant.application.ports.catalogs import Catalog
from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.bean_conditions import property_evidence
from sextant.application.resolve.dispatch import dispatch_of
from sextant.application.resolve.settings_fields import (
    CONFIG_MODEL_FORM,
    SettingsKey,
    settings_keys,
)
from sextant.application.resolve.values import KEY_READ, Path
from sextant.domain.symbols import bare_descriptor, member_name, owner_of, type_descriptor

# The condition kind of a test the analysis does not evaluate (D01 `endpoint_existence.kind`).
TEST = "test"
# The condition kind of a test that reads only settings fields (the bean model's own word).
PROPERTY = "property"
# The environment of a module that resolves none of its own (`resolved_config` holds none).
DEFAULT_ENVIRONMENT = "default"
# The one spelling of a condition left open, which `bean_presence` in `schema.sql` spells too
# (SQL cannot import it; `test_the_evidence_prefix_is_the_one_the_bean_presence_view_states`
# holds the two equal).
NOT_EVALUATED = "a condition this analysis does not evaluate: "

# One guard: the method whose body holds the test, the test as written, the arm, its reads, and
# the field symbol of each read the scanner could type (read, symbol).
# Last, the value a condition on a key states the key has (`having_value`, the property
# condition's word), None for a test of the code.
Guard = tuple[str, str, bool, tuple[str, ...], tuple[tuple[str, str], ...], str | None]
# The guards of one alternative, outermost first (a caller's before its callee's, an include's
# before the routes under it), each once.
Conjunction = tuple[Guard, ...]
Alternatives = frozenset[Conjunction]
UNCONDITIONAL: Alternatives = frozenset({()})
# What a registration ran through: a call `(method, ordinal)`, or a write under a test
# `(writing method, its tests)` as `Path.written_under` names one.
Site = tuple[str, int | str]
# The call a row's own path chose for a method (`Path.calls_into`): the calling context it was
# derived in.
Chosen = Mapping[str, tuple[str, int]]


class Decider(Protocol):
    """What decides the tests of one record on a path (`values.Tests`): the paths its call
    or write runs on, each with the positions of the guards not decided there."""

    def ran(
        self, method: str, guards: str, within: Path | None
    ) -> tuple[tuple[Path | None, tuple[int, ...]], ...]: ...


@dataclass
class Conditions:
    """The guarded calls and who calls whom, read once per resolve, and each method's
    alternatives as they are asked for. `tests` holds the record of each site one of whose
    tests states the value it reads (`guards[].value`), as the facts write it, for `decider`
    to decide (ruling R2 of 2026-11-25); with no decider every test stays open."""

    guards: dict[Site, tuple[Guard, ...]]
    callers: dict[str, tuple[tuple[str, int], ...]]
    tests: dict[Site, str] = field(default_factory=dict)
    decider: Decider | None = None
    _methods: dict[tuple[str, bool], Alternatives] = field(default_factory=dict)
    _entered: set[str] = field(default_factory=set)

    def of_sites(
        self,
        sites: Iterable[Site],
        chosen: Chosen | None = None,
        untied: bool = False,
        on: Path | None = None,
    ) -> Alternatives:
        """Where every call of `sites` runs, outermost first: one alternative per choice of
        one alternative of each call, joined. A method `chosen` names a call of is run by
        that call alone (task 10b review, Major 1): a row derived through one call of a helper
        takes that call's tests, never those of the helper's other callers.

        `untied`: the row cannot be tied to one call of a method `chosen` leaves out, though
        that method's calls register different rows (re-review ruling, part 2). Then a method
        some calls run under a test and some under none is taken to run under its tests only:
        the row is "not evaluated", never served on the strength of a call that may have
        registered another row.

        `on` is the path the row was derived on, where a test is decided (the module
        docstring): no alternative at all where a call of `sites` runs on no path."""
        found = UNCONDITIONAL
        for site in dict.fromkeys(sites):
            found = _simplest(
                frozenset(
                    _joined(left, right)
                    for left in found
                    for right in self._of_site(site, chosen or {}, frozenset(), untied, on)
                )
            )
        return found

    def _of_site(
        self,
        site: Site,
        chosen: Chosen,
        followed: frozenset[str],
        untied: bool,
        on: Path | None = None,
    ) -> Alternatives:
        method = site[0]
        own = self.guards.get(site)
        if own is None:
            # A `return` under tests a path read a value through names its tests itself
            # (`Path.written_under`): the ones still open on that path.
            own = _guards_of(method, site[1]) if isinstance(site[1], str) else ()
        ran: tuple[tuple[Path | None, tuple[int, ...]], ...] = ((on, tuple(range(len(own)))),)
        if self.decider is not None and site in self.tests:
            ran = self.decider.ran(method, self.tests[site], on)
        found: set[Conjunction] = set()
        for path, kept in ran:
            # A test decided per caller chose that caller: the method runs by that call.
            calls = chosen if path is on or path is None else {**chosen, **path.calls_into()}
            if method in calls and method not in followed:
                outer = self._of_site(calls[method], calls, followed | {method}, untied, path)
            else:
                outer = self._of_method(method, untied)
            still = tuple(own[position] for position in kept)
            found |= {_joined(conjunction, still) for conjunction in outer}
        return frozenset(found)

    def _of_method(self, method: str, untied: bool = False) -> Alternatives:
        """Where `method` runs: wherever any call of it runs; everywhere where nothing in the
        module calls it, and while it is being followed in a cycle. `untied` (`of_sites`): a
        call under no test does not make it run everywhere where another call is under one."""
        key = (method, untied)
        if key in self._methods:
            return self._methods[key]
        callers = self.callers.get(method, ())
        if not callers or method in self._entered:
            return UNCONDITIONAL
        self._entered.add(method)
        try:
            found: set[Conjunction] = set()
            for site in callers:
                found |= self._of_site(site, {}, frozenset(), untied)
                if () in found and not untied:
                    break
        finally:
            self._entered.discard(method)
        if untied and len(found) > 1:
            found.discard(())
        answer = _simplest(frozenset(found))
        self._methods[key] = answer
        return answer


def _joined(outer: Conjunction, inner: Iterable[Guard]) -> Conjunction:
    """`outer`'s guards, then each of `inner`'s it does not hold, in order."""
    return (*outer, *(guard for guard in inner if guard not in outer))


def _simplest(alternatives: Alternatives) -> Alternatives:
    """`alternatives` without one that another implies (a superset of another's guards): the
    row exists wherever the smaller does. Two of the same guards in another order are one."""
    if () in alternatives:
        return UNCONDITIONAL
    by_guards: dict[frozenset[Guard], Conjunction] = {}
    for one in sorted(alternatives):
        by_guards.setdefault(frozenset(one), one)
    return frozenset(
        one for guards, one in by_guards.items() if not any(other < guards for other in by_guards)
    )


def _guards_of(method: str, written: str) -> tuple[Guard, ...]:
    """The tests of one record of `method`'s body, as the facts write them."""
    return tuple(
        (
            method,
            str(g["test"]),
            bool(g["holds"]),
            tuple(g.get("reads") or ()),
            tuple(sorted((g.get("fields") or {}).items())),
            g.get("having_value"),
        )
        for g in json.loads(written)
    )


def conditions_of(workspace: Workspace, decider: Decider | None = None) -> Conditions:
    """The guarded calls and the guarded field writes, and the callers of each method where
    any is guarded. Read by the engine once per run: `call_edges` is derived, so it is never
    kept across passes."""
    guards: dict[Site, tuple[Guard, ...]] = {}
    tests: dict[Site, str] = {}
    guarded: list[tuple[Site, str]] = [
        ((str(row["caller"]), int(str(row["ordinal"]))), str(row["guards"]))
        for row in workspace.query("call_site_guards")
    ]
    # A write is named by its method and its tests, as a path that read it names it.
    guarded += [
        ((str(row["written_by"]), str(row["guards"])), str(row["guards"]))
        for row in workspace.query("field_write_guards")
    ]
    # A return is named as a write is: by its method and its tests.
    guarded += [
        ((str(row["method"]), str(row["guards"])), str(row["guards"]))
        for row in workspace.query("method_return_guards")
    ]
    for site, written in guarded:
        guards[site] = _guards_of(site[0], written)
        if any(g.get("value") is not None for g in json.loads(written)):
            tests[site] = written
    callers: dict[str, list[tuple[str, int]]] = {}
    if guards:
        for row in workspace.query("calls_running"):
            callers.setdefault(str(row["callee"]), []).append(
                (str(row["caller"]), int(str(row["ordinal"])))
            )
    return Conditions(
        guards, {callee: tuple(sites) for callee, sites in callers.items()}, tests, decider
    )


def environments_of(workspace: Workspace) -> tuple[str, ...]:
    """The environments the module resolves, or `default` where it resolves none."""
    found = sorted({str(row["environment"]) for row in workspace.query("resolved_config")})
    return tuple(found) or (DEFAULT_ENVIRONMENT,)


@dataclass(frozen=True)
class SettingsReads:
    """What a guard that reads settings fields is explained by: each settings field's key by
    bare field symbol (`settings_fields.settings_keys`), and what each environment's
    configuration sets for a key (None: a placeholder the module does not fill)."""

    keys: Mapping[str, SettingsKey]
    config: Mapping[str, Mapping[str, str | None]]
    # The objects whose attribute read is the key of that name (`key_reads` in
    # `value-models/`), and the settings modules, each an environment (`settings_modules`):
    # a read of a name of either is a read of that key (ruling R3 of 2026-11-25).
    objects: frozenset[str] = frozenset()

    def key_of(self, field: str) -> SettingsKey | None:
        """The key the read of `field` (a bare field symbol) is a read of, None for a field
        that is no setting."""
        found = self.keys.get(field)
        if found is None and owner_of(field) in self.objects:
            return SettingsKey(member_name(field), None, None)
        return found


def settings_reads_of(workspace: Workspace, catalog: Catalog) -> SettingsReads:
    """The settings fields of the module the catalog's config model declares, empty where it
    declares none. Read once per resolve, and only for a run whose rows are guarded."""
    model = next(
        (row for row in catalog.returns_arguments if row.get("form") == CONFIG_MODEL_FORM), None
    )
    stated = {str(row["owner"]) for row in catalog.returns_arguments if row.get("form") == KEY_READ}
    if model is None or not (model.get("settings_form") or stated):
        return SettingsReads({}, {})
    keys = settings_keys(workspace, model, workspace.once(dispatch_of))
    config: dict[str, dict[str, str | None]] = {}
    for row in workspace.query("resolved_config"):
        value = row["value"]
        if value is None and row.get("source") is None:
            continue  # never declared in the environment: "nothing", not a placeholder
        config.setdefault(str(row["environment"]), {})[str(row["key"])] = (
            None if value is None else str(value)
        )
    # A settings module is named by its environment (`settings_modules`), so the module of
    # each environment is one whose names are keys.
    modules = {type_descriptor(environment) for environment in config}
    return SettingsReads(keys, config, frozenset(stated | modules))


def _settings_keys_of(guard: Guard, settings: SettingsReads) -> list[SettingsKey] | None:
    """The key of each read of `guard`, where every read is a read of a settings field with a
    key; None where any is not (a read the scanner could not type, a name, a field of another
    class), and then the guard is a `test`."""
    fields = dict(guard[4])
    found = [
        settings.key_of(bare_descriptor(fields[read])) if read in fields else None
        for read in guard[3]
    ]
    if not found or any(one is None or one.key is None for one in found):
        return None
    return [one for one in found if one is not None]


@dataclass(frozen=True)
class Existence:
    """Where the calls one registration of a row ran, read two ways (`Conditions.of_sites`):
    `tied`, through the calls its paths chose, and `untied`, taking no call under no test as
    deciding for a method its paths chose none of. `key` is the registration's own calls (the
    route's root and terminal): one key giving several rows is several calls of a helper."""

    tied: Alternatives
    untied: Alternatives
    key: tuple[tuple[str, int], ...]


def existence_rows(
    registrations: Sequence[tuple[Mapping[str, Any], Existence]],
    environments: Sequence[str],
    settings: SettingsReads | None = None,
) -> list[dict[str, Any]]:
    """The `endpoint_existence` rows of each registered row: its alternatives OR-ed across
    every registration that made it, nothing for a row one of them makes unconditionally.

    Where one registration's calls gave several rows, those rows came from different calls
    of a helper, and a row its paths do not tie to one of them is read `untied` (re-review
    ruling, part 2): never "served" because some other call of the helper ran under no
    test. A helper called with nothing that differs gives one row, which is read `tied`."""
    rows_of: dict[tuple[tuple[str, int], ...], set[int]] = {}
    for row, existence in registrations:
        rows_of.setdefault(existence.key, set()).add(id(row))
    by_row: dict[int, tuple[Mapping[str, Any], set[Conjunction]]] = {}
    for row, existence in registrations:
        several = len(rows_of[existence.key]) > 1
        alternatives = existence.untied if several else existence.tied
        by_row.setdefault(id(row), (row, set()))[1].update(alternatives)
    written: list[dict[str, Any]] = []
    for row, found in by_row.values():
        alternatives = _simplest(frozenset(found))
        if alternatives == UNCONDITIONAL:
            continue
        for route, conjunction in enumerate(sorted(alternatives)):
            for position, guard in enumerate(conjunction):
                method, test, holds, reads = guard[:4]
                explained = _settings_keys_of(guard, settings) if settings else None
                keys = (
                    []
                    if explained is None
                    else list(dict.fromkeys(str(one.key) for one in explained))
                )
                expression = json.dumps(
                    {"holds": holds, "reads": list(reads), "test": test}
                    | ({"keys": keys} if explained is not None else {})
                    | ({"having_value": guard[5]} if guard[5] is not None else {}),
                    sort_keys=True,
                )
                for environment in environments:
                    written.append(
                        {
                            "protocol": row["protocol"],
                            "direction": row["direction"],
                            "method": row["method"],
                            "path": row["path"],
                            "handler": row["handler"],
                            "caller": row["caller"],
                            "route": route,
                            "position": position,
                            "via": method,
                            "kind": TEST if explained is None else PROPERTY,
                            "expression": expression,
                            "environment": environment,
                            "holds": "unresolved",
                            "resolution": "unresolved",
                            "evidence": f"{NOT_EVALUATED}`{test}`"
                            if explained is None or settings is None
                            else _evidence(explained, environment, settings),
                        }
                    )
    return written


def _evidence(found: Sequence[SettingsKey], environment: str, settings: SettingsReads) -> str:
    """A property guard's evidence in one environment: the bean property condition's lines for
    its keys, with a field's class-body default said where the configuration sets nothing, and
    the file a key may come from where the module names one through no literal (R26)."""
    config = settings.config.get(environment, {})
    keys = list(dict.fromkeys(str(one.key) for one in found))
    defaults = {str(one.key): one.default for one in found if one.default is not None}
    text = property_evidence(keys, environment, config, defaults)
    named = [one.file_detail() for one in found if one.file is not None and one.key not in config]
    return "; ".join([text, *dict.fromkeys(named)])
