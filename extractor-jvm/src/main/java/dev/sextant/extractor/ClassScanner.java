package dev.sextant.extractor;

import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.List;
import java.util.TreeMap;
import java.util.function.Consumer;
import kotlin.metadata.KmType;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassVisitor;
import org.objectweb.asm.FieldVisitor;
import org.objectweb.asm.MethodVisitor;
import org.objectweb.asm.Opcodes;
import org.objectweb.asm.Type;

/** Reads one class file and emits symbol facts as JSONL lines. */
public final class ClassScanner {
    private final String coordinates;
    private final String version;

    public ClassScanner(String coordinates, String version) {
        this.coordinates = coordinates;
        this.version = version;
    }

    public List<String> scan(byte[] classBytes, String documentId) {
        return scan(classBytes, documentId, reason -> {});
    }

    /** {@code onKotlinMetadataUnsupported} fires when this class's own {@code @Metadata}
     *  named a compiler version {@code kotlin-metadata-jvm} does not understand — the
     *  library's supported version always trails the compiler's, so this is the ordinary
     *  path for a module built on a newer Kotlin, not a corrupt class file. The class is
     *  still scanned in full; only its Kotlin-declared nullability is unavailable, and
     *  the caller decides what "unavailable" means for coverage reporting (Main does, at
     *  the class-file level M03/FR-17 requires). */
    public List<String> scan(byte[] classBytes, String documentId,
                              Consumer<String> onKotlinMetadataUnsupported) {
        return scan(classBytes, documentId, onKotlinMetadataUnsupported, sourceFile -> {});
    }

    /** {@code onSourceFile} receives the {@code SourceFile} attribute (JVMS 4.7.10) — the
     *  NAME of the file this class was compiled from, with no directory part.
     *
     *  <p>Reported out rather than turned into a fact here, because the caller is what
     *  knows the class's location on disk and therefore the only place the two halves of
     *  a source PATH can be joined. Absent for a class compiled with debug information
     *  stripped, in which case the caller keeps deriving what it can. */
    public List<String> scan(byte[] classBytes, String documentId,
                              Consumer<String> onKotlinMetadataUnsupported,
                              Consumer<String> onSourceFile) {
        List<String> lines = new ArrayList<>();
        new ClassReader(classBytes)
            .accept(new Visitor(lines, documentId, onKotlinMetadataUnsupported, onSourceFile),
                    ClassReader.SKIP_FRAMES);
        // DELIBERATELY NOT READ, with the reason stated here so W8's ledger can collect
        // it rather than rediscover it (§2.3's distinction: "read, no consumer yet" is
        // legitimate, "declared, never read" is the defect, and this is a third thing —
        // read by nobody because it duplicates what is already read).
        //
        // CLASS-LEVEL TYPE ANNOTATIONS (JVMS 4.7.20, sorts `CLASS_EXTENDS`,
        // `CLASS_IMPLEMENTS`, `CLASS_TYPE_PARAMETER`). W7's row names them; they are
        // not read, and the reason is a consumer rather than a difficulty.
        //
        // Measured: `class TA extends Base<@Marked String>` really does emit
        // `CLASS_EXTENDS, type_index=65535, location=[TYPE_ARGUMENT(0)]`, so the
        // information is there. But every consumer of a type annotation reaches it
        // through the `annotations` view targeting a FIELD — `shapes/nullability.py`
        // is the only reader, and it matches on a field's `type_path`. Nothing asks
        // what a SUPERTYPE's type argument is annotated with, and emitting facts for
        // it would be reading an attribute because a list says to.
        //
        // The rule this follows, learned the expensive way on `module-info`: ask
        // whether the consumer exists before asking whether the attribute does.
        //
        // `LocalVariableTypeTable` (JVMS 4.7.14). W6's plan row names it beside
        // `LocalVariableTable`, and it holds a local's GENERIC signature where the plain
        // table holds the erased descriptor. Measured on `generic(List<T>, Map<String,
        // List<T>>)`: the type table adds `Ljava/util/List<TT;>;` and the NAMES — which
        // is all W6 wants — are in the plain table either way. The generic parameter
        // types are already read, from the method's own `Signature` attribute (W5), and
        // Sextant emits no body locals at all. So there is nothing here a fact would
        // carry that another attribute does not already state.
        return lines;
    }

    /** D00 §1: overloads are disambiguated by **descriptor hash**, never by an
     *  ordinal, because "an ordinal changes when a sibling is added" and a
     *  symbol that moves is a symbol nothing downstream can join on — NFR-3,
     *  and every curation, link and blast radius that depends on it.
     *
     *  <p>Spent on every method, not only on names that are currently shared.
     *  Making its *presence* conditional reintroduces the very instability the
     *  rule forbids one level up: `save().` becomes `save(sig_…).` the day
     *  somebody adds an overload beside it, and the identity of a method
     *  nobody touched has moved. §1's bare `save().` is the common case
     *  written for readability; its stated reasoning is the binding part.
     *
     *  <p>The whole descriptor is hashed, return type included: two methods
     *  differing only in return type are legal bytecode, and a colliding
     *  symbol is the defect this exists to prevent. Prefixed rather than bare
     *  hexadecimal, for the reason the same section gives. */
    static String disambiguatorOf(String descriptor) {
        try {
            StringBuilder hex = new StringBuilder();
            byte[] digest = MessageDigest.getInstance("SHA-256").digest(descriptor.getBytes("UTF-8"));
            for (int i = 0; i < 4; i++) hex.append(String.format("%02x", digest[i]));
            return "sig_" + hex;
        } catch (NoSuchAlgorithmException | java.io.UnsupportedEncodingException impossible) {
            throw new IllegalStateException("SHA-256 or UTF-8 missing from this JVM", impossible);
        }
    }

    String symbolOf(String descriptorPath) {
        return "sextant-jvm maven " + coordinates + " " + version + " " + descriptorPath;
    }

    private final class Visitor extends ClassVisitor {
        private List<String> lines;
        private final String documentId;
        private final Consumer<String> onKotlinMetadataUnsupported;
        private final Consumer<String> onSourceFile;
        private String typeSymbol;
        // ASM's internal name for the class's own direct supertype, kept from
        // `visit` because a method visitor sees no class-level context: it is
        // what tells a generated Avro record apart from any other class whose
        // <clinit> parses a schema (DescriptorHarvest).
        private String superName;
        // Held from `visit` until `visitEnd`, so the class symbol can carry the
        // enclosing relationship the InnerClasses/EnclosingMethod attributes
        // state (W4). Before this, every nested class reported `enclosing: null`
        // — measured on the fixture: OrderResult$Detail and 4 others.
        private String internalName;
        private int classAccess;
        private String classSignature;
        private String nestHost;
        private final List<String> nestMembers = new ArrayList<>();
        private final java.util.TreeSet<String> unreadAttributes = new java.util.TreeSet<>();
        private final List<String> permittedSubclasses = new ArrayList<>();
        private String[] classInterfaces;
        private String enclosingSymbol;
        // Populated from @Metadata before any field is visited (ASM visits class-level
        // annotations before fields — see visitAnnotation below); empty for every
        // non-Kotlin class, which leaves Java's rule as the only source.
        private KotlinNullability.Decoded kotlinNullability = KotlinNullability.NONE;

        Visitor(List<String> lines, String documentId, Consumer<String> onKotlinMetadataUnsupported,
                 Consumer<String> onSourceFile) {
            super(Opcodes.ASM9);
            this.lines = lines;
            this.documentId = documentId;
            this.onKotlinMetadataUnsupported = onKotlinMetadataUnsupported;
            this.onSourceFile = onSourceFile;
        }

        /** JVMS 4.7.28 `NestHost`: the top-level class whose nest this one belongs to.
         *
         *  <p>Distinct from `enclosing` (W4), which names the IMMEDIATE encloser — for
         *  `A$B$C` that is `A$B`, where the nest host is `A`. Both are real answers to
         *  different questions, and the top-level one is what OI-45 records
         *  `outer_type_of` guessing at by splitting a binary name on `$` — a split that
         *  mis-reads a top-level class genuinely named `Foo$Bar`. This is the class file
         *  stating it. */
        @Override
        public void visitNestHost(String host) {
            nestHost = symbolOf(host + "#");
        }

        /** JVMS 4.7.29 `NestMembers`, the same relationship read from the host's side:
         *  every class sharing this one's nest, which is what gives private access
         *  between them. Only a nest HOST carries it. */
        @Override
        public void visitNestMember(String member) {
            nestMembers.add(JsonOut.string(symbolOf(member + "#")));
        }

        /** Any attribute this reader does not understand — a vendor's, or one from a
         *  class-file version newer than this build.
         *
         *  <p>Recorded by NAME only, and deliberately: the point is that §2.3's ledger
         *  can say what was SEEN and not read, which is a different claim from "not
         *  present". Reading the bytes would mean guessing at a layout nobody
         *  published. */
        @Override
        public void visitAttribute(org.objectweb.asm.Attribute attribute) {
            if (attribute != null && attribute.type != null) {
                unreadAttributes.add(JsonOut.string(attribute.type));
            }
        }

        /** JVMS 4.7.31 `PermittedSubclasses`: the COMPLETE set of types allowed to
         *  extend a sealed one — the language guaranteeing a closed hierarchy, which is
         *  the one case where "every implementation of this" is answerable rather than
         *  approximated by whatever the scan happened to see. */
        @Override
        public void visitPermittedSubclass(String permitted) {
            permittedSubclasses.add(JsonOut.string(symbolOf(permitted + "#")));
        }

        /** JVMS 4.7.10 `SourceFile`: the NAME of the file this class was compiled from.
         *
         *  <p>It was being derived instead — the class's own path with `.class` swapped
         *  for `.java` and everything from the first `$` cut off — which is a guess that
         *  is right for javac and wrong for every other compiler on the JVM. Measured on
         *  this repository's own fixtures: `KotlinOrder.class` was reported as
         *  `KotlinOrder.java`, a file that does not exist in the module, and every
         *  `KotlinOrderRoutes$…` lambda class named the same non-existent file.
         *
         *  <p>`debug` (the second parameter, `SourceDebugExtension`) is deliberately not
         *  read here: it is a SEPARATE attribute with its own entry in §2.3's ledger. */
        @Override
        public void visitSource(String source, String debug) {
            if (source != null) onSourceFile.accept(source);
            ownLines = SourceMap.outputLinesOf(source, debug);
        }

        /** The output lines that belong to this class's OWN source file, or null when
         *  every line does. Set from `SourceDebugExtension` before any method is
         *  visited — ASM delivers `visitSource` ahead of `visitMethod`. */
        private int[][] ownLines;

        @Override
        public void visit(int v, int access, String name, String sig, String superName, String[] ifaces) {
            typeSymbol = symbolOf(name + "#");
            this.superName = superName;
            // D00 §5a's PTR carrier. `superName` says only "extends
            // ParameterizedTypeReference"; the Signature attribute is the only
            // place its argument is written down, and for an anonymous subclass
            // — which is the shape a real one takes — the class declares
            // nothing else that names the payload at all.
            // DEFERRED to visitEnd, and re-inserted at index 0 so the fact
            // stream's order is byte-for-byte what it was (NFR-1 — `symbols.seq`
            // IS this order). ASM fires `visit` first but `visitOuterClass` and
            // `visitInnerClass` only afterwards, and those two carry the
            // enclosing relationship: emitting here would mean emitting before
            // the attribute that answers the question.
            this.internalName = name;
            this.classAccess = access;
            this.classSignature = sig;
            this.classInterfaces = ifaces;
        }

