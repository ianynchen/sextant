package dev.sextant.extractor;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.InputStream;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.Opcodes;

/**
 * W5: the `Signature` attribute, read for the half of it that was being dropped.
 *
 * <p>It was already read for field types, method RETURN types, the generic superclass and
 * the generic superinterfaces. It was not read for method or constructor PARAMETER types,
 * nor for the formal type parameters either a class or a method declares — so a fact could
 * say a method returns {@code Map<K, T>} while being unable to say what {@code K} or
 * {@code T} were, and every parameter arrived erased.
 */
class GenericSignatureTest {

    private List<String> scan(String simpleName) throws Exception {
        try (InputStream in =
                getClass().getResourceAsStream("/dev/sextant/extractor/" + simpleName + ".class")) {
            return new ClassScanner("com.acme/orders", "1.0.0")
                .scan(in.readAllBytes(), "doc-" + simpleName);
        }
    }

    private String symbol(String simpleName, String named) throws Exception {
        return scan(simpleName).stream()
            .filter(line -> line.contains("\"kind\":\"symbol\"") && line.contains(named))
            .findFirst()
            .orElseThrow(() -> new AssertionError("no symbol fact matching " + named));
    }

    /** The descriptor index of the parameter whose entry contains {@code needle},
     *  counted by the {@code "annotations":} marker each parameter entry opens with —
     *  the same positional read {@link ParameterAnnotationSkewTest} uses.
     *
     *  <p>Positional rather than a verbatim literal of the whole list: the literal
     *  discriminated just as well but had to be regenerated whenever a fixture gained an
     *  annotation, and a regenerated expectation is one nobody reads. This still fails on
     *  every misalignment, because a misaligned parameter list is well formed and differs
     *  only in WHICH entry holds the type argument. */
    private static int parameterHolding(String fact, String needle) {
        int at = fact.indexOf(needle);
        assertTrue(at > 0, "not present in the fact at all: " + needle);
        return fact.substring(0, at).split("\"annotations\":", -1).length - 2;
    }

    @Test
    void a_parameterized_parameter_keeps_its_type_argument() throws Exception {
        // The descriptor says `Ljava/util/List;` and nothing else. Only the
        // signature says the elements are Strings, and a shape pass rooting a
        // request body from a parameter cannot expand `List` alone.
        assertTrue(
            symbol("GenericSignatureSample", "accept").contains("\"java/util/List#\""),
            "the parameter's own symbol was lost");
        assertTrue(
            symbol("GenericSignatureSample", "accept").contains("\"java/lang/String#\""),
            "List<String> was still erased to List at the parameter position");
    }

    @Test
    void a_type_variable_parameter_keeps_its_name_rather_than_its_erasure() throws Exception {
        // `T item` erases to `Comparable` — the bound — which names a real type
        // that is not the declared one. The signature says `T`, and `T` is what
        // a substitution binds. The return position has been able to say this
        // since `returnFromSignature` existed; the parameter position could not.
        assertTrue(
            symbol("GenericSignatureSample", "accept").contains("\"symbol\":\"T\""),
            "the parameter's type variable was reported as its erasure");
    }

    @Test
    void a_method_with_no_signature_attribute_still_reports_its_parameters() throws Exception {
        // `plain(String)` uses no type variable and no parameterization, so javac
        // writes no Signature at all (measured). The erased descriptor is the only
        // source there is, and it must still be read — a generic-only path would
        // have emptied the parameter list of most methods in any real module.
        //
        // It returns VOID on purpose: with a `String` return the fact carries the
        // same symbol twice, and this assertion passed with the parameter dropped
        // entirely — the return type was answering for it.
        String plain = symbol("GenericSignatureSample", "plain");
        assertTrue(plain.contains("\"java/lang/String#\""), "the erased fallback was dropped");
        assertTrue(plain.contains("\"annotations\":[]"), "the parameter entry itself is missing");
    }

