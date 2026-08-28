package dev.sextant.extractor;

/** Minimal JSON emission. Java ships no JSON library and one report object does
 *  not justify a dependency; escaping is the only subtlety. */
public final class JsonOut {
    private JsonOut() {}

    public static String string(String raw) {
        StringBuilder out = new StringBuilder("\"");
        for (int i = 0; i < raw.length(); i++) {
            char c = raw.charAt(i);
            switch (c) {
                case '"' -> out.append("\\\"");
                case '\\' -> out.append("\\\\");
                case '\n' -> out.append("\\n");
                case '\r' -> out.append("\\r");
                case '\t' -> out.append("\\t");
                default -> {
                    if (c < 0x20) out.append(String.format("\\u%04x", (int) c));
                    else out.append(c);
                }
            }
        }
        return out.append('"').toString();
    }

    public static String array(java.util.List<String> jsonValues) {
        return "[" + String.join(",", jsonValues) + "]";
    }

    /** Keys must be supplied already sorted: byte-identical output (NFR-1). */
    public static String object(java.util.SortedMap<String, String> jsonByKey) {
        StringBuilder out = new StringBuilder("{");
        boolean first = true;
        for (var entry : jsonByKey.entrySet()) {
            if (!first) out.append(',');
            out.append(string(entry.getKey())).append(':').append(entry.getValue());
            first = false;
        }
        return out.append('}').toString();
    }
}
