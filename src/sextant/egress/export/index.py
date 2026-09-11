"""The index bundle (F8 §9.3, W35) — where, not only what.

## What this is for

Sextant scans a repository and could say WHAT exists without ever saying WHERE. An agent
holding the bundle still had to grep the source it had already been told about, which is
the cost this removes: one lookup returns `<source root>/com/acme/Api.<ext>:41`, and the
agent opens that file at that line instead of searching for a name.

## Why NDJSON rather than a table

Ruled in §9.3. The bundle already has three shapes and this is the third: `graph/*.parquet`
is the dataset a query engine reads, `render/` is the projection a person reads, and
`index/` is the projection a machine reader loads once. NDJSON because **a grep hit returns
one complete self-describing record** — which is what matters when an agent opens the file
cold, with no schema and no engine. A Parquet table is not greppable and a DuckDB file must
be learned before it answers anything.

**The accepted cost, stated in the design:** the index cannot be joined against the tables
in DuckDB. Its job is to reach a `file:line` fast; after that the consumer opens the file,
or queries the tables by the exact symbol the index just handed back — which is why every
record carries the symbol verbatim.

## What a line number can and cannot be

`LineNumberTable` is per METHOD BODY (JVMS 4.7.12). So:

* a method or constructor carries its own extent, and that is exact;
* a **type or a field carries none, and never will** — the class file states no declaration
  line for either. Measured on `mall-admin`: 20,961 of 22,059 methods and all 818
  constructors have one; every one of 509 classes, 132 interfaces and 2,000 fields reads 0.

A type's record therefore carries `line: null` and says so, rather than being given the
first line of its first method — which is where its first METHOD is, not where the class is
declared, and would read as fact.

## The six answers, and the two that assemble the others

`symbols`, `callers`, `implementors`, `annotated`, `shape_carriers` and `addresses` each
answer one question from one table. `files` and `impact` (W36) answer two that need
several, and they exist because the JOIN is the work:

* **`files`** — per file, what it declares and which annotations appear in it, so an agent
  decides **not to open** a file. Most of what an assistant spends goes on files opened and
  discarded, which makes this the cheapest win in the index.
* **`impact`** — "change `Order`" → the shape, its fields, the endpoints carrying it, and
  the handlers and callers of those, each already placed. Nobody names a field; they name a
  type, and what they need back is every place that decision reaches.

## Redaction

**This is an EXIT, and every exit masks** (2K design §1: the workspace stays verbatim
because analysis needs real values, and masking happens where data crosses the trust
boundary — the bundle being one). The index reads the same rows `graph/` does, so an
address it published unmasked would be the same bytes the parquet beside it takes trouble
to strip: measured before this was wired, a root at
`https://user:hunter2@internal.example.com/orders` reached `addresses.ndjson` whole while
`graph/roots.parquet` held `https://internal.example.com/orders`.

Only the ADDRESS-bearing fields take it — `path`, on the two files that carry one — because
that is the only kind of value these records hold. A symbol, a file path, a line number, an
annotation's NAME and a construct kind are none of them values a rule masks, and passing
them through the redactor would be the redactor asked a question about the wrong grammar.
Annotation ARGUMENTS are deliberately not in the index at all, which is why no JSON rule is
needed here.

## What a path is

`documents.relative_path` is a package path (`com/acme/orders/Api.<ext>`), relative to a
source root and openable against nothing on its own. `metadata.json` carries the module's
`source_roots`, so this joins the two — and where the joined file does not exist on disk,
the record says which roots were tried instead of publishing a path that opens nothing.
"""

import json
import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from sextant.domain.redaction import Redactor
from sextant.domain.symbols import bare_descriptor

