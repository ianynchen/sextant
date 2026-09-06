"""Every shipped catalog has a test proving it DECLINES (GUIDELINES §10, §8).

§10 requires that anything which detects, matches or classifies is tested on
near-miss input that must NOT match, asserting *nothing* was produced. The
suite honours that for the rules written since Task 5; it does not honour it
for most of the catalogs shipped before, and that gap is not theoretical:

- a gRPC endpoint was minted from an ordinary `extends` pair, and the golden
  fixture missed it — the reviewer's own word — "by luck", because its one
  subclass happens to override nothing;
- `@KafkaHandler` outside a class-level `@KafkaListener` derived an endpoint
  with an EMPTY name, live since phase 2D, because no test ever asked
  `spring-kafka.yml` to decline.

Both are the RUNBOOK's "generic match, specific label" shape, and in both the
suite was full of fixtures demonstrating the rule FIRING. A suite that only
proves a rule can fire cannot tell you it declines correctly.

**This test does not write the near-misses. It makes their absence visible per
catalog**, so the backlog is a list of names that only ever gets shorter rather
than an intention nobody can audit.

## How a test declares what it covers

A test states its catalog with the `declines` marker, and nothing else counts:

    @pytest.mark.declines("spring-rabbit")
    def test_a_rabbit_handler_on_a_class_carrying_no_listener_derives_nothing(...):
        ...
        assert rows == []

A naming convention would have been cheaper and is exactly the mechanism this
project keeps being bitten by — `detect.coordinates` was declared by all 41
catalogs of its day and read by nothing (§5.3), and a rule satisfied by a
substring of a function name is satisfied by accident the first time somebody
writes a test about `spring-web` that has nothing to do with declining. The
marker has to be typed deliberately, names the catalog explicitly, and is
runnable in its own right (`pytest -m declines`).

The marker is a DECLARATION by the test's author, not a proof: this file reads
it statically and does not re-verify that the marked body asserts emptiness.
What it does verify is that the id names a catalog that actually ships, so a
typo or a retired catalog fails here rather than quietly covering nothing.

`test_a_web_filter_derives_nothing_from_any_shipped_catalog`
(`tests/application/test_endpoints.py`) is deliberately NOT marked, although it
runs every shipped catalog at once. It negates a boundary, not a catalog's own
conjuncts, and counting it would mark all fifty covered on the strength of one
input — which is the vacuous pass this whole file exists to prevent.
"""

import ast
from pathlib import Path

REPO = Path(__file__).parents[2]
CATALOGS = REPO / "src" / "sextant" / "catalogs"
TESTS = REPO / "tests"

# Catalogs with no declining test yet, and the direction this list travels.
#
# This is a BACKLOG, not an exemption. Every entry is a rule that matches on a
# shape and publishes a specific meaning, with nothing in the suite proving it
# stays silent on a shape it does not own. They are listed rather than counted
# so that removing one is a deliberate edit visible in a diff, and so that a
# NEW catalog cannot join them: adding a `.yml` without a declining test fails
# `test_every_shipped_catalog_has_a_declining_test` immediately.
#
# `spring-kafka` is first on the list on purpose — the empty-name
# `@KafkaHandler` row is the defect this file's docstring opens with, and it is
# still live.
_NO_DECLINING_TEST_YET = frozenset(
    {
        "spring-kafka",
        "spring-kafka-media",
        "spring-kafka-message",
        "spring-jms",
        "aws-sqs-sdk",
        "google-pubsub-publisher",
        "google-pubsub-subscriber",
        "spring-cloud-stream",
        "spring-stomp",
        "jakarta-websocket",
        "spring-web",
        "spring-mvc",
        "spring-restclient",
        "spring-cloud-openfeign",
        "okhttp",
        "spring-data-rest",
        "spring-graphql",
        "graphql-schema",
        "microprofile-graphql",
        "netflix-dgs",
        "grpc-java",
        "grpc-spring",
        "grpc-schema",
        "grpc-net-devh",
        "spring-ws",
        "jakarta-jws",
        "jakarta-jws-client",
        "wsdl-schema",
    }
)


def shipped_catalogs() -> set[str]:
    """Every catalog the package actually ships, read off the directory.

    Enumerated, never listed: a hand-maintained roster drifts, and the one
    thing this rule must not do is stop seeing a catalog.
    """
    return {path.stem for path in CATALOGS.glob("*.yml")}


