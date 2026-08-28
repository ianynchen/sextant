package dev.sextant.extractor;

import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.List;
import java.util.TreeMap;
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
        List<String> lines = new ArrayList<>();
        new ClassReader(classBytes).accept(new Visitor(lines, documentId), ClassReader.SKIP_FRAMES);
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
        private String typeSymbol;
        // Populated from @Metadata before any field is visited (ASM visits class-level
        // annotations before fields — see visitAnnotation below); empty for every
        // non-Kotlin class, which leaves Java's rule as the only source.
        private java.util.Map<String, Boolean> kotlinNullability = KotlinNullability.NONE;

        Visitor(List<String> lines, String documentId) {
            super(Opcodes.ASM9);
            this.lines = lines;
            this.documentId = documentId;
        }

        @Override
        public void visit(int v, int access, String name, String sig, String superName, String[] ifaces) {
            typeSymbol = symbolOf(name + "#");
            boolean isInterface = (access & Opcodes.ACC_INTERFACE) != 0;
            emit(typeSymbol, isInterface ? "interface" : "class", null, null, access);
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

            // Parameter names (visitParameter) and parameter annotations
            // (visitParameterAnnotation) arrive as callbacks during the visit, so the
            // symbol fact — whose signature embeds both — is only emitted at visitEnd,
            // once every callback for this method has fired.
            return new MethodVisitor(Opcodes.ASM9) {
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
                    emit(methodSymbol, constructKind, typeSymbol,
                         signatureJson(descriptor, sig, parameterNames, parameterAnnotations,
                                       parameterTypeAnnotations, returnTypeAnnotations), access);
                }
            };
        }

        @Override
        public FieldVisitor visitField(int access, String name, String descriptor, String sig, Object value) {
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
                    emit(fieldSymbol, "field", typeSymbol, fieldSignatureJson(type, kotlinNullable), access,
                         kotlinNullable == null ? null : kotlinExt(kotlinNullable));
                }
            };
        }

        @Override
        public org.objectweb.asm.AnnotationVisitor visitAnnotation(String descriptor, boolean visible) {
            // The compiler's own bookkeeping, not a fact of its own (D00 §5a is about
            // annotations someone wrote) — decode it into the property lookup instead
            // of letting its protobuf blob out through the normal annotation stream.
            if (KotlinNullability.DESCRIPTOR.equals(descriptor)) {
                return KotlinNullability.collector(decoded -> kotlinNullability = decoded);
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
         *  carries "the same way" a return type does. */
        private String fieldSignatureJson(Type type, Boolean kotlinNullable) {
            TreeMap<String, String> signature = new TreeMap<>();
            signature.put("returns", fieldTypeRef(type, kotlinNullable));
            return JsonOut.object(signature);
        }

        /** D1 and D3 both land on the type reference, alongside the symbol
         *  TypeRefs.ref already carries — nullability "sits on the type
         *  reference" (D00 §5a), not beside it. */
        private String fieldTypeRef(Type type, Boolean kotlinNullable) {
            TreeMap<String, String> ref = new TreeMap<>();
            ref.put("symbol", JsonOut.string(TypeRefs.descriptorName(type)));
            ref.put("arguments", JsonOut.array(List.of()));
            ref.put("wire_type", JsonOut.string(WireTypes.of(type)));
            ref.put("wire_format", JsonOut.string(WireTypes.format(type)));
            if (kotlinNullable != null) {
                // Kotlin's `String` vs `String?` is a declaration, not a default the
                // language falls back to absent other evidence — unlike Java's "no
                // annotation found" guess, this is `resolved` (D00 §5a). A Kotlin
                // field landing here as `partial` instead would mean the @Metadata
                // read silently did nothing.
                ref.put("nullable", String.valueOf(kotlinNullable));
                ref.put("nullable_resolution", JsonOut.string("resolved"));
            } else {
                // The language's own answer, not an annotation's. A primitive cannot
                // hold null and the type system settles it; a reference may, but
                // nothing declared that it should — so the claim is weaker and says
                // so, rather than a third enum value existing (D00 §5a).
                boolean nullable = type.getSort() == Type.OBJECT || type.getSort() == Type.ARRAY;
                ref.put("nullable", String.valueOf(nullable));
                ref.put("nullable_resolution", JsonOut.string(nullable ? "partial" : "resolved"));
            }
            return JsonOut.object(ref);
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

        private void emit(String symbol, String constructKind, String enclosing, String signature, int access) {
            emit(symbol, constructKind, enclosing, signature, access, null);
        }

        private void emit(String symbol, String constructKind, String enclosing, String signature, int access,
                           String ext) {
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
            lines.add(JsonOut.object(fact));
        }
    }
}
