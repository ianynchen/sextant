"""Tests for the `supertype_dispatch` engine (D02 §2's `supertype_dispatch`
style, 2O design §3b, Task 7b).

Facts are hand-built to mirror CP-9's real, checkpoint-recorded shapes exactly
(`scripts/probes/cp9_servlet_shapes.md`, measured against Apache Tomcat
10.1.50, 11.0.24 and 9.0.121): `@WebServlet` arrives as a TYPE-level
annotation whose `args` carry `urlPatterns` or `value` as a LIST even when one
string was written (rows 20-23); a `protected` handler's recorded `visibility`
is `other`, never `protected` (row 24); a handler's parameter types are
readable off its own signature (rows 25-26); and the `extends` edge is present
and module-prefixed even though `HttpServlet` lives in a container jar the
workspace never scanned (rows 27-28). Rather than compiling real class files
per case — which `scripts/probes/cp9_servlet/` already did once, for every one
of these shapes, and recorded.

Two catalogs are exercised, not one: `jakarta-servlet.yml` throughout, and
`javax-servlet.yml` in section (e), which CP-9's third column (Tomcat 9.0.121,
Servlet 4.0) measured row for row against the other two.

Every address below is invented (`/orders/*`, never a pattern the probe
served): the shipped catalog's live answer against real container bytecode
belongs to the probe, not here (the `test_supertype_derived.py` precedent this
file otherwise mirrors).
"""

import json
from pathlib import Path

import pytest

from sextant.application.ports.catalogs import Catalog, CatalogError
from sextant.application.resolve.endpoints import derive_endpoints
from sextant.domain.closed_sets import ConstructKind, OriginTier
from sextant.domain.factfile import write_fact_file
from sextant.domain.facts import (
    AnnotationFact,
    AnnotationUse,
    Document,
    Parameter,
    Signature,
    SymbolFact,
    TypeRef,
)
from sextant.ingress.catalogs.yaml_source import YamlCatalogSource
from sextant.resources import catalogs_dir
from sextant.storage.duckdb.workspace import DuckDbWorkspace

CATALOGS = catalogs_dir()

CAPABILITIES = {"annotation_args", "type_annotations", "typed_signatures", "superclass"}

# The module-coordinates prefix a real symbol fact's own `symbol` carries
# (D00 §5a) — `test_supertype_derived.py`'s own `_MODULE` precedent.
_MODULE = "sextant-jvm maven com.acme/legacy-web 1.0.0 "

DISPATCH_BASE = "jakarta/servlet/http/HttpServlet#"
AGNOSTIC_BASE = "jakarta/servlet/GenericServlet#"
ADDRESS_ANNOTATION = "jakarta/servlet/annotation/WebServlet#"
REQUEST = "jakarta/servlet/http/HttpServletRequest#"
RESPONSE = "jakarta/servlet/http/HttpServletResponse#"
AGNOSTIC_REQUEST = "jakarta/servlet/ServletRequest#"
AGNOSTIC_RESPONSE = "jakarta/servlet/ServletResponse#"
SERVLET = "com/acme/legacy/OrderServlet#"

_DISPATCH_PARAMETERS = [
    "jakarta.servlet.http.HttpServletRequest",
    "jakarta.servlet.http.HttpServletResponse",
]
_MATCHES: dict[str, object] = {
    "supertype": "jakarta.servlet.http.HttpServlet",
    "address": {
        "annotation": "jakarta.servlet.annotation.WebServlet",
        "args": ["urlPatterns", "value"],
    },
    "members": "overridden_dispatch_methods",
    "dispatch": [
        {"name": "doGet", "parameters": _DISPATCH_PARAMETERS, "method": "GET"},
        {"name": "doPost", "parameters": _DISPATCH_PARAMETERS, "method": "POST"},
        {"name": "doPut", "parameters": _DISPATCH_PARAMETERS, "method": "PUT"},
        {"name": "doDelete", "parameters": _DISPATCH_PARAMETERS, "method": "DELETE"},
        {"name": "doHead", "parameters": _DISPATCH_PARAMETERS, "method": "HEAD"},
        {"name": "doOptions", "parameters": _DISPATCH_PARAMETERS, "method": "OPTIONS"},
        {"name": "doTrace", "parameters": _DISPATCH_PARAMETERS, "method": "TRACE"},
    ],
    "bypassed_by": [
        {"name": "service", "parameters": _DISPATCH_PARAMETERS},
        {
            "name": "service",
            "parameters": ["jakarta.servlet.ServletRequest", "jakarta.servlet.ServletResponse"],
        },
    ],
}


