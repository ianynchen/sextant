package dev.sextant.extractor;

import java.util.List;

/** A named subclass that fixes its base's type argument. The class file's own
 *  descriptor says only "extends TypeCarrier"; the {@code Signature} attribute
 *  is the only place {@code List<String>} is written down. */
public class SupertypeSample extends TypeCarrier<List<String>> {

    /** The anonymous spelling, which is the one a real call site takes:
     *  {@code new ParameterizedTypeReference<List<OrderView>>() {}} compiles to
     *  a {@code $1} class whose signature is the sole carrier of the payload. */
    static TypeCarrier<List<String>> anonymous() {
        return new TypeCarrier<List<String>>() {};
    }

    /** A generic class over a *plain* base: the class file still carries a
     *  {@code Signature} — the type parameter alone puts it there — but the
     *  superclass part names a bare type with no argument to capture. */
    static class PlainBase<T> {
        T held;
    }
}
