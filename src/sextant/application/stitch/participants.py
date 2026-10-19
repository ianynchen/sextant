"""The participant set of one reactor (M05's job, done for one build).

`M05` assembles participants from `system.yml`, `system.state.json` and bundles fetched from
earlier runs. None of that exists, and a reactor needs none of it: `module analyze` at a
reactor root already records every module it found in `modules.json`, and each module's graph
is in its own workspace. So the participant set is that record, read rather than re-walked —
which also makes "analyze must have run first" an explicit precondition instead of a
surprise, the same precondition `api._refuse_if_unanalyzed` already states off the same file.

**This module is pure.** It is handed what the file said and what the filesystem showed, and
returns rows. The reading belongs to the adapter above it (GUIDELINES' layering: application
never reaches for a path of its own).
"""

from dataclasses import dataclass
from pathlib import Path

# What `participants.kind` carries. Only the first is written on the reactor path: a declared
# external host is a `system.yml` fact and there is no manifest (M06 "External participants",
# not built — user decision 5, 2026-10-19).
SERVICE = "service"
EXTERNAL = "external"


@dataclass(frozen=True)
class Participant:
    """One service of the system, and whether its graph could be read.

    `name` is what a link is MATCHED by — a service-discovery name a client states, like
    `customers-service`. On the reactor path it is the module's artifactId, which is both
    what Spring's `spring.application.name` defaults to and what every `lb://` in the two
    pinned gateways names. It is not unique in principle (two groups may ship the same
    artifactId), which is why `module_id` is carried beside it and why matching reports
    several candidates rather than picking one.
    """

    name: str
    module_id: str
    location: Path | None
    commit_id: str | None
    present: bool
    absent_reason: str | None

    def row(self) -> dict[str, object]:
        """This participant as `participants` takes it (D01's system scope)."""
        return {
            "name": self.name,
            "kind": SERVICE,
            "module_id": self.module_id,
            "location": None if self.location is None else str(self.location),
            "commit_id": self.commit_id,
            "present": self.present,
            "absent_reason": self.absent_reason,
        }


def participants_of(modules: "list[dict[str, object]]") -> tuple[Participant, ...]:
    """One `Participant` per module the reactor named, present or absent.

    `modules` is `modules.json`'s own `modules` array, each entry already carrying the two
    things the workspace lookup needs — `module_id` and the resolved `location`, which the
    adapter sets to the module's workspace path where one exists and to None where it does
    not — plus `analyzed`, `skip_reason` and `commit_id`.

    **An absent participant is a ROW, not an omission**, and that is the whole reason this
    function returns the skipped modules too. `M06`'s rule is that an unmatched call into a
    participant nobody could read is attributed to the gap rather than reported as an
    architectural finding, and a missing row cannot tell a reader which case they are
    looking at: *nothing calls this* and *we could not read this* are different statements
    about a system.

    Ordered by name, then `module_id`, so the set is the same on every run (NFR-1) and two
    modules sharing an artifactId still order deterministically.
    """
    out = []
    for entry in modules:
        module_id = str(entry.get("module_id") or "")
        if not module_id:
            # A reactor entry with no coordinate names no participant. `modules.json`
            # always carries one; this is the refusal rather than a row whose `name` would
            # be the empty string and whose matches would be nonsense.
            continue
        out.append(
            Participant(
                name=module_id.rsplit(":", 1)[-1],
                module_id=module_id,
                location=entry.get("location"),  # type: ignore[arg-type]
                commit_id=None if entry.get("commit_id") is None else str(entry["commit_id"]),
                present=entry.get("location") is not None,
                absent_reason=_absent_reason(entry),
            )
        )
    return tuple(sorted(out, key=lambda p: (p.name, p.module_id)))


def _absent_reason(entry: "dict[str, object]") -> str | None:
    """Why this participant's graph could not be read, in the words a reader can act on —
    or None where it was read.

    The three cases are distinct and a reader needs them apart: a module the detector
    skip-listed on purpose (a `pom` packaging aggregator, say) is not the same as one
    `analyze` was never run for, and neither is the same as one whose workspace has since
    been deleted. The first is correct behaviour; the other two are something to do.
    """
    if entry.get("location") is not None:
        return None
    skip = entry.get("skip_reason")
    if skip:
        return f"the module was skip-listed when the reactor was analyzed: {skip}"
    if not entry.get("analyzed"):
        return "the module was not analyzed; run `sextant module analyze` at the reactor root"
    return "the module was analyzed but its workspace is no longer there"
