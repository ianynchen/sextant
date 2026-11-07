"""Receiver binding (spec 2026-11-06 §3b, plan 1 task 8): the resolver binds a call the
scanner wrote with no owner, from what produced its receiver, on the existing value walk.

Each test scans a small Python tree with the real scanner, writes the module fact (`c3`),
and runs the real pipeline with no catalogs, then reads `bound_receivers` (one row per
path the walk reached the receiver by) and `call_edges` (one edge per bound owner).
"""

from pathlib import Path

import pytest

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


def _owners(workspace: DuckDbWorkspace, site: tuple[str, int]) -> list[tuple[object, ...]]:
    return sorted(
        (str(row["owner"]), str(row["resolution"]), str(row["reason"]))
        for row in _bound(workspace, site)
    )


def test_a_field_a_subclass_also_sets_is_both_writes(tmp_path: Path):
    """Ruling R33: an object's attributes are one namespace, whichever class's code wrote
    them. `self.d` read in `B` is `Session` on a `B` and `Client` on a `D`: a closed list,
    never the base's write alone."""
    workspace = _resolved(
        tmp_path,
        {
            "a.py": _A,
            "b.py": "from app.a import Session, Client\n"
            "class B:\n"
            "    def __init__(self):\n"
            "        self.d = Session()\n"
            "    def use(self):\n"
            "        self.d.get(1)\n"
            "class D(B):\n"
            "    def __init__(self):\n"
            "        super().__init__()\n"
            "        self.d = Client()\n",
        },
    )
    site = _site(workspace, "app/b/B#use(sig_dd69782a).", "get")
    assert _owners(workspace, site) == [
        (_CLIENT, "narrowed", "None"),
        (_SESSION, "narrowed", "None"),
    ]
    assert sorted(str(row["callee"]) for row in _edges(workspace, site)) == [
        _PREFIX + "app/a/Client#get(sig_dd69782a).",
        _PREFIX + "app/a/Session#get(sig_dd69782a).",
    ]
    workspace.close()


def test_a_class_attribute_a_subclass_overrides_is_both_values(tmp_path: Path):
    """`model = …` / `serializer_class = …` overridden in a subclass: `self.c` in the base
    is either class's attribute."""
    workspace = _resolved(
        tmp_path,
        {
            "a.py": _A,
            "b.py": "from app.a import Session, Client\n"
            "class B:\n"
            "    c = Session()\n"
            "    def use(self):\n"
            "        self.c.get(1)\n"
            "class D(B):\n"
            "    c = Client()\n",
        },
    )
    site = _site(workspace, "app/b/B#use(sig_dd69782a).", "get")
    assert _owners(workspace, site) == [
        (_CLIENT, "narrowed", "None"),
        (_SESSION, "narrowed", "None"),
    ]
    workspace.close()


def test_a_field_an_ancestor_writes_is_read_in_the_subclass(tmp_path: Path):
    """`self.d` read in `D`, written only in `B.__init__`: the ancestor's write, one value."""
    workspace = _resolved(
        tmp_path,
        {
            "a.py": _A,
            "b.py": "from app.a import Session\n"
            "class B:\n"
            "    def __init__(self):\n"
            "        self.d = Session()\n"
            "class D(B):\n"
            "    def use(self):\n"
            "        self.d.get(1)\n",
        },
    )
    site = _site(workspace, "app/b/D#use(sig_dd69782a).", "get")
    assert _owners(workspace, site) == [(_SESSION, "resolved", "None")]
    workspace.close()


def test_a_field_of_a_class_with_an_unread_parent_is_partial(tmp_path: Path):
    """A parent nothing scanned may write the attribute too: the module's write is kept
    beside `external`, and the site is `partial`."""
    workspace = _resolved(
        tmp_path,
        {
            "a.py": _A,
            "b.py": "from app.a import Session\n"
            "from elsewhere import Base\n"
            "class D(Base):\n"
            "    def __init__(self):\n"
            "        self.d = Session()\n"
            "    def use(self):\n"
            "        self.d.get(1)\n",
        },
    )
    site = _site(workspace, "app/b/D#use(sig_dd69782a).", "get")
    assert _owners(workspace, site) == [
        ("None", "unresolved", "external"),
        (_SESSION, "partial", "None"),
    ]
    workspace.close()


