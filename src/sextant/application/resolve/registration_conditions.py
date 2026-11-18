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
exists unconditionally, and then nothing is written. A row's calls are its registration (the
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
key explains cannot be called a property condition.

**Stated limits.** A function in a cycle of calls is taken to run unconditionally while the
cycle is being followed (the old answer, never a dropped row). A test is never evaluated, even
where its value is written in the repository. A read the scanner cannot type is not linked to a
settings field, so its guard stays `test`. A class body's statements are read with no test the module body puts them
under.

Cost (GUIDELINES §8.7): per inbound catalog run, one read of the guarded call sites (a fact
query, cached per load) and, only where some call is guarded, one read of the call edges; each
method's alternatives are computed once.
"""

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from sextant.application.ports.catalogs import Catalog
from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.bean_conditions import property_evidence
from sextant.application.resolve.dispatch import dispatch_of
from sextant.application.resolve.settings_fields import (
    CONFIG_MODEL_FORM,
    SettingsKey,
    settings_keys,
)
from sextant.domain.symbols import bare_descriptor

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
Guard = tuple[str, str, bool, tuple[str, ...], tuple[tuple[str, str], ...]]
# The guards of one alternative, outermost first (a caller's before its callee's, an include's
# before the routes under it), each once.
Conjunction = tuple[Guard, ...]
Alternatives = frozenset[Conjunction]
UNCONDITIONAL: Alternatives = frozenset({()})
# The call a row's own path chose for a method (`Path.calls_into`): the calling context it was
# derived in.
Chosen = Mapping[str, tuple[str, int]]


@dataclass
class Conditions:
    """The guarded calls and who calls whom, read once per resolve, and each method's
    alternatives as they are asked for."""

    guards: dict[tuple[str, int], tuple[Guard, ...]]
    callers: dict[str, tuple[tuple[str, int], ...]]
    _methods: dict[tuple[str, bool], Alternatives] = field(default_factory=dict)
    _entered: set[str] = field(default_factory=set)

    def of_sites(
        self,
        sites: Iterable[tuple[str, int]],
        chosen: Chosen | None = None,
        untied: bool = False,
    ) -> Alternatives:
        """Where every call of `sites` runs, outermost first: one alternative per choice of
        one alternative of each call, joined. A method `chosen` names a call of is run by
        that call alone (task 10b review, Major 1): a row derived through one call of a helper
        takes that call's tests, never those of the helper's other callers.

        `untied`: the row cannot be tied to one call of a method `chosen` leaves out, though
        that method's calls register different rows (re-review ruling, part 2). Then a method
        some calls run under a test and some under none is taken to run under its tests only:
        the row is "not evaluated", never served on the strength of a call that may have
        registered another row."""
        found = UNCONDITIONAL
        for site in dict.fromkeys(sites):
            found = _simplest(
                frozenset(
                    _joined(left, right)
                    for left in found
                    for right in self._of_site(site, chosen or {}, frozenset(), untied)
                )
            )
        return found

    def _of_site(
        self, site: tuple[str, int], chosen: Chosen, followed: frozenset[str], untied: bool
    ) -> Alternatives:
        own = self.guards.get(site, ())
        method = site[0]
        if method in chosen and method not in followed:
            outer = self._of_site(chosen[method], chosen, followed | {method}, untied)
        else:
            outer = self._of_method(method, untied)
        return frozenset(_joined(conjunction, own) for conjunction in outer)

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


def conditions_of(workspace: Workspace) -> Conditions:
    """The guarded calls, and the callers of each method where any call is guarded. Read by the
    engine once per run: `call_edges` is derived, so it is never kept across passes."""
    guards: dict[tuple[str, int], tuple[Guard, ...]] = {}
    for row in workspace.query("call_site_guards"):
        caller = str(row["caller"])
        guards[(caller, int(str(row["ordinal"])))] = tuple(
            (
                caller,
                str(g["test"]),
                bool(g["holds"]),
                tuple(g.get("reads") or ()),
                tuple(sorted((g.get("fields") or {}).items())),
            )
            for g in json.loads(str(row["guards"]))
        )
    callers: dict[str, list[tuple[str, int]]] = {}
    if guards:
        for row in workspace.query("calls_running"):
            callers.setdefault(str(row["callee"]), []).append(
                (str(row["caller"]), int(str(row["ordinal"])))
            )
    return Conditions(guards, {callee: tuple(sites) for callee, sites in callers.items()})


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


def settings_reads_of(workspace: Workspace, catalog: Catalog) -> SettingsReads:
    """The settings fields of the module the catalog's config model declares, empty where it
    declares none. Read once per resolve, and only for a run whose rows are guarded."""
    model = next(
        (row for row in catalog.returns_arguments if row.get("form") == CONFIG_MODEL_FORM), None
    )
    if model is None or not model.get("settings_form"):
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
    return SettingsReads(keys, config)


def _settings_keys_of(guard: Guard, settings: SettingsReads) -> list[SettingsKey] | None:
    """The key of each read of `guard`, where every read is a read of a settings field with a
    key; None where any is not (a read the scanner could not type, a name, a field of another
    class), and then the guard is a `test`."""
    fields = dict(guard[4])
    found = [
        settings.keys.get(bare_descriptor(fields[read])) if read in fields else None
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
                    | ({"keys": keys} if explained is not None else {}),
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
