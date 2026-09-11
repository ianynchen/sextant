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
    // A generic argument that is one of our own first-party types, not a
    // JDK box or collection — proves the recursion keeps a real reference
    // (with its own wire_type/nullable) rather than a bare string (D00 §5a).
    public List<FieldSampleItem> items;
    // A generic argument that is itself parameterized — the case that
    // proves the recursion actually recurses, not just one level deep.
    public Map<String, List<String>> nestedTags;
    // An array of a first-party type. javac writes no Signature attribute for
    // it, so the erased descriptor is the only source — and the element type
    // survives there solely as the `[]` suffix on the symbol, which is
    // descriptor grammar the language-blind half must not have to parse.
    public FieldSampleItem[] alternates;
    // The other array path: inside a generic argument the element arrives
    // through the Signature attribute instead of the descriptor.
    public List<String[]> nameGroups;
    // `A-M10`: a TWO-dimensional array, whose descriptor is the only source
    // javac gives (no Signature attribute is written for a plain array). Its
    // symbol must carry BOTH dimensions and its single argument must be the
    // one-dimensional array it holds — `Type#getElementType` returns the
    // INNERMOST element type, so building the fact from it made this field and
    // `alternates` byte-identical apart from the class name.
    public FieldSampleItem[][] alternateGroups;
    // A constant bound to the type rather than to any instance. Somebody wrote
    // it, so the fact is emitted — with the modifier that lets a consumer keep
    // it off the wire, which is the only thing separating it from a payload
    // field the scanner must not lose.
    public static final String SOURCE = "web";
    // The same claim, declared outright: the language marks this field as not
    // serialized, so no payload carries it.
    public transient String cachedSummary;

    // Both the return type and the parameter type are annotated, so a scanner
    // that discarded which type reference an annotation belongs to (as opposed
    // to whether it belongs to one at all) would attach both to the same place.
    public @org.jspecify.annotations.Nullable String getName(
            @org.jspecify.annotations.Nullable String input) {
        return input;
    }
}
