"""Tests for the backward value walk (`resolve/values.py`, spec 2026-09-22 §1b–§1d).

**Hand-built facts, MODULE-PREFIXED, for OI-4's reason** — the one
`test_return_flow.py` and `test_call_edges.py` both state at length: one identity
has two string spellings, a call target composes BARE and a body's symbol carries
its module coordinates, and a join across the two matches nothing on a real module
while passing on a fixture that spells everything alike. The walk crosses that
boundary at every `bound_to_parameter` and every `returned_by` edge, so every
symbol below is spelled the way a real scan spells it.

The two tables the edge query reads are built by the passes that own them
(`record_return_flows`, `record_call_edges`) rather than inserted by hand: a
fixture that wrote `return_flows` itself would prove the walk agrees with the test
author about what a return flow is, which is not the question.

**The M-1 test is first on purpose** (spec §0c). It is why the primitive is a path,
and nothing else in this file would catch a regression to per-position resolution:
every other test here has one slot, and a per-position walk answers those exactly
as a per-path one does.
"""

from pathlib import Path
from typing import Any

import pytest
from fixture_module import write_fixture_module_fact

from sextant.application.ports.catalogs import Catalog
from sextant.application.resolve.call_edges import record_call_edges
from sextant.application.resolve.effective_calls import effective_call_sites
from sextant.application.resolve.return_flow import record_return_flows
from sextant.application.resolve.shadow import record_value_resolutions
from sextant.application.resolve.shapes.arguments import channel_of_answer, url_of_answer
from sextant.application.resolve.values import (
    _REASONS,
    RECEIVER,
    Answer,
    Binding,
    resolve_site,
    value_index,
)
from sextant.domain.closed_sets import ConstructKind, OriginTier
from sextant.domain.factfile import write_fact_file
from sextant.domain.facts import (
    CallArgument,
    CallSiteFact,
    CallTarget,
    Document,
    Fact,
    FieldWriteFact,
    MethodReturnFact,
    Parameter,
    Signature,
    SymbolFact,
    TypeRef,
)
from sextant.domain.symbols import method_descriptor
from sextant.storage.duckdb.workspace import DuckDbWorkspace

_MODULE = "sextant-jvm maven com.acme/orders-service 1.0.0 "
_PKG = "com/acme/orders/values/"

# The sink every fixture site calls: deliberately NOT declared, so it is the
# third-party boundary `call_edges` draws with a NULL callee. What the walk
# answers is about the site's ARGUMENTS, and a declared sink would add bodies
# that say nothing about them.
_REGISTRY = _PKG + "Registry#"
_ONE = "(Ljava/lang/String;)V"
_PAIR = "(Ljava/lang/String;Ljava/lang/Class;)V"
_MANY = "([Ljava/lang/String;)V"
_MAKES_STRING = "()Ljava/lang/String;"
_MAKES_OBJECT = "()Ljava/lang/Object;"
_TAKES_STRING = "(Ljava/lang/String;)V"

_REGISTRAR = _PKG + "Registrar#"
_CALLER = _PKG + "Caller#"
_NAMES = _PKG + "Names#"
_PUBLISHER = _PKG + "Publisher#"
_ARRAYS = _PKG + "Arrays#"
_MUTATOR = _PKG + "Mutator#"
_BUFFER = _PKG + "Buffer#"
_BINDER = _PKG + "Binder#"
# A binding whose WRITER the facts name — the sixth edge's own shape (spec
# 2026-10-18). `Written#<init>(String)` assigns its parameter to the field, and two
# callers construct it with different literals, so the edge resolves to BOTH.
_WRITTEN = _PKG + "Written#"
# A lambda that CLOSES OVER a value — the seventh edge's own shape (`OI-150`).
# `Closing#install` captures a literal into `Closing#body`, whose parameter 0 is that
# capture; nothing calls `body` directly, so without the edge its parameter is `external`.
_CLOSING = _PKG + "Closing#"
# A binding whose only write is a constant the walk has NO literal kind for — a class
# constant, which `private Class<Order> t = Order.class` produces. The fact is emitted (the
# grammar has a `class` kind); the walk cannot turn it into a value.
# A value that reaches a concat THROUGH a rendering call — javac's own
# `String.valueOf(Object)` around a non-String operand, which is the shape every address
# assembled from an object has (`OI-138` cause 3, CP-39).
_RENDERED = _PKG + "Rendered#"
_UNREADABLE = _PKG + "Unreadable#"
_ENTRY = _PKG + "Entry#"
_OUTSIDE = _PKG + "Outside#"
# The identity arm's producer (spec §2): deliberately NOT declared, so every value it
# hands back is `external` until an `identified_by` entry says which of its arguments IS
# that value — which is the real shape, since the producers catalogs write hop
# declarations for live in jars (`jakarta.jms.Session`, `ProjectSubscriptionName`).
_NAME = _PKG + "Name#"
_IDENTIFIED = _PKG + "Identified#"
_UNREAD = _PKG + "Unread#"
_LOOP = _PKG + "Loop#"
_ASSEMBLER = _PKG + "Assembler#"
_PRESERVED = _PKG + "Preserved#"
_AUTHORITY_CHAIN = _PKG + "AuthorityChain#"
_JOINER = _PKG + "Joiner#"
_HALF_JOINER = _PKG + "HalfJoiner#"
_CONFIG_JOINER = _PKG + "ConfigJoiner#"
_TWO_HOLES = _PKG + "TwoHoles#"
_RECEIVING = _PKG + "Receiving#"
_FACTORY = _PKG + "Factory#"
_DEEP = _PKG + "Deep#"
_DIAMOND = _PKG + "Diamond#"

_ORDER_WORKER = _PKG + "OrderWorker#"
_BILLING_WORKER = _PKG + "BillingWorker#"
_REGISTRY_IMPL = _PKG + "RegistryImpl#"
# Capability 9.19 (spec 2026-10-21 merged values): a wrapper that reassigns its parameter on
# one branch before the consuming call, and a class whose merges have no root.
_WRAPPER = _PKG + "Wrapper#"
_FORKED = _PKG + "Forked#"
_SUBSTRING = ("java/lang/String#", "substring", "(I)Ljava/lang/String;")


def _symbol(owner: str, name: str, jvm: str) -> str:
    """A method's symbol as a real scan writes it: module coordinates and all."""
    return _MODULE + method_descriptor(owner, name, jvm)


def _document() -> Document:
    return Document(
        document_id="doc_values",
        relative_path="com/acme/orders/values/Registrar.java",
        module_id="com.acme:orders-service",
        language="java",
        sextant_version="0.1.0",
        fact_schema_version=2,
        scanner_id="asm",
        content_hash="sha256:v",
        origin_entry="target/classes",
        origin_tier=OriginTier.MODULE_OUTPUT,
        redaction_set_hash="sha256:none",
    )


def _type(owner: str) -> SymbolFact:
    return SymbolFact(
        document_id="doc_values", symbol=_MODULE + owner, construct_kind=ConstructKind.CLASS
    )


def _declared(owner: str, name: str, jvm: str) -> SymbolFact:
    return SymbolFact(
        document_id="doc_values",
        symbol=_symbol(owner, name, jvm),
        construct_kind=ConstructKind.METHOD,
        enclosing=_MODULE + owner,
        signature=Signature(parameters=[], returns=TypeRef(symbol="java/lang/String#")),
    )


def _returns(owner: str, name: str, jvm: str, ordinal: int, value: CallArgument) -> Fact:
    return MethodReturnFact(
        document_id="doc_values",
        method=_symbol(owner, name, jvm),
        ordinal=ordinal,
        value=value,
    )


def _void(owner: str, name: str, jvm: str) -> Fact:
    """The `method_return` fact a method that hands nothing back still carries — one per
    return instruction, D00 §5 — and the reason it matters here: `dispatch` reads this
    table to answer "did we read a body", so a callee without one is indistinguishable
    from a third-party call and binds no parameter at all."""
    return MethodReturnFact(
        document_id="doc_values", method=_symbol(owner, name, jvm), ordinal=0, value=None
    )


def _site(
    caller: str,
    ordinal: int,
    target: tuple[str, str, str],
    *,
    kind: str = "static",
    arguments: list[CallArgument] | None = None,
    result: int | None = None,
    receiver: int | None = None,
    receiver_parameter: int | None = None,
) -> Fact:
    owner, name, jvm = target
    return CallSiteFact(
        document_id="doc_values",
        caller=caller,
        target=CallTarget(owner=owner, name=name, descriptor=jvm),
        invoke_kind=kind,
        ordinal=ordinal,
        result=result,
        receiver=receiver,
        receiver_parameter=receiver_parameter,
        arguments=arguments or [],
    )


# The identity producer's two overloads, which only a descriptor or an arity separates.
_OF_TWO = "(Ljava/lang/String;Ljava/lang/String;)Ljava/lang/Object;"
_OF_ONE = "(Ljava/lang/String;)Ljava/lang/Object;"
# The VARARGS overload of the same producer, and the empty one. `all_strings` is the only
# rule that reads either: a varargs call carries ONE `array` argument (capability 9.15,
# never N unpacked ones), and a no-argument call is the `absent` that D00 §5 distinguishes
# from an unreadable list.
_OF_VARARGS = "([Ljava/lang/String;)Ljava/lang/Object;"
_OF_NONE = "()Ljava/lang/Object;"
# Its CONSTRUCTORS, which only a descriptor separates — `ContainerProperties(String...)`
# beside `ContainerProperties(Pattern)` is the shipped pair arity cannot tell apart.
_CTOR_ONE = "(Ljava/lang/String;)V"
_CTOR_ARRAY = "([Ljava/lang/String;)V"
_TOUCH = "()V"

_PAIR_TARGET = (_REGISTRY, "pair", _PAIR)
_ONE_TARGET = (_REGISTRY, "one", _ONE)
_MANY_TARGET = (_REGISTRY, "many", _MANY)


