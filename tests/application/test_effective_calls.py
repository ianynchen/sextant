"""Tests for `effective_call_sites` (spec 2026-09-19 §3, Task 3) — proof step 1 that the
projection point is a PURE RENAME before either Kotlin projection lands on it: with nothing
to project yet, the function returns exactly `call_sites`'s own rows, and `Workspace.once`
hands back the same list on a second call rather than rebuilding it.

Then §3a (Task 4): a call to a compiler-emitted `$default` bridge reaches every engine as a
call to the function the bridge stands for, with the arguments the caller left to their
defaults marked `unresolved`/`defaulted` rather than guessed — read off the bridge's own
symbol fact (`bridge_of`) and the mask literal the compiler passed. The mask semantics are
the measured ones (spec §0 F3, CP-23): a SET bit means the caller did NOT supply that
parameter, bit 0 being the first declared parameter after the receiver.

Then §3b (Task 5): an `instance` argument whose class's type fact carries `lambda_body`
reaches every engine as a `lambda` naming that body with `captures: 0` — the projection
that makes a class-compiled closure indistinguishable from an `invokedynamic` one to a
routing walk, and gives such a route its handler (`kotlin-class-lambdas`,
`kotlin-null-handler`).

Then autoboxing: javac wraps a primitive constant in `<Wrapper>.valueOf(<prim>)` (JLS 5.1.7),
so `f(3)` reaches the facts as an argument produced by that call, and a boxed varargs as
an array of such results. The projection reads the constant the source wrote (CP-55 row 22).
"""

from pathlib import Path

import pytest

from sextant.application.resolve.effective_calls import effective_call_sites
from sextant.domain.closed_sets import ConstructKind, OriginTier
from sextant.domain.factfile import write_fact_file
from sextant.domain.facts import (
    CallArgument,
    CallSiteFact,
    CallTarget,
    Document,
    Parameter,
    Signature,
    SymbolFact,
    TypeRef,
)
from sextant.domain.symbols import method_descriptor
from sextant.storage.duckdb.workspace import DuckDbWorkspace

_MODULE = "sextant-jvm maven com.acme/orders-service 1.0.0 "
CALLER = "com/acme/orders/Caller#handle(sig_a1)."

API = "com/x/Api#"
GREET = "(Ljava/lang/String;Z)Ljava/lang/String;"
GREET_BRIDGE = "(Lcom/x/Api;Ljava/lang/String;ZILjava/lang/Object;)Ljava/lang/String;"
DEFAULTED = {"kind": "unresolved", "reason": "defaulted"}


def _document() -> Document:
    return Document(
        document_id="doc_1",
        relative_path="com/acme/orders/Caller.java",
        module_id="com.acme:orders-service",
        language="java",
        sextant_version="0.1.0",
        fact_schema_version=2,
        scanner_id="asm",
        content_hash="sha256:a",
        origin_entry="target/classes",
        origin_tier=OriginTier.MODULE_OUTPUT,
        redaction_set_hash="sha256:b",
    )


def _site(
    caller: str,
    ordinal: int,
    owner: str,
    name: str,
    *,
    descriptor: str = "(...)V",
    arguments: list[CallArgument] | None = None,
    result: int | None = None,
    invoke_kind: str = "static",
) -> CallSiteFact:
    return CallSiteFact(
        document_id="doc_1",
        caller=caller,
        target=CallTarget(owner=owner, name=name, descriptor=descriptor),
        invoke_kind=invoke_kind,
        ordinal=ordinal,
        result=result,
        arguments=list(arguments or []),
    )


def _method_symbol(
    bare: str,
    *,
    enclosing: str | None = None,
    bridge_of: str | None = None,
    static: bool = False,
    signature: Signature | None = None,
) -> SymbolFact:
    """A method's own symbol fact; `static` lands in `modifiers` the way the extractor
    writes it, `bridge_of` only where a caller sets it (absent on every other fact), and
    `signature` only where a test reads a parameter's own flags off the declaration."""
    return SymbolFact(
        document_id="doc_1",
        symbol=_MODULE + bare,
        construct_kind=ConstructKind.METHOD,
        enclosing=None if enclosing is None else _MODULE + enclosing,
        modifiers={"static": static, "synthetic": bridge_of is not None},
        bridge_of=bridge_of,
        signature=signature,
    )


def _method(owner: str, name: str, descriptor: str, **keys) -> SymbolFact:
    return _method_symbol(method_descriptor(owner, name, descriptor), enclosing=owner, **keys)


def _workspace(tmp_path: Path, facts: list) -> DuckDbWorkspace:
    write_fact_file(tmp_path / "facts" / "Caller.jsonl", _document(), facts)
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    return workspace