def _document() -> Document:
    return Document(
        document_id="doc_1",
        relative_path="com/acme/legacy/OrderServlet.java",
        module_id="com.acme:legacy-web",
        language="java",
        sextant_version="0.1.0",
        fact_schema_version="1.0.0",
        scanner_id="asm",
        scanner_version="9.16",
        content_hash="sha256:a",
        origin_entry="target/classes",
        origin_tier=OriginTier.MODULE_OUTPUT,
        redaction_set_hash="sha256:b",
    )


def _class(symbol: str = SERVLET, *, superclass: str = DISPATCH_BASE) -> SymbolFact:
    """One declared class carrying capability 9.13's `superclass` edge.

    The edge is module-prefixed even though its target lives in a container
    jar nothing here scanned — CP-9 row 27, and the reason this style matches
    on the BARE descriptor rather than on `supertype_derived`'s own
    "the extends target is itself in the module's facts" test.
    """
    return SymbolFact(
        document_id="doc_1",
        symbol=_MODULE + symbol,
        construct_kind=ConstructKind.CLASS,
        superclass=_MODULE + superclass,
    )


def _method(
    name: str, *parameters: str, owner: str = SERVLET, visibility: str = "other"
) -> SymbolFact:
    """One declared method with its parameter types.

    `visibility` defaults to `other`, which is what CP-9 row 24 measured for a
    `protected` handler: D00 §5a's column is two-valued and cannot say
    `protected`, so no test here may depend on it saying so.
    """
    return SymbolFact(
        document_id="doc_1",
        symbol=f"{_MODULE}{owner}{name}(sig_{name}).",
        construct_kind=ConstructKind.METHOD,
        enclosing=_MODULE + owner,
        visibility=visibility,
        signature=Signature(
            parameters=[Parameter(type=TypeRef(symbol=symbol)) for symbol in parameters],
            returns=TypeRef(symbol="void#"),
        ),
    )


def _annotated(args: dict[str, object], *, owner: str = SERVLET) -> AnnotationFact:
    return AnnotationFact(
        document_id="doc_1",
        target=_MODULE + owner,
        use=AnnotationUse(annotation=ADDRESS_ANNOTATION, args=args),  # type: ignore[arg-type]
        retention="RUNTIME",
    )


def _catalog(matches: dict[str, object] | None = None) -> Catalog:
    """The SHIPPED catalog unless a test is about a malformed one.

    Every behaviour test below runs `jakarta-servlet.yml` itself rather than a
    copy of it — which is what makes each `declines` marker a statement about
    the catalog that ships (`tests/architecture/test_catalog_near_miss_coverage.py`)
    rather than about a fixture that could drift away from it. `_MATCHES`
    above is the same vocabulary written out, and it is used only by the
    validation cases, which need a block to break.
    """
    if matches is None:
        return next(c for c in YamlCatalogSource(CATALOGS).load() if c.id == "jakarta-servlet")
    return Catalog(
        id="test-jakarta-servlet",
        style="supertype_dispatch",
        protocol="http",
        direction="inbound",
        requires=("annotation_args", "type_annotations", "typed_signatures", "superclass"),
        matches=matches,
        source=Path("test-jakarta-servlet.yml"),
    )


def _rows(tmp_path: Path, facts: list, catalog: Catalog | None = None) -> list[dict]:
    write_fact_file(tmp_path / "facts" / "OrderServlet.jsonl", _document(), facts)
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    skipped = derive_endpoints(workspace, [catalog or _catalog()], capabilities=CAPABILITIES)
    assert skipped == []
    rows = [dict(row) for row in workspace.query("endpoints")]
    workspace.close()
    return rows


def _identities(rows: list[dict]) -> set[tuple[str | None, str]]:
    return {(row["method"], str(row["path"])) for row in rows}