def _facts() -> list[Fact]:
    """One fact set, one arm per rule the walk implements.

    Every method that is WALKED INTO is declared, because `call_edges` and
    `return_flows` only name a body this workspace read — which is the same
    boundary the walk reports as `external`, and two of the arms below rely on
    a producer that was deliberately left undeclared.
    """
    register = _symbol(_REGISTRAR, "register", _PAIR)
    facts: list[Fact] = [
        _type(owner)
        for owner in (
            _REGISTRAR,
            _CALLER,
            _NAMES,
            _PUBLISHER,
            _ARRAYS,
            _MUTATOR,
            _BINDER,
            _WRITTEN,
            _RENDERED,
            _UNREADABLE,
            _CLOSING,
            _ENTRY,
            _OUTSIDE,
            _IDENTIFIED,
            _UNREAD,
            _LOOP,
            _ASSEMBLER,
            _PRESERVED,
            _AUTHORITY_CHAIN,
            _JOINER,
            _HALF_JOINER,
            _CONFIG_JOINER,
            _TWO_HOLES,
            _RECEIVING,
            _FACTORY,
            _DEEP,
            _DIAMOND,
        )
    ]
    facts += [
        # M-1: one helper, two call sites, two values per call.
        _declared(_REGISTRAR, "register", _PAIR),
        _void(_REGISTRAR, "register", _PAIR),
        _declared(_CALLER, "run", "()V"),
        _site(
            register,
            0,
            _PAIR_TARGET,
            kind="virtual",
            arguments=[
                CallArgument(kind="parameter", value=0),
                CallArgument(kind="parameter", value=1),
            ],
        ),
        _site(
            _symbol(_CALLER, "run", "()V"),
            0,
            (_REGISTRAR, "register", _PAIR),
            arguments=[
                CallArgument(kind="string", value="orders"),
                CallArgument(kind="class", symbol=_ORDER_WORKER),
            ],
        ),
        _site(
            _symbol(_CALLER, "run", "()V"),
            1,
            (_REGISTRAR, "register", _PAIR),
            arguments=[
                CallArgument(kind="string", value="billing"),
                CallArgument(kind="class", symbol=_BILLING_WORKER),
            ],
        ),
        # Several returns in one callee.
        _declared(_NAMES, "pick", _MAKES_STRING),
        _returns(_NAMES, "pick", _MAKES_STRING, 0, CallArgument(kind="string", value="orders")),
        _returns(
            _NAMES, "pick", _MAKES_STRING, 1, CallArgument(kind="string", value="orders-fast")
        ),
        _declared(_NAMES, "one", _MAKES_STRING),
        _returns(_NAMES, "one", _MAKES_STRING, 0, CallArgument(kind="string", value="solo")),
        _declared(_PUBLISHER, "publish", "()V"),
        _site(_symbol(_PUBLISHER, "publish", "()V"), 0, (_NAMES, "pick", _MAKES_STRING), result=5),
        _site(
            _symbol(_PUBLISHER, "publish", "()V"),
            1,
            _ONE_TARGET,
            kind="virtual",
            arguments=[CallArgument(kind="unresolved", source=5)],
        ),
        # The array rule (§1c), both ways round.
        _declared(_ARRAYS, "listed", "()V"),
        _site(
            _symbol(_ARRAYS, "listed", "()V"),
            0,
            _MANY_TARGET,
            kind="virtual",
            arguments=[
                CallArgument(
                    kind="array",
                    elements=[
                        CallArgument(kind="string", value="alpha"),
                        CallArgument(kind="string", value="beta"),
                    ],
                )
            ],
        ),
        _declared(_ARRAYS, "partly", "()V"),
        _site(
            _symbol(_ARRAYS, "partly", "()V"),
            0,
            _MANY_TARGET,
            kind="virtual",
            arguments=[
                CallArgument(
                    kind="array",
                    elements=[
                        CallArgument(kind="string", value="alpha"),
                        CallArgument(kind="unresolved"),
                    ],
                )
            ],
        ),
        # A value handed to a method that might mutate it, and the same shape
        # with nothing in between.
        _declared(_MUTATOR, "escaped", "()V"),
        _site(_symbol(_MUTATOR, "escaped", "()V"), 0, (_NAMES, "one", _MAKES_STRING), result=7),
        _site(
            _symbol(_MUTATOR, "escaped", "()V"),
            1,
            (_BUFFER, "append", _TAKES_STRING),
            kind="virtual",
            receiver=7,
            arguments=[CallArgument(kind="string", value="x")],
        ),
        _site(
            _symbol(_MUTATOR, "escaped", "()V"),
            2,
            _ONE_TARGET,
            kind="virtual",
            arguments=[CallArgument(kind="unresolved", source=7)],
        ),
        _declared(_MUTATOR, "kept", "()V"),
        _site(_symbol(_MUTATOR, "kept", "()V"), 0, (_NAMES, "one", _MAKES_STRING), result=7),
        _site(
            _symbol(_MUTATOR, "kept", "()V"),
            1,
            _ONE_TARGET,
            kind="virtual",
            arguments=[CallArgument(kind="unresolved", source=7)],
        ),
        # A binding whose WRITER is reported: the field is assigned from the
        # constructor's parameter 0, and two callers construct it with different
        # literals. The sixth edge crosses to both (spec 2026-10-18 §4 case 1 —
        # a closed set, so both ARE the answer).
        SymbolFact(
            document_id="doc_values",
            symbol=_symbol(_WRITTEN, "<init>", _TAKES_STRING),
            # A CONSTRUCTOR, not a method: `dispatch` resolves a `<init>` target against the
            # construct kind, so a constructor declared as a method is a body `call_edges`
            # cannot reach and `bound_to_parameter` never crosses into.
            construct_kind=ConstructKind.CONSTRUCTOR,
            enclosing=_MODULE + _WRITTEN,
            signature=Signature(
                parameters=[Parameter(name="value", type=TypeRef(symbol="java/lang/String#"))],
                returns=TypeRef(symbol="void#"),
            ),
            visibility="public",
        ),
        FieldWriteFact(
            document_id="doc_values",
            field=_WRITTEN + "held.",
            from_parameter=0,
            written_by=_symbol(_WRITTEN, "<init>", _TAKES_STRING),
        ),
        _declared(_WRITTEN, "send", "()V"),
        _site(
            _symbol(_WRITTEN, "send", "()V"),
            0,
            _ONE_TARGET,
            kind="virtual",
            arguments=[CallArgument(kind="field", symbol=_WRITTEN + "held.")],
        ),
        # A binding read.
        _declared(_BINDER, "read", "()V"),
        _site(
            _symbol(_BINDER, "read", "()V"),
            0,
            _ONE_TARGET,
            kind="virtual",
            arguments=[CallArgument(kind="field", symbol=_BINDER + "name.")],
        ),
        # A parameter nothing in this module binds.
        _declared(_ENTRY, "handle", _TAKES_STRING),
        _site(
            _symbol(_ENTRY, "handle", _TAKES_STRING),
            0,
            _ONE_TARGET,
            kind="virtual",
            arguments=[CallArgument(kind="parameter", value=0)],
        ),
        # A value from a body this workspace never read.
        _declared(_OUTSIDE, "use", "()V"),
        _site(
            _symbol(_OUTSIDE, "use", "()V"),
            0,
            (_PKG + "Third#", "make", _MAKES_STRING),
            kind="virtual",
            result=9,
        ),
        _site(
            _symbol(_OUTSIDE, "use", "()V"),
            1,
            _ONE_TARGET,
            kind="virtual",
            arguments=[CallArgument(kind="unresolved", source=9)],
        ),
        # The identity arm (spec §2, §0b): a producer this workspace never read, whose
        # own argument is what the value it handed back IS. Four methods, because the
        # entry that answers and the entries that must NOT are different facts.
        _declared(_IDENTIFIED, "use", "()V"),
        _site(
            _symbol(_IDENTIFIED, "use", "()V"),
            0,
            (_NAME, "of", _OF_TWO),
            arguments=[
                CallArgument(kind="string", value="a-project"),
                CallArgument(kind="string", value="raw-notify"),
            ],
            result=1,
        ),
        _site(
            _symbol(_IDENTIFIED, "use", "()V"),
            1,
            _ONE_TARGET,
            kind="virtual",
            arguments=[CallArgument(kind="unresolved", source=1)],
        ),
        # The same producer under a ONE-argument overload, which `arity` is the only
        # thing that tells from the two-argument one once owner and name agree.
        _declared(_IDENTIFIED, "overload", "()V"),
        _site(
            _symbol(_IDENTIFIED, "overload", "()V"),
            0,
            (_NAME, "of", _OF_ONE),
            arguments=[CallArgument(kind="string", value="sole")],
            result=1,
        ),
        _site(
            _symbol(_IDENTIFIED, "overload", "()V"),
            1,
            _ONE_TARGET,
            kind="virtual",
            arguments=[CallArgument(kind="unresolved", source=1)],
        ),
        # The SAME producer spelled as a varargs call, which is the other half of how a
        # topic list reaches the walk: `Subscriptions.topics("a", "b")` and
        # `Arrays.asList("a", "b")` compile to ONE array argument, where `List.of("a", "b")`
        # binds a fixed-arity overload and arrives as two. `all_strings` must answer both
        # alike, and it does it by resolving the one array SLOT and letting `_elements`
        # expand it — so this site is what proves no second expander was written.
        _declared(_IDENTIFIED, "varargs", "()V"),
        _site(
            _symbol(_IDENTIFIED, "varargs", "()V"),
            0,
            (_NAME, "of", _OF_VARARGS),
            arguments=[
                CallArgument(
                    kind="array",
                    elements=[
                        CallArgument(kind="string", value="first-topic"),
                        CallArgument(kind="string", value="second-topic"),
                    ],
                )
            ],
            result=1,
        ),
        _site(
            _symbol(_IDENTIFIED, "varargs", "()V"),
            1,
            _ONE_TARGET,
            kind="virtual",
            arguments=[CallArgument(kind="unresolved", source=1)],
        ),
        # The same producer HALF read, which is the one case where this walk and the
        # engines' shipped reader are known to disagree. No corpus in the estate has one —
        # measured, 0 of 27 — but `test_call_engines.py` pins the engine's answer, so the
        # walk's belongs beside it in writing rather than in a reviewer's head.
        _declared(_IDENTIFIED, "partial", "()V"),
        _site(
            _symbol(_IDENTIFIED, "partial", "()V"),
            0,
            (_NAME, "of", _OF_TWO),
            arguments=[
                CallArgument(kind="string", value="readable-topic"),
                CallArgument(kind="unresolved"),
            ],
            result=1,
        ),
        _site(
            _symbol(_IDENTIFIED, "partial", "()V"),
            1,
            _ONE_TARGET,
            kind="virtual",
            arguments=[CallArgument(kind="unresolved", source=1)],
        ),
        # The same producer called with NOTHING, which D00 §5 says is a fact rather than an
        # ambiguity — "called with no values" is a different statement from "the list could
        # not be read", and answering it `absent` is what keeps the two apart.
        _declared(_IDENTIFIED, "empty", "()V"),
        _site(
            _symbol(_IDENTIFIED, "empty", "()V"),
            0,
            (_NAME, "of", _OF_NONE),
            arguments=[],
            result=1,
        ),
        _site(
            _symbol(_IDENTIFIED, "empty", "()V"),
            1,
            _ONE_TARGET,
            kind="virtual",
            arguments=[CallArgument(kind="unresolved", source=1)],
        ),
        # An identified producer whose OWN identified argument came from another one:
        # two hops, which is one more than any hop declaration could ever express.
        _declared(_IDENTIFIED, "nested", "()V"),
        _site(
            _symbol(_IDENTIFIED, "nested", "()V"),
            0,
            (_NAME, "text", _OF_ONE),
            arguments=[CallArgument(kind="string", value="deep-notify")],
            result=1,
        ),
        _site(
            _symbol(_IDENTIFIED, "nested", "()V"),
            1,
            (_NAME, "of", _OF_TWO),
            arguments=[
                CallArgument(kind="string", value="a-project"),
                CallArgument(kind="unresolved", source=1),
            ],
            result=2,
        ),
        _site(
            _symbol(_IDENTIFIED, "nested", "()V"),
            2,
            _ONE_TARGET,
            kind="virtual",
            arguments=[CallArgument(kind="unresolved", source=2)],
        ),
        # A value BUILT here, by a producer the identity table names. Four methods, because
        # what the arm must reach, what it must refuse, and what it must not mistake for a
        # construction are different facts.
        _declared(_IDENTIFIED, "built", "()V"),
        _site(
            _symbol(_IDENTIFIED, "built", "()V"),
            0,
            (_NAME, "<init>", _CTOR_ONE),
            kind="special",
            arguments=[CallArgument(kind="string", value="built-notify")],
            receiver=1,
        ),
        _site(
            _symbol(_IDENTIFIED, "built", "()V"),
            1,
            _ONE_TARGET,
            kind="virtual",
            arguments=[CallArgument(kind="instance", source=1, symbol=_NAME)],
        ),
        # The same, under the constructor a `descriptor` turns away.
        _declared(_IDENTIFIED, "built_other", "()V"),
        _site(
            _symbol(_IDENTIFIED, "built_other", "()V"),
            0,
            (_NAME, "<init>", _CTOR_ARRAY),
            kind="special",
            arguments=[CallArgument(kind="string", value="other-notify")],
            receiver=1,
        ),
        _site(
            _symbol(_IDENTIFIED, "built_other", "()V"),
            1,
            _ONE_TARGET,
            kind="virtual",
            arguments=[CallArgument(kind="instance", source=1, symbol=_NAME)],
        ),
        # Built, then written to before it is used.
        _declared(_IDENTIFIED, "mutated", "()V"),
        _site(
            _symbol(_IDENTIFIED, "mutated", "()V"),
            0,
            (_NAME, "<init>", _CTOR_ONE),
            kind="special",
            arguments=[CallArgument(kind="string", value="mutated-notify")],
            receiver=1,
        ),
        _site(
            _symbol(_IDENTIFIED, "mutated", "()V"),
            1,
            (_NAME, "touch", _TOUCH),
            kind="virtual",
            receiver=1,
        ),
        _site(
            _symbol(_IDENTIFIED, "mutated", "()V"),
            2,
            _ONE_TARGET,
            kind="virtual",
            arguments=[CallArgument(kind="instance", source=1, symbol=_NAME)],
        ),
        # A value this method did NOT build — held elsewhere, and merely CALLED here. The
        # `RawJmsBridge` shape: `session.createProducer(session.createQueue("raw-audit"))`.
        _declared(_IDENTIFIED, "borrowed", "()V"),
        _site(
            _symbol(_IDENTIFIED, "borrowed", "()V"),
            0,
            (_NAME, "of", _OF_ONE),
            kind="virtual",
            arguments=[CallArgument(kind="string", value="not-what-the-holder-is")],
            result=2,
            receiver=1,
        ),
        _site(
            _symbol(_IDENTIFIED, "borrowed", "()V"),
            1,
            _ONE_TARGET,
            kind="virtual",
            arguments=[CallArgument(kind="unresolved", source=1)],
        ),
        # **The seventh edge: a lambda's CAPTURE** (`OI-150`). `install` captures a literal
        # into the synthetic `body`, and `body`'s parameter 0 IS that capture. The two facts
        # that say so are the capture site — whose arguments are the captured values, in
        # order — and the `lambda` entry naming the body it created, which carries the value
        # the capture site produced.
        _declared(_CLOSING, "install", "()V"),
        _site(
            _symbol(_CLOSING, "install", "()V"),
            0,
            ("java/lang/invoke/LambdaMetafactory#", "test", _MAKES_OBJECT),
            arguments=[CallArgument(kind="string", value="closed-over")],
            result=5,
        ),
        _site(
            _symbol(_CLOSING, "install", "()V"),
            1,
            _ONE_TARGET,
            kind="virtual",
            arguments=[
                CallArgument(
                    kind="lambda",
                    # The entry names the body as the extractor does: BARE, which is the
                    # descriptor half of its real symbol and not a name invented here.
                    symbol=method_descriptor(_CLOSING, "body", _TAKES_STRING),
                    captures=1,
                    source=5,
                )
            ],
        ),
        # The body reads its capture and hands it on. Nothing calls `body`: the framework
        # invokes it, which is exactly why the capture is the only edge that reaches it.
        _declared(_CLOSING, "body", _TAKES_STRING),
        _void(_CLOSING, "body", _TAKES_STRING),
        _site(
            _symbol(_CLOSING, "body", _TAKES_STRING),
            0,
            _ONE_TARGET,
            kind="virtual",
            arguments=[CallArgument(kind="parameter", value=0)],
        ),
        # A value rendered into a concat: `Name#of("raw-notify")` produces something an
        # identity entry can name, `String.valueOf` renders it, and the text is joined.
        _declared(_RENDERED, "publish", "()V"),
        _site(
            _symbol(_RENDERED, "publish", "()V"),
            0,
            (_NAME, "of", _OF_ONE),
            arguments=[CallArgument(kind="string", value="raw-notify")],
            result=5,
        ),
        _site(
            _symbol(_RENDERED, "publish", "()V"),
            1,
            ("java/lang/String#", "valueOf", "(Ljava/lang/Object;)Ljava/lang/String;"),
            arguments=[CallArgument(kind="unresolved", source=5)],
            result=9,
        ),
        _site(
            _symbol(_RENDERED, "publish", "()V"),
            2,
            ("java/lang/invoke/StringConcatFactory#", "makeConcatWithConstants", _MAKES_OBJECT),
            arguments=[CallArgument(kind="unresolved", source=9)],
            result=12,
        ),
        _site(
            _symbol(_RENDERED, "publish", "()V"),
            3,
            _ONE_TARGET,
            kind="virtual",
            arguments=[CallArgument(kind="concat", source=12, value="{}/orders")],
        ),
        # A binding written from a CONSTANT the walk has no literal kind for.
        _declared(_UNREADABLE, "read", "()V"),
        _site(
            _symbol(_UNREADABLE, "read", "()V"),
            0,
            _ONE_TARGET,
            kind="virtual",
            arguments=[CallArgument(kind="field", symbol=_UNREADABLE + "held.")],
        ),
        FieldWriteFact(
            document_id="doc_values",
            field=_UNREADABLE + "held.",
            value=CallArgument(kind="class", symbol="com/acme/orders/values/Order#"),
            written_by=_symbol(_UNREADABLE, "<init>", "()V"),
        ),
        # Values the grammar names nothing for.
        _declared(_UNREAD, "use", "()V"),
        _site(
            _symbol(_UNREAD, "use", "()V"),
            0,
            _ONE_TARGET,
            kind="virtual",
            arguments=[CallArgument(kind="unresolved")],
        ),
        _site(
            _symbol(_UNREAD, "use", "()V"),
            1,
            _ONE_TARGET,
            kind="virtual",
            arguments=[
                CallArgument(kind="lambda", symbol=_UNREAD + "body(sig_0).", captures=0, source=3)
            ],
        ),
        _site(
            _symbol(_UNREAD, "use", "()V"),
            2,
            _ONE_TARGET,
            kind="virtual",
            arguments=[CallArgument(kind="null")],
        ),
        # An array the extractor could NOT read end to end: no element list at all, which
        # is the other half of D00 §5's sentence and stays a reason.
        _declared(_ARRAYS, "unread", "()V"),
        _site(
            _symbol(_ARRAYS, "unread", "()V"),
            0,
            _MANY_TARGET,
            kind="virtual",
            arguments=[CallArgument(kind="array")],
        ),
        # A value produced by a site whose body WAS read and whose returns answer for
        # nothing: a dispatch the bootstrap names, which `return_flows` refuses outright.
        _declared(_UNREAD, "body", _MAKES_STRING),
        _returns(_UNREAD, "body", _MAKES_STRING, 0, CallArgument(kind="string", value="made")),
        _declared(_UNREAD, "made", "()V"),
        CallSiteFact(
            document_id="doc_values",
            caller=_symbol(_UNREAD, "made", "()V"),
            target=CallTarget(
                owner="java/util/function/Supplier#",
                name="get",
                descriptor="()Ljava/lang/Object;",
            ),
            invoke_kind="dynamic",
            ordinal=0,
            result=61,
            implementation=method_descriptor(_UNREAD, "body", _MAKES_STRING),
        ),
        _site(
            _symbol(_UNREAD, "made", "()V"),
            1,
            _ONE_TARGET,
            kind="virtual",
            arguments=[CallArgument(kind="unresolved", source=61)],
        ),
        # A value MUTATED inside the callee before the `return`, and its twin that is not.
        _declared(_NAMES, "built", _MAKES_STRING),
        _site(
            _symbol(_NAMES, "built", _MAKES_STRING), 0, (_NAMES, "one", _MAKES_STRING), result=21
        ),
        _site(
            _symbol(_NAMES, "built", _MAKES_STRING),
            1,
            (_BUFFER, "append", _TAKES_STRING),
            kind="virtual",
            receiver=21,
            arguments=[CallArgument(kind="string", value="x")],
        ),
        _returns(_NAMES, "built", _MAKES_STRING, 0, CallArgument(kind="unresolved", source=21)),
        _declared(_NAMES, "passed", _MAKES_STRING),
        _site(
            _symbol(_NAMES, "passed", _MAKES_STRING), 0, (_NAMES, "one", _MAKES_STRING), result=41
        ),
        _returns(_NAMES, "passed", _MAKES_STRING, 0, CallArgument(kind="unresolved", source=41)),
        _declared(_MUTATOR, "reads", "()V"),
        _site(_symbol(_MUTATOR, "reads", "()V"), 0, (_NAMES, "built", _MAKES_STRING), result=31),
        _site(
            _symbol(_MUTATOR, "reads", "()V"),
            1,
            _ONE_TARGET,
            kind="virtual",
            arguments=[CallArgument(kind="unresolved", source=31)],
        ),
        _declared(_MUTATOR, "quiet", "()V"),
        _site(_symbol(_MUTATOR, "quiet", "()V"), 0, (_NAMES, "passed", _MAKES_STRING), result=51),
        _site(
            _symbol(_MUTATOR, "quiet", "()V"),
            1,
            _ONE_TARGET,
            kind="virtual",
            arguments=[CallArgument(kind="unresolved", source=51)],
        ),
        # A zero-length varargs call: the empty element list is the FACT (D00 §5).
        _declared(_ARRAYS, "none", "()V"),
        _site(
            _symbol(_ARRAYS, "none", "()V"),
            0,
            _MANY_TARGET,
            kind="virtual",
            arguments=[CallArgument(kind="array", elements=[])],
        ),
        # Two methods that hand each other the same parameter.
        _declared(_LOOP, "ping", _TAKES_STRING),
        _void(_LOOP, "ping", _TAKES_STRING),
        _declared(_LOOP, "pong", _TAKES_STRING),
        _void(_LOOP, "pong", _TAKES_STRING),
        _site(
            _symbol(_LOOP, "ping", _TAKES_STRING),
            0,
            (_LOOP, "pong", _TAKES_STRING),
            arguments=[CallArgument(kind="parameter", value=0)],
        ),
        _site(
            _symbol(_LOOP, "ping", _TAKES_STRING),
            1,
            _ONE_TARGET,
            kind="virtual",
            arguments=[CallArgument(kind="parameter", value=0)],
        ),
        _site(
            _symbol(_LOOP, "pong", _TAKES_STRING),
            0,
            (_LOOP, "ping", _TAKES_STRING),
            arguments=[CallArgument(kind="parameter", value=0)],
        ),
        # An address the code assembles.
        _declared(_ASSEMBLER, "call", "()V"),
        _site(
            _symbol(_ASSEMBLER, "call", "()V"),
            0,
            _ONE_TARGET,
            kind="virtual",
            arguments=[CallArgument(kind="concat", value="/orders/{}", source=4)],
        ),
        # A producer whose identity is an AUTHORITY, joined to a path — the shape ruling 2
        # needs (`OI-142`). The hole is at the start, so the join must say where the
        # authority ends rather than running the two together.
        _declared(_AUTHORITY_CHAIN, "call", "()V"),
        _site(
            _symbol(_AUTHORITY_CHAIN, "call", "()V"),
            0,
            (_NAME, "of", _OF_TWO),
            arguments=[
                CallArgument(kind="string", value="a-project"),
                CallArgument(kind="string", value="one-service"),
            ],
            result=70,
        ),
        # The concat's `source` names the INDY, not the producer — which is the real
        # bytecode shape: javac emits one `invokedynamic` whose own argument is the
        # operand. A fixture pointing the concat straight at the producer made `_joined`
        # read that producer's TWO arguments as two operands against a one-hole template,
        # and the count check refused it. Correct behaviour, wrong fixture.
        _site(
            _symbol(_AUTHORITY_CHAIN, "call", "()V"),
            1,
            _ONE_TARGET,
            kind="virtual",
            result=71,
            arguments=[CallArgument(kind="unresolved", source=70)],
        ),
        _site(
            _symbol(_AUTHORITY_CHAIN, "call", "()V"),
            2,
            _ONE_TARGET,
            kind="virtual",
            arguments=[CallArgument(kind="concat", value="{}/owners", source=71)],
        ),
        # A producer the table identifies, then a call ON its result that hands back
        # something still standing for the same thing — the `from_receiver` chain
        # (`OI-142`). Two methods: one where the producer's identity is SINGLE-VALUED and
        # one where it ENUMERATES, because the gate between them is the safety argument.
        _declared(_PRESERVED, "single", "()V"),
        _site(
            _symbol(_PRESERVED, "single", "()V"),
            0,
            (_NAME, "of", _OF_TWO),
            arguments=[
                CallArgument(kind="string", value="a-project"),
                CallArgument(kind="string", value="one-service"),
            ],
            result=50,
        ),
        _site(
            _symbol(_PRESERVED, "single", "()V"),
            1,
            _ONE_TARGET,
            kind="virtual",
            receiver=50,
            result=51,
            arguments=[CallArgument(kind="int", value=0)],
        ),
        _site(
            _symbol(_PRESERVED, "single", "()V"),
            2,
            _ONE_TARGET,
            kind="virtual",
            arguments=[CallArgument(kind="unresolved", source=51)],
        ),
        _declared(_PRESERVED, "enumerating", "()V"),
        _site(
            _symbol(_PRESERVED, "enumerating", "()V"),
            0,
            (_NAME, "of", _OF_TWO),
            arguments=[
                CallArgument(kind="string", value="topic-a"),
                CallArgument(kind="string", value="topic-b"),
            ],
            result=60,
        ),
        _site(
            _symbol(_PRESERVED, "enumerating", "()V"),
            1,
            _ONE_TARGET,
            kind="virtual",
            receiver=60,
            result=61,
            arguments=[CallArgument(kind="int", value=0)],
        ),
        _site(
            _symbol(_PRESERVED, "enumerating", "()V"),
            2,
            _ONE_TARGET,
            kind="virtual",
            arguments=[CallArgument(kind="unresolved", source=61)],
        ),
        # An assembled address whose every operand IS a source literal — the shape
        # ruling 1 (2026-10-17) joins. The producing site is the concat itself, and its
        # own arguments are the operands.
        _declared(_JOINER, "call", "()V"),
        _site(
            _symbol(_JOINER, "call", "()V"),
            0,
            _ONE_TARGET,
            kind="virtual",
            result=40,
            arguments=[CallArgument(kind="string", value="http://host/")],
        ),
        _site(
            _symbol(_JOINER, "call", "()V"),
            1,
            _ONE_TARGET,
            kind="virtual",
            arguments=[CallArgument(kind="concat", value="{}orders", source=40)],
        ),
        # Two holes, both literals: the template is filled in ORDER, not by chance.
        _declared(_TWO_HOLES, "call", "()V"),
        _site(
            _symbol(_TWO_HOLES, "call", "()V"),
            0,
            _ONE_TARGET,
            kind="virtual",
            result=41,
            arguments=[
                CallArgument(kind="string", value="alpha"),
                CallArgument(kind="string", value="omega"),
            ],
        ),
        _site(
            _symbol(_TWO_HOLES, "call", "()V"),
            1,
            _ONE_TARGET,
            kind="virtual",
            arguments=[CallArgument(kind="concat", value="/{}/middle/{}", source=41)],
        ),
        # One operand a literal, the other a PARAMETER — "anything that changes at
        # runtime" in the ruling's own words, so nothing joins.
        _declared(_HALF_JOINER, "call", _TAKES_STRING),
        _site(
            _symbol(_HALF_JOINER, "call", _TAKES_STRING),
            0,
            _ONE_TARGET,
            kind="virtual",
            result=42,
            arguments=[
                CallArgument(kind="string", value="http://host/"),
                CallArgument(kind="parameter", value=0),
            ],
        ),
        _site(
            _symbol(_HALF_JOINER, "call", _TAKES_STRING),
            1,
            _ONE_TARGET,
            kind="virtual",
            arguments=[CallArgument(kind="concat", value="{}orders/{}", source=42)],
        ),
        # A receiver produced by a call, which is a slot like any other.
        _declared(_FACTORY, "make", _MAKES_OBJECT),
        _returns(
            _FACTORY,
            "make",
            _MAKES_OBJECT,
            0,
            CallArgument(kind="instance", symbol=_REGISTRY_IMPL),
        ),
        _declared(_RECEIVING, "use", "()V"),
        _site(_symbol(_RECEIVING, "use", "()V"), 0, (_FACTORY, "make", _MAKES_OBJECT), result=3),
        _site(
            _symbol(_RECEIVING, "use", "()V"),
            1,
            _ONE_TARGET,
            kind="virtual",
            receiver=3,
            arguments=[CallArgument(kind="string", value="x")],
        ),
        # Four methods deep, because there is no cap (§3a).
        _declared(_DEEP, "go", "()V"),
        _declared(_DEEP, "one", _TAKES_STRING),
        _void(_DEEP, "one", _TAKES_STRING),
        _declared(_DEEP, "two", _TAKES_STRING),
        _void(_DEEP, "two", _TAKES_STRING),
        _declared(_DEEP, "three", _TAKES_STRING),
        _void(_DEEP, "three", _TAKES_STRING),
        _site(
            _symbol(_DEEP, "go", "()V"),
            0,
            (_DEEP, "one", _TAKES_STRING),
            arguments=[CallArgument(kind="string", value="deep")],
        ),
        _site(
            _symbol(_DEEP, "one", _TAKES_STRING),
            0,
            (_DEEP, "two", _TAKES_STRING),
            arguments=[CallArgument(kind="parameter", value=0)],
        ),
        _site(
            _symbol(_DEEP, "two", _TAKES_STRING),
            0,
            (_DEEP, "three", _TAKES_STRING),
            arguments=[CallArgument(kind="parameter", value=0)],
        ),
        _site(
            _symbol(_DEEP, "three", _TAKES_STRING),
            0,
            _ONE_TARGET,
            kind="virtual",
            arguments=[CallArgument(kind="parameter", value=0)],
        ),
        # One position reached through two different wrappers — the shape that makes the
        # memo's KEY observable. `mid` is called by `left` and by `right`, both of which
        # `top` calls, so `top`'s own parameter is resolved twice: once on the path
        # through `left` and once on the path through `right`.
        _declared(_DIAMOND, "start", "()V"),
        _declared(_DIAMOND, "top", _TAKES_STRING),
        _void(_DIAMOND, "top", _TAKES_STRING),
        _declared(_DIAMOND, "left", _TAKES_STRING),
        _void(_DIAMOND, "left", _TAKES_STRING),
        _declared(_DIAMOND, "right", _TAKES_STRING),
        _void(_DIAMOND, "right", _TAKES_STRING),
        _declared(_DIAMOND, "mid", _TAKES_STRING),
        _void(_DIAMOND, "mid", _TAKES_STRING),
        _site(
            _symbol(_DIAMOND, "start", "()V"),
            0,
            (_DIAMOND, "top", _TAKES_STRING),
            arguments=[CallArgument(kind="string", value="alpha")],
        ),
        _site(
            _symbol(_DIAMOND, "top", _TAKES_STRING),
            0,
            (_DIAMOND, "left", _TAKES_STRING),
            arguments=[CallArgument(kind="parameter", value=0)],
        ),
        _site(
            _symbol(_DIAMOND, "top", _TAKES_STRING),
            1,
            (_DIAMOND, "right", _TAKES_STRING),
            arguments=[CallArgument(kind="parameter", value=0)],
        ),
        _site(
            _symbol(_DIAMOND, "left", _TAKES_STRING),
            0,
            (_DIAMOND, "mid", _TAKES_STRING),
            arguments=[CallArgument(kind="parameter", value=0)],
        ),
        _site(
            _symbol(_DIAMOND, "right", _TAKES_STRING),
            0,
            (_DIAMOND, "mid", _TAKES_STRING),
            arguments=[CallArgument(kind="parameter", value=0)],
        ),
        _site(
            _symbol(_DIAMOND, "mid", _TAKES_STRING),
            0,
            _ONE_TARGET,
            kind="virtual",
            arguments=[CallArgument(kind="parameter", value=0)],
        ),
    ]
    # --- Capability 9.19: a merged value (spec 2026-10-21 merged values) ------------------
    # `Wrapper#send(path)`: `if (path.startsWith("/")) path = path.substring(1); one(path)`.
    # Site 0 is the `substring` call ON the parameter (its result is value 10); site 1 is the
    # consumer, whose argument is the MERGE of the parameter and that result — Apollo's
    # `RetryableRestTemplate#execute`, as the extractor now writes it (CP-41). Two callers
    # hand `send` their literals, one with the slash the wrapper strips and one without.
    # `Forked` holds the two merges that have NO root: two literals, and a parameter beside a
    # call that is not on it.
    facts += [
        _type(_WRAPPER),
        _type(_FORKED),
        _declared(_WRAPPER, "send", _TAKES_STRING),
        _void(_WRAPPER, "send", _TAKES_STRING),
        _site(
            _symbol(_WRAPPER, "send", _TAKES_STRING),
            0,
            _SUBSTRING,
            kind="virtual",
            receiver_parameter=0,
            result=10,
            arguments=[CallArgument(kind="int", value=1)],
        ),
        _site(
            _symbol(_WRAPPER, "send", _TAKES_STRING),
            1,
            _ONE_TARGET,
            kind="virtual",
            arguments=[
                CallArgument(
                    kind="merge",
                    candidates=[
                        CallArgument(kind="parameter", value=0),
                        CallArgument(kind="unresolved", source=10),
                    ],
                )
            ],
        ),
        _declared(_WRAPPER, "ledger", "()V"),
        _site(
            _symbol(_WRAPPER, "ledger", "()V"),
            0,
            (_WRAPPER, "send", _TAKES_STRING),
            kind="virtual",
            arguments=[CallArgument(kind="string", value="/a")],
        ),
        _declared(_WRAPPER, "entry", "()V"),
        _site(
            _symbol(_WRAPPER, "entry", "()V"),
            0,
            (_WRAPPER, "send", _TAKES_STRING),
            kind="virtual",
            arguments=[CallArgument(kind="string", value="b")],
        ),
        _declared(_FORKED, "pick", _TAKES_STRING),
        _site(
            _symbol(_FORKED, "pick", _TAKES_STRING),
            0,
            _ONE_TARGET,
            kind="virtual",
            arguments=[
                CallArgument(
                    kind="merge",
                    candidates=[
                        CallArgument(kind="string", value="/a"),
                        CallArgument(kind="string", value="/b"),
                    ],
                )
            ],
        ),
        _declared(_FORKED, "other", _TAKES_STRING),
        _site(
            _symbol(_FORKED, "other", _TAKES_STRING),
            0,
            (_NAMES, "make", _MAKES_STRING),
            result=20,
        ),
        _site(
            _symbol(_FORKED, "other", _TAKES_STRING),
            1,
            _ONE_TARGET,
            kind="virtual",
            arguments=[
                CallArgument(
                    kind="merge",
                    candidates=[
                        CallArgument(kind="parameter", value=0),
                        CallArgument(kind="unresolved", source=20),
                    ],
                )
            ],
        ),
    ]
    return facts


