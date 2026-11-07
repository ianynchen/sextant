"""A click program's commands are `entry_point` roots, and their parameters `request_params`
(design 2026-11-06-reading-decorators §5, plan 1 task 9b; closes OI-22).

Each test writes a small click program, scans it with the real Python scanner against the click
8.5.0 Sextant itself installs (its own source is the library read), writes the module fact with
the program's `entry_points`, and runs the real pipeline with the shipped catalogs. It then
reads `roots` (one row per command path, `root_kind = entry_point`) and `endpoint_metadata`
(one row per parameter, `caller` the command's function).
"""

import re
from pathlib import Path

import click
import pytest

from sextant.application.ports.catalogs import CatalogError
from sextant.application.ports.detector import LibraryRoot
from sextant.application.ports.scanner import ScanRequest
from sextant.application.query.trace import traces_of
from sextant.application.resolve.pipeline import resolve
from sextant.application.resolve.shapes.inbound_routes import (
    fallback_word,
    validated_word_fallback,
)
from sextant.application.resolve.values import UNPACKED_SLOT, argument_slot
from sextant.domain.closed_sets import RootKind
from sextant.domain.factfile import write_fact_file
from sextant.domain.facts import Document, ModuleFact
from sextant.ingress.catalogs.yaml_source import YamlCatalogSource
from sextant.ingress.extract.python.scanner import PythonScanner
from sextant.resources import catalogs_dir
from sextant.storage.duckdb.workspace import DuckDbWorkspace

_PREFIX = "sextant-python pypi shop 1 "
# The click Sextant installs, read as the program's library (`scripts/probes/click_commands.md`).
_CLICK = LibraryRoot(coordinate="click", version="8.5.0", archive=Path(click.__file__).parents[1])
# A program shaped like Sextant's own `src/sextant/cli/app.py`.
_SHOP = (
    "import click\n"
    "@click.group()\n"
    "def cli():\n    pass\n"
    "@cli.group()\n"
    "def module():\n    pass\n"
    "@module.command('analyze')\n"
    "@click.argument('path', type=click.Path(exists=True))\n"
    "@click.option('--workspace', 'workspace_dir', default=None)\n"
    "@click.option('--allow-resolve', 'allow_resolve', is_flag=True, default=False)\n"
    "def module_analyze(path, workspace_dir, allow_resolve):\n"
    "    run(path)\n"
    "def run(path):\n    return path\n"
)


def _facts(tmp_path: Path, files: dict[str, str], entry_points: dict[str, str] | None) -> Path:
    source = tmp_path / "src"
    for name, text in files.items():
        path = source / "app" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    facts = tmp_path / "facts"
    PythonScanner().scan(
        ScanRequest(
            module_id="shop",
            coordinates="shop",
            version="1",
            classes_dir=source,
            out_dir=facts,
            dependency_archives=(_CLICK,),
        )
    )
    module = Document(
        document_id="module",
        relative_path="pyproject.toml",
        module_id="shop",
        language="python",
        sextant_version="0",
        fact_schema_version="0",
        scanner_id="module",
        content_hash="sha256:none",
        origin_entry="shop",
        origin_tier="module_output",
        redaction_set_hash="sha256:none",
    )
    write_fact_file(
        facts / "module.jsonl",
        module,
        [
            ModuleFact(
                document_id="module",
                module_id="shop",
                module_kind="pyproject",
                languages=["python"],
                source_roots=["src"],
                output_dirs=["src"],
                lookup="c3",
                entry_points=entry_points,
            )
        ],
    )
    return facts


def _resolved(
    tmp_path: Path,
    files: dict[str, str],
    entry_points: dict[str, str] | None = None,
) -> DuckDbWorkspace:
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    resolve(
        workspace,
        _facts(tmp_path, files, {"shop": "app.cli:cli"} if entry_points is None else entry_points),
        YamlCatalogSource(catalogs_dir()),
        PythonScanner().capabilities(),
    )
    return workspace


def _roots(workspace: DuckDbWorkspace) -> list[tuple[str, str | None]]:
    return [
        (_bare(row["handler"]), row["path"])
        for row in workspace.query("roots")
        if row["root_kind"] == str(RootKind.ENTRY_POINT)
    ]


