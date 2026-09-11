package dev.sextant.extractor;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.List;
import org.junit.jupiter.api.Test;

class CapabilitiesTest {

    @Test
    void the_declared_capabilities_are_sorted() {
        // `Capabilities.ALL`'s own javadoc states this — "Sorted, so the report
        // is byte-identical between runs (NFR-1)" — and nothing checked it.
        //
        // W6 broke it by inserting two names beside a related one rather than in
        // order, and nothing noticed: the Python side reads the list into a
        // frozenset, so order survives only in the jar's own `--capabilities`
        // output, which is what NFR-1 is about. A stated invariant with no guard
        // is one edit away from being untrue.
        assertEquals(
            Capabilities.ALL.stream().sorted().toList(),
            Capabilities.ALL,
            "Capabilities.ALL is not in sorted order");
    }

    @Test
    void no_capability_is_declared_twice() {
        // A duplicate reads as one name to every consumer (they all take a set)
        // and as two in the report, so it would break byte-stability without
        // changing behaviour anywhere a test could see it.
        assertEquals(
            List.copyOf(new java.util.LinkedHashSet<>(Capabilities.ALL)),
            Capabilities.ALL,
            "a capability is declared more than once");
    }
}
