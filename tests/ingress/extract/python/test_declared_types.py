"""`PythonScanner`: what the module's own code declares (OI-324 part 2).

A function or method of the file that declares its return (`def load() -> list[User]`) types
what the scanner reads OFF its result through a library's signature: an element, a part, an
entered value. The call made directly on the result keeps its owner to the resolver, which
follows the body's returns first (`tests/application/test_declared_types.py`). Every tree is
built in `tmp_path`; nothing is imported or run."""

from pathlib import Path

from tests.ingress.extract.python.test_generics import _owner_of, _scan, _sites

USER = "app/models/User#"
CLIENT = "app/models/Client#"
LIST = "builtins/list#"
DICT = "builtins/dict#"
_MODELS = "from app.models import User, Client\n"


def test_a_declared_list_return_types_its_elements_not_the_call_on_it(tmp_path: Path):
    """`load() -> list[User]`: iterating its result gives `User`s, so `u.save()` is owned; the
    `__iter__` on the result itself is left to the resolver, which reads the body first."""
    tree = _scan(
        tmp_path,
        _MODELS + "def load() -> list[User]:\n"
        "    return fetch()\n"
        "def f():\n"
        "    for u in load():\n"
        "        u.save()\n"
        "    load().append(User())\n",
    )
    assert _owner_of(tree, "app/run#f", "__iter__") == [None]
    assert _owner_of(tree, "app/run#f", "__next__") == ["typing/Iterator#"]
    assert _owner_of(tree, "app/run#f", "save") == [USER]
    assert _owner_of(tree, "app/run#f", "append") == [None]


def test_a_method_of_this_file_declares_through_self_and_a_typed_local(tmp_path: Path):
    """`self.items()` and `repo.items()` on a `repo: Repo` both find `Repo.items`, whose
    declared `dict[str, Client]` makes `.values()` elements `Client`s."""
    tree = _scan(
        tmp_path,
        _MODELS + "class Repo:\n"
        "    def items(self) -> dict[str, Client]:\n"
        "        return self._items\n"
        "    def go(self):\n"
        "        for c in self.items().values():\n"
        "            c.send()\n"
        "def f(repo: Repo):\n"
        "    for c in repo.items().values():\n"
        "        c.send()\n",
    )
    assert _owner_of(tree, "app/run/Repo#go", "values") == [None]
    assert _owner_of(tree, "app/run/Repo#go", "send") == [CLIENT]
    assert _owner_of(tree, "app/run#f", "send") == [CLIENT]


def test_a_generic_class_of_this_file_fills_its_declared_type_variable(tmp_path: Path):
    """`class Box(Generic[T])` with `def all(self) -> list[T]`: on a `Box[User]` the elements
    are `User`s; on a bare `Box` the variable is unfilled and nothing is typed."""
    tree = _scan(
        tmp_path,
        _MODELS + "from typing import Generic, TypeVar\n"
        "T = TypeVar('T')\n"
        "class Box(Generic[T]):\n"
        "    def all(self) -> list[T]:\n"
        "        return self._all\n"
        "def f(box: Box[User], bare: Box):\n"
        "    box.all()[0].save()\n"
        "    bare.all()[0].save()\n",
    )
    assert _owner_of(tree, "app/run#f", "save") == [USER, None]


def test_a_protocol_method_with_no_body_declares_the_only_answer(tmp_path: Path):
    """A `Protocol` method has no body to follow: its declared `Iterator[dict[str, int]]`
    types each row, so `row.get` is owned by `dict`."""
    tree = _scan(
        tmp_path,
        "from typing import Iterator, Protocol\n"
        "class Store(Protocol):\n"
        "    def rows(self) -> Iterator[dict[str, int]]: ...\n"
        "def f(store: Store):\n"
        "    for row in store.rows():\n"
        "        row.get('a')\n",
    )
    assert _owner_of(tree, "app/run#f", "get") == [DICT]


def test_a_declared_tuple_is_taken_apart_by_position(tmp_path: Path):
    """`pair() -> tuple[User, Client]`: `a, b = pair()` gives each name its part."""
    tree = _scan(
        tmp_path,
        _MODELS + "def pair() -> tuple[User, Client]:\n"
        "    return make()\n"
        "def f():\n"
        "    a, b = pair()\n"
        "    a.save()\n"
        "    b.send()\n",
    )
    assert _owner_of(tree, "app/run#f", "save") == [USER]
    assert _owner_of(tree, "app/run#f", "send") == [CLIENT]


def test_two_definitions_declaring_differently_declare_nothing(tmp_path: Path):
    """A name defined on two branches with two declared returns names no one type."""
    tree = _scan(
        tmp_path,
        _MODELS + "if flag:\n"
        "    def load() -> list[User]:\n"
        "        return a()\n"
        "else:\n"
        "    def load() -> list[Client]:\n"
        "        return b()\n"
        "def f():\n"
        "    load()[0].save()\n",
    )
    assert _owner_of(tree, "app/run#f", "save") == [None]


