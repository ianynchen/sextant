package dev.sextant.extractor;

import java.util.List;

/** What this extractor can actually read out of a class file.
 *
 *  <p>Declared HERE, in the artifact that does the reading, and reported to the
 *  caller — because the caller cannot know it. The jar is built by a separate
 *  step (`./gradlew build`), so a Python-side list saying what the subprocess
 *  can do is a claim about a binary that may be older than the claim. It gates
 *  which catalogs run, so a wrong answer does not fail: it runs catalogs
 *  against fact kinds that were never emitted, and the module reports an
 *  absence it cannot distinguish from a real one.
 *
 *  <p>A jar that is behind now reports FEWER capabilities than the catalogs
 *  need, and the workspace says so through `skipped_catalogs` — the channel
 *  D02 §2 already defines for exactly this ("a weaker scanner must degrade
 *  visibly"). No new refusal was needed; the honest degradation already had a
 *  place to be reported.
 *
 *  <p>Sorted, so the report is byte-identical between runs (NFR-1). */
public final class Capabilities {
    private Capabilities() {}

    public static final List<String> ALL = List.of(
        // Phase 1: read straight from declarations.
        "annotation_args",
        // Capability 9.15: an `ANEWARRAY`/`AASTORE` construction reads as an
        // array of elements rather than one opaque `unresolved`.
        "array_arguments",
        // Phase 2C's per-method dataflow pass over every invoke.
        "call_site",
        "chain_reconstruction",
        // The class-file major each document was read from (JVMS 4.1), taken
        // from the bytes rather than from ASM's constants. Its consumers are
        // the accepted-range test, multi-release selection's target fallback,
        // and language labelling.
        "class_file_version",
        // Capability 9.14: parameterized superinterface references, kept as
        // full type references where `implemented_interfaces` erases them.
        "generic_interfaces",
        "implemented_interfaces",
        "kotlin_metadata",
        // Capability 9.17: the lambda body a `dynamic` call site dispatches
        // into, which is what stops those calls being orphaned.
        "lambda_body",
        // Capability 9.18: the value each return instruction hands back.
        "method_returns",
        // Capability 9.16: an annotation-valued annotation argument, read
        // recursively rather than dropped with no key at all.
        "nested_annotation_args",
        "string_constants",
        // Capability 9.13: a class symbol's erased direct superclass.
        "superclass",
        "type_annotations",
        "typed_signatures");
}