# --- (a) the address: every pattern is its own endpoint --------------------


def test_each_url_pattern_is_its_own_endpoint(tmp_path: Path):
    """CP-9 rows 1-2: one class, an array-valued address argument, and BOTH
    patterns served. One declaration is N endpoints, never one — a reader
    taking only the first would silently lose half a module's surface."""
    facts = [
        _class(),
        _method("doGet", REQUEST, RESPONSE),
        _annotated({"urlPatterns": ["/orders/*", "/legacy/orders/*"]}),
    ]
    rows = _rows(tmp_path, facts)

    assert _identities(rows) == {("GET", "/orders/*"), ("GET", "/legacy/orders/*")}
    assert {row["protocol"] for row in rows} == {"http"}
    assert {row["direction"] for row in rows} == {"inbound"}
    assert {row["resolution"] for row in rows} == {"resolved"}
    assert {row["handler"] for row in rows} == {f"{_MODULE}{SERVLET}doGet(sig_doGet)."}


def test_the_alias_argument_names_the_same_address(tmp_path: Path):
    """CP-9 rows 3 and 22: `value` and `urlPatterns` are the same attribute
    under two spellings, and they reach the facts as DIFFERENT argument keys.
    A catalog naming only one would derive nothing for half the estate."""
    facts = [
        _class(),
        _method("doGet", REQUEST, RESPONSE),
        _annotated({"value": ["/orders/*"]}),
    ]

    assert _identities(_rows(tmp_path, facts)) == {("GET", "/orders/*")}


def test_a_single_string_address_reads_the_same_as_a_one_element_list(tmp_path: Path):
    """CP-9 row 23 measured the one-element ARRAY the compiler writes for
    `urlPatterns = "/orders/*"`. D00 §5's `LiteralValue` also admits a bare
    string, so both spellings must reach the same address rather than the
    scalar one deriving nothing."""
    facts = [
        _class(),
        _method("doGet", REQUEST, RESPONSE),
        _annotated({"urlPatterns": "/orders/*"}),
    ]

    assert _identities(_rows(tmp_path, facts)) == {("GET", "/orders/*")}


def test_the_pattern_is_published_verbatim_rather_than_interpreted(tmp_path: Path):
    """A servlet pattern is a grammar (`/legacy/*`, `*.do`), not a path to be
    composed or canonicalised. CP-9 measured only that a declared pattern is
    served at its own literal spelling, so that is what is published — an
    engine that normalised `*.do` would publish an address no probe covered."""
    facts = [
        _class(),
        _method("doGet", REQUEST, RESPONSE),
        _annotated({"urlPatterns": ["*.do"]}),
    ]

    assert _identities(_rows(tmp_path, facts)) == {("GET", "*.do")}


# --- (b) the verb: one row per handler the module DECLARES ------------------


def test_one_row_per_declared_dispatch_override(tmp_path: Path):
    """CP-9 rows 4-6: the verb is the overridden method's own, one each, and
    each row names that override as its handler."""
    facts = [
        _class(),
        _method("doGet", REQUEST, RESPONSE),
        _method("doPost", REQUEST, RESPONSE),
        _annotated({"urlPatterns": ["/orders"]}),
    ]
    rows = _rows(tmp_path, facts)

    assert _identities(rows) == {("GET", "/orders"), ("POST", "/orders")}
    by_method = {row["method"]: row["handler"] for row in rows}
    assert by_method["POST"] == f"{_MODULE}{SERVLET}doPost(sig_doPost)."


def test_an_explicitly_overridden_head_or_options_derives_its_own_row(tmp_path: Path):
    """CP-9 rows 11-12: both are served, and — unlike the implicit case below
    — the module DECLARED the handler, so there is a symbol to attribute and a
    declaration to report."""
    facts = [
        _class(),
        _method("doHead", REQUEST, RESPONSE),
        _method("doOptions", REQUEST, RESPONSE),
        _annotated({"urlPatterns": ["/orders"]}),
    ]

    assert _identities(_rows(tmp_path, facts)) == {("HEAD", "/orders"), ("OPTIONS", "/orders")}


