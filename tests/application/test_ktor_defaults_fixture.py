"""The `$default` bridge projection (spec 2026-09-19 §3a) pinned on REAL bytecode: the
module-local DSL function with a default parameter in `fixtures/orders-ktor`'s
`KtorRoutes.kt` (`kotlin-default-bridge-calls`), called with and without the argument.

`fun Route.mount(path, version = "v1", build)` is a top-level extension, so kotlinc 2.2.0
compiles it to a STATIC `KtorRoutesKt.mount(Route, String, String, Function1)` and, for the
call that omits `version`, emits `mount$default(this, "/d", null, build, 2, null)` — a
different name and a six-slot descriptor no rule for `mount` can match (`javap -c -p
fixtures/orders-ktor/target/classes/com/acme/kt/KtorRoutesKt.class`, 2026-09-20). The
projection hands every engine that site as `mount` with `version` unresolved/defaulted,
and this file asserts that on the analysed fixture rather than on hand-built facts.

Two pins, one primary. (a) `effective_call_sites` on the analysed workspace, no catalog
involved — the raw `call_sites` row still names `mount$default`, the projected one names
`mount`. (b) A TEST-ONLY catalog — the shipped `ktor-routing.yml` plus one prefix rule for
`mount` — derives `GET /d/x` resolved, the row the projection makes possible, beside
`GET /e/y` from the plain call. The shipped catalog carries no rule for `mount` (helper
following is a later task), so `tests/e2e/test_rest_inbound_delivered.py` pins the two
calls as deriving nothing there; this file is where the bridge itself is pinned, because
the package's catalog directory is its only source and a test-only catalog cannot ship.
"""

from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from fixture_build import FIXTURES, compile_fixture
from sextant.application.ports.catalogs import Catalog
from sextant.application.resolve.effective_calls import effective_call_sites
from sextant.application.resolve.endpoints import derive_endpoints
from sextant.cli.app import cli
from sextant.ingress.catalogs.yaml_source import YamlCatalogSource
from sextant.resources import catalogs_dir
from sextant.storage.duckdb.workspace import DuckDbWorkspace

KTOR = FIXTURES / "orders-ktor"
FACADE = "com/acme/kt/KtorRoutesKt#"
ROUTE, STRING, FUNCTION1 = (
    "Lio/ktor/server/routing/Route;",
    "Ljava/lang/String;",
    "Lkotlin/jvm/functions/Function1;",
)
# The sibling's descriptor and the bridge's, as `javap -s` prints them.
MOUNT = "(" + ROUTE + STRING + STRING + FUNCTION1 + ")" + ROUTE
MOUNT_BRIDGE = "(" + ROUTE + STRING + STRING + FUNCTION1 + "ILjava/lang/Object;)" + ROUTE
DEFAULTED = {"kind": "unresolved", "reason": "defaulted"}


