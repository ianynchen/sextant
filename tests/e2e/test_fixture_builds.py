import subprocess
from pathlib import Path

FIXTURE = Path(__file__).parents[2] / "fixtures" / "orders-service"


def test_fixture_produces_class_files_when_built():
    subprocess.run(["mvn", "-q", "-o", "compile"], cwd=FIXTURE, check=True)
    classes = FIXTURE / "target" / "classes" / "com" / "acme" / "orders"
    assert (classes / "OrderController.class").exists()
