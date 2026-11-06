"""Receiver binding (spec 2026-11-06 §3b, plan 1 task 8): the resolver binds a call the
scanner wrote with no owner, from what produced its receiver, on the existing value walk.

Each test scans a small Python tree with the real scanner, writes the module fact (`c3`),
and runs the real pipeline with no catalogs, then reads `bound_receivers` (one row per
path the walk reached the receiver by) and `call_edges` (one edge per bound owner).
"""

from pathlib import Path

from sextant.application.ports.catalogs import Catalog, CatalogSource
from sextant.application.ports.scanner import ScanRequest
from sextant.application.resolve.call_edges import record_call_edges
from sextant.application.resolve.pipeline import resolve
from sextant.application.resolve.receiver_binding import bind_until_settled
from sextant.application.resolve.return_flow import record_return_flows
from sextant.domain.factfile import write_fact_file
from sextant.domain.facts import Document, ModuleFact
from sextant.ingress.extract.python.scanner import PythonScanner
from sextant.storage.duckdb.workspace import DuckDbWorkspace

_PREFIX = "sextant-python pypi shop 1 "
_SESSION = "app/a/Session#"
_CLIENT = "app/a/Client#"
_A = (
    "class Session:\n"
    "    def __init__(self):\n"
    "        self.opened = True\n"
    "    def get(self, url):\n"
    "        return url\n"
    "class Client:\n"
    "    def get(self, url):\n"
    "        return url\n"
)


class _NoCatalogs(CatalogSource):
    def load(self) -> list[Catalog]:
        return []


def _facts(tmp_path: Path, files: dict[str, str]) -> Path:
    source = tmp_path / "src"
    for name, text in files.items():
        path = source / "app" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    facts = tmp_path / "facts"
    PythonScanner().scan(
        ScanRequest(
            module_id="shop", coordinates="shop", version="1", classes_dir=source, out_dir=facts
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
            )
        ],
    )
    return facts


def _resolved(tmp_path: Path, files: dict[str, str]) -> DuckDbWorkspace:
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    resolve(workspace, _facts(tmp_path, files), _NoCatalogs(), set())
    return workspace


def _site(workspace: DuckDbWorkspace, method: str, name: str) -> tuple[str, int]:
    """The one call named `name` in `method`."""
    (found,) = [
        (str(row["caller"]), int(str(row["ordinal"])))
        for row in workspace.query("call_sites")
        if row["caller"] == _PREFIX + method and row["name"] == name
    ]
    return found


def _bound(workspace: DuckDbWorkspace, site: tuple[str, int]) -> list[dict[str, object]]:
    return [
        row for row in workspace.query("bound_receivers") if (row["caller"], row["ordinal"]) == site
    ]


def _edges(workspace: DuckDbWorkspace, site: tuple[str, int]) -> list[dict[str, object]]:
    return [row for row in workspace.query("call_edges") if (row["caller"], row["ordinal"]) == site]


def test_constructor_local_binds(tmp_path: Path):
    """`from app.a import Session; s = Session(); s.get()`: the scanner writes the class
    call as a static call on the module (it cannot see that `Session` is a class), and the
    resolver reads it as that class's constructor, so `s` is a `Session`."""
    workspace = _resolved(
        tmp_path,
        {
            "a.py": _A,
            "b.py": "from app.a import Session\ndef f():\n    s = Session()\n    s.get('/a')\n",
        },
    )
    site = _site(workspace, "app/b#f(sig_dd69782a).", "get")
    rows = _bound(workspace, site)
    assert [(row["owner"], row["resolution"], row["evidence"]) for row in rows] == [
        (_SESSION, "resolved", "syntax")
    ]
    assert [row["callee"] for row in _edges(workspace, site)] == [
        _PREFIX + "app/a/Session#get(sig_dd69782a)."
    ]
    # The class call itself is an edge to the class's construction, not to a method named
    # `Session` on the module.
    construction = _site(workspace, "app/b#f(sig_dd69782a).", "Session")
    assert [row["target"] for row in _edges(workspace, construction)] == [
        "app/a/Session#<init>(sig_dd69782a)."
    ]
    workspace.close()


def test_return_value_binds(tmp_path: Path):
    """A call's result is what the callee returns (`return_flow`): `make()` returns a
    `Session`, so `make().get()` runs `Session.get`."""
    workspace = _resolved(
        tmp_path,
        {
            "a.py": _A + "def make():\n    return Session()\n",
            "b.py": "from app.a import make\ndef f():\n    m = make()\n    m.get('/b')\n",
        },
    )
    site = _site(workspace, "app/b#f(sig_dd69782a).", "get")
    assert [row["owner"] for row in _bound(workspace, site)] == [_SESSION]
    assert [row["callee"] for row in _edges(workspace, site)] == [
        _PREFIX + "app/a/Session#get(sig_dd69782a)."
    ]
    workspace.close()


