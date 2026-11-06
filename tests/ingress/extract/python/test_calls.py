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


def test_keyword_binds_to_position_when_signature_known(tmp_path: Path):
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
    # Each argument is at its parameter's position, the default in the gap, and no
    # argument keeps a keyword.
    assert send.arguments == [
        CallArgument(kind="string", value="/a"),
        CallArgument(kind="null"),
        CallArgument(kind="int", value=9),
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
        "use",
        "open_it",
        "__enter__",
        "write",
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
    assert init.arguments == [CallArgument(kind="int", value=1)]


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
