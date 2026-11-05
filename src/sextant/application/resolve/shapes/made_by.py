"""`made_by` (D02 §2's `annotation_driven`, Android outbound spec M8): an annotation-declared
client gets its server address from the object that made it.

A Retrofit interface states a verb and a path, and nothing about the server. The server is
the `baseUrl` of the builder that made the `Retrofit` object, and that object makes the
client in `create(OrdersApi.class)`. The catalog names that call and the argument that holds
the interface's class literal; this module joins the three pieces that already exist:

1. every call the catalog names whose class argument is the row's interface;
2. the object each such call is made on, followed back to the call that made it, through
   locals, fields, parameters and helper returns (`values.producer_paths` with
   `which_object`, the object walk `ObjectKeys` reads for in-process dispatch), keeping the
   path it took;
3. the steps folded into that object before it was made (`chains.chain_ends`, the walk the
   `fluent` engine folds `baseUrl` with, rooted at the call that made the object), their
   argument read on the path of step 2.

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
from sextant.application.resolve.dispatch import Dispatch, dispatch_of
from sextant.application.resolve.shapes.arguments import _string_value, _walked_with, split_url
from sextant.application.resolve.shapes.chains import chain_ends
from sextant.application.resolve.shapes.mounts import weaker
from sextant.application.resolve.values import (
    CYCLE,
    EXPRESSION,
    LITERAL,
    RECEIVER,
    STRING,
    Answer,
    Path,
    ValueIndex,
    cached_value_index,
    producer_paths,
)
from sextant.domain.closed_sets import Resolution
from sextant.domain.config_keys import carries_expression
from sextant.domain.symbols import (
    bare_descriptor,
    method_name,
    owner_of,
    type_descriptor,
    without_type_marker,
)

MADE_BY = "made_by"
# The one capture a `made_by` step may declare: the server address the object is made with.
_BASE = "base"
_PARTIAL = str(Resolution.PARTIAL)
_RESOLVED = str(Resolution.RESOLVED)
_NARROWED = str(Resolution.NARROWED)
# The schemes `okhttp3.HttpUrl` parses; it throws on any other (retrofit 2.11.0, `_joined`).
_SCHEMES = ("http", "https")
# The name the facts give a constructor: a construction makes an object (`ObjectKeys`).
_CONSTRUCTOR = "<init>"


def validated_made_by(catalog: Catalog) -> Mapping[str, Any] | None:
    """`matches.made_by`, its steps checked, or None where the catalog declares none.

    The catalog load is the one rule for the word itself (`yaml_source._check_made_by`): an
    outbound `annotation_driven` catalog only, the keys `owner` and `method` (the call that
    makes the client object), `class_arg` (the argument of that call holding the
    interface's class literal) and `steps`. Only the steps are checked here: they are the
    `fluent` engine's own step words, folded on the object that call is made on. Every step
    captures `base` and nothing else: a step capturing anything else would load and be read
    by nothing."""
    # A mapping: the catalog load refuses any other (`yaml_source._check_made_by`).
    declared: Mapping[str, Any] | None = catalog.matches.get(MADE_BY)
    if declared is None:
        return None
    where = f"loading catalog {catalog.source}: `{MADE_BY}`"
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
    dispatch = workspace.once(dispatch_of)
    symbols = _type_symbols(workspace)
    rows: list[dict[str, Any]] = []
    for candidate in candidates:
        for serving, made in _clients_of(candidate, bases, dispatch, symbols):
            for peer, path, resolution in dict.fromkeys(
                _addressed(candidate, base) for base in made
            ):
                rows.append(
                    {
                        "handler": candidate["handler"],
                        "served_by": candidate.get("served_by"),
                        "caller": candidate.get("caller"),
                        "method": candidate["method"],
                        "was": candidate["path"],
                        "serving": serving,
                        "peer": peer,
                        "path": path,
                        "resolution": resolution,
                    }
                )
    workspace.derive("endpoint_candidates_address", catalog_id=catalog.id, rows=rows)


def _clients_of(
    candidate: Mapping[str, Any],
    bases: Mapping[str | None, tuple[_Base, ...]],
    dispatch: Dispatch,
    symbols: Mapping[str, str],
) -> list[tuple[Any, tuple[_Base, ...]]]:
    """The interfaces a candidate row is called through, each as the `served_by` its row
    carries and the addresses of the objects made for it (fix round 2, the controller's ruling
    of 2026-11-05).

    A method an interface declares is called through that interface and through every
    interface that inherits it without declaring its own (`Dispatch.heirs`, JVMS 5.4.3.3):
    `create(AuthApi.class)` makes a client whose `health()` is `BaseApi`'s. So each such
    interface that a `made_by` call names gets a row of its own, served by it, with its own
    objects' addresses. The declaring interface keeps a row of its own where a call makes it
    directly; where only interfaces below it are made, its calls are theirs, and a row of its
    own would claim a client nothing made. Where NO interface on the way is made, the row is
    kept as it is, at `partial` with no server: the declaration is the only evidence of the
    call, and dropping it would lose a call the code declares."""
    interface = _interface_of(candidate)
    # An outbound row names its interface method as the CALLER (D01 §3: `caller` with
    # `handler` NULL), an inbound one as the handler.
    declared = candidate.get("caller") or candidate.get("handler")
    heirs = (
        dispatch.heirs(interface, method_name(bare_descriptor(str(declared))))
        if interface is not None and declared is not None
        else []
    )
    made: list[tuple[Any, tuple[_Base, ...]]] = [
        (symbols.get(heir, heir), bases[heir]) for heir in heirs if heir in bases
    ]
    if interface in bases or not made:
        made.insert(0, (candidate.get("served_by"), bases.get(interface, (_NOT_READ,))))
    return made


def _type_symbols(workspace: Workspace) -> dict[str, str]:
    """Each type that lists interfaces, by bare descriptor, as the module spells its symbol:
    the `served_by` a row made through an inheriting interface carries."""
    return {
        bare_descriptor(str(row["symbol"])): str(row["symbol"])
        for row in workspace.query("implementations")
    }


def _interface_of(candidate: Mapping[str, Any]) -> str | None:
    """The interface a candidate row is declared on: the type that serves it (an inherited
    method's row is served by the interface that inherits it), else its method's owner."""
    served = candidate.get("served_by")
    if served:
        return bare_descriptor(str(served))
    declared = candidate.get("caller") or candidate.get("handler")
    return None if declared is None else owner_of(bare_descriptor(str(declared)))


def _bases_by_interface(
    workspace: Workspace, catalog: Catalog, made_by: Mapping[str, Any]
) -> dict[str | None, tuple[_Base, ...]]:
    """Each interface a `made_by` call names, with every server address the objects those
    calls are made on carry. An interface no call names is absent.

    **The object is followed on its own path, and the address is read on that same path.**
    The object walk (`values.producer_paths`, `which_object`: the reader `ObjectKeys` uses for
    in-process dispatch) names the call that made the object and the path it took there,
    with each descent into a helper written as the call that entered it. The `base` is then
    read within that path (`resolve_positions(..., within=)`), so a helper
    `retrofit(base) = Retrofit.Builder().baseUrl(base).build()` called twice gives each
    `create` its own caller's base, never both: one object, one path, one address."""
    index = cached_value_index(workspace, catalog.not_hand_offs, catalog.hand_off_effects)
    owner = type_descriptor(str(made_by["owner"]))
    slot = int(made_by["class_arg"])
    # Where an object is made, as `ObjectKeys` reads it: a construction, or a call whose body
    # is not here.
    made = index.unscanned | frozenset((built, _CONSTRUCTOR) for built in index.constructed)
    # The calls that make the objects, per interface, each with the path the walk took to it
    # and whether that path is exact. None where the path reaches no such call.
    makers: dict[str | None, list[tuple[tuple[str, int] | None, Path | None, bool]]] = {}
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
        found = makers.setdefault(interface, [])
        for producer, path in producer_paths(index, site, RECEIVER, made, which_object=True):
            # A path that comes back to where it started adds no object (`ObjectKeys`).
            if producer.reason == CYCLE:
                continue
            if producer.caller is None or producer.ordinal is None:
                found.append((None, None, False))
                continue
            found.append(((producer.caller, producer.ordinal), path, producer.inexact))
    made_at = {key for entries in makers.values() for key, _, _ in entries if key is not None}
    captured = _captured_at(workspace, catalog, made_by, index, made_at)
    reads = _Reads(workspace=workspace, values=index)
    bases: dict[str | None, tuple[_Base, ...]] = {}
    for made_for, entries in makers.items():
        read: list[_Base] = []
        for key, taken, inexact in entries:
            if key is None:
                read.append(_NOT_READ)
                continue
            for captured_base, unsure in captured.get(key) or ((None, False),):
                read.extend(_bases_of(captured_base, reads, taken, inexact or unsure))
        bases[made_for] = tuple(dict.fromkeys(read or (_NOT_READ,)))
    return bases


def _captured_at(
    workspace: Workspace,
    catalog: Catalog,
    made_by: Mapping[str, Any],
    index: ValueIndex,
    made_at: set[tuple[str, int]],
) -> dict[tuple[str, int], tuple[tuple[Any, bool], ...]]:
    """The `base` argument folded into each object made at `made_at`, and whether the fold is
    exact, read by the `fluent` chain walk rooted at the call that made it: the catalog's
    steps fold backward onto it exactly as `baseUrl` folds onto a WebClient built before its
    root (`_prefix_captures`). The argument is read later, on the path the object took."""
    roots: dict[tuple[str, str], dict[str, Any]] = {}
    for key in sorted(made_at):
        site = index.sites.get(key)
        if site is None:
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
    found: dict[tuple[str, int], list[tuple[Any, bool]]] = {}
    for end in chain_ends(workspace, chain, frozenset({_BASE})):
        key = (str(end.root["caller"]), int(str(end.root["ordinal"])))
        if key in made_at:
            found.setdefault(key, []).append((end.captures.get(_BASE), end.inexact))
    return {key: tuple(captures) for key, captures in found.items()}


def _bases_of(
    argument: Any, reads: _Reads, within: Path | None, inexact: bool
) -> tuple[_Base, ...]:
    """The server addresses one captured `base` argument holds: its literal, else each value
    the value walk reaches for it within `within`, the path the object took (a parameter is
    the argument the caller on that path hands it). A configuration key the walk reaches is
    the address's own text, as a `fluent` base is (`trace-the-value-to-its-source`)."""
    if not isinstance(argument, dict):
        return (_NOT_READ,)
    cap = _PARTIAL if inexact else _RESOLVED
    literal = _string_value(argument)
    if literal is not None:
        return (_Base(literal, cap),)
    walked = _walked_with(argument, reads, (), reader=_base_answer, within=within)
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