# One record per line, and the files are written in a fixed order with their rows sorted,
# so two exports of one workspace are byte-identical (NFR-1).
_SYMBOLS = "symbols.ndjson"
_CALLERS = "callers.ndjson"
_IMPLEMENTORS = "implementors.ndjson"
_ANNOTATED = "annotated.ndjson"
_SHAPE_CARRIERS = "shape_carriers.ndjson"
_ADDRESSES = "addresses.ndjson"
# F8 §9.3 rows 4 and 5 (W36).
_FILES = "files.ndjson"
_IMPACT = "impact.ndjson"


def write_index(
    bundle: Path,
    *,
    symbols: Sequence[dict[str, object]],
    documents: Sequence[dict[str, object]],
    call_edges: Sequence[dict[str, object]],
    implementations: Sequence[dict[str, object]],
    annotations: Sequence[dict[str, object]],
    endpoints: Sequence[dict[str, object]],
    roots: Sequence[dict[str, object]],
    shapes: Sequence[dict[str, object]],
    shape_fields: Sequence[dict[str, object]],
    source_roots: Sequence[str],
    module_root: Path,
    redactor: Redactor,
) -> list[str]:
    """Writes `index/*.ndjson` into `bundle` and returns the file names written.

    Every index is derived from tables the bundle already ships, so nothing here is a new
    claim: an index that disagreed with `graph/` would be a second answer to a question the
    tables already settle. What it adds is the JOIN a consumer would otherwise perform —
    symbol to document to source root — and the reverse direction of edges the tables store
    one way round.
    """
    located, lookup, paths = _locations(symbols, documents, source_roots, module_root)
    index = bundle / "index"
    index.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for name, records in (
        (_SYMBOLS, _symbol_records(located)),
        (_CALLERS, _caller_records(call_edges, lookup)),
        (_IMPLEMENTORS, _implementor_records(implementations, lookup)),
        (_ANNOTATED, _annotated_records(annotations, lookup, paths)),
        (_SHAPE_CARRIERS, _shape_carrier_records(endpoints, lookup, redactor)),
        (_ADDRESSES, _address_records(roots, lookup, redactor)),
        (_FILES, _file_records(located, lookup, annotations, paths)),
        (_IMPACT, _impact_records(shapes, shape_fields, endpoints, lookup, redactor)),
    ):
        (index / name).write_text(
            "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
            encoding="utf-8",
        )
        written.append(name)
    return written


def _locations(
    symbols: Sequence[dict[str, object]],
    documents: Sequence[dict[str, object]],
    source_roots: Sequence[str],
    module_root: Path,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, str | None]]:
    """Every symbol's `{file, line, line_end, kind, enclosing}` twice over — the LISTING
    keyed on each symbol exactly once and the LOOKUP keyed on both spellings — plus each
    DOCUMENT's own resolved path.

    Built once and shared by every index below, because each of them answers with a
    location and re-deriving it per index is where two indexes come to disagree.

    The document paths are the third, because a file is a thing in its own right: a
    `package-info` declares no symbol at all and still opens, still carries the package's
    nullness rule, and still deserves a digest record saying an agent can skip it.

    Two symbol maps rather than one because they are two jobs. `symbols.ndjson` is a listing and
    must hold each symbol once; every other index performs a LOOKUP, and the key it holds
    may be either spelling — a symbol carries its module coordinates (D00 §5a) and a SHAPE
    ID does not, so `impact`'s `com/acme/orders/OrderCommand#` matched nothing against a
    map keyed on the whole symbol and every contract reported itself undeclared. Aliasing
    the single map instead emitted every symbol twice in the listing.
    """
    paths = {
        str(document["document_id"]): _openable(
            str(document["relative_path"]),
            source_roots,
            module_root,
            document["origin_entry"],
        )
        for document in documents
    }
    found: dict[str, dict[str, Any]] = {}
    for symbol in symbols:
        start = int(str(symbol["line_start"] or 0))
        end = int(str(symbol["line_end"] or 0))
        whole = str(symbol["symbol"])
        location = {
            "file": paths.get(str(symbol["document_id"])),
            # NULL, not 0, and not the first line of the first method: a class file states
            # no declaration line for a type or a field, so there is nothing to report and
            # a number here would be a claim about where the DECLARATION is.
            "line": start or None,
            "line_end": end or None,
            "kind": str(symbol["construct_kind"]),
            "enclosing": symbol["enclosing"],
        }
        # The LISTING: one entry per symbol, under its whole spelling. The both-spellings
        # map is built from this one below — aliasing here instead emitted every symbol
        # twice in `symbols.ndjson`, which is why these are two maps and not one.
        found[whole] = location
    # The LOOKUP: the same locations under both spellings. They can never collide — a bare
    # descriptor has no module coordinates by definition — so one extra map covers every
    # caller that holds either.
    lookup = dict(found)
    for whole, location in found.items():
        lookup.setdefault(bare_descriptor(whole), location)
    return found, lookup, paths


