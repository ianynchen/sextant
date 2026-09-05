"""Every probe records WHERE its evidence was measured (GUIDELINES §5.4).

CP-5 recorded eight observation cells for a Spring Boot version that never
ran. The harness passed `-Dboot.version=4.1.1`, rebuilt without `clean`, and
executed the previous version's fat jar twice while printing a `4.1.1` header.
Every claim in that table was independently true; none of it was measured where
it said it was, and the mislabelled column sat in plain sight for a full review
cycle because the document and the harness both restated the parameter rather
than the observation.

§5.4 now requires the identity to come from the run's OWN output, and the
evidence table to be generated rather than written. This test asserts the
document half of that: for every configuration a probe claims, the file says
where the identity came from and which committed harness produced it.

## What "a provenance record" means here

Read off `cp5_actuator_paths.md`, which was rebuilt to be self-evidencing and
is the model this rule generalises. That file, and no other probe yet, does
four things:

1. Its observation table's column headers ARE the configurations it claims —
   one column per identity (`3.5.10`, `4.1.1`).
2. Those identities also appear in its version-scope statement, so the scope
   the verdict is bounded to and the columns it was measured on cannot drift
   apart.
3. Its observation section names the committed harness the table came from
   ("Verbatim from `run.sh`'s generated table").
4. That section says the headers are what each running process REPORTED —
   "the version the JVM under test reported in its own Spring Boot banner, not
   the version the loop asked for" — which is the sentence a reader needs in
   order to know the column is an observation and not a parameter.

This checks the RECORD, not the measurement. What actually makes CP-5's
identities trustworthy is `cp5_actuator/run.sh` parsing each JVM's own banner
and aborting when it disagrees with the version requested; no test of a
Markdown file can verify that a process booted. What a test of the Markdown
file CAN do is refuse a probe that never says where its numbers came from —
which is the state every pre-§5.4 probe is in, and the state CP-5 was in when
it published a table for a run that did not happen.
"""

import re
from pathlib import Path

REPO = Path(__file__).parents[2]
PROBES = REPO / "scripts" / "probes"

# Probes written before §5.4, kept as a SHRINKING list rather than grandfathered
# in silently. Each still carries real evidence — CP-1's six path rows and
# CP-6's converter row were observed against a live app, and CP-3/CP-8 and the
# Spring Integration probe both ship committed fixtures — but none of them
# records its configuration the way §5.4 now requires:
#
#   cp1_spring_paths.md   "this run used Boot 4.0.1" is the parameter, and the
#   cp6_boot_converter.md  probe app was a scratch directory, not committed:
#                          nothing to re-run, nothing that reported a version.
#   cp2_data_rest.md      names observed component versions in prose, with no
#                         observation table keyed by them and no harness.
#   cp3_cp8_grpc_facts.md ships a committed fixture and exact coordinates, but
#                         its evidence is fact-stream shapes, not a table whose
#                         columns are configurations.
#   spring-integration-destinations.md  same shape: a committed fixture and a
#                         `mvn -o dependency:list` version block, no per-column
#                         identities.
#
# Retiring an entry means rebuilding that probe the way CP-5 was rebuilt, and
# is a deliberate edit visible in a diff. A NEW probe cannot join this list
# without one: `test_every_probe_records_where_its_evidence_came_from` fails on
# any `scripts/probes/*.md` that is neither compliant nor named below.
_PREDATES_THE_RULE = frozenset(
    {
        "cp1_spring_paths.md",
        "cp2_data_rest.md",
        "cp3_cp8_grpc_facts.md",
        "cp6_boot_converter.md",
        "spring-integration-destinations.md",
    }
)

# A configuration identity as a probe writes one in a column header: a version.
# Deliberately narrow — a header this does not match is not treated as a
# configuration at all, so a probe cannot claim coverage with a column named
# `probe` or `#`.
_IDENTITY = re.compile(r"^\d+(?:\.\d+)+[A-Za-z0-9.\-]*$")

# The observation section must attribute its identities to the run itself AND
# disclaim the parameter that was passed in. Both halves are required: "run
# against Boot 4.1.1" satisfies neither, and "the banner said 4.1.1" without
# the disclaimer is the sentence CP-5's first version could also have written
# while printing a version it had not run.
_REPORTED_BY_THE_RUN = re.compile(r"\b(report(s|ed)?|print(s|ed)?|emitted|banner)\b", re.IGNORECASE)
_NOT_THE_PARAMETER = re.compile(
    r"\bnot the (version|parameter|value|one)\b"
    r"|\brather than the (version|parameter|value)\b"
    r"|\bnever from the (loop|parameter|version)\b",
    re.IGNORECASE,
)