def _params(workspace: DuckDbWorkspace) -> list[tuple[object, ...]]:
    return sorted(
        (row["path"], row["kind"], row["name"], row["requirement"], row["resolution"])
        for row in workspace.query("endpoint_metadata")
        if row["protocol"] is None and row["direction"] == "inbound"
    )


def test_a_click_command_is_an_entry_point_root(tmp_path: Path):
    """A command is an `entry_point` root: no protocol, no method, no wire markers, and the
    handler is the command's own function."""
    workspace = _resolved(tmp_path, {"cli.py": _SHOP})

    (row,) = [r for r in workspace.query("roots") if r["root_kind"] == "entry_point"]
    assert (_bare(row["handler"]), row["protocol"], row["method"], row["method_kind"]) == (
        _handler("module_analyze"),
        None,
        None,
        None,
    )


def test_group_nesting_gives_the_full_command_path(tmp_path: Path):
    """The groups are mounts, each named from its function, and the top group's word is the
    entry point's name: `shop module analyze`, words joined by one space."""
    workspace = _resolved(tmp_path, {"cli.py": _SHOP})

    assert _roots(workspace) == [(_handler("module_analyze"), "shop module analyze")]


def test_options_become_request_params(tmp_path: Path):
    """The decorators between the registration and the function are its parameters:
    `--allow-resolve` is a flag, `path` a required argument (no `default`, no `required`), and
    `--workspace` an optional option. The type is not a column (design §5)."""
    workspace = _resolved(tmp_path, {"cli.py": _SHOP})

    assert _params(workspace) == [
        ("shop module analyze", "argument", "path", "required", "resolved"),
        ("shop module analyze", "flag", "--allow-resolve", "optional", "resolved"),
        ("shop module analyze", "option", "--workspace", "optional", "resolved"),
    ]
    assert {_bare(row["caller"]) for row in workspace.query("endpoint_metadata")} == {
        _handler("module_analyze")
    }


def test_a_command_root_gets_a_trace(tmp_path: Path):
    """A trace starts at the command's function and reaches what it calls."""
    workspace = _resolved(tmp_path, {"cli.py": _SHOP})

    (trace,) = [t for t in traces_of(workspace) if t.root.kind is RootKind.ENTRY_POINT]
    assert [_bare(step.callee) for step in trace.steps] == [_handler("run")]


def test_a_group_with_no_name_is_named_from_its_function_by_clicks_rule(tmp_path: Path):
    """click 8.5.0 lower-cases the function's name, turns `_` into `-` and drops a last part
    `command`, `cmd`, `group` or `grp` (`init_data_group` is `init-data`)."""
    workspace = _resolved(
        tmp_path,
        {
            "cli.py": (
                "import click\n"
                "@click.group()\n"
                "def cli():\n    pass\n"
                "@cli.group()\n"
                "def init_data_group():\n    pass\n"
                "@init_data_group.command()\n"
                "def load_all_cmd():\n    pass\n"
            )
        },
    )

    assert _roots(workspace) == [(_handler("load_all_cmd"), "shop init-data load-all")]


def test_typers_spelling_is_the_same_data_without_the_suffix_rule():
    """typer 0.27.1's `get_command_name` lower-cases and turns `_` into `-`, and keeps every
    suffix: the same mapping with no `drop_suffixes` (design §3c)."""
    typer = validated_word_fallback(
        {"name": "construct_name", "lower": True, "replace": {"_": "-"}}, "test"
    )
    clicks = validated_word_fallback(
        {
            "name": "construct_name",
            "lower": True,
            "replace": {"_": "-"},
            "drop_suffixes": ["command", "cmd", "group", "grp"],
        },
        "test",
    )
    assert typer is not None and clicks is not None
    assert fallback_word(typer, "Init_Data_Command") == "init-data-command"
    assert fallback_word(clicks, "Init_Data_Command") == "init-data"
    assert fallback_word(clicks, "command") == "command"


