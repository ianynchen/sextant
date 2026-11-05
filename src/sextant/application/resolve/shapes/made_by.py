"""`made_by` (D02 §2's `annotation_driven`, Android outbound spec M8): an annotation-declared
client gets its server address from the object that made it.

A Retrofit interface states a verb and a path, and nothing about the server. The server is
the `baseUrl` of the builder that made the `Retrofit` object, and that object makes the
client in `create(OrdersApi.class)`. The catalog names that call and the argument that holds
the interface's class literal; this module joins the three pieces that already exist:

1. every call the catalog names whose class argument is the row's interface;
2. the object each such call is made on, followed back to the call that made it, through
   locals, fields, parameters and helper returns (`dispatch_registrations.ObjectKeys`, the
   object walk built for in-process dispatch);
3. the steps folded into that object before it was made (`chains.chain_ends`, the walk the
   `fluent` engine folds `baseUrl` with, rooted at the call that made the object).

Each address read is joined to the row's own path, one row per address (the set of calls the
module makes is closed: each address is exact, never a hedge). A row whose address is not
read, because no such call names its interface, or the object comes from code we do not
have, or the step's argument is not read, keeps its path with no peer, and is `partial`:
the server address is not read. It is never `resolved`.

Read once per catalog, on the candidate rows, before the rows go into `endpoints`, so the
earlier-catalog-wins rule (`insert_endpoints.sql`) compares the address the row really has.
"""

from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any
from urllib.parse import urljoin, urlsplit

from sextant.application.ports.catalogs import Catalog, CatalogError
from sextant.application.ports.workspace import Workspace

# The module, not the name: `dispatch_registrations` reads `annotation_driven`, which reads
# this module, so the class is looked up when it is used, after every module has loaded.
from sextant.application.resolve import dispatch_registrations
from sextant.application.resolve.shapes.arguments import _string_value, _walked_with, split_url
from sextant.application.resolve.shapes.chains import chain_ends
from sextant.application.resolve.shapes.mounts import weaker
from sextant.application.resolve.values import (
    EXPRESSION,
    LITERAL,
    STRING,
    Answer,
    ValueIndex,
    cached_value_index,
)
from sextant.domain.closed_sets import Resolution
from sextant.domain.config_keys import carries_expression
from sextant.domain.symbols import (
    bare_descriptor,
    owner_of,
    type_descriptor,
    without_type_marker,
)

MADE_BY = "made_by"
_KEYS = frozenset({"owner", "method", "class_arg", "steps"})
# The one capture a `made_by` step may declare: the server address the object is made with.
_BASE = "base"
_PARTIAL = str(Resolution.PARTIAL)
_RESOLVED = str(Resolution.RESOLVED)
_NARROWED = str(Resolution.NARROWED)
# The schemes `okhttp3.HttpUrl` parses; it throws on any other (retrofit 2.11.0, `_joined`).
_SCHEMES = ("http", "https")


def validated_made_by(catalog: Catalog) -> Mapping[str, Any] | None:
    """`matches.made_by`, its shape checked, or None where the catalog declares none.

    Only on an `annotation_driven` catalog that derives outbound rows: the address is the
    address a CLIENT calls, and only an annotation-declared client has no call of its own to
    read it from. The keys are `owner` and `method` (the call that makes the client object),
    `class_arg` (the argument of that call holding the interface's class literal) and
    `steps` (the `fluent` engine's own step words, folded on the object that call is made
    on). Every step captures `base` and nothing else: a step capturing anything else would
    load and be read by nothing."""
    declared = catalog.matches.get(MADE_BY)
    if declared is None:
        return None
    where = f"loading catalog {catalog.source}: `{MADE_BY}`"
    if catalog.style != "annotation_driven" or catalog.direction != "outbound":
        raise CatalogError(
            f"{where} is a word of an outbound `annotation_driven` catalog only: it says where "
            f"an annotation-declared client gets its server address"
        )
    if not isinstance(declared, dict):
        raise CatalogError(f"{where} must be a mapping, got {declared!r}")
    unknown = sorted(set(declared) - _KEYS)
    missing = sorted(_KEYS - set(declared))
    if unknown or missing:
        raise CatalogError(
            f"{where} declares {sorted(_KEYS)} exactly; unknown {unknown}, missing {missing}"
        )
    for key in ("owner", "method"):
        if not isinstance(declared[key], str) or not declared[key]:
            raise CatalogError(f"{where}'s `{key}` must be a name, got {declared[key]!r}")
    class_arg = declared["class_arg"]
    if not isinstance(class_arg, int) or isinstance(class_arg, bool) or class_arg < 0:
        raise CatalogError(f"{where}'s `class_arg` is an argument index, got {class_arg!r}")
    steps = declared["steps"]
    if not isinstance(steps, list) or not steps:
        raise CatalogError(f"{where}'s `steps` must be a non-empty list of steps")
    for step in steps:
        if not isinstance(step, dict) or "owner" not in step:
            raise CatalogError(
                f"{where}'s steps each name an `owner`: only an owner-declared step folds "
                f"backward onto the object (D02 §2's `fluent`), got {step!r}"
            )
        if set(step.get("captures") or {}) != {_BASE}:
            raise CatalogError(
                f"{where}'s steps each capture `{_BASE}` and nothing else, got {step!r}"
            )
    return declared


