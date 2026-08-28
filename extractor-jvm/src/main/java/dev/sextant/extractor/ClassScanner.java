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
            for (int i = 0; i < parameterCount; i++) parameterAnnotations.add(new ArrayList<>());

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
                public void visitEnd() {
                    emit(methodSymbol, constructKind, typeSymbol,
                         signatureJson(descriptor, sig, parameterNames, parameterAnnotations), access);
                }
            };
        }

        @Override
        public FieldVisitor visitField(int access, String name, String descriptor, String sig, Object value) {
            String owner = typeSymbol.substring(typeSymbol.lastIndexOf(' ') + 1);
            String fieldSymbol = symbolOf(owner + name + ".");
            Type type = Type.getType(descriptor);

            return new FieldVisitor(Opcodes.ASM9) {
                @Override
                public org.objectweb.asm.AnnotationVisitor visitAnnotation(String d, boolean visible) {
                    return annotationVisitor(fieldSymbol, d, visible);
                }

                @Override
                public void visitEnd() {
                    emit(fieldSymbol, "field", typeSymbol, fieldSignatureJson(type), access);
                }
            };
        }

        @Override
        public org.objectweb.asm.AnnotationVisitor visitAnnotation(String descriptor, boolean visible) {
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

        /** A parameter-level annotation is not a fact: it attaches inline on the
         *  parameter's entry in the signature (D00 §5a — "annotations attach without
         *  the parameter needing a symbol of its own"). */
        private org.objectweb.asm.AnnotationVisitor parameterAnnotationVisitor(
                String descriptor, List<String> sink) {
            return useCollectingVisitor(descriptor, sink::add);
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
                                      String[] parameterNames, List<List<String>> parameterAnnotations) {
            Type[] argumentTypes = Type.getArgumentTypes(descriptor);
            List<String> parameters = new ArrayList<>();
            for (int i = 0; i < argumentTypes.length; i++) {
                TreeMap<String, String> parameter = new TreeMap<>();
                parameter.put("annotations", JsonOut.array(parameterAnnotations.get(i)));
                parameter.put("name", parameterNames[i] == null ? "null" : JsonOut.string(parameterNames[i]));
                parameter.put("type", TypeRefs.fromType(argumentTypes[i]));
                parameters.add(JsonOut.object(parameter));
            }
            String generic = TypeRefs.returnFromSignature(genericSignature);
            String returns = generic != null ? generic : TypeRefs.fromType(Type.getReturnType(descriptor));
            TreeMap<String, String> signature = new TreeMap<>();
            signature.put("parameters", JsonOut.array(parameters));
            signature.put("returns", returns);
            return JsonOut.object(signature);
        }

        /** A field has no parameter list, only the type reference D00 §5a says it
         *  carries "the same way" a return type does. */
        private String fieldSignatureJson(Type type) {
            TreeMap<String, String> signature = new TreeMap<>();
            signature.put("returns", fieldTypeRef(type));
            return JsonOut.object(signature);
        }

        /** D1 and D3 both land on the type reference, alongside the symbol
         *  TypeRefs.ref already carries — nullability "sits on the type
         *  reference" (D00 §5a), not beside it. */
        private String fieldTypeRef(Type type) {
            TreeMap<String, String> ref = new TreeMap<>();
            ref.put("symbol", JsonOut.string(referenceSymbol(type)));
            ref.put("arguments", JsonOut.array(List.of()));
            ref.put("wire_type", JsonOut.string(WireTypes.of(type)));
            ref.put("wire_format", JsonOut.string(WireTypes.format(type)));
            // The language's own answer, not an annotation's. A primitive cannot
            // hold null and the type system settles it; a reference may, but
            // nothing declared that it should — so the claim is weaker and says
            // so, rather than a third enum value existing (D00 §5a).
            boolean nullable = type.getSort() == Type.OBJECT || type.getSort() == Type.ARRAY;
            ref.put("nullable", String.valueOf(nullable));
            ref.put("nullable_resolution", JsonOut.string(nullable ? "partial" : "resolved"));
            return JsonOut.object(ref);
        }

        // Mirrors TypeRefs.descriptorName's symbol grammar. Kept local rather
        // than exposed from TypeRefs: this task's scope is visitField, and
        // fields need no generic-argument recursion beyond what method
        // parameters already settle for without it.
        private String referenceSymbol(Type type) {
            return switch (type.getSort()) {
                case Type.ARRAY -> referenceSymbol(type.getElementType()) + "[]";
                case Type.OBJECT -> type.getInternalName() + "#";
                default -> type.getClassName() + "#";
            };
        }

        private void emit(String symbol, String constructKind, String enclosing, String signature, int access) {
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
            lines.add(JsonOut.object(fact));
        }
    }
}