def test_a_name_written_as_a_keyword_is_read_by_name(tmp_path: Path):
    """`command(name=...)`: the name is position 0 or the keyword `name` (`{arg: 0, keyword:
    name}`), so a keyword is read where no position is written."""
    workspace = _resolved(
        tmp_path,
        {
            "cli.py": (
                "import click\n"
                "@click.group()\n"
                "def cli():\n    pass\n"
                "@cli.command(name='serve', help='Serve it.')\n"
                "def run_server():\n    pass\n"
            )
        },
    )

    assert _roots(workspace) == [(_handler("run_server"), "shop serve")]


def test_a_position_counts_positional_arguments_only():
    """The facts write positional arguments first, then keyword ones (R27): `arg1` of
    `option("--dry-run", is_flag=True)` is no argument at all, never `is_flag`'s `True`."""
    arguments = [
        {"kind": "string", "value": "--dry-run", "keyword": None},
        {"kind": "boolean", "value": True, "keyword": "is_flag"},
    ]
    assert argument_slot(arguments, "arg1") is None
    assert argument_slot(arguments, 0) == 0
    assert argument_slot(arguments, {"keyword": "is_flag"}) == 1
    assert argument_slot(arguments, {"arg": 1, "keyword": "is_flag"}) == 1
    # A JVM argument has no `keyword`: a position is its index, as before.
    assert argument_slot([{"kind": "string"}, {"kind": "int"}], 1) == 1


def test_an_unpacked_argument_makes_the_reference_not_readable():
    """A `*` value at or before the position may be the argument, and a missing keyword may be
    in a `**` value: neither is an argument the code writes (`UNPACKED_SLOT`)."""
    star = [{"kind": "unresolved", "source": 1, "keyword": "*"}]
    stars = [{"kind": "unresolved", "source": 1, "keyword": "**"}]
    assert argument_slot(star, 0) == UNPACKED_SLOT
    assert argument_slot(stars, {"keyword": "name"}) == UNPACKED_SLOT
    assert argument_slot(stars, {"arg": 0, "keyword": "name"}) == UNPACKED_SLOT
    assert argument_slot([], {"keyword": "name"}) is None


def test_a_command_named_from_an_unpacked_mapping_has_no_path(tmp_path: Path):
    """`@cli.command(**options)`: the name may be in the mapping, so it is not read, and the
    function's name is not used in its place: the root keeps its handler and has no path."""
    workspace = _resolved(
        tmp_path,
        {
            "cli.py": (
                "import click\n"
                "OPTIONS = {'name': 'serve'}\n"
                "@click.group()\n"
                "def cli():\n    pass\n"
                "@cli.command(**OPTIONS)\n"
                "def run_server():\n    pass\n"
            )
        },
    )

    assert _roots(workspace) == [(_handler("run_server"), None)]


def test_the_handler_walk_goes_through_a_stated_decorator_into_module_code(tmp_path: Path):
    """Between the registration and the function: a click option (stated, `result_returns`)
    and a decorator in the module's own code that hands the function back. The handler is the
    function, and the option is its parameter."""
    workspace = _resolved(
        tmp_path,
        {
            "cli.py": (
                "import click\n"
                "def logged(fn):\n    return fn\n"
                "@click.group()\n"
                "def cli():\n    pass\n"
                "@cli.command('go')\n"
                "@click.option('--fast', is_flag=True)\n"
                "@logged\n"
                "def go():\n    pass\n"
            )
        },
    )

    assert _roots(workspace) == [(_handler("go"), "shop go")]
    assert _params(workspace) == [("shop go", "flag", "--fast", "optional", "resolved")]


@pytest.mark.declines("click")
@pytest.mark.pins("values.an-UNSTATED-library-call-hands-back-no-argument")
def test_a_library_decorator_no_value_model_states_names_no_handler(tmp_path: Path):
    """`click.pass_context` returns a new function (`new_func`), and no value model states it:
    the walk ends at the library, so no function here is the command's handler. The command is
    still registered: its row keeps its path with `handler` NULL, and its option, which no
    function can be linked to, gives no parameter row. The command beside it is unaffected."""
    workspace = _resolved(
        tmp_path,
        {
            "cli.py": (
                "import click\n"
                "@click.group()\n"
                "def cli():\n    pass\n"
                "@cli.command('ctx')\n"
                "@click.pass_context\n"
                "@click.option('--n')\n"
                "def with_context(ctx, n):\n    pass\n"
                "@cli.command('plain')\n"
                "def plain():\n    pass\n"
            )
        },
    )

    assert _roots(workspace) == [(_handler("plain"), "shop plain"), (None, "shop ctx")]
    assert _params(workspace) == []
    # A row with no handler starts no trace.
    assert [t.root.identities[0].path for t in traces_of(workspace)] == ["shop plain"]


