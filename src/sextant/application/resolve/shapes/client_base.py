"""A client's base address (spec 2026-10-26 §3c, §3g items 1-3): the `client_base` catalog
key, and the join that puts a relative call onto the base.

A library whose client holds a base address — Ktor's `defaultRequest { url("…") }` — sends a
relative call to the base JOINED with the call's own address, and the join is the library's
rule, not ours (DR-6). Two halves live here, so the `fluent` client catalog and Task 6's
`single_call` WebSocket and SSE catalogs share one copy of each:

- **`client_base_of`**, the key read and its shape refused at load. It says where the client
  sits at the call that issues it (`client_arg`), the configuration calls a base is set
  through (`ladder`, each with the argument holding its block), the call inside the last
  block that sets the base (`setter`), and which join applies (`join`). All of it is catalog
  data: nothing here names a framework.
- **`join_url`**, the join itself, one rule per behaviour measured. A rule is named for what
  it does, never for the framework that does it (the source rules keep framework names out of
  code); the catalog that declares the join is where the framework is named.

**What is not here yet: reading a client's construction through the ladder.** The value walk
answers what a value IS, never which call built it, and a client held in a field or a
top-level `val` written from a call has no fact at all (D00 §5, CP-33 rows 6-7). Until both
are closed an engine declaring `client_base` keeps a relative address's path, peer NULL, at
`unresolved`.
"""

from collections.abc import Mapping
from types import MappingProxyType
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from sextant.application.ports.catalogs import CatalogError

# The join Ktor's `DefaultRequest` makes, read off its 3.6.0 bytecode
# (`DefaultRequest$Plugin.mergeUrls` and `concatenatePath`) and measured by CP-54 rows 51-60:
# a relative path REPLACES the base's last segment (a base ending in `/` has an empty last
# segment, so it keeps every directory), and the base's query follows the call's own.
REPLACE_LAST_SEGMENT = "replace_last_segment"
_JOINS = (REPLACE_LAST_SEGMENT,)

_KEYS = {"client_arg", "ladder", "setter", "join"}
_RUNG_KEYS = {"owner", "method", "block_arg", "descriptor", "parent"}
_SETTER_KEYS = {"owner", "method", "value_arg", "descriptor"}
# A rung that DERIVES a client from another (`HttpClient.config { … }`) inherits the other's
# base where its own block sets none (CP-54 row 80). `receiver` is the one place the parent
# can be: the call is made on it.
_PARENTS = ("receiver",)


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
