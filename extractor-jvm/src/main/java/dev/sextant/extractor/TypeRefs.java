package dev.sextant.extractor;

import java.util.ArrayList;
import java.util.List;
import java.util.TreeMap;
import java.util.function.Consumer;
import org.objectweb.asm.Type;
import org.objectweb.asm.signature.SignatureReader;
import org.objectweb.asm.signature.SignatureVisitor;

/** Type references: a symbol reference plus optional type arguments, recursively
 *  (D00 §5a). Recorded verbatim — unwrapping envelopes is catalog knowledge. */
public final class TypeRefs {
    private TypeRefs() {}

    public static String fromType(Type type) {
        return ref(descriptorName(type), List.of());
    }

    // Package-private: ClassScanner's field type references share this exact
    // symbol grammar rather than keeping their own copy of it.
    static String descriptorName(Type type) {
        return switch (type.getSort()) {
            case Type.OBJECT -> type.getInternalName() + "#";
            case Type.ARRAY -> descriptorName(type.getElementType()) + "[]";
            default -> type.getClassName() + "#";
        };
    }

    public static String ref(String symbol, List<String> argumentJson) {
        TreeMap<String, String> fields = new TreeMap<>();
        fields.put("symbol", JsonOut.string(symbol));
        fields.put("arguments", JsonOut.array(argumentJson));
        return JsonOut.object(fields);
    }

    /** Generic return type from the Signature attribute, or null when absent. */
    public static String returnFromSignature(String signature) {
        if (signature == null) return null;
        List<String> collected = new ArrayList<>();
        new SignatureReader(signature).accept(new SignatureVisitor(org.objectweb.asm.Opcodes.ASM9) {
            @Override public SignatureVisitor visitReturnType() {
                return new Collector(collected);
            }
        });
        return collected.isEmpty() ? null : collected.get(0);
    }

    private static final class Collector extends SignatureVisitor {
        private final List<String> sink;
        private String owner;
        private final List<String> arguments = new ArrayList<>();

        Collector(List<String> sink) {
            super(org.objectweb.asm.Opcodes.ASM9);
            this.sink = sink;
        }

        @Override public void visitClassType(String name) {
            if (owner == null) owner = name + "#";
        }

        @Override public SignatureVisitor visitTypeArgument(char wildcard) {
            return new Collector(arguments);
        }

        @Override public void visitEnd() {
            if (owner != null) sink.add(ref(owner, arguments));
        }
    }

    /** A field's fully augmented type reference: the {symbol, arguments} envelope every
     *  type reference carries (D00 §5a), plus D1's wire-type projection and D3's
     *  nullability at **every** level of the chain — a parameterized type keeps each of
     *  its arguments as a full reference of its own, never a bare string.
     *  `List&lt;CustomerRef&gt;` must keep `CustomerRef`, not erase to plain `List`.
     *
     *  <p>Reads the field's generic {@code Signature} attribute when present — the erased
     *  descriptor alone has already lost every type argument by the time it reaches this
     *  method — and falls back to the descriptor when absent, which is exactly when the
     *  JVM spec omits the attribute: a field typed with no type variable and no
     *  parameterization (a plain {@code String} or {@code long}) gets no {@code Signature}
     *  attribute at all.
     *
     *  <p>{@code nullableOverride}, when non-null, replaces the computed top-level
     *  nullability with a value another source already resolved — Kotlin's type system,
     *  D3's Kotlin half — without touching any nested type argument, which that source
     *  says nothing about. */
    public static String fieldRef(Type erasedType, String genericSignature, Boolean nullableOverride) {
        Node node = genericSignature == null ? null : fromSignature(genericSignature);
        if (node == null) node = nodeFromType(erasedType);
        return toJson(nullableOverride == null ? node : node.withNullable(nullableOverride));
    }

    private static Node fromSignature(String genericSignature) {
        List<Node> collected = new ArrayList<>();
        new SignatureReader(genericSignature).acceptType(new NodeCollector(collected::add));
        // A malformed or unrecognised FieldTypeSignature has no honest reference to
        // build; the caller falls back to the descriptor, which is never wrong, only
        // less specific.
        return collected.isEmpty() ? null : collected.get(0);
    }

