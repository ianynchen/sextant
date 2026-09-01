"""The JVM half of declared-shape naming (2G design §3).

`test_descriptors.py` exercises these rules through real descriptors, but only
for the one shape the fixture schemas take: options present, one file per
package, nesting one deep. The rules a real repository hits — an omitted
`java_outer_classname`, `java_multiple_files`, a schema whose target package is
its own — have no descriptor in that test, and a symbol derived by a rule
nobody exercises joins nothing at all.
"""

from sextant.ingress.extract.jvm.generated_naming import JvmGeneratedNaming
from sextant.ingress.interpret.descriptors import SchemaLocation


def _location(**overrides):
    fields = {
        "schema_format": "protobuf",
        "file_name": "order.proto",
        "package": "sextant.orders",
        "path": ("OrderRequest",),
        "options": {},
        "declared_names": frozenset(),
    }
    return SchemaLocation(**{**fields, **overrides})


def test_a_message_is_named_inside_the_files_holder_class():
    naming = JvmGeneratedNaming()

    symbol = naming.class_symbol(
        _location(
            options={
                "java_package": "com.example.orders.proto",
                "java_outer_classname": "OrderProtos",
            }
        )
    )

    assert symbol == "com/example/orders/proto/OrderProtos$OrderRequest#"


def test_nesting_follows_the_schemas_own_nesting():
    naming = JvmGeneratedNaming()

    symbol = naming.class_symbol(
        _location(
            path=("OrderRequest", "Line"),
            options={
                "java_package": "com.example.orders.proto",
                "java_outer_classname": "OrderProtos",
            },
        )
    )

    assert symbol == "com/example/orders/proto/OrderProtos$OrderRequest$Line#"


def test_one_file_per_message_lifts_the_message_out_of_the_holder():
    """`java_multiple_files` is not decoration: with it, the holder class
    holds no messages, and a symbol that still nests them names a class the
    artifact does not contain."""
    naming = JvmGeneratedNaming()

    symbol = naming.class_symbol(
        _location(
            options={
                "java_package": "com.example.orders.proto",
                "java_outer_classname": "OrderProtos",
                "java_multiple_files": True,
            }
        )
    )

    assert symbol == "com/example/orders/proto/OrderRequest#"


def test_an_absent_holder_name_falls_back_to_the_generators_own_default():
    """A schema that names no holder class still compiles to one, named after
    the file."""
    naming = JvmGeneratedNaming()

    symbol = naming.class_symbol(_location(file_name="order_events.proto"))

    assert symbol == "sextant/orders/OrderEvents$OrderRequest#"


def test_the_default_holder_name_yields_when_a_type_already_claims_it():
    """protoc's collision rule: a file whose own type is called `Order`
    cannot also generate a holder called `Order`."""
    naming = JvmGeneratedNaming()

    symbol = naming.class_symbol(
        _location(file_name="order.proto", path=("Order",), declared_names=frozenset({"Order"}))
    )

    assert symbol == "sextant/orders/OrderOuterClass$Order#"


def test_an_absent_target_package_falls_back_to_the_schemas_own():
    naming = JvmGeneratedNaming()

    symbol = naming.class_symbol(_location(options={"java_outer_classname": "OrderProtos"}))

    assert symbol == "sextant/orders/OrderProtos$OrderRequest#"


def test_an_avro_record_is_one_top_level_class_named_by_its_namespace():
    """Avro generates a class per record, never a nested one, so a namespace
    is a package and nothing wraps it."""
    naming = JvmGeneratedNaming()

    symbol = naming.class_symbol(
        _location(
            schema_format="avro",
            file_name="",
            package="com.example.orders.avro",
            path=("AuditEvent",),
        )
    )

    assert symbol == "com/example/orders/avro/AuditEvent#"
