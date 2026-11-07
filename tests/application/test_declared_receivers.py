"""Receiver binding with declared types (OI-324 part 2): what the module's own code declares
answers where the code it runs does not.

The walk follows a call's result into its callee's body first, path by path; on a return path
the body answers with no type, and for a method with no body (a `Protocol`'s, an abstract
one), the method's declared return type answers, with `declared` evidence. Each test scans a
small tree with the real scanner and runs the real pipeline (`test_receiver_binding`)."""

from pathlib import Path

from test_receiver_binding import _PREFIX, _bound, _edges, _resolved, _site

_USER = "app/a/User#"
_MODELS = (
    "from typing import Protocol\n"
    "class User:\n"
    "    def save(self):\n"
    "        return 1\n"
    "class Admin(User):\n"
    "    def save(self):\n"
    "        return 2\n"
)
_F = "app/b#f(sig_dd69782a)."


def _rows(workspace, site):
    return [(row["owner"], row["evidence"], row["reason"]) for row in _bound(workspace, site)]


def test_a_declared_return_answers_where_the_body_gives_no_type(tmp_path: Path):
    """`load() -> User` returns what an unread library call gives: the declared `User`
    answers, `declared`, and the edges go to `User.save` and its override."""
    workspace = _resolved(
        tmp_path,
        {
            "a.py": _MODELS + "import json\ndef load() -> User:\n    return json.loads('x')\n",
            "b.py": "from app.a import load\ndef f():\n    load().save()\n",
        },
    )
    site = _site(workspace, _F, "save")
    assert _rows(workspace, site) == [(_USER, "declared", None)]
    assert sorted(str(row["callee"]) for row in _edges(workspace, site)) == [
        _PREFIX + "app/a/Admin#save(sig_dd69782a).",
        _PREFIX + "app/a/User#save(sig_dd69782a).",
    ]
    workspace.close()


def test_the_bodys_own_type_stays_the_answer_on_its_path(tmp_path: Path):
    """`make() -> User` returning `Admin()`: the body's `Admin` is what runs, `syntax`."""
    workspace = _resolved(
        tmp_path,
        {
            "a.py": _MODELS + "def make() -> User:\n    return Admin()\n",
            "b.py": "from app.a import make\ndef f():\n    make().save()\n",
        },
    )
    assert _rows(workspace, _site(workspace, _F, "save")) == [("app/a/Admin#", "syntax", None)]
    workspace.close()


def test_a_protocol_method_with_no_body_answers_with_its_declaration(tmp_path: Path):
    """A `Protocol` method has no body: its declared `User` is the only answer."""
    workspace = _resolved(
        tmp_path,
        {
            "a.py": _MODELS + "class Store(Protocol):\n    def get(self) -> User: ...\n",
            "b.py": "from app.a import Store\ndef f(store: Store):\n    store.get().save()\n",
        },
    )
    assert _rows(workspace, _site(workspace, _F, "save")) == [(_USER, "declared", None)]
    workspace.close()


def test_a_declared_union_is_each_of_its_classes(tmp_path: Path):
    """`-> User | Store` is a closed list: one row per class, the site `narrowed`."""
    workspace = _resolved(
        tmp_path,
        {
            "a.py": _MODELS
            + "class Store:\n    def save(self):\n        return 3\n"
            + "def pick() -> User | Store | None:\n    return unknown()\n",
            "b.py": "from app.a import pick\ndef f():\n    pick().save()\n",
        },
    )
    rows = _bound(workspace, _site(workspace, _F, "save"))
    assert sorted((row["owner"], row["evidence"], row["resolution"]) for row in rows) == [
        ("app/a/Store#", "declared", "narrowed"),
        (_USER, "declared", "narrowed"),
    ]
    workspace.close()