def test_parameter_binds_per_caller_path_never_combined(tmp_path: Path):
    """Two callers pass a `Session` and a `Client`: two rows, each on the path of its own
    caller, at `narrowed` (a closed list). Never one row naming both, never a row on a
    path that does not pass that type."""
    workspace = _resolved(
        tmp_path,
        {
            "a.py": _A
            + "def use(c):\n    c.get('/c')\n"
            + "def one():\n    use(Session())\n"
            + "def two():\n    use(Client())\n",
        },
    )
    site = _site(workspace, "app/a#use(sig_dd69782a).", "get")
    rows = _bound(workspace, site)
    assert sorted((str(row["owner"]), str(row["path_id"])) for row in rows) == [
        (_CLIENT, _PREFIX + "app/a#two(sig_dd69782a).@1"),
        (_SESSION, _PREFIX + "app/a#one(sig_dd69782a).@1"),
    ]
    assert {row["resolution"] for row in rows} == {"narrowed"}
    edges = _edges(workspace, site)
    assert sorted(str(row["callee"]) for row in edges) == [
        _PREFIX + "app/a/Client#get(sig_dd69782a).",
        _PREFIX + "app/a/Session#get(sig_dd69782a).",
    ]
    assert {row["resolution"] for row in edges} == {"narrowed"}
    workspace.close()


def test_field_written_in_init_binds_self_field_calls(tmp_path: Path):
    """`self.s = Session()` in `__init__` is a `field_write`; `self.s.get()` reads it."""
    workspace = _resolved(
        tmp_path,
        {
            "a.py": _A
            + "class Holder:\n"
            + "    def __init__(self):\n"
            + "        self.s = Session()\n"
            + "    def go(self):\n"
            + "        self.s.get('/d')\n",
        },
    )
    site = _site(workspace, "app/a/Holder#go(sig_dd69782a).", "get")
    assert [row["owner"] for row in _bound(workspace, site)] == [_SESSION]
    workspace.close()


def test_module_singleton_imported_from_another_file_binds(tmp_path: Path):
    """Review Focus 3: a module-level `shared = Session()` read in another file is the
    static field `app/a#shared.`, written once in `<clinit>`."""
    workspace = _resolved(
        tmp_path,
        {
            "a.py": _A + "shared = Session()\n",
            "b.py": "from app.a import shared\ndef f():\n    shared.get('/e')\n",
        },
    )
    site = _site(workspace, "app/b#f(sig_dd69782a).", "get")
    assert [row["owner"] for row in _bound(workspace, site)] == [_SESSION]
    assert [row["callee"] for row in _edges(workspace, site)] == [
        _PREFIX + "app/a/Session#get(sig_dd69782a)."
    ]
    workspace.close()


def test_function_passed_as_value_is_escapes(tmp_path: Path):
    """A function handed to another call as a value is called by whoever received it,
    which the module does not show: its parameter's calls are `escapes`, with a detail."""
    workspace = _resolved(
        tmp_path,
        {
            "a.py": _A
            + "def handler(c):\n    c.get('/h')\n"
            + "def register(fn):\n    return fn\n"
            + "register(handler)\n",
        },
    )
    site = _site(workspace, "app/a#handler(sig_dd69782a).", "get")
    rows = _bound(workspace, site)
    assert [(row["owner"], row["reason"]) for row in rows] == [(None, "escapes")]
    assert "handler" in str(rows[0]["detail"])
    (edge,) = _edges(workspace, site)
    assert (edge["target"], edge["callee"], edge["resolution"]) == (None, None, "unresolved")
    workspace.close()


def test_no_caller_is_external(tmp_path: Path):
    """A function nothing in the module calls is called from outside it."""
    workspace = _resolved(tmp_path, {"a.py": _A + "def nobody(c):\n    c.get('/n')\n"})
    site = _site(workspace, "app/a#nobody(sig_dd69782a).", "get")
    rows = _bound(workspace, site)
    assert [(row["owner"], row["reason"]) for row in rows] == [(None, "external")]
    assert "nobody" in str(rows[0]["detail"])
    workspace.close()


