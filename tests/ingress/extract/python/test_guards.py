"""`PythonScanner`: the tests a call runs under within its own body (D00 §5 `call_site.guards`,
OI-368, plan 2026-11-08-python-fastapi-inbound Task 10b, approved by the user 2026-11-09).

Each guard is an `if` test (or a conditional expression's) that the scanner does not decide: its
text, which arm the call is in (`holds`), and the names it reads. A call after an arm that always
returns runs only where that arm's test went the other way; an arm that always raises guards
nothing, since its test only decides whether the program goes on. A test the
language decides (a constant, `typing.TYPE_CHECKING`) writes nothing. Every tree is built in
`tmp_path`; nothing is imported or run."""

from pathlib import Path

from test_flow import _scan, _sites

from sextant.domain.facts import CallSiteFact, FieldWriteFact, MethodReturnFact


def _guards(sites) -> dict[str, list[tuple[str, bool, list[str]]] | None]:
    return {
        name: None
        if site.guards is None
        else [(guard.test, guard.holds, list(guard.reads)) for guard in site.guards]
        for name, site in sites.items()
    }


def test_each_arm_and_an_early_return_guard_the_calls_under_them(tmp_path: Path):
    facts = _scan(
        tmp_path,
        "def f(flag, s):\n"
        "    a()\n"
        "    if s.ENV != 'prod':\n"
        "        b()\n"
        "    else:\n"
        "        c()\n"
        "    if flag:\n"
        "        return\n"
        "    d()\n"
        "    e() if s.X else g()\n",
    )

    enter = ("s.ENV != 'prod'", True, ["s.ENV"])
    stay = ("flag", False, ["flag"])
    # `s.ENV` and `s.X` read attributes of the parameter `s`: each read is an ownerless call
    # on it (fact schema 21), named as the attribute; the calls this test is about are the rest.
    reads = [
        f.target.name
        for f in facts
        if isinstance(f, CallSiteFact) and f.target.name in ("ENV", "X")
    ]
    assert sorted(reads) == ["ENV", "X"]
    facts = [
        f for f in facts if not (isinstance(f, CallSiteFact) and f.target.name in ("ENV", "X"))
    ]
    assert _guards(_sites(facts)) == {
        "a": None,
        "b": [enter],
        "c": [("s.ENV != 'prod'", False, ["s.ENV"])],
        "d": [stay],
        "e": [stay, ("s.X", True, ["s.X"])],
        "g": [stay, ("s.X", False, ["s.X"])],
    }


def test_an_elif_is_under_the_test_before_it_too(tmp_path: Path):
    facts = _scan(
        tmp_path,
        "def f(x, y):\n"
        "    if x:\n"
        "        a()\n"
        "    elif y and not x:\n"
        "        b()\n"
        "    if run(x):\n"
        "        return\n"
        "    c()\n",
    )

    sites = _sites(facts)
    assert _guards({name: sites[name] for name in ("a", "b", "c")}) == {
        "a": [("x", True, ["x"])],
        "b": [("x", False, ["x"]), ("y and (not x)", True, ["y", "x"])],
        "c": [("run(x)", False, ["run", "x"])],
    }


def test_a_test_whose_arm_raises_guards_nothing(tmp_path: Path):
    """`if bad: raise ...` decides only whether the program goes on (polar's
    `add_versioned_routers` validates its default version so): the code after it, and the arm
    beside a raising one, run wherever the program runs, so neither carries the test."""
    facts = _scan(
        tmp_path,
        "def f(x, y):\n"
        "    if run(x):\n"
        "        raise ValueError\n"
        "    a()\n"
        "    if y:\n"
        "        b()\n"
        "    else:\n"
        "        raise KeyError()\n",
    )

    sites = _sites(facts)
    assert _guards({name: sites[name] for name in ("a", "b")}) == {"a": None, "b": None}


def test_a_test_the_language_decides_writes_nothing(tmp_path: Path):
    facts = _scan(
        tmp_path,
        "import typing\n"
        "def f():\n"
        "    if typing.TYPE_CHECKING:\n"
        "        a()\n"
        "    else:\n"
        "        b()\n"
        "    if True:\n"
        "        c()\n"
        "    if not False:\n"
        "        d()\n",
    )

    assert _guards(_sites(facts)) == {"a": None, "b": None, "c": None, "d": None}


def test_a_nested_function_starts_with_no_guard(tmp_path: Path):
    """A function defined under a test runs when it is called: its calls carry their own body's
    tests only, the caller's being the resolver's to follow."""
    facts = _scan(
        tmp_path,
        "def f(flag):\n    if flag:\n        def inner():\n            a()\n        inner()\n",
    )

    inner = [
        site
        for site in facts
        if getattr(site, "kind", None) == "call_site" and site.target.name == "a"
    ]
    assert [site.guards for site in inner] == [None]
    assert list(_guards(_sites(facts)).values()) == [[("flag", True, ["flag"])]]


def test_a_narrowing_test_guards_both_arms(tmp_path: Path):
    """An `isinstance` test narrows a local in each arm, and each arm's calls carry the test."""
    facts = _scan(
        tmp_path,
        "class A:\n"
        "    pass\n"
        "def f(x):\n"
        "    if isinstance(x, A):\n"
        "        a(x)\n"
        "    else:\n"
        "        b(x)\n",
    )

    sites = _sites(facts)
    assert _guards({name: sites[name] for name in ("a", "b")}) == {
        "a": [("isinstance(x, A)", True, ["isinstance", "x", "A"])],
        "b": [("isinstance(x, A)", False, ["isinstance", "x", "A"])],
    }


