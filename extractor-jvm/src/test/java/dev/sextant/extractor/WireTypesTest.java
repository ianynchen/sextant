package dev.sextant.extractor;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.objectweb.asm.Type;

/** D1: "the extractor projects what the language leaves no choice about —
 *  primitives, their boxes, String, arrays, collections". {@code
 *  FieldSample.java} carries one boxed field (a {@code Long}) and asserts on
 *  it from real bytecode in {@code FieldScanTest}; the remaining six boxed
 *  primitives are cheaper to check directly against a descriptor than to add
 *  six more fields to a fixture nothing else needs them for. */
class WireTypesTest {

    @Test
    void projects_a_boxed_long_to_integer_int64_like_its_primitive() {
        Type boxedLong = Type.getType("Ljava/lang/Long;");
        assertEquals("integer", WireTypes.of(boxedLong));
        assertEquals("int64", WireTypes.format(boxedLong));
    }

    @Test
    void projects_a_boxed_integer_to_integer_int32() {
        Type boxedInteger = Type.getType("Ljava/lang/Integer;");
        assertEquals("integer", WireTypes.of(boxedInteger));
        assertEquals("int32", WireTypes.format(boxedInteger));
    }

    @Test
    void projects_a_boxed_short_and_byte_to_integer_int32() {
        Type boxedShort = Type.getType("Ljava/lang/Short;");
        Type boxedByte = Type.getType("Ljava/lang/Byte;");
        assertEquals("integer", WireTypes.of(boxedShort));
        assertEquals("int32", WireTypes.format(boxedShort));
        assertEquals("integer", WireTypes.of(boxedByte));
        assertEquals("int32", WireTypes.format(boxedByte));
    }

    @Test
    void projects_a_boxed_character_to_integer_with_no_format() {
        Type boxedCharacter = Type.getType("Ljava/lang/Character;");
        assertEquals("integer", WireTypes.of(boxedCharacter));
        assertEquals("", WireTypes.format(boxedCharacter));
    }

    @Test
    void projects_boxed_double_and_float_to_number() {
        Type boxedDouble = Type.getType("Ljava/lang/Double;");
        Type boxedFloat = Type.getType("Ljava/lang/Float;");
        assertEquals("number", WireTypes.of(boxedDouble));
        assertEquals("double", WireTypes.format(boxedDouble));
        assertEquals("number", WireTypes.of(boxedFloat));
        assertEquals("float", WireTypes.format(boxedFloat));
    }

    @Test
    void projects_a_boxed_boolean_to_boolean() {
        assertEquals("boolean", WireTypes.of(Type.getType("Ljava/lang/Boolean;")));
    }

    @Test
    void projects_a_list_to_array() {
        Type list = Type.getType("Ljava/util/List;");
        assertEquals("array", WireTypes.of(list));
    }

    /** Deliberately not "object": an object shape has named fields, and a
     *  map's keys are arbitrary. Collapsing the two would make a
     *  {@code Map<String, X>} look type-compatible with a record (D1). */
    @Test
    void projects_a_map_to_map_rather_than_object() {
        Type map = Type.getType("Ljava/util/Map;");
        assertEquals("map", WireTypes.of(map));
    }
}
