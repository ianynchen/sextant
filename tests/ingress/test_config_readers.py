from pathlib import Path

from sextant.application.ports.artifacts import ReadRequest, group_files_by_reader
from sextant.domain.closed_sets import OriginTier
from sextant.domain.resource_files import list_files
from sextant.ingress.read.properties import PropertiesReader
from sextant.ingress.read.yaml_config import YamlConfigReader


def _write(root: Path, name: str, text: str) -> Path:
    file = root / name
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(text, encoding="utf-8")
    return file


def _read_one(reader, root: Path, file: Path, module_id: str = "com.acme:orders"):
    pairs = reader.read(ReadRequest(module_id=module_id, version="1.0.0", files=(file,), root=root))
    assert len(pairs) == 1
    return pairs[0]


# --- PropertiesReader ---------------------------------------------------


def test_properties_reader_accepts_only_the_properties_extension():
    reader = PropertiesReader()
    assert reader.accepts("properties")
    assert not reader.accepts("yml")
    assert not reader.accepts("yaml")


def test_properties_reader_flattens_a_dotted_key_verbatim(tmp_path: Path):
    file = _write(tmp_path, "application.properties", "a.b.c=v\n")
    document, facts = _read_one(PropertiesReader(), tmp_path, file)

    assert len(facts) == 1
    entry = facts[0]
    assert entry.key_raw == "a.b.c"
    assert entry.key_path == "a.b.c"
    assert entry.value == "v"
    assert entry.doc_index == 0
    assert entry.document_id == document.document_id


def test_properties_reader_keeps_trailing_spaces_and_placeholders_untouched(tmp_path: Path):
    file = _write(
        tmp_path,
        "application.properties",
        "trailing=v   \nplaceholder=${some.value}\n",
    )
    _, facts = _read_one(PropertiesReader(), tmp_path, file)

    values = {entry.key_raw: entry.value for entry in facts}
    assert values["trailing"] == "v   "
    assert values["placeholder"] == "${some.value}"


def test_properties_reader_supports_colon_and_equals_delimiters(tmp_path: Path):
    file = _write(tmp_path, "application.properties", "a=1\nb: 2\n")
    _, facts = _read_one(PropertiesReader(), tmp_path, file)

    values = {entry.key_raw: entry.value for entry in facts}
    assert values == {"a": "1", "b": "2"}


def test_properties_reader_skips_comments_and_blank_lines(tmp_path: Path):
    file = _write(
        tmp_path,
        "application.properties",
        "# a comment\n! another comment\n\nkey=value\n",
    )
    _, facts = _read_one(PropertiesReader(), tmp_path, file)

    assert [entry.key_raw for entry in facts] == ["key"]


def test_properties_reader_treats_a_backslash_escaped_delimiter_as_key_content(tmp_path: Path):
    # 2F review fix round 1: the naive first-`:`-or-`=` scan mis-parses
    # `a\:b=v` as key `a\` / value `b=v`. Per the Java properties spec, a
    # backslash-escaped delimiter is key content, not the split point.
    file = _write(tmp_path, "application.properties", "a\\:b=v\n")
    _, facts = _read_one(PropertiesReader(), tmp_path, file)

    assert len(facts) == 1
    entry = facts[0]
    # key_raw keeps the as-written, still-escaped spelling...
    assert entry.key_raw == "a\\:b"
    # ...key_path carries the unescaped form — the raw-vs-path distinction
    # D00 §5c states, made real for the first time by a flat format.
    assert entry.key_path == "a:b"
    assert entry.value == "v"


def test_properties_reader_skips_a_malformed_line_without_failing_the_file(tmp_path: Path):
    file = _write(tmp_path, "application.properties", "not-a-valid-line\nkey=value\n")
    document, facts = _read_one(PropertiesReader(), tmp_path, file)

    assert not document.partial
    assert [entry.key_raw for entry in facts] == ["key"]


def test_properties_reader_document_fields_mirror_a_scanner_emitted_document(tmp_path: Path):
    file = _write(tmp_path, "sub/application.properties", "key=value\n")
    document, _ = _read_one(PropertiesReader(), tmp_path, file)

    assert document.relative_path == "sub/application.properties"
    assert document.module_id == "com.acme:orders"
    assert document.language == "properties"
    assert document.scanner_id == "sextant-config-reader"
    assert document.origin_tier == OriginTier.MODULE_OUTPUT
    assert document.content_hash.startswith("sha256:")
    assert document.document_id  # a non-empty derived id
    assert not document.partial
    assert document.partial_reason is None


# --- YamlConfigReader -----------------------------------------------------


def test_yaml_reader_accepts_yml_and_yaml_but_normalizes_the_document_language(tmp_path: Path):
    reader = YamlConfigReader()
    assert reader.accepts("yml")
    assert reader.accepts("yaml")
    assert not reader.accepts("properties")

    file = _write(tmp_path, "application.yml", "a: 1\n")
    document, _ = _read_one(reader, tmp_path, file)
    assert document.language == "yaml"