def _greet_bridge_call(mask: CallArgument, receiver: CallArgument | None = None) -> CallSiteFact:
    """`invokestatic Api.greet$default(this, "y", false, <mask>, null)` — the shape kotlinc
    emits for `api.greet("y")` when `greet`'s second parameter has a default (CP-23)."""
    return _site(
        CALLER,
        0,
        API,
        "greet$default",
        descriptor=GREET_BRIDGE,
        result=1,
        arguments=[
            receiver or CallArgument(kind="parameter", value=0),
            CallArgument(kind="string", value="y"),
            CallArgument(kind="boolean", value=False),
            mask,
            CallArgument(kind="null"),
        ],
    )


def _greet_facts(*sites: CallSiteFact, bridge_of: str | None = "greet") -> list:
    return [
        _method_symbol(CALLER),
        _method(API, "greet", GREET),
        _method(API, "greet$default", GREET_BRIDGE, bridge_of=bridge_of, static=True),
        *sites,
    ]


def _only(workspace: DuckDbWorkspace) -> dict:
    (row,) = effective_call_sites(workspace)
    return row


def test_effective_call_sites_is_the_raw_list_when_nothing_projects(tmp_path: Path):
    workspace = _workspace(
        tmp_path,
        [_method_symbol(CALLER), _site(CALLER, 0, "com/x/Y#", "m", result=1, arguments=[])],
    )

    assert effective_call_sites(workspace) == workspace.query("call_sites")
    assert effective_call_sites(workspace) is effective_call_sites(workspace)  # once per load


def test_a_bridge_call_reaches_engines_as_the_function_with_the_defaulted_argument_unresolved(
    tmp_path: Path,
):
    """Mask 2 = bit 1 set = the SECOND declared parameter was left to its default. The
    engines see `greet("y", <defaulted>)` on the receiver the bridge's slot 0 carried — an
    unresolved argument, never a guessed default (spec §3a, user ruling) — and the row
    still says where it came from."""
    workspace = _workspace(
        tmp_path, _greet_facts(_greet_bridge_call(CallArgument(kind="int", value=2)))
    )

    row = _only(workspace)
    (raw,) = workspace.query("call_sites")
    assert (row["owner"], row["name"], row["descriptor"]) == (API, "greet", GREET)
    assert row["invoke_kind"] == "virtual"
    assert (row["receiver"], row["receiver_parameter"]) == (None, 0)
    assert row["arguments"] == [raw["arguments"][1], DEFAULTED]
    assert row["evidence_bridge"] == API + "greet$default" + GREET_BRIDGE
    # Everything the projection does not own is the site's own: identity and result.
    assert (row["caller"], row["ordinal"], row["result"]) == (raw["caller"], 0, 1)


def test_mask_zero_keeps_every_argument_and_a_receiver_value_becomes_the_row_receiver(
    tmp_path: Path,
):
    """Nothing defaulted: the two declared arguments pass through as they were. The
    receiver slot held a constructed value rather than a parameter, so `receiver` is its
    value id and `receiver_parameter` stays NULL — D00 §5's two receiver columns."""
    workspace = _workspace(
        tmp_path,
        _greet_facts(
            _greet_bridge_call(
                CallArgument(kind="int", value=0), CallArgument(kind="instance", source=7)
            )
        ),
    )

    row = _only(workspace)
    (raw,) = workspace.query("call_sites")
    assert row["arguments"] == raw["arguments"][1:3]
    assert (row["receiver"], row["receiver_parameter"]) == (7, None)
    assert row["invoke_kind"] == "virtual"


def test_mask_three_marks_both_arguments_defaulted(tmp_path: Path):
    workspace = _workspace(
        tmp_path, _greet_facts(_greet_bridge_call(CallArgument(kind="int", value=3)))
    )

    assert _only(workspace)["arguments"] == [DEFAULTED, DEFAULTED]


def test_a_static_sibling_moves_no_receiver(tmp_path: Path):
    """`js$default(String, int, int, Object)` stands for a static `js(String, int)`: the
    bridge's slot 0 is a real argument, not a receiver, so the dispatch form and both
    receiver columns stay exactly what the bytecode said."""
    statics = "com/x/Statics#"
    js, bridge = "(Ljava/lang/String;I)V", "(Ljava/lang/String;IILjava/lang/Object;)V"
    workspace = _workspace(
        tmp_path,
        [
            _method_symbol(CALLER),
            _method(statics, "js", js, static=True),
            _method(statics, "js$default", bridge, bridge_of="js", static=True),
            _site(
                CALLER,
                0,
                statics,
                "js$default",
                descriptor=bridge,
                arguments=[
                    CallArgument(kind="string", value="q"),
                    CallArgument(kind="int", value=0),
                    CallArgument(kind="int", value=2),
                    CallArgument(kind="null"),
                ],
            ),
        ],
    )

    row = _only(workspace)
    (raw,) = workspace.query("call_sites")
    assert (row["name"], row["descriptor"]) == ("js", js)
    assert row["arguments"] == [raw["arguments"][0], DEFAULTED]
    assert (row["invoke_kind"], row["receiver"], row["receiver_parameter"]) == (
        "static",
        None,
        None,
    )
    assert row["evidence_bridge"] == statics + "js$default" + bridge


