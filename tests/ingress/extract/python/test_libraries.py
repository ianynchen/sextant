"""`PythonScanner` part 4 (spec 2026-11-06 §3e "Libraries"): library signatures and types,
read from the project's installed environment and from the pinned typeshed copy.

Every environment is a fake one built in `tmp_path`: a `site-packages` folder with a
`*.dist-info` per distribution and the distribution's files. Nothing is installed,
imported or run."""

from pathlib import Path

from sextant.application.ports.detector import LibraryRoot
from sextant.application.ports.scanner import ScanRequest
from sextant.domain.factfile import read_fact_tree
from sextant.domain.facts import CallArgument, CallSiteFact, SymbolFact
from sextant.domain.symbols import bare_descriptor
from sextant.ingress.detect.python import PythonDetector
from sextant.ingress.extract.python.libraries import Libraries
from sextant.ingress.extract.python.scanner import PythonScanner
from sextant.resources import typeshed_dir

COMMIT = (typeshed_dir() / "COMMIT").read_text(encoding="utf-8").strip()


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _install(site: Path, name: str, version: str, files: dict[str, str]) -> LibraryRoot:
    """A distribution as an installer leaves it: its files, and a `.dist-info` whose
    `RECORD` lists them."""
    info = site / f"{name}-{version}.dist-info"
    _write(info / "METADATA", f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n\n")
    for relative, text in files.items():
        _write(site / relative, text)
    record = [f"{relative},sha256=x,1" for relative in files]
    record += [f"{info.name}/METADATA,,", f"{info.name}/RECORD,,"]
    _write(info / "RECORD", "\n".join(record) + "\n")
    return LibraryRoot(coordinate=name, version=version, archive=site)


def _scan(tmp_path: Path, files: dict[str, str], libraries: tuple[LibraryRoot, ...]):
    root = tmp_path / "src"
    for relative, text in files.items():
        _write(root / relative, text)
    out = tmp_path / "facts"
    report = PythonScanner().scan(
        ScanRequest(
            module_id="shop",
            coordinates="shop",
            version="1.0.0",
            classes_dir=root,
            out_dir=out,
            dependency_archives=libraries,
        )
    )
    return report, read_fact_tree(out)


def _sites(tree, method_prefix: str) -> list[CallSiteFact]:
    return [
        fact
        for _, _, facts in tree
        for fact in facts
        if isinstance(fact, CallSiteFact) and bare_descriptor(fact.caller).startswith(method_prefix)
    ]


def _library_symbols(tree) -> dict[str, str | None]:
    """Each library symbol, bare, with the `origin` of the document it is in."""
    return {
        bare_descriptor(fact.symbol): document.origin
        for _, document, facts in tree
        if document.origin is not None
        for fact in facts
        if isinstance(fact, SymbolFact)
    }


_FASTAPI = {
    "fastapi/__init__.py": "from .routing import APIRouter as APIRouter\n",
    "fastapi/routing.py": (
        "class APIRouter:\n    def get(self, path: str):\n        return path\n"
    ),
    "fastapi/py.typed": "",
}


def test_reexported_name_resolves_to_defining_symbol(tmp_path: Path):
    """`fastapi.APIRouter` is a re-export of `fastapi.routing.APIRouter`: every way the
    module names it gives the defining symbol (ruling R4 spelling), and the library's own
    facts carry the distribution as their origin."""
    fastapi = _install(tmp_path / "site", "fastapi", "0.115.0", _FASTAPI)

    _, tree = _scan(
        tmp_path,
        {
            "app/main.py": (
                "import fastapi\n"
                "from fastapi import APIRouter\n"
                "a = APIRouter()\n"
                "b = fastapi.APIRouter()\n"
                "def handler(router: APIRouter):\n"
                "    return router\n"
            )
        },
        (fastapi,),
    )

    calls = [(s.target.owner, s.target.name) for s in _sites(tree, "app/main#<clinit>")]
    assert calls == [("fastapi/routing#", "APIRouter"), ("fastapi/routing#", "APIRouter")]
    (handler,) = [
        fact
        for _, _, facts in tree
        for fact in facts
        if isinstance(fact, SymbolFact)
        and bare_descriptor(fact.symbol).startswith("app/main#handler")
    ]
    assert handler.signature is not None
    assert handler.signature.parameters[0].type.symbol == "fastapi/routing/APIRouter#"
    library = _library_symbols(tree)
    assert library["fastapi/routing/APIRouter#"] == "fastapi"
    assert "fastapi/APIRouter#" not in library


def test_uninstalled_library_has_no_symbols_and_is_reported(tmp_path: Path):
    """A declared library missing from the environment gives no symbols, so the name
    stays as its import line writes it, and the detector says why."""
    project = tmp_path / "project"
    _write(
        project / "pyproject.toml",
        '[project]\nname = "shop"\nversion = "1"\ndependencies = ["fastapi", "httpx"]\n',
    )
    _write(project / "shop" / "__init__.py", "from fastapi import APIRouter\nr = APIRouter()\n")
    environment = project / ".venv"
    _write(environment / "pyvenv.cfg", "home = /usr/bin\n")
    site = environment / "lib" / "python3.12" / "site-packages"
    _install(site, "httpx", "0.27.0", {"httpx/__init__.py": "", "httpx/py.typed": ""})

    model = PythonDetector().detect(project)

    assert "fastapi is not installed in the scanned environment" in model.notes
    assert not any(note.startswith("httpx") for note in model.notes)
    (module,) = model.modules
    assert [library.coordinate for library in module.dependency_archives] == ["httpx"]

    _, tree = _scan(
        tmp_path,
        {"shop/__init__.py": "from fastapi import APIRouter\nr = APIRouter()\n"},
        module.dependency_archives,
    )
    (call,) = _sites(tree, "shop#<clinit>")
    assert (call.target.owner, call.target.name) == ("fastapi#", "APIRouter")
    assert not any(origin == "fastapi" for origin in _library_symbols(tree).values())


_REQUESTS = {
    "requests/__init__.py": "from .api import get\n",
    "requests/api.py": "def get(url, params=None, **kwargs):\n    pass\n",
    "requests/models.py": "class Response:\n    def json(self):\n        pass\n",
}


def test_typeshed_gives_requests_types_with_provenance(tmp_path: Path):
    """`requests` ships no types (no `py.typed`), so its typeshed stubs are read in its
    place: the re-export, the return type of `get`, and each fact's provenance."""
    requests = _install(tmp_path / "site", "requests", "2.33.1", _REQUESTS)

    _, tree = _scan(
        tmp_path,
        {
            "app/client.py": (
                "import requests\n"
                "def fetch(url: str):\n"
                "    response = requests.get(url)\n"
                "    return response.json()\n"
            )
        },
        (requests,),
    )

    get, json = _sites(tree, "app/client#fetch")
    assert (get.target.owner, get.target.name) == ("requests/api#", "get")
    assert (json.target.owner, json.target.name) == ("requests/models/Response#", "json")
    assert json.receiver == get.result
    library = _library_symbols(tree)
    stubs = f"typeshed@{COMMIT}/requests@~=2.33.0"
    assert library["requests/models/Response#"] == stubs
    documents = {
        document.relative_path: document
        for _, document, _ in tree
        if document.origin is not None and document.origin.startswith("typeshed@")
    }
    assert documents["requests/models.pyi"].origin == stubs
    assert documents["requests/models.pyi"].origin_tier == "dependency"


def _argument(kind: str, value: object = None, keyword: str | None = None) -> CallArgument:
    return CallArgument(kind=kind, value=value, keyword=keyword)  # type: ignore[arg-type]


def test_overload_is_chosen_by_argument_types_else_a_closed_list(tmp_path: Path):
    """`subprocess.run` (typeshed, `@overload`): `text=True` picks the overload for text,
    as a type checker picks the first one the argument types match; an argument of
    unknown type that decides between overloads gives the closed list of what the
    matching overloads return, `narrowed`."""
    libraries = Libraries((), typeshed_dir())
    command = CallArgument(kind="array", elements=[_argument("string", "ls")])

    chosen = libraries.call_returns(
        "subprocess#", "run", [command, _argument("boolean", True, "text")]
    )
    unknown = libraries.call_returns(
        "subprocess#", "run", [command, _argument("unresolved", None, "text")]
    )

    completed = "subprocess/CompletedProcess#"
    assert chosen is not None
    assert chosen.resolution == "resolved"
    assert [(t.symbol, [a.symbol for a in t.arguments]) for t in chosen.types] == [
        (completed, ["builtins/str#"])
    ]
    assert unknown is not None
    assert unknown.resolution == "narrowed"
    assert [(t.symbol, [a.symbol for a in t.arguments]) for t in unknown.types] == [
        (completed, ["builtins/str#"]),
        (completed, ["builtins/bytes#"]),
        (completed, ["typing/Any#"]),
    ]


def test_a_library_call_result_names_the_owner_of_the_next_call(tmp_path: Path):
    """The one chosen overload's return type is the owner of a call on the result, as a
    compiler's return type would be; a closed list leaves the owner to the resolver."""
    _, tree = _scan(
        tmp_path,
        {
            "app/run.py": (
                "import subprocess\n"
                "def go(flag):\n"
                "    done = subprocess.run(['ls'], text=True)\n"
                "    done.check_returncode()\n"
                "    either = subprocess.run(['ls'], text=flag)\n"
                "    either.check_returncode()\n"
            )
        },
        (),
    )

    run, check, run_again, check_again = _sites(tree, "app/run#go")
    assert (run.target.owner, run.target.name) == ("subprocess#", "run")
    assert check.target.owner == "subprocess/CompletedProcess#"
    assert check.receiver == run.result
    assert check_again.target.owner is None
    assert check_again.receiver == run_again.result