def test_an_explicitly_overridden_trace_derives_its_own_row(tmp_path: Path):
    """CP-9 rows 31 and 13, verdict 7 as fix round 1 restated it.

    `HttpServlet.service` dispatches TRACE to `doTrace` exactly as it
    dispatches GET to `doGet` — measured, on all three containers, over a
    connector configured `allowTrace="true"` (row 31: 200). The DEFAULT
    connector refuses the method before dispatch (row 13: 405), but
    `allowTrace` is connector configuration, overridable by whoever deploys
    the module and invisible from its repository, so the default is not proof
    that the address is unserved. A class overriding `doTrace` has declared a
    handler, and a declared handler is a code fact; `docs/COVERAGE.md` carries
    the connector as a STATED DEPENDENCY, on the same terms as Actuator's
    `exposure.include`. This row disappears the day the dependency stops being
    overridable at deploy time."""
    facts = [
        _class(),
        _method("doTrace", REQUEST, RESPONSE),
        _annotated({"urlPatterns": ["/orders"]}),
    ]

    assert _identities(_rows(tmp_path, facts)) == {("TRACE", "/orders")}


def test_implicitly_dispatched_verbs_derive_no_row_of_their_own(tmp_path: Path):
    """CP-9 rows 7-9 and 32, and verdict 5 — THE RULING, pinned.

    `HttpServlet` really does serve HEAD and OPTIONS from a class declaring
    only `doGet` (200 on all three containers, `Allow: GET, HEAD, OPTIONS`),
    and TRACE too where the connector permits the method (row 32: 200 off
    `HttpServlet`'s own `doTrace`). None of the three is derived, because the
    code serving them is in a container jar this workspace never scanned: a
    HEAD row would carry either a NULL handler or `doGet`'s symbol, and the
    second is false — `doGet` is CALLED BY the HEAD path, it does not serve
    HEAD. It is also the ruling this phase already made for the first two
    verbs on Spring Data REST (`docs/COVERAGE.md`), and two catalogs answering
    one question two ways would be the §6 blend. A stated under-report,
    falsified the day an endpoint row can name a handler outside the module.

    This is the complement of the test above, and the pair is what makes the
    TRACE ruling principled rather than a per-verb preference: an EXPLICIT
    override is a declaration, an implicit dispatch is not.
    """
    facts = [
        _class(),
        _method("doGet", REQUEST, RESPONSE),
        _annotated({"urlPatterns": ["/orders"]}),
    ]

    assert _identities(_rows(tmp_path, facts)) == {("GET", "/orders")}


def test_a_parameter_symbol_carrying_module_coordinates_still_matches(tmp_path: Path):
    """D00 §5a: a symbol is module coordinates then a descriptor, and ONLY the
    descriptor is ever compared. The supertype side has always been normalised
    with `bare_descriptor`; the member side is normalised the same way, so the
    two halves of one selector are compared in one coordinate space.

    Not reachable through the shipped catalogs — CP-9 row 25 measured a
    dispatch signature's parameter symbols BARE, and a dispatch contract's
    parameter types are dependency types by construction — which is exactly
    why it needs a test: an asymmetry nothing can reach today fails by
    deriving NOTHING, silently, the first time a catalog names a
    module-local parameter type. §10's permanently-quiet shape.
    """
    facts = [
        _class(),
        _method("doGet", _MODULE + REQUEST, _MODULE + RESPONSE),
        _annotated({"urlPatterns": ["/orders"]}),
    ]

    assert _identities(_rows(tmp_path, facts)) == {("GET", "/orders")}


def test_the_payload_columns_stay_null_because_the_parameters_are_the_container_s(
    tmp_path: Path,
):
    """A dispatch handler's declared parameters are the container's own
    request and response objects, never the wire payload — a servlet reads its
    payload off a stream, which no static read can see. So the row carries no
    `handler_signature` either: that column is what tells
    `derive_endpoint_contracts.sql` a row WANTS owner-keyed shape expansion,
    and expanding these two types would publish the container's API as the
    module's contract."""
    facts = [
        _class(),
        _method("doPost", REQUEST, RESPONSE),
        _annotated({"urlPatterns": ["/orders"]}),
    ]
    [row] = _rows(tmp_path, facts)

    assert row["request_shape"] is None
    assert row["response_shape"] is None
    assert row["handler_signature"] is None
    assert row["caller"] is None and row["peer"] is None


