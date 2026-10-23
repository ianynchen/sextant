import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import TypeVar, cast

import duckdb

from sextant.application.boundary.source import STAMPS, NotABoundarySource
from sextant.domain.factfile import redact_config_entry_line
from sextant.domain.redaction import Redactor

T = TypeVar("T")

_SQL_DIR = Path(__file__).parent

_NAMED_QUERIES = {
    "documents": "SELECT * FROM documents ORDER BY document_id",
    # `handler` is part of the ordering, not decoration: two mappings may share
    # a wire identity, and an ordering with ties is an ordering that can change
    # between runs (NFR-1). `caller` closes the last tie: an outbound row has
    # no handler at all, so a messaging row whose destination could not be read
    # (`method`/`path`/`handler` all NULL — `sendDefault`, and a reply whose
    # `@SendTo` names nothing) ties with every other such row on the first four
    # columns, leaving their order the insert order rather than an ordering.
    "endpoints": "SELECT * FROM endpoints ORDER BY protocol, method, path, handler, caller",
    "shapes": "SELECT * FROM shapes ORDER BY shape_id",
    # `ordinal` alone would tie across shapes; `shape_id` first is what makes
    # the ordering total rather than merely stable within one shape (NFR-1).
    "shape_fields": "SELECT * FROM shape_fields ORDER BY shape_id, ordinal",
    # The field facts the shape pass expands, in declaration order within each
    # defining document — `seq` is what `ordinal` is derived from, so the
    # ordering is part of the answer rather than a convenience (NFR-1).
    #
    # The two modifiers come through because nothing else can say whether a
    # declared field reaches a payload: a constant bound to the type and a
    # field declared not serialized are as public and as typed as any other,
    # and a pass with nothing to filter on turns both into contract terms
    # nobody wrote. False where a scanner reports no modifiers at all — an
    # absent answer is not a claim that the field is off the wire.
    "fields": """
        SELECT symbol, document_id, seq, signature -> 'returns' AS returns,
               coalesce((modifiers ->> 'static')::BOOLEAN, false) AS "static",
               coalesce((modifiers ->> 'transient')::BOOLEAN, false) AS "transient"
        FROM symbols
        WHERE construct_kind = 'field'
        ORDER BY document_id, seq
    """,
    # The declared types the facts call enumerations. A reference to an
    # enumeration is indistinguishable from a reference to a record — only the
    # referenced type's own fact carries the construct kind — so the pass reads
    # them all once rather than looking one up per field.
    "enum_types": """
        SELECT symbol FROM symbols WHERE construct_kind = 'enum' ORDER BY symbol
    """,
    # Annotations on one target. Ordered by name so a target carrying two of
    # them is read the same way twice; which one wins is the caller's rule,
    # never this ordering.
    "annotations_of": """
        SELECT annotation, args, type_path FROM annotations WHERE target = ? ORDER BY annotation
    """,
    # Every annotation in the workspace, regardless of target — what a scope
    # rule (D02 §2e) needs: the class or package it was declared on is not the
    # field it claims, so `annotations_of`'s per-field lookup cannot find it.
    # `args` rides along for Task 6's effective-annotations pre-pass
    # (`resolve/effective_annotations.py`), which needs a composing type's
    # own declared attributes and not just which annotation it carries.
    # Ordered so two fields under the same scope read its claim the same way.
    # The ORDER BY must uniquely determine row order: the parallel parquet
    # writer preserves only what the sort fixes, so tied rows land in
    # nondeterministic order. (target, annotation) ties are real — 6 of 11
    # field-checked workspaces carry them (review audit, 2026-09-04) — so
    # this widening is genuine hardening. It is NOT the identified cause of
    # the byte-identity e2e's two observed flakes: that fixture has zero
    # tied groups, and the flake's cause remains unidentified and open.
    "annotations": """
        SELECT target, annotation, args, type_path FROM annotations
        ORDER BY target, annotation, type_path, args
    """,
    # `ordinal` alone would tie across callers; `caller` first is what makes
    # the ordering total, the same reason `shape_fields` orders by
    # `shape_id, ordinal` rather than `ordinal` alone (NFR-1).
    "call_sites": "SELECT * FROM call_sites ORDER BY caller, ordinal",
    # D00 §5's field_write: constructors only, direct traces only — the field
    # resolution ladder's (2F) second rung, joining a `field`-kind argument's
    # symbol back to the parameter it was assigned from. Ordered by `field`
    # so a field written by more than one constructor overload reads its
    # candidates together, `from_parameter` breaking the tie (NFR-1).
    # `value` beside them since 2026-10-18 (`OI-138` cause 2): a write from a CONSTANT
    # carries the constant and no parameter, so `from_parameter` is NULL on those rows and
    # the ladder's own reader skips them. NULLS LAST keeps the parameter writes — the rung
    # that reads this — ahead of the constant ones in the tie-break order (NFR-1).
    "field_writes": (
        "SELECT field, from_parameter, value, written_by FROM field_writes "
        # `value` is in the key as well: one method can write one field from several
        # constants, and the other three columns are equal on those rows, so without it the
        # order between them is whatever the engine happens to produce (NFR-1).
        "ORDER BY field, from_parameter NULLS LAST, value::VARCHAR, written_by"
    ),
    # D00 §5's `method_return` (capability 9.18): what each method hands back,
    # one row per return instruction. 2Q's `G3` — cross-method return
    # propagation — is its consumer, and the first one: OI-15 recorded the
    # gap between the fact shipping and a reader existing, and this query is
    # half of closing it.
    #
    # `value` stays JSON and is parsed by the caller, exactly as
    # `call_sites.arguments` is: it is an entry of D00 §5's argument grammar,
    # and a void return's explicit JSON `null` says something a
    # `{"kind":"unresolved"}` does not. Ordered by `method, ordinal` so a
    # method with two `return` statements reads its two answers in
    # instruction order, twice (NFR-1) — the same total ordering
    # `call_sites` takes for the same reason.
    "method_returns": "SELECT method, ordinal, value FROM method_returns ORDER BY method, ordinal",
    # 2Q `G3`'s own derived table. Ordered so a site's candidate callees and
    # each callee's several returns read in one fixed order (NFR-1); `caller,
    # ordinal` alone is not total, since a site whose dispatch narrowed to
    # two implementations contributes a row per implementation.
    "return_flows": """
        SELECT caller, ordinal, result, callee, return_ordinal, value, resolution, evidence
        FROM return_flows ORDER BY caller, ordinal, callee, return_ordinal
    """,
    # D00 §5a's PTR carrier: every declared type's own generic supertype
    # reference, keyed by the type's own (module-prefixed) symbol — the
    # `single_call` engine strips the prefix itself, the same way
    # `_enum_symbols` does, so this stays a plain projection like every other
    # named query. `json_type(...) NOT IN ('NULL')` is deliberate, not
    # `IS NOT NULL`: DuckDB's `->` returns the JSON scalar `'null'` (a string,
    # not SQL NULL) for a fact that explicitly recorded no supertype, and only
    # a genuinely absent key evaluates to SQL NULL — `IS NOT NULL` alone would
    # keep the explicit-null rows too and hand the engine a supertype to
    # follow that no fact ever carried.
    "supertypes": """
        SELECT payload ->> 'symbol' AS symbol, payload -> 'supertype' AS supertype
        FROM raw_facts
        WHERE kind = 'symbol' AND json_type(payload -> 'supertype') NOT IN ('NULL')
          AND document_id IN (SELECT document_id FROM selected_documents)
        ORDER BY symbol
    """,
    # `implemented_interfaces`: every class symbol's own declared interfaces,
    # keyed by the type's own (module-prefixed) symbol — Task 10 consumes this
    # the way `single_call` consumes `supertypes` above. Unlike `supertype`,
    # whose Python default is `None` (dumped as the JSON scalar `null`),
    # `interfaces`' default is an empty list — a hand-built or Python-written
    # fact always carries the key, empty or not, so `json_type(...) <> 'NULL'`
    # would keep every symbol. `json_array_length(...) > 0` excludes both a
    # genuinely absent key (SQL NULL propagates through the comparison) and an
    # explicit empty array the same way, which is what "a class implementing
    # none" must mean regardless of which writer produced the fact.
    "implementations": """
        SELECT payload ->> 'symbol' AS symbol, payload -> 'interfaces' AS interfaces
        FROM raw_facts
        WHERE kind = 'symbol' AND json_array_length(payload -> 'interfaces') > 0
          AND document_id IN (SELECT document_id FROM selected_documents)
        UNION ALL
        SELECT payload ->> 'symbol' AS symbol, payload -> 'interfaces' AS interfaces
        FROM raw_facts
        WHERE kind = 'type_header' AND json_array_length(payload -> 'interfaces') > 0
        ORDER BY symbol
    """,
    # Capability 9.13's own erased-superclass carrier (2O design §1b, Task 5):
    # every class symbol that declares one, keyed by the class's own
    # (module-prefixed) symbol, its `superclass` alongside it — unlike
    # `interfaces` above, both sides arrive ALREADY module-prefixed in the
    # real emitted fact (`ClassScanner`'s `erasedSuperclassJson` writes the
    # full symbol form directly, not the bare descriptor `interfaces`
    # entries carry), so no strip-then-reprefix step is needed at either
    # side of a join against `symbols`/`superclasses` itself. A plain TEXT
    # field, not a JSON one — `payload ->> 'superclass'` alone already
    # excludes an absent key (SQL NULL) the way `supertype`'s own
    # `json_type(...) NOT IN ('NULL')` guard has to spell out, because
    # `superclass` was never given a `null`-writing Python default the way
    # `supertype`'s PTR carrier was (D00 §5a). `supertype_derived`'s own
    # "the extends target is itself in the module's facts" test reads this
    # alongside `declared_symbols`. The parens around `(payload ->>
    # 'superclass')` are load-bearing, not stylistic: this DuckDB build binds
    # `AND` tighter than a bare `->>` immediately after it, so
    # `kind = 'symbol' AND payload ->> 'superclass' IS NOT NULL` parses as
    # `(kind = 'symbol' AND payload) ->> 'superclass' IS NOT NULL` and fails
    # casting the JSON `payload` column to a boolean — reproduced directly
    # against `raw_facts` before this fix landed, not a guess.
    # **`type_header` facts are unioned in here and in `implementations`, and NOWHERE
    # else** (D00 §5, 2026-10-21). They are the superclass, interfaces and class-level
    # annotations of every DEPENDENCY type this module refers to, read from the class file's
    # header in the resolved classpath — so a module exception extending a library exception
    # reaches `Throwable`, and `type_hierarchy`'s walk no longer stops at the first class in
    # a jar. They are a kind of their own rather than `symbol` facts precisely so that the
    # engines minting endpoint rows from declarations (`symbols`, `annotations`) cannot see
    # a library's `@RestController` or `CrudRepository` through them: a header-read type is
    # in the LATTICE and nowhere else, and `declared_symbols` still does not list it, which
    # keeps `type_hierarchy.scanned` and `method_resolution` saying — truthfully — that its
    # methods were never read.
    "superclasses": """
        SELECT payload ->> 'symbol' AS symbol, payload ->> 'superclass' AS superclass
        FROM raw_facts
        WHERE kind = 'symbol' AND (payload ->> 'superclass') IS NOT NULL
          AND document_id IN (SELECT document_id FROM selected_documents)
        UNION ALL
        SELECT payload ->> 'symbol' AS symbol, payload ->> 'superclass' AS superclass
        FROM raw_facts
        WHERE kind = 'type_header' AND (payload ->> 'superclass') IS NOT NULL
        ORDER BY symbol
    """,
    # Every static body a compiler-emitted holder of an interface's default
    # method bodies carries (D00 §5, the delivery register's `DefaultImpls`
    # item): the body's own module-prefixed symbol, the interface its holder
    # stands for (`implements_default_of`, module-prefixed as `superclass`
    # above is), the interface method's NAME (`bridge_of`) and the body's
    # `signature`, whose first parameter is the interface instance. Neither key
    # is projected by `symbols`, so this reads `raw_facts` the way
    # `superclasses` does. The join to the enclosing type's own fact is what
    # keeps an ordinary `$default` bridge — which carries `bridge_of` too, on
    # every data class — out: only a method whose TYPE carries
    # `implements_default_of` is a holder body. `dispatch.py` reads this and
    # nothing else does.
    "default_bodies": """
        SELECT m.payload ->> 'symbol'               AS symbol,
               t.payload ->> 'implements_default_of' AS interface,
               m.payload ->> 'bridge_of'            AS stands_for,
               m.payload ->  'signature'            AS signature
        FROM raw_facts m
        JOIN raw_facts t
          ON t.kind = 'symbol'
         AND (t.payload ->> 'symbol') = (m.payload ->> 'enclosing')
         AND (t.payload ->> 'implements_default_of') IS NOT NULL
        WHERE m.kind = 'symbol' AND (m.payload ->> 'bridge_of') IS NOT NULL
          AND m.document_id IN (SELECT document_id FROM selected_documents)
        ORDER BY symbol
    """,
    # Spec 2026-09-19 §3a. Every method fact carrying `bridge_of` — module and library
    # documents alike — with the name of the function it stands for, which is what
    # `resolve/effective_calls.py` needs to re-target a call to a compiler-emitted
    # default-argument bridge: the site's own target names the bridge, this says which
    # function, and `method_declarations` says whether the sibling exists and is static.
    # `symbols` does not project `bridge_of`, so this reads `raw_facts` as `default_bodies`
    # does. Ordered on the symbol (NFR-1).
    "bridge_declarations": """
        SELECT m.payload ->> 'symbol'    AS symbol,
               m.payload ->> 'bridge_of' AS bridge_of
        FROM raw_facts m
        WHERE m.kind = 'symbol' AND (m.payload ->> 'bridge_of') IS NOT NULL
          AND m.document_id IN (SELECT document_id FROM selected_documents)
        ORDER BY symbol
    """,
    # Spec 2026-09-19 §3b (R2). Every type fact carrying `lambda_body` — the extractor's
    # statement that this class is a compiled lambda and which method holds its body —
    # which is what `resolve/effective_calls.py` needs to hand an `instance` argument of
    # that class to the engines as the `lambda` it is. Read from `raw_facts` as
    # `bridge_declarations` is, for the same reason: `symbols` does not project the key.
    # Ordered on the symbol (NFR-1).
    "lambda_bodies": """
        SELECT payload ->> 'symbol' AS symbol, payload ->> 'lambda_body' AS body
        FROM raw_facts
        WHERE kind = 'symbol' AND (payload ->> 'lambda_body') IS NOT NULL
          AND document_id IN (SELECT document_id FROM selected_documents)
        ORDER BY symbol
    """,
    # Every declared method's own enclosing type and visibility (2O design
    # §1b, Task 5): `method_declarations` above carries `signature` instead,
    # which this join has no use for, and `method_symbols` carries neither
    # `enclosing` nor `visibility` at all — `supertype_derived`'s own
    # `overridden_public_methods` evidence needs both, to tell an
    # implementer's own override from an unrelated same-named method
    # elsewhere in the module AND to gate it on visibility (D00 §5, `Visibility`'s
    # four members — `G-73` — the same column `mapping.members: public_methods`
    # already reads SQL-side in `derive_endpoints.sql`). Both `symbol` and `enclosing`
    # share the module-prefixed coordinate space `effective_annotations.py`'s
    # own `method_declarations` join already relies on. Ordered by symbol for
    # the same reason every other declaration-level query here is.
    #
    # `static` comes through for the same reason it does on `fields` above —
    # the declaring language is the only thing that can say it, and a reader
    # enumerating an interface's exposed members has to tell a member bound to
    # the TYPE from one bound to an instance. `derived_resource` is that reader
    # (fix round 3, I-3): a `static` helper on a Spring Data repository is not
    # a query method, and deriving a `/search/` route for one publishes a URL
    # the framework does not serve. False where a scanner reports no modifiers
    # at all — an absent answer is not a claim that the method is static.
    "method_visibility": """
        SELECT symbol, enclosing, visibility,
               coalesce((modifiers ->> 'static')::BOOLEAN, false) AS "static"
        FROM symbols
        WHERE construct_kind = 'method' ORDER BY symbol
    """,
    # Every `declared_shape` fact (2G design §3), keyed by its own `symbol` —
    # the generated class a compiled schema type travels as, or the schema's
    # own full name for a source-origin one — with its `fields` JSON array
    # carried through verbatim for the expansion pass to project. Only the
    # columns expansion actually reads: `schema_name`/`schema_format`/`origin`
    # are DR-4 precedence's own concern, already settled upstream (`analyze`'s
    # `_prefer_compiled`) before a fact ever reaches this table — reselecting
    # `origin` here would read as if precedence lived in this query too.
    # Ordered by `(symbol, document_id)`, the same tiebreak the interpreter's
    # own sort uses for a symbol that legitimately arrives twice (a shared
    # nested type inlined into more than one schema payload), so which
    # occurrence wins a dict keyed on `symbol` never depends on read order
    # (NFR-1).
    # `schema_format` is the format ladder's rung 4 (2G design §5): the
    # schema that described this shape is the only thing that can say which
    # wire format the payload's own TYPE suggests. `role` is 2H's
    # `schema_operations` engine (D02 §2, 2H design §3): the operation root a
    # type serves, where its schema names one — re-added here WITH a consumer,
    # which is the rule the 2G trim enforced, and read by nothing else.
    # `operation` (2O design §1a) is that same engine's consumer, one role
    # later: the `{input_ref, output_ref, client_streaming, server_streaming}`
    # sub-record a `role == "operation"` shape carries, SQL NULL for every
    # other shape (the amendment added the key; it did not fill it
    # retroactively). `schema_name`/`origin` stay unselected — DR-4 precedence
    # is settled upstream, in `analyze`'s `_prefer_compiled`, before a fact
    # reaches this table.
    "declared_shapes": """
        SELECT payload ->> 'symbol'        AS symbol,
               payload ->> 'evidence'      AS evidence,
               payload ->> 'schema_format' AS schema_format,
               payload ->> 'role'          AS role,
               payload ->  'operation'     AS operation,
               payload ->  'fields'        AS fields,
               -- F4 §5.2 (W24). `schema_operations` mints rows with NO handler and no
               -- caller — its own docstring's "the schema names no code" — so
               -- `drop_borrowed_endpoints.sql` has nothing on such a row to key on.
               -- The tier is projected here instead, and that engine filters its own
               -- roots: a dependency's `.proto` describes the DEPENDENCY's service,
               -- and publishing its operations as this module's API is the same
               -- fabrication by a route the delete cannot reach.
               (SELECT d.origin_tier FROM documents d
                 WHERE d.document_id = raw_facts.document_id) AS origin_tier
        FROM raw_facts WHERE kind = 'declared_shape'
        ORDER BY symbol, document_id
    """,
    # Every declared method symbol, module-prefixed exactly as the fact wrote
    # it — what `interface_implementation` joins a receiver back to (D02 §2's
    # handler rule). A registration's own receiver argument carries only the
    # BARE descriptor (D00 §5a: a call argument never repeats the module
    # coordinates), so a handler built by concatenating that descriptor with
    # the catalog's method name would name no symbol any fact ever emitted;
    # the engine matches against these instead and writes the row it found,
    # verbatim. Ordered by symbol so a type declaring two overloads of the
    # handler method is read the same way twice (NFR-1).
    #
    # A handler may be a method OR a free function (D00 §4) — the same
    # widening `derive_endpoints.sql` already carries; the JVM extractor
    # emits no `function`, so today's behavior is unchanged.
    "method_symbols": """
        SELECT symbol FROM symbols WHERE construct_kind IN ('method', 'function') ORDER BY symbol
    """,
    # Annotation TYPE symbols — checkpoint item (2): an annotation type
    # compiles to `construct_kind: "interface"` (there is no dedicated
    # `annotation` kind), so this is the cheapest correct source for Task
    # 6's "module-local" test (`resolve/effective_annotations.py`): a
    # composed annotation's own type symbol must appear here before its
    # meta-annotations are followed at all — the jar half (D02 §7) never
    # does. `method_symbols` above cannot serve this; a composing type is
    # never a method.
    # BOTH kinds, and `annotation` is the one this exists for: an `@interface`
    # reported `construct_kind: "interface"` until W7 read `ACC_ANNOTATION`, which
    # is why the query is named for the kind it was never really about. Dropping
    # `annotation` here loses every composed mapping — measured on the fixture,
    # `@ApiGet` and `@OrderTopicListener` took `GET /api/composed`, `GET /composed`
    # and the `composed-orders` listener with them. Plain interfaces stay in the
    # set because they were always in it and nothing measured says they should go.
    "interface_symbols": """
        SELECT symbol FROM symbols
        WHERE construct_kind IN ('interface', 'annotation') ORDER BY symbol
    """,
    # Every declared method's own enclosing type and signature JSON,
    # module-prefixed exactly as the fact wrote them (D00 §5a) — checkpoint
    # item (4)'s inheritance join needs both, and `method_symbols` above
    # cannot serve it: `enclosing` places a candidate within its declaring
    # type at all (interface, implementer, or a scanned ancestor further up
    # the chain), and `signature` is what the structural bridge rule
    # (`resolve/effective_annotations.py`'s `inherited_rows`) compares a
    # same-name sibling's parameter/return types against. Ordered by symbol
    # for the same reason `method_symbols` is.
    #
    # `construct_kind = 'method'`, deliberately not `'function'` too (unlike
    # `method_symbols` above, which is a plain call-registration lookup a
    # free function could equally satisfy): inheritance needs `enclosing` to
    # place a candidate within a declaring type at all, and a free function
    # has none — there is no hierarchy for it to inherit through, so
    # widening this query to `IN ('method', 'function')` would only ever add
    # rows this pass's own `enclosing IS NULL` guard immediately drops.
    # `modifiers` carries D00 §5a's `synthetic`, which folds in `ACC_BRIDGE`
    # because javac sets the two together. The effective-annotations walk needs
    # it to tell a method a human wrote from the forwarder javac generates
    # beside it — a distinction it used to infer from the two having the same
    # name and different return types, which sees a covariant bridge and is
    # blind to a generic-parameter one.
    "method_declarations": """
        SELECT symbol, enclosing, signature, modifiers FROM symbols
        WHERE construct_kind = 'method' ORDER BY symbol
    """,
    # F4 §5.2 (W26). The same method rows as `method_declarations` above PLUS
    # `visibility`, for shape expansion's bean-accessor fallback: a payload type whose
    # fields yield no wire contract is described from its public accessors instead, and
    # "public" is the half neither existing query carries beside a signature.
    # `method_declarations` has the signature and no visibility; `method_visibility` has
    # the visibility and no signature. Joining the two in Python would make the accessor
    # set depend on two queries agreeing about which rows exist, which is a second place
    # for the answer to be wrong. Widening `method_declarations` itself would change what
    # its existing readers select, the reason `declared_symbols_with_documents` was added
    # beside `declared_symbols` rather than replacing it.
    # Narrowed here rather than in Python because these three are the ACCESSOR's own
    # definition, not one shape model's opinion: a `serialization.accessors` entry
    # constrains the method NAME and optionally its return's wire type, so it can narrow
    # this set further but can never make a private, parameterised or `void` method an
    # accessor. Pushing them down is what keeps the pass from parsing the `signature`
    # JSON of every method in the workspace — on `mall-admin` that is tens of thousands
    # of rows, and this runs once per catalog.
    #
    # **The no-value test is on `wire_type`, not on the key's presence**, and the first
    # version got that wrong (W26 review). `json_type(... -> 'returns') NOT IN ('NULL')`
    # reads as "the scanner omitted the key for a method that returns nothing", and no
    # scanner does that: `returns` is ALWAYS written, and a no-value one is a JSON OBJECT
    # like any other. Six such methods passed this filter on the fixture, and one named
    # `getNothing` would have reached `shape_fields` as a field called `nothing` with
    # `wire_type: ''` — a value outside D00 §5b's vocabulary, in the export.
    #
    # `wire_type = ''` is the projection's own answer for "reaches no wire type at all",
    # and it covers both the no-value return and the uninstantiable placeholder TYPE
    # beside it, which a test on the type's own name would have let through. Asking the
    # projection rather than the name is also what keeps a language's spelling out of
    # this layer (`test_language_confinement`).
    #
    # `visibility` is in the WHERE and NOT in the SELECT: the narrowing is this query's
    # whole contribution over `method_declarations`, and no reader wants the value back.
    # It was projected until W26's review, which read the comment above as saying the
    # column travels to the caller.
    "accessor_declarations": """
        SELECT symbol, enclosing, signature, modifiers FROM symbols
        WHERE construct_kind = 'method'
          AND visibility = 'public'
          AND coalesce(signature -> 'returns' ->> 'wire_type', '') <> ''
          AND coalesce(json_array_length(signature -> 'parameters'), 0) = 0
        ORDER BY symbol
    """,
    # Every declared constructor's own enclosing type and signature JSON —
    # the field ladder's rung 2 (2F design §4). A `field_write` fact names
    # the parameter INDEX a field was assigned from and nothing else, and a
    # constructor PARAMETER's own annotations live only inside this
    # signature: they are never emitted as their own `annotation` fact (Task
    # 6 checkpoint item (3)), so the `annotations` view cannot serve this and
    # `method_declarations` above never sees a constructor at all. Ordered by
    # symbol so a type declaring two overloads reads its candidates in the
    # same order twice (NFR-1).
    "constructor_declarations": """
        SELECT symbol, enclosing, signature FROM symbols
        WHERE construct_kind = 'constructor' ORDER BY symbol
    """,
    # Every declared symbol, whatever its construct kind — the one thing
    # `application/enrich/validate.py` needs to answer "does this exist?" about
    # a member a claim names or a node a diagram draws (2K design §6). The
    # kind-filtered queries above cannot serve it: a component's members are
    # types, methods and fields together, and asking three queries to rebuild
    # one set would make the answer depend on which kinds were remembered.
    # One column, because existence is the whole question. Ordered by symbol
    # for NFR-1, like every other projection here.
    "declared_symbols": "SELECT symbol FROM symbols ORDER BY symbol",
    # The class-level annotations a `type_header` carries, flattened to the `annotations`
    # view's own columns so a consumer can treat the two sources alike. Read by
    # `error_advice` alone, for `@ResponseStatus` on a handled exception's class — the one
    # engine that asks a TYPE question of an annotation rather than minting a row from it.
    # Deliberately not folded into the `annotations` view: that view is what every endpoint
    # engine scans for declarations, and a dependency's class-level annotations must not
    # appear there (the `superclasses` note above says why).
    "type_header_annotations": """
        SELECT payload ->> 'symbol'          AS target,
               use ->> 'annotation'          AS annotation,
               use ->  'args'                AS args
        FROM raw_facts, UNNEST(from_json(payload -> 'annotations', '["JSON"]')) AS t(use)
        WHERE kind = 'type_header'
        ORDER BY target, annotation
    """,
    # W4b: JVMS 4.7.28's `NestHost` — the TOP-LEVEL type whose nest a nested type
    # belongs to, which three engines had been deriving by splitting a binary name
    # on `$`. Only a nested type above a certain class-file version carries it, so
    # this is a partial map by construction and its reader falls back rather than
    # treating an absent row as "already top-level".
    "nest_hosts": """
        SELECT payload ->> 'symbol' AS symbol, payload ->> 'nest_host' AS nest_host
        FROM raw_facts
        WHERE kind = 'symbol' AND (payload ->> 'nest_host') IS NOT NULL
          AND document_id IN (SELECT document_id FROM selected_documents)
        ORDER BY symbol
    """,
    # Every declared INTERFACE with the three things a supertype-shaped match
    # asks of it (2O design §2a, Task 6): its own visibility, its erased
    # superinterfaces, and capability 9.14's parameterized references to them.
    # Read from `raw_facts` rather than the `symbols` view because that view
    # projects neither list — and both are needed together: `interfaces` is
    # what the closure walk follows, `generic_interfaces` the only place a
    # superinterface's TYPE ARGUMENTS survive (`interfaces` erases
    # `CrudRepository<Order, Long>` to a bare symbol), and joining two queries
    # on symbol would only rebuild this row.
    #
    # `generic_interfaces` is SQL NULL for a class the extractor found nothing
    # generic on — the emitter writes the key only when it has one — which is
    # a different absence from an empty array and is read as the same "nothing
    # parameterized here" by the caller.
    "interface_declarations": """
        SELECT payload ->> 'symbol'            AS symbol,
               payload ->> 'visibility'        AS visibility,
               payload -> 'interfaces'         AS interfaces,
               payload -> 'generic_interfaces' AS generic_interfaces
        FROM raw_facts
        WHERE kind = 'symbol' AND (payload ->> 'construct_kind') = 'interface'
          AND document_id IN (SELECT document_id FROM selected_documents)
        ORDER BY symbol
    """,
    # D00 §5's `module` fact, as the one question a catalog asks of it today
    # (2O design §2a, ruling R9): which `groupId:artifactId` coordinates this
    # module's build declares. The JSON array is projected whole and parsed by
    # the reader, the same way `implementations` hands `interfaces` over —
    # unnesting it here would need a second column to keep the ordering
    # deterministic, and the list is small enough that the reader's own set is
    # cheaper. NO ROW AT ALL is the honest answer for a workspace whose facts
    # predate the module fact, or one a test built by hand, and it is a
    # DIFFERENT answer from an empty array (a build that declares nothing) —
    # which is why the gate distinguishes them.
    # `dependency_versions` rides the same row (F1): the version each of those
    # coordinates resolved to, projected whole for the same reason the
    # coordinates are. A coordinate ABSENT from the map is a version this
    # analysis could not read, which is a different answer from a dependency
    # with no version — so a reader scoping a rule to a version must treat the
    # absence as unanswerable, exactly as the gate treats a missing row.
    "module_dependencies": """
        SELECT payload ->> 'module_id'            AS module_id,
               payload -> 'dependency_coordinates' AS dependency_coordinates,
               payload -> 'dependency_versions'    AS dependency_versions,
               -- Who answered for the two above (spec 2026-10-21 §3c): `maven` or `gradle`
               -- means the build tool's own resolved set, transitives included, and an
               -- absence from it is a real absence; `declared` means a build-file parse.
               payload ->> 'dependency_source'     AS dependency_source
        FROM raw_facts WHERE kind = 'module'
        ORDER BY module_id
    """,
    # `documents` counts class files this module BUILT; the one synthetic document holding
    # every `type_header` fact is not one, so it is left out here and counted on its own as
    # `type_headers` — the number of dependency types whose header was read.
    "coverage": """
        SELECT count(*) FILTER (WHERE NOT header_only)                AS documents,
               sum(CASE WHEN partial AND NOT header_only THEN 1 ELSE 0 END) AS partial_documents,
               (SELECT count(*) FROM raw_facts WHERE kind = 'type_header') AS type_headers,
               -- The other half of that number (spec 2026-10-21 §3e): named types the read
               -- found in no archive, off the header document that holds the read.
               (SELECT coalesce(max(type_headers_unlocated), 0) FROM documents
                WHERE header_only)                                    AS type_headers_unlocated
        FROM documents
    """,
    # FR-17 clause 3 (F8 §9.5, W38). How much was UNDERSTOOD, beside how many files were
    # opened. Three GROUP BYs on columns that already exist, composed into `coverage` by
    # `resolve/pipeline.py` — the vocabulary is D00's closed sets and folding rows into a
    # summary is Python's job, not a CASE expression's.
    "resolution_distribution": """
        SELECT resolution AS bucket, count(*) AS edges
        FROM call_edges GROUP BY 1 ORDER BY 1
    """,
    # The number the one above cannot give. `resolution` says whether DISPATCH settled a
    # call; it reads 100% `resolved` on two of the four measured corpora, because naming a
    # target the compiler wrote is easy and reading its BODY is the hard part. This says
    # how often the body was there: `mall-admin` 78%, and 32% on the three that depend
    # heavily on libraries nobody scanned.
    "reach_distribution": """
        SELECT CASE WHEN callee IS NULL THEN 'boundary' ELSE 'body_read' END AS bucket,
               count(*) AS edges
        FROM call_edges GROUP BY 1 ORDER BY 1
    """,
    # WHY a body was not reached, which is what makes the reach rate actionable: an owner
    # in an unscanned jar is a scanning decision, `no_declaration_found` is a defect.
    # Keyed per (class, name, descriptor) rather than per edge — that is the grain the
    # lookup itself answers at (JVMS 5.4.3.3, F3 §4.2).
    "method_resolution_distribution": """
        SELECT reason AS bucket, count(*) AS methods
        FROM method_resolution GROUP BY 1 ORDER BY 1
    """,
    # `resolve/config.py`'s own input: every config_entry, in declaration
    # order within its document (`config_entries.seq`, D00 §5c) and its
    # document ahead of that (`document_id`) so a multi-document file's own
    # documents are read together, `doc_index` breaking the tie between them
    # — the same NFR-1 ordering role `call_sites`'s `caller, ordinal` plays.
    "config_entries": "SELECT * FROM config_entries ORDER BY document_id, doc_index, seq",
    # `resolved_config`'s own export/read shape (D01): ordered by
    # `environment, key` so "unresolved for prod, resolved for dev" reads as
    # two adjacent rows rather than an arbitrary interleaving (NFR-1).
    "resolved_config": """
        SELECT key, value, source, environment, unresolved_reason
        FROM resolved_config ORDER BY environment, key
    """,
    # The per-environment answer for every address expression a client-side
    # row carries — a JOIN, never a write (2F design §3, job 3): endpoint
    # rows keep their expressions, `resolved_config` keeps the values, and
    # nothing rewrites a row per environment. One row per (client-side
    # endpoint, environment).
    #
    # `direction <> 'inbound'` rather than `= 'outbound'`: a `both` row is a
    # path the module both exposes and CALLS (D02 §3's merge), so it carries
    # a caller's address expression exactly as an outbound row does — an
    # equality test would silently drop every merged one.
    #
    # A placeholder count, not a regex alternation, decides the three cases:
    # `${` occurs zero times (a literal, which passes straight through with
    # its own value), once (substituted from `resolved_config` for this
    # environment), or more (`multi_placeholder` — D01's own reason for an
    # expression that is substitutable only piecewise, the one reason M04's
    # pass 2 never emits because it belongs to this join alone). `length`
    # minus the length with the opening delimiter removed, over the
    # delimiter's own length, IS that count.
    #
    # `path` and `peer` are resolved independently — a row may carry an
    # expression in either or both (D01 §3: `peer` is the target hint,
    # `path` the address, and 2F's base composition puts a whole unsplit
    # expression in `path` with `peer` NULL). The single `unresolved_reason`
    # column reports `path`'s answer first, `peer`'s only when `path` had
    # nothing to say, so one column still names why a row did not resolve
    # for an environment.
    #
    # With no resolved environments at all the join is empty and so is this
    # answer: "the same rows, unresolved" and "no environments to resolve
    # against" are different claims, and only the first one would be a lie.
    "resolved_peers": """
        WITH environments AS (SELECT DISTINCT environment FROM resolved_config),
        candidates AS (
            SELECT protocol, direction, method, path, peer, caller, catalog_id
            FROM endpoints
            WHERE direction <> 'inbound'
        ),
        paired AS (
            SELECT c.*, e.environment,
                   ((length(coalesce(c.path, '')) -
                     length(replace(coalesce(c.path, ''), '${', ''))) / 2)::INTEGER
                       AS path_placeholders,
                   ((length(coalesce(c.peer, '')) -
                     length(replace(coalesce(c.peer, ''), '${', ''))) / 2)::INTEGER
                       AS peer_placeholders,
                   regexp_extract(coalesce(c.path, ''), '\\$\\{([^}]*)\\}', 1) AS path_key,
                   regexp_extract(coalesce(c.peer, ''), '\\$\\{([^}]*)\\}', 1) AS peer_key
            FROM candidates c CROSS JOIN environments e
        ),
        joined AS (
            SELECT p.*,
                   pk.value AS path_value, pk.unresolved_reason AS path_reason,
                   qk.value AS peer_value, qk.unresolved_reason AS peer_reason
            FROM paired p
            LEFT JOIN resolved_config pk
                   ON pk.key = p.path_key AND pk.environment = p.environment
            LEFT JOIN resolved_config qk
                   ON qk.key = p.peer_key AND qk.environment = p.environment
        )
        SELECT protocol, direction, method, path, peer, caller, catalog_id, environment,
               CASE WHEN path_placeholders = 0 THEN path
                    WHEN path_placeholders > 1 THEN NULL
                    WHEN path_value IS NULL THEN NULL
                    ELSE replace(path, '${' || path_key || '}', path_value) END AS resolved_path,
               CASE WHEN peer_placeholders = 0 THEN peer
                    WHEN peer_placeholders > 1 THEN NULL
                    WHEN peer_value IS NULL THEN NULL
                    ELSE replace(peer, '${' || peer_key || '}', peer_value) END AS resolved_peer,
               coalesce(
                   CASE WHEN path_placeholders > 1 THEN 'multi_placeholder'
                        WHEN path_placeholders = 1 AND path_value IS NULL
                            THEN coalesce(path_reason, 'missing_key') END,
                   CASE WHEN peer_placeholders > 1 THEN 'multi_placeholder'
                        WHEN peer_placeholders = 1 AND peer_value IS NULL
                            THEN coalesce(peer_reason, 'missing_key') END
               ) AS unresolved_reason
        FROM joined
        ORDER BY environment, protocol, method, path, peer, caller
    """,
    # The 2K hand-off ledger (2G design §6). Ordered by the wire identity the
    # row carries, `question` breaking a tie where one endpoint raises both
    # kinds — "rows are ordered by wire identity for NFR-1 determinism", and
    # an ordering with ties is one that can change between runs.
    #
    # Wire identity plus `question` is NOT total, which is why the row's own
    # content closes it: two listeners on one destination are two rows sharing
    # every one of those four columns (`endpoints` itself orders by
    # `handler, caller` for exactly this reason), and their order would
    # otherwise be the insert order rather than an ordering. `candidates` is
    # cast to text because it is the answer that differs between two such
    # rows, and `evidence` is the last tie-break — two rows agreeing on all
    # six are the same question asked twice and may appear in either order
    # without changing a byte.
    "open_questions": """
        SELECT protocol, method, path, question, candidates, evidence
        FROM open_questions
        ORDER BY protocol, method, path, question, candidates::VARCHAR, evidence
    """,
    # Every symbol that came out of an extracted LIBRARY rather than the
    # module's own output, with the coordinate it came from (D00 §2's
    # `origin`). Read by the renderer, which has to mark a row a library
    # contributed: an endpoint row names a handler or a caller and nothing
    # else, so the attribution has to be joined back through the document the
    # symbol was declared in.
    #
    # Joined through the `documents` view, which projects `origin` for the
    # bundle's sake anyway (schema.sql's own note): one projection, read by the
    # renderer and exported, rather than a second extraction that could drift
    # from it. `origin` is absent — hence NULL here — on a module's own
    # document, so `IS NOT NULL` is the whole filter. Ordered by symbol for
    # NFR-1.
    "library_symbols": """
        SELECT s.symbol AS symbol, d.origin AS origin
        FROM symbols s
        JOIN documents d ON d.document_id = s.document_id
        WHERE d.origin IS NOT NULL
        ORDER BY symbol
    """,
    # The two NON-WIRE tables (2O design §4). Ordered on their whole content
    # rather than on a key, for the reason `open_questions` above states: these
    # rows carry no wire identity to order by, and an ordering with ties is one
    # that can change between runs (NFR-1). Two `@Scheduled` methods sharing a
    # trigger and an expression are two real rows — nothing but the handler
    # tells them apart — so the handler leads, and `catalog_id` closes the tie
    # a second catalog claiming the same annotation would otherwise leave open.
    "scheduled_work": """
        SELECT handler, trigger, expression, resolution, evidence, catalog_id
        FROM scheduled_work
        ORDER BY handler, trigger, expression, resolution, evidence, catalog_id
    """,
    # `scope` is cast to text in the ORDER BY for the reason `open_questions`
    # casts `candidates`: it is a JSON document, DuckDB has no ordering for
    # one, and it is the column that differs between two rows agreeing on
    # everything to its left.
    "error_handlers": """
        SELECT handler, advice, declared_by, scope, exception, status,
               response_shape, resolution, evidence, catalog_id
        FROM error_handlers
        ORDER BY advice, handler, exception, status, response_shape,
                 declared_by, scope::VARCHAR, resolution, evidence, catalog_id
    """,
    # Spec 2026-10-22-boundary-vocabulary-and-diff §2: one query per boundary kind, read by
    # `application/boundary/source.py` over a workspace and over a bundle's Parquet alike,
    # so each is plain SELECT over the exported tables' columns. One row per table row —
    # grouping on identity is the reader's, because it must treat NULL as equal to NULL
    # and SQL equality does not.
    #
    # The ORDER BY is identity, then every attribute, then the evidence columns, so the
    # rows arrive in a fixed order (NFR-1). It decides no attribute: where the rows of a
    # group disagree on one, the reader carries every distinct value, sorted, as
    # `{"several": [...]}`, never the value of whichever row came first.
    # The `direction` test is the same text as `Kind.where` in the vocabulary (a test pins
    # it): a `both` row is one wire identity on each side.
    "boundary_endpoint": """
        SELECT protocol, method, path, request_shape, response_shape, consumes, produces,
               format, resolution, direction, handler, caller, catalog_id
        FROM endpoints WHERE direction IN ('inbound', 'both')
        ORDER BY protocol, method, path, request_shape, response_shape, consumes, produces,
                 format, resolution, direction, handler, caller, catalog_id
    """,
    "boundary_dependency": """
        SELECT protocol, method, path, peer, request_shape, response_shape, format,
               resolution, direction, handler, caller, catalog_id
        FROM endpoints WHERE direction IN ('outbound', 'both')
        ORDER BY protocol, method, path, peer, request_shape, response_shape, format,
                 resolution, direction, handler, caller, catalog_id
    """,
    "boundary_contract": """
        SELECT shape_id, content_hash, origin_tier FROM shapes
        ORDER BY shape_id, content_hash, origin_tier
    """,
    "boundary_property": """
        SELECT key, environment, value, unresolved_reason, source FROM resolved_config
        ORDER BY key, environment, value, unresolved_reason, source
    """,
    "boundary_schedule": """
        SELECT handler, trigger, expression, resolution, catalog_id FROM scheduled_work
        ORDER BY handler, trigger, expression, resolution, catalog_id
    """,
    "boundary_error_handler": """
        SELECT handler, exception, advice, scope, status, response_shape, catalog_id
        FROM error_handlers
        ORDER BY handler, exception, advice, status, response_shape, scope::VARCHAR,
                 catalog_id
    """,
    # The documents that declare the symbols the boundary rows name — every handler and
    # caller an endpoint row carries, and the handler of a schedule and of an error
    # handler — so the reader learns each row's documents and their `origin_tier` in one
    # read rather than one per row. `symbols` is already limited to the documents the
    # multi-release selection kept. A symbol declared in two documents is two rows.
    "boundary_symbol_documents": """
        SELECT DISTINCT s.symbol AS symbol, d.relative_path, d.origin_tier
        FROM symbols s JOIN documents d ON d.document_id = s.document_id
        WHERE s.symbol IN (
            SELECT handler FROM endpoints UNION SELECT caller FROM endpoints
            UNION SELECT handler FROM scheduled_work UNION SELECT handler FROM error_handlers
        )
        ORDER BY s.symbol, d.relative_path, d.origin_tier
    """,
    # A shape's declaring document. The shape id is the symbol with its module prefix
    # (`<scanner> <build> <coordinates> <version> `) removed, and the prefix holds the only
    # spaces a symbol has, so the last space-separated token of the symbol IS the shape id —
    # an equality, which the engine hashes, where a suffix test would be a scan per shape.
    # A declared schema's bare name matches no symbol and has no row here, which is right:
    # no class file declares it.
    "boundary_shape_documents": """
        SELECT DISTINCT sh.shape_id AS shape_id, d.relative_path, d.origin_tier
        FROM shapes sh
        JOIN symbols s ON regexp_extract(s.symbol, '[^ ]+$') = sh.shape_id
        JOIN documents d ON d.document_id = s.document_id
        ORDER BY sh.shape_id, d.relative_path, d.origin_tier
    """,
    # 2Q `I1`'s root set — the methods a trace starts at, with the kind of
    # thing that starts it and the wire address that reaches it. Ordered on the
    # whole row because that is all there is: `handler` alone is not total (one
    # method can be both the target of a request and the target of a clock,
    # which is two rows and two different answers, and one handler can serve
    # three addresses, which is three rows `roots_of` collapses back into one
    # root), and an ordering with ties is one that can change between runs
    # (NFR-1) — the `scheduled_work` reasoning, one table on.
    "roots": """
        SELECT handler, root_kind, protocol, method, path
        FROM roots
        ORDER BY handler, root_kind, protocol, method, path
    """,
    # F8 §9.4's reachability (W37). The pass that WRITES this table has no need to read it
    # back, so it shipped with an export query and no named one — which meant nothing
    # in-process could see it and every check on its content had to open the parquet.
    # Ordered `root, depth, symbol` rather than the pass's own `root, symbol`: depth is
    # what a reader slices on ("what does this handler call directly"), and it is total
    # with `symbol` behind it because one (root, symbol) is one row by construction.
    "reachability": """
        SELECT root, symbol, depth, terminal
        FROM reachability
        ORDER BY root, depth, symbol
    """,
    # Spec 2026-09-22 §3d/§7a's shadow review list. Empty on every analysis that
    # did not ask for shadow mode, which is what an ordinary run should answer.
    #
    # The ordering is what a REVIEWER reads it in: one catalog's questions
    # together, then position, then path — because the review is per catalog
    # (Tasks 7-9 migrate one engine at a time and read their own rows first),
    # and because a position answered on several paths is several rows that
    # belong beside one another. Total by construction: (catalog, caller,
    # ordinal, slot, path) is the row's identity, so no tie survives it.
    "value_resolutions": """
        SELECT catalog, caller, ordinal, slot, path, outcome,
               answer_kind, literal_kind, value, reason
        FROM value_resolutions
        ORDER BY catalog, caller, ordinal, slot, path
    """,
    # `G-74`'s own join: every `invoke_kind: throw` call site whose CALLER is a symbol a
    # root reaches (`reachability`, the root's own body at depth 0 included) — a throw
    # site reachable from a handler, at whatever depth. `cs.owner` is the thrown TYPE,
    # Task 16's own shape (`G-52`): non-NULL where the extractor read it (a `NEW`, an
    # invoke's declared return) and NULL for a rethrow whose type lives in the try-catch
    # table nothing here reads. `call_sites` is already scoped to `selected_documents` in
    # its own view definition, so this join needs no filter of its own — the
    # `default_bodies` precedent above scopes at `raw_facts`; this one scopes at the view
    # built on it. `egress/render/document.py`'s `Fails with` line is the only reader.
    "reachable_throws": """
        SELECT r.root AS root, cs.caller AS caller, cs.ordinal AS ordinal, cs.owner AS target
        FROM reachability r
        JOIN call_sites cs ON cs.caller = r.symbol
        WHERE cs.invoke_kind = 'throw'
        ORDER BY root, caller, ordinal
    """,
    # 2Q `G4`'s call graph. `caller, ordinal` alone is not total — a site whose
    # dispatch narrowed to two bodies is two rows — so `target` and `callee`
    # close it; `callee` is last because it is the column those two rows differ
    # in, and NULLs sort together at one end rather than interleaving (NFR-1).
    #
    # Ordered by `ordinal` within a caller and NOT by anything else first,
    # because that order is the answer: it is the control-flow position the
    # statements were written in, and it is what gives a walk over these rows
    # its nesting.
    # F3 §4.2's two resolution tables. Ordered by their own search order rather than
    # alphabetically: `position` is what decides which ancestor answered, so a reader
    # sorting these rows any other way is reading them wrong.
    # F4 §5.2 (W25). The formal type parameters a generic declaration introduces, in
    # DECLARATION ORDER — which is what binds them to a reference's own `arguments`:
    # `CommonResult<T>` seen as `CommonResult<UmsAdmin>` binds `T` to `UmsAdmin` by
    # position, and a list that lost its order would bind the wrong one silently.
    # Emitted only where a declaration HAS parameters (`ClassScanner`'s "nothing
    # generic, nothing captured" rule), so an absent row means a non-generic type.
    # A declared symbol with the document that declared it, so a consumer can ask where
    # a type came from (W25's `shapes.origin_tier`). `declared_symbols` answers the
    # symbol alone, and widening it would change what every existing reader gets.
    "declared_symbols_with_documents": ("SELECT symbol, document_id FROM symbols ORDER BY symbol"),
    # F8 §9.3 (W35). Everything the index needs to PLACE a symbol, in one query: the
    # symbol, the document that declared it, its kind and enclosing type, and the line
    # extent `LineNumberTable` gave it.
    #
    # Its own query rather than widening `declared_symbols_with_documents`, whose two
    # readers want exactly two columns — the reason `declared_symbols_with_documents` was
    # added beside `declared_symbols` rather than replacing it.
    #
    # `line_start`/`line_end` are 0 where the class file states none, which for a TYPE or a
    # FIELD is always: neither carries a `LineNumberTable`. The index turns that 0 into a
    # NULL, because "the class file does not say" and "line zero" are different things.
    # F8 §9.3 (W35). Every document's path AND where its class file was read from, which
    # is what lets the index reach a SIBLING module's sources: the sibling's own root is
    # the parent of its `target/classes`, and nothing else in the workspace names it.
    "located_documents": """
        SELECT document_id, relative_path, origin_entry FROM documents ORDER BY document_id
    """,
    # F8 §9.3 (W36 review). The annotation view WITH its document, which is what places an
    # annotation whose target is not a symbol: a package declaration
    # (`…/package-info#`) has no symbol row of its own, so `NullMarked` — a scope rule
    # covering every type in the package — came out of the index with `file: null`.
    "located_annotations": """
        SELECT target, annotation, document_id FROM annotations
        ORDER BY target, annotation, document_id
    """,
    "located_symbols": """
        SELECT symbol, document_id, construct_kind, enclosing, line_start, line_end
        FROM symbols ORDER BY symbol
    """,
    "type_parameters": """
        SELECT payload ->> 'symbol'         AS symbol,
               payload ->  'type_parameters' AS type_parameters
        FROM raw_facts
        WHERE kind = 'symbol'
          AND json_type(payload -> 'type_parameters') NOT IN ('NULL')
          AND document_id IN (SELECT document_id FROM selected_documents)
        ORDER BY symbol
    """,
    "type_hierarchy": "SELECT * FROM type_hierarchy ORDER BY child, position, ancestor",
    # F5 §6.2 (W29). Ordered on the whole row because nothing shorter is total: one call
    # may carry several headers, and two callers may reach one address with different ones
    # — so the endpoint columns alone tie, and `kind, name` ties for a repeated header
    # name, which is legal HTTP. A tie is an order that can change between runs (NFR-1).
    # Spec 2026-10-21-conditional-controllers (ruled 2026-10-22), read since spec
    # 2026-10-22-conditional-beans through the VIEW of that name: the conditions an endpoint
    # row's bean carries, one row per environment, in the order a reader compares them —
    # endpoint, then environment. `caller`, `via` and `bean_kind` last, the view's own order;
    # they join the ORDER BY so an outbound row (no handler) and two routes of one bean are as
    # total an order as one inbound row (NFR-1).
    "endpoint_conditions": """
        SELECT protocol, direction, method, path, handler, kind, expression, environment,
               holds, resolution, evidence, caller, via, bean_kind, bean
        FROM endpoint_conditions
        ORDER BY protocol, direction, method, path, handler, kind, expression, environment,
                 caller, via, bean_kind, bean
    """,
    # Spec 2026-10-22-conditional-beans §2: the conditions every bean carries, keyed by the
    # bean. Ordered on the whole row — one bean may be reached by several routes, each a
    # (bean_kind, via), and several conditions per route.
    "bean_conditions": """
        SELECT bean, bean_kind, via, kind, expression, environment, holds, resolution,
               evidence
        FROM bean_conditions
        ORDER BY bean, bean_kind, via, kind, expression, environment, holds, resolution,
                 evidence
    """,
    # Where each conditional bean exists, per environment — the view folding the rows above
    # (OR across routes, AND within one; ruled 2026-10-22).
    "bean_presence": """
        SELECT bean, environment, holds, resolution, evidence
        FROM bean_presence
        ORDER BY bean, environment
    """,
    # The bean each code symbol belongs to — the one rule (own symbol, then owner class) the
    # `endpoint_conditions` view and the documents both read (Task 5, ruling 1). One row per
    # symbol whose bean is conditional.
    "symbol_beans": "SELECT symbol, bean FROM symbol_beans ORDER BY symbol, bean",
    # Which candidates of each narrowed call site exist in each environment (spec §3; Task 5,
    # ruling 3): every candidate of a site with a conditional one, per environment. Ordered on
    # the site, then the candidate, then the environment — the order a trace block reads it.
    "candidate_presence": """
        SELECT caller, ordinal, callee, bean, environment, holds, resolution, evidence
        FROM candidate_presence
        ORDER BY caller, ordinal, callee NULLS LAST, bean, environment
    """,
    # Every interface the framework registers and implements at run time, with each type it
    # is assignable to (CP-46) — what `candidate_presence` matches a call site's named type on.
    "interface_beans": "SELECT bean, type FROM interface_beans ORDER BY bean, type",
    # The lambda bodies each method's `dynamic` call sites create (spec 2026-10-22-conditional-
    # beans §2a): a body a factory method creates is that factory's code. `invoke_kind` is the
    # site's own dispatch form; the reader keeps the synthetic bodies (lambdas) among them.
    "lambda_edges": """
        SELECT DISTINCT caller, callee FROM call_edges
        WHERE invoke_kind = 'dynamic' AND callee IS NOT NULL
        ORDER BY caller, callee
    """,
    # The bodies every virtual or interface call site dispatches to, each with the method the
    # site names and the type declaring the body (spec 2026-10-22-conditional-beans, ruled
    # 2026-10-22): which bean an INHERITED body runs as part of is asked of the module's own
    # method resolution for exactly these. Equi-joins on the site and the body's own symbol.
    "dispatched_bodies": """
        SELECT DISTINCT e.callee AS body, s.name, s.descriptor, y.enclosing
        FROM call_edges e
        JOIN call_sites s ON s.caller = e.caller AND s.ordinal = e.ordinal
        JOIN symbols y ON y.symbol = e.callee
        WHERE e.invoke_kind IN ('virtual', 'interface') AND y.enclosing IS NOT NULL
        ORDER BY body, s.name, s.descriptor, y.enclosing
    """,
    # The constructor calls a `@Bean` method's body makes, and every other one in the module
    # (spec 2026-10-22-conditional-beans §2a): which class a factory constructs, and whether
    # that class is also constructed anywhere else. Read once per resolve, restricted here to
    # `<init>` sites with a body this workspace read — a library class has no code a derived
    # row could live in. The site's own `name` says what is called, so nothing parses a
    # descriptor to tell a constructor from a method.
    "constructor_edges": """
        SELECT DISTINCT e.caller, e.callee
        FROM call_edges e
        JOIN call_sites s ON s.caller = e.caller AND s.ordinal = e.ordinal
        WHERE s.name = '<init>' AND e.callee IS NOT NULL
        ORDER BY e.caller, e.callee
    """,
    "endpoint_metadata": """
        SELECT protocol, direction, method, path, caller, kind, name, value,
               resolution, evidence, requirement
        FROM endpoint_metadata
        ORDER BY protocol, direction, method, path, caller, kind, name, value,
                 resolution, evidence, requirement
    """,
    # Spec 2026-09-19 §4d/§5a. The combinator's stash of per-route requirements, read once
    # per resolve by the requirements pass. Ordered on the whole row for the reason the
    # query above is: two selectors under one route are two rows that tie on every
    # route column.
    "route_requirements": """
        SELECT * FROM route_requirements
        ORDER BY caller, handler, method, path, catalog_id, kind, name, value, requirement,
                 resolution, evidence
    """,
    # Spec 2026-09-21 §3b. The channel edge — `fed_by`/`read_by`/`sends_to` rows several
    # engines write — read once per resolve by the join pass and once by `config_join.gaps`.
    # Ordered on the whole row for the reason the two above are: one channel may be read
    # by several handlers and fed by several adapters, so nothing shorter is total.
    "channel_bindings": """
        SELECT * FROM channel_bindings
        ORDER BY channel, role, symbol, protocol, direction, destination, catalog_id,
                 resolution
    """,
    "method_resolution": ("SELECT * FROM method_resolution ORDER BY class, name, descriptor"),
    "call_edges": """
        SELECT caller, ordinal, invoke_kind, target, callee, result, resolution, evidence,
               terminal_kind, target_kind
        FROM call_edges ORDER BY caller, ordinal, target, callee
    """,
    # Spec 2026-10-22-boundary-vocabulary-and-diff §5 (FR-24): the six in-process questions
    # `application/query/questions.py` answers, each ONE read (GUIDELINES §8.7) and the walk
    # behind `impact` one read per hop of its frontier, never one per symbol it reaches.
    #
    # A symbol is placed by its declaring document's path and the line extent its fact
    # gives. A line of 0 is the class file stating none — always so for a type or a field —
    # and comes back NULL, the export index's own rule (`located_symbols` above).
    #
    # `type_hierarchy` and a signature name a type BARE (D00 §5a) while `symbols`,
    # `call_edges.caller` and `.callee` carry the module coordinates, so the caller hands a
    # type over bare and a hierarchy row joins `symbols` on the symbol's last
    # space-separated token, as `boundary_shape_documents` does. Every answer is ordered on
    # the symbol, then the file, so a symbol two documents declare is two rows in a fixed
    # order (NFR-1).
    "question_source": """
        SELECT s.symbol AS symbol, d.relative_path AS file,
               nullif(s.line_start, 0) AS line_start, nullif(s.line_end, 0) AS line_end
        FROM symbols s JOIN documents d ON d.document_id = s.document_id
        WHERE s.symbol = ?
        ORDER BY symbol, file
    """,
    # One hop each way. A call that left the workspace has no callee — no body was read —
    # and is not a symbol, so `question_callees` leaves it out.
    "question_callers": """
        SELECT DISTINCT e.caller AS symbol, d.relative_path AS file,
               nullif(s.line_start, 0) AS line_start, nullif(s.line_end, 0) AS line_end
        FROM call_edges e
        LEFT JOIN symbols s ON s.symbol = e.caller
        LEFT JOIN documents d ON d.document_id = s.document_id
        WHERE e.callee = ?
        ORDER BY symbol, file
    """,
    "question_callees": """
        SELECT DISTINCT e.callee AS symbol, d.relative_path AS file,
               nullif(s.line_start, 0) AS line_start, nullif(s.line_end, 0) AS line_end
        FROM call_edges e
        LEFT JOIN symbols s ON s.symbol = e.callee
        LEFT JOIN documents d ON d.document_id = s.document_id
        WHERE e.caller = ? AND e.callee IS NOT NULL
        ORDER BY symbol, file
    """,
    # The direct subtypes of a BARE type — a class's superclass and every interface it
    # declares are each a row, so this is "implements or extends".
    "question_implementations": """
        SELECT DISTINCT coalesce(s.symbol, t.child) AS symbol, d.relative_path AS file,
               nullif(s.line_start, 0) AS line_start, nullif(s.line_end, 0) AS line_end
        FROM type_hierarchy t
        LEFT JOIN symbols s ON regexp_extract(s.symbol, '[^ ]+$') = t.child
        LEFT JOIN documents d ON d.document_id = s.document_id
        WHERE t.ancestor = ?
        ORDER BY symbol, file
    """,
    # What references a BARE type: a member whose signature names it as a parameter's type
    # or as what it returns (a field's own type is its `returns`), at ANY depth of type
    # arguments — `List<Money>` and `Map<String, Money>` both name `Money` — and a direct
    # subtype.
    #
    # **The signature rows are CANDIDATES, confirmed by the caller.** A recursive walk of
    # the JSON in SQL needs `json_tree`, which the dependency floor (`duckdb>=1.1`) does
    # not have, so this read selects every member whose signature TEXT contains the bare
    # type — which a true match always does, the descriptor being written verbatim in the
    # JSON — and hands the text over; `application/query/questions.py` walks the parsed
    # signature and drops a row that merely contains it (`com/a/Money#` inside
    # `com/b/com/a/Money#`, or inside an annotation's arguments). `kind` says which arm a
    # row came from: `signature` rows are to be confirmed, `subtype` rows are answers.
    "question_uses": """
        WITH subject AS (SELECT ?::VARCHAR AS type),
        users AS (
            SELECT 'signature' AS kind, s.symbol AS symbol, s.signature::VARCHAR AS signature
            FROM symbols s JOIN subject ON contains(s.signature::VARCHAR, subject.type)
            UNION
            SELECT 'subtype' AS kind, coalesce(s.symbol, t.child) AS symbol, NULL AS signature
            FROM type_hierarchy t
            JOIN subject ON t.ancestor = subject.type
            LEFT JOIN symbols s ON regexp_extract(s.symbol, '[^ ]+$') = t.child
        )
        SELECT DISTINCT u.kind AS kind, u.symbol AS symbol, u.signature AS signature,
               d.relative_path AS file,
               nullif(s.line_start, 0) AS line_start, nullif(s.line_end, 0) AS line_end
        FROM users u
        LEFT JOIN symbols s ON s.symbol = u.symbol
        LEFT JOIN documents d ON d.document_id = s.document_id
        ORDER BY symbol, file, kind
    """,
    # A type's own members — what `impact` of a type seeds its walk with beside the type,
    # because a change to the type is a change to what its members' callers depend on.
    "question_members": """
        SELECT symbol FROM symbols WHERE enclosing = ? ORDER BY symbol
    """,
    # One hop of `impact`'s upstream walk, for the WHOLE frontier at once: `walked` is a
    # list of `{symbol, bare, owner}` (the caller splits the symbol, through the one seam
    # that knows its grammar), and every row names the walked symbol it came from.
    #
    #   caller      a call edge whose callee is the walked symbol, with its resolution
    #   signature   a CANDIDATE member whose signature text contains the walked type, with
    #               that text, for the caller to confirm (`question_uses` says why)
    #   use         a direct subtype of the walked type
    #   unread      a call edge whose target names the walked symbol and whose callee is
    #               NULL — the callee's body was not read, so whether the call dispatches
    #               to the walked symbol is unconfirmed
    #   unscanned   a DIRECT ancestor of the walked symbol's own type (or of the type
    #               itself) that this workspace never read, through which code it holds no
    #               body for may call in (`type_hierarchy` rows are direct only)
    #
    # The last two are where the walk cannot see, and the caller lists them rather than
    # walking them.
    "question_impact_step": """
        WITH walked AS (
            SELECT w.symbol AS symbol, w.bare AS bare, w.owner AS owner
            FROM (
                SELECT unnest(?::STRUCT(symbol VARCHAR, bare VARCHAR, owner VARCHAR)[]) AS w
            )
        ),
        reached AS (
            SELECT 'caller' AS arm, w.symbol AS walked, e.caller AS symbol,
                   e.resolution AS resolution, NULL AS signature
            FROM call_edges e JOIN walked w ON e.callee = w.symbol
            UNION ALL
            -- Only a walked TYPE is looked for in signature text (a type's bare descriptor
            -- is its own owner): a member's descriptor is no type a signature names, and
            -- containment is the one join here that is not an equality.
            SELECT 'signature', w.symbol, s.symbol, 'resolved', s.signature::VARCHAR
            FROM symbols s JOIN walked w
              ON w.bare = w.owner AND contains(s.signature::VARCHAR, w.bare)
            UNION ALL
            SELECT 'use', w.symbol, coalesce(s.symbol, t.child), 'resolved', NULL
            FROM type_hierarchy t
            JOIN walked w ON t.ancestor = w.bare
            LEFT JOIN symbols s ON regexp_extract(s.symbol, '[^ ]+$') = t.child
            UNION ALL
            SELECT 'unread', w.symbol, e.caller, e.resolution, NULL
            FROM call_edges e JOIN walked w ON e.target = w.bare
            WHERE e.callee IS NULL
            UNION ALL
            SELECT 'unscanned', w.symbol, t.ancestor, NULL, NULL
            FROM type_hierarchy t JOIN walked w ON t.child = w.owner
            WHERE NOT t.scanned
        )
        SELECT DISTINCT r.arm AS arm, r.walked AS walked, r.symbol AS symbol,
               r.resolution AS resolution, r.signature AS signature, d.relative_path AS file,
               nullif(s.line_start, 0) AS line_start, nullif(s.line_end, 0) AS line_end
        FROM reached r
        LEFT JOIN symbols s ON s.symbol = r.symbol
        LEFT JOIN documents d ON d.document_id = s.document_id
        ORDER BY arm, walked, symbol, resolution, file
    """,
    # A cheap read of what `analyze` already loaded — for `render`, which
    # queries the workspace instead of reloading fact files from disk.
    "facts": "SELECT count(*) AS facts FROM raw_facts",
    # Which documents survived multi-release selection (W3c). Its own named
    # query so the export and any reader ask the same question, ordered so the
    # answer is stable between runs (NFR-1).
    "selected_documents": "SELECT * FROM selected_documents ORDER BY document_id",
    # D00 §5's `constant` (W4), which had no producer until `ConstantValue` was
    # read. Ordered on the symbol, which is unique per field.
    "constants": "SELECT * FROM constants ORDER BY symbol",
    # Spec 2026-09-22 §1a's five value edges, normalised out of `call_sites`,
    # `return_flows` and `call_edges`. The ONE named query whose text is read
    # from a file rather than written here, and the file's header says why: five
    # arms, each naming the fact and the projection behind it, would read badly
    # wedged between one-line neighbours.
    #
    # **Read, never executed as DDL.** §3b refuses a materialised copy of rows
    # three tables already hold, and a `CREATE VIEW` is still an object in the
    # catalog — `schema_objects()` finds it, the export ratchet below quite
    # correctly demands a query for it, and every bundle then carries a derived
    # copy beside the three tables it derives from. Measured while it was a
    # view: 420 KB on `mall-admin`, the second-largest file in the bundle.
    # Schema growth is one of the costs §3b names, so there is no database
    # object at all; `query("value_edges")` runs this text against the three
    # tables as they stand.
    #
    # **Nothing calls it yet, deliberately.** The walk that reads it is the next
    # task and the measurement that gates the walk is the one after; an engine
    # reading a value edge before that measurement lands is exactly what §3a
    # forbids ("Build the edge view and the walk. No engine calls it.").
    #
    # Its ordering is the file's last statement, over the whole union and on
    # every column (NFR-1) — stated there, beside the arms whose ties it breaks.
    "value_edges": (_SQL_DIR / "value_edges.sql").read_text(encoding="utf-8"),
    # D01's system scope. The two native tables, ordered for NFR-1 exactly as every
    # other query here is: a tie left to insert order is not an ordering.
    "participants": "SELECT * FROM participants ORDER BY name, module_id",
    "links": (
        "SELECT * FROM links ORDER BY from_participant, from_protocol, from_method, "
        "from_path, from_caller, to_participant, to_method, to_path"
    ),
    # Every participant's endpoints, through the federated view `federate` builds — one
    # view over the module workspaces, never a copy (D01, amended 2026-10-19). Reading it
    # before `federate` has run raises, which is the honest failure: a system query over
    # no participants would otherwise answer "no endpoints" and mean "no participants".
    "system_endpoints": (
        "SELECT * FROM system_endpoints "
        "ORDER BY participant, protocol, method, path, handler, caller"
    ),
    # The same, for the configuration a comparison resolves values from. Filtered to one
    # environment by the caller (`M06` step 0, user decision 7): never a fall back to
    # another environment's value, so the filter is the query's own parameter.
    "system_config": (
        "SELECT * FROM system_config WHERE environment = ? ORDER BY participant, key"
    ),
    # Every participant's `endpoint_conditions`, federated as `system_endpoints` is: the
    # conditions an inbound endpoint carries, which a link to it states beside itself.
    "system_endpoint_conditions": (
        "SELECT * FROM system_endpoint_conditions "
        "ORDER BY participant, protocol, direction, method, path, handler, caller, via, bean, "
        "kind, expression, environment"
    ),
    # Every participant's `bean_presence`, federated the same way: where the bean behind a
    # link's endpoint (either end of it) EXISTS — the one answer, OR across the bean's routes.
    "system_bean_presence": (
        "SELECT * FROM system_bean_presence ORDER BY participant, bean, environment"
    ),
}

