"""`PythonScanner` part 3 (spec 2026-11-06 §3a, D00 §5 `call_site` rule 9): every call's
place in its body's control flow — `dominator`, `on_every_exit`, `post_dominator`,
`reaches_return` and `loop_group` — with the meanings the JVM extractor gives them, and a
`merge` where a name's value joins from two paths. Every expression may raise, so a call in
a `try` body dominates nothing in its handler. Every tree is built in `tmp_path`; nothing is
imported or run."""

from pathlib import Path

from sextant.application.ports.scanner import ScanRequest
from sextant.domain.factfile import read_fact_tree
from sextant.domain.facts import CallArgument, CallSiteFact, MethodReturnFact
from sextant.domain.symbols import PY_SIGNATURE, bare_descriptor, disambiguator_of
from sextant.ingress.extract.python.scanner import PythonScanner

DIS = disambiguator_of(PY_SIGNATURE)


# The functions the bodies call, so each call names its function (`app/lib#a`).
_IMPORTS = "from app.lib import a, b, c, d, e, g, h, k, items, more, use, setup, make, run, old\n"


def _scan(tmp_path: Path, text: str):
    root = tmp_path / "src"
    path = root / "app/m.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_IMPORTS + text, encoding="utf-8")
    out = tmp_path / "facts"
    PythonScanner().scan(
        ScanRequest(module_id="shop", coordinates=".", version=".", classes_dir=root, out_dir=out)
    )
    return [fact for _, _, facts in read_fact_tree(out) for fact in facts]


def _sites(facts, caller: str = "f") -> dict[str, CallSiteFact]:
    """The call sites of `app/m#<caller>`, by called name (each name called once)."""
    sites = [
        f
        for f in facts
        if isinstance(f, CallSiteFact) and bare_descriptor(f.caller) == f"app/m#{caller}({DIS})."
    ]
    named = {site.target.name: site for site in sites}
    assert len(named) == len(sites), [s.target.name for s in sites]
    return named


def _flow(sites: dict[str, CallSiteFact]) -> dict[str, tuple]:
    """Each site's five fields, with the ordinals of `dominator`, `post_dominator` and
    `loop_group` written as the called name they belong to."""
    name_of = {site.ordinal: name for name, site in sites.items()}
    return {
        name: (
            name_of.get(site.dominator) if site.dominator is not None else None,
            site.on_every_exit,
            name_of.get(site.post_dominator) if site.post_dominator is not None else None,
            site.reaches_return,
            name_of.get(site.loop_group) if site.loop_group is not None else None,
        )
        for name, site in sites.items()
    }


# Columns: dominator, on_every_exit, post_dominator, reaches_return, loop_group.


def test_if_elif_else(tmp_path: Path):
    facts = _scan(
        tmp_path,
        "def f(c):\n"
        "    a()\n"
        "    if c:\n"
        "        b()\n"
        "    elif d():\n"
        "        e()\n"
        "    else:\n"
        "        g()\n"
        "    h()\n",
    )

    assert _flow(_sites(facts)) == {
        "a": (None, True, "h", True, None),
        "b": ("a", False, "h", True, None),
        "d": ("a", False, "h", True, None),
        "e": ("d", False, "h", True, None),
        "g": ("d", False, "h", True, None),
        "h": ("a", True, None, True, None),
    }


def test_for_and_while_with_else(tmp_path: Path):
    facts = _scan(
        tmp_path,
        "def f():\n"
        "    for x in items():\n"
        "        a(x)\n"
        "    else:\n"
        "        b()\n"
        "    while more():\n"
        "        c()\n"
        "    else:\n"
        "        d()\n"
        "    e()\n",
    )

    assert _flow(_sites(facts)) == {
        "items": (None, True, "__iter__", True, None),
        # `for` is `__iter__`, then `__next__` at the head of every pass, the loop's test as
        # `more()` is the `while`'s.
        "__iter__": ("items", True, "__next__", True, None),
        "__next__": ("__iter__", True, "b", True, "__next__"),
        "a": ("__next__", False, "__next__", True, "__next__"),
        "b": ("__next__", True, "more", True, None),
        "more": ("b", True, "d", True, "more"),
        "c": ("more", False, "more", True, "more"),
        "d": ("more", True, "e", True, None),
        "e": ("d", True, None, True, None),
    }


def test_a_loop_that_never_ends_reaches_no_return(tmp_path: Path):
    facts = _scan(tmp_path, "def f():\n    a()\n    while True:\n        b()\n")

    assert _flow(_sites(facts)) == {
        "a": (None, False, None, False, None),
        "b": ("a", False, None, False, "b"),
    }