def test_a_thirty_three_parameter_function_reads_its_second_mask(tmp_path: Path):
    """Parameter 32 is bit 0 of the SECOND mask int (ceil(33/32) = 2 mask slots). With the
    first mask 0 and the second 1, exactly the last declared parameter is defaulted — and
    the sibling descriptor is the bridge's minus receiver, both masks and the marker."""
    wide = "com/x/Wide#"
    declared = 33
    sibling = "(" + "I" * declared + ")V"
    bridge = "(Lcom/x/Wide;" + "I" * declared + "II" + "Ljava/lang/Object;)V"
    arguments = [
        CallArgument(kind="parameter", value=0),
        *(CallArgument(kind="int", value=index) for index in range(declared)),
        CallArgument(kind="int", value=0),
        CallArgument(kind="int", value=1),
        CallArgument(kind="null"),
    ]
    workspace = _workspace(
        tmp_path,
        [
            _method_symbol(CALLER),
            _method(wide, "f", sibling),
            _method(wide, "f$default", bridge, bridge_of="f", static=True),
            _site(CALLER, 0, wide, "f$default", descriptor=bridge, arguments=arguments),
        ],
    )

    row = _only(workspace)
    (raw,) = workspace.query("call_sites")
    assert (row["name"], row["descriptor"]) == ("f", sibling)
    assert row["arguments"] == raw["arguments"][1:33] + [DEFAULTED]


def _extension_signature(*slots: str) -> Signature:
    """A declaration whose FIRST slot is its extension receiver — the extractor's
    `receiver: true` on that parameter (`kotlin-extension-functions`), the other slots
    plain — so a test states the flag exactly where the fact stream carries it."""
    first, *rest = slots
    return Signature(
        parameters=[
            Parameter(type=TypeRef(symbol=first), erased_symbol=first, receiver=True),
            *(Parameter(type=TypeRef(symbol=slot), erased_symbol=slot) for slot in rest),
        ]
    )


ROUTE, STRING, FUNCTION1 = (
    "Lio/ktor/server/routing/Route;",
    "Ljava/lang/String;",
    "Lkotlin/jvm/functions/Function1;",
)
FACADE = "com/acme/kt/KtorRoutesKt#"
MOUNT = "(" + ROUTE + STRING + STRING + FUNCTION1 + ")" + ROUTE
MOUNT_BRIDGE = "(" + ROUTE + STRING + STRING + FUNCTION1 + "ILjava/lang/Object;)" + ROUTE


def test_a_static_siblings_extension_receiver_is_not_a_mask_bit(tmp_path: Path):
    """`fun Route.mount(path, version = "v1", build)` is a STATIC method whose slot 0 is the
    receiver the author wrote, and the compiler's mask counts the parameters the author
    declared — `version` is bit 1, though it is the sibling's slot 2. MEASURED on
    `fixtures/orders-ktor` (`javap -c -p KtorRoutesKt.class`, kotlinc 2.2.0): the call
    `mount("/d") { }` is `mount$default(this, "/d", null, build, 2, null)` and the bridge's
    body is `iload 4; iconst_2; iand; ifeq; ldc "v1"; astore_2` — slot 2 is the one
    substituted. The declaration says which slot is the receiver (`receiver: true`, the
    extractor's `kotlin-extension-functions`), so bit *i* is the slot AFTER it: `/d`, the
    path, stays the string it is, and `version` is the argument marked defaulted. Read
    the other way round, the path a rule reads would be unresolved and a null `version`
    would pass as a value — a wrong argument on the idiomatic shape of every DSL helper."""
    workspace = _workspace(
        tmp_path,
        [
            _method_symbol(CALLER),
            _method(
                FACADE,
                "mount",
                MOUNT,
                static=True,
                signature=_extension_signature(ROUTE, STRING, STRING, FUNCTION1),
            ),
            _method(FACADE, "mount$default", MOUNT_BRIDGE, bridge_of="mount", static=True),
            _site(
                CALLER,
                0,
                FACADE,
                "mount$default",
                descriptor=MOUNT_BRIDGE,
                result=1,
                arguments=[
                    CallArgument(kind="parameter", value=0),
                    CallArgument(kind="string", value="/d"),
                    CallArgument(kind="null"),
                    CallArgument(kind="lambda", symbol=FACADE + "body(sig_b).", captures=0),
                    CallArgument(kind="int", value=2),
                    CallArgument(kind="null"),
                ],
            ),
        ],
    )

    row = _only(workspace)
    (raw,) = workspace.query("call_sites")
    assert (row["name"], row["descriptor"]) == ("mount", MOUNT)
    assert row["arguments"] == [
        raw["arguments"][0],
        raw["arguments"][1],
        DEFAULTED,
        raw["arguments"][3],
    ]
    assert (row["invoke_kind"], row["receiver"], row["receiver_parameter"]) == (
        "static",
        None,
        None,
    )
    assert row["evidence_bridge"] == FACADE + "mount$default" + MOUNT_BRIDGE


