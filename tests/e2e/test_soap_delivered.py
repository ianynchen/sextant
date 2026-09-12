"""SOAP is delivered when a Spring-WS endpoint declared the way Spring-WS permits derives
every message it serves.

**Not a document check.** This asserts what Sextant produces from real bytecode built by
`mvn` from a fixture that uses the framework the way an application does. It cannot be
satisfied by editing `COVERAGE.md`, and it goes green only when the feature works.
"""

from pathlib import Path

import pytest
from click.testing import CliRunner

from fixture_build import FIXTURES, compile_fixture
from sextant.cli.app import cli
from sextant.storage.duckdb.workspace import DuckDbWorkspace

REPO = Path(__file__).resolve().parents[2]
FIXTURE = REPO / "fixtures" / "orders-service"
SOAP_FINAL = FIXTURES / "orders-soap-final"
NS = "http://orders.example.com/ws"


@pytest.fixture(scope="module")
def soap_addresses(analyzed_orders_service: Path) -> set[str]:
    # The session's one `module analyze` of `orders-service` (`tests/conftest.py`), not a
    # run of its own: this fixture only reads rows. MEASURED on PR #20's CI run 34665949923:
    # the e2e files each analysed the same fixture on their own worker at once, and the
    # progress bar sat at 78% for nineteen minutes while all four did.
    workspace = DuckDbWorkspace(analyzed_orders_service / "workspace.duckdb")
    try:
        return {
            str(row["path"])
            for row in workspace.query("endpoints")
            if str(row["protocol"]) == "soap"
        }
    finally:
        workspace.close()


def test_one_handler_serving_two_message_types_derives_both(soap_addresses: set[str]):
    """`@PayloadRoot` is `@Repeatable(PayloadRoots.class)` — confirmed in spring-ws-core's
    own class file — and Spring-WS routes BOTH messages to the annotated method.

    Reading only the first silently halves a SOAP service's surface: the second message
    type is served in production and absent from the document. Repeatable annotations are
    read through a catalog's `container:` key, which five other catalogs declare.
    """
    missing = {
        address
        for address in (f"{{{NS}}}amendOrderRequest", f"{{{NS}}}reviseOrderRequest")
        if address not in soap_addresses
    }
    assert missing == set(), (
        f"a Spring-WS handler serving two message types derived {2 - len(missing)} of 2. "
        f"Missing: {sorted(missing)}. Derived soap addresses: {sorted(soap_addresses)}"
    )


def test_the_single_payload_root_and_soap_action_forms_still_derive(soap_addresses: set[str]):
    """The control. A change that made the repeatable form work by breaking the singular
    one would pass the test above and deliver nothing."""
    for address in (
        f"{{{NS}}}placeOrderRequest",
        "http://orders.example.com/action/cancelOrder",
    ):
        assert address in soap_addresses, f"{address} stopped deriving"


@pytest.fixture(scope="module")
def soap_final_paths(tmp_path_factory: pytest.TempPathFactory) -> set[str]:
    """`orders-soap-final`, analysed on its own: a `@WebService` class declaring one
    ordinary public method and one `public final` method (Task 9, `jaxws-public-final`),
    and two more `@WebService` classes, one extending an annotated base and one a plain
    base that itself extends an annotated grandparent (Task 10b,
    `jaxws-inherited-unannotated`)."""
    workspace_dir = tmp_path_factory.mktemp("soap-final")
    compile_fixture(SOAP_FINAL)
    result = CliRunner().invoke(
        cli, ["module", "analyze", str(SOAP_FINAL), "--workspace", str(workspace_dir)]
    )
    assert result.exit_code == 0, result.output
    workspace = DuckDbWorkspace(workspace_dir / "workspace.duckdb")
    try:
        return {
            str(row["path"])
            for row in workspace.query("endpoints")
            if str(row["protocol"]) == "soap"
        }
    finally:
        workspace.close()


def test_a_public_final_method_is_not_an_operation(soap_final_paths):
    """JAX-WS RI 4.0.2 `isWebMethodBySpec` excludes `static` and `final` (CP-13 Q4). Ours
    excluded `static` only, so a `public final` helper on a `@WebService` derived a SOAP
    operation nobody serves. `modifiers.final` has been in the facts since W7."""
    assert any(p.endswith("quote") for p in soap_final_paths), sorted(soap_final_paths)
    assert not any(p.endswith("internalAudit") for p in soap_final_paths), sorted(soap_final_paths)


def test_an_operation_inherited_from_an_unannotated_superclass_is_not_published(
    soap_final_paths,
):
    """A public method a `@WebService` class inherits WITHOUT overriding is an operation
    only when the class that DECLARES it carries `@WebService`: jaxws-rt 4.0.2's
    `RuntimeModeler.isWebMethodBySpec` (offsets 124-147) and Apache CXF 4.0.5's
    `JaxWsServiceConfiguration.hasWebServiceAnnotation` (offsets 0-17) both end with
    `method.getDeclaringClass().getAnnotation(WebService.class)`, and a live run of both
    over `BillingWebService extends AbstractBilling` produced `charge` only (w63,
    `scripts/probes/w63_cxf_web_method_rule.md`). `gate_ancestry` published every scanned
    ancestor's public methods regardless, so `audit` derived as a SOAP operation neither
    runtime serves.

    Two inheritance shapes, told apart by namespace: `TieredQuoteService` (its own `tier`,
    plus `price` inherited from `@WebService PricedService`) publishes both under ITS
    namespace, which is what says the row came through the walk rather than from
    `PricedService`'s own gate; `PlainBasedService` (its own `own`, plus `audit` inherited
    from plain `AbstractQuote`) publishes `own` — and `root`, which `AbstractQuote` inherits
    from the `@WebService` `RootQuote` above it. That last row is the half of the rule the
    others cannot show: the check filters by DECLARING class, the walk does not stop at
    the first plain class, so a method declared by an annotated grandparent still reaches
    the gate below through a plain parent."""
    tiered = "http://tiered.soapf.acme.com/"
    plain = "http://plain.soapf.acme.com/"
    assert f"{{{tiered}}}tier" in soap_final_paths, sorted(soap_final_paths)
    assert f"{{{tiered}}}price" in soap_final_paths, sorted(soap_final_paths)
    assert f"{{{plain}}}own" in soap_final_paths, sorted(soap_final_paths)
    assert f"{{{plain}}}root" in soap_final_paths, sorted(soap_final_paths)
    assert f"{{{plain}}}audit" not in soap_final_paths, sorted(soap_final_paths)
    assert not any(p.endswith("audit") for p in soap_final_paths), sorted(soap_final_paths)