def test_break_and_continue(tmp_path: Path):
    facts = _scan(
        tmp_path,
        "def f(xs):\n"
        "    for x in xs:\n"
        "        if a(x):\n"
        "            continue\n"
        "        if b(x):\n"
        "            break\n"
        "        c(x)\n"
        "    else:\n"
        "        d()\n"
        "    e()\n",
    )

    assert _flow(_sites(facts)) == {
        "__iter__": (None, True, "__next__", True, None),
        "__next__": ("__iter__", True, "e", True, "__next__"),
        "a": ("__next__", False, "e", True, "__next__"),
        "b": ("a", False, "e", True, "__next__"),
        "c": ("b", False, "__next__", True, "__next__"),
        # A `break` skips the `else`.
        "d": ("__next__", False, "e", True, None),
        "e": ("__next__", True, None, True, None),
    }


def test_try_except_else_finally(tmp_path: Path):
    facts = _scan(
        tmp_path,
        "class E(Exception): pass\n"
        "def f():\n"
        "    a()\n"
        "    try:\n"
        "        b()\n"
        "        c()\n"
        "    except E:\n"
        "        d()\n"
        "    else:\n"
        "        g()\n"
        "    finally:\n"
        "        h()\n"
        "    k()\n",
    )

    assert _flow(_sites(facts)) == {
        # The `finally` runs again on the way out of an exception no handler took, and
        # then raises it: that path reaches no return.
        "a": (None, True, "h", False, None),
        # Any expression of a `try` body may raise, so `b` may be skipped by the
        # handler, and nothing in the body dominates `d`.
        "b": ("a", False, "h", False, None),
        "c": ("b", False, "g", False, None),
        "d": ("a", False, "h", True, None),
        "g": ("c", False, "h", True, None),
        "h": ("a", True, "k", False, None),
        "k": ("h", True, None, True, None),
    }


def test_a_handler_that_raises_is_not_a_path_from_a_completed_call(tmp_path: Path):
    # D00 §5: the handler is entered where `a` did NOT complete, as on the JVM.
    facts = _scan(
        tmp_path,
        "class Failed(Exception): pass\n"
        "def f():\n"
        "    try:\n"
        "        x = a()\n"
        "    except Exception:\n"
        "        raise Failed()\n"
        "    b(x)\n",
    )

    flow = _flow(_sites(facts))
    assert flow["a"] == (None, True, "b", True, None)
    assert flow["b"] == ("a", True, None, True, None)
    assert flow["<init>"] == (None, False, None, False, None)


def test_with_may_swallow_what_its_block_raises(tmp_path: Path):
    facts = _scan(
        tmp_path,
        "def f(m):\n    a()\n    with m.open() as x:\n        b(x)\n        c()\n    d()\n",
    )

    assert _flow(_sites(facts)) == {
        # The manager may raise again what the block raised.
        "a": (None, True, "open", False, None),
        "open": ("a", True, "__enter__", False, None),
        "__enter__": ("open", True, "d", False, None),
        # ... or swallow it, so the rest of the block may be skipped and `d` still runs:
        # nothing in the block runs on every path, or dominates `d`.
        "b": ("__enter__", False, "d", False, None),
        "c": ("b", False, "d", True, None),
        "d": ("__enter__", True, None, True, None),
    }


def test_return_and_raise(tmp_path: Path):
    facts = _scan(
        tmp_path,
        "class E(Exception): pass\n"
        "def f(c):\n"
        "    a()\n"
        "    if c:\n"
        "        return b()\n"
        "    if d():\n"
        "        raise E(g())\n"
        "    h()\n",
    )

    assert _flow(_sites(facts)) == {
        "a": (None, True, None, False, None),
        "b": ("a", False, None, True, None),
        "d": ("a", False, "h", False, None),
        "g": ("d", False, None, False, None),
        "<init>": ("g", False, None, False, None),
        "h": ("d", False, None, True, None),
    }


def test_a_function_that_always_raises_has_no_call_on_every_exit(tmp_path: Path):
    facts = _scan(tmp_path, "def f():\n    a()\n    raise ValueError(b())\n")

    flow = _flow(_sites(facts))
    assert flow["a"] == (None, False, None, False, None)
    assert flow["b"] == ("a", False, None, False, None)


def test_a_call_after_a_return_is_in_no_path(tmp_path: Path):
    facts = _scan(tmp_path, "def f():\n    a()\n    return\n    b()\n")

    flow = _flow(_sites(facts))
    assert flow["a"] == (None, True, None, True, None)
    assert flow["b"] == (None, False, None, False, None)