def test_a_member_siblings_extension_receiver_is_not_a_mask_bit_either(tmp_path: Path):
    """A member extension, `class Owner { fun String.m(n: Int = 1) }`: the bridge is
    `m$default(Owner, String, int, int, Object)` — the owner slot, then the receiver the
    author wrote as the first slot the sibling owns (the extractor's own measured comment
    on `kotlin-extension-functions`, kotlinc 2.2.0) — and the instance sibling is
    `m(String, int)` with slot 0 flagged `receiver`. Mask 1 is bit 0, the FIRST declared
    parameter, which is `n`: the sibling's slot 1, not its receiver."""
    owner = "com/x/Owner#"
    m, bridge = "(Ljava/lang/String;I)V", "(Lcom/x/Owner;Ljava/lang/String;IILjava/lang/Object;)V"
    workspace = _workspace(
        tmp_path,
        [
            _method_symbol(CALLER),
            _method(owner, "m", m, signature=_extension_signature(STRING, "I")),
            _method(owner, "m$default", bridge, bridge_of="m", static=True),
            _site(
                CALLER,
                0,
                owner,
                "m$default",
                descriptor=bridge,
                arguments=[
                    CallArgument(kind="parameter", value=0),
                    CallArgument(kind="string", value="s"),
                    CallArgument(kind="int", value=0),
                    CallArgument(kind="int", value=1),
                    CallArgument(kind="null"),
                ],
            ),
        ],
    )

    row = _only(workspace)
    (raw,) = workspace.query("call_sites")
    assert (row["name"], row["descriptor"]) == ("m", m)
    assert row["arguments"] == [raw["arguments"][1], DEFAULTED]
    assert (row["invoke_kind"], row["receiver_parameter"]) == ("virtual", 0)


def test_thirty_two_declared_parameters_after_an_extension_receiver_need_one_mask(
    tmp_path: Path,
):
    """The mask count follows the DECLARED parameters, not the sibling's slots: 32
    declared after a receiver is 33 slots and ONE mask (ceil(32/32)), where a slot count
    would demand two and find no sibling at all — the site left untouched, and a
    defaulted argument passed to a rule as the placeholder value the caller pushed."""
    wide = "com/x/WideKt#"
    declared = 32
    sibling = "(" + STRING + "I" * declared + ")V"
    bridge = "(" + STRING + "I" * declared + "ILjava/lang/Object;)V"
    arguments = [
        CallArgument(kind="string", value="r"),
        *(CallArgument(kind="int", value=index) for index in range(declared)),
        CallArgument(kind="int", value=1 << 31),
        CallArgument(kind="null"),
    ]
    workspace = _workspace(
        tmp_path,
        [
            _method_symbol(CALLER),
            _method(
                wide,
                "f",
                sibling,
                static=True,
                signature=_extension_signature(STRING, *(["I"] * declared)),
            ),
            _method(wide, "f$default", bridge, bridge_of="f", static=True),
            _site(CALLER, 0, wide, "f$default", descriptor=bridge, arguments=arguments),
        ],
    )

    row = _only(workspace)
    (raw,) = workspace.query("call_sites")
    assert (row["name"], row["descriptor"]) == ("f", sibling)
    assert row["arguments"] == raw["arguments"][0:32] + [DEFAULTED]


def test_a_default_call_whose_bridge_carries_no_bridge_of_is_left_alone(tmp_path: Path):
    """The extractor's stated declines (a library not scanned, an ambiguity it would not
    guess at) reach here as a `$default` symbol with no `bridge_of` — and the site stays
    exactly as the bytecode said, rather than being re-derived from its name (spec §3a)."""
    workspace = _workspace(
        tmp_path,
        _greet_facts(_greet_bridge_call(CallArgument(kind="int", value=2)), bridge_of=None),
    )

    assert effective_call_sites(workspace) == workspace.query("call_sites")


def test_both_candidate_siblings_declared_leaves_the_site_untouched(tmp_path: Path):
    """A5: the bridge's descriptor fits an instance `greet(String, boolean)` AND a static
    `greet(Api, String, boolean)` — both declared, so which slot is the receiver is a guess.
    Ambiguity is not a guess: the site is left as it is."""
    facts = _greet_facts(_greet_bridge_call(CallArgument(kind="int", value=2)))
    facts.append(
        _method(API, "greet", "(Lcom/x/Api;Ljava/lang/String;Z)Ljava/lang/String;", static=True)
    )
    workspace = _workspace(tmp_path, facts)

    assert effective_call_sites(workspace) == workspace.query("call_sites")


