"""The index bundle (F8 §9.3, W35) — where, not only what.

Every test here builds its own tiny source tree under `tmp_path`, because the thing under
test is a JOIN against files on disk: a path that resolves against nothing is the failure
mode, and a test that never touched a filesystem could not tell a resolved path from an
invented one.

The shipped index's live numbers are measured on the four corpora and recorded in
COVERAGE §3a-xii.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from sextant.domain.redaction import Redactor
from sextant.egress.export.index import write_index

_MODULE = "sextant-jvm maven com.acme/orders-service 1.0.0 "
_API = _MODULE + "com/acme/Api#"
_LIST = _MODULE + "com/acme/Api#list()."


def _symbol(
    symbol: str,
    document_id: str = "doc",
    kind: str = "method",
    enclosing: str | None = _API,
    line_start: int = 41,
    line_end: int = 44,
) -> dict[str, object]:
    return {
        "symbol": symbol,
        "document_id": document_id,
        "construct_kind": kind,
        "enclosing": enclosing,
        "line_start": line_start,
        "line_end": line_end,
    }


def _tree(tmp_path: Path, *files: str) -> Path:
    """A module root with `files` written under it, so a resolved path is a path that
    really opens."""
    for name in files:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("// source\n", encoding="utf-8")
    return tmp_path


def _write(tmp_path: Path, **overrides: object) -> dict[str, list[dict]]:
    """Runs `write_index` with empty defaults for everything not named, and reads the
    files back."""
    bundle = tmp_path / "bundle"
    arguments: dict[str, object] = {
        "symbols": [],
        "documents": [],
        "call_edges": [],
        "implementations": [],
        "annotations": [],
        "endpoints": [],
        "roots": [],
        "shapes": [],
        "shape_fields": [],
        "source_roots": ["src/main/java"],
        "module_root": tmp_path,
        "redactor": Redactor.from_rules(),
    }
    arguments.update(overrides)
    names = write_index(bundle, **arguments)  # type: ignore[arg-type]
    return {
        name.removesuffix(".ndjson"): [
            json.loads(line) for line in (bundle / "index" / name).read_text().splitlines()
        ]
        for name in names
    }


def test_a_symbol_resolves_to_a_file_that_opens(tmp_path: Path):
    """The whole point of the wave: Sextant could say WHAT exists and never WHERE.

    `documents.relative_path` is a package path, openable against nothing on its own; the
    module's `source_roots` are what it is relative TO, and joining them is what turns a
    symbol into something an agent can open.
    """
    root = _tree(tmp_path, "src/main/java/com/acme/Api.java")
    index = _write(
        root,
        symbols=[_symbol(_LIST)],
        documents=[
            {"document_id": "doc", "relative_path": "com/acme/Api.java", "origin_entry": None}
        ],
    )

    [record] = index["symbols"]
    assert record["file"] == "src/main/java/com/acme/Api.java"
    assert (root / record["file"]).is_file()
    assert (record["line"], record["line_end"]) == (41, 44)


def test_a_root_that_does_not_hold_the_file_is_not_guessed(tmp_path: Path):
    """The roots are TRIED, not assumed. A module with two of them puts each class under
    exactly one, and the file's existence is what says which — a first-root guess would
    publish a path that opens nothing, which a consumer acts on before discovering."""
    root = _tree(tmp_path, "src/main/kotlin/com/acme/Api.java")
    index = _write(
        root,
        symbols=[_symbol(_LIST)],
        documents=[
            {"document_id": "doc", "relative_path": "com/acme/Api.java", "origin_entry": None}
        ],
        source_roots=["src/main/java", "src/main/kotlin"],
    )

    assert index["symbols"][0]["file"] == "src/main/kotlin/com/acme/Api.java"


def test_a_symbol_no_root_holds_says_so_rather_than_pointing_nowhere(tmp_path: Path):
    """None, not a path. Generated sources are the live case — `AuditEvent.java` is
    written into the build directory, not into a declared source root — and a null that a
    consumer must ask about beats a path it would open and find missing."""
    index = _write(
        tmp_path,
        symbols=[_symbol(_LIST)],
        documents=[
            {"document_id": "doc", "relative_path": "com/acme/Api.java", "origin_entry": None}
        ],
    )

    assert index["symbols"][0]["file"] is None


def test_a_sibling_modules_symbol_is_placed_through_its_own_root(tmp_path: Path):
    """The difference between an index that works on a reactor and one that does not.

    A sibling's sources are under the SIBLING's root, which this module's roots reach not
    at all: measured before this, the index placed 157 of `mall-admin`'s 648 documents —
    every one of its own and not a symbol of the four reactor siblings it scans, 1,428 of
    25,521. `origin_entry` names the classes directory each document was read from, and
    the module root above it is searched for rather than computed, because how deep that
    sits is the build tool's business (`target/classes` against
    `build/classes/java/main`).
    """
    root = _tree(
        tmp_path / "mall-admin",
        "src/main/java/com/acme/Api.java",
    )
    _tree(tmp_path / "mall-common", "src/main/java/com/acme/Common.java")
    # The classes DIRECTORY has to exist: that is what tells a reactor sibling from a jar,
    # and a jar's own path is where an unbounded walk goes wrong.
    (tmp_path / "mall-common" / "target" / "classes").mkdir(parents=True)
    index = _write(
        root,
        symbols=[_symbol(_MODULE + "com/acme/Common#get().", document_id="sibling")],
        documents=[
            {
                "document_id": "sibling",
                "relative_path": "com/acme/Common.java",
                "origin_entry": str(tmp_path / "mall-common" / "target" / "classes"),
            }
        ],
    )

    assert index["symbols"][0]["file"] == "../mall-common/src/main/java/com/acme/Common.java"
    assert (root / index["symbols"][0]["file"]).is_file()


def test_no_index_record_carries_an_absolute_path(tmp_path: Path):
    """A bundle travels, and an absolute path names a directory that exists on exactly one
    computer. A sibling comes back relative even though the only thing naming it —
    `origin_entry` — is absolute."""
    root = _tree(tmp_path / "mod", "src/main/java/com/acme/Api.java")
    _tree(tmp_path / "other", "src/main/java/com/acme/Other.java")
    (tmp_path / "other" / "target" / "classes").mkdir(parents=True)
    index = _write(
        root,
        symbols=[
            _symbol(_LIST),
            _symbol(_MODULE + "com/acme/Other#go().", document_id="sibling"),
        ],
        documents=[
            {"document_id": "doc", "relative_path": "com/acme/Api.java", "origin_entry": None},
            {
                "document_id": "sibling",
                "relative_path": "com/acme/Other.java",
                "origin_entry": str(tmp_path / "other" / "target" / "classes"),
            },
        ],
    )

    for record in index["symbols"]:
        assert not str(record["file"]).startswith("/"), record


def test_a_type_carries_no_line_because_the_class_file_states_none(tmp_path: Path):
    """`LineNumberTable` is per METHOD BODY (JVMS 4.7.12). A type and a field carry none —
    measured on `mall-admin`, every one of 509 classes, 132 interfaces and 2,000 fields —
    so the record says NULL rather than 0, and rather than borrowing the first line of the
    first method, which is where that METHOD is."""
    root = _tree(tmp_path, "src/main/java/com/acme/Api.java")
    index = _write(
        root,
        symbols=[
            _symbol(_API, kind="class", enclosing=None, line_start=0, line_end=0),
            _symbol(_LIST),
        ],
        documents=[
            {"document_id": "doc", "relative_path": "com/acme/Api.java", "origin_entry": None}
        ],
    )

    by_symbol = {record["symbol"]: record for record in index["symbols"]}
    assert by_symbol[_API]["line"] is None and by_symbol[_API]["line_end"] is None
    # The file is still known: WHERE the class is declared is unreadable, which file holds
    # it is not.
    assert by_symbol[_API]["file"] == "src/main/java/com/acme/Api.java"
    assert by_symbol[_LIST]["line"] == 41


def test_the_caller_index_reverses_the_edge_the_table_stores_one_way(tmp_path: Path):
    """`call_edges` is caller-major, so "who calls X" is a scan there and a lookup here —
    which is the whole reason a reverse index exists at all."""
    root = _tree(tmp_path, "src/main/java/com/acme/Api.java")
    index = _write(
        root,
        symbols=[_symbol(_LIST)],
        documents=[
            {"document_id": "doc", "relative_path": "com/acme/Api.java", "origin_entry": None}
        ],
        call_edges=[
            {"caller": _LIST, "callee": _MODULE + "com/acme/Service#run()."},
            {"caller": _LIST, "callee": None},
        ],
    )

    [record] = index["callers"]
    assert record["symbol"] == _MODULE + "com/acme/Service#run()."
    # The caller is PLACED, which is what makes the answer actionable.
    assert record["called_by"][0]["file"] == "src/main/java/com/acme/Api.java"
    assert record["called_by"][0]["line"] == 41


def test_an_edge_with_no_callee_is_not_a_caller_of_anything(tmp_path: Path):
    """A call that reached a body this workspace never read has nothing to be a caller OF,
    so it contributes no record — as opposed to a record keyed on null, which every
    boundary call in the module would then share."""
    index = _write(
        tmp_path,
        call_edges=[{"caller": _LIST, "callee": None}],
    )

    assert index["callers"] == []


def test_an_unscanned_callee_still_gets_a_record_with_a_null_location(tmp_path: Path):
    """The keys are always present, so a consumer reads `record["file"]` without testing
    for it. A call into a third-party jar is the ordinary case: the caller is placed and
    the callee is not, and "not known" must not read as "not asked"."""
    index = _write(
        tmp_path,
        call_edges=[{"caller": _LIST, "callee": _MODULE + "com/acme/Gone#go()."}],
    )

    [record] = index["callers"]
    assert record["called_by"][0]["file"] is None
    assert set(record["called_by"][0]) == {
        "symbol",
        "file",
        "line",
        "line_end",
        "kind",
        "enclosing",
    }


def test_the_address_index_answers_what_a_human_actually_says(tmp_path: Path):
    """`GET /order/list` -> handler -> `file:line`.

    A person names a route, not a symbol, and every other index needs a symbol to begin —
    so without this one the bundle cannot answer the question anybody asks first.
    """
    root = _tree(tmp_path, "src/main/java/com/acme/Api.java")
    index = _write(
        root,
        symbols=[_symbol(_LIST)],
        documents=[
            {"document_id": "doc", "relative_path": "com/acme/Api.java", "origin_entry": None}
        ],
        roots=[
            {
                "handler": _LIST,
                "root_kind": "inbound_endpoint",
                "protocol": "http",
                "method": "GET",
                "path": "/order/list",
            }
        ],
    )

    [record] = index["addresses"]
    assert (record["method"], record["path"]) == ("GET", "/order/list")
    assert record["file"] == "src/main/java/com/acme/Api.java"
    assert record["line"] == 41


def test_a_shape_is_indexed_by_the_side_it_travels_on(tmp_path: Path):
    """ "Who ACCEPTS an `OrderRequest`" and "who RETURNS one" are different questions, and
    an index that could only answer their union would send a reader to read both."""
    index = _write(
        tmp_path,
        endpoints=[
            {
                "protocol": "http",
                "direction": "inbound",
                "method": "POST",
                "path": "/orders",
                "handler": _LIST,
                "caller": None,
                "request_shape": json.dumps({"shape_id": "com/acme/OrderRequest#"}),
                "response_shape": json.dumps({"shape_id": "com/acme/OrderView#"}),
            }
        ],
    )

    by_shape = {record["shape_id"]: record for record in index["shape_carriers"]}
    assert (
        by_shape["com/acme/OrderRequest#"]["request"]
        and not (by_shape["com/acme/OrderRequest#"]["response"])
    )
    assert (
        by_shape["com/acme/OrderView#"]["response"]
        and not (by_shape["com/acme/OrderView#"]["request"])
    )


def test_the_implementor_index_keeps_an_unscanned_interface(tmp_path: Path):
    """ "Who implements `java.io.Serializable`" is a real question about THIS module's types
    even where the interface itself is a jar nobody opened, so the index is keyed on every
    interface NAMED rather than on every interface scanned."""
    index = _write(
        tmp_path,
        implementations=[
            {"symbol": _API, "interfaces": json.dumps(["java/io/Serializable#"])},
        ],
    )

    [record] = index["implementors"]
    assert record["symbol"] == "java/io/Serializable#"
    assert record["implemented_by"][0]["symbol"] == _API


def test_two_exports_of_one_workspace_are_byte_identical(tmp_path: Path):
    """NFR-1. Every file is written in a fixed order with its rows sorted, so a bundle
    committed to a repository does not churn between runs that found the same thing."""
    root = _tree(tmp_path, "src/main/java/com/acme/Api.java")
    arguments: dict[str, object] = {
        "symbols": [_symbol(_LIST), _symbol(_API, kind="class", enclosing=None)],
        "documents": [
            {"document_id": "doc", "relative_path": "com/acme/Api.java", "origin_entry": None}
        ],
        "call_edges": [
            {"caller": _LIST, "callee": _MODULE + "com/acme/B#b()."},
            {"caller": _API, "callee": _MODULE + "com/acme/B#b()."},
        ],
        "source_roots": ["src/main/java"],
        "module_root": root,
        "redactor": Redactor.from_rules(),
    }
    first = write_index(
        root / "one",
        implementations=[],
        annotations=[],
        endpoints=[],
        roots=[],
        shapes=[],
        shape_fields=[],
        **arguments,  # type: ignore[arg-type]
    )
    second = write_index(
        root / "two",
        implementations=[],
        annotations=[],
        endpoints=[],
        roots=[],
        shapes=[],
        shape_fields=[],
        **arguments,  # type: ignore[arg-type]
    )

    assert first == second
    for name in first:
        assert (root / "one" / "index" / name).read_bytes() == (
            root / "two" / "index" / name
        ).read_bytes()


def test_an_address_is_masked_on_the_way_into_the_index(tmp_path: Path):
    """The index is an EXIT, and every exit masks (2K design §1).

    It reads the same rows `graph/` does, so an address published unmasked here is the same
    bytes the parquet beside it takes trouble to strip. Measured before this was wired: a
    root at `https://user:hunter2@internal.example.com/orders` reached `addresses.ndjson`
    whole while `graph/roots.parquet` held `https://internal.example.com/orders` — one
    bundle, two answers, and the credential in the greppable one.
    """
    index = _write(
        tmp_path,
        roots=[
            {
                "handler": _LIST,
                "root_kind": "inbound_endpoint",
                "protocol": "http",
                "method": "GET",
                "path": "https://user:hunter2@internal.example.com/orders",
            }
        ],
        endpoints=[
            {
                "protocol": "http",
                "direction": "outbound",
                "method": "POST",
                "path": "https://svc:s3cr3t@billing.example.com/charge",
                "handler": None,
                "caller": _LIST,
                "request_shape": json.dumps({"shape_id": "com/acme/Req#"}),
                "response_shape": None,
            }
        ],
    )

    [address] = index["addresses"]
    assert address["path"] == "https://internal.example.com/orders"
    [carrier] = index["shape_carriers"]
    assert carrier["request"][0]["path"] == "https://billing.example.com/charge"
    # And nothing else in the bundle carries either secret.
    assert "hunter2" not in json.dumps(index) and "s3cr3t" not in json.dumps(index)


def test_a_null_address_stays_null_rather_than_becoming_a_string(tmp_path: Path):
    """The near-miss for the mask. A root with no address — a scheduled job — must not come
    back as `"None"`, which is what a redactor handed `str(None)` would produce."""
    index = _write(
        tmp_path,
        roots=[
            {
                "handler": _LIST,
                "root_kind": "scheduled",
                "protocol": "",
                "method": None,
                "path": None,
            }
        ],
    )

    assert index["addresses"][0]["path"] is None


def test_the_file_digest_says_what_a_file_holds_without_opening_it(tmp_path: Path):
    """Index 4, and the cheapest win in the bundle: most of what an assistant spends goes
    on files opened and discarded, so the record that lets it decide NOT to open one pays
    for itself first.

    Counts and sorted annotation names rather than the symbols themselves — `symbols` already
    carries every symbol with its own location, and repeating them here would double the
    index to answer a second time what one grep already answers.
    """
    root = _tree(tmp_path, "src/main/java/com/acme/Api.java")
    index = _write(
        root,
        symbols=[
            _symbol(_API, kind="class", enclosing=None, line_start=0, line_end=0),
            _symbol(_LIST),
            _symbol(_MODULE + "com/acme/Api#get().", line_start=50, line_end=52),
        ],
        documents=[
            {"document_id": "doc", "relative_path": "com/acme/Api.java", "origin_entry": None}
        ],
        annotations=[
            {"target": _API, "annotation": "org/x/RestController#", "document_id": "doc"},
            {"target": _LIST, "annotation": "org/x/GetMapping#", "document_id": "doc"},
        ],
    )

    [record] = index["files"]
    assert record["file"] == "src/main/java/com/acme/Api.java"
    assert record["declares"] == {"class": 1, "method": 2}
    assert record["annotations"] == ["org/x/GetMapping#", "org/x/RestController#"]
    assert record["symbols"] == 3


def test_a_file_nothing_could_place_is_not_a_digest_record(tmp_path: Path):
    """There is no decision to support about a file the reader cannot open, so an
    unplaced document contributes nothing rather than a record keyed on null — which every
    generated class in the module would otherwise share."""
    index = _write(
        tmp_path,
        symbols=[_symbol(_LIST)],
        documents=[
            {"document_id": "doc", "relative_path": "com/acme/Api.java", "origin_entry": None}
        ],
    )

    assert index["files"] == []


def test_change_impact_assembles_the_join_a_consumer_would_otherwise_make(tmp_path: Path):
    """Index 5. Nobody says "change `com/acme/OrderView#totalAmount`"; they say "change
    `Order`", and what they need back is every place that decision reaches — the shape,
    its fields, the endpoints carrying it, and the handlers and callers of those, each
    already placed.

    Assembling it here rather than leaving a consumer to join four other index files is
    the whole value: the join is the work, and it is the same join every time.
    """
    root = _tree(tmp_path, "src/main/java/com/acme/Api.java")
    index = _write(
        root,
        symbols=[
            # Module-PREFIXED, as the scanner emits it, while the shape id below is bare:
            # that mismatch is the thing the lookup has to bridge.
            _symbol(
                _MODULE + "com/acme/Order#",
                kind="class",
                enclosing=None,
                line_start=0,
                line_end=0,
            ),
            _symbol(_LIST),
        ],
        documents=[
            {"document_id": "doc", "relative_path": "com/acme/Api.java", "origin_entry": None}
        ],
        shapes=[{"shape_id": "com/acme/Order#", "open": False}],
        shape_fields=[
            {"shape_id": "com/acme/Order#", "wire_name": "total"},
            {"shape_id": "com/acme/Order#", "wire_name": "id"},
        ],
        endpoints=[
            {
                "protocol": "http",
                "direction": "inbound",
                "method": "POST",
                "path": "/orders",
                "handler": _LIST,
                "caller": None,
                "request_shape": json.dumps({"shape_id": "com/acme/Order#"}),
                "response_shape": None,
            }
        ],
    )

    [record] = index["impact"]
    assert record["shape_id"] == "com/acme/Order#"
    # The DECLARATION is placed, which is where the change is made. A shape id is a bare
    # descriptor and a symbol carries module coordinates; looking up only the whole
    # spelling reported every contract in the index undeclared.
    assert record["declared_at"]["file"] == "src/main/java/com/acme/Api.java"
    assert record["fields"] == ["id", "total"]
    assert [(e["side"], e["path"]) for e in record["endpoints"]] == [("request", "/orders")]
    # And the handler is placed too — a list of symbols an agent must then look up one by
    # one is a list it has to make six more requests about.
    assert record["reached_from"][0]["file"] == "src/main/java/com/acme/Api.java"
    assert record["reached_from"][0]["line"] == 41


def test_a_parameterised_shape_is_declared_where_its_type_is(tmp_path: Path):
    """`CommonResult<OrderView>` is a USE of two declarations, not a third one.

    The record keeps the parameterised id — that is the thing on the wire — but places it
    at the type, because that is the file a change is made in. Without the trim the
    declaration lookup misses and a generic wrapper, which is every one of `mall-admin`'s
    result envelopes, reports itself undeclared.

    And a `caller` of NULL is an inbound endpoint nothing in this module calls; it is
    dropped rather than written as a `None` symbol with no location.
    """
    root = _tree(tmp_path, "src/main/java/com/acme/Api.java")
    parameterised = "com/acme/CommonResult#<com/acme/OrderView#>"
    index = _write(
        root,
        symbols=[
            _symbol(
                _MODULE + "com/acme/CommonResult#",
                kind="class",
                enclosing=None,
                line_start=0,
                line_end=0,
            ),
            _symbol(_LIST),
        ],
        documents=[
            {"document_id": "doc", "relative_path": "com/acme/Api.java", "origin_entry": None}
        ],
        shapes=[{"shape_id": parameterised, "open": False}],
        shape_fields=[],
        endpoints=[
            {
                "protocol": "http",
                "direction": "inbound",
                "method": "GET",
                "path": "/orders",
                "handler": _LIST,
                "caller": None,
                "request_shape": None,
                "response_shape": json.dumps({"shape_id": parameterised}),
            }
        ],
    )

    [record] = index["impact"]
    assert record["shape_id"] == parameterised
    assert record["declared_at"]["file"] == "src/main/java/com/acme/Api.java"
    # The handler alone. A NULL caller is not a symbol, and a record listing it would send
    # a reader to look up nothing.
    assert [reached["symbol"] for reached in record["reached_from"]] == [_LIST]


def test_change_impact_masks_the_addresses_it_carries(tmp_path: Path):
    """`impact` carries endpoint paths of its own, so it takes the exit's rule like the
    two files that carry one already do — a mask applied in two of three places is a mask
    a reader cannot rely on."""
    index = _write(
        tmp_path,
        shapes=[{"shape_id": "com/acme/Order#", "open": False}],
        endpoints=[
            {
                "protocol": "http",
                "direction": "outbound",
                "method": "POST",
                "path": "https://svc:s3cr3t@billing.example.com/charge",
                "handler": None,
                "caller": _LIST,
                "request_shape": json.dumps({"shape_id": "com/acme/Order#"}),
                "response_shape": None,
            }
        ],
    )

    [record] = index["impact"]
    assert record["endpoints"][0]["path"] == "https://billing.example.com/charge"
    assert "s3cr3t" not in json.dumps(index)


def test_a_jar_document_is_not_walked_towards_a_file_that_merely_shares_its_package(
    tmp_path: Path,
):
    """A LIBRARY's sources are not in this repository, so there is nothing to walk towards
    and everything to walk into.

    Measured on this repo's own fixture: the opted-in `orders-soap-client` jar was walked
    on every export — from `~/.m2/repository` up through the home directory to `/`,
    testing `<ancestor>/<source root>/<package path>` at each — and it returned null only
    because no such directory happened to exist there. Here one does, holding an unrelated
    file with the same package path, which is the publication that is worse than a null.

    The test is jar-vs-DIRECTORY rather than `origin`, because a reactor sibling carries a
    coordinate too and is exactly the case the walk exists for.
    """
    root = _tree(tmp_path / "repo" / "mod", "src/main/java/com/acme/Api.java")
    # The jar sits INSIDE the reactor and an unrelated file with the same package path
    # sits beside it, so the boundary check cannot be what saves this: only the
    # jar-versus-directory test can.
    _tree(tmp_path / "repo" / "libs", "src/main/java/com/acme/Vendor.java")
    jar = tmp_path / "repo" / "libs" / "target" / "lib-1.0.0.jar"
    jar.parent.mkdir(parents=True, exist_ok=True)
    jar.write_bytes(b"PK\x03\x04")
    index = _write(
        root,
        symbols=[_symbol(_MODULE + "com/acme/Vendor#get().", document_id="lib")],
        documents=[
            {
                "document_id": "lib",
                "relative_path": "com/acme/Vendor.java",
                "origin_entry": str(jar),
            }
        ],
    )

    assert index["symbols"][0]["file"] is None


def test_placement_does_not_depend_on_the_directory_the_export_runs_in(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """NFR-1. A RELATIVE `origin_entry` is anchored on the directory `analyze` ran in,
    which the bundle does not record — resolving it at export would anchor it on the
    EXPORTING process's directory instead, and two exports from two directories would
    place the same symbol differently.

    It is never needed either: a relative entry is this run's own module, which the source
    roots already place. Three of the four measured corpora record relative entries for
    every one of their own documents, so this is the ordinary shape and not an edge.
    """
    root = _tree(tmp_path / "mod", "src/main/java/com/acme/Api.java")
    _tree(tmp_path / "elsewhere", "src/main/java/com/acme/Ghost.java")
    (tmp_path / "elsewhere" / "target" / "classes").mkdir(parents=True)
    documents = [
        {
            "document_id": "ghost",
            "relative_path": "com/acme/Ghost.java",
            # Relative, as `analyze` records it when run with a relative path.
            "origin_entry": "elsewhere/target/classes",
        }
    ]
    # Run from the directory that WOULD make it resolve — inside the reactor bound, with
    # the file really there. Everything is in place except a reason to believe the path.
    monkeypatch.chdir(tmp_path)
    index = _write(
        root,
        symbols=[_symbol(_MODULE + "com/acme/Ghost#go().", document_id="ghost")],
        documents=documents,
    )

    assert index["symbols"][0]["file"] is None, (
        "a relative entry names a directory only the ANALYZING process knew"
    )


def test_the_walk_stops_at_this_modules_parent(tmp_path: Path):
    """Bounded by the reactor, not by the filesystem. A sibling sits beside this module, so
    its root is under this module's PARENT; anything further up is an ancestor holding a
    same-package file by coincidence, and taking it publishes the wrong source."""
    root = _tree(tmp_path / "repo" / "mod", "src/main/java/com/acme/Api.java")
    # Two levels above the module's parent — outside the reactor.
    _tree(tmp_path, "src/main/java/com/acme/Far.java")
    classes = tmp_path / "repo" / "far" / "deeper" / "target" / "classes"
    classes.mkdir(parents=True)
    index = _write(
        root,
        symbols=[_symbol(_MODULE + "com/acme/Far#go().", document_id="far")],
        documents=[
            {
                "document_id": "far",
                "relative_path": "com/acme/Far.java",
                "origin_entry": str(classes),
            }
        ],
    )

    assert index["symbols"][0]["file"] is None


def test_a_shape_carrier_hit_is_a_complete_answer(tmp_path: Path):
    """Every record self-describing, which this file was the one exception to: it shipped
    the handler and caller as bare symbols, so a hit handed back a name the reader then had
    to look up in `symbols.ndjson` before it could do anything."""
    root = _tree(tmp_path, "src/main/java/com/acme/Api.java")
    index = _write(
        root,
        symbols=[_symbol(_LIST)],
        documents=[
            {"document_id": "doc", "relative_path": "com/acme/Api.java", "origin_entry": None}
        ],
        endpoints=[
            {
                "protocol": "http",
                "direction": "inbound",
                "method": "POST",
                "path": "/orders",
                "handler": _LIST,
                "caller": None,
                "request_shape": json.dumps({"shape_id": "com/acme/Order#"}),
                "response_shape": None,
            }
        ],
    )

    [carried] = index["shape_carriers"][0]["request"]
    assert carried["handler_at"]["file"] == "src/main/java/com/acme/Api.java"
    assert carried["handler_at"]["line"] == 41
    # A row carries a handler OR a caller, so the absent one is null rather than an
    # all-null location answering a question nobody asked.
    assert carried["caller_at"] is None


def test_every_index_file_is_written_in_a_stable_order(tmp_path: Path):
    """NFR-1, and the byte-identity test above cannot see this.

    That one calls `write_index` twice in ONE process with the same input lists, so an
    index built by iterating a `set` or a dict comes out identical both times and every
    missing `sorted()` survives it. Here the inputs are SHUFFLED between the two runs,
    which is what a different scan order — or a different hash seed — really looks like.

    **Every input, not the three that group into sets.** The first version shuffled
    `call_edges`, `implementations` and `annotations` only, which left nine orderings with
    nothing watching them: the symbol listing, the annotation grouping, both shape-carrier
    sides, the three inside a file digest and the three inside a change-impact record.
    Measured by removing each `sorted()` in turn — nine of eighteen survived the suite.
    """
    root = _tree(
        tmp_path,
        *(f"src/main/java/com/acme/F{n}.java" for n in range(12)),
    )
    documents = [
        {"document_id": f"doc{n}", "relative_path": f"com/acme/F{n}.java", "origin_entry": None}
        for n in range(12)
    ]
    # Two symbols per document and two KINDS, so the `declares` map inside a digest has
    # something to order and the digest list itself has twelve files to order.
    symbols = [
        _symbol(_MODULE + f"com/acme/C{n}#", document_id=f"doc{n}", kind="class", enclosing=None)
        for n in range(12)
    ] + [_symbol(_MODULE + f"com/acme/C{n}#go().", document_id=f"doc{n}") for n in range(12)]
    # Three callees and three interfaces, not one each: a reverse index with a single key
    # has no order to get wrong, and both of these grouping sorts survived a shuffle for
    # exactly that reason.
    callers = [
        {
            "caller": _MODULE + f"com/acme/C{n}#go().",
            "callee": _MODULE + f"com/acme/T{n % 3}#t().",
        }
        for n in range(12)
    ]
    interfaces = [
        {
            "symbol": _MODULE + f"com/acme/C{n}#",
            "interfaces": json.dumps([f"com/acme/Face{n % 3}#"]),
        }
        for n in range(12)
    ]
    # Two annotations per target, so the set inside one digest's `annotations` list and the
    # set inside one `annotated` record both have an order to get wrong.
    annotations = [
        {
            "target": _MODULE + f"com/acme/C{n}#",
            "annotation": f"org/x/Ann{n % 2}#",
            "document_id": f"doc{n}",
        }
        for n in range(12)
    ] + [
        {
            "target": _MODULE + f"com/acme/C{n}#",
            "annotation": "org/x/Common#",
            "document_id": f"doc{n}",
        }
        for n in range(12)
    ]
    # Every shape on BOTH sides of a different endpoint, which is what gives the carrier
    # index two lists per record and the impact index a list of endpoints to order.
    shapes = [{"shape_id": f"com/acme/S{n}#", "open": False} for n in range(12)]
    shape_fields = [
        {"shape_id": f"com/acme/S{n}#", "wire_name": name}
        for n in range(12)
        for name in ("total", "id", "createdAt")
    ]
    endpoints = [
        {
            "protocol": "http",
            "direction": "inbound",
            "method": method,
            "path": f"/s{n}/{method.lower()}",
            "handler": _MODULE + f"com/acme/C{n}#go().",
            "caller": _MODULE + f"com/acme/C{(n + 1) % 12}#go().",
            "request_shape": json.dumps({"shape_id": f"com/acme/S{n}#"}),
            "response_shape": json.dumps({"shape_id": f"com/acme/S{n}#"}),
        }
        for n in range(12)
        for method in ("POST", "PUT")
    ]
    roots = [
        {
            "handler": _MODULE + f"com/acme/C{n}#go().",
            "root_kind": "http_endpoint",
            "protocol": "http",
            "method": "POST",
            "path": f"/s{n}/post",
        }
        for n in range(12)
    ]

    def run(where: str, order: int) -> dict[str, str]:
        write_index(
            root / where,
            symbols=symbols[::order],
            documents=documents[::order],
            call_edges=callers[::order],
            implementations=interfaces[::order],
            annotations=annotations[::order],
            endpoints=endpoints[::order],
            roots=roots[::order],
            shapes=shapes[::order],
            shape_fields=shape_fields[::order],
            source_roots=["src/main/java"],
            module_root=root,
            redactor=Redactor.from_rules(),
        )
        return {
            path.name: path.read_text(encoding="utf-8")
            for path in sorted((root / where / "index").iterdir())
        }

    forwards, backwards = run("forwards", 1), run("backwards", -1)
    # Named rather than asserted whole, so a file that stopped being written at all cannot
    # pass this by being absent from both sides.
    assert sorted(forwards) == [
        "addresses.ndjson",
        "annotated.ndjson",
        "callers.ndjson",
        "files.ndjson",
        "impact.ndjson",
        "implementors.ndjson",
        "shape_carriers.ndjson",
        "symbols.ndjson",
    ]
    assert forwards == backwards


def test_the_index_is_the_same_under_a_different_hash_seed(tmp_path: Path):
    """NFR-1 again, and the shuffle above cannot see this either.

    A record assembled from a SET comes out in whatever order that set iterates, and within
    one process that order is fixed — so shuffling the inputs changes nothing and the
    missing `sorted()` survives. It is the interpreter's hash seed that decides it, and
    that changes between runs on the same input, which is the case NFR-1 is about.
    `resolve/terminals.py` found the same defect the same way, over six seeds.

    Two SUBPROCESSES, because `PYTHONHASHSEED` is read once at interpreter start and
    cannot be changed from inside one.
    """
    root = _tree(tmp_path, "src/main/java/com/acme/Api.java")
    program = tmp_path / "run.py"
    program.write_text(
        f"""