@pytest.fixture(scope="module")
def analyzed_ktor(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """`orders-ktor`, analysed once the way the e2e `ktor_rows` fixture does it — through
    `module analyze` — so the workspace is the CLI's own, not a hand-scanned one."""
    workspace_dir = tmp_path_factory.mktemp("ktor-defaults")
    compile_fixture(KTOR)
    result = CliRunner().invoke(
        cli, ["module", "analyze", str(KTOR), "--workspace", str(workspace_dir)]
    )
    assert result.exit_code == 0, result.output
    return workspace_dir / "workspace.duckdb"


def _mount_sites(rows: list[dict]) -> list[dict]:
    """The `mount` and `mount$default` sites inside `defaults()`'s routing body — the
    `defaults$lambda$8` the block compiles to — in ordinal order."""
    return sorted(
        (
            row
            for row in rows
            if "#defaults$lambda$" in str(row["caller"]) and str(row["name"]).startswith("mount")
        ),
        key=lambda row: int(row["ordinal"]),
    )


def test_the_defaulted_dsl_call_reaches_engines_as_mount_with_version_unresolved(
    analyzed_ktor: Path,
):
    """(a), the primary pin. The raw fact keeps the bytecode's statement — the six-slot
    `mount$default` with the caller's placeholder `null` and the mask literal 2 — and the
    projected site is `mount(Route, String, String, Function1)`: the receiver and the path
    `/d` as the caller pushed them, `version` (slot 2, mask bit 1 — the receiver the
    author wrote is no declared parameter and has no bit) unresolved/defaulted, the block
    kept, and `evidence_bridge` naming the bridge the call was. The plain call
    `mount("/e", "v2")` is the control: untouched, `evidence_bridge` NULL."""
    workspace = DuckDbWorkspace(analyzed_ktor)
    try:
        raw = _mount_sites(workspace.query("call_sites"))
        projected = _mount_sites(effective_call_sites(workspace))
    finally:
        workspace.close()

    assert [(row["name"], row["descriptor"]) for row in raw] == [
        ("mount$default", MOUNT_BRIDGE),
        ("mount", MOUNT),
    ]
    assert raw[0]["arguments"][1:3] == [{"kind": "string", "value": "/d"}, {"kind": "null"}]
    assert raw[0]["arguments"][4:] == [{"kind": "int", "value": 2}, {"kind": "null"}]

    defaulted, plain = projected
    assert (defaulted["owner"], defaulted["name"], defaulted["descriptor"]) == (
        FACADE,
        "mount",
        MOUNT,
    )
    assert defaulted["evidence_bridge"] == FACADE + "mount$default" + MOUNT_BRIDGE
    assert defaulted["arguments"][0] == {"kind": "parameter", "value": 0}
    assert defaulted["arguments"][1] == {"kind": "string", "value": "/d"}
    assert defaulted["arguments"][2] == DEFAULTED
    assert defaulted["arguments"][3]["kind"] == "lambda" and len(defaulted["arguments"]) == 4
    assert (defaulted["invoke_kind"], defaulted["receiver_parameter"]) == ("static", None)

    assert (plain["name"], plain["descriptor"], plain.get("evidence_bridge")) == (
        "mount",
        MOUNT,
        None,
    )
    assert plain["arguments"][1:3] == [
        {"kind": "string", "value": "/e"},
        {"kind": "string", "value": "v2"},
    ]


def _defaults_catalog(tmp_path: Path) -> list[Catalog]:
    """The shipped `ktor-routing.yml` with ONE more prefix rule — `mount` at the SIBLING's
    arity, 4, never the bridge's 6: the projection is what makes the rule match — written
    to `tmp_path` and loaded through the same source the shipped catalogs load through."""
    raw = yaml.safe_load((catalogs_dir() / "ktor-routing.yml").read_text(encoding="utf-8"))
    raw["matches"]["vocabulary"]["prefixes"].append(
        {
            "owner": "com.acme.kt.KtorRoutesKt",
            "method": "mount",
            "arity": 4,
            "receiver_arg": 0,
            "path_arg": 1,
            "body_arg": 3,
            "origin_param": 0,
        }
    )
    (tmp_path / "kt-defaults.yml").write_text(yaml.safe_dump(raw), encoding="utf-8")
    return YamlCatalogSource(tmp_path).load()


def test_under_a_catalog_naming_mount_the_defaulted_call_derives_its_route(
    analyzed_ktor: Path, tmp_path: Path
):
    """(b). `mount("/d") { get("/x") { } }` derives `GET /d/x` resolved — THE row the
    projection makes possible: before it, the site named `mount$default` at arity 6 and
    matched nothing, so `/d/x` did not exist. `mount("/e", "v2") { get("/y") { } }` is the
    control that derives with or without the projection. `version` does not shape the
    path (`mount` is `route(path, build)`), so a rule reading `path_arg: 1` states the
    truth and both rows are resolved; the two `mountedVersions` writes inside `mount` are
    not on the walk. Every `orders()` row of the shipped catalog derives as before."""
    catalogs = _defaults_catalog(tmp_path)
    workspace = DuckDbWorkspace(analyzed_ktor)
    try:
        skipped = derive_endpoints(
            workspace, catalogs, capabilities=set(catalogs[0].requires) | {"array_arguments"}
        )
        assert skipped == []
        rows = {
            (str(row["method"]), str(row["path"]), str(row["resolution"]))
            for row in workspace.query("endpoints")
            if "#defaults(" in str(row["caller"])
        }
        every = [dict(row) for row in workspace.query("endpoints")]
    finally:
        workspace.close()

    assert rows == {("GET", "/d/x", "resolved"), ("GET", "/e/y", "resolved")}, rows
    assert ("GET", "/api/orders", "resolved") in {
        (str(r["method"]), str(r["path"]), str(r["resolution"])) for r in every
    }
    assert len(every) == 10, sorted((r["method"], r["path"], r["caller"]) for r in every)
