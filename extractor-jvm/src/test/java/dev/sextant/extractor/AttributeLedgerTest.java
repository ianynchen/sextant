package dev.sextant.extractor;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;
import org.junit.jupiter.api.Test;

/**
 * W8. The ledger is only worth having if it cannot drift from the code, so these check
 * the three ways it could: an attribute missing from it, a reason that is not one, and a
 * claim of "read" whose reader no longer exists.
 */
class AttributeLedgerTest {

    /** JVMS 4.7's own list, transcribed from the section numbers. This is the
     *  independent side of the comparison: if the ledger and this disagree, one of them
     *  is wrong and the test cannot say which — which is the point of writing it twice
     *  rather than deriving one from the other. */
    private static final List<String> JVMS_4_7 = List.of(
        "ConstantValue", "Code", "StackMapTable", "Exceptions", "InnerClasses",
        "EnclosingMethod", "Synthetic", "Signature", "SourceFile", "SourceDebugExtension",
        "LineNumberTable", "LocalVariableTable", "LocalVariableTypeTable", "Deprecated",
        "RuntimeVisibleAnnotations", "RuntimeInvisibleAnnotations",
        "RuntimeVisibleParameterAnnotations", "RuntimeInvisibleParameterAnnotations",
        "RuntimeVisibleTypeAnnotations", "RuntimeInvisibleTypeAnnotations",
        "AnnotationDefault", "BootstrapMethods", "MethodParameters", "Module",
        "ModulePackages", "ModuleMainClass", "NestHost", "NestMembers", "Record",
        "PermittedSubclasses");

    @Test
    void every_attribute_jvms_defines_is_in_the_ledger_exactly_once() {
        List<String> ledger = AttributeLedger.ATTRIBUTES.stream()
            .map(AttributeLedger.Entry::attribute)
            .toList();
        assertEquals(
            JVMS_4_7.stream().sorted().toList(),
            ledger.stream().sorted().toList(),
            "the ledger and JVMS 4.7 disagree about which attributes exist");
        assertEquals(
            JVMS_4_7.size(), Set.copyOf(ledger).size(), "an attribute is listed twice");
    }

    @Test
    void nothing_is_in_a_third_state() {
        // The whole point. Before the ledger, an attribute nobody had read and an
        // attribute nobody had THOUGHT about were indistinguishable from outside —
        // both simply produced no facts — so `✅ ASM` in COVERAGE claimed something it
        // could not support. Every entry is read, or not read for a stated reason.
        for (AttributeLedger.Entry entry : AttributeLedger.ATTRIBUTES) {
            assertTrue(
                entry.evidence() != null && !entry.evidence().isBlank(),
                entry.attribute() + " is in neither state: no reader and no reason");
        }
    }

    @Test
    void a_reason_for_not_reading_is_a_reason_and_not_an_excuse() {
        // "Not implemented" is the third state wearing a sentence. A reason says why
        // NOT reading it is the right answer — what it would duplicate, what it says
        // nothing about, or what was measured and found empty.
        List<String> excuses = new ArrayList<>();
        for (AttributeLedger.Entry entry : AttributeLedger.ATTRIBUTES) {
            if (entry.read()) continue;
            String reason = entry.evidence().toLowerCase();
            for (String excuse : List.of("not implemented", "todo", "later", "for now",
                                          "not yet", "unsupported")) {
                if (reason.contains(excuse)) excuses.add(entry.attribute() + ": " + excuse);
            }
            assertTrue(
                entry.evidence().length() > 60,
                entry.attribute() + "'s reason is too short to be one: " + entry.evidence());
        }
        assertTrue(excuses.isEmpty(), "a deferral is not a reason: " + excuses);
    }

    @Test
    void every_attribute_claimed_read_names_a_reader_that_exists() {
        // The claim that rots first. An attribute marked read whose callback has been
        // renamed or deleted is exactly "declared, never read" — the defect the ledger
        // exists to make impossible — so the reader is resolved against the real
        // visitor classes rather than trusted.
        List<String> missing = AttributeLedger.ATTRIBUTES.stream()
            .filter(AttributeLedger.Entry::read)
            .filter(entry -> !readerExists(readerToken(entry.evidence())))
            .map(entry -> entry.attribute() + " claims " + entry.evidence())
            .toList();
        assertTrue(missing.isEmpty(), "an attribute claims a reader that does not exist: " + missing);
    }

    @Test
    void the_reader_check_fails_when_the_reader_is_not_there() {
        // Negative test, because the check above is only worth its line if a WRONG
        // claim fails it. Its first version matched any `visit(`-shaped text anywhere
        // in the source — call sites and comments included — so `Record`'s claim of
        // `visit` was satisfied by four unrelated `AnnotationVisitor.visit(` calls and
        // could not have failed however the reader was renamed.
        assertFalse(readerExists("visitRecordComponent"),
            "a callback the scanner does NOT override resolved anyway");
        assertFalse(readerExists("ClassScanner#noSuchMethod"),
            "a method that does not exist resolved anyway");
        assertFalse(readerExists("MethodFlow#constructKindOf"),
            "a method resolved against the wrong file");
        assertTrue(readerExists("visitLineNumber"), "a real override did not resolve");
        assertTrue(readerExists("ClassScanner#constructKindOf"),
            "a real method did not resolve");
    }

