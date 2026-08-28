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
            // A box's format tracks the primitive it boxes; getInternalName()
            // is only valid for an OBJECT sort, so this must not be reached
            // for BOOLEAN, CHAR or ARRAY (they stay the "" default below).
            case Type.OBJECT -> objectLikeFormat(type);
            default -> "";
        };
    }

    // D1: "the extractor projects what the language leaves no choice about —
    // primitives, their boxes, String, arrays, collections". Primitives and
    // arrays are already sorted out by getSort() above; this is the rest of
    // that list — boxes, String, and the JDK's own collection interfaces —
    // matched by exact internal name, never structurally (a third-party type
    // that happens to implement List is still first-party/catalog territory,
    // decided elsewhere). Everything else reference-typed is catalog
    // knowledge (D2's known_types) or, absent a catalog entry, an open
    // object — never guessed at here.
    private static String objectLike(Type type) {
        return switch (type.getInternalName()) {
            case "java/lang/String" -> "string";
            case "java/lang/Boolean" -> "boolean";
            case "java/lang/Integer", "java/lang/Long", "java/lang/Short",
                 "java/lang/Byte", "java/lang/Character" -> "integer";
            case "java/lang/Double", "java/lang/Float" -> "number";
            case "java/util/List", "java/util/Set", "java/util/Collection",
                 "java/util/Iterable" -> "array";
            // A map's keys are arbitrary, which "object" cannot say (D1): an
            // object shape has named fields, and collapsing the two would
            // make a Map<String, X> look type-compatible with a record.
            case "java/util/Map" -> "map";
            default -> "object";
        };
    }

    // The format half of the same box mapping, kept as its own small switch
    // rather than folded into objectLike: of() and format() are already two
    // parallel switches over getSort() above, and this keeps that shape
    // rather than introducing a combined-result type neither needs elsewhere.
    private static String objectLikeFormat(Type type) {
        return switch (type.getInternalName()) {
            case "java/lang/Integer", "java/lang/Short", "java/lang/Byte" -> "int32";
            case "java/lang/Long" -> "int64";
            case "java/lang/Double" -> "double";
            case "java/lang/Float" -> "float";
            default -> "";
        };
    }
}