# --- (c) the near-misses (§10), each paired with a positive above -----------


@pytest.mark.declines("jakarta-servlet")
def test_a_dispatch_subclass_with_no_address_annotation_derives_nothing(tmp_path: Path):
    """CP-9 rows 19 and 29: the annotation IS the registration. A class
    extending the dispatch supertype and overriding `doGet` — every other
    conjunct satisfied — is a 404 without it, and carries no annotation fact
    at all, so the absence is read rather than inferred.

    Paired positive: `test_each_url_pattern_is_its_own_endpoint`, the same
    class WITH the annotation.
    """
    facts = [_class(), _method("doGet", REQUEST, RESPONSE)]

    assert _rows(tmp_path, facts) == []


@pytest.mark.declines("jakarta-servlet")
def test_a_class_overriding_service_and_declaring_no_verb_derives_nothing(tmp_path: Path):
    """CP-9 rows 14-15, verdict 8 as amended for `A-M2`.
    `service(HttpServletRequest, HttpServletResponse)` is the very method that
    reads the request's verb and dispatches to `doXxx`; a class that overrides
    it **and declares no `doXxx` at all** serves GET and PUT alike (200 and
    200), so the verb map does not describe it. Applying the map anyway would
    publish `GET` and withhold `PUT` — a WRONG answer, not a partial one.

    NO `doGet` here, and that is the correction: this test used to declare one
    and assert nothing derived, which is the defect `A-M2` names rather than the
    rule CP-9 measured. Its paired positive is now the test below.
    """
    facts = [
        _class(),
        _method("service", REQUEST, RESPONSE),
        _annotated({"urlPatterns": ["/orders"]}),
    ]

    assert _rows(tmp_path, facts) == []


@pytest.mark.parametrize(
    ("request_type", "response_type"),
    [(REQUEST, RESPONSE), (AGNOSTIC_REQUEST, AGNOSTIC_RESPONSE)],
    ids=["protected-service", "public-protocol-agnostic-service"],
)
def test_a_wrapper_that_overrides_service_still_derives_the_verbs_it_declares(
    tmp_path: Path, request_type: str, response_type: str
):
    """`A-M2`, the positive the bypass used to swallow. A cross-cutting wrapper
    — `service()` overridden to add a header and then delegate through
    `super.service(req, resp)`, with `doGet` declared — is the commonest real
    form of a `service()` override, and it lost its WHOLE surface: address,
    verbs and handlers.

    Measured on all three CP-9 containers and BOTH `service` signatures (rows
    35-40): such a class serves GET (200) and POST (200) and REFUSES PUT (405).
    `HttpServlet`'s own dispatch still runs, so the verb table describes it
    exactly, and the 405 is what says so — a class serving every verb alike
    would have answered 200 there.

    Both signatures are parametrized rather than reasoned across, for the
    reason `A-M2` exists: `HttpServlet` has two `service` methods and a verdict
    read against one must not be applied to the other."""
    facts = [
        _class(),
        _method("doGet", REQUEST, RESPONSE),
        _method("service", request_type, response_type),
        _annotated({"urlPatterns": ["/orders"]}),
    ]

    assert [(row["method"], row["path"]) for row in _rows(tmp_path, facts)] == [("GET", "/orders")]


@pytest.mark.declines("jakarta-servlet")
def test_the_protocol_agnostic_service_alone_still_derives_nothing(tmp_path: Path):
    """The second bypass signature's own near-miss, and the reason
    `bypassed_by` is a LIST of `{name, parameters}` rather than a list of names:
    `service(ServletRequest, ServletResponse)` is a different method from the
    protected one — same name, different parameter types — and a class
    overriding it with no `doXxx` has replaced the dispatch just as
    completely."""
    facts = [
        _class(),
        _method("service", AGNOSTIC_REQUEST, AGNOSTIC_RESPONSE),
        _annotated({"urlPatterns": ["/orders"]}),
    ]

    assert _rows(tmp_path, facts) == []


