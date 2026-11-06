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
from sextant.ingress.extract.python.imports import Target
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


# Fix round 1.


def _returns(found) -> tuple[str, list[tuple[str, list[str]]]] | None:
    if found is None:
        return None
    return found.resolution, [(t.symbol, [a.symbol for a in t.arguments]) for t in found.types]


def test_an_alias_is_read_to_its_literals_so_a_binary_mode_opens_a_binary_file():
    """`open(path, 'rb')`: the text overload's `mode: OpenTextMode` is an alias of
    `Literal[...]` unions, read through, so `'rb'` does not fit it and the binary reading
    overload is the one chosen. A mode of unknown type leaves the closed list."""
    libraries = Libraries((), typeshed_dir())

    binary = libraries.call_returns(
        "builtins#", "open", [_argument("string", "x"), _argument("string", "rb")]
    )
    text = libraries.call_returns("builtins#", "open", [_argument("string", "x")])
    unknown = libraries.call_returns(
        "builtins#", "open", [_argument("string", "x"), _argument("unresolved")]
    )

    assert _returns(binary) == ("resolved", [("_io/BufferedReader#", [])])
    assert _returns(text) == ("resolved", [("_io/TextIOWrapper#", [])])
    assert unknown is not None and unknown.resolution == "narrowed"


def test_a_parameter_type_the_rule_cannot_read_leaves_the_closed_list(tmp_path: Path):
    """The first overload's `Shape` is a protocol: whether `5` fits it is not decided
    here, so the first overload is not taken as certain."""
    shapes = _install(
        tmp_path / "site",
        "shapes",
        "1.0",
        {
            "shapes/py.typed": "",
            "shapes/__init__.py": (
                "from typing import Protocol, overload\n"
                "class Shape(Protocol):\n    def area(self) -> float: ...\n"
                "class A: ...\nclass B: ...\n"
                "@overload\ndef make(x: Shape) -> A: ...\n"
                "@overload\ndef make(x: int) -> B: ...\n"
                "def make(x): ...\n"
            ),
        },
    )
    libraries = Libraries((shapes,), typeshed_dir())

    found = libraries.call_returns("shapes#", "make", [_argument("int", 5)])

    assert _returns(found) == ("narrowed", [("shapes/A#", []), ("shapes/B#", [])])


_OBSERVERS = {
    "obslib/py.typed": "",
    "obslib/__init__.py": (
        "import sys\n"
        "if sys.platform.startswith('linux'):\n    from .inotify import Observer\n"
        "elif sys.platform == 'darwin':\n    from .fsevents import Observer\n"
        "else:\n    from .polling import Observer\n"
        "try:\n    from ._speedups import parse\nexcept ImportError:\n    from ._pure import parse\n"
        "if sys.platform == 'win32':\n    def watch() -> int: ...\n"
        "else:\n    def watch() -> str: ...\n"
    ),
    "obslib/inotify.py": "class Observer:\n    def start(self) -> None: ...\n",
    "obslib/fsevents.py": "class Observer:\n    def start(self) -> None: ...\n",
    "obslib/polling.py": "class Observer:\n    def start(self) -> None: ...\n",
    "obslib/_speedups.py": "def parse(text): ...\n",
    "obslib/_pure.py": "def parse(text): ...\n",
}


def test_a_name_a_library_binds_in_several_branches_is_a_closed_list(tmp_path: Path):
    """`Observer` is imported from one of three modules by platform, `parse` from one of
    two by `ImportError`: each is the closed list of its bindings, never the last one;
    and a function defined in both branches returns the closed list of their types."""
    observers = _install(tmp_path / "site", "obslib", "1.0", _OBSERVERS)

    _, tree = _scan(
        tmp_path,
        {
            "app/w.py": (
                "from obslib import Observer, parse\n"
                "def h(o: Observer):\n    o.start()\n    parse('x')\n"
            )
        },
        (observers,),
    )
    libraries = Libraries((observers,), typeshed_dir())

    (handler,) = [
        fact
        for _, _, facts in tree
        for fact in facts
        if isinstance(fact, SymbolFact) and bare_descriptor(fact.symbol).startswith("app/w#h")
    ]
    assert handler.signature is not None
    written = handler.signature.parameters[0].type
    assert written.symbol == "typing/Union#"
    assert [a.symbol for a in written.arguments] == [
        "obslib/inotify/Observer#",
        "obslib/fsevents/Observer#",
        "obslib/polling/Observer#",
    ]
    start, parse = _sites(tree, "app/w#h")
    assert start.target.owner is None
    assert parse.target.owner != "obslib/_pure#"
    assert _returns(libraries.call_returns("obslib#", "watch", [])) == (
        "narrowed",
        [("builtins/int#", []), ("builtins/str#", [])],
    )


