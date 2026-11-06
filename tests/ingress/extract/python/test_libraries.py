"""`PythonScanner` part 4 (spec 2026-11-06 §3e "Libraries"): library signatures and types,
read from the project's installed environment and from the pinned typeshed copy.

Every environment is a fake one built in `tmp_path`: a `site-packages` folder with a
`*.dist-info` per distribution and the distribution's files. Nothing is installed,
imported or run."""

from pathlib import Path

from sextant.application.ports.detector import LibraryRoot
from sextant.application.ports.scanner import ScanRequest
from sextant.domain.factfile import read_fact_tree
from sextant.domain.facts import (
    CallArgument,
    CallSiteFact,
    SymbolFact,
    TypeHeaderFact,
)
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
    """Each library type's header (D00 §5 `type_header`), bare, with its `origin`. A
    library writes no document and no `symbol` fact of its own: the test says so too."""
    assert not any(document.origin is not None for _, document, _ in tree)
    return {
        bare_descriptor(fact.symbol): fact.origin
        for _, _, facts in tree
        for fact in facts
        if isinstance(fact, TypeHeaderFact)
    }


def _header_document(tree):
    (found,) = [document for _, document, _ in tree if document.header_only]
    return found


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
    # `fastapi#`, the owner its import line gives, is in no library the scan holds.
    assert _header_document(tree).type_headers_unlocated >= 1


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
    assert library["requests/api#"] == stubs
    header = _header_document(tree)
    assert header.origin_tier == "dependency"
    assert header.relative_path == "<environment>"


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


# Fix round 2: library types are type headers, as on the JVM (ruling A).


def test_library_types_are_headers_up_their_bases_and_nothing_else(tmp_path: Path):
    """Every library type the module names gets one `type_header` in the one
    `header_only` document, then each of its bases transitively, with the written bases
    mapped as a module class's are (first `superclass`, the rest `interfaces`). No
    member, no library document, no library `symbol`. `object` is the boundary, and a
    named type no library holds is counted as not located."""
    shapes = _install(
        tmp_path / "site",
        "shapes",
        "1.0",
        {
            "shapes/py.typed": "",
            "shapes/__init__.py": "from .child import Child as Child\n",
            "shapes/child.py": (
                "from .base import Base, Mixin\n"
                "class Child(Base, Mixin):\n    def area(self) -> float: ...\n"
            ),
            "shapes/base.py": "class Root: ...\nclass Base(Root): ...\nclass Mixin: ...\n",
        },
    )

    report, tree = _scan(
        tmp_path,
        {
            "app/main.py": (
                "from shapes import Child\n"
                "from missing import Gone\n"
                "class Mine(Child): ...\n"
                "def f(g: Gone): ...\n"
            )
        },
        (shapes,),
    )

    headers = {
        bare_descriptor(fact.symbol): fact
        for _, _, facts in tree
        for fact in facts
        if isinstance(fact, TypeHeaderFact)
    }
    child = headers["shapes/child/Child#"]
    assert child.origin == "shapes" and child.version == "1.0"
    assert child.construct_kind == "class"
    assert child.annotations == []
    assert bare_descriptor(str(child.superclass)) == "shapes/base/Base#"
    assert [bare_descriptor(i) for i in child.interfaces] == ["shapes/base/Mixin#"]
    assert bare_descriptor(str(headers["shapes/base/Base#"].superclass)) == "shapes/base/Root#"
    assert headers["shapes/base/Root#"].superclass is None
    assert "builtins/object#" not in headers
    assert not any(bare_descriptor(s).startswith("shapes/child/Child#area") for s in headers)
    assert not any(document.origin is not None for _, document, _ in tree)
    assert not [
        fact
        for _, document, facts in tree
        if document.header_only
        for fact in facts
        if not isinstance(fact, TypeHeaderFact)
    ]
    assert _header_document(tree).type_headers_unlocated >= 1
    assert report.documents == 1


def test_a_library_class_whose_bases_are_not_all_read_gets_no_header(tmp_path: Path):
    """`class Model(Base)` where `Base = declarative_base()`: the class's parents are not
    all read (Task 5b's rule), and `type_header` has no key to say so, so no header is
    written for it — a lookup reaching it ends there with `external` — and the scan
    names why."""
    orm = _install(
        tmp_path / "site",
        "orm",
        "1.0",
        {
            "orm/py.typed": "",
            "orm/__init__.py": "Base = make_base()\nclass Model(Base): ...\n",
        },
    )

    report, tree = _scan(
        tmp_path, {"app/m.py": "from orm import Model\nclass Mine(Model): ...\n"}, (orm,)
    )

    assert "orm/Model#" not in _library_symbols(tree)
    assert any(note.startswith("orm.Model: ") for note in report.uncovered)


