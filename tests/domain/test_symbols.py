from sextant.domain.symbols import Symbol

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