    @Test
    void an_inner_class_constructor_puts_the_signature_on_the_declared_parameter() throws Exception {
        // The skew this alignment exists for, measured rather than assumed: javac writes
        // `(LGenericSignatureSample;Ljava/util/List;)V` as the descriptor and
        // `(Ljava/util/List<Ljava/lang/String;>;)V` as the signature — JVMS 4.7.9.1
        // permits omitting an implicitly declared parameter, and `MethodParameters`
        // flags this one `mandated` (measured). Read positionally,
        // `List<String>` lands on the ENCLOSING INSTANCE and the real parameter stays
        // erased, and both parameters are still well formed either way — which is why
        // this is asserted on the whole list verbatim rather than on a `contains`. The
        // output is byte-stable by NFR-1, so the literal is a fixed target.
        String constructor = symbol("GenericSignatureSample$Inner", "<init>");
        assertEquals(
            1,
            parameterHolding(constructor, "java/lang/String#"),
            "the signature's type argument did not land on the declared parameter");
        assertEquals(
            0,
            parameterHolding(constructor, "\"erased_symbol\":\"dev/sextant/extractor/GenericSignatureSample#\""),
            "the enclosing instance is not the first descriptor parameter");
    }

    @Test
    void a_class_declares_its_formal_type_parameters_with_their_bounds() throws Exception {
        // `class GenericSignatureSample<T extends Comparable<T>>`. Without this,
        // nothing in a fact said what `T` was, and the `T` a parameter or a
        // return type now names would be an unattached string.
        String type = symbol("GenericSignatureSample", "GenericSignatureSample#");
        assertTrue(type.contains("\"type_parameters\":"), "the class declared none");
        assertTrue(type.contains("\"name\":\"T\""), "the type parameter's name was lost");
        assertTrue(type.contains("java/lang/Comparable#"), "the bound was lost");
    }

    @Test
    void a_method_declares_its_own_formal_type_parameters() throws Exception {
        // `<K extends CharSequence> Map<K, T> pair(K)`. The class's parameter is
        // not the only one a substitution has to bind.
        //
        // The BOUND is asserted on `bounded` below, not here: `CharSequence` is
        // also `K`'s erasure, so `pair` carries it either way and an assertion
        // on it here would pass against the pre-W5 code.
        String method = symbol("GenericSignatureSample", "pair");
        assertTrue(method.contains("\"name\":\"K\""), "the method's own type parameter was lost");
    }

    @Test
    void a_type_parameter_keeps_every_bound_it_declares_in_order() throws Exception {
        // `<W extends Number & Serializable> void bounded(String)`, written
        // `W:Ljava/lang/Number;:Ljava/io/Serializable;` (measured): a class bound
        // then an interface bound. Neither type is the type of anything the method
        // declares, so only the bounds can put them in this fact.
        String method = symbol("GenericSignatureSample", "bounded");
        assertTrue(
            method.contains("\"symbol\":\"java/lang/Number#\""), "the class bound was lost");
        assertTrue(
            method.indexOf("java/io/Serializable#") > method.indexOf("java/lang/Number#"),
            "the two bounds are not in declaration order");
    }

    @Test
    void a_bound_that_is_itself_a_type_variable_survives() throws Exception {
        // `<A, C extends A>`. A type VARIABLE is handed over the moment it is
        // seen, not at an end-of-node callback, so a bound collector keyed on that
        // callback drops it — silently, with a well-formed empty bounds list.
        //
        // `A` also shows the Object bound being recorded rather than dropped:
        // javac writes `A:Ljava/lang/Object;` for a parameter declared with no
        // bound at all, so an empty list here would mean either "unbounded" or
        // "not read".
        String method = symbol("GenericSignatureSample", "chained");
        assertTrue(
            method.contains("\"symbol\":\"java/lang/Object#\",\"wire_format\":\"\","
                + "\"wire_type\":\"object\"}],\"name\":\"A\"}"),
            "the unbounded parameter did not record the Object bound the class file states");
        assertTrue(
            method.contains("\"symbol\":\"A\",\"wire_format\":\"\","
                + "\"wire_type\":\"object\"}],\"name\":\"C\"}"),
            "a bound that is a type variable was dropped");
    }

