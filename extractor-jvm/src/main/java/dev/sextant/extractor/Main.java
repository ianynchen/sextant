package dev.sextant.extractor;

import java.io.Closeable;
import java.io.IOException;
import java.nio.file.*;
import java.security.MessageDigest;
import java.util.*;
import java.util.stream.Stream;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;

/** The subprocess contract: arguments in, fact files out, a JSON report on
 *  stdout. Errors exit non-zero with a message on stderr. */
public final class Main {

    /** Names the FACILITY, never the library (D00 §2). It read `"asm"` until
     *  Step 1, which is what made a library version look like the right thing
     *  to put beside it — and then that field drifted to a capability number. */
    private static final String SCANNER_ID = "sextant-jvm-extractor";

    /** The manifest attribute the build writes with the RESOLVED coordinates of
     *  every declared scanning library (`build.gradle.kts`). */
    private static final String LIBRARIES_ATTRIBUTE = "Sextant-Scanner-Libraries";

    /** JEP 238's overlay root. Everything below it is a versioned copy of a
     *  class whose reachable form may also exist at the archive root. */
    private static final String VERSIONS_PREFIX = "META-INF/versions/";

    /** What a document records when it came from the archive ROOT rather than
     *  from an overlay — the copy every JVM sees regardless of its version. */
    private static final String BASE_RELEASE = "base";

    /** The class-file majors the pinned ASM can actually parse (JVMS 4.1).
     *
     *  <p>45 is where the format starts and has never moved. The ceiling is a
     *  property of the ASM version this jar bundles, so it is asserted by
     *  {@code ClassFileVersionTest} against real bytes rather than trusted:
     *  `build.gradle.kts` already claimed "that range is pinned by a test in
     *  this same source tree" and no such test existed, which is how a ceiling
     *  drifts silently — a newer JDK's classes are refused and the refusal is
     *  the only thing that says so. */
    static final int ACCEPTED_MAJOR_MIN = 45;

    static final int ACCEPTED_MAJOR_MAX = 71;

