"""`PythonScanner`: what the module's own code declares (OI-324 part 2).

A function or method of the file that declares its return (`def load() -> list[User]`) types
what the scanner reads OFF its result through a library's signature: an element, a part, an
entered value. The call made directly on the result keeps its owner to the resolver, which
follows the body's returns first (`tests/application/test_declared_types.py`). Every tree is
built in `tmp_path`; nothing is imported or run."""

from pathlib import Path

from test_generics import _owner_of, _scan, _sites

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


# -- attributes declared in a class body (step 3) ------------------------------------------

_SERVICE = (
    "from dataclasses import dataclass\n"
    "class HttpClient:\n"
    "    def get(self):\n"
    "        return 1\n"
    "@dataclass\n"
    "class Service:\n"
    "    client: HttpClient\n"
    "    clients: list[HttpClient]\n"
    "    def run(self):\n"
    "        self.client.get()\n"
    "        for c in self.clients:\n"
    "            c.get()\n"
)
_HTTP = "app/run/HttpClient#"


def test_an_attribute_read_on_a_value_takes_its_class_body_declaration(tmp_path: Path):
    """`s.client` with `s: Service` is the `HttpClient` the class body declares (PEP 526), for
    any class: no framework is named. An element of `s.clients` is one too."""
    tree = _scan(
        tmp_path,
        _SERVICE + "def f(s: Service):\n"
        "    s.client.get()\n"
        "    for c in s.clients:\n"
        "        c.get()\n",
    )
    assert _owner_of(tree, "app/run#f", "get") == [_HTTP, _HTTP]


def test_an_attribute_of_self_leaves_its_owner_to_the_writes_and_types_its_elements(
    tmp_path: Path,
):
    """`self.client` is what the object's writes hold (the resolver reads them, ruling R33):
    no owner here; an element of `self.clients` is read off the declaration."""
    tree = _scan(tmp_path, _SERVICE)
    assert _owner_of(tree, "app/run/Service#run", "get") == [None, _HTTP]
    assert _owner_of(tree, "app/run/Service#run", "__iter__") == [None]


# -- isinstance narrowing (step 4) -----------------------------------------------------------


def test_isinstance_narrows_inside_its_branch_only(tmp_path: Path):
    """`isinstance(x, User)` makes `x` a `User` in the body; after the `if`, where the other
    path joins, `x` is what it was."""
    tree = _scan(
        tmp_path,
        _MODELS + "def f(x):\n    if isinstance(x, User):\n        x.save()\n    x.save()\n",
    )
    saves = [s for s in _sites(tree, "app/run#f") if s.target.name == "save"]
    assert [(s.target.owner, s.receiver_parameter) for s in saves] == [(USER, 0), (None, 0)]


def test_an_early_exit_on_the_negated_test_narrows_the_rest(tmp_path: Path):
    """`if not isinstance(x, User): return` leaves only the path where `x` is a `User`."""
    tree = _scan(
        tmp_path,
        _MODELS + "def f(x: object):\n"
        "    if not isinstance(x, User):\n"
        "        raise TypeError(x)\n"
        "    x.save()\n",
    )
    assert _owner_of(tree, "app/run#f", "save") == [USER]


def test_a_tuple_of_classes_is_a_closed_list(tmp_path: Path):
    """`isinstance(x, (User, Client))` makes `x` one of them: no one owner."""
    tree = _scan(
        tmp_path,
        _MODELS + "def f(x):\n    if isinstance(x, (User, Client)):\n        x.save()\n",
    )
    assert _owner_of(tree, "app/run#f", "save") == [None]


def test_no_narrowing_survives_a_reassignment(tmp_path: Path):
    """`x = make()` inside the branch: `x` is the new value, not the tested one."""
    tree = _scan(
        tmp_path,
        _MODELS + "def f(x):\n"
        "    if not isinstance(x, User):\n"
        "        return\n"
        "    x = make()\n"
        "    x.save()\n"
        "    y = x\n"
        "    if isinstance(y, Client):\n"
        "        y = make()\n"
        "        y.send()\n",
    )
    assert _owner_of(tree, "app/run#f", "save") == [None]
    assert _owner_of(tree, "app/run#f", "send") == [None]


def test_and_narrows_each_name_it_tests(tmp_path: Path):
    """`isinstance(a, User) and isinstance(b, Client)` narrows both in the body."""
    tree = _scan(
        tmp_path,
        _MODELS + "def f(a, b):\n"
        "    if isinstance(a, User) and isinstance(b, Client):\n"
        "        a.save()\n"
        "        b.send()\n",
    )
    assert _owner_of(tree, "app/run#f", "save") == [USER]
    assert _owner_of(tree, "app/run#f", "send") == [CLIENT]


# -- a generic class's written parents (step 6) --------------------------------------------