# What the export PROJECTION masks (2K design §1), each named where its own
# query below says why. THREE MAPS, one per rule, because the rule is the thing
# that must not be duplicated — not the column:
#
#   addresses    `endpoints.path`/`.peer`, `open_questions.path`, `roots.path`,
#                `endpoint_conditions.path`
#   the grammar  `call_sites.arguments`, `annotations.args`,
#                `return_flows.value`, `method_returns.value`,
#                `bean_conditions.expression` (and the view repeating it)
#   evidence     `bean_conditions.evidence`, `bean_presence.evidence` and the
#                views repeating them — free text quoting the grammar
#   config       `resolved_config.value`, `config_entries.value`, and
#                `config_entry` fact payloads (`_stage_fact_redactions`, joined
#                by BOTH the `facts/*.parquet` stream and `graph/raw_facts`)
#
# A column joins the map its VALUE belongs to, never one chosen per table:
# `roots.path` is carried column-for-column from the endpoint that named the
# handler, so a root masked by a different map would name a different thing;
# and all four grammar columns are built from the same string constants read
# out of bytecode, so a hardcoded `https://user:pass@host` reaches a bundle
# through any of them.
# The masking is here and only here: the workspace itself keeps verbatim values,
# because analysis needs them — peer resolution substitutes real addresses —
# and the user's own disk is not the trust boundary. The bundle is.
#
# The mechanism is a LEFT JOIN against a staged substitution table, not a
# scalar function: DuckDB's Python UDFs require numpy, which is not a
# dependency here, and restating the redactor's rules as SQL would be a second
# copy of `domain/redaction.py` drifting beside the first. `_stage_redactions`
# computes the masked strings in Python, through the one redactor, and stages
# only the ones that actually change; `coalesce` leaves every other value
# exactly as the table holds it, byte for byte.
_REDACTED_CONFIG_VALUES = "redacted_config_values"
_REDACTED_ADDRESSES = "redacted_addresses"
_REDACTED_JSON = "redacted_json"
_REDACTED_PAYLOADS = "redacted_payloads"
# Free text that QUOTES the grammar — a condition's `evidence`, which repeats its expression
# (`bean_presence`'s "the configured value is unknown here: …") or a placeholder's raw
# spelling — masked by `redact_text`, since it is not a JSON document `redact_json` can walk.
_REDACTED_EVIDENCE = "redacted_evidence"
# `config_entries` is the RAW half of what `resolved_config` holds resolved —
# the same values, before the resolver joined them — so it masks by the same
# rule through the same `Redactor.redact_value`, keyed on the entry's own
# `key_path` exactly as `redact_config_entry_line` keys it. Its own map rather
# than `_REDACTED_CONFIG_VALUES` because the two are keyed on different key
# spellings: a raw entry's `key_path` and a resolved row's `key` are not
# always the same string, and a join across them would silently miss.
_REDACTED_ENTRY_VALUES = "redacted_entry_values"
# The first of two temp tables a DERIVATION stages (P-4): every annotation-driven
# catalog's candidate endpoint rows, written by `derive_endpoints.sql` once per
# resolve and read by `insert_endpoints.sql` once per catalog. Temp for the
# reason the redaction maps are: it is working state of one resolve, never
# part of the schema and never in a bundle — every row it holds that survives
# its catalog's turn is in `endpoints`, and every row that does not was
# refused by the earlier-catalog-wins rule.
_ENDPOINT_CANDIDATES = "endpoint_candidates"
# The second (spec 2026-09-19 §4d/§5a): the combinator's per-route requirements,
# written by `route_requirements_insert` per engine run and read once by the
# requirements pass after every row's protocol is final. Temp for the same
# reason — every row it holds that names a live route is in `endpoint_metadata`
# by the end of the resolve, and every row that does not named a route the
# engine refused.
_ROUTE_REQUIREMENTS = "route_requirements"
# The third (spec 2026-09-21 §3b): the channel edge, written by every engine that learns
# one end of a named channel and joined once per resolve by `resolve/channel_bindings.py`.
# Temp for the same reason — every edge that reaches a wire is in `endpoints` by the end
# of the resolve, and every one that does not is a `channel_destination` question.
_CHANNEL_BINDINGS = "channel_bindings"

