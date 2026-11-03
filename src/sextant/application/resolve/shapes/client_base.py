"""A client's base address (spec 2026-10-26 §3c, §3g items 1-3): the `client_base` catalog
key, the reader that finds the base, and the join that puts a relative call onto it.

A library whose client holds a base address — Ktor's `defaultRequest { url("…") }` — sends a
relative call to the base JOINED with the call's own address, and the join is the library's
rule, not ours (DR-6). Three parts live here, so the `fluent` client catalog and Task 6's
`single_call` WebSocket and SSE catalogs share one copy of each:

- **`client_base_of`**, the key read and its shape refused at load. It says where the client
  sits at the call that issues it (`client_arg`), the configuration calls a base is set
  through (`ladder`, each with the argument holding its block), the call inside the last
  block that sets the base (`setter`), which join applies (`join`), and which other calls
  may move the base (`may_set_base`). All of it is catalog data: nothing here names a framework.
- **`join_url`**, the join itself, one rule per behaviour measured. A rule is named for what
  it does, never for the framework that does it (the source rules keep framework names out of
  code); the catalog that declares the join is where the framework is named.
- **`client_base`**, the base itself: the client's construction found by the value walk's
  producer reader (`values.producers_of`), then read through the declared ladder to the
  setter's string. It names no engine's types, so `fluent` and `single_call` call the same
  copy.
- **`against_client_base`**, what a relative address the code states becomes: the joined
  URL, a configuration base carried at `partial`, or the address kept at `unresolved` where
  no base is read or the join declines — one decision, which both engines render in their
  own row shape.

The key itself is declared once per CLIENT, not per catalog: a catalog names a model in
`client-models/` (`client_model:`) and states only its own `client_arg`, and the loader
merges the two (`ingress/catalogs/yaml_source._with_client_model`).
"""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from weakref import WeakKeyDictionary

from sextant.application.ports.catalogs import CatalogError
from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.shapes.arguments import call_site_index, carries_expression
from sextant.application.resolve.shapes.member_values import static_field_value
from sextant.application.resolve.values import (
    CYCLE,
    EXPRESSION,
    INT,
    LITERAL,
    NON_ENUMERABLE,
    NOT_READABLE,
    RECEIVER,
    STRING,
    UNRESOLVED,
    Path,
    ValueIndex,
    entered_position,
    inexact,
    producer_paths,
    producers_of,
    resolve_positions,
)
from sextant.domain.closed_sets import Resolution
from sextant.domain.symbols import returned_type, type_descriptor, with_descriptor

# The join Ktor's `DefaultRequest` makes, read off its 3.6.0 bytecode
# (`DefaultRequest$Plugin.mergeUrls` and `concatenatePath`) and measured by CP-54 rows 51-60:
# a relative path REPLACES the base's last segment (a base ending in `/` has an empty last
# segment, so it keeps every directory), and the base's query follows the call's own.
REPLACE_LAST_SEGMENT = "replace_last_segment"
# The join Vert.x's `WebClientBase` makes, measured by CP-56 row group (e) (rows 123-132): a
# client's default host and port fill a request that names neither, each part on its own, a
# request's own part wins, and an absolute request reads neither. It moves only the peer:
# Vert.x never rewrites the path.
FILL_AUTHORITY = "fill_authority"
_JOINS = (REPLACE_LAST_SEGMENT, FILL_AUTHORITY)

_KEYS = {"client_arg", "ladder", "setter", "join", "may_set_base"}
# THE OPTIONS-OBJECT RUNG (Vert.x spec 2026-10-30 §3d, §3g item 7). A client configured by an
# OBJECT handed to its factory — `WebClient.create(vertx, options)` — rather than by a block:
# each rung names the factory and the argument holding the object (`options_arg`), and the
# address parts are the calls made ON that object (`setters`, each naming the `part` it
# sets). One ladder is one shape: a rung of each kind in one ladder is refused, since the
# reader of one cannot follow the other.
_OPTIONS_KEYS = {"client_arg", "ladder", "setters", "join"}
_OPTIONS_RUNG_KEYS = {"owner", "method", "options_arg", "descriptor"}
_OPTIONS_SETTER_KEYS = {"owner", "method", "descriptor", "part", "value_arg"}
# `ssl` is not a part: a peer carries no scheme, so a read of it would change nothing.
_PARTS = ("host", "port", "uri")
# Optional beside the setters: which calls on an options object CONFIGURE it — hand back that
# same object — named by the object's type and the declared return types that mean "this
# object" (an inherited setter is declared to return a supertype, CP-56 row 112). The window
# between the object's construction and its use reads them as configuring it, not as the
# object escaping (ruling 4, spec 2026-10-30).
_CONFIGURES = "configures"
_CONFIGURES_KEYS = {"owner", "returns"}
# Optional beside the setters: the framework's own value of each part an options object leaves
# unset (`{part: value}`, spec 2026-11-02 rule 5) — Vert.x's `localhost` and 80, CP-56 row 132.
# Used only on a path whose object the no-argument constructor built and every call on which
# was read; anywhere else an unset part is unknown.
_UNSET = "unset"
# Where the client sits, besides an argument index of the call executing the request: the
# RECEIVER of the chain's root call — `client.get("/q")` is called on the client itself.
CLIENT_IS_RECEIVER = "receiver"
# Optional: the default port of each scheme (`{scheme: port}`), which a call that sets its
# own scheme on the request needs to know whether Ktor writes the port (CP-54 rows 94-108).
_DEFAULT_PORTS = "default_ports"
# One call's `request_url`, what it sets on the request's URL before its address is read:
# a `scheme`, and a `port` where the call sets one too.
_REQUEST_KEYS = {"scheme", "port"}
_RUNG_KEYS = {"owner", "method", "block_arg", "descriptor", "parent"}
_SETTER_KEYS = {"owner", "method", "value_arg", "descriptor"}
# One `may_set_base` entry: an owner, optionally narrowed to a method and a descriptor, and
# optionally to a call whose argument `arg` reads the static field `field` (`{owner, name}`)
# — a plugin handed to a generic installer (`install(DefaultRequest)`, CP-54 row 92).
_MAY_SET_KEYS = {"owner", "method", "descriptor", "arg", "field"}
# A rung that DERIVES a client from another (`HttpClient.config { … }`) inherits the other's
# base where its own block sets none (CP-54 row 80). `receiver` is the one place the parent
# can be: the call is made on it.
_FROM_RECEIVER = "receiver"
_PARENTS = (_FROM_RECEIVER,)


# The interim word Task 4 shipped, folded into `client_base`: declaring where the base is set
# is what says a relative address is relative to it.
_RETIRED = "relative_to_client_base"


def client_base_of(matches: Mapping[str, Any], source: object) -> Mapping[str, Any] | None:
    """A catalog's `matches.client_base`, validated, or None where it declares none — the one
    reader every style declaring the key calls (`fluent` and `single_call`), so the refusals
    are written once. `source` names the catalog file in a refusal.

    The retired `relative_to_client_base` is refused rather than ignored, so a catalog still
    spelling it does not load as one whose relative rows read `resolved`."""
    if _RETIRED in matches:
        raise CatalogError(
            f"loading catalog {source}: `{_RETIRED}` is folded into `client_base` (D02 §2, read "
            f"by the `fluent` and `single_call` styles), which declares where the client's base "
            f"is set; declare that instead"
        )
    return _validated(matches.get("client_base"), source)