        /** JVMS 4.7.7 `EnclosingMethod`, for a LOCAL or ANONYMOUS class: the
         *  method it was declared inside. The class file states this; nothing
         *  else does, and splitting the binary name on `$` recovers the outer
         *  TYPE at best and never the method. */
        @Override
        public void visitOuterClass(String owner, String name, String descriptor) {
            enclosingSymbol = name == null
                ? symbolOf(owner + "#")
                : symbolOf(owner + "#" + name + "(" + disambiguatorOf(descriptor) + ").");
        }

        /** JVMS 4.7.6 `InnerClasses`. The table lists every nested class this
         *  one MENTIONS, so the entry that matters is the one naming this class
         *  itself; `outerName` is null for a local or anonymous class, which is
         *  the case `visitOuterClass` above answers instead.
         *
         *  <p>`EnclosingMethod` wins where both are present: it names the method,
         *  which is strictly more than the type, and a local class has both. */
        @Override
        public void visitInnerClass(String name, String outerName, String innerName, int access) {
            if (!name.equals(internalName) || outerName == null) return;
            if (enclosingSymbol == null) enclosingSymbol = symbolOf(outerName + "#");
            // This table's `access` word is NOT read. It carries the source's own
            // nesting modifier — a `private` nested class reports package-private
            // in the class file's own word, and ACC_PRIVATE only here — but nothing
            // consumes that today, and the two attempts to consume it both went
            // wrong: as visibility it flipped protected types to `other`, and as the
            // construct kind it reported every nested record as `class`. Recovering
            // the nesting modifier is OI-51; it starts by reading `access` here.
        }

        /** Capability 9.14: the parameterized superinterface references
         *  {@link TypeRefs#genericInterfacesFromSignature} recovers, applied to this
         *  class's own signature. Null — never an empty array — when nothing declared
         *  here is generic, the same "absent key means none" rule {@link
         *  #interfaceSymbolsJson} states for the erased list. */
        private String genericInterfacesJson(String sig) {
            List<String> generic = TypeRefs.genericInterfacesFromSignature(sig);
            return generic.isEmpty() ? null : JsonOut.array(generic);
        }

        /** Capability 9.13: D00 §4's `relationship_kind: extends`, made real. CP-3 found
         *  no fact recording it at all — `interfaces` erases every implemented type, and
         *  `supertype` (above) captures a superclass ONLY when its signature is generic,
         *  so a plain {@code class Foo extends Bar} produced nothing naming {@code Bar}.
         *  The class file's own {@code super_class} constant-pool entry — {@code
         *  superName}, always present in ASM's {@code visit} whether or not the class
         *  carries a {@code Signature} attribute — is what closes the gap.
         *
         *  <p>Null for {@code java.lang.Object}. JVMS 4.1 gives every INTERFACE this same
         *  entry though no interface "extends" it, and every class with no declared
         *  superclass gets it implicitly, so writing it would put a superclass reference
         *  on every interface and every root class in a module and say nothing with any
         *  of them — the same "nothing generic, nothing captured" rule {@link
         *  TypeRefs#genericSuperclassFromSignature} states, applied to the one case that
         *  carries no information either way. */
        private String erasedSuperclassJson(String superName) {
            if (superName == null || "java/lang/Object".equals(superName)) return null;
            return JsonOut.string(symbolOf(superName + "#"));
        }

        /** `implemented_interfaces`: the interface array ASM hands {@code visit},
         *  converted to the same symbol grammar every class-level reference uses
         *  ({@link #symbolOf}), in declaration order. Null — never an empty array —
         *  for a class implementing none, so an absent key means "none" rather than
         *  an empty array a consumer has to special-case identically. */
        private String interfaceSymbolsJson(String[] ifaces) {
            if (ifaces == null || ifaces.length == 0) return null;
            List<String> symbols = new ArrayList<>();
            for (String iface : ifaces) symbols.add(JsonOut.string(symbolOf(iface + "#")));
            return JsonOut.array(symbols);
        }

        /** Whether a `construct_kind` names a TYPE rather than one of its members.
         *  Spelled once because three class-level attributes ride on the type's fact
         *  and `emit` is shared with fields and methods. */
        private static boolean isType(String constructKind) {
            return "class".equals(constructKind)
                || "interface".equals(constructKind)
                || "annotation".equals(constructKind)
                || "enum".equals(constructKind)
                || "record".equals(constructKind);
        }

        /** D00 §4's construct kinds carry `enum` beside `class` and `interface`, and
         *  the type's own fact is the only place the distinction survives: a type
         *  reference to an enumeration is indistinguishable from a reference to a
         *  record. Called `class`, a closed set of constants is expanded structurally
         *  by a consumer that has no way to know better, and each constant becomes a
         *  field of a payload nobody sends — where D00 §5b's `enum` wire type says the
         *  whole thing in one value.
         *
         *  <p>The interface test comes first because an annotation type is both, and
         *  the enum test before the fallback because an enum is a class in the JVM's
         *  own model. */
        private String constructKindOf(int access) {
            // BEFORE the interface test, because an annotation type carries
            // ACC_INTERFACE too — `@interface` compiles to an interface extending
            // java.lang.annotation.Annotation. Tested second, every `@interface` in
            // the estate reported `construct_kind: "interface"`, which is the
            // distinction §8.1 rule 5 says to follow where the provider makes one:
            // the flag exists precisely to tell them apart.
            if ((access & Opcodes.ACC_ANNOTATION) != 0) return "annotation";
            if ((access & Opcodes.ACC_INTERFACE) != 0) return "interface";
            // `ACC_ENUM` alone is not "is an enum type". javac sets it on the
            // ANONYMOUS class it generates for an enum constant with a body, whose
            // superclass is the enum rather than `java/lang/Enum` — and
            // `Class.isEnum()` refuses to call those enums for exactly that reason.
            // Measured across 1,681 cached jars: 16,563 real enum types and 5,895
            // classes carrying the flag that are not one, a quarter of every row the
            // `enum_types` query returns. kotlinc does not set the bit on its
            // equivalent at all, so the two compilers already disagree and reading
            // the flag alone follows one of them.
            if ((access & Opcodes.ACC_ENUM) != 0 && "java/lang/Enum".equals(superName)) {
                return "enum";
            }
            // W7. JVMS 4.7.30's `Record` attribute is what says a type is a record,
            // and its presence is the whole signal. `record` has been in
            // D00 §4's closed set since it was written and had NO producer — every
            // record in the estate reported `class` — which is the "declared, never
            // read" shape §2.3's ledger exists to catch, reached from the other side.
            // `ACC_RECORD` is ASM reporting the `Record` attribute's PRESENCE — it is
            // not a JVMS class access flag, it is synthesised from the attribute, which
            // is exactly the question being asked.
            //
            // This was two signals before: a flag set from `visitRecordComponent`, plus
            // a `java/lang/Record` superclass test to cover what the first missed.
            // `visitRecordComponent` fires once per COMPONENT, so `record Empty() {}`
            // never fired it while carrying the attribute — 16 such classes in the local
            // dependency cache, in Hibernate and Spring Boot, and a marker record is the
            // shape a sealed hierarchy uses most. Both approximations are gone; the
            // ledger's own test is what surfaced that ASM states it directly.
            if ((access & Opcodes.ACC_RECORD) != 0) return "record";
            return "class";
        }

        /** A TYPE's declaration modifiers (W7). Always written, both keys, for the
         *  reason D00 §5a gives for a field's: an absent one cannot be told apart
         *  from a scanner that does not report it.
         *
         *  <p>`abstract` and `final` are the two a caller can act on — one says the
         *  type cannot be instantiated, the other that nothing can extend it — and
         *  they are the flags a sealed hierarchy and a value type both turn on. */
        private String typeModifiersJson(int access) {
            TreeMap<String, String> modifiers = new TreeMap<>();
            modifiers.put("abstract", String.valueOf((access & Opcodes.ACC_ABSTRACT) != 0));
            modifiers.put("final", String.valueOf((access & Opcodes.ACC_FINAL) != 0));
            modifiers.put("deprecated", String.valueOf((access & Opcodes.ACC_DEPRECATED) != 0));
            return JsonOut.object(modifiers);
        }