def test_a_call_into_a_library_method_is_external_and_coverage_counts_module_files(
    tmp_path: Path,
):
    """The module's own documents are what `coverage.documents` counts, the header
    document aside; the `symbols` view holds no library entry; and a call into a library
    method answers `external` in `method_resolution`, as for an unscanned jar type."""
    from sextant.application.resolve.call_edges import record_call_edges
    from sextant.storage.duckdb.workspace import DuckDbWorkspace

    requests = _install(tmp_path / "site", "requests", "2.33.1", _REQUESTS)
    _scan(
        tmp_path,
        {"app/client.py": "import requests\ndef fetch(url):\n    return requests.get(url)\n"},
        (requests,),
    )
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    record_call_edges(workspace)
    (coverage,) = workspace.query("coverage")
    symbols = {bare_descriptor(str(row["symbol"])) for row in workspace.query("declared_symbols")}
    resolutions = [row for row in workspace.query("method_resolution") if row["name"] == "get"]
    headers = workspace.query("type_headers")
    workspace.close()

    assert coverage["documents"] == 1
    assert coverage["type_headers"] == len(headers) > 0
    assert all(symbol.startswith("app/") for symbol in symbols)
    (get,) = resolutions
    assert get["reason"] == "external"


def _opting(tmp_path: Path, extract: str | None):
    project = tmp_path / "project"
    _write(
        project / "pyproject.toml",
        '[project]\nname = "shop"\nversion = "1"\ndependencies = ["fastapi", "httpx"]\n',
    )
    _write(project / "shop" / "__init__.py", "")
    if extract is not None:
        _write(project / ".sextant.yml", extract)
    environment = project / ".venv"
    _write(environment / "pyvenv.cfg", "home = /usr/bin\n")
    site = environment / "lib" / "python3.12" / "site-packages"
    _install(site, "fastapi", "0.115.0", _FASTAPI)
    _install(site, "httpx", "0.27.0", {"httpx/__init__.py": "def get(u): return u\n"})
    return PythonDetector().detect(project).modules[0], site


def test_a_library_opted_into_is_scanned_whole(tmp_path: Path):
    """R21, D04 §2a: `extract_libraries: [fastapi]` gives the module a library root, and
    the library's own scan reads its files (bodies included) and no other
    distribution's, every document with `origin: fastapi` in the dependency tier."""
    module, site = _opting(tmp_path, "extract_libraries:\n  - fastapi\n")

    (library,) = module.library_roots
    assert (library.coordinate, library.version, library.archive) == ("fastapi", "0.115.0", site)

    out = tmp_path / "lib-facts"
    PythonScanner().scan(
        ScanRequest(
            module_id="shop",
            coordinates=library.coordinate,
            version=library.version,
            classes_dir=library.archive,
            out_dir=out,
            origin=library.coordinate,
        )
    )
    tree = read_fact_tree(out)
    assert sorted(document.relative_path for _, document, _ in tree) == [
        "fastapi/__init__.py",
        "fastapi/routing.py",
    ]
    assert {(document.origin, document.origin_tier) for _, document, _ in tree} == {
        ("fastapi", "dependency")
    }
    assert any(fact.kind == "method_return" for _, _, facts in tree for fact in facts)


def test_a_library_not_opted_into_has_no_root(tmp_path: Path):
    """Without `extract_libraries`, nothing of a library's bodies is read: only its
    headers (above)."""
    module, _ = _opting(tmp_path, None)
    assert module.library_roots == ()
    module, _ = _opting(tmp_path / "other", "extract_libraries:\n  - flask\n")
    assert module.library_roots == ()
    assert module.libraries_not_resolved == ("flask: the module declares no such dependency",)


# Fix round 3.


def test_an_opted_in_library_reads_only_its_own_record_files(tmp_path: Path):
    """Two distributions share the namespace folder `ns/` (as `google-api-core` and
    `protobuf` share `google/`): opting into one reads exactly the `.py` files its
    `RECORD` lists, never the other's file in the same folder. A distribution whose
    `RECORD` is missing is not resolved, with the reason, and nothing is guessed."""
    project = tmp_path / "project"
    _write(
        project / "pyproject.toml",
        '[project]\nname = "shop"\nversion = "1"\ndependencies = ["ns-core", "ns-proto", "bare"]\n',
    )
    _write(project / "shop" / "__init__.py", "")
    _write(project / ".sextant.yml", "extract_libraries:\n  - ns-core\n  - bare\n")
    environment = project / ".venv"
    _write(environment / "pyvenv.cfg", "home = /usr/bin\n")
    site = environment / "lib" / "python3.12" / "site-packages"
    _install(site, "ns-core", "1.0", {"ns/core/__init__.py": "def a():\n    return 1\n"})
    _install(site, "ns-proto", "2.0", {"ns/proto/__init__.py": "def b():\n    return 2\n"})
    _install(site, "bare", "3.0", {"bare/__init__.py": ""})
    (site / "bare-3.0.dist-info" / "RECORD").unlink()

    (module,) = PythonDetector().detect(project).modules
    (library,) = module.library_roots
    out = tmp_path / "lib-facts"
    PythonScanner().scan(
        ScanRequest(
            module_id="shop",
            coordinates=library.coordinate,
            version=library.version,
            classes_dir=library.archive,
            out_dir=out,
            origin=library.coordinate,
        )
    )

    assert library.coordinate == "ns-core"
    assert [document.relative_path for _, document, _ in read_fact_tree(out)] == [
        "ns/core/__init__.py"
    ]
    assert module.libraries_not_resolved == (
        "bare: its installed RECORD is missing or unreadable, so its files are not known",
    )
