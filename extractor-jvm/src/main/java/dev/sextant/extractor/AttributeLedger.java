package dev.sextant.extractor;

import java.util.List;

/** Every attribute JVMS 4.7 defines, and every access flag JVMS 4.1/4.5/4.6 defines,
 *  each in exactly ONE of two states: read, or deliberately not read with a stated
 *  reason. **There is no third state** — and the absence of a third state is the point.
 *
 *  <p>Before this, an attribute the scanner ignored and an attribute nobody had thought
 *  about looked identical from outside: both simply produced no facts. That is the
 *  difference §2.3 names between *"read, no consumer yet"* — legitimate, a fact waiting
 *  for a tier that will use it — and *"declared, never read"*, which is a claim the
 *  scanner does not honour. `docs/COVERAGE.md`'s `✅ ASM` said nothing at all while both
 *  were invisible.
 *
 *  <p>Kept beside the reader rather than in a document, because a document drifts from
 *  the code silently and `AttributeLedgerTest` will not: it checks this list against
 *  JVMS's own, and checks that every entry claiming to be read names a callback that
 *  exists. */
public final class AttributeLedger {
    private AttributeLedger() {}

    /** How an attribute is handled, and the evidence for the claim. */
    public record Entry(String attribute, String jvms, boolean read, String evidence) {}

    /** `reader` is the ASM callback or field that reads it — the string a test resolves
     *  against the visitor classes, so a claim of "read" cannot outlive its reader. */
    private static Entry read(String attribute, String jvms, String reader) {
        return new Entry(attribute, jvms, true, reader);
    }

    /** `reason` is why NOT reading it is the right answer. Never "not implemented" —
     *  that is the third state this list exists to abolish. */
    private static Entry skipped(String attribute, String jvms, String reason) {
        return new Entry(attribute, jvms, false, reason);
    }

    public static final List<Entry> ATTRIBUTES = List.of(
        read("ConstantValue", "4.7.2", "visitField"),
        read("Code", "4.7.3", "visitMethod"),
        skipped("StackMapTable", "4.7.4",
            "Verification metadata for the JVM's own type checker. It describes the "
            + "operand stack at a branch target and says nothing any declaration does, "
            + "so ASM is asked to SKIP_FRAMES and the bytes are never parsed."),
        read("Exceptions", "4.7.5", "visitMethod"),
        read("InnerClasses", "4.7.6", "visitInnerClass"),
        read("EnclosingMethod", "4.7.7", "visitOuterClass"),
        read("Synthetic", "4.7.8", "visitMethod"),
        read("Signature", "4.7.9", "visitMethod"),
        read("SourceFile", "4.7.10", "visitSource"),
        read("SourceDebugExtension", "4.7.11", "visitSource"),
        read("LineNumberTable", "4.7.12", "visitLineNumber"),
        read("LocalVariableTable", "4.7.13", "visitEnd"),
        skipped("LocalVariableTypeTable", "4.7.14",
            "Carries a local's GENERIC signature where 4.7.13 carries the erased "
            + "descriptor. Measured on `generic(List<T>, Map<String, List<T>>)`: the "
            + "names W6 wants are in the plain table either way, the generic PARAMETER "
            + "types already come from `Signature` (W5), and Sextant emits no body "
            + "locals at all. Nothing here it does not duplicate."),
        read("Deprecated", "4.7.15", "visitMethod"),
        read("RuntimeVisibleAnnotations", "4.7.16", "visitAnnotation"),
        read("RuntimeInvisibleAnnotations", "4.7.17", "visitAnnotation"),
        read("RuntimeVisibleParameterAnnotations", "4.7.18", "visitParameterAnnotation"),
        read("RuntimeInvisibleParameterAnnotations", "4.7.19", "visitParameterAnnotation"),
        read("RuntimeVisibleTypeAnnotations", "4.7.20", "visitTypeAnnotation"),
        read("RuntimeInvisibleTypeAnnotations", "4.7.20", "visitTypeAnnotation"),
        read("AnnotationDefault", "4.7.22", "visitAnnotationDefault"),
        read("BootstrapMethods", "4.7.23", "visitMethod"),
        read("MethodParameters", "4.7.24", "visitParameter"),
        skipped("Module", "4.7.25",
            "A module descriptor is not a type, and `module-info.class` yields no symbol "
            + "at all. Module identity comes from the build's own coordinates, and "
            + "`requires`/`exports` say less about dependencies than the build file "
            + "already does."),
        skipped("ModulePackages", "4.7.26",
            "The packages a module lists, which the classes themselves already state one "
            + "by one. Same reason as 4.7.25."),
        skipped("ModuleMainClass", "4.7.27",
            "Would give OI-22's `entry_point` root kind a producer that is a DECLARATION "
            + "rather than a guess. Measured before deciding: of 52 jars in the local "
            + "corpus carrying a module descriptor, NONE declares a main class — it is "
            + "set for an executable module, not a library — so the producer would be "
            + "correct and fire on nothing. OI-22 stays open, with this recorded as why."),
        read("NestHost", "4.7.28", "visitNestHost"),
        read("NestMembers", "4.7.29", "visitNestMember"),
        read("Record", "4.7.30", "visit"),
        read("PermittedSubclasses", "4.7.31", "visitPermittedSubclass"));

