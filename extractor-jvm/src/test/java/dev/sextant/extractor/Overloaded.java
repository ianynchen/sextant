package dev.sextant.extractor;

/** Two methods sharing one name — the case D00 §1's descriptor-hash
 *  disambiguator exists for — beside one that does not, because the
 *  disambiguator is spent on both: a suffix that appears only once a sibling
 *  arrives moves the identity of a method nobody touched. */
public class Overloaded {
    public String render(int value) { return ""; }

    public String render(String value) { return ""; }

    public String plain() { return ""; }
}