def test_a_class_writes_its_generic_parents_and_its_parameters(tmp_path: Path):
    """`class Repo(Base[User], Mixin[User, int])` keeps each parent's type arguments (D00 §5a
    `supertype`, `generic_interfaces`); `class Base(Generic[T])` its parameter `T`."""
    from sextant.domain.facts import SymbolFact

    tree = _scan(
        tmp_path,
        _MODELS + "from typing import Generic, TypeVar\n"
        "T = TypeVar('T')\n"
        "K = TypeVar('K')\n"
        "class Base(Generic[T]):\n    pass\n"
        "class Mixin(Generic[T, K]):\n    pass\n"
        "class Plain:\n    pass\n"
        "class Repo(Base[User], Plain, Mixin[User, int]):\n    pass\n",
    )
    classes = {
        fact.symbol.split(" ")[-1]: fact
        for _, _, facts in tree
        for fact in facts
        if isinstance(fact, SymbolFact) and fact.construct_kind == "class"
    }
    base, repo = classes["app/run/Base#"], classes["app/run/Repo#"]
    assert [p.name for p in base.type_parameters] == ["T"]
    assert repo.supertype is not None
    assert (repo.supertype.symbol, [a.symbol for a in repo.supertype.arguments]) == (
        "app/run/Base#",
        [USER],
    )
    assert [(g.symbol, [a.symbol for a in g.arguments]) for g in repo.generic_interfaces] == [
        ("app/run/Mixin#", [USER, "builtins/int#"])
    ]


def test_a_bare_qualifier_gives_no_type_and_a_wrapped_one_its_argument(tmp_path: Path):
    """`limit: Final = 3` says how the name is bound, not its type: no owner and no field type
    naming `typing/Final#`; `client: Final[Client]` and `ClassVar[Client]` are `Client`."""
    from sextant.domain.facts import SymbolFact

    tree = _scan(
        tmp_path,
        "from typing import ClassVar, Final\n"
        "class Client:\n    def send(self):\n        return 1\n"
        "class Box:\n"
        "    limit: Final = 3\n"
        "    client: Final[Client]\n"
        "    shared: ClassVar[Client]\n"
        "def f(b: Box):\n"
        "    b.limit.bit_length()\n"
        "    b.client.send()\n"
        "    b.shared.send()\n",
    )
    fields = {
        fact.symbol.split(" ")[-1]: fact.signature.returns.symbol
        for _, _, facts in tree
        for fact in facts
        if isinstance(fact, SymbolFact) and fact.construct_kind == "field" and fact.signature
        if fact.signature.returns is not None
    }
    assert fields["app/run/Box#limit."] != "typing/Final#"
    assert _owner_of(tree, "app/run#f", "bit_length") == [None]
    assert _owner_of(tree, "app/run#f", "send") == ["app/run/Client#", "app/run/Client#"]


def test_a_return_written_self_is_kept_as_written(tmp_path: Path):
    """`def make(cls) -> Self` writes `Self` as its return (D00 §5a), not the defining class."""
    from sextant.domain.facts import SymbolFact

    tree = _scan(
        tmp_path,
        "from typing import Self\nclass Repo:\n"
        "    @classmethod\n    def make(cls) -> Self:\n        return cls()\n",
    )
    (make,) = [
        fact
        for _, _, facts in tree
        for fact in facts
        if isinstance(fact, SymbolFact) and "#make(" in fact.symbol
    ]
    assert make.signature is not None and make.signature.returns is not None
    assert make.signature.returns.symbol == "Self"


# -- the headers of the files a file imports (round 1, item 2) ---------------------------


def _scan_files(tmp_path: Path, files: dict[str, str]):
    from sextant.application.ports.scanner import ScanRequest
    from sextant.domain.factfile import read_fact_tree
    from sextant.ingress.extract.python.scanner import PythonScanner

    root = tmp_path / "src"
    for name, text in files.items():
        path = root / "app" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    out = tmp_path / "facts"
    PythonScanner().scan(
        ScanRequest(
            module_id="shop", coordinates="shop", version="1.0.0", classes_dir=root, out_dir=out
        )
    )
    return read_fact_tree(out)


_OTHER = (
    "from typing import Iterator\n"
    "class Client:\n    def send(self):\n        return 1\n"
    "class User:\n    def save(self):\n        return 1\n"
    "def rows() -> Iterator[dict[str, int]]:\n    return fetch()\n"
    "class Svc:\n    client: Client\n    users: list[User]\n"
    "class Users(list[User]):\n    pass\n"
)


def test_another_files_declared_return_types_what_is_read_off_its_result(tmp_path: Path):
    """`rows() -> Iterator[dict[str, int]]` in `a.py`: in `b.py`, each row is a `dict`."""
    tree = _scan_files(
        tmp_path,
        {
            "a.py": _OTHER,
            "b.py": "from app.a import rows\ndef f():\n    for r in rows():\n        r.get('x')\n",
        },
    )
    assert _owner_of(tree, "app/b#f", "get") == [DICT]
    assert _owner_of(tree, "app/b#f", "__iter__") == [None]


