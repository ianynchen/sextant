import json
import subprocess
from pathlib import Path

import duckdb
from click.testing import CliRunner

from sextant.cli.app import cli
from sextant.domain.factfile import read_fact_file

REPO = Path(__file__).parents[2]
FIXTURE = REPO / "fixtures" / "orders-service"


def _run(workspace: Path) -> None:
    runner = CliRunner()
    for command in ("analyze", "render", "export"):
        result = runner.invoke(
            cli, ["module", command, str(FIXTURE), "--workspace", str(workspace)]
        )
        assert result.exit_code == 0, result.output


def _fingerprint(workspace: Path) -> dict[str, bytes]:
    captured = {}
    for path in sorted(workspace.rglob("*")):
        if path.is_file() and path.suffix in {".jsonl", ".json", ".md", ".parquet"}:
            captured[str(path.relative_to(workspace))] = path.read_bytes()
    return captured


def test_output_is_byte_identical_when_the_pipeline_runs_twice(tmp_path: Path):
    subprocess.run(["mvn", "-q", "-o", "compile"], cwd=FIXTURE, check=True)
    first, second = tmp_path / "one", tmp_path / "two"
    _run(first)
    _run(second)
    assert _fingerprint(first) == _fingerprint(second)


def test_the_document_names_every_fixture_endpoint_and_its_gaps(tmp_path: Path):
    subprocess.run(["mvn", "-q", "-o", "compile"], cwd=FIXTURE, check=True)
    _run(tmp_path)
    document = (tmp_path / "render" / "architecture.md").read_text()
    for route in ("POST", "GET", "/v1/orders", "/v1/orders/{id}"):
        assert route in document
    assert "Known gaps" in document
    assert "## Outbound endpoints" in document
    assert "/billing/invoices" in document
    assert "/billing/settlements" in document
    # InventoryWebClient#search builds its URL from a uriBuilder lambda: the
    # fluent engine follows only one hop, so path stays honestly NULL rather
    # than guessed, and the endpoint column says so instead of `GET None`.
    assert "GET (unresolved)" in document
    assert "classDiagram" in document
    # Phase 2D (Task 11): a verbless messaging row renders `protocol path`,
    # no method — `order-events` is now `direction: both` (merged with the
    # producer catalogs' own `KafkaTemplate.send`), so it appears once in
    # each of the inbound and outbound sections.
    assert "kafka order-events" in document
    # Phase 2D (Task 12): the @SendTo reply row keeps its own identity —
    # `order-return-receipts` never merges into `order-returns`, since the
    # reply topic is a distinct destination — and carries its own contract
    # (`onReturn`'s return type, ReceiptView) rather than the handler's.
    assert "kafka order-return-receipts" in document
    # A NULL-path outbound messaging row (no literal destination resolved —
    # here `sendDefault`) renders `{protocol} (unresolved)`, the same
    # honesty rule as the HTTP `GET (unresolved)` row above.
    assert "kafka (unresolved)" in document


def test_every_fact_the_extractor_writes_validates_against_the_domain_model(tmp_path: Path):
    """The contract between the two halves of the fact stream (final review,
    M5). `load_facts` reads the JSONL straight into DuckDB — deliberately,
    for the bulk-load reason NFR-11 states — so nothing in the running
    pipeline ever puts the extractor's own output through the pydantic models
    that define D00 §5. A field the extractor renamed, a `kind` outside the
    closed set, an argument shape the model does not describe: all of it
    would flow through the pipeline and only surface as a column that reads
    NULL for no visible reason.

    So the whole fact tree the fixture produces is validated here, line by
    line, through the project's own reader — the document header as
    `Document`, every following line through `TypeAdapter(Fact)`, which
    raises on the first one the model refuses. The kind check keeps the test
    from passing vacuously on an empty or truncated tree; `module` is absent
    on purpose, being the detector's fact rather than the scanner's."""
    subprocess.run(["mvn", "-q", "-o", "compile"], cwd=FIXTURE, check=True)
    _run(tmp_path)

    files = sorted((tmp_path / "facts").rglob("*.jsonl"))
    validated = [read_fact_file(path) for path in files]
    kinds = {fact.kind for _, facts in validated for fact in facts}
    total = sum(len(facts) for _, facts in validated)

    assert files != []
    assert {"annotation", "call_site", "symbol"} <= kinds
    assert total >= len(files)


def test_the_bundle_answers_what_the_workspace_answered(tmp_path: Path):
    subprocess.run(["mvn", "-q", "-o", "compile"], cwd=FIXTURE, check=True)
    _run(tmp_path)  # analyze + render + export
    # Phase 2D (Task 12): metadata.json's own direction/protocol buckets
    # (written by analyze, D05 §3) count every messaging protocol too, a
    # `both` row counting on both sides (metadata.py's own rule) — the same
    # 55-endpoint fixture as the endpoints.parquet check below, viewed
    # through the other artifact.
    metadata = json.loads((tmp_path / "metadata.json").read_text())
    assert metadata["endpoints"]["inbound"] == {
        "http": 18,
        "jms": 2,
        "kafka": 8,
        "pubsub": 1,
        "sqs": 1,
    }
    assert metadata["endpoints"]["outbound"] == {
        "http": 19,
        "jms": 2,
        "kafka": 7,
        "pubsub": 1,
        "sqs": 2,
    }
    runner = CliRunner()
    result = runner.invoke(cli, ["module", "export", str(FIXTURE), "--workspace", str(tmp_path)])
    assert result.exit_code == 0, result.output
    bundle = Path(result.output.strip())
    manifest = json.loads((bundle / "manifest.json").read_text())
    assert manifest["producer"]["catalog_hash"].startswith("sha256:")
    assert "reactive_flow_not_traced" in manifest["gaps"]
    assert "endpoints" in manifest["contents"]["tables"]
    rows = duckdb.sql(
        f"SELECT direction, count(*) AS n FROM read_parquet('{bundle / 'graph' / 'endpoints.parquet'}') "
        "GROUP BY direction ORDER BY direction"
    ).fetchall()
    # Phase 2C: the spring-resttemplate catalog's four `single_call` routes
    # (BillingRestTemplate), plus the three `fluent` catalogs' eight
    # reconstructed-chain routes (WebClient/RestClient/OkHttp), join the
    # outbound side, real end to end.
    # Phase 2D (Task 10): the three listener catalogs add 11 inbound rows
    # (kafka 8, jms 2, sqs 1 — see test_pipeline.py for the full breakdown)
    # and 2 kafka outbound `@SendTo` reply rows.
    # Phase 2D (Task 11): the five producer catalogs (six files —
    # `ReplyingKafkaTemplate` gets its own, `matches.owner` being
    # single-valued) add 11 raw derived rows, five of which immediately
    # merge into an inbound row — four already existing from Task 10
    # (`order-events`, `order-audit`, `order-returns`, `audit.queue`) plus
    # one new on both sides in this same task (pubsub `order-notifications`,
    # the only Task 11 merge where neither side pre-existed). Each merge
    # converts one inbound + one outbound row into one `both` row, so five
    # merges: inbound 28+1-5=24, outbound 20+10-5=25, both 1+5=6 — see
    # test_pipeline.py for the full row-by-row breakdown.
    assert rows == [("both", 6), ("inbound", 24), ("outbound", 25)]