    public static void main(String[] args) {
        try {
            Map<String, String> options = parse(args);
            // Asked BEFORE a scan, because capabilities decide which catalogs
            // run and the caller needs them without paying for an extraction.
            // `parse` reads argument PAIRS, so this flag is checked against the
            // raw arguments rather than through it.
            if (args.length == 1 && args[0].equals("--capabilities")) {
                List<String> named = new ArrayList<>();
                for (String capability : Capabilities.ALL) named.add(JsonOut.string(capability));
                TreeMap<String, String> answer = new TreeMap<>();
                answer.put("capabilities", JsonOut.array(named));
                System.out.println(JsonOut.object(answer));
                return;
            }
            Path classes = Path.of(options.get("classes"));
            Path out = Path.of(options.get("out"));
            ClassScanner scanner =
                new ClassScanner(options.get("coordinates"), options.get("version"));

            int documents = 0;
            int facts = 0;
            List<String> uncovered = new ArrayList<>();
            try (ClassSource source = ClassSource.of(classes)) {
                List<String> classFiles = source.names();
                // The silent-success hole, closed (2I Task 6). A `--classes`
                // that yields no class file at all used to report
                // `documents: 0, facts: 0` at exit 0 with an empty `uncovered`
                // — indistinguishable from a scan that genuinely found
                // nothing to say. The two honest shapes are split by what is
                // wrong: an input this extractor cannot READ is a failed
                // request and exits non-zero (`ClassSource.of` throws); an
                // input it read fine that simply holds no class file is a
                // finding ABOUT the input, so it rides the channel findings
                // already ride (FR-17's `uncovered`) and reaches
                // metadata.json and the rendered gaps list by itself. A jar of
                // zero classes is legitimate-but-suspicious, and this is what
                // makes it visible instead of silent.
                //
                // Named by the COORDINATE where one was given, and only by the
                // path otherwise. An `uncovered` entry is read by a person, in
                // metadata.json and in a published bundle: an absolute archive
                // path under someone's home directory identifies nothing once
                // it leaves the machine that produced it, while the coordinate
                // is the same name the configuration used to ask for it.
                if (classFiles.isEmpty()) {
                    String named = options.getOrDefault("origin", options.get("classes"));
                    uncovered.add(named + ": no class files found");
                }
                for (String classRelative : classFiles) {
                    // READ INSIDE the guard, not before it. A corrupt archive
                    // entry — a bad CRC, a truncated deflate stream — throws
                    // here rather than in the parse, and while this sat outside
                    // the guard that threw straight out of the loop: measured
                    // on a three-entry jar with one corrupt entry, exit 1 with
                    // ONE document on disk and nothing recording that two more
                    // were never attempted. An arbitrary unlabelled prefix is
                    // the one shape that is genuinely indistinguishable from a
                    // complete scan of a smaller archive.
                    byte[] bytes;
                    List<String> reasons = new ArrayList<>();
                    try {
                        bytes = source.read(classRelative);
                    } catch (Exception unreadable) {
                        bytes = new byte[0];
                        reasons.add("archive entry unreadable (" + unreadable + ")");
                    }
                    // JVMS 4.1 fixes `major_version` at offset 6, big-endian,
                    // and it is read from the BYTES rather than from ASM's own
                    // constant set — that set runs ahead of the reader, so it
                    // would answer for a class file this build cannot parse.
                    // Recorded on every document, readable or not: it is the
                    // one thing a refusal can still say about the class it
                    // refused, and it is what tells a reader whether a gap is
                    // "too new for this scanner" or something else.
                    int classMajor = majorVersionOf(bytes);
                    // D00 §2: one class file is one document, a nested or
                    // anonymous class's own file included. The id is the sha256
                    // of the **class**-relative path, so `OrderResult` and its
                    // nested `Detail` never collide on one id; `relative_path`
                    // instead names the outer **source** file, because that is
                    // the file a human edited. The two fields answer different
                    // questions on purpose.
                    String documentId = sha256(classRelative);
                    // Filled by the scan below, from the class file's own
                    // `SourceFile` attribute. A one-element array rather than a
                    // field on the scanner, which is reused across every entry
                    // in this loop and would carry the previous class's answer
                    // into a class that states none.
                    String[] sourceFile = {null};
                    // A Kotlin class compiled by a newer compiler than
                    // kotlin-metadata-jvm supports is not a corrupt class file —
                    // its nullability just cannot be read. The class is still
                    // scanned and its fact file still written (with Java's own
                    // rule standing in for the field), but the gap itself is an
                    // honesty obligation the same as a nested class's (FR-17).
                    // SKIPPED, NOT FATAL (Critical 1). One class this build
                    // cannot parse used to take the whole scan with it —
                    // `catch (Exception)` around this loop, exit 1, zero fact
                    // files — so a single class file from a JDK ahead of our
                    // ASM lost every other class in the module. It is now a
                    // finding ABOUT one class, on the channel findings already
                    // ride, and the document is still WRITTEN: its id, path,
                    // content hash and class-file major are all knowable
                    // without parsing it, and a class that vanishes silently is
                    // the failure FR-17 exists to prevent.
                    //
                    // `partial_reason` carries the exception's own text rather
                    // than a message of ours: what ASM refused is the fact, and
                    // predicting its wording would be a claim about a library
                    // we did not measure (§8.1).
                    // One `partial` flag, THREE ways to earn it, and D00 §2's
                    // definition covers all: "analysed incompletely, with a
                    // reason". An archive entry we could not read, a class we
                    // could not parse, and a Kotlin class whose metadata a
                    // newer compiler wrote in a form this build cannot decode —
                    // the last is still scanned and still yields facts, but its
                    // nullability is missing, which is exactly an incomplete
                    // analysis.
                    List<String> lines = List.of();
                    String partialReason = null;
                    if (reasons.isEmpty()) {
                        try {
                            lines = scanner.scan(bytes, documentId,
                                reason -> reasons.add("kotlin metadata unreadable (" + reason + ")"),
                                stated -> sourceFile[0] = stated);
                        } catch (IllegalArgumentException | IndexOutOfBoundsException unreadable) {
                            // Narrowed by TYPE, not only by scope. `catch (Exception)`
                            // swallowed OUR OWN defects too — an NPE in a visitor, a
                            // bad substring in signature parsing — and reported them
                            // as "class unreadable" at exit 0, so a regression in this
                            // extractor degraded a module to zero facts for the
                            // affected classes instead of failing loudly (§13.6).
                            //
                            // These two are what a class file this build cannot read
                            // actually throws: ASM refuses an unsupported major with
                            // IllegalArgumentException, and a truncated or malformed
                            // constant pool surfaces as an index error. Anything else
                            // is ours, and propagates.
                            lines = List.of();
                            reasons.add("class unreadable (" + unreadable + ")");
                        }
                    }
                    if (!reasons.isEmpty()) {
                        partialReason = String.join("; ", reasons);
                        uncovered.add(classRelative + ": " + partialReason);
                    }
                    // Named after the class file, not after `relative`: a
                    // nested class and its outer share a source path, and two
                    // documents writing to one file would leave only the
                    // last one on disk.
                    // D00 §2 defines `content_hash` as "of the source of truth
                    // this was read from". When the archive entry could not be
                    // read there IS no source of truth here, and hashing the
                    // empty array wrote sha256:e3b0c442… — the well-known hash
                    // of nothing — as though it were a measurement, and made
                    // two different corrupt entries hash-identical. A stated
                    // sentinel instead: absence, not a default (NFR-2).
                    String contentHash = bytes.length == 0 && partialReason != null
                        ? "unread"
                        : "sha256:" + sha256Bytes(bytes);
                    // AFTER the scan, because the class file is what names its own
                    // source. A class this build could not parse states nothing, and
                    // falls back to the derivation.
                    String relative = sourcePathOf(classRelative, sourceFile[0]);
                    writeFactFile(out.resolve(replaceSuffix(classRelative, ".class", ".jsonl")),
                                  relative, documentId, options, contentHash, lines,
                                  classMajor, partialReason, classReleaseOf(classRelative),
                                  withoutVersionPrefix(classRelative));
                    documents++;
                    facts += lines.size();
                }
            }
            System.out.println(report(documents, facts, uncovered));
        } catch (Exception failure) {
            System.err.println("extractor failed: " + failure);
            System.exit(1);
        }
    }