@pytest.mark.declines("jakarta-servlet")
def test_a_protocol_agnostic_supertype_derives_nothing(tmp_path: Path):
    """CP-9 rows 16-17 and 28, verdict 9. A `GenericServlet` subclass carries
    the SAME address annotation and serves GET and PUT alike through one
    protocol-agnostic `service` — it declares no verb dispatch at all. It is
    excluded structurally, by its own `superclass` not being the one the
    catalog names, rather than by a special case."""
    facts = [
        _class(superclass=AGNOSTIC_BASE),
        _method("service", AGNOSTIC_REQUEST, AGNOSTIC_RESPONSE, visibility="public"),
        _annotated({"urlPatterns": ["/orders"]}),
    ]

    assert _rows(tmp_path, facts) == []


@pytest.mark.declines("jakarta-servlet")
def test_a_same_named_method_with_other_parameter_types_derives_nothing(tmp_path: Path):
    """CP-9 rows 18 and 26 — GUIDELINES §8.1's language rule, pinned.

    A method identifies by name AND parameter types in order; arity is a
    consequence of that list, never the rule. `doGet(String,
    HttpServletResponse)` therefore overrides nothing, the supertype's own
    `doGet` still applies, and the container answers 405. A member selector
    keyed on the NAME alone would publish `GET /orders` here — an address
    nothing serves.

    Paired positive: `test_each_url_pattern_is_its_own_endpoint`, the same
    method name with the parameter types that DO make it an override.
    """
    facts = [
        _class(),
        _method("doGet", "java/lang/String#", RESPONSE),
        _annotated({"urlPatterns": ["/orders"]}),
    ]

    assert _rows(tmp_path, facts) == []


@pytest.mark.declines("jakarta-servlet")
def test_an_address_annotation_naming_no_pattern_derives_nothing(tmp_path: Path):
    """An address that cannot be read is not an address. `@WebServlet(name =
    "orders")` carries a servlet NAME and no URL at all; publishing the class
    at an empty path would address nothing, which is the defect Task 7 fixed
    for the annotation engine's own empty compositions."""
    facts = [
        _class(),
        _method("doGet", REQUEST, RESPONSE),
        _annotated({"name": "orders"}),
    ]

    assert _rows(tmp_path, facts) == []


@pytest.mark.declines("jakarta-servlet")
def test_an_address_annotation_writing_BOTH_SPELLINGS_derives_nothing(tmp_path: Path):
    """The two argument spellings are ALIASES of one attribute, and writing
    both is a declaration the container refuses to deploy — so the module
    serves nothing at all, and publishing either value would be a fabricated
    address rather than "the attribute the author named".

    The `args` list is therefore an alias SET, not a precedence list: exactly
    one of its keys must be present. Order-independent by construction, which
    is what makes the answer the same whichever spelling the compiler happened
    to write first.

    Paired positive: `test_the_alias_argument_names_the_same_address`, the
    same class writing one of them.
    """
    facts = [
        _class(),
        _method("doGet", REQUEST, RESPONSE),
        _annotated({"urlPatterns": ["/orders"], "value": ["/legacy/orders"]}),
    ]

    assert _rows(tmp_path, facts) == []


@pytest.mark.declines("jakarta-servlet")
def test_a_declared_address_with_no_dispatch_override_derives_nothing(tmp_path: Path):
    """The address alone is not a boundary: a registered class overriding no
    dispatch method answers 405 to every verb (CP-9 row 6 is that default
    answering for one verb). "The registration is the evidence" cuts both
    ways — this is the other conjunct missing."""
    facts = [_class(), _annotated({"urlPatterns": ["/orders"]})]

    assert _rows(tmp_path, facts) == []


def test_an_unrelated_supertype_derives_nothing_from_this_style(tmp_path: Path):
    """Ordinary class inheritance is not evidence of anything — the C-1 lesson
    `supertype_derived` learned, restated for a style whose gate is a
    supertype the catalog NAMES. A class extending some abstract base of its
    own, annotated or not, is invisible here."""
    facts = [
        _class(superclass="com/acme/legacy/AbstractJob#"),
        _method("doGet", REQUEST, RESPONSE),
        _annotated({"urlPatterns": ["/orders"]}),
    ]

    assert _rows(tmp_path, facts) == []


# --- (d) two classes, and the identity dedup --------------------------------


