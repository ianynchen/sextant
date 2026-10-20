"""The filter chain (M06 steps 1, 2 and 4), for the participants of one reactor.

Each outbound endpoint runs through protocol equality, then wire identity, then uniqueness.
Step 0 (the environment) is the caller's — it decides which `resolved_config` values the
comparison sees — and step 3 (structural compatibility) is specified and not built, which the
spec records as the user's decision 2.

**Nothing above `name_match`.** Several survivors is `narrowed` with every candidate listed,
never a pick; nothing matched is NO LINK at all, and the document says so as a finding. A
wrong link invents an architectural dependency, which `M06` calls fabrication rather than
imprecision — "and an agent will then reason from it".
"""

import json
from dataclasses import dataclass

from sextant.application.resolve.shapes.arguments import UNREADABLE_HOST
from sextant.application.stitch.participants import Participant
from sextant.domain.closed_sets import Resolution

# `M06` step 4's evidence words, the two this slice can produce.
#
# `declared` where the CLIENT STATED who it calls — a service-discovery name in the code or
# in a gateway route — which `M06`'s key table calls the strong HTTP case: the destination is
# read, not inferred from the shape of the system. `name_match` where uniqueness did the work
# instead: nobody named the peer, exactly one participant serves the address, and that one
# survivor is the answer.
DECLARED = "declared"
NAME_MATCH = "name_match"

# A Spring Cloud Gateway route's destination: `lb://customers-service` names the SERVICE and
# no route at all. Read here rather than in a catalog because it is not framework knowledge —
# it is a URI scheme sitting in the `path` column, and what this module does with it is
# publish a participant-level link, never a guess about which endpoint a request reaches.
_LOAD_BALANCED = "lb://"


@dataclass(frozen=True)
class Link:
    """One matched pair, as `links` takes it (D01's system scope).

    A PARTICIPANT-level link leaves every `to_*` endpoint column except the participant
    NULL: a gateway forwarding to `lb://customers-service` names the destination service and
    no route, and NULL is how this table says "the participant, not one of its endpoints".
    """

    from_participant: str
    from_protocol: str
    from_method: str | None
    from_path: str | None
    from_caller: str | None
    to_participant: str
    to_protocol: str | None = None
    to_method: str | None = None
    to_path: str | None = None
    resolution: str = str(Resolution.RESOLVED)
    evidence: str = NAME_MATCH
    candidates: tuple[str, ...] = ()

    def row(self) -> dict[str, object]:
        return {
            "from_participant": self.from_participant,
            "from_protocol": self.from_protocol,
            "from_method": self.from_method,
            "from_path": self.from_path,
            "from_caller": self.from_caller,
            "to_participant": self.to_participant,
            "to_protocol": self.to_protocol,
            "to_method": self.to_method,
            "to_path": self.to_path,
            "resolution": self.resolution,
            "evidence": self.evidence,
            # NULL rather than `[]` where there was nothing to choose between: an empty
            # array reads as "candidates were considered and none survived", which is a
            # different statement from "this link had one answer".
            "candidates": json.dumps(list(self.candidates)) if self.candidates else None,
        }


@dataclass(frozen=True)
class Unmatched:
    """An outbound endpoint that produced no link, and WHY.

    `M06`'s honesty obligation, and the reason this is a type rather than a silence: an
    unmatched outbound endpoint is "either a service outside the system, a participant nobody
    added, or a dependency nobody documented", and a reader can only tell those apart from the
    reason. A row in `links` with an empty other end would say none of it.
    """

    participant: str
    protocol: str
    method: str | None
    path: str | None
    caller: str | None
    reason: str


