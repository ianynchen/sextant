"""Directory- and file-name conventions shared by every build-system
detector (2M Task 3 fix round 1, M2): the same literal names, named once, so
an edit to one detector's own copy cannot silently drift from the other's.

How each detector turns these names into directories it actually REPORTS
stays detector-specific — Maven has no per-build resource-root override to
read, so it always resolves these relative to `src/main`; Gradle reads the
resource roots the build itself declares (2M Task 3 fix round 1, I5), which
closes the non-conventional-layout gap Maven's own fixed guess cannot."""

# Files that declare how a module is packaged to run. Names, not contents:
# M02 forbids a detector from reading code, and these are build files. Never
# a framework name (M02) — a container image is evidence a module ships
# something runnable, regardless of what runs inside it.
CONTAINER_FILES = (
    "Dockerfile",
    "Containerfile",
    "compose.yaml",
    "compose.yml",
    "docker-compose.yaml",
    "docker-compose.yml",
)

# Schema-source directory names, sibling to the language source roots
# (protobuf-maven-plugin/avro-maven-plugin convention, and Gradle's own
# plugins for the same tools): ordered, unlike a set, because `schema_roots`
# reports them in this fixed order rather than whatever a directory listing
# would give.
SOURCE_SCHEMA_NAMES = ("proto", "avro")

# Schema-source directory names that live ON THE CLASSPATH, under a
# resources root, rather than beside the language source roots — a SOAP
# contract is served at runtime, and `META-INF/wsdl` is where the JAX-WS
# packaging convention puts it. Each is a path SUFFIX under whichever
# resources root(s) a detector reports, in the fixed order `schema_roots`
# uses; Spring GraphQL's SDL directory is the one of the three that is not
# itself a contract format, but the same "ships on the classpath" reasoning
# puts it here rather than beside the source roots.
RESOURCE_SCHEMA_SUFFIXES = (
    ("graphql",),
    ("wsdl",),
    ("xsd",),
    ("META-INF", "wsdl"),
)
