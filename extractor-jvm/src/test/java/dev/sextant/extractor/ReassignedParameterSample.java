package dev.sextant.extractor;

/** Committed fixture for {@code field_write}'s parameter rule: a write that loads a
 *  parameter's SLOT is the parameter only where nothing in the method stores to that slot.
 *  Each method here reassigns the parameter before the write — on a branch, or in one
 *  straight line — except the near-misses, whose loaded parameter is untouched. Compiled by
 *  Gradle's own test compilation, so the assertions are about the bytecode javac emits. */
final class ReassignedParameterSample {
    static String host;
    static int count;
    String base;
    String url;
    String kept;

    /** The reviewer's static case: the fallback replaces the parameter on one branch. */
    static void init(String given) {
        if (!given.startsWith("https://")) given = "https://fallback.example.com/s";
        host = given;
    }

    /** The reviewer's instance case: a trailing slash appended on one branch. */
    void normalise(String given) {
        if (!given.endsWith("/")) given = given + "/";
        this.base = given;
    }

    /** One straight line: a value parked back into the parameter's own slot. */
    void trimmed(String given) {
        given = given.trim();
        this.url = given;
    }

    /** The same into a static field. */
    static void trimmedStatic(String given) {
        given = given.trim();
        host = given;
    }

    /** An {@code IINC} on the parameter's slot is a store too. */
    static void bumped(int n) {
        n++;
        count = n;
    }

    /** Near-miss: the parameter loaded is untouched, so it is still the value. */
    void untouched(String given) {
        this.kept = given;
    }

    /** Near-miss: ANOTHER parameter is reassigned; the one written is untouched. */
    static void otherReassigned(String given, String other) {
        other = other.trim();
        host = given;
        count = other.length();
    }
}
