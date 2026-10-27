"""A client's base address (spec 2026-10-26 §3c, §3g items 1-3): the `client_base` catalog
key, the reader that finds the base, and the join that puts a relative call onto it.

A library whose client holds a base address — Ktor's `defaultRequest { url("…") }` — sends a
relative call to the base JOINED with the call's own address, and the join is the library's
rule, not ours (DR-6). Three parts live here, so the `fluent` client catalog and Task 6's
`single_call` WebSocket and SSE catalogs share one copy of each:

- **`client_base_of`**, the key read and its shape refused at load. It says where the client
  sits at the call that issues it (`client_arg`), the configuration calls a base is set
  through (`ladder`, each with the argument holding its block), the call inside the last
  block that sets the base (`setter`), which join applies (`join`), and where a client
  nothing sets a base on sends (`default_base`). All of it is catalog data: nothing here
  names a framework.
- **`join_url`**, the join itself, one rule per behaviour measured. A rule is named for what
  it does, never for the framework that does it (the source rules keep framework names out of
  code); the catalog that declares the join is where the framework is named.
- **`client_base`**, the base itself: the client's construction found by the value walk's
  producer reader (`values.producers_of`), then read through the declared ladder to the
  setter's string. It names no engine's types, so `fluent` and `single_call` call the same
  copy.
"""

from collections.abc import Mapping
from types import MappingProxyType
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from sextant.application.ports.catalogs import CatalogError
from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.shapes.arguments import call_site_index
from sextant.application.resolve.values import (
    CYCLE,
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
from sextant.domain.symbols import type_descriptor, with_descriptor

# The join Ktor's `DefaultRequest` makes, read off its 3.6.0 bytecode
# (`DefaultRequest$Plugin.mergeUrls` and `concatenatePath`) and measured by CP-54 rows 51-60:
# a relative path REPLACES the base's last segment (a base ending in `/` has an empty last
# segment, so it keeps every directory), and the base's query follows the call's own.
REPLACE_LAST_SEGMENT = "replace_last_segment"
_JOINS = (REPLACE_LAST_SEGMENT,)

_KEYS = {"client_arg", "ladder", "setter", "join", "default_base"}
_RUNG_KEYS = {"owner", "method", "block_arg", "descriptor", "parent"}
_SETTER_KEYS = {"owner", "method", "value_arg", "descriptor"}
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
    unknown = sorted(set(declared) - _KEYS)
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
    if not isinstance(declared["default_base"], str) or not _has_host(declared["default_base"]):
        raise CatalogError(
            f"{where}'s `default_base` is the absolute address a client with no base sends "
            f"to, got {declared['default_base']!r}"
        )
    return MappingProxyType(declared)


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


def client_base(
    workspace: Workspace,
    values: ValueIndex | None,
    client_value: Mapping[str, Any],
    declared: Mapping[str, Any],
) -> tuple[str | None, str | None]:
    """The base the client in `client_value` sends a relative address to, as `(base,
    None)`, or `(None, reason)` where it cannot be read.

    `client_value` is the client argument of the call that issues the request, carrying
    where it was read (`captured_at`, `(caller, ordinal, slot)`); `declared` is the
    catalog's `client_base`. The client's construction is found by the value walk's
    producer reader, with every ladder rung declared as a stop, and read like this:

    - **a rung's block is read for the base** — the setter called in it, or in the block of
      a rung called in it, in order; the LAST absolute address wins (CP-54 row 85), and a
      relative one declines the block (row 86, not modelled);
    - **a derived client (`parent: receiver`) whose block sets none inherits** its
      receiver's base (row 80), the receiver walked the same way;
    - **a client whose construction is reached and sets no base sends to `default_base`**
      (Ktor: `http://localhost`, rows 50, 57).

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
    return _Ladder(workspace, values, declared).base_of(site, slot, ())


class _Ladder:
    """One reading of a catalog's `client_base` ladder over one workspace's facts."""

    def __init__(
        self, workspace: Workspace, values: ValueIndex, declared: Mapping[str, Any]
    ) -> None:
        self._workspace = workspace
        self._values = values
        self._by_caller = workspace.once(call_site_index).by_caller
        self._rungs = [
            {**rung, "owner": type_descriptor(str(rung["owner"]))} for rung in declared["ladder"]
        ]
        setter = declared["setter"]
        self._setter = {**setter, "owner": type_descriptor(str(setter["owner"]))}
        self._default = str(declared["default_base"])
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
        """The base of the client one declared call built."""
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
        return self._default, None

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
        base: str | None = None
        for inner in self._by_caller.get(body, []):
            if _matches(inner, self._setter):
                address, reason = self._setter_value(inner)
                if address is None or not _has_host(address):
                    return None, reason or UNTRACED
                base = address
                continue
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
            if answer.kind != LITERAL or answer.literal_kind != STRING:
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


def _matches(site: Mapping[str, Any], call: Mapping[str, Any]) -> bool:
    """`site` is the declared call: owner and method, and the descriptor where one is
    declared."""
    return (
        site.get("owner") == call["owner"]
        and site.get("name") == call["method"]
        and ("descriptor" not in call or site.get("descriptor") == call["descriptor"])
    )


def _has_host(address: str) -> bool:
    """An absolute address: a scheme and a host, which is what replaces a base (CP-54
    rows 55, 85) where a relative one would be resolved against it (row 86)."""
    split = urlsplit(address)
    return bool(split.scheme) and bool(split.hostname)


def join_url(base: str, relative: str, rule: str) -> str | None:
    """`relative` sent from a client whose base is `base`, under the framework's `rule` — or
    None where the join DECLINES: the address is one whose result is not modelled, and the
    caller keeps it unresolved rather than publishing a string the framework never sends.

    Only `replace_last_segment` exists. A client with no base at all is the caller's case:
    Ktor's request builder then takes its origin, `http://localhost` (CP-54 rows 50, 57), and
    this join with that origin as the base gives the same URL."""
    if rule != REPLACE_LAST_SEGMENT:
        raise ValueError(f"no join rule {rule!r}; the rules are {list(_JOINS)}")
    return _replace_last_segment(base, relative)


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
