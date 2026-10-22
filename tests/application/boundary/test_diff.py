"""The derivation diff (spec 2026-10-22-boundary-vocabulary-and-diff §3, FR-22): two analyses
of one module joined on the vocabulary's identities, every kind reported even at zero.

Each side is a workspace written row by row, because a row written by hand says exactly what
the test is about; the masking tests also export one side as a bundle, which is the drift
scenario the diff exists for (a CI bundle against a local workspace, §3d).
"""

import json
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import cast

import pytest
from click.testing import CliRunner

from sextant import api
from sextant.application.boundary.diff import DiffRefused, diff_sources
from sextant.application.boundary.source import BoundarySource
from sextant.application.boundary.vocabulary import KINDS
from sextant.cli.app import cli
from sextant.domain.redaction import REDACTED, RedactionRules, Redactor
from sextant.storage.duckdb.workspace import DuckDbWorkspace, open_read_only

FIXTURE = Path(__file__).parents[3] / "fixtures" / "orders-service"
REDACTOR = Redactor.from_rules()
_ZERO = {"added": 0, "removed": 0, "changed": 0}

_MODULE = {
    "id": "com.acme:orders-service",
    "kind": "service",
    "languages": ["java"],
    "dependency_source": "declared",
}
_PROVENANCE = {"commit": "630906a7", "sextant_version": "0.1.0", "fact_schema_version": 2}
_METADATA = {
    "schema_version": 3,
    "boundary_vocabulary_version": 1,
    "catalog_hash": "sha256:catalogs",
    "module": _MODULE,
    "provenance": _PROVENANCE,
    "environments": ["default", "prod"],
}


@pytest.fixture
def sources() -> Iterator[Callable[[Path], BoundarySource]]:
    """Opens sources and closes every one at teardown, so no test leaves a file locked."""
    opened: list[BoundarySource] = []

    def open_one(path: Path) -> BoundarySource:
        source = BoundarySource.open(path, open_read_only)
        opened.append(source)
        return source

    yield open_one
    for source in opened:
        source.close()


def _insert(workspace: DuckDbWorkspace, table: str, **columns: object) -> None:
    names = ", ".join(columns)
    marks = ", ".join("?" for _ in columns)
    workspace._connection.execute(
        f"INSERT INTO {table} ({names}) VALUES ({marks})", list(columns.values())
    )


def _endpoint(workspace: DuckDbWorkspace, **columns: object) -> None:
    _insert(
        workspace,
        "endpoints",
        **{"protocol": "http", "direction": "inbound", "resolution": "resolved", **columns},
    )


def _field(
    workspace: DuckDbWorkspace,
    shape: str,
    ordinal: int,
    name: str,
    required: bool = False,
    wire_type: str = "string",
) -> None:
    _insert(workspace, "shape_fields", shape_id=shape, ordinal=ordinal, wire_name=name,
            wire_type=wire_type, wire_format=None, required=required, nullable=False,
            resolution="resolved", evidence="declared")  # fmt: skip


def _shape(shape_id: str) -> str:
    return json.dumps(
        {"nullable": True, "shape_id": shape_id, "wire_format": "", "wire_type": "object"}
    )


def _built(root: Path, build: Callable[[DuckDbWorkspace], None], **metadata: object) -> Path:
    """A workspace directory whose tables `build` filled, closed so a source can open it.
    `metadata` overrides the top-level keys of `metadata.json` (a `None` deletes one)."""
    directory = root / ".sextant"
    directory.mkdir(parents=True)
    document = {**_METADATA, **metadata}
    document = {key: value for key, value in document.items() if value is not None}
    (directory / "metadata.json").write_text(json.dumps(document), encoding="utf-8")
    workspace = DuckDbWorkspace(directory / "workspace.duckdb")
    try:
        build(workspace)
    finally:
        workspace.close()
    return directory