    /** Where the class files being scanned come from. Two forms, because a
     *  library ships as a jar and a module's own output does not: a directory
     *  tree of loose `.class` files, and a jar read as a zip.
     *
     *  <p>Both answer with class-relative POSIX names in one fixed sorted
     *  order, which is what keeps a scan byte-identical between runs and
     *  between platforms (NFR-1) — a zip's own entry order is whatever the
     *  archiver wrote and is never relied on. */
    private interface ClassSource extends Closeable {

        /** Every `.class` file this source holds, class-relative and sorted. */
        List<String> names() throws IOException;

        byte[] read(String name) throws IOException;

        /** Refuses anything it cannot read, rather than reporting an empty
         *  scan: a `--classes` naming a regular file that is not a jar (or a
         *  path that does not exist at all) is a failed REQUEST, and a failed
         *  request exits non-zero. */
        static ClassSource of(Path classes) throws IOException {
            if (Files.isDirectory(classes)) {
                return new DirectorySource(classes);
            }
            if (Files.isRegularFile(classes) && classes.getFileName().toString().endsWith(".jar")) {
                return new JarSource(classes);
            }
            throw new IllegalArgumentException(
                "--classes must name a directory of class files or a .jar file: " + classes);
        }
    }

    private record DirectorySource(Path root) implements ClassSource {

        @Override public List<String> names() throws IOException {
            try (Stream<Path> walk = Files.walk(root)) {
                return walk.filter(p -> p.toString().endsWith(".class"))
                           .map(p -> posix(root.relativize(p)))
                           .sorted()
                           .toList();
            }
        }

