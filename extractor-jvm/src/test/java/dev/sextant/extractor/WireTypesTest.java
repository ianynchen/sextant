package dev.sextant.extractor;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.objectweb.asm.Type;

/** D1: "the extractor projects what the language leaves no choice about —
 *  primitives, their boxes, String, arrays, collections". The fixture (fixed
 *  by Task 2, asserted on by name in later tasks) carries no boxed or
 *  {@code Map}-typed field, so those two cases are asserted directly against
 *  a descriptor here rather than by editing it. */
class WireTypesTest {

    @Test
    void projects_a_boxed_long_to_integer_int64_like_its_primitive() {
        Type boxedLong = Type.getType("Ljava/lang/Long;");
        assertEquals("integer", WireTypes.of(boxedLong));
        assertEquals("int64", WireTypes.format(boxedLong));
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
