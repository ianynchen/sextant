"""`PythonScanner` part 2 (spec 2026-11-06 §3a, "Flow inside one function", "Calls whose
owner is not known"): every call with its receiver, result and arguments, every return,
and every field write, written as the facts the JVM extractor writes. Every tree is built
in `tmp_path`; nothing is imported or run."""

from pathlib import Path

from sextant.application.ports.scanner import ScanRequest
from sextant.domain.factfile import read_fact_tree
from sextant.domain.facts import (
    CallArgument,
    CallSiteFact,
    FieldWriteFact,
    MethodReturnFact,
    SymbolFact,
)
from sextant.domain.symbols import PY_SIGNATURE, bare_descriptor, disambiguator_of
from sextant.ingress.extract.python.scanner import PythonScanner

DIS = disambiguator_of(PY_SIGNATURE)


def _scan(tmp_path: Path, files: dict[str, str]):
    root = tmp_path / "src"
    for relative, text in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    out = tmp_path / "facts"
    PythonScanner().scan(
        ScanRequest(module_id="shop", coordinates=".", version=".", classes_dir=root, out_dir=out)
    )
    return read_fact_tree(out)


def _facts(tree, kind):
    return [fact for _, _, facts in tree for fact in facts if isinstance(fact, kind)]


def _calls(tree, caller: str) -> list[CallSiteFact]:
    return [c for c in _facts(tree, CallSiteFact) if bare_descriptor(c.caller) == caller]


def _call(tree, name: str) -> CallSiteFact:
    (found,) = [c for c in _facts(tree, CallSiteFact) if c.target.name == name]
    return found


def _returns(tree, method: str) -> list[MethodReturnFact]:
    return [r for r in _facts(tree, MethodReturnFact) if bare_descriptor(r.method) == method]


# -- the brief's tests -------------------------------------------------------------------


def test_call_on_a_typed_parameter_names_its_owner(tmp_path: Path):
    tree = _scan(
        tmp_path,
        {
            "app/api.py": (
                "from app.svc import OrderService\n"
                "def handle(svc: OrderService):\n"
                "    svc.create('x')\n"
            ),
            "app/svc.py": "class OrderService: pass\n",
        },
    )

    create = _call(tree, "create")
    assert create.target.owner == "app/svc/OrderService#"
    assert create.invoke_kind == "virtual"
    assert create.receiver_parameter == 0
    assert bare_descriptor(create.caller) == f"app/api#handle({DIS})."
    assert create.arguments == [CallArgument(kind="string", value="x")]


def test_call_on_an_unknown_receiver_names_only_the_receiver(tmp_path: Path):
    tree = _scan(
        tmp_path,
        {
            "app/api.py": (
                "import httpx\ndef fetch(url):\n    client = httpx.Client()\n"
                "    return client.get(url)\n"
            )
        },
    )

    built, get = _calls(tree, f"app/api#fetch({DIS}).")
    assert built.target.owner == "httpx#"
    assert built.invoke_kind == "static"
    assert get.target.owner is None
    assert get.target.name == "get"
    assert get.invoke_kind == "virtual"
    # The receiver is the value the client call produced, by id.
    assert get.receiver == built.result
    assert get.arguments == [CallArgument(kind="parameter", value=0)]
    (returned,) = _returns(tree, f"app/api#fetch({DIS}).")
    assert returned.value == CallArgument(kind="unresolved", source=get.result)


def test_fstring_url_is_concat(tmp_path: Path):
    tree = _scan(
        tmp_path,
        {
            "app/api.py": (
                "import requests\n"
                "def fetch(base, order_id):\n"
                "    requests.get(f'{base}/orders/{order_id}')\n"
                "    requests.post(base + '/orders')\n"
            )
        },
    )

    calls = _calls(tree, f"app/api#fetch({DIS}).")
    fstring, get, plus, post = calls
    assert get.arguments == [
        CallArgument(kind="concat", value="{}/orders/{}", source=fstring.result)
    ]
    # The concatenation is its own site: the holes' values are its arguments.
    assert fstring.invoke_kind == "dynamic"
    assert fstring.arguments == [
        CallArgument(kind="parameter", value=0),
        CallArgument(kind="parameter", value=1),
    ]
    assert post.arguments == [CallArgument(kind="concat", value="{}/orders", source=plus.result)]
    assert plus.arguments == [CallArgument(kind="parameter", value=0)]


def test_a_keyword_is_written_as_written_even_where_the_signature_is_known(tmp_path: Path):
    """Ruling R27 (amends R2): the scanner never turns a keyword into a position, so a call
    in the callee's own file is written as one from another file is, and the resolver binds
    both by one rule."""
    tree = _scan(
        tmp_path,
        {
            "app/m.py": (
                "def send(url, body=None, *, timeout=5):\n"
                "    pass\n"
                "def main():\n"
                "    send('/a', timeout=9)\n"
            )
        },
    )

    send = _call(tree, "send")
    assert send.invoke_kind == "static"
    assert send.arguments == [
        CallArgument(kind="string", value="/a"),
        CallArgument(kind="int", value=9, keyword="timeout"),
    ]


def test_implicit_return_none_is_a_method_return(tmp_path: Path):
    tree = _scan(
        tmp_path,
        {"app/m.py": ("def f(x):\n    if x:\n        return 1\ndef g():\n    return 2\n")},
    )

    assert [(r.ordinal, r.value) for r in _returns(tree, f"app/m#f({DIS}).")] == [
        (0, CallArgument(kind="int", value=1)),
        (1, CallArgument(kind="null")),
    ]
    # A body that always returns has no implicit return.
    assert [r.value for r in _returns(tree, f"app/m#g({DIS}).")] == [
        CallArgument(kind="int", value=2)
    ]