def declining_tests() -> dict[str, list[str]]:
    """Catalog id -> the `declines`-marked tests that cover it, `file:line:name`.

    Read statically rather than through pytest's own collection: the marker is
    a decorator on a function, which the AST answers for without importing a
    thousand fixtures, and this file is an architecture rule, not a run of the
    suite it inspects.
    """
    found: dict[str, list[str]] = {}
    for path in sorted(TESTS.rglob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            for catalog_id in _declared_ids(node):
                where = f"{path.relative_to(REPO)}:{node.lineno}:{node.name}"
                found.setdefault(catalog_id, []).append(where)
    return found


def _declared_ids(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    """The catalog ids a `@pytest.mark.declines("...")` decorator names."""
    ids = []
    for decorator in node.decorator_list:
        if not isinstance(decorator, ast.Call):
            continue
        target = decorator.func
        if not (isinstance(target, ast.Attribute) and target.attr == "declines"):
            continue
        for argument in decorator.args:
            if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                ids.append(argument.value)
    return ids


def test_every_shipped_catalog_has_a_declining_test():
    """The rule itself. A catalog is covered when some test declares it with
    the `declines` marker; anything else is on the backlog above, by name."""
    uncovered = shipped_catalogs() - set(declining_tests()) - _NO_DECLINING_TEST_YET
    assert uncovered == set(), (
        "these shipped catalogs have no test proving they DECLINE on near-miss "
        "input (GUIDELINES §10) and are not on this file's backlog:\n"
        + "\n".join(f"  - {catalog_id}" for catalog_id in sorted(uncovered))
        + "\n\nWrite the near-miss — an input satisfying every conjunct of the "
        "rule but one, asserting NOTHING is derived — and mark it "
        '`@pytest.mark.declines("<catalog id>")`. Adding the id to '
        "_NO_DECLINING_TEST_YET is the other option, and it makes the backlog "
        "longer, which is the direction that list does not travel."
    )


def test_the_backlog_only_ever_shrinks():
    """A catalog that has GAINED a declining test must leave the backlog in the
    same commit, and an entry naming nothing at all must go too.

    Without this the list is write-only: an id could sit there forever after
    the gap it records was closed, and the count would look like a backlog
    while measuring nothing. Both halves make retiring an entry a deliberate
    edit rather than a thing that quietly stops being true.
    """
    covered = set(declining_tests())
    stale = sorted(_NO_DECLINING_TEST_YET & covered)
    unknown = sorted(_NO_DECLINING_TEST_YET - shipped_catalogs())
    assert (stale, unknown) == ([], []), (
        "_NO_DECLINING_TEST_YET is out of date — "
        f"now covered, so remove them: {stale or 'none'}; "
        f"not a shipped catalog at all: {unknown or 'none'}"
    )


def test_every_declines_marker_names_a_catalog_that_ships():
    """A marker is only as good as its argument. A typo, or an id left behind
    by a retired catalog, would declare coverage of nothing at all — the
    §5.3 failure in miniature, a name existing where a mechanism does not."""
    shipped = shipped_catalogs()
    phantom = {
        catalog_id: where
        for catalog_id, where in declining_tests().items()
        if catalog_id not in shipped
    }
    assert phantom == {}, "`declines` markers naming catalogs that do not ship:\n" + "\n".join(
        f"  - {catalog_id}: {', '.join(where)}" for catalog_id, where in phantom.items()
    )


def test_the_marker_scan_finds_the_declining_tests_that_exist():
    """A coverage check that discovers nothing passes for the wrong reason —
    every catalog would be uncovered, the backlog would swallow all of them,
    and the file would assert only that the allowlist is complete. Task 7's
    `spring-rabbit` near-miss is the pin: if the scan cannot see that one, it
    can see none of them."""
    covered = declining_tests()
    assert covered, "the `declines` marker scan found no marked test anywhere"
    assert "spring-rabbit" in covered, (
        "the scan no longer sees the `spring-rabbit` declining test "
        "(`@RabbitHandler` on a class carrying no `@RabbitListener`) — the "
        "marker mechanism is broken, not the coverage"
    )