def _openable(
    relative_path: str,
    source_roots: Sequence[str],
    module_root: Path,
    origin_entry: object,
) -> str | None:
    """A document's package path resolved to something a consumer can open, RELATIVE to
    the module root, or None where nothing holds it.

    The roots are TRIED, not assumed: a module declaring two of them — this repo's own
    fixture does, one per language it compiles — puts each class under exactly one, and the
    file's existence is what says which. None rather than a first-root guess — a path that
    opens nothing is worse than an admitted absence, because a consumer acts on the first
    and asks about the second.

    **A SIBLING module's sources are under that sibling's root**, and this module's roots
    reach none of them. `origin_entry` names the classes directory the document was read
    from, so the sibling's root is its parent, and the same tried-not-assumed rule then
    applies there. Without this the index placed 157 of `mall-admin`'s 648 documents — its
    own, and not one symbol of the four reactor siblings it scans, which is 1,428 of
    25,521 symbols.

    **Never absolute.** An absolute path names a directory that exists on one computer, and
    a bundle travels. A sibling comes back as `../mall-common/<source root>/…`, which is
    what a checkout of the reactor can actually open; anything that will not reduce to a
    relative path is dropped rather than published.
    """
    for root in source_roots:
        if (module_root / root / relative_path).is_file():
            return f"{root}/{relative_path}"
    return _beside_a_sibling(relative_path, source_roots, module_root, origin_entry)


def _beside_a_sibling(
    relative_path: str,
    source_roots: Sequence[str],
    module_root: Path,
    origin_entry: object,
) -> str | None:
    """The same lookup against the module that PRODUCED this document, where that is not
    the module being exported.

    The sibling's own source roots are not recorded anywhere — only the module being
    analysed has a detector run against it — so this reuses THIS module's, which is the
    honest approximation for a reactor: sibling modules of one build almost always share a
    layout, and the file's existence still decides. A sibling laid out differently simply
    does not resolve, and says so with a null.

    **The module root is SEARCHED for, not computed from the classes directory**, because
    how deep that sits is the build tool's business: one writes its classes two directories
    below the module root and another four. Walking up and asking "does this ancestor hold the file under one of the
    source roots" answers for both without either being named here.

    **The walk is bounded three ways**, and it had none of them: an entry that is not a
    classes DIRECTORY is skipped, a relative one is skipped, and the walk stops at this
    module's parent. Unbounded it climbed to `/` on every export of the fixture, and any
    ancestor holding a file with the same package path would have been published as the
    source — a path to the WRONG file, which is worse than a null, and one escaping the
    checkout at that.
    """
    if origin_entry is None:
        return None
    entry = Path(str(origin_entry))
    # **A CLASSES DIRECTORY, never an archive.** A document extracted from a jar has its
    # jar's path here, and that library's sources are not in this repository at all — so
    # there is nothing to walk towards and everything to walk into. Asking whether the
    # entry is a directory tests the thing itself; `origin` does not, because a reactor
    # SIBLING carries a coordinate too (`com.macro.mall:mall-mbg`) and is exactly the case
    # this function exists for. Without this the fixture's own opted-in jar was walked on
    # every export — from `~/.m2/repository` up through the home directory to `/`, testing
    # `<ancestor>/<source root>/<package path>` at each — and any unrelated file sharing
    # that package path would have been published as this symbol's source.
    if not entry.is_dir():
        return None
    # **Absolute only.** A RELATIVE `origin_entry` is anchored on the directory `analyze`
    # ran in, which the bundle does not record — resolving it here would anchor it on the
    # EXPORTING process's directory instead, and two exports from two directories would
    # place the same symbol differently (NFR-1). It is also never needed: a relative entry
    # is this run's own module, which the first branch above already placed.
    if not entry.is_absolute():
        return None
    # Bounded by the reactor rather than by the filesystem. A sibling module sits beside
    # this one, so its root is under this module's PARENT; the walk stops there rather
    # than continuing to `/`, where an ancestor holding a same-package file would be taken
    # on nothing but the coincidence of the package name.
    boundary = module_root.resolve().parent
    for ancestor in entry.resolve().parents:
        if not ancestor.is_relative_to(boundary):
            break
        for root in source_roots:
            candidate = ancestor / root / relative_path
            if not candidate.is_file():
                continue
            try:
                relative = Path(os.path.relpath(candidate, module_root.resolve()))
            except ValueError:
                # Different drives on Windows: no relative path exists, so there is
                # nothing portable to publish.
                return None
            return relative.as_posix()
    return None