        @Override
        public MethodVisitor visitMethod(int access, String name, String descriptor, String sig, String[] ex) {
            // `ex` is JVMS 4.7.5 `Exceptions`, and it was accepted and discarded. A
            // declared `throws` is the method's own statement about what it can fail
            // with — the same question `error_advice` answers from the handler side —
            // and nothing could read it from the declaring side at all.
            String throwsJson = throwsJson(ex);
            String owner = typeSymbol.substring(typeSymbol.lastIndexOf(' ') + 1);
            String methodSymbol = symbolOf(owner + name + "(" + disambiguatorOf(descriptor) + ").");
            String constructKind = "<init>".equals(name) ? "constructor" : "method";
            int parameterCount = Type.getArgumentTypes(descriptor).length;
            String[] parameterNames = new String[parameterCount];
            // JVMS 4.7.24 `MethodParameters`' access flags, one slot per DESCRIPTOR
            // parameter. `ACC_MANDATED` marks a parameter the language declares
            // implicitly (an inner class's enclosing instance); `ACC_SYNTHETIC` marks
            // one the compiler invented (a captured local, an enum's name/ordinal).
            // Together they are exactly the set a `Signature` attribute may omit, and
            // they are the only thing in the class file that says WHICH descriptor
            // slots those are. -1, never 0, for a method with no such attribute: 0 is
            // a real flag value meaning "declared in source".
            int[] parameterFlags = new int[parameterCount];
            java.util.Arrays.fill(parameterFlags, -1);
            List<List<String>> parameterAnnotations = new ArrayList<>();
            List<List<String>> parameterTypeAnnotations = new ArrayList<>();
            for (int i = 0; i < parameterCount; i++) {
                parameterAnnotations.add(new ArrayList<>());
                parameterTypeAnnotations.add(new ArrayList<>());
            }
            List<String> returnTypeAnnotations = new ArrayList<>();
            // Read back through a local rather than through the visitor below, whose
            // own `access` field (a MethodNode's) shadows this parameter with the
            // same value. Same answer either way; naming which one is meant keeps it
            // that way if either ever stops being true.
            int methodAccess = access;
            // `OI-81`: a Kotlin `$default` bridge, recognised from its shape and joined to
            // the function it stands for. Null for every other method.
            KotlinDefaultBridge defaultBridge =
                KotlinDefaultBridge.recognise(access, name, descriptor, kotlinNullability);

            // Parameter names (visitParameter) and parameter annotations
            // (visitParameterAnnotation) arrive as callbacks during the visit, so the
            // symbol fact — whose signature embeds both — is only emitted at visitEnd,
            // once every callback for this method has fired.
            //
            // A MethodNode rather than a bare MethodVisitor, because the call-site
            // pass needs the whole instruction list and ASM's Analyzer reads it from
            // exactly this type. MethodNode *is* a MethodVisitor, so the annotation
            // and signature collection below is unchanged; the instruction stream it
            // does not override is what the node records. Deliberately no super call
            // in the annotation overrides: each returns a visitor of its own, and
            // delegating as well would have MethodNode build annotation nodes nobody
            // reads from values it never receives.
            return new org.objectweb.asm.tree.MethodNode(
                    Opcodes.ASM9, access, name, descriptor, sig, ex) {
                private int parameterIndex = 0;
                // 0 is "no line stated", never line 0: JVMS numbers source lines
                // from 1, and a method with no `Code` attribute — abstract, native,
                // or on an interface — has no table to read.
                private int lineStart = 0;
                private int lineEnd = 0;
                private String annotationDefault;
                // JVMS 4.7.18's `num_parameters`, held PER ATTRIBUTE. The visible
                // and invisible parameter annotations are two separate attributes
                // and the format permits different counts.
                //
                // Honest scope, measured: javac writes the SAME count in both, so
                // collapsing these into one field changes no output javac
                // produces — a mutation test confirmed the whole suite still
                // passes. They stay separate because the FORMAT allows the
                // counts to differ and reading one attribute's count against the
                // other's entries would be wrong for any producer that does; not
                // because a javac-built class file can tell the difference.
                // -1 means the attribute was absent, which is not 0.
                private int annotableVisible = -1;
                private int annotableInvisible = -1;

                @Override
                public void visitAnnotableParameterCount(int count, boolean visible) {
                    if (visible) annotableVisible = count; else annotableInvisible = count;
                }

                /** The descriptor index the attribute's entry {@code parameter}
                 *  belongs to, or {@code -1} when nothing in the class file says.
                 *
                 *  <p>JVMS 4.7.18 lets the table be SHORTER than the descriptor's
                 *  parameter list, because a compiler omits parameters it did not
                 *  read from source. This used to shift by the difference between
                 *  the two counts, on the rule that what is omitted is omitted from
                 *  the FRONT — the outer instance on an inner class, {@code
                 *  $enum$name} / {@code $enum$ordinal} on an enum.
                 *
                 *  <p>**That rule is javac's, and it is not even all of javac's.**
                 *  Measured on javac 26: a LOCAL class that captures gets its
                 *  captured values appended at the END, so
                 *  {@code GenericSignatureSample$1Local}'s constructor is
                 *  {@code (Outer, List, StringBuilder, int)} with one table entry —
                 *  and shifting from the end put {@code @Labelled}, written on the
                 *  {@code List}, onto the captured {@code int}. Both parameters
                 *  exist, the fact is well formed, and nothing downstream can tell.
                 *  The enum case this shift was built for is the same failure in the
                 *  other direction, which is why it was built.
                 *
                 *  <p>{@link #sourceDeclaredSlots} answers it from the class file
                 *  instead: the i-th table entry belongs to the i-th slot flagged
                 *  neither mandated nor synthetic.
                 *
                 *  <p>A FULL-LENGTH table needs none of that and is taken as it
                 *  stands — kotlinc writes one entry per descriptor parameter, empty
                 *  for the synthetic ones ({@code KotlinParameterAnnotated}), and so
                 *  does javac for a method that synthesised nothing.
                 *
                 *  <p>With NO flags to read, the index is taken as the slot — the
                 *  same fallback the type-annotation path takes, for the same
                 *  measured reason. Every shape that omits a slot from the FRONT
                 *  carries {@code MethodParameters} saying so (an enum's
                 *  constructor, an inner class's), and the one measured shape that
                 *  carries none — a local class declared in a STATIC method —
                 *  appends its synthetics, so counting from zero is already right
                 *  there. Stated as what was measured, not as a property of the
                 *  format: a producer that omits from the front and writes no flags
                 *  would defeat it, and no such producer is in evidence. */
                private int alignedParameter(int parameter, boolean visible) {
                    int declared = parameterAnnotations.size();
                    int annotable = visible ? annotableVisible : annotableInvisible;
                    // An absent count attribute means ASM reports one entry per
                    // descriptor parameter, so the index is already the slot.
                    if (annotable < 0 || annotable == declared) return parameter;
                    int[] slots = sourceDeclaredSlots(parameterFlags);
                    if (slots == null) return parameter;
                    // The flags are there but do not account for the difference.
                    // Nothing invented on top of that.
                    if (slots.length != annotable) return -1;
                    return parameter < slots.length ? slots[parameter] : -1;
                }

                /** JVMS 4.7.12 `LineNumberTable`: which source line each bytecode
                 *  offset came from. Kept as the smallest and largest, which is the
                 *  method's own extent in the file.
                 *
                 *  <p>Every line number in the estate was 0 — measured on mall-admin,
                 *  1,428 symbols, `line_start: 0` and `line_end: 0` on all of them — so
                 *  Sextant could say WHAT exists and never WHERE. An index that cannot
                 *  produce `file:line` saves nobody a grep.
                 *
                 *  <p>It is the extent of the CODE, not of the declaration: the first
                 *  line is the body's first statement, so annotations and the signature
                 *  sit above it. The class file states no declaration line, and
                 *  inventing one by subtracting would be a guess about formatting.
                 *
                 *  <p>Not sorted, not assumed ordered: the table's entries are in
                 *  bytecode-offset order, and a compiler is free to emit a later source
                 *  line at an earlier offset — a loop condition compiled after the body
                 *  is the ordinary case. Min and max over all entries is the only read
                 *  that survives that. */
                @Override
                public void visitLineNumber(int line, org.objectweb.asm.Label start) {
                    // Delegated FIRST and unconditionally. This visitor is a
                    // MethodNode, and MethodNode.visitLineNumber appends a
                    // LineNumberNode to the very instruction list MethodFlow
                    // numbers positions in — a call-site argument's `source`, a
                    // `receiver` and a `result` are all `instructions.indexOf(…)`.
                    // Swallowing the callback silently renumbered every one of
                    // them: internally consistent, so no fact is false and no
                    // test noticed, but every id in the estate moved for a change
                    // whose scope is three read-only attributes.
                    super.visitLineNumber(line, start);
                    // A line in this table is not necessarily a line in THIS file.
                    // Kotlin inlines a function by remapping its body's lines into a
                    // synthetic range past the end of the file and recording the real
                    // mapping in `SourceDebugExtension` — so a method calling `let` or
                    // `forEach` carries lines belonging to the Kotlin standard library,
                    // or to a file the compiler invented. Measured on kotlinc 2.4.10: a
                    // 13-line `Std.kt` reported `useForEach` as 9-17, where 16 and 17
                    // are `_Collections.kt` 2068-2069.
                    if (!SourceMap.contains(ownLines, line)) return;
                    if (lineStart == 0 || line < lineStart) lineStart = line;
                    if (line > lineEnd) lineEnd = line;
                }

                @Override
                public void visitParameter(String parameterName, int parameterAccess) {
                    if (parameterIndex < parameterNames.length) {
                        parameterNames[parameterIndex] = parameterName;
                        // `parameterAccess` was being discarded. It is JVMS 4.7.24's
                        // flags, and it is the discriminator the generic-parameter
                        // alignment below needs: counting alone cannot say whether a
                        // missing signature entry was dropped from the front or the end.
                        parameterFlags[parameterIndex] = parameterAccess;
                    }
                    parameterIndex++;
                }

                @Override
                public org.objectweb.asm.AnnotationVisitor visitAnnotation(String d, boolean visible) {
                    return annotationVisitor(methodSymbol, d, visible);
                }

                /** JVMS 4.7.22 `AnnotationDefault` (W4): what an ANNOTATION
                 *  TYPE's element evaluates to when a use omits it.
                 *
                 *  <p>Until now the catalogs carried these as hardcoded
                 *  constants — a claim about what a framework does at a version
                 *  nobody measured, which is the prediction §8.1 forbids. The
                 *  jar states it; this reads it. */
                @Override
                public org.objectweb.asm.AnnotationVisitor visitAnnotationDefault() {
                    return defaultValueVisitor(value -> annotationDefault = value);
                }

                @Override
                public org.objectweb.asm.AnnotationVisitor visitParameterAnnotation(
                        int parameter, String d, boolean visible) {
                    int index = alignedParameter(parameter, visible);
                    if (index < 0 || index >= parameterAnnotations.size()) return null;
                    return parameterAnnotationVisitor(d, parameterAnnotations.get(index));
                }

                @Override
                public org.objectweb.asm.AnnotationVisitor visitTypeAnnotation(
                        int typeRef, org.objectweb.asm.TypePath typePath, String d, boolean visible) {
                    // A method has more than one type reference — the return type,
                    // and each parameter — so unlike a field's single reference,
                    // the annotation itself does not say which one it belongs to.
                    // TypeReference's sort does: attach to the matching slot in the
                    // signature (D00 §5a) rather than a flat fact a consumer would
                    // have to match back to "which parameter, or the return type".
                    org.objectweb.asm.TypeReference reference = new org.objectweb.asm.TypeReference(typeRef);
                    return switch (reference.getSort()) {
                        case org.objectweb.asm.TypeReference.METHOD_RETURN ->
                            typeAnnotationEntryVisitor(typePath, d, visible, returnTypeAnnotations);
                        case org.objectweb.asm.TypeReference.METHOD_FORMAL_PARAMETER -> {
                            // JVMS 4.7.20.1 indexes FORMAL PARAMETER DECLARATIONS,
                            // not descriptor slots — the same distinction 4.7.18
                            // makes for parameter annotations above, and answered
                            // by the same flags rather than by a second piece of
                            // arithmetic that could disagree with the first.
                            //
                            // It used to borrow the ANNOTATION table's count as a
                            // stand-in for a count this attribute does not carry,
                            // and shift by it. That is two guesses stacked: the
                            // borrowed number, and the direction to shift it in.
                            int[] slots = sourceDeclaredSlots(parameterFlags);
                            int formal = reference.getFormalParameterIndex();
                            // Two ways this attribute gives no usable evidence, and
                            // both mean "the index IS the slot".
                            //
                            // NULL — no `MethodParameters` at all. Measured: a local
                            // class in a STATIC method, which appends its synthetics,
                            // so counting from zero is already right there.
                            //
                            // EMPTY — flags present, and every slot flagged. That is
                            // self-contradictory as evidence: it says the method
                            // declares no formal parameters while this attribute is
                            // indexing into them. A record's COMPACT canonical
                            // constructor is exactly that shape (measured: `mandated,
                            // mandated` on a two-parameter descriptor with
                            // `param_index=1`), because what is implicit there is the
                            // CONSTRUCTOR, not any parameter. Without this arm the
                            // annotation is silently dropped — a `@Nullable` on a
                            // record component, gone.
                            int index = (slots == null || slots.length == 0) ? formal
                                : (formal < slots.length ? slots[formal] : -1);
                            yield (index >= 0 && index < parameterTypeAnnotations.size())
                                ? typeAnnotationEntryVisitor(
                                    typePath, d, visible, parameterTypeAnnotations.get(index))
                                : null;
                        }
                        // Type-parameter bounds, the receiver type, and throws
                        // clauses have no slot in today's signature (D00 §5a covers
                        // parameters and the return type only) — out of scope here,
                        // not silently misattributed to one of those two.
                        default -> null;
                    };
                }

                /** JVMS 4.7.13 `LocalVariableTable`: the name a source file gave each
                 *  local, including the parameters, which occupy the first slots.
                 *
                 *  <p>Only fills a name nothing else stated. `MethodParameters` (4.7.24)
                 *  is the more specific attribute — it describes PARAMETERS, where this
                 *  one describes every local and happens to cover them — so where both
                 *  are present the first one wins and this changes nothing.
                 *
                 *  <p>A slot is not a parameter index: `this` takes slot 0 on an
                 *  instance method, and a `long` or `double` takes TWO slots (JVMS
                 *  2.6.1), so the fourth parameter of `(JDLjava/lang/String;)` sits at
                 *  slot 5. The slots are walked with the descriptor rather than counted.
                 *
                 *  <p>And a slot is REUSED: a local declared after a parameter goes out
                 *  of scope can take its number, so slot alone names two variables in
                 *  one method. The entry taken is the one whose scope begins at the
                 *  method's first instruction, which a parameter's always does and a
                 *  body local's never can. That is why this runs at `visitEnd` over the
                 *  parsed node rather than from a streaming callback: the labels only
                 *  become comparable once the whole method has been read. */
                private void fillParameterNamesFromLocals() {
                    if (localVariables == null || localVariables.isEmpty()) return;
                    org.objectweb.asm.tree.LabelNode first = null;
                    for (org.objectweb.asm.tree.AbstractInsnNode node : instructions) {
                        if (node instanceof org.objectweb.asm.tree.LabelNode label) {
                            first = label;
                            break;
                        }
                    }
                    if (first == null) return;
                    java.util.Map<Integer, org.objectweb.asm.tree.LocalVariableNode> bySlot =
                        new java.util.HashMap<>();
                    for (org.objectweb.asm.tree.LocalVariableNode local : localVariables) {
                        if (local.start == first && local.name != null) {
                            bySlot.putIfAbsent(local.index, local);
                        }
                    }
                    Type[] argumentTypes = Type.getArgumentTypes(descriptor);
                    int slot = (methodAccess & Opcodes.ACC_STATIC) != 0 ? 0 : 1;
                    for (int i = 0; i < argumentTypes.length && i < parameterNames.length; i++) {
                        org.objectweb.asm.tree.LocalVariableNode local = bySlot.get(slot);
                        // The DESCRIPTOR has to agree too. "Scoped from the first
                        // instruction, in this slot" is strong evidence and not proof: no
                        // compiler measured here puts anything else there, but the format
                        // permits it, and the failure mode without this check is a WRONG
                        // name rather than a missing one — well formed, and undetectable.
                        // Matching the erased type turns that back into no answer.
                        if (parameterNames[i] == null
                                && local != null
                                && argumentTypes[i].getDescriptor().equals(local.desc)) {
                            parameterNames[i] = local.name;
                        }
                        slot += argumentTypes[i].getSize();
                    }
                }

                @Override
                public void visitEnd() {
                    super.visitEnd();
                    fillParameterNamesFromLocals();
                    emit(methodSymbol, constructKind, typeSymbol,
                         signatureJson(name, descriptor, sig, parameterNames, parameterFlags,
                                       throwsJson,
                                       parameterAnnotations,
                                       parameterTypeAnnotations, returnTypeAnnotations,
                                       defaultBridge), methodAccess,
                         null, methodModifiersJson(methodAccess), null, null, null, null,
                         annotationDefault, typeParametersJson(sig), lineStart, lineEnd, null,
                         defaultBridge == null ? null : JsonOut.string(defaultBridge.function()));
                    // After the method's own symbol, never before: a call site
                    // names its caller, and a fact file reads top-down.
                    lines.addAll(MethodFlow.callSites(documentId, methodSymbol, this));
                    // D00 §5's method_return: what this method hands back, one
                    // fact per return instruction. After the call sites, not
                    // before, because a returned value's `source` names one of
                    // them and a fact file reads top-down.
                    lines.addAll(MethodFlow.methodReturns(documentId, methodSymbol, this));
                    // D00 §5's field_write: constructors only. MethodFlow does
                    // its own "<init>" gate, the same way it does its own
                    // per-instruction scan for call sites, so this call is
                    // unconditional here and a no-op on every other method.
                    lines.addAll(MethodFlow.fieldWrites(documentId, this));
                    // D00 §5's embedded_descriptor: static initializers only,
                    // gated inside DescriptorHarvest for the same reason. The
                    // fact names the class, not the method, so it is emitted
                    // where the constants are read rather than beside the
                    // class's own symbol — which ASM visits before any method
                    // body exists to read.
                    lines.addAll(
                        DescriptorHarvest.embeddedDescriptors(documentId, owner, superName, this));
                }
            };
        }