@pytest.fixture(scope="module")
def walked(tmp_path_factory: pytest.TempPathFactory) -> DuckDbWorkspace:
    """The workspace, with the two derived tables the edge query reads built by
    the passes that own them. Handed back OPEN — every test reads through it."""
    tmp_path = tmp_path_factory.mktemp("values")
    facts = tmp_path / "facts"
    write_fact_file(facts / "values.jsonl", _document(), _facts())
    write_fixture_module_fact(facts)
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(facts)
    record_return_flows(workspace)
    record_call_edges(workspace)
    return workspace


# The canonical compiler-emitted default-argument bridge, from `test_effective_calls.py`'s
# own fixture: an INSTANCE `greet(String, boolean)` plus the static
# `greet$default(Api, String, boolean, int, Object)` the compiler emits beside it. Its own
# workspace, because what it pins is a disagreement between two READINGS of one site, and
# a fixture that also held ordinary sites would let the walk pass on those alone.
_API = _PKG + "Api#"
_GREET = "(Ljava/lang/String;Z)V"
_GREET_BRIDGE = "(Lcom/acme/orders/values/Api;Ljava/lang/String;ZILjava/lang/Object;)V"
_HANDLER = _PKG + "Handler#"
_HANDLE = "(Lcom/acme/orders/values/Api;)V"
# The same bridge shape over a method that HANDS BACK its own parameter, for the forward
# crossing: the walk descends through the bridge site into `label`'s return, and the frame
# it pushes has to be the projected row too.
_LABEL = "(Ljava/lang/String;)Ljava/lang/String;"
_LABEL_BRIDGE = (
    "(Lcom/acme/orders/values/Api;Ljava/lang/String;ILjava/lang/Object;)Ljava/lang/String;"
)
_READ = "()V"


