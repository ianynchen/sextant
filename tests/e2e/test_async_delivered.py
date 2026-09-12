"""Async and internal boundaries are delivered when a Spring Integration flow declared with
the framework's own annotations is visible, channel by channel.

**What "visible" means here, because it is not an endpoint row.** A Spring Integration
channel is an in-process pipe with no wire identity — which broker it reaches, if any, is
exactly what bytecode cannot say — so `spring-integration.yml` deliberately derives NO
endpoint rows and files each channel a module names as a `channel_destination` open
question instead. That question IS the derived output, and it is what a reader sees. The
first draft of this test asserted on `endpoints` and found zero, including for the two
annotations the catalog already read; the table was wrong, not the catalog.

**Not a document check.** Real bytecode, real pipeline, assertion on what was derived.
"""

import pytest
from click.testing import CliRunner

from fixture_build import FIXTURES, compile_fixture
from sextant.cli.app import cli
from sextant.storage.duckdb.workspace import DuckDbWorkspace

FIXTURE = FIXTURES / "spring-integration-probe"


@pytest.fixture(scope="module")
def channels(tmp_path_factory: pytest.TempPathFactory) -> set[str]:
    workspace_dir = tmp_path_factory.mktemp("integration")
    compile_fixture(FIXTURE)
    result = CliRunner().invoke(
        cli, ["module", "analyze", str(FIXTURE), "--workspace", str(workspace_dir)]
    )
    assert result.exit_code == 0, result.output
    workspace = DuckDbWorkspace(workspace_dir / "workspace.duckdb")
    try:
        return {
            str(row["path"])
            for row in workspace.query("open_questions")
            if str(row["question"]) == "channel_destination"
        }
    finally:
        workspace.close()


# The seven annotations Spring Integration ships beside the two the catalog already read,
# each with the channel attribute it ACTUALLY declares (javap, spring-integration-core 6.2.4).
# A flow written with these is the ordinary shape of a Spring Integration application, and
# before `G-47` every one of these channels was absent from the document.
_EXPECTED = {
    "raw.orders",  # @Transformer inputChannel
    "clean.orders",  # @Transformer outputChannel
    "valid.orders",  # @Filter outputChannel, @Splitter inputChannel
    "order.lines",  # @Splitter outputChannel, @Aggregator inputChannel
    "order.totals",  # @Aggregator outputChannel, @Router inputChannel
    "priced.totals",  # @BridgeFrom value
    "archive.orders",  # @BridgeTo value
}


def test_every_channel_bearing_annotation_derives_its_channel(channels: set[str]):
    """`G-47`. The catalog read 2 of the 9 channel-bearing annotations. A module using any
    of the other seven had those channels absent — and `@Transformer`, `@Filter`,
    `@Splitter`, `@Aggregator` and `@Router` are the components a Spring Integration flow
    is made of."""
    missing = _EXPECTED - channels
    assert missing == set(), (
        f"{len(missing)} of {len(_EXPECTED)} channels derived nothing: {sorted(missing)}. "
        f"Derived: {sorted(channels)}"
    )


def test_the_two_annotations_already_read_still_derive(channels: set[str]):
    """The control — `Shape2AdapterAndHandler`'s `@ServiceActivator(inputChannel =
    "amqpInputChannel")`, which derived before this change."""
    assert "amqpInputChannel" in channels, (
        f"the @ServiceActivator channel stopped deriving. Derived: {sorted(channels)}"
    )
