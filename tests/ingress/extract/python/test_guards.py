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