    /** Every access flag, on any of the three tables that carry them. `evidence` names
     *  the key a flag reaches a fact through, or why it does not. */
    public static final List<Entry> ACCESS_FLAGS = List.of(
        read("ACC_PUBLIC", "4.1/4.5/4.6", "visibility"),
        read("ACC_STATIC", "4.5/4.6", "modifiers.static"),
        read("ACC_FINAL", "4.1/4.5/4.6", "modifiers.final"),
        read("ACC_ABSTRACT", "4.1/4.6", "modifiers.abstract"),
        read("ACC_SYNTHETIC", "4.1/4.5/4.6", "modifiers.synthetic"),
        read("ACC_BRIDGE", "4.6", "modifiers.synthetic"),
        read("ACC_VARARGS", "4.6", "modifiers.varargs"),
        read("ACC_NATIVE", "4.6", "modifiers.native"),
        read("ACC_SYNCHRONIZED", "4.6", "modifiers.synchronized"),
        read("ACC_TRANSIENT", "4.5", "modifiers.transient"),
        read("ACC_VOLATILE", "4.5", "modifiers.volatile"),
        read("ACC_DEPRECATED", "4.7.15", "modifiers.deprecated"),
        read("ACC_INTERFACE", "4.1", "construct_kind"),
        read("ACC_ANNOTATION", "4.1", "construct_kind"),
        read("ACC_ENUM", "4.1/4.5", "construct_kind"),
        read("ACC_MODULE", "4.1", "suppresses the symbol for a module descriptor"),
        read("ACC_MANDATED", "4.7.24", "aligns the short parameter tables"),
        // Not a JVMS class access flag at all: ASM synthesises it from the presence of
        // the `Record` attribute (4.7.30) and reports it in `visit`. Listed because the
        // ledger's own test compares against every flag ASM defines, which is what
        // surfaced that the attribute could be read in one place instead of two.
        read("ACC_RECORD", "ASM, from 4.7.30", "construct_kind"),
        skipped("ACC_PRIVATE", "4.5/4.6",
            "`visibility` is two-valued by D00 §5a — `public` or `other` — because the "
            + "question it answers is whether a member is callable from outside, and "
            + "private, protected and package-private all answer no. Reading three more "
            + "flags to collapse them again would add a distinction no consumer makes."),
        skipped("ACC_PROTECTED", "4.5/4.6",
            "Folded into `other` with ACC_PRIVATE, for the reason given there: the "
            + "question `visibility` answers is whether a member is callable from "
            + "outside its own type, and protected answers no to that."),
        skipped("ACC_SUPER", "4.1",
            "Set on essentially every class since Java 1.1 and ignored by every JVM since "
            + "8 — it selects the old `invokespecial` semantics. It distinguishes nothing "
            + "in any class file this reads."),
        skipped("ACC_STRICT", "4.6",
            "`strictfp` became the default in Java 17 (JEP 306) and the flag is no longer "
            + "emitted at all by a compiler targeting 17 or later. It says nothing about "
            + "an interface's shape in either era."),
        skipped("ACC_OPEN", "4.7.25",
            "A flag on the module descriptor itself, which is not read at all — see the "
            + "Module entry above for why. It says a module opens every package for "
            + "reflection, which is a runtime permission and not a declaration shape."),
        skipped("ACC_TRANSITIVE", "4.7.25",
            "A flag on a module's `requires` directive, which is not read — see Module. "
            + "It says a dependency is re-exported to anyone requiring this module, "
            + "which is a resolution rule the build file states more completely."),
        skipped("ACC_STATIC_PHASE", "4.7.25",
            "A flag on a module's `requires` directive, which is not read — see Module. "
            + "It marks a dependency needed to compile and not to run, and a build file "
            + "records that as a scope, where every consumer here already reads it."));
}