def _bridge_facts(mask: int) -> list[Fact]:
    """`api.greet("y")` as the compiler writes it: the receiver, the arguments the caller
    supplied, the mask saying which were left to their defaults, and the marker."""
    return [
        _type(_API),
        _type(_HANDLER),
        _declared(_API, "greet", _GREET),
        _void(_API, "greet", _GREET),
        SymbolFact(
            document_id="doc_values",
            symbol=_symbol(_API, "greet$default", _GREET_BRIDGE),
            construct_kind=ConstructKind.METHOD,
            enclosing=_MODULE + _API,
            modifiers={"static": True, "synthetic": True},
            bridge_of="greet",
        ),
        _declared(_HANDLER, "handle", _HANDLE),
        _site(
            _symbol(_HANDLER, "handle", _HANDLE),
            0,
            (_API, "greet$default", _GREET_BRIDGE),
            arguments=[
                # The receiver the caller pushed into slot 0 — a constructed instance, so
                # a walk that reads this slot as parameter 0 answers a TYPE SYMBOL, which
                # is the fabrication the fix-round review measured.
                CallArgument(kind="instance", symbol=_API, source=70),
                CallArgument(kind="string", value="y"),
                CallArgument(kind="boolean", value=False),
                CallArgument(kind="int", value=mask),
                CallArgument(kind="null"),
            ],
        ),
        # `label(String)` hands its own parameter back, called through its own bridge.
        _declared(_API, "label", _LABEL),
        _returns(_API, "label", _LABEL, 0, CallArgument(kind="parameter", value=0)),
        SymbolFact(
            document_id="doc_values",
            symbol=_symbol(_API, "label$default", _LABEL_BRIDGE),
            construct_kind=ConstructKind.METHOD,
            enclosing=_MODULE + _API,
            modifiers={"static": True, "synthetic": True},
            bridge_of="label",
        ),
        _declared(_HANDLER, "read", _READ),
        _site(
            _symbol(_HANDLER, "read", _READ),
            0,
            (_API, "label$default", _LABEL_BRIDGE),
            result=80,
            arguments=[
                CallArgument(kind="instance", symbol=_API, source=70),
                CallArgument(kind="string", value="z"),
                CallArgument(kind="int", value=0),
                CallArgument(kind="null"),
            ],
        ),
        _site(
            _symbol(_HANDLER, "read", _READ),
            1,
            _ONE_TARGET,
            kind="virtual",
            arguments=[CallArgument(kind="unresolved", source=80)],
        ),
        # Two sites inside `greet`, one reading each of its own parameters.
        _site(
            _symbol(_API, "greet", _GREET),
            0,
            _ONE_TARGET,
            kind="virtual",
            arguments=[CallArgument(kind="parameter", value=0)],
        ),
        _site(
            _symbol(_API, "greet", _GREET),
            1,
            _ONE_TARGET,
            kind="virtual",
            arguments=[CallArgument(kind="parameter", value=1)],
        ),
    ]


@pytest.fixture(scope="module")
def bridged(tmp_path_factory: pytest.TempPathFactory) -> dict[int, DuckDbWorkspace]:
    """One workspace per mask: 0 (the caller supplied both) and 2 (it left the second to
    its default). Both handed back open — the tests read through them."""
    built: dict[int, DuckDbWorkspace] = {}
    for mask in (0, 2):
        tmp_path = tmp_path_factory.mktemp(f"values_bridge_{mask}")
        facts = tmp_path / "facts"
        write_fact_file(facts / "bridge.jsonl", _document(), _bridge_facts(mask))
        write_fixture_module_fact(facts)
        workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
        workspace.load_facts(facts)
        record_return_flows(workspace)
        record_call_edges(workspace)
        built[mask] = workspace
    return built


def _at(workspace: DuckDbWorkspace, method: str, ordinal: int) -> dict[str, Any]:
    rows = [
        row
        for row in workspace.query("call_sites")
        if row["caller"] == method and row["ordinal"] == ordinal
    ]
    assert len(rows) == 1, f"no single site at {method}@{ordinal}"
    return dict(rows[0])


def _bindings(workspace: DuckDbWorkspace, method: str, ordinal: int) -> list[Binding]:
    return resolve_site(workspace, _at(workspace, method, ordinal))


def _reasons(bindings: list[Binding], slot: int | str = 0) -> list[str | None]:
    return [binding.slots[slot].reason for binding in bindings]


def test_a_helper_called_twice_yields_two_paths_not_four_combinations(walked):
    """**Spec §0c M-1, and the reason the primitive is a path.** `register("orders",
    OrderWorker)` and `register("billing", BillingWorker)` reach ONE site inside
    `register`. Resolving its two slots INDEPENDENTLY yields 2x2 = four pairs, two of
    which no code path produces — recorded at `resolved` and indistinguishable from an
    observation, which is the cardinal sin this repository exists not to commit.

    Per path it is two bindings, and each binding's slots agree because they came from
    the same caller. Memoise on the position alone and this test fails with four rows;
    nothing else in this file would notice."""
    bindings = _bindings(walked, _symbol(_REGISTRAR, "register", _PAIR), 0)
    assert [(b.slots[0].value, b.slots[1].value) for b in bindings] == [
        ("orders", _ORDER_WORKER),
        ("billing", _BILLING_WORKER),
    ]


def test_each_binding_names_the_calling_context_it_came_from(walked):
    """§1b: a binding carries the path, so a reader can say WHICH call produced the row
    — and two bindings that differ only in their values would be two rows nobody can
    tell apart when one of them turns out to be wrong."""
    bindings = _bindings(walked, _symbol(_REGISTRAR, "register", _PAIR), 0)
    assert [b.path for b in bindings] == [
        (f"{_symbol(_CALLER, 'run', '()V')}@0",),
        (f"{_symbol(_CALLER, 'run', '()V')}@1",),
    ]


def test_several_returns_in_a_callee_are_several_paths(walked):
    """`method_return` keeps several returns as several facts on the stated ground that
    picking one would be a fact about code that may never run. The walk keeps them as
    several bindings for the same reason (§1c)."""
    bindings = _bindings(walked, _symbol(_PUBLISHER, "publish", "()V"), 1)
    assert sorted(str(b.slots[0].value) for b in bindings) == ["orders", "orders-fast"]
    assert len({b.path for b in bindings}) == 2


def test_an_array_whose_every_element_is_written_branches_into_elements(walked):
    """The enumerable half of §1c's rule — D00's array rule, generalised: every index a
    distinct written constant yields elements, and each element is its own path.

    Paired with the test below on purpose (GUIDELINES §10): a walk that answered
    `non_enumerable` for every array would pass that one and fail this one."""
    bindings = _bindings(walked, _symbol(_ARRAYS, "listed", "()V"), 0)
    assert [b.slots[0].value for b in bindings] == ["alpha", "beta"]


def test_an_array_with_one_unnameable_element_keeps_the_others(walked):
    """**An element with no name costs one trailing unresolved, not the whole array**
    (ruled 2026-10-16). The shape here is the one the facts can state — an array the
    extractor READ whose second element it could not name — so membership is known and
    only the name is missing. `alpha` is read from bytecode, and dropping it would exclude
    a destination on inference (§8, "exclude only on proof").

    `non_enumerable` is about MEMBERSHIP, and the case that still earns it has its own test
    below: an array the extractor could not read at all reports no `elements` and answers
    `non_enumerable`. A loop-built or branch-merged value never arrives as an array either
    — the facts carry no "this was a loop" claim — so it is an unread argument answering
    `not_readable`.

    This pin asserted one bare `non_enumerable` until the ruling. It moved together with
    `_all_arguments`' equivalent, which is what keeps the two spellings of one topic list
    answering alike — and what makes the walk agree with `shapes/arguments.channels_of`,
    whose contract has always been "one tuple per readable element, plus one trailing
    unresolved, never one per failure"."""
    bindings = _bindings(walked, _symbol(_ARRAYS, "partly", "()V"), 0)
    assert [(b.slots[0].value, b.slots[0].reason) for b in bindings] == [
        ("alpha", None),
        (None, "not_readable"),
    ]


