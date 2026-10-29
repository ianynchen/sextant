import pytest

from sextant.application.boundary.vocabulary import KINDS, kinds_fed_by
from sextant.domain.version import BOUNDARY_VOCABULARY_VERSION


def test_the_seven_kinds_in_their_order():
    """The set is closed (spec 2026-10-22 §2): these seven, in this order, because the
    diff and the observability map both walk the registry in registry order."""
    assert list(KINDS) == [
        "module",
        "endpoint",
        "dependency",
        "data-contract",
        "boundary-property",
        "schedule",
        "error-handler",
    ]


def test_the_vocabulary_version_is_three():
    """The stamp lives in `domain/version.py` with the other three; the registry does not
    keep a second copy of it (the Step 0 lesson: copies of one stamp drift). Version 2 is
    `dependency` gaining `conditions` (spec 2026-10-23-deployment-set-conditions, ruling 2);
    version 3 is `schedule`'s identity gaining `name` (spec 2026-10-28-quartz, ruling 5)."""
    assert BOUNDARY_VOCABULARY_VERSION == 3


@pytest.mark.pins("boundary.a-DEPENDENCY-carries-its-callers-conditions")
def test_a_dependency_carries_conditions_as_an_endpoint_does():
    """Ruling 2: conditions belong to beans, so a row of either direction carries them."""
    assert "conditions" in KINDS["dependency"].attributes
    assert KINDS["dependency"].attributes.index("conditions") == (
        KINDS["dependency"].attributes.index("resolution") - 1
    )


def test_every_kind_is_keyed_by_its_own_name():
    assert all(name == kind.name for name, kind in KINDS.items())


@pytest.mark.pins("boundary.the-HANDLER-is-evidence-never-identity")
def test_endpoint_identity_is_the_exposed_address_and_the_handler_is_evidence():
    """§2 "the wire is the identity; the symbol is evidence": an endpoint that moved
    controller is the same endpoint, so the handler is never an identity or attribute column."""
    assert KINDS["endpoint"].identity == ("protocol", "method", "path")
    assert "handler" in KINDS["endpoint"].evidence and "handler" not in KINDS["endpoint"].attributes
    assert KINDS["dependency"].identity == ("protocol", "method", "path", "peer")


def test_a_dependency_keeps_its_peer_and_the_caller_is_evidence():
    assert "peer" in KINDS["dependency"].identity
    assert "caller" in KINDS["dependency"].evidence


def test_data_contract_identity_is_the_shape_symbol_never_the_content_hash():
    """The hash is what CHANGES when a field is added, so it is an attribute — the
    `changed` entry the drift scenario exists for — and never what identifies the shape."""
    contract = KINDS["data-contract"]
    assert contract.identity == ("shape_id",)
    assert "content_hash" in contract.attributes and "content_hash" not in contract.identity


def test_a_kind_derived_from_a_table_names_it_and_a_module_does_not():
    assert KINDS["endpoint"].table == "endpoints"
    assert KINDS["dependency"].table == "endpoints"
    assert KINDS["data-contract"].table == "shapes"
    assert KINDS["module"].table is None


def test_only_the_kinds_catalogs_write_are_grounded_in_code():
    """`grounded_in_code` is what lets the observability map say `not-observable` for a
    kind whose catalogs were all skipped; a module's own metadata or a config value is read
    off a file, not derived by a catalog, so it can never be not-observable."""
    grounded = [name for name, kind in KINDS.items() if kind.grounded_in_code]
    assert grounded == ["endpoint", "dependency", "data-contract", "schedule", "error-handler"]


def test_no_column_is_both_an_identity_and_an_attribute_or_evidence():
    for kind in KINDS.values():
        assert not set(kind.identity) & set(kind.attributes), kind.name
        assert not set(kind.identity) & set(kind.evidence), kind.name
        assert not set(kind.attributes) & set(kind.evidence), kind.name


def test_which_kinds_a_catalog_feeds():
    assert kinds_fed_by("scheduled_work", None, False) == ("schedule",)
    assert kinds_fed_by("scheduled_chain", None, False) == ("schedule",)
    assert kinds_fed_by("error_advice", None, False) == ("error-handler",)
    assert kinds_fed_by("annotation_driven", "inbound", True) == ("endpoint", "data-contract")
    assert kinds_fed_by("single_call", "outbound", False) == ("dependency",)
    assert kinds_fed_by("fluent", "both", False) == ("endpoint", "dependency")


def test_a_shape_model_adds_data_contract_to_any_wire_style_and_only_there():
    assert kinds_fed_by("single_call", "outbound", True) == ("dependency", "data-contract")
    assert kinds_fed_by("schema_operations", "inbound", False) == ("endpoint",)
    # A style that writes a non-wire table feeds exactly its own kind (§4b).
    assert kinds_fed_by("scheduled_work", None, True) == ("schedule",)
    assert kinds_fed_by("error_advice", "inbound", True) == ("error-handler",)


def test_an_unknown_direction_feeds_both_endpoint_kinds():
    """A `config_join` catalog (`spring-integration`, `spring-kafka-media`) declares no
    direction because its rows are of either: the direction is known per row, not per
    catalog. Feeding nothing would let a skipped one read as "no kind could be affected"."""
    assert kinds_fed_by("config_join", None, False) == ("endpoint", "dependency")
    assert kinds_fed_by("config_join", "", False) == ("endpoint", "dependency")
    assert kinds_fed_by("annotation_driven", None, True) == (
        "endpoint",
        "dependency",
        "data-contract",
    )


def test_a_both_direction_row_belongs_to_both_endpoint_kinds():
    """No pass writes a `both` row today; the linking tier will, and a row that is both
    exposed and called is one wire identity on each side."""
    assert KINDS["endpoint"].where == "direction IN ('inbound', 'both')"
    assert KINDS["dependency"].where == "direction IN ('outbound', 'both')"