        @Override
        public FieldVisitor visitField(int access, String name, String descriptor, String sig, Object value) {
            // Compiler machinery — an enumeration's constant array, a captured
            // outer instance — is not a declaration: nobody wrote it, so there is
            // no fact to make about it. A modifier would be the wrong answer,
            // because that says "somebody declared this, and it stays off the
            // wire"; this is a member no source file contains, and a symbol graph
            // carrying it answers questions about code that does not exist.
            if ((access & Opcodes.ACC_SYNTHETIC) != 0) return null;
            String owner = typeSymbol.substring(typeSymbol.lastIndexOf(' ') + 1);
            String fieldSymbol = symbolOf(owner + name + ".");
            Type type = Type.getType(descriptor);
            // null when this field is not a Kotlin property (every Java field, and any
            // Kotlin field @Metadata did not name) — Java's rule still applies to those.
            Boolean kotlinNullable = kotlinNullability.properties().get(name);

            return new FieldVisitor(Opcodes.ASM9) {
                @Override
                public org.objectweb.asm.AnnotationVisitor visitAnnotation(String d, boolean visible) {
                    return annotationVisitor(fieldSymbol, d, visible);
                }

                @Override
                public org.objectweb.asm.AnnotationVisitor visitTypeAnnotation(
                        int typeRef, org.objectweb.asm.TypePath typePath, String d, boolean visible) {
                    return typeAnnotationVisitor(fieldSymbol, typePath, d, visible);
                }

                @Override
                public void visitEnd() {
                    emit(fieldSymbol, "field", typeSymbol, fieldSignatureJson(type, sig, kotlinNullable), access,
                         kotlinNullable == null ? null : kotlinExt(kotlinNullable), modifiersJson(access));
                    // D00 §5's `constant`, which had no producer until now. JVMS
                    // 4.7.2's `ConstantValue` is what ASM hands over as the
                    // `value` parameter above, and it was being ignored.
                    //
                    // Its stated consumer is topic and URL resolution:
                    // `static final String TOPIC = "orders"` is how a great many
                    // real listeners name their destination, and without this the
                    // address resolves to an unresolved reference instead of a
                    // wire identity.
                    //
                    // The class file carries the attribute ONLY for a static final
                    // field of a primitive or String type — the shape that can be a
                    // constant expression. A field initialised in `<clinit>` has no
                    // such attribute and produces nothing here: what a static
                    // initialiser computes is a different question, and answering
                    // it from this attribute would be a guess.
                    if (value != null) {
                        TreeMap<String, String> constant = new TreeMap<>();
                        constant.put("kind", JsonOut.string("constant"));
                        constant.put("document_id", JsonOut.string(documentId));
                        constant.put("symbol", JsonOut.string(fieldSymbol));
                        constant.put("value", constantJson(value));
                        lines.add(JsonOut.object(constant));
                    }
                }
            };
        }

        @Override
        public org.objectweb.asm.AnnotationVisitor visitAnnotation(String descriptor, boolean visible) {
            // The compiler's own bookkeeping, not a fact of its own (D00 §5a is about
            // annotations someone wrote) — decode it into the property lookup instead
            // of letting its protobuf blob out through the normal annotation stream.
            if (KotlinNullability.DESCRIPTOR.equals(descriptor)) {
                return KotlinNullability.collector(
                    decoded -> kotlinNullability = decoded, onKotlinMetadataUnsupported);
            }
            return annotationVisitor(typeSymbol, descriptor, visible);
        }

        /** A `ConstantValue` as JSON, in its own native type.
         *
         *  <p>ASM hands back an Integer, Long, Float, Double or String — the only
         *  types JVMS 4.7.2 admits. Kept as a JSON number or string rather than
         *  stringified, because a consumer resolving an address needs the string
         *  and one reading a port needs the number; re-parsing text downstream
         *  would put a guess between the reader and the class file.
         *
         *  <p>`boolean`, `byte`, `short` and `char` constants are stored as
         *  Integer by the format itself — the class file does not distinguish
         *  them here, and the field's own descriptor is where that lives. This
         *  reports what the attribute holds and does not reconstruct a type the
         *  attribute did not record. */
        private static String constantJson(Object value) {
            if (value instanceof String text) return JsonOut.string(text);
            // NaN and the infinities are NOT JSON. RFC 8259 has no such
            // literals, and `String.valueOf` writes them as bare tokens —
            // `"value":NaN` — which a conforming parser rejects outright. It
            // went unnoticed because Python's `json` accepts them by default
            // and DuckDB tolerates them, so the whole pipeline stays green
            // while emitting a fact file somebody else's reader refuses. A
            // bundle is published FOR other consumers, so their parser is the
            // one that matters.
            //
            // Written as their Java spelling in a STRING, which is what the
            // field genuinely holds and is the only representation JSON has
            // for it. The field's own descriptor says it is a double, so a
            // reader can tell this apart from a String constant that happens
            // to read "NaN".
            if (value instanceof Double d && (d.isNaN() || d.isInfinite())) {
                return JsonOut.string(String.valueOf(d));
            }
            if (value instanceof Float f && (f.isNaN() || f.isInfinite())) {
                return JsonOut.string(String.valueOf(f));
            }
            // Long and Double are otherwise written plainly: JSON has one
            // number type, and a reader that needs the width has the
            // field's descriptor.
            return String.valueOf(value);
        }

        /** A type- or method-level annotation is a fact of its own (D00 §5, "annotation"). */
        private org.objectweb.asm.AnnotationVisitor annotationVisitor(
                String target, String descriptor, boolean visible) {
            return useCollectingVisitor(descriptor, use -> {
                TreeMap<String, String> fact = new TreeMap<>();
                fact.put("kind", JsonOut.string("annotation"));
                fact.put("document_id", JsonOut.string(documentId));
                fact.put("target", JsonOut.string(target));
                fact.put("use", use);
                fact.put("retention", JsonOut.string(visible ? "runtime" : "class"));
                lines.add(JsonOut.object(fact));
            });
        }

