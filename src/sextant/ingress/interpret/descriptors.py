"""The one interpreter (2G design §3): the only place in the system that
understands a schema format. Embedded descriptor payloads in, `declared_shape`
facts out — no extractor in any language links a schema runtime, and adding a
format touches this package and nothing else.

This module is the entry point and the dispatch. One format per module beside
it (`protobuf`, `avro`, `graphql_sdl`, `wsdl_xsd`), each the only module that
may import its format's runtime — which is what
`tests/architecture/test_protobuf_confinement.py` enforces, per module rather
than for the package as a whole. The split landed with the fourth format (2I
design §3's sanctioned refactor): the rule was always "one place understands
one format", and four formats in one file had stopped making that visible.

Understanding a schema format is not the same as understanding a language, and
this package deliberately does only the first. Naming the class a code
generator compiled a schema type into is per-language knowledge, so it arrives
as a `GeneratedNaming` the caller supplies (ARCHITECTURE §10's confinement
rule) — the same shape as every other adapter this system wires in.

Failure is a gap, never a crash: a payload that cannot be read lands its
symbol in the returned failure list (the `descriptors_not_interpreted` gap),
and every other payload still interprets.
"""

from collections.abc import Sequence

from sextant.domain.facts import DeclaredShapeFact, EmbeddedDescriptorFact
from sextant.ingress.interpret.avro import avro_shapes
from sextant.ingress.interpret.graphql_sdl import graphql_shapes
from sextant.ingress.interpret.protobuf import protobuf_shapes
from sextant.ingress.interpret.wire import GeneratedNaming, Origin, SchemaLocation
from sextant.ingress.interpret.wsdl_xsd import wsdl_shapes

# Re-exported: `SchemaLocation` and `GeneratedNaming` are this package's
# public seam, and the composition root and the JVM naming adapter have always
# reached them here.
__all__ = ["GeneratedNaming", "Origin", "SchemaLocation", "interpret_descriptors"]


def interpret_descriptors(
    descriptors: Sequence[EmbeddedDescriptorFact], naming: GeneratedNaming
) -> tuple[list[DeclaredShapeFact], list[str]]:
    """Every message, record and declared type the payloads carry, and the
    symbols of the payloads that could not be interpreted.

    `naming` names the generated classes compiled-origin shapes are keyed by;
    source-origin shapes compile to no class and are keyed by the schema's own
    full name, so nothing is asked of it for them.

    Three of the four branches are handed the module's whole payload set
    rather than one payload at a time, because their formats declare types
    across file boundaries: a protobuf descriptor imports another, SDL files
    merge into one schema, and a WSDL's types live in the `.xsd` it imports.
    Avro is the exception — an `.avsc` is self-contained.

    Output never depends on the order the descriptors arrived in (NFR-1):
    descriptor input order is whatever an artifact walk happened to produce,
    and the fact files are content-hashed. `symbol` alone does not order it —
    one symbol legitimately arrives twice, because every generated class
    inlines the whole schema it needs and a shared nested record is therefore
    declared once per embedding — so the document and origin that produced a
    shape break the tie, and a stable sort's fallback to input order never
    decides anything.
    """
    shapes: list[DeclaredShapeFact] = []
    failed: list[str] = []
    for fact in descriptors:
        if fact.schema_format == "avro":
            found, unread = avro_shapes(fact, naming)
            shapes.extend(found)
            failed.extend(unread)
    for found, unread in (
        protobuf_shapes([d for d in descriptors if d.schema_format == "protobuf"], naming),
        graphql_shapes([d for d in descriptors if d.schema_format == "graphql"]),
        wsdl_shapes([d for d in descriptors if d.schema_format == "wsdl"]),
    ):
        shapes.extend(found)
        failed.extend(unread)
    return sorted(
        shapes, key=lambda shape: (shape.symbol, shape.document_id, shape.origin)
    ), sorted(failed)