def _validated(declared: Any, source: object) -> Mapping[str, Any] | None:
    """`client_base`, refused unless every part is readable; None where it is absent."""
    if declared is None:
        return None
    where = f"loading catalog {source}: `client_base`"
    if not isinstance(declared, dict):
        raise CatalogError(f"{where} is a mapping of {sorted(_KEYS)}, got {declared!r}")
    ladder = declared.get("ladder")
    if isinstance(ladder, list) and any(
        isinstance(rung, dict) and "options_arg" in rung for rung in ladder
    ):
        return _validated_options(declared, where)
    unknown = sorted(set(declared) - _KEYS - {_DEFAULT_PORTS})
    missing = sorted(_KEYS - set(declared))
    if unknown or missing:
        raise CatalogError(
            f"{where} declares {sorted(_KEYS)}; unknown {unknown}, missing {missing}"
        )
    _index(declared["client_arg"], f"{where}'s `client_arg`")
    ladder = declared["ladder"]
    if not isinstance(ladder, list) or not ladder:
        raise CatalogError(f"{where}'s `ladder` is a non-empty list of calls, got {ladder!r}")
    for rung in ladder:
        _call(rung, _RUNG_KEYS, "block_arg", f"{where}'s `ladder` entry {rung!r}")
        if "parent" in rung and rung["parent"] not in _PARENTS:
            raise CatalogError(
                f"{where}'s `ladder` entry `{rung.get('method')}` declares `parent: "
                f"{rung['parent']!r}`; the parent a derived client inherits from is one of "
                f"{list(_PARENTS)}"
            )
    _call(declared["setter"], _SETTER_KEYS, "value_arg", f"{where}'s `setter`")
    if declared["join"] != REPLACE_LAST_SEGMENT:
        raise CatalogError(
            f"{where}'s `join` is `{REPLACE_LAST_SEGMENT}` for a ladder of block rungs (one of "
            f"{list(_JOINS)} by shape), got {declared['join']!r}"
        )
    may = declared["may_set_base"]
    if not isinstance(may, list):
        raise CatalogError(f"{where}'s `may_set_base` is a list of calls, got {may!r}")
    for entry in may:
        _may_set_entry(entry, f"{where}'s `may_set_base` entry {entry!r}")
    ports = declared.get(_DEFAULT_PORTS, {})
    if not isinstance(ports, dict) or not all(
        isinstance(scheme, str) and scheme and _is_port(port) for scheme, port in ports.items()
    ):
        raise CatalogError(
            f"{where}'s `{_DEFAULT_PORTS}` maps each scheme to its default port, got {ports!r}"
        )
    return MappingProxyType(declared)


def _validated_options(declared: dict[str, Any], where: str) -> Mapping[str, Any]:
    """An options-object `client_base`: every rung an options rung, the setters naming the part
    each sets, `fill_authority`, and the optional `configures` and `unset` — refused unless every
    part is readable."""
    unknown = sorted(set(declared) - _OPTIONS_KEYS - {_CONFIGURES, _UNSET})
    missing = sorted(_OPTIONS_KEYS - set(declared))
    if unknown or missing:
        raise CatalogError(
            f"{where} of options rungs declares {sorted(_OPTIONS_KEYS)} and optionally "
            f"`{_CONFIGURES}` and `{_UNSET}`; unknown {unknown}, missing {missing}"
        )
    if declared["client_arg"] != CLIENT_IS_RECEIVER:
        _index(declared["client_arg"], f"{where}'s `client_arg` (or `{CLIENT_IS_RECEIVER}`)")
    for rung in declared["ladder"]:
        if not isinstance(rung, dict) or "options_arg" not in rung:
            raise CatalogError(
                f"{where}'s `ladder` mixes options rungs (`options_arg`) with {rung!r}: one "
                f"ladder is one shape"
            )
        _call(rung, _OPTIONS_RUNG_KEYS, "options_arg", f"{where}'s `ladder` entry {rung!r}")
    setters = declared["setters"]
    if not isinstance(setters, list) or not setters:
        raise CatalogError(f"{where}'s `setters` is a non-empty list of calls, got {setters!r}")
    for setter in setters:
        _call(setter, _OPTIONS_SETTER_KEYS, "value_arg", f"{where}'s `setters` entry {setter!r}")
        if setter.get("part") not in _PARTS:
            raise CatalogError(
                f"{where}'s `setters` entry `{setter['method']}` declares `part: "
                f"{setter.get('part')!r}`; a part is one of {list(_PARTS)}"
            )
    if declared["join"] != FILL_AUTHORITY:
        raise CatalogError(
            f"{where}'s `join` is `{FILL_AUTHORITY}` for a ladder of options rungs, got "
            f"{declared['join']!r}"
        )
    for entry in declared.get(_CONFIGURES, ()):
        if (
            not isinstance(entry, dict)
            or set(entry) != _CONFIGURES_KEYS
            or not isinstance(entry["owner"], str)
            or not isinstance(entry["returns"], list)
            or not all(isinstance(each, str) and each for each in entry["returns"])
        ):
            raise CatalogError(
                f"{where}'s `{_CONFIGURES}` entry {entry!r} is `{{owner, returns}}`: the options "
                f"type and the declared return types that hand back that same object"
            )
    unset = declared.get(_UNSET, {})
    if not isinstance(unset, dict) or not all(
        part in _PARTS
        and (_is_port(value) if part == "port" else isinstance(value, str) and bool(value))
        for part, value in unset.items()
    ):
        raise CatalogError(
            f"{where}'s `{_UNSET}` maps a part ({list(_PARTS)}) to the framework's own value of "
            f"it — a port a port number, any other part a non-empty string — got {unset!r}"
        )
    return MappingProxyType(declared)


def request_url_of(
    row: Mapping[str, Any], declared: Mapping[str, Any] | None, where: str
) -> Mapping[str, Any] | None:
    """A call row's `request_url`, validated, or None where it declares none: what the call
    sets on its request's URL before the address is read — `ws("/chat")` the scheme `ws`,
    `wss("/chat")` the scheme `wss` and the port 443 (CP-54 rows 95-108). It means something
    only against a client base, and only where the base's `default_ports` names the scheme,
    because whether the port is written depends on the scheme's default."""
    request = row.get("request_url")
    if request is None:
        return None
    if declared is None:
        raise CatalogError(
            f"{where} declares `request_url` and its catalog no `client_base`: what a call sets "
            f"on its request only changes the address it is joined to"
        )
    ports = declared.get(_DEFAULT_PORTS, {})
    if (
        not isinstance(request, dict)
        or not set(request) <= _REQUEST_KEYS
        or not isinstance(request.get("scheme"), str)
        or ("port" in request and not _is_port(request["port"]))
    ):
        raise CatalogError(
            f"{where}'s `request_url` is `{{scheme, port?}}`, a scheme and a port, got {request!r}"
        )
    if request["scheme"] not in ports:
        raise CatalogError(
            f"{where}'s `request_url` scheme `{request['scheme']}` has no default port in the "
            f"client base's `{_DEFAULT_PORTS}` ({sorted(ports)})"
        )
    return MappingProxyType(request)


