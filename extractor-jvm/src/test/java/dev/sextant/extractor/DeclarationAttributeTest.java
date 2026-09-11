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
        // The flags javac really emits for one, measured: 0x1600.
        writer.visit(org.objectweb.asm.Opcodes.V17,
                     org.objectweb.asm.Opcodes.ACC_INTERFACE
                         | org.objectweb.asm.Opcodes.ACC_ABSTRACT
                         | org.objectweb.asm.Opcodes.ACC_SYNTHETIC,
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

    @Test
    void a_record_with_no_components_is_still_a_record() throws Exception {
        // `visitRecordComponent` fires once per component, so a marker record never
        // fires it — while the `Record` attribute is present and `Class.isRecord()`
        // returns true. Inferring the kind from a COUNT OF CALLBACKS is the same
        // mistake as inferring a parameter list from a count: the class file states
        // it, in the superclass `java/lang/Record`, which JLS 8.1.4 makes a
        // compile-time error to write by hand.
        assertTrue(
            symbol("EmptyRecord", "EmptyRecord#").contains("\"construct_kind\":\"record\""),
            "a record with no components read as a class");
    }

    @Test
    void an_enum_constant_with_a_body_is_a_class_not_an_enum() throws Exception {
        // javac compiles each such constant into an ANONYMOUS class carrying
        // `ACC_ENUM`, whose superclass is the enum and not `java/lang/Enum` —
        // `Class.isEnum()` refuses to call it an enum for exactly that reason, and
        // kotlinc does not set the bit at all. Reading the flag alone followed one
        // compiler's convention and put 5,895 non-enums into `enum_types`, a quarter
        // of everything that query returns.
        assertTrue(
            symbol("ConstantsWithBodies$1", "ConstantsWithBodies$1#")
                .contains("\"construct_kind\":\"class\""),
            "a constant body still reads as an enum");
        assertTrue(
            symbol("ConstantsWithBodies", "ConstantsWithBodies#")
                .contains("\"construct_kind\":\"enum\""),
            "the enum itself must still be an enum");
    }

    @Test
    void a_nested_type_reports_the_same_kind_a_top_level_one_would() throws Exception {
        // The kind was read from the `InnerClasses` access word (JVMS 4.7.6). That
        // word agrees with the class file's own on ACC_INTERFACE, ACC_ENUM and
        // ACC_ANNOTATION, so four of these five passed — and it has no `Record`
        // attribute for ASM to synthesise ACC_RECORD from, so every NESTED record
        // read as `class`: 1,262 of the 1,739 records in the local dependency cache.
        // All five are asserted, because a word that answers only four of them is
        // the wrong word to read whichever one happens to be tested.
        assertTrue(
            symbol("NestingHost$NestedRecord", "NestingHost$NestedRecord#")
                .contains("\"construct_kind\":\"record\""),
            "a nested record read as something else");
        assertTrue(
            symbol("NestingHost$PrivateNestedRecord", "NestingHost$PrivateNestedRecord#")
                .contains("\"construct_kind\":\"record\""),
            "a private nested record read as something else");
        assertTrue(
            symbol("NestingHost$NestedInterface", "NestingHost$NestedInterface#")
                .contains("\"construct_kind\":\"interface\""),
            "a nested interface read as something else");
        assertTrue(
            symbol("NestingHost$NestedAnnotation", "NestingHost$NestedAnnotation#")
                .contains("\"construct_kind\":\"annotation\""),
            "a nested annotation read as something else");
        assertTrue(
            symbol("NestingHost$NestedEnum", "NestingHost$NestedEnum#")
                .contains("\"construct_kind\":\"enum\""),
            "a nested enum read as something else");
        assertTrue(
            symbol("NestingHost$NestedClass", "NestingHost$NestedClass#")
                .contains("\"construct_kind\":\"class\""),
            "a nested class read as something else");
    }

    @Test
    void deprecated_is_reported_on_a_type_and_on_a_field_too() throws Exception {
        // Neither was asserted anywhere: deleting the `deprecated` line from the type
        // writer AND from the field writer left the entire suite green, because the
        // only assertion was on two methods.
        assertTrue(symbol("DeprecatedType", "DeprecatedType#").contains("\"deprecated\":true"));
        assertTrue(symbol("DeprecatedType", "#obsolete.").contains("\"deprecated\":true"));
        assertTrue(symbol("DeprecatedType", "#current.").contains("\"deprecated\":false"));
    }

    @Test
    void class_level_attributes_never_ride_on_a_member_fact() throws Exception {
        // `emit` is shared by types, fields and methods, and the three class-level
        // keys are gated on the construct being a TYPE. Deleting that gate left the
        // suite green, so a method could have claimed its class's nest membership.
        String member = symbol("GenericSignatureSample$Inner", "<init>");
        assertTrue(!member.contains("nest_host"), "a constructor claimed a nest host");
        assertTrue(!member.contains("nest_members"), "a constructor listed nest members");
        assertTrue(!member.contains("unread_attributes"), "a constructor claimed attributes");
    }

    @Test
    void a_class_merely_named_like_a_reserved_file_class_is_kept() throws Exception {
        // The NAME is not the evidence. A real `package-info` states
        // `ACC_INTERFACE | ACC_SYNTHETIC` and has no members; a real module descriptor
        // states `ACC_MODULE`. Matching the name alone deleted a legitimate class —
        // and for `package-info`, deleted only its TYPE, leaving its methods behind
        // with an `enclosing` naming a symbol that no longer exists.
        org.objectweb.asm.ClassWriter writer =
            new org.objectweb.asm.ClassWriter(org.objectweb.asm.ClassWriter.COMPUTE_MAXS);
        writer.visit(org.objectweb.asm.Opcodes.V17, org.objectweb.asm.Opcodes.ACC_PUBLIC,
                     "com/acme/orders/package-info", null, "java/lang/Object", null);
        org.objectweb.asm.MethodVisitor method = writer.visitMethod(
            org.objectweb.asm.Opcodes.ACC_PUBLIC, "real", "()V", null, null);
        method.visitCode();
        method.visitInsn(org.objectweb.asm.Opcodes.RETURN);
        method.visitMaxs(0, 0);
        method.visitEnd();
        writer.visitEnd();

        List<String> facts = new ClassScanner("com.acme/orders", "1.0.0")
            .scan(writer.toByteArray(), "doc-impostor");
        assertTrue(
            facts.stream().anyMatch(line ->
                line.contains("\"construct_kind\":\"class\"") && line.contains("package-info#")),
            "a real class named package-info lost its type symbol: " + facts);
    }
}
