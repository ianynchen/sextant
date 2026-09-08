package dev.sextant.extractor;

import java.util.ArrayList;
import java.util.List;

/** JSR-045 `SourceDebugExtension` (JVMS 4.7.11), read for one question only: **which of
 *  a method's line numbers belong to the class's own source file.**
 *
 *  <p>A `LineNumberTable` entry is a line in SOME file, and a compiler that inlines code
 *  says which in this attribute rather than in the table. Kotlin does exactly that: it
 *  remaps an inlined body's lines into a synthetic range past the end of the enclosing
 *  file, so a method calling `let` or `forEach` — both `inline` in the standard library —
 *  carries lines that belong to `_Collections.kt`, or to a `fake.kt` the compiler
 *  invented. Measured, kotlinc 2.4.10: a 13-line `Std.kt` whose `useForEach` reads
 *  9 through 17, with 16 and 17 mapping to `_Collections.kt` 2068-2069.
 *
 *  <p>Treating every entry as this file's is javac's convention, not the format's, and
 *  publishing a `line_end` past the end of the file a reader was just told to open is the
 *  same shape of well-formed falsehood §8.1 rule 2 forbids.
 *
 *  <p>**Scope, deliberately narrow.** This reads the attribute to make `LineNumberTable`
 *  correct; it does not emit it. The strata, the file table and the `KotlinDebug` section
 *  are not published as facts — that is `SourceDebugExtension`'s own row in §2.3's ledger,
 *  and it stays there. */
final class SourceMap {
    private SourceMap() {}

    /** Inclusive output-line ranges belonging to {@code source}, or {@code null} when
     *  there is no map and every line therefore belongs to it. */
    static int[][] outputLinesOf(String source, String debug) {
        if (source == null || debug == null) return null;
        List<String> lines = List.of(debug.split("\n", -1));
        int fileSection = lines.indexOf("*F");
        int lineSection = lines.indexOf("*L");
        if (fileSection < 0 || lineSection < 0 || lineSection < fileSection) return null;
        Integer ownFile = fileIdOf(lines, fileSection, lineSection, source);
        // The map exists but does not name this file — nothing here can say which lines
        // are ours, so nothing is filtered. Less specific, never wrong.
        if (ownFile == null) return null;
        List<int[]> ranges = new ArrayList<>();
        int current = ownFile;
        for (int i = lineSection + 1; i < lines.size(); i++) {
            String entry = lines.get(i).trim();
            if (entry.isEmpty()) continue;
            // `*S`, `*E`, or the start of any other section: the mappings are over.
            if (entry.startsWith("*")) break;
            current = appendMapping(entry, current, ownFile, ranges);
        }
        return ranges.isEmpty() ? null : ranges.toArray(new int[0][]);
    }

    /** The id the file section gives {@code source}. The section is pairs of lines —
     *  {@code + 1 Std.kt} then a path — or single lines {@code 1 Std.kt}; both spellings
     *  are read, and only the id matters. */
    private static Integer fileIdOf(List<String> lines, int from, int to, String source) {
        for (int i = from + 1; i < to; i++) {
            String entry = lines.get(i).trim();
            if (entry.startsWith("+ ")) entry = entry.substring(2).trim();
            int space = entry.indexOf(' ');
            if (space < 0) continue;
            Integer id = number(entry.substring(0, space));
            if (id != null && entry.substring(space + 1).trim().equals(source)) return id;
        }
        return null;
    }

    /** One {@code InputStartLine[#FileId][,RepeatCount]:OutputStartLine[,Increment]}
     *  mapping. Returns the file id in force after it — JSR-045 lets a mapping omit
     *  {@code #FileId}, in which case the previous one stands. */
    private static int appendMapping(String entry, int current, int ownFile, List<int[]> ranges) {
        int colon = entry.indexOf(':');
        if (colon < 0) return current;
        String input = entry.substring(0, colon);
        String output = entry.substring(colon + 1);

        int fileId = current;
        int hash = input.indexOf('#');
        if (hash >= 0) {
            String after = input.substring(hash + 1);
            int comma = after.indexOf(',');
            Integer stated = number(comma < 0 ? after : after.substring(0, comma));
            if (stated != null) fileId = stated;
            input = input.substring(0, hash) + (comma < 0 ? "" : after.substring(comma));
        }
        int repeat = 1;
        int inputComma = input.indexOf(',');
        if (inputComma >= 0) {
            Integer stated = number(input.substring(inputComma + 1));
            if (stated != null) repeat = stated;
        }
        int outputComma = output.indexOf(',');
        Integer start = number(outputComma < 0 ? output : output.substring(0, outputComma));
        int increment = 1;
        if (outputComma >= 0) {
            Integer stated = number(output.substring(outputComma + 1));
            if (stated != null) increment = stated;
        }
        if (start == null || repeat < 1 || increment < 1) return fileId;
        if (fileId == ownFile) {
            // Each of `repeat` input lines maps to `increment` output lines, laid end to
            // end from `start` — so the block runs to `start + repeat * increment - 1`.
            ranges.add(new int[] {start, start + repeat * increment - 1});
        }
        return fileId;
    }

    private static Integer number(String text) {
        String trimmed = text.trim();
        if (trimmed.isEmpty()) return null;
        for (int i = 0; i < trimmed.length(); i++) {
            if (trimmed.charAt(i) < '0' || trimmed.charAt(i) > '9') return null;
        }
        try {
            return Integer.valueOf(trimmed);
        } catch (NumberFormatException notANumber) {
            return null;
        }
    }

    /** Whether {@code line} is one this class's own source file accounts for. A null map
     *  means nothing said otherwise, which is every class no compiler inlined into. */
    static boolean contains(int[][] ranges, int line) {
        if (ranges == null) return true;
        for (int[] range : ranges) {
            if (line >= range[0] && line <= range[1]) return true;
        }
        return false;
    }
}