def match(
    participants: "tuple[Participant, ...]",
    endpoints: "list[dict[str, object]]",
) -> "tuple[tuple[Link, ...], tuple[Unmatched, ...]]":
    """Every link the participants' endpoints support, and every outbound endpoint that
    produced none with the reason it did not.

    `endpoints` is the federated `system_endpoints` view whole — one list, read once, indexed
    here. GUIDELINES §8.7: no read is per candidate and none is per participant pair.

    **The keys, strongest first, which is `M06`'s own ordering:**

    1. **The service name the CLIENT states.** A `peer` column naming exactly one participant
       settles WHO is called before any path is compared, so the path then only has to pick
       the route within that one participant. This is the key that makes a second module
       serving the same path harmless.
    2. **A gateway's load-balanced destination.** `lb://customers-service` in the `path`
       column names the service and no route: a participant-level link, because predicting
       which route a request reaches means simulating the router.
    3. **Verb and path alone.** Weakest, and uniqueness across the participants decides it —
       one survivor is a link at `name_match`, several is `narrowed` with all of them.

    **And one refusal, which is the user's decision 6.** An address whose AUTHORITY went
    unread — `<host>/services/admin` — is never matched by path alone, even where exactly one
    participant serves that path. Uniqueness inside the set cannot rule out a target outside
    it, so the only key that would link it rests on the half of the address nobody read.
    """
    # Every name a client could state, to the participant it names. A participant answers to
    # its artifactId AND to the name it registers in discovery, because those differ — the
    # artifactId is `spring-petclinic-customers-service` and the client states
    # `customers-service` (`participants.with_registered_names`).
    by_name: dict[str, object] = {}
    for participant in participants:
        if not participant.present:
            continue
        for name in participant.answers_to():
            # A name two participants share cannot settle who is called, so neither gets to
            # claim it. `module_id` keeps them apart in the table; nothing here can.
            by_name[name] = _AMBIGUOUS if name in by_name else participant
    served: dict[tuple[str, str | None, str], set[str]] = {}
    for row in endpoints:
        if str(row["direction"]) != "inbound":
            continue
        path = row["path"]
        if path is None:
            continue
        key = (str(row["protocol"]), _verb(row), str(path))
        served.setdefault(key, set()).add(str(row["participant"]))

    links: list[Link] = []
    unmatched: list[Unmatched] = []
    for row in endpoints:
        if str(row["direction"]) != "outbound":
            continue
        link, reason = _one(row, by_name, served)
        if link is not None:
            links.append(link)
        else:
            unmatched.append(
                Unmatched(
                    participant=str(row["participant"]),
                    protocol=str(row["protocol"]),
                    method=_verb(row),
                    path=None if row["path"] is None else str(row["path"]),
                    caller=None if row.get("caller") is None else str(row["caller"]),
                    reason=str(reason),
                )
            )
    return tuple(links), tuple(unmatched)


# A name more than one present participant carries. Not a participant, and deliberately not
# None: `by_name.get(peer)` returning this says "the name was found and settles nothing",
# which is a different answer from "the name is not in this system".
_AMBIGUOUS = object()


def _one(
    row: "dict[str, object]",
    by_name: "dict[str, object]",
    served: "dict[tuple[str, str | None, str], set[str]]",
) -> "tuple[Link | None, str | None]":
    """One outbound endpoint through the chain: its link, or None and the reason."""
    source = str(row["participant"])
    protocol = str(row["protocol"])
    verb = _verb(row)
    path = None if row["path"] is None else str(row["path"])
    caller = None if row.get("caller") is None else str(row["caller"])
    peer = None if row.get("peer") is None else str(row["peer"])

    def refuse(reason: str) -> "tuple[None, str]":
        return None, reason

    if path is None:
        # `M06`'s own reading of such a row: "this method calls something over HTTP" is true
        # and useful on its own, and it is not a link.
        return refuse("the address could not be read at all")

    # Key 2, before the path is read as a path: `lb://name` is a destination, not a route.
    if path.startswith(_LOAD_BALANCED):
        stated = path[len(_LOAD_BALANCED) :]
        target = by_name.get(stated)
        if target is _AMBIGUOUS:
            return refuse(f"more than one participant is named {stated!r}")
        if target is None:
            return refuse(f"no participant in this system is named {stated!r}")
        assert isinstance(target, Participant)
        return (
            Link(
                from_participant=source,
                from_protocol=protocol,
                from_method=verb,
                from_path=path,
                from_caller=caller,
                # The participant's OWN name, never the alias the client stated: the row has
                # to join `participants`, and a reader comparing two links must see one
                # spelling per participant.
                to_participant=target.name,
                evidence=DECLARED,
            ),
            None,
        )

    # The refusal (user decision 6). Before any path comparison, because the point is that
    # this path is not the whole address.
    if path.startswith(UNREADABLE_HOST):
        return refuse(
            "the address's authority went unread, so the path alone cannot say who is called"
        )

    # Key 1: the peer the client stated narrows WHO before the path picks the route.
    candidates = served.get((protocol, verb, path), set()) - {source}
    if peer is not None:
        target = by_name.get(peer)
        if target is _AMBIGUOUS:
            return refuse(f"more than one participant is named {peer!r}")
        if target is None:
            # The client named a destination this system does not contain. That is `M06`'s
            # "a service outside the system" — a finding, and emphatically not a licence to
            # fall through to the path and link to whoever happens to serve it.
            return refuse(f"the client names {peer!r}, which is not a participant")
        named_participant = target
        assert isinstance(named_participant, Participant)
        if named_participant.name not in candidates:
            # WHO is known and the route is not. The dependency is real — the code calls
            # that service — so the honest row is a participant link, and the route is
            # simply not something this pair of facts settles.
            return (
                Link(
                    from_participant=source,
                    from_protocol=protocol,
                    from_method=verb,
                    from_path=path,
                    from_caller=caller,
                    to_participant=named_participant.name,
                    evidence=DECLARED,
                ),
                None,
            )
        return (
            Link(
                from_participant=source,
                from_protocol=protocol,
                from_method=verb,
                from_path=path,
                from_caller=caller,
                to_participant=named_participant.name,
                to_protocol=protocol,
                to_method=verb,
                to_path=path,
                evidence=DECLARED,
            ),
            None,
        )

    # Key 3, the weak one: uniqueness across the participants decides (step 4).
    if not candidates:
        return refuse("no participant in this system serves this address")
    if len(candidates) > 1:
        return (
            Link(
                from_participant=source,
                from_protocol=protocol,
                from_method=verb,
                from_path=path,
                from_caller=caller,
                # The first candidate alphabetically fills the column so the row is
                # readable, and `candidates` carries all of them — which is what a
                # `narrowed` link means and what `M06`'s honesty obligation asks for. A
                # reader must consult `resolution` before `to_participant`, exactly as they
                # must for `format` beside `format_resolution` (D01 §3).
                to_participant=min(candidates),
                to_protocol=protocol,
                to_method=verb,
                to_path=path,
                resolution=str(Resolution.NARROWED),
                candidates=tuple(sorted(candidates)),
            ),
            None,
        )
    return (
        Link(
            from_participant=source,
            from_protocol=protocol,
            from_method=verb,
            from_path=path,
            from_caller=caller,
            to_participant=next(iter(candidates)),
            to_protocol=protocol,
            to_method=verb,
            to_path=path,
        ),
        None,
    )