        @Override public byte[] read(String name) throws IOException {
            return Files.readAllBytes(root.resolve(name));
        }

        @Override public void close() {}
    }

    private static final class JarSource implements ClassSource {
        private final java.util.jar.JarFile zip;
        private final boolean multiRelease;

        JarSource(Path jar) throws IOException {
            // Throws on a file that is not a readable zip, which `of` above
            // lets propagate: a corrupt jar is an error, never an empty scan.
            //
            // A JarFile rather than a ZipFile purely so the manifest can be
            // PARSED. Deliberately NOT opened with a Runtime.Version: that
            // would make the jar hide its own overlays and pick for us, and
            // the selection is a property of the module doing the depending,
            // decided downstream at resolve (Fork 4) — not of the jar.
            // `verify = false`: `JarFile(File)` alone turns ON signature
            // verification, which digests every entry read and throws
            // SecurityException on a stale signature — common in shaded jars.
            // The manifest is all this needs; verifying is a cost and a failure
            // mode it never asked for.
            this.zip = new java.util.jar.JarFile(jar.toFile(), false);
            this.multiRelease = declaresMultiRelease(zip);
        }

        /** JEP 238's gate, read ONCE per archive.
         *
         *  <p>A parsed attribute lookup, never a grep: the jar specification
         *  makes attribute names case-insensitive (which
         *  {@code Attributes.getValue(String)} honours) and manifest values
         *  FOLD at 72 bytes with a leading-space continuation, so a text search
         *  can match half a value or miss a folded one. No manifest at all
         *  takes the same branch as an absent attribute. */
        private static boolean declaresMultiRelease(java.util.jar.JarFile jar) {
            // A manifest this cannot PARSE is not a jar we cannot read. `Manifest`
            // throws on a header line without a colon, a duplicate name, or a
            // stray continuation — all of which occur in real jars — and this ran
            // from the constructor, so one such dependency exited the whole scan
            // with zero fact files. That is the exact failure "an unreadable class
            // is skipped, not fatal" exists to prevent, reintroduced one level up.
            //
            // Unparseable answers `false`, which is the same branch as absent: the
            // JVM only searches `META-INF/versions/` when the manifest SAYS so,
            // and a manifest nobody can parse says nothing.
            try {
                var manifest = jar.getManifest();
                if (manifest == null) return false;
                String declared = manifest.getMainAttributes().getValue("Multi-Release");
                return declared != null && declared.trim().equalsIgnoreCase("true");
            } catch (IOException unparseable) {
                return false;
            }
        }

        @Override public List<String> names() {
            // Directory entries are skipped by the `.class` filter itself; a
            // zip may also omit them entirely, so nothing here may depend on
            // their presence.
            //
            // WITHOUT the attribute the overlays are not scanned AT ALL, and
            // that is not the same as treating them as ordinary classes: the
            // JVM never searches `META-INF/versions/` unless the manifest says
            // to, so those entries sit at a path no loader will look in. They
            // are unreachable code, and scanning them mints symbols that
            // collide with the reachable base copies.
            //
            // Measured across 2,402 cached jars: 6 carry `META-INF/versions/`
            // entries with no `Multi-Release: true`. `testcontainers-2.0.5.jar`
            // is the extreme — 1,218 such entries (shaded snakeyaml and jackson
            // paths a shade plugin copied in) under a manifest carrying only
            // Manifest-Version and Implementation-Version. This one check
            // removes 1,218 phantom documents from that jar alone.
            return zip.stream()
                      .map(ZipEntry::getName)
                      .filter(name -> name.endsWith(".class"))
                      .filter(name -> multiRelease || !name.startsWith(VERSIONS_PREFIX))
                      .sorted()
                      .toList();
        }

        @Override public byte[] read(String name) throws IOException {
            ZipEntry entry = zip.getEntry(name);
            try (var stream = zip.getInputStream(entry)) {
                return stream.readAllBytes();
            }
        }

        @Override public void close() throws IOException {
            zip.close();
        }
    }

