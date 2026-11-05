"""`resolve/beans.py` — bean identity (spec 2026-09-21 §3a): which declared factory
method built the value an injected parameter names.

What is pinned here and why. The rungs are PER REFERENCE KIND (spec §0b A2): a
channel reference is never resolved by type, because the container itself sees
more candidates than the module declares (Spring Integration auto-registers
`errorChannel` and `nullChannel`) and falls back to the parameter's name — so a
fold that picked the module's single channel bean by type would name a bean
the container does not inject. A container reference (a type no framework bean
shares) takes the container's own order: qualifier, unique type, name.

The fold is driven by the shipped `bean-models/spring.yml` here — so the file's
own spellings are what these facts are read through — and by an invented model
in the last test, which is what proves the module spells no framework itself.
The fold is built ONCE per load and per MODEL through `Workspace.once`, so two
catalogs naming the same model share it (GUIDELINES §8.7); the identity
assertion is what catches a builder keyed per call.
"""

from pathlib import Path

import pytest
import yaml

from sextant.application.ports.catalogs import Catalog
from sextant.application.resolve.beans import (
    NO_RECIPE,
    UNREAD_TYPE,
    Ambiguous,
    BeanRef,
    NotProvided,
    Parameter,
    ProvidedBy,
    Unresolved,
    bean_table,
    declared_beans,
    injected_parameters,
    qualifier_of,
)
from sextant.domain.closed_sets import ConstructKind, OriginTier
from sextant.domain.factfile import write_fact_file
from sextant.domain.facts import (
    AnnotationFact,
    AnnotationUse,
    Document,
    Signature,
    SymbolFact,
    TypeHeaderFact,
    TypeRef,
)
from sextant.domain.facts import Parameter as DeclaredParameter
from sextant.ingress.catalogs.yaml_source import YamlCatalogSource
from sextant.resources import catalogs_dir
from sextant.storage.duckdb.workspace import DuckDbWorkspace

# The module-coordinates prefix a real symbol fact's own `symbol` carries (D00
# §5a; `test_conditions.py`'s precedent): `annotations.target` and
# `method_declarations.symbol` both carry it, and `BeanRef.method` is that full
# symbol, so a fixture using bare descriptors could not tell a fold that joined
# the two tables from one that did not.
_MODULE = "sextant-jvm maven com.acme/orders-service 1.0.0 "
_CONFIG = "com/acme/MessagingConfig#"
# Real descriptors carry the `sig_` disambiguator; the bean NAME is the method's
# plain name with it stripped (`domain.symbols.method_name`).
_ORDERS_CHANNEL = _CONFIG + "ordersChannel(sig_1a2b3c4d)."
_CONTAINER = _CONFIG + "container(sig_3c4d5e6f)."
_OTHER_CONTAINER = _CONFIG + "otherContainer(sig_4d5e6f70)."
_NAMED_BEAN = _CONFIG + "y(sig_5e6f7081)."
_HELPER = _CONFIG + "helper(sig_6f708192)."

_SPRING = yaml.safe_load(
    (catalogs_dir() / "bean-models" / "spring.yml").read_text(encoding="utf-8")
)
_BEAN = "org/springframework/context/annotation/Bean#"
_QUALIFIER = "org/springframework/beans/factory/annotation/Qualifier#"
_PRIMARY = "org/springframework/context/annotation/Primary#"
_CHANNEL_TYPE = "org/springframework/messaging/MessageChannel#"
_CONTAINER_TYPE = "org/springframework/amqp/rabbit/listener/SimpleMessageListenerContainer#"


