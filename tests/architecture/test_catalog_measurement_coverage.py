"""Every catalog says which framework VERSION its rule was measured against
(GUIDELINES §5.4, §8.1, §8.3; D02 §1a; principles sweep `A-Mi4`, `A-Mi8`).

## The defect this closes

There was no version field anywhere on a catalog. Thirty-two of the fifty-two
catalogs shipping when this was written stated no version at all, and the twenty
that did stated it in COMMENTS, which nothing reads and nothing checks. So a
catalog silently claimed its rule for every version of a framework on evidence
from one — and framework rules move, measurably:

- `RequestMappingHandlerMapping.isHandler` lost its `@RequestMapping` disjunct
  between Spring generations (CP-7, CP-11: one
  `hasAnnotation(beanType, Controller.class)` call and nothing else, on all four
  minors in scope);
- `WebClient$RequestHeadersSpec.exchange` exists at spring-webflux 6.1.6 and is
  **removed** at 7.0.2 (CP-12 row 2), while `spring-webclient.yml` declares it.

§5.4's rule is that a verdict is bounded by what it measured. A catalog is a
standing verdict about a framework, so it states its bound or it does not have
one.

## What a `measured:` row claims, and what it must not

    measured:
      - { artifact: org.springframework:spring-webmvc, versions: ["6.1.6"],
          identity: reported, by: scripts/probes/cp11_sweep_round1.md }

`artifact` is the artifact the rule was READ OUT OF, which is not always the one
`detect.coordinates` names: `spring-web.yml`'s handler gate is
`spring-webmvc`'s predicate, and recording the declared dependency instead would
file the evidence against a jar nobody opened.

`identity` is where the version STRING came from — `reported` when the artifact
or the running process stated it itself, `assumed` when nothing in the archive
does and the value is the coordinate that resolved it. Two shipped rows are
`assumed`, both Retrofit's, because the retrofit jar states a version nowhere at
all and both probes label their column so. The distinction exists because CP-5
published eight observation cells under a version header no process had reported,
and §5.4 was written in response.

**A version nobody measured is not written here.** `A-Mi8` is that defect in
miniature — a catalog naming a version because its sibling named two — and the
honest entry for an unmeasured catalog is a row in `_NOT_MEASURED_YET` below,
never a plausible-looking number. This file's whole value is that a `measured:`
row is evidence rather than an intention.

## Why an allowlist rather than a count

§8.3 requires a new enforceable rule to ship with the audit list of the sites it
governs, and `_NOT_MEASURED_YET` IS that audit: the catalogs whose rule no
committed probe has measured, listed by name with what each is waiting on —
twenty-six when F5 counted them, and shorter by every Stage 4 pass since. Listed
rather than counted so retiring one is a deliberate edit visible in a diff, and
so a NEW catalog cannot join them silently — adding a `.yml` without a
`measured:` block fails `test_every_shipped_catalog_declares_what_it_measured`
immediately. This list does not travel in the direction of getting longer.

## What this cannot do

It checks the RECORD, not the measurement. It asserts that every version a
catalog cites appears in the version-scope paragraph of the probe it cites, so a
number typed into a catalog that its own probe never ran cannot survive — but it
cannot check the ARTIFACT half of the pairing, because a probe's version-scope
paragraph spells frameworks the way a person writes them ("Apache Tomcat
10.1.50", "Spring Boot 3.5.10") rather than as coordinates. Which artifact a
version belongs to is the probe harness's own answer, and
`test_probe_provenance.py` is what refuses a probe that does not say where its
numbers came from.

It is also silent about whether a MODULE under analysis runs the version a
catalog measured. That comparison needs `module.dependencies` — resolved
versions, which F1 landed — and it is deliberately not wired here: this is the
catalog's side of the question only.

It is OFFLINE and deterministic (NFR-1): it reads committed files and runs
nothing.
"""

import re
from pathlib import Path

import yaml

REPO = Path(__file__).parents[2]
CATALOGS = REPO / "src" / "sextant" / "catalogs"

