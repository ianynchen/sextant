"""Schema-format confinement (2G design §3): exactly one module in the system
understands a schema format, and exactly one shells to a schema compiler.

The layering contracts in `pyproject.toml` reason about `sextant.*` packages,
so neither can see an import of a third-party runtime. This rule is about a
third-party import, and it is the rule the whole "dumb extractor / one
interpreter" layering rests on: a second reader of `google.protobuf` is a
second place that knows what a descriptor means, and the next schema format
would then need adding twice.

`grpc_tools` is confined the same way for the same reason, one step earlier —
compiling `.proto` text is the source-file reader's job, not the
interpreter's, and not anybody else's.

`graphql` is the third entry and the rule's first real test: 2H added a schema
format, and it added it by extending the interpreter and this allowlist — the
SDL reader (`ingress/read/graphql_sdl.py`) emits its file verbatim and never
imports a GraphQL runtime at all.

2I's WSDL/XSD branch adds no runtime to confine: it reads XML with the
STANDARD LIBRARY, and the rule it needs is the negative one — that no
third-party XML package was quietly added to do the job. Since the interpreter
split into one module per format (2I design §3), each allowlist names its
format's module rather than the package: `google.protobuf` in the protobuf
branch and nowhere else, `graphql` in the SDL branch and nowhere else. The
rule was always per-format; before the split there was only one file to point
at.
"""

import ast
import sys
from pathlib import Path

SOURCE_ROOT = Path(__file__).parents[2] / "src" / "sextant"

INTERPRET = SOURCE_ROOT / "ingress" / "interpret"
# The per-format branches of 2G design §3, and the `.proto` reader of §2.
PROTOBUF_BRANCH = INTERPRET / "protobuf.py"
GRAPHQL_BRANCH = INTERPRET / "graphql_sdl.py"
WSDL_BRANCH = INTERPRET / "wsdl_xsd.py"
PROTO_READER = SOURCE_ROOT / "ingress" / "read" / "proto_source.py"
WSDL_READER = SOURCE_ROOT / "ingress" / "read" / "wsdl_xsd.py"

# Every third-party XML library a WSDL/XSD branch could have reached for
# instead of the standard library. Naming them is the point: the branch parses
# XML, so "no XML dependency" is only checkable against the packages that
# would have been the alternative.
THIRD_PARTY_XML = ("lxml", "defusedxml", "xmlschema", "zeep", "xmltodict", "bs4")


def _imported_modules(path: Path) -> set[str]:
    """Every module name a file imports, dotted — `from x import y` counted
    as both `x` and `x.y`, so a package reached through either spelling is
    seen."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            names |= {f"{node.module}.{alias.name}" for alias in node.names}
    return names


def _importers(package: str) -> list[Path]:
    """Every Python source Sextant ships that imports the package or anything
    under it."""
    return sorted(
        path
        for path in SOURCE_ROOT.rglob("*.py")
        if any(
            name == package or name.startswith(f"{package}.") for name in _imported_modules(path)
        )
    )


def _offenders(package: str, allowed: Path) -> list[str]:
    return [str(path.relative_to(SOURCE_ROOT)) for path in _importers(package) if path != allowed]


def test_the_protobuf_runtime_is_imported_only_by_its_own_branch():
    assert _offenders("google.protobuf", PROTOBUF_BRANCH) == []


def test_the_graphql_runtime_is_imported_only_by_its_own_branch():
    """The SDL reader is the module this would catch first: it hands the
    interpreter the file's text verbatim, and a `parse` call there would be a
    second place that knows what SDL means."""
    assert _offenders("graphql", GRAPHQL_BRANCH) == []


def test_the_schema_compiler_is_imported_only_by_the_proto_reader():
    assert _offenders("grpc_tools", PROTO_READER) == []


def test_no_third_party_xml_library_is_shipped_at_all():
    """The WSDL/XSD branch's own rule (2I design §3): stdlib `ElementTree`,
    zero new dependencies. There is no runtime to confine here, so the rule is
    the negative one — and it is stronger than the others, because NOTHING may
    import these, not even the branch that parses XML."""
    assert {package: _importers(package) for package in THIRD_PARTY_XML} == {
        package: [] for package in THIRD_PARTY_XML
    }


def test_the_wsdl_reader_parses_nothing_at_all():
    """The reader emits its file verbatim, so it must not reach even the
    standard library's parser — that is the interpreter's alone (2G design
    §3), which is the same line the SDL reader holds against `graphql`."""
    assert not any(name.startswith("xml.") for name in _imported_modules(WSDL_READER))


def test_the_check_finds_the_protobuf_runtime_where_one_is_allowed_to_be():
    """A confinement check that matches nothing anywhere passes for the wrong
    reason. The protobuf branch is the one module that must read descriptors,
    so the check must see the import there."""
    assert PROTOBUF_BRANCH in _importers("google.protobuf")


def test_the_check_finds_the_graphql_runtime_where_one_is_allowed_to_be():
    """The same positive control, for the same reason: an empty offender list
    proves nothing unless the walk can be shown to see this import."""
    assert GRAPHQL_BRANCH in _importers("graphql")


def test_the_check_would_catch_a_module_that_imports_a_third_party_xml_library(
    tmp_path, monkeypatch
):
    """`test_no_third_party_xml_library_is_shipped_at_all` asserts an empty
    list, which passes for two reasons a bare empty list cannot tell apart: no
    violation, or a checker blind to one. Nothing shipped imports any of these
    — that is the point of the rule — so the positive control has to be
    synthetic, the same way `grpc_tools`'s is."""
    offender = tmp_path / "offender.py"
    offender.write_text("from lxml import etree\n", encoding="utf-8")
    monkeypatch.setattr(sys.modules[__name__], "SOURCE_ROOT", tmp_path)
    assert _importers("lxml") == [offender]


def test_the_check_finds_the_standard_library_parser_where_one_is_allowed_to_be():
    """And the branch that IS allowed to parse does — so the negative rule
    above is not passing because nothing here reads XML at all."""
    assert "xml.etree" in _imported_modules(WSDL_BRANCH)


def test_the_check_would_catch_a_module_that_imports_the_schema_compiler(tmp_path, monkeypatch):
    """The test above passes today for two reasons a bare empty offender list
    cannot tell apart: no violation, or a checker blind to one. Unlike
    `google.protobuf` (caught above, imported by the interpreter), nothing
    shipped imports `grpc_tools` at all — `proto_source.py` shells to
    `grpc_tools.protoc` as a subprocess (its own module docstring), so the
    walk above never actually sees a `grpc_tools` import to flag. Point it at
    a synthetic tree holding a module that DOES import `grpc_tools`, the
    same positive control the protobuf check gets for free from real code, to
    rule out the second reading."""
    offender = tmp_path / "offender.py"
    offender.write_text("import grpc_tools.protoc\n", encoding="utf-8")
    monkeypatch.setattr(sys.modules[__name__], "SOURCE_ROOT", tmp_path)
    assert _offenders("grpc_tools", PROTO_READER) == ["offender.py"]
