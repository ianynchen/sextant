"""`PythonScanner`: the type-variable rule and iteration (OI-324, spec 2026-11-06 §3a "Types
written in the code").

A library method whose written return holds a type variable gives the type the receiver's
type arguments, the class's own written bases or the call's arguments fill it with, as the
typing specification defines it; where nothing fills it the result stays untyped. `for x in
xs` is the iteration it is: `xs.__iter__()`, then `__next__()` on the iterator, each a call
site, as javac writes `iterator()` and `next()` for a for-each loop. `xs[i]` is
`xs.__getitem__(i)`. Every tree is built in `tmp_path`; nothing is imported or run."""

from pathlib import Path

from sextant.application.ports.detector import LibraryRoot
from sextant.application.ports.scanner import ScanRequest
from sextant.domain.factfile import read_fact_tree
from sextant.domain.facts import CallSiteFact
from sextant.domain.symbols import bare_descriptor
from sextant.ingress.extract.python.scanner import PythonScanner

USER = "app/models/User#"
CLIENT = "app/models/Client#"
LIST = "builtins/list#"
DICT = "builtins/dict#"
ITERATOR = "typing/Iterator#"
_MODELS = "from app.models import User, Client\n"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _scan(tmp_path: Path, text: str, libraries: tuple[LibraryRoot, ...] = ()):
    root = tmp_path / "src"
    _write(root / "app" / "run.py", text)
    out = tmp_path / "facts"
    PythonScanner().scan(
        ScanRequest(
            module_id="shop",
            coordinates="shop",
            version="1.0.0",
            classes_dir=root,
            out_dir=out,
            dependency_archives=libraries,
        )
    )
    return read_fact_tree(out)


def _sites(tree, caller: str) -> list[CallSiteFact]:
    return [
        fact
        for _, _, facts in tree
        for fact in facts
        if isinstance(fact, CallSiteFact) and bare_descriptor(fact.caller).startswith(caller)
    ]


def _owners(tree, caller: str) -> list[tuple[str | None, str | None]]:
    return [(site.target.owner, site.target.name) for site in _sites(tree, caller)]


def _owner_of(tree, caller: str, name: str) -> list[str | None]:
    return [site.target.owner for site in _sites(tree, caller) if site.target.name == name]


def test_an_element_of_a_list_takes_the_lists_type_argument(tmp_path: Path):
    """`list[User].__getitem__(0)` is written `-> _T`, and `list[_T]` with `_T` = User gives
    a `User`; `for u in users` calls `__iter__` (`-> Iterator[_T]`) and then `__next__` on the
    iterator, so `u` is a `User` too, and the facts say where it came from."""
    tree = _scan(
        tmp_path,
        _MODELS + "def f(users: list[User]):\n"
        "    users[0].save()\n"
        "    for u in users:\n"
        "        u.save()\n",
    )

    get, save, iterate, step, save_again = _sites(tree, "app/run#f")
    assert (get.target.owner, get.target.name) == (LIST, "__getitem__")
    assert get.receiver_parameter == 0
    assert [a.kind for a in get.arguments] == ["int"]
    assert (save.target.owner, save.receiver) == (USER, get.result)
    assert (iterate.target.owner, iterate.target.name) == (LIST, "__iter__")
    assert (step.target.owner, step.target.name, step.receiver) == (
        ITERATOR,
        "__next__",
        iterate.result,
    )
    assert (save_again.target.owner, save_again.receiver) == (USER, step.result)


def test_a_slice_is_the_lists_own_type(tmp_path: Path):
    """A slice argument chooses the `slice` overload, `-> list[_T]`: a list of users."""
    tree = _scan(
        tmp_path,
        _MODELS + "def f(users: list[User], name: str):\n"
        "    users[1:][0].save()\n"
        "    name[1:].upper()\n",
    )

    assert _owners(tree, "app/run#f") == [
        (LIST, "__getitem__"),
        (LIST, "__getitem__"),
        (USER, "save"),
        ("builtins/str#", "__getitem__"),
        ("builtins/str#", "upper"),
    ]


