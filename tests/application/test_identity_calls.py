"""`delegated_outers`: the identity of a class that makes no marker call of
its own is the one marked class its nest's code calls into (Quarkus Mutiny
gRPC spec §3a).

Pure function over call-site rows and a nest-host map, so the rows here carry
only the three columns it reads (`caller`, `owner`, `name`). Every class name
is invented; the SHAPES (a wrapper's nested `ImplBase` calling the generated
class's accessor, a client calling the wrapper's stub) are the ones measured
in `quarkus-quickstarts`."""

import pytest

from sextant.application.resolve.shapes.identity_calls import delegated_outers

_MODULE = "sextant-jvm maven com.acme/billing 1.0.0 "
GRPC = "com/acme/proto/BillingGrpc#"
WRAPPER = "com/acme/proto/MutinyBillingGrpc#"
IMPL_BASE = "com/acme/proto/MutinyBillingGrpc$BillingImplBase#"
STUB = "com/acme/proto/MutinyBillingGrpc$MutinyBillingStub#"
CLIENT = "com/acme/BillingClient#"
HOSTS = {IMPL_BASE: WRAPPER, STUB: WRAPPER}


def _call(caller_type: str, caller_method: str, owner: str, name: str) -> dict[str, str]:
    return {"caller": f"{_MODULE}{caller_type}{caller_method}().", "owner": owner, "name": name}


def test_a_wrapper_calling_one_marked_class_takes_its_identity() -> None:
    sites = [_call(IMPL_BASE, "bindService", GRPC, "getServiceDescriptor")]

    assert delegated_outers(sites, {GRPC}, HOSTS) == {WRAPPER: GRPC}


def test_delegation_follows_an_unmarked_nest_to_a_marked_one() -> None:
    sites = [
        _call(CLIENT, "sayHello", STUB, "sayHello"),
        _call(STUB, "<init>", GRPC, "newStub"),
    ]

    assert delegated_outers(sites, {GRPC}, HOSTS) == {CLIENT: GRPC, WRAPPER: GRPC}


@pytest.mark.pins("grpc.a-WRAPPER-takes-the-one-identity-it-delegates-to")
def test_two_marked_classes_reached_is_no_identity() -> None:
    a, b, facade = "com/acme/AGrpc#", "com/acme/BGrpc#", "com/acme/Facade#"
    sites = [
        _call(facade, "first", a, "newBlockingStub"),
        _call(facade, "second", b, "newBlockingStub"),
    ]

    assert delegated_outers(sites, {a, b}, {}) == {}


def test_a_cycle_among_unmarked_nests_terminates() -> None:
    a, b = "com/acme/A#", "com/acme/B#"
    sites = [_call(a, "go", b, "go"), _call(b, "go", a, "go")]

    assert delegated_outers(sites, set(), {}) == {}


def test_a_marked_class_is_never_remapped() -> None:
    a, b = "com/acme/AGrpc#", "com/acme/BGrpc#"
    sites = [_call(a, "other", b, "newStub")]

    assert delegated_outers(sites, {a, b}, {}) == {}


def test_a_call_into_a_library_class_is_not_an_identity() -> None:
    sites = [_call(CLIENT, "log", "java/util/logging/Logger#", "info")]

    assert delegated_outers(sites, {GRPC}, HOSTS) == {}


def test_a_marked_class_named_by_its_nested_type_is_read_as_its_outer() -> None:
    """`calling_classes` gives the type that DECLARES the marker call, which
    can be a nested one; a call is read against outer classes, so the marked
    set is read the same way."""
    nested = "com/acme/proto/BillingGrpc$Descriptors#"
    sites = [_call(IMPL_BASE, "bindService", GRPC, "getServiceDescriptor")]

    assert delegated_outers(sites, {nested}, {**HOSTS, nested: GRPC}) == {WRAPPER: GRPC}
