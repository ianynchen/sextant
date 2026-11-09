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
joined).

Each guard of each alternative is one `endpoint_existence` row per environment the module
resolves (D01): kind `test`, its expression the test as the code writes it with the arm it is
in, `holds = unresolved`. Names no framework: the calls are the engine's, the tests the facts'.

**Stated limits.** A function in a cycle of calls is taken to run unconditionally while the
cycle is being followed (the old answer, never a dropped row). A test is never evaluated, even
where its value is written in the repository: plan 3 links a settings field to its
configuration key. A class body's statements are read with no test the module body puts them
under.

Cost (GUIDELINES §8.7): per inbound catalog run, one read of the guarded call sites (a fact
query, cached per load) and, only where some call is guarded, one read of the call edges; each
method's alternatives are computed once.
"""

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from sextant.application.ports.workspace import Workspace

# The condition kind of a test the analysis does not evaluate (D01 `endpoint_existence.kind`).
TEST = "test"
# The environment of a module that resolves none of its own (`resolved_config` holds none).
DEFAULT_ENVIRONMENT = "default"
NOT_EVALUATED = "a condition this analysis does not evaluate: "

# One guard: the method whose body holds the test, the test as written, the arm, its reads.
Guard = tuple[str, str, bool, tuple[str, ...]]
Conjunction = frozenset[Guard]
Alternatives = frozenset[Conjunction]
UNCONDITIONAL: Alternatives = frozenset({frozenset()})


@dataclass
class Conditions:
    """The guarded calls and who calls whom, read once per resolve, and each method's
    alternatives as they are asked for."""

    guards: dict[tuple[str, int], tuple[Guard, ...]]
    callers: dict[str, tuple[tuple[str, int], ...]]
    _methods: dict[str, Alternatives] = field(default_factory=dict)
    _entered: set[str] = field(default_factory=set)

    def of_sites(self, sites: Iterable[tuple[str, int]]) -> Alternatives:
        """Where every call of `sites` runs: one alternative per choice of one alternative of
        each call, joined."""
        found = UNCONDITIONAL
        for site in dict.fromkeys(sites):
            found = _simplest(
                frozenset(left | right for left in found for right in self._of_site(site))
            )
        return found

    def _of_site(self, site: tuple[str, int]) -> Alternatives:
        own = frozenset(self.guards.get(site, ()))
        return frozenset(own | conjunction for conjunction in self._of_method(site[0]))

    def _of_method(self, method: str) -> Alternatives:
        """Where `method` runs: wherever any call of it runs; everywhere where nothing in the
        module calls it, and while it is being followed in a cycle."""
        if method in self._methods:
            return self._methods[method]
        callers = self.callers.get(method, ())
        if not callers or method in self._entered:
            return UNCONDITIONAL
        self._entered.add(method)
        try:
            found: set[Conjunction] = set()
            for site in callers:
                found |= self._of_site(site)
                if frozenset() in found:
                    break
        finally:
            self._entered.discard(method)
        answer = _simplest(frozenset(found))
        self._methods[method] = answer
        return answer


def _simplest(alternatives: Alternatives) -> Alternatives:
    """`alternatives` without one that another implies (a superset of another's guards): the
    row exists wherever the smaller does."""
    if frozenset() in alternatives:
        return UNCONDITIONAL
    return frozenset(one for one in alternatives if not any(other < one for other in alternatives))


def conditions_of(workspace: Workspace) -> Conditions:
    """The guarded calls, and the callers of each method where any call is guarded. Read by the
    engine once per run: `call_edges` is derived, so it is never kept across passes."""
    guards: dict[tuple[str, int], tuple[Guard, ...]] = {}
    for row in workspace.query("call_site_guards"):
        caller = str(row["caller"])
        guards[(caller, int(str(row["ordinal"])))] = tuple(
            (caller, str(g["test"]), bool(g["holds"]), tuple(g.get("reads") or ()))
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


def existence_rows(
    registrations: Sequence[tuple[Mapping[str, Any], Alternatives]],
    environments: Sequence[str],
) -> list[dict[str, Any]]:
    """The `endpoint_existence` rows of each registered row: its alternatives OR-ed across
    every registration that made it, nothing for a row one of them makes unconditionally."""
    by_row: dict[int, tuple[Mapping[str, Any], set[Conjunction]]] = {}
    for row, alternatives in registrations:
        by_row.setdefault(id(row), (row, set()))[1].update(alternatives)
    written: list[dict[str, Any]] = []
    for row, found in by_row.values():
        alternatives = _simplest(frozenset(found))
        if alternatives == UNCONDITIONAL:
            continue
        for route, conjunction in enumerate(sorted(alternatives, key=lambda c: sorted(c))):
            for method, test, holds, reads in sorted(conjunction):
                expression = json.dumps(
                    {"holds": holds, "reads": list(reads), "test": test}, sort_keys=True
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
                            "via": method,
                            "kind": TEST,
                            "expression": expression,
                            "environment": environment,
                            "holds": "unresolved",
                            "resolution": "unresolved",
                            "evidence": f"{NOT_EVALUATED}`{test}`",
                        }
                    )
    return written
