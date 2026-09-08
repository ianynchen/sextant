package dev.sextant.extractor;

import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.InputStream;
import java.util.List;
import org.junit.jupiter.api.Test;

/** W7's declaration attributes: `Record`, `Exceptions`, `PermittedSubclasses`,
 *  `Deprecated`. */
class DeclarationAttributeTest {

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

    @Test
    void a_record_stops_reporting_itself_as_a_class() throws Exception {
        // There is no ACC_RECORD; JVMS 4.7.30's `Record` attribute is the signal, and its
        // presence is all of it. `record` has been in D00 §4's closed set since it was
        // written and had NO producer — every record in the estate read `class`, which is
        // the "declared, never read" shape reached from the other side.
        assertTrue(
            symbol("RecordComponents", "RecordComponents#").contains("\"construct_kind\":\"record\""),
            "a record still reads as a class");
        assertTrue(
            symbol("AccessFlagSample", "AccessFlagSample#").contains("\"construct_kind\":\"class\""),
            "a plain class must be unaffected");
    }

    @Test
    void a_records_components_are_already_its_fields() throws Exception {
        // Why the components are NOT emitted as a second fact shape: they are already
        // here as the record's private final fields, in declaration order, with their
        // types. Emitting them again would be two vocabularies for one declaration.
        List<String> facts = scan("RecordComponents");
        assertTrue(
            facts.stream().anyMatch(f -> f.contains("RecordComponents#id.") && f.contains("\"field\"")),
            "the first component is not present as a field");
        assertTrue(
            facts.stream().anyMatch(f -> f.contains("RecordComponents#tags.") && f.contains("\"field\"")),
            "the second component is not present as a field");
    }

    @Test
    void a_sealed_type_names_every_type_permitted_to_extend_it() throws Exception {
        String sealed = symbol("SealedSample", "SealedSample#");
        assertTrue(sealed.contains("\"permits\":"), "the sealed type states no permits");
        assertTrue(sealed.contains("SealedSample$Approved#") || sealed.contains("Approved#"),
            "the first permitted subtype is missing");
        assertTrue(sealed.contains("Rejected#"), "the second permitted subtype is missing");
    }

    @Test
    void an_unsealed_type_carries_no_permits_key_at_all() throws Exception {
        // The same "nothing to say, nothing written" rule `supertype` and
        // `generic_interfaces` follow: nearly every type permits nothing.
        assertTrue(
            !symbol("AccessFlagSample", "AccessFlagSample#").contains("permits"),
            "an ordinary class carried a permits key");
    }

    @Test
    void a_declared_throws_is_carried_in_declaration_order() throws Exception {
        // ASM has always handed `Exceptions` to `visitMethod`; the parameter was accepted
        // and discarded. Order matters because it is the declaration's own.
        String settle = symbol("SealedSample", "settle");
        int io = settle.indexOf("java/io/IOException#");
        int interrupted = settle.indexOf("java/lang/InterruptedException#");
        assertTrue(io > 0 && interrupted > 0, "a declared throws is missing: " + settle);
        assertTrue(io < interrupted, "the declared order was not kept");
        assertTrue(settle.contains("\"throws\":"), "throws is not inside the signature");
    }

    @Test
    void a_method_declaring_no_throws_carries_no_key() throws Exception {
        assertTrue(
            !symbol("AccessFlagSample", "#array(").contains("throws"),
            "a method declaring nothing carried a throws key");
    }

    @Test
    void a_deprecated_declaration_says_so() throws Exception {
        // JVMS 4.7.15, which ASM folds into the access flags. Distinct from the
        // `@Deprecated` ANNOTATION, which a catalog reads separately — a class file can
        // carry either, both, or neither.
        assertTrue(symbol("SealedSample", "legacy").contains("\"deprecated\":true"));
        assertTrue(symbol("SealedSample", "settle").contains("\"deprecated\":false"));
    }

    @Test
    void a_nested_type_names_the_nest_it_belongs_to() throws Exception {
        // JVMS 4.7.28, and distinct from `enclosing` (W4), which names the IMMEDIATE
        // encloser: for `A$B$C` that is `A$B` where the nest host is `A`. The top-level
        // one is what OI-45 records `outer_type_of` guessing at by splitting a binary
        // name on `$` — a split that mis-reads a top-level class genuinely named
        // `Foo$Bar`, since `$` is a legal identifier character. This is the class file
        // stating it.
        String nested = symbol("GenericSignatureSample$Inner", "GenericSignatureSample$Inner#");
        assertTrue(nested.contains("\"nest_host\":"), "a nested type states no nest host");
        assertTrue(nested.contains("GenericSignatureSample#\""), nested);
    }