def test_yaml_reader_flattens_nested_maps_to_dotted_paths(tmp_path: Path):
    file = _write(tmp_path, "application.yml", "a:\n  b:\n    c: v\n")
    _, facts = _read_one(YamlConfigReader(), tmp_path, file)

    assert len(facts) == 1
    assert facts[0].key_raw == "a.b.c"
    assert facts[0].key_path == "a.b.c"
    assert facts[0].value == "v"


def test_yaml_reader_normalizes_a_list_value_to_indexed_segments(tmp_path: Path):
    file = _write(tmp_path, "application.yml", "foo:\n  - one\n  - two\n")
    _, facts = _read_one(YamlConfigReader(), tmp_path, file)

    values = {entry.key_path: entry.value for entry in facts}
    assert values == {"foo[0]": "one", "foo[1]": "two"}


def test_yaml_reader_assigns_doc_index_per_document_in_a_multi_document_stream(tmp_path: Path):
    file = _write(tmp_path, "application.yml", "a: one\n---\na: two\n---\na: three\n")
    _, facts = _read_one(YamlConfigReader(), tmp_path, file)

    assert [(entry.doc_index, entry.value) for entry in facts] == [
        (0, "one"),
        (1, "two"),
        (2, "three"),
    ]


def test_yaml_reader_never_coerces_a_scalar_that_looks_typed(tmp_path: Path):
    file = _write(
        tmp_path,
        "application.yml",
        "a: true\nb: 123\nc: 3.14\nd: null\ne: ~\n",
    )
    _, facts = _read_one(YamlConfigReader(), tmp_path, file)

    values = {entry.key_path: entry.value for entry in facts}
    assert values["a"] == "true"
    assert values["b"] == "123"
    assert values["c"] == "3.14"
    assert values["d"] == "null"
    assert values["e"] == "~"
    assert all(isinstance(value, str) for value in values.values())


def test_yaml_reader_document_fields_mirror_a_scanner_emitted_document(tmp_path: Path):
    # 2F review fix round 1: pins the same Document-field contract the
    # properties reader's equivalent test pins above — both readers share
    # `build_document`, but each path (and `language`) is worth asserting
    # on its own rather than trusting the shared helper by inference.
    file = _write(tmp_path, "sub/application.yml", "key: value\n")
    document, _ = _read_one(YamlConfigReader(), tmp_path, file)

    assert document.relative_path == "sub/application.yml"
    assert document.module_id == "com.acme:orders"
    assert document.language == "yaml"
    assert document.scanner_id == "sextant-config-reader"
    assert document.origin_tier == OriginTier.MODULE_OUTPUT
    assert document.content_hash.startswith("sha256:")
    assert document.document_id  # a non-empty derived id
    assert not document.partial
    assert document.partial_reason is None


def test_yaml_reader_degrades_honestly_on_an_unparseable_file(tmp_path: Path):
    file = _write(tmp_path, "application.yml", "a: [unclosed\n")
    document, facts = _read_one(YamlConfigReader(), tmp_path, file)

    assert document.partial
    assert document.partial_reason is not None
    assert facts == []


# --- Shared discovery/grouping helpers ------------------------------------


def test_list_files_sorts_by_relative_path_string_not_path_parts(tmp_path: Path):
    # 2F review fix round 1: `Path.__lt__` compares parts tuples, not the
    # rendered string — `("a", "b.yml")` sorts before `("a.yml",))`
    # because a shorter first segment always sorts first regardless of what
    # follows it, the reverse of comparing the relative path *strings*
    # `"a.yml"` and `"a/b.yml"` (`.` sorts before `/`), which is what NFR-1
    # actually means by "sorted by relative path."
    a_yml = _write(tmp_path, "a.yml", "a: 1\n")
    a_b_yml = _write(tmp_path, "a/b.yml", "a: 1\n")

    assert list_files(tmp_path) == (a_yml, a_b_yml)


def test_list_files_returns_every_file_sorted_by_relative_path(tmp_path: Path):
    _write(tmp_path, "z.properties", "a=1\n")
    _write(tmp_path, "a/b.yml", "a: 1\n")
    _write(tmp_path, "m.yml", "a: 1\n")

    files = list_files(tmp_path)

    assert files == (
        tmp_path / "a" / "b.yml",
        tmp_path / "m.yml",
        tmp_path / "z.properties",
    )


def test_group_files_by_reader_partitions_files_by_the_first_accepting_reader(tmp_path: Path):
    properties_file = tmp_path / "a.properties"
    yaml_file = tmp_path / "b.yml"
    other_file = tmp_path / "c.txt"
    files = (properties_file, yaml_file, other_file)
    properties_reader = PropertiesReader()
    yaml_reader = YamlConfigReader()

    grouped = group_files_by_reader(files, [properties_reader, yaml_reader])

    assert grouped == [
        (properties_reader, (properties_file,)),
        (yaml_reader, (yaml_file,)),
    ]
