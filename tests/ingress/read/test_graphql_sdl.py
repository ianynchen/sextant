"""The `.graphqls` reader (2H design §2): SDL text in, one verbatim
`embedded_descriptor` fact per file out.

The reader never parses — Spring merges every `.graphqls` under the root into
ONE schema, so a per-file interpretation would be wrong about any type a
sibling file declares. Merging is the interpreter's job, module-wide (2G
design §3), and the proof that this reader does not reach a GraphQL runtime
lives in `tests/architecture/test_protobuf_confinement.py`, where the rest of
the schema-format confinement rule already is.
"""

from pathlib import Path

from sextant.application.ports.artifacts import ReadRequest, group_files_by_reader
from sextant.domain.resource_files import list_files
from sextant.ingress.read.avsc import AvscReader
from sextant.ingress.read.graphql_sdl import GraphqlSdlReader
from sextant.ingress.read.properties import PropertiesReader
from sextant.ingress.read.proto_source import ProtoSourceReader
from sextant.ingress.read.yaml_config import YamlConfigReader

REPO = Path(__file__).parents[3]
GRAPHQL_FIXTURE = REPO / "fixtures" / "orders-service" / "src" / "main" / "resources" / "graphql"


def _write(root: Path, name: str, text: str) -> Path:
    file = root / name
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(text, encoding="utf-8")
    return file


def _read(reader, root: Path, *files: Path, module_id: str = "com.acme:orders"):
    return reader.read(ReadRequest(module_id=module_id, version="1.0.0", files=files, root=root))


def test_the_reader_accepts_both_sdl_extensions_and_nothing_else():
    """Spring GraphQL's own default is `**/*.graphqls`, and `.graphql` is the
    spelling the rest of the ecosystem uses for the same file."""
    reader = GraphqlSdlReader()
    assert reader.accepts("graphqls")
    assert reader.accepts("graphql")
    assert not reader.accepts("proto")
    assert not reader.accepts("avsc")
    assert not reader.accepts("yml")


def test_one_verbatim_source_descriptor_per_sdl_file(tmp_path: Path):
    """Verbatim because the interpreter is the only thing that may understand
    the format: anything this reader normalized would be a projection it made
    up, and the SDL's own text is what a later merge has to work from."""
    text = "type Order {\n  id: ID!\n}\n"
    file = _write(tmp_path, "schema.graphqls", text)

    [(document, facts)] = _read(GraphqlSdlReader(), tmp_path, file)

    assert not document.partial
    assert document.language == "graphql"
    assert len(facts) == 1
    fact = facts[0]
    assert fact.kind == "embedded_descriptor"
    assert fact.schema_format == "graphql"
    # SDL is a repository file that compiles into no class: source origin, and
    # the `declared` evidence tier that follows from it.
    assert fact.origin == "source"
    assert fact.payload == text
    assert fact.document_id == document.document_id
    # The file's own path under the schema root — display identity, the same
    # role `symbol` plays for the `.proto` reader. It is what a gap names when
    # the interpreter cannot read this file.
    assert fact.symbol == "schema.graphqls"


def test_every_sdl_file_of_task_1s_fixture_is_read_as_its_own_descriptor():
    """Two files, two facts: the multi-file schema stays two documents here
    and becomes one type universe only in the interpreter."""
    files = tuple(sorted(GRAPHQL_FIXTURE.glob("*.graphqls")))
    pairs = _read(GraphqlSdlReader(), GRAPHQL_FIXTURE, *files)

    by_path = {document.relative_path: (document, facts) for document, facts in pairs}
    assert set(by_path) == {"audit.graphqls", "schema.graphqls"}
    for path, (document, facts) in by_path.items():
        assert not document.partial
        assert [fact.symbol for fact in facts] == [path]
        assert facts[0].payload == (GRAPHQL_FIXTURE / path).read_text(encoding="utf-8")


def test_a_file_that_is_not_text_degrades_honestly(tmp_path: Path):
    """The one failure a reader that never parses can still have. No `symbol`
    is invented for it: `partial` is the whole story, exactly as the `.avsc`
    reader treats a file it cannot read."""
    file = tmp_path / "binary.graphqls"
    file.write_bytes(b"\xff\xfe\x00type Order")

    [(document, facts)] = _read(GraphqlSdlReader(), tmp_path, file)

    assert document.partial
    assert document.partial_reason is not None
    assert facts == []


def test_the_sdl_reader_coexists_with_every_other_reader_in_the_registry(tmp_path: Path):
    """One registry serves config roots and schema roots alike, so a new
    reader that claimed an extension another already owns would silently
    steal its files."""
    properties_file = _write(tmp_path, "application.properties", "a=1\n")
    yaml_file = _write(tmp_path, "application.yml", "a: 1\n")
    avsc_file = _write(tmp_path, "schema.avsc", '{"type":"record","name":"X","fields":[]}')
    proto_file = _write(tmp_path, "schema.proto", 'syntax = "proto3";\nmessage X {}\n')
    sdl_file = _write(tmp_path, "schema.graphqls", "type X { id: ID! }\n")
    alternate_sdl_file = _write(tmp_path, "other.graphql", "type Y { id: ID! }\n")

    readers = [
        PropertiesReader(),
        YamlConfigReader(),
        AvscReader(),
        ProtoSourceReader(),
        GraphqlSdlReader(),
    ]
    grouped = group_files_by_reader(list_files(tmp_path), readers)

    by_reader = {type(reader).__name__: owned for reader, owned in grouped}
    assert by_reader["PropertiesReader"] == (properties_file,)
    assert by_reader["YamlConfigReader"] == (yaml_file,)
    assert by_reader["AvscReader"] == (avsc_file,)
    assert by_reader["ProtoSourceReader"] == (proto_file,)
    assert by_reader["GraphqlSdlReader"] == (alternate_sdl_file, sdl_file)