def _is_port(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 0 < value < 65536


def _may_set_entry(entry: Any, where: str) -> None:
    """One `may_set_base` entry: an `owner`, and optional `method`, `descriptor`, and an
    `arg`/`field` pair, each of its own type."""
    if not isinstance(entry, dict):
        raise CatalogError(f"{where} is a mapping of {sorted(_MAY_SET_KEYS)}")
    unknown = sorted(set(entry) - _MAY_SET_KEYS)
    if unknown:
        raise CatalogError(
            f"{where} declares unknown {unknown}; it may declare {sorted(_MAY_SET_KEYS)}"
        )
    if not isinstance(entry.get("owner"), str) or not entry["owner"]:
        raise CatalogError(f"{where} names no `owner`")
    for word in ("method", "descriptor"):
        if word in entry and (not isinstance(entry[word], str) or not entry[word]):
            raise CatalogError(f"{where}'s `{word}` is a non-empty string")
    if ("arg" in entry) != ("field" in entry):
        raise CatalogError(f"{where} declares `arg` and `field` together or neither")
    if "arg" in entry:
        _index(entry["arg"], f"{where}'s `arg`")
        field = entry["field"]
        if (
            not isinstance(field, dict)
            or set(field) != {"owner", "name"}
            or not all(isinstance(part, str) and part for part in field.values())
        ):
            raise CatalogError(f"{where}'s `field` is `{{owner, name}}`, got {field!r}")


def _call(entry: Any, keys: set[str], position: str, where: str) -> None:
    """One `{owner, method, <position>}` call of the key, with an optional `descriptor`."""
    if not isinstance(entry, dict):
        raise CatalogError(f"{where} is a mapping of {sorted(keys)}")
    unknown = sorted(set(entry) - keys)
    if unknown:
        raise CatalogError(f"{where} declares unknown {unknown}; it may declare {sorted(keys)}")
    for word in ("owner", "method"):
        if not isinstance(entry.get(word), str) or not entry[word]:
            raise CatalogError(f"{where} names no `{word}`")
    if "descriptor" in entry and not isinstance(entry["descriptor"], str):
        raise CatalogError(f"{where}'s `descriptor` is a method descriptor string")
    if position not in entry:
        raise CatalogError(f"{where} names no `{position}`")
    _index(entry[position], f"{where}'s `{position}`")


def _index(value: Any, where: str) -> None:
    """An argument position: a non-negative integer, and not a boolean (Python counts one
    as an integer)."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise CatalogError(f"{where} is an argument index, a non-negative integer, got {value!r}")


# Where a client's base cannot be read although the code that sets it is reached: a setter
# handed a value the code computes, a block the ladder does not declare, a relative setter
# (not modelled, CP-54 row 86). The same word `metadata.KNOWN_GAPS` publishes for the class.
UNTRACED = "computed_base_addresses_not_traced"
# Where an engine stamps the position it READ an argument at, `(caller, ordinal, slot)` —
# the key `chains._captured_at` writes, and what the walk names a position by.
_READ_AT = "captured_at"

# The base each construction answers, per workspace for one resolve: `N` calls on one client
# read its construction once. Keyed on the workspace weakly, as `values._INDEX_BY_WORKSPACE`
# is, and tied to the value index it was computed against — a new resolve builds a new index,
# so a stale entry is never read. Inside, keyed on the ladder declared (two catalogs may
# declare two) and the construction's `(caller, ordinal)`.
_Answers = dict[tuple[str, str, int], tuple[str | None, str | None]]
_BUILT: "WeakKeyDictionary[Workspace, tuple[ValueIndex, _Answers]]" = WeakKeyDictionary()


def client_base(
    workspace: Workspace,
    values: ValueIndex | None,
    client_value: Mapping[str, Any],
    declared: Mapping[str, Any],
) -> tuple[str | None, str | None]:
    """The base the client in `client_value` sends a relative address to, as `(base,
    None)`, or `(None, reason)` where it cannot be read.

    `client_value` is the client argument of the call that issues the request, and **the
    caller must stamp where it read it**: `captured_at`, `(caller, ordinal, slot)`, the
    position the walk starts from. `fluent` stamps it with `_captured_at`; a `single_call`
    catalog whose client is argument 0 of the call site passes
    `{**argument, "captured_at": (site["caller"], site["ordinal"], 0)}`. An argument with no
    stamp answers `not_readable`. `declared` is the catalog's `client_base`. The client's
    construction is found by the value walk's producer reader, with every ladder rung
    declared as a stop, and read like this:

    - **a rung's block is read for the base** — the setter called in it, or in the block of
      a rung called in it, in order; the LAST absolute address wins (CP-54 row 85), and a
      relative one declines the block (row 86, not modelled);
    - **a derived client (`parent: receiver`) whose block sets none inherits** its
      receiver's base (row 80), the receiver walked the same way;
    - **a construction reached with no declared setter reached gives NO base**
      (`UNTRACED`), exactly as an unreached one does. Ktor sends such a client's relative
      call to its builder's origin, `http://localhost` (rows 50, 57), but that the client
      has no base cannot be proven from the bytecode: the set of forms that set one —
      `install(DefaultRequest)`, a caller-supplied `block()`, a helper the block calls — is
      open. (Reversed by ruling, Task 10 fix round 2.)
    - **a base that WAS read is not silently overridden**: a block declines where it holds
      a call matching a rung or the setter on owner and name under another descriptor, any
      other call on the setter's owner type, a call the catalog lists in `may_set_base`
      (`install(DefaultRequest) { … }`, row 92), or a call handing its receiver to a method
      of this module whose body is not followed (`configure(this)`).

    A base may be a configuration expression (`${pricing.url}`): the setter's value
    resolves to text carrying a `${…}` key. It is answered as it is, and the caller
    renders it as the configuration convention does, never joining it — Ktor's join
    depends on whether the base ends in `/`, which the key does not say.

    A setter handed anything but a string literal is resolved by the walk at the setter —
    a captured parameter of the method that built the client crosses to that method's
    callers. The producer records no path, so where those callers hand in DIFFERENT bases
    nothing says which one this client was built with: every path must agree, and where
    they do not the answer is `non_enumerable` rather than a pairing across paths (ruling
    M-1). Every other end is the walk's own reason, or `UNTRACED` where the code setting
    the base is reached and not read.
    """
    if values is None:
        return None, NOT_READABLE
    read_at = client_value.get(_READ_AT)
    if read_at is None:
        return None, NOT_READABLE
    caller, ordinal, slot = read_at
    site = values.sites.get((str(caller), int(str(ordinal))))
    if site is None:
        return None, NOT_READABLE
    held = _BUILT.get(workspace)
    if held is None or held[0] is not values:
        held = (values, {})
        _BUILT[workspace] = held
    return _Ladder(workspace, values, declared, held[1]).base_of(site, slot, ())


class _Ladder:
    """One reading of a catalog's `client_base` ladder over one workspace's facts."""

    def __init__(
        self,
        workspace: Workspace,
        values: ValueIndex,
        declared: Mapping[str, Any],
        built: _Answers,
    ) -> None:
        self._workspace = workspace
        self._built = built
        self._ladder_key = json.dumps(dict(declared), sort_keys=True, default=str)
        self._values = values
        self._by_caller = workspace.once(call_site_index).by_caller
        self._rungs = [
            {**rung, "owner": type_descriptor(str(rung["owner"]))} for rung in declared["ladder"]
        ]
        setter = declared["setter"]
        self._setter = {**setter, "owner": type_descriptor(str(setter["owner"]))}
        self._may_set = [
            {
                **entry,
                "owner": type_descriptor(str(entry["owner"])),
                **(
                    {
                        "fields": {
                            (
                                type_descriptor(str(entry["field"]["owner"])),
                                str(entry["field"]["name"]),
                            ): "declared"
                        }
                    }
                    if "field" in entry
                    else {}
                ),
            }
            for entry in declared["may_set_base"]
        ]
        self._stops = frozenset((rung["owner"], str(rung["method"])) for rung in self._rungs)

    def base_of(
        self, site: Mapping[str, Any], slot: int | str, seen: tuple[tuple[str, int], ...]
    ) -> tuple[str | None, str | None]:
        """The base of the client at `slot` of `site`: one per path the producer reader
        finds, and only where every path agrees."""
        bases: list[str] = []
        for producer in producers_of(self._values, site, slot, self._stops):
            if producer.caller is None or producer.ordinal is None:
                return None, producer.reason or NOT_READABLE
            built = (producer.caller, producer.ordinal)
            if built in seen:
                return None, CYCLE
            base, reason = self._built_by(built, (*seen, built))
            if base is None:
                return None, reason
            bases.append(base)
        distinct = list(dict.fromkeys(bases))
        if not distinct:
            return None, NOT_READABLE
        if len(distinct) > 1:
            return None, NON_ENUMERABLE
        return distinct[0], None

    def _built_by(
        self, built: tuple[str, int], seen: tuple[tuple[str, int], ...]
    ) -> tuple[str | None, str | None]:
        """The base of the client one declared call built, read once per construction per
        resolve (`_BUILT`). A `cycle` answer depends on the path that met it, so it is not
        kept."""
        key = (self._ladder_key, *built)
        held = self._built.get(key)
        if held is not None:
            return held
        answer = self._read_construction(built, seen)
        if answer[1] != CYCLE:
            self._built[key] = answer
        return answer

    def _read_construction(
        self, built: tuple[str, int], seen: tuple[tuple[str, int], ...]
    ) -> tuple[str | None, str | None]:
        site = self._values.sites[built]
        rung = self._rung_of(site)
        if rung is None:
            # The declared owner and method under an overload no rung declares: the call is
            # reached, and what its block means is not measured.
            return None, UNTRACED
        base, reason = self._block_base(site, rung)
        if reason is not None:
            return None, reason
        if base is not None:
            return base, None
        if rung.get("parent") == _FROM_RECEIVER:
            return self.base_of(site, RECEIVER, seen)
        # No declared setter was reached. Not "no base": absence cannot be proven from the
        # bytecode, so the base is unread, as for an unreached construction.
        return None, UNTRACED

    def _block_base(
        self, site: Mapping[str, Any], rung: Mapping[str, Any]
    ) -> tuple[str | None, str | None]:
        """What `rung`'s block at `site` sets the base to: `(base, None)`, `(None, None)`
        where it sets none, or `(None, reason)` where it cannot be read."""
        arguments = site["arguments"] or []
        position = int(rung["block_arg"])
        block = arguments[position] if position < len(arguments) else None
        if not isinstance(block, Mapping) or block.get("kind") != "lambda":
            return None, UNTRACED
        body = with_descriptor(str(site["caller"]), str(block.get("symbol")))
        # The block's own receiver: the body's parameter after the values it captured
        # (`CallArgument.captures`, D00 §5).
        receiver = int(str(block.get("captures") or 0))
        base: str | None = None
        for inner in self._by_caller.get(body, []):
            if _matches(inner, self._setter):
                address, reason = self._setter_value(inner)
                if address is None or not (_has_host(address) or carries_expression(address)):
                    return None, reason or UNTRACED
                base = address
                continue
            if self._may_move_base(inner) or self._hands_off(inner, receiver):
                return None, UNTRACED
            if _hands_to_supplied_code(inner, receiver):
                return None, UNTRACED
            nested = self._rung_of(inner)
            if nested is None or nested.get("parent") is not None:
                continue
            set_there, reason = self._block_base(inner, nested)
            if reason is not None:
                return None, reason
            if set_there is not None:
                base = set_there
        return base, None

    def _setter_value(self, site: Mapping[str, Any]) -> tuple[str | None, str | None]:
        """The string the setter at `site` is handed: the literal, or the one value every
        path of the walk agrees on there."""
        slot = int(self._setter["value_arg"])
        answers = [
            reached["value"]
            for reached in resolve_positions(self._workspace, {"value": (site, slot)}, self._values)
        ]
        texts: list[str] = []
        for answer in answers:
            if answer.kind == UNRESOLVED:
                return None, answer.reason or NOT_READABLE
            # A string the code states, or a configuration expression carrying a `${…}` key;
            # an assembled value with no key (`https://{}/`) is not read.
            stated = answer.kind == LITERAL and answer.literal_kind == STRING
            keyed = answer.kind == EXPRESSION and carries_expression(str(answer.value))
            if not (stated or keyed):
                return None, UNTRACED
            texts.append(str(answer.value))
        distinct = list(dict.fromkeys(texts))
        if not distinct:
            return None, NOT_READABLE
        if len(distinct) > 1:
            return None, NON_ENUMERABLE
        return distinct[0], None

    def _rung_of(self, site: Mapping[str, Any]) -> Mapping[str, Any] | None:
        return next((rung for rung in self._rungs if _matches(site, rung)), None)

    def _hands_off(self, site: Mapping[str, Any], receiver: int) -> bool:
        """Whether `site` hands the block's receiver to a method of THIS module —
        `configure(this)` — whose body is scanned and not followed here, so it may set the
        base. "Of this module" is the walk's own test: a site whose callee `call_edges`
        resolved, `ValueIndex.reached`. A library call handed the receiver (the compiler's
        null check on it, `install$default(config, WebSockets)`) is not this question:
        library knowledge is catalog data, `may_set_base`. A rung is not asked."""
        if self._rung_of(site) is not None:
            return False
        if (str(site["caller"]), int(str(site["ordinal"]))) not in self._values.reached:
            return False
        return _hands_receiver(site, receiver)

    def _may_move_base(self, site: Mapping[str, Any]) -> bool:
        """A call in a reached block that may set the base although it is not the declared
        setter or a declared rung — so the block's silence is not "no base":
        - a rung or the setter's owner and name under another descriptor (Ktor's
          `url { … }`, `defaultRequest(replace = true) { … }`, rows 46, 48);
        - any other call on the setter's owner type (`host = …`, `url.takeFrom(…)`);
        - a call `may_set_base` lists (`install(DefaultRequest) { … }`, row 92)."""
        if self._rung_of(site) is not None:
            return False
        if any(_same_name(site, call) for call in (*self._rungs, self._setter)):
            return True
        if site.get("owner") == self._setter["owner"]:
            return True
        return any(_listed(site, entry) for entry in self._may_set)


# The invoke kinds made on no value: a static call, and an `invokedynamic` (a lambda or a
# concatenation being built, D00 §5) — neither runs another object's method.
_NOT_ON_A_VALUE = ("static", "dynamic")


def _hands_to_supplied_code(site: Mapping[str, Any], receiver: int) -> bool:
    """Whether `site` hands the block's receiver to code the walk cannot see: an INSTANCE
    call made on any value other than the receiver itself — a captured value, another
    parameter, a field read, a local. `block()` in `HttpClient(CIO) { defaultRequest { … };
    block() }` is `invoke(block, receiver)` on the caller's `block`, wherever it is held, and
    what that does is code the walk never sees; it may replace the base. A static call is
    made on no value at all (the compiler's null check on the receiver, `install$default(
    config, …)`), so it is not this question; nor is a call made ON the receiver, which is the
    library's own method on its own object; and a call not handed the receiver cannot
    configure it."""
    if site.get("invoke_kind") in _NOT_ON_A_VALUE:
        return False
    on = site.get("receiver_parameter")
    if on is not None and int(str(on)) == receiver:
        return False
    return _hands_receiver(site, receiver)


def _hands_receiver(site: Mapping[str, Any], receiver: int) -> bool:
    """Whether one of `site`'s arguments is the block's receiver parameter."""
    return any(
        isinstance(argument, Mapping)
        and argument.get("kind") == "parameter"
        and argument.get("value") == receiver
        for argument in site["arguments"] or []
    )


def _matches(site: Mapping[str, Any], call: Mapping[str, Any]) -> bool:
    """`site` is the declared call: owner and method, and the descriptor where one is
    declared."""
    return (
        site.get("owner") == call["owner"]
        and site.get("name") == call["method"]
        and ("descriptor" not in call or site.get("descriptor") == call["descriptor"])
    )


def _same_name(site: Mapping[str, Any], call: Mapping[str, Any]) -> bool:
    return bool(site.get("owner") == call["owner"] and site.get("name") == call["method"])


def _listed(site: Mapping[str, Any], entry: Mapping[str, Any]) -> bool:
    """`site` is the `may_set_base` entry's call: its owner, and its method, descriptor and
    field argument where the entry names them."""
    if site.get("owner") != entry["owner"]:
        return False
    if "method" in entry and site.get("name") != entry["method"]:
        return False
    if "descriptor" in entry and site.get("descriptor") != entry["descriptor"]:
        return False
    if "fields" not in entry:
        return True
    arguments = site["arguments"] or []
    position = int(entry["arg"])
    argument = arguments[position] if position < len(arguments) else None
    return static_field_value(argument, entry["fields"]) is not None


def _has_host(address: str) -> bool:
    """An absolute address: a scheme and a host, which is what replaces a base (CP-54
    rows 55, 85) where a relative one would be resolved against it (row 86)."""
    split = urlsplit(address)
    return bool(split.scheme) and bool(split.hostname)


# What an options object sets on ONE path, part by part (`host`, `port`, `uri`): the text a
# setter was handed, or `None` where the part was set with a value not read here or is not
# known on that path. A part ABSENT is proven unset on that path (spec 2026-11-02 rule 5): the
# object was built by the no-argument constructor and every call on it was read.
Parts = Mapping[str, str | None]
# The parts the options reader's rows SHOW (the user's ruling of 2026-11-03, option A, as
# `fluent.PUBLISHED_PARTS` states its own): a call on a branch that sets none of them is no
# split for the several-splits rule. Each is read into the row: `host` and `port` the peer,
# `uri` the path. `tests/architecture/test_published_parts_are_complete.py` holds every part a
# client model's setter declares to this set.
PUBLISHED_PARTS = frozenset({"host", "port", "uri"})
# One reader per declared ladder per workspace for one resolve, tied to the value index it
# reads, as `_BUILT` is: the calls that configure an options object are read off the module
# once, and each options object's paths once, however many requests its client sends.
_READERS: "WeakKeyDictionary[Workspace, tuple[ValueIndex, dict[str, _Options]]]" = (
    WeakKeyDictionary()
)


@dataclass(frozen=True)
class PathParts:
    """What one path through an options object (or a client's factory and its options) sets
    (spec 2026-11-02 rule 4): `parts` as `Parts` says, and whether the path is exact — False
    where rule 9 makes it inexact (a side of a split no fact proves, several splits setting a
    published part) or a branch was passed through, so a row read off it is no surer than
    `partial`."""

    parts: Parts
    exact: bool = True

    def __hash__(self) -> int:
        return hash((tuple(sorted(self.parts.items())), self.exact))


def client_defaults(
    workspace: Workspace,
    values: ValueIndex | None,
    client_value: Mapping[str, Any],
    declared: Mapping[str, Any],
    within: Path | None = None,
) -> tuple[PathParts, ...]:
    """The defaults the client in `client_value` fills into a request, ONE per path (spec
    2026-11-02 rules 4-5), read off the options object its factory was handed (an options-object
    `client_base`, Vert.x spec §3d). Never merged: two paths that differ are two answers.

    `client_value` is stamped as `client_base` says (`captured_at`); `within` is the path the
    request was read on, which every answer agrees with. The client is found by the producer
    reader with every rung a stop, as the block ladder's is; the rung's `options_arg` is then
    read per path (`_Options.paths_of`). On each path a part is the text read, None where it was
    set and not read or is not known, and the framework's own default (`unset`, the client
    model's) where it is proven unset. A client not reached, a factory under an overload no
    rung declares, and an options object not read are every part unknown. Every part is
    present in every answer."""
    reader = _options_reader(workspace, values, declared)
    site, slot = (None, 0) if reader is None else reader.position(client_value)
    if reader is None or site is None:
        return (PathParts(_UNKNOWN),)
    return reader.defaults_of(site, slot, within)


def options_parts(
    workspace: Workspace,
    values: ValueIndex | None,
    options_value: Mapping[str, Any],
    declared: Mapping[str, Any],
    within: Path | None = None,
) -> tuple[PathParts, ...]:
    """What the options object in `options_value` sets, ONE per path — the reader
    `client_defaults` reads a client's options with, for an options object a REQUEST is made from
    (Vert.x's `request(m, RequestOptions)`). Stamped as `client_base` says. A part proven unset is
    absent (the request then takes the client's), so no framework default is applied here; an
    object not read is every part unknown."""
    reader = _options_reader(workspace, values, declared)
    site, slot = (None, 0) if reader is None else reader.position(options_value)
    if reader is None or site is None:
        return (PathParts(_UNKNOWN),)
    return tuple(
        dict.fromkeys(
            PathParts(read.parts if read.proven else {**_UNKNOWN, **read.parts}, read.exact)
            for read, path in reader.paths_of(site, slot)
            if within is None or path.joined(within) is not None
        )
    ) or (PathParts(_UNKNOWN),)


# Every part not known: an options object, a client or a factory the reader cannot read.
_UNKNOWN: Parts = MappingProxyType(dict.fromkeys(_PARTS))


@dataclass(frozen=True)
class _Read:
    """One path's reading of an options object: the parts its setters set, whether a part no
    setter set is proven unset (`proven`: the no-argument constructor built it and every call on
    it was read), and whether the path is exact."""

    parts: Parts
    proven: bool
    exact: bool

    def __hash__(self) -> int:
        return hash((tuple(sorted(self.parts.items())), self.proven, self.exact))


def _options_reader(
    workspace: Workspace, values: ValueIndex | None, declared: Mapping[str, Any]
) -> "_Options | None":
    if values is None or "setters" not in declared:
        return None
    held = _READERS.get(workspace)
    if held is None or held[0] is not values:
        held = (values, {})
        _READERS[workspace] = held
    key = json.dumps(dict(declared), sort_keys=True, default=str)
    if key not in held[1]:
        held[1][key] = _Options(workspace, values, declared)
    return held[1][key]


class _Options:
    """One reading of an options-object `client_base` over one workspace's facts."""

    def __init__(
        self,
        workspace: Workspace,
        values: ValueIndex,
        declared: Mapping[str, Any],
    ) -> None:
        self._workspace = workspace
        self._values = values
        self._read: dict[tuple[str, int, int | str], tuple[tuple[_Read, Path], ...]] = {}
        self._rungs = [
            {**rung, "owner": type_descriptor(str(rung["owner"]))} for rung in declared["ladder"]
        ]
        self._setters = [
            {**setter, "owner": type_descriptor(str(setter["owner"]))}
            for setter in declared["setters"]
        ]
        # The framework's own value of each part an options object leaves unset (rule 5).
        self._unset = {str(part): str(value) for part, value in declared.get(_UNSET, {}).items()}
        self._stops = frozenset((rung["owner"], str(rung["method"])) for rung in self._rungs)
        owners = {setter["owner"] for setter in self._setters}
        returns = {
            type_descriptor(str(entry["owner"])): {
                type_descriptor(str(each)) for each in entry["returns"]
            }
            for entry in declared.get(_CONFIGURES, ())
        }
        owners |= set(returns)
        self._owners = frozenset(owners)
        # The methods that make a call on an options type THROUGH A FIELD (`receiver_field`):
        # the field may hold the object a chain in that method built, and D00 §5 records no
        # store from a local (`this.held = o; this.held.setDefaultPort(5)`), so the walk cannot
        # rule it out (item 2 review, C1). One pass over the call sites.
        self._configured_through_fields = frozenset(
            str(site["caller"])
            for site in values.sites.values()
            if site.get("receiver_field") and str(site.get("owner")) in owners
        )
        # The calls that configure an options object, as the walk names one — `(owner, name,
        # descriptor)` exactly — read off the module's own calls: a setter, and every call on an
        # options type returning a type `configures` says is that same object. Once per reading,
        # one pass over the call sites (GUIDELINES §8.7).
        self._configuring = frozenset(
            (str(site["owner"]), str(site["name"]), str(site["descriptor"]))
            for site in values.sites.values()
            if site.get("descriptor")
            and (
                any(_matches(site, setter) for setter in self._setters)
                or returned_type(str(site["descriptor"])) in returns.get(str(site["owner"]), ())
            )
        )
        # The chain reader stops at, and walks through, each of those calls and the options
        # types' constructors, so it answers the whole chain that built the object.
        self._chain = frozenset(
            {(owner, name) for owner, name, _ in self._configuring}
            | {(owner, "<init>") for owner in owners}
        )

    def position(self, value: Mapping[str, Any]) -> tuple[Mapping[str, Any] | None, int | str]:
        read_at = value.get(_READ_AT)
        if read_at is None:
            return None, 0
        caller, ordinal, slot = read_at
        return self._values.sites.get((str(caller), int(str(ordinal)))), slot

    def defaults_of(
        self, site: Mapping[str, Any], slot: int | str, within: Path | None = None
    ) -> tuple[PathParts, ...]:
        """The defaults of the client at `slot` of `site`, one per path (rule 4): each factory
        call reaching it, and each path through the options that factory was handed that agrees
        with the path to the factory (and with `within`). A part proven unset takes the
        framework's own value (`unset`, rule 5); a factory the reader cannot read is every part
        unknown on its path."""
        found: list[PathParts] = []
        # WHICH factory made the client is the question, so the calls made on it in between
        # — every request it sends, `client.get(…)` — do not make it another client
        # (`which_object`, the object reader's switch): a client used twice in one method is
        # still the one its factory built.
        for producer, path in producer_paths(
            self._values, site, slot, self._stops, which_object=True
        ):
            if within is not None and path.joined(within) is None:
                continue
            exact = not producer.inexact and not inexact(path)
            built = (
                None
                if producer.caller is None or producer.ordinal is None
                else self._values.sites[(producer.caller, producer.ordinal)]
            )
            rung = (
                None
                if built is None
                else next((r for r in self._rungs if _matches(built, r)), None)
            )
            # The factory under an overload no rung declares: what it does with its arguments
            # is not measured, so every part is unknown on this path — as for a client the walk
            # did not reach.
            reads = (
                []
                if built is None or rung is None
                else [
                    read
                    for read, options_path in self.paths_of(built, int(rung["options_arg"]))
                    if options_path.joined(path) is not None
                ]
            )
            if not reads:
                found.append(PathParts(_UNKNOWN, exact))
                continue
            found.extend(
                PathParts(
                    {
                        part: read.parts[part]
                        if part in read.parts
                        else self._unset.get(part)
                        if read.proven
                        else None
                        for part in _PARTS
                    },
                    exact and read.exact,
                )
                for read in reads
            )
        return tuple(dict.fromkeys(found)) or (PathParts(_UNKNOWN),)

    def paths_of(self, site: Mapping[str, Any], slot: int | str) -> tuple[tuple[_Read, Path], ...]:
        """What the setters made on the options object at `slot` of `site` set, ONE per path to
        its construction (rule 4), with the path — read once per position per resolve
        (`_READERS`): each path's chain of calls in run order, the last call to a part winning,
        each setter's argument read on that path (`_value`). A path that ends anywhere but a
        chain rooted at a construction — `escapes`, an unrooted chain, a parameter nothing
        binds — is every part unknown (rule 2)."""
        key = (str(site["caller"]), int(str(site["ordinal"])), slot)
        if key in self._read:
            return self._read[key]
        found: list[tuple[_Read, Path]] = []
        for producer, path in producer_paths(
            self._values,
            site,
            slot,
            self._chain,
            along_receivers=True,
            configuring=self._configuring,
            counting=self._counts,
        ):
            exact = not producer.inexact and not inexact(path)
            # An object stored in a field (rule 2; item 2 review, C1): once there anything can
            # change it — a call through the field, here or in another method — and the walk
            # reads none of those calls on the object it reaches, so nothing about it is known.
            if not producer.rooted or not producer.chain or self._stored(producer.chain):
                found.append((_Read(_UNKNOWN, False, exact), path))
                continue
            parts: dict[str, str | None] = {}
            for caller, ordinal in producer.chain:
                call = self._values.sites[(caller, ordinal)]
                setter = next((one for one in self._setters if _matches(call, one)), None)
                if setter is not None:
                    parts[str(setter["part"])] = self._value(call, int(setter["value_arg"]), path)
            found.append((_Read(parts, self._built_bare(producer.chain[0]), exact), path))
        read = tuple(dict.fromkeys(found))
        self._read[key] = read
        return read

    def _stored(self, chain: tuple[tuple[str, int], ...]) -> bool:
        """Whether the object a chain built may be held in a field, where anything can change it
        (`ValueIndex.stored`, `stored_parameters`: "once in a field, anything can change it"):
        the value a construction made or a call of the chain handed back was stored, or a
        parameter a call of the chain is made on was; or a method of the chain configures an object
        of the options type through a field (`_configured_through_fields`), which may be this
        one."""
        for caller, ordinal in chain:
            if caller in self._configured_through_fields:
                return True
            row = self._values.sites[(caller, ordinal)]
            made = row.get("receiver") if row.get("name") == "<init>" else row.get("result")
            if made is not None and (caller, int(str(made))) in self._values.stored:
                return True
            on = row.get("receiver_parameter")
            if on is not None and (caller, int(str(on))) in self._values.stored_parameters:
                return True
        return False

    def _built_bare(self, root: tuple[str, int]) -> bool:
        """Whether a chain's first call is an options type's NO-ARGUMENT constructor (rule 5):
        only then does a part no later call sets hold the framework's own default. A constructor
        handed anything (`new WebClientOptions(json)`, a copy) sets what it is handed."""
        row = self._values.sites[root]
        return (
            row.get("name") == "<init>"
            and row.get("descriptor") == "()V"
            and row.get("owner") in self._owners
        )

    def _counts(self, method: str, ordinal: int) -> bool:
        """Whether a call this reader gathered sets a part its rows publish (`PUBLISHED_PARTS`):
        a split on a call that sets none (`setSsl`) is no split for the several-splits rule."""
        call = self._values.sites.get((method, ordinal))
        return call is not None and any(
            _matches(call, setter) and setter["part"] in PUBLISHED_PARTS for setter in self._setters
        )

    def _value(self, site: Mapping[str, Any], slot: int, path: Path) -> str | None:
        """The text a setter was handed on `path`, traced by the value walk: a string or integer
        literal, or a configuration expression; None where the path gives anything else or
        several values (rule 6: pairing two setters' candidates would publish combinations no
        path makes). A setter gathered inside a body a hand-off entered reads a parameter of
        that body at the call that entered it on this path (`entered_position`), so a helper
        called by two callers sets each caller's own value (item 1's review, concern 6)."""
        texts: set[str] = set()
        caller, ordinal = str(site["caller"]), int(str(site["ordinal"]))
        for entered in path.entered_into(caller, ordinal) or ((),):
            at, at_slot = entered_position(self._values, site, slot, entered)
            for reached in resolve_positions(
                self._workspace, {"value": (at, at_slot)}, self._values, within=path
            ):
                answer = reached["value"]
                stated = answer.kind == LITERAL and answer.literal_kind in (STRING, INT)
                keyed = answer.kind == EXPRESSION and carries_expression(str(answer.value))
                if answer.narrowed or answer.inexact or not (stated or keyed):
                    return None
                texts.add(str(answer.value))
        return texts.pop() if len(texts) == 1 else None


def against_client_base(
    workspace: Workspace | None,
    values: ValueIndex | None,
    client_value: Mapping[str, Any] | None,
    declared: Mapping[str, Any],
    address: str,
    request: Mapping[str, Any] | None = None,
    path_only: bool = False,
) -> tuple[str, str]:
    """What `address`, read in full as the code states it, is sent to by a client that may
    hold a base: `(address, resolution)`, for the caller to render in its own row shape.

    `path_only` says the text is a PATH handed to the request as it stands — the parts form,
    `ws(path = …)`, whose `path` Ktor gives `URLBuilder.setEncodedPath` and never parses
    (CP-54 rows 124-134). It is then never an absolute address, and a path carrying `?` or
    `#` is kept, `unresolved`: Ktor writes it as it stands, and what an engine makes of that
    text and how a base's own query follows it is not measured.

    - **an absolute address is the whole address** (CP-54 rows 55, 110-112, 119), `resolved`;
    - **a relative one joins the base** of `client_value` (`client_base`, stamped as it says)
      by the catalog's `join`, under the call's `request` where it sets one, `resolved`;
    - **a configuration base** (`${pricing.url}`) is carried, `base + address` as written, at
      `partial` and never joined — the join depends on whether the deployed value ends in
      `/`, which the key does not say;
    - **otherwise the address is a path, not the URL called**: no base is read (the client is
      not reached, or no setter is) or the join declines, so it is kept, `unresolved`.
    """
    if path_only and _marks_query_or_fragment(address):
        return address, str(Resolution.UNRESOLVED)
    if not path_only and _has_host(address):
        return address, str(Resolution.RESOLVED)
    base = None
    if client_value is not None and workspace is not None:
        base, _ = client_base(workspace, values, client_value, declared)
    if base is not None and carries_expression(base):
        return base + address, str(Resolution.PARTIAL)
    joined = (
        None
        if base is None
        else join_url(
            base,
            address,
            str(declared["join"]),
            request,
            declared.get(_DEFAULT_PORTS),
            path_only,
        )
    )
    if joined is None:
        return address, str(Resolution.UNRESOLVED)
    return joined, str(Resolution.RESOLVED)


def join_url(
    base: str,
    relative: str,
    rule: str,
    request: Mapping[str, Any] | None = None,
    default_ports: Mapping[str, int] | None = None,
    path_only: bool = False,
) -> str | None:
    """`relative` sent from a client whose base is `base`, under the framework's `rule` — or
    None where the join DECLINES: the address is one whose result is not modelled, and the
    caller keeps it unresolved rather than publishing a string the framework never sends.

    Only `replace_last_segment` exists. Ktor sends a client with no base to its request
    builder's origin, `http://localhost` (CP-54 rows 50, 57), and this join with that origin
    as the base gives the same URL — but the reader never assumes that a client has none.

    `request` is what the CALL sets on its request's URL before the address is read (a
    WebSocket call's scheme, and its port where it sets one, `request_url` on its row), and
    `default_ports` the scheme's default port each is rendered against: see
    `_with_request_scheme`. `path_only` reads `relative` as a path handed over as it stands,
    never parsed as an address: see `_path_onto`."""
    if rule != REPLACE_LAST_SEGMENT:
        raise ValueError(f"no join rule {rule!r}; the rules are {list(_JOINS)}")
    if request is None:
        if path_only:
            return _path_onto(base, relative)
        return _replace_last_segment(base, relative)
    return _with_request_scheme(base, relative, request, default_ports or {}, path_only)


def _with_request_scheme(
    base: str,
    relative: str,
    request: Mapping[str, Any],
    ports: Mapping[str, int],
    path_only: bool = False,
) -> str | None:
    """The join for a call that sets its own scheme on the request before its address is
    read, as Ktor 3.6.0 sends it (CP-54 rows 61-62, 94-113; `ktor-client-core`'s
    `websocket.BuildersKt` lambdas set the protocol, and `wss("…")` and `webSocketSession`
    the port, then `DefaultRequest$Plugin.mergeUrls` keeps the request's protocol, and its
    port where one is set, over the base's — bytecode 50-72):

    - **the path and query are the `DefaultRequest` join's** (rows 99, 104), `_replace_last_segment`;
    - **the scheme is the call's** (rows 95-98);
    - **the port is the call's where it sets one, else the base's** — the base's own, or its
      scheme's default — and written only where it differs from the CALL's scheme's default
      (row 94): `ws` over `https://h/` is `ws://h:443/…` (rows 61, 95), `wss("…")` over
      `https://h:8443/` is `wss://h/…` (row 101), `wss(path = …)` over `http://h/` is
      `wss://h:80/…` (row 106);
    - **an absolute address is sent as written** (rows 110-112), whatever scheme the call sets;
    - **declined**: a protocol-relative address (it takes the call's scheme, row 113, measured
      for `ws` alone), a scheme with no host (as for the HTTP join), a base carrying user info,
      and a scheme the port table does not name.
    """
    if path_only:
        joined = _path_onto(base, relative)
    else:
        scheme, refused = _scheme_of(relative)
        if refused:
            return None
        if scheme is not None:
            return relative if _has_host(relative) else None
        if len(relative) - len(relative.lstrip("/")) >= 2:
            return None
        joined = _replace_last_segment(base, relative)
    origin = urlsplit(base)
    if joined is None or "@" in origin.netloc:
        return None
    try:
        stated = origin.port
    except ValueError:
        return None
    base_port = stated if stated is not None else ports.get(origin.scheme)
    called = str(request["scheme"])
    default = ports.get(called)
    if base_port is None or default is None:
        return None
    port = int(request.get("port", base_port))
    host = origin.netloc if stated is None else origin.netloc[: origin.netloc.rfind(":")]
    sent = urlsplit(joined)
    authority = host if port == default else f"{host}:{port}"
    return urlunsplit((called, authority, sent.path, sent.query, sent.fragment))


def _path_onto(base: str, path: str) -> str | None:
    """`path` joined onto `base` where it is a PATH handed to the request as it stands — Ktor's
    parts form, `url(scheme, host, port, path)`, which calls `URLBuilderKt.set` and so
    `setEncodedPath(path)`, never `takeFrom` (CP-54 rows 124-134). Nothing in the text is
    parsed: it is split on `/` into segments as `setEncodedPath` splits it, and those join the
    base's by `concatenatePath`, as a relative address's do. So `//x/y` is the path `//x/y` on
    the base's host (rows 124, 129), not an authority; a whole URL replaces the base's last
    segment like any path without a leading `/` (rows 125, 130); and the base's query follows
    the path (rows 133-134), the request carrying none of its own. A `?` or `#` in the text
    declines — Ktor writes it as it stands (rows 126-127, 131), and how a base's query follows
    it is not measured."""
    if _marks_query_or_fragment(path):
        return None
    origin = urlsplit(base)
    segments = _concatenate_path(_encoded_segments(origin.path), _encoded_segments(path))
    return urlunsplit(
        (origin.scheme, origin.netloc, _join_path(segments), origin.query, origin.fragment)
    )


def _marks_query_or_fragment(text: str) -> bool:
    """Whether a path the request is handed as it stands carries the mark that, in an
    address, starts a query or a fragment."""
    return any(mark in text for mark in "?#")


def _replace_last_segment(base: str, relative: str) -> str | None:
    """Ktor 3.6.0's `DefaultRequest$Plugin.mergeUrls(defaultUrl, requestUrl)`, read off the
    bytecode of `ktor-client-core` 3.6.0, with the parsing its two inputs went through
    (`ktor-http` 3.6.0's `URLParserKt.takeFromUnsafe`, `findScheme` and
    `URLBuilderKt.setEncodedPath`):

    - **the early return is on a HOST, not a scheme** (`mergeUrls` bytecode 15-38): a request
      carrying a host is left as Ktor parsed it. Here it is returned AS WRITTEN — Ktor
      re-renders it (a default port dropped, say), which is not modelled. A request carrying
      no scheme takes the base's first (0-12), so a protocol-relative `//host/x` is sent with
      the base's scheme (CP-54 row 83). Two or more leading slashes start an authority
      whatever their number (`takeFromUnsafe` 461-643), so `///x/y` is host `x` (row 84);
    - **a scheme and no host DECLINES**: `gemini-pro:generateContent` keeps its own scheme
      over the base's host, and Ktor writes the base's port explicitly because the new
      scheme's default differs — `gemini-pro://…:443/v1beta/models/generateContent` (rows
      81-82). Reproducing that needs `URLProtocol`'s default-port table, and the result is a
      URL no engine serves, so it is not published. So does a scheme `findScheme` refuses
      (an illegal character before the `:`; Ktor throws), and an authority with no host;
    - the path is `concatenatePath(base segments, request segments)` (75-91);
    - the fragment is the request's where it has one, the base's otherwise (94-124);
    - the query is the REQUEST's parameters, then each of the base's whose name the request
      does not carry (127-281) — so `?limit=5` over a base `?key=1` is `?limit=5&key=1`
      (row 59), and a name both carry keeps the request's values only.

    Not modelled: `encodeURLPath`'s percent-encoding of characters a path may not carry
    (an address as the code writes it is kept as written), user info and port in the
    REQUEST (a relative address has neither), and a trailing `?` with no parameters.
    """
    scheme, refused = _scheme_of(relative)
    if refused:
        return None
    rest = relative if scheme is None else relative[len(scheme) + 1 :]
    slashes = len(rest) - len(rest.lstrip("/"))
    if slashes >= 2:
        authority = rest[slashes:]
        if not authority or authority[0] in "/?#":
            return None
        if scheme is not None:
            return relative
        return f"{urlsplit(base).scheme}://{authority}"
    if scheme is not None:
        return None
    request = urlsplit(relative)
    origin = urlsplit(base)
    segments = _concatenate_path(
        _encoded_segments(origin.path),
        _request_segments(request.path, relative[len(request.path) : len(request.path) + 1]),
    )
    query = "&".join(_merged_parameters(_parameters(request.query), _parameters(origin.query)))
    # `urlunsplit` writes a path that does not start with `/` after one, as
    # `URLUtilsKt.appendUrlFullPath` does, and omits an empty query and fragment.
    return urlunsplit(
        (
            origin.scheme,
            origin.netloc,
            _join_path(segments),
            query,
            request.fragment or origin.fragment,
        )
    )


def _scheme_of(address: str) -> tuple[str | None, bool]:
    """`URLParserKt.findScheme`, as `(scheme, refused)`: the text before the first `:`,
    unless a `/`, `?` or the fragment's mark comes first (no scheme). A scheme starts with a
    letter and continues with letters, digits, `+`, `-` or `.`; any other character before
    the `:` makes Ktor throw `Illegal character in scheme`, answered `refused`."""
    illegal = False
    for position, character in enumerate(address):
        if character == ":":
            if illegal or position == 0:
                return None, True
            return address[:position], False
        if character in "/?#":
            return None, False
        allowed = character.isascii() and (
            character.isalpha() or (position and (character.isdigit() or character in "+-."))
        )
        illegal = illegal or not allowed
    return None, False


def _encoded_segments(path: str) -> list[str]:
    """`URLBuilderKt.setEncodedPath`, how the base's path becomes segments: blank is none,
    `/` is the root (`ROOT_PATH`, one empty segment), anything else splits on `/`."""
    if not path.strip():
        return []
    if path == "/":
        return [""]
    return path.split("/")


def _request_segments(path: str, follows: str) -> list[str]:
    """`URLParserKt.takeFromUnsafe` on a fresh request builder (no segments yet), how a
    relative address becomes segments; `follows` is the character after the path — `?`, the
    fragment's mark, or empty at the end. Called with none or one leading slash only — two
    or more start an authority (`_replace_last_segment`). One `/` roots the path (`ROOT_PATH`
    before the rest, bytecode 892-918; CP-54 row 52), none leaves it relative.
    With no path text after them, an address that ends there is the root where it is slashes
    (646-673), and one a query or fragment follows is the root only for a `?` with no slash
    before it (943-989).
    """
    slashes = len(path) - len(path.lstrip("/"))
    rest = path[slashes:]
    if not rest:
        if not follows:
            return [""] if slashes else []
        return [""] if not slashes and follows == "?" else []
    return ([""] if slashes == 1 else []) + rest.split("/")


def _concatenate_path(parent: list[str], child: list[str]) -> list[str]:
    """`DefaultRequest$Plugin.concatenatePath(parent, child)`: no child keeps the parent, no
    parent takes the child, a child whose first segment is empty (it started with `/`) is
    the whole path, and otherwise the parent's LAST segment is dropped and the child takes
    its place — which is why a base without a trailing `/` loses its last segment (row 53)
    and one with it keeps every directory (rows 51, 60)."""
    if not child:
        return parent
    if not parent:
        return child
    if child[0] == "":
        return child
    return parent[:-1] + child


def _join_path(segments: list[str]) -> str:
    """`URLBuilderKt.joinPath`: none is blank, one empty segment is `/`, one segment is
    itself, more are joined by `/`."""
    if not segments:
        return ""
    if len(segments) == 1:
        return "/" if segments[0] == "" else segments[0]
    return "/".join(segments)


def _parameters(query: str) -> dict[str, list[str]]:
    """A query's parameters by name, in first-appearance order, each keeping its own text:
    Ktor's `ParametersBuilder` groups the values of one name together."""
    grouped: dict[str, list[str]] = {}
    for item in query.split("&"):
        if item:
            grouped.setdefault(item.partition("=")[0], []).append(item)
    return grouped


def _merged_parameters(request: dict[str, list[str]], base: dict[str, list[str]]) -> list[str]:
    """`mergeUrls` bytecode 127-281: the request's parameters, then each of the base's whose
    name the request does not carry."""
    merged = [item for items in request.values() for item in items]
    for name, items in base.items():
        if name not in request:
            merged.extend(items)
    return merged