def _document() -> Document:
    return Document(
        document_id="doc_1",
        relative_path="com/acme/MessagingConfig.java",
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


def _method(bare: str, returns: str | None = None) -> SymbolFact:
    return SymbolFact(
        document_id="doc_1",
        symbol=_MODULE + bare,
        construct_kind=ConstructKind.METHOD,
        enclosing=_MODULE + _CONFIG,
        signature=Signature(
            parameters=[],
            returns=None if returns is None else TypeRef(symbol=returns),
        ),
    )


def _bean(
    bare: str, returns: str, *, annotation: str = _BEAN, args: dict | None = None
) -> list[SymbolFact | AnnotationFact]:
    """A declared factory method: its symbol fact and the declaring annotation on it."""
    return [
        _method(bare, returns),
        AnnotationFact(
            document_id="doc_1",
            target=_MODULE + bare,
            retention="runtime",
            use=AnnotationUse(annotation=annotation, args=args or {}),
        ),
    ]


def _primary(bare: str) -> AnnotationFact:
    """The primary-marking annotation on a declared factory method."""
    return AnnotationFact(
        document_id="doc_1",
        target=_MODULE + bare,
        retention="runtime",
        use=AnnotationUse(annotation=_PRIMARY, args={}),
    )


def _catalog(model: dict, catalog_id: str = "invented") -> Catalog:
    return Catalog(
        id=catalog_id,
        style="fluent",
        protocol="",
        direction="",
        requires=(),
        matches={},
        source=Path(f"{catalog_id}.yml"),
        bean_model=model,
    )


def _library_headers() -> list[TypeHeaderFact]:
    """The class-file headers a resolved classpath gives for the library types these tests
    use, so their place in the hierarchy is known (`beans.TypeLattice`)."""
    channel = "org/springframework/messaging/MessageChannel#"
    supertypes = {
        channel: (),
        "org/springframework/messaging/SubscribableChannel#": (channel,),
        "org/springframework/messaging/PollableChannel#": (channel,),
        "org/springframework/integration/channel/DirectChannel#": (
            "org/springframework/messaging/SubscribableChannel#",
        ),
        _CONTAINER_TYPE: (),
    }
    return [
        TypeHeaderFact(
            document_id="doc_1",
            symbol="sextant-jvm maven org.springframework/spring 6.1.6 " + bare,
            construct_kind=ConstructKind.INTERFACE if "messaging" in bare else ConstructKind.CLASS,
            interfaces=list(interfaces),
            origin="org.springframework:spring",
            version="6.1.6",
        )
        for bare, interfaces in supertypes.items()
    ]


def _loaded(tmp_path: Path, facts: list) -> DuckDbWorkspace:
    facts = _library_headers() + facts
    write_fact_file(tmp_path / "facts" / "MessagingConfig.jsonl", _document(), facts)
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    return workspace


def _parameter(
    erased_type: str, name: str | None, qualifier: str | None = None, index: int = 0
) -> Parameter:
    return Parameter(
        method=_MODULE + _HELPER,
        index=index,
        erased_type=erased_type,
        name=name,
        qualifier=qualifier,
    )


def _orders_channel_ref() -> BeanRef:
    return BeanRef(
        method=_MODULE + _ORDERS_CHANNEL, name="ordersChannel", erased_return=_CHANNEL_TYPE
    )


# --- the rungs, per reference kind ------------------------------------------------


def test_a_qualifier_names_the_bean(tmp_path: Path):
    """The first rung for EVERY reference kind: a qualifier names the bean outright,
    whatever the parameter is called and whatever its type. A qualifier naming no
    bean and no known channel is `none` — never a fall-through to the later rungs,
    which is what the container does too (an explicit qualifier that matches
    nothing fails the injection rather than widening it)."""
    workspace = _loaded(tmp_path, _bean(_ORDERS_CHANNEL, _CHANNEL_TYPE) + [_method(_HELPER)])
    table = bean_table(workspace, _catalog(_SPRING), known_channels=frozenset({"auditChannel"}))
    workspace.close()

    assert table.bean_of(_parameter(_CHANNEL_TYPE, "inputChannel", qualifier="ordersChannel")) == (
        _orders_channel_ref()
    )
    # A qualifier naming a channel the index knows but no method declares.
    assert table.bean_of(_parameter(_CHANNEL_TYPE, "inputChannel", qualifier="auditChannel")) == (
        BeanRef(method=None, name="auditChannel", erased_return=None)
    )
    assert table.bean_of(_parameter(_CHANNEL_TYPE, "ordersChannel", qualifier="nothing")) == (
        Unresolved("none")
    )


def test_a_qualifier_on_a_non_channel_parameter_never_becomes_a_known_channel(tmp_path: Path):
    """Fix round 1. The container auto-creates a CHANNEL under a referenced name
    and nothing else, so a qualifier on a container-typed parameter that names
    no declared bean is `none` even when a channel the index knows shares the
    name — never a phantom `BeanRef(method=None)` of a type the container would
    not inject. The same qualifier on a channel-typed parameter IS that channel."""
    workspace = _loaded(tmp_path, _bean(_CONTAINER, _CONTAINER_TYPE) + [_method(_HELPER)])
    table = bean_table(workspace, _catalog(_SPRING), known_channels=frozenset({"auditChannel"}))
    workspace.close()

    assert table.bean_of(_parameter(_CONTAINER_TYPE, "c", qualifier="auditChannel")) == (
        Unresolved("none")
    )
    assert table.bean_of(_parameter(_CHANNEL_TYPE, "c", qualifier="auditChannel")) == BeanRef(
        method=None, name="auditChannel", erased_return=None
    )


def test_a_channel_parameter_resolves_by_name_never_by_type(tmp_path: Path):
    """Spec §0b A2. One `@Bean MessageChannel ordersChannel()` in the module; the
    parameter `inputChannel` of that type is NOT it — the container sees
    `errorChannel` and `nullChannel` beside it and resolves by name, so a fold
    picking the module's single channel by type would name a bean the container
    never injects. The parameter `ordersChannel` is it."""
    workspace = _loaded(tmp_path, _bean(_ORDERS_CHANNEL, _CHANNEL_TYPE) + [_method(_HELPER)])
    table = bean_table(workspace, _catalog(_SPRING), known_channels=frozenset())
    workspace.close()

    assert table.kind_of(_CHANNEL_TYPE) == "channel"
    assert table.bean_of(_parameter(_CHANNEL_TYPE, "inputChannel")) == Unresolved("none")
    assert table.bean_of(_parameter(_CHANNEL_TYPE, "ordersChannel")) == _orders_channel_ref()


@pytest.mark.parametrize(
    "interface",
    [
        "org/springframework/messaging/SubscribableChannel#",
        "org/springframework/messaging/PollableChannel#",
    ],
)
def test_every_channel_interface_the_framework_beans_implement_is_a_channel(
    tmp_path: Path, interface: str
):
    """Fix round 1. The model lists the channel INTERFACES the framework's own
    beans implement — `errorChannel` is a `SubscribableChannel`, `nullChannel`
    both — because a parameter declared by any of them has those beans among its
    candidates and resolves by name; the module's single `@Bean` of the interface
    is not unique. A concrete channel CLASS is not listed: no framework bean is
    of it, so the module's single `@Bean DirectChannel` is the unique candidate
    and the type rung is right."""
    direct = "org/springframework/integration/channel/DirectChannel#"
    facts = _bean(_ORDERS_CHANNEL, interface) + _bean(_CONTAINER, direct) + [_method(_HELPER)]
    workspace = _loaded(tmp_path, facts)
    table = bean_table(workspace, _catalog(_SPRING), known_channels=frozenset())
    workspace.close()

    assert table.kind_of(interface) == "channel"
    assert table.bean_of(_parameter(interface, "inputChannel")) == Unresolved("none")
    assert table.kind_of(direct) == "other"
    assert table.bean_of(_parameter(direct, "inputChannel")) == BeanRef(
        method=_MODULE + _CONTAINER, name="container", erased_return=direct
    )


def test_a_channel_name_the_index_knows_resolves_without_a_bean(tmp_path: Path):
    """The container auto-creates a channel under a referenced name, so a
    parameter named like a channel the handler index knows IS that channel
    even though no method declares it: `method` is None, the name is the
    identity. A name neither declared nor known stays `none`."""
    workspace = _loaded(tmp_path, [_method(_HELPER)])
    table = bean_table(workspace, _catalog(_SPRING), known_channels=frozenset({"auditChannel"}))
    workspace.close()

    assert table.bean_of(_parameter(_CHANNEL_TYPE, "auditChannel")) == (
        BeanRef(method=None, name="auditChannel", erased_return=None)
    )
    assert table.bean_of(_parameter(_CHANNEL_TYPE, "billingChannel")) == Unresolved("none")


def test_a_container_parameter_resolves_by_unique_type_then_name(tmp_path: Path):
    """The container's own candidate order for a type no framework bean shares
    (cited on `bean-models/spring.yml`, CP-27): one bean of
    the type is it whatever the parameter is called; two are `ambiguous` — unless
    one is primary (the next test) or the parameter is named like one of them,
    which is the name rung."""
    one = _bean(_CONTAINER, _CONTAINER_TYPE) + [_method(_HELPER)]
    workspace = _loaded(tmp_path, one)
    table = bean_table(workspace, _catalog(_SPRING), known_channels=frozenset())
    workspace.close()

    assert table.kind_of(_CONTAINER_TYPE) == "other"
    assert table.bean_of(_parameter(_CONTAINER_TYPE, "anything")) == BeanRef(
        method=_MODULE + _CONTAINER, name="container", erased_return=_CONTAINER_TYPE
    )
    # A type nothing declares is `none`, not `ambiguous`.
    assert table.bean_of(_parameter("com/acme/Missing#", "nothing")) == Unresolved("none")

    two = one + _bean(_OTHER_CONTAINER, _CONTAINER_TYPE)
    workspace = _loaded(tmp_path / "two", two)
    table = bean_table(workspace, _catalog(_SPRING), known_channels=frozenset())
    workspace.close()

    assert table.bean_of(_parameter(_CONTAINER_TYPE, "anything")) == Unresolved("ambiguous")
    assert table.bean_of(_parameter(_CONTAINER_TYPE, "otherContainer")) == BeanRef(
        method=_MODULE + _OTHER_CONTAINER, name="otherContainer", erased_return=_CONTAINER_TYPE
    )


def _header(bare: str, superclass: str | None = None, interfaces: tuple[str, ...] = ()):
    """A dependency type whose class-file header was read: its place in the hierarchy is known."""
    return TypeHeaderFact(
        document_id="doc_1",
        symbol="sextant-jvm maven com.vendor/lib 1.0.0 " + bare,
        construct_kind=ConstructKind.CLASS,
        superclass=superclass,
        interfaces=list(interfaces),
        origin="com.vendor:lib",
        version="1.0.0",
    )


_SUPERTYPE = "com/acme/Supertype#"


@pytest.mark.pins("beans.the-NAME-rung-reads-only-the-TYPE-s-candidates")
@pytest.mark.pins("beans.the-TYPE-rung-counts-SUBTYPES")
def test_the_rungs_read_only_the_beans_of_the_parameter_s_type(tmp_path: Path):
    """Task 3 review m3, whole-branch review m3. The container weighs only the candidates of
    the parameter's type (`findAutowireCandidates`): a bean of the type or of a subtype of it.
    So a bean whose type extends the parameter's is the only bean of that type, whatever the
    parameter is called; and a bean of an unrelated type that shares the parameter's name,
    or that its qualifier names, is never injected. Here every type on the bean's walk was
    read (two dependency headers), so "unrelated" is known, not guessed."""
    facts = (
        _bean(_CONTAINER, _CONTAINER_TYPE)
        + [_method(_HELPER)]
        + [_header(_CONTAINER_TYPE, superclass=_SUPERTYPE), _header(_SUPERTYPE)]
    )
    workspace = _loaded(tmp_path, facts)
    table = bean_table(workspace, _catalog(_SPRING), known_channels=frozenset())
    workspace.close()

    assert table.bean_of(_parameter("com/acme/Unrelated#", "container")) == Unresolved("none")
    assert table.bean_of(_parameter("com/acme/Unrelated#", "c", qualifier="container")) == (
        Unresolved("none")
    )
    container = BeanRef(
        method=_MODULE + _CONTAINER, name="container", erased_return=_CONTAINER_TYPE
    )
    assert table.bean_of(_parameter(_SUPERTYPE, "anything")) == container
    assert table.bean_of(_parameter(_SUPERTYPE, "c", qualifier="container")) == container


@pytest.mark.pins("beans.a-bean-of-UNREAD-hierarchy-is-kept-by-the-QUALIFIER-only")
def test_a_bean_whose_hierarchy_was_not_read_is_kept_by_the_qualifier_only(tmp_path: Path):
    """Whole-branch review m1. `@Bean ThreadPoolExecutor pool()` injected as
    `@Qualifier("pool") ExecutorService`: the JDK's types have no header, so the walk from
    `ThreadPoolExecutor` cannot say whether it reaches `ExecutorService`. A qualifier naming
    a bean that is not assignable fails the container's start, so the qualifier rung keeps it.
    The type and name rungs need the hierarchy and do not choose it: `none`, never a guess.
    A parameter of a MODULE type cannot be filled by a type outside the module (a dependency
    does not depend on the module), so there the unread bean is not a candidate."""
    executor = "java/util/concurrent/ExecutorService#"
    pool_type = "java/util/concurrent/ThreadPoolExecutor#"
    pool = _CONFIG + "pool(sig_7a8b9c0d)."
    facts = _bean(pool, pool_type) + [
        _method(_HELPER),
        SymbolFact(document_id="doc_1", symbol=_MODULE + "com/acme/Orders#",
                   construct_kind=ConstructKind.CLASS),
    ]  # fmt: skip
    workspace = _loaded(tmp_path, facts)
    table = bean_table(workspace, _catalog(_SPRING), known_channels=frozenset())
    workspace.close()

    bean = BeanRef(method=_MODULE + pool, name="pool", erased_return=pool_type)
    assert table.bean_of(_parameter(executor, "e", qualifier="pool")) == bean
    assert table.bean_of(_parameter(executor, "pool")) == Unresolved("none")
    assert table.bean_of(_parameter("com/acme/Orders#", "o", qualifier="pool")) == (
        Unresolved("none")
    )


def test_one_primary_among_the_type_candidates_wins_over_the_name_match(tmp_path: Path):
    """Final fix wave, item 1. Two beans of the container type, one marked
    primary, and a parameter NAMED after the other: the container injects the
    primary (`determineAutowireCandidate` tries `determinePrimaryCandidate`
    before it compares names — spring-beans 6.1.6, CP-27 row 15), so the fold
    answers the primary and never the name match, which would fold the wrong
    container's queues into the row. A parameter named after neither takes the
    primary too."""
    facts = (
        _bean(_CONTAINER, _CONTAINER_TYPE)
        + [_primary(_CONTAINER)]
        + _bean(_OTHER_CONTAINER, _CONTAINER_TYPE)
        + [_method(_HELPER)]
    )
    workspace = _loaded(tmp_path, facts)
    table = bean_table(workspace, _catalog(_SPRING), known_channels=frozenset())
    workspace.close()

    primary = BeanRef(
        method=_MODULE + _CONTAINER, name="container", erased_return=_CONTAINER_TYPE, primary=True
    )
    assert table.bean_of(_parameter(_CONTAINER_TYPE, "otherContainer")) == primary
    assert table.bean_of(_parameter(_CONTAINER_TYPE, "anything")) == primary
    # A qualifier still comes first — it names the other bean outright.
    assert table.bean_of(_parameter(_CONTAINER_TYPE, "c", qualifier="otherContainer")) == BeanRef(
        method=_MODULE + _OTHER_CONTAINER, name="otherContainer", erased_return=_CONTAINER_TYPE
    )


def test_two_primaries_among_the_type_candidates_are_ambiguous(tmp_path: Path):
    """Two primaries of one type fail the container's injection
    (`determinePrimaryCandidate` raises `NoUniqueBeanDefinitionException` when
    both are the factory's own definitions — CP-27 Q15), so the fold does not
    fall through to the name rung either: `ambiguous`, even for a parameter
    named after one of them."""
    facts = (
        _bean(_CONTAINER, _CONTAINER_TYPE)
        + [_primary(_CONTAINER)]
        + _bean(_OTHER_CONTAINER, _CONTAINER_TYPE)
        + [_primary(_OTHER_CONTAINER), _method(_HELPER)]
    )
    workspace = _loaded(tmp_path, facts)
    table = bean_table(workspace, _catalog(_SPRING), known_channels=frozenset())
    workspace.close()

    assert table.bean_of(_parameter(_CONTAINER_TYPE, "otherContainer")) == Unresolved("ambiguous")
    assert table.bean_of(_parameter(_CONTAINER_TYPE, "anything")) == Unresolved("ambiguous")


def test_a_primary_on_a_channel_bean_changes_nothing(tmp_path: Path):
    """A channel reference is never resolved by type (spec §0b A2), so the
    primary rung — a choice AMONG type candidates — never runs for it: the
    parameter's name is still the one rung, and a primary channel bean whose
    name is not the parameter's is still `none`."""
    facts = _bean(_ORDERS_CHANNEL, _CHANNEL_TYPE) + [_primary(_ORDERS_CHANNEL), _method(_HELPER)]
    workspace = _loaded(tmp_path, facts)
    table = bean_table(workspace, _catalog(_SPRING), known_channels=frozenset())
    workspace.close()

    assert table.bean_of(_parameter(_CHANNEL_TYPE, "inputChannel")) == Unresolved("none")
    assert table.bean_of(_parameter(_CHANNEL_TYPE, "ordersChannel")) == BeanRef(
        method=_MODULE + _ORDERS_CHANNEL,
        name="ordersChannel",
        erased_return=_CHANNEL_TYPE,
        primary=True,
    )


@pytest.mark.parametrize(
    "args",
    [
        pytest.param({"name": ["x"]}, id="name-as-array"),
        pytest.param({"value": ["x"]}, id="value-as-array"),
        pytest.param({"name": "x"}, id="name-as-string"),
        pytest.param({"value": ["x", "alias"]}, id="first-of-several"),
    ],
)
def test_a_bean_named_by_the_name_attribute_wins_over_the_method_name(tmp_path: Path, args: dict):
    """`@Bean(name = "x") String y()` is the bean `x` (spec §0a F8: `name()` and
    `value()` are aliases, both `String[]`). The scanner records an array
    attribute as a list and a single string as itself (D00 §5's literal
    model); the first element is the name, so both forms are pinned, and the
    method's own name no longer answers for it."""
    workspace = _loaded(
        tmp_path, _bean(_NAMED_BEAN, "java/lang/String#", args=args) + [_method(_HELPER)]
    )
    table = bean_table(workspace, _catalog(_SPRING), known_channels=frozenset())
    workspace.close()

    expected = BeanRef(method=_MODULE + _NAMED_BEAN, name="x", erased_return="java/lang/String#")
    assert table.bean_of(_parameter("java/lang/String#", "x")) == expected
    assert table.bean_called(_MODULE + _NAMED_BEAN) == expected
    assert table.bean_of(_parameter("com/acme/Other#", "y")) == Unresolved("none")


def test_a_direct_call_to_a_bean_method_names_it(tmp_path: Path):
    """`channel(ordersChannel())` inside another `@Bean` method — the reference is
    the declaring method itself, no parameter in between. A call to a method
    that declares no bean is None: it is an ordinary call, not an injection."""
    workspace = _loaded(tmp_path, _bean(_ORDERS_CHANNEL, _CHANNEL_TYPE) + [_method(_HELPER)])
    table = bean_table(workspace, _catalog(_SPRING), known_channels=frozenset())
    workspace.close()

    assert table.bean_called(_MODULE + _ORDERS_CHANNEL) == _orders_channel_ref()
    assert table.bean_called(_MODULE + _HELPER) is None


def test_a_nameless_parameter_skips_the_name_rung(tmp_path: Path):
    """A method compiled without `-parameters` carries no parameter names (spec
    §3a). The type rung still answers for a container; a channel, which has no
    rung but the name, is `none` — never `ambiguous`, because no candidate was
    ever weighed."""
    facts = (
        _bean(_CONTAINER, _CONTAINER_TYPE)
        + _bean(_ORDERS_CHANNEL, _CHANNEL_TYPE)
        + [_method(_HELPER)]
    )
    workspace = _loaded(tmp_path, facts)
    table = bean_table(workspace, _catalog(_SPRING), known_channels=frozenset({"ordersChannel"}))
    workspace.close()

    assert table.bean_of(_parameter(_CONTAINER_TYPE, None)) == BeanRef(
        method=_MODULE + _CONTAINER, name="container", erased_return=_CONTAINER_TYPE
    )
    assert table.bean_of(_parameter(_CHANNEL_TYPE, None)) == Unresolved("none")


def test_two_declarations_of_one_bean_name_are_ambiguous_by_name(tmp_path: Path):
    """Spec §3a: a rung with two candidates is `Unresolved`, and the name rung is
    a rung. Two `@Bean` methods named `ordersChannel` (a `@Profile` twin — spec
    §0c B5, recorded and not evaluated) are two candidates for the name; each is
    still the bean a DIRECT call to it names, because that reference has no
    name to be ambiguous about."""
    twin = _CONFIG + "ordersChannel(sig_7081a2b3)."
    facts = _bean(_ORDERS_CHANNEL, _CHANNEL_TYPE) + _bean(twin, _CHANNEL_TYPE) + [_method(_HELPER)]
    workspace = _loaded(tmp_path, facts)
    table = bean_table(workspace, _catalog(_SPRING), known_channels=frozenset())
    workspace.close()

    assert table.bean_of(_parameter(_CHANNEL_TYPE, "ordersChannel")) == Unresolved("ambiguous")
    assert table.bean_of(_parameter(_CHANNEL_TYPE, "x", qualifier="ordersChannel")) == (
        Unresolved("ambiguous")
    )
    assert table.bean_called(_MODULE + twin) == BeanRef(
        method=_MODULE + twin, name="ordersChannel", erased_return=_CHANNEL_TYPE
    )


# --- the qualifier helper -------------------------------------------------------


def test_qualifier_of_reads_the_qualifier_annotation_off_a_parameter():
    """The caller reads a declared parameter's own annotations
    (`Parameter.annotations` on the signature) and asks this for the name — a
    string or the first element of an array, None when the parameter carries no
    qualifier at all. Another annotation on the parameter is not one."""

    def declared(*uses: AnnotationUse) -> list[dict]:
        # The form the caller holds: `method_declarations.signature` arrives as
        # decoded JSON, so a parameter's annotations are dicts, never models.
        parameter = DeclaredParameter(
            name="c", type=TypeRef(symbol=_CHANNEL_TYPE), annotations=uses
        )
        return parameter.model_dump()["annotations"]

    qualified = declared(AnnotationUse(annotation=_QUALIFIER, args={"value": "ordersChannel"}))
    array = declared(AnnotationUse(annotation=_QUALIFIER, args={"value": ["ordersChannel"]}))
    other = declared(AnnotationUse(annotation=_BEAN, args={"value": "ordersChannel"}))
    assert qualifier_of(qualified, _SPRING) == "ordersChannel"
    assert qualifier_of(array, _SPRING) == "ordersChannel"
    assert qualifier_of(other, _SPRING) is None
    assert qualifier_of(declared(), _SPRING) is None


# --- the fold: once per load and per model, and no framework of its own ------------


def test_the_fold_is_shared_by_every_catalog_naming_the_same_model(tmp_path: Path):
    """GUIDELINES §8.7: the fold reads every method declaration and every
    annotation once per load and per MODEL, not once per catalog — two catalogs
    naming `spring` share it, and a catalog naming a different model gets its
    own, because the model is what the fold is a function of. The invented
    model is also the proof that the module spells no framework: its own
    annotation and channel type are what the same facts are read through."""
    invented = {
        "id": "invented",
        "declaring_annotation": "com.acme.di.Provides",
        "name_attrs": ["named"],
        "qualifier_annotation": "com.acme.di.Named",
        "primary_annotation": "com.acme.di.Preferred",
        "channel_types": ["com.acme.di.Pipe"],
    }
    facts = (
        _bean(_ORDERS_CHANNEL, _CHANNEL_TYPE)
        + _bean(_CONTAINER, "com/acme/di/Pipe#", annotation="com/acme/di/Provides#")
        + [_method(_HELPER)]
    )
    workspace = _loaded(tmp_path, facts)
    bean_table(workspace, _catalog(_SPRING, "one"), known_channels=frozenset())
    bean_table(workspace, _catalog(_SPRING, "two"), known_channels=frozenset())
    other = bean_table(workspace, _catalog(invented, "three"), known_channels=frozenset())
    shared = declared_beans(workspace, _SPRING)
    assert shared is declared_beans(workspace, dict(_SPRING))
    assert declared_beans(workspace, invented) is not shared
    workspace.close()

    # Under the invented model `@Bean` declares nothing and `Provides` does;
    # `Pipe` is the channel type and `MessageChannel` is an ordinary one.
    assert other.bean_called(_MODULE + _ORDERS_CHANNEL) is None
    assert other.kind_of("com/acme/di/Pipe#") == "channel"
    assert other.kind_of(_CHANNEL_TYPE) == "other"
    assert other.bean_of(_parameter("com/acme/di/Pipe#", "container")) == BeanRef(
        method=_MODULE + _CONTAINER, name="container", erased_return="com/acme/di/Pipe#"
    )
    assert other.bean_of(_parameter("com/acme/di/Pipe#", "x")) == Unresolved("none")


# --- which recipe fills a container-filled parameter (spec 2026-11-05 di-recipe-hop §2) ----
#
# `injected_parameters` reads EVERY bean model (D02 §1c), not one catalog's: here the shipped
# `bean-models/` directory, so Dagger's rules are read through `dagger.yml`'s own words and
# Spring's through `spring.yml`'s. Dagger is mirrored exactly (§2a): the key is the qualifier
# with all of its attributes plus the full type, an unqualified parameter matches an
# unqualified recipe only, and a key that is not unique in the module is never a guess.

_MODELS = YamlCatalogSource(catalogs_dir()).bean_models()
_PROVIDES = "dagger/Provides#"
_INJECT = "javax/inject/Inject#"
_NAMED = "javax/inject/Named#"
_BILLING = "com/acme/Billing#"
_NOT_NULL = "org/jetbrains/annotations/NotNull#"
_RETROFIT = "retrofit2/Retrofit#"
_NETWORK = "com/acme/NetworkModule#"
_API = _NETWORK + "api(sig_c3728865)."


def _type(symbol: str, *arguments: TypeRef) -> TypeRef:
    return TypeRef(symbol=symbol, arguments=list(arguments))


def _slot(declared: TypeRef, *uses: AnnotationUse, name: str = "retrofit") -> DeclaredParameter:
    return DeclaredParameter(
        name=name, type=declared, erased_symbol=declared.symbol, annotations=list(uses)
    )


def _recipe(
    bare: str,
    returns: TypeRef,
    *annotations: AnnotationUse,
    parameters: tuple[DeclaredParameter, ...] = (),
    static: bool = False,
    declaring: str = _PROVIDES,
) -> list[SymbolFact | AnnotationFact]:
    """A method carrying `declaring` and `annotations`, as the scanner records it: one symbol
    fact with its signature and modifiers, one annotation fact per use on the method."""
    owner = bare.partition("#")[0] + "#"
    return [
        SymbolFact(
            document_id="doc_1",
            symbol=_MODULE + bare,
            construct_kind=ConstructKind.METHOD,
            enclosing=_MODULE + owner,
            signature=Signature(parameters=list(parameters), returns=returns),
            modifiers={"static": static},
        )
    ] + [
        AnnotationFact(document_id="doc_1", target=_MODULE + bare, retention="runtime", use=use)
        for use in (AnnotationUse(annotation=declaring), *annotations)
    ]


def _qualifier_types() -> list[SymbolFact | AnnotationFact | TypeHeaderFact]:
    """`@Named` as a library type whose header was read (javax.inject's own jar), and the
    module's own `@Billing`: each carries `javax.inject.Qualifier`, which is what makes it a
    qualifier. `@NotNull` (its jar's header read) carries nothing, so it never is one."""
    return [
        TypeHeaderFact(
            document_id="doc_1",
            symbol="sextant-jvm maven org.jetbrains/annotations 13.0 " + _NOT_NULL,
            construct_kind=ConstructKind.ANNOTATION,
            origin="org.jetbrains:annotations",
            version="13.0",
        ),
        TypeHeaderFact(
            document_id="doc_1",
            symbol="sextant-jvm maven javax.inject/javax.inject 1 " + _NAMED,
            construct_kind=ConstructKind.ANNOTATION,
            annotations=[AnnotationUse(annotation="javax/inject/Qualifier#")],
            origin="javax.inject:javax.inject",
            version="1",
        ),
        SymbolFact(
            document_id="doc_1", symbol=_MODULE + _BILLING, construct_kind=ConstructKind.ANNOTATION
        ),
        AnnotationFact(
            document_id="doc_1",
            target=_MODULE + _BILLING,
            retention="runtime",
            use=AnnotationUse(annotation="javax/inject/Qualifier#"),
        ),
    ]


def _named(value: str) -> AnnotationUse:
    return AnnotationUse(annotation=_NAMED, args={"value": value})


def _consumer(*uses: AnnotationUse, declared: TypeRef | None = None) -> list:
    """`@Provides fun api(retrofit: Retrofit): OrdersApi` — the recipe whose parameter the
    container fills, carrying `uses` on that parameter."""
    return _recipe(
        _API,
        _type("com/acme/OrdersApi#"),
        parameters=(_slot(declared or _type(_RETROFIT), *uses),),
    )


_VALUE = "org.springframework.beans.factory.annotation.Value"


def _injections(tmp_path: Path, facts: list) -> dict:
    workspace = _loaded(tmp_path, _qualifier_types() + facts)
    try:
        return dict(injected_parameters(workspace, _MODELS, (_VALUE,)))
    finally:
        workspace.close()


@pytest.mark.pins("beans.a-QUALIFIED-recipe-never-fills-an-UNQUALIFIED-parameter")
def test_an_unqualified_parameter_gets_the_one_unqualified_recipe(tmp_path: Path):
    """Measured on Dagger 2.57.2: an unqualified `Retrofit` parameter got the unqualified
    recipe although a `@Named("pay")` and a `@Billing` recipe of the same type were in the
    same module. A qualified recipe is not a candidate for an unqualified request (Spring
    differs here). An annotation that is not a qualifier (`@NotNull`) changes nothing. The
    recipe is an instance method, as in a Kotlin `object` module."""
    found = _injections(
        tmp_path,
        _recipe(_NETWORK + "retrofit(sig_e61c31ac).", _type(_RETROFIT))
        + _recipe(_NETWORK + "payRetrofit(sig_e61c31ac).", _type(_RETROFIT), _named("pay"))
        + _recipe(
            _NETWORK + "billingRetrofit(sig_e61c31ac).",
            _type(_RETROFIT),
            AnnotationUse(annotation=_BILLING),
        )
        + _consumer(AnnotationUse(annotation=_NOT_NULL)),
    )

    assert found[(_MODULE + _API, 0)] == ProvidedBy(_MODULE + _NETWORK + "retrofit(sig_e61c31ac).")


def test_two_unqualified_recipes_of_one_key_are_ambiguous(tmp_path: Path):
    """Dagger refuses two recipes of one key on one component (`DuplicateBindings`), but
    the same two in modules on DIFFERENT components compile, and Sextant sees the whole
    module, not the component. Two in the module is `ambiguous`, never a guess."""
    first = "com/acme/JavaModule#retrofit(sig_e61c31ac)."
    second = _NETWORK + "retrofit(sig_e61c31ac)."
    found = _injections(
        tmp_path,
        _recipe(first, _type(_RETROFIT), static=True)
        + _recipe(second, _type(_RETROFIT))
        + _consumer(),
    )

    assert found[(_MODULE + _API, 0)] == Ambiguous((_MODULE + first, _MODULE + second))


_REGION = "com/vendor/Region#"


@pytest.mark.pins("beans.an-UNREAD-annotation-may-be-a-QUALIFIER")
def test_an_annotation_whose_type_was_not_read_may_be_a_qualifier(tmp_path: Path):
    """Whole-branch review m2. Whether an annotation is a qualifier is read off its type; a
    type that is neither the module's nor a read dependency header (`@Region`, its jar not
    resolved) may be one. An unqualified slot carrying it, or an unqualified recipe of the
    slot's type carrying it, cannot be keyed: `unread_type`, never the unqualified recipe.
    Dagger refuses two qualifiers on one binding, so beside a qualifier that WAS read the
    unread annotation is not one."""
    plain = _NETWORK + "retrofit(sig_e61c31ac)."
    pay = _NETWORK + "payRetrofit(sig_e61c31ac)."
    region = AnnotationUse(annotation=_REGION)
    recipes = _recipe(plain, _type(_RETROFIT)) + _recipe(pay, _type(_RETROFIT), _named("pay"))

    assert _injections(tmp_path / "slot", recipes + _consumer(region))[
        (_MODULE + _API, 0)
    ] == NotProvided(UNREAD_TYPE)
    assert _injections(tmp_path / "qualified", recipes + _consumer(_named("pay"), region))[
        (_MODULE + _API, 0)
    ] == ProvidedBy(_MODULE + pay)
    other = _NETWORK + "regionRetrofit(sig_e61c31ac)."
    unread_recipe = recipes + _recipe(other, _type(_RETROFIT), region)
    assert _injections(tmp_path / "recipe", unread_recipe + _consumer())[
        (_MODULE + _API, 0)
    ] == NotProvided(UNREAD_TYPE)


def test_no_recipe_of_the_key_is_not_provided(tmp_path: Path):
    """A key no recipe in the module provides (a recipe in another Gradle module, an
    `@Inject` class, `@BindsInstance`): `none`, never the nearest recipe."""
    found = _injections(
        tmp_path,
        _recipe(_NETWORK + "payRetrofit(sig_e61c31ac).", _type(_RETROFIT), _named("pay"))
        + _consumer(),
    )

    assert found[(_MODULE + _API, 0)] == NotProvided(NO_RECIPE)


@pytest.mark.pins("beans.a-QUALIFIER-s-ATTRIBUTES-are-part-of-the-key")
@pytest.mark.pins("beans.a-QUALIFIED-recipe-never-fills-an-UNQUALIFIED-parameter")
def test_a_qualifier_matches_with_all_of_its_attributes(tmp_path: Path):
    """`@Named("a")` and `@Named("b")` are two keys: each parameter gets its own recipe,
    and `@Named("c")` gets none, never a recipe of another name."""
    recipes = _recipe(_NETWORK + "a(sig_e61c31ac).", _type(_RETROFIT), _named("a")) + _recipe(
        _NETWORK + "b(sig_e61c31ac).", _type(_RETROFIT), _named("b")
    )

    for value, expected in (
        ("a", ProvidedBy(_MODULE + _NETWORK + "a(sig_e61c31ac).")),
        ("b", ProvidedBy(_MODULE + _NETWORK + "b(sig_e61c31ac).")),
        ("c", NotProvided(NO_RECIPE)),
    ):
        found = _injections(tmp_path / value, recipes + _consumer(_named(value)))
        assert found[(_MODULE + _API, 0)] == expected, value


@pytest.mark.pins("beans.a-QUALIFIED-recipe-never-fills-an-UNQUALIFIED-parameter")
def test_the_module_s_own_qualifier_is_one(tmp_path: Path):
    """`@Billing` is a qualifier because its own type carries `javax.inject.Qualifier`: the
    `@Billing` parameter gets the `@Billing` recipe, not the unqualified one."""
    billing = _NETWORK + "billingRetrofit(sig_e61c31ac)."
    found = _injections(
        tmp_path,
        _recipe(_NETWORK + "retrofit(sig_e61c31ac).", _type(_RETROFIT))
        + _recipe(billing, _type(_RETROFIT), AnnotationUse(annotation=_BILLING))
        + _consumer(AnnotationUse(annotation=_BILLING)),
    )

    assert found[(_MODULE + _API, 0)] == ProvidedBy(_MODULE + billing)


@pytest.mark.pins("beans.TYPE-ARGUMENTS-are-part-of-the-key")
def test_type_arguments_are_part_of_the_key(tmp_path: Path):
    """`List<String>` and `List<Integer>` are two keys in Dagger, one erasure on the JVM."""
    strings = _NETWORK + "strings(sig_3f061508)."
    numbers = _NETWORK + "numbers(sig_3f061508)."
    listed = _type("java/util/List#", _type("java/lang/Integer#"))
    found = _injections(
        tmp_path,
        _recipe(strings, _type("java/util/List#", _type("java/lang/String#")))
        + _recipe(numbers, listed)
        + _consumer(declared=listed),
    )

    assert found[(_MODULE + _API, 0)] == ProvidedBy(_MODULE + numbers)


@pytest.mark.pins("beans.a-MULTIBINDING-recipe-never-fills-T")
def test_a_multibinding_contribution_is_never_the_recipe_for_its_type(tmp_path: Path):
    """An `@IntoSet` recipe of `String` adds an element to `Set<String>`; it does not
    provide `String`. Alone it is no recipe for a `String` parameter; beside a plain
    `String` recipe, the plain one is the only candidate."""
    into_set = _recipe(
        _NETWORK + "element(sig_aa).",
        _type("java/lang/String#"),
        AnnotationUse(annotation="dagger/multibindings/IntoSet#"),
    )
    plain = _NETWORK + "plain(sig_aa)."
    consumer = _consumer(declared=_type("java/lang/String#"))

    assert _injections(tmp_path / "alone", into_set + consumer)[(_MODULE + _API, 0)] == (
        NotProvided(NO_RECIPE)
    )
    beside = _injections(
        tmp_path / "beside", into_set + _recipe(plain, _type("java/lang/String#")) + consumer
    )
    assert beside[(_MODULE + _API, 0)] == ProvidedBy(_MODULE + plain)


@pytest.mark.pins("beans.an-INJECT-constructor-s-parameters-are-container-filled")
def test_an_inject_constructor_s_parameters_are_container_filled(tmp_path: Path):
    """`class OrdersRepo @Inject constructor(retrofit: Retrofit)`: the container fills the
    constructor's parameters by the same key. A constructor with no `@Inject` is not the
    container's to fill, so it has no entry."""
    inject = "com/acme/OrdersRepo#<init>(sig_be4b88df)."
    plain = "com/acme/Plain#<init>(sig_be4b88df)."
    retrofit = _NETWORK + "retrofit(sig_e61c31ac)."

    def constructor(bare: str) -> SymbolFact:
        return SymbolFact(
            document_id="doc_1",
            symbol=_MODULE + bare,
            construct_kind=ConstructKind.CONSTRUCTOR,
            enclosing=_MODULE + bare.partition("#")[0] + "#",
            signature=Signature(parameters=[_slot(_type(_RETROFIT))], returns=_type("void#")),
        )

    found = _injections(
        tmp_path,
        _recipe(retrofit, _type(_RETROFIT))
        + [constructor(inject), constructor(plain)]
        + [
            AnnotationFact(
                document_id="doc_1",
                target=_MODULE + inject,
                retention="runtime",
                use=AnnotationUse(annotation=_INJECT),
            )
        ],
    )

    assert found[(_MODULE + inject, 0)] == ProvidedBy(_MODULE + retrofit)
    assert (_MODULE + plain, 0) not in found


@pytest.mark.pins("beans.a-COMPANION-recipe-and-its-STATIC-FORWARDER-are-one")
def test_a_companion_recipe_and_its_static_forwarder_are_one_recipe(tmp_path: Path):
    """Measured on Dagger 2.57.2 + Kotlin 2.2.21: `@JvmStatic @Provides` in a companion
    object compiles to TWO methods carrying `@Provides` — the companion's instance method
    and a static forwarder of the same name and descriptor on the enclosing module — and
    the component calls the forwarder. One recipe, never `ambiguous`. A plain companion
    recipe (no forwarder) is found on the companion itself."""
    module = "com/acme/CompModule#"
    companion = "com/acme/CompModule$Companion#"
    stat = "statRetrofit(sig_e61c31ac)."
    comp = "compRetrofit(sig_e61c31ac)."
    facts = (
        [
            SymbolFact(document_id="doc_1", symbol=_MODULE + module, construct_kind="class"),
            SymbolFact(
                document_id="doc_1",
                symbol=_MODULE + companion,
                construct_kind="class",
                enclosing=_MODULE + module,
            ),
        ]
        + _recipe(module + stat, _type(_RETROFIT), _named("stat"), static=True)
        + _recipe(companion + stat, _type(_RETROFIT), _named("stat"))
        + _recipe(companion + comp, _type(_RETROFIT), _named("comp"))
    )

    stat_found = _injections(tmp_path / "stat", facts + _consumer(_named("stat")))
    comp_found = _injections(tmp_path / "comp", facts + _consumer(_named("comp")))

    assert stat_found[(_MODULE + _API, 0)] == ProvidedBy(_MODULE + module + stat)
    assert comp_found[(_MODULE + _API, 0)] == ProvidedBy(_MODULE + companion + comp)


def test_a_spring_bean_parameter_crosses_by_spring_s_own_ladder(tmp_path: Path):
    """Spec §2b: a `@Bean` method's parameter takes Spring's ladder unchanged — the answer
    is `bean_of`'s. Here the parameter is unqualified and two beans share its type: Spring
    picks the `@Primary` one, which Dagger's rules would call `ambiguous`."""
    container = _CONFIG + "container(sig_3c4d5e6f)."
    other = _CONFIG + "otherContainer(sig_4d5e6f70)."
    helper = _CONFIG + "helper(sig_6f708192)."
    facts = (
        _recipe(container, _type(_CONTAINER_TYPE), declaring=_BEAN)
        + _recipe(other, _type(_CONTAINER_TYPE), declaring=_BEAN)
        + [_primary(other)]
        + _recipe(
            helper,
            _type("com/acme/Helper#"),
            parameters=(_slot(_type(_CONTAINER_TYPE), name="c"),),
            declaring=_BEAN,
        )
    )
    workspace = _loaded(tmp_path, facts)
    try:
        found = injected_parameters(workspace, _MODELS, (_VALUE,))
        ladder = bean_table(workspace, _catalog(_SPRING), known_channels=frozenset()).bean_of(
            _parameter(_CONTAINER_TYPE, "c")
        )
    finally:
        workspace.close()

    assert isinstance(ladder, BeanRef)
    assert found[(_MODULE + helper, 0)] == ProvidedBy(_MODULE + other) == ProvidedBy(ladder.method)


def test_an_ambiguous_spring_slot_carries_the_beans_the_ladder_weighed(tmp_path: Path):
    """Whole-branch review m4: one encoding of the ladder. Two beans of the slot's type,
    neither primary, and a name that is neither's: the ladder weighed both, and the table's
    `Ambiguous` names exactly those, read off `bean_of`'s own answer."""
    container = _CONFIG + "container(sig_3c4d5e6f)."
    other = _CONFIG + "otherContainer(sig_4d5e6f70)."
    helper = _CONFIG + "helper(sig_6f708192)."
    facts = (
        _recipe(container, _type(_CONTAINER_TYPE), declaring=_BEAN)
        + _recipe(other, _type(_CONTAINER_TYPE), declaring=_BEAN)
        + _recipe(
            helper,
            _type("com/acme/Helper#"),
            parameters=(_slot(_type(_CONTAINER_TYPE), name="c"),),
            declaring=_BEAN,
        )
        + [
            SymbolFact(
                document_id="doc_1",
                symbol=_MODULE + "com/acme/Helper#",
                construct_kind=ConstructKind.CLASS,
            )
        ]
    )
    workspace = _loaded(tmp_path, facts)
    try:
        found = injected_parameters(workspace, _MODELS, (_VALUE,))
    finally:
        workspace.close()

    assert found[(_MODULE + helper, 0)] == Ambiguous((_MODULE + container, _MODULE + other))


@pytest.mark.pins("beans.a-GENERIC-Spring-slot-has-NO-entry")
def test_a_spring_slot_of_a_generic_type_is_not_the_ladder_s(tmp_path: Path):
    """Review I1. Spring fills `List<ClientHttpRequestInterceptor>` with EVERY interceptor
    bean; the ladder keys on the erasure and would pick the one `@Bean List<String>` by
    type. A generic slot under `candidates` gets no entry: missing, never false (the
    precedent of `annotation_driven.generic_parameter`)."""
    listed = _type("java/util/List#", _type("org/acme/Interceptor#"))
    template = _CONFIG + "template(sig_77)."
    found = _injections(
        tmp_path,
        _recipe(
            _CONFIG + "hosts(sig_78).",
            _type("java/util/List#", _type("java/lang/String#")),
            declaring=_BEAN,
        )
        + _recipe(
            template,
            _type("org/acme/Template#"),
            parameters=(_slot(listed, name="interceptors"),),
            declaring=_BEAN,
        ),
    )

    assert (_MODULE + template, 0) not in found


@pytest.mark.pins("beans.a-CONFIGURED-slot-has-NO-entry")
def test_a_slot_filled_from_configuration_is_not_a_recipe_s(tmp_path: Path):
    """Review m1. Spring fills a `@Value("${orders.url}")` parameter from configuration,
    not from a bean, even when one bean of its type exists. It gets no entry, so the walk
    keeps today's reading of it. The annotation is the one the catalogs already name as
    `field_sources.value_annotation`; no new word."""
    client = _CONFIG + "client(sig_79)."
    found = _injections(
        tmp_path,
        _recipe(_CONFIG + "name(sig_80).", _type("java/lang/String#"), declaring=_BEAN)
        + _recipe(
            client,
            _type("org/acme/Client#"),
            parameters=(
                _slot(
                    _type("java/lang/String#"),
                    AnnotationUse(
                        annotation="org/springframework/beans/factory/annotation/Value#",
                        args={"value": "${orders.url}"},
                    ),
                    name="url",
                ),
                _slot(_type("java/lang/String#"), name="name"),
            ),
            declaring=_BEAN,
        ),
    )

    assert (_MODULE + client, 0) not in found
    assert found[(_MODULE + client, 1)] == ProvidedBy(_MODULE + _CONFIG + "name(sig_80).")


def test_the_table_is_built_once_per_resolve(tmp_path: Path):
    """GUIDELINES §8.7: built once per load through `Workspace.once`, keyed on the models'
    contents, so every reader in one resolve shares it."""
    workspace = _loaded(tmp_path, _qualifier_types() + _consumer())
    try:
        first = injected_parameters(workspace, _MODELS, (_VALUE,))
        assert injected_parameters(workspace, dict(_MODELS), [_VALUE]) is first
    finally:
        workspace.close()