# One query per table and view IN THE SCHEMA — all of them, with no exclusion
# class. The ratchet runs the direction that catches the defect: an object in
# `schema.sql` with no query here is a TEST FAILURE
# (`tests/storage/test_workspace.py`), not a quiet omission.
#
# It used to be eleven hand-listed names, and the SEVEN they omitted —
# `raw_facts`, `call_edges` (1,393 rows on `mall-admin`), `return_flows` (444),
# `roots` (79), and the three views `config_entries`, `field_writes` and
# `method_returns` — were dropped from every bundle with nothing saying so. A
# consumer could read a rendered trace and had no way to recompute or check
# what it asserted. Ruled by the user: **nothing is dropped on export.**
# Parquet, DuckDB and the indices exist so an agent or a program can query
# fast, and making a consumer re-derive what we already hold is the friction
# the format removes.
#
# `_EXPORTED_TABLES` is DERIVED from this dict rather than restated beside it,
# so adding a table asks its author exactly two questions and neither can be
# skipped: *does it export?* — write the query or the ratchet fails — and *does
# analysis read its values?* — yes keeps the real value and redacts here, no
# redacts at the origin instead (§6.2). There is no third answer to either.
_EXPORT_QUERIES = {
    "documents": _NAMED_QUERIES["documents"],
    # `path` and `peer` are the columns that can carry a whole address (D01
    # §3, 2I's unsplit-expression ruling), so they carry URL userinfo too.
    # Ordered on the table's own columns — `e.path`, not the projected alias —
    # so masking a row cannot reorder the file (NFR-1).
    "endpoints": f"""
        SELECT e.* REPLACE (coalesce(p.masked, e.path) AS path,
                            coalesce(q.masked, e.peer) AS peer)
        FROM endpoints e
        LEFT JOIN {_REDACTED_ADDRESSES} p ON p.address = e.path
        LEFT JOIN {_REDACTED_ADDRESSES} q ON q.address = e.peer
        ORDER BY e.protocol, e.method, e.path, e.handler, e.caller
    """,
    # The ledger carries the SAME `path` an endpoint row does — it is keyed on
    # a wire identity — so it masks by the same map. Render and export must
    # agree about one address: a question rendered against a stripped address
    # and exported against a bare one names two different rows.
    "open_questions": f"""
        SELECT o.protocol, o.method, coalesce(a.masked, o.path) AS path, o.question,
               o.candidates, o.evidence
        FROM open_questions o
        LEFT JOIN {_REDACTED_ADDRESSES} a ON a.address = o.path
        ORDER BY o.protocol, o.method, o.path, o.question, o.candidates::VARCHAR, o.evidence
    """,
    # The live exposure 2K closes: this table's `value` column exported
    # verbatim. Joined on (key, value) rather than key alone because one key
    # resolves to different values in different environments, and the mask a
    # key pattern produces is the same either way only by coincidence — a
    # value pattern's is not.
    "resolved_config": f"""
        SELECT c.key, coalesce(m.masked, c.value) AS value, c.source, c.environment,
               c.unresolved_reason
        FROM resolved_config c
        LEFT JOIN {_REDACTED_CONFIG_VALUES} m ON m.key = c.key AND m.value = c.value
        ORDER BY c.environment, c.key
    """,
    "shapes": _NAMED_QUERIES["shapes"],
    "shape_fields": _NAMED_QUERIES["shape_fields"],
    # The two non-wire tables export through their named query verbatim, and
    # the reason is that NEITHER carries a masked column. `_REDACTED_ADDRESSES`
    # exists for the columns that can hold a whole URL — `endpoints.path`/
    # `.peer` and the ledger's `path` — and neither of these tables has one: a
    # trigger expression is a cron string or a delay, a scope attribute is a
    # package or a type, and a status is a status. `_REDACTED_CONFIG_VALUES`
    # keys on `resolved_config`'s own (key, value) pairs, which nothing here
    # holds either. Stated rather than left to inference, because "this table
    # is exported unmasked" is the claim a reviewer has to be able to check.
    "scheduled_work": _NAMED_QUERIES["scheduled_work"],
    "error_handlers": _NAMED_QUERIES["error_handlers"],
    # `arguments` and `args` carry JSON the analysis read out of code, and a
    # hardcoded `https://user:pass@host` literal lands in one whole. They pass
    # `redact_json` — userinfo stripping over every string leaf — and NOT the
    # key-based rule: a call argument is not a configuration key, and the path
    # and URL literals in one ARE the wire identities the linking tier matches
    # services on (2K Task 1 review, ruled). Joined on the column's own
    # canonical JSON text, which is what `_stage_redactions` staged.
    "call_sites": f"""
        SELECT c.* REPLACE (coalesce(j.masked::JSON, c.arguments) AS arguments)
        FROM call_sites c
        LEFT JOIN {_REDACTED_JSON} j ON j.original = c.arguments::VARCHAR
        ORDER BY c.caller, c.ordinal
    """,
    "symbols": "SELECT * FROM symbols ORDER BY symbol",
    "annotations": f"""
        SELECT a.target, a.annotation, coalesce(j.masked::JSON, a.args) AS args,
               a.type_path, a.retention
        FROM annotations a
        LEFT JOIN {_REDACTED_JSON} j ON j.original = a.args::VARCHAR
        ORDER BY a.target, a.annotation, a.type_path, a.args
    """,
    # ---- The six a bundle used to drop, plus the fact table itself (C10) ----
    #
    # The fact stream ALSO travels as `facts/<document_id>.parquet`, one file
    # per document, which is the shape a reader wanting ONE document's facts
    # needs. This is the other shape: the whole table, queryable in a single
    # scan beside the derived tables it explains. Same rows, same mask, same
    # `_REDACTED_PAYLOADS` map — `export_facts` and this cannot disagree,
    # because there is one map and one redactor behind both.
    #
    # `rowid` is the order the facts were loaded in, which is the order the
    # fact files declare them in (D00 §7) — the same ordering `export_facts`
    # already ships on, reused rather than invented.
    "raw_facts": f"""
        SELECT f.kind, f.document_id, coalesce(m.masked::JSON, f.payload) AS payload
        FROM raw_facts f
        LEFT JOIN {_REDACTED_PAYLOADS} m ON m.original = f.payload::VARCHAR
        ORDER BY f.rowid
    """,
    # Carries a whole address in `path` — copied column-for-column from the
    # `endpoints` row that named the handler — so it masks through the SAME
    # address map those columns and `open_questions.path` use. A root masked
    # differently from the endpoint it was carried from would name two
    # different things.
    #
    # Ordering is the named query's, which is total where `handler` alone is
    # not: one method can be both a request target and a clock target, and one
    # handler can serve three addresses.
    # F8 §9.4 (W37). The alternate orderings. Their masking is their base table's, applied
    # again here rather than referenced: `roots.path` is an address, and a second file of
    # the same rows that skipped the mask would be the leak the index bundle just had.
    "call_edges_by_callee": (
        "SELECT * FROM call_edges_by_callee ORDER BY callee, caller, ordinal, target"
    ),
    "roots_by_address": f"""
        SELECT r.handler, r.root_kind, r.protocol, r.method,
               coalesce(a.masked, r.path) AS path
        FROM roots_by_address r
        LEFT JOIN {_REDACTED_ADDRESSES} a ON a.address = r.path
        ORDER BY r.protocol, r.method, r.path, r.handler, r.root_kind
    """,
    # F8 §9.4 (W37). No masked column: every value is a symbol, an integer or a boolean.
    # The ROOT here is a handler, not an address — `roots` carries the address, and this
    # table joins to it on the handler rather than repeating a column the redactor would
    # then have to reach in two places.
    "reachability": _NAMED_QUERIES["reachability"],
    "roots": f"""
        SELECT r.handler, r.root_kind, r.protocol, r.method,
               coalesce(a.masked, r.path) AS path
        FROM roots r
        LEFT JOIN {_REDACTED_ADDRESSES} a ON a.address = r.path
        ORDER BY r.handler, r.root_kind, r.protocol, r.method, r.path
    """,
    # Spec 2026-09-22 §3d/§7a's shadow review list, and its `value` column is masked by
    # the ADDRESS map rather than by the grammar one. That is the map's own rule applied
    # rather than a choice per table: a `would_resolve` row carries the string an engine
    # WOULD publish as `endpoints.path`, so it is the same value the address map already
    # masks one table along, and masking it by a different rule would spell one address
    # two ways in one bundle. `value_resolutions.value` is staged INTO that map beside
    # the four address columns (`_stage_redactions`), for the reason the map's own
    # comment gives about `roots.path`: a map built from the columns that existed when it
    # was written leaves any later address unmasked with nothing saying so.
    #
    # Empty in every ordinary bundle — the table is filled only by `--shadow` — and
    # exported anyway, because there is no exclusion class (the ratchet above), and
    # because a shadow bundle is exactly the artefact a reviewer would hand to someone
    # else to read.
    "value_resolutions": f"""
        SELECT v.catalog, v.caller, v.ordinal, v.slot, v.path, v.outcome,
               v.answer_kind, v.literal_kind, coalesce(m.masked, v.value) AS value, v.reason
        FROM value_resolutions v
        LEFT JOIN {_REDACTED_ADDRESSES} m ON m.address = v.value
        ORDER BY v.catalog, v.caller, v.ordinal, v.slot, v.path
    """,
    # No masked column, and stated rather than left to inference (the
    # `scheduled_work`/`error_handlers` precedent above): every column here is
    # a symbol, a descriptor, a dispatch form, an integer or a closed-set
    # value. There is nowhere in it for an address, a config value or a string
    # constant out of bytecode to be.
    "call_edges": _NAMED_QUERIES["call_edges"],
    # F3 §4.2. Both carry only symbols, a closed-set value and an integer — no address,
    # config value or bytecode string — so redaction has nothing to reach here, the same
    # reason `call_edges` above is exported whole. W34's ratchet requires them: a table
    # in the schema and absent from the export is a test failure.
    "type_hierarchy": ("SELECT * FROM type_hierarchy ORDER BY child, position, ancestor"),
    # F5 §6.2 (W29): exported WHOLE and unmasked here, which is the one place that reads
    # differently from every other value column in this map. `value` was already redacted
    # by the pass that wrote it — nothing in this system reads a metadata value, so there
    # is no analysis to break by masking early and no second chance to forget. A mask
    # applied here as well would be the redactor run twice over its own output.
    "endpoint_metadata": _NAMED_QUERIES["endpoint_metadata"],
    # Structured for a machine (ruling 1, 2026-10-22): the conditions rows go out as they
    # are, the document being the one verbose rendering of them — the bean's own rows and the
    # view every endpoint row reads them through (spec 2026-10-22-conditional-beans), the
    # symbol-to-bean rule both views use, and the per-environment candidates of every narrowed
    # call site a trace block states. Three of their columns reach a value redaction exists
    # for, and each is masked by the map its value belongs to. `endpoint_conditions.path` is
    # the endpoint row's own `path` — an outbound row's address, URL userinfo and all — so it
    # masks by the address map `endpoints.path` uses. `expression` quotes a condition's
    # annotation arguments verbatim (a `havingValue` is a string out of bytecode), so it takes
    # the `redact_json` pass `annotations.args` takes. `evidence` is free text quoting that
    # expression, or the raw spelling of a placeholder in the configuration, so it takes
    # `redact_text` — the same strip, over text that is not a JSON document
    # (`_REDACTED_EVIDENCE`). `symbol_beans` and `interface_beans` hold symbols only.
    "endpoint_conditions": f"""
        SELECT c.* REPLACE (coalesce(a.masked, c.path) AS path,
                            coalesce(j.masked, c.expression) AS expression,
                            coalesce(t.masked, c.evidence) AS evidence)
        FROM ({_NAMED_QUERIES["endpoint_conditions"]}) c
        LEFT JOIN {_REDACTED_ADDRESSES} a ON a.address = c.path
        LEFT JOIN {_REDACTED_JSON} j ON j.original = c.expression
        LEFT JOIN {_REDACTED_EVIDENCE} t ON t.original = c.evidence
        ORDER BY c.protocol, c.direction, c.method, c.path, c.handler, c.kind, c.expression,
                 c.environment, c.caller, c.via, c.bean_kind, c.bean
    """,
    "bean_conditions": f"""
        SELECT b.* REPLACE (coalesce(j.masked, b.expression) AS expression,
                            coalesce(t.masked, b.evidence) AS evidence)
        FROM ({_NAMED_QUERIES["bean_conditions"]}) b
        LEFT JOIN {_REDACTED_JSON} j ON j.original = b.expression
        LEFT JOIN {_REDACTED_EVIDENCE} t ON t.original = b.evidence
        ORDER BY b.bean, b.bean_kind, b.via, b.kind, b.expression, b.environment, b.holds,
                 b.resolution, b.evidence
    """,
    "bean_presence": f"""
        SELECT p.* REPLACE (coalesce(t.masked, p.evidence) AS evidence)
        FROM ({_NAMED_QUERIES["bean_presence"]}) p
        LEFT JOIN {_REDACTED_EVIDENCE} t ON t.original = p.evidence
        ORDER BY p.bean, p.environment
    """,
    "symbol_beans": _NAMED_QUERIES["symbol_beans"],
    "candidate_presence": f"""
        SELECT p.* REPLACE (coalesce(t.masked, p.evidence) AS evidence)
        FROM ({_NAMED_QUERIES["candidate_presence"]}) p
        LEFT JOIN {_REDACTED_EVIDENCE} t ON t.original = p.evidence
        ORDER BY p.caller, p.ordinal, p.callee NULLS LAST, p.bean, p.environment
    """,
    "interface_beans": _NAMED_QUERIES["interface_beans"],
    "method_resolution": ("SELECT * FROM method_resolution ORDER BY class, name, descriptor"),
    # `value` is an entry of the ARGUMENT grammar — the constant a field was written from —
    # so it takes the same `redact_json` pass `constants.value` and `call_sites.arguments`
    # take, by the same join. Exporting it clear while `raw_facts` ships the same literal
    # masked would put both spellings in one bundle, which is what review caught here:
    # `private String endpoint = "https://alice:s3cr3t@internal.example.com/orders"` reached
    # `field_writes.parquet` in the clear while `raw_facts.parquet` carried it masked.
    "field_writes": f"""
        SELECT w.document_id, w.field, w.from_parameter,
               coalesce(j.masked::JSON, w.value) AS value, w.written_by
        FROM field_writes w
        LEFT JOIN {_REDACTED_JSON} j ON j.original = w.value::VARCHAR
        ORDER BY w.document_id, w.field, w.from_parameter NULLS LAST, w.value::VARCHAR,
                 w.written_by
    """,
    # Worth carrying rather than recomputable: without it a consumer sees the
    # tagged copies in `documents` and cannot tell which one the derived rows
    # were built from.
    "selected_documents": _NAMED_QUERIES["selected_documents"],
    # A constant IS a string read out of bytecode, which is the exact
    # population `_REDACTED_JSON`'s userinfo rule exists for — the same rule
    # `call_sites.arguments` takes. Exporting it clear while `raw_facts` ships
    # the same literal masked would put both spellings in one bundle.
    "constants": f"""
        SELECT c.document_id, c.symbol, coalesce(j.masked::JSON, c.value) AS value
        FROM constants c
        LEFT JOIN {_REDACTED_JSON} j ON j.original = c.value::VARCHAR
        ORDER BY c.symbol
    """,
    # `value` is an entry of the ARGUMENT grammar — the same JSON shape
    # `call_sites.arguments` carries, produced from the same string constants
    # in bytecode — so it takes the same `redact_json` pass, over userinfo in
    # every string leaf. Its rows are staged alongside the call-site and
    # annotation JSON in `_stage_redactions`, one map for one grammar.
    "return_flows": f"""
        SELECT rf.caller, rf.ordinal, rf.result, rf.callee, rf.return_ordinal,
               coalesce(j.masked::JSON, rf.value) AS value, rf.resolution, rf.evidence
        FROM return_flows rf
        LEFT JOIN {_REDACTED_JSON} j ON j.original = rf.value::VARCHAR
        ORDER BY rf.caller, rf.ordinal, rf.callee, rf.return_ordinal
    """,
    "method_returns": f"""
        SELECT mr.document_id, mr.method, mr.ordinal,
               coalesce(j.masked::JSON, mr.value) AS value
        FROM method_returns mr
        LEFT JOIN {_REDACTED_JSON} j ON j.original = mr.value::VARCHAR
        ORDER BY mr.document_id, mr.method, mr.ordinal
    """,
    # The raw half of `resolved_config` — a configuration value as the file
    # declared it, before the resolver joined profiles and placeholders. It is
    # therefore exactly as disclosing as the resolved column beside it, and
    # exporting it in the clear beside a masked `resolved_config` would mask
    # nothing at all.
    "config_entries": f"""
        SELECT c.document_id, c.key_raw, c.key_path,
               coalesce(m.masked, c.value) AS value, c.doc_index, c.seq
        FROM config_entries c
        LEFT JOIN {_REDACTED_ENTRY_VALUES} m
               ON m.key_path = c.key_path AND m.value = c.value
        ORDER BY c.document_id, c.doc_index, c.seq
    """,
}

