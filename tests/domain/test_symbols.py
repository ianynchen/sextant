from sextant.domain.symbols import (
    Symbol,
    bare_descriptor,
    member_name,
    owner_of,
    simple_name,
    type_descriptor,
)

ORDER_SERVICE = Symbol(
    scheme="sextant-jvm",
    package_manager="maven",
    package="com.acme/orders",
    version="2.1.0",
    descriptor="com/acme/OrderService#save().",
)


def test_symbol_renders_the_scip_grammar_when_converted_to_string():
    assert str(ORDER_SERVICE) == (
        "sextant-jvm maven com.acme/orders 2.1.0 com/acme/OrderService#save()."
    )


def test_short_id_is_prefixed_and_stable_when_the_same_symbol_is_built_twice():
    twin = Symbol(**vars(ORDER_SERVICE))
    assert ORDER_SERVICE.short_id == twin.short_id
    assert ORDER_SERVICE.short_id.startswith("sym_")


def test_short_id_differs_when_the_descriptor_differs():
    other = Symbol(**{**vars(ORDER_SERVICE), "descriptor": "com/acme/OrderService#load()."})
    assert other.short_id != ORDER_SERVICE.short_id


def test_owner_of_returns_the_owning_type_descriptor_with_its_trailing_hash():
    assert owner_of("com/acme/OrderService#save().") == "com/acme/OrderService#"


def test_owner_of_is_none_for_a_free_function_symbol_scip_spells_with_no_hash():
    assert owner_of("pkg/handleOrders().") is None


def test_member_name_on_an_enum_constant():
    assert member_name("org/springframework/http/HttpMethod#POST.") == "POST"


def test_member_name_on_a_method():
    assert member_name("com/acme/OrderService#save().") == "save()"


def test_member_name_on_a_hashless_descriptor():
    assert member_name("pkg/handleOrders().") == "pkg/handleOrders()"


def test_bare_descriptor_strips_the_space_separated_module_coordinates():
    assert bare_descriptor(str(ORDER_SERVICE)) == "com/acme/OrderService#save()."


def test_bare_descriptor_is_the_whole_string_when_no_coordinates_are_present():
    assert bare_descriptor("com/acme/OrderService#save().") == "com/acme/OrderService#save()."


def test_type_descriptor_round_trips_the_docstring_example():
    assert type_descriptor("reactor.core.publisher.Mono") == "reactor/core/publisher/Mono#"


def test_simple_name_unchanged_behavior():
    assert simple_name("com/acme/OrderService#") == "OrderService"
