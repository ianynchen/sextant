"""What a generator yields (plan 2026-11-08-python-fastapi-inbound N10): each `yield` is a
`method_return` marked `yielded`, beside the generator object's own `unresolved` return, which
is what a call of the method hands back. FastAPI hands a yield dependency's first yield to the
parameter it fills (`get_db`), and `contextmanager`'s `with … as v` reads the same fact.

Every tree is built in `tmp_path`; nothing is imported or run."""

from pathlib import Path

from test_calls import _calls, _returns, _scan

from sextant.domain.facts import CallArgument
from sextant.domain.symbols import PY_SIGNATURE, disambiguator_of

DIS = disambiguator_of(PY_SIGNATURE)


def _shape(tree, method: str) -> list[tuple[int, bool, str | None, int | None]]:
    """Each return of `method` as (ordinal, yielded, value kind, value source)."""
    return [
        (
            one.ordinal,
            one.yielded,
            None if one.value is None else one.value.kind,
            None if one.value is None else one.value.source,
        )
        for one in _returns(tree, method)
    ]


def test_each_yield_is_a_yielded_return_before_the_generator_object(tmp_path: Path):
    """`get_db`'s one yield is the session it built; the call's own return stays the
    generator object, `unresolved`, numbered after it."""
    tree = _scan(
        tmp_path,
        {
            "app/deps.py": (
                "class Session:\n"
                "    def close(self) -> None:\n"
                "        pass\n"
                "def get_db():\n"
                "    session = Session()\n"
                "    try:\n"
                "        yield session\n"
                "    finally:\n"
                "        session.close()\n"
            )
        },
    )
    method = f"app/deps#get_db({DIS})."
    (init, _) = _calls(tree, method)
    assert _shape(tree, method) == [
        (0, True, "instance", init.receiver),
        (1, False, "unresolved", None),
    ]


def test_a_bare_yield_yields_none_and_each_branch_yields_its_own(tmp_path: Path):
    """`yield` alone hands out `None`; a yield on each branch is a fact each, in written
    order."""
    tree = _scan(
        tmp_path,
        {
            "app/gen.py": (
                "def pick(flag: bool):\n    if flag:\n        yield 'a'\n    else:\n        yield\n"
            )
        },
    )
    returns = _returns(tree, f"app/gen#pick({DIS}).")
    assert [(one.ordinal, one.yielded, one.value) for one in returns] == [
        (0, True, CallArgument(kind="string", value="a")),
        (1, True, CallArgument(kind="null")),
        (2, False, CallArgument(kind="unresolved")),
    ]


def test_an_async_generator_yields_and_a_return_in_a_generator_is_no_value(tmp_path: Path):
    """An `async def` with a `yield` is a generator too; its `return` ends it and hands
    nothing to the caller, so it writes no return of its own."""
    tree = _scan(
        tmp_path,
        {"app/gen.py": ("async def stream(n: int):\n    if n:\n        return\n    yield n\n")},
    )
    returns = _returns(tree, f"app/gen#stream({DIS}).")
    assert [(one.yielded, one.value) for one in returns] == [
        (True, CallArgument(kind="parameter", value=0)),
        (False, CallArgument(kind="unresolved")),
    ]


def test_a_nested_generator_yields_for_itself_and_yield_from_is_no_value(tmp_path: Path):
    """A function holding a nested generator is no generator: the yield is the nested
    function's. `yield from` hands on another iterator's values, which no fact names."""
    tree = _scan(
        tmp_path,
        {
            "app/gen.py": (
                "def outer():\n"
                "    def inner():\n"
                "        yield 1\n"
                "    return inner\n"
                "def chained(items: list):\n"
                "    yield from items\n"
            )
        },
    )
    outer = _returns(tree, f"app/gen#outer({DIS}).")
    assert [one.yielded for one in outer] == [False]
    inner = [one for one in _returns(tree, f"app/gen#outer$inner({DIS}).")]
    assert [(one.yielded, one.value) for one in inner] == [
        (True, CallArgument(kind="int", value=1)),
        (False, CallArgument(kind="unresolved")),
    ]
    chained = _returns(tree, f"app/gen#chained({DIS}).")
    assert [(one.yielded, one.value) for one in chained] == [
        (False, CallArgument(kind="unresolved"))
    ]