        /** A type-use annotation (JSR 308) is the same `annotation` fact as
         *  {@link #annotationVisitor}, plus the `type_path` ASM hands back through
         *  {@code TypePath}. That path is the only thing that tells
         *  {@code @Nullable List<String>} apart from {@code List<@Nullable String>}
         *  (D00 §5a) — dropping it collapses both to "a Nullable sits somewhere on
         *  this field", which a later task cannot attach to the right reference.
         *
         *  <p>Read from **both** retention tables: the caller passes {@code visible}
         *  from whichever of {@code RuntimeVisibleTypeAnnotations} or
         *  {@code RuntimeInvisibleTypeAnnotations} ASM is currently walking.
         *  JSpecify's annotations are {@code RUNTIME}; {@code javax.annotation.Nullable}
         *  and the JetBrains spellings are mostly {@code CLASS} — a module compiled
         *  over a decade carries several spellings at different retentions, and
         *  reading only one table silently misses the others. */
        private org.objectweb.asm.AnnotationVisitor typeAnnotationVisitor(
                String target, org.objectweb.asm.TypePath typePath, String descriptor, boolean visible) {
            // null renders as "the outer type" per the TypePath contract, not as
            // the four-character string "null".
            String typePathString = typePath == null ? "" : String.valueOf(typePath);
            return useCollectingVisitor(descriptor, use -> {
                TreeMap<String, String> fact = new TreeMap<>();
                fact.put("kind", JsonOut.string("annotation"));
                fact.put("document_id", JsonOut.string(documentId));
                fact.put("target", JsonOut.string(target));
                fact.put("use", use);
                fact.put("retention", JsonOut.string(visible ? "runtime" : "class"));
                fact.put("type_path", JsonOut.string(typePathString));
                lines.add(JsonOut.object(fact));
            });
        }

        /** A parameter-level annotation is not a fact: it attaches inline on the
         *  parameter's entry in the signature (D00 §5a — "annotations attach without
         *  the parameter needing a symbol of its own"). */
        private org.objectweb.asm.AnnotationVisitor parameterAnnotationVisitor(
                String descriptor, List<String> sink) {
            return useCollectingVisitor(descriptor, sink::add);
        }

        /** A method's type-use annotation attaches the same way — inline on the
         *  return type or the matching parameter's entry, never a flat fact —
         *  but unlike a declaration-level parameter annotation it also carries
         *  `retention` and `type_path`: D00 §5a's per-reference value is what
         *  tells `@Nullable List<String>` apart from `List<@Nullable String>`,
         *  and both retention tables land here (see {@link #typeAnnotationVisitor}). */
        private org.objectweb.asm.AnnotationVisitor typeAnnotationEntryVisitor(
                org.objectweb.asm.TypePath typePath, String descriptor, boolean visible, List<String> sink) {
            String typePathString = typePath == null ? "" : String.valueOf(typePath);
            return useCollectingVisitor(descriptor, use -> {
                TreeMap<String, String> entry = new TreeMap<>();
                entry.put("use", use);
                entry.put("retention", JsonOut.string(visible ? "runtime" : "class"));
                entry.put("type_path", JsonOut.string(typePathString));
                sink.add(JsonOut.object(entry));
            });
        }

        /** Collects one annotation's argument values and hands the finished
         *  {@code {"annotation":...,"args":{...}}} JSON to {@code onUse}. */
        private org.objectweb.asm.AnnotationVisitor useCollectingVisitor(
                String descriptor, java.util.function.Consumer<String> onUse) {
            return useCollectingVisitor(descriptor, 0, onUse);
        }

        /** How many levels of annotation may nest BELOW the outermost one before
         *  the collector stops descending. The outermost annotation is depth 0,
         *  so {@code @RabbitListener(bindings = @QueueBinding(value = @Queue(…)))}
         *  reaches depth 2 and the deepest shape in the estate
         *  ({@code …@Queue(arguments = @Argument(…))}) reaches depth 3.
         *
         *  <p>The Java language bounds this on its own — javac rejects a cyclic
         *  annotation element type, so a chain cannot revisit a type and is
         *  bounded by the number of distinct annotation types written — but the
         *  extractor reads CLASS FILES, which need not have come from javac. A
         *  hand-built or corrupt one can nest to any depth, and an unbounded
         *  recursion here is a StackOverflowError in the middle of a scan rather
         *  than a fact. Five is comfortably past the deepest real shape and far
         *  short of any stack limit. */
        private static final int MAX_NESTED_ANNOTATION_DEPTH = 5;

        /** {@code depth} is this annotation's own nesting level, 0 for the
         *  outermost. Below {@link #MAX_NESTED_ANNOTATION_DEPTH} a nested
         *  annotation is collected recursively into the SAME
         *  {@code {"annotation":…,"args":{…}}} shape the outer one uses (D00 §5a's
         *  literal model, extended by capability 9.16 rather than duplicated);
         *  at the bound it becomes
         *  {@code {"annotation":…,"unresolved":"depth_limit"}} — the type is real
         *  evidence read off the descriptor and is kept, the arguments were never
         *  read and so no {@code args} key is written at all. An EMPTY
         *  {@code args} would be a silent truncation: indistinguishable from an
         *  annotation genuinely written with no arguments (GUIDELINES §8). */
        private org.objectweb.asm.AnnotationVisitor useCollectingVisitor(
                String descriptor, int depth, java.util.function.Consumer<String> onUse) {
            String annotation = Type.getType(descriptor).getInternalName() + "#";
            TreeMap<String, String> args = new TreeMap<>();
            return new org.objectweb.asm.AnnotationVisitor(Opcodes.ASM9) {
                @Override public void visit(String name, Object value) {
                    args.put(name == null ? "value" : name, literal(value));
                }
                @Override public void visitEnum(String name, String descriptor, String constant) {
                    args.put(name == null ? "value" : name, enumReference(descriptor, constant));
                }
                @Override public org.objectweb.asm.AnnotationVisitor visitAnnotation(
                        String name, String descriptor) {
                    String key = name == null ? "value" : name;
                    return nestedUseVisitor(descriptor, depth, use -> args.put(key, use));
                }
                @Override public org.objectweb.asm.AnnotationVisitor visitArray(String name) {
                    List<String> items = new ArrayList<>();
                    return new org.objectweb.asm.AnnotationVisitor(Opcodes.ASM9) {
                        @Override public void visit(String ignored, Object value) {
                            items.add(literal(value));
                        }
                        @Override public void visitEnum(
                                String ignored, String descriptor, String constant) {
                            items.add(enumReference(descriptor, constant));
                        }
                        // An ARRAY of annotations, which is what javac folds two or
                        // more of a @Repeatable annotation into: `@Scheduled` twice
                        // on one method compiles to a single `@Schedules({…,…})`, so
                        // without this override a method with two schedules carries
                        // no trigger at all while a method with one carries its own.
                        @Override public org.objectweb.asm.AnnotationVisitor visitAnnotation(
                                String ignored, String descriptor) {
                            return nestedUseVisitor(descriptor, depth, items::add);
                        }
                        @Override public void visitEnd() {
                            args.put(name == null ? "value" : name, JsonOut.array(items));
                        }
                    };
                }
                @Override public void visitEnd() {
                    TreeMap<String, String> use = new TreeMap<>();
                    use.put("annotation", JsonOut.string(annotation));
                    use.put("args", JsonOut.object(args));
                    onUse.accept(JsonOut.object(use));
                }
            };
        }

        /** A single UNNAMED annotation value — what `AnnotationDefault` carries.
         *
         *  <p>The same grammar an annotation ARGUMENT already uses (scalar, enum
         *  reference, nested use, or an array of those), reached through the
         *  same helpers, because a default and an argument are the same kind of
         *  value written in two places. ASM delivers it with a null name, which
         *  is why this cannot simply reuse `useCollectingVisitor`: that one is
         *  built around a whole annotation USE and its named arguments. */
        private org.objectweb.asm.AnnotationVisitor defaultValueVisitor(
                java.util.function.Consumer<String> onValue) {
            return new org.objectweb.asm.AnnotationVisitor(Opcodes.ASM9) {
                @Override public void visit(String ignored, Object value) {
                    onValue.accept(literal(value));
                }
                @Override public void visitEnum(String ignored, String descriptor, String constant) {
                    onValue.accept(enumReference(descriptor, constant));
                }
                @Override public org.objectweb.asm.AnnotationVisitor visitAnnotation(
                        String ignored, String descriptor) {
                    return nestedUseVisitor(descriptor, 0, onValue);
                }
                @Override public org.objectweb.asm.AnnotationVisitor visitArray(String ignored) {
                    List<String> items = new ArrayList<>();
                    return new org.objectweb.asm.AnnotationVisitor(Opcodes.ASM9) {
                        @Override public void visit(String i2, Object value) {
                            items.add(literal(value));
                        }
                        @Override public void visitEnum(String i2, String d, String constant) {
                            items.add(enumReference(d, constant));
                        }
                        @Override public org.objectweb.asm.AnnotationVisitor visitAnnotation(
                                String i2, String d) {
                            return nestedUseVisitor(d, 0, items::add);
                        }
                        @Override public void visitEnd() {
                            onValue.accept(JsonOut.array(items));
                        }
                    };
                }
            };
        }

        /** One nested annotation value, at {@code parentDepth + 1}. Returning
         *  {@code null} at the bound is ASM's own "skip this sub-tree" contract —
         *  the value is already recorded as unresolved by then, so nothing is lost
         *  silently. */
        private org.objectweb.asm.AnnotationVisitor nestedUseVisitor(
                String descriptor, int parentDepth, java.util.function.Consumer<String> onUse) {
            if (parentDepth + 1 > MAX_NESTED_ANNOTATION_DEPTH) {
                TreeMap<String, String> use = new TreeMap<>();
                use.put("annotation",
                    JsonOut.string(Type.getType(descriptor).getInternalName() + "#"));
                use.put("unresolved", JsonOut.string("depth_limit"));
                onUse.accept(JsonOut.object(use));
                return null;
            }
            return useCollectingVisitor(descriptor, parentDepth + 1, onUse);
        }

        /** ASM reports an enum-valued argument through {@code visitEnum}, never
         *  {@code visit}, so it needs its own override at both levels: a scalar
         *  argument and an element inside an array. D00 §5a's literal model calls
         *  for an enum reference, so it carries its owning type rather than the
         *  bare constant name. Dropping it would make {@code @RequestMapping} with
         *  no method indistinguishable from one that names every method. */
        private String enumReference(String descriptor, String constant) {
            return JsonOut.string(
                Type.getType(descriptor).getInternalName() + "#" + constant + ".");
        }

        private String literal(Object value) {
            if (value instanceof String text) return JsonOut.string(text);
            // NaN and the infinities are NOT JSON (RFC 8259 has no such
            // literals), so `String.valueOf` would write a bare token that a
            // conforming reader refuses. Quoted, as `constantJson` does — the
            // descriptor says the field is a double, so this cannot be confused
            // with a String that happens to read "NaN".
            if (value instanceof Double d && (d.isNaN() || d.isInfinite())) {
                return JsonOut.string(String.valueOf(d));
            }
            if (value instanceof Float f && (f.isNaN() || f.isInfinite())) {
                return JsonOut.string(String.valueOf(f));
            }
            if (value instanceof Boolean || value instanceof Number) return String.valueOf(value);
            if (value instanceof Type type) return JsonOut.string(type.getInternalName() + "#");
            // A PRIMITIVE array. ASM does not call `visitArray` for one — it
            // hands over the whole `int[]`/`long[]`/`char[]`/`boolean[]` here —
            // and the fallthrough below stringified it, producing `[I@2a70a3d8`:
            // an identity hash that DIFFERS ON EVERY RUN. That is a byte-stability
            // violation (NFR-1), and it is already committed in a golden fixture.
            // Expanded into the array grammar the annotation's own values use.
            if (value != null && value.getClass().isArray()) {
                List<String> items = new ArrayList<>();
                int length = java.lang.reflect.Array.getLength(value);
                for (int i = 0; i < length; i++) {
                    items.add(literal(java.lang.reflect.Array.get(value, i)));
                }
                return JsonOut.array(items);
            }
            return JsonOut.string(String.valueOf(value));
        }