def test_a_call_syntax_makes_is_not_bound_on_a_declaration_alone(tmp_path: Path):
    """A declared type does not say whether the value is the class or an instance (the facts
    write `type[User]` as `User`), so `m.kind()()`, with `m` bound by the resolver, is not
    read as `User.__call__`. (Where the scanner reads `kind`'s header itself, it knows the
    class object and writes the construction.)"""
    workspace = _resolved(
        tmp_path,
        {
            "a.py": _MODELS
            + "class Maker:\n    def kind(self) -> type[User]:\n        return unknown()\n",
            "b.py": "from app.a import Maker\ndef f(m):\n    m.kind()()\n"
            "def g():\n    f(Maker())\n",
        },
    )
    site = _site(workspace, "app/b#f(sig_dd69782a).", "__call__")
    ((owner, _, reason),) = _rows(workspace, site)
    assert (owner, reason) == (None, "not_readable")
    assert not [row for row in _edges(workspace, site) if row["callee"]]
    workspace.close()


def test_an_unannotated_callee_is_followed_as_before(tmp_path: Path):
    """No declaration, no new answer: the body's unread result stays a reason."""
    workspace = _resolved(
        tmp_path,
        {
            "a.py": _MODELS + "import json\ndef load():\n    return json.loads('x')\n",
            "b.py": "from app.a import load\ndef f():\n    load().save()\n",
        },
    )
    ((owner, _, reason),) = _rows(workspace, _site(workspace, _F, "save"))
    assert owner is None and reason is not None
    workspace.close()


def test_a_decorated_function_declares_nothing_for_its_call(tmp_path: Path):
    """`@contextmanager`-shaped: the name holds what the decorator made, so a call of it is
    that value's, which `load`'s own `-> User` does not describe."""
    workspace = _resolved(
        tmp_path,
        {
            "a.py": _MODELS
            + "import json, functools\n"
            + "def deco(f):\n    return functools.partial(f)\n"
            + "@deco\ndef load() -> User:\n    return json.loads('x')\n",
            "b.py": "from app.a import load\ndef f():\n    load().save()\n",
        },
    )
    assert not [row for row in _bound(workspace, _site(workspace, _F, "save")) if row["owner"]]
    workspace.close()


def test_a_call_in_the_callees_own_file_takes_its_declaration_too(tmp_path: Path):
    """The call on the result of a same-file function keeps its owner to the resolver, which
    answers as for a call from another file."""
    workspace = _resolved(
        tmp_path,
        {
            "a.py": _MODELS
            + "import json\ndef load() -> User:\n    return json.loads('x')\n"
            + "def f():\n    load().save()\n",
        },
    )
    assert _rows(workspace, _site(workspace, "app/a#f(sig_dd69782a).", "save")) == [
        (_USER, "declared", None)
    ]
    workspace.close()


# -- attributes declared in a class body (step 3) ------------------------------------------

_CLIENTS = (
    "class HttpClient:\n"
    "    def get(self):\n"
    "        return 1\n"
    "class FastClient(HttpClient):\n"
    "    def get(self):\n"
    "        return 2\n"
)


def test_an_attribute_no_code_writes_is_its_declaration(tmp_path: Path):
    """A dataclass's `client: HttpClient`: its generated `__init__` is not code we read, so
    the declaration answers, `declared`, and the edges reach the override too."""
    workspace = _resolved(
        tmp_path,
        {
            "a.py": _CLIENTS
            + "from dataclasses import dataclass\n@dataclass\nclass Service:\n"
            + "    client: HttpClient\n    def run(self):\n        self.client.get()\n",
        },
    )
    site = _site(workspace, "app/a/Service#run(sig_dd69782a).", "get")
    assert _rows(workspace, site) == [("app/a/HttpClient#", "declared", None)]
    assert len(_edges(workspace, site)) == 2
    workspace.close()


