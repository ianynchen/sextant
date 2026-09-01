"""`.graphqls` / `.graphql` SDL schema files (2H design §2). A reader here
reads the neutral shape of the file — one embedded schema payload, verbatim —
and never interprets it: understanding a schema format is
`ingress.interpret.descriptors`'s job alone (2G design §3), and the GraphQL
runtime this module deliberately does not import is confined there
(`tests/architecture/test_protobuf_confinement.py`).

Unlike the `.proto` reader, nothing here compiles anything, and unlike the
`.avsc` reader, nothing here reads a name out of the file: Spring merges every
SDL file under the schema root into ONE schema, so a type this file names may
be declared in a sibling and the merge only makes sense module-wide. One file
is therefore one payload and nothing more — the merge happens once, later, in
the interpreter."""

from sextant.application.ports.artifacts import ReadRequest
from sextant.domain.facts import Document, EmbeddedDescriptorFact, Fact
from sextant.ingress.read import build_document


class GraphqlSdlReader:
    """Keyed by extensions `graphqls` and `graphql` (M03) — Spring GraphQL's
    own default suffix, and the spelling the wider ecosystem uses for the
    same file."""

    reads_schema_sources = True

    def accepts(self, file_kind: str) -> bool:
        return file_kind in ("graphqls", "graphql")

    def read(self, request: ReadRequest) -> list[tuple[Document, list[Fact]]]:
        pairs: list[tuple[Document, list[Fact]]] = []
        for file in request.files:
            content = file.read_bytes()
            try:
                text = content.decode("utf-8")
            except UnicodeDecodeError as error:
                # The one failure a reader that never parses can still have.
                # No `symbol` to name here without reading the schema, so this
                # file yields no embedded_descriptor fact at all — `partial`
                # is the whole story, as it is for an unreadable `.avsc`.
                document = build_document(
                    file=file,
                    root=request.root,
                    module_id=request.module_id,
                    language="graphql",
                    content=content,
                    partial=True,
                    partial_reason=f"unreadable graphql schema: {error}",
                )
                pairs.append((document, []))
                continue

            document = build_document(
                file=file,
                root=request.root,
                module_id=request.module_id,
                language="graphql",
                content=content,
            )
            fact = EmbeddedDescriptorFact(
                document_id=document.document_id,
                # The file's own path under the schema root, the same
                # path-derived display identity the `.proto` reader records —
                # and the name a gap carries when the interpreter cannot read
                # this file. It is never the cross-origin join key
                # (`DeclaredShapeFact.schema_name` is that), and a GraphQL
                # file declares many types, so no single type name could
                # stand for it.
                symbol=file.relative_to(request.root).as_posix(),
                schema_format="graphql",
                payload=text,
                origin="source",
            )
            pairs.append((document, [fact]))
        return pairs