def test_rounds_stop_when_nothing_new_binds(tmp_path: Path):
    """`r.run(Session())` in another file than `Runner` is bound in round 1; only then is
    `Runner.run` called by anything, so its parameter's call binds in round 2; round 3 binds
    nothing and the rounds stop."""
    facts = _facts(
        tmp_path,
        {
            "a.py": _A + "class Runner:\n    def run(self, s):\n        s.get('/r')\n",
            "b.py": "from app.a import Runner, Session\n"
            "def main():\n"
            "    r = Runner()\n"
            "    r.run(Session())\n",
        },
    )
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(facts)
    workspace.derive("bound_receivers_reset")
    record_return_flows(workspace)
    record_call_edges(workspace)
    assert bind_until_settled(workspace) == (1, 1, 0)
    site = _site(workspace, "app/a/Runner#run(sig_dd69782a).", "get")
    assert [row["owner"] for row in _bound(workspace, site)] == [_SESSION]
    workspace.close()


def test_a_receiver_still_unbound_after_eight_rounds_is_not_readable(tmp_path: Path):
    """Each `x.run(...)` below is bound only once the call that handed `x` in is, so
    `K<n>.run`'s call binds in round n + 1, and the rounds stop at eight. `K9.run`'s call,
    still unbound, says so."""
    chained = "".join(
        f"class K{n}:\n    def run(self, x):\n        x.run(K{n + 2}())\n" for n in range(1, 10)
    )
    ends = "".join(f"class K{n}:\n    def run(self, x):\n        pass\n" for n in (10, 11))
    workspace = _resolved(tmp_path, {"a.py": chained + ends + "def main():\n    K1().run(K2())\n"})
    site = _site(workspace, "app/a/K9#run(sig_dd69782a).", "run")
    rows = _bound(workspace, site)
    assert [(row["owner"], row["reason"]) for row in rows] == [(None, "not_readable")]
    assert rows[0]["detail"] == "receiver of run not followed after 8 rounds"
    workspace.close()


def test_a_name_bound_to_two_classes_on_two_branches_binds_each_narrowed(tmp_path: Path):
    """Carried item (c): `try: from app.a import Session as S` / `except: ... Client as S`
    is one module field written twice; `S.get` binds to each class, one row each."""
    workspace = _resolved(
        tmp_path,
        {
            "a.py": _A,
            "b.py": "try:\n"
            "    from app.a import Session as S\n"
            "except ImportError:\n"
            "    from app.a import Client as S\n"
            "def f():\n"
            "    S.get(None, '/s')\n",
        },
    )
    site = _site(workspace, "app/b#f(sig_dd69782a).", "get")
    rows = _bound(workspace, site)
    assert sorted(str(row["owner"]) for row in rows) == [_CLIENT, _SESSION]
    assert {row["resolution"] for row in rows} == {"narrowed"}
    workspace.close()


def test_a_keyword_argument_fills_the_parameter_of_its_name(tmp_path: Path):
    """Fix round 1, ruling R2: `h(y=Session(), x=Client())` fills `x` with the `Client`.
    Slot for slot, `x` would read the `Session` handed to `y`."""
    workspace = _resolved(
        tmp_path,
        {
            "a.py": _A,
            "h.py": "def h(x, y):\n    x.get('/')\n",
            "b.py": "from app.a import Session, Client\n"
            "from app.h import h\n"
            "def f():\n    h(y=Session(), x=Client())\n",
        },
    )
    site = _site(workspace, "app/h#h(sig_dd69782a).", "get")
    assert [(row["owner"], row["resolution"]) for row in _bound(workspace, site)] == [
        (_CLIENT, "resolved")
    ]
    workspace.close()


def test_a_keyword_naming_no_parameter_fills_none(tmp_path: Path):
    """A keyword that names no parameter feeds none: `h(q=Session())` leaves `x` to its
    default, which is `not_readable` on that caller's path, never the `Session`."""
    workspace = _resolved(
        tmp_path,
        {
            "a.py": _A,
            "h.py": "def h(x=None, **rest):\n    x.get('/')\n",
            "b.py": "from app.a import Session, Client\n"
            "from app.h import h\n"
            "def f():\n    h(q=Session())\n"
            "def g():\n    h(Client(), q=Session())\n",
        },
    )
    site = _site(workspace, "app/h#h(sig_dd69782a).", "get")
    rows = _bound(workspace, site)
    assert sorted((str(row["owner"]), str(row["reason"])) for row in rows) == [
        ("None", "not_readable"),
        (_CLIENT, "None"),
    ]
    unfilled = next(row for row in rows if row["owner"] is None)
    assert "parameter 0" in str(unfilled["detail"])
    assert {row["resolution"] for row in rows if row["owner"]} == {"partial"}
    workspace.close()


