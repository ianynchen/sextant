"""A call that reads a deployment-set key by name is the expression `${KEY}` (plan 3 Task 3,
approved N1; rulings R16, R17): `os.getenv("HOST")`, `os.environ["HOST"]` and
`os.environ.get("HOST", "d")` (`value-models/python-environment.yml`). A default the call
carries is declared and never the value; a key that is no literal is `non_enumerable`.

Each test scans a small program with the real Python scanner and reads the outbound row's
address, as `test_python_outbound` does."""

import pytest
from test_python_outbound import _CLIENTS, _outbound

from fixture_python import FIXTURES
from sextant.application.ports.detector import LibraryRoot


@pytest.fixture(scope="module")
def libraries(orders_fastapi_env) -> tuple[LibraryRoot, ...]:
    (site,) = (FIXTURES / "orders-fastapi" / ".venv" / "lib").glob("python*/site-packages")
    return tuple(LibraryRoot(name, version, site) for name, version in _CLIENTS.items())


_HEAD = "import os\nimport requests\ndef call(var: str) -> None:\n"


def _addresses(tmp_path, libraries, body: str) -> list[tuple[object, ...]]:
    """(peer, path, resolution) of each outbound row of `call`."""
    rows = _outbound(tmp_path, libraries, _HEAD + body)
    return [(row[1], row[2], row[4]) for row in rows]


@pytest.mark.parametrize(
    "read",
    [
        "os.getenv('HOST')",
        "os.getenv('HOST', 'localhost')",
        "os.getenv(key='HOST')",
        "os.getenv('HOST', default='localhost')",
        "os.environ['HOST']",
        "os.environ.get('HOST')",
        "os.environ.get('HOST', 'localhost')",
        "os.environ.get(key='HOST', default='localhost')",
    ],
)
def test_an_environment_read_in_a_url_is_the_key_expression(tmp_path, libraries, read):
    """The default a call carries is never the value: every spelling reads `${HOST}`, a literal
    default rendered inside it after the model's separator (plan 3 ruling R25)."""
    key = "HOST:-localhost" if "localhost" in read else "HOST"
    assert _addresses(tmp_path, libraries, f"    requests.get(f'http://{{{read}}}/x')\n") == [
        (None, f"http://${{{key}}}/x", "resolved")
    ]


@pytest.mark.parametrize("read", ["os.getenv('U')", "os.environ['U']", "os.environ.get('U', 'd')"])
def test_an_environment_read_is_the_whole_address(tmp_path, libraries, read):
    """R17: an argument that is a call's result resolves through the same walk as any value."""
    key = "U:-d" if "'d'" in read else "U"
    assert _addresses(tmp_path, libraries, f"    requests.get({read})\n") == [
        (None, f"${{{key}}}", "resolved")
    ]


@pytest.mark.parametrize("read", ["os.getenv(var)", "os.environ[var]", "os.environ.get(var, 'd')"])
def test_a_key_that_is_no_literal_is_unresolved(tmp_path, libraries, read):
    rows = _addresses(tmp_path, libraries, f"    requests.get(f'http://{{{read}}}/x')\n")
    assert all(resolution != "resolved" for _, _, resolution in rows)
    assert all("${" not in str(path) for _, path, _ in rows)


def test_a_default_after_or_is_never_the_value(tmp_path, libraries):
    """Review Focus 1: `os.getenv("K") or "d"` carries no default in the call, and the
    address is never `d`. The merged host is not read whole, and nothing of "dflt" is published."""
    rows = _addresses(
        tmp_path,
        libraries,
        "    requests.get('http://' + (os.getenv('K') or 'dflt') + '/x')\n",
    )
    # The `or` makes the host one of two values: read as a hole, so the row is partial.
    assert rows == [(None, "/x", "partial")]


# --- The entry form --------------------------------------------------------------------------


def _loaded(directory, text: str):
    from sextant.ingress.catalogs.yaml_source import YamlCatalogSource

    (directory / "value-models").mkdir()
    (directory / "value-models" / "invented.yml").write_text(text, encoding="utf-8")
    return YamlCatalogSource(directory).environment_reads()


def test_the_shipped_entries_read_as_the_typeshed_symbols():
    from sextant.ingress.catalogs.yaml_source import YamlCatalogSource
    from sextant.resources import catalogs_dir

    found = {
        (entry["owner"], entry["method"])
        for entry in YamlCatalogSource(catalogs_dir()).environment_reads()
    }
    assert found == {("os#", "getenv"), ("os/_Environ#", "__getitem__"), ("os/_Environ#", "get")}


@pytest.mark.parametrize(
    "entry",
    [
        "{ owner: os, method: getenv, by: x.md }",  # no key_arg
        "{ owner: os, method: getenv, key_arg: first, by: x.md }",  # not a reference
        "{ owner: os, method: getenv, key_arg: 0, default_arg: -1, by: x.md }",
        "{ owner: os, method: getenv, key_arg: 0 }",  # no probe
        "{ owner: os, method: getenv, key_arg: 0, value: 1, by: x.md }",  # unknown key
    ],
)
def test_a_malformed_environment_read_is_refused(tmp_path, entry):
    from sextant.application.ports.catalogs import CatalogError

    with pytest.raises(CatalogError, match="environment_reads"):
        _loaded(tmp_path, f"id: invented\nenvironment_reads:\n  - {entry}\n")


def test_a_call_stated_twice_is_refused(tmp_path):
    from sextant.application.ports.catalogs import CatalogError

    row = "{ owner: os, method: getenv, key_arg: 0, by: x.md }"
    with pytest.raises(CatalogError, match="twice"):
        _loaded(tmp_path, f"id: invented\nenvironment_reads:\n  - {row}\n  - {row}\n")


# --- The declared default ----------------------------------------------------------------------


def _read(tmp_path, libraries, body: str):
    """The answer of the one read `body` makes, as the walk gives it for `requests.get`'s url."""
    from test_fastapi_routes import _resolved
    from test_python_outbound import _MODELS

    from sextant.application.resolve.values import resolve_site, value_index
    from sextant.ingress.catalogs.yaml_source import YamlCatalogSource
    from sextant.resources import catalogs_dir

    workspace = _resolved(
        tmp_path, libraries, {"main.py": _HEAD + body, "models.py": _MODELS}, locked=_CLIENTS
    )
    source = YamlCatalogSource(catalogs_dir())
    index = value_index(
        workspace, returns_arguments=source.returns_arguments() + source.environment_reads()
    )
    (site,) = [
        row
        for row in workspace.query("call_sites")
        if row["name"] == "get" and str(row["owner"]).startswith("requests")
    ]
    answers = [
        binding.slots[0]
        for binding in resolve_site(
            workspace, {"caller": site["caller"], "ordinal": site["ordinal"]}, index=index
        )
    ]
    workspace.close()
    return answers


@pytest.mark.parametrize(
    ("read", "default"),
    [
        ("os.getenv('K', 'dflt')", "dflt"),
        ("os.environ.get('K', 'dflt')", "dflt"),
        ("os.environ.get('K', default='dflt')", "dflt"),
        ("os.getenv('K', 8080)", 8080),
        ("os.getenv('K')", None),
        ("os.environ['K']", None),
        ("os.getenv('K', var)", None),  # a default that is no literal records nothing
    ],
)
def test_a_literal_default_is_recorded_and_is_never_the_value(tmp_path, libraries, read, default):
    (answer,) = _read(tmp_path, libraries, f"    requests.get({read})\n")
    assert (answer.kind, answer.value, answer.default) == ("expression", "${K}", default)
