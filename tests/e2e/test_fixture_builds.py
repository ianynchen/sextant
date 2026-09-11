from pathlib import Path

from fixture_build import compile_fixture

FIXTURE = Path(__file__).parents[2] / "fixtures" / "orders-service"


def test_fixture_produces_class_files_when_built():
    compile_fixture(FIXTURE)
    classes = FIXTURE / "target" / "classes" / "com" / "acme" / "orders"
    assert (classes / "OrderController.class").exists()
    contracts = classes / "contracts"
    assert (contracts / "OrderRequest.class").exists()
    assert (contracts / "OrderView.class").exists()
    assert (contracts / "CustomerRef.class").exists()
