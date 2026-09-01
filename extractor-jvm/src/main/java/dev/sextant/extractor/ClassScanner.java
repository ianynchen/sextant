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
        private final List<String> lines;
        private final String documentId;
        private final Consumer<String> onKotlinMetadataUnsupported;
        private String typeSymbol;
        // ASM's internal name for the class's own direct supertype, kept from
        // `visit` because a method visitor sees no class-level context: it is
        // what tells a generated Avro record apart from any other class whose
        // <clinit> parses a schema (DescriptorHarvest).
        private String superName;
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
            emit(typeSymbol, constructKindOf(access), null, null, access, null, null,
                 TypeRefs.genericSuperclassFromSignature(sig), interfaceSymbolsJson(ifaces));
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

                @Override
                public void visitParameter(String parameterName, int parameterAccess) {
                    if (parameterIndex < parameterNames.length) parameterNames[parameterIndex] = parameterName;
                    parameterIndex++;
                }

                @Override
                public org.objectweb.asm.AnnotationVisitor visitAnnotation(String d, boolean visible) {
                    return annotationVisitor(methodSymbol, d, visible);
                }

                @Override
                public org.objectweb.asm.AnnotationVisitor visitParameterAnnotation(
                        int parameter, String d, boolean visible) {
                    if (parameter < 0 || parameter >= parameterAnnotations.size()) return null;
                    return parameterAnnotationVisitor(d, parameterAnnotations.get(parameter));
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
                            int index = reference.getFormalParameterIndex();
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
                         null, methodModifiersJson(methodAccess));
                    // After the method's own symbol, never before: a call site
                    // names its caller, and a fact file reads top-down.
                    lines.addAll(MethodFlow.callSites(documentId, methodSymbol, this));
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
            String annotation = Type.getType(descriptor).getInternalName() + "#";
            TreeMap<String, String> args = new TreeMap<>();
            return new org.objectweb.asm.AnnotationVisitor(Opcodes.ASM9) {
                @Override public void visit(String name, Object value) {
                    args.put(name == null ? "value" : name, literal(value));
                }
                @Override public void visitEnum(String name, String descriptor, String constant) {
                    args.put(name == null ? "value" : name, enumReference(descriptor, constant));
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
            if (value instanceof Boolean || value instanceof Number) return String.valueOf(value);
            if (value instanceof Type type) return JsonOut.string(type.getInternalName() + "#");
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

        private void emit(String symbol, String constructKind, String enclosing, String signature, int access,
                           String ext, String modifiers, String supertype) {
            emit(symbol, constructKind, enclosing, signature, access, ext, modifiers, supertype, null);
        }

        private void emit(String symbol, String constructKind, String enclosing, String signature, int access,
                           String ext, String modifiers, String supertype, String interfaces) {
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
            lines.add(JsonOut.object(fact));
        }
    }
}
