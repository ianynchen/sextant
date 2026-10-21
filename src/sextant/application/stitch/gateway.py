"""A gateway route's prefix, joined to the paths the service it names serves.

**This is a PATH PREFIX and not a rewrite engine**, which is the whole design and was the
user's own correction. A class-level `@RequestMapping("/owners")` in front of a method's
`@GetMapping("/{ownerId}")` makes `/owners/{ownerId}`; `setPathPrefixes` does the same per
package. A gateway route is that shape with the two halves in two MODULES:

    gateway declares      Path=/api/customer/**  ->  lb://customers-service
    customers-service serves                         GET /owners/{ownerId}
    full address          GET /api/customer/owners/{ownerId}

So nothing here simulates a router. `M06`'s "no runtime prediction" rule is kept by composing
a prefix the configuration states, and by REFUSING wherever the configuration does not license
the composition.

**The gate.** `StripPrefix=N` must remove exactly the prefix being composed, which is true
when `N` equals the prefix's segment count — `/api/customer` is two segments and the route
says `StripPrefix=2`. Where they disagree the composition is wrong: with `StripPrefix=1` the
service receives `/customer/owners/7`, so either its own published path already carries a
`/customer` context or the route is broken, and neither is prefix-plus-path. Measured across
the corpus, `N` equals the segment count on 9 routes of 9.

`stitch` names no framework, so WHICH keys hold a route comes from the catalog
(`spring-cloud-gateway-properties.yml`'s `indexed` block: the prefix, the `Path` predicate,
the `uri` destination, and the `strip` filter). This module is handed those names.
"""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from sextant.application.stitch.links import DECLARED, Link
from sextant.domain.closed_sets import Resolution

# A route's wildcard tail, as a `Path=` predicate writes it. Everything before it is the
# literal prefix this module composes with; the tail is what the service's own paths fill.
_WILDCARD = "/**"

# `Name=arg` — the shortcut form a predicate and a filter are both written in. The catalog
# declares WHICH names matter; this is only the split.
_SHORTCUT = re.compile(r"^(?P<name>[A-Za-z][A-Za-z0-9]*)=(?P<args>.*)$")


@dataclass(frozen=True)
class RouteModel:
    """The configuration keys a gateway route lives under, as a catalog declares them."""

    prefix: str
    predicates_field: str
    path_predicate: str
    # The predicate that RESTRICTS a route to some verbs (`Method=GET,POST`). A route
    # declaring none forwards every method; one declaring it forwards only those, and a
    # composed link for any other verb is an address the gateway rejects.
    method_predicate: str
    destination_field: str
    filters_field: str
    strip_filter: str


@dataclass(frozen=True)
class Refusal:
    """A route whose prefix could not be composed, and why.

    `M06`'s honesty obligation applied to this join: the route still produces a
    participant-level link, so the dependency is not lost — what is refused is the claim
    about WHICH endpoints it reaches, and a reader needs the two numbers to see why.
    """

    participant: str
    route: str
    reason: str


def route_model(matches: "Mapping[str, object]") -> "RouteModel | None":
    """The `RouteModel` a catalog's `indexed` block declares, or None where it declares none.

    Read defensively because this reads another engine's block: a catalog that grows a route
    model without a `strip` entry contributes no composition rather than half of one.
    """
    indexed = matches.get("indexed")
    if not isinstance(indexed, dict):
        return None
    item = indexed.get("item")
    prefix = indexed.get("prefix")
    if not isinstance(item, dict) or not isinstance(prefix, str):
        return None
    path = item.get("path")
    method = item.get("method")
    peer = item.get("peer")
    strip = item.get("strip")
    predicates = item.get("predicates")
    if not all(isinstance(block, dict) for block in (path, method, peer, strip, predicates)):
        return None
    return RouteModel(
        prefix=prefix,
        predicates_field=str(predicates["field"]),  # type: ignore[index]
        path_predicate=str(path["name"]),  # type: ignore[index]
        method_predicate=str(method["name"]),  # type: ignore[index]
        destination_field=str(peer["field"]),  # type: ignore[index]
        filters_field=str(strip["field"]),  # type: ignore[index]
        strip_filter=str(strip["name"]),  # type: ignore[index]
    )