def probe_documents() -> list[Path]:
    """Every probe write-up, read off the directory rather than listed."""
    return sorted(PROBES.glob("*.md"))


def _section(text: str, heading: re.Pattern[str]) -> str:
    """The body of the first `##` section whose heading matches, or ``""``."""
    blocks = re.split(r"^## ", text, flags=re.MULTILINE)[1:]
    return next((block for block in blocks if heading.match(block)), "")


def _identities(section: str) -> set[str]:
    """The configuration identities a section's table columns claim."""
    header = next((line for line in section.splitlines() if line.startswith("|")), "")
    return {cell.strip() for cell in header.split("|") if _IDENTITY.match(cell.strip())}


def _version_scope(text: str) -> str:
    """The `**Version scope...**` paragraph, which §5.4 requires a probe to
    state and which bounds every verdict below it."""
    match = re.search(r"\*\*Version scope[^*]*\*\*(.*?)\n\n", text, flags=re.DOTALL)
    return match.group(1) if match else ""


def _named_repository_paths(text: str) -> set[str]:
    """Every in-repo path the document names, harness or fixture."""
    return set(re.findall(r"\b(?:scripts/probes|fixtures)/[\w./-]*[\w/]", text))


def _failures(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    observations = _section(text, re.compile(r"Observations?\b"))
    problems = []

    if not observations:
        problems.append("no `## Observations` section — nothing states what was measured")

    claimed = _identities(observations)
    if not claimed:
        problems.append(
            "the observation table declares no configuration identity in its column "
            "headers, so no cell can be attributed to a configuration"
        )

    unscoped = sorted(claimed - set(re.findall(r"\d+(?:\.\d+)+", _version_scope(text))))
    if unscoped:
        problems.append(
            f"measured on {unscoped} but the version-scope statement does not name them — "
            "§5.4 bounds a verdict by what it measured, and the two must agree"
        )

    harnesses = _named_repository_paths(text)
    missing = sorted(name for name in harnesses if not (REPO / name).exists())
    if not harnesses:
        problems.append(
            "names no committed harness under `scripts/probes/` or `fixtures/` — "
            "a table nobody can re-run cannot be re-checked"
        )
    if missing:
        problems.append(f"names harness paths that do not exist: {missing}")

    generated_by = {Path(name).name for name in harnesses}
    if not any(name in observations for name in generated_by):
        problems.append(
            "the observation section does not name the harness it came from — "
            "§5.4 requires the evidence table to be generated, not written"
        )

    if not (_REPORTED_BY_THE_RUN.search(observations) and _NOT_THE_PARAMETER.search(observations)):
        problems.append(
            "the observation section does not attribute its identities to the run's own "
            "output and disclaim the parameter passed in — the CP-5 failure exactly: "
            "eight cells labelled with a version the process never reported"
        )

    return problems


def test_every_probe_records_where_its_evidence_came_from():
    """The rule. A probe either carries a provenance record for the
    configurations it claims, or is named in `_PREDATES_THE_RULE`."""
    offences = {
        path.name: _failures(path)
        for path in probe_documents()
        if path.name not in _PREDATES_THE_RULE and _failures(path)
    }
    assert offences == {}, "probes with no §5.4 provenance record:\n" + "\n".join(
        f"  {name}:\n" + "\n".join(f"    - {problem}" for problem in problems)
        for name, problems in sorted(offences.items())
    )


def test_the_predates_the_rule_list_only_ever_shrinks():
    """An entry survives only while the probe it names still exists and still
    fails. A probe rebuilt the way CP-5 was leaves the list in the same commit;
    otherwise the list measures nothing and looks like a backlog."""
    present = {path.name for path in probe_documents()}
    gone = sorted(_PREDATES_THE_RULE - present)
    now_compliant = sorted(
        name for name in _PREDATES_THE_RULE & present if not _failures(PROBES / name)
    )
    assert (gone, now_compliant) == ([], []), (
        "_PREDATES_THE_RULE is out of date — "
        f"no such probe: {gone or 'none'}; "
        f"now carries a provenance record, so remove them: {now_compliant or 'none'}"
    )


def test_the_check_passes_on_the_probe_it_was_derived_from():
    """CP-5 is the model (`b023f61` rebuilt it to be self-evidencing), so a
    rule generalised from it that cannot see it pass is measuring something
    else. This is the pin that stops the requirements above from drifting into
    a shape no real probe satisfies — at which point every future probe would
    land on the backlog and the rule would enforce nothing."""
    assert _failures(PROBES / "cp5_actuator_paths.md") == []
