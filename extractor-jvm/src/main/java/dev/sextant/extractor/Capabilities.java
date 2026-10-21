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
        // W4. A catalog cannot ask for a fact it has no name for — `requires:`
        // matches on these strings — so reading an attribute without declaring
        // one leaves it unreachable however correctly it was read.
        //
        // `annotation_default` (JVMS 4.7.22): what an annotation element falls
        // back to when a use omits it. Its consumer is a catalog that today
        // hardcodes the same number from documentation, where a framework
        // version change makes the hardcoded answer silently wrong.
        "annotation_default",
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
        // A StringConcatFactory site's recipe, so an address the code assembles
        // reads as a template rather than as `unresolved`.
        "concat_template",
        // JVMS 4.7.2's `ConstantValue`: `static final String TOPIC = "orders"`
        // is how a great many real listeners name their destination, and the
        // address is unresolvable without it.
        "constant_value",
        // JVMS 4.7.6/4.7.7: the class file's own statement of what encloses a
        // nested class — including, for an anonymous one, the enclosing METHOD,
        // which splitting a binary name on `$` cannot reach.
        "enclosing_class",
        // Capability 9.14: parameterized superinterface references, kept as
        // full type references where `implemented_interfaces` erases them.
        "generic_interfaces",
        "implemented_interfaces",
        "kotlin_metadata",
        // Capability 9.17: the lambda body a `dynamic` call site dispatches
        // into, which is what stops those calls being orphaned.
        "lambda_body",
        // W6. JVMS 4.7.12 `LineNumberTable`: which source line a method's code
        // came from. Every line number in the estate was 0 — measured on
        // mall-admin, 1,428 symbols, all of them — so Sextant could say WHAT
        // exists and never WHERE. Its consumer is the index (W35): an address
        // that cannot produce `file:line` saves nobody a grep.
        "line_numbers",
        // W6. JVMS 4.7.13 `LocalVariableTable`: the name a source file gave each
        // local, which covers the parameters. It fills a name only where
        // `MethodParameters` stated none — measured on spring-web 6.1.6, 1,048 of
        // 9,164 parameter names come from here and from nowhere else.
        "local_variable_names",
        // Capability 9.18: the value each return instruction hands back.
        "method_returns",
        // Capability 9.16: an annotation-valued annotation argument, read
        // recursively rather than dropped with no key at all.
        "nested_annotation_args",
        // W6. JVMS 4.7.10: the NAME of the file a class was compiled from, as
        // the class file states it rather than as the class's own path implies.
        // The derivation it replaces was javac's conventions in code — `.java`,
        // and everything from the first `$` cut off — so every Kotlin class in
        // a module named a `.java` file that does not exist. Its consumer is
        // `relative_path`, which is what an index has to hand a reader who
        // wants to OPEN the declaration.
        "source_file",
        "string_constants",
        // Capability 9.13: a class symbol's erased direct superclass.
        "superclass",
        "type_annotations",
        // The `type_header` fact (D00 §5): the superclass, interfaces and class-level
        // annotations of every DEPENDENCY type this module's classes refer to, read from
        // the class file's header in the resolved classpath — bodies never. What makes a
        // module exception extending a library exception reach `Throwable`, and a
        // library class's `@ResponseStatus` readable, without scanning the whole jar.
        "type_headers",
        // W5. The formal type parameters a class or method declares, with their
        // bounds — the name and the position a generic substitution binds. The
        // parameter types `typed_signatures` reports can now be a bare type
        // VARIABLE, read from the signature instead of erased, and without this
        // that variable would be a string attached to nothing.
        //
        // NO CONSUMER YET, and stated so rather than left to be found: W25 is
        // where generic substitution reads it. That is the legitimate half of
        // §2.3's distinction — "read, no consumer yet" — as against "declared,
        // never read", which is the defect.
        "type_parameters",
        // W5 also completed this one: a method's or constructor's PARAMETER
        // types now come from the `Signature` attribute where it has one, as
        // the return type and a field's type already did. `List<String>` keeps
        // `String` at a parameter position, and `T` stays `T` rather than
        // arriving as whatever it erases to.
        "typed_signatures");
}