def test_a_call_through_an_unstated_library_decorator_names_it(tmp_path: Path):
    """A call of a name a library decorator no value model states made ends `external`, and
    the detail names the decorator the walk stopped at."""
    workspace = _resolved(
        tmp_path,
        {
            "cli.py": (
                "import click\n"
                "@click.pass_context\n"
                "def with_context(ctx):\n    pass\n"
                "def use():\n    with_context()\n"
            )
        },
        entry_points={},
    )

    (row,) = [
        row for row in workspace.query("bound_receivers") if _bare(row["caller"]) == _handler("use")
    ]
    assert (row["reason"], row["detail"]) == (
        "external",
        (
            "receiver of __call__ is what the library call click/decorators#pass_context "
            "returns, which no value model states"
        ),
    )


@pytest.mark.parametrize(
    ("body", "called"),
    [
        # dispatch's `process_signals`: a `with` over a `contextmanager` helper of its own.
        (
            (
                "    from contextlib import contextmanager\n"
                "    @contextmanager\n"
                "    def session_scope(e):\n        yield e\n"
                "    with session_scope(1) as s:\n        helper(s)\n"
            ),
            "helper",
        ),
        # A `partial` called in the body: a `__call__` chain of the body's own.
        ("    f = functools.partial(print, 1)\n    f()\n    helper(1)\n", "helper"),
        # A function handed to a call in the body is that call's, never the command's.
        ("    run = functools.partial(print)\n    run(helper)\n", None),
    ],
)
def test_the_handler_is_the_function_the_registration_receives(
    tmp_path: Path, body: str, called: str | None
):
    """A command with no decorator between hands its own function to the registration, and
    that function is the handler, whatever its body calls: a call of a value inside the body
    is a chain of its own and never stands for the command (review of task 9b)."""
    workspace = _resolved(
        tmp_path,
        {
            "cli.py": (
                "import click, functools\n"
                "@click.group()\n"
                "def cli():\n    pass\n"
                "def helper(x=None):\n    pass\n"
                "@cli.command('go')\n"
                "def go():\n" + body
            )
        },
    )

    assert _roots(workspace) == [(_handler("go"), "shop go")]
    if called is not None:
        (trace,) = [t for t in traces_of(workspace) if t.root.kind is RootKind.ENTRY_POINT]
        assert _handler(called) in {_bare(step.callee) for step in trace.steps}


def test_with_no_entry_point_the_outermost_word_is_the_program_hole(tmp_path: Path):
    """A program is started by the name it is installed under; with no entry point naming the
    top group, that word is the named hole `<program>`."""
    workspace = _resolved(tmp_path, {"cli.py": _SHOP}, entry_points={})

    assert _roots(workspace) == [(_handler("module_analyze"), "<program> module analyze")]


def test_a_command_an_entry_point_names_is_the_program(tmp_path: Path):
    """A lone `@click.command()` the entry point names is started as the program itself: its
    path is the program's name, its own word not typed. Extras in the target are not part of
    it."""
    workspace = _resolved(
        tmp_path,
        {"cli.py": "import click\n@click.command()\ndef main():\n    pass\n"},
        entry_points={"shop-cli": "app.cli:main [extra]"},
    )

    assert _roots(workspace) == [(_handler("main"), "shop-cli")]