def test_a_value_mutated_inside_the_callee_before_its_return_is_unresolved_escapes(walked):
    """**`escapes` has to survive a return crossing** (fix round, 2026-09-23). `built()`
    produces a value, calls a method ON it, and returns it; the caller reads that return.
    Byte for byte this is the shape `_through`'s own docstring names —
    `result.setFilename(x); return result;` — one method along, and skipping the check
    there answered the PRE-mutation literal, which is a stale value asserted at `resolved`.

    A return has no comparable use point (`method_returns.ordinal` numbers return
    instructions, not call sites), so the whole class is refused: any call on the value
    after its producer. MEASURED across every fixture with compiled classes, 112 of 836
    returned values that carry a source — 13.4%, and 33 of 413 on `orders-service`."""
    bindings = _bindings(walked, _symbol(_MUTATOR, "reads", "()V"), 1)
    assert _reasons(bindings) == ["escapes"]


def test_a_value_the_callee_only_passes_through_still_resolves(walked):
    """The positive paired with the class refusal above, and the reason it is worth
    measuring rather than assuming: `passed()` produces the same value and hands it back
    untouched. A refusal for every returned value would pass the near-miss and quietly
    stop resolving anything that crosses a return."""
    bindings = _bindings(walked, _symbol(_MUTATOR, "quiet", "()V"), 1)
    assert [b.slots[0].value for b in bindings] == ["solo"]


def test_an_array_the_extractor_could_not_read_is_non_enumerable_not_absent(walked):
    """The other half of D00 §5's sentence, and the near-miss for `absent`: an array with
    no element list at all could not be read, which is a different statement from "called
    with no values". Without this the two halves collapse into one answer."""
    bindings = _bindings(walked, _symbol(_ARRAYS, "unread", "()V"), 0)
    assert _reasons(bindings) == ["non_enumerable"]


def test_a_value_from_a_body_that_was_read_but_answers_for_nothing_is_not_readable(walked):
    """The `external`/`not_readable` discrimination from the other side, and the one
    `not_readable` branch that real facts reach through the walk rather than through a
    guard: the body IS named — `call_edges` took the hop — but `return_flows` refuses a
    site whose dispatch the bootstrap names, so nothing answers for the value. "We cannot
    see it" and "we can see it and it names no value" must not collapse."""
    bindings = _bindings(walked, _symbol(_UNREAD, "made", "()V"), 1)
    assert _reasons(bindings) == ["not_readable"]
    assert any(
        row["ordinal"] == 0 and row["callee"] is not None
        for row in walked.query("call_edges")
        if row["caller"] == _symbol(_UNREAD, "made", "()V")
    ), "the fixture must name a body, or this tests `external` by accident"


def test_a_value_a_method_might_have_mutated_before_use_is_unresolved_escapes(walked):
    """§1d's `escapes`. Between the call that produced the value and the call that uses
    it there is a call ON the value, and nothing in the facts says what it wrote."""
    bindings = _bindings(walked, _symbol(_MUTATOR, "escaped", "()V"), 2)
    assert _reasons(bindings) == ["escapes"]


def test_the_same_chain_with_nothing_in_between_resolves(walked):
    """The positive paired with `escapes` (GUIDELINES §10): the rule declines above and
    must still fire here, or a walk that answered `escapes` for every produced value
    would look correct all the way down."""
    bindings = _bindings(walked, _symbol(_MUTATOR, "kept", "()V"), 1)
    assert [b.slots[0].value for b in bindings] == ["solo"]


def test_a_binding_read_whose_writer_nobody_reported_is_unresolved_no_writer(walked):
    """§1d's `no_writer`, and its meaning is NARROWER since the sixth edge landed
    (2026-10-18): not "the walk cannot follow a writer" but "no write of this binding was
    reported". `Binder#name` is assigned nowhere this fact set describes — the remaining
    unreported shapes are a literal, a call's result and a static initialiser (CP-33 rows
    2, 6, 7, 8), plus a container writing the field reflectively, which no bytecode shows.
    """
    bindings = _bindings(walked, _symbol(_BINDER, "read", "()V"), 0)
    assert _reasons(bindings) == ["no_writer"]


@pytest.mark.pins("values.a-field-read-reaches-the-value-written-into-it")
def test_a_binding_read_follows_the_writer_the_facts_name(walked):
    """**THE SIXTH EDGE** (spec `2026-10-18-the-sixth-edge-design.md`). `Written#held` is
    assigned from its constructor's parameter 0, the `field_write` fact names that
    constructor, and the walk now crosses into it instead of stopping.

    **What this pins is the HOP, and the reason word is how it is visible here.** Nothing
    in this fact set calls `Written#<init>`, so the crossing lands on §4's case 2 — the
    user's own words, *"if there is no call to this function, we don't know what are
    possible values"* — and the walk's word for that is `external`. With the edge gone the
    answer is `no_writer`, which says something different: not "the values come from
    outside" but "no write of this binding was reported".

    **Case 1 is pinned on real bytecode instead**, where it belongs:
    `tests/e2e/test_kafka_delivered.py::test_a_destination_held_in_a_constructor_assigned_field_derives_every_value`
    builds `OrderPublisher` twice with different topics and asserts both rows derive
    resolved. A synthetic fact set cannot stand in for that: `call_edges` resolves a
    `<init>` callee from shapes real compilation produces, and a hand-built constructor
    call here links to no body — which is why this test asserts the hop rather than the
    values.
    """
    bindings = _bindings(walked, _symbol(_WRITTEN, "send", "()V"), 0)
    # `external`, not `no_writer`: the writer WAS found and crossed into, and nothing in
    # this fact set calls that constructor — which is the walk's own word for "the values
    # come from outside what was scanned". Without the edge the answer is `no_writer`, a
    # different statement, and that difference is what this test exists to hold.
    assert _reasons(bindings) == ["external"]


@pytest.mark.pins("values.a-lambda-body-reaches-the-values-it-CAPTURED")
def test_a_lambda_body_reaches_the_value_it_closed_over(walked):
    """**THE SEVENTH EDGE** (`OI-150`). A lambda body is a synthetic method whose leading
    parameters are the values the enclosing method closed over, and nothing in the
    `bound_to_parameter` facts binds them — so the walk answered `external` for every
    captured value, however plainly the code stated it.

    Here `install` captures the literal `closed-over` and `body` reads it. The edge is the
    two facts already in the stream: the capture site, whose arguments ARE the captured
    values in order, and the `lambda` entry naming the body and carrying the value that site
    produced. With the edge gone the answer is `external` — "the values come from outside
    what was scanned" — about a literal six lines up.

    **What it cost to be missing**, measured on real bytecode: a prefix declaration holding
    its pattern as a captured `String` parameter resolved nothing, so two controllers
    differing only by their prefix collapsed onto one published path. The e2e row is
    `tests/e2e/test_rest_inbound_delivered.py`'s `/text-api/text/{id}`.
    """
    bindings = _bindings(walked, _symbol(_CLOSING, "body", _TAKES_STRING), 0)
    assert [binding.slots[0].value for binding in bindings] == ["closed-over"]


@pytest.mark.pins("values.an-UNREADABLE-constant-answers-not_readable-never-nothing")
def test_a_constant_the_walk_cannot_read_answers_not_readable_and_keeps_the_site(walked):
    """**An answer, never an absence.** `Unreadable#held` is written from a `class` constant
    — `private Class<Order> t = Order.class`, ordinary code — and the walk has no literal
    kind for one.

    Contributing NOTHING there was a measured defect, found by review before the constant
    read shipped: with no answer and no other writer, `_binding` returned an EMPTY tuple,
    which `resolve_site` reads as "no path answers every slot" and drops **every slot of the
    site**. On real bytecode that cost a `getForObject(url, responseType)` its ADDRESS —
    `url` resolved through the sixth edge and was thrown away because the field beside it
    held a class constant.

    One binding, one `not_readable` answer: the write WAS reported, so `no_writer` would be
    false, and the value is not one this walk can act on.
    """
    bindings = _bindings(walked, _symbol(_UNREADABLE, "read", "()V"), 0)
    assert len(bindings) == 1, bindings
    assert _reasons(bindings) == ["not_readable"]


def test_a_parameter_no_scanned_caller_binds_is_unresolved_external(walked):
    """§1d's `external`, on the crossing edge: nothing in this module calls
    `Entry#handle`, so whatever it is handed comes from outside what was scanned. That
    is a different statement from "the code branches", and a reader can act on it."""
    bindings = _bindings(walked, _symbol(_ENTRY, "handle", _TAKES_STRING), 0)
    assert _reasons(bindings) == ["external"]


def test_a_value_from_a_body_this_workspace_never_read_is_unresolved_external(walked):
    """§6: it does not cross the module boundary. The producer is a call into a type
    nothing scanned, which `call_edges` records with a NULL callee — 1,411 of 2,065
    value-producing sites on `mall-admin`, so this is the common case, not the corner."""
    bindings = _bindings(walked, _symbol(_OUTSIDE, "use", "()V"), 1)
    assert _reasons(bindings) == ["external"]


# --- The identity table (spec §2, §0b): the MEANING half the walk cannot hold ---------
# A backward walk reaching `session.createQueue("raw-audit")` has a `Queue` object and
# nothing in the facts says what string identifies one — "the correction this design is
# built on, made three times before it stuck". These pin that `identified_by` answers
# exactly there, and that the entries it must pass over are passed over.

_OF_TWO_IDENTITY = {"owner": _NAME, "method": "of", "arg": 1}
_ALL_STRINGS_SPELLING = "all_strings"


def _identified(
    workspace: DuckDbWorkspace, method: str, ordinal: int, identities: list[dict[str, Any]]
) -> list[Binding]:
    return resolve_site(workspace, _at(workspace, method, ordinal), None, identities)


_RENDERING_IDENTITY = {
    "owner": "java/lang/String#",
    "method": "valueOf",
    "arg": 0,
    "arity": 1,
    "preserves": "authority",
}
_ADDRESS_IDENTITY = {"owner": _NAME, "method": "of", "arg": 0, "arity": 1}
_AUTHORITY_IDENTITY = {**_ADDRESS_IDENTITY, "yields": "authority"}


@pytest.mark.pins("values.a-RENDERING-carries-an-authority-and-nothing-else")
def test_a_rendering_carries_an_authority_and_refuses_an_address(walked):
    """**The gate that makes a rendering entry shippable at all** (`OI-138` cause 3, CP-39).

    javac inserts `String.valueOf` around every non-String operand of a concatenation, so
    the walk meets it in every address a module assembles from an object. `OI-142` refused
    an identity entry over it and was right about the danger: read off the platform's own
    bytecode, it returns `arg.toString()`, and for a destination identified as `"raw-notify"`
    that text is a vendor debug string — carrying it would publish an address that never
    existed, at `resolved`.

    So the entry declares `preserves: authority`, and the two directions are:

    * the producer yields an ADDRESS (the default) — the rendering carries nothing, the hole
      stays a hole, and the template says exactly what it said before;
    * the producer yields an AUTHORITY — WHO is called does not change when the value is
      rendered, so it is carried, and the consumer files it under `peer`.
    """
    refused = _identified(
        walked,
        _symbol(_RENDERED, "publish", "()V"),
        3,
        [_ADDRESS_IDENTITY, _RENDERING_IDENTITY],
    )
    assert [binding.slots[0].value for binding in refused] == ["{}/orders"]

    carried = _identified(
        walked,
        _symbol(_RENDERED, "publish", "()V"),
        3,
        [_AUTHORITY_IDENTITY, _RENDERING_IDENTITY],
    )
    assert [binding.slots[0].value for binding in carried] == ["//raw-notify/orders"]


def test_a_producer_nothing_identifies_stays_the_reason_it_was(walked):
    """The negative half, first, because every test below is only worth reading against
    it (GUIDELINES §10): the same position, the same facts, an EMPTY table — and the walk
    answers what it answered before Task 7. An identity arm that fired on the producer
    rather than on the entry would pass every test below and fail this one."""
    bindings = _bindings(walked, _symbol(_IDENTIFIED, "use", "()V"), 1)
    assert _reasons(bindings) == ["external"]


def test_an_identity_entry_answers_with_the_producers_own_argument(walked):
    """§0b's whole example, one framework along: the value is what `Name.of`'s argument 1
    says it is, and only framework knowledge says so. The walk found the producing call;
    the table said which of its arguments is the value (§1e)."""
    bindings = _identified(walked, _symbol(_IDENTIFIED, "use", "()V"), 1, [_OF_TWO_IDENTITY])
    assert [(b.slots[0].kind, b.slots[0].value) for b in bindings] == [("literal", "raw-notify")]


def test_an_identity_entry_with_no_owner_matches_a_free_function(walked):
    """**§5a, and it is a language-neutrality rule rather than a convenience.** Go's
    `nats.Connect(url)` and Python's `boto3.client("sqs")` are free functions, and
    `owner_of` already documents that an ownerless symbol is an answer here, never an
    exception — so requiring `owner` would bake OO into a model the fact grammar does
    not have."""
    bindings = _identified(
        walked, _symbol(_IDENTIFIED, "use", "()V"), 1, [{"method": "of", "arg": 1}]
    )
    assert [b.slots[0].value for b in bindings] == ["raw-notify"]