def _symbol_records(located: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Index 1: symbol -> file, line range, kind, enclosing. Pays for every other."""
    return [{"symbol": symbol, **location} for symbol, location in sorted(located.items())]


def _caller_records(
    call_edges: Sequence[dict[str, object]], located: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    """Index 2a: who CALLS this — resolved, not text.

    Keyed on the CALLEE, which is the direction `call_edges` does not store: the table is
    caller-major, so "who calls X" is a scan there and a lookup here. Rows with no callee
    are dropped: the call reached a body this workspace never read, so there is nothing to
    be a caller OF.
    """
    reverse: dict[str, set[str]] = {}
    for edge in call_edges:
        callee = edge["callee"]
        if callee is None:
            continue
        reverse.setdefault(str(callee), set()).add(str(edge["caller"]))
    return [
        {
            "symbol": callee,
            "called_by": [{"symbol": caller, **_at(located, caller)} for caller in sorted(callers)],
        }
        for callee, callers in sorted(reverse.items())
    ]


def _implementor_records(
    implementations: Sequence[dict[str, object]], located: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    """Index 2b: who IMPLEMENTS this interface.

    Also the reverse of what is stored — the fact names a type and the interfaces it
    implements — and it carries every interface named, including ones this workspace never
    scanned: "who implements this marker interface from a jar" is a real question about a
    types even where the interface itself is a jar nobody opened.
    """
    reverse: dict[str, set[str]] = {}
    for row in implementations:
        for interface in json.loads(str(row["interfaces"] or "[]")):
            reverse.setdefault(str(interface), set()).add(str(row["symbol"]))
    return [
        {
            "symbol": interface,
            "implemented_by": [
                {"symbol": child, **_at(located, child)} for child in sorted(children)
            ],
        }
        for interface, children in sorted(reverse.items())
    ]


def _annotated_records(
    annotations: Sequence[dict[str, object]],
    located: dict[str, dict[str, Any]],
    paths: dict[str, str | None],
) -> list[dict[str, Any]]:
    """Index 2c: which declarations carry this annotation.

    The target may be a type, a method or a field, so the record carries whatever the
    location index knows about it rather than assuming a class.
    """
    reverse: dict[str, set[str]] = {}
    by_target: dict[str, dict[str, object]] = {}
    for row in annotations:
        reverse.setdefault(str(row["annotation"]), set()).add(str(row["target"]))
        by_target.setdefault(str(row["target"]), row)
    return [
        {
            "annotation": annotation,
            "on": [
                {"symbol": target, **_placed(located, paths, by_target[target], target)}
                for target in sorted(targets)
            ],
        }
        for annotation, targets in sorted(reverse.items())
    ]


def _placed(
    located: dict[str, dict[str, Any]],
    paths: dict[str, str | None],
    row: dict[str, object],
    target: str,
) -> dict[str, Any]:
    """One annotation target's location, falling back to its DOCUMENT's file where the
    target is not a symbol — see `_annotation_file`. The line stays null: a document knows
    which file, never where in it."""
    location = _at(located, target)
    if location["file"] is None:
        location["file"] = paths.get(str(row.get("document_id")))
    return location


def _shape_carrier_records(
    endpoints: Sequence[dict[str, object]],
    lookup: dict[str, dict[str, Any]],
    redactor: Redactor,
) -> list[dict[str, Any]]:
    """Index 2d: which endpoints CARRY this shape, and on which side.

    Request and response are kept apart rather than folded into "mentions": "who accepts an
    `OrderRequest`" and "who returns one" are different questions, and an index that could
    only answer their union would send a reader to read both.
    """
    reverse: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for endpoint in endpoints:
        for side in ("request_shape", "response_shape"):
            declared = endpoint[side]
            if not declared:
                continue
            shape_id = json.loads(str(declared)).get("shape_id")
            if not shape_id:
                continue
            entry = reverse.setdefault(str(shape_id), {"request": [], "response": []})
            entry[side.removesuffix("_shape")].append(
                {
                    "protocol": endpoint["protocol"],
                    "direction": endpoint["direction"],
                    "method": endpoint["method"],
                    # The exit's mask, the same one `graph/endpoints.parquet` applies to
                    # this column: an address can carry credentials in front of it.
                    "path": _address(endpoint["path"], redactor),
                    # PLACED, like every other index's answer. This file shipped the two
                    # symbols bare, which made it the one index whose hit was not a
                    # complete answer — a reader had to look the handler up in
                    # `symbols.ndjson` to do anything with it.
                    "handler": endpoint["handler"],
                    "handler_at": _at_or_none(lookup, endpoint["handler"]),
                    "caller": endpoint["caller"],
                    "caller_at": _at_or_none(lookup, endpoint["caller"]),
                }
            )
    return [
        {
            "shape_id": shape_id,
            "request": sorted(sides["request"], key=lambda row: json.dumps(row, sort_keys=True)),
            "response": sorted(sides["response"], key=lambda row: json.dumps(row, sort_keys=True)),
        }
        for shape_id, sides in sorted(reverse.items())
    ]


def _address_records(
    roots: Sequence[dict[str, object]],
    located: dict[str, dict[str, Any]],
    redactor: Redactor,
) -> list[dict[str, Any]]:
    """Index 3: `GET /order/list` -> root -> handler -> `file:line`.

    **The agent starts from what a human said.** A person names a route, not a symbol, and
    every other index in this file needs a symbol to begin — so without this one the bundle
    still cannot answer the question anybody actually asks first.

    Built from `roots` rather than `endpoints`: a root is where a trace begins, which is
    what a reader wants to reach, and `roots` already carries the wire identity each
    handler is reached by. A handler serving three addresses is three records, and one
    address is one record however the handler is spelled.
    """
    return sorted(
        (
            {
                "protocol": root["protocol"],
                "method": root["method"],
                # Masked, exactly as `graph/roots.parquet`'s own column is.
                "path": _address(root["path"], redactor),
                "root_kind": root["root_kind"],
                "handler": str(root["handler"]),
                **_at(located, str(root["handler"])),
            }
            for root in roots
        ),
        key=lambda record: json.dumps(record, sort_keys=True),
    )


def _at_or_none(lookup: dict[str, dict[str, Any]], symbol: object) -> dict[str, Any] | None:
    """`_at` for a column that may be NULL. An endpoint carries a handler OR a caller, so
    one of the two is absent on every row and a location for it would be an answer to a
    question nobody asked."""
    return None if symbol is None else _at(lookup, str(symbol))


def _address(value: object, redactor: Redactor) -> str | None:
    """One address column through the exit's redactor, NULL left as NULL.

    `redact_text` rather than `redact_value`: an address is not a configuration key, and
    what it carries when it carries anything is userinfo in front of a host — which is the
    rule `graph/`'s own `_REDACTED_ADDRESSES` map applies to these same columns.
    """
    return None if value is None else redactor.redact_text(str(value))


def _file_records(
    located: dict[str, dict[str, Any]],
    lookup: dict[str, dict[str, Any]],
    annotations: Sequence[dict[str, object]],
    paths: dict[str, str | None],
) -> list[dict[str, Any]]:
    """Index 4: per FILE — what it declares, and which annotations appear in it.

    **The cheapest win, and the one an agent's budget actually goes on.** Most of what an
    assistant spends is files opened and discarded; this is the record that lets it decide
    NOT to open one. A file with no annotation the reader cares about and no symbol it is
    looking for can be skipped without being read.

    Keyed on the resolved path, so a file nothing could place contributes nothing — there
    is no decision to support about a file the reader cannot open. Counts and sorted name
    lists rather than the symbols themselves: `symbols.ndjson` already carries every symbol
    with its own location, and repeating them here would double the index to say a second
    time what one grep already answers.

    **Built from the DOCUMENTS, not from the placed symbols.** The first version iterated
    symbols, which made the real criterion "declares nothing" rather than "cannot be
    placed" — so every `package-info` file was dropped: 3 in the fixture, 14 in
    `jhipster-sample-app`, 4 in `spring-petclinic-rest`, each opening perfectly well and
    each carrying the package-scope nullness rule that governs every type beside it. A
    digest is a fact about a FILE, and a file that declares nothing is exactly the file an
    agent most wants to be told it can skip.
    """
    annotated: dict[str, set[str]] = {}
    for row in annotations:
        path = _annotation_file(row, lookup, paths)
        if path is None:
            continue
        annotated.setdefault(path, set()).add(str(row["annotation"]))
    files: dict[str, dict[str, Any]] = {
        str(path): {"file": str(path), "declares": {}, "symbols": 0, "annotations": []}
        for path in paths.values()
        if path is not None
    }
    for symbol, location in located.items():
        path = location["file"]
        if path is None:
            continue
        entry = files[str(path)]
        entry["symbols"] += 1
        kind = str(location["kind"])
        entry["declares"][kind] = int(entry["declares"].get(kind, 0)) + 1
        del symbol
    for path, entry in files.items():
        # Sorted for the reader of this dict IN PROCESS; no test can tell the difference,
        # because the writer below serialises every record with `sort_keys=True` and that
        # fixes the key order in the bytes whatever this does. Kept rather than removed so
        # the structure says what it means, and recorded here so nobody adds a test for it
        # and concludes the ordering is checked.
        entry["declares"] = dict(sorted(entry["declares"].items()))
        entry["annotations"] = sorted(annotated.get(path, ()))
    return [files[path] for path in sorted(files)]


def _annotation_file(
    row: dict[str, object],
    lookup: dict[str, dict[str, Any]],
    paths: dict[str, str | None],
) -> str | None:
    """Which file carries one annotation use — the target's own, or the DOCUMENT's where
    the target is not a symbol.

    A package declaration (`…/package-info#`) has no symbol row, so `NullMarked` — the
    scope rule that governs every type in the package — placed nowhere. The document
    always knows, and for a declaration annotation the two answers are the same file.
    """
    location = lookup.get(str(row["target"]))
    if location is not None and location["file"] is not None:
        return str(location["file"])
    return paths.get(str(row.get("document_id")))


def _impact_records(
    shapes: Sequence[dict[str, object]],
    shape_fields: Sequence[dict[str, object]],
    endpoints: Sequence[dict[str, object]],
    located: dict[str, dict[str, Any]],
    redactor: Redactor,
) -> list[dict[str, Any]]:
    """Index 5: "change `Order`" — the shape, its fields, the endpoints carrying it and
    the handlers and callers of those, as a list ready to open.

    **One record per contract type, because that is the unit a person names.** Nobody says
    "change `com/acme/OrderView#totalAmount`"; they say "change `Order`", and what they
    need back is every place that decision reaches. Assembling it here rather than leaving
    a consumer to join four other index files is the whole value: the join is the work, and
    it is the same join every time.

    `endpoints` carries the wire identities, already masked; `handlers` and `callers` are
    the symbols on those rows, PLACED, because a list of symbols an agent then has to look
    up one by one is a list it has to make six more requests about.
    """
    described = {str(shape["shape_id"]) for shape in shapes}
    fields: dict[str, list[str]] = {}
    for row in shape_fields:
        fields.setdefault(str(row["shape_id"]), []).append(str(row["wire_name"]))
    carried: dict[str, list[dict[str, Any]]] = {}
    for endpoint in endpoints:
        for side in ("request_shape", "response_shape"):
            declared = endpoint[side]
            if not declared:
                continue
            shape_id = json.loads(str(declared)).get("shape_id")
            if not shape_id:
                continue
            carried.setdefault(str(shape_id), []).append(
                {
                    "side": side.removesuffix("_shape"),
                    "protocol": endpoint["protocol"],
                    "direction": endpoint["direction"],
                    "method": endpoint["method"],
                    "path": _address(endpoint["path"], redactor),
                    "handler": endpoint["handler"],
                    "caller": endpoint["caller"],
                }
            )
    records: list[dict[str, Any]] = []
    for shape_id in sorted(described):
        # The TYPE, not the parameterised id: a shape's own declaration is where a change
        # is made, and `CommonResult#<OrderView#>` is a use of two of them.
        symbol = _unparameterised_id(shape_id)
        on_the_wire = sorted(
            carried.get(shape_id, []), key=lambda row: json.dumps(row, sort_keys=True)
        )
        reached = sorted(
            {
                str(row[which])
                for row in on_the_wire
                for which in ("handler", "caller")
                if row[which] is not None
            }
        )
        records.append(
            {
                "shape_id": shape_id,
                "declared_at": _at(located, symbol),
                "fields": sorted(fields.get(shape_id, ())),
                "endpoints": on_the_wire,
                "reached_from": [{"symbol": s, **_at(located, s)} for s in reached],
            }
        )
    return records


def _unparameterised_id(shape_id: str) -> str:
    """A shape id with its bound arguments dropped, which is the symbol a declaration
    lives at. Four characters rather than a shared helper: `egress/render`'s own copy
    answers a different question — which shape id in a diagram IS this ancestor — and the
    seam these two files really share, `domain/symbols`, has no shape-id grammar in it."""
    return shape_id.split("<", 1)[0]


def _at(located: dict[str, dict[str, Any]], symbol: str) -> dict[str, Any]:
    """Where `symbol` is, or an all-NULL location for one this workspace never scanned.

    The keys are always present, so a consumer reads `record["file"]` without testing for
    it and a missing location reads as "not known" rather than as "not asked". A call into
    a third-party jar is the ordinary case: the caller is placed and the callee is not.

    `_locations` keys every symbol under BOTH spellings, so a caller holding either finds
    it — see there for why.
    """
    location = located.get(symbol)
    if location is None:
        return {"file": None, "line": None, "line_end": None, "kind": None, "enclosing": None}
    return dict(location)


__all__ = ["write_index"]