def test_abstract_ellipsis_body_has_no_method_return(tmp_path: Path):
    tree = _scan(
        tmp_path,
        {
            "app/m.py": (
                "from abc import ABC, abstractmethod\n"
                "from typing import Protocol\n"
                "class Repo(ABC):\n"
                "    @abstractmethod\n"
                "    def save(self, x): ...\n"
                "class Port(Protocol):\n"
                "    def send(self, x):\n"
                "        '''Send x.'''\n"
                "class Real:\n"
                "    def save(self, x): ...\n"
            )
        },
    )

    assert _returns(tree, f"app/m/Repo#save({DIS}).") == []
    assert _returns(tree, f"app/m/Port#send({DIS}).") == []
    # A plain method with an ellipsis body is a body: it returns None.
    assert [r.value for r in _returns(tree, f"app/m/Real#save({DIS}).")] == [
        CallArgument(kind="null")
    ]


def test_field_write_to_another_objects_attribute_is_not_written_until_ruled(tmp_path: Path):
    """A write to another object's attribute is not written yet: `field_write` has no
    receiver key (ruling pending, see the task report). What IS written: `self.x = …`
    names the class's field, and `C.x = …` from outside the class names C's field."""
    tree = _scan(
        tmp_path,
        {
            "app/m.py": (
                "import os\n"
                "class Client:\n"
                "    def __init__(self, base, timeout):\n"
                "        self.base = base\n"
                "        self.session = os.getenv('S')\n"
                "def configure(client):\n"
                "    Client.default = 3\n"
                "    client.base = 'x'\n"
            )
        },
    )

    writes = {
        (w.field, bare_descriptor(w.written_by or "")): w for w in _facts(tree, FieldWriteFact)
    }
    init = f"app/m/Client#<init>({DIS})."
    assert writes[("app/m/Client#base.", init)].from_parameter == 0
    getenv = _call(tree, "getenv")
    assert writes[("app/m/Client#session.", init)].value == CallArgument(
        kind="unresolved", source=getenv.result
    )
    configure = f"app/m#configure({DIS})."
    assert writes[("app/m/Client#default.", configure)].value == CallArgument(kind="int", value=3)
    assert [key for key in writes if key[1] == configure] == [("app/m/Client#default.", configure)]


# -- the coordinator's decisions -----------------------------------------------------------


def test_keyword_of_a_call_whose_signature_is_not_known_keeps_its_name(tmp_path: Path):
    tree = _scan(
        tmp_path,
        {
            "app/main.py": (
                "from fastapi import FastAPI\n"
                "from app.items import router\n"
                "app = FastAPI()\n"
                "app.include_router(router, prefix='/items')\n"
            )
        },
    )

    include = _call(tree, "include_router")
    assert bare_descriptor(include.caller) == f"app/main#<clinit>({DIS})."
    assert include.receiver_field == "app/main#app."
    assert include.target.owner is None
    assert include.arguments == [
        CallArgument(kind="field", symbol="app/items#router."),
        CallArgument(kind="string", value="/items", keyword="prefix"),
    ]


def test_every_statement_form_writes_its_calls(tmp_path: Path):
    tree = _scan(
        tmp_path,
        {
            "app/m.py": (
                "from app.lib import check, fail, label, load, open_it, price, use\n"
                "def run(items, lock):\n"
                "    total = 0\n"
                "    total += price(items)\n"
                "    for item in load(items):\n"
                "        use(item)\n"
                "    with open_it(lock) as handle:\n"
                "        handle.write('x')\n"
                "    names = [label(i) for i in items]\n"
                "    if check(total):\n"
                "        raise fail()\n"
            )
        },
    )

    names = [c.target.name for c in _calls(tree, f"app/m#run({DIS}).")]
    assert names == [
        "price",
        "load",
        "__iter__",
        "__next__",
        "use",
        "open_it",
        "__enter__",
        "write",
        "__iter__",
        "__next__",
        "label",
        "check",
        "fail",
    ]
    enter = _call(tree, "__enter__")
    write = _call(tree, "write")
    assert enter.receiver == _call(tree, "open_it").result
    assert write.receiver == enter.result


def test_nested_function_and_lambda_are_methods_of_their_own(tmp_path: Path):
    tree = _scan(
        tmp_path,
        {
            "app/m.py": (
                "from app.lib import rank, work\n"
                "def outer(items):\n"
                "    def inner(x):\n"
                "        return work(x)\n"
                "    items.sort(key=lambda i: rank(i))\n"
                "    return inner\n"
            )
        },
    )

    symbols = {bare_descriptor(s.symbol): s for s in _facts(tree, SymbolFact)}
    inner = f"app/m#outer$inner({DIS})."
    lam = f"app/m#lambda$outer$0({DIS})."
    assert symbols[inner].enclosing is not None
    assert bare_descriptor(symbols[inner].enclosing) == "app/m#"
    assert [c.target.name for c in _calls(tree, inner)] == ["work"]
    assert [c.target.name for c in _calls(tree, lam)] == ["rank"]
    sort = _call(tree, "sort")
    assert sort.arguments == [CallArgument(kind="lambda", symbol=lam, captures=0, keyword="key")]
    (returned,) = _returns(tree, f"app/m#outer({DIS}).")
    assert returned.value == CallArgument(kind="lambda", symbol=inner, captures=0)


def _made(tree, caller: str) -> list[CallSiteFact]:
    """The capture sites of `caller`: where it makes a function that captured values."""
    return [
        c
        for c in _calls(tree, caller)
        if c.target.owner == "types/FunctionType#" and c.target.name == "<init>"
    ]


def test_a_nested_function_captures_the_outer_names_it_reads_after_its_parameters(
    tmp_path: Path,
):
    tree = _scan(
        tmp_path,
        {
            "app/m.py": (
                "from app.lib import work\n"
                "def outer(view, flag):\n"
                "    def inner(request, *args):\n"
                "        return flag and view(request, *args)\n"
                "    return inner\n"
            )
        },
    )

    outer = f"app/m#outer({DIS})."
    inner = f"app/m#outer$inner({DIS})."
    (site,) = _made(tree, outer)
    assert site.invoke_kind == "dynamic"
    assert site.arguments == [
        CallArgument(kind="parameter", value=1),
        CallArgument(kind="parameter", value=0),
    ]
    (returned,) = _returns(tree, outer)
    assert returned.value == CallArgument(
        kind="lambda", symbol=inner, captures=2, source=site.result
    )
    # Written `(request, *args)`: `flag` is parameter 2, `view` parameter 3.
    (view,) = [c for c in _calls(tree, inner) if c.target.name == "__call__"]
    assert view.receiver_parameter == 3
    assert view.arguments == [
        CallArgument(kind="parameter", value=0),
        CallArgument(kind="parameter", value=1, keyword="*"),
    ]


