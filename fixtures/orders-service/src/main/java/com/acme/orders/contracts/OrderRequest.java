package com.acme.orders.contracts;

import com.fasterxml.jackson.annotation.JsonIgnore;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.math.BigDecimal;
import java.util.List;
import java.util.Optional;
import org.jspecify.annotations.NonNull;
import org.jspecify.annotations.Nullable;

public class OrderRequest {
    // No annotation: nullable by Java's rule, which settles it outright — so
    // the fact reads `resolved` (D3, corrected by ruling B).
    public String reference;
    // Declared nullable: resolution `resolved`.
    public @Nullable String note;
    // Declared not-null, overriding Java's permissive default — and renamed,
    // so `wire_name` is `customer_id` and never `customerId`.
    @JsonProperty("customer_id")
    public @NonNull String customerId;
    // Optional is a declared wrapper with `semantics: optional`, so this field
    // is `required: false`. Its nullability is decided by what the envelope
    // holds rather than by the envelope: rooting lands on `String`, which
    // Java's rule makes `nullable: true`. The one field whose two flags —
    // independent by D00 §5a — are visibly read from different places.
    public Optional<String> note2;
    // Absent from the wire entirely: no shape_field at all.
    @JsonIgnore
    public String internalTrace;
    // A nested object, and a collection of them.
    public CustomerRef customer;
    public List<CustomerRef> alternates;
    // A primitive: not_null by the type system, projected by the extractor.
    public long total;
    // A known type: an object in code, a number on the wire. Expanding it
    // would contribute intVal, scale, intCompact and precision — none of which
    // exists on any payload (D2).
    @JsonProperty("total_amount")
    public BigDecimal totalAmount;
    // An enumeration: a closed set of constants, mapped to the `enum` wire type
    // and never expanded. Expanded structurally it would contribute NEW and
    // DONE as if a payload carried fields by those names.
    public OrderStatus status;
    // Bound to the type, not to an instance: as public as any field here and on
    // no payload. The symbol fact is still emitted — somebody declared it — and
    // carries the modifier the shape pass filters on.
    public static final String SOURCE = "web";

    /** Non-finite constants, so the strict-JSON guard has something to catch.
     *  RFC 8259 has no NaN or Infinity literal, and writing one unquoted makes
     *  the whole fact file invalid for a conforming reader — a defect that was
     *  invisible because no fixture carried a float or double at all. */
    public static final double NO_TIMEOUT = Double.NaN;

    public static final float UNBOUNDED = Float.POSITIVE_INFINITY;
    // The same claim, declared outright rather than implied by staticness.
    public transient String cachedSummary;
}