# Catalogs no committed probe has measured, and what each is waiting on. A
# BACKLOG, not an exemption: every entry is a rule shipping today whose version
# scope is unknown, which is exactly the state §5.4 refuses to leave implicit.
#
# Retiring an entry means running a probe against a named artifact at a named
# version and citing it — the Stage 4 per-catalog pass, where these are the
# reading list.
_NOT_MEASURED_YET: dict[str, str] = {
    "aws-sqs-sdk": "no probe opens the AWS SDK v2 `SqsClient` jar",
    "google-pubsub-publisher": "CP-10 measured `google-pubsub-client`'s descriptor only",
    "graphql-schema": "a schema-file rule; no framework jar has been read for it",
    "grpc-java": "CP-3/CP-8 ship a fixture and coordinates but measure fact shapes, not a jar",
    "grpc-net-devh": "no probe opens `net.devh:grpc-server-spring-boot-starter`",
    "grpc-schema": "a schema-file rule; no framework jar has been read for it",
    "grpc-spring": "no probe opens `org.springframework.grpc:spring-grpc-core`",
    "jakarta-jws-client": "CP-13 measured the SERVER side (`RuntimeModeler`) only",
    "netflix-dgs": "no probe opens `com.netflix.graphql.dgs:graphql-dgs`",
    "spring-advice": "no probe opens `ExceptionHandlerExceptionResolver`",
    "spring-cloud-openfeign": "no probe opens `spring-cloud-openfeign-core`",
    "spring-cloud-stream": "`A-C5`; no probe opens `spring-cloud-stream`'s binding rule",
    "spring-graphql": "no probe opens `org.springframework.graphql:spring-graphql`",
    "spring-integration": "its probe predates §5.4 — a `dependency:list` block, no identities",
    "spring-kafka-media": "no probe opens the serializer table this file encodes",
    "spring-kafka-message": "CP-10/CP-12 measured the TEMPLATE side only",
    "spring-ws": "CP-10 measured `WebServiceTemplate`, not `@Endpoint`/`@PayloadRoot`",
    "wsdl-schema": "a schema-file rule; no framework jar has been read for it",
}

# `identity` is closed on purpose (NFR-5's discipline for every other closed
# vocabulary in this project): a third value would be a new claim about
# provenance, and adding one is a schema change rather than a catalog author's
# choice.
_IDENTITIES = frozenset({"reported", "assumed"})

_COORDINATE = re.compile(r"^[A-Za-z0-9_.\-]+:[A-Za-z0-9_.\-]+$")