def test_a_field_of_a_subclass_with_an_unread_parent_is_partial(tmp_path: Path):
    """A subtype whose other parent was not read: that parent's code may write the
    attribute on the object `B.use` is called on."""
    workspace = _resolved(
        tmp_path,
        {
            "a.py": _A,
            "b.py": "from app.a import Session\n"
            "from elsewhere import Mixin\n"
            "class B:\n"
            "    def __init__(self):\n"
            "        self.d = Session()\n"
            "    def use(self):\n"
            "        self.d.get(1)\n"
            "class D(B, Mixin):\n"
            "    pass\n",
        },
    )
    site = _site(workspace, "app/b/B#use(sig_dd69782a).", "get")
    assert _owners(workspace, site) == [
        ("None", "unresolved", "external"),
        (_SESSION, "partial", "None"),
    ]
    workspace.close()


def test_a_name_a_nested_function_rebinds_nonlocal_is_not_one_value(tmp_path: Path):
    """`nonlocal h; h = Client()` in a callback: when the callback runs is not known here,
    so `h.get()` after `run(cb)` is no one value, never the `Session` written before."""
    workspace = _resolved(
        tmp_path,
        {
            "a.py": _A,
            "b.py": "from app.a import Session, Client\n"
            "def f(run):\n"
            "    h = Session()\n"
            "    def cb():\n"
            "        nonlocal h\n"
            "        h = Client()\n"
            "    run(cb)\n"
            "    h.get(1)\n",
        },
    )
    site = _site(workspace, "app/b#f(sig_dd69782a).", "get")
    assert _owners(workspace, site) == [("None", "unresolved", "not_readable")]
    assert [row["callee"] for row in _edges(workspace, site)] == [None]
    workspace.close()


def test_a_match_capture_is_a_write_of_its_name(tmp_path: Path):
    """`case Client() as s:` binds `s` to the subject `v`, which nothing here passes;
    `case [s, *rest]:` to a part of it, not read. After the `match`, `s` is no one value
    (a path the scanner does not follow joined with the others), never the `Session`."""
    workspace = _resolved(
        tmp_path,
        {
            "a.py": _A,
            "b.py": "from app.a import Session, Client\n"
            "def f(v):\n"
            "    s = Session()\n"
            "    match v:\n"
            "        case Client() as s if s.get(0):\n"
            "            pass\n"
            "        case [s, *rest]:\n"
            "            s.get(1)\n"
            "    s.get(2)\n",
        },
    )
    guard, inside, after = sorted(
        (
            (str(row["caller"]), int(str(row["ordinal"])))
            for row in workspace.query("call_sites")
            if row["name"] == "get"
        ),
        key=lambda site: site[1],
    )
    assert _owners(workspace, guard) == [("None", "unresolved", "external")]
    assert _owners(workspace, inside) == [("None", "unresolved", "not_readable")]
    assert _owners(workspace, after) == [("None", "unresolved", "not_readable")]
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


def test_a_call_in_the_callees_own_file_binds_as_one_from_another_file(tmp_path: Path):
    """Ruling R27: the scanner writes `k=Session()` as written in either file, and the
    resolver's one calling rule binds both calls of `f3(a, *, k)` to `Session`."""
    workspace = _resolved(
        tmp_path,
        {
            "a.py": _A,
            "b.py": "from app.a import Session, Client\n"
            "def f3(a, *, k):\n    k.get('/')\n"
            "def g():\n    f3(Client(), k=Session())\n",
            "c.py": "from app.a import Session, Client\nfrom app.b import f3\n"
            "def h():\n    f3(Client(), k=Session())\n",
        },
    )
    rows = _bound(workspace, _site(workspace, "app/b#f3(sig_dd69782a).", "get"))
    assert sorted((str(row["owner"]), str(row["path_id"]).rsplit(" ", 1)[-1]) for row in rows) == [
        (_SESSION, "app/b#g(sig_dd69782a).@2"),
        (_SESSION, "app/c#h(sig_dd69782a).@2"),
    ]
    workspace.close()