def test_an_unpacked_mapping_decides_no_parameter(tmp_path: Path):
    """`h(**options)` may fill any parameter: `x` is `not_readable` on that path."""
    workspace = _resolved(
        tmp_path,
        {
            "a.py": _A,
            "h.py": "def h(x):\n    x.get('/')\n",
            "b.py": "from app.h import h\ndef f(options):\n    h(**options)\n",
        },
    )
    site = _site(workspace, "app/h#h(sig_dd69782a).", "get")
    assert [(row["owner"], row["reason"]) for row in _bound(workspace, site)] == [
        (None, "not_readable")
    ]
    workspace.close()


def test_a_union_parameter_binds_each_member_narrowed(tmp_path: Path):
    """Carried item (c): `s: Session | Client` is a closed list of two types, one row each,
    `narrowed`, evidence `syntax`; with `| None`, None has no method, and the detail says so."""
    workspace = _resolved(
        tmp_path,
        {
            "a.py": _A,
            "b.py": "from typing import Union\n"
            "from app.a import Session, Client\n"
            "def u(s: Union[Session, Client]):\n    s.get('/')\n"
            "def v(s: Session | Client | None):\n    s.get('/')\n",
        },
    )
    for method in ("app/b#u(sig_dd69782a).", "app/b#v(sig_dd69782a)."):
        rows = _bound(workspace, _site(workspace, method, "get"))
        assert sorted((str(row["owner"]), row["resolution"], row["evidence"]) for row in rows) == [
            (_CLIENT, "narrowed", "syntax"),
            (_SESSION, "narrowed", "syntax"),
        ]
    nullable = _bound(workspace, _site(workspace, "app/b#v(sig_dd69782a).", "get"))
    assert all("None" in str(row["detail"]) for row in nullable)
    workspace.close()


def test_a_union_with_object_is_no_closed_list(tmp_path: Path):
    """`Session | object` may be any value: no row names `Session` as the whole list."""
    workspace = _resolved(
        tmp_path,
        {
            "a.py": _A,
            "b.py": "from app.a import Session\ndef w(s: Session | object):\n    s.get('/')\n",
        },
    )
    rows = _bound(workspace, _site(workspace, "app/b#w(sig_dd69782a).", "get"))
    assert {row["owner"] for row in rows} == {None}
    workspace.close()


def test_a_class_name_the_module_rebinds_is_a_variable_not_the_class(tmp_path: Path):
    """`Session = Client` after `class Session` makes `app/a#Session.` a variable with a
    writer: `Session()` imported from it is no construction of the class `Session`."""
    workspace = _resolved(
        tmp_path,
        {
            "a.py": _A + "Session = Client\n",
            "b.py": "from app.a import Session\ndef f():\n    s = Session()\n    s.get('/')\n",
        },
    )
    site = _site(workspace, "app/b#f(sig_dd69782a).", "get")
    assert _SESSION not in {row["owner"] for row in _bound(workspace, site)}
    workspace.close()


def test_a_path_the_walk_cannot_hold_keeps_the_site_open(tmp_path: Path):
    """One caller hands `h` a `Client`; the other a value that went through one helper on
    two calls, which no path can hold. The `Client` row is not the whole list: `partial`,
    beside a `not_readable` row saying why."""
    workspace = _resolved(
        tmp_path,
        {
            "a.py": _A,
            "b.py": "from app.a import Session, Client\n"
            "def wrap(x):\n    return x\n"
            "def h(c):\n    c.get('/')\n"
            "def f():\n    h(Client())\n"
            "def g():\n    h(wrap(wrap(Session())))\n",
        },
    )
    site = _site(workspace, "app/b#h(sig_dd69782a).", "get")
    rows = _bound(workspace, site)
    assert (_CLIENT, "partial") in {(row["owner"], row["resolution"]) for row in rows}
    assert any(row["reason"] == "not_readable" for row in rows)
    workspace.close()