    private static Node nodeFromType(Type type) {
        boolean nullable = type.getSort() == Type.OBJECT || type.getSort() == Type.ARRAY;
        return new Node(descriptorName(type), List.of(), nullable, WireTypes.of(type), WireTypes.format(type));
    }

    private static String toJson(Node node) {
        TreeMap<String, String> fields = new TreeMap<>();
        fields.put("symbol", JsonOut.string(node.symbol()));
        fields.put("arguments", JsonOut.array(node.argumentsJson()));
        fields.put("wire_type", JsonOut.string(node.wireType()));
        fields.put("wire_format", JsonOut.string(node.wireFormat()));
        fields.put("nullable", String.valueOf(node.nullable()));
        // D3 (corrected): `resolution` is candidate-set semantics (CONTEXT.md) — how
        // certain a fact's *target* is — and a boolean has no candidate set. Java's type
        // system settles nullability outright: every reference permits null and every
        // primitive forbids it. Never partial, never anything but resolved on the JVM.
        fields.put("nullable_resolution", JsonOut.string("resolved"));
        return JsonOut.object(fields);
    }

    /** One level of an augmented type reference, pre-serialization — {@link #toJson}
     *  turns exactly one of these into the JSON object a caller keeps. */
    private record Node(String symbol, List<String> argumentsJson, boolean nullable,
                         String wireType, String wireFormat) {
        Node withNullable(boolean value) {
            return new Node(symbol, argumentsJson, value, wireType, wireFormat);
        }
    }

    /** Walks a {@code FieldTypeSignature} (JVMS 4.7.9.1) — a class type, an array type, a
     *  type variable, or (nested inside an array) a base type — recursively, handing one
     *  {@link Node} to {@code onDone} once that level is fully parsed. Mirrors
     *  {@link Collector}'s traversal shape; kept separate because every level here also
     *  carries D1's wire-type projection and D3's nullability, which {@link Collector}'s
     *  bare {symbol, arguments} envelope has no room for. */
    private static final class NodeCollector extends SignatureVisitor {
        private final Consumer<Node> onDone;
        private String owner;
        private final List<String> arguments = new ArrayList<>();

        NodeCollector(Consumer<Node> onDone) {
            super(org.objectweb.asm.Opcodes.ASM9);
            this.onDone = onDone;
        }

        @Override public void visitBaseType(char descriptor) {
            Type type = Type.getType(String.valueOf(descriptor));
            onDone.accept(new Node(descriptorName(type), List.of(), false,
                WireTypes.of(type), WireTypes.format(type)));
        }

        // Not a real class — recorded by the name the signature itself gives it, never
        // resolved to its bound (resolution is not this task's job). Any instantiation of
        // a type variable is still a reference in Java, so the nullability rule holds.
        @Override public void visitTypeVariable(String name) {
            onDone.accept(new Node(name, List.of(), true, "object", ""));
        }

        @Override public SignatureVisitor visitArrayType() {
            return new NodeCollector(element -> onDone.accept(
                new Node(element.symbol() + "[]", List.of(), true, "array", "")));
        }

        @Override public void visitClassType(String name) {
            if (owner == null) owner = name;
        }

        @Override public void visitInnerClassType(String name) {
            if (owner != null) owner = owner + "$" + name;
        }

        // The wildcard kind (`+`/`-`/`=`) has no field on D00 §5a's type reference — only
        // the bound is recorded, exactly as the signature states it. Resolving variance is
        // not this task's job any more than resolving a type variable's bound is.
        @Override public SignatureVisitor visitTypeArgument(char wildcard) {
            return new NodeCollector(node -> arguments.add(toJson(node)));
        }

        // An unbounded wildcard (`?`) has no bound to recurse into — recorded rather than
        // silently dropped from the argument list.
        @Override public void visitTypeArgument() {
            arguments.add(toJson(new Node("?", List.of(), true, "object", "")));
        }

        @Override public void visitEnd() {
            if (owner == null) return;
            Type type = Type.getObjectType(owner);
            onDone.accept(new Node(owner + "#", arguments, true, WireTypes.of(type), WireTypes.format(type)));
        }
    }
}
