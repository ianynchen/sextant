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
    BeanRef,
    Parameter,
    Unresolved,
    bean_table,
    declared_beans,
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
    TypeRef,
)
from sextant.domain.facts import Parameter as DeclaredParameter
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


def _loaded(tmp_path: Path, facts: list) -> DuckDbWorkspace:
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
    """The container's own order for a type no framework bean shares
    (`DefaultListableBeanFactory.determineAutowireCandidate`, CP-27): one bean of
    the type is it whatever the parameter is called; two are `ambiguous` — unless
    the parameter is named like one of them, which is the name rung."""
    one = _bean(_CONTAINER, _CONTAINER_TYPE) + [_method(_HELPER)]
    workspace = _loaded(tmp_path, one)
    table = bean_table(workspace, _catalog(_SPRING), known_channels=frozenset())
    workspace.close()

    assert table.kind_of(_CONTAINER_TYPE) == "other"
    assert table.bean_of(_parameter(_CONTAINER_TYPE, "anything")) == BeanRef(
        method=_MODULE + _CONTAINER, name="container", erased_return=_CONTAINER_TYPE
    )
    # A type nothing declares is `none`, not `ambiguous` — unless the parameter is
    # NAMED like a declared bean: the fold carries no type hierarchy, so a parameter
    # declared as the bean's supertype has no type candidate and its name is the one
    # rung left (the container would match the subtype; the fold matches the name).
    assert table.bean_of(_parameter("com/acme/Missing#", "nothing")) == Unresolved("none")
    assert table.bean_of(_parameter("com/acme/Supertype#", "container")) == BeanRef(
        method=_MODULE + _CONTAINER, name="container", erased_return=_CONTAINER_TYPE
    )

    two = one + _bean(_OTHER_CONTAINER, _CONTAINER_TYPE)
    workspace = _loaded(tmp_path / "two", two)
    table = bean_table(workspace, _catalog(_SPRING), known_channels=frozenset())
    workspace.close()

    assert table.bean_of(_parameter(_CONTAINER_TYPE, "anything")) == Unresolved("ambiguous")
    assert table.bean_of(_parameter(_CONTAINER_TYPE, "otherContainer")) == BeanRef(
        method=_MODULE + _OTHER_CONTAINER, name="otherContainer", erased_return=_CONTAINER_TYPE
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
