import json
import subprocess
from pathlib import Path

from click.testing import CliRunner

from sextant.cli.app import cli

REPO = Path(__file__).parents[2]
FIXTURE = REPO / "fixtures" / "orders-service"


def test_analyze_writes_metadata_and_reports_endpoint_count(tmp_path: Path):
    subprocess.run(["mvn", "-q", "-o", "compile"], cwd=FIXTURE, check=True)
    result = CliRunner().invoke(
        cli, ["module", "analyze", str(FIXTURE), "--workspace", str(tmp_path)]
    )
    assert result.exit_code == 0, result.output
    metadata = json.loads((tmp_path / "metadata.json").read_text())
    assert metadata["endpoints"]["inbound"]["http"] == 3


def test_render_writes_the_document_after_analyze(tmp_path: Path):
    runner = CliRunner()
    runner.invoke(cli, ["module", "analyze", str(FIXTURE), "--workspace", str(tmp_path)])
    result = runner.invoke(
        cli, ["module", "render", str(FIXTURE), "--workspace", str(tmp_path)]
    )
    assert result.exit_code == 0, result.output
    document = (tmp_path / "render" / "architecture.md").read_text()
    assert "POST" in document and "/v1/orders" in document


def test_render_exits_nonzero_with_a_message_when_no_workspace_exists(tmp_path: Path):
    result = CliRunner().invoke(
        cli, ["module", "render", str(FIXTURE), "--workspace", str(tmp_path)]
    )
    assert result.exit_code != 0
    assert "module analyze" in result.output