def test_dict_get_and_items_unpack_by_position(tmp_path: Path):
    """`dict[str, Client].get(k)` is `_VT | None`: a `Client`, as `Optional[Client]` is (None
    has no method). `items()` iterates `tuple[str, Client]`, unpacked by position."""
    tree = _scan(
        tmp_path,
        _MODELS + "def f(clients: dict[str, Client]):\n"
        "    clients.get('a').send()\n"
        "    clients['b'].send()\n"
        "    for name, client in clients.items():\n"
        "        name.upper()\n"
        "        client.send()\n",
    )

    assert _owners(tree, "app/run#f") == [
        (DICT, "get"),
        (CLIENT, "send"),
        (DICT, "__getitem__"),
        (CLIENT, "send"),
        (DICT, "items"),
        ("_collections_abc/dict_items#", "__iter__"),
        (ITERATOR, "__next__"),
        ("builtins/str#", "upper"),
        (CLIENT, "send"),
    ]


def test_a_tuple_of_unknown_arity_is_not_unpacked(tmp_path: Path):
    """`tuple[User, ...]` does not say how many there are: the two names stay untyped, and a
    two-part tuple unpacked into three names is not read either."""
    tree = _scan(
        tmp_path,
        _MODELS + "def f(many: list[tuple[User, ...]], pairs: list[tuple[User, Client]]):\n"
        "    for a, b in many:\n"
        "        a.save()\n"
        "    for c, d, e in pairs:\n"
        "        c.save()\n"
        "    for user, client in pairs:\n"
        "        user.save()\n"
        "        client.send()\n",
    )

    assert _owner_of(tree, "app/run#f", "save") == [None, None, USER]
    assert _owner_of(tree, "app/run#f", "send") == [CLIENT]


def test_comprehensions_and_async_for_iterate_too(tmp_path: Path):
    tree = _scan(
        tmp_path,
        _MODELS + "from collections.abc import AsyncIterator\n"
        "async def f(users: list[User], stream: AsyncIterator[User]):\n"
        "    [u.save() for u in users]\n"
        "    async for v in stream:\n"
        "        v.save()\n",
    )

    assert _owners(tree, "app/run#f") == [
        (LIST, "__iter__"),
        (ITERATOR, "__next__"),
        (USER, "save"),
        ("typing/AsyncIterator#", "__aiter__"),
        ("typing/AsyncIterator#", "__anext__"),
        (USER, "save"),
    ]


def test_a_user_generic_class_fills_the_library_parameter_through_its_bases(tmp_path: Path):
    """`class Bag(list[T], Generic[T])` maps its own `T` onto `list`'s `_T`; `Bag[User]`
    then gives users. A PEP 695 `class Box[T](Sequence[T])` does the same through
    `Sequence`."""
    tree = _scan(
        tmp_path,
        _MODELS + "from collections.abc import Sequence\n"
        "from typing import Generic, TypeVar\n"
        "T = TypeVar('T')\n"
        "class Bag(list[T], Generic[T]):\n"
        "    pass\n"
        "class Box[T](Sequence[T]):\n"
        "    pass\n"
        "def f(bag: Bag[User], box: Box[User]):\n"
        "    bag[0].save()\n"
        "    for u in bag:\n"
        "        u.save()\n"
        "    box[0].save()\n",
    )

    assert _owner_of(tree, "app/run#f", "save") == [USER, USER, USER]


def test_a_subclass_that_fixes_the_parameter_gives_it(tmp_path: Path):
    tree = _scan(
        tmp_path,
        _MODELS + "class Users(list[User]):\n"
        "    pass\n"
        "def f(users: Users):\n"
        "    users.pop().save()\n",
    )

    assert _owners(tree, "app/run#f") == [("app/run/Users#", "pop"), (USER, "save")]


def test_a_method_the_class_writes_itself_is_its_body_not_the_library_signature(
    tmp_path: Path,
):
    """A method the scanned class defines has a body, which the resolver follows: the
    library's signature for the name it overrides is not taken, and the class's own `-> T`
    is not read here either."""
    tree = _scan(
        tmp_path,
        _MODELS + "from typing import Generic, TypeVar\n"
        "T = TypeVar('T')\n"
        "class Users(list[User]):\n"
        "    def pop(self, index=-1):\n"
        "        return None\n"
        "class Repo(Generic[T]):\n"
        "    def get(self) -> T:\n"
        "        raise NotImplementedError\n"
        "def f(users: Users, repo: Repo[User]):\n"
        "    users.pop().save()\n"
        "    repo.get().save()\n",
    )

    assert _owner_of(tree, "app/run#f", "save") == [None, None]