def _bundled(workspace_dir: Path, destination: Path, redactor: Redactor = REDACTOR) -> Path:
    """`workspace_dir` exported as a bundle — masked through `redactor` exactly as
    `module export` masks — with the manifest a bundle carries."""
    workspace = DuckDbWorkspace(workspace_dir / "workspace.duckdb")
    try:
        workspace.export_tables(destination, redactor)
    finally:
        workspace.close()
    metadata = json.loads((workspace_dir / "metadata.json").read_text())
    manifest = {
        "module": metadata["module"],
        "source": {"commit": metadata["provenance"]["commit"]},
        "producer": {
            "sextant_version": metadata["provenance"]["sextant_version"],
            "fact_schema_version": metadata["provenance"]["fact_schema_version"],
            "graph_schema_version": metadata["schema_version"],
            "boundary_vocabulary_version": metadata["boundary_vocabulary_version"],
            "catalog_hash": metadata["catalog_hash"],
            "redaction_set_hash": redactor.rule_set_hash,
        },
        "environments": metadata["environments"],
    }
    (destination / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return destination


def _owners(workspace: DuckDbWorkspace, version: str = "") -> None:
    """Two petclinic routes; `version` moves and renames the controller the way upstream's
    `organize controllers by version` did (§1b): `v1` is `rest/v1/OwnerControllerV1`."""
    package, suffix = (f"{version}/", version.upper()) if version else ("", "")
    for method, path in (("GET", "/api/owners"), ("POST", "/api/owners")):
        _endpoint(workspace, method=method, path=path,
                  handler=f"com/acme/rest/{package}OwnerController{suffix}#"
                          f"{method.lower()}().")  # fmt: skip


# --- the empty change set ---------------------------------------------------------------


def test_identical_sides_produce_the_empty_change_set_with_every_kind_at_zero(
    tmp_path: Path, sources: Callable[[Path], BoundarySource]
):
    """NFR-1: identical inputs, and an empty diff is all zeros, never an absent answer."""
    side = sources(_built(tmp_path, _owners))
    diff = diff_sources(side, side, REDACTOR, REDACTOR)
    assert diff.entries == ()
    assert diff.summary == {name: _ZERO for name in KINDS}
    assert diff.producer_changed is False


@pytest.mark.pins("boundary.every-kind-is-in-the-summary-at-zero")
def test_every_kind_is_present_in_the_summary_at_zero_even_with_no_rows_anywhere(
    tmp_path: Path, sources: Callable[[Path], BoundarySource]
):
    a = sources(_built(tmp_path / "a", lambda w: None))
    b = sources(_built(tmp_path / "b", lambda w: _endpoint(w, method="GET", path="/x")))
    summary = diff_sources(a, b, REDACTOR, REDACTOR).summary
    assert list(summary) == list(KINDS)  # registry order, every kind
    assert summary["endpoint"] == {"added": 1, "removed": 0, "changed": 0}
    assert all(summary[name] == _ZERO for name in KINDS if name != "endpoint")


# --- identity: the wire, not the code -----------------------------------------------------


@pytest.mark.pins("boundary.the-HANDLER-is-evidence-never-identity")
def test_a_moved_controller_is_no_entry_and_a_new_route_is_added(
    tmp_path: Path, sources: Callable[[Path], BoundarySource]
):
    """§1b: every controller moved into `v1/` and was renamed `…V1`; on the wire only the
    new `v2` route happened. The handler is evidence, so the move says nothing."""

    def after(workspace: DuckDbWorkspace) -> None:
        _owners(workspace, version="v1")
        _endpoint(workspace, method="GET", path="/api/v2/owners",
                  handler="com/acme/rest/v2/OwnerControllerV2#page().")  # fmt: skip

    a = sources(_built(tmp_path / "a", _owners))
    b = sources(_built(tmp_path / "b", after))
    diff = diff_sources(a, b, REDACTOR, REDACTOR)
    assert [(e.kind, e.change, e.identity["path"]) for e in diff.entries] == [
        ("endpoint", "added", "/api/v2/owners")
    ]
    (added,) = diff.entries
    assert added.identity == {"protocol": "http", "method": "GET", "path": "/api/v2/owners"}
    assert added.from_ is None and added.to is not None
    assert set(added.to) == {"request", "response", "request_shape", "response_shape",
                             "consumes", "produces", "format", "requirements", "conditions",
                             "resolution"}  # fmt: skip
    assert added.evidence["symbols"] == ["com/acme/rest/v2/OwnerControllerV2#page()."]
    assert added.compatibility is None  # an added route is not a body change


def test_a_removed_route_carries_the_evidence_of_the_side_it_was_on(
    tmp_path: Path, sources: Callable[[Path], BoundarySource]
):
    a = sources(_built(tmp_path / "a", _owners))
    b = sources(_built(tmp_path / "b", lambda w: _endpoint(w, method="GET", path="/api/owners",
                                                           handler="X#get().")))  # fmt: skip
    (removed,) = diff_sources(a, b, REDACTOR, REDACTOR).entries
    assert (removed.change, removed.identity["method"], removed.to) == ("removed", "POST", None)
    assert removed.from_ is not None and removed.from_["resolution"] == "resolved"
    assert removed.evidence["symbols"] == ["com/acme/rest/OwnerController#post()."]
    assert removed.origin == "module_output"


# --- bodies, field by field ---------------------------------------------------------------


_Fields = list[tuple[str, bool]] | list[tuple[str, bool, str]]


def _array_of(descriptor: str) -> str:
    return json.dumps(
        {"item": json.loads(descriptor), "nullable": True, "wire_format": "", "wire_type": "array"}
    )


def _owner_route(
    fields: _Fields,
    body: str,
    shape: str = "com/acme/Owner#",
    descriptor: Callable[[str], str] = _shape,
) -> Callable[[DuckDbWorkspace], None]:
    """`GET /owners` whose `body` (`request` or `response`) is `descriptor(shape)`, `shape`
    having `fields` as (wire name, required[, wire type])."""

    def build(workspace: DuckDbWorkspace) -> None:
        for ordinal, (name, required, *wire_type) in enumerate(fields):
            _field(workspace, shape, ordinal, name, required, *wire_type)
        _endpoint(workspace, method="GET", path="/owners", handler="H#owners().",
                  **{f"{body}_shape": descriptor(shape)})  # fmt: skip

    return build


def _changed_owner(
    root: Path,
    sources: Callable[[Path], BoundarySource],
    before: _Fields,
    after: _Fields,
    body: str,
):
    a = sources(_built(root / "a", _owner_route(before, body)))
    b = sources(_built(root / "b", _owner_route(after, body)))
    (entry,) = diff_sources(a, b, REDACTOR, REDACTOR).entries
    assert (entry.kind, entry.change) == ("endpoint", "changed")
    return entry


def test_a_response_field_added_is_a_compatible_change_with_from_and_to(
    tmp_path: Path, sources: Callable[[Path], BoundarySource]
):
    """Decision 1: a field added to a response reads `changed` with `from`/`to` — never
    gone-and-back — and `from`/`to` carry only the attribute that differs."""
    old, new = [("id", True), ("name", False)], [("id", True), ("name", False), ("phone", False)]
    entry = _changed_owner(tmp_path, sources, old, new, "response")
    assert entry.compatibility == "compatible"
    assert entry.from_ is not None and entry.to is not None
    assert set(entry.from_) == set(entry.to) == {"response"}
    assert [f["wire_name"] for f in entry.from_["response"]] == ["id", "name"]  # type: ignore[attr-defined]
    assert [f["wire_name"] for f in entry.to["response"]] == ["id", "name", "phone"]  # type: ignore[attr-defined]


@pytest.mark.pins("boundary.a-REQUIRED-request-field-added-is-breaking")
def test_a_required_request_field_added_is_breaking(
    tmp_path: Path, sources: Callable[[Path], BoundarySource]
):
    """M06 step 3 read forwards in time: an old client does not send the new field the
    server now requires."""
    entry = _changed_owner(tmp_path, sources, [("id", True)], [("id", True), ("tz", True)],
                           "request")  # fmt: skip
    assert entry.compatibility == "breaking"


def test_an_optional_request_field_added_is_compatible(
    tmp_path: Path, sources: Callable[[Path], BoundarySource]
):
    entry = _changed_owner(tmp_path, sources, [("id", True)], [("id", True), ("tz", False)],
                           "request")  # fmt: skip
    assert entry.compatibility == "compatible"


def test_a_response_field_removed_is_breaking(
    tmp_path: Path, sources: Callable[[Path], BoundarySource]
):
    """An old client that declared `name` now always reads null."""
    entry = _changed_owner(tmp_path, sources, [("id", True), ("name", False)], [("id", True)],
                           "response")  # fmt: skip
    assert entry.compatibility == "breaking"


def test_an_existing_request_field_that_becomes_required_is_breaking(
    tmp_path: Path, sources: Callable[[Path], BoundarySource]
):
    """A client that never sent `tz` now fails, though no field was added."""
    entry = _changed_owner(tmp_path, sources, [("id", True), ("tz", False)],
                           [("id", True), ("tz", True)], "request")  # fmt: skip
    assert entry.compatibility == "breaking"


@pytest.mark.parametrize("body", ["request", "response"])
def test_an_existing_fields_wire_type_change_is_breaking(
    body: str, tmp_path: Path, sources: Callable[[Path], BoundarySource]
):
    entry = _changed_owner(tmp_path, sources, [("id", True, "string")],
                           [("id", True, "integer")], body)  # fmt: skip
    assert entry.compatibility == "breaking"


@pytest.mark.parametrize("body", ["request", "response"])
def test_a_body_that_becomes_a_list_of_the_same_dto_is_one_breaking_change(
    body: str, tmp_path: Path, sources: Callable[[Path], BoundarySource]
):
    """`OrderView` -> `List<OrderView>`: the field set is the item's either way, so only the
    descriptor's structure can see it — compared with the type symbol erased."""
    fields = [("id", True), ("name", False)]
    a = sources(_built(tmp_path / "a", _owner_route(fields, body)))
    b = sources(_built(tmp_path / "b", _owner_route(fields, body,
                                                    descriptor=lambda s: _array_of(_shape(s)))))  # fmt: skip
    (entry,) = diff_sources(a, b, REDACTOR, REDACTOR).entries
    assert (entry.kind, entry.change, entry.compatibility) == ("endpoint", "changed", "breaking")
    assert entry.from_ is not None and entry.to is not None
    assert set(entry.from_) == set(entry.to) == {f"{body}_shape"}
    assert entry.to[f"{body}_shape"]["wire_type"] == "array"  # type: ignore[index]
    assert "com/acme/Owner#" not in json.dumps([entry.from_, entry.to])


@pytest.mark.parametrize("body", ["request", "response"])
def test_a_renamed_dto_with_the_same_structure_is_no_entry(
    body: str, tmp_path: Path, sources: Callable[[Path], BoundarySource]
):
    """Decision 1: implementation never matters. The class name is not on the wire."""
    fields = [("id", True), ("name", False)]
    a = sources(
        _built(
            tmp_path / "a", _owner_route(fields, body, descriptor=lambda s: _array_of(_shape(s)))
        )
    )
    b = sources(_built(tmp_path / "b", _owner_route(fields, body, shape="com/acme/v1/OwnerV1#",
                                                    descriptor=lambda s: _array_of(_shape(s)))))  # fmt: skip
    assert diff_sources(a, b, REDACTOR, REDACTOR).entries == ()


def test_a_body_that_becomes_several_is_changed_with_no_label(
    tmp_path: Path, sources: Callable[[Path], BoundarySource]
):
    """Two handlers behind one address with different response shapes carry
    `{"several": [...]}`; nothing compares field by field, so the change is reported and
    the label is `None` rather than a guess."""

    def after(workspace: DuckDbWorkspace) -> None:
        _owner_route([("id", True)], "response")(workspace)
        _field(workspace, "com/acme/Pet#", 0, "species")
        _endpoint(workspace, method="GET", path="/owners", handler="H#pets().",
                  response_shape=_shape("com/acme/Pet#"))  # fmt: skip

    a = sources(_built(tmp_path / "a", _owner_route([("id", True)], "response")))
    b = sources(_built(tmp_path / "b", after))
    (entry,) = diff_sources(a, b, REDACTOR, REDACTOR).entries
    assert entry.change == "changed" and entry.compatibility is None
    # Both shapes are one structure with the symbol erased, so only the field sets differ.
    assert entry.to is not None and set(entry.to) == {"response"}
    assert len(entry.to["response"]["several"]) == 2  # type: ignore[call-overload, index]


def test_a_non_body_change_has_no_label(tmp_path: Path, sources: Callable[[Path], BoundarySource]):
    a = sources(_built(tmp_path / "a", lambda w: _endpoint(w, method="GET", path="/x")))
    b = sources(_built(tmp_path / "b", lambda w: _endpoint(w, method="GET", path="/x",
                                                           produces="application/json")))  # fmt: skip
    (entry,) = diff_sources(a, b, REDACTOR, REDACTOR).entries
    assert (entry.from_, entry.to, entry.compatibility) == (
        {"produces": None}, {"produces": "application/json"}, None,
    )  # fmt: skip


def test_a_contract_with_a_new_field_is_changed_and_names_the_field(
    tmp_path: Path, sources: Callable[[Path], BoundarySource]
):
    """The identity is the shape symbol; the hash and the field set are what change. The
    field set is keyed by wire name, so `to` names the new field."""

    def contract(content_hash: str, names: tuple[str, ...]) -> Callable[[DuckDbWorkspace], None]:
        def build(workspace: DuckDbWorkspace) -> None:
            _insert(workspace, "shapes", shape_id="com/acme/OwnerDto#", content_hash=content_hash,
                    open=False)  # fmt: skip
            for ordinal, name in enumerate(names):
                _field(workspace, "com/acme/OwnerDto#", ordinal, name)

        return build

    a = sources(_built(tmp_path / "a", contract("md5:1", ("id", "name"))))
    b = sources(_built(tmp_path / "b", contract("md5:2", ("id", "name", "phone"))))
    (entry,) = diff_sources(a, b, REDACTOR, REDACTOR).entries
    assert (entry.kind, entry.change) == ("data-contract", "changed")
    assert entry.identity == {"shape_id": "com/acme/OwnerDto#"}
    assert entry.to is not None and entry.from_ is not None
    assert entry.to["fields"]["phone"]["wire_type"] == "string"  # type: ignore[index]
    assert list(entry.from_["fields"]) == ["id", "name"]  # type: ignore[call-overload]
    assert (entry.from_["content_hash"], entry.to["content_hash"]) == ("md5:1", "md5:2")
    assert entry.compatibility is None


# --- masking: both sides through the same exit (§3d) ---------------------------------------

_SECRET_PEER = "https://alice:s3cr3t@billing.internal"
_SECRET_KEY = "orders.api-key"


def _secrets(workspace: DuckDbWorkspace) -> None:
    _endpoint(workspace, direction="outbound", method="POST", path="/v1/charge",
              peer=_SECRET_PEER, caller="C#charge().")  # fmt: skip
    _insert(workspace, "resolved_config", key=_SECRET_KEY, value="k-123", source="application.yml",
            environment="default")  # fmt: skip


@pytest.mark.pins("boundary.both-sides-pass-through-the-REDACTOR")
def test_a_masked_bundle_and_its_verbatim_workspace_diff_empty(
    tmp_path: Path, sources: Callable[[Path], BoundarySource]
):
    """The drift scenario: a bundle shipped from CI against the workspace it came from. Its
    peer and config value are masked and the workspace's are not; read naively, both would
    be changes."""
    workspace = _built(tmp_path / "w", _secrets)
    bundle = _bundled(workspace, tmp_path / "bundle")
    verbatim, masked = sources(workspace), sources(bundle)
    # Not vacuous: the two readers DO disagree before the diff masks.
    assert [r["peer"] for r in verbatim.rows(KINDS["dependency"])] == [_SECRET_PEER]
    assert [r["peer"] for r in masked.rows(KINDS["dependency"])] == ["https://billing.internal"]
    assert [r["value"] for r in masked.rows(KINDS["boundary-property"])] == [REDACTED]
    assert diff_sources(masked, verbatim, REDACTOR, REDACTOR).entries == ()
    assert diff_sources(verbatim, masked, REDACTOR, REDACTOR).entries == ()


@pytest.mark.pins("boundary.both-sides-pass-through-the-REDACTOR")
def test_the_diffs_own_output_is_masked(tmp_path: Path, sources: Callable[[Path], BoundarySource]):
    a = sources(_built(tmp_path / "a", lambda w: None))
    b = sources(_built(tmp_path / "b", _secrets))
    entries = diff_sources(a, b, REDACTOR, REDACTOR).entries
    assert [(e.kind, e.change) for e in entries] == [
        ("dependency", "added"), ("boundary-property", "added"),
    ]  # fmt: skip
    dependency, prop = entries
    assert dependency.identity["peer"] == "https://billing.internal"
    assert prop.to == {"value": REDACTED, "unresolved_reason": None}
    assert "s3cr3t" not in json.dumps(diff_sources(a, b, REDACTOR, REDACTOR).to_json())


def test_two_addresses_that_mask_alike_are_one_entry_as_in_the_bundle(
    tmp_path: Path, sources: Callable[[Path], BoundarySource]
):
    """Two peers that differ only in userinfo are two rows in the workspace and ONE in the
    bundle (export masked them before the source grouped them). The diff joins the
    workspace's two after masking, keeping both callers and both formats, so the pair still
    diffs empty — dropping one of them would be a silent choice."""

    def build(workspace: DuckDbWorkspace) -> None:
        for user, caller, wire in (("alice", "A#a().", "json"), ("bob", "B#b().", "xml")):
            _endpoint(workspace, direction="outbound", method="POST", path="/v1/charge",
                      peer=f"https://{user}:pw@billing", caller=caller, format=wire)  # fmt: skip

    workspace = _built(tmp_path / "w", build)
    bundle = _bundled(workspace, tmp_path / "bundle")
    assert len(sources(workspace).rows(KINDS["dependency"])) == 2
    assert len(sources(bundle).rows(KINDS["dependency"])) == 1
    assert diff_sources(sources(workspace), sources(bundle), REDACTOR, REDACTOR).entries == ()

    one = sources(_built(tmp_path / "one", lambda w: _endpoint(
        w, direction="outbound", method="POST", path="/v1/charge", peer="https://billing",
        caller="A#a().", format="json")))  # fmt: skip
    (entry,) = diff_sources(one, sources(workspace), REDACTOR, REDACTOR).entries
    assert entry.to == {"format": {"several": ["json", "xml"]}}
    assert entry.evidence["symbols"] == ["A#a().", "B#b()."]  # both callers, joined


def test_the_fixture_bundle_and_its_workspace_diff_empty(
    analyzed_workspace_copy: Path, sources: Callable[[Path], BoundarySource]
):
    """The real exit on the real fixture: `module export` masks `orders.internal.dsn` by
    the module's own `.sextant.yml`, and the diff, masking the workspace by the same rules,
    sees nothing."""
    result = CliRunner().invoke(
        cli, ["module", "export", str(FIXTURE), "--workspace", str(analyzed_workspace_copy)]
    )
    assert result.exit_code == 0, result.output
    bundle = Path(result.output.strip())
    redactor = api._redactor_for(FIXTURE)
    workspace, masked = sources(analyzed_workspace_copy), sources(bundle)
    values = {r["key"]: r["value"] for r in masked.rows(KINDS["boundary-property"])}
    assert REDACTED in values.values()  # the bundle did mask something
    diff = diff_sources(masked, workspace, Redactor.from_rules(), redactor)
    assert diff.entries == () and diff.producer_changed is False
    recorded = {**cast(dict[str, object], diff.b["producer"]), "redaction_recorded": True}
    assert diff.a["producer"] == recorded


# --- refusals (§3c), before any row is read --------------------------------------------------


class _Unreadable(BoundarySource):
    """A side whose rows must never be read: every refusal is decided on stamps alone."""

    def rows(self, kind):  # type: ignore[no-untyped-def]
        raise AssertionError(f"read {kind.name} rows before refusing")


def _stamped(root: Path, **metadata: object) -> BoundarySource:
    return _Unreadable(open_read_only(_built(root, lambda w: None, **metadata)))


def test_different_graph_schema_versions_refuse_by_name(tmp_path: Path):
    a, b = _stamped(tmp_path / "a", schema_version=2), _stamped(tmp_path / "b")
    with pytest.raises(DiffRefused, match="graph_schema_version 2 vs 3") as refused:
        diff_sources(a, b, REDACTOR, REDACTOR, allow_producer_change=True)  # no flag overrides this
    assert refused.value.stamps == ("graph_schema_version",)


def test_different_fact_schema_and_vocabulary_versions_refuse_by_name(tmp_path: Path):
    a = _stamped(tmp_path / "a", boundary_vocabulary_version=2,
                 provenance={**_PROVENANCE, "fact_schema_version": 1})  # fmt: skip
    b = _stamped(tmp_path / "b")
    with pytest.raises(DiffRefused) as refused:
        diff_sources(a, b, REDACTOR, REDACTOR)
    assert "fact_schema_version 1 vs 2" in str(refused.value)
    assert "boundary_vocabulary_version 2 vs 1" in str(refused.value)
    assert set(refused.value.stamps) == {"fact_schema_version", "boundary_vocabulary_version"}


def test_different_module_ids_refuse_naming_both(tmp_path: Path):
    a = _stamped(tmp_path / "a", module={**_MODULE, "id": "com.acme:billing"})
    b = _stamped(tmp_path / "b")
    with pytest.raises(DiffRefused, match="com.acme:billing vs com.acme:orders-service"):
        diff_sources(a, b, REDACTOR, REDACTOR, allow_producer_change=True)


@pytest.mark.pins("boundary.a-PRODUCER-mismatch-refuses-unless-allowed")
def test_different_sextant_versions_refuse_unless_allowed_and_then_label(
    tmp_path: Path, sources: Callable[[Path], BoundarySource]
):
    """Decision 3: a fixed dispatch bug changes rows with no code change, so the default
    is to refuse; allowed, the output says so and carries both stamps."""
    a = sources(_built(tmp_path / "a", lambda w: None,
                       provenance={**_PROVENANCE, "sextant_version": "0.2.0"}))  # fmt: skip
    b = sources(_built(tmp_path / "b", lambda w: None))
    with pytest.raises(DiffRefused, match="sextant_version 0.2.0 vs 0.1.0") as refused:
        diff_sources(a, b, REDACTOR, REDACTOR)
    assert refused.value.stamps == ("sextant_version",)
    diff = diff_sources(a, b, REDACTOR, REDACTOR, allow_producer_change=True)
    assert diff.producer_changed is True
    assert (diff.a["producer"]["sextant_version"], diff.b["producer"]["sextant_version"]) == (  # type: ignore[index]
        "0.2.0", "0.1.0",
    )  # fmt: skip


def test_different_catalog_hashes_refuse_like_the_sextant_version(tmp_path: Path):
    a, b = _stamped(tmp_path / "a", catalog_hash="sha256:other"), _stamped(tmp_path / "b")
    with pytest.raises(DiffRefused, match="catalog_hash sha256:other vs sha256:catalogs"):
        diff_sources(a, b, REDACTOR, REDACTOR)


def test_a_bundle_masked_under_other_rules_refuses_on_the_redaction_set_hash(
    tmp_path: Path, sources: Callable[[Path], BoundarySource]
):
    """ "The value changed" and "the mask changed" cannot be told apart. A workspace side is
    masked by the redactor given for it, so that is the rule set it is compared under."""
    workspace = _built(tmp_path / "w", _secrets)
    wider = Redactor.from_rules(RedactionRules(key_patterns=("charge",)))
    bundle = sources(_bundled(workspace, tmp_path / "bundle", wider))
    with pytest.raises(DiffRefused, match="redaction_set_hash") as refused:
        diff_sources(bundle, sources(workspace), REDACTOR, REDACTOR)
    assert refused.value.stamps == ("redaction_set_hash",)
    side = sources(workspace)
    producer = cast(dict[str, object], diff_sources(side, side, REDACTOR, REDACTOR).a["producer"])
    assert producer["redaction_set_hash"] == REDACTOR.rule_set_hash
    # Computed by the diff for the rules it masked under, not recorded by an export.
    assert producer["redaction_recorded"] is False


_DSN_KEY = "orders.internal.dsn"
_DSN_RULES = Redactor.from_rules(RedactionRules(key_patterns=("dsn",)))


def _dsn(value: str) -> Callable[[DuckDbWorkspace], None]:
    def build(workspace: DuckDbWorkspace) -> None:
        _insert(workspace, "resolved_config", key=_DSN_KEY, value=value,
                source="application.yml", environment="default")  # fmt: skip

    return build


@pytest.mark.pins("boundary.a-PRODUCER-mismatch-refuses-unless-allowed")
def test_two_workspaces_masked_under_their_own_rules_refuse_where_the_rules_differ(
    tmp_path: Path, sources: Callable[[Path], BoundarySource]
):
    """Spec §3d: each side is masked under ITS OWN rules. A `redact:` rule only side b's
    `.sextant.yml` declares is side b's rule set, so the two hashes differ and the diff
    refuses, naming both — never masking b under a's rules and printing b's secret."""
    a = sources(_built(tmp_path / "a", _dsn("jdbc:OLD")))
    b = sources(_built(tmp_path / "b", _dsn("jdbc:NEW-SECRET")))
    with pytest.raises(DiffRefused) as refused:
        diff_sources(a, b, REDACTOR, _DSN_RULES)
    assert refused.value.stamps == ("redaction_set_hash",)
    assert f"redaction_set_hash {REDACTOR.rule_set_hash} vs {_DSN_RULES.rule_set_hash}" in str(
        refused.value
    )


@pytest.mark.pins("boundary.both-sides-pass-through-the-REDACTOR")
@pytest.mark.parametrize("rules_on", ["a", "b"])
def test_allowed_both_sides_are_masked_under_the_union_of_the_two_rule_sets(
    tmp_path: Path, sources: Callable[[Path], BoundarySource], rules_on: str
):
    """Under `allow_producer_change` the diff runs, labelled, and BOTH sides are masked by
    every rule either side declared: whichever side wanted the DSN hidden, it never leaves
    in the clear, and two values the union masks alike are no change."""
    a = sources(_built(tmp_path / "a", lambda w: None))
    b = sources(_built(tmp_path / "b", _dsn("jdbc:NEW-SECRET")))
    redactors = (_DSN_RULES, REDACTOR) if rules_on == "a" else (REDACTOR, _DSN_RULES)
    diff = diff_sources(a, b, *redactors, allow_producer_change=True)
    assert diff.producer_changed is True
    (entry,) = diff.entries
    assert (entry.kind, entry.change, entry.to) == (
        "boundary-property", "added", {"value": REDACTED, "unresolved_reason": None},
    )  # fmt: skip
    assert "NEW-SECRET" not in json.dumps(diff.to_json())
    old = sources(_built(tmp_path / "old", _dsn("jdbc:OLD")))
    assert diff_sources(old, b, *redactors, allow_producer_change=True).entries == ()


def test_two_bundles_are_compared_on_the_hashes_they_recorded(
    tmp_path: Path, sources: Callable[[Path], BoundarySource]
):
    """A bundle's hash is the one its exporter recorded, whatever redactor the diff is handed
    for it: two bundles masked under different rules refuse, naming both recorded values."""
    workspace = _built(tmp_path / "w", _secrets)
    plain = sources(_bundled(workspace, tmp_path / "plain"))
    wider = sources(_bundled(workspace, tmp_path / "wider", _DSN_RULES))
    with pytest.raises(DiffRefused) as refused:
        diff_sources(plain, wider, REDACTOR, REDACTOR)
    assert f"redaction_set_hash {REDACTOR.rule_set_hash} vs {_DSN_RULES.rule_set_hash}" in str(
        refused.value
    )
    same = sources(_bundled(workspace, tmp_path / "same", _DSN_RULES))
    assert diff_sources(wider, same, REDACTOR, REDACTOR).producer_changed is False


def test_a_side_missing_a_stamp_is_refused_by_name(tmp_path: Path):
    a, b = _stamped(tmp_path / "a", catalog_hash=None), _stamped(tmp_path / "b")
    with pytest.raises(DiffRefused, match="catalog_hash absent on a"):
        diff_sources(a, b, REDACTOR, REDACTOR, allow_producer_change=True)
    with pytest.raises(DiffRefused, match="catalog_hash absent on b"):
        diff_sources(b, a, REDACTOR, REDACTOR, allow_producer_change=True)


# --- the output -----------------------------------------------------------------------------


def _mixed(root: Path, sources: Callable[[Path], BoundarySource]):
    def before(workspace: DuckDbWorkspace) -> None:
        for path in ("/b", "/gone"):
            _endpoint(workspace, method="GET", path=path, handler="H#h().")
        _insert(workspace, "shapes", shape_id="com/acme/Z#", content_hash="md5:1", open=False)

    def after(workspace: DuckDbWorkspace) -> None:
        _endpoint(workspace, method="GET", path="/b", handler="H#h().", format="json")
        for method, path in (("POST", "/a"), ("GET", "/a"), ("GET", "/c")):
            _endpoint(workspace, method=method, path=path, handler="H#h().")
        _insert(workspace, "shapes", shape_id="com/acme/A#", content_hash="md5:2", open=False)
        _insert(workspace, "shapes", shape_id="com/acme/Z#", content_hash="md5:1", open=False)

    a = sources(_built(root / "a", before))
    b = sources(_built(root / "b", after, provenance={**_PROVENANCE, "commit": "778285e8"}))
    return diff_sources(a, b, REDACTOR, REDACTOR)


def test_entries_are_sorted_by_kind_change_identity(
    tmp_path: Path, sources: Callable[[Path], BoundarySource]
):
    """Registry order of kinds, then added, removed, changed, then identity — so two runs
    print the same file (NFR-1)."""
    diff = _mixed(tmp_path, sources)
    assert [(e.kind, e.change, e.identity.get("method"), e.identity.get("path")) for e in diff.entries] == [
        ("endpoint", "added", "GET", "/a"),
        ("endpoint", "added", "GET", "/c"),
        ("endpoint", "added", "POST", "/a"),
        ("endpoint", "removed", "GET", "/gone"),
        ("endpoint", "changed", "GET", "/b"),
        ("data-contract", "added", None, None),
    ]  # fmt: skip
    assert diff.summary["endpoint"] == {"added": 3, "removed": 1, "changed": 1}
    assert diff.summary["data-contract"] == {"added": 1, "removed": 0, "changed": 0}


def test_to_json_has_exactly_the_spec_keys(
    tmp_path: Path, sources: Callable[[Path], BoundarySource]
):
    document = _mixed(tmp_path, sources).to_json()
    assert list(document) == [
        "boundary_vocabulary_version", "a", "b", "producer_changed", "entries", "summary",
    ]  # fmt: skip
    assert document["boundary_vocabulary_version"] == 1
    assert document["a"]["commit"] == "630906a7" and document["b"]["commit"] == "778285e8"  # type: ignore[index]
    assert set(document["a"]) == {"module", "commit", "producer"}  # type: ignore[arg-type]
    assert document["a"]["module"] == "com.acme:orders-service"  # type: ignore[index]
    entries = document["entries"]
    by_change = {entry["change"]: entry for entry in entries}  # type: ignore[attr-defined, index]
    common = {"kind", "change", "identity", "evidence", "origin", "compatibility"}
    assert set(by_change["added"]) == common | {"to"}
    assert set(by_change["removed"]) == common | {"from"}
    assert set(by_change["changed"]) == common | {"from", "to"}
    assert by_change["changed"]["from"] == {"format": None}
    assert json.loads(json.dumps(document)) == document  # plain JSON, nothing to coerce


def test_to_text_prints_the_summary_table_then_one_line_per_entry(
    tmp_path: Path, sources: Callable[[Path], BoundarySource]
):
    diff = _mixed(tmp_path, sources)
    lines = diff.to_text().splitlines()
    assert lines[0] == "| kind | added | removed | changed |"
    assert "| endpoint | 3 | 1 | 1 |" in lines
    assert sum(line.startswith("|") for line in lines) == 2 + len(KINDS)  # header, rule, kinds
    entry_lines = [line for line in lines if line.startswith("- ")]
    assert len(entry_lines) == len(diff.entries)
    assert entry_lines[4].startswith("- endpoint changed ") and "format" in entry_lines[4]
