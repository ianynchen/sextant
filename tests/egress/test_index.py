"""The index bundle (F8 §9.3, W35) — where, not only what.

Every test here builds its own tiny source tree under `tmp_path`, because the thing under
test is a JOIN against files on disk: a path that resolves against nothing is the failure
mode, and a test that never touched a filesystem could not tell a resolved path from an
invented one.

The shipped index's live numbers are measured on the four corpora and recorded in
COVERAGE §3a-xii.
"""

import json
from pathlib import Path

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
            {"target": _API, "annotation": "org/x/RestController#"},
            {"target": _LIST, "annotation": "org/x/GetMapping#"},
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