def test_self_is_the_receivers_type(tmp_path: Path):
    """A library method written `-> Self` gives the receiver's own class, a subclass's when
    the receiver is one, never the class that defines the method."""
    site = tmp_path / "site"
    info = site / "builder-1.0.dist-info"
    _write(info / "METADATA", "Metadata-Version: 2.1\nName: builder\nVersion: 1.0\n\n")
    _write(
        site / "builder" / "__init__.py",
        "from typing import Self\nclass Builder:\n    def add(self) -> Self: ...\n",
    )
    _write(site / "builder" / "py.typed", "")
    _write(
        info / "RECORD",
        "builder/__init__.py,,\nbuilder/py.typed,,\n"
        "builder-1.0.dist-info/METADATA,,\nbuilder-1.0.dist-info/RECORD,,\n",
    )
    library = LibraryRoot(coordinate="builder", version="1.0", archive=site)
    tree = _scan(
        tmp_path,
        "from builder import Builder\n"
        "class Mine(Builder):\n"
        "    pass\n"
        "def f(b: Builder, m: Mine):\n"
        "    b.add().add()\n"
        "    m.add().add()\n",
        (library,),
    )

    assert _owners(tree, "app/run#f") == [
        ("builder/Builder#", "add"),
        ("builder/Builder#", "add"),
        ("app/run/Mine#", "add"),
        ("app/run/Mine#", "add"),
    ]


def test_a_union_receiver_gives_a_type_only_where_every_member_gives_it(tmp_path: Path):
    """`list[User] | tuple[User, ...]`: each member's element is a `User`, so the element
    is one. `list[User] | list[Client]` gives two: no one type is written, the owner is left
    to the resolver."""
    tree = _scan(
        tmp_path,
        _MODELS + "def f(same: list[User] | tuple[User, ...], mixed: list[User] | list[Client]):\n"
        "    same[0].save()\n"
        "    mixed[0].save()\n",
    )

    assert _owners(tree, "app/run#f") == [
        (None, "__getitem__"),
        (USER, "save"),
        (None, "__getitem__"),
        (None, "save"),
    ]


def test_a_bare_list_gives_no_element_type(tmp_path: Path):
    """`list` with no type argument says nothing of its elements: nothing is guessed."""
    tree = _scan(
        tmp_path,
        "from typing import Any\n"
        "def f(xs: list, ys: list[Any], zs):\n"
        "    xs[0].save()\n"
        "    for x in xs:\n"
        "        x.save()\n"
        "    ys[0].save()\n"
        "    zs[0].save()\n",
    )

    assert _owner_of(tree, "app/run#f", "save") == [None, None, None, None]


def test_an_undecided_overload_stays_undecided(tmp_path: Path):
    """`users[i]` with `i` of no known type fits both `__getitem__` overloads, which return
    `_T` and `list[_T]`: the closed list stays, and no one type is written."""
    tree = _scan(
        tmp_path,
        _MODELS + "def f(users: list[User], i, j: int):\n"
        "    users[i].save()\n"
        "    users[j].save()\n",
    )

    assert _owner_of(tree, "app/run#f", "save") == [None, USER]


def test_an_argument_fills_a_functions_type_variable(tmp_path: Path):
    """`sorted(Iterable[T]) -> list[T]` takes `T` from its argument, as `Callable`'s result
    does (design 2026-11-06-reading-decorators §3b); `enumerate(users)` is an
    `enumerate[User]`, whose `__next__` gives `tuple[int, User]`."""
    tree = _scan(
        tmp_path,
        _MODELS + "def f(users: list[User]):\n"
        "    sorted(users)[0].save()\n"
        "    for i, u in enumerate(users):\n"
        "        u.save()\n"
        "        i.bit_length()\n",
    )

    assert _owner_of(tree, "app/run#f", "save") == [USER, USER]
    assert _owner_of(tree, "app/run#f", "bit_length") == ["builtins/int#"]


