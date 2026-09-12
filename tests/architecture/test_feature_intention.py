"""Every feature has a test that fails when the feature does not work.

**The rule this enforces, and why it is a test rather than a guideline.** On 2026-09-11 the
user observed that five days of work had moved no feature to delivered, and that principles
written down and not enforced were broken one by one while every rule with a failing test
behind it held. So the rule about how features get built is itself a test.

**The rule.** A feature is built by writing a FIXTURE first — code a Spring Boot developer
would recognise as their own — plus an assertion on what Sextant derives from it, and
watching that assertion fail. Then the feature is built until it passes.

That single artefact answers both questions that were being got wrong:

* *Is this the right thing to build?* If no realistic fixture exhibits the symptom, no user
  is waiting on it. `G-36` needed `@PayloadRoot` twice on one handler, which any Spring-WS
  developer writes. `G-52` needed a class invented to contain a method that only throws —
  and consumed a day.
* *Is the test testing the intention?* An assertion on derived output from real bytecode
  cannot be satisfied by editing a document, which is exactly what the near-miss and guard
  tests could not tell you: hundreds were green while three features were undelivered,
  because they assert that a catalog RULE discriminates rather than that a user's SURFACE
  appears.

**What this file checks.** That every feature named in the delivery register has such a
test, and that the test is of the right kind — it runs the pipeline and asserts on derived
rows, rather than reading a document. It deliberately does NOT check that the test passes:
a red intention test is the correct state for an undelivered feature, and is how the work
is tracked.
"""

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
DELIVERY = REPO / "docs" / "java-kotlin-delivery-list.md"
E2E = REPO / "tests" / "e2e"

# What makes a test an INTENTION test rather than a document check: it drives the real
# pipeline over real bytecode and reads back what was derived. A file naming none of these
# is asserting something other than the feature.
_PIPELINE_MARKERS = ("module", "analyze")
# `open_questions` belongs here because a catalog may derive NOTHING ELSE and still be
# doing its job: `spring-integration.yml` files each channel as a `channel_destination`
# question, since an in-process pipe has no wire identity to publish. The first version of
# this list omitted it, and the Async intention test — correct, and asserting on exactly
# what a reader sees — was rejected as "asserting on nothing derived".
_DERIVED_MARKERS = (
    'workspace.query("endpoints")',
    'workspace.query("call_edges")',
    'workspace.query("open_questions")',
    "render",
)


def _fenced(language: str) -> list[str]:
    """The lines of the first ```<language> block in the delivery list."""
    match = re.search(rf"```{language}\n(.*?)```", DELIVERY.read_text(), re.DOTALL)
    assert match is not None, f"the delivery list has no ```{language} block"
    return [line for line in match.group(1).split("\n") if line.strip()]


def _features() -> dict[str, list[str]]:
    """`feature -> blockers`, from the delivery list's own register."""
    match = re.search(r"```delivery\n(.*?)```", DELIVERY.read_text(), re.DOTALL)
    assert match is not None, "the delivery list has no ```delivery block"
    features: dict[str, list[str]] = {}
    for line in match.group(1).split("\n"):
        if not line.strip():
            continue
        name, _, blockers = (cell.strip() for cell in line.split("|"))
        features[name] = blockers.split()
    return features


def _slug(feature: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", feature.lower()).strip("_")


def _intention_test(feature: str) -> Path | None:
    candidate = E2E / f"test_{_slug(feature)}_delivered.py"
    return candidate if candidate.exists() else None


def _not_yet_written() -> set[str]:
    """Features whose intention test is acknowledged missing.

    A green suite that hides missing work and a red suite nobody can read are both
    useless. This is the third option: the check EXPECTS these to fail and fails if one
    unexpectedly passes, so writing the test forces the name out of this block. A feature
    in neither this block nor `tests/e2e/` is a hard failure — the gap cannot be created
    silently, only acknowledged.
    """
    return {name.strip() for line in _fenced("intention-test-missing") for name in line.split("|")}


@pytest.mark.parametrize("feature", sorted(_features()))
def test_every_feature_has_an_intention_test(feature: str, request: pytest.FixtureRequest):
    """No feature is worked on without one, and none is called delivered without one.

    The file is named for the feature so that its absence is visible in a directory
    listing rather than discoverable only by reading this test.
    """
    path = _intention_test(feature)
    if feature in _not_yet_written():
        request.node.add_marker(
            pytest.mark.xfail(strict=True, reason=f"{feature}: intention test not written")
        )
    assert path is not None, (
        f"'{feature}' has no intention test. Expected "
        f"tests/e2e/test_{_slug(feature)}_delivered.py — a fixture a Spring Boot developer "
        f"would recognise as their own code, plus an assertion on what Sextant derives "
        f"from it. Write it and watch it FAIL before building anything: if no realistic "
        f"fixture exhibits the symptom, no user is waiting on this feature."
    )


@pytest.mark.parametrize("feature", sorted(_features()))
def test_an_intention_test_asserts_on_derived_output(feature: str):
    """A test that reads a document instead of the pipeline is the failure mode this whole
    file exists against: it goes green while the product is broken."""
    path = _intention_test(feature)
    if path is None:
        pytest.skip("covered by test_every_feature_has_an_intention_test")
    source = path.read_text()
    assert all(marker in source for marker in _PIPELINE_MARKERS), (
        f"{path.name} does not run the pipeline. An intention test compiles the fixture and "
        f"runs `module analyze`; anything else is asserting about our own documents."
    )
    assert any(marker in source for marker in _DERIVED_MARKERS), (
        f"{path.name} runs the pipeline but asserts on nothing it derived. The assertion "
        f"has to be on the rows or the document a user reads, or the test cannot tell a "
        f"working feature from a broken one."
    )
    # READS, not mentions. A docstring explaining that this test cannot be satisfied by
    # editing COVERAGE.md is exactly the right thing to say; opening the file is not.
    reads_a_document = [
        line
        for line in source.split("\n")
        if re.search(r"(COVERAGE|open-issues|delivery-list)\.md", line)
        and re.search(r"read_text|open\(|Path\(|/ \"docs\"", line)
    ]
    assert reads_a_document == [], (
        f"{path.name} reads a document: {reads_a_document}. A feature's test must be "
        f"satisfiable only by the feature working, never by editing a document that "
        f"describes it."
    )
