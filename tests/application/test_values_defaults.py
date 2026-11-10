"""A call that fills no argument for a parameter passes the parameter's default (plan
2026-11-08-python-fastapi-inbound Task 4, N1; rulings R15, R16).

`_Walk._parameter` reads the parameter's `default` (D00 §5a) on that caller's path, in the
body that runs the `def`: the owner's `<clinit>` for a module function or a method, the
enclosing function for a nested `def` or a `lambda` (read from the naming rule, R15). A call
whose `*` or `**` argument could fill the slot is not one that leaves it to its default, so
that path stays `not_readable`. `= None` is `absent` (R16). No JVM parameter has a default."""

from pathlib import Path

from test_receiver_binding import _resolved, _site

from sextant.application.resolve.values import (
    ABSENT,
    LITERAL,
    NOT_READABLE,
    UNRESOLVED,
    resolve_site,
    value_index,
)
from sextant.storage.duckdb.workspace import DuckDbWorkspace

_FETCH = (
    "import requests\n"
    "def fetch(url, timeout=10, *, retries=3):\n"
    "    return requests.get(url, timeout=timeout, retries=retries)\n"
)


def _slot(workspace: DuckDbWorkspace, method: str, name: str, slot: int) -> list[tuple]:
    """`(kind, value, reason)` of one slot of the one call `name` in `method`, per path."""
    caller, ordinal = _site(workspace, method, name)
    bindings = resolve_site(
        workspace, {"caller": caller, "ordinal": ordinal}, index=value_index(workspace)
    )
    return [
        (answer.kind, answer.value, answer.reason)
        for answer in (binding.slots[slot] for binding in bindings)
    ]


def test_a_call_that_omits_an_argument_passes_the_default(tmp_path: Path):
    """`fetch(url)` with `timeout=10`: on that caller's path `timeout` is `10`, resolved."""
    workspace = _resolved(
        tmp_path,
        {"http.py": _FETCH, "b.py": "from app.http import fetch\ndef f():\n    fetch('/a')\n"},
    )
    get = "app/http#fetch(sig_dd69782a)."
    assert _slot(workspace, get, "get", 1) == [(LITERAL, 10, None)]
    assert _slot(workspace, get, "get", 0) == [(LITERAL, "/a", None)]
    workspace.close()


def test_a_filled_argument_is_the_callers_value_not_the_default(tmp_path: Path):
    """The near-miss: `fetch('/a', 3)` and `fetch('/b', timeout=4)` fill `timeout`; each path
    is its own caller's value, and the default joins neither."""
    workspace = _resolved(
        tmp_path,
        {
            "http.py": _FETCH,
            "b.py": "from app.http import fetch\n"
            "def f():\n    fetch('/a', 3)\n"
            "def g():\n    fetch('/b', timeout=4)\n",
        },
    )
    assert sorted(_slot(workspace, "app/http#fetch(sig_dd69782a).", "get", 1)) == [
        (LITERAL, 3, None),
        (LITERAL, 4, None),
    ]
    workspace.close()


def test_a_keyword_only_parameter_left_unfilled_passes_its_default(tmp_path: Path):
    """`retries` is keyword-only: a call naming no `retries` passes `3`, and a `*args` call,
    which can fill no keyword-only parameter, passes it too."""
    workspace = _resolved(
        tmp_path,
        {
            "http.py": _FETCH,
            "b.py": "from app.http import fetch\n"
            "def f():\n    fetch('/a')\n"
            "def g(items):\n    fetch(*items)\n",
        },
    )
    assert _slot(workspace, "app/http#fetch(sig_dd69782a).", "get", 2) == [
        (LITERAL, 3, None),
        (LITERAL, 3, None),
    ]
    workspace.close()