# Derived, never restated (see the note above `_EXPORT_QUERIES`): the exported
# list IS the set of queries, so the two cannot fall out of step. Sorted, so
# the manifest's `contents.tables` is deterministic too.
_EXPORTED_TABLES = tuple(sorted(_EXPORT_QUERIES))

# The named queries whose answer depends on the loaded facts and nothing else: each
# reads only `raw_facts` and the fact views (`_FACT_VIEWS`), and no derivation writes
# any of those — `load_facts` is their one writer, which is why `query` can hand back
# the rows it already read (`_fact_reads`) until the next load. Measured on
# `mall-admin` before this existed: the resolve read `method_declarations` 59 times
# (22,059 rows each, 1.3 million rows built into dicts), `call_sites` 39 times,
# `declared_symbols_with_documents` 74 times — 11.8s of the 53.7s analyze, for rows
# that could not have changed between one read and the next. A query that reads a
# DERIVED table (`endpoints`, `shapes`, `call_edges`, `resolved_config`, ...) is not
# here and is never cached: the passes that write those tables run between the reads.
#
# Rows served from the cache are the SAME list and dict objects every time, so a
# caller reads them and never writes into them — the one discipline this asks, and
# `tests/storage/test_workspace.py` pins the cache, its invalidation, and that a
# derived-table query stays uncached. The cache is per instance: a second
# `DuckDbWorkspace` opened on the same file would not see this one's `load_facts`.
# No caller opens two — `analyze` owns one workspace per module and `render`/`export`
# reopen it only after `analyze` has closed — and two open handles writing one
# DuckDB file would be a conflict the database refuses before the cache mattered.
_FACT_ONLY = frozenset(
    {
        "documents",
        # The class-level annotations of header-read dependency types (D00 §5
        # `type_header`): a read over `raw_facts` alone, so cached per load like every
        # other fact query — the cache rule test is what said so.
        "type_header_annotations",
        # A `DefaultImpls` holder and its bodies are facts, read once per resolve like
        # every other declaration (the merge of the delivery branch added the query).
        "default_bodies",
        # A default-argument bridge's own fact, read once per resolve by the call-site
        # projection (spec 2026-09-19 §3a).
        "bridge_declarations",
        # A class-compiled lambda's type fact, read once per resolve by the same
        # projection (spec 2026-09-19 §3b).
        "lambda_bodies",
        "fields",
        "enum_types",
        "annotations_of",
        "annotations",
        "call_sites",
        "field_writes",
        "method_returns",
        "supertypes",
        "implementations",
        "superclasses",
        "method_visibility",
        "declared_shapes",
        "method_symbols",
        "interface_symbols",
        "method_declarations",
        "accessor_declarations",
        "constructor_declarations",
        "declared_symbols",
        "nest_hosts",
        "interface_declarations",
        "module_dependencies",
        "coverage",
        "config_entries",
        "library_symbols",
        "declared_symbols_with_documents",
        "located_documents",
        "located_annotations",
        "located_symbols",
        "type_parameters",
        "facts",
        "selected_documents",
        "constants",
        "question_source",
        "question_members",
    }
)

