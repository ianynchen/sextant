package dev.sextant.extractor;

/** Two methods sharing one name — the case D00 §1's descriptor-hash
 *  disambiguator exists for — beside one that does not, because a method
 *  with no sibling keeps the bare `().` form the same section specifies. */
public class Overloaded {
    public String render(int value) { return ""; }

    public String render(String value) { return ""; }

    public String plain() { return ""; }
}