def test_a_declared_sibling_whose_static_ness_contradicts_its_slot_reading_is_not_the_sibling(
    tmp_path: Path,
):
    """The receiver reading says slot 0 is a receiver, so the sibling it names is an
    instance method; a `greet(String, boolean)` declared STATIC on the same type fits the
    descriptor and contradicts the reading. The compiler cannot emit that pair for one
    function, so the contradiction is not settled either way: the site stays as it is."""
    workspace = _workspace(
        tmp_path,
        [
            _method_symbol(CALLER),
            _method(API, "greet", GREET, static=True),
            _method(API, "greet$default", GREET_BRIDGE, bridge_of="greet", static=True),
            _greet_bridge_call(CallArgument(kind="int", value=2)),
        ],
    )

    assert effective_call_sites(workspace) == workspace.query("call_sites")


def test_a_bridge_whose_sibling_is_not_declared_leaves_the_site_untouched(tmp_path: Path):
    """The near-miss for the sibling-existence check: `bridge_of` names `greet` but no
    `greet` with either candidate descriptor is declared, so there is nothing to re-target
    to and the site stays as it is."""
    workspace = _workspace(
        tmp_path,
        [
            _method_symbol(CALLER),
            _method(API, "greet$default", GREET_BRIDGE, bridge_of="greet", static=True),
            _greet_bridge_call(CallArgument(kind="int", value=2)),
        ],
    )

    assert effective_call_sites(workspace) == workspace.query("call_sites")


def test_a_mask_that_is_not_an_int_literal_leaves_the_site_untouched(tmp_path: Path):
    """A mask the bytecode computes rather than states cannot say which parameters were
    supplied; a wrong trimming is worse than the silence there is today (spec §3a), so the
    whole site stays as it is — not a partial projection with the mask guessed."""
    workspace = _workspace(
        tmp_path, _greet_facts(_greet_bridge_call(CallArgument(kind="unresolved")))
    )

    assert effective_call_sites(workspace) == workspace.query("call_sites")


def test_the_raw_call_sites_are_not_changed_by_the_projection(tmp_path: Path):
    """`call_sites` is the exported bundle's and the graph readers' statement of the
    bytecode; the projection copies a row before changing it, never writes into the
    cached list or its dicts."""
    site = _greet_bridge_call(CallArgument(kind="int", value=2))
    workspace = _workspace(tmp_path, _greet_facts(site))
    before = [dict(row) for row in workspace.query("call_sites")]

    effective_call_sites(workspace)

    (raw,) = workspace.query("call_sites")
    assert [raw] == before
    assert (raw["name"], raw["descriptor"], raw["invoke_kind"]) == (
        "greet$default",
        GREET_BRIDGE,
        "static",
    )
    assert len(raw["arguments"]) == 5
    assert "evidence_bridge" not in raw


# --- §3b: a class-compiled lambda is the `lambda` it stands for -------------------------

LAMBDA_CLASS = "com/x/Routes$orders$1#"
# The body a suspend closure compiles into (CP-23): `invokeSuspend(Object)`, spelled as
# the extractor spells `lambda_body` — the bare descriptor with its hashed disambiguator.
LAMBDA_BODY = method_descriptor(
    LAMBDA_CLASS, "invokeSuspend", "(Ljava/lang/Object;)Ljava/lang/Object;"
)
PLAIN_CLASS = "com/x/Routes$plain$1#"
VERB = "io/x/RoutingKt#"
VERB_DESC = "(Lio/x/Route;Ljava/lang/String;Lkotlin/jvm/functions/Function2;)Lio/x/Route;"


def _type_symbol(bare: str, *, lambda_body: str | None = None) -> SymbolFact:
    """A class's own type fact; `lambda_body` only where the extractor marks the class a
    compiled lambda (absent on every other fact, as `bridge_of` is)."""
    return SymbolFact(
        document_id="doc_1",
        symbol=_MODULE + bare,
        construct_kind=ConstructKind.CLASS,
        lambda_body=lambda_body,
    )


def _lambda_facts(*arguments: CallArgument) -> list:
    return [
        _method_symbol(CALLER),
        _type_symbol(LAMBDA_CLASS, lambda_body=LAMBDA_BODY),
        _method_symbol(LAMBDA_BODY, enclosing=LAMBDA_CLASS),
        _type_symbol(PLAIN_CLASS),
        _site(
            CALLER,
            0,
            VERB,
            "get",
            descriptor=VERB_DESC,
            result=5,
            arguments=[
                CallArgument(kind="parameter", value=0),
                CallArgument(kind="string", value="/orders"),
                *arguments,
            ],
        ),
    ]