    private static void writeFactFile(Path target, String relative, String documentId,
                                      Map<String, String> options, String contentHash,
                                      List<String> factLines, int classMajor,
                                      String partialReason, String classRelease,
                                      String className) throws IOException {
        Files.createDirectories(target.getParent());
        TreeMap<String, String> document = new TreeMap<>();
        document.put("kind", JsonOut.string("document"));
        document.put("document_id", JsonOut.string(documentId));
        document.put("relative_path", JsonOut.string(relative));
        document.put("module_id", JsonOut.string(options.get("module-id")));
        document.put("language", JsonOut.string("java"));
        document.put("sextant_version", JsonOut.string(required(options, "sextant-version")));
        // A JSON NUMBER, and handed in rather than held here (Step 0). Python
        // owns this stamp: nothing in this repository can see the Python
        // constant, which is why the literal that used to sit on this line
        // drifted to a value none of its three siblings held. A required
        // option cannot drift — it can only be absent, and absence is refused.
        document.put("fact_schema_version", String.valueOf(factSchemaVersion(options)));
        // The FACILITY that produced this document, not the library it used
        // (D00 §2's own rule, which `"asm"` broke). There is no
        // `scanner_version` beside it any more: this facility ships inside
        // Sextant and moves with `sextant_version` above, while the versions
        // that CAN move on their own — ASM, kotlin-metadata-jvm — are
        // third-party and are recorded ONCE per workspace in metadata.json
        // rather than repeated on every one of a module's documents.
        document.put("scanner_id", JsonOut.string(SCANNER_ID));
        document.put("content_hash", JsonOut.string(contentHash));
        document.put("origin_entry", JsonOut.string(options.get("classes")));
        // The library this document was extracted FROM, as its coordinate —
        // written only when `--origin` names one (D00 §2). Omitted entirely
        // for a module's own output, rather than written as null, so a scan
        // of a module is byte-for-byte the scan it was before opt-in library
        // extraction existed.
        //
        // The TIER moves with it, and must: `module_output` on a class this
        // module did not build is a claim known to be false. `dependency` is
        // the factual answer and deliberately not `first_party`/`third_party`
        // — those need the group patterns D04 §2 declares and nothing
        // implements, so either would be a guess about ownership dressed as
        // an observation (D00 §4).
        if (options.get("origin") != null) {
            document.put("origin", JsonOut.string(options.get("origin")));
            document.put("origin_tier", JsonOut.string("dependency"));
        } else {
            document.put("origin_tier", JsonOut.string("module_output"));
        }
        document.put("redaction_set_hash", JsonOut.string(options.getOrDefault("redaction-hash", "sha256:none")));
        // REAL, at last. Both were the literal strings "false" and "null" with
        // no code path able to set either, so every document claimed a complete
        // analysis whether or not it had one — and `partial_documents` reached
        // the rendered gaps list and the bundle's `coverage.partial` as a
        // number that could only ever be zero.
        document.put("partial", partialReason == null ? "false" : "true");
        document.put("partial_reason",
                     partialReason == null ? "null" : JsonOut.string(partialReason));
        // The class-file major this document was read from (JVMS 4.1). A JSON
        // number: it is compared and ordered against the accepted range, which
        // is the one stamp here that genuinely IS ordered.
        document.put("class_major", String.valueOf(classMajor));
        // TAG, DO NOT DROP (Fork 4). Which copy of an overlaid class this is:
        // `base`, or the release its `META-INF/versions/N/` prefix declares.
        // Nothing is discarded here and nothing is selected here — the target
        // release is a property of the MODULE doing the depending, so one scan
        // of a jar can serve two modules that declare different releases, and
        // deciding in the extractor would force a re-scan per consumer and put
        // a config-derived judgement inside the fact layer.
        document.put("class_release", JsonOut.string(classRelease));
        // The class-file's own name with any overlay prefix removed — the name
        // the JVM knows the class BY, which is what makes two copies of one
        // class recognisable as copies. `relative_path` cannot serve: it is the
        // SOURCE path, and a nested class shares its outer's, so grouping on it
        // would treat `A` and `A$B` as copies of each other.
        document.put("class_name", JsonOut.string(className));

        List<String> all = new ArrayList<>();
        all.add(JsonOut.object(document));
        all.addAll(factLines);
        Files.write(target, String.join("\n", all).concat("\n").getBytes("UTF-8"));
    }

