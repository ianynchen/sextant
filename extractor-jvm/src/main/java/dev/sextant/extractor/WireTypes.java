package dev.sextant.extractor;

import org.objectweb.asm.Type;

/** JVM descriptor to D00 §5b's wire vocabulary. Lives here because it is
 *  language knowledge: `J` means int64 to a JVM reader and to nobody else. */
final class WireTypes {
    private WireTypes() {}

    static String of(Type type) {
        return switch (type.getSort()) {
            case Type.BOOLEAN -> "boolean";
            case Type.BYTE, Type.SHORT, Type.INT, Type.LONG, Type.CHAR -> "integer";
            case Type.FLOAT, Type.DOUBLE -> "number";
            case Type.ARRAY -> "array";
            default -> objectLike(type);
        };
    }

    static String format(Type type) {
        return switch (type.getSort()) {
            case Type.LONG -> "int64";
            case Type.INT, Type.SHORT, Type.BYTE -> "int32";
            case Type.DOUBLE -> "double";
            case Type.FLOAT -> "float";
            default -> "";
        };
    }

    // String is the one reference type the language itself settles a wire
    // meaning for (D1's "primitives, their boxes, String, arrays"). Anything
    // else reference-typed is catalog knowledge (D2's known_types) or, absent
    // a catalog entry, an open object — never guessed at here.
    private static String objectLike(Type type) {
        return "java/lang/String".equals(type.getInternalName()) ? "string" : "object";
    }
}
