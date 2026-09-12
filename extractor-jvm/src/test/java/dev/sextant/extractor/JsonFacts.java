package dev.sextant.extractor;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** Enough JSON to read one fact line back: the extractor's own {@code JsonOut} writes
 *  objects, arrays, strings, numbers, booleans and null, and nothing else.
 *
 *  <p>Test-only, and shared: it was a private copy in each of the three earlier
 *  Kotlin tests, and the fourth test that needed it is the one that lifted it. */
final class JsonFacts {
    private final String text;
    private int at;

    private JsonFacts(String text) {
        this.text = text;
    }

    /** The one value {@code text} spells — for a fact line, a {@code Map}. */
    static Object parse(String text) {
        return new JsonFacts(text).value();
    }

    private Object value() {
        char c = text.charAt(at);
        if (c == '{') return objectValue();
        if (c == '[') return arrayValue();
        if (c == '"') return string();
        if (text.startsWith("true", at)) { at += 4; return true; }
        if (text.startsWith("false", at)) { at += 5; return false; }
        if (text.startsWith("null", at)) { at += 4; return null; }
        int start = at;
        while (at < text.length() && "-+.eE0123456789".indexOf(text.charAt(at)) >= 0) at++;
        return Double.parseDouble(text.substring(start, at));
    }

    private Map<String, Object> objectValue() {
        Map<String, Object> fields = new LinkedHashMap<>();
        at++; // {
        while (text.charAt(at) != '}') {
            String key = string();
            at++; // :
            fields.put(key, value());
            if (text.charAt(at) == ',') at++;
        }
        at++; // }
        return fields;
    }

    private List<Object> arrayValue() {
        List<Object> items = new ArrayList<>();
        at++; // [
        while (text.charAt(at) != ']') {
            items.add(value());
            if (text.charAt(at) == ',') at++;
        }
        at++; // ]
        return items;
    }

    private String string() {
        StringBuilder out = new StringBuilder();
        at++; // opening quote
        while (text.charAt(at) != '"') {
            char c = text.charAt(at++);
            if (c != '\\') {
                out.append(c);
                continue;
            }
            char escaped = text.charAt(at++);
            switch (escaped) {
                case 'n' -> out.append('\n');
                case 't' -> out.append('\t');
                case 'r' -> out.append('\r');
                case 'b' -> out.append('\b');
                case 'f' -> out.append('\f');
                case 'u' -> {
                    out.append((char) Integer.parseInt(text.substring(at, at + 4), 16));
                    at += 4;
                }
                default -> out.append(escaped); // \" \\ \/
            }
        }
        at++; // closing quote
        return out.toString();
    }
}
