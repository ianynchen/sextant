"""Shared helpers for the shape-rooting and shape-expansion tests (Tasks 9-12).

Written once here because every later task references these names, and each
would otherwise define them slightly differently."""


def type_ref(symbol: str, *arguments: dict) -> dict:
    """A D00 §5a type reference: a symbol plus recursive type arguments."""
    return {"symbol": symbol, "arguments": list(arguments)}


ORDER_VIEW = type_ref("com/acme/orders/contracts/OrderView#")

# A shape's id **is** its descriptor symbol (pre-flight ruling F1), so there is
# no `shape_id_of`: the constant below is both the type reference's symbol and
# the row key every shape query uses.
ORDER_REQUEST = "com/acme/orders/contracts/OrderRequest#"

# The enumeration `OrderRequest.status` points at: mapped to the `enum` wire
# type and never expanded, so no shape is ever written for it (D00 §5b).
ORDER_STATUS = "com/acme/orders/contracts/OrderStatus#"

# A type whose fields already arrive with a settled type-system answer
# (Task 11): the derivation must pass that answer through, never re-derive or
# downgrade it.
KOTLIN_ORDER = "com/acme/orders/contracts/KotlinOrder#"

# Declared under a package-level scope annotation (Task 11, D02 §2e), in its
# own package so the scope claims only this type.
SCOPED_REQUEST = "com/acme/orders/scoped/ScopedRequest#"


def mono_of(inner: dict) -> dict:
    return type_ref("reactor/core/publisher/Mono#", inner)


def response_entity_of(inner: dict) -> dict:
    return type_ref("org/springframework/http/ResponseEntity#", inner)


def unknown_box_of(inner: dict) -> dict:
    return type_ref("com/acme/UnknownBox#", inner)


SPRING_WRAPPERS = [
    {"type": "reactor.core.publisher.Mono", "payload_arg": 0, "semantics": "async"},
    {
        "type": "org.springframework.http.ResponseEntity",
        "payload_arg": 0,
        "semantics": "http_envelope",
    },
    {"type": "java.util.Optional", "payload_arg": 0, "semantics": "optional"},
]


def shape_of(workspace, shape_id: str) -> dict:
    """The one `shapes` row for a shape id."""
    return next(s for s in workspace.query("shapes") if s["shape_id"] == shape_id)


def shape_fields_of(workspace, shape_id: str) -> list[dict]:
    """Every field of one shape, in ordinal order."""
    return [f for f in workspace.query("shape_fields") if f["shape_id"] == shape_id]


def field_of(workspace, shape_id: str, wire_name: str) -> dict:
    """One field, **keyed by its wire name — never the source field name.**

    D01 §5 makes `wire_name` the identity, so `customerId` is looked up as
    `customer_id`. Keying on the source name here would quietly reintroduce
    the thing that section exists to forbid.
    """
    return next(f for f in shape_fields_of(workspace, shape_id) if f["wire_name"] == wire_name)
