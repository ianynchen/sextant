package dev.sextant.extractor;

import java.math.BigDecimal;
import java.util.List;
import java.util.Map;

/** Committed alongside {@code Sample.java} so field-scanning tests assert on
 *  what javac actually emits without reaching into a sibling Maven module's
 *  gitignored build output. */
public class FieldSample {
    public long total;
    public String reference;
    public Long boxedTotal;
    public List<String> tags;
    public Map<String, String> attributes;
    public BigDecimal amount;
    public @org.jspecify.annotations.Nullable String note;
    public @org.jspecify.annotations.NonNull String required;
    // The distinction D00 §5a says only a per-reference value can express:
    // the outer type is nullable here, the element type below.
    public @org.jspecify.annotations.Nullable List<String> maybeList;
    public List<@org.jspecify.annotations.Nullable String> listOfMaybe;
    // CLASS retention: the invisible-type-annotation table, unlike everything
    // else in this file which is JSpecify's RUNTIME.
    public @ClassRetainedNullable String classRetained;

    // Both the return type and the parameter type are annotated, so a scanner
    // that discarded which type reference an annotation belongs to (as opposed
    // to whether it belongs to one at all) would attach both to the same place.
    public @org.jspecify.annotations.Nullable String getName(
            @org.jspecify.annotations.Nullable String input) {
        return input;
    }
}