def test_an_instance_of_a_class_carrying_lambda_body_reaches_engines_as_that_lambda(
    tmp_path: Path,
):
    """`get("/orders") { … }` whose handler the compiler made a class: the site's third
    argument is an `instance` of that class, and every engine reads it as a `lambda`
    naming the body method — `captures: 0` exactly, because constructor-captured values
    are fields of the class and never leading parameters of the body (spec §3b) — with
    the value id the instance carried, so a follow through `source` still lands."""
    workspace = _workspace(
        tmp_path,
        _lambda_facts(CallArgument(kind="instance", symbol=LAMBDA_CLASS, source=4)),
    )

    row = _only(workspace)
    (raw,) = workspace.query("call_sites")
    assert row["arguments"] == [
        raw["arguments"][0],
        raw["arguments"][1],
        {"kind": "lambda", "symbol": LAMBDA_BODY, "captures": 0, "source": 4},
    ]
    # Everything but the argument is the site's own: no bridge rewrite happened here.
    assert (row["owner"], row["name"], row["descriptor"]) == (VERB, "get", VERB_DESC)
    assert (row["caller"], row["ordinal"], row["result"]) == (raw["caller"], 0, 5)
    assert "evidence_bridge" not in row


def test_an_instance_of_a_class_with_no_lambda_body_is_left_alone(tmp_path: Path):
    """The near-miss on the one conjunct: the class IS scanned (its type fact is in the
    workspace) and carries no `lambda_body`, so it is an ordinary object handed to the
    call — a handler adapter, a request object — and stays the `instance` it is. Nothing
    is inferred from the class's name or its nesting."""
    workspace = _workspace(
        tmp_path,
        _lambda_facts(CallArgument(kind="instance", symbol=PLAIN_CLASS, source=4)),
    )

    assert effective_call_sites(workspace) == workspace.query("call_sites")


def test_a_named_constant_of_a_lambda_class_reaches_engines_as_that_lambda(tmp_path: Path):
    """A closure that captures nothing is not `new`ed at all under `-Xlambdas=class`: the
    compiler gives its class one `INSTANCE` and the call site reads it — `getstatic
    Routes$orders$1.INSTANCE` (CP-23 Q7b, kotlinc 2.2.0), which the extractor emits as the
    `enum` kind it gives every named constant of its own type, saying the consumer that
    needs the distinction joins for it. The join is `lambda_body` on the constant's OWNER:
    the argument is that lambda, as an `instance` of the class would be, and with no
    `source` because a field read produces no value id. Every prefix block of a routing
    tree takes this shape (`routing { }`, `route("/api") { }` capture nothing), so without
    it a class-compiled routing tree is never entered and derives nothing at all."""
    workspace = _workspace(
        tmp_path,
        _lambda_facts(CallArgument(kind="enum", symbol=LAMBDA_CLASS + "INSTANCE.")),
    )

    row = _only(workspace)
    (raw,) = workspace.query("call_sites")
    assert row["arguments"] == [
        raw["arguments"][0],
        raw["arguments"][1],
        {"kind": "lambda", "symbol": LAMBDA_BODY, "captures": 0},
    ]


def test_a_named_constant_of_a_class_with_no_lambda_body_is_left_alone(tmp_path: Path):
    """The same near-miss on the constant read: `BigDecimal.ZERO`, a Kotlin `object`'s
    `INSTANCE`, a real enum constant — every one is `enum`-kind, and none has an owner
    marked `lambda_body`, so every one stays the constant it is."""
    workspace = _workspace(
        tmp_path,
        _lambda_facts(CallArgument(kind="enum", symbol=PLAIN_CLASS + "INSTANCE.")),
    )

    assert effective_call_sites(workspace) == workspace.query("call_sites")


def test_a_lambda_class_inside_an_array_argument_is_projected_in_its_element(
    tmp_path: Path,
):
    """A varargs call carries ONE `array` argument whose `elements` are the arguments
    (capability 9.15), and `_expanded_arguments` reads those elements — so a compiled
    lambda passed among varargs is projected where it sits, and the array keeps every
    other element and its own keys as they were."""
    workspace = _workspace(
        tmp_path,
        _lambda_facts(
            CallArgument(
                kind="array",
                elements=[
                    CallArgument(kind="instance", symbol=LAMBDA_CLASS, source=4),
                    CallArgument(kind="string", value="x"),
                    CallArgument(kind="instance", symbol=PLAIN_CLASS, source=6),
                ],
            )
        ),
    )

    row = _only(workspace)
    (raw,) = workspace.query("call_sites")
    array = raw["arguments"][2]
    assert row["arguments"][2] == {
        **array,
        "elements": [
            {"kind": "lambda", "symbol": LAMBDA_BODY, "captures": 0, "source": 4},
            array["elements"][1],
            array["elements"][2],
        ],
    }


def test_a_lambda_instance_without_a_source_projects_without_one(tmp_path: Path):
    """`source` travels only where the instance carried one: a projected argument never
    invents a value id, because a follow through `source` -> `result` on an invented
    number would land on an unrelated site."""
    workspace = _workspace(
        tmp_path, _lambda_facts(CallArgument(kind="instance", symbol=LAMBDA_CLASS))
    )

    assert _only(workspace)["arguments"][2] == {
        "kind": "lambda",
        "symbol": LAMBDA_BODY,
        "captures": 0,
    }