def test_a_lambda_captures_the_outer_name_it_reads(tmp_path: Path):
    tree = _scan(
        tmp_path,
        {
            "app/m.py": (
                "from app.lib import rank\n"
                "def outer(items, by):\n"
                "    items.sort(key=lambda i: rank(i, by))\n"
            )
        },
    )

    outer = f"app/m#outer({DIS})."
    lam = f"app/m#lambda$outer$0({DIS})."
    (site,) = _made(tree, outer)
    assert site.arguments == [CallArgument(kind="parameter", value=1)]
    sort = _call(tree, "sort")
    assert sort.arguments == [
        CallArgument(kind="lambda", symbol=lam, captures=1, source=site.result, keyword="key")
    ]
    assert _call(tree, "rank").arguments == [
        CallArgument(kind="parameter", value=0),
        CallArgument(kind="parameter", value=1),
    ]


def test_a_middle_function_captures_what_its_inner_function_reads(tmp_path: Path):
    tree = _scan(
        tmp_path,
        {
            "app/m.py": (
                "def a(k):\n"
                "    def b(f):\n"
                "        def c(request):\n"
                "            return f(request) if k else None\n"
                "        return c\n"
                "    return b\n"
            )
        },
    )

    a, b, c = (f"app/m#{name}({DIS})." for name in ("a", "a$b", "a$b$c"))
    (from_a,) = _made(tree, a)
    assert from_a.arguments == [CallArgument(kind="parameter", value=0)]
    (made_b,) = _returns(tree, a)
    assert made_b.value.captures == 1
    # `b` holds `k` as its parameter 1, and hands it on to `c` beside its own `f`.
    (from_b,) = _made(tree, b)
    assert from_b.arguments == [
        CallArgument(kind="parameter", value=0),
        CallArgument(kind="parameter", value=1),
    ]
    (made_c,) = _returns(tree, b)
    assert made_c.value.captures == 2
    (f,) = [x for x in _calls(tree, c) if x.target.name == "__call__"]
    assert f.receiver_parameter == 1


def test_a_name_a_deeper_function_holds_itself_is_no_capture_of_the_middle(tmp_path: Path):
    """`c` reads its own parameter `request` and `b` holds none: `b` captures nothing of `a`,
    though `a` has a `request` too; `c` captures `b`'s `f` alone (OI-536)."""
    tree = _scan(
        tmp_path,
        {
            "app/m.py": (
                "def a(request):\n"
                "    def b(f):\n"
                "        def c(request):\n"
                "            def d():\n"
                "                return None\n"
                "            return f(request) or d\n"
                "        return c\n"
                "    return b\n"
            )
        },
    )

    assert _made(tree, f"app/m#a({DIS}).") == []
    (from_b,) = _made(tree, f"app/m#a$b({DIS}).")
    assert from_b.arguments == [CallArgument(kind="parameter", value=0)]


def test_a_name_written_again_after_the_def_is_captured_unread(tmp_path: Path):
    tree = _scan(
        tmp_path,
        {
            "app/m.py": (
                "from app.lib import make, other\n"
                "def outer():\n"
                "    view = make()\n"
                "    def inner(request):\n"
                "        return view(request)\n"
                "    view = other()\n"
                "    return inner\n"
            )
        },
    )

    (site,) = _made(tree, f"app/m#outer({DIS}).")
    assert site.arguments == [CallArgument(kind="unresolved")]


def test_a_name_a_loop_writes_is_captured_unread_by_a_def_in_the_loop(tmp_path: Path):
    """`for name in NAMES: def view(...)`: the loop writes `name` again on its next pass, after
    the `def`, so the capture has no one value (OI-535); a name the loop does not write keeps
    its value."""
    tree = _scan(
        tmp_path,
        {
            "app/m.py": (
                "def outer():\n"
                "    kept = 'k'\n"
                "    for name in ['a', 'b']:\n"
                "        def view(request):\n"
                "            return (name, kept)\n"
                "        register(view)\n"
            )
        },
    )

    (site,) = _made(tree, f"app/m#outer({DIS}).")
    assert site.arguments == [
        CallArgument(kind="unresolved"),
        CallArgument(kind="string", value="k"),
    ]


def test_a_name_an_inner_function_rebinds_nonlocal_is_captured_unread(tmp_path: Path):
    tree = _scan(
        tmp_path,
        {
            "app/m.py": (
                "def outer(count):\n"
                "    def bump():\n"
                "        nonlocal count\n"
                "        count = count + 1\n"
                "    def read():\n"
                "        return count\n"
                "    return read\n"
            )
        },
    )

    # `bump` and `read` each capture `count`; neither has one value of it.
    sites = _made(tree, f"app/m#outer({DIS}).")
    assert [site.arguments for site in sites] == [[CallArgument(kind="unresolved")]] * 2


def test_a_function_with_no_capture_a_class_and_the_receiver_are_named_directly(
    tmp_path: Path,
):
    tree = _scan(
        tmp_path,
        {
            "app/m.py": (
                "from app.lib import work\n"
                "class Box:\n"
                "    def outer(self):\n"
                "        def helper(x):\n"
                "            return work(x)\n"
                "        class Local:\n"
                "            pass\n"
                "        def inner(y):\n"
                "            self.put(helper(y), Local())\n"
                "        return inner\n"
            )
        },
    )

    outer = f"app/m/Box#outer({DIS})."
    inner = f"app/m/Box#outer$inner({DIS})."
    assert _made(tree, outer) == []
    (returned,) = _returns(tree, outer)
    assert returned.value == CallArgument(kind="lambda", symbol=inner, captures=0)
    called = {(c.target.owner, c.target.name) for c in _calls(tree, inner)}
    assert ("app/m/Box#", "outer$helper") in called
    assert ("app/m/Box$outer$Local#", "<init>") in called
    (put,) = [c for c in _calls(tree, inner) if c.target.name == "put"]
    assert put.receiver_parameter is None