def test_async_and_await(tmp_path: Path):
    facts = _scan(
        tmp_path,
        "class E(Exception): pass\n"
        "async def f(m):\n"
        "    await a()\n"
        "    try:\n"
        "        await b()\n"
        "    except E:\n"
        "        await d()\n"
        "    async for x in m.stream():\n"
        "        await g(x)\n"
        "    await h()\n",
    )

    assert _flow(_sites(facts)) == {
        "a": (None, True, "stream", True, None),
        "b": ("a", False, "stream", True, None),
        "d": ("a", False, "stream", True, None),
        "stream": ("a", True, "__aiter__", True, None),
        "__aiter__": ("stream", True, "__anext__", True, None),
        "__anext__": ("__aiter__", True, "h", True, "__anext__"),
        "g": ("__anext__", False, "__anext__", True, "__anext__"),
        "h": ("__anext__", True, None, True, None),
    }


def test_yield_is_not_an_exit(tmp_path: Path):
    facts = _scan(tmp_path, "def f():\n    a()\n    yield b()\n    c()\n")

    assert _flow(_sites(facts)) == {
        "a": (None, True, "b", True, None),
        "b": ("a", True, "c", True, None),
        "c": ("b", True, None, True, None),
    }


def test_a_comprehension_is_a_loop(tmp_path: Path):
    facts = _scan(
        tmp_path,
        "def f():\n    a()\n    ys = [b(x) for x in items() if c(x)]\n    d(ys)\n",
    )

    assert _flow(_sites(facts)) == {
        "a": (None, True, "items", True, None),
        "items": ("a", True, "__iter__", True, None),
        "__iter__": ("items", True, "__next__", True, None),
        "__next__": ("__iter__", True, "d", True, "__next__"),
        "c": ("__next__", False, "__next__", True, "__next__"),
        "b": ("c", False, "__next__", True, "__next__"),
        "d": ("__next__", True, None, True, None),
    }


def test_a_generator_expression_may_run_after_the_function_returned(tmp_path: Path):
    facts = _scan(
        tmp_path,
        "def f():\n    g = (b(x) for x in items())\n    d()\n    return g\n",
    )

    assert _flow(_sites(facts)) == {
        "items": (None, True, "__iter__", True, None),
        # Its `iter()` runs at once; its `next()` and its element run when it is consumed,
        # possibly after `f` returned: nothing is known to follow them.
        "__iter__": ("items", True, "d", True, None),
        "__next__": ("__iter__", False, None, False, "__next__"),
        "b": ("__next__", False, None, False, "__next__"),
        "d": ("__iter__", True, None, True, None),
    }


def test_match(tmp_path: Path):
    facts = _scan(
        tmp_path,
        "def f(v):\n"
        "    match a(v):\n"
        "        case 1:\n"
        "            b()\n"
        "        case [x] if c(x):\n"
        "            d()\n"
        "        case _:\n"
        "            e()\n"
        "    g()\n",
    )

    assert _flow(_sites(facts)) == {
        "a": (None, True, "g", True, None),
        "c": ("a", False, "g", True, None),
        "b": ("a", False, "g", True, None),
        "d": ("c", False, "g", True, None),
        "e": ("a", False, "g", True, None),
        "g": ("a", True, None, True, None),
    }


def test_short_circuit_and_conditional_expression(tmp_path: Path):
    facts = _scan(
        tmp_path,
        "def f():\n    x = a() or b()\n    y = c() if d() else e()\n    g(x, y)\n",
    )

    assert _flow(_sites(facts)) == {
        "a": (None, True, "d", True, None),
        "b": ("a", False, "d", True, None),
        "d": ("a", True, "g", True, None),
        "c": ("d", False, "g", True, None),
        "e": ("d", False, "g", True, None),
        "g": ("d", True, None, True, None),
    }


def test_an_assert_may_be_skipped_and_may_raise(tmp_path: Path):
    # `python -O` drops every `assert`, so its test is not known to run.
    facts = _scan(tmp_path, "def f():\n    assert a()\n    b()\n")

    assert _flow(_sites(facts)) == {
        "a": (None, False, "b", False, None),
        "b": (None, True, None, True, None),
    }


def test_a_value_set_on_two_branches_is_a_merge(tmp_path: Path):
    facts = _scan(
        tmp_path,
        "def f(c):\n    if c:\n        x = a()\n    else:\n        x = b()\n    use(x)\n",
    )

    sites = _sites(facts)
    assert sites["use"].arguments == [
        CallArgument(
            kind="merge",
            candidates=[
                CallArgument(kind="unresolved", source=sites["a"].result),
                CallArgument(kind="unresolved", source=sites["b"].result),
            ],
        )
    ]


def test_every_body_writes_the_fields(tmp_path: Path):
    facts = _scan(
        tmp_path,
        "import functools\n"
        "setup()\n"
        "class C:\n"
        "    x = make()\n"
        "    @functools.cache\n"
        "    def m(self):\n"
        "        return (lambda: run())()\n",
    )

    sites = [f for f in facts if isinstance(f, CallSiteFact)]
    assert len(sites) == 5
    assert all(s.on_every_exit is not None and s.reaches_return is not None for s in sites)