    /** The reader an `evidence` string names: everything before the first space, so a
     *  claim may carry a qualification after it (`RuntimeVisibleTypeAnnotations` names
     *  the two places it is NOT read). */
    private static String readerToken(String evidence) {
        int space = evidence.indexOf(' ');
        return space < 0 ? evidence : evidence.substring(0, space);
    }

    /** Whether the source declares the named reader. Two spellings, because not every
     *  attribute is read through a visitor callback: `File#method` is a method declared
     *  in that file — ASM's tree API materialises `BootstrapMethods` onto an
     *  `InvokeDynamicInsnNode` and no `visit*` override is involved — and a bare name
     *  is a `visit*` override. */
    private static boolean readerExists(String reader) {
        int hash = reader.indexOf('#');
        if (hash < 0) return visitorCallbacks().contains(reader);
        String file = reader.substring(0, hash) + ".java";
        String method = reader.substring(hash + 1);
        return java.util.regex.Pattern
            .compile("^\\s*(?:public|protected|private)?\\s*(?:static\\s+)?[\\w.$<>\\[\\], ]+?\\s+"
                     + java.util.regex.Pattern.quote(method) + "\\s*\\(",
                     java.util.regex.Pattern.MULTILINE)
            .matcher(sourceOf(file))
            .find();
    }

    /** Every `visit*` method the scanner overrides, read from its SOURCE.
     *
     *  <p>Reflection cannot answer this: the parameter, line-number and type-annotation
     *  callbacks are overridden inside ANONYMOUS classes — the `MethodNode` built per
     *  method — which `getDeclaredClasses` does not return. Reading the source is the
     *  honest way to ask "is this callback overridden", and it is what the ledger's
     *  claim actually means. */
    private static Set<String> visitorCallbacks() {
        Set<String> names = new java.util.HashSet<>();
        for (String file : List.of("ClassScanner.java", "MethodFlow.java", "TypeRefs.java")) {
            java.util.regex.Matcher found =
                // A DECLARATION, not any `visit(`-shaped text. The first version had no
                // anchor and no return type, so it matched call sites and comments too:
                // every `AnnotationVisitor.visit(...)` call in the file made the bare
                // name `visit` resolve, and a claim that resolves to a call site cannot
                // fail when the override behind it is deleted. A modifier and a return
                // type in front is what makes this a declaration.
                java.util.regex.Pattern
                    .compile("^\\s*(?:public|protected|private)\\s+[\\w.$<>\\[\\], ]+?\\s+"
                             + "(visit|visit[A-Z][A-Za-z]*)\\s*\\(",
                             java.util.regex.Pattern.MULTILINE)
                    .matcher(sourceOf(file));
            while (found.find()) names.add(found.group(1));
        }
        assertTrue(names.size() > 15, "found almost no callbacks; the source path is wrong");
        return names;
    }

    /** One extractor source file's text, or `""` when it is not on disk. */
    private static String sourceOf(String file) {
        java.nio.file.Path source =
            java.nio.file.Path.of("src/main/java/dev/sextant/extractor", file);
        if (!java.nio.file.Files.isRegularFile(source)) return "";
        try {
            return java.nio.file.Files.readString(source);
        } catch (java.io.IOException unreadable) {
            throw new AssertionError("cannot read " + source, unreadable);
        }
    }

    @Test
    void every_access_flag_is_in_the_ledger_with_a_state() {
        // The same rule for flags (§2.5): emitted, or in the set with a reason. Eleven
        // were silently dropped before W7 — an interface's `default` and `abstract`
        // methods emitted identical modifiers, and `f(String...)` was indistinguishable
        // from `f(String[])`.
        for (AttributeLedger.Entry entry : AttributeLedger.ACCESS_FLAGS) {
            assertTrue(
                entry.evidence() != null && !entry.evidence().isBlank(),
                entry.attribute() + " is in neither state");
            if (!entry.read()) {
                assertTrue(
                    entry.evidence().length() > 40,
                    entry.attribute() + "'s reason is too short to be one");
            }
        }
        // Every flag ASM itself defines, so a flag cannot be omitted by forgetting it.
        Set<String> known = java.util.Arrays.stream(org.objectweb.asm.Opcodes.class.getFields())
            .map(java.lang.reflect.Field::getName)
            .filter(name -> name.startsWith("ACC_"))
            .collect(Collectors.toSet());
        Set<String> listed = AttributeLedger.ACCESS_FLAGS.stream()
            .map(AttributeLedger.Entry::attribute)
            .collect(Collectors.toSet());
        List<String> unlisted = known.stream().filter(name -> !listed.contains(name)).sorted().toList();
        assertTrue(unlisted.isEmpty(), "access flags ASM defines and the ledger does not: " + unlisted);
    }
}