@dataclass(frozen=True)
class _Reads:
    """What the value walk reads a captured argument with (`arguments._walked_with`)."""

    workspace: Workspace
    values: ValueIndex
    facts: Any = None
    field_sources: Any = None


@dataclass(frozen=True)
class _Base:
    """One server address read for an interface: its text, and how sure the read is. None
    text is an address not read."""

    text: str | None
    resolution: str = _RESOLVED


_NOT_READ = _Base(None, _PARTIAL)


def addressed_candidates(workspace: Workspace, catalog: Catalog) -> None:
    """This catalog's candidate rows with the server address joined in (module docstring).
    Nothing for a catalog declaring no `made_by`."""
    made_by = validated_made_by(catalog)
    if made_by is None:
        return
    candidates = workspace.query("endpoint_candidates_of", catalog_id=catalog.id)
    if not candidates:
        return
    bases = _bases_by_interface(workspace, catalog, made_by)
    rows: list[dict[str, Any]] = []
    for candidate in candidates:
        interface = _interface_of(candidate)
        addressed = dict.fromkeys(
            _addressed(candidate, base) for base in bases.get(interface, (_NOT_READ,))
        )
        for peer, path, resolution in addressed:
            rows.append(
                {
                    "handler": candidate["handler"],
                    "method": candidate["method"],
                    "was": candidate["path"],
                    "peer": peer,
                    "path": path,
                    "resolution": resolution,
                }
            )
    workspace.derive("endpoint_candidates_address", catalog_id=catalog.id, rows=rows)


def _interface_of(candidate: Mapping[str, Any]) -> str | None:
    """The interface a candidate row is declared on: the type that serves it (an inherited
    method's row is served by the interface that inherits it), else its handler's owner."""
    served = candidate.get("served_by")
    if served:
        return bare_descriptor(str(served))
    handler = candidate.get("handler")
    return None if handler is None else owner_of(bare_descriptor(str(handler)))


def _bases_by_interface(
    workspace: Workspace, catalog: Catalog, made_by: Mapping[str, Any]
) -> dict[str | None, tuple[_Base, ...]]:
    """Each interface a `made_by` call names, with every server address the objects those
    calls are made on carry. An interface no call names is absent."""
    index = cached_value_index(workspace, catalog.not_hand_offs, catalog.hand_off_effects)
    owner = type_descriptor(str(made_by["owner"]))
    slot = int(made_by["class_arg"])
    objects = dispatch_registrations.ObjectKeys(workspace, catalog)
    # The calls that make the objects, per interface, in the order the walk names them.
    makers: dict[str | None, list[str | None]] = {}
    for site in index.sites.values():
        if str(site.get("owner")) != owner or str(site.get("name")) != made_by["method"]:
            continue
        arguments = site.get("arguments") or []
        argument = arguments[slot] if slot < len(arguments) else None
        # A class argument the call does not state as a literal names no interface this
        # module can tell: the interfaces it makes keep the rows of every other call.
        if not isinstance(argument, dict) or argument.get("kind") != "class":
            continue
        interface = bare_descriptor(str(argument.get("symbol")))
        for key in objects.of(site):
            makers.setdefault(interface, []).append(key)
    made_at = {key for keys in makers.values() for key in keys if key is not None}
    read = _bases_made_at(workspace, catalog, made_by, index, made_at)
    return {
        interface: tuple(
            dict.fromkeys(
                base
                for key in keys
                for base in ((read.get(key) or (_NOT_READ,)) if key is not None else (_NOT_READ,))
            )
        )
        for interface, keys in makers.items()
    }


def _object_key(site: Mapping[str, Any]) -> str:
    """A site named as `ObjectKeys` names the call that made an object."""
    return f"{site['caller']}#{site['ordinal']}"


def _bases_made_at(
    workspace: Workspace,
    catalog: Catalog,
    made_by: Mapping[str, Any],
    index: ValueIndex,
    made_at: set[str],
) -> dict[str, tuple[_Base, ...]]:
    """The server addresses folded into each object made at `made_at`, read by the `fluent`
    chain walk rooted at the call that made it: the catalog's steps fold backward onto it
    exactly as `baseUrl` folds onto a WebClient built before its root (`_prefix_captures`)."""
    roots: dict[tuple[str, str], dict[str, Any]] = {}
    for site in index.sites.values():
        if _object_key(site) not in made_at:
            continue
        owner, name = str(site["owner"]), str(site["name"])
        # The owner as the facts spell it, less its type marker: the catalog's converter
        # (`type_descriptor`) gives the same symbol back, as it does for a dotted name.
        roots[(owner, name)] = {"owner": without_type_marker(owner), "method": name}
    if not roots:
        return {}
    chain = replace(
        catalog,
        matches={
            "roots": list(roots.values()),
            "steps": list(made_by["steps"]),
            "terminal": sorted({name for _, name in roots}),
        },
    )
    reads = _Reads(workspace=workspace, values=index)
    found: dict[str, list[_Base]] = {}
    for end in chain_ends(workspace, chain, frozenset({_BASE})):
        key = _object_key(end.root)
        if key not in made_at:
            continue
        for base in _bases_of(end.captures.get(_BASE), reads, end):
            found.setdefault(key, []).append(base)
    return {key: tuple(dict.fromkeys(bases)) for key, bases in found.items()}


