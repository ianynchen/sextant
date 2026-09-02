"""The `.wsdl`/`.xsd` reader (2I design §3): XML text in, one verbatim
`embedded_descriptor` fact per file out.

The reader never parses. A WSDL is meaningless without the `.xsd` files its
`<types>` imports, and a standalone `.xsd` joins the same type universe, so a
per-file interpretation would be wrong about every cross-file reference —
merging is the interpreter's job, module-wide (2G design §3), exactly as it is
for SDL. Two extensions, ONE `schema_format`, because a WSDL embeds XSD in its
`<types>` element: the two files are two spellings of one type universe, not
two formats.

That this reader reaches no XML library beyond the standard one lives in
`tests/architecture/test_protobuf_confinement.py`, where the rest of the
schema-format confinement rule already is.
"""

from pathlib import Path

from sextant.application.ports.artifacts import ReadRequest, group_files_by_reader
from sextant.domain.ignorefile import IgnoreRules
from sextant.domain.resource_files import list_files
from sextant.ingress.read.avsc import AvscReader
from sextant.ingress.read.graphql_sdl import GraphqlSdlReader
from sextant.ingress.read.properties import PropertiesReader
from sextant.ingress.read.proto_source import ProtoSourceReader
from sextant.ingress.read.wsdl_xsd import WsdlXsdReader
from sextant.ingress.read.yaml_config import YamlConfigReader

REPO = Path(__file__).parents[3]
WSDL_FIXTURE = REPO / "fixtures" / "orders-service" / "src" / "main" / "resources" / "wsdl"


def _write(root: Path, name: str, text: str) -> Path:
    file = root / name
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(text, encoding="utf-8")
    return file


def _read(reader, root: Path, *files: Path, module_id: str = "com.acme:orders"):
    return reader.read(ReadRequest(module_id=module_id, version="1.0.0", files=files, root=root))


def test_the_reader_accepts_both_contract_extensions_and_nothing_else():
    """One reader for both, because they are one type universe: a WSDL's
    `<types>` holds XSD, and the `.xsd` beside it is the same schema split
    across a file boundary."""
    reader = WsdlXsdReader()
    assert reader.accepts("wsdl")
    assert reader.accepts("xsd")
    assert not reader.accepts("xml")
    assert not reader.accepts("graphqls")
    assert not reader.accepts("proto")
    assert not reader.accepts("avsc")


def test_the_reader_serves_the_schema_loop():
    """`analyze` partitions its two read loops on this declaration, never on
    the root a file was found under — and `src/main/resources/wsdl` sits
    inside a resource root exactly as the SDL directory does."""
    assert WsdlXsdReader().reads_schema_sources is True


def test_one_verbatim_source_descriptor_per_xsd_file(tmp_path: Path):
    """Verbatim because the interpreter is the only thing that may understand
    the format: anything normalized here would be a projection this reader
    made up, and the file's own text is what a later cross-file merge has to
    work from."""
    text = '<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"/>\n'
    file = _write(tmp_path, "orders-types.xsd", text)

    [(document, facts)] = _read(WsdlXsdReader(), tmp_path, file)

    assert not document.partial
    # The file's own kind, not the shared `schema_format`: `language` says
    # which format a given file WAS (D00 §2), and these two differ there even
    # though they interpret as one.
    assert document.language == "xsd"
    assert len(facts) == 1
    fact = facts[0]
    assert fact.kind == "embedded_descriptor"
    # One format covering both extensions — a WSDL embeds XSD in `<types>`.
    assert fact.schema_format == "wsdl"
    # A contract file in the repository compiles into no class: source origin,
    # and the `declared` evidence tier that follows from it.
    assert fact.origin == "source"
    assert fact.payload == text
    assert fact.document_id == document.document_id
    # The file's own path under the schema root — display identity, and the
    # name a gap carries when the interpreter cannot read this file. It is
    # also what a sibling's `schemaLocation` is resolved against, so it must
    # be the path and never a name read out of the document.
    assert fact.symbol == "orders-types.xsd"


def test_a_wsdl_file_reads_as_the_same_format_under_its_own_language(tmp_path: Path):
    text = '<wsdl:definitions xmlns:wsdl="http://schemas.xmlsoap.org/wsdl/"/>\n'
    file = _write(tmp_path, "orders.wsdl", text)

    [(document, facts)] = _read(WsdlXsdReader(), tmp_path, file)

    assert document.language == "wsdl"
    assert facts[0].schema_format == "wsdl"
    assert facts[0].payload == text
    assert facts[0].symbol == "orders.wsdl"