def declared_measurements() -> dict[str, list[dict[str, object]]]:
    """`catalog id -> its `measured:` rows`, read off the directory.

    Enumerated, never listed: a hand-maintained roster drifts, and the one thing
    this rule must not do is stop seeing a catalog.
    """
    found: dict[str, list[dict[str, object]]] = {}
    for path in sorted(CATALOGS.glob("*.yml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        rows = document.get("measured")
        if rows is not None:
            found[path.stem] = rows
    return found


def shipped_catalogs() -> set[str]:
    return {path.stem for path in CATALOGS.glob("*.yml")}


def _version_scope(document: Path) -> str:
    """The `**Version scope…**` paragraph §5.4 requires a probe to state, which
    is the sentence every verdict in that file is bounded by."""
    text = document.read_text(encoding="utf-8")
    match = re.search(r"\*\*Version scope[^*]*\*\*(.*?)(?=\n\n)", text, re.DOTALL)
    return match.group(0) if match else ""


def test_every_shipped_catalog_declares_what_it_measured():
    """The rule. A catalog with neither a `measured:` block nor an allowlist row
    claims its framework rule for every version of that framework, on evidence
    from at most one."""
    undeclared = shipped_catalogs() - set(declared_measurements()) - set(_NOT_MEASURED_YET)
    assert undeclared == set(), (
        "these shipped catalogs declare no `measured:` block (D02 §1a) and are not on this "
        "file's audit list:\n"
        + "\n".join(f"  - {catalog_id}" for catalog_id in sorted(undeclared))
        + "\n\nRun a probe against the artifact this catalog's rule lives in, record the "
        "version the artifact reported, and cite the probe document in `by:`. Adding the id "
        "to _NOT_MEASURED_YET is the other option, and it makes the audit list longer, which "
        "is the direction that list does not travel. Writing a version nobody measured is "
        "neither option: that is `A-Mi8`'s own defect."
    )


def test_the_audit_list_only_ever_shrinks():
    """A catalog that has GAINED a measurement must leave the list in the same
    commit, and an entry naming nothing at all must go too.

    Without this the list is write-only: an id could sit here forever after the
    gap it records was closed, and worse, it would exempt any FUTURE rewrite of
    that catalog from stating a version at all.
    """
    measured = set(declared_measurements())
    stale = sorted(set(_NOT_MEASURED_YET) & measured)
    unknown = sorted(set(_NOT_MEASURED_YET) - shipped_catalogs())
    assert (stale, unknown) == ([], []), (
        "_NOT_MEASURED_YET is out of date — "
        f"now declares a `measured:` block, so remove them: {stale or 'none'}; "
        f"not a shipped catalog at all: {unknown or 'none'}"
    )


def test_every_measured_row_is_well_formed():
    """An unchecked value does not stay in the file: it is the provenance a
    reader trusts, and a malformed one is indistinguishable from a real
    measurement at a glance."""
    malformed: list[str] = []
    for catalog_id, rows in sorted(declared_measurements().items()):
        if not isinstance(rows, list) or not rows:
            malformed.append(f"{catalog_id}: `measured:` is not a non-empty list")
            continue
        for index, row in enumerate(rows):
            where = f"{catalog_id}[{index}]"
            if not isinstance(row, dict):
                malformed.append(f"{where}: not a mapping")
                continue
            artifact = row.get("artifact")
            if not isinstance(artifact, str) or not _COORDINATE.match(artifact):
                malformed.append(
                    f"{where}: `artifact` is not a `groupId:artifactId` — {artifact!r}"
                )
            versions = row.get("versions")
            if not isinstance(versions, list) or not versions:
                malformed.append(f"{where}: `versions` is not a non-empty list — {versions!r}")
            elif not all(isinstance(version, str) and version for version in versions):
                malformed.append(f"{where}: `versions` holds a non-string — {versions!r}")
            if row.get("identity") not in _IDENTITIES:
                malformed.append(
                    f"{where}: `identity` is not one of {sorted(_IDENTITIES)} — "
                    f"{row.get('identity')!r}"
                )
            by = row.get("by")
            if not isinstance(by, str) or not (REPO / by).is_file():
                malformed.append(f"{where}: `by` names no committed file — {by!r}")
    assert malformed == [], "malformed `measured:` rows:\n" + "\n".join(
        f"  - {line}" for line in malformed
    )


def test_every_cited_version_appears_in_the_probe_that_is_cited():
    """`A-Mi8`, mechanically. A version a catalog states and its own probe never
    ran is a guess wearing a citation, and it is exactly the shape CP-5 shipped:
    a number printed beside output from a run that did not produce it.

    The probe's `**Version scope…**` paragraph is the right side to check
    against, because §5.4 makes that paragraph the bound on every verdict in the
    file — so a version outside it is outside the evidence even when the
    document mentions it somewhere else.
    """
    unsupported: list[str] = []
    scopes: dict[str, str] = {}
    for catalog_id, rows in sorted(declared_measurements().items()):
        for row in rows:
            document = REPO / str(row["by"])
            if not document.is_file():
                continue  # `test_every_measured_row_is_well_formed` owns this.
            scope = scopes.setdefault(str(row["by"]), _version_scope(document))
            for version in row["versions"]:
                if version not in scope:
                    unsupported.append(
                        f"{catalog_id}: {row['artifact']} {version} is not in "
                        f"{row['by']}'s version scope"
                    )
    assert unsupported == [], (
        "these `measured:` versions are not in the version scope of the probe they cite:\n"
        + "\n".join(f"  - {line}" for line in unsupported)
        + "\n\nRe-run the probe with the version added to its own artifact list, or cite the "
        "probe that did run it. Do not widen the catalog's claim to a version nothing opened."
    )


def test_every_cited_probe_states_a_version_scope_at_all():
    """A citation is only as good as the paragraph it points at. A probe with no
    version scope bounds nothing, so a row citing it would read as measured while
    resting on the same silence the block exists to end."""
    scopeless = sorted(
        {
            str(row["by"])
            for rows in declared_measurements().values()
            for row in rows
            if (REPO / str(row["by"])).is_file() and not _version_scope(REPO / str(row["by"]))
        }
    )
    assert scopeless == [], (
        f"these cited probes state no `**Version scope…**` paragraph (§5.4): {scopeless}"
    )


def test_the_scan_finds_the_blocks_that_ship():
    """A coverage check that discovers nothing passes for the wrong reason —
    every catalog would be undeclared, the audit list would swallow the ones it
    names, and the rest would fail loudly; but the well-formedness and citation
    rules above would pass vacuously on an empty scan.

    Two pins, one per `identity` value, so a reader that lost either arm is
    caught here rather than by agreeing with everything.
    """
    measured = declared_measurements()
    assert measured, "the `measured:` scan found no block in any shipped catalog"
    assert "spring-webclient" in measured, (
        "the scan no longer sees `spring-webclient`'s block — that is the catalog whose "
        "declared `exchange` terminal exists at spring-webflux 6.1.6 and is gone at 7.0.2, "
        "which is the finding this whole file exists to make sayable"
    )
    identities = {str(row["identity"]) for rows in measured.values() for row in rows}
    assert identities == _IDENTITIES, (
        "the shipped estate no longer exercises both `identity` values — "
        f"found {sorted(identities)}. `assumed` is Retrofit's, and a reader that stopped "
        "distinguishing it from `reported` would let CP-5's mislabelled column back in."
    )
