"""The registered `ArtifactReader`s (D00 §5c) — one place `cli/app.py`'s
`analyze()` call and the config-bearing-extension drift test
(`tests/application/test_enrich_tools.py`) both build against, rather than
two independently-hardcoded copies of the same six readers that could
silently drift apart (2K Task 5 fix round 1, minor)."""

from sextant.application.ports.artifacts import ArtifactReader
from sextant.ingress.read.avsc import AvscReader
from sextant.ingress.read.graphql_sdl import GraphqlSdlReader
from sextant.ingress.read.properties import PropertiesReader
from sextant.ingress.read.proto_source import ProtoSourceReader
from sextant.ingress.read.wsdl_xsd import WsdlXsdReader
from sextant.ingress.read.yaml_config import YamlConfigReader

# Registry order matters (`group_files_by_reader`'s own docstring: "the
# first reader whose `accepts` claims a file's extension owns it"), kept
# exactly as `cli/app.py`'s own `analyze()` call listed it before this
# extraction.
READERS: tuple[ArtifactReader, ...] = (
    PropertiesReader(),
    YamlConfigReader(),
    AvscReader(),
    ProtoSourceReader(),
    GraphqlSdlReader(),
    WsdlXsdReader(),
)