        /** JVMS 4.7.5 `Exceptions` as symbols, or null when the method declares none —
         *  which is most of them, and an empty list on every one would say nothing. */
        private String throwsJson(String[] exceptions) {
            if (exceptions == null || exceptions.length == 0) return null;
            List<String> declared = new ArrayList<>();
            for (String thrown : exceptions) declared.add(JsonOut.string(symbolOf(thrown + "#")));
            return JsonOut.array(declared);
        }

        private String signatureJson(String methodName, String descriptor, String genericSignature,
                                      String[] parameterNames, int[] parameterFlags,
                                      String declaredThrows,
                                      List<List<String>> parameterAnnotations,
                                      List<List<String>> parameterTypeAnnotations,
                                      List<String> returnTypeAnnotations,
                                      KotlinDefaultBridge defaultBridge) {
            Type[] argumentTypes = Type.getArgumentTypes(descriptor);
            // W5: the descriptor has already erased every type argument and every type
            // variable by the time it reaches here — `List<String>` is `List`, and `T` is
            // whatever it happens to erase to. The `Signature` attribute is the only place
            // either survives, and it was read for the RETURN type and for fields while
            // parameters kept taking the erased one.
            List<TypeRefs.Node> genericParameters = TypeRefs.parametersFromSignature(genericSignature);
            int[] genericOf = alignedSignature(argumentTypes.length, genericParameters.size(),
                                                parameterFlags);
            // Q2's `suspend fun` obligation. kotlinc erases a suspending function's
            // declared return to `Object` and appends a `Continuation` parameter nobody
            // wrote, so the facts published a parameter absent from the source and a
            // return type absent from the language. The declared type survives as that
            // `Continuation`'s own type argument and its NULLABILITY survives only in
            // `@kotlin.Metadata` — measured: `fetch(String): KotlinSample` and
            // `maybe(String): KotlinSample?` compile to one descriptor, one signature
            // hash, and kotlinc stamps `@Nullable` on BOTH, so no annotation separates
            // them either.
            //
            // Read back, a `suspend fun` is an ordinary function: the trailing parameter
            // is dropped and the return is the type the author declared. Nothing
            // downstream has to know coroutines exist, which is the whole point — the
            // synthetic is symmetric, appearing identically here and at every call site,
            // and the SYMBOL's identity hashes the raw descriptor (`disambiguatorOf`),
            // so dropping it here cannot move an identity or break descriptor matching.
            // Null for every Java method and for any Kotlin one `@Metadata` did not name —
            // Java's rule still applies to those, and it is right for them.
            //
            // `OI-81`: a `$default` bridge is one metadata never names — it is compiler
            // output, not a declaration — so `copy` read `nullable: false` beside a
            // `copy$default` reading `true`, for one declared type. The bridge is read
            // under its SIBLING's key: the function it stands for declared its return
            // and its parameters, and the bridge's own slots are the sibling's
            // (measured, kotlinc 2.2.0: `greet$default` is
            // `(Ldev/sextant/extractor/KotlinDefaultsSample;Ljava/lang/String;ZILjava/lang/Object;)Ljava/lang/String;`
            // — receiver, the function's slots, an `int` mask per 32 parameters, an
            // `Object` marker). The receiver, masks and marker are nobody's declaration
            // and keep Java's rule, which is what `defaultBridge.receiverSlots()` and
            // `declaredSlots()` bound below. The `Continuation` a suspend sibling's
            // bridge carries sits INSIDE the declared range and is subtracted from it
            // the way the sibling's own read drops it, so the slots still line up.
            // A bridge whose sibling could not be settled (`siblingKey() == null`) is read
            // under its own key, which metadata never holds: Java's rule everywhere.
            String methodKey = defaultBridge == null || defaultBridge.siblingKey() == null
                ? methodName + descriptor
                : defaultBridge.siblingKey();
            Boolean kotlinReturnNullable = kotlinNullability.returnNullable().get(methodKey);
            // TWO conjuncts, and each rules out a measured class of wrong answer.
            //
            // `suspendMethods` is metadata's own statement. The structural test alone —
            // "the last parameter is a `Continuation`" — fires on a Java method that
            // declares one, on a Kotlin `fun` that merely takes one, and above all on the
            // `<init>` of every generated coroutine state-machine class, which would then
            // stop reporting `returns: void#`.
            //
            // The DESCRIPTOR's own last slot has to be the `Continuation` as well, because
            // the truncation below removes a descriptor slot while the recovery reads a
            // SIGNATURE position, and those two coincide only when the signature is
            // full-length. It is routinely not: an inner class's constructor carries the
            // enclosing instance in its descriptor and omits it from its signature, so
            // trusting the signature alone deleted the author's own declared parameter and
            // kept the synthetic — the exact inversion W5's alignment exists to prevent.
            boolean continuationLast = argumentTypes.length > 0
                && argumentTypes[argumentTypes.length - 1].getSort() == Type.OBJECT
                && "kotlin/coroutines/Continuation".equals(
                    argumentTypes[argumentTypes.length - 1].getInternalName());
            // `OI-80`: the `Continuation`'s type argument spells `Int` as `Integer`, because
            // a type argument cannot be a primitive. Metadata's classifier and nullability
            // together say whether the source wrote the primitive — `Int?` did not.
            String coroutineReturn =
                kotlinNullability.suspendMethods().contains(methodKey) && continuationLast
                    ? TypeRefs.coroutineReturnFromSignature(genericSignature, kotlinReturnNullable,
                                                            kotlinNullability.primitiveReturn(methodKey))
                    : null;
            int declaredParameters = coroutineReturn == null
                ? argumentTypes.length
                : argumentTypes.length - 1;
            // `OI-82`, the PARAMETER half of `G-63`. Kotlin states a parameter's
            // nullability in its TYPE, and Java's rule — every reference permits null —
            // is wrong for every Kotlin declaration that does not write `?`. Applied only
            // where metadata's parameter count matches the slots this rule is confident
            // about, because metadata lists what the SOURCE declared while the descriptor
            // may carry synthetics, and those are not always trailing: javac puts an
            // inner class's enclosing instance and an enum's name/ordinal FIRST, a local
            // class's captures LAST, and kotlinc appends a suspend function's
            // `Continuation` (already removed from the count above). A partial alignment
            // would move a nullability onto the wrong parameter, which is worse than not
            // reading it, so where the counts differ every parameter keeps Java's rule.
            List<KmType> kotlinParameterTypes = kotlinNullability.parameterTypes().get(methodKey);
            // The descriptor slots metadata's list is laid against: every declared one for
            // an ordinary method; for a `$default` bridge, the sibling's own slots past
            // the receiver, less the `Continuation` a suspend sibling's bridge still
            // carries there (its own read dropped it from `declaredParameters` above; the
            // bridge's last slot is the marker, so `continuationLast` cannot).
            int alignedFrom = defaultBridge == null ? 0 : defaultBridge.receiverSlots();
            int alignedCount = defaultBridge == null
                ? declaredParameters
                : defaultBridge.declaredSlots()
                    - (kotlinNullability.suspendMethods().contains(methodKey) ? 1 : 0);
            boolean parametersAligned = kotlinParameterTypes != null
                && kotlinParameterTypes.size() == alignedCount;
            List<String> parameters = new ArrayList<>();
            for (int i = 0; i < declaredParameters; i++) {
                TreeMap<String, String> parameter = new TreeMap<>();
                parameter.put("annotations", JsonOut.array(parameterAnnotations.get(i)));
                parameter.put("name", parameterNames[i] == null ? "null" : JsonOut.string(parameterNames[i]));
                // The erased descriptor type wherever the alignment declined to answer.
                // It is never wrong, only less specific.
                TypeRefs.Node type = genericOf[i] >= 0
                    ? genericParameters.get(genericOf[i])
                    : TypeRefs.nodeFromType(argumentTypes[i]);
                if (parametersAligned && i >= alignedFrom && i < alignedFrom + alignedCount) {
                    type = TypeRefs.withDeclaredNullability(
                        type, kotlinParameterTypes.get(i - alignedFrom));
                }
                parameter.put("type", TypeRefs.toJson(type));
                // The DESCRIPTOR's own symbol for this position, kept beside the
                // signature's rather than replaced by it.
                //
                // Reading the signature is what lets `List<String>` keep `String`, but it
                // also makes a parameter declared `T` report the symbol `T` — and a type
                // variable's name is scoped to the declaration that introduced it. An
                // interface calls it `E` where its implementation calls it `T`, for one
                // method. Four consumers compare parameter symbols ACROSS declarations —
                // an overload dedup key, a bridge-recognition rule, a supertype selector
                // matched against catalog-declared types, and a payload-type lookup that
                // reads annotations off the named type — and every one of them needs a
                // symbol that means the same thing in both places. Emitting only the
                // signature's answer did not change that symbol so much as DELETE the one
                // they were using, with no way back to it from the fact.
                //
                // Written on EVERY parameter, not only where it differs. A JSON path
                // wildcard drops elements whose key is missing (measured in DuckDB), so a
                // sparse key yields a SHORTER list and silently misaligns against the
                // parameter it belongs to — the same class of defect as the descriptor /
                // signature skew above.
                parameter.put("erased_symbol",
                    JsonOut.string(TypeRefs.descriptorName(argumentTypes[i])));
                // Type-use annotations on this parameter's type — distinct from
                // "annotations" above, which are declaration-level (D00 §5a).
                parameter.put("type_annotations", JsonOut.array(parameterTypeAnnotations.get(i)));
                parameters.add(JsonOut.object(parameter));
            }
            String generic = TypeRefs.returnFromSignature(genericSignature, kotlinReturnNullable);
            String returns = coroutineReturn != null
                ? coroutineReturn
                : generic != null
                    ? generic
                    // `fieldRef` with no signature is `fromType` plus the override —
                    // the erased descriptor type, which is where a method with no
                    // `Signature` attribute has always got its return.
                    : TypeRefs.fieldRef(Type.getReturnType(descriptor), null, kotlinReturnNullable);
            TreeMap<String, String> signature = new TreeMap<>();
            signature.put("parameters", JsonOut.array(parameters));
            signature.put("returns", returns);
            signature.put("return_type_annotations", JsonOut.array(returnTypeAnnotations));
            // `throws` belongs to the SIGNATURE rather than beside it: it is part of what
            // a caller must handle to call this method, which is what a signature is.
            // Omitted entirely when the method declares none — most do not.
            if (declaredThrows != null) signature.put("throws", declaredThrows);
            return JsonOut.object(signature);
        }