def test_the_raw_call_sites_are_not_changed_by_the_lambda_projection(tmp_path: Path):
    """The same guarantee the bridge step gives, for this step: the cached `call_sites`
    rows and their argument dicts — including the elements of an `array` — are read and
    never written into."""
    workspace = _workspace(
        tmp_path,
        _lambda_facts(
            CallArgument(kind="instance", symbol=LAMBDA_CLASS, source=4),
            CallArgument(
                kind="array",
                elements=[CallArgument(kind="instance", symbol=LAMBDA_CLASS, source=8)],
            ),
        ),
    )
    before = [dict(row) for row in workspace.query("call_sites")]

    effective_call_sites(workspace)

    (raw,) = workspace.query("call_sites")
    assert [raw] == before
    assert raw["arguments"][2]["kind"] == "instance"
    assert raw["arguments"][3]["elements"][0]["kind"] == "instance"


def test_a_bridge_call_handing_a_lambda_class_gets_both_projections(tmp_path: Path):
    """The two steps compose: `Api.greet$default(this, <lambda class>, false, mask, null)`
    is re-targeted to `greet` (§3a) AND the instance in its first declared slot is read
    as the body it stands for (§3b) — on the projected row, with the raw row untouched."""
    greet = "(Lkotlin/jvm/functions/Function2;Z)Ljava/lang/String;"
    bridge = "(Lcom/x/Api;Lkotlin/jvm/functions/Function2;ZILjava/lang/Object;)Ljava/lang/String;"
    workspace = _workspace(
        tmp_path,
        [
            _method_symbol(CALLER),
            _type_symbol(LAMBDA_CLASS, lambda_body=LAMBDA_BODY),
            _method_symbol(LAMBDA_BODY, enclosing=LAMBDA_CLASS),
            _method(API, "greet", greet),
            _method(API, "greet$default", bridge, bridge_of="greet", static=True),
            _site(
                CALLER,
                0,
                API,
                "greet$default",
                descriptor=bridge,
                arguments=[
                    CallArgument(kind="parameter", value=0),
                    CallArgument(kind="instance", symbol=LAMBDA_CLASS, source=4),
                    CallArgument(kind="boolean", value=False),
                    CallArgument(kind="int", value=2),
                    CallArgument(kind="null"),
                ],
            ),
        ],
    )

    row = _only(workspace)
    assert (row["name"], row["descriptor"]) == ("greet", greet)
    assert row["arguments"] == [
        {"kind": "lambda", "symbol": LAMBDA_BODY, "captures": 0, "source": 4},
        DEFAULTED,
    ]
    (raw,) = workspace.query("call_sites")
    assert raw["arguments"][1]["kind"] == "instance"


# --- autoboxing: a boxing call's result is the constant it was handed -------------------

INTEGER = "java/lang/Integer#"
INTEGER_VALUE_OF = "(I)Ljava/lang/Integer;"
TAKES = "com/x/Api#"
TAKES_DESC = "(Ljava/lang/Integer;)V"


def _boxed(
    result: int,
    value: CallArgument,
    *,
    owner: str = INTEGER,
    name: str = "valueOf",
    descriptor: str = INTEGER_VALUE_OF,
    ordinal: int = 0,
) -> CallSiteFact:
    return _site(
        CALLER, ordinal, owner, name, descriptor=descriptor, result=result, arguments=[value]
    )


def _boxing_facts(*sites: CallSiteFact) -> list:
    return [_method_symbol(CALLER), *sites]


def _bare(value):
    """An argument as written: the loaded dict carries every grammar key, absent ones None."""
    if isinstance(value, dict):
        return {key: _bare(item) for key, item in value.items() if item is not None}
    if isinstance(value, list):
        return [_bare(item) for item in value]
    return value


def _the_call(workspace: DuckDbWorkspace, name: str) -> dict:
    (row,) = [row for row in effective_call_sites(workspace) if row["name"] == name]
    return {**row, "arguments": _bare(row["arguments"])}


@pytest.mark.pins("effective-calls.AUTOBOXING-reads-as-its-constant")
def test_a_boxed_int_argument_reads_as_the_int(tmp_path: Path):
    """`f(Integer.valueOf(3))`: the argument is the call's result, an `unresolved` carrying
    the producing call's `source`; the engines read the `int` the source wrote."""
    workspace = _workspace(
        tmp_path,
        _boxing_facts(
            _boxed(1, CallArgument(kind="int", value=3)),
            _site(
                CALLER,
                1,
                TAKES,
                "f",
                descriptor=TAKES_DESC,
                arguments=[CallArgument(kind="unresolved", source=1)],
            ),
        ),
    )

    assert _the_call(workspace, "f")["arguments"] == [{"kind": "int", "value": 3}]