def gateway_links(
    config: "Sequence[Mapping[str, object]]",
    endpoints: "Sequence[Mapping[str, object]]",
    model: "RouteModel | None",
    names: "Mapping[str, str]",
) -> "tuple[tuple[Link, ...], tuple[Refusal, ...]]":
    """One link per (route, served endpoint) pair, and one refusal per route that could not
    be composed.

    `names` maps every name a client could state — a participant's own and its aliases — to
    that participant's own name, which is `links.match`'s index and is what a link must
    carry so the row joins `participants`.

    **Every link here is `resolved`, not `narrowed`**, and the distinction is the user's own
    ruling. `/api/customer/**` reaches all eight of `customers-service`'s endpoints and every
    one of them genuinely is reachable: a `GET /api/customer/owners/7` does reach
    `GET /owners/{ownerId}`, and `GET /api/customer/petTypes` does reach `GET /petTypes`.
    Each pair is individually certain, so each is its own resolved link. `narrowed` means a
    set one of whose members is the answer and we cannot say which — eight certain links are
    not one uncertain link.

    Costs nothing per `GUIDELINES` §8.7: one pass over the configuration rows the caller
    already holds, and one pass over the endpoints indexed by participant.
    """
    if model is None:
        return (), ()
    served: dict[str, list[Mapping[str, object]]] = {}
    for row in endpoints:
        if str(row["direction"]) == "inbound" and row["path"] is not None:
            served.setdefault(str(row["participant"]), []).append(row)

    links: list[Link] = []
    refusals: list[Refusal] = []
    for participant, index, route in _routes(config, model):
        prefix, destination, strip, verbs = route
        if prefix is None or destination is None:
            # A route this analysis could not read whole. The `peer` rule of the catalog's
            # own engine already published the destination as an outbound row, so the
            # participant-level link is minted there; nothing is lost by saying nothing here.
            continue
        target = names.get(destination)
        if target is None:
            continue
        segments = [piece for piece in prefix.split("/") if piece]
        if strip is None or strip != len(segments):
            refusals.append(
                Refusal(
                    participant=participant,
                    route=f"{prefix}{_WILDCARD}",
                    reason=(
                        f"the route strips {strip} path "
                        f"segment{'' if strip == 1 else 's'} and its prefix has "
                        f"{len(segments)}, so the gateway's own address is not that prefix "
                        f"plus the service's path"
                        if strip is not None
                        else f"the route declares no {model.strip_filter} filter, so what "
                        f"it removes from the path is unread"
                    ),
                )
            )
            continue
        for row in served.get(target, ()):
            # **A route restricted to some verbs reaches only those.** `Method=GET` in front
            # of a service serving `GET` and `POST /orders` composes ONE link, not two: the
            # gateway rejects a `POST /o/orders` before it ever forwards, so a link for it
            # would be an address no request takes. MEASURED as a false fact before this
            # check existed. A route declaring no `Method` forwards every verb, which is
            # what an empty set means here.
            if verbs and str(row["method"]).upper() not in verbs:
                continue
            path = str(row["path"])
            links.append(
                Link(
                    from_participant=participant,
                    from_protocol=str(row["protocol"]),
                    from_method=None if row["method"] is None else str(row["method"]),
                    # The gateway's OWN address for this route: the prefix it serves under
                    # followed by the path the service serves. A service path of `/` leaves
                    # the prefix alone rather than producing a trailing slash.
                    from_path=prefix if path == "/" else f"{prefix}{path}",
                    from_caller=None,
                    to_participant=target,
                    to_protocol=str(row["protocol"]),
                    to_method=None if row["method"] is None else str(row["method"]),
                    to_path=path,
                    resolution=str(Resolution.RESOLVED),
                    evidence=DECLARED,
                )
            )
        _ = index
    return tuple(links), tuple(refusals)


def _routes(
    config: "Sequence[Mapping[str, object]]", model: "RouteModel"
) -> "list[tuple[str, int, tuple[str | None, str | None, int | None, frozenset[str]]]]":
    """Every route in the configuration, as `(participant, index, (prefix, destination,
    strip))`.

    The configuration layer flattens a route list to `…routes[N].<field>` keys, so a route is
    reassembled from the index in its key. Sorted by participant and index, for NFR-1.
    """
    collected: dict[tuple[str, int], dict[str, str]] = {}
    pattern = re.compile(rf"^{re.escape(model.prefix)}\[(?P<index>\d+)\]\.(?P<field>.+)$")
    for row in config:
        key = str(row.get("key") or "")
        value = row.get("value")
        if value is None:
            continue
        match = pattern.match(key)
        if match is None:
            continue
        slot = (str(row["participant"]), int(match.group("index")))
        collected.setdefault(slot, {})[match.group("field")] = str(value)

    out = []
    for (participant, index), fields in sorted(collected.items()):
        out.append((participant, index, _one(fields, model)))
    return out


def _one(
    fields: "Mapping[str, str]", model: "RouteModel"
) -> "tuple[str | None, str | None, int | None, frozenset[str]]":
    """One route's `(literal prefix, destination name, strip count, verbs)` — `verbs` empty
    where the route declares no `Method` predicate and so forwards every one.

    Each is None where the configuration does not state it readably: a `Path=` predicate
    without a `/**` tail prefixes nothing (it names one exact address, which the catalog's own
    row already publishes), a destination that is not `lb://name` names no participant, and a
    `StripPrefix` whose argument is not a number is unread rather than guessed at.
    """
    prefix = None
    destination = None
    strip = None
    verbs: set[str] = set()
    for field, value in fields.items():
        if field.startswith(f"{model.predicates_field}["):
            shortcut = _SHORTCUT.match(value)
            if shortcut and shortcut.group("name") == model.path_predicate:
                pattern = shortcut.group("args")
                if pattern.endswith(_WILDCARD):
                    prefix = pattern[: -len(_WILDCARD)]
            elif shortcut and shortcut.group("name") == model.method_predicate:
                verbs.update(
                    verb.strip().upper()
                    for verb in shortcut.group("args").split(",")
                    if verb.strip()
                )
        elif field.startswith(f"{model.filters_field}["):
            shortcut = _SHORTCUT.match(value)
            if shortcut and shortcut.group("name") == model.strip_filter:
                argument = shortcut.group("args").strip()
                if argument.isdigit():
                    strip = int(argument)
        elif field == model.destination_field:
            # `lb://name` — a load-balanced destination names a service. Anything else (an
            # absolute `http://host:port`) names a host, not a participant of this build.
            if value.startswith("lb://"):
                destination = value[len("lb://") :]
    return prefix, destination, strip, frozenset(verbs)
