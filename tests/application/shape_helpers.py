"""Shared helpers for the shape-rooting and shape-expansion tests (Tasks 9-12).

Written once here because every later task references these names, and each
would otherwise define them slightly differently."""


def type_ref(symbol: str, *arguments: dict) -> dict:
    """A D00 §5a type reference: a symbol plus recursive type arguments."""
    return {"symbol": symbol, "arguments": list(arguments)}


ORDER_VIEW = type_ref("com/acme/orders/contracts/OrderView#")


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