def test_a_sibling_function_with_captures_and_the_bodys_own_name_are_named_directly(
    tmp_path: Path,
):
    """`b` calls its sibling `a`, which captured `n`, and `again` calls itself: each call
    names the body it runs, as before captures were written, so the call graph keeps the
    edge. What `a` captured is bound where `a` was made."""
    tree = _scan(
        tmp_path,
        {
            "app/m.py": (
                "from app.lib import work\n"
                "def outer(n):\n"
                "    def a(k):\n"
                "        return work(k, n)\n"
                "    def b(k):\n"
                "        return a(k)\n"
                "    def again(k):\n"
                "        return again(k - n)\n"
                "    return b, again\n"
            )
        },
    )

    called = {(c.target.owner, c.target.name) for c in _calls(tree, f"app/m#outer$b({DIS}).")}
    assert ("app/m#", "outer$a") in called
    recursive = _calls(tree, f"app/m#outer$again({DIS}).")
    assert ("app/m#", "outer$again") in {(c.target.owner, c.target.name) for c in recursive}


def test_closed_list_receiver_is_followed_through_its_field(tmp_path: Path):
    tree = _scan(
        tmp_path,
        {
            "app/codec.py": (
                "try:\n"
                "    import ujson as json\n"
                "except ImportError:\n"
                "    import json\n"
                "def dump(x):\n"
                "    return json.dumps(x)\n"
            )
        },
    )

    dumps = _call(tree, "dumps")
    assert dumps.target.owner is None
    assert dumps.receiver is not None
    assert dumps.receiver_field == "app/codec#json."
    writes = [w for w in _facts(tree, FieldWriteFact) if w.field == "app/codec#json."]
    assert [w.value for w in writes] == [
        CallArgument(kind="class", symbol="ujson#"),
        CallArgument(kind="class", symbol="json#"),
    ]


def test_a_module_level_alias_of_an_imported_name_binds_like_an_import(tmp_path: Path):
    tree = _scan(
        tmp_path,
        {
            "app/errors.py": (
                "import jwt\n"
                "DecodeError = jwt.DecodeError\n"
                "class Bad(DecodeError, ValueError): pass\n"
                "def check():\n"
                "    raise DecodeError('x')\n"
            )
        },
    )

    (bad,) = [s for s in _facts(tree, SymbolFact) if bare_descriptor(s.symbol) == "app/errors/Bad#"]
    assert bare_descriptor(bad.superclass or "") == "jwt/DecodeError#"
    assert [bare_descriptor(i) for i in bad.interfaces] == ["builtins/ValueError#"]
    raised = _call(tree, "DecodeError")
    assert (raised.target.owner, raised.invoke_kind) == ("jwt#", "static")


def test_super_call_is_special_on_the_first_parent(tmp_path: Path):
    tree = _scan(
        tmp_path,
        {
            "app/m.py": (
                "class Base:\n"
                "    def __init__(self, x): pass\n"
                "class Child(Base):\n"
                "    def __init__(self):\n"
                "        super().__init__(x=1)\n"
            )
        },
    )

    init = next(c for c in _facts(tree, CallSiteFact) if c.target.name == "<init>")
    assert (init.target.owner, init.invoke_kind) == ("app/m/Base#", "special")
    assert init.arguments == [CallArgument(kind="int", value=1, keyword="x")]


def test_lists_are_arrays_and_a_local_function_reference_is_a_lambda(tmp_path: Path):
    tree = _scan(
        tmp_path,
        {
            "app/m.py": (
                "from app.lib import register\n"
                "def handler(): pass\n"
                "def main():\n"
                "    register(['a', 'b'], handler)\n"
            )
        },
    )

    register = _call(tree, "register")
    assert register.arguments == [
        CallArgument(
            kind="array",
            symbol="builtins/list#",
            elements=[
                CallArgument(kind="string", value="a"),
                CallArgument(kind="string", value="b"),
            ],
        ),
        CallArgument(kind="lambda", symbol=f"app/m#handler({DIS}).", captures=0),
    ]


def test_an_unnameable_written_type_is_not_erased_to_any(tmp_path: Path):
    tree = _scan(tmp_path, {"app/m.py": "def f(x: Mystery): pass\n"})

    (f,) = [s for s in _facts(tree, SymbolFact) if bare_descriptor(s.symbol) == f"app/m#f({DIS})."]
    assert f.signature is not None
    assert f.signature.parameters[0].erased_symbol == "Mystery"


def test_a_list_in_a_local_is_read_once_as_written(tmp_path: Path):
    """A list can change once code is handed it, as a JVM array that reaches another
    call can: the first read is the literal, a later read is `unresolved`."""
    tree = _scan(
        tmp_path,
        {
            "app/m.py": (
                "from app.lib import use\n"
                "def run():\n"
                "    found = ['a']\n"
                "    found.append('b')\n"
                "    use(found)\n"
            )
        },
    )

    assert _call(tree, "use").arguments == [CallArgument(kind="unresolved")]


# -- fix round 1 -------------------------------------------------------------------------


def test_a_function_defined_twice_shares_one_body_counter(tmp_path: Path):
    """Two definitions of one name are one method symbol, so they share its ordinals and
    value ids, and each return names its own body's call."""
    tree = _scan(
        tmp_path,
        {
            "app/m.py": (
                "import sys\n"
                "from app.lib import g, h\n"
                "if sys.flags.debug:\n"
                "    def f(x):\n"
                "        return g(x)\n"
                "else:\n"
                "    def f(x):\n"
                "        return h(x)\n"
            )
        },
    )

    method = f"app/m#f({DIS})."
    calls = {c.target.name: c for c in _calls(tree, method)}
    assert sorted(c.ordinal for c in calls.values()) == [0, 1]
    assert calls["g"].result != calls["h"].result
    returns = _returns(tree, method)
    assert sorted(r.ordinal for r in returns) == [0, 1]
    assert [r.value.source for r in returns if r.value is not None] == [
        calls["g"].result,
        calls["h"].result,
    ]