def test_an_identity_chain_goes_as_deep_as_the_code_does(walked):
    """**The cap that is gone** (§3a: no cap in v1). `Name.of(project, Name.text("deep-
    notify"))` is TWO identified producers in a row, and a hop declaration caps at one by
    construction — `channel_via` says "it is one hop that way" and has no second hop to
    say. The walk has no such limit, and the entries are two facts about two producers."""
    bindings = _identified(
        walked,
        _symbol(_IDENTIFIED, "nested", "()V"),
        2,
        [_OF_TWO_IDENTITY, {"owner": _NAME, "method": "text", "arg": 0}],
    )
    assert [b.slots[0].value for b in bindings] == ["deep-notify"]


# The `from_receiver` form (`OI-142`): an entry saying its call's result stands for
# whatever its RECEIVER stands for. `arg` cannot express it — a discovery chain's
# `.get(0)` names an index and `.getUri()` names nothing — and the gate below is what
# makes an entry on a JDK accessor safe to declare estate-wide.
_PRESERVING = {"owner": _ONE_TARGET[0], "method": _ONE_TARGET[1], "from_receiver": True}


def test_an_authority_joined_to_a_path_is_written_scheme_relative(walked):
    """Ruling 2, granted by the user 2026-10-17: peer and path from separate evidence.

    A service-discovery lookup yields WHO is being called — `one-service`, with no scheme
    and no path. Run together with the template's tail that is `one-service/owners`, which
    CP-2's splitter reads as a relative path, so the peer column is lost and both halves
    end up in `path`.

    `//one-service/owners` is RFC 3986 §4.2's scheme-relative reference — a real URI form
    rather than an invention — and the `//` states exactly where the authority ends.
    `split_url` then separates them with no new shape to learn, which is asserted in
    `tests/application/test_arguments.py` on the string this produces.
    """
    entry = {**_OF_TWO_IDENTITY, "yields": "authority"}
    bindings = _identified(walked, _symbol(_AUTHORITY_CHAIN, "call", "()V"), 2, [entry])
    assert [b.slots[0].value for b in bindings] == ["//one-service/owners"]


def test_an_ADDRESS_identity_joined_to_a_path_is_not_marked(walked):
    """The negative half (GUIDELINES §10), and the one that keeps `/api/v1` safe. An
    identity that yields an ADDRESS — every entry in the table but one — is joined
    verbatim, because a value that is already a whole address says where its own authority
    starts. Marking it would turn a path prefix into a host: `basePath + "/orders"` where
    `basePath` is `/api/v1` has the identical SHAPE, and `//api/v1/orders` would publish
    `api` as the service being called."""
    bindings = _identified(walked, _symbol(_AUTHORITY_CHAIN, "call", "()V"), 2, [_OF_TWO_IDENTITY])
    assert [b.slots[0].value for b in bindings] == ["one-service/owners"]


def test_a_receiver_preserving_entry_hands_on_a_single_valued_identity(walked):
    """The positive half. The producer's identity is ONE value, the call on its result
    says "I still stand for that", and the consuming position answers it.

    This is the user's own argument of 2026-10-17, which is what the entry rests on: an
    element of a list of a service's instances is that same service, because every
    instance of a service IS that service. Measured over the shipped table, the only
    single-valued entry producing a collection is `Collections.singletonList` at
    `arg: 0` — and `singletonList("x").get(0)` IS `x`, so propagating is right there too.
    """
    bindings = _identified(
        walked, _symbol(_PRESERVED, "single", "()V"), 2, [_OF_TWO_IDENTITY, _PRESERVING]
    )
    assert [b.slots[0].value for b in bindings] == ["one-service"]
    assert [b.slots[0].literal_kind for b in bindings] == ["string"]


@pytest.mark.pins("values.an-enumerating-identity-is-not-preserved-through-a-receiver")
def test_a_receiver_preserving_entry_REFUSES_an_enumerating_identity(walked):
    """**The safety half, and the reason the form can be declared on a JDK accessor at
    all.** An `identified_by` entry is read by every catalog at once, over every call in
    the estate — so an entry on element access meets topic lists as well as service
    instances. `List.of("topic-a", "topic-b").get(0)` must NOT answer both topics: that
    is one element reported as every element, a wrong answer at `resolved`, which is the
    single failure spec 2026-09-22 §7 says this family of work risks.

    The gate is the walk's own multiplicity rather than a special case: an enumerating
    identity resolves to SEVERAL answers, and an element of a collection identified as
    many things is one of them, which one being unknowable from the facts. MEASURED over
    the shipped table — 23 entries, three enumerating, and all three are topic lists
    (`List.of`, `Arrays.asList`, `Subscriptions.topics`).
    """
    enumerating = {**_OF_TWO_IDENTITY, "arg": _ALL_STRINGS_SPELLING}
    bindings = _identified(
        walked, _symbol(_PRESERVED, "enumerating", "()V"), 2, [enumerating, _PRESERVING]
    )
    assert _reasons(bindings) == ["not_readable"]
    assert [b.slots[0].value for b in bindings] == [None]


def test_a_receiver_preserving_entry_on_a_static_call_answers_nothing(walked):
    """No receiver, nothing to preserve. `not_readable` rather than `external`: the call
    IS inside what was scanned, and what is missing is the value it was invoked on — a
    distinction §1d draws and a consumer acts on."""
    bindings = _identified(
        walked, _symbol(_PRESERVED, "single", "()V"), 2, [{**_PRESERVING, "method": "of"}]
    )
    assert _reasons(bindings) == ["external"]


@pytest.mark.pins("values.an-identity-entry-with-a-role-is-not-an-identity")
def test_a_roled_identity_entry_is_not_what_this_value_is(walked):
    """**A `role` says something narrower than "this argument IS the value", and reading
    one here would answer one value twice.** `new ProducerRecord(topic, …, payload)`
    hoists as two entries — `role: channel` and `role: payload` — because two positions of
    one constructor are not interchangeable and the CONSUMING row is what selects between
    them (`yaml_source._constructor_identities`). A role-free entry makes the whole claim;
    a roled one makes half of it, and half is not an identity."""
    roled = {**_OF_TWO_IDENTITY, "role": "channel"}
    bindings = _identified(walked, _symbol(_IDENTIFIED, "use", "()V"), 1, [roled])
    assert _reasons(bindings) == ["external"]


def test_the_COUNTING_identity_rule_is_still_passed_over(walked):
    """The negative half first (GUIDELINES §10), and it is the half that did NOT move.
    `last` picks one argument by counting which overload was called — `record_wrappers`'
    descriptor discrimination — and no arm of this walk reads it, so the position answers
    exactly what an empty table leaves it at. The engines read that spelling as they
    always have.

    This test and the one below were ONE test asserting both rules were passed over, and
    splitting them is the whole visible change: `all_strings` moved, `last` did not, and a
    loop over the two could not say so."""
    entry = {**_OF_TWO_IDENTITY, "arg": "last"}
    bindings = _identified(walked, _symbol(_IDENTIFIED, "use", "()V"), 1, [entry])
    assert _reasons(bindings) == ["external"]


def test_the_PLURAL_identity_rule_answers_with_every_argument_of_its_producer(walked):
    """`all_strings` says the producer's result IS the collection of its own arguments, so
    `Name.of("a-project", "raw-notify")` answers TWICE at the position that consumes it.
    §1c's multiplicity is PATHS, and one `element-of` step per argument is what keeps the
    two answers two paths rather than one position carrying a list.

    **Until this arm existed the position answered `external`** — and that answer was wrong
    on its own terms rather than merely incomplete: `external` means "a producer outside
    what was scanned", true of `List.of`'s body, but the value is not in the body. It is in
    arguments the facts already carry at the call site, so the walk was asserting a miss it
    could have read. MEASURED on the shipped estate: three consuming positions answered
    `external` this way — `kafka-consumer`'s `subscribe(List.of(..))`, `kafka-streams`'
    `stream(List.of(..))` and `pekko-connectors-kafka`'s `plainSource(.., topics(..))`.

    The ORDER is the producer's own argument order, which is the order the engines publish
    a topic list in (`_all_string_channels`: "in call order")."""
    entry = {**_OF_TWO_IDENTITY, "arg": "all_strings"}
    bindings = _identified(walked, _symbol(_IDENTIFIED, "use", "()V"), 1, [entry])
    assert [binding.slots[0].value for binding in bindings] == ["a-project", "raw-notify"]


def test_the_plural_rule_reads_a_VARARGS_producer_through_the_array_arm(walked):
    """**The two spellings of one topic list answer alike, and this is the half that could
    have needed a second expander and does not.** `Subscriptions.topics("a", "b")` and
    `Arrays.asList("a", "b")` are genuine varargs — ONE `array` argument in the facts
    (capability 9.15), never two positional ones — so `all_strings` resolves that single
    slot and `_elements` expands it, the same arm D00's array rule has always used.

    So nothing in the walk learns what a varargs call is, and the PATH is what shows the
    two arms composing: `argument 0 -> element 0`, the plural identity's step over
    `_elements`' own."""
    entry = {"owner": _NAME, "method": "of", "arg": "all_strings"}
    bindings = _identified(walked, _symbol(_IDENTIFIED, "varargs", "()V"), 1, [entry])
    assert [binding.slots[0].value for binding in bindings] == ["first-topic", "second-topic"]
    assert [binding.path for binding in bindings] == [
        ("argument 0", "element 0"),
        ("argument 0", "element 1"),
    ]


def test_a_HALF_READ_producer_keeps_what_it_read_plus_one_reason(walked):
    """**The readable member survives, and the user ruled it so on 2026-10-16.** A call's
    argument list is fixed, positional and complete at the call site, so
    `of("readable-topic", variable)` is a COMPLETE list of two with one unreadable member —
    not D00's partly-written array, where the MEMBERSHIP itself is uncertain. The readable
    topic is read from bytecode, not inferred, and dropping it would exclude a destination
    on inference (§8, "exclude only on proof") in the direction §8 says is hardest to
    notice: no wrong row is left behind and the reader cannot tell it was ever there.

    ONE trailing unresolved, never one per failed member, matching
    `shapes/arguments._all_string_channels` — and it carries the failing member's OWN
    reason, which is what makes the row actionable. This test asserted
    `["non_enumerable"]` when the arm first landed; both pins moved together with the
    ruling, which is why `test_call_engines.py`'s equivalent still passes untouched.

    The array arm is NOT changed by this: `Arrays.asList(arr)` reaches `_elements` through
    a reference, membership there really is uncertain, and `non_enumerable` still answers.
    """
    entry = {"owner": _NAME, "method": "of", "arg": "all_strings"}
    bindings = _identified(walked, _symbol(_IDENTIFIED, "partial", "()V"), 1, [entry])
    assert [(b.slots[0].value, b.slots[0].reason) for b in bindings] == [
        ("readable-topic", None),
        (None, "not_readable"),
    ]


def test_the_plural_rule_answers_a_producer_called_with_NOTHING_absent(walked):
    """`absent`, not a reason — the same statement `_elements` makes for an empty array and
    for the same reason D00 §5 gives: "called with no values" is the FACT, and it is the one
    place in this grammar where an empty value says something an absent key would not. A
    reason here would contradict the facts it was read from.

    This is also where the walk and the engines' shipped reader are known to differ —
    `_all_string_channels` never returns zero rows and answers one unresolved tuple instead.
    MEASURED: 21 of the estate's 27 `all_strings` sites carry no string argument, and NONE
    of them is reached from a position a catalog asks about, so the difference is logged
    rather than reconciled here."""
    entry = {"owner": _NAME, "method": "of", "arg": "all_strings"}
    bindings = _identified(walked, _symbol(_IDENTIFIED, "empty", "()V"), 1, [entry])
    assert [binding.slots[0].kind for binding in bindings] == ["absent"]


def test_an_identity_entrys_arity_tells_two_overloads_apart(walked):
    """`arity` and `descriptor` are part of what an entry MATCHES on, which is what lets a
    discriminated entry and a bare one coexist in one table (`yaml_source.value_model`).
    Here the site is the ONE-argument overload and the entry names the two-argument one,
    so it must not answer — the platform's URI type is the shipped case, where a
    one-string constructor sits beside four whose argument 0 is the SCHEME."""
    discriminated = {**_OF_TWO_IDENTITY, "arity": 2}
    at_one = _symbol(_IDENTIFIED, "overload", "()V")
    assert _reasons(_identified(walked, at_one, 1, [discriminated])) == ["external"]
    assert [
        b.slots[0].value
        for b in _identified(walked, at_one, 1, [{"owner": _NAME, "method": "of", "arg": 0}])
    ] == ["sole"]


_CTOR_IDENTITY = {"owner": _NAME, "method": "<init>", "arg": 0}


def test_a_constructed_value_answers_the_type_symbol_when_nothing_identifies_it(walked):
    """The negative half first (GUIDELINES §10), and it is ruling T-3 itself: a declaration
    reference IS the value, so `new Name(…)` answers the concrete type it was built from —
    as a `symbol`, never as text. Every constructed type in this estate but TWO is this case
    — MEASURED, the constructions `_construction` finds AND an entry claims have exactly two
    producers, `URI`'s one-string constructor (8 values) and `Queue`'s (2); the other two
    reachable initialiser entries match no construction anywhere. Four is the count of
    reachable ENTRIES and not of types. The arm below must leave every other one exactly
    where it is."""
    [binding] = _bindings(walked, _symbol(_IDENTIFIED, "built", "()V"), 1)
    assert (binding.slots[0].literal_kind, binding.slots[0].value) == ("symbol", _NAME)


def test_an_identity_entry_reaches_a_CONSTRUCTOR_and_not_only_a_factory(walked):
    """**The arm could not reach a constructor at all until this test existed** (review
    round 1). `_entry` answered an `instance` argument with its type symbol BEFORE reading
    its `source`, so a constructed value never reached `_value` — and **eleven** of the
    twenty-five shipped identity entries name an initialiser, **four** of them reachable
    here at all (the rest carry a `role` or a rule-valued `arg`, which `_identified` passes
    over). One of the four is `java.net.URI`'s, through which two shipped catalogs publish a
    resolved address today. `new Name("x")` and `Name.of(…, "x")` are one question and must
    answer alike."""
    bindings = _identified(walked, _symbol(_IDENTIFIED, "built", "()V"), 1, [_CTOR_IDENTITY])
    assert [(b.slots[0].literal_kind, b.slots[0].value) for b in bindings] == [
        ("string", "built-notify")
    ]