def test_an_unpacked_argument_that_could_fill_the_slot_is_not_the_default(tmp_path: Path):
    """`fetch('/a', *rest)` may fill `timeout` from `rest`, and `fetch('/a', **options)` may
    fill `timeout` or `retries`: neither path is the default, and each stays `not_readable`."""
    workspace = _resolved(
        tmp_path,
        {
            "http.py": _FETCH,
            "b.py": "from app.http import fetch\n"
            "def f(rest):\n    fetch('/a', *rest)\n"
            "def g(options):\n    fetch('/a', **options)\n",
        },
    )
    get = "app/http#fetch(sig_dd69782a)."
    assert _slot(workspace, get, "get", 1) == [
        (UNRESOLVED, None, NOT_READABLE),
        (UNRESOLVED, None, NOT_READABLE),
    ]
    assert sorted(map(str, _slot(workspace, get, "get", 2))) == sorted(
        map(str, [(LITERAL, 3, None), (UNRESOLVED, None, NOT_READABLE)])
    )
    workspace.close()


def test_a_none_default_is_absent(tmp_path: Path):
    """`= None` states there is no value (ruling R16): `absent`, not a reason."""
    workspace = _resolved(
        tmp_path,
        {
            "http.py": "import requests\n"
            "def fetch(url, timeout=None):\n    return requests.get(url, timeout=timeout)\n",
            "b.py": "from app.http import fetch\ndef f():\n    fetch('/a')\n",
        },
    )
    assert _slot(workspace, "app/http#fetch(sig_dd69782a).", "get", 1) == [(ABSENT, None, None)]
    workspace.close()


def test_a_module_function_default_is_read_in_the_module_body(tmp_path: Path):
    """R15, form 1: `def fetch(url, timeout=pick())` evaluates `pick()` in the module's
    `<clinit>`, so the default is what `pick` returns."""
    workspace = _resolved(
        tmp_path,
        {
            "http.py": "import requests\n"
            "def pick():\n    return 'slow'\n"
            "def fetch(url, timeout=pick()):\n    return requests.get(url, timeout=timeout)\n",
            "b.py": "from app.http import fetch\ndef f():\n    fetch('/a')\n",
        },
    )
    assert _slot(workspace, "app/http#fetch(sig_dd69782a).", "get", 1) == [(LITERAL, "slow", None)]
    workspace.close()


def test_a_method_default_is_read_in_the_class_body(tmp_path: Path):
    """R15, form 2: a method's default runs in its class body (`C`'s `<clinit>`), whose call
    ordinals are its own: the module body's call at the same ordinal is another value."""
    workspace = _resolved(
        tmp_path,
        {
            "http.py": "import requests\n"
            "def module_pick():\n    return 'module'\n"
            "def class_pick():\n    return 'class'\n"
            "LEVEL = module_pick()\n"
            "class C:\n"
            "    def fetch(self, url, timeout=class_pick()):\n"
            "        return requests.get(url, timeout=timeout)\n"
            "def f():\n    C().fetch('/a')\n",
        },
    )
    assert _slot(workspace, "app/http/C#fetch(sig_dd69782a).", "get", 1) == [
        (LITERAL, "class", None)
    ]
    workspace.close()


def test_a_nested_def_and_a_lambda_default_are_read_in_the_enclosing_function(tmp_path: Path):
    """R15, form 3: `inner`'s default and the lambda's run in `outer`'s body, and a nested
    `def` inside `__init__` (`new$inner`) runs in the constructor."""
    workspace = _resolved(
        tmp_path,
        {
            "http.py": "import requests\n"
            "def module_pick():\n    return 'module'\n"
            "def outer_pick():\n    return 'outer'\n"
            "def init_pick():\n    return 'init'\n"
            "LEVEL = module_pick()\n"
            "def outer():\n"
            "    def inner(timeout=outer_pick()):\n"
            "        return requests.get('/i', timeout=timeout)\n"
            "    inner()\n"
            "    run = lambda timeout=outer_pick(): requests.post('/l', timeout=timeout)\n"
            "    run()\n"
            "class C:\n"
            "    def __init__(self):\n"
            "        def inner(timeout=init_pick()):\n"
            "            return requests.put('/c', timeout=timeout)\n"
            "        inner()\n",
        },
    )
    assert _slot(workspace, "app/http#outer$inner(sig_dd69782a).", "get", 1) == [
        (LITERAL, "outer", None)
    ]
    assert _slot(workspace, "app/http#lambda$outer$0(sig_dd69782a).", "post", 1) == [
        (LITERAL, "outer", None)
    ]
    assert _slot(workspace, "app/http/C#new$inner(sig_dd69782a).", "put", 1) == [
        (LITERAL, "init", None)
    ]
    workspace.close()
