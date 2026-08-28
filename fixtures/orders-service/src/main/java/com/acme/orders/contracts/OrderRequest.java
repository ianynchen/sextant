package com.acme.orders.contracts;

import com.fasterxml.jackson.annotation.JsonIgnore;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.math.BigDecimal;
import java.util.List;
import java.util.Optional;
import org.jspecify.annotations.NonNull;
import org.jspecify.annotations.Nullable;

public class OrderRequest {
    // No annotation: nullable by Java's rule, at resolution `partial` (D3).
    public String reference;
    // Declared nullable: resolution `resolved`.
    public @Nullable String note;
    // Declared not-null, overriding Java's permissive default — and renamed,
    // so `wire_name` is `customer_id` and never `customerId`.
    @JsonProperty("customer_id")
    public @NonNull String customerId;
    // Optional is a declared wrapper with `semantics: optional`, so this field
    // is `required: false` while staying `nullable: false`. The only case that
    // separates the two flags D00 §5a insists are independent.
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
}