def test_a_raise_inside_with_or_try_finally_always_raises(tmp_path: Path):
    """Review Minor 8: an arm whose raise sits in a `with` or a `try ... finally` always raises,
    as `_falls_through` reads it, so it guards nothing either."""
    facts = _scan(
        tmp_path,
        "def f(x, y):\n"
        "    if not x:\n"
        "        with g():\n"
        "            raise ValueError\n"
        "    a()\n"
        "    if not y:\n"
        "        try:\n"
        "            raise KeyError\n"
        "        finally:\n"
        "            h()\n"
        "    b()\n",
    )

    sites = _sites(facts)
    assert _guards({name: sites[name] for name in ("a", "b")}) == {"a": None, "b": None}


def test_the_main_block_test_guards_nothing(tmp_path: Path):
    """Ruled 2026-11-09 (review Major 2): `__name__ == "__main__"` is an entry point."""
    facts = _scan(
        tmp_path,
        "def f():\n"
        "    if __name__ == '__main__':\n"
        "        a()\n"
        "    if '__main__' != __name__:\n"
        "        return\n"
        "    b()\n",
    )

    sites = _sites(facts)
    assert _guards({name: sites[name] for name in ("a", "b")}) == {"a": None, "b": None}


def test_a_field_write_carries_the_tests_it_runs_under(tmp_path: Path):
    """D00 §5 `field_write.guards` (fact schema 23, ruling R1 of 2026-11-25, OI-508, OI-509):
    a write to a name carries the tests it runs under within its own body, outermost first, by
    the rules of a call's. A write under none, and one under a test the language decides,
    carries none."""
    facts = _scan(
        tmp_path,
        "import os\n"
        "from typing import TYPE_CHECKING\n"
        "A = ['a']\n"
        "if os.environ:\n"
        "    A += ['b']\n"
        "    if os.sep:\n"
        "        B = 1\n"
        "else:\n"
        "    C = 2\n"
        "if not TYPE_CHECKING:\n"
        "    D = 3\n"
        "def f(flag):\n"
        "    global E\n"
        "    if flag:\n"
        "        return\n"
        "    E = 4\n"
        "class K:\n"
        "    def __init__(self, flag):\n"
        "        if flag:\n"
        "            self.x = 5\n",
    )

    written = [
        (
            fact.field.rsplit("#", 1)[1],
            None
            if fact.guards is None
            else [(guard.test, guard.holds, list(guard.reads)) for guard in fact.guards],
        )
        for fact in facts
        if isinstance(fact, FieldWriteFact)
    ]
    outer = ("os.environ", True, ["os.environ"])
    assert written == [
        ("A.", None),
        ("A.", [outer]),
        ("B.", [outer, ("os.sep", True, ["os.sep"])]),
        ("C.", [("os.environ", False, ["os.environ"])]),
        ("D.", None),
        ("E.", [("flag", False, ["flag"])]),
        ("x.", [("flag", True, ["flag"])]),
    ]


def test_a_return_carries_the_tests_it_runs_under(tmp_path: Path):
    """D00 §5 `method_return.guards` (fact schema 24, ruling R5 of 2026-11-25, OI-532): a
    `return` carries the tests it runs under within its own body, by the rules of a call's:
    the return after an arm that always returns is under that arm's test, the other way."""
    facts = _scan(
        tmp_path,
        "def d(function=None, x=1):\n"
        "    if function:\n"
        "        return wrap(function)\n"
        "    return wrap\n"
        "def plain():\n"
        "    return 1\n",
    )

    returned = {
        (fact.method.rsplit("#", 1)[1].split("(")[0], fact.ordinal): None
        if fact.guards is None
        else [(guard.test, guard.holds) for guard in fact.guards]
        for fact in facts
        if isinstance(fact, MethodReturnFact)
    }
    assert returned == {
        ("d", 0): [("function", True)],
        ("d", 1): [("function", False)],
        ("plain", 0): None,
    }


def test_a_test_of_one_value_states_the_value_and_when_it_is_true(tmp_path: Path):
    """D00 §5 `guards[].value` and `when` (fact schema 24, ruling R2 of 2026-11-25): a test
    that is one value (`x`), its negation (`not x`), or its comparison with `None` by `is`
    states the value it reads, in the argument grammar, and what of it makes the test true.
    Every other form states neither."""
    facts = _scan(
        tmp_path,
        "FLAG = True\n"
        "def f(p, q):\n"
        "    if p:\n"
        "        a()\n"
        "    if not q:\n"
        "        b()\n"
        "    if p is None:\n"
        "        c()\n"
        "    if q is not None:\n"
        "        d()\n"
        "    if FLAG:\n"
        "        e()\n"
        "    if p == 1:\n"
        "        g()\n"
        "    if p and q:\n"
        "        h()\n"
        "    if p in (1, 2):\n"
        "        k()\n",
    )

    stated = {
        name: [
            (guard.when, None if guard.value is None else (guard.value.kind, guard.value.value))
            for guard in site.guards
        ]
        for name, site in _sites(facts).items()
    }
    assert stated["a"] == [("true", ("parameter", 0))]
    assert stated["b"] == [("false", ("parameter", 1))]
    assert stated["c"] == [("null", ("parameter", 0))]
    assert stated["d"] == [("not_null", ("parameter", 1))]
    assert stated["e"] == [("true", ("field", None))]
    assert stated["g"] == stated["h"] == stated["k"] == [(None, None)]
