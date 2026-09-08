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
    no disagreements either. Asserts every question is present before any of
    them is compared against a catalog."""
    numbers = {number.rstrip("abcdefgh") for number in probe_rows()}
    assert numbers == {"1", "2", "3", "4", "5", "6"}, (
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


def test_the_websocket_gate_is_the_annotation_that_marks_a_SERVED_endpoint():
    """`A-C1`. `@OnMessage` is `@Target(METHOD)`, carries no address, and ships
    in the CLIENT api jar (CP-11 Q3) — it is the message callback for a
    dialling-out `@ClientEndpoint` class exactly as much as for a served
    `@ServerEndpoint` one. A catalog with no type gate therefore published a
    WebSocket client as an inbound server endpoint, direction inverted and
    address invented in one row.

    `@ServerEndpoint` is the annotation that makes a class served, it is
    `@Target(TYPE)`, and the catalog's gate must name it — never `@OnMessage`,
    and never nothing.

    EVERY spelling the gate lists, not just the first. W12 added the `javax` one
    beside the `jakarta` one (§3.1's list form), and this assertion used to pin
    the scalar — which would have passed a list whose second element was
    `@OnMessage`, the exact thing it exists to refuse."""
    observed = probe_rows()["3"]["observed"]
    assert "OnMessage in jakarta.websocket-client-api @Target(METHOD)" in observed
    assert "ServerEndpoint in jakarta.websocket-api @Target(TYPE)" in observed
    matches = catalog("jakarta-websocket")["matches"]
    declared = matches["type_annotation"]
    gates = [declared] if isinstance(declared, str) else declared
    assert gates, "the websocket catalog declares no type gate at all"
    assert all(name.endswith(".websocket.server.ServerEndpoint") for name in gates), gates
    assert "jakarta.websocket.ClientEndpoint" not in yaml.dump(matches)
    assert "javax.websocket.ClientEndpoint" not in yaml.dump(matches)


def test_the_stomp_gate_is_the_predicate_spring_stomp_itself_runs():
    """`A-C1`. `spring-stomp.yml` declared no type-level gate at all, so one
    method annotation minted an endpoint at the empty address. Spring STOMP's
    own handler test is the SAME `AnnotatedElementUtils.hasAnnotation(beanType,
    Controller.class)` call MVC runs (CP-11 Q5) — which is what makes adding
    the gate a mirror rather than a tightening somebody chose."""
    stomp = probe_rows()["5"]["observed"]
    mvc = probe_rows()["2a"]["observed"]
    # `ldc` vs `ldc_w` is a constant-pool index width, not a different rule.
    assert stomp.replace("ldc_w", "ldc") == mvc
    assert (
        catalog("spring-stomp")["matches"]["type_annotation"]
        == "org.springframework.stereotype.Controller"
    )


def test_an_http_interface_client_must_be_an_interface():
    """`A-C1`. `spring-http-interface.yml` declared neither a type gate nor
    `declared_on`, so an exchange annotation on a concrete CLASS derived an
    outbound row for a client the framework would never create.

    The requirement is real but it is not asserted where the client is created:
    `createClient` hands the type to Spring AOP's `ProxyFactory`, and
    `AdvisedSupport.addInterface` is what refuses a non-interface (CP-11 Q6a,
    Q6b). Both rows are pinned, because a verdict that rests on a two-hop chain
    is only a measurement while both hops are recorded."""
    assert "aop/framework/ProxyFactory.getProxy" in probe_rows()["6a"]["observed"]
    guard = probe_rows()["6b"]["observed"]
    assert "java/lang/Class.isInterface" in guard
    assert "IllegalArgumentException" in guard
    assert catalog("spring-http-interface")["matches"]["declared_on"] == "interface"


def test_retrofit_only_ever_proxies_an_interface():
    """`A-C6`. `Retrofit.create` validates its argument before proxying it, and
    a non-interface throws `IllegalArgumentException("API declarations must be
    interfaces.")` (CP-11 Q4). A `@GET`-annotated method on a concrete class is
    therefore not a Retrofit call site at all, and the outbound row the catalog
    published for one was a plausible-looking dependency that does not exist."""
    guard = probe_rows()["4"]["observed"]
    assert "java/lang/Class.isInterface" in guard
    assert "API declarations must be interfaces." in guard
    assert catalog("retrofit")["matches"]["declared_on"] == "interface"