def _verb(row: "dict[str, object]") -> str | None:
    """The row's HTTP method, or None where it declares none.

    Carried through comparisons as-is rather than defaulted: a verbless row is one whose verb
    nobody read, and treating that as equal to every verb would link a call to routes it
    cannot reach. Two verbless rows on one path do compare equal, which is the same NULL-safe
    reading `endpoints`' own dedup key takes.
    """
    return None if row.get("method") is None else str(row["method"])


@dataclass(frozen=True)
class Uncalled:
    """An inbound endpoint no link points at.

    `M06`'s other finding that is not an error: such an endpoint is "either dead, or called
    from outside". Both readings are useful and this module cannot tell them apart — which is
    why it reports the row and makes no claim about which it is.
    """

    participant: str
    protocol: str
    method: str | None
    path: str
    handler: str | None


def uncalled(
    endpoints: "list[dict[str, object]]", links: "tuple[Link, ...]"
) -> "tuple[Uncalled, ...]":
    """Every inbound endpoint no link reaches.

    **A PARTICIPANT-level link reaches all of them.** A gateway forwarding to
    `lb://customers-service` names the service and no route, so every route that service
    serves is reachable through it — and calling one of them "uncalled" would be a false
    finding about a dependency this analysis did read. So a participant named by any link
    has none of its endpoints reported here.

    Ordered for NFR-1, and deduplicated: two catalogs describing one handler produce one
    endpoint row each only if they differ, and a finding stated twice is noise.
    """
    reached: set[tuple[str, str, str | None, str]] = set()
    whole: set[str] = set()
    for link in links:
        if link.to_path is None:
            whole.add(link.to_participant)
        else:
            reached.add((link.to_participant, str(link.to_protocol), link.to_method, link.to_path))
    out = set()
    for row in endpoints:
        if str(row["direction"]) != "inbound" or row["path"] is None:
            continue
        participant = str(row["participant"])
        if participant in whole:
            continue
        key = (participant, str(row["protocol"]), _verb(row), str(row["path"]))
        if key in reached:
            continue
        out.add(
            Uncalled(
                participant=participant,
                protocol=str(row["protocol"]),
                method=_verb(row),
                path=str(row["path"]),
                handler=None if row.get("handler") is None else str(row["handler"]),
            )
        )
    return tuple(
        sorted(
            out, key=lambda u: (u.participant, u.protocol, u.path, u.method or "", u.handler or "")
        )
    )
