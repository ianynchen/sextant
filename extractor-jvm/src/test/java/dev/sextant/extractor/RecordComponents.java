package dev.sextant.extractor;

import java.util.List;
import java.util.Objects;

/** A record with a COMPACT canonical constructor — the shape that disproves
 *  "mandated means omitted from the tables".
 *
 *  <p>Measured, javac 26: the constructor's descriptor carries two parameters,
 *  {@code MethodParameters} flags BOTH {@code mandated}, and its tables omit
 *  nothing — a full-length parameter-annotation table and a type annotation at
 *  {@code param_index=1}. What is implicit here is the CONSTRUCTOR, not either
 *  parameter, and reading the flags as "these slots were omitted" concludes the
 *  method declares no parameters at all and drops the annotation.
 *
 *  <p>Records are mainstream Java and a type-use {@code @Nullable} on a component
 *  is ordinary, so this is not an exotic shape. */
public record RecordComponents(String id, @Labelled("body") @TypeUsed List<String> tags) {
    public RecordComponents {
        Objects.requireNonNull(id);
    }
}