@pytest.mark.pins("effective-calls.AUTOBOXING-reads-as-its-constant")
def test_boxed_varargs_elements_read_as_their_ints(tmp_path: Path):
    """`onDaysOfTheWeek(3, 5)`: an `Integer[]` whose elements are `valueOf` results."""
    workspace = _workspace(
        tmp_path,
        _boxing_facts(
            _boxed(1, CallArgument(kind="int", value=3)),
            _boxed(2, CallArgument(kind="int", value=5), ordinal=1),
            _site(
                CALLER,
                2,
                TAKES,
                "days",
                descriptor="([Ljava/lang/Integer;)V",
                arguments=[
                    CallArgument(
                        kind="array",
                        elements=[
                            CallArgument(kind="unresolved", source=1),
                            CallArgument(kind="unresolved", source=2),
                        ],
                    )
                ],
            ),
        ),
    )

    assert _the_call(workspace, "days")["arguments"] == [
        {"kind": "array", "elements": [{"kind": "int", "value": 3}, {"kind": "int", "value": 5}]}
    ]


def test_a_valueOf_of_a_non_constant_is_left_alone(tmp_path: Path):
    workspace = _workspace(
        tmp_path,
        _boxing_facts(
            _boxed(1, CallArgument(kind="parameter", value=0)),
            _site(
                CALLER,
                1,
                TAKES,
                "f",
                descriptor=TAKES_DESC,
                arguments=[CallArgument(kind="unresolved", source=1)],
            ),
        ),
    )

    assert _the_call(workspace, "f")["arguments"] == [{"kind": "unresolved", "source": 1}]


def test_a_string_valueOf_is_not_boxing(tmp_path: Path):
    workspace = _workspace(
        tmp_path,
        _boxing_facts(
            _boxed(
                1,
                CallArgument(kind="int", value=3),
                owner="java/lang/String#",
                descriptor="(I)Ljava/lang/String;",
            ),
            _site(
                CALLER,
                1,
                TAKES,
                "f",
                descriptor="(Ljava/lang/String;)V",
                arguments=[CallArgument(kind="unresolved", source=1)],
            ),
        ),
    )

    assert _the_call(workspace, "f")["arguments"] == [{"kind": "unresolved", "source": 1}]


@pytest.mark.parametrize(
    ("wrapper", "primitive", "kind", "value"),
    [
        ("Boolean", "Z", "boolean", True),
        ("Byte", "B", "int", 1),
        ("Character", "C", "int", 65),
        ("Short", "S", "int", 2),
        ("Integer", "I", "int", 3),
        ("Long", "J", "long", 4),
    ],
)
def test_every_integral_boxing_method_reads_as_its_constant(
    tmp_path: Path, wrapper: str, primitive: str, kind: str, value: object
):
    workspace = _workspace(
        tmp_path,
        _boxing_facts(
            _boxed(
                1,
                CallArgument(kind=kind, value=value),
                owner=f"java/lang/{wrapper}#",
                descriptor=f"({primitive})Ljava/lang/{wrapper};",
            ),
            _site(CALLER, 1, TAKES, "f", arguments=[CallArgument(kind="unresolved", source=1)]),
        ),
    )

    assert _the_call(workspace, "f")["arguments"] == [{"kind": kind, "value": value}]


def test_a_boxing_result_of_another_method_is_not_joined(tmp_path: Path):
    """Value ids are per method: `source: 1` in `handle` is not the `valueOf` result 1
    of some other method."""
    other = "com/acme/orders/Caller#other(sig_a2)."
    workspace = _workspace(
        tmp_path,
        [
            _method_symbol(CALLER),
            _method_symbol(other),
            _site(
                other,
                0,
                INTEGER,
                "valueOf",
                descriptor=INTEGER_VALUE_OF,
                result=1,
                arguments=[CallArgument(kind="int", value=3)],
            ),
            _site(
                CALLER,
                0,
                TAKES,
                "f",
                descriptor=TAKES_DESC,
                arguments=[CallArgument(kind="unresolved", source=1)],
            ),
        ],
    )

    assert _the_call(workspace, "f")["arguments"] == [{"kind": "unresolved", "source": 1}]


def test_the_raw_call_sites_are_not_changed_by_the_boxing_projection(tmp_path: Path):
    workspace = _workspace(
        tmp_path,
        _boxing_facts(
            _boxed(1, CallArgument(kind="int", value=3)),
            _site(
                CALLER,
                1,
                TAKES,
                "f",
                descriptor=TAKES_DESC,
                arguments=[CallArgument(kind="unresolved", source=1)],
            ),
        ),
    )
    effective_call_sites(workspace)

    (raw,) = [r for r in workspace.query("call_sites") if r["name"] == "f"]
    assert _bare(raw["arguments"]) == [{"kind": "unresolved", "source": 1}]