def test_two_classes_sharing_one_pattern_and_verb_derive_one_row(tmp_path: Path):
    """D02 §5's wire identity is `(protocol, direction, method, path)`, and two
    declarations of it are one endpoint. Deterministic in which handler
    survives: the first by the fact stream's own symbol order, which every
    named query is sorted by (NFR-1)."""
    other = "com/acme/legacy/AaaServlet#"
    facts = [
        _class(),
        _method("doGet", REQUEST, RESPONSE),
        _annotated({"urlPatterns": ["/orders"]}),
        _class(other),
        _method("doGet", REQUEST, RESPONSE, owner=other),
        _annotated({"urlPatterns": ["/orders"]}, owner=other),
    ]
    rows = _rows(tmp_path, facts)

    assert _identities(rows) == {("GET", "/orders")}
    assert rows[0]["handler"] == f"{_MODULE}{other}doGet(sig_doGet)."


# --- (e) the second spelling: `javax-servlet.yml` ---------------------------
#
# CP-9 grew a third column for it (Apache Tomcat 9.0.121, Servlet 4.0) rather
# than the catalog being shipped on the assumption that the two behave alike,
# and all 33 rows measured identical to the two `jakarta` columns modulo the
# package name (`scripts/probes/cp9_servlet_shapes.md`). These tests pin the
# consequence: one rule, two spellings, and NO leakage between them — which is
# the whole of what could be wrong here without being invalid, since the two
# files differ by a string substitution a copy-paste can half-apply.

_JAVAX = {
    "supertype": "javax/servlet/http/HttpServlet#",
    "annotation": "javax/servlet/annotation/WebServlet#",
    "request": "javax/servlet/http/HttpServletRequest#",
    "response": "javax/servlet/http/HttpServletResponse#",
}


def _javax_catalog() -> Catalog:
    return next(c for c in YamlCatalogSource(CATALOGS).load() if c.id == "javax-servlet")


def _javax_facts(*methods: SymbolFact, args: dict[str, object] | None = None) -> list:
    """A `javax`-spelled servlet class: the same three pieces of evidence, with
    every dependency type named in the other package."""
    return [
        _class(superclass=_JAVAX["supertype"]),
        *methods,
        AnnotationFact(
            document_id="doc_1",
            target=_MODULE + SERVLET,
            use=AnnotationUse(
                annotation=_JAVAX["annotation"],
                args=args or {"urlPatterns": ["/orders"]},  # type: ignore[arg-type]
            ),
            retention="RUNTIME",
        ),
    ]


def test_the_two_spellings_declare_one_rule(tmp_path: Path):
    """The two catalogs' `matches` blocks are the SAME document under a package
    rename, and that is the claim CP-9's third column licenses: 33 rows
    identical modulo the spelling.

    Asserted structurally rather than shape by shape because the failure this
    guards is a substitution half-applied — a `jakarta` parameter type left in
    one `dispatch` entry, a `bypassed_by` signature not renamed — each of which
    is wrong without being invalid, matches nothing, and derives nothing
    silently (§10). A deliberate divergence between the two must therefore
    start by measuring one, which is the point.

    The equality below substitutes on the `javax` side only, so on its own it
    is blind to exactly the leftovers it names: an unreplaced `jakarta.servlet`
    string inside `javax-servlet.yml` passes through `.replace()` untouched and
    then matches the jakarta document. The first assertion is what closes that
    — this catalog describes an API whose every type is spelled `javax`, so a
    `jakarta` name anywhere in its `matches` block falsifies the claim
    directly, whether or not the two documents still compare equal.
    """
    jakarta = _catalog().matches
    javax = _javax_catalog().matches

    assert "jakarta" not in json.dumps(javax, sort_keys=True)
    assert json.dumps(javax, sort_keys=True).replace("javax.servlet", "jakarta.servlet") == (
        json.dumps(jakarta, sort_keys=True)
    )


def test_the_second_spelling_derives_its_own_endpoint(tmp_path: Path):
    """CP-9 rows 1-6 on Tomcat 9.0.121, the same answers as the other two
    columns: the annotation registers the class and the overridden `doXxx`
    names the verb."""
    facts = _javax_facts(_method("doGet", _JAVAX["request"], _JAVAX["response"]))

    assert _identities(_rows(tmp_path, facts, _javax_catalog())) == {("GET", "/orders")}