    /** The class-file format version at JVMS 4.1's fixed offset: bytes 6-7,
     *  big-endian, immediately after the 4-byte magic and the 2-byte minor.
     *
     *  <p>Read from the FILE and never from ASM's constant set, which runs
     *  ahead of the reader that ships with it — asking ASM would answer for a
     *  class file this build cannot actually parse, which is the one case this
     *  value exists to describe.
     *
     *  <p>A file too short to hold a header cannot state a version, and
     *  {@link #ACCEPTED_MAJOR_MIN} - 1 would be a guess; it answers 0, which is
     *  outside every real range (JVMS 4.1 starts at 45) and so reads as
     *  "unknown" without colliding with any true value. */
    static int majorVersionOf(byte[] bytes) {
        if (bytes.length < 8) return 0;
        return ((bytes[6] & 0xFF) << 8) | (bytes[7] & 0xFF);
    }

    /** Forward slashes whatever the platform. `relative_path` is hashed into
     *  the document id and reappears in artifact names, so a backslash here
     *  would make one module produce different documents on Windows. */
    private static String posix(Path relative) {
        StringBuilder joined = new StringBuilder();
        for (Path part : relative) {
            if (joined.length() > 0) joined.append('/');
            joined.append(part);
        }
        return joined.toString();
    }

    /** Suffix-aware, because `String.replace` is a *global* substring replace:
     *  it rewrites every occurrence, so a workspace path holding ".java"
     *  anywhere would be corrupted mid-string rather than re-extensioned. */
    private static String replaceSuffix(String value, String from, String to) {
        if (!value.endsWith(from)) {
            throw new IllegalArgumentException("expected " + value + " to end with " + from);
        }
        return value.substring(0, value.length() - from.length()) + to;
    }

    /** The source file a class file was compiled from (D00 §2): everything from
     *  the class name's first {@code $} onwards is the compiler's nesting
     *  notation, not part of any file name — {@code OrderResult$Detail.class}
     *  and the anonymous {@code OrderController$1.class} were both edited as
     *  their outer class's {@code .java}.
     *
     *  <p>Searched from the last separator rather than across the whole path,
     *  because a directory is free to hold a {@code $} of its own and cutting
     *  there would name a source file in a package that does not exist. */
    private static String sourcePathOf(String classRelative, String sourceFile) {
        // The overlay prefix is stripped FIRST, or the derived source path is a
        // file that cannot exist:
        // `META-INF/versions/21/org/.../VirtualThreadDelegate.java` names no
        // file in any repository. An overlay is a different COMPILATION of the
        // same source, not a different source.
        String withoutSuffix = replaceSuffix(withoutVersionPrefix(classRelative), ".class", "");
        int lastSlash = withoutSuffix.lastIndexOf('/');
        if (namesAFile(sourceFile)) {
            // The class file STATES its source file's name (JVMS 4.7.10). Only the
            // directory is ours to supply, and it is the class's own — which is the
            // package path for every language whose files live in package directories.
            return lastSlash < 0 ? sourceFile : withoutSuffix.substring(0, lastSlash + 1) + sourceFile;
        }
        // Nothing stated it — a class compiled with debug information stripped. The
        // derivation below is what this always did, and it is a guess in the shape of
        // javac's own conventions: `.java`, and everything from the first `$` cut off
        // because that is the compiler's nesting notation rather than part of a name.
        int nested = withoutSuffix.indexOf('$', lastSlash + 1);
        return (nested < 0 ? withoutSuffix : withoutSuffix.substring(0, nested)) + ".java";
    }

