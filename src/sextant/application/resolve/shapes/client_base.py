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
    LITERAL,
    NON_ENUMERABLE,
    NOT_READABLE,
    RECEIVER,
    STRING,
    UNRESOLVED,
    ValueIndex,
    producers_of,
    resolve_positions,
)
from sextant.domain.closed_sets import Resolution
from sextant.domain.symbols import type_descriptor, with_descriptor

# The join Ktor's `DefaultRequest` makes, read off its 3.6.0 bytecode
# (`DefaultRequest$Plugin.mergeUrls` and `concatenatePath`) and measured by CP-54 rows 51-60:
# a relative path REPLACES the base's last segment (a base ending in `/` has an empty last
# segment, so it keeps every directory), and the base's query follows the call's own.
REPLACE_LAST_SEGMENT = "replace_last_segment"
_JOINS = (REPLACE_LAST_SEGMENT,)

_KEYS = {"client_arg", "ladder", "setter", "join", "may_set_base"}
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
            f"loading catalog {source}: `{_RETIRED}` is folded into `client_base` (D02 §2's "
            f"`fluent` style), which declares where the client's base is set; declare that "
            f"instead"
        )
    return _validated(matches.get("client_base"), source)


def _validated(declared: Any, source: object) -> Mapping[str, Any] | None:
    """`client_base`, refused unless every part is readable; None where it is absent."""
    if declared is None:
        return None
    where = f"loading catalog {source}: `client_base`"
    if not isinstance(declared, dict):
        raise CatalogError(f"{where} is a mapping of {sorted(_KEYS)}, got {declared!r}")
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
    if declared["join"] not in _JOINS:
        raise CatalogError(f"{where}'s `join` is one of {list(_JOINS)}, got {declared['join']!r}")
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
# the key `fluent._captured_at` writes, and what the walk names a position by.
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


def _hands_to_supplied_code(site: Mapping[str, Any], receiver: int) -> bool:
    """Whether `site` hands the block's receiver to code SUPPLIED from outside the block: a
    call made on a value the block captured or on another of its parameters, never on the
    receiver itself. `block()` in `HttpClient(CIO) { defaultRequest { … }; block() }` is
    `invoke(block, receiver)` on the captured `block`, and what that does is the caller's
    code, which the walk never sees; it may replace the base. A static call is made on no
    value at all (the compiler's null check on the receiver, `install$default(config, …)`),
    so it is not this question, and a call on the captured value not handed the receiver
    cannot configure it."""
    on = site.get("receiver_parameter")
    if on is None or int(str(on)) == receiver:
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