def test_a_call_of_a_cached_function_runs_its_body(tmp_path: Path):
    """`@functools.cache def f` holds the cache's wrapper, which runs `f` with the same
    arguments (`result_calls: arg0`); so does a `contextmanager` helper. A factory spelling
    (`lru_cache(maxsize=8)`) states nothing: the call ends at the library."""
    workspace = _resolved(
        tmp_path,
        {
            "cli.py": (
                "import contextlib\n"
                "import functools\n"
                "@functools.cache\n"
                "def cached():\n    return 1\n"
                "@contextlib.contextmanager\n"
                "def managed():\n    yield 1\n"
                "@functools.lru_cache(maxsize=8)\n"
                "def bounded():\n    return 2\n"
                "def use():\n"
                "    cached()\n"
                "    managed()\n"
                "    bounded()\n"
            )
        },
    )

    edges = {
        _bare(row["callee"])
        for row in workspace.query("call_edges")
        if _bare(row["caller"]) == _handler("use") and row["callee"] is not None
    }
    assert _handler("cached") in edges
    assert _handler("managed") in edges
    assert _handler("bounded") not in edges


def _handler(name: str) -> str:
    """A function of `app/cli.py`, as `_bare` spells a symbol."""
    return f"app/cli#{name}"


def _bare(symbol: object) -> str | None:
    """A method symbol without its module prefix and its signature hash: `app/cli#name`;
    None for none."""
    if symbol is None:
        return None
    return re.sub(r"\(sig_[0-9a-f]+\)\.$", "", str(symbol).removeprefix(_PREFIX))


@pytest.mark.parametrize(
    ("catalog", "refused"),
    [
        ("root_kind: scheduled\n", "routes its rows to entry_point only"),
        ("root_kind: entry_point\nprotocol: http\n", "declares no `protocol`"),
    ],
)
def test_the_loader_refuses_a_malformed_root_kind(tmp_path: Path, catalog: str, refused: str):
    (tmp_path / "x.yml").write_text(
        "id: x\nstyle: fluent\n" + catalog + "matches:\n  roots: []\n", encoding="utf-8"
    )
    with pytest.raises(CatalogError, match=refused):
        YamlCatalogSource(tmp_path).load()


def test_the_loader_refuses_root_kind_on_another_style(tmp_path: Path):
    (tmp_path / "x.yml").write_text(
        "id: x\nstyle: single_call\nroot_kind: entry_point\nmatches: {}\n", encoding="utf-8"
    )
    with pytest.raises(CatalogError, match="read on a fluent catalog only"):
        YamlCatalogSource(tmp_path).load()


@pytest.mark.parametrize(
    "entry",
    [
        "{ owner: a.b, method: f, result_returns: arg0 }",
        "{ owner: a.b, method: f, returns: arg0, result_calls: arg0, by: p.md }",
        "{ owner: a.b, method: f, result_returns: 0, by: p.md }",
        "{ owner: a.b, method: f, passes: arg0, by: p.md }",
    ],
)
def test_the_loader_refuses_a_malformed_returns_argument(tmp_path: Path, entry: str):
    models = tmp_path / "value-models"
    models.mkdir()
    (models / "m.yml").write_text(f"id: m\nreturns_argument:\n  - {entry}\n", encoding="utf-8")
    with pytest.raises(CatalogError, match="returns_argument"):
        YamlCatalogSource(tmp_path).returns_arguments()


def test_the_loader_refuses_one_call_stated_twice(tmp_path: Path):
    models = tmp_path / "value-models"
    models.mkdir()
    for name in ("a", "b"):
        (models / f"{name}.yml").write_text(
            f"id: {name}\nreturns_argument:\n"
            "  - { owner: a.b, method: f, result_returns: arg0, by: p.md }\n",
            encoding="utf-8",
        )
    with pytest.raises(CatalogError, match="one call is stated once"):
        YamlCatalogSource(tmp_path).returns_arguments()


_CLICK_LIKE = (
    "id: x\nstyle: fluent\nroot_kind: entry_point\nrequires: [value_ids]\nmatches:\n"
    "  roots:\n    - { owner: a.Group, method: group, captures: { url: arg0 } }\n"
    "  steps:\n    - { method: __call__, captures: { handler: arg0 } }\n"
    "  terminal: [__call__]\n"
)