    /** Whether a {@code SourceFile} value can be joined to a directory as a file name.
     *
     *  <p>It is a free-form constant-pool string, not a validated path, and it reaches
     *  `relative_path` — which is hashed into artifact names and read by anything that
     *  opens a file. A value carrying a separator or naming a directory is refused and
     *  the derivation stands in: what a class file says about itself is evidence, not
     *  an instruction. */
    private static boolean namesAFile(String sourceFile) {
        return sourceFile != null
            && !sourceFile.isEmpty()
            && sourceFile.indexOf('/') < 0
            && sourceFile.indexOf('\\') < 0
            // A drive-relative name — `C:Weird.java` — carries no separator and still
            // names no file once a directory is joined in front of it.
            && sourceFile.indexOf(':') < 0
            && !sourceFile.equals(".")
            && !sourceFile.equals("..");
    }

    /** The release an overlaid entry declares, or {@link #BASE_RELEASE}.
     *
     *  <p>Read from the PATH, which is where JEP 238 puts it. A malformed
     *  segment — `META-INF/versions/notanumber/…` — is treated as base rather
     *  than guessed at or refused: the entry is still a real class file, and
     *  inventing a release for it would be a claim the archive never made. */
    private static String classReleaseOf(String classRelative) {
        int release = versionOf(classRelative);
        return release < 0 ? BASE_RELEASE : String.valueOf(release);
    }

    /** The release an overlay path declares, or -1 when the path is not a valid
     *  overlay at all.
     *
     *  <p>ONE decision, shared with {@link #withoutVersionPrefix}, because the
     *  two used to disagree: this validated the segment and fell back to `base`,
     *  while the other stripped the prefix unconditionally. A path like
     *  `META-INF/versions/notanumber/com/x/Y.class` was then simultaneously NOT
     *  an overlay (tagged `base`) and one (named `com/x/Y.class`) — so it shared
     *  a name and a release with the genuine base copy, and which survived
     *  selection was decided by a sha256.
     *
     *  <p>JEP 238 requires a positive integer of at least 9 — versioned entries
     *  did not exist before Java 9 — so `-1`, `+21` and `8` are not releases,
     *  and `Integer.parseInt` alone accepted all three. */
    private static int versionOf(String classRelative) {
        if (!classRelative.startsWith(VERSIONS_PREFIX)) return -1;
        int end = classRelative.indexOf('/', VERSIONS_PREFIX.length());
        if (end < 0) return -1;
        String segment = classRelative.substring(VERSIONS_PREFIX.length(), end);
        if (segment.isEmpty()) return -1;
        for (int i = 0; i < segment.length(); i++) {
            if (segment.charAt(i) < '0' || segment.charAt(i) > '9') return -1;
        }
        try {
            int release = Integer.parseInt(segment);
            return release >= 9 ? release : -1;
        } catch (NumberFormatException tooLarge) {
            return -1;
        }
    }

    /** The class-relative name with any `META-INF/versions/N/` prefix removed —
     *  the name the class is KNOWN by, which is what makes two copies of one
     *  class recognisable as copies downstream. */
    private static String withoutVersionPrefix(String classRelative) {
        // Strips only where {@link #versionOf} agrees this IS an overlay, so the
        // two helpers cannot answer differently about one path.
        if (versionOf(classRelative) < 0) return classRelative;
        return classRelative.substring(classRelative.indexOf('/', VERSIONS_PREFIX.length()) + 1);
    }

    private static String report(int documents, int facts, List<String> uncovered)
            throws IOException {
        List<String> quoted = new ArrayList<>();
        for (String source : uncovered) quoted.add(JsonOut.string(source));
        TreeMap<String, String> fields = new TreeMap<>();
        fields.put("documents", String.valueOf(documents));
        fields.put("facts", String.valueOf(facts));
        fields.put("scanner_id", JsonOut.string(SCANNER_ID));
        // What actually read the class files, with the versions Gradle
        // RESOLVED — provenance a consumer can act on, in place of the literal
        // "9.18" that named no ASM release at all.
        List<String> libraries = new ArrayList<>();
        for (String coordinate : scannerLibraries()) libraries.add(JsonOut.string(coordinate));
        fields.put("scanner_libraries", JsonOut.array(libraries));
        // What THIS jar can read (Capabilities). Reported rather than assumed
        // by the caller: the jar is built by a separate step, so a Python-side
        // list is a claim about a binary that may be older than the claim, and
        // it gates which catalogs run.
        List<String> capabilities = new ArrayList<>();
        for (String capability : Capabilities.ALL) capabilities.add(JsonOut.string(capability));
        fields.put("capabilities", JsonOut.array(capabilities));
        fields.put("uncovered", JsonOut.array(quoted));
        return JsonOut.object(fields);
    }