def test_a_parent_init_called_through_its_class_fills_self_first(tmp_path: Path):
    """`Base.__init__(self, Session())` calls `Base`'s `__init__` through the class: `self`
    is its first argument, so `c` is the `Session` — beside `super().__init__(Client())`."""
    workspace = _resolved(
        tmp_path,
        {
            "a.py": _A + "class Base:\n"
            "    def __init__(self, c):\n        self.c = c\n"
            "    def run(self):\n        self.c.get('/')\n"
            "class Kid(Base):\n    def __init__(self):\n        Base.__init__(self, Session())\n"
            "class Kid2(Base):\n    def __init__(self):\n        super().__init__(Client())\n",
            "b.py": "from app.a import Kid, Kid2\ndef f():\n    Kid().run()\n    Kid2().run()\n",
        },
    )
    rows = _bound(workspace, _site(workspace, "app/a/Base#run(sig_dd69782a).", "get"))
    assert sorted(str(row["owner"]) for row in rows) == [_CLIENT, _SESSION]
    workspace.close()


def test_a_method_called_through_its_class_fills_self_with_its_first_argument(tmp_path: Path):
    """`H.use(h, Session())` from another file: `h` fills `self`, so `x` is the `Session`,
    never `H`. A classmethod called through its class fills no `cls`."""
    workspace = _resolved(
        tmp_path,
        {
            "a.py": _A + "class H:\n    def use(self, x):\n        x.get('/')\n"
            "class U:\n    @classmethod\n    def c(cls, x, y):\n        y.get('/')\n",
            "b.py": "from app.a import H, U, Session, Client\n"
            "def f():\n    h = H()\n    H.use(h, Session())\n    U.c(Session(), Client())\n",
        },
    )
    used = _bound(workspace, _site(workspace, "app/a/H#use(sig_dd69782a).", "get"))
    assert [row["owner"] for row in used] == [_SESSION]
    classed = _bound(workspace, _site(workspace, "app/a/U#c(sig_dd69782a).", "get"))
    # The decorator hands `c` on as a value, which adds its `escapes` row beside the binding.
    assert {row["owner"] for row in classed if row["owner"]} == {_CLIENT}
    workspace.close()


def test_a_function_that_always_raises_is_called_not_external(tmp_path: Path):
    """A function with no normal return has no body the edges reach, but its callers are in
    the module: its parameter is `not_readable`, saying so, never "nothing calls"."""
    workspace = _resolved(
        tmp_path,
        {
            "a.py": _A,
            "b.py": "from app.a import Session\n"
            "def fail(c):\n    c.get('/')\n    raise ValueError('x')\n"
            "def f():\n    fail(Session())\n",
        },
    )
    rows = _bound(workspace, _site(workspace, "app/b#fail(sig_dd69782a).", "get"))
    assert [row["reason"] for row in rows] == ["not_readable"]
    assert "never returns normally" in str(rows[0]["detail"])
    workspace.close()


# Task 9a fix round 1: a decorated name holds its decorator's result (design §3e).

_IDENT = (
    "def ident(fn):\n    return fn\n@ident\ndef f():\n    return 1\ndef run():\n    return f()\n"
)


def test_a_module_decorator_that_returns_its_argument_gives_the_function_back(tmp_path: Path):
    """`@ident def f` makes `f` the field written from `ident(f)`; `ident` returns its
    argument, so the walk follows `ident`'s own code to the function value, and calling a
    function runs it (ruling R29, as a lambda on the JVM): `f()` is an edge to `f`'s body,
    with no owner bound for it."""
    workspace = _resolved(tmp_path, {"a.py": _IDENT})
    site = _site(workspace, "app/a#run(sig_dd69782a).", "__call__")
    assert [(row["callee"], row["resolution"]) for row in _edges(workspace, site)] == [
        (_PREFIX + "app/a#f(sig_dd69782a).", "resolved")
    ]
    assert _bound(workspace, site) == []
    workspace.close()


_WRAPPING = (
    "def deco(fn):\n"
    "    def w(*a):\n"
    "        return fn(*a)\n"
    "    return w\n"
    "@deco\ndef f():\n    return 1\n"
    "def run():\n    return f()\n"
)


def test_a_decorator_that_returns_its_own_wrapper_runs_the_wrapper(tmp_path: Path):
    """`deco` returns its nested `w`: the name `f` holds `w`, so `f()` runs `w`'s body."""
    workspace = _resolved(tmp_path, {"a.py": _WRAPPING})
    site = _site(workspace, "app/a#run(sig_dd69782a).", "__call__")
    assert [row["callee"] for row in _edges(workspace, site)] == [
        _PREFIX + "app/a#deco$w(sig_dd69782a)."
    ]
    workspace.close()