_MALFORMED = (
    ("  path_fallback: { name: other }\n", "path_fallback"),
    ("  path_fallback: { name: construct_name, drop_suffixes: cmd }\n", "path_fallback"),
    (
        (
            "  router_type: [a.Group]\n  mount:\n    - { owner: a.Group, method: __call__,"
            " router_arg: chain_result, prefix_from: receiver_path }\n"
        ),
        "only as a declared root",
    ),
    (
        (
            "  router_type: [a.Group]\n  mount:\n    - { owner: a.Group, method: group,"
            " router_arg: { keyword: 3 }, prefix_arg: 0 }\n"
        ),
        "an argument is a position",
    ),
    (
        (
            "  request_params:\n    - { owner: a.b, method: option, kind: header, name_arg: 0,"
            " requirement: optional }\n"
        ),
        "`kind` must be one of",
    ),
    (
        (
            "  request_params:\n    - { owner: a.b, method: option, kind: option, name_arg: 0,"
            " requirement: binder }\n"
        ),
        "`requirement` must be one of",
    ),
    (
        (
            "  request_params:\n    - { owner: a.b, method: option, kind: option,"
            " name_arg: { key: x }, requirement: optional }\n"
        ),
        "an argument is a position",
    ),
    (
        (
            "  request_params:\n    - { owner: a.b, method: option, kind: option, name_arg: 0,"
            " requirement: optional, typed_arg: 1 }\n"
        ),
        "carry only",
    ),
)


@pytest.mark.parametrize(("extra", "refused"), _MALFORMED)
def test_the_engine_refuses_each_malformed_new_form(tmp_path: Path, extra: str, refused: str):
    """Each new form is refused, naming the catalog, the first time the engine reads it."""
    (tmp_path / "x.yml").write_text(_CLICK_LIKE + extra, encoding="utf-8")
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    with pytest.raises(CatalogError, match=refused):
        resolve(
            workspace,
            _facts(tmp_path, {"cli.py": "pass\n"}, {}),
            YamlCatalogSource(tmp_path),
            PythonScanner().capabilities(),
        )


def test_a_capture_refuses_a_malformed_keyword_reference(tmp_path: Path):
    (tmp_path / "x.yml").write_text(
        _CLICK_LIKE.replace("captures: { url: arg0 }", "captures: { url: { keyword: 1 } }"),
        encoding="utf-8",
    )
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    with pytest.raises(CatalogError, match="not a call-site position"):
        resolve(
            workspace,
            _facts(tmp_path, {"cli.py": "pass\n"}, {}),
            YamlCatalogSource(tmp_path),
            PythonScanner().capabilities(),
        )


def test_an_endpoint_catalog_refuses_path_fallback(tmp_path: Path):
    """`path_fallback` names a chain's word from its handler, which only an entry-point
    catalog reads: on an endpoint catalog it would load and do nothing."""
    (tmp_path / "x.yml").write_text(
        _CLICK_LIKE.replace("root_kind: entry_point\n", "protocol: http\ndirection: inbound\n")
        + "  path_fallback: construct_name\n",
        encoding="utf-8",
    )
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    with pytest.raises(CatalogError, match="only a `root_kind: entry_point` catalog reads"):
        resolve(
            workspace,
            _facts(tmp_path, {"cli.py": "pass\n"}, {}),
            YamlCatalogSource(tmp_path),
            PythonScanner().capabilities(),
        )


_SINGLE_CALL = (
    "id: x\nstyle: single_call\nprotocol: http\ndirection: outbound\nmatches:\n"
    "  owner: app.lib\n"
    "  methods:\n"
    "    - { name: fetch, http_method: GET, url_arg: {arg: 0, keyword: url} }\n"
)


def test_a_single_call_row_reads_its_address_by_keyword(tmp_path: Path):
    """`url_arg: {arg: 0, keyword: url}` on a `single_call` row reads the address written as
    position 0 or as `url=`, written after another keyword; each is a module constant, so the
    value walk reads it at the slot the reference names."""
    (tmp_path / "x.yml").write_text(_SINGLE_CALL, encoding="utf-8")
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    resolve(
        workspace,
        _facts(
            tmp_path,
            {
                "lib.py": "def fetch(url=None, timeout=None):\n    return url\n",
                "cli.py": (
                    "from app.lib import fetch\n"
                    "STOCK = 'http://inventory/stock'\n"
                    "ITEMS = 'http://inventory/items'\n"
                    "def by_name():\n    fetch(timeout=3, url=STOCK)\n"
                    "def by_place():\n    fetch(ITEMS, timeout=3)\n"
                ),
            },
            {},
        ),
        YamlCatalogSource(tmp_path),
        PythonScanner().capabilities(),
    )

    assert sorted((row["peer"], row["path"]) for row in workspace.query("endpoints")) == [
        ("inventory", "/items"),
        ("inventory", "/stock"),
    ]