    @Test
    void a_capturing_local_class_takes_its_signature_on_the_declared_parameter() throws Exception {
        // The shape that makes counting alone WRONG. javac appends a local class's
        // captured values to the constructor descriptor — at the END — so
        // `$1Local`'s descriptor is (Outer, List, StringBuilder, int) against a
        // one-entry signature. Aligned from the end, `List<String>` lands on the
        // `int`: well formed, and false. `MethodParameters` says which slot is the
        // declared one (measured: mandated, -, synthetic, synthetic).
        //
        // Asserted on the whole list verbatim, like the `Inner` case above and for
        // the same reason: every misalignment of these four produces four
        // well-formed parameters, so nothing narrower discriminates.
        String constructor = symbol("GenericSignatureSample$1Local", "<init>");
        assertEquals(
            1,
            parameterHolding(constructor, "java/lang/String#"),
            "the signature's type argument landed on a captured value, not the declared parameter");
        assertEquals(
            3,
            parameterHolding(constructor, "\"erased_symbol\":\"int#\""),
            "the captured int is not the last descriptor parameter");
    }

    @Test
    void a_constructor_with_no_method_parameters_attribute_stays_erased() throws Exception {
        // The same capture in a STATIC method: javac writes no `MethodParameters`
        // at all (measured), so nothing says which slots the signature omitted.
        // Every parameter keeps its erased type — less specific, never wrong —
        // rather than the scanner inventing an alignment.
        assertFalse(
            symbol("GenericSignatureSample$1StaticLocal", "<init>").contains("java/lang/String#"),
            "a type argument was placed with nothing saying which parameter it belongs to");
    }

    @Test
    void a_signature_the_parameter_flags_do_not_account_for_is_not_aligned() throws Exception {
        // The remaining branch, and no compiler in this repository emits it — so it is
        // driven by handing the scanner a class file built to have it. `MethodParameters`
        // declares BOTH parameters as source-declared while the signature names only one.
        // The two disagree and the flags do not say why, so there is no honest alignment
        // and every parameter keeps its erased type. Laying the one entry onto the first
        // unflagged slot instead would be a guess, and a well-formed one.
        org.objectweb.asm.ClassWriter writer =
            new org.objectweb.asm.ClassWriter(org.objectweb.asm.ClassWriter.COMPUTE_MAXS);
        writer.visit(Opcodes.V17, Opcodes.ACC_PUBLIC, "Unaccounted", null, "java/lang/Object", null);
        org.objectweb.asm.MethodVisitor method = writer.visitMethod(
            Opcodes.ACC_PUBLIC, "take",
            "(Ljava/util/List;Ljava/util/List;)V",
            "(Ljava/util/List<Ljava/lang/String;>;)V", null);
        method.visitParameter(null, 0);
        method.visitParameter(null, 0);
        method.visitCode();
        method.visitInsn(Opcodes.RETURN);
        method.visitMaxs(0, 0);
        method.visitEnd();
        writer.visitEnd();

        String taken = new ClassScanner("com.acme/orders", "1.0.0")
            .scan(writer.toByteArray(), "doc-unaccounted").stream()
            .filter(line -> line.contains("\"kind\":\"symbol\"") && line.contains("take"))
            .findFirst()
            .orElseThrow();
        assertFalse(
            taken.contains("java/lang/String#"),
            "a type argument was placed on a parameter the flags do not account for");
    }

    @Test
    void a_parameter_flags_table_shorter_than_the_descriptor_is_not_trusted() throws Exception {
        // JVMS 4.7.24 does not require `MethodParameters` to carry one entry per
        // descriptor parameter, and a slot with no entry has no flags to read. Left
        // unguarded, the second parameter here reads as "not source-declared" purely
        // because nothing was said about it, the counts then agree, and the signature's
        // `List<String>` is laid onto the first parameter — on the strength of a
        // statement the class file never made. No compiler in this repository emits a
        // short table, so this is built rather than compiled.
        org.objectweb.asm.ClassWriter writer =
            new org.objectweb.asm.ClassWriter(org.objectweb.asm.ClassWriter.COMPUTE_MAXS);
        writer.visit(Opcodes.V17, Opcodes.ACC_PUBLIC, "ShortTable", null, "java/lang/Object", null);
        org.objectweb.asm.MethodVisitor method = writer.visitMethod(
            Opcodes.ACC_PUBLIC, "take",
            "(Ljava/util/List;Ljava/util/List;)V",
            "(Ljava/util/List<Ljava/lang/String;>;)V", null);
        method.visitParameter(null, 0);   // one entry, two parameters
        method.visitCode();
        method.visitInsn(Opcodes.RETURN);
        method.visitMaxs(0, 0);
        method.visitEnd();
        writer.visitEnd();

        String taken = new ClassScanner("com.acme/orders", "1.0.0")
            .scan(writer.toByteArray(), "doc-short").stream()
            .filter(line -> line.contains("\"kind\":\"symbol\"") && line.contains("take"))
            .findFirst()
            .orElseThrow();
        assertFalse(
            taken.contains("java/lang/String#"),
            "a parameter with no flags entry was read as though it had one");
    }

