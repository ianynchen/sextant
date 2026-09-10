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

# One record per line, and the files are written in a fixed order with their rows sorted,
# so two exports of one workspace are byte-identical (NFR-1).
_SYMBOLS = "symbols.ndjson"
_CALLERS = "callers.ndjson"
_IMPLEMENTORS = "implementors.ndjson"
_ANNOTATED = "annotated.ndjson"
_SHAPE_CARRIERS = "shape_carriers.ndjson"
_ADDRESSES = "addresses.ndjson"


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
    source_roots: Sequence[str],
    module_root: Path,
) -> list[str]:
    """Writes `index/*.ndjson` into `bundle` and returns the file names written.

    Every index is derived from tables the bundle already ships, so nothing here is a new
    claim: an index that disagreed with `graph/` would be a second answer to a question the
    tables already settle. What it adds is the JOIN a consumer would otherwise perform —
    symbol to document to source root — and the reverse direction of edges the tables store
    one way round.
    """
    located = _locations(symbols, documents, source_roots, module_root)
    index = bundle / "index"
    index.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for name, records in (
        (_SYMBOLS, _symbol_records(located)),
        (_CALLERS, _caller_records(call_edges, located)),
        (_IMPLEMENTORS, _implementor_records(implementations, located)),
        (_ANNOTATED, _annotated_records(annotations, located)),
        (_SHAPE_CARRIERS, _shape_carrier_records(endpoints)),
        (_ADDRESSES, _address_records(roots, located)),
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
) -> dict[str, dict[str, Any]]:
    """Every symbol's `{file, line, line_end, kind, enclosing}`, keyed by symbol.

    Built once and shared by every index below, because each of them answers with a
    location and re-deriving it per index is where two indexes come to disagree.
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
        found[str(symbol["symbol"])] = {
            "file": paths.get(str(symbol["document_id"])),
            # NULL, not 0, and not the first line of the first method: a class file states
            # no declaration line for a type or a field, so there is nothing to report and
            # a number here would be a claim about where the DECLARATION is.
            "line": start or None,
            "line_end": end or None,
            "kind": str(symbol["construct_kind"]),
            "enclosing": symbol["enclosing"],
        }
    return found


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
    how deep that sits is the build tool's business: one writes `target/classes` and another
    one build tool writes two levels down and another four. Walking up from the classes
    directory and asking "does this ancestor hold the file under one of the source roots"
    answers for both without either being named here — and the file's own existence is
    what stops the walk, so an ancestor that merely looks plausible is never taken.
    """
    if origin_entry is None:
        return None
    for ancestor in Path(str(origin_entry)).resolve().parents:
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
    annotations: Sequence[dict[str, object]], located: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    """Index 2c: which declarations carry this annotation.

    The target may be a type, a method or a field, so the record carries whatever the
    location index knows about it rather than assuming a class.
    """
    reverse: dict[str, set[str]] = {}
    for row in annotations:
        reverse.setdefault(str(row["annotation"]), set()).add(str(row["target"]))
    return [
        {
            "annotation": annotation,
            "on": [{"symbol": target, **_at(located, target)} for target in sorted(targets)],
        }
        for annotation, targets in sorted(reverse.items())
    ]


def _shape_carrier_records(endpoints: Sequence[dict[str, object]]) -> list[dict[str, Any]]:
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
                    "path": endpoint["path"],
                    "handler": endpoint["handler"],
                    "caller": endpoint["caller"],
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
    roots: Sequence[dict[str, object]], located: dict[str, dict[str, Any]]
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
                "path": root["path"],
                "root_kind": root["root_kind"],
                "handler": str(root["handler"]),
                **_at(located, str(root["handler"])),
            }
            for root in roots
        ),
        key=lambda record: json.dumps(record, sort_keys=True),
    )


def _at(located: dict[str, dict[str, Any]], symbol: str) -> dict[str, Any]:
    """Where `symbol` is, or an all-NULL location for one this workspace never scanned.

    The keys are always present, so a consumer reads `record["file"]` without testing for
    it and a missing location reads as "not known" rather than as "not asked". A call into
    a third-party jar is the ordinary case: the caller is placed and the callee is not.
    """
    location = located.get(symbol)
    if location is None:
        return {"file": None, "line": None, "line_end": None, "kind": None, "enclosing": None}
    return dict(location)


__all__ = ["write_index"]