    @Test
    void a_nest_host_names_its_members() throws Exception {
        // JVMS 4.7.29, the same relationship from the host's side — the set that gets
        // private access to each other, which only the host carries.
        String host = symbol("GenericSignatureSample", "\"construct_kind\":\"class\"");
        assertTrue(host.contains("\"nest_members\":"), "the host lists no members");
        assertTrue(host.contains("GenericSignatureSample$Inner#"), host);
    }

    @Test
    void a_type_that_is_not_nested_carries_neither_key() throws Exception {
        String plain = symbol("SourceLocationSample", "SourceLocationSample#");
        assertTrue(!plain.contains("nest_host"), "an un-nested type claims a nest host");
        assertTrue(!plain.contains("nest_members"), "a type nesting nothing lists members");
    }

    @Test
    void an_attribute_this_build_cannot_read_is_recorded_by_name() throws Exception {
        // The point is that §2.3's ledger can say what was SEEN and not read, which is a
        // different claim from "not present" — a vendor's attribute, or one from a
        // class-file version newer than this build. The NAME only: reading the bytes
        // would mean guessing at a layout nobody published.
        //
        // Built rather than compiled: no compiler here emits one, and the fixture module
        // measured zero.
        org.objectweb.asm.ClassWriter writer =
            new org.objectweb.asm.ClassWriter(org.objectweb.asm.ClassWriter.COMPUTE_MAXS);
        writer.visit(org.objectweb.asm.Opcodes.V17, org.objectweb.asm.Opcodes.ACC_PUBLIC,
                     "Vendored", null, "java/lang/Object", null);
        writer.visitAttribute(new org.objectweb.asm.Attribute("SomeVendorAttribute") {
            @Override
            protected org.objectweb.asm.ByteVector write(
                    org.objectweb.asm.ClassWriter target, byte[] code, int codeLength,
                    int maxStack, int maxLocals) {
                return new org.objectweb.asm.ByteVector();
            }
        });
        writer.visitEnd();

        String type = new ClassScanner("com.acme/orders", "1.0.0")
            .scan(writer.toByteArray(), "doc-vendored").stream()
            .filter(line -> line.contains("\"kind\":\"symbol\""))
            .findFirst()
            .orElseThrow();
        assertTrue(type.contains("\"unread_attributes\":"), type);
        assertTrue(type.contains("SomeVendorAttribute"), type);
    }

    @Test
    void a_package_info_keeps_its_annotations_and_loses_only_the_invented_symbol() throws Exception {
        // `package-info.class` is the reserved file class javac compiles a PACKAGE's
        // annotations onto. Emitting a `class` symbol for it put a type into the graph
        // that no source declares — the same phantom `module-info` produced.
        //
        // But unlike `module-info` it is NOT skipped, and this is why: a package-level
        // nullability scope (D02 §2e) is declared through exactly this target, and
        // `shapes/nullability.py` strips the trailing `package-info#` to recover the
        // package it claims. Dropping the file would take the scope with it.
        org.objectweb.asm.ClassWriter writer =
            new org.objectweb.asm.ClassWriter(org.objectweb.asm.ClassWriter.COMPUTE_MAXS);
        writer.visit(org.objectweb.asm.Opcodes.V17,
                     org.objectweb.asm.Opcodes.ACC_INTERFACE | org.objectweb.asm.Opcodes.ACC_ABSTRACT,
                     "com/acme/orders/package-info", null, "java/lang/Object", null);
        writer.visitAnnotation("Lorg/jspecify/annotations/NullMarked;", true).visitEnd();
        writer.visitEnd();

        List<String> facts = new ClassScanner("com.acme/orders", "1.0.0")
            .scan(writer.toByteArray(), "doc-package-info");
        assertTrue(
            facts.stream().noneMatch(line -> line.contains("\"kind\":\"symbol\"")),
            "the invented package-info symbol survives: " + facts);
        assertTrue(
            facts.stream().anyMatch(line ->
                line.contains("\"kind\":\"annotation\"") && line.contains("NullMarked")),
            "the package's own annotation was lost with it: " + facts);
    }
}