def _bases_of(argument: Any, reads: _Reads, end: Any) -> tuple[_Base, ...]:
    """The server addresses one captured `base` argument holds: its literal, else each value
    the value walk reaches for it on the chain's own path (a parameter is the argument each
    caller hands it). A configuration key the walk reaches is the address's own text, as a
    `fluent` base is (`trace-the-value-to-its-source`)."""
    if not isinstance(argument, dict):
        return (_NOT_READ,)
    cap = _PARTIAL if end.inexact else _RESOLVED
    literal = _string_value(argument)
    if literal is not None:
        return (_Base(literal, cap),)
    walked = _walked_with(argument, reads, (), reader=_base_answer, within=end.path)
    return tuple(
        _Base(text, weaker(resolution, cap)) if text is not None else _NOT_READ
        for _, text, resolution in walked or ((None, None, _PARTIAL),)
    )


def _base_answer(answer: Answer | None) -> tuple[str | None, str | None, str]:
    """One walk answer for a server address, as `(None, text, resolution)`: a string literal
    or a configuration expression with no unread hole is read; a branch among several is
    `narrowed`, and a value reached through a merge is `partial`; every other answer is not
    read."""
    if answer is None:
        return None, None, _PARTIAL
    readable = (answer.kind == LITERAL and answer.literal_kind == STRING) or (
        answer.kind == EXPRESSION and "{}" not in str(answer.value)
    )
    if not readable:
        return None, None, _PARTIAL
    if answer.inexact:
        return None, str(answer.value), _PARTIAL
    if answer.narrowed:
        return None, str(answer.value), _NARROWED
    return None, str(answer.value), _RESOLVED


def _addressed(candidate: Mapping[str, Any], base: _Base) -> tuple[str | None, str | None, str]:
    """One candidate row's peer, path and resolution, sent from a client made with `base`.

    A row whose annotation already states its server (a peer, or an absolute URL as its
    path, which replaces the base whatever it is) keeps that address: the base adds nothing
    to it."""
    path = candidate["path"]
    resolution = str(candidate["resolution"])
    if candidate.get("peer") is not None:
        return candidate["peer"], path, resolution
    if path is not None and urlsplit(str(path)).scheme in _SCHEMES:
        peer, stated = split_url(str(path))
        return peer, stated or "/", resolution
    joined = None if base.text is None or path is None else _joined(base.text, str(path))
    if joined is None:
        return None, path, weaker(resolution, _PARTIAL)
    if carries_expression(joined):
        # A configuration key is never split into a peer: the whole address is kept, as a
        # `fluent` base composed with an expression is (`fluent._address_of`).
        return None, joined, weaker(resolution, base.resolution)
    peer, joined_path = split_url(joined)
    if peer is None:
        return None, path, weaker(resolution, _PARTIAL)
    return peer, joined_path or "/", weaker(resolution, base.resolution)


def _joined(base: str, path: str) -> str | None:
    """`path` sent from a client whose server address is `base`, or None where it cannot be
    told.

    MEASURED against retrofit 2.11.0 (`javap -c -p`, 2026-11-05): `Retrofit$Builder.baseUrl(String)`
    parses the text with `okhttp3.HttpUrl.get(String)`, which throws on anything but an
    absolute `http` or `https` URL, and `baseUrl(HttpUrl)` throws
    `IllegalArgumentException("baseUrl must end in /: …")` where the last path segment is
    not empty. `RequestBuilder` makes the request URL with `baseUrl.newBuilder(relativeUrl)`
    and `baseUrl.resolve(relativeUrl)`, OkHttp's reference resolution, which is RFC 3986
    §5.2's: `orders/{id}` keeps the base's path, `/orders` replaces it, and an absolute URL
    replaces the whole address. So a base that is not an absolute `http(s)` URL, or whose
    path does not end in `/`, makes no client and is not read.

    A base holding a configuration expression cannot be parsed. Since a working client's
    base ends in `/`, a relative path is the base followed by the path; a path with a
    leading `/` replaces the base's own path, which the expression hides, so that address
    is not read."""
    if urlsplit(path).scheme in _SCHEMES:
        return path
    if carries_expression(base):
        if path.startswith("/"):
            return None
        return base + path
    parts = urlsplit(base)
    if parts.scheme not in _SCHEMES or not parts.netloc:
        return None
    if parts.path and not parts.path.endswith("/"):
        return None
    return urljoin(base, path)