@pytest.mark.xfail(
    strict=True,
    reason="a nested function's read of an enclosing name (`fn` in `w`) is `unresolved`: the "
    "scanner writes no captures (calls.py `_local`), so the wrapper's `fn(*a)` is not followed "
    "to `f` (task 9a fix round 2 report)",
)
def test_the_wrappers_call_of_its_argument_reaches_the_decorated_function(tmp_path: Path):
    workspace = _resolved(tmp_path, {"a.py": _WRAPPING})
    inner = _site(workspace, "app/a#deco$w(sig_dd69782a).", "__call__")
    assert [row["callee"] for row in _edges(workspace, inner)] == [
        _PREFIX + "app/a#f(sig_dd69782a)."
    ]
    workspace.close()


def test_a_functools_wraps_wrapper_stops_at_the_library_until_it_is_stated(tmp_path: Path):
    """`@functools.wraps(fn) def w` makes `w` what `wraps(fn)(w)` returns, which no value
    model states yet (9b's `returns_argument`): `f()` is `external`, with no wrong owner and
    no edge to a body it may not run."""
    workspace = _resolved(
        tmp_path,
        {
            "a.py": "import functools\n"
            + _WRAPPING.replace("    def w(*a):", "    @functools.wraps(fn)\n    def w(*a):")
        },
    )
    site = _site(workspace, "app/a#run(sig_dd69782a).", "__call__")
    assert {row["reason"] for row in _bound(workspace, site)} == {"external"}
    assert [(e["target"], e["callee"]) for e in _edges(workspace, site)] == [(None, None)]
    workspace.close()


def test_a_function_on_one_path_and_an_object_on_another_are_each_their_own(tmp_path: Path):
    """`call(h)` is given a function on one path and a `Runner` on another: `h()` runs the
    function's body on the first and `Runner.__call__` on the second, two edges, `narrowed`;
    the `Runner` path is a bound row, the function path binds no owner."""
    workspace = _resolved(
        tmp_path,
        {
            "a.py": (
                "class Runner:\n    def __call__(self):\n        return 2\n"
                "def job():\n    return 1\n"
                "def call(h):\n    return h()\n"
                "def one():\n    call(job)\n"
                "def two():\n    call(Runner())\n"
            )
        },
    )
    site = _site(workspace, "app/a#call(sig_dd69782a).", "__call__")
    assert sorted((e["callee"], e["resolution"]) for e in _edges(workspace, site)) == [
        (_PREFIX + "app/a#job(sig_dd69782a).", "narrowed"),
        (_PREFIX + "app/a/Runner#__call__(sig_dd69782a).", "narrowed"),
    ]
    assert [row["owner"] for row in _bound(workspace, site)] == ["app/a/Runner#"]
    workspace.close()


def test_a_formatted_string_is_never_read_as_a_function(tmp_path: Path):
    """R19b: an f-string is a `concat` made by a `dynamic` `str.format` site, never a
    function value, so calling it binds no body."""
    workspace = _resolved(
        tmp_path,
        {"a.py": "def call(h):\n    return h()\ndef one(y):\n    call(f'{y}!')\n"},
    )
    site = _site(workspace, "app/a#call(sig_dd69782a).", "__call__")
    assert all(e["callee"] is None for e in _edges(workspace, site))
    workspace.close()


def test_a_library_wrapper_stops_at_the_library(tmp_path: Path):
    """`@tenacity.retry def r` (not installed): `r` holds what the library returns, which
    the module does not show, so `r()` is `external` with no edge. `@functools.cache def f`:
    typeshed writes the wrapper's class, so `f()` is that class's `__call__`, a library
    method. Neither reaches a wrong owner."""
    workspace = _resolved(
        tmp_path,
        {
            "a.py": (
                "import functools\nimport tenacity\n"
                "@functools.cache\ndef f():\n    return 1\n"
                "@tenacity.retry\ndef r():\n    return 1\n"
                "def run():\n    f()\n    r()\n"
            )
        },
    )
    cached = (_PREFIX + "app/a#run(sig_dd69782a).", 0)
    retried = (_PREFIX + "app/a#run(sig_dd69782a).", 1)
    assert [(e["target"], e["callee"]) for e in _edges(workspace, cached)] == [
        ("functools/_lru_cache_wrapper#__call__(sig_dd69782a).", None)
    ]
    assert [(row["owner"], row["reason"]) for row in _bound(workspace, retried)] == [
        (None, "external")
    ]
    assert [(e["target"], e["callee"]) for e in _edges(workspace, retried)] == [(None, None)]
    workspace.close()
