package dev.sextant.extractor;

/** A minimal first-party type, used only as a generic type argument in
 *  {@code FieldSample} — proves a nested reference keeps its own symbol
 *  (D00 §5a) rather than being erased to a bare {@code java/util/List#}. */
public class FieldSampleItem {
    public String id;
}