def test_a_subclass_redeclaring_the_attribute_is_one_more_class(tmp_path: Path):
    """Ruling R33: a read in `Service` takes `Service`'s declaration and each subtype's, here
    `Fast`'s narrower `client: FastClient` in another file: a closed list, one row each."""
    workspace = _resolved(
        tmp_path,
        {
            "a.py": _CLIENTS
            + "class Service:\n    client: HttpClient\n"
            + "    def run(self):\n        self.client.get()\n",
            "b.py": "from app.a import Service, FastClient\n"
            "class Fast(Service):\n    client: FastClient\n",
        },
    )
    site = _site(workspace, "app/a/Service#run(sig_dd69782a).", "get")
    assert sorted(_rows(workspace, site)) == [
        ("app/a/FastClient#", "declared", None),
        ("app/a/HttpClient#", "declared", None),
    ]
    workspace.close()


def test_a_write_the_walk_reads_a_type_of_stays_the_answer(tmp_path: Path):
    """`self.client = FastClient()` is what the object holds: `syntax`, the declaration aside."""
    workspace = _resolved(
        tmp_path,
        {
            "a.py": _CLIENTS
            + "class Service:\n    client: HttpClient\n"
            + "    def __init__(self):\n        self.client = FastClient()\n"
            + "    def run(self):\n        self.client.get()\n",
        },
    )
    site = _site(workspace, "app/a/Service#run(sig_dd69782a).", "get")
    assert _rows(workspace, site) == [("app/a/FastClient#", "syntax", None)]
    workspace.close()


def test_a_declaration_naming_another_files_alias_is_the_aliased_class(tmp_path: Path):
    """`Alias = HttpClient` in `a.py` is a field there; `c: Alias` in `b.py` names the class
    the alias is (round 1, item 3, read off `a.py`'s header), never the path `app/a/Alias#`,
    which no class carries."""
    workspace = _resolved(
        tmp_path,
        {
            "a.py": _CLIENTS + "Alias = HttpClient\n",
            "b.py": "from app.a import Alias\nclass S:\n    c: Alias\n"
            "    def run(self):\n        self.c.get()\n",
        },
    )
    site = _site(workspace, "app/b/S#run(sig_dd69782a).", "get")
    assert [row["owner"] for row in _bound(workspace, site) if row["owner"]] == [
        "app/a/HttpClient#"
    ]
    workspace.close()


# -- a generic class from another file (step 6) --------------------------------------------

_REPO = (
    _MODELS
    + "from typing import Generic, TypeVar\n"
    + "T = TypeVar('T')\n"
    + "class Repo[M]:\n"
    + "    def get(self) -> M:\n"
    + "        return unknown()\n"
    + "class Old(Generic[T]):\n"
    + "    def first(self) -> T | None:\n        return unknown()\n"
    + "class Mid[X](Repo[X]):\n"
    + "    pass\n"
)


def test_a_subclass_in_another_file_fills_its_generic_parents_parameters(tmp_path: Path):
    """`UserRepo(Repo[User])`: `get`'s declared `M` is `User` on a `UserRepo`, through the
    parent's written type arguments, PEP 695 or `Generic[T]`, one hop or two."""
    workspace = _resolved(
        tmp_path,
        {
            "a.py": _REPO,
            "b.py": "from app.a import Repo, Old, Mid, User\n"
            "class UserRepo(Repo[User]):\n    pass\n"
            "class OldRepo(Old[User]):\n    pass\n"
            "class Leaf(Mid[User]):\n    pass\n"
            "def f(r: UserRepo, o: OldRepo, l: Leaf):\n"
            "    r.get().save()\n"
            "    o.first().save()\n"
            "    l.get().save()\n",
        },
    )
    saves = sorted(
        (int(str(row["ordinal"])), row["owner"], row["evidence"])
        for row in workspace.query("bound_receivers")
        if str(row["caller"]).endswith(_F) and row["owner"]
    )
    assert [(owner, evidence) for _, owner, evidence in saves] == [(_USER, "declared")] * 3
    workspace.close()


