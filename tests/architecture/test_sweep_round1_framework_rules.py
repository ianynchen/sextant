"""Every rule the round-1 sweep fix pass mirrors is pinned to CP-11's bytecode.

`scripts/probes/cp11_sweep_round1.md` carries the table its committed harness
generates — one row per framework question, with the artifact the run resolved,
the version that JAR reported about itself, and what `javap` said. This file is
the offline half: it asserts the shipped catalogs and engines still say what the
measurement says.

## Why a pin and not a comment

Each of CP-11's four findings is a rule that was *plausible and wrong*, encoded
from documentation or memory and left to rot for a month. A comment recording
the measurement rots the same way. A test fails.

The direction matters: this pins the CATALOG against the MEASUREMENT, so
re-running the harness after a framework bump and pasting a changed table makes
the catalog fail until it is brought back into line — which is the moment a
version-scoped rule is supposed to be re-decided (§5.4).

It is OFFLINE and deterministic (NFR-1): it reads two committed files and runs
nothing. What makes the table trustworthy is the harness's own abort on a
mislabelled identity, not this test.
"""

import re
from pathlib import Path

import yaml

REPO = Path(__file__).parents[2]
CATALOGS = REPO / "src" / "sextant" / "catalogs"
PROBE = REPO / "scripts" / "probes" / "cp11_sweep_round1.md"

# The generated table's own header, matched in full: a header that has drifted
# means the columns below are being read positionally against something else.
_HEADER = "| # | question | artifact | version | observed |"
_BACKTICKED = re.compile(r"^`(.*)`$")
# `name(Ldescriptor;...)` as `probe.py` prints one verb setter.
_SETTER = re.compile(r"^([\w$]+)\(")


def _cell(text: str) -> str:
    stripped = text.strip()
    match = _BACKTICKED.match(stripped)
    return match.group(1) if match else stripped


def probe_rows() -> dict[str, dict[str, str]]:
    """The committed measurement, keyed by the question number the harness
    printed (`1`, `2a`, `2b`, …)."""
    lines = PROBE.read_text(encoding="utf-8").splitlines()
    start = next((i for i, line in enumerate(lines) if line.strip() == _HEADER), None)
    assert start is not None, (
        f"{PROBE.relative_to(REPO)} carries no observation table with the header the harness "
        f"generates:\n  {_HEADER}\nRe-run scripts/probes/cp11_sweep_round1/run.sh and paste its "
        "second table in verbatim."
    )
    rows = {}
    for line in lines[start + 2 :]:
        if not line.startswith("|"):
            break
        cells = [_cell(cell) for cell in line.strip().strip("|").split("|")]
        rows[cells[0]] = {
            "question": cells[1],
            "artifact": cells[2],
            "version": cells[3],
            "observed": cells[4],
        }
    return rows


def catalog(name: str) -> dict:
    return yaml.safe_load((CATALOGS / f"{name}.yml").read_text(encoding="utf-8")) or {}


def test_the_probe_table_is_readable_at_all():
    """A pin that parses nothing passes for the wrong reason: an empty table has
    no disagreements either. Asserts the four questions are all present before
    any of them is compared against a catalog."""
    numbers = {number.rstrip("abcdefgh") for number in probe_rows()}
    assert numbers == {"1", "2", "3", "4"}, (
        f"CP-11's observation table is missing questions — found {sorted(numbers)}"
    )


def test_okhttp_declares_a_step_for_every_verb_setter_the_builder_has():
    """`A-C2`. The catalog's root seeds `http_method: GET`, which is OkHttp's
    real default for a bare `Request.Builder` — and is honest ONLY while every
    method that sets the verb is a declared step. An uncovered one falls through
    as an unmatched step (D02 §4) and leaves the seeded GET standing at
    `resolved`/`compiler`, which is exactly how `.method("DELETE", body)`
    published GET.

    This is the completeness half `test_defaulted_identity_values.py` says it
    cannot check: that file refuses an unexplained seeded literal, this one
    refuses the seed's stated CONDITION going false."""
    measured = probe_rows()["1"]["observed"]
    setters = {match.group(1) for part in measured.split(", ") if (match := _SETTER.match(part))}
    declared = {str(step["method"]) for step in catalog("okhttp")["matches"]["steps"]}

    missing = sorted(setters - declared)
    assert missing == [], (
        f"`okhttp3.Request$Builder` {probe_rows()['1']['version']} declares verb-setting methods "
        f"`okhttp.yml` has no step for: {missing}. Each one falls through as an unmatched step "
        "and publishes the root's `http_method: GET` default for a request that is not a GET."
    )


def test_the_spring_handler_gate_names_the_annotation_the_framework_tests_for():
    """`A-C7`. Two claims, and the second is the one that rots: the handler
    test is a PREDICATE call rather than a literal compare, and it names
    `org.springframework.stereotype.Controller`.

    Pinned per Spring minor, which is the point of measuring four of them: the
    sentence GUIDELINES §8.1 used to teach this rule with ("accepts
    `@Controller` **or** a type-level `@RequestMapping`") was an older Spring's
    behaviour asserted from memory, and it shipped wrong for a month. A single
    minor could not have caught that; four identical bodies can say the rule is
    stable, and a fifth that differs will fail here."""
    bodies = {row["observed"] for number, row in probe_rows().items() if number.startswith("2")}
    assert len(bodies) == 1, f"`isHandler` is not identical across the measured minors: {bodies}"
    [body] = bodies
    assert "AnnotatedElementUtils.hasAnnotation" in body, (
        "`isHandler` is no longer a predicate call — if it became a literal annotation compare, "
        "the composition widening `A-C7` added is over-reporting and must be re-decided"
    )
    tested = "org/springframework/stereotype/Controller"
    assert f"class {tested}" in body
    assert catalog("spring-mvc")["matches"]["type_annotation"] == tested.replace("/", ".")