@pytest.mark.declines("javax-servlet")
def test_a_jakarta_spelled_servlet_derives_nothing_from_the_javax_catalog(tmp_path: Path):
    """The near-miss the second catalog introduces, and the only one that is
    new: a module compiled against the OTHER API. Every conjunct is satisfied
    except the package, and the two APIs are genuinely different types — a
    class extending `jakarta.servlet.http.HttpServlet` is not served by
    anything this catalog describes.

    Paired positive: `test_the_second_spelling_derives_its_own_endpoint`.
    """
    facts = [
        _class(),
        _method("doGet", REQUEST, RESPONSE),
        _annotated({"urlPatterns": ["/orders"]}),
    ]

    assert _rows(tmp_path, facts, _javax_catalog()) == []


@pytest.mark.declines("jakarta-servlet")
def test_a_javax_spelled_servlet_derives_nothing_from_the_jakarta_catalog(tmp_path: Path):
    """The mirror, and it is not redundant: the leak this guards runs in the
    other direction — a `jakarta` catalog that had kept a `javax` name would
    match legacy classes and publish them under a rule measured elsewhere."""
    facts = _javax_facts(_method("doGet", _JAVAX["request"], _JAVAX["response"]))

    assert _rows(tmp_path, facts) == []


@pytest.mark.declines("javax-servlet")
def test_a_javax_class_overriding_service_and_declaring_no_verb_derives_nothing(
    tmp_path: Path,
):
    """The bypass under the second spelling, pinned separately from the
    equivalence test above because `bypassed_by` is the block whose entries can
    be renamed wrongly and stay silent: a signature left naming the `jakarta`
    types would match nothing, the bypass would never fire, and this class
    would publish nothing-shaped rows for a class serving every verb alike
    (CP-9 rows 14-15).

    No `doGet`, since `A-M2`: a `javax` wrapper that declares one derives it,
    exactly as its `jakarta` twin does."""
    facts = _javax_facts(_method("service", _JAVAX["request"], _JAVAX["response"]))

    assert _rows(tmp_path, facts, _javax_catalog()) == []


# --- (f) the catalog is refused before any class is matched -----------------


def _without(key: str) -> dict[str, object]:
    return {name: value for name, value in _MATCHES.items() if name != key}


@pytest.mark.parametrize(
    "matches",
    [
        _without("supertype"),
        _without("address"),
        _without("members"),
        _without("dispatch"),
        _without("bypassed_by"),
    ],
)
def test_a_catalog_missing_a_required_block_is_refused(tmp_path: Path, matches: dict):
    """The `interface_implementation._validate_matches` precedent: a broken
    catalog fails at the file that can be fixed, never as a silently empty
    derivation. `bypassed_by` is required even though it may be empty — a
    style whose supertype has no bypass says so explicitly rather than by
    omission, because an omitted bypass is indistinguishable from a forgotten
    one and the forgotten one publishes wrong verbs."""
    with pytest.raises(CatalogError):
        _rows(tmp_path, [_class()], _catalog(matches))


@pytest.mark.parametrize(
    "matches",
    [
        {**_MATCHES, "members": "public_methods"},
        {**_MATCHES, "address": {"annotation": "a.B"}},
        {**_MATCHES, "address": {"annotation": "a.B", "args": []}},
        {**_MATCHES, "dispatch": []},
        {**_MATCHES, "dispatch": [{"name": "doGet", "method": "GET"}]},
        {**_MATCHES, "dispatch": [{"name": "doGet", "parameters": ["a.B"]}]},
        {**_MATCHES, "bypassed_by": [{"name": "service"}]},
    ],
)
def test_a_catalog_whose_vocabulary_is_malformed_is_refused(tmp_path: Path, matches: dict):
    """Each of these is WRONG without being INVALID YAML, which is exactly the
    §10 test for a key needing a guard. A `dispatch` entry with no
    `parameters` is the sharpest: it would read as a name-only selector, which
    CP-9 row 18 proves publishes an address nothing serves."""
    with pytest.raises(CatalogError):
        _rows(tmp_path, [_class()], _catalog(matches))