# -- values where paths join (fix round 1): a value that can arrive is never left out -------


def _s(text: str) -> CallArgument:
    return CallArgument(kind="string", value=text)


def _used(facts) -> CallArgument:
    (site,) = [f for f in facts if isinstance(f, CallSiteFact) and f.target.name == "use"]
    (argument,) = site.arguments
    return argument


def _candidates(argument: CallArgument) -> list[CallArgument]:
    assert argument.kind == "merge", argument
    return argument.candidates or []


def test_a_continue_in_an_inner_loops_else_belongs_to_the_outer_loop(tmp_path: Path):
    facts = _scan(
        tmp_path,
        "def f():\n"
        "    v = 'x'\n"
        "    for i in items():\n"
        "        v = 'y'\n"
        "        for j in more():\n"
        "            if c(j):\n"
        "                break\n"
        "        else:\n"
        "            continue\n"
        "        v = 'z'\n"
        "    use(v)\n",
    )

    used = _used(facts)
    assert used == CallArgument(kind="unresolved") or _s("y") in _candidates(used)


def test_a_break_skips_the_loops_else(tmp_path: Path):
    facts = _scan(
        tmp_path,
        "def f():\n"
        "    v = 'x'\n"
        "    for i in items():\n"
        "        if c(i):\n"
        "            v = 'y'\n"
        "            break\n"
        "    else:\n"
        "        v = 'z'\n"
        "    use(v)\n",
    )

    assert sorted(c.value for c in _candidates(_used(facts))) == ["y", "z"]


def test_a_finally_may_be_entered_before_the_body_assigned(tmp_path: Path):
    facts = _scan(
        tmp_path,
        "def f():\n    conn = None\n    try:\n        conn = make()\n        a(conn)\n"
        "    finally:\n        use(conn)\n",
    )

    used = _used(facts)
    if used != CallArgument(kind="unresolved"):
        made = CallArgument(kind="unresolved", source=_sites(facts)["make"].result)
        assert sorted(map(repr, _candidates(used))) == sorted(
            map(repr, [CallArgument(kind="null"), made])
        )


def test_a_handler_may_be_entered_before_the_body_assigned(tmp_path: Path):
    facts = _scan(
        tmp_path,
        "class E(Exception): pass\n"
        "def f():\n    v = 'x'\n    try:\n        v = 'y'\n        a()\n"
        "    except E:\n        use(v)\n",
    )

    used = _used(facts)
    assert used == CallArgument(kind="unresolved") or sorted(
        c.value for c in _candidates(used)
    ) == ["x", "y"]


def test_a_with_that_swallows_keeps_the_value_from_before_it(tmp_path: Path):
    facts = _scan(
        tmp_path,
        "from contextlib import suppress\n"
        "def f():\n    v = old()\n    with suppress(KeyError):\n        v = make()\n    use(v)\n",
    )

    sites = _sites(facts)
    sources = {c.source for c in _candidates(_used(facts))}
    assert sources == {sites["old"].result, sites["make"].result}


def test_a_name_unbound_before_a_with_has_only_the_values_it_was_given(tmp_path: Path):
    facts = _scan(
        tmp_path,
        "def f(p):\n    with open(p) as fh:\n        data = fh.read()\n    use(data)\n",
    )

    sites = _sites(facts)
    assert _used(facts) == CallArgument(kind="unresolved", source=sites["read"].result)


def test_a_branch_that_continues_does_not_reach_the_join(tmp_path: Path):
    facts = _scan(
        tmp_path,
        "def f():\n"
        "    for i in items():\n"
        "        v = 'x'\n"
        "        if c():\n"
        "            v = 'y'\n"
        "            continue\n"
        "        use(v)\n",
    )

    assert _used(facts) == _s("x")


def test_a_match_whose_last_case_is_irrefutable_has_no_fall_through(tmp_path: Path):
    facts = _scan(
        tmp_path,
        "def f(n):\n    match n:\n        case 1:\n            v = 'a'\n"
        "        case _:\n            v = 'b'\n    use(v)\n",
    )

    assert _candidates(_used(facts)) == [_s("a"), _s("b")]


def test_a_break_in_an_inner_loops_else_ends_an_endless_loop(tmp_path: Path):
    facts = _scan(
        tmp_path,
        "def f():\n    while True:\n        for x in items():\n            a(x)\n"
        "        else:\n            break\n",
    )

    returns = [
        r
        for r in facts
        if isinstance(r, MethodReturnFact) and bare_descriptor(r.method).startswith("app/m#f(")
    ]
    assert [r.value for r in returns] == [CallArgument(kind="null")]
