"""Tests for the YAML catalog loader (D02 §1, §6).

Validates that catalogs load correctly from YAML files in a directory,
with closed-set constraints enforced on protocol and direction.
"""

from pathlib import Path

import pytest

from sextant.application.ports.catalogs import CatalogError
from sextant.ingress.catalogs.yaml_source import YamlCatalogSource

_MINIMAL_CATALOG = """id: {id}
style: annotation_driven
protocol: {protocol}
direction: inbound
matches: {{}}
"""


def _write_catalog(tmp_path: Path, filename: str, protocol: str = "http") -> None:
    """Write a minimal valid catalog YAML file to tmp_path with the given protocol.

    Args:
        tmp_path: Directory where the catalog will be written.
        filename: Name of the catalog file to create (e.g., "x-kafka.yml").
        protocol: The protocol value to use in the catalog (default: "http").
    """
    catalog_id = filename.replace(".yml", "")
    content = _MINIMAL_CATALOG.format(id=catalog_id, protocol=protocol)
    (tmp_path / filename).write_text(content, encoding="utf-8")


def test_broker_family_protocols_load_and_message_is_retired(tmp_path):
    """New broker family protocols (kafka, jms, sqs, pubsub) load correctly.

    MESSAGE protocol has been retired and replaced with the four specific
    broker family protocols. This test verifies all four new protocols load
    and are sorted by filename when returned.
    """
    for protocol in ("kafka", "jms", "sqs", "pubsub"):
        _write_catalog(tmp_path, f"x-{protocol}.yml", protocol=protocol)
    loaded = YamlCatalogSource(tmp_path).load()
    assert [c.protocol for c in loaded] == ["jms", "kafka", "pubsub", "sqs"]


def test_message_is_no_longer_a_protocol(tmp_path):
    """The 'message' protocol value is rejected as a closed-set violation.

    MESSAGE was removed from the Protocol closed set in favor of specific
    broker family protocols. Any catalog declaring protocol: message should
    raise CatalogError with a message about closed sets.
    """
    _write_catalog(tmp_path, "x.yml", protocol="message")
    with pytest.raises(CatalogError, match="closed"):
        YamlCatalogSource(tmp_path).load()