        /** The DESCRIPTOR indices of the parameters a source file actually declared, in
         *  order — {@code slots[i]} is where the i-th declared parameter sits. Null when
         *  {@code MethodParameters} (JVMS 4.7.24) is absent or does not cover every slot,
         *  which is not the same as an empty result and must not be treated as one.
         *
         *  <p>`ACC_MANDATED` marks a parameter the language declares implicitly — an inner
         *  class's enclosing instance; `ACC_SYNTHETIC` marks one the compiler invented — an
         *  enum's name and ordinal, a local class's captured values.
         *
         *  <p>**They are not, however, "exactly the set the short tables omit", and this
         *  javadoc said so until a record proved otherwise.** `ACC_MANDATED` means
         *  IMPLICITLY DECLARED, which is not the same claim. A record's COMPACT canonical
         *  constructor has every slot flagged mandated — the constructor is what is
         *  implicit, not its parameters — while its tables omit nothing (measured: a
         *  two-parameter descriptor, both mandated, a full-length parameter-annotation
         *  table and a type annotation at `param_index=1`). So an EMPTY result here means
         *  "the flags say nothing useful", never "this method declares no parameters", and
         *  a caller must not read it as the latter. Each caller states which it does.
         *
         *  <p>ONE helper for every such table, and that is the point of it. Three
         *  attributes are indexed by declared parameters rather than by descriptor slots —
         *  {@code Signature} (4.7.9.1), {@code Runtime[In]VisibleParameterAnnotations}
         *  (4.7.18) and {@code METHOD_FORMAL_PARAMETER} type annotations (4.7.20.1) — and
         *  each of them was aligned by its own arithmetic on counts. Counting cannot answer
         *  it: javac puts an inner class's enclosing instance and an enum's name/ordinal
         *  FIRST but a local class's captures LAST, so the same difference-of-two-counts
         *  means opposite things. The flags say which slots they are, once, for all three. */
        private static int[] sourceDeclaredSlots(int[] parameterFlags) {
            List<Integer> declared = new ArrayList<>();
            for (int slot = 0; slot < parameterFlags.length; slot++) {
                // -1 is the absent attribute, and it is not a flag value: with nothing
                // written about a slot there is nothing to align by.
                if (parameterFlags[slot] < 0) return null;
                if ((parameterFlags[slot] & (Opcodes.ACC_MANDATED | Opcodes.ACC_SYNTHETIC)) == 0) {
                    declared.add(slot);
                }
            }
            int[] slots = new int[declared.size()];
            for (int i = 0; i < slots.length; i++) slots[i] = declared.get(i);
            return slots;
        }

        /** Which entry of the {@code Signature} attribute's parameter list — if any —
         *  belongs to each DESCRIPTOR parameter. {@code -1} means "no answer": the caller
         *  keeps the erased type there.
         *
         *  <p>The two lists are not always the same length. JVMS 4.7.9.1 lets a signature
         *  omit parameters that are implicitly declared, and a compiler may also leave out
         *  ones it synthesised. **The difference in COUNT does not say which slots those
         *  are**, and this is the correction to a rule that was written here as though it
         *  did. Measured, javac 26:
         *
         *  <ul>
         *    <li>an inner class's constructor gets the enclosing instance FIRST —
         *        {@code (LOuter;Ljava/util/List;)V} against {@code (Ljava/util/List<…>;)V};
         *    <li>an enum's constructor gets name and ordinal FIRST;
         *    <li>but a LOCAL class that captures gets its captures LAST —
         *        {@code (Ljava/util/List;Ljava/lang/StringBuilder;I)V} against the same
         *        one-parameter {@code (Ljava/util/List<…>;)V}.
         *  </ul>
         *
         *  <p>Aligning from the end is right for the first two and wrong for the third: it
         *  puts {@code List<String>} on an {@code int}, and the fact is WELL FORMED, so
         *  nothing downstream can notice. Deriving nothing would have been acceptable
         *  (§8.1 rule 2); deriving that is not.
         *
         *  <p>{@code MethodParameters} (JVMS 4.7.24) is what actually distinguishes them,
         *  and §8.1 rule 5 says to follow the provider where it makes a distinction rather
         *  than infer one: a parameter flagged {@code ACC_MANDATED} or {@code ACC_SYNTHETIC}
         *  is exactly one the signature may omit, wherever it sits. So the signature's
         *  entries are laid onto the slots flagged as neither, in order.
         *
         *  <p>The attribute is not always there — measured: a local class in a STATIC
         *  method has no {@code MethodParameters} at all, and it is also the shape with
         *  captures at the end. With the counts disagreeing and nothing saying why, there
         *  is no honest alignment, so every parameter keeps its erased type. Less specific,
         *  never wrong. */
        private int[] alignedSignature(int declared, int generic, int[] parameterFlags) {
            int[] genericOf = new int[declared];
            java.util.Arrays.fill(genericOf, -1);
            if (generic == 0) return genericOf;
            // The overwhelming majority: the signature names every parameter, so the
            // question of which ones it dropped does not arise.
            if (generic == declared) {
                for (int i = 0; i < declared; i++) genericOf[i] = i;
                return genericOf;
            }
            int[] slots = sourceDeclaredSlots(parameterFlags);
            // No attribute to align by, or a disagreement its flags do not explain.
            // Nothing invented on top of either.
            if (slots == null || slots.length != generic) return genericOf;
            for (int i = 0; i < generic; i++) genericOf[slots[i]] = i;
            return genericOf;
        }

        /** W5: the formal type parameters a class or method declares, with their bounds
         *  (D00 §5a) — null, never `[]`, when the declaration has none, so `emit` leaves
         *  the key off entirely rather than writing an empty list onto every fact.
         *
         *  <p>One helper for both, because they are one question: `class Box<T>` and
         *  `<K> Map<K,V> pair(K)` declare type parameters by the identical signature
         *  grammar, and a consumer binding `T` should not have to ask which construct it
         *  is holding first. */
        private String typeParametersJson(String genericSignature) {
            List<String> declared = TypeRefs.typeParametersFromSignature(genericSignature);
            return declared.isEmpty() ? null : JsonOut.array(declared);
        }

        /** A field has no parameter list, only the type reference D00 §5a says it
         *  carries "the same way" a return type does. {@code TypeRefs.fieldRef} reads
         *  the field's generic {@code Signature} when present, so `List<CustomerRef>`
         *  keeps `CustomerRef` rather than erasing to plain `List` (D00 §5a) — the
         *  erased {@code type} is still passed as the fallback for a field whose
         *  descriptor carries no type argument to lose, and never gets one.
         *
         *  <p>{@code kotlinNullable} overrides only the top-level nullability, never a
         *  nested type argument: Kotlin's `@Metadata` resolves a property's own
         *  nullability, not its generic arguments' (out of this task's scope either
         *  way, same as it is for an unannotated Java field's arguments). */
        private String fieldSignatureJson(Type type, String genericSignature, Boolean kotlinNullable) {
            TreeMap<String, String> signature = new TreeMap<>();
            signature.put("returns", TypeRefs.fieldRef(type, genericSignature, kotlinNullable));
            return JsonOut.object(signature);
        }

        /** D00 §6: the raw @Metadata read stays recoverable behind the extension
         *  namespace even once it has been projected onto the shared field above —
         *  the projection must not be the only place the answer survives. */
        private String kotlinExt(boolean nullable) {
            TreeMap<String, String> kotlin = new TreeMap<>();
            kotlin.put("nullable", String.valueOf(nullable));
            TreeMap<String, String> ext = new TreeMap<>();
            ext.put("kotlin", JsonOut.object(kotlin));
            return JsonOut.object(ext);
        }

        /** The declaration modifiers that decide whether a field reaches a payload at
         *  all, beside `visibility` and in the same language-blind spelling: `static`
         *  is a value bound to the type rather than to an instance, `transient` a
         *  declaration the language marks as not serialized. Neither is nullability
         *  and neither is visibility — a public constant is as public as any field
         *  and still on no payload — so a consumer filtering on what it already had
         *  would have to guess.
         *
         *  <p>Both keys are always written, never only the true one: an absent key
         *  cannot be told apart from a scanner that does not report the modifier. */
        private String modifiersJson(int access) {
            TreeMap<String, String> modifiers = new TreeMap<>();
            modifiers.put("static", String.valueOf((access & Opcodes.ACC_STATIC) != 0));
            modifiers.put("transient", String.valueOf((access & Opcodes.ACC_TRANSIENT) != 0));
            // W7. `final` on a field is what tells a constant apart from a mutable
            // one, and `volatile` is a declaration about concurrency the language
            // makes and nothing here could read.
            modifiers.put("final", String.valueOf((access & Opcodes.ACC_FINAL) != 0));
            modifiers.put("volatile", String.valueOf((access & Opcodes.ACC_VOLATILE) != 0));
            // JVMS 4.7.15 `Deprecated`, which ASM folds into the access flags. A
            // declaration the language itself marks as on its way out — distinct from
            // `@Deprecated`, the annotation, which a catalog reads separately: a class
            // file can carry either, both, or neither.
            modifiers.put("deprecated", String.valueOf((access & Opcodes.ACC_DEPRECATED) != 0));
            return JsonOut.object(modifiers);
        }

        /** A METHOD's declaration modifiers — the same `modifiers` slot, a different
         *  pair of keys, because the two constructs do not share a vocabulary.
         *  {@code transient} is deliberately absent: its bit ({@code 0x0080}) is
         *  {@code ACC_VARARGS} on a method, so writing it here would report every
         *  varargs method as not-serialized — a modifier nobody declared.
         *
         *  <p>Both keys answer the same question for a consumer enumerating a
         *  class's exposed members: {@code static} is bound to the type rather than
         *  to an instance, and {@code synthetic} is compiler machinery nobody wrote
         *  — a covariant-return bridge, a lambda body, an accessor for a nested
         *  class's private member. Unlike {@code visitField}, {@code visitMethod}
         *  does NOT skip synthetic declarations (the inheritance walk's own bridge
         *  rule depends on seeing them), so the flag is the only way a later pass
         *  can tell one from a method a human declared. {@code ACC_BRIDGE} is folded
         *  into it because a bridge is synthetic in every sense that matters here
         *  and javac sets the two together on the same declaration. */
        private String methodModifiersJson(int access) {
            TreeMap<String, String> modifiers = new TreeMap<>();
            modifiers.put("static", String.valueOf((access & Opcodes.ACC_STATIC) != 0));
            modifiers.put("synthetic", String.valueOf(
                (access & (Opcodes.ACC_SYNTHETIC | Opcodes.ACC_BRIDGE)) != 0));
            // W7's six. `abstract` first, because without it an interface's `default`
            // method and its abstract ones emitted IDENTICAL modifiers — a consumer
            // asking "does this interface declare behaviour" had nothing to read.
            modifiers.put("abstract", String.valueOf((access & Opcodes.ACC_ABSTRACT) != 0));
            // `varargs` is the flag capability 9.15 needs: `f(String...)` and
            // `f(String[])` compile to the same descriptor, so a call passing three
            // strings and one passing `new String[]{…}` were indistinguishable.
            modifiers.put("varargs", String.valueOf((access & Opcodes.ACC_VARARGS) != 0));
            modifiers.put("final", String.valueOf((access & Opcodes.ACC_FINAL) != 0));
            modifiers.put("native", String.valueOf((access & Opcodes.ACC_NATIVE) != 0));
            modifiers.put("synchronized", String.valueOf((access & Opcodes.ACC_SYNCHRONIZED) != 0));
            // JVMS 4.7.15 `Deprecated`, which ASM folds into the access flags. A
            // declaration the language itself marks as on its way out — distinct from
            // `@Deprecated`, the annotation, which a catalog reads separately: a class
            // file can carry either, both, or neither.
            modifiers.put("deprecated", String.valueOf((access & Opcodes.ACC_DEPRECATED) != 0));
            return JsonOut.object(modifiers);
        }