def test_an_identity_entrys_descriptor_tells_two_constructors_apart(walked):
    """`descriptor` is what separates two one-argument constructors of one type, which
    `arity` cannot — `ContainerProperties(String...)` beside `ContainerProperties(Pattern)`
    is the shipped pair, and both shipped `ContainerProperties`/`ConsumerProperties` entries
    carry one. The entry names the `(String)` form; the site is the `(String[])` one, so it
    must answer the type symbol and not the string that constructor was handed."""
    discriminated = {**_CTOR_IDENTITY, "descriptor": _CTOR_ONE}
    at_array = _symbol(_IDENTIFIED, "built_other", "()V")
    [turned_away] = _identified(walked, at_array, 1, [discriminated])
    assert turned_away.slots[0].literal_kind == "symbol"
    [matched] = _identified(walked, at_array, 1, [{**_CTOR_IDENTITY, "descriptor": _CTOR_ARRAY}])
    assert matched.slots[0].value == "other-notify"


@pytest.mark.pins("values.a-construction-hands-nothing-back")
def test_a_call_that_hands_something_back_is_not_a_construction(walked):
    """**The fabrication this arm nearly shipped, found by measuring the estate rather than
    by reading the code.** `session.createProducer(session.createQueue("raw-audit"))` holds
    its `Session` in a FIELD, so that value has no producer edge either — and the first call
    it is the receiver of is `createQueue`, which an identity entry names. Read as the
    session's construction, the answer was `raw-audit`: a queue name published as the
    identity of a connection, at `resolved`, which is spec §7's one failure.

    A construction hands nothing back — D00 §5's "result is null for a void one", which is
    why `produced_by` carries no edge for one — and `createQueue` hands back a `Queue`. So
    the value stays unread, and the reason is the one the pre-existing rule already gave it:
    a call was made ON it before it was used and nothing says what that call wrote."""
    entry = {"owner": _NAME, "method": "of", "arg": 0}
    bindings = _identified(walked, _symbol(_IDENTIFIED, "borrowed", "()V"), 1, [entry])
    assert _reasons(bindings) == ["escapes"]
    assert [binding.slots[0].value for binding in bindings] == [None]


def test_a_value_written_to_between_its_construction_and_its_use_escapes(walked):
    """§1d's `escapes`, at a constructor — the rule still declines here, which is what makes
    the test above evidence of anything (GUIDELINES §10).

    **And the window opens at the CONSTRUCTION, which it did not before.** `produced_by` is
    read off `call_sites.result` and an initialiser has none, so a constructed value had no
    producer ordinal at all and the window opened before its own construction: every
    `new Thing(x)` later used answered `escapes` on the constructor itself. How many
    positions that moved, and how many of them a catalog asks about, is a measured figure
    and lives in one place — `docs/research/2026-09-23-value-walk-measurement.md` §6.3 —
    which every other site cites rather than copying. *This docstring carried a figure of
    its own until 2026-09-23 and it was the one that round re-derived and retracted.*

    Unidentified, the slot answers the type symbol and never reaches the window at all —
    T-3's answer, and the pairing that shows the refusal below belongs to the arm."""
    site = _symbol(_IDENTIFIED, "mutated", "()V")
    assert [b.slots[0].literal_kind for b in _bindings(walked, site, 2)] == ["symbol"]
    identified = _identified(walked, site, 2, [_CTOR_IDENTITY])
    assert _reasons(identified) == ["escapes"]
    assert [binding.slots[0].value for binding in identified] == [None]


def test_a_value_the_facts_name_nothing_for_is_unresolved_not_readable(walked):
    """§1d's `not_readable`: the producer is there and its value cannot be named. Today
    every miss collapses into one word; this is the one that keeps that meaning, so the
    other five can mean something narrower."""
    bindings = _bindings(walked, _symbol(_UNREAD, "use", "()V"), 0)
    assert _reasons(bindings) == ["not_readable"]


def test_a_lambda_argument_answers_not_readable_rather_than_a_body_symbol(walked):
    """`value_edges.sql` rules on this in its `names_declaration` arm: a lambda names a
    BODY, not a declaration whose value can be identified, and a walk handed that symbol
    would have a method descriptor where it asked for a value."""
    bindings = _bindings(walked, _symbol(_UNREAD, "use", "()V"), 1)
    assert _reasons(bindings) == ["not_readable"]
    assert [b.slots[0].value for b in bindings] == [None]


def test_a_value_the_code_states_is_not_there_is_absent_rather_than_a_miss(walked):
    """`absent` (ruled 2026-09-23): the code STATES there is no value — an explicit null,
    and a zero-length varargs call. D00 §5 draws this line itself for the empty element
    list ("the empty list is the fact ... 'called with no values' is a different statement
    from 'the array could not be read'"), so answering `non_enumerable` there would call a
    known-empty thing ambiguous and contradict the facts it was read from.

    A resolved answer, not a reason: a consumer told `not_readable` would go looking for a
    value that is not there to be found."""
    for method, ordinal in (
        (_symbol(_UNREAD, "use", "()V"), 2),
        (_symbol(_ARRAYS, "none", "()V"), 0),
    ):
        bindings = _bindings(walked, method, ordinal)
        assert [(b.slots[0].kind, b.slots[0].value, b.slots[0].reason) for b in bindings] == [
            ("absent", None, None)
        ], f"{method}@{ordinal}"


def test_a_walk_that_returns_to_a_position_on_its_own_path_is_unresolved_cycle(walked):
    """§1d's `cycle`, which is also the termination proof: `ping` hands its parameter to
    `pong`, `pong` hands it back, and the walk answers rather than running forever."""
    bindings = _bindings(walked, _symbol(_LOOP, "ping", _TAKES_STRING), 1)
    assert _reasons(bindings) == ["cycle"]


def test_an_assembled_address_is_carried_verbatim_and_never_evaluated(walked):
    """§1b's `expression`, and §8.2's line: the template is what the facts carry, so the
    walk hands it back as written. It is never a `literal` — §6 keeps a computed string
    out of this repository — and a consumer reading literals sees nothing here."""
    bindings = _bindings(walked, _symbol(_ASSEMBLER, "call", "()V"), 0)
    assert [(b.slots[0].kind, b.slots[0].value) for b in bindings] == [("expression", "/orders/{}")]
    assert _reasons(bindings) == [None]


def test_a_concat_of_source_literals_joins_into_one_literal(walked):
    """Ruling 1, granted by the user 2026-10-17: *"join them when every single piece is a
    fixed string typed into the source code."*

    Nothing is reverse-engineered. javac emits one `invokedynamic` plus a recipe, the
    extractor already turns that recipe into a template with `{}` per runtime operand
    (and already substitutes the bootstrap's own constants, `\u0002`), and the operands
    are the concat site's OWN arguments — `domain/facts.py`: *"What FILLS the hole is the
    concat site's own call-site fact, reached by `source` -> `result`."* This joins what
    the facts already hold.

    It answers `literal`, not `expression`, because the result IS a fixed string the code
    states — the thing a catalog reading a destination can use."""
    bindings = _bindings(walked, _symbol(_JOINER, "call", "()V"), 1)
    assert [(b.slots[0].kind, b.slots[0].value) for b in bindings] == [
        ("literal", "http://host/orders")
    ]
    assert [b.slots[0].literal_kind for b in bindings] == ["string"]


def test_two_holes_are_filled_in_order(walked):
    """The template is split on its holes and interleaved, never substituted one hole at a
    time: a resolved operand that itself contains `{}` would otherwise be re-scanned and
    the second hole filled from the first operand's text."""
    bindings = _bindings(walked, _symbol(_TWO_HOLES, "call", "()V"), 1)
    assert [b.slots[0].value for b in bindings] == ["/alpha/middle/omega"]


def test_a_concat_fills_the_holes_it_can_and_leaves_the_rest_as_holes(walked):
    """Spec 2026-10-18 §3, replacing an all-or-nothing rule that discarded what WAS read.

    One operand is a source literal and the other a method PARAMETER. Until 2026-10-18
    this answered the template untouched — `{}orders/{}` — on the reasoning that a
    half-filled address is a claim about a string nobody wrote. That reasoning was right
    about the ADDRESS and wrong about the answer: `http://host/orders/{}` claims no
    address, it states the part that was read and prints the part that was not as a hole.

    `OI-143` is what made the difference matter. `apolloconfig/apollo` funnels 64 calls
    into `restTemplate.exchange(parseHost(service) + path, …)`, a template of `{}{}` whose
    host hole never resolves — so all-or-nothing discarded 64 known paths to avoid
    half-stating one address.

    **`expression`, never `literal`, and that is the safety.** A partly-filled template is
    not a value the code states, and `channel_of_answer` refuses an expression — so no
    messaging catalog can read one as a destination. A broker resolves a destination it is
    GIVEN, and half of one is not a destination."""
    bindings = _bindings(walked, _symbol(_HALF_JOINER, "call", _TAKES_STRING), 1)
    assert [(b.slots[0].kind, b.slots[0].value) for b in bindings] == [
        ("expression", "http://host/orders/{}")
    ]


def test_a_receiver_is_a_slot_like_any_other(walked):
    """§1b: one entry point, not two. The receiver is resolved by the same walk as an
    argument — here through the returns of the call that produced it — and a binding
    carries it under the one key that is not an index."""
    bindings = _bindings(walked, _symbol(_RECEIVING, "use", "()V"), 1)
    assert [b.slots[RECEIVER].value for b in bindings] == [_REGISTRY_IMPL]
    assert [b.slots[0].value for b in bindings] == ["x"]


def test_a_declaration_answers_with_a_symbol_that_no_reader_can_mistake_for_a_string(walked):
    """A class reference IS the value (`value_edges.sql`'s `names_declaration` arm), and
    the answer carries the symbol. It must not carry it as a `string` literal: a catalog
    reading a destination out of a slot would take `com/acme/…#` for an address, which is
    a fabrication of exactly the kind §7 says this work's whole risk is."""
    bindings = _bindings(walked, _symbol(_REGISTRAR, "register", _PAIR), 0)
    kinds = {(b.slots[1].kind, b.slots[1].literal_kind) for b in bindings}
    assert kinds == {("literal", "symbol")}
    assert {(b.slots[0].kind, b.slots[0].literal_kind) for b in bindings} == {("literal", "string")}


def test_the_walk_follows_a_chain_as_deep_as_the_code_goes(walked):
    """§3a: no cap in v1, and Task 4's measurement is what decides whether one is ever
    needed. Four methods deep is past every "one hop" this codebase has ever declared —
    seven of them, in eighteen places (§0) — and the value still arrives."""
    bindings = _bindings(walked, _symbol(_DEEP, "three", _TAKES_STRING), 0)
    assert [b.slots[0].value for b in bindings] == ["deep"]
    assert [len(b.path) for b in bindings] == [3]


def test_one_position_reached_two_ways_keeps_the_two_paths_apart(walked):
    """**The memo's key, measured.** `mid` is reached through `left` and through `right`,
    and both wrappers are called by `top` — so `top`'s parameter is resolved twice, on two
    paths that disagree about which call reached `mid`.

    Memoise on the position ALONE and the second walk is handed the first one's answer,
    trail and all: both bindings then claim the path through `left`, which is a row
    asserting that a value arrived by a call it did not arrive by. That is M-1's
    fabrication one level down, and this is the only test here that sees it — the helper
    test above passes under a position-only memo, because there each position is resolved
    exactly once."""
    top = _symbol(_DIAMOND, "top", _TAKES_STRING)
    bindings = _bindings(walked, _symbol(_DIAMOND, "mid", _TAKES_STRING), 0)
    assert [b.path for b in bindings] == [
        (
            f"{_symbol(_DIAMOND, 'start', '()V')}@0",
            f"{top}@0",
            f"{_symbol(_DIAMOND, 'left', _TAKES_STRING)}@0",
        ),
        (
            f"{_symbol(_DIAMOND, 'start', '()V')}@0",
            f"{top}@1",
            f"{_symbol(_DIAMOND, 'right', _TAKES_STRING)}@0",
        ),
    ]
    assert [b.slots[0].value for b in bindings] == ["alpha", "alpha"]


def test_a_bridge_over_an_instance_method_answers_the_siblings_own_parameters(bridged):
    """**The Critical this round found, pinned at the exact shape it was found in.** A
    `bound_to_parameter` edge pairs a PROJECTED callee — the function the bridge stands for
    — with a RAW slot index, so a walk reading raw `call_sites` was handed the bridge's
    leading receiver for the sibling's parameter 0: `com/acme/orders/values/Api#`, a type
    symbol where a string belongs, IN RANGE so nothing caught it. That is the fabrication
    `literal_kind: symbol` exists to prevent, arriving through another door.

    Reading the PROJECTION fixes the correspondence rather than papering over it: the
    callee and the argument list then come from one row, so the callee's parameter *p* is
    that row's slot *p*. The assertion is on both parameters, and on the value NOT being
    the receiver, because a walk that answered a reason here would also pass a test that
    only checked "not the receiver"."""
    bindings = _bindings(bridged[0], _symbol(_API, "greet", _GREET), 0)
    assert [(b.slots[0].kind, b.slots[0].value) for b in bindings] == [("literal", "y")]
    assert [b.slots[0].value for b in bindings] != [_API], "the bridge's receiver, not p0"
    second = _bindings(bridged[0], _symbol(_API, "greet", _GREET), 1)
    assert [(b.slots[0].kind, b.slots[0].value) for b in second] == [("literal", False)]


