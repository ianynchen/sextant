"""`PythonScanner` part 3 (spec 2026-11-06 §3a, D00 §5 `call_site` rule 9): every call's
place in its body's control flow — `dominator`, `on_every_exit`, `post_dominator`,
`reaches_return` and `loop_group` — with the meanings the JVM extractor gives them, and a
`merge` where a name's value joins from two paths. Every expression may raise, so a call in
a `try` body dominates nothing in its handler. Every tree is built in `tmp_path`; nothing is
imported or run."""

from pathlib import Path

from sextant.application.ports.scanner import ScanRequest
from sextant.domain.factfile import read_fact_tree
from sextant.domain.facts import CallArgument, CallSiteFact
from sextant.domain.symbols import PY_SIGNATURE, bare_descriptor, disambiguator_of
from sextant.ingress.extract.python.scanner import PythonScanner

DIS = disambiguator_of(PY_SIGNATURE)


# The functions the bodies call, so each call names its function (`app/lib#a`).
_IMPORTS = "from app.lib import a, b, c, d, e, g, h, k, items, more, use, setup, make, run\n"


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
        "items": (None, True, "b", True, None),
        "a": ("items", False, "b", True, "a"),
        "b": ("items", True, "more", True, None),
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
        "a": (None, False, "e", True, "a"),
        "b": ("a", False, "e", True, "a"),
        "c": ("b", False, "e", True, "a"),
        # A `break` skips the `else`.
        "d": (None, False, "e", True, None),
        "e": (None, True, None, True, None),
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
        "stream": ("a", True, "h", True, None),
        "g": ("stream", False, "h", True, "g"),
        "h": ("stream", True, None, True, None),
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
        "items": ("a", True, "d", True, None),
        "c": ("items", False, "d", True, "c"),
        "b": ("c", False, "d", True, "c"),
        "d": ("items", True, None, True, None),
    }


def test_a_generator_expression_may_run_after_the_function_returned(tmp_path: Path):
    facts = _scan(
        tmp_path,
        "def f():\n    g = (b(x) for x in items())\n    d()\n    return g\n",
    )

    assert _flow(_sites(facts)) == {
        "items": (None, True, "d", True, None),
        # It runs when it is consumed, possibly after `f` returned: nothing is known to
        # follow it.
        "b": ("items", False, None, False, "b"),
        "d": ("items", True, None, True, None),
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