def test_a_generic_parent_itself_leaves_its_parameter_unfilled(tmp_path: Path):
    """On a bare `Repo` nothing fills `M`: no answer, never a guessed one."""
    workspace = _resolved(
        tmp_path,
        {
            "a.py": _REPO,
            "b.py": "from app.a import Repo\ndef f(r: Repo):\n    r.get().save()\n",
        },
    )
    assert not [row for row in _bound(workspace, _site(workspace, _F, "save")) if row["owner"]]
    workspace.close()


# -- `Self` (round 1, item 1) ------------------------------------------------------------

_FACTORY = (
    "from typing import Self\n"
    "class Repo:\n"
    "    @classmethod\n    def make(cls) -> Self:\n        return cls()\n"
    "    def find(self):\n        return 0\n"
    "    def again(self):\n        return self.make()\n"
    "class Other(Repo):\n    def find(self):\n        return 1\n"
)


def test_self_is_the_class_the_call_was_made_through(tmp_path: Path):
    """`UserRepo.make()`, `make` on `Repo` declared `-> Self`: the result is a `UserRepo`,
    exactly, though `UserRepo` is another file's class the resolver binds."""
    workspace = _resolved(
        tmp_path,
        {
            "a.py": _FACTORY,
            "b.py": "from app.a import Repo\nclass UserRepo(Repo):\n"
            "    def find(self):\n        return 2\n"
            "def f():\n    UserRepo.make().find()\n",
        },
    )
    site = _site(workspace, _F, "find")
    assert [(r["owner"], r["evidence"], r["resolution"]) for r in _bound(workspace, site)] == [
        ("app/b/UserRepo#", "declared", "resolved")
    ]
    workspace.close()


def test_self_through_the_methods_own_receiver_is_the_class_or_a_subclass(tmp_path: Path):
    """`self.make()` inside `Repo`: the receiver is a `Repo` or any subclass, one row each."""
    workspace = _resolved(
        tmp_path,
        {"a.py": _FACTORY + "def f(r: Repo):\n    r.again().find()\n"},
    )
    site = _site(workspace, "app/a#f(sig_dd69782a).", "find")
    assert sorted(str(r["owner"]) for r in _bound(workspace, site)) == [
        "app/a/Other#",
        "app/a/Repo#",
    ]
    workspace.close()


def test_a_class_a_package_re_exports_is_named_by_where_it_is_defined(tmp_path: Path):
    """`from app.pkg import Order`, `app/pkg/__init__.py` re-exporting it from `.order`: the
    call names `app/pkg/order/Order#`, the class, and reaches its body (round 1, item 3)."""
    workspace = _resolved(
        tmp_path,
        {
            "pkg/__init__.py": "from .order import Order\n",
            "pkg/order.py": "class Order:\n    def total(self):\n        return 1\n",
            "b.py": "from app.pkg import Order\ndef f(o: Order):\n    o.total()\n",
        },
    )
    site = _site(workspace, _F, "total")
    assert [row["callee"] for row in _edges(workspace, site)] == [
        _PREFIX + "app/pkg/order/Order#total(sig_dd69782a)."
    ]
    workspace.close()


def test_a_parameter_with_a_written_type_is_that_type_for_the_type_reader(tmp_path: Path):
    """`self.session` written from `__init__`'s `session: Session`: the written parameter type
    answers, as the scanner takes it for a call on the parameter itself, and no caller is
    read for it (round 1: on polar's repository graph that walk did not end in minutes)."""
    workspace = _resolved(
        tmp_path,
        {
            "a.py": "class Session:\n    def run(self):\n        return 1\n"
            "class Repo:\n"
            "    def __init__(self, session: Session):\n        self.session = session\n"
            "    def go(self):\n        self.session.run()\n",
            "b.py": "from app.a import Repo\ndef f(s):\n    Repo(s).go()\n",
        },
    )
    site = _site(workspace, "app/a/Repo#go(sig_dd69782a).", "run")
    assert _rows(workspace, site) == [("app/a/Session#", "declared", None)]
    workspace.close()