def test_the_rounds_rewalk_only_what_a_new_edge_can_change(tmp_path: Path):
    """R25: rounds after the first re-walk only the sites whose walk crossed, or ended at, a
    method that gained a caller; the table is the one a full re-walk each round writes."""
    files = {
        "a.py": _A + "class Runner:\n    def run(self, s):\n        s.get('/r')\n"
        "def use(c):\n    c.get('/c')\n",
        "b.py": "from app.a import Runner, Session, Client, use\n"
        "def main():\n    r = Runner()\n    r.run(Session())\n    use(Client())\n",
        # The eight-round chain of the cap test, so every round and the cap are compared.
        "k.py": "".join(
            f"class K{n}:\n    def run(self, x):\n        x.run(K{n + 2}())\n" for n in range(1, 10)
        )
        + "".join(f"class K{n}:\n    def run(self, x):\n        pass\n" for n in (10, 11))
        + "def main():\n    K1().run(K2())\n",
    }
    tables = []
    for incremental in (True, False):
        facts = _facts(tmp_path / str(incremental), files)
        workspace = DuckDbWorkspace(tmp_path / f"{incremental}.duckdb")
        workspace.load_facts(facts)
        workspace.derive("bound_receivers_reset")
        record_return_flows(workspace)
        record_call_edges(workspace)
        counts = bind_until_settled(workspace, incremental=incremental)
        tables.append((counts, workspace.query("bound_receivers"), workspace.query("call_edges")))
        workspace.close()
    assert len(tables[0][0]) == 8
    assert tables[0] == tables[1]


def test_a_constructor_fills_its_init_parameters_by_name(tmp_path: Path):
    """Fix round 2: `Svc(Session())` and `Svc(s=Client())` fill `Svc.__init__`'s `s`, so
    `self.s.get()` binds both, one row each — a constructor is a callee like any other."""
    workspace = _resolved(
        tmp_path,
        {
            "a.py": _A,
            "svc.py": "class Svc:\n"
            "    def __init__(self, s):\n        self.s = s\n"
            "    def run(self):\n        self.s.get('/')\n",
            "b.py": "from app.a import Session, Client\n"
            "from app.svc import Svc\n"
            "def f():\n    Svc(Session()).run()\n"
            "def g():\n    Svc(s=Client()).run()\n",
        },
    )
    rows = _bound(workspace, _site(workspace, "app/svc/Svc#run(sig_dd69782a).", "get"))
    assert sorted(str(row["owner"]) for row in rows) == [_CLIENT, _SESSION]
    workspace.close()


def test_an_unpacked_sequence_decides_no_later_positional(tmp_path: Path):
    """`f(*items, Client())`: how many places `items` fills is not known, so `b` is not the
    `Client` — `not_readable` on that path."""
    workspace = _resolved(
        tmp_path,
        {
            "a.py": _A,
            "h.py": "def f(a, b):\n    b.get('/')\n",
            "b.py": "from app.a import Client\nfrom app.h import f\n"
            "def g(items):\n    f(*items, Client())\n",
        },
    )
    rows = _bound(workspace, _site(workspace, "app/h#f(sig_dd69782a).", "get"))
    assert [(row["owner"], row["reason"]) for row in rows] == [(None, "not_readable")]
    workspace.close()


def test_a_positional_argument_to_a_variadic_function_fills_its_first_parameter(tmp_path: Path):
    """`def f(a, *rest): f(Client())` binds `a`: the extra positionals go to `rest`."""
    workspace = _resolved(
        tmp_path,
        {
            "a.py": _A,
            "h.py": "def f(a, *rest):\n    a.get('/')\n",
            "b.py": "from app.a import Client\nfrom app.h import f\ndef g():\n    f(Client(), 1, 2)\n",
        },
    )
    rows = _bound(workspace, _site(workspace, "app/h#f(sig_dd69782a).", "get"))
    assert [row["owner"] for row in rows] == [_CLIENT]
    workspace.close()


def test_a_keyword_only_parameter_is_filled_by_name_or_left_to_its_default(tmp_path: Path):
    """`def f(a, *, b=None)`: `f(x, b=Client())` fills `b`; `f(x)` leaves it to its default,
    `not_readable` naming parameter 1."""
    workspace = _resolved(
        tmp_path,
        {
            "a.py": _A,
            "h.py": "def f(a, *, b=None):\n    b.get('/')\n",
            "b.py": "from app.a import Session, Client\nfrom app.h import f\n"
            "def g():\n    f(Session(), b=Client())\n"
            "def k():\n    f(Session())\n",
        },
    )
    rows = _bound(workspace, _site(workspace, "app/h#f(sig_dd69782a).", "get"))
    assert sorted((str(row["owner"]), str(row["reason"])) for row in rows) == [
        ("None", "not_readable"),
        (_CLIENT, "None"),
    ]
    unfilled = next(row for row in rows if row["owner"] is None)
    assert "parameter 1" in str(unfilled["detail"])
    kinds = {
        str(row["symbol"]).rsplit(" ", 1)[-1]: [
            parameter.get("kind") for parameter in row["signature"]["parameters"]
        ]
        for row in workspace.query("method_declarations")
        if "app/h#f" in str(row["symbol"])
    }
    assert kinds == {"app/h#f(sig_dd69782a).": ["positional", "keyword_only"]}
    workspace.close()