def test_a_class_defined_twice_shares_one_clinit_counter(tmp_path: Path):
    tree = _scan(
        tmp_path,
        {
            "app/m.py": (
                "import sys\n"
                "from app.lib import g, h\n"
                "if sys.flags.debug:\n"
                "    class C:\n"
                "        a = g()\n"
                "else:\n"
                "    class C:\n"
                "        a = h()\n"
            )
        },
    )

    calls = _calls(tree, f"app/m/C#<clinit>({DIS}).")
    assert sorted(c.ordinal for c in calls) == [0, 1]
    assert len({c.result for c in calls}) == 2


def test_an_attribute_chain_through_a_variable_invents_no_type(tmp_path: Path):
    tree = _scan(
        tmp_path,
        {
            "app/m.py": (
                "from fastapi import FastAPI\n"
                "import httpx\n"
                "from app.config import settings\n"
                "app = FastAPI()\n"
                "client = httpx.Client()\n"
                "def run():\n"
                "    app.state.client.get('/x')\n"
                "    client.headers.update({})\n"
                "    settings.http.client.post()\n"
            ),
            "app/config.py": "settings = 1\n",
        },
    )

    for name in ("get", "update", "post"):
        call = _call(tree, name)
        assert call.target.owner is None
        assert call.receiver_field is None
        assert call.receiver is not None


def test_self_inside_a_nested_function_is_the_methods_receiver(tmp_path: Path):
    """A nested function sees the method's `self` as a JVM lambda body sees `this`."""
    tree = _scan(
        tmp_path,
        {
            "app/m.py": (
                "class Svc:\n"
                "    def run(self):\n"
                "        def go():\n"
                "            return self.client.get('/x')\n"
                "        return go\n"
            )
        },
    )

    get = _call(tree, "get")
    assert bare_descriptor(get.caller) == f"app/m/Svc#run$go({DIS})."
    assert get.receiver_field == "app/m/Svc#client."
    assert get.receiver_field_kind == "instance"


def test_a_try_import_inside_a_function_is_a_closed_list(tmp_path: Path):
    tree = _scan(
        tmp_path,
        {
            "app/m.py": (
                "from app.lib import use\n"
                "def run(x):\n"
                "    try:\n"
                "        import ujson as json\n"
                "    except ImportError:\n"
                "        import json\n"
                "    use(json)\n"
                "    return json.dumps(x)\n"
            )
        },
    )

    assert _call(tree, "use").arguments == [
        CallArgument(
            kind="merge",
            candidates=[
                CallArgument(kind="class", symbol="ujson#"),
                CallArgument(kind="class", symbol="json#"),
            ],
        )
    ]
    dumps = _call(tree, "dumps")
    assert dumps.target.owner is None
    assert dumps.receiver is not None


def test_an_element_store_and_delete_are_the_calls_the_language_makes(tmp_path: Path):
    """`x[i] = v` is `x.__setitem__(i, v)`, `del x[i]` is `x.__delitem__(i)`, and
    `x[i] += v` is the read then `__setitem__` (ruled 2026-11-23), named as `__getitem__`
    is: on a module name through `receiver_field`, at module level and in a function."""
    tree = _scan(
        tmp_path,
        {
            "app/m.py": (
                "VERBS = ['get']\n"
                "VERBS[0] = 'x'\n"
                "del VERBS[0]\n"
                "VERBS[0] += 'z'\n"
                "def f():\n"
                "    VERBS[0] = 'q'\n"
                "    del VERBS[0]\n"
            )
        },
    )

    def on_verbs(caller: str) -> list[tuple[str, list[CallArgument]]]:
        return [
            (c.target.name, c.arguments)
            for c in _calls(tree, caller)
            if c.receiver_field == "app/m#VERBS." and c.target.owner == "builtins/list#"
        ]

    zero = CallArgument(kind="int", value=0)
    module = on_verbs(f"app/m#<clinit>({DIS}).")
    assert [name for name, _ in module] == [
        "__setitem__",
        "__delitem__",
        "__getitem__",
        "__setitem__",
    ]
    assert module[0][1] == [zero, CallArgument(kind="string", value="x")]
    assert module[1][1] == [zero]
    assert on_verbs(f"app/m#f({DIS}).") == [
        ("__setitem__", [zero, CallArgument(kind="string", value="q")]),
        ("__delitem__", [zero]),
    ]


def test_an_element_inside_a_tuple_target_is_stored_or_deleted(tmp_path: Path):
    """`x[0], b = v` stores into the element at module level as in a function, and
    `del (x[0], b)` deletes it (OI-515)."""
    tree = _scan(
        tmp_path,
        {
            "app/m.py": (
                "VERBS = ['get']\n"
                "VERBS[0], b = 'post', 1\n"
                "del (VERBS[0], b)\n"
                "def f():\n"
                "    VERBS[0], c = 'post', 1\n"
                "    del (VERBS[0], c)\n"
            )
        },
    )

    for caller in (f"app/m#<clinit>({DIS}).", f"app/m#f({DIS})."):
        assert [
            c.target.name
            for c in _calls(tree, caller)
            if c.receiver_field == "app/m#VERBS." and c.target.owner == "builtins/list#"
        ] == ["__setitem__", "__delitem__"], caller