@pytest.mark.parametrize(
    ("catalog", "refused"),
    [
        # A mapping in another shape on a style that reads the keyword form.
        (_SINGLE_CALL.replace("{arg: 0, keyword: url}", "{arg: 0, name: url}"), "_arg"),
        # A keyword form on a style whose readers take a position only.
        (
            (
                "id: x\nstyle: combinator\nprotocol: http\ndirection: inbound\nmatches:\n"
                "  routes:\n    - { owner: a.B, method: get, path_arg: {keyword: path} }\n"
            ),
            "on a fluent or single_call catalog",
        ),
    ],
)
def test_the_loader_refuses_a_mapping_argument_it_cannot_read(
    tmp_path: Path, catalog: str, refused: str
):
    (tmp_path / "x.yml").write_text(catalog, encoding="utf-8")
    with pytest.raises(CatalogError, match=refused):
        YamlCatalogSource(tmp_path).load()


def _one_command(tmp_path: Path, decorators: str, signature: str) -> list[tuple[object, ...]]:
    """The parameter rows of one command `go` under `decorators`, its `def` `signature`."""
    workspace = _resolved(
        tmp_path,
        {
            "cli.py": (
                "import click\n"
                "N = int('2')\n"
                "@click.group()\n"
                "def cli():\n    pass\n"
                "@cli.command('go')\n" + decorators + f"def go({signature}):\n    pass\n"
            )
        },
    )
    return [row[1:4] for row in _params(workspace)]


@pytest.mark.parametrize(
    ("decorator", "requirement"),
    [
        # Any number of values, none included (design §3f, `optional_when`).
        ("@click.argument('files', nargs=-1)\n", "optional"),
        # An explicit `required` still wins.
        ("@click.argument('files', nargs=-1, required=True)\n", "required"),
        ("@click.argument('files', nargs=2)\n", "required"),
        # `nargs` written, not as a literal: not read.
        ("@click.argument('files', nargs=N)\n", None),
    ],
)
def test_nargs_minus_one_makes_an_argument_optional(
    tmp_path: Path, decorator: str, requirement: str | None
):
    assert _one_command(tmp_path, decorator, "files") == [("argument", "files", requirement)]


def test_the_measured_nargs_arguments_read_optional(tmp_path: Path):
    """The five `nargs=-1` arguments the review measured, as dispatch's `cli.py` and redash's
    `cli/rq.py` write them (click 8.5.0), one command each."""
    workspace = _resolved(
        tmp_path,
        {
            "cli.py": (
                "import click\n"
                "from click import argument\n"
                "@click.group()\n"
                "def cli():\n    pass\n"
                "@cli.command('install')\n@click.argument('plugins', nargs=-1)\n"
                "def install_plugins(plugins):\n    pass\n"
                "@cli.command('merge')\n@click.argument('revisions', nargs=-1)\n"
                "def merge_revisions(revisions):\n    pass\n"
                "@cli.command('list')\n@click.argument('tasks', nargs=-1)\n"
                "def list_tasks(tasks):\n    pass\n"
                "@cli.command('shell')\n"
                "@click.argument('ipython_args', nargs=-1, type=click.UNPROCESSED)\n"
                "def shell(ipython_args):\n    pass\n"
                "@cli.command('worker')\n@argument('queues', nargs=-1)\n"
                "def worker(queues):\n    pass\n"
            )
        },
    )

    assert {(row[2], row[3]) for row in _params(workspace)} == {
        ("plugins", "optional"),
        ("revisions", "optional"),
        ("tasks", "optional"),
        ("ipython_args", "optional"),
        ("queues", "optional"),
    }


