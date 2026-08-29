package dev.sextant.extractor;

import java.util.List;

public class Sample {
    public String greet(int times) { return ""; }

    // A parameterized return type, so a method's Signature attribute is
    // exercised the same way a field's is: the argument must survive as a
    // reference of its own rather than erasing to a bare List.
    public List<String> greetAll() { return List.of(); }

    // The one return type that projects onto no wire type at all.
    public void reset() {}
}