def test_an_augmented_element_store_reads_its_object_and_index_once(tmp_path: Path):
    """`x[f()] += v` runs `f()` once (OI-513): the store takes the object and the index the
    read took."""
    tree = _scan(
        tmp_path,
        {
            "app/m.py": (
                "def at():\n    return 0\n"
                "def table():\n    return VERBS\n"
                "VERBS = ['get']\n"
                "table()[at()] += 'z'\n"
                "def f():\n"
                "    table()[at():at()] += ['q']\n"
            )
        },
    )

    for caller in (f"app/m#<clinit>({DIS}).", f"app/m#f({DIS})."):
        calls = _calls(tree, caller)
        named = [c.target.name for c in calls]
        assert named.count("table") == 1, caller
        assert named.count("at") == (1 if "clinit" in caller else 2), caller
        (read,) = [c for c in calls if c.target.name == "__getitem__"]
        (store,) = [c for c in calls if c.target.name == "__setitem__"]
        assert (store.receiver, store.arguments[0]) == (read.receiver, read.arguments[0])


def _writes(tree, field: str) -> list[CallArgument | None]:
    return [w.value for w in _facts(tree, FieldWriteFact) if w.field == field]


def _star(symbol: str) -> CallArgument:
    return CallArgument(kind="field", symbol=symbol, keyword="*")


def _list(*elements: CallArgument) -> CallArgument:
    return CallArgument(kind="array", symbol="builtins/list#", elements=list(elements))


def test_a_written_list_and_tuple_carry_their_class(tmp_path: Path):
    tree = _scan(tmp_path, {"app/m.py": "A = ['a']\nB = ('b',)\n"})

    a = CallArgument(kind="string", value="a")
    assert _writes(tree, "app/m#A.") == [_list(a)]
    assert _writes(tree, "app/m#B.") == [
        CallArgument(
            kind="array",
            symbol="builtins/tuple#",
            elements=[CallArgument(kind="string", value="b")],
        )
    ]


def test_list_of_a_value_is_the_list_of_its_members(tmp_path: Path):
    """`list(x)` makes a new list of `x`'s elements: `[*x]`. Only the builtin `list` is it:
    a name `list` this code binds to something else is a call of that."""
    tree = _scan(
        tmp_path,
        {
            "app/m.py": "A = ['a']\nB = list(A)\n",
            "app/n.py": "from app.lib import list\nA = ['a']\nB = list(A)\n",
            "app/o.py": "def f(x, make):\n    list = make\n    return list(x)\n",
        },
    )

    assert _writes(tree, "app/m#B.") == [_list(CallArgument(kind="string", value="a"))]
    (other,) = _writes(tree, "app/n#B.")
    assert other is not None and other.kind == "unresolved"
    (returned,) = _returns(tree, f"app/o#f({DIS}).")
    assert returned.value is not None and returned.value.kind == "unresolved"


def test_append_and_extend_on_a_module_list_are_writes(tmp_path: Path):
    """At module level, `x.append(v)` writes `x` as `[*x, v]` and `x.extend(vs)` as
    `[*x, *vs]`, a written list's elements in place. The call returns nothing, and no
    `append` or `extend` site is written for it."""
    tree = _scan(
        tmp_path,
        {
            "app/m.py": (
                "from app.lib import OTHER\n"
                "X = ['a']\n"
                "X.append('b')\n"
                "X.extend(['c', 'd'])\n"
                "X.extend(OTHER)\n"
                "R = X.append('e')\n"
            )
        },
    )

    def text(value: str) -> CallArgument:
        return CallArgument(kind="string", value=value)

    other = (_writes(tree, "app/m#X.")[3].elements or [])[-1]
    assert other.keyword == "*"
    a, b, c, d = text("a"), text("b"), text("c"), text("d")
    assert _writes(tree, "app/m#X.") == [
        _list(a),
        _list(a, b),
        _list(a, b, c, d),
        _list(a, b, c, d, other),
        _list(a, b, c, d, other, text("e")),
    ]
    assert _writes(tree, "app/m#R.") == [CallArgument(kind="null")]
    assert not [c for c in _facts(tree, CallSiteFact) if c.target.name in ("append", "extend")]


def test_an_adder_that_is_not_on_a_list_of_this_module_body_stays_a_call(tmp_path: Path):
    """Inside a function, on a name of another module, or on a name this body last wrote as
    something that is not a list, `append` and `extend` are calls."""
    tree = _scan(
        tmp_path,
        {
            "app/m.py": (
                "from app.other import Y\n"
                "X = ['a']\n"
                "def f():\n"
                "    X.append('b')\n"
                "Y.append('c')\n"
                "Z = ['a']\n"
                "Z = make()\n"
                "Z.extend(['d'])\n"
            )
        },
    )

    assert len(_writes(tree, "app/m#X.")) == 1
    assert len(_writes(tree, "app/m#Z.")) == 2
    assert not _writes(tree, "app/other#Y.")
    adders = [
        c.target.name for c in _facts(tree, CallSiteFact) if c.target.name in ("append", "extend")
    ]
    assert adders == ["append", "append", "extend"]


def test_a_name_written_as_a_tuple_is_not_a_list(tmp_path: Path):
    """`T = ('a',)` then `T += OTHER`: a tuple is no list, so the sum is not written as a
    list of the list class (older Django settings write `MIDDLEWARE_CLASSES` so)."""
    tree = _scan(
        tmp_path,
        {"app/m.py": "from app.lib import OTHER\nT = ('a',)\nT += OTHER\nT.append('b')\n"},
    )

    first, summed = _writes(tree, "app/m#T.")
    assert first is not None and first.symbol == "builtins/tuple#"
    assert summed is None or summed.kind != "array"


