"""Dropping the return type from a catalog's descriptor must not make two rows
ambiguous (F2 §4.1, JLS 8.4.2).

`single_call._matching_method` compares PARAMETER TYPES, not the whole descriptor: a
method is identified by its name and parameter types, and comparing the return type as
well made every row version-dependent by accident — ten `spring-kafka-template` rows
declare `CompletableFuture`, the Spring Kafka 3.x return, and the identical call in a
2.x module returns `ListenableFuture` and matched nothing at all.

**That is only safe while no two rows collide once the return type is gone**, and the
decision was made on a measurement of the catalogs as they stood. This file is what
keeps the measurement true: a catalog added later that declares two rows with the same
owner, name and parameter list, differing only in what they return, would make
`_matching_method`'s first-match-wins arbitrary — and arbitrary in a way no test of
that catalog's own rows would reveal, because either row looks correct alone.

A covariant-return bridge genuinely does put two such methods in one class file. That
is not a collision here: call sites are disambiguated by OWNER, which is part of the
match, and both are semantically one method because the bridge delegates to the other.
The check is therefore scoped to one owner within one catalog.
"""

from collections import defaultdict
from pathlib import Path

from sextant.domain.symbols import parameter_types
from sextant.ingress.catalogs.yaml_source import YamlCatalogSource

REPO = Path(__file__).parents[2]
CATALOGS = REPO / "src" / "sextant" / "catalogs"


def _declared(node: object, owner: object = None) -> list[tuple[object, str, str]]:
    """Every `(owner, name, descriptor)` a catalog declares, wherever it declares one.

    Walks the whole `matches` tree rather than reading `matches.methods`, because
    `fluent`'s `steps`/`terminal` and `interface_implementation`'s `registration` name
    methods too, and a rule about method identity that only looked at one style would
    be a rule with a hole in it.

    **Those grammars spell it `method:`, not `name:`, and an earlier version of this
    walker matched only `name`.** It therefore found exactly the 96 rows a two-line read
    of `matches["methods"]` would have found, while its docstring claimed to have closed
    a hole that was still open — and open precisely when it will matter, the day those
    grammars gain descriptors (`A-Mi19`). Both spellings are read here, and the test
    below asserts the walker can see a collision in a `steps` entry, because a guard
    nobody can watch fail is a guard nobody should trust.
    """
    found: list[tuple[object, str, str]] = []
    if isinstance(node, dict):
        here = node.get("owner", owner)
        named = node.get("name") or node.get("method")
        if named is not None and "descriptor" in node:
            found.append((here, str(named), str(node["descriptor"])))
        for key, value in node.items():
            if key != "owner":
                found.extend(_declared(value, here))
    elif isinstance(node, list):
        for item in node:
            found.extend(_declared(item, owner))
    return found


def test_no_two_rows_become_ambiguous_once_the_return_type_is_dropped():
    """The rule. Two rows sharing a catalog, owner, name and parameter list may not
    differ only in their return type."""
    groups: dict[tuple[str, str, str, str], set[str]] = defaultdict(set)
    for catalog in YamlCatalogSource(CATALOGS).load():
        for owner, name, descriptor in _declared(catalog.matches):
            key = (catalog.id, str(owner), name, parameter_types(descriptor))
            groups[key].add(descriptor)

    collisions = sorted((key, sorted(values)) for key, values in groups.items() if len(values) > 1)

    assert collisions == [], (
        "these rows are identical once the return type is dropped, so which one a call "
        "site matches is decided by their order in the file:\n"
        + "\n".join(
            f"  - {catalog}: {owner}{name}{params} -> {', '.join(values)}"
            for (catalog, owner, name, params), values in collisions
        )
        + "\n\nSplit them by a parameter type, or by owner — the return type cannot "
        "tell them apart, because it is not part of method identity (JLS 8.4.2)."
    )


def test_the_walker_sees_a_collision_declared_in_a_fluent_step():
    """The walker's own reach, asserted rather than described.

    `steps` and `terminal` entries name their method with `method:`; `methods` rows use
    `name:`. A walker reading only one spelling passes this file's real check while
    seeing nothing outside `matches.methods` — which is what it did. This is the
    synthetic shape that tells the two apart.
    """
    matches = {
        "owner": "com/acme/Client#",
        "steps": [
            {"method": "uri", "descriptor": "(Ljava/lang/String;)Lcom/acme/Client;"},
            {"method": "uri", "descriptor": "(Ljava/lang/String;)Lcom/acme/Other;"},
        ],
    }

    declared = _declared(matches)

    assert len(declared) == 2, "a `steps` entry names its method `method:`, not `name:`"
    assert len({parameter_types(descriptor) for _, _, descriptor in declared}) == 1, (
        "both entries share a parameter list and differ only in what they return — the "
        "collision this file exists to refuse"
    )