def test_a_reexport_is_followed_into_an_installed_distribution_not_declared(tmp_path: Path):
    """`fapi.Request` is `starlite.requests.Request`: starlite is installed (fapi needs
    it) but not declared, and the chain is followed into it. Where the defining
    distribution is not installed, the name is the one the library's import gives, and
    the scan says the definition is not read."""
    site = tmp_path / "site"
    fapi = _install(
        site,
        "fapi",
        "1.0",
        {
            "fapi/py.typed": "",
            "fapi/__init__.py": (
                "from starlite.requests import Request as Request\n"
                "from gone.things import Thing as Thing\n"
            ),
        },
    )
    _install(
        site,
        "starlite",
        "1.0",
        {
            "starlite/py.typed": "",
            "starlite/__init__.py": "",
            "starlite/requests.py": "class Request:\n    pass\n",
        },
    )

    report, tree = _scan(
        tmp_path,
        {"app/w.py": "from fapi import Request, Thing\ndef h(r: Request, t: Thing): ...\n"},
        (fapi,),
    )

    (handler,) = [
        fact
        for _, _, facts in tree
        for fact in facts
        if isinstance(fact, SymbolFact) and bare_descriptor(fact.symbol).startswith("app/w#h")
    ]
    assert handler.signature is not None
    assert [p.type.symbol for p in handler.signature.parameters] == [
        "starlite/requests/Request#",
        "gone/things/Thing#",
    ]
    assert _library_symbols(tree)["starlite/requests/Request#"] == "starlite"
    assert (
        "fapi.Thing: defined in gone, which is not installed in the scanned environment"
        in report.uncovered
    )


def test_an_unpacked_argument_list_leaves_the_closed_list(tmp_path: Path):
    """`*args` and `**options` make the arguments' number and names unknown, so the
    overloads the count would choose between are all left."""
    _, tree = _scan(
        tmp_path,
        {
            "app/r.py": (
                "import subprocess\n"
                "def go(options, args):\n"
                "    a = subprocess.run(['ls'], **options)\n"
                "    a.check_returncode()\n"
                "    b = subprocess.run(*args)\n"
                "    b.check_returncode()\n"
            )
        },
        (),
    )

    _, check, _, check_again = _sites(tree, "app/r#go")
    assert check.target.owner is None
    assert check_again.target.owner is None


def test_the_environments_python_decides_the_standard_library(tmp_path: Path):
    """An environment on Python 3.11 with no declared library installed: `distutils`
    (removed in 3.12) is its standard library, read by the environment's version."""
    environment = tmp_path / "env"
    _write(environment / "pyvenv.cfg", "home = /usr/bin\nversion_info = 3.11.9\n")
    (environment / "lib" / "python3.11" / "site-packages").mkdir(parents=True)

    libraries = Libraries((), typeshed_dir(), environment)

    assert libraries.member(Target("distutils"), "core") == (Target("distutils/core"),)


def test_a_star_import_honours_all_and_skips_private_names(tmp_path: Path):
    """`from .impl import *` re-exports what `impl.__all__` lists, or with no `__all__`
    every name not starting with `_`."""
    stars = _install(
        tmp_path / "site",
        "stars",
        "1.0",
        {
            "stars/py.typed": "",
            "stars/__init__.py": "from .listed import *\nfrom .plain import *\n",
            "stars/listed.py": "__all__ = ['Shown']\nclass Shown: ...\nclass Hidden: ...\n",
            "stars/plain.py": "class Public: ...\nclass _Private: ...\n",
        },
    )
    libraries = Libraries((stars,), typeshed_dir())

    assert libraries.member(Target("stars"), "Shown") == (Target("stars/listed", "Shown"),)
    assert libraries.member(Target("stars"), "Public") == (Target("stars/plain", "Public"),)
    assert libraries.member(Target("stars"), "Hidden") is None
    assert libraries.member(Target("stars"), "_Private") is None
