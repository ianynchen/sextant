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
}