def test_a_nested_file_is_named_by_its_path_under_the_schema_root(tmp_path: Path):
    """`schemaLocation` is relative to the importing file, so the symbol has
    to carry the whole relative path — a bare file name would make two
    same-named schemas in different directories indistinguishable to the
    interpreter's cross-file resolution."""
    file = _write(tmp_path, "common/types.xsd", '<xs:schema xmlns:xs="x"/>\n')

    [(_, facts)] = _read(WsdlXsdReader(), tmp_path, file)

    assert facts[0].symbol == "common/types.xsd"


def test_every_contract_file_of_task_1s_fixture_is_read_as_its_own_descriptor():
    """Two files, two facts: the WSDL and the XSD it imports stay two
    documents here and become one type universe only in the interpreter."""
    files = tuple(sorted(WSDL_FIXTURE.iterdir()))
    pairs = _read(WsdlXsdReader(), WSDL_FIXTURE, *files)

    by_path = {document.relative_path: (document, facts) for document, facts in pairs}
    assert set(by_path) == {"orders.wsdl", "orders-types.xsd"}
    for path, (document, facts) in by_path.items():
        assert not document.partial
        assert [fact.symbol for fact in facts] == [path]
        assert facts[0].schema_format == "wsdl"
        assert facts[0].payload == (WSDL_FIXTURE / path).read_text(encoding="utf-8")


def test_a_file_that_is_not_text_degrades_honestly(tmp_path: Path):
    """The one failure a reader that never parses can still have. No `symbol`
    is invented for it: `partial` is the whole story, exactly as the `.avsc`
    and `.graphqls` readers treat a file they cannot read."""
    file = tmp_path / "broken.xsd"
    file.write_bytes(b"\xff\xfe\x00<xs:schema")

    [(document, facts)] = _read(WsdlXsdReader(), tmp_path, file)

    assert document.partial
    assert document.partial_reason is not None
    assert facts == []


def test_xml_that_does_not_parse_is_still_emitted_verbatim(tmp_path: Path):
    """The reader is not the parse boundary: a file that is text is a payload,
    and whether it is well-formed XML is the interpreter's question — which is
    the only place that may answer it (2G design §3). Reported there as that
    file's gap, named by this symbol."""
    file = _write(tmp_path, "truncated.wsdl", "<wsdl:definitions>")

    [(document, facts)] = _read(WsdlXsdReader(), tmp_path, file)

    assert not document.partial
    assert [fact.symbol for fact in facts] == ["truncated.wsdl"]


def test_the_contract_reader_coexists_with_every_other_reader_in_the_registry(tmp_path: Path):
    """One registry serves config roots and schema roots alike, so a new
    reader that claimed an extension another already owns would silently
    steal its files."""
    properties_file = _write(tmp_path, "application.properties", "a=1\n")
    yaml_file = _write(tmp_path, "application.yml", "a: 1\n")
    avsc_file = _write(tmp_path, "schema.avsc", '{"type":"record","name":"X","fields":[]}')
    proto_file = _write(tmp_path, "schema.proto", 'syntax = "proto3";\nmessage X {}\n')
    sdl_file = _write(tmp_path, "schema.graphqls", "type X { id: ID! }\n")
    wsdl_file = _write(tmp_path, "orders.wsdl", '<wsdl:definitions xmlns:wsdl="w"/>\n')
    xsd_file = _write(tmp_path, "orders-types.xsd", '<xs:schema xmlns:xs="x"/>\n')

    readers = [
        PropertiesReader(),
        YamlConfigReader(),
        AvscReader(),
        ProtoSourceReader(),
        GraphqlSdlReader(),
        WsdlXsdReader(),
    ]
    grouped = group_files_by_reader(
        list_files(tmp_path, tmp_path, IgnoreRules.load(tmp_path)), readers
    )

    by_reader = {type(reader).__name__: owned for reader, owned in grouped}
    assert by_reader["PropertiesReader"] == (properties_file,)
    assert by_reader["YamlConfigReader"] == (yaml_file,)
    assert by_reader["AvscReader"] == (avsc_file,)
    assert by_reader["ProtoSourceReader"] == (proto_file,)
    assert by_reader["GraphqlSdlReader"] == (sdl_file,)
    assert by_reader["WsdlXsdReader"] == (xsd_file, wsdl_file)