# JSON columns a named query hands over DECODED — Python objects, not the JSON text
# DuckDB returns for a JSON column — decoded once, when the rows are first read, and
# shared through `_fact_reads` from then on. Only where a measurement puts the parse
# above everything else: `method_declarations`' two columns were parsed by every
# annotation-driven catalog in turn — 2.6 million `json.loads` calls on `mall-admin`,
# the profiler's single largest row, for 22,059 rows whose text never changed — and
# `call_sites.arguments` was the next million, every call-reading engine decoding all
# 24,815 sites for itself. Every other JSON column stays text, exactly as its readers
# expect it; a query joins this map when a profile says its parse is the cost, and its
# readers stop decoding it the same day. The decoded objects are shared like the rows:
# read, never written into.
_DECODED_COLUMNS = {
    "method_declarations": ("signature", "modifiers"),
    "call_sites": ("arguments",),
}

_NAMED_DERIVATIONS = {
    # P-4: `endpoints` derives EVERY annotation-driven catalog's candidate rows
    # in one execution, into the temp table `endpoint_candidates`, which
    # `endpoints_insert` then reads one catalog at a time — the statement's
    # cost is its size at bind time, so it runs once per resolve where it ran
    # once per catalog.
    "endpoints": "derive_endpoints.sql",
    "endpoints_insert": "insert_endpoints.sql",
    "call_endpoints": "derive_call_endpoints.sql",
    "endpoints_reset": "reset_endpoints.sql",
    "endpoint_contracts": "derive_endpoint_contracts.sql",
    "prefix_endpoint_paths": "prefix_endpoint_paths.sql",
    "shapes": "derive_shapes.sql",
    "shape_fields": "derive_shape_fields.sql",
    "shapes_reset": "reset_shapes.sql",
    "resolved_config_reset": "reset_resolved_config.sql",
    "resolved_config_insert": "insert_resolved_config.sql",
    "stamp_media": "stamp_media.sql",
    "stamp_declared_response": "stamp_declared_response.sql",
    "stamp_declared_request": "stamp_declared_request.sql",
    "stamp_format": "stamp_format.sql",
    "bind_request_shape": "bind_request_shape.sql",
    "reclassify_protocol": "reclassify_protocol.sql",
    "reclassify_open_questions": "reclassify_open_questions.sql",
    "open_questions_reset": "reset_open_questions.sql",
    "open_questions_insert": "insert_open_questions.sql",
    # 2O design §4's two non-wire families. Each is a reset/insert PAIR for the
    # reason `open_questions` is: the reset runs once per resolve from the
    # pipeline, the insert once per catalog from the engine.
    "scheduled_work_reset": "reset_scheduled_work.sql",
    "scheduled_work_insert": "insert_scheduled_work.sql",
    "error_handlers_reset": "reset_error_handlers.sql",
    "error_handlers_insert": "insert_error_handlers.sql",
    # 2Q `G3`. A reset/insert pair like the two above, but reset and insert
    # BOTH run from the one pass that writes here — there is exactly one
    # writer, and the pipeline-owned reset those two need exists only because
    # more than one catalog writes to them.
    "return_flows_reset": "reset_return_flows.sql",
    "return_flows_insert": "insert_return_flows.sql",
    # 2Q `I1`. A reset/insert pair owned by its one writing pass, exactly as
    # `return_flows` above is and for the same reason.
    "roots_reset": "reset_roots.sql",
    "roots_insert": "insert_roots.sql",
    # F8 §9.4 (W37): the trace walk's own reachability, kept. Reset BESIDE the insert —
    # this was the one insert in this map without one, and a second `analyze` over a
    # workspace doubled every row.
    "reachability_reset": "reset_reachability.sql",
    "reachability": "insert_reachability.sql",
    # 2Q `G4`. A reset/insert pair owned by its one writing pass, as above.
    # F4 §5.2 (W24). Runs from inside `derive_endpoints`, immediately before the merge
    # — see the statement's own header for why that ordering is load-bearing.
    "borrowed_endpoints_drop": "drop_borrowed_endpoints.sql",
    "borrowed_error_handlers_drop": "drop_borrowed_error_handlers.sql",
    "call_edges_reset": "reset_call_edges.sql",
    "call_edges_insert": "insert_call_edges.sql",
    "type_hierarchy_reset": "reset_type_hierarchy.sql",
    "type_hierarchy_insert": "insert_type_hierarchy.sql",
    "method_resolution_reset": "reset_method_resolution.sql",
    "method_resolution_insert": "insert_method_resolution.sql",
    "endpoint_metadata_reset": "reset_endpoint_metadata.sql",
    "endpoint_metadata_insert": "insert_endpoint_metadata.sql",
    "bean_conditions_reset": "reset_bean_conditions.sql",
    "bean_conditions_insert": "insert_bean_conditions.sql",
    "interface_beans_insert": "insert_interface_beans.sql",
    # D01's system scope, written by `application/stitch`. A reset/insert pair each,
    # both run once per `system analyze` — unlike the resolve tables above, where the
    # reset is the pipeline's and the insert is per catalog.
    "participants_reset": "reset_participants.sql",
    "participants_insert": "insert_participants.sql",
    "links_reset": "reset_links.sql",
    "links_insert": "insert_links.sql",
    # Spec 2026-09-19 §4d/§5a. A reset/insert pair like `endpoint_metadata`'s and
    # for the same reason: the reset runs once per resolve from `derive_endpoints`
    # (beside `endpoints_reset`, ahead of every engine), the insert once per engine run.
    "route_requirements_reset": "reset_route_requirements.sql",
    "route_requirements_insert": "insert_route_requirements.sql",
    # Spec 2026-09-21 §3b. The same pair, for the same reason: the reset runs once per
    # resolve from `derive_endpoints` beside `route_requirements_reset`, the insert once
    # per engine run that learned an end of a channel.
    "channel_bindings_reset": "reset_channel_bindings.sql",
    "channel_bindings_insert": "insert_channel_bindings.sql",
    # Spec 2026-09-22 §3d/§7a. A reset/insert pair owned by its one writing pass
    # (`resolve/shadow.py`), the `roots`/`reachability` discipline — but with the RESET
    # run on every resolve and the insert only in shadow mode, so an ordinary analysis
    # empties a table it never fills rather than leaving a previous shadow run's review
    # list behind. The file itself says why that is not merely tidy.
    "value_resolutions_reset": "reset_value_resolutions.sql",
    "value_resolutions_insert": "insert_value_resolutions.sql",
}