    @Test
    void a_type_variable_symbol_is_scoped_to_the_declaration_that_names_it() throws Exception {
        // The consequence of reading parameter types from the signature, pinned where it
        // is caused rather than left to be found downstream. A type variable's symbol is
        // its NAME, and a name means nothing outside the declaration that introduced it.
        //
        // `Sub#get(T)` carries a `Signature` and reads `T`. The bridge javac ships beside
        // it — same class, same erased descriptor — carries none and reads
        // `java/lang/Object#`. Before W5 both read `java/lang/Object#` and compared EQUAL.
        //
        // Two shipped consumers compare parameter symbols across declarations and are
        // therefore affected: `effective_annotations._is_bridge`, which recognises a
        // bridge by its parameters matching the real override's, and
        // `derive_endpoints.sql`'s overload dedup key. Both are recorded in
        // `docs/open-issues.md`; the fix is theirs, but the fact is this.
        // `erased_symbol` is what makes them comparable again: it is the DESCRIPTOR's
        // answer, identical on both, and every consumer that keys or looks a type up by
        // a parameter reads it rather than `type.symbol`.
        List<String> methods = scan("GenericSignatureSample$Sub").stream()
            .filter(line -> line.contains("\"kind\":\"symbol\"") && line.contains("#get("))
            .toList();
        assertEquals(2, methods.size(), "expected the override and its bridge");
        assertEquals(
            1,
            methods.stream().filter(line -> line.contains("\"symbol\":\"T\"")).count(),
            "exactly one of the two — the one with a Signature — states the type variable");
        assertTrue(
            methods.stream().anyMatch(line ->
                line.contains("\"synthetic\":true") && !line.contains("\"symbol\":\"T\"")),
            "the bridge is the erased one, and it already says it is synthetic");
    }