def test_a_defaulted_parameter_is_a_reason_and_never_the_value_the_bridge_pushed(bridged):
    """The second shape of the same cause. With the mask set, the caller supplied nothing
    for parameter 1 and the projection marks the slot `defaulted`; the RAW row still holds
    the `0`/`false` the bridge pushed, which a walk reading it would publish as the value.
    A parameter that takes its declared default is a reason, not a literal — and not
    `absent` either, which would claim the code states there is no value."""
    bindings = _bindings(bridged[2], _symbol(_API, "greet", _GREET), 1)
    assert [(b.slots[0].kind, b.slots[0].reason) for b in bindings] == [
        ("unresolved", "not_readable")
    ]
    # The parameter the caller DID supply still resolves, so this is a narrow refusal.
    supplied = _bindings(bridged[2], _symbol(_API, "greet", _GREET), 0)
    assert [b.slots[0].value for b in supplied] == ["y"]


def test_a_raw_row_handed_in_at_the_front_door_is_projected_before_it_is_read(bridged):
    """**The Critical, one level out** (fix round 2). The walk's internal reads were fixed
    by reading the projection; `resolve_site` itself still read whatever row it was handed,
    so a caller passing the RAW row for a bridge call got the bridge's receiver as slot 0 —
    `com/acme/orders/values/Api#`, the same fabrication, at the exact function a consumer
    is about to be wired into.

    The fix is to project inside rather than to document a requirement: a rule every future
    caller must remember is a cause left in place. The row handed in names the site; the
    walk resolves the projected row for it, so the raw arity of five collapses to the
    sibling's two and slot 0 is the argument the caller actually wrote."""
    raw = [
        row
        for row in bridged[0].query("call_sites")
        if row["caller"] == _symbol(_HANDLER, "handle", _HANDLE) and row["ordinal"] == 0
    ]
    assert len(raw) == 1 and len(raw[0]["arguments"]) == 5, "the fixture's raw row"
    bindings = resolve_site(bridged[0], dict(raw[0]))
    # The sibling's two parameters plus the receiver the projection lifted OUT of slot 0 —
    # never five slots, and never the receiver standing in for parameter 0.
    assert [set(b.slots) for b in bindings] == [{0, 1, RECEIVER}]
    assert [(b.slots[0].kind, b.slots[0].value) for b in bindings] == [("literal", "y")]
    assert [b.slots[0].value for b in bindings] != [_API], "the bridge's receiver"
    assert [(b.slots[1].kind, b.slots[1].value) for b in bindings] == [("literal", False)]


def test_a_value_returned_through_a_bridge_reads_the_siblings_arguments(bridged):
    """The FORWARD crossing over the same shape, which rests on the same invariant and
    would have carried the same defect. `label` hands its own parameter back, so the walk
    descends into its return and the frame it pushes — the site it descended through — is
    what answers `label`'s parameter 0. That site is a bridge call: read raw, its slot 0 is
    the receiver; read projected, it is the `"z"` the caller wrote."""
    bindings = _bindings(bridged[0], _symbol(_HANDLER, "read", _READ), 1)
    assert [(b.slots[0].kind, b.slots[0].value) for b in bindings] == [("literal", "z")]


def test_the_reasons_are_the_closed_set_the_design_declares(walked):
    """§1d is a CLOSED vocabulary, and §3a keeps `fan_out` and `depth` out of it until a
    measurement asks for them. A seventh word added here without that ruling is the thing
    this test exists to fail on."""
    assert set(_REASONS) == {
        "not_readable",
        "non_enumerable",
        "escapes",
        "no_writer",
        "external",
        "cycle",
    }


def test_an_index_built_once_answers_what_a_fresh_one_answers(walked):
    """§8.7: the walk reads five queries to build its index, and a caller resolving many
    positions builds it once. The two paths must answer identically, or the fast one is a
    different operation wearing the same name."""
    index = value_index(walked)
    site = _at(walked, _symbol(_REGISTRAR, "register", _PAIR), 0)
    assert resolve_site(walked, site, index) == resolve_site(walked, site)


def test_every_hand_built_symbol_is_module_prefixed():
    """OI-4's own remedy, asserted rather than trusted: a fixture that spelled a caller
    or a callee bare would exercise a join this walk does not actually perform."""
    for fact in _facts():
        for symbol in (getattr(fact, "symbol", None), getattr(fact, "caller", None)):
            if symbol is not None:
                assert str(symbol).startswith(_MODULE)


def test_the_fixture_is_loaded_at_all(walked: DuckDbWorkspace, tmp_path: Path):
    """The OI-4 count check `test_return_flow.py` puts first: a join that matched nothing
    would leave every assertion above vacuously green."""
    assert walked.query("value_edges")
    assert {str(row["kind"]) for row in walked.query("value_edges")} >= {
        "produced_by",
        "returned_by",
        "read_from_binding",
        "bound_to_parameter",
        "names_declaration",
    }


# ---------------------------------------------------------------------------
# Shadow mode (spec §7a) and the `value_resolutions` table (§3d)
# ---------------------------------------------------------------------------

# One catalog, asking about one slot of one method — the smallest thing that is a real
# ask. `Registry#one` is called from eight of the fixture's arms above, and between them
# they answer a literal, several literals on several paths, and four of §1d's six reasons,
# so the shadow rows this produces exercise both outcomes without a catalog invented to
# produce each.
_ASKING = Catalog(
    id="values-probe",
    style="single_call",
    protocol="jms",
    direction="outbound",
    requires=(),
    matches={"methods": [{"owner": "com.acme.orders.values.Registry", "method": "one", "arg": 0}]},
    source=Path("values-probe.yml"),
)

# The three tables §3c diffs, and the three §7a promises shadow mode does not move.
_PUBLISHED = ("endpoints", "endpoint_metadata", "shapes")


def _shadow_rows(workspace: DuckDbWorkspace) -> list[dict[str, Any]]:
    record_value_resolutions(workspace, [_ASKING], shadow=True)
    return [dict(row) for row in workspace.query("value_resolutions")]


def test_shadow_mode_records_what_it_would_resolve_and_publishes_nothing(walked):
    """**Spec §7a, and the test that is the point of the task.** The whole risk of this
    work is that a conversion is a new ASSERTION — §3c's diff catches movement and not
    wrongness, because a wrong address looks exactly like a right one in a diff. Shadow
    mode makes every candidate reviewable as data before a row changes, which is worth
    nothing unless it is true that no row changes.

    Both halves are asserted together deliberately. A recorder that wrote its rows by
    deriving them would pass the first assertion and fail the second, and a recorder that
    ran nothing would pass the second and fail the first.
    """
    before = {name: walked.query(name) for name in _PUBLISHED}
    rows = _shadow_rows(walked)
    assert {row["outcome"] for row in rows} == {"would_resolve", "unresolved"}
    for name in _PUBLISHED:
        assert walked.query(name) == before[name], name


def test_a_would_resolve_row_carries_the_value_it_would_publish(walked):
    """§7a's "reviewable as data" is the whole deliverable, and a row saying only THAT a
    position would resolve is not reviewable: the reviewer's question is whether the
    address is right. `Publisher#publish`@1 reads a value returned by a callee with two
    `return` statements, so it is two paths and two candidate claims — the multiplicity
    §1c keeps rather than picking one of."""
    rows = [
        row
        for row in _shadow_rows(walked)
        if row["caller"] == _symbol(_PUBLISHER, "publish", "()V") and row["ordinal"] == 1
    ]
    assert [(row["outcome"], row["answer_kind"], row["value"]) for row in rows] == [
        ("would_resolve", "literal", "orders"),
        ("would_resolve", "literal", "orders-fast"),
    ]
    assert {row["literal_kind"] for row in rows} == {"string"}
    assert [row["path"] for row in rows] == [
        f"{_symbol(_NAMES, 'pick', _MAKES_STRING)} returns 0",
        f"{_symbol(_NAMES, 'pick', _MAKES_STRING)} returns 1",
    ]


def test_an_unresolved_row_carries_the_reason_and_no_value(walked):
    """§1d's vocabulary is decoration unless something records it (§3d), and this table is
    the something. Four of the six reasons are reachable from this one catalog's ask, each
    naming a different thing a reader can act on: "we cannot see the jar" is not "the code
    branches", and today both collapse into one word."""
    rows = [row for row in _shadow_rows(walked) if row["outcome"] == "unresolved"]
    assert {row["reason"] for row in rows} >= {"external", "not_readable", "escapes", "no_writer"}
    assert {row["value"] for row in rows} == {None}
    assert {row["answer_kind"] for row in rows} == {"unresolved"}


def test_the_table_is_bounded_by_what_catalogs_ask_not_by_the_facts(walked):
    """**§3d's bound, and the thing that makes the table readable at all.** What the bound
    is worth estate-wide is measured in
    `docs/research/2026-09-23-value-walk-measurement.md` §2 and is cited rather than
    repeated here — this test asserts the bound's SHAPE, not its estate-wide size. Here the
    one catalog asks about slot 0 of `Registry#one` and nothing else, so every row names
    that method — a writer that had lost the bound and emitted a row per fact would fail
    this on the fixture's other sixty-odd argument positions."""
    rows = _shadow_rows(walked)
    assert rows
    assert {row["slot"] for row in rows} == {"0"}
    assert {row["catalog"] for row in rows} == {"values-probe"}
    asked = {
        (str(site["caller"]), int(str(site["ordinal"])))
        for site in effective_call_sites(walked)
        if str(site["owner"]) == _REGISTRY and str(site["name"]) == "one"
    }
    assert {(row["caller"], row["ordinal"]) for row in rows} == asked


def test_shadow_rows_do_not_survive_an_ordinary_analysis(walked):
    """The reset is unconditional, and that is not tidiness. A workspace analysed once
    with `--shadow` and again without it would otherwise keep the first run's review list
    — rows describing a walk this analysis did not run, against sites it may have moved.
    `reachability` shipped without its reset and doubled every row on a second analyze;
    this is the same defect, caught before it shipped."""
    assert _shadow_rows(walked)
    record_value_resolutions(walked, [_ASKING], shadow=False)
    assert walked.query("value_resolutions") == []


def test_shadow_mode_asks_about_a_position_no_catalog_names_and_records_nothing(walked):
    """The bound, from the other side: a catalog that asks about nothing this workspace
    calls writes no row at all. An empty table is the honest answer, not a defect — the
    same shape §3b names as its precedent (eight catalogs declared `metadata_from` on
    `orders-quarkus` and zero annotation walks ran)."""
    record_value_resolutions(
        walked,
        [
            Catalog(
                id="asks-nothing",
                style="single_call",
                protocol="jms",
                direction="outbound",
                requires=(),
                matches={
                    "methods": [{"owner": "com.acme.nowhere.Absent", "method": "gone", "arg": 0}]
                },
                source=Path("asks-nothing.yml"),
            )
        ],
        shadow=True,
    )
    assert walked.query("value_resolutions") == []


# --- Capability 9.19: a merged value with a common root (spec 2026-10-21) ---------------


@pytest.mark.pins("values.a-MERGE-is-read-not-skipped")
@pytest.mark.pins("values.a-rooted-merge-is-INEXACT-never-exact")
def test_a_merge_of_a_parameter_and_a_call_on_it_resolves_to_every_caller_inexactly(walked):
    """§3b. `send`'s consumer sees the parameter OR `substring`'s result, and `substring`'s
    own site says its receiver IS that parameter — so both candidates are the same value,
    possibly re-rendered. The walk answers the parameter, crosses to both callers (ruling
    1's multiplicity: two bindings, one literal each) and marks every answer INEXACT,
    because what `substring` did to the text was never read. Nothing here knows what
    `substring` is; the same facts with `trim` in its place answer identically."""
    bindings = _bindings(walked, _symbol(_WRAPPER, "send", _TAKES_STRING), 1)
    answers = sorted((str(b.slots[0].value), b.slots[0].inexact) for b in bindings)
    assert answers == [("/a", True), ("b", True)]
    assert all(b.slots[0].kind == "literal" for b in bindings)


@pytest.mark.pins("values.a-merge-without-a-ROOT-is-never-picked-from")
def test_a_merge_of_two_literals_has_no_root_and_stays_non_enumerable(walked):
    """Ruling 1, unchanged: two literals on two branches are two possible values and no
    single one. The candidates are in the fact for a reader; the walk picks neither."""
    assert _reasons(_bindings(walked, _symbol(_FORKED, "pick", _TAKES_STRING), 0)) == [
        "non_enumerable"
    ]


def test_a_merge_with_a_call_that_is_not_on_the_root_has_no_root(walked):
    """The root check reads the producing site's receiver and arguments and nothing else:
    `make()` takes nothing and is called on nothing, so its result is not a rendering of
    the parameter beside it, and the merge is a genuine fork."""
    assert _reasons(_bindings(walked, _symbol(_FORKED, "other", _TAKES_STRING), 1)) == [
        "non_enumerable"
    ]


_INEXACT = Answer(kind="literal", value="/billing/ledger", literal_kind="string", inexact=True)
_EXACT = Answer(kind="literal", value="/billing/ledger", literal_kind="string")


@pytest.mark.pins("shapes.an-INEXACT-address-publishes-at-partial")
def test_an_inexact_address_publishes_at_partial():
    """What `inexact` does downstream (§3b): a url reader publishes the text at `partial`
    — the word the resolution set has for "part of this address was read" — where the same
    text read exactly publishes at `resolved`."""
    assert url_of_answer(_INEXACT) == (None, "/billing/ledger", "partial")
    assert url_of_answer(_EXACT) == (None, "/billing/ledger", "resolved")


@pytest.mark.pins("shapes.an-INEXACT-channel-is-refused")
def test_an_inexact_channel_is_refused():
    """A channel reader refuses an inexact literal, because a broker resolves a destination
    it is GIVEN and a name some call may have re-rendered is not one."""
    assert channel_of_answer(_INEXACT) == (None, None, "unresolved")
    assert channel_of_answer(_EXACT) == (None, "/billing/ledger", "resolved")