# The fact "tables" `schema.sql` defines as VIEWS over `raw_facts`, in dependency
# order: `documents` first, `selected_documents` reads it, and every view after
# those filters on `selected_documents`. Measured on `mall-admin` (648 documents,
# 75,614 facts), a view is re-evaluated on EVERY query — the JSON extraction and
# the selection subquery both — and `derive_endpoint_shapes` ran `annotations_of`
# 629 times at 32ms each to fetch 369 rows. Each of these is materialized into a
# `fact_<view>` table once per load (`_materialize_facts`), and the view is
# re-pointed at that table, so the named queries and the derivations stay exactly
# as written. `call_edges_by_callee` and `roots_by_address` are not here: they
# are orderings of derived tables, and read no JSON.
_FACT_VIEWS = (
    "documents",
    "selected_documents",
    "symbols",
    "annotations",
    "config_entries",
    "call_sites",
    "method_returns",
    "constants",
    "field_writes",
)
# No index on any of them, which was measured rather than assumed: with
# `annotations(target)`, `symbols(symbol)`, `symbols(enclosing)`,
# `call_sites(caller)` and `method_returns(method)` all built, no pass moved on
# either corpus (`derive_endpoint_shapes` 5.4s either way on `mall-admin`, the one
# pass with a point lookup — `annotations_of` — and it reads 369 rows across 629
# calls at 0.1s total once the table exists), and building them added 0.1s to
# every load. That holds as long as no named query or derivation looks a fact up
# by equality against a table too large to scan in the time a lookup takes.


def _fact_table(view: str) -> str:
    return f"fact_{view}"


_JSON = duckdb.sqltype("JSON")


def _bound(params: dict[str, object]) -> dict[str, object]:
    """The parameters as they are handed to DuckDB: a list, tuple or dict travels as
    ONE JSON value, everything else as itself.

    A statement's `$rows::STRUCT(...)[]` or `$names::VARCHAR[]` cast reads the same
    either way — DuckDB casts JSON to the declared type as it casts a Python list to
    it, checked value for value against the Python route (quotes, backslashes,
    non-ASCII text, NULLs, empty lists, numbers into VARCHAR) — with one case where the
    two routes answer DIFFERENTLY rather than fail: a dict or list placed in a VARCHAR
    struct field, which the Python route writes in DuckDB's own literal spelling
    (`{'k': [1, v]}`) and this route as JSON (`{"k":[1,"v"]}`). No production builder
    hands a bare dict or list to a VARCHAR field — every such value is JSON text already
    (`annotation_driven.py`'s synthetic `args` and `derived_resource.py`'s `candidates`
    are `json.dumps`'d; `return_flow.py`'s `value` is `method_returns.value` carried
    through as the text it was read as), so the column holds the same text either way. The cost is not the same. Handed a Python list, the DuckDB client converts it one element at a time and,
    for each element, tries to `import pandas` to ask whether the element is a DataFrame;
    with pandas not installed the failed import is retried every time (nothing caches
    it: `PythonImportCacheItem::LoadModule` in duckdb-python sets the item to null and
    the next call loads again), and each retry walks `sys.path`. Measured on
    `mall-admin`: `call_edges_insert` handed 24,591 rows of ten columns and spent 8.9s in
    the statement, 459,034 of those import attempts; the same rows as one JSON value take
    60ms. Across a whole analyze the named derivations went from 18.3s to 1.8s of 53.7s
    (`return_flows_insert` 3.8s to 0.1s, `method_resolution_insert` 2.7s to 0.02s). That
    holds as long as the client behaves this way with pandas absent; with pandas
    installed the per-element route is merely slow (1.5s for those rows) rather than
    pathological, and this is still the faster one.

    The value is typed `JSON` so the statement's own cast is JSON-to-type: bound as plain
    text the cast would be VARCHAR-to-type, which reads DuckDB's own literal syntax and
    mangles a backslash-u escape. The JSON-to-STRUCT cast is strict about keys — a row
    missing a column the struct declares is an error rather than a NULL — and `derive`
    says what it does about that. That strictness, `duckdb.sqltype` and `duckdb.Value`
    were checked on duckdb 1.5.5 (`uv.lock`'s pin); `pyproject.toml` admits `>=1.1`,
    and on a release whose cast is looser the retry in `derive` is what still gives the
    Python route's answer.
    """
    return {
        name: (
            duckdb.Value(json.dumps(value), _JSON)
            if isinstance(value, (list, tuple, dict))
            else value
        )
        for name, value in params.items()
    }


def _run_named(
    connection: duckdb.DuckDBPyConnection, name: str, params: dict[str, object]
) -> list[dict[str, object]]:
    cursor = connection.execute(_NAMED_QUERIES[name], list(_bound(params).values()) or None)
    columns = [column[0] for column in cursor.description]
    rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
    for column in _DECODED_COLUMNS.get(name, ()):
        for row in rows:
            text = row[column]
            row[column] = None if text is None else json.loads(str(text))
    return rows


# The tables the boundary queries read (spec 2026-10-22 §2): the ten a bundle ships as
# `graph/<name>.parquet` and a workspace holds as tables or views of the same name. The set
# the `boundary_*` queries above name and nothing else, so a read-only open creates only
# what the diff can ask for.
READ_ONLY_TABLES = (
    "documents",
    "endpoint_conditions",
    "endpoint_metadata",
    "endpoints",
    "error_handlers",
    "resolved_config",
    "scheduled_work",
    "shape_fields",
    "shapes",
    "symbols",
)


