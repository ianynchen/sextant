package dev.sextant.extractor;

import java.util.ArrayList;
import java.util.List;
import java.util.TreeMap;
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
}