        private void emit(String symbol, String constructKind, String enclosing, String signature, int access) {
            emit(symbol, constructKind, enclosing, signature, access, null, null, null, null);
        }

        private void emit(String symbol, String constructKind, String enclosing, String signature, int access,
                           String ext, String modifiers) {
            emit(symbol, constructKind, enclosing, signature, access, ext, modifiers, null, null);
        }

        /** The deferred class symbol, inserted at index 0 so the fact stream is
         *  byte-for-byte the order it always was (`symbols.seq` IS that order).
         *  It is emitted HERE rather than in `visit` because the attributes that
         *  answer "what encloses this class" — `EnclosingMethod` and
         *  `InnerClasses` — only arrive afterwards. */
        @Override
        public void visitEnd() {
            // `InnerClasses` supplies the NESTING flags only. It was replacing the
            // class-file flags wholesale, and `emit` derives `visibility` from
            // ACC_PUBLIC — so a PROTECTED nested type, which javac writes as
            // ACC_PUBLIC in the ClassFile and ACC_PROTECTED in this table,
            // flipped from `public` to `other`. Nesting is what this attribute
            // knows; visibility is not its question.
            //
            // (The comment that used to sit here had the mechanism backwards:
            // a PRIVATE nested class is written package-private at the top
            // level, so it is `protected` where the two disagree in the
            // ACC_PUBLIC direction.)
            // A `package-info.class` is not a type either: it is the reserved file
            // class javac compiles a package's ANNOTATIONS onto, and emitting a `class`
            // symbol for it put a type into the graph that no source declares. Its
            // annotation facts stay — `shapes/nullability.py` reads a package-level
            // scope through exactly this target — and only the invented symbol goes.
            // The NAME is not the evidence — a legitimate class can be called
            // `package-info` (Kotlin backticks allow it, and a hyphen is a legal JVM
            // unqualified name). What javac's file class STATES is
            // `ACC_INTERFACE | ACC_SYNTHETIC` with no members at all, and requiring
            // that matters twice over: suppressing the type of a real class would
            // leave its methods behind with an `enclosing` naming a symbol that does
            // not exist, because this runs at `visitEnd` and they are already emitted.
            //
            // Both spellings of the name, so the default package is not a hole — and
            // it is the dangerous one: `shapes/nullability.py` strips `package-info#`
            // to recover the package a scope claims, and in the default package that
            // leaves the module prefix, a prefix of EVERY symbol in the module.
            boolean isPackageFileClass = typeSymbol != null
                && (typeSymbol.endsWith("/package-info#") || typeSymbol.endsWith(" package-info#"))
                && (classAccess & (Opcodes.ACC_INTERFACE | Opcodes.ACC_SYNTHETIC))
                    == (Opcodes.ACC_INTERFACE | Opcodes.ACC_SYNTHETIC);
            if (isPackageFileClass) return;
            // A module descriptor states `ACC_MODULE`, and states it in the bytes
            // rather than in the file name. Matching the name instead silently
            // deleted any class whose file happened to end that way — measured, a
            // Kotlin class named `Xmodule-info` produced zero documents, zero facts
            // and an EMPTY `uncovered`, which is the silent-success hole `Main`'s own
            // comment says was closed. Suppressed here rather than skipped there, so
            // the document is still written and counted.
            if ((classAccess & Opcodes.ACC_MODULE) != 0) return;
            int access = classAccess;
            // The construct kind is read from the class file's OWN access word, not
            // from `nestedAccess`. Measured over javac 21 output for a nested
            // interface, enum, @interface, record and plain class: the two words
            // agree on ACC_INTERFACE, ACC_ENUM and ACC_ANNOTATION, and differ on
            // ACC_RECORD, which only the class file's word carries — ASM synthesises
            // it in `visit` from JVMS 4.7.30's `Record` attribute, and the
            // `InnerClasses` table has no attribute to synthesise it from. Routing
            // the kind through `nestedAccess` therefore reported every NESTED record
            // as `class`: 1,262 of the 1,739 records in the local dependency cache,
            // 73%. `nestedAccess` answers nesting and visibility, which is what
            // JVMS 4.7.6 knows; it does not answer what the type IS.
            emit(typeSymbol, constructKindOf(access), enclosingSymbol, null, access, null,
                 typeModifiersJson(access),
                 TypeRefs.genericSuperclassFromSignature(classSignature),
                 interfaceSymbolsJson(classInterfaces),
                 genericInterfacesJson(classSignature), erasedSuperclassJson(superName), null,
                 typeParametersJson(classSignature), 0, 0,
                 permittedSubclasses.isEmpty() ? null : JsonOut.array(permittedSubclasses));
            // `emit` appends, and this one belongs FIRST — a class's own symbol
            // precedes its members in every fact file, and `symbols.seq` is that
            // order. Moving the appended line is simpler than redirecting where
            // `emit` writes: swapping the destination field left a window where
            // anything else appending during the call would have landed in the
            // wrong list.
            lines.add(0, lines.remove(lines.size() - 1));
        }

        private void emit(String symbol, String constructKind, String enclosing, String signature, int access,
                           String ext, String modifiers, String supertype) {
            emit(symbol, constructKind, enclosing, signature, access, ext, modifiers, supertype, null);
        }

        private void emit(String symbol, String constructKind, String enclosing, String signature, int access,
                           String ext, String modifiers, String supertype, String interfaces) {
            emit(symbol, constructKind, enclosing, signature, access, ext, modifiers, supertype, interfaces,
                 null, null);
        }

        private void emit(String symbol, String constructKind, String enclosing, String signature, int access,
                           String ext, String modifiers, String supertype, String interfaces,
                           String genericInterfaces, String superclass) {
            emit(symbol, constructKind, enclosing, signature, access, ext, modifiers, supertype,
                 interfaces, genericInterfaces, superclass, null);
        }

        private void emit(String symbol, String constructKind, String enclosing, String signature, int access,
                           String ext, String modifiers, String supertype, String interfaces,
                           String genericInterfaces, String superclass, String annotationDefault) {
            emit(symbol, constructKind, enclosing, signature, access, ext, modifiers, supertype,
                 interfaces, genericInterfaces, superclass, annotationDefault, null);
        }

        private void emit(String symbol, String constructKind, String enclosing, String signature, int access,
                           String ext, String modifiers, String supertype, String interfaces,
                           String genericInterfaces, String superclass, String annotationDefault,
                           String typeParameters) {
            // 0/0 — no lines stated. Every construct but a method reaches here:
            // a class carries no `LineNumberTable` of its own (JVMS 4.7.12 lives
            // inside `Code`), and neither does a field.
            emit(symbol, constructKind, enclosing, signature, access, ext, modifiers, supertype,
                 interfaces, genericInterfaces, superclass, annotationDefault, typeParameters, 0, 0);
        }

        private void emit(String symbol, String constructKind, String enclosing, String signature, int access,
                           String ext, String modifiers, String supertype, String interfaces,
                           String genericInterfaces, String superclass, String annotationDefault,
                           String typeParameters, int lineStart, int lineEnd) {
            emit(symbol, constructKind, enclosing, signature, access, ext, modifiers, supertype,
                 interfaces, genericInterfaces, superclass, annotationDefault, typeParameters,
                 lineStart, lineEnd, null);
        }

        private void emit(String symbol, String constructKind, String enclosing, String signature, int access,
                           String ext, String modifiers, String supertype, String interfaces,
                           String genericInterfaces, String superclass, String annotationDefault,
                           String typeParameters, int lineStart, int lineEnd, String permits) {
            emit(symbol, constructKind, enclosing, signature, access, ext, modifiers, supertype,
                 interfaces, genericInterfaces, superclass, annotationDefault, typeParameters,
                 lineStart, lineEnd, permits, null);
        }

        private void emit(String symbol, String constructKind, String enclosing, String signature, int access,
                           String ext, String modifiers, String supertype, String interfaces,
                           String genericInterfaces, String superclass, String annotationDefault,
                           String typeParameters, int lineStart, int lineEnd, String permits,
                           String bridgeOf) {
            TreeMap<String, String> fact = new TreeMap<>();
            fact.put("kind", JsonOut.string("symbol"));
            fact.put("document_id", JsonOut.string(documentId));
            fact.put("symbol", JsonOut.string(symbol));
            fact.put("construct_kind", JsonOut.string(constructKind));
            fact.put("enclosing", enclosing == null ? "null" : JsonOut.string(enclosing));
            fact.put("signature", signature == null ? "null" : signature);
            fact.put("visibility", JsonOut.string((access & Opcodes.ACC_PUBLIC) != 0 ? "public" : "other"));
            fact.put("line_start", String.valueOf(lineStart));
            fact.put("line_end", String.valueOf(lineEnd));
            if (ext != null) fact.put("ext", ext);
            if (modifiers != null) fact.put("modifiers", modifiers);
            if (supertype != null) fact.put("supertype", supertype);
            if (interfaces != null) fact.put("interfaces", interfaces);
            if (genericInterfaces != null) fact.put("generic_interfaces", genericInterfaces);
            if (superclass != null) fact.put("superclass", superclass);
            if (annotationDefault != null) fact.put("annotation_default", annotationDefault);
            // W5. Emitted only when the declaration HAS formal type parameters, the same
            // "nothing generic, nothing captured" rule `supertype` and `generic_interfaces`
            // already follow — most classes and nearly every method declare none, and an
            // empty list on all of them says nothing with a key on every fact.
            if (typeParameters != null) fact.put("type_parameters", typeParameters);
            // Emitted only for a SEALED type — every other class permits nothing, and an
            // empty list on all of them says nothing with a key on every fact (the same
            // rule `supertype` and `generic_interfaces` follow).
            if (permits != null) fact.put("permits", permits);
            // `OI-81`: only a Kotlin `$default` bridge carries this — the name of the
            // function it stands for, beside the `synthetic: true` its modifiers already
            // say. Absent on every other fact, the same "nothing to say, no key" rule as
            // `permits`. The bridge stays published as its own symbol: a call site names
            // it by its own descriptor, and this is what lets a consumer follow it back.
            if (bridgeOf != null) fact.put("bridge_of", bridgeOf);
            // On the TYPE's own fact, never on its members — these are class-level
            // attributes, and `emit` is shared with fields and methods. Gated on the
            // construct being a type rather than on `class` specifically: a nested
            // interface, record, enum or annotation has a nest host just the same.
            if (isType(constructKind)) {
                if (nestHost != null) fact.put("nest_host", JsonOut.string(nestHost));
                if (!nestMembers.isEmpty()) fact.put("nest_members", JsonOut.array(nestMembers));
                if (!unreadAttributes.isEmpty()) {
                    fact.put("unread_attributes", JsonOut.array(List.copyOf(unreadAttributes)));
                }
            }
            lines.add(JsonOut.object(fact));
        }
    }
}