def _sql_string(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


_WORKSPACE_FILE = "workspace.duckdb"
_LOOKED_FOR = (
    "a workspace (a directory holding workspace.duckdb and metadata.json, usually "
    "<module>/.sextant) or a bundle (a directory holding manifest.json and graph/)"
)


def _json_document(directory: Path, name: str) -> dict[str, object]:
    file = directory / name
    if not file.is_file():
        raise NotABoundarySource(directory, f"{name} is missing")
    return cast(dict[str, object], json.loads(file.read_text(encoding="utf-8")))


def _block(document: dict[str, object], *path: str) -> dict[str, object]:
    for step in path:
        document = cast(dict[str, object], document.get(step) or {})
    return document


def _required(where: Path, document: dict[str, object], *path: str) -> str:
    value = _block(document, *path[:-1]).get(path[-1])
    if value is None:
        raise NotABoundarySource(where, f"its {path[0]} document names no {'.'.join(path)}")
    return str(value)


def _names(document: dict[str, object], key: str) -> list[str]:
    return [str(name) for name in cast(list[object], document.get(key, []))]


class ReadOnlyGraph:
    """A workspace or an exported bundle opened to be read and never changed, behind the
    `GraphReader` port. The named queries run on either unchanged because both are presented
    as views called what the queries call them."""

    def __init__(
        self,
        connection: duckdb.DuckDBPyConnection,
        *,
        module: dict[str, object],
        commit: str,
        producer: dict[str, object],
        environments: list[str],
        is_bundle: bool,
        module_root: Path | None,
    ) -> None:
        self._connection = connection
        self._module = module
        self._commit = commit
        self._producer = producer
        self._environments = environments
        self._is_bundle = is_bundle
        self._module_root = module_root

    @property
    def module(self) -> dict[str, object]:
        return self._module

    @property
    def commit(self) -> str:
        return self._commit

    @property
    def producer(self) -> dict[str, object]:
        return self._producer

    @property
    def environments(self) -> list[str]:
        return self._environments

    @property
    def is_bundle(self) -> bool:
        return self._is_bundle

    @property
    def module_root(self) -> Path | None:
        return self._module_root

    def query(self, name: str, **params: object) -> list[dict[str, object]]:
        return _run_named(self._connection, name, params)

    def close(self) -> None:
        self._connection.close()


def _views(connection: duckdb.DuckDBPyConnection, definition: Callable[[str], str]) -> None:
    for table in READ_ONLY_TABLES:
        connection.execute(f"CREATE VIEW {table} AS {definition(table)}")


def open_read_only(path: Path) -> ReadOnlyGraph:
    """`path` is `<module>/.sextant`, `<module>` (whose `.sextant` is used) or a bundle
    directory. Nothing is created, migrated or written: a workspace is attached READ_ONLY
    (which `DuckDbWorkspace.__init__` is not — it runs the schema on every open) and a
    bundle's Parquet is only read. Raises `NotABoundarySource` for anything else."""
    if (path / "manifest.json").is_file():
        return _open_bundle(path)
    for workspace in (path, path / ".sextant"):
        if (workspace / _WORKSPACE_FILE).is_file():
            return _open_workspace(workspace)
    raise NotABoundarySource(path, f"neither is there {_LOOKED_FOR}")


def _open_workspace(workspace: Path) -> ReadOnlyGraph:
    metadata = _json_document(workspace, "metadata.json")
    provenance = _block(metadata, "provenance")
    found: dict[str, object] = {
        "sextant_version": provenance.get("sextant_version"),
        "fact_schema_version": provenance.get("fact_schema_version"),
        "graph_schema_version": metadata.get("schema_version"),
        "boundary_vocabulary_version": metadata.get("boundary_vocabulary_version"),
        "catalog_hash": metadata.get("catalog_hash"),
    }
    _required(workspace, metadata, "module", "id")
    commit = _required(workspace, metadata, "provenance", "commit")
    connection = duckdb.connect()
    try:
        # READ_ONLY is the guarantee: the engine refuses any write.
        connection.execute(
            f"ATTACH {_sql_string(str(workspace / _WORKSPACE_FILE))} AS w (READ_ONLY)"
        )
        _views(connection, lambda table: f"SELECT * FROM w.{table}")
    except duckdb.Error as error:
        connection.close()
        raise NotABoundarySource(workspace, f"it could not be opened read-only: {error}") from error
    return ReadOnlyGraph(
        connection,
        module=_block(metadata, "module"),
        commit=commit,
        producer={name: value for name, value in found.items() if value is not None},
        environments=_names(metadata, "environments"),
        is_bundle=False,
        module_root=workspace.parent,
    )


def _open_bundle(bundle: Path) -> ReadOnlyGraph:
    manifest = _json_document(bundle, "manifest.json")
    _required(bundle, manifest, "module", "id")
    commit = _required(bundle, manifest, "source", "commit")
    missing = [t for t in READ_ONLY_TABLES if not (bundle / "graph" / f"{t}.parquet").is_file()]
    if missing:
        raise NotABoundarySource(
            bundle, f"its graph/ lacks {', '.join(missing)} (exported by an older Sextant)"
        )
    producer = _block(manifest, "producer")
    connection = duckdb.connect()
    try:
        _views(
            connection,
            lambda table: (
                f"SELECT * FROM read_parquet({_sql_string(str(bundle / 'graph' / f'{table}.parquet'))})"
            ),
        )
    except duckdb.Error as error:
        connection.close()
        raise NotABoundarySource(bundle, f"it could not be opened read-only: {error}") from error
    return ReadOnlyGraph(
        connection,
        module=_block(manifest, "module"),
        commit=commit,
        producer={name: producer[name] for name in STAMPS if producer.get(name) is not None},
        environments=_names(manifest, "environments"),
        is_bundle=True,
        module_root=None,
    )


class StaleParticipantError(RuntimeError):
    """`federate` was handed a participant workspace lacking a table the system views read:
    derived by an older Sextant, before that table existed. Named, with the command to run,
    rather than a bare `Catalog Error` on the first system query."""


# The system views, each a `UNION ALL` over one table of every participant (D01 "System
# scope"): (view, participant table, columns).
_FEDERATED_VIEWS: tuple[tuple[str, str, str], ...] = (
    ("system_endpoints", "endpoints", "*"),
    ("system_config", "resolved_config", "*"),
    # Spec 2026-10-21-conditional-controllers (ruling 2): a condition is data on the
    # inbound endpoint and the link states it, read from the participant's own
    # `endpoint_conditions` — a VIEW since spec 2026-10-22-conditional-beans, which binds
    # inside the participant's own catalog when attached.
    ("system_endpoint_conditions", "endpoint_conditions", "*"),
    # Where each conditional bean exists, per environment: the verdict a link states for
    # either end, read beside the rows above (spec 2026-10-22-conditional-beans §3).
    ("system_bean_presence", "bean_presence", "*"),
)

# Names `schema.sql` once declared as a TABLE and now declares as a VIEW (spec
# 2026-10-22-conditional-beans: `endpoint_conditions`). `CREATE OR REPLACE VIEW` refuses to
# replace a table, so a workspace file an earlier build wrote is dropped of the table first
# — `_add_columns_the_schema_has_gained`'s reasoning: it is derived, and the next resolve
# rebuilds what it held.
_TABLES_NOW_VIEWS = ("endpoint_conditions",)


class DuckDbWorkspace:
    """The Workspace port over DuckDB. Owns SQL and D01; knows nothing about
    frameworks, languages or protocols (ARCHITECTURE §10)."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = duckdb.connect(str(path))
        schema = (_SQL_DIR / "schema.sql").read_text(encoding="utf-8")
        self._drop_tables_the_schema_made_views()
        self._connection.execute(schema)
        self._add_columns_the_schema_has_gained(schema)
        # Read HERE, while every fact view is still the form `schema.sql` just gave
        # it: once `_materialize_facts` has re-pointed a view at its table, the
        # catalog holds `SELECT * FROM fact_<view>` and the defining SELECT is gone
        # from it until the next open. `schema.sql` stays the single source — this
        # is DuckDB's own parse of it, never a copy kept beside it.
        self._fact_view_definitions = self._fact_view_definitions_from_catalog()
        self._reuse_or_drop_materialized_facts()
        # `_FACT_ONLY` rows already read since the last `load_facts`, keyed by the query
        # name and its bound values in order — the order `?` placeholders bind in.
        self._fact_reads: dict[tuple[object, ...], list[dict[str, object]]] = {}
        # What `once` built since the last `load_facts`, keyed by the builder (the
        # port states the contract). The builder running right now, if any, so that
        # `query` can refuse it a derived table — an answer folded from one would
        # survive the derivation that changed it, silently, until the next load.
        self._folds: dict[Callable[[DuckDbWorkspace], object], object] = {}
        self._folding: Callable[[DuckDbWorkspace], object] | None = None
        # Every derivation that fell back to per-value binding (`derive`), in order —
        # the slow route, counted so a whole pipeline can assert it took none
        # (`tests/application/test_pipeline.py`).
        self._per_value_retries: list[str] = []
        # The rows `_stage_fact_redactions` last computed, with the hash of the rule
        # set that computed them: `export_tables` and `export_facts` both stage the
        # same map over the same `raw_facts`, and computing it twice per export was
        # the single largest cost of exporting `mall-admin` (4.0s of 5.4s under the
        # profiler). Kept as rows rather than as the temp table because each export
        # method still drops its table when it finishes — the values are re-inserted,
        # never re-derived. Cleared with `_fact_reads`, for the same reason: this is
        # a reading of `raw_facts`, and `load_facts` is its one writer.
        self._staged_payloads: tuple[str, list[tuple[str, ...]]] | None = None

    def _drop_tables_the_schema_made_views(self) -> None:
        """Drops an existing TABLE `schema.sql` now declares as a view (`_TABLES_NOW_VIEWS`),
        so the schema's `CREATE OR REPLACE VIEW` can run on a workspace file an earlier build
        wrote — `module analyze` reopens that file rather than starting a new one, and is the
        command every stale-workspace refusal tells the reader to run."""
        placeholders = ", ".join("?" for _ in _TABLES_NOW_VIEWS)
        held = self._connection.execute(
            "SELECT table_name FROM duckdb_tables() WHERE database_name = current_database() "
            f"AND schema_name = 'main' AND table_name IN ({placeholders})",
            list(_TABLES_NOW_VIEWS),
        ).fetchall()
        for (table,) in held:
            self._connection.execute(f"DROP TABLE {table}")

    def _add_columns_the_schema_has_gained(self, schema: str) -> None:
        """Adds any column `schema.sql` declares that an EXISTING workspace file does
        not have.

        `schema.sql` is all `CREATE TABLE IF NOT EXISTS`, which does exactly nothing to
        a table that already exists — so every column added to it since a workspace file
        was written is missing from that file, and the first statement to select it dies
        with `Binder Error: Table "shapes" does not have a column with name
        "origin_tier"`. That is not a hypothetical: re-running `analyze` over the
        fixture's own `.sextant` directory did it, and the message names a column rather
        than the thing a reader can act on.

        **Adding is the whole migration, and it is enough because these tables are
        derived.** Everything but `raw_facts` is rebuilt from the facts on each
        `analyze`, and `raw_facts` itself is emptied and reloaded — so a column that
        arrives empty here is filled by the run that added it. Nothing is dropped or
        retyped: a column the schema no longer declares is left alone rather than
        deleted, because deleting data to satisfy a shape is the destructive direction
        and no shipped change has needed it.

        The expected shape comes from DuckDB's own parse of the same text, in a throwaway
        in-memory database, rather than from a regex over the DDL or a list maintained
        beside it — the two ways this could disagree with `schema.sql` while looking
        right.
        """
        reference = duckdb.connect(":memory:")
        try:
            reference.execute(schema)
            expected = reference.execute(
                "SELECT table_name, column_name, data_type FROM information_schema.columns "
                "WHERE table_schema = 'main' ORDER BY table_name, ordinal_position"
            ).fetchall()
        finally:
            reference.close()
        held = {
            (str(table), str(column))
            for table, column in self._connection.execute(
                "SELECT table_name, column_name FROM information_schema.columns "
                "WHERE table_schema = 'main'"
            ).fetchall()
        }
        for table, column, data_type in expected:
            if (str(table), str(column)) in held:
                continue
            self._connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {data_type}")

    def load_facts(self, fact_root: Path) -> int:
        """One bulk statement over the whole tree. Per-row insertion is a
        defect under NFR-11 — the difference is orders of magnitude."""
        pattern = str(fact_root / "**" / "*.jsonl")
        # Before the table is touched, not after the load succeeds: a load that fails
        # half-way must not leave the previous facts' rows answering for it.
        self._fact_reads.clear()
        self._folds.clear()
        self._per_value_retries.clear()
        self._staged_payloads = None
        self._connection.execute("DELETE FROM raw_facts")
        self._connection.execute(
            """
            INSERT INTO raw_facts
            SELECT json ->> 'kind', json ->> 'document_id', json
            FROM read_ndjson_objects(?)
            """,
            [pattern],
        )
        row = self._connection.execute("SELECT count(*) FROM raw_facts").fetchone()
        assert row is not None
        self._materialize_facts()
        return int(row[0])

    def _fact_view_definitions_from_catalog(self) -> dict[str, str]:
        """Each fact view's defining SELECT, as DuckDB stores it: `CREATE VIEW <name>
        AS <select>;`, normalized and stripped of comments, so the text after the
        first ` AS ` is the SELECT itself."""
        rows = self._connection.execute(
            "SELECT view_name, sql FROM duckdb_views() WHERE view_name IN "
            f"({', '.join('?' for _ in _FACT_VIEWS)})",
            list(_FACT_VIEWS),
        ).fetchall()
        return {str(name): str(sql).split(" AS ", 1)[1] for name, sql in rows}

    def _materialize_facts(self) -> None:
        """Each fact view becomes a `fact_<view>` table holding the view's rows, and
        the view is re-pointed at it, so no query re-extracts JSON from `raw_facts`.

        Called at the end of `load_facts` and nowhere else, which is what makes the
        tables stale-proof: `raw_facts` has exactly one writer, and this runs after
        it. In `_FACT_VIEWS` order, so a definition that reads `selected_documents`
        reads the table just built for it rather than the JSON form. Measured on
        `mall-admin`: 0.4s to build; `derive_endpoint_shapes` went from 39.8s to 5.4s
        and `derive_endpoints` from 44.1s to 27.7s. On `fixtures/orders-service` it
        costs 20ms and the same two passes go from 5.1s to 2.8s.
        """
        for view in _FACT_VIEWS:
            table = _fact_table(view)
            self._connection.execute(
                f"CREATE OR REPLACE TABLE {table} AS {self._fact_view_definitions[view]}"
            )
            self._connection.execute(f"CREATE OR REPLACE VIEW {view} AS SELECT * FROM {table}")

    def _reuse_or_drop_materialized_facts(self) -> None:
        """A REOPENED workspace keeps its `fact_*` tables only while they still match
        the schema; otherwise they are dropped and the next `load_facts` rebuilds them.

        `__init__` has just run `schema.sql`, which re-issues every fact view in its
        JSON form — so without this, every command that opens an analyzed workspace
        (render, export, every test that reopens the file) would run the slow views
        while the tables sat unused. The rule: the views are re-pointed at the tables
        only if EVERY table exists and its column list — names and types, in order —
        equals the view's as the schema defines it now. A schema that gained a column
        since the tables were written must not be masked by a stale table, and a
        table that lost one must not answer for a view that still declares it.
        """
        held = {
            str(name)
            for (name,) in self._connection.execute(
                "SELECT table_name FROM duckdb_tables() WHERE table_name IN "
                f"({', '.join('?' for _ in _FACT_VIEWS)})",
                [_fact_table(view) for view in _FACT_VIEWS],
            ).fetchall()
        }
        if all(_fact_table(view) in held for view in _FACT_VIEWS) and all(
            self._columns_of(view) == self._columns_of(_fact_table(view)) for view in _FACT_VIEWS
        ):
            for view in _FACT_VIEWS:
                self._connection.execute(
                    f"CREATE OR REPLACE VIEW {view} AS SELECT * FROM {_fact_table(view)}"
                )
            return
        for table in held:
            self._connection.execute(f"DROP TABLE {table}")

    def _columns_of(self, name: str) -> list[tuple[str, str]]:
        return [
            (str(column), str(data_type))
            for column, data_type in self._connection.execute(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_schema = 'main' AND table_name = ? ORDER BY ordinal_position",
                [name],
            ).fetchall()
        ]

    def derive(self, name: str, **params: object) -> None:
        sql = (_SQL_DIR / _NAMED_DERIVATIONS[name]).read_text(encoding="utf-8")
        try:
            self._connection.execute(sql, _bound(params) or None)
        except duckdb.ConversionException:
            # Where the JSON route refuses and the Python route did not (`_bound`):
            # a struct key the statement declares and a bound row does not carry
            # (NULL by the Python route), a key the row carries and the struct does
            # not declare (`has unknown key`, dropped by the Python route), and a key
            # whose case differs from the declaration's (matched case-blind by the
            # Python route). The first is a contract the hand-built rows in
            # `tests/storage/test_workspace.py` and
            # `tests/application/test_effective_annotations.py` pin — a row states
            # what differs, the statement's own type supplies the rest — so all three
            # are kept by handing the statement the values the way it always took
            # them. A value DuckDB genuinely cannot convert fails this second run
            # too, with the statement's own error; nothing is masked, and any other
            # error (a binder error, say) propagates from the first run untouched.
            # Every production row builder fills exactly the declared keys, which is
            # what keeps this the slow route nobody takes — and because one
            # undeclared key would put a whole list back on the 8.9s path, each
            # retry is recorded by name and the pipeline test asserts there were
            # none.
            self._per_value_retries.append(name)
            self._connection.execute(sql, params or None)

    def query(self, name: str, **params: object) -> list[dict[str, object]]:
        if name not in _FACT_ONLY:
            if self._folding is not None:
                raise ValueError(
                    f"{self._folding!r} reads `{name}`, which is not a query over facts "
                    f"alone: a value `once` keeps until the next load may read only the "
                    f"fact tables, or a derivation run after it would leave it stale"
                )
            return self._read(name, params)
        key = (name, *params.values())
        rows = self._fact_reads.get(key)
        if rows is None:
            rows = self._fact_reads[key] = self._read(name, params)
        return rows

    def once(self, build: Callable[["DuckDbWorkspace"], T]) -> T:
        if build in self._folds:
            return cast(T, self._folds[build])
        # Saved and restored rather than set and cleared, so a builder that reads
        # another fold leaves the outer builder under the guard when the inner returns.
        outer, self._folding = self._folding, build
        try:
            value = self._folds[build] = build(self)
        finally:
            self._folding = outer
        return value

    def _read(self, name: str, params: dict[str, object]) -> list[dict[str, object]]:
        return _run_named(self._connection, name, params)

    def export_tables(self, destination: Path, redactor: Redactor) -> list[str]:
        graph = destination / "graph"
        graph.mkdir(parents=True, exist_ok=True)
        self._stage_redactions(redactor)
        # `raw_facts` exports here as well as through `export_facts`, and both
        # join the same payload map — so it is staged for both rather than
        # owned by either.
        self._stage_fact_redactions(redactor)
        try:
            for name in _EXPORTED_TABLES:
                sql = _EXPORT_QUERIES[name]
                self._connection.execute(
                    f"COPY ({sql}) TO ? (FORMAT parquet, COMPRESSION zstd)",
                    [str(graph / f"{name}.parquet")],
                )
        finally:
            self._drop_staged(
                _REDACTED_CONFIG_VALUES,
                _REDACTED_ADDRESSES,
                _REDACTED_JSON,
                _REDACTED_ENTRY_VALUES,
                _REDACTED_PAYLOADS,
                _REDACTED_EVIDENCE,
            )
        return list(_EXPORTED_TABLES)

    def schema_objects(self) -> list[str]:
        """Every table and view `schema.sql` created, from DuckDB's own
        catalog rather than from a list beside it — a list would be the very
        thing the export ratchet exists to stop being hand-maintained.

        Read by `tests/storage/test_workspace.py`, whose assertion runs the
        direction that catches the defect: an object HERE with no export query
        fails the build. Eleven names were hand-listed for four phases and the
        seven they omitted left every bundle quietly incomplete.

        Staged redaction tables are excluded by name — they are temp tables
        this class creates and drops inside one export, never part of the
        schema. So are the endpoint-candidates table the endpoints derivation
        stages, the route-requirements stash the combinator writes and the channel
        edge the engines write, for the same reason (`_ENDPOINT_CANDIDATES`,
        `_ROUTE_REQUIREMENTS`, `_CHANNEL_BINDINGS`).
        """
        rows = self._connection.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'main' AND table_name NOT IN "
            "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ORDER BY table_name",
            [
                _REDACTED_CONFIG_VALUES,
                _REDACTED_ADDRESSES,
                _REDACTED_JSON,
                _REDACTED_ENTRY_VALUES,
                _REDACTED_PAYLOADS,
                _REDACTED_EVIDENCE,
                _ENDPOINT_CANDIDATES,
                _ROUTE_REQUIREMENTS,
                _CHANNEL_BINDINGS,
                # D01's two SYSTEM-scope tables. They are in `schema.sql` because one
                # class opens both kinds of workspace, and they are not in a module
                # bundle because a bundle is a MODULE artifact (D06 describes no bundle
                # for the system workspace). A module bundle carrying an empty `links`
                # would state that this module has no links, which is not a fact about
                # the module — linking is a tier above it. This is the only exclusion
                # here that is about SCOPE rather than about a table `schema.sql` did
                # not create, which is why it is spelled out rather than listed.
                "participants",
                "links",
            ],
        ).fetchall()
        # The `fact_*` tables are excluded for the same reason the staged tables are:
        # not objects `schema.sql` created. Each holds the rows of one fact view, and
        # that view exports under its own name, so nothing is dropped — a second
        # export of the same rows would be the copy that could fall out of step.
        materialized = {_fact_table(view) for view in _FACT_VIEWS}
        return [str(name) for (name,) in rows if str(name) not in materialized]

    def _drop_staged(self, *names: str) -> None:
        """Dropped rather than left behind: these hold the very values the
        export exists to keep out of a bundle, and a workspace reused by a
        later command has no business carrying them."""
        for staged in names:
            self._connection.execute(f"DROP TABLE IF EXISTS {staged}")

    def _stage_map(self, name: str, columns: str, rows: list[tuple[str, ...]]) -> None:
        """One substitution table, holding only the rows that actually CHANGE.
        An ordinary module stages nothing at all, which is what makes the join
        free where there is nothing to mask and keeps every unmatched value
        byte-identical to what the table holds."""
        self._connection.execute(f"CREATE OR REPLACE TEMP TABLE {name}({columns})")
        if rows:
            placeholders = ", ".join("?" for _ in rows[0])
            self._connection.executemany(f"INSERT INTO {name} VALUES ({placeholders})", rows)

    def _stage_redactions(self, redactor: Redactor) -> None:
        """The masked strings the export projections join against — computed
        in Python, through the one redactor, over the DISTINCT values the
        masked columns hold (a value repeated across environments, or a JSON
        argument list repeated across call sites, is redacted once, not once
        per row)."""
        config_rows = self._connection.execute(
            "SELECT DISTINCT key, value FROM resolved_config WHERE value IS NOT NULL"
        ).fetchall()
        self._stage_map(
            _REDACTED_CONFIG_VALUES,
            "key VARCHAR, value VARCHAR, masked VARCHAR",
            [
                (str(key), str(value), masked)
                for key, value in config_rows
                if (masked := redactor.redact_value(str(key), str(value))) != str(value)
            ],
        )

        # `open_questions` is unioned in with the endpoint columns because it
        # is keyed on a wire identity and carries the same `path` — one map,
        # so a question and the row it asks about cannot mask differently.
        # `roots` joins for the same reason and is not merely redundant: its
        # `path` is CARRIED from the endpoint that named the handler, so the
        # values overlap today, but a map built from endpoints alone would
        # leave any future root address unmasked with nothing saying so.
        # `value_resolutions.value` joins the same map (spec 2026-09-22 §7a): a
        # `would_resolve` row carries the string an engine WOULD publish as an
        # endpoint's `path`, so it is the same value by a different name and one
        # map is what keeps a shadow row and the row it anticipates spelled alike.
        # Empty on every analysis but a `--shadow` one, which costs this UNION a
        # scan of an empty table.
        address_rows = self._connection.execute(
            "SELECT DISTINCT path AS address FROM endpoints WHERE path IS NOT NULL "
            "UNION SELECT DISTINCT peer FROM endpoints WHERE peer IS NOT NULL "
            "UNION SELECT DISTINCT path FROM open_questions WHERE path IS NOT NULL "
            "UNION SELECT DISTINCT path FROM roots WHERE path IS NOT NULL "
            "UNION SELECT DISTINCT value FROM value_resolutions WHERE value IS NOT NULL"
        ).fetchall()
        self._stage_map(
            _REDACTED_ADDRESSES,
            "address VARCHAR, masked VARCHAR",
            [
                (str(address), masked)
                for (address,) in address_rows
                if (masked := redactor.redact_text(str(address))) != str(address)
            ],
        )

        # One map for one GRAMMAR: `call_sites.arguments`, `annotations.args`,
        # `return_flows.value`, `method_returns.value`, `constants.value` and
        # `field_writes.value` are all entries of D00 §5's argument shape,
        # built from the same string constants read out of bytecode — so one
        # hardcoded `https://user:pass@host` reaches a bundle through any of
        # the six, and all six take the same pass.
        #
        # **`field_writes.value` joined the grammar on 2026-10-18 and this
        # union did not, which shipped a credential in the clear beside the
        # same literal masked in `raw_facts`** — found by review, with the
        # bundle dumped, before the change was committed. The lesson is the
        # one `constants` already carried in its own export comment: a new
        # column of this grammar is not added until it is in this list, and
        # `tests/storage/test_workspace.py::test_the_three_unpinned_redaction_joins_actually_mask`
        # carries a row per column so the next one cannot ship untested.
        json_rows = self._connection.execute(
            "SELECT DISTINCT arguments::VARCHAR AS original FROM call_sites "
            "WHERE arguments IS NOT NULL "
            "UNION SELECT DISTINCT args::VARCHAR FROM annotations WHERE args IS NOT NULL "
            "UNION SELECT DISTINCT value::VARCHAR FROM return_flows WHERE value IS NOT NULL "
            "UNION SELECT DISTINCT value::VARCHAR FROM method_returns WHERE value IS NOT NULL "
            "UNION SELECT DISTINCT value::VARCHAR FROM constants WHERE value IS NOT NULL "
            "UNION SELECT DISTINCT value::VARCHAR FROM field_writes WHERE value IS NOT NULL "
            "UNION SELECT DISTINCT expression FROM bean_conditions WHERE expression IS NOT NULL"
        ).fetchall()
        self._stage_map(
            _REDACTED_JSON,
            "original VARCHAR, masked VARCHAR",
            [
                (str(original), masked)
                for (original,) in json_rows
                if (masked := redactor.redact_json(str(original))) != str(original)
            ],
        )

        # A condition's evidence, from the table and the view that composes it: the view's
        # reasons are built from the table's expressions, so each composed string is staged
        # as the view spells it rather than masked piecewise. `candidate_presence` carries
        # `bean_presence`'s evidence or `compiler`, and `endpoint_conditions` the table's, so
        # both are covered without evaluating either view a second time.
        evidence_rows = self._connection.execute(
            "SELECT DISTINCT evidence FROM bean_conditions WHERE evidence IS NOT NULL "
            "UNION SELECT DISTINCT evidence FROM bean_presence WHERE evidence IS NOT NULL"
        ).fetchall()
        self._stage_map(
            _REDACTED_EVIDENCE,
            "original VARCHAR, masked VARCHAR",
            [
                (str(original), masked)
                for (original,) in evidence_rows
                if (masked := redactor.redact_text(str(original))) != str(original)
            ],
        )

        # Keyed on `key_path` and masked by `redact_value`, which is the SAME
        # call `domain/factfile.redact_config_entry_line` makes on the same
        # field of the same fact — not a second expression of the rule, the
        # same one, reached from the column instead of from the payload text.
        entry_rows = self._connection.execute(
            "SELECT DISTINCT key_path, value FROM config_entries WHERE value IS NOT NULL"
        ).fetchall()
        self._stage_map(
            _REDACTED_ENTRY_VALUES,
            "key_path VARCHAR, value VARCHAR, masked VARCHAR",
            [
                (str(key_path), str(value), masked)
                for key_path, value in entry_rows
                if (masked := redactor.redact_value(str(key_path), str(value))) != str(value)
            ],
        )

    def export_facts(self, destination: Path, redactor: Redactor) -> int:
        """The bundle's fact files, with `config_entry` payload VALUES masked
        on the way out (2K Task 1 review, ruled): everything that LEAVES is
        masked, and a bundle carrying `graph/resolved_config.parquet` masked
        beside a `facts/` holding the same values in the clear masks nothing.

        The **local** fact files under the workspace are untouched, and so is
        `raw_facts` — the same verbatim-workspace rule the graph tables keep.
        Hence the two hashes a bundle carries, which describe two different
        moments: a document's own `redaction_set_hash` stays `sha256:none`
        because nothing was applied when those facts were READ, and the
        manifest's names the set that masked THIS bundle."""
        self._stage_fact_redactions(redactor)
        try:
            rows = self._connection.execute(
                "SELECT DISTINCT document_id FROM raw_facts ORDER BY document_id"
            ).fetchall()
            for (document_id,) in rows:
                target = destination / "facts" / f"{document_id}.parquet"
                target.parent.mkdir(parents=True, exist_ok=True)
                # Two bound values, not one: DuckDB's `?` positional binding does
                # not carry through a COPY statement's TO clause when the query
                # it wraps also binds a `?` (reproduced against duckdb 1.5.5) —
                # `$1`/`$2` does. `?` still covers the single-parameter case in
                # export_tables above.
                self._connection.execute(
                    "COPY (SELECT f.kind, f.document_id, "
                    f"      coalesce(m.masked::JSON, f.payload) AS payload "
                    f"FROM raw_facts f LEFT JOIN {_REDACTED_PAYLOADS} m "
                    "     ON m.original = f.payload::VARCHAR "
                    "WHERE f.document_id = $1 ORDER BY f.rowid) "
                    "TO $2 (FORMAT parquet, COMPRESSION zstd)",
                    [document_id, str(target)],
                )
            return len(rows)
        finally:
            self._drop_staged(_REDACTED_PAYLOADS)

    def _stage_fact_redactions(self, redactor: Redactor) -> None:
        """Masked `config_entry` payloads, keyed by the payload text the export
        joins on. Each one is masked by `domain/factfile.redact_config_entry_line`
        — the ONE place "a config_entry's value, masked by its own key" is
        expressed (2K Task 7 fix round 2), shared with the enrichment jail's
        fact-serving path (`application/enrich/tools.py`) rather than each
        carrying its own copy of the same shape.

        Only `config_entry` is rewritten. Every other fact kind copies through
        untouched, which is why this reads the kind rather than walking every
        payload: a symbol or a call-site fact is not a place a configuration
        value can be, and the JSON columns those facts project into the graph
        are masked at their own exit above.

        **Residual, stated rather than discovered:** an exotic hardcoded
        secret in a string constant — one no key names, no value pattern
        matches, and that is not a URL with userinfo — survives into the
        bundle. Closing that means value patterns, which is what `.sextant.yml`
        gives a repository that knows the shape of its own secrets."""
        # EVERY fact payload, not only `config_entry`. The bundle masks
        # `call_sites.arguments`, `annotations.args`, `return_flows.value` and
        # `method_returns.value` — and then shipped `raw_facts`, which contains
        # those very facts, verbatim in the same directory. A consumer
        # recomputing a derived table from the fact stream got different values
        # and could not tell a redaction from a defect.
        #
        # Two rules, applied in order, because they answer different questions:
        # a `config_entry`'s value is masked by its own KEY (the pattern rule),
        # and every payload's string leaves then pass the userinfo strip that
        # `call_sites` and the rest already take.
        #
        # Computed ONCE per rule set: the second export method of the same
        # workspace re-stages the rows the first computed. The rule-set hash is
        # the key because it is what names a redactor — two redactors with the
        # same hash mask every payload the same way.
        if self._staged_payloads is not None and self._staged_payloads[0] == redactor.rule_set_hash:
            self._stage_map(
                _REDACTED_PAYLOADS, "original VARCHAR, masked VARCHAR", self._staged_payloads[1]
            )
            return
        #
        # Filtered in SQL first: a payload reaches `redact_json` only when the
        # redactor's own prefilter says some string in it could match a rule.
        # The predicate is a SUPERSET of "the walk would change this payload"
        # (`Redactor.json_text_prefilter` states the argument per rule), so
        # every payload the walk would change is still walked, and a payload
        # the predicate excludes has no string any rule can act on — the walk
        # would have handed it back unchanged, and unchanged payloads are not
        # staged. The masking itself is untouched: the one redactor still
        # decides, over every payload that passes. Measured on `mall-admin`:
        # 75,296 distinct payloads walked became 592, and one staging went
        # from 1.1s to 0.11s, 0.1s of it this query. `None` means a value
        # pattern has no literal prefix, and then every payload is walked as
        # before.
        prefilter = redactor.json_text_prefilter()
        grammar = self._connection.execute(
            "SELECT original FROM ("
            "  SELECT DISTINCT payload::VARCHAR AS original FROM raw_facts "
            "  WHERE kind <> 'config_entry')"
            + (" WHERE regexp_matches(original, ?)" if prefilter is not None else ""),
            [] if prefilter is None else [prefilter],
        ).fetchall()
        staged_grammar: list[tuple[str, ...]] = [
            (str(original), masked)
            for (original,) in grammar
            if (masked := redactor.redact_json(str(original))) != str(original)
        ]
        entries = self._connection.execute(
            "SELECT DISTINCT payload::VARCHAR AS original FROM raw_facts "
            "WHERE kind = 'config_entry' "
            # Parenthesised because `IS NOT NULL` binds tighter than `->>`
            # in DuckDB (RUNBOOK) — unbracketed this reads as a boolean
            # subscript and fails at run time naming the whole payload.
            "AND (payload ->> 'value') IS NOT NULL"
        ).fetchall()
        staged: list[tuple[str, ...]] = [
            (str(original), masked)
            for (original,) in entries
            if (masked := redactor.redact_json(redact_config_entry_line(str(original), redactor)))
            != str(original)
        ]
        self._staged_payloads = (redactor.rule_set_hash, staged + staged_grammar)
        self._stage_map(
            _REDACTED_PAYLOADS, "original VARCHAR, masked VARCHAR", self._staged_payloads[1]
        )

    def federate(self, participants: Mapping[str, Path]) -> None:
        """The port's contract, as DuckDB does it: `ATTACH` each participant read-only and
        define the two views as a `UNION ALL` across them.

        **`ATTACH` reads a header, not a database**, which is what makes D01's "federating
        them costs no import stage" true rather than aspirational. MEASURED 2026-10-19 on
        `ruoyi-vue-pro`: 18 workspaces totalling 432 MB attach in 45 ms, the views define
        in 0.5 ms, and one scan of all 484 endpoint rows takes 2 ms. Nothing here needs
        caching or a narrowed view.

        The alias is positional (`p0`, `p1`, …) and never the participant's own name: a
        name is an artifactId and may carry a hyphen, which is not an identifier, and
        quoting it would put the caller's string into SQL. The name travels as a VALUE in
        the view's own `participant` column instead, which is also what the matcher reads.
        """
        aliases = []
        for index, (name, location) in enumerate(sorted(participants.items())):
            alias = f"p{index}"
            self._connection.execute(f"DETACH DATABASE IF EXISTS {alias}")
            # READ_ONLY because this workspace is the only one being written: a system run
            # must not be able to touch a participant's graph, and the flag is the
            # enforcement rather than a convention.
            self._connection.execute(f"ATTACH '{location}' AS {alias} (READ_ONLY)")
            aliases.append((alias, name))
            # A view binds at creation, so a participant lacking one of the federated tables
            # — a workspace an OLDER Sextant derived, before that table existed — would make
            # the first system query raise a bare `Catalog Error`. Refused here, naming the
            # participant and what to do, which is the same answer `render` gives a stale
            # workspace (D01 §7's stamp): there is no analysis here this build can read.
            # Present means present as the KIND this build's own schema makes it — a table
            # or a view, read off this workspace's own catalog — because a participant
            # analysed before `endpoint_conditions` became a view still holds a TABLE of
            # that name, with a column fewer, and the `UNION ALL` below would fail on it.
            present = self._object_kinds(alias)
            expected = self._object_kinds(None)
            missing = sorted(
                table
                for _, table, _ in _FEDERATED_VIEWS
                if present.get(table) != expected.get(table)
            )
            if missing:
                raise StaleParticipantError(
                    f"participant `{name}` ({location}) carries no `{'`, `'.join(missing)}` "
                    "as this build derives it: its workspace was derived by an older Sextant. "
                    "Run `sextant module analyze` on it again, then `system analyze`."
                )
        for view, table, columns in _FEDERATED_VIEWS:
            if not aliases:
                # No participant whose graph could be read. The view still EXISTS and is
                # empty, because the alternative — no view — makes a system query raise
                # `Catalog Error` and say nothing about why. `participants` carries the
                # reason per participant; this keeps the query answerable.
                self._connection.execute(
                    f"CREATE OR REPLACE VIEW {view} AS "
                    f"SELECT NULL AS participant, {table}.* FROM {table} WHERE false"
                )
                continue
            union = " UNION ALL ".join(
                f"SELECT '{name}' AS participant, {columns} FROM {alias}.{table}"
                for alias, name in aliases
            )
            self._connection.execute(f"CREATE OR REPLACE VIEW {view} AS {union}")

    def _object_kinds(self, database: str | None) -> dict[str, str]:
        """Every table and view `database` holds (this workspace's own where None), mapped
        to `table` or `view` — what `federate` compares a participant's against."""
        where = "database_name = coalesce(?, current_database()) AND NOT internal"
        kinds = {
            str(name): "table"
            for (name,) in self._connection.execute(
                f"SELECT table_name FROM duckdb_tables() WHERE {where}", [database]
            ).fetchall()
        }
        kinds.update(
            (str(name), "view")
            for (name,) in self._connection.execute(
                f"SELECT view_name FROM duckdb_views() WHERE {where}", [database]
            ).fetchall()
        )
        return kinds

    def close(self) -> None:
        # The staged rows hold the values the export exists to keep out of a
        # bundle; nothing after `close` has a use for them.
        self._staged_payloads = None
        self._connection.close()