def test_a_declared_class_object_is_constructed_when_called(tmp_path: Path):
    """`kind() -> type[User]`: calling the result constructs a `User` (R37); subscripting it
    is no element read."""
    tree = _scan(
        tmp_path,
        _MODELS + "def kind() -> type[User]:\n    return User\ndef f():\n    kind()().save()\n",
    )
    sites = _sites(tree, "app/run#f")
    assert [(s.target.owner, s.target.name, s.invoke_kind) for s in sites][1:] == [
        (USER, "<init>", "virtual"),
        (USER, "save", "virtual"),
    ]


def test_a_decorated_function_declares_nothing_for_its_call(tmp_path: Path):
    """A decorated name holds what its decorator made: its declaration says nothing of it."""
    tree = _scan(
        tmp_path,
        _MODELS + "def deco(f):\n"
        "    return f\n"
        "@deco\n"
        "def load() -> list[User]:\n"
        "    return a()\n"
        "def f():\n"
        "    load()[0].save()\n",
    )
    assert _owner_of(tree, "app/run#f", "save") == [None]


# -- container literals (step 2) ------------------------------------------------------------


def test_a_container_literal_is_its_class_with_its_elements_types(tmp_path: Path):
    """`[u, u]` is a `list[User]`, `{'a': c}` a `dict[str, Client]`, `{u}` a `set[User]` and
    `(u, c)` a `tuple[User, Client]`; an element read off each is typed."""
    tree = _scan(
        tmp_path,
        _MODELS + "def f(u: User, c: Client):\n"
        "    [u, u][0].save()\n"
        "    {'a': c}['a'].send()\n"
        "    for x in {u}:\n"
        "        x.save()\n"
        "    (u, c)[1].send()\n",
    )
    assert _owner_of(tree, "app/run#f", "__getitem__") == [LIST, DICT, "builtins/tuple#"]
    assert _owner_of(tree, "app/run#f", "__iter__") == ["builtins/set#"]
    assert _owner_of(tree, "app/run#f", "save") == [USER, USER]
    assert _owner_of(tree, "app/run#f", "send") == [CLIENT, CLIENT]


def test_mixed_elements_are_a_closed_list_never_one_of_them(tmp_path: Path):
    """`[u, c]` holds a `User | Client`: a call on an element has no one owner."""
    tree = _scan(
        tmp_path,
        _MODELS + "def f(u: User, c: Client):\n    [u, c][0].save()\n",
    )
    assert _owner_of(tree, "app/run#f", "save") == [None]


def test_a_local_literal_keeps_its_class_after_it_is_handed_out(tmp_path: Path):
    """`found = []`: every call on `found` is a `list`'s, at every read; its elements are not
    known once it was handed out (it may have been written to), so `found[0]` is untyped."""
    tree = _scan(
        tmp_path,
        _MODELS + "def f(u: User):\n"
        "    found = []\n"
        "    found.append(u)\n"
        "    found.append(u)\n"
        "    found[0].save()\n"
        "    names = {'a': u}\n"
        "    names['b'] = Client()\n"
        "    names['b'].save()\n",
    )
    assert _owner_of(tree, "app/run#f", "append") == [LIST, LIST]
    assert _owner_of(tree, "app/run#f", "__getitem__") == [LIST, DICT]
    assert _owner_of(tree, "app/run#f", "save") == [None, None]


def test_a_comprehension_is_its_class_with_its_elements_type(tmp_path: Path):
    """`[u for _ in xs]` is a `list[User]`; `{k: c for k in ks}` a dict."""
    tree = _scan(
        tmp_path,
        _MODELS + "def f(xs, ks, u: User, c: Client):\n"
        "    users = [u for _ in xs]\n"
        "    users[0].save()\n"
        "    clients = {k: c for k in ks}\n"
        "    clients.values()\n",
    )
    assert _owner_of(tree, "app/run#f", "save") == [USER]
    assert _owner_of(tree, "app/run#f", "values") == [DICT]


def test_a_literal_writes_the_facts_it_wrote_before(tmp_path: Path):
    """The element types are the scanner's own: the facts still read `array` and `merge`."""
    tree = _scan(
        tmp_path,
        _MODELS + "def g(*a):\n"
        "    return a\n"
        "def f(c):\n"
        "    xs = [1] if c else [2]\n"
        "    g(xs, {'a': 1})\n",
    )
    (call,) = [s for s in _sites(tree, "app/run#f") if s.target.name == "g"]
    assert call.arguments[0].kind == "merge"
    assert [a.kind for a in call.arguments[0].candidates or []] == ["array", "array"]
    assert call.arguments[1].kind == "unresolved"
