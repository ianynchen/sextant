package dev.sextant.extractor;

import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.List;
import java.util.TreeMap;
import java.util.function.Consumer;
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
        List<String> lines = new ArrayList<>();
        new ClassReader(classBytes)
            .accept(new Visitor(lines, documentId, onKotlinMetadataUnsupported), ClassReader.SKIP_FRAMES);
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
        private String[] classInterfaces;
        private String enclosingSymbol;
        private Integer nestedAccess;
        // Populated from @Metadata before any field is visited (ASM visits class-level
        // annotations before fields — see visitAnnotation below); empty for every
        // non-Kotlin class, which leaves Java's rule as the only source.
        private java.util.Map<String, Boolean> kotlinNullability = KotlinNullability.NONE;

        Visitor(List<String> lines, String documentId, Consumer<String> onKotlinMetadataUnsupported) {
            super(Opcodes.ASM9);
            this.lines = lines;
            this.documentId = documentId;
            this.onKotlinMetadataUnsupported = onKotlinMetadataUnsupported;
        }

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
            // The nested class's own access flags live HERE, not on the class
            // file's own `access` (JVMS 4.7.6): a nested `private` class reports
            // ACC_PUBLIC at the top level, because the JVM has no other place to
            // put it. This is the only place the source's own modifier survives.
            nestedAccess = access;
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
            if ((access & Opcodes.ACC_INTERFACE) != 0) return "interface";
            if ((access & Opcodes.ACC_ENUM) != 0) return "enum";
            return "class";
        }

        @Override
        public MethodVisitor visitMethod(int access, String name, String descriptor, String sig, String[] ex) {
            String owner = typeSymbol.substring(typeSymbol.lastIndexOf(' ') + 1);
            String methodSymbol = symbolOf(owner + name + "(" + disambiguatorOf(descriptor) + ").");
            String constructKind = "<init>".equals(name) ? "constructor" : "method";
            int parameterCount = Type.getArgumentTypes(descriptor).length;
            String[] parameterNames = new String[parameterCount];
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
                 *  belongs to.
                 *
                 *  <p>JVMS 4.7.18 lets the table be SHORTER than the descriptor's
                 *  parameter list, because javac omits parameters it synthesised —
                 *  the outer instance on an inner class, {@code $enum$name} and
                 *  {@code $enum$ordinal} on an enum. Those are LEADING, so
                 *  entries align from the END and the shift is the difference
                 *  between the two counts.
                 *
                 *  <p>That is JAVAC's rule, not the format's, and it was stated
                 *  here as though it were the format's. Kotlin appends its
                 *  synthetics at the END — a {@code Continuation} on a suspend
                 *  fun — so a short table there would make aligning from the end
                 *  WRONG. Measured rather than assumed: kotlinc writes one entry
                 *  per descriptor parameter, empty for the synthetic ones, so the
                 *  table is full length and the shift computes to 0.
                 *  {@code KotlinParameterAnnotated} pins it. Measured on the fixtures:
                 *  0 for a top-level class, 1 for an inner class, 2 for an enum —
                 *  it is not a constant, and indexing from zero put an enum
                 *  constructor's annotation on {@code $enum$name}, which is also a
                 *  String and so undetectable downstream by type.
                 *
                 *  <p>An absent or larger-than-descriptor count shifts by nothing:
                 *  there is no evidence of synthesis to correct for, and inventing
                 *  one would move an annotation that was already right. */
                private int alignedParameter(int parameter, boolean visible) {
                    int declared = parameterAnnotations.size();
                    int annotable = visible ? annotableVisible : annotableInvisible;
                    if (annotable < 0 || annotable > declared) return parameter;
                    return parameter + (declared - annotable);
                }

                @Override
                public void visitParameter(String parameterName, int parameterAccess) {
                    if (parameterIndex < parameterNames.length) parameterNames[parameterIndex] = parameterName;
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
                            // makes for parameter annotations, twenty lines up.
                            // Aligned the same way, from the end, so a type-use
                            // annotation on an enum or inner-class constructor
                            // lands where it was written.
                            int declared = parameterTypeAnnotations.size();
                            int annotable = visible ? annotableVisible : annotableInvisible;
                            int shift = (annotable < 0 || annotable > declared)
                                ? 0 : declared - annotable;
                            int index = reference.getFormalParameterIndex() + shift;
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

                @Override
                public void visitEnd() {
                    super.visitEnd();
                    emit(methodSymbol, constructKind, typeSymbol,
                         signatureJson(descriptor, sig, parameterNames, parameterAnnotations,
                                       parameterTypeAnnotations, returnTypeAnnotations), methodAccess,
                         null, methodModifiersJson(methodAccess), null, null, null, null,
                         annotationDefault);
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
            Boolean kotlinNullable = kotlinNullability.get(name);

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

        private String signatureJson(String descriptor, String genericSignature,
                                      String[] parameterNames, List<List<String>> parameterAnnotations,
                                      List<List<String>> parameterTypeAnnotations,
                                      List<String> returnTypeAnnotations) {
            Type[] argumentTypes = Type.getArgumentTypes(descriptor);
            List<String> parameters = new ArrayList<>();
            for (int i = 0; i < argumentTypes.length; i++) {
                TreeMap<String, String> parameter = new TreeMap<>();
                parameter.put("annotations", JsonOut.array(parameterAnnotations.get(i)));
                parameter.put("name", parameterNames[i] == null ? "null" : JsonOut.string(parameterNames[i]));
                parameter.put("type", TypeRefs.fromType(argumentTypes[i]));
                // Type-use annotations on this parameter's type — distinct from
                // "annotations" above, which are declaration-level (D00 §5a).
                parameter.put("type_annotations", JsonOut.array(parameterTypeAnnotations.get(i)));
                parameters.add(JsonOut.object(parameter));
            }
            String generic = TypeRefs.returnFromSignature(genericSignature);
            String returns = generic != null ? generic : TypeRefs.fromType(Type.getReturnType(descriptor));
            TreeMap<String, String> signature = new TreeMap<>();
            signature.put("parameters", JsonOut.array(parameters));
            signature.put("returns", returns);
            signature.put("return_type_annotations", JsonOut.array(returnTypeAnnotations));
            return JsonOut.object(signature);
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
            int access = classAccess;
            int constructFlags = nestedAccess != null ? nestedAccess : classAccess;
            emit(typeSymbol, constructKindOf(constructFlags), enclosingSymbol, null, access, null, null,
                 TypeRefs.genericSuperclassFromSignature(classSignature),
                 interfaceSymbolsJson(classInterfaces),
                 genericInterfacesJson(classSignature), erasedSuperclassJson(superName));
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
            TreeMap<String, String> fact = new TreeMap<>();
            fact.put("kind", JsonOut.string("symbol"));
            fact.put("document_id", JsonOut.string(documentId));
            fact.put("symbol", JsonOut.string(symbol));
            fact.put("construct_kind", JsonOut.string(constructKind));
            fact.put("enclosing", enclosing == null ? "null" : JsonOut.string(enclosing));
            fact.put("signature", signature == null ? "null" : signature);
            fact.put("visibility", JsonOut.string((access & Opcodes.ACC_PUBLIC) != 0 ? "public" : "other"));
            fact.put("line_start", "0");
            fact.put("line_end", "0");
            if (ext != null) fact.put("ext", ext);
            if (modifiers != null) fact.put("modifiers", modifiers);
            if (supertype != null) fact.put("supertype", supertype);
            if (interfaces != null) fact.put("interfaces", interfaces);
            if (genericInterfaces != null) fact.put("generic_interfaces", genericInterfaces);
            if (superclass != null) fact.put("superclass", superclass);
            if (annotationDefault != null) fact.put("annotation_default", annotationDefault);
            lines.add(JsonOut.object(fact));
        }
    }
}