def test_a_sum_onto_a_list_name_is_a_list(tmp_path: Path):
    """A name last written as a list in this body is a list, whatever its other writes."""
    tree = _scan(
        tmp_path,
        {
            "app/m.py": (
                "from app.lib import OTHER, f, make\n"
                "x = make()\n"
                "x = ['a']\n"
                "x += OTHER\n"
                "b = make()\n"
                "b = ['p']\n"
                "urlpatterns = f(*b) + b\n"
                "count = 0\n"
                "count += 1\n"
                "text = 'a'\n"
                "text += 'x'\n"
            )
        },
    )

    summed = _writes(tree, "app/m#x.")[-1]
    assert summed is not None and summed.kind == "array"
    own, other = summed.elements or []
    assert own == CallArgument(kind="string", value="a")
    assert other.keyword == "*"
    patterns = _writes(tree, "app/m#urlpatterns.")[-1]
    assert patterns is not None and patterns.kind == "array"
    called, held = patterns.elements or []
    assert called.kind == "unresolved" and called.keyword == "*"
    assert held == CallArgument(kind="string", value="p")
    counted = _writes(tree, "app/m#count.")[-1]
    assert counted is not None and counted.kind == "unresolved"
    texted = _writes(tree, "app/m#text.")[-1]
    assert texted is not None and texted.kind == "concat"


def test_format_on_a_literal_is_its_template(tmp_path: Path):
    """`"...".format(...)` on a string literal is the `concat` its fields make, filled by
    position, by number or by name; `{{` and `}}` are braces."""
    tree = _scan(
        tmp_path,
        {
            "app/m.py": (
                "def a(rule):\n    return '/<org>{}'.format(rule)\n"
                "def b(x, y):\n    return '{b}-{a}'.format(a=x, b=y)\n"
                "def c(x, y):\n    return '{1}/{0}/{1}'.format(x, y)\n"
                "def d():\n    return '{{x}}/{}'.format('k')\n"
                "def e(x, y):\n    return '{}/{n}'.format(x, n=y)\n"
            )
        },
    )

    def p(at: int) -> CallArgument:
        return CallArgument(kind="parameter", value=at)

    expected = {
        "a": ("/<org>{}", [p(0)]),
        "b": ("{}-{}", [p(1), p(0)]),
        "c": ("{}/{}/{}", [p(1), p(0), p(1)]),
        "d": ("{x}/{}", [CallArgument(kind="string", value="k")]),
        "e": ("{}/{}", [p(0), p(1)]),
    }
    for name, (template, operands) in expected.items():
        method = f"app/m#{name}({DIS})."
        (site,) = _calls(tree, method)
        assert site.invoke_kind == "dynamic"
        assert site.target.owner == "builtins/str#"
        assert site.target.name == "format"
        assert site.receiver is None
        assert site.arguments == operands
        (returned,) = _returns(tree, method)
        assert returned.value == CallArgument(kind="concat", value=template, source=site.result)


def test_format_the_reader_does_not_model_is_unread(tmp_path: Path):
    """A conversion, a format spec, an attribute or index of a field, automatic and numbered
    fields mixed, an unpacked argument, a field with no argument, or a receiver that is not a
    literal: the value is unread, as any call on a string is."""
    shapes = [
        "'{0!r}'.format(x)",
        "'{:>8}'.format(x)",
        "'{a.b}'.format(a=x)",
        "'{a[0]}'.format(a=x)",
        "'{}{0}'.format(x)",
        "'{}'.format(*x)",
        "'{a}'.format(**x)",
        "'{1}'.format(x)",
        "'{n}'.format(x)",
        "'{'.format(x)",
        "x.format(1)",
    ]
    text = "".join(f"def f{at}(x):\n    return {shape}\n" for at, shape in enumerate(shapes))
    tree = _scan(tmp_path, {"app/m.py": text})

    for at, shape in enumerate(shapes):
        method = f"app/m#f{at}({DIS})."
        (returned,) = _returns(tree, method)
        assert returned.value is not None and returned.value.kind == "unresolved", shape
        assert not [s for s in _calls(tree, method) if s.invoke_kind == "dynamic"], shape


def test_a_template_whose_text_holds_braces_that_are_no_hole(tmp_path: Path):
    """`{{` and `}}` are a brace of the text. Where the text then holds `{}`, the template
    (whose holes are `{}`) cannot tell it from a hole: the value is unread (OI-519). Other
    braces of the text are kept as they are."""
    shapes = ["'/x/{{}}/{}'.format(x)", "f'/x/{{}}/{x}'"]
    kept = "'/x/{{id}}/{}'.format(x)"
    text = "".join(
        f"def f{at}(x):\n    return {shape}\n" for at, shape in enumerate([*shapes, kept])
    )
    tree = _scan(tmp_path, {"app/m.py": text})

    for at, shape in enumerate(shapes):
        method = f"app/m#f{at}({DIS})."
        (returned,) = _returns(tree, method)
        assert returned.value is not None and returned.value.kind == "unresolved", shape
        assert not [s for s in _calls(tree, method) if s.invoke_kind == "dynamic"], shape
    (returned,) = _returns(tree, f"app/m#f{len(shapes)}({DIS}).")
    assert returned.value is not None
    assert (returned.value.kind, returned.value.value) == ("concat", "/x/{id}/{}")


# -- held lists in order (plan 2026-11-23 Task 6) -----------------------------------------

_A = CallArgument(kind="string", value="a")
_B = CallArgument(kind="string", value="b")


def test_a_copy_of_a_module_list_holds_the_elements_at_its_line(tmp_path: Path):
    """`B = [*A]` is written with what `A` holds at that line: the `b` added to `A` later is
    not in the copy (spec §4c M6). The later write of `A` holds both."""
    tree = _scan(
        tmp_path,
        {"app/m.py": "A = ['a']\nB = [*A]\nA = A + ['b']\nC = [*A]\nA += ['c']\n"},
    )

    assert _writes(tree, "app/m#B.") == [_list(_A)]
    assert _writes(tree, "app/m#C.") == [_list(_A, _B)]
    assert _writes(tree, "app/m#A.")[1:] == [
        _list(_A, _B),
        _list(_A, _B, CallArgument(kind="string", value="c")),
    ]


def test_a_name_written_under_a_test_or_in_a_loop_keeps_its_read(tmp_path: Path):
    """A name written under a test or in a loop has no one value from there on: a later
    `*name` stays a read of the name, which the walk answers with every write of it."""
    tree = _scan(
        tmp_path,
        {
            "app/m.py": (
                "import os\n"
                "A = ['a']\n"
                "if os.environ:\n"
                "    A += ['b']\n"
                "B = [*A]\n"
                "for _ in range(2):\n"
                "    F = ['f']\n"
                "G = [*F]\n"
            )
        },
    )

    assert _writes(tree, "app/m#B.") == [_list(_star("app/m#A."))]
    assert _writes(tree, "app/m#G.") == [_list(_star("app/m#F."))]