def test_a_heterogeneous_tuple_indexed_by_a_literal_gives_that_position(tmp_path: Path):
    tree = _scan(
        tmp_path,
        _MODELS + "def f(pair: tuple[User, Client], text: str):\n"
        "    pair[1].send()\n"
        "    pair[0].save()\n"
        "    head, _, tail = text.partition(':')\n"
        "    tail.strip()\n",
    )

    assert _owner_of(tree, "app/run#f", "send") == [CLIENT]
    assert _owner_of(tree, "app/run#f", "save") == [USER]
    assert _owner_of(tree, "app/run#f", "strip") == ["builtins/str#"]


def test_subscripting_a_class_is_a_type_not_an_item_read(tmp_path: Path):
    """`list[int]` or `Generic[T]` makes a type (`__class_getitem__`): no `__getitem__` is
    written for it."""
    tree = _scan(
        tmp_path,
        "from typing import Generic, Optional, TypeVar, cast\n"
        "T = TypeVar('T')\n"
        "class Box(Generic[T]):\n"
        "    pass\n"
        "def f(x):\n"
        "    return cast(Optional[list[int]], x)\n",
    )

    assert "__getitem__" not in [name for _, name in _owners(tree, "app/run#")]


def test_a_type_expression_writes_no_subscript_call(tmp_path: Path):
    """Ruling R37: a class base, `cast`'s type and `isinstance`'s class are type
    expressions, so a subscript in them is a type, whatever its name binds to; so is a
    subscript of a class a library defines. A subscript of a value still is `__getitem__`."""
    site = tmp_path / "site"
    info = site / "pages-1.0.dist-info"
    _write(info / "METADATA", "Metadata-Version: 2.1\nName: pages\nVersion: 1.0\n\n")
    _write(
        site / "pages" / "__init__.py",
        "from typing import Generic, TypeVar\nT = TypeVar('T')\nclass Page(Generic[T]): ...\n",
    )
    _write(site / "pages" / "py.typed", "")
    _write(
        info / "RECORD",
        "pages/__init__.py,,\npages/py.typed,,\n"
        "pages-1.0.dist-info/METADATA,,\npages-1.0.dist-info/RECORD,,\n",
    )
    library = LibraryRoot(coordinate="pages", version="1.0", archive=site)
    tree = _scan(
        tmp_path,
        _MODELS + "from typing import cast\n"
        "from app.repos import Repo\n"
        "from pages import Page\n"
        "class Users(Repo[User]):\n"
        "    pass\n"
        "def f(y, rows):\n"
        "    cast(Repo[User], y)\n"
        "    isinstance(y, Repo[User])\n"
        "    wrap(Page[User])\n"
        "    return rows[0]\n",
        (library,),
    )

    getitems = [site for site in _sites(tree, "app/run#") if site.target.name == "__getitem__"]
    assert [bare_descriptor(site.caller) for site in getitems] == ["app/run#f(sig_dd69782a)."]
    assert getitems[0].receiver_parameter == 1


def test_a_type_of_x_value_is_the_class_object(tmp_path: Path):
    """`c: type[Repo]` holds the class: an explicit `c.create()` is a call through the class
    (owner `Repo`, as before), but `c[0]` and `for m in c` are protocol calls Python looks
    up on the class's own type, so they get no `Repo` owner. `Type[...]` and
    `Optional[type[...]]` read the same."""
    tree = _scan(
        tmp_path,
        "from typing import Optional, Type\n"
        "class Repo:\n"
        "    def __getitem__(self, k): ...\n"
        "    @classmethod\n"
        "    def create(cls): ...\n"
        "def f(c: type[Repo], d: Type[Repo], e: Optional[type[Repo]], r: Repo):\n"
        "    c.create()\n"
        "    c[0]\n"
        "    d[0]\n"
        "    e[0]\n"
        "    for m in c:\n"
        "        pass\n"
        "    r[0]\n",
    )

    assert _owners(tree, "app/run#f") == [
        ("app/run/Repo#", "create"),
        (None, "__getitem__"),
        (None, "__getitem__"),
        (None, "__getitem__"),
        (None, "__iter__"),
        (None, "__next__"),
        ("app/run/Repo#", "__getitem__"),
    ]