    private static Map<String, String> parse(String[] args) {
        Map<String, String> options = new HashMap<>();
        for (int i = 0; i < args.length - 1; i += 2) {
            options.put(args[i].replaceFirst("^--", ""), args[i + 1]);
        }
        return options;
    }

    /** An option this extractor will not invent a value for. A default here is
     *  a second copy of somebody else's constant, and the one that used to
     *  stand in for `--fact-schema-version` is exactly how four producers of
     *  one stamp came to hold two values (Step 0). Absent is a failed request. */
    private static String required(Map<String, String> options, String name) {
        String value = options.get(name);
        if (value == null) {
            throw new IllegalArgumentException("--" + name + " is required");
        }
        return value;
    }

    /** Parsed rather than passed through, because it is written as a JSON
     *  NUMBER: a value that cannot be an integer would otherwise leave this
     *  extractor emitting a fact file no reader can parse. */
    private static int factSchemaVersion(Map<String, String> options) {
        String value = required(options, "fact-schema-version");
        try {
            return Integer.parseInt(value);
        } catch (NumberFormatException notAnInteger) {
            throw new IllegalArgumentException(
                "--fact-schema-version must be an integer, got: " + value);
        }
    }

    /** This jar's own scanning libraries, `group:artifact:version` each, in the
     *  order the build sorted them.
     *
     *  <p>Read through {@link java.util.jar.Manifest} and never by scanning the
     *  file's text: manifest values FOLD at 72 bytes with a leading-space
     *  continuation, so this attribute arrives split across lines and a
     *  substring search would return half a coordinate.
     *
     *  <p>Absent is a FAILED BUILD, not an empty list — a jar that cannot say
     *  what read the class files has lost the provenance a consumer uses to
     *  decide whether to trust a bundle, and answering `[]` would publish that
     *  loss as a fact. */
    private static List<String> scannerLibraries() throws IOException {
        java.net.URL source = Main.class.getProtectionDomain().getCodeSource().getLocation();
        // `toURI`, never `getPath()`: a URL's path is URL-ENCODED, so an install
        // under `/Users/me/My Projects/` arrives as `My%20Projects` and names a
        // file that does not exist. That failed EVERY scan on such a machine —
        // and did it from `report()`, after every fact file had been written, so
        // the whole extraction was thrown away with a FileNotFoundException
        // pointing nowhere near the cause.
        java.io.File located;
        try {
            located = new java.io.File(source.toURI());
        } catch (java.net.URISyntaxException notAUri) {
            throw new IOException("cannot locate this jar from " + source, notAUri);
        }
        try (var jar = new java.util.jar.JarFile(located)) {
            var manifest = jar.getManifest();
            String value = manifest == null
                ? null
                : manifest.getMainAttributes().getValue(LIBRARIES_ATTRIBUTE);
            if (value == null || value.isBlank()) {
                throw new IllegalStateException(
                    LIBRARIES_ATTRIBUTE + " is missing from " + source
                        + " — the extractor cannot state what produced its facts");
            }
            return List.of(value.split(","));
        }
    }

    private static String sha256(String value) throws Exception {
        return sha256Bytes(value.getBytes("UTF-8"));
    }

    private static String sha256Bytes(byte[] value) throws Exception {
        StringBuilder hex = new StringBuilder();
        for (byte b : MessageDigest.getInstance("SHA-256").digest(value)) {
            hex.append(String.format("%02x", b));
        }
        return hex.toString();
    }
}