def test_another_list_added_under_a_test_is_a_read_under_that_test(tmp_path: Path):
    """`if X: A += other.B`: the members of `other.B` are served only where the test holds,
    and the write says so (`field_write.guards`, ruling R1 of 2026-11-25, OI-508): they stay a
    read of the other name, never the elements this body holds in order. A registration-like
    call's result added under a test stays a member."""
    tree = _scan(
        tmp_path,
        {
            "app/m.py": (
                "import os\n"
                "from app import other\n"
                "from app.lib import reg\n"
                "L = ['l']\n"
                "A = ['a']\n"
                "if os.environ:\n"
                "    A += other.B\n"
                "    A += L\n"
                "    A += [reg()]\n"
            ),
            "app/other.py": "B = ['x']\n",
        },
    )

    first, under, local, call = _writes(tree, "app/m#A.")
    assert first == _list(_A)
    assert under == _list(_star("app/m#A."), _star("app/other#B."))
    assert local == _list(_star("app/m#A."), _star("app/m#L."))
    assert call is not None and call.elements is not None
    own, member = call.elements
    assert own == _star("app/m#A.")
    assert member.kind == "unresolved" and member.source is not None and member.keyword is None
    guarded = [w.guards for w in _facts(tree, FieldWriteFact) if w.field == "app/m#A."]
    assert guarded[0] is None
    assert [[g.test for g in guards or []] for guards in guarded[1:]] == [["os.environ"]] * 3


def test_a_star_import_of_a_variable_is_a_write_of_the_name(tmp_path: Path):
    """`from app.base import *` binds each variable `base` holds to the importing module's
    name, as `from app.base import DEBUG` does (ruling R9): one field write per name the
    star takes and the module's own statements do not bind, its value a read of the name
    where it is defined, through a second star too. A name the module writes itself keeps
    its own write alone; a function, a class and a `_private` name are not written."""
    tree = _scan(
        tmp_path,
        {
            "app/__init__.py": "",
            "app/defaults.py": "TIMEOUT = 5\n",
            "app/base.py": "from app.defaults import *\nDEBUG = False\nROOT = 'app.urls'\n"
            "_HIDDEN = 1\ndef helper():\n    return None\n",
            "app/local.py": "from app.base import *\nDEBUG = True\n",
        },
    )

    writes = {
        bare_descriptor(w.field): (w.value.kind, w.value.symbol and bare_descriptor(w.value.symbol))
        for w in _facts(tree, FieldWriteFact)
        if bare_descriptor(w.field).startswith("app/local#")
    }
    assert writes == {
        "app/local#DEBUG.": ("boolean", None),
        "app/local#ROOT.": ("field", "app/base#ROOT."),
        "app/local#TIMEOUT.": ("field", "app/defaults#TIMEOUT."),
    }


def test_a_write_of_a_name_a_star_import_can_replace_says_so(tmp_path: Path):
    """D00 §5 `field_write.replaceable` (fact schema 25, ruling R10 of 2026-11-25): a write of
    a module name carries the mark where a star import of that module can replace the name.
    A name the module writes itself: a star written after the write that binds it too
    (`late`), a star whose source is not read, a star in a `try`; never a star the write
    comes after (`base`, ruled 2026-11-26). A name star imports alone give: where a star of the module is
    not read, or the name is replaceable where the last star takes it from. A star source
    that is read and does not bind the name replaces nothing. A read from another file of a
    marked name a star alone gives names that module's name, not the one where it is defined
    (`reader#A`); the write of a star itself names where the name is defined, and has the
    mark where any module on the way can replace it (`over`)."""
    absent = "try:\n    from app.absent import *\nexcept ImportError:\n    pass\n"
    tree = _scan(
        tmp_path,
        {
            "app/__init__.py": "",
            "app/defaults.py": "TIMEOUT = 5\nDEBUG = True\n",
            "app/base.py": "from app.defaults import *\nDEBUG = False\nROOT = 'app.urls'\n",
            "app/late.py": "DEBUG = False\nfrom app.defaults import *\n",
            "app/local.py": "from app.base import *\nONLY = 1\n" + absent,
            "app/over.py": "from app.local import *\n",
            "app/reader.py": "from app import base, local\nA = local.ROOT\nB = base.TIMEOUT\n",
        },
    )

    marked = {
        bare_descriptor(w.field): (
            w.replaceable,
            w.value.symbol and bare_descriptor(w.value.symbol),
        )
        for w in _facts(tree, FieldWriteFact)
        if bare_descriptor(w.field).startswith("app/")
    }
    assert marked == {
        "app/defaults#TIMEOUT.": (None, None),
        "app/defaults#DEBUG.": (None, None),
        "app/base#DEBUG.": (None, None),
        "app/late#DEBUG.": (True, None),
        "app/late#TIMEOUT.": (None, "app/defaults#TIMEOUT."),
        "app/base#ROOT.": (None, None),
        "app/base#TIMEOUT.": (None, "app/defaults#TIMEOUT."),
        "app/local#ONLY.": (True, None),
        "app/local#DEBUG.": (True, "app/base#DEBUG."),
        "app/local#ROOT.": (True, "app/base#ROOT."),
        "app/local#TIMEOUT.": (True, "app/defaults#TIMEOUT."),
        "app/over#ONLY.": (True, "app/local#ONLY."),
        "app/over#DEBUG.": (True, "app/base#DEBUG."),
        "app/over#ROOT.": (True, "app/base#ROOT."),
        "app/over#TIMEOUT.": (True, "app/defaults#TIMEOUT."),
        "app/reader#A.": (None, "app/local#ROOT."),
        "app/reader#B.": (None, "app/defaults#TIMEOUT."),
    }
