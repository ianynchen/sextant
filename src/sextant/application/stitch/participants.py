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

import json
from dataclasses import dataclass, replace
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
    # Every OTHER name this participant answers to — the name it registers in discovery,
    # which is what a client states. See `with_registered_names`.
    aliases: tuple[str, ...] = ()

    def answers_to(self) -> "tuple[str, ...]":
        """Every name a client could state for this participant: its own and its aliases."""
        return (self.name, *self.aliases)

    def row(self) -> dict[str, object]:
        """This participant as `participants` takes it (D01's system scope)."""
        return {
            "name": self.name,
            "kind": SERVICE,
            "module_id": self.module_id,
            # NULL rather than `[]` where there is no alias, for `links.candidates`'
            # reason: an empty array reads as a statement, and there is none to make.
            "aliases": json.dumps(list(self.aliases)) if self.aliases else None,
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
    ids = [str(entry.get("module_id") or "") for entry in modules]
    bare = [module_id.rsplit(":", 1)[-1] for module_id in ids]
    # **A name two modules share is not a name.** `participants.name` is what the
    # federation, the links and the document key on, and a dict keyed by it collapsed two
    # participants into one — MEASURED: of two modules both called `svc`, one's graph was
    # never attached and nothing said so. So where artifactIds collide, each participant
    # is named by its FULL coordinate and the bare artifactId becomes an alias on both —
    # which makes a client stating `svc` hit the ambiguity refusal, as it must, while each
    # participant's own rows still carry a name that is theirs alone.
    collided = {name for name in bare if bare.count(name) > 1}
    out = []
    for entry, module_id, short in zip(modules, ids, bare, strict=True):
        if not module_id:
            # A reactor entry with no coordinate names no participant. `modules.json`
            # always carries one; this is the refusal rather than a row whose `name` would
            # be the empty string and whose matches would be nonsense.
            continue
        unique = module_id if short in collided else short
        out.append(
            Participant(
                name=unique,
                module_id=module_id,
                location=entry.get("location"),  # type: ignore[arg-type]
                commit_id=None if entry.get("commit_id") is None else str(entry["commit_id"]),
                present=entry.get("location") is not None,
                absent_reason=_absent_reason(entry),
                aliases=(short,) if unique != short else (),
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


def with_registered_names(
    participants: "tuple[Participant, ...]",
    config: "list[dict[str, object]]",
    key: str | None,
) -> "tuple[Participant, ...]":
    """`participants`, each carrying the name it REGISTERS as an alias.

    **A build coordinate is not a service name**, and the gap is the whole reason this
    exists. The artifactId is `spring-petclinic-customers-service`; every client in that
    system states `customers-service`, which is the name the module registers in discovery
    and declares in its own configuration. MEASURED: on the artifactId alone that corpus
    produces 0 links, because the matcher correctly refuses a peer it cannot find; with the
    registered name it produces 10.

    `key` is the configuration key holding it, which a CATALOG declares
    (`participant_name_key` — on the family's base catalog, where `config_model` and
    `terminals` live for the same reason). Which key it is, is framework knowledge; this
    function only knows that some key answers the question, and `None` means no loaded
    catalog declared one, in which case every participant keeps its artifactId.

    `config` is the federated `system_config` view already filtered to ONE environment by
    the caller (`M06` step 0, user decision 7). So the alias is read per environment and
    never filled from another environment's value — a module that registers one name under
    `prod` and another under `dev` is two different systems, and this answers about the one
    asked for.

    **An alias equal to the artifactId adds nothing and is dropped**, which keeps the column
    NULL for the common case rather than restating the name beside itself — `mall-swarm`'s
    six modules are all this case, because their artifactIds already are their service names.
    """
    if key is None:
        return participants
    registered: dict[str, str] = {}
    for row in config:
        if str(row.get("key")) != key or row.get("value") is None:
            continue
        registered[str(row["participant"])] = str(row["value"])
    out = []
    for participant in participants:
        name = registered.get(participant.name)
        if name is None or name in participant.answers_to():
            out.append(participant)
        else:
            out.append(replace(participant, aliases=(*participant.aliases, name)))
    return tuple(out)