@pytest.mark.parametrize(
    ("decorator", "signature", "rows"),
    [
        (
            "@click.option('-m', '--message', 'message', default=None)\n",
            "message",
            [("option", "--message", "optional"), ("option", "-m", "optional")],
        ),
        (
            "@click.option('--dry-run', is_flag=True)\n",
            "dry_run",
            [("flag", "--dry-run", "optional")],
        ),
        (
            "@click.option('-v', '--verbose', is_flag=True, help='Say more.')\n",
            "verbose",
            [("flag", "--verbose", "optional"), ("flag", "-v", "optional")],
        ),
        # An argument's one declaration is its name, though it is the parameter's too.
        ("@click.argument('path')\n", "path", [("argument", "path", "required")]),
    ],
)
def test_each_spelling_of_an_option_is_a_row(
    tmp_path: Path, decorator: str, signature: str, rows: list[tuple[object, ...]]
):
    """`name_arg: all_strings` reads every string an option writes positionally (never its
    `help=`); one equal to a parameter of the handler names that parameter, and each other is a
    spelling a user types, one row each (design §3f)."""
    assert _one_command(tmp_path, decorator, signature) == rows


def test_the_loader_refuses_a_malformed_optional_when(tmp_path: Path):
    (tmp_path / "x.yml").write_text(
        _CLICK_LIKE
        + "  request_params:\n    - { owner: a.b, method: argument, kind: argument, name_arg: 0,"
        " requirement: required, optional_when: { arg: { keyword: nargs } } }\n",
        encoding="utf-8",
    )
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    with pytest.raises(CatalogError, match="optional_when"):
        resolve(
            workspace,
            _facts(tmp_path, {"cli.py": "pass\n"}, {}),
            YamlCatalogSource(tmp_path),
            PythonScanner().capabilities(),
        )


def test_a_command_on_a_subclassed_group_is_registered(tmp_path: Path):
    """`class MyGroup(click.Group)`: its `command` is `Group.command`, matched as the walk
    matches a root on a subtype (redash's `AppGroup` is such a class)."""
    workspace = _resolved(
        tmp_path,
        {
            "cli.py": (
                "import click\n"
                "class MyGroup(click.Group):\n    pass\n"
                "cli = MyGroup()\n"
                "@cli.command('x')\n"
                "@click.option('--n')\n"
                "def x(n):\n    pass\n"
            )
        },
        entry_points={},
    )

    assert _roots(workspace) == [(_handler("x"), "<program> x")]
    assert _params(workspace) == [("<program> x", "option", "--n", "optional", "resolved")]


def test_an_option_of_a_handler_taking_any_keyword_has_no_name(tmp_path: Path):
    """`def b(**kwargs)` may receive any name, so no string `option("--y", "y_val")` writes can
    be told to be the parameter's rather than a spelling: one row, name NULL, `unresolved`,
    its requirement as read."""
    rows = _one_command(tmp_path, "@click.option('--y', 'y_val', required=True)\n", "**kwargs")

    assert rows == [("option", None, "required")]


@pytest.mark.parametrize(
    "catalog",
    [
        # A key read as an integer: `single_call`'s `client_base.client_arg`.
        (
            "id: x\nstyle: single_call\nprotocol: http\ndirection: outbound\nmatches:\n"
            "  owner: app.lib\n  client_base: { client_arg: {keyword: client} }\n"
            "  methods:\n    - { name: fetch, http_method: GET, url_arg: 0 }\n"
        ),
        # A fluent step's `receiver_arg`, read as an integer.
        _CLICK_LIKE.replace(
            "{ method: __call__, captures: { handler: arg0 } }",
            "{ method: __call__, receiver_arg: {keyword: self}, captures: { handler: arg0 } }",
        ),
        # `channel_arg` on a catalog that declares `dispatch`: `dispatch_hops` reads it as one.
        (
            "id: x\nstyle: single_call\ndispatch: { mechanism: actor }\nmatches:\n"
            "  owner: app.lib\n"
            "  methods:\n    - { name: fetch, channel_arg: {keyword: key} }\n"
        ),
    ],
)
def test_the_loader_refuses_a_keyword_form_on_a_key_read_as_an_integer(
    tmp_path: Path, catalog: str
):
    (tmp_path / "x.yml").write_text(catalog, encoding="utf-8")
    with pytest.raises(CatalogError, match="read as an argument position only"):
        YamlCatalogSource(tmp_path).load()