    @Test
    void kotlins_trailing_synthetics_do_not_move_a_parameter_type() throws Exception {
        // Kotlin is the other producer this scanner reads, and it is the one that would
        // break a count-based alignment first: it appends its synthetics at the END — a
        // `Continuation` on a suspend fun, a mask and a marker on a `$default` bridge —
        // and it writes no `MethodParameters` attribute for W5 to align by.
        //
        // Measured (kotlinc 2.2.0), and the reason none of that matters: kotlinc writes a
        // FULL-LENGTH signature. `batched(List<String>)` compiles to
        // `(Ljava/util/List;Lkotlin/coroutines/Continuation;)Ljava/lang/Object;` and its
        // signature names BOTH, so the counts agree and the entries are taken in place.
        // The `$default` bridge carries no signature at all, so every parameter there
        // stays erased. Neither path reaches the flag-based alignment.
        //
        // This is the pin. Were kotlinc to start writing a SHORT signature, the counts
        // would disagree, no attribute would explain the gap, and the parameters would
        // fall back to erased — visible as this test failing, not as a wrong type.
        // A type reference writes its `arguments` before its own `symbol` (the keys are
        // sorted), so each parameter reads argument-then-symbol and the four together
        // give the exact order: List<String>, then Continuation<Unit>.
        //
        // REWRITTEN when the `suspend fun` read landed (`G-63`, Q2). This test used to
        // read the order `String < List < Unit < Continuation` across the published
        // parameters, which required the `Continuation` to BE published. It no longer is:
        // a suspending function is now read as the ordinary function it describes, its
        // trailing synthetic dropped and its return taken from that synthetic's own type
        // argument (`kotlin/Unit` becoming `void`, as an ordinary Kotlin `fun` returning
        // `Unit` already reads).
        //
        // The property this test exists for is UNCHANGED and still pinned here. The
        // synthetic is dropped AFTER alignment, so a SHORT signature would still break
        // the alignment first: the counts would disagree, no attribute would explain the
        // gap, `names` would fall back to the erased `java/util/List#` carrying NO type
        // argument, and the assertion below would fail. What is measured is the same
        // thing; only the shape it is read through has moved.
        //
        // The element reads `nullable: false` since `OI-82`: `List<String>` declares a
        // non-null element, and this pin used to carry Java's `true` for it — the
        // parameter half of the defect `G-63` closed for returns.
        String suspending = symbol("KotlinGenericSignature", "batched");
        assertTrue(
            suspending.contains("\"arguments\":[{\"arguments\":[],\"nullable\":false,"
                + "\"nullable_resolution\":\"resolved\",\"symbol\":\"java/lang/String#\""),
            "the declared parameter lost its type argument, which is what a SHORT "
                + "signature from kotlinc would look like");
        assertFalse(
            suspending.contains("kotlin/coroutines/Continuation#"),
            "the trailing synthetic is published as a parameter again");
        assertTrue(
            suspending.contains("\"returns\":{\"arguments\":[],\"nullable\":false,"
                + "\"nullable_resolution\":\"resolved\",\"symbol\":\"void#\""),
            "a suspend fun returning Unit did not read as the void it is");

        // A Kotlin function's own formal type parameter, read the same way a Java one is.
        String ranked = symbol("KotlinGenericSignature", "ranked");
        assertTrue(ranked.contains("\"name\":\"T\""), "kotlin's formal type parameter was lost");
        assertTrue(ranked.contains("\"symbol\":\"T\""), "kotlin's type-variable parameter was erased");

        // The `$default` bridge: no signature, five parameters, all erased. Aligning a
        // zero-length list would be the one way to get this wrong.
        assertFalse(
            symbol("KotlinGenericSignature", "defaulted$default").contains("java/lang/String#"),
            "a bridge with no signature was given a type argument from somewhere");
    }

    @Test
    void every_parameter_carries_the_descriptors_own_symbol_beside_the_signatures() throws Exception {
        // The signature's answer and the descriptor's, both kept. `T` is what a
        // substitution binds; the erasure is what can be compared between two
        // declarations, because a variable's NAME cannot be.
        String accept = symbol("GenericSignatureSample", "accept");
        assertTrue(
            accept.contains("\"erased_symbol\":\"java/lang/Comparable#\""),
            "the type variable parameter lost the descriptor's answer");
        assertTrue(accept.contains("\"symbol\":\"T\""), "the signature's answer was lost");

        // Written on EVERY parameter, not only the ones where the two differ: a JSON
        // path wildcard drops elements whose key is missing (measured), so a sparse key
        // gives a SHORTER list that misaligns against the parameters it describes. The
        // bridge in `Sub` is the pair that has to compare equal.
        assertEquals(
            2,
            accept.split("\"erased_symbol\":", -1).length - 1,
            "both parameters must carry it, including the one with nothing to add");
        assertEquals(
            2,
            scan("GenericSignatureSample$Sub").stream()
                .filter(line -> line.contains("#get("))
                .filter(line -> line.contains("\"erased_symbol\":\"java/lang/Object#\""))
                .count(),
            "the override and its bridge must present the same parameter to a consumer");
    }

    @Test
    void a_declaration_with_no_type_parameters_carries_no_key_at_all() throws Exception {
        // The "nothing generic, nothing captured" rule `supertype` and
        // `generic_interfaces` already follow: an empty list written onto every
        // method in every module says nothing with a key on every fact.
        assertFalse(
            symbol("GenericSignatureSample", "plain").contains("type_parameters"),
            "a non-generic method carried an empty type-parameter list");
        assertFalse(
            symbol("GenericSignatureSample$Inner", "GenericSignatureSample$Inner#")
                .contains("type_parameters"),
            "a non-generic class carried an empty type-parameter list");
    }
}