import json, sys
from pathlib import Path
from sextant.domain.redaction import Redactor
from sextant.egress.export.index import write_index

root = Path({str(root)!r})
module = {_MODULE!r}
# Sixteen distinct symbols on one shape's endpoints, so the set that collects them has
# enough members for its iteration order to depend on the seed.
endpoints = [
    {{
        "protocol": "http",
        "direction": "inbound",
        "method": "POST",
        "path": "/orders/" + str(n),
        "handler": module + "com/acme/H" + str(n) + "#go().",
        "caller": module + "com/acme/K" + str(n) + "#go().",
        "request_shape": json.dumps({{"shape_id": "com/acme/Order#"}}),
        "response_shape": None,
    }}
    for n in range(8)
]
out = Path(sys.argv[1])
write_index(
    out,
    symbols=[],
    documents=[
        {{"document_id": "doc", "relative_path": "com/acme/Api.java", "origin_entry": None}}
    ],
    call_edges=[],
    implementations=[],
    annotations=[],
    endpoints=endpoints,
    roots=[],
    shapes=[{{"shape_id": "com/acme/Order#", "open": False}}],
    shape_fields=[],
    source_roots=["src/main/java"],
    module_root=root,
    redactor=Redactor.from_rules(),
)
sys.stdout.write((out / "index" / "impact.ndjson").read_text(encoding="utf-8"))
""",
        encoding="utf-8",
    )

    def run(seed: str) -> str:
        finished = subprocess.run(
            [sys.executable, str(program), str(tmp_path / ("out" + seed))],
            check=True,
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONHASHSEED": seed},
        )
        return finished.stdout

    first = run("0")
    # The symbols really are in there, so a run that silently wrote nothing cannot pass by
    # matching another empty one.
    assert "com/acme/H7#go()." in first
    for seed in ("1", "2", "3", "4", "5"):
        assert run(seed) == first, f"index differs under PYTHONHASHSEED={seed}"


def test_a_file_that_declares_nothing_still_gets_a_digest_record(tmp_path: Path):
    """A digest is a fact about a FILE, and the first version built it from placed SYMBOLS
    — which made the real criterion "declares nothing" rather than "cannot be placed".

    Every `package-info` file was dropped: 3 in the fixture, 14 in `jhipster-sample-app`,
    4 in `spring-petclinic-rest`. Each opens perfectly well and each carries the
    package-scope nullness rule that governs every type beside it — and a file that
    declares nothing is exactly the file an agent most wants to be told it can skip.
    """
    root = _tree(tmp_path, "src/main/java/com/acme/package-info.java")
    index = _write(
        root,
        symbols=[],
        documents=[
            {
                "document_id": "pkg",
                "relative_path": "com/acme/package-info.java",
                "origin_entry": None,
            }
        ],
        annotations=[
            {
                "target": _MODULE + "com/acme/package-info#",
                "annotation": "org/x/NullMarked#",
                "document_id": "pkg",
            }
        ],
    )

    [record] = index["files"]
    assert record["file"] == "src/main/java/com/acme/package-info.java"
    assert record["declares"] == {} and record["symbols"] == 0
    assert record["annotations"] == ["org/x/NullMarked#"]


def test_one_declaration_carrying_two_annotations_appears_under_both(tmp_path: Path):
    """A type usually carries several, and the index is keyed by ANNOTATION, so the same
    declaration is a member of several records.

    The reverse map holds targets in a set, so a target repeated under one annotation is
    one entry — and the row kept for placement is whichever came first, which is why they
    must place identically. They do: placement reads the location index, and a target has
    one location however many annotations name it.
    """
    root = _tree(tmp_path, "src/main/java/com/acme/Api.java")
    target = _MODULE + "com/acme/Api#"
    index = _write(
        root,
        symbols=[_symbol(target, kind="class", enclosing=None, line_start=0, line_end=0)],
        documents=[
            {"document_id": "doc", "relative_path": "com/acme/Api.java", "origin_entry": None}
        ],
        annotations=[
            {"target": target, "annotation": "org/x/Service#", "document_id": "doc"},
            {"target": target, "annotation": "org/x/Validated#", "document_id": "doc"},
            # The same pair again, as a second scanned occurrence would arrive.
            {"target": target, "annotation": "org/x/Service#", "document_id": "doc"},
        ],
    )

    assert [record["annotation"] for record in index["annotated"]] == [
        "org/x/Service#",
        "org/x/Validated#",
    ]
    for record in index["annotated"]:
        assert [on["symbol"] for on in record["on"]] == [target]
        assert record["on"][0]["file"] == "src/main/java/com/acme/Api.java"
    # And the file digest names both once, not the three rows that arrived.
    [digest] = index["files"]
    assert digest["annotations"] == ["org/x/Service#", "org/x/Validated#"]


def test_an_annotation_whose_target_is_not_a_symbol_is_placed_by_its_document(
    tmp_path: Path,
):
    """A package declaration has no symbol row, so a scope rule covering every type in the
    package — `@NullMarked`, `@NonNullApi` — came out of the index placed nowhere.

    The document always knows which file; it cannot know WHERE in it, so the line stays
    null rather than being invented.
    """
    root = _tree(tmp_path, "src/main/java/com/acme/package-info.java")
    index = _write(
        root,
        documents=[
            {
                "document_id": "pkg",
                "relative_path": "com/acme/package-info.java",
                "origin_entry": None,
            }
        ],
        annotations=[
            {
                "target": _MODULE + "com/acme/package-info#",
                "annotation": "org/x/NullMarked#",
                "document_id": "pkg",
            }
        ],
    )

    [record] = index["annotated"]
    assert record["on"][0]["file"] == "src/main/java/com/acme/package-info.java"
    assert record["on"][0]["line"] is None
