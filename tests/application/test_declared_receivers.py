"""Receiver binding with declared types (OI-324 part 2): what the module's own code declares
answers where the code it runs does not.

The walk follows a call's result into its callee's body first, path by path; on a return path
the body answers with no type, and for a method with no body (a `Protocol`'s, an abstract
one), the method's declared return type answers, with `declared` evidence. Each test scans a
small tree with the real scanner and runs the real pipeline (`test_receiver_binding`)."""

from pathlib import Path

from tests.application.test_receiver_binding import _PREFIX, _bound, _edges, _resolved, _site

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
    write `type[User]` as `User`), so `kind()()` is not read as `User.__call__`."""
    workspace = _resolved(
        tmp_path,
        {
            "a.py": _MODELS + "def kind() -> type[User]:\n    return unknown()\n",
            "b.py": "from app.a import kind\ndef f():\n    kind()()\n",
        },
    )
    site = _site(workspace, _F, "__call__")
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