def test_another_files_class_body_types_an_attribute_read_on_a_value(tmp_path: Path):
    """`s.client` with `s: Svc` from `a.py` is the `Client` its body declares; an element of
    `s.users` a `User`; and a library method inherited by a class of `a.py` is read there."""
    tree = _scan_files(
        tmp_path,
        {
            "a.py": _OTHER,
            "b.py": "from app.a import Svc, Users\n"
            "def f(s: Svc, u: Users):\n"
            "    s.client.send()\n"
            "    for x in s.users:\n        x.save()\n"
            "    u.pop().save()\n",
        },
    )
    assert _owner_of(tree, "app/b#f", "send") == ["app/a/Client#"]
    assert _owner_of(tree, "app/b#f", "save") == ["app/a/User#", "app/a/User#"]


def test_a_class_re_exported_by_a_package_is_read_from_where_it_is_defined(tmp_path: Path):
    """`from app.pkg import Svc`, where `app/pkg/__init__.py` re-exports it from `.svc`: the
    header of the file that defines it answers."""
    tree = _scan_files(
        tmp_path,
        {
            "a.py": _OTHER,
            "pkg/__init__.py": "from .svc import Svc\n",
            "pkg/svc.py": "from app.a import Client\nclass Svc:\n    client: Client\n",
            "b.py": "from app.pkg import Svc\ndef f(s: Svc):\n    s.client.send()\n",
        },
    )
    assert _owner_of(tree, "app/b#f", "send") == ["app/a/Client#"]


def test_an_attribute_whose_declared_class_is_a_descriptor_is_what_its_get_gives(
    tmp_path: Path,
):
    """`price: Typed[Client]` where `Typed` defines `__get__`: reading `obj.price` runs it, so
    the attribute is never a `Typed` (a library descriptor gives what its `__get__` is written
    to return; this one's is a body of the module, not read here); a class whose methods are
    not read may be a descriptor, so its declaration gives nothing."""
    tree = _scan(
        tmp_path,
        "from typing import Generic, TypeVar, overload\n"
        "T = TypeVar('T')\n"
        "class Client:\n    def send(self):\n        return 1\n"
        "class Typed(Generic[T]):\n"
        "    def __get__(self, instance: object, owner: object) -> T: ...\n"
        "    def send(self):\n        return 2\n"
        "class Box:\n    price: Typed[Client]\n" + _MODELS + "class Other:\n    user: User\n"
        "def f(b: Box, o: Other):\n    b.price.send()\n    o.user.save()\n",
    )
    assert _owner_of(tree, "app/run#f", "send") == [None]
    assert _owner_of(tree, "app/run#f", "save") == [None]


def test_another_files_alias_of_a_type_or_a_value_names_no_class(tmp_path: Path):
    """`SaveFixture = Callable[...]` in `a.py` is an alias its own scope reads: written as a
    type in `b.py` it names no class (never the path `app/a/SaveFixture#`). A `NewType` of a
    class is that class, whose methods its values have."""
    tree = _scan_files(
        tmp_path,
        {
            "a.py": _OTHER
            + "from typing import Callable, NewType\n"
            + "SaveFixture = Callable[[int], None]\n"
            + "ClientId = NewType('ClientId', Client)\n",
            "b.py": "from app.a import SaveFixture, ClientId\n"
            "def f(save: SaveFixture, c: ClientId):\n    save(1)\n    c.send()\n",
        },
    )
    assert _owner_of(tree, "app/b#f", "__call__") == [None]
    assert _owner_of(tree, "app/b#f", "send") == ["app/a/Client#"]


def test_calling_a_newtype_hands_back_its_argument(tmp_path: Path):
    """`ClientId(c)`, `ClientId = NewType("ClientId", Client)`, is no construction: at run time
    it hands `c` back, so no call is written and the value is `c` (round 2, item 3)."""
    tree = _scan_files(
        tmp_path,
        {
            "a.py": _OTHER + "from typing import NewType\nClientId = NewType('ClientId', Client)\n",
            "b.py": "from app.a import ClientId, Client\n"
            "def f(c: Client):\n    ClientId(c).send()\n",
        },
    )
    sites = _sites(tree, "app/b#f")
    # The receiver is the parameter `c` itself, which the resolver follows.
    assert [(s.target.name, s.receiver_parameter) for s in sites] == [("send", 0)]


def test_a_newtype_of_a_newtype_is_still_the_class_it_wraps(tmp_path: Path):
    """polar's `AsyncReadSession = NewType(..., _AsyncSession)` then `AsyncSession =
    NewType(..., AsyncReadSession)`: a parameter written `AsyncSession` holds the class."""
    tree = _scan_files(
        tmp_path,
        {
            "a.py": _OTHER + "from typing import NewType\n"
            "ReadClient = NewType('ReadClient', Client)\n"
            "WriteClient = NewType('WriteClient', ReadClient)\n",
            "b.py": "from app.a import WriteClient\ndef f(c: WriteClient):\n    c.send()\n",
        },
    )
    assert _owner_of(tree, "app/b#f", "send") == ["app/a/Client#"]
