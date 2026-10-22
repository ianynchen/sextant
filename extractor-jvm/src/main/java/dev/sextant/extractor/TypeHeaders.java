package dev.sextant.extractor;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.jar.JarEntry;
import java.util.jar.JarFile;
import org.objectweb.asm.AnnotationVisitor;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassVisitor;
import org.objectweb.asm.FieldVisitor;
import org.objectweb.asm.Handle;
import org.objectweb.asm.Label;
import org.objectweb.asm.MethodVisitor;
import org.objectweb.asm.Opcodes;
import org.objectweb.asm.Type;

/**
 * The {@code type_header} fact (D00 §5): what a DEPENDENCY type extends, implements and is
 * annotated with — read from its class-file header in the resolved classpath, bodies never.
 *
 * <p><b>Why it exists.</b> An engine proves a type is a throwable by walking {@code extends}
 * facts to one of a few declared roots, and those facts exist only for classes this module
 * compiled. {@code MethodArgumentNotValidException extends BindException extends Exception} —
 * the first two live in spring-web and spring-context, so the walk stopped at the first and a
 * handler taking that parameter derived nothing from it. The previous escape scanned the WHOLE
 * jar on a user's say-so ({@code extract_libraries}); this reads one header per referenced
 * type instead, which is sub-millisecond each and bounded by the number of distinct types the
 * module names.
 *
 * <p><b>What it deliberately is not.</b> No method or field of a dependency class is read,
 * so no call edge, declaration or body arrives: {@code method_resolution}'s
 * {@code owner_not_scanned} is untouched, and a dependency type stays "not scanned" to every
 * consumer that asks whether its METHODS were — only its place in the hierarchy becomes known.
 * These facts are a kind of their own rather than {@code symbol}/{@code annotation} facts, so
 * no engine that mints endpoint rows from declarations can see a library's {@code @RestController}
 * through them (measured risk: a dependency's {@code CrudRepository} subinterface would otherwise
 * mint CRUD routes as this module's).
 *
 * <p><b>Two rules, both stated rather than left implicit.</b> A type found in several jars is
 * read from the FIRST on the classpath, which is what the JVM does. A type found in none — the
 * JDK's, or a dependency that did not resolve — gets no fact: the walk simply stops there, as it
 * always did, and the catalog's declared roots are the JDK boundary on purpose.
 */
final class TypeHeaders {

    /** One resolved dependency: the coordinate the facts name it by, its version, its jar. */
    record Entry(String coordinate, String version, Path archive) {}

    /** What one run produced, for the exit report and the synthetic document. */
    record Result(List<String> factLines, int headers, int unlocated) {}

    private TypeHeaders() {}

    /** {@code coordinate \t version \t archive}, one per line; blank lines ignored. */
    static List<Entry> readClasspathFile(Path file) throws IOException {
        List<Entry> entries = new ArrayList<>();
        for (String line : Files.readAllLines(file, StandardCharsets.UTF_8)) {
            if (line.isBlank()) continue;
            String[] parts = line.split("\t", -1);
            if (parts.length != 3) {
                throw new IllegalArgumentException(
                    "classpath file line is not `coordinate<TAB>version<TAB>archive`: " + line);
            }
            entries.add(new Entry(parts[0], parts[1], Path.of(parts[2])));
        }
        return entries;
    }

    /** Every internal class name {@code classBytes} refers to, from its header, its members'
     *  descriptors and its instructions. Primitives and arrays are reduced to the class they
     *  name, so {@code [Lcom/x/Foo;} contributes {@code com/x/Foo}. */
    static void collectReferences(byte[] classBytes, Set<String> into) {
        new ClassReader(classBytes).accept(new ReferenceCollector(into),
            ClassReader.SKIP_DEBUG | ClassReader.SKIP_FRAMES);
    }

    /** The header facts for every referenced type that is not the module's own and is found
     *  in the classpath, transitively up each one's superclass and interfaces. */
    static Result resolve(Set<String> referenced, Set<String> own, List<Entry> classpath,
                          String documentId) throws IOException {
        List<String> lines = new ArrayList<>();
        int unlocated = 0;
        Map<Path, JarFile> opened = new LinkedHashMap<>();
        try {
            Set<String> seen = new HashSet<>(own);
            Deque<String> queue = new ArrayDeque<>();
            for (String name : new java.util.TreeSet<>(referenced)) {
                if (seen.add(name)) queue.add(name);
            }
            while (!queue.isEmpty()) {
                String name = queue.poll();
                // A type whose class file sits in a DIRECTORY entry — a reactor sibling's own
                // `target/classes` — is scanned whole as a library root by the Python side,
                // so no header is written for it here and it is not "in no archive" either:
                // it was read, in full, elsewhere. Counting it unlocated said "203 unread"
                // on a module whose siblings were every one of them read (`mall-admin`).
                if (scannedElsewhere(name, classpath)) continue;
                Located located = locate(name, classpath, opened);
                if (located == null) {
                    unlocated++;
                    continue;
                }
                Header header = readHeader(located.bytes());
                lines.add(fact(documentId, name, header, located.entry()));
                if (header.superName != null && seen.add(header.superName)) queue.add(header.superName);
                for (String iface : header.interfaces) {
                    if (seen.add(iface)) queue.add(iface);
                }
            }
        } finally {
            for (JarFile jar : opened.values()) jar.close();
        }
        return new Result(lines, lines.size(), unlocated);
    }

    private record Located(Entry entry, byte[] bytes) {}

    /** Whether some directory entry on the classpath holds {@code name}'s class file. */
    private static boolean scannedElsewhere(String name, List<Entry> classpath) {
        for (Entry entry : classpath) {
            if (Files.isDirectory(entry.archive())
                    && Files.isRegularFile(entry.archive().resolve(name + ".class"))) {
                return true;
            }
        }
        return false;
    }

    /** First jar on the classpath holding {@code name}, which is the JVM's own rule. Jars are
     *  opened on first use and kept open for the run. */
    private static Located locate(String name, List<Entry> classpath, Map<Path, JarFile> opened)
            throws IOException {
        String entryName = name + ".class";
        for (Entry entry : classpath) {
            JarFile jar = opened.get(entry.archive());
            if (jar == null) {
                if (!Files.isRegularFile(entry.archive())) continue;
                jar = new JarFile(entry.archive().toFile(), false);
                opened.put(entry.archive(), jar);
            }
            JarEntry found = jar.getJarEntry(entryName);
            if (found == null) continue;
            try (InputStream in = jar.getInputStream(found)) {
                return new Located(entry, in.readAllBytes());
            }
        }
        return null;
    }

    private static final class Header {
        int access;
        String superName;
        String[] interfaces = new String[0];
        final List<String> annotations = new ArrayList<>();
    }

    /** The header alone: SKIP_CODE drops every method body before ASM parses it, and the
     *  visitor returns null for members, so nothing below the class level is even visited. */
    private static Header readHeader(byte[] bytes) {
        Header header = new Header();
        new ClassReader(bytes).accept(new ClassVisitor(Opcodes.ASM9) {
            @Override public void visit(int version, int access, String name, String signature,
                                        String superName, String[] interfaces) {
                header.access = access;
                header.superName = superName;
                header.interfaces = interfaces == null ? new String[0] : interfaces;
            }
            @Override public AnnotationVisitor visitAnnotation(String descriptor, boolean visible) {
                return ClassScanner.collectAnnotationUse(descriptor, header.annotations::add);
            }
            @Override public FieldVisitor visitField(int a, String n, String d, String s, Object v) {
                return null;
            }
            @Override public MethodVisitor visitMethod(int a, String n, String d, String s, String[] e) {
                return null;
            }
        }, ClassReader.SKIP_CODE | ClassReader.SKIP_DEBUG | ClassReader.SKIP_FRAMES);
        return header;
    }

    /** The symbol grammar {@link ClassScanner#symbolOf} uses, with the LIBRARY's own
     *  coordinate and version — a dependency class is not this module's, and its symbol
     *  must not say it is. Matching downstream is on the bare descriptor either way. */
    private static String symbol(Entry entry, String internalName) {
        return "sextant-jvm maven " + entry.coordinate().replace(':', '/') + " "
            + entry.version() + " " + internalName + "#";
    }

    private static String fact(String documentId, String name, Header header, Entry entry) {
        TreeMap<String, String> fact = new TreeMap<>();
        fact.put("kind", JsonOut.string("type_header"));
        fact.put("document_id", JsonOut.string(documentId));
        fact.put("symbol", JsonOut.string(symbol(entry, name)));
        fact.put("construct_kind", JsonOut.string(constructKind(header.access)));
        fact.put("superclass",
            header.superName == null || "java/lang/Object".equals(header.superName)
                ? "null" : JsonOut.string(symbol(entry, header.superName)));
        List<String> interfaces = new ArrayList<>();
        for (String iface : header.interfaces) interfaces.add(JsonOut.string(symbol(entry, iface)));
        fact.put("interfaces", JsonOut.array(interfaces));
        fact.put("annotations", JsonOut.array(header.annotations));
        fact.put("origin", JsonOut.string(entry.coordinate()));
        fact.put("version", JsonOut.string(entry.version()));
        return JsonOut.object(fact);
    }

    private static String constructKind(int access) {
        if ((access & Opcodes.ACC_ANNOTATION) != 0) return "annotation";
        if ((access & Opcodes.ACC_INTERFACE) != 0) return "interface";
        if ((access & Opcodes.ACC_ENUM) != 0) return "enum";
        if ((access & Opcodes.ACC_RECORD) != 0) return "record";
        return "class";
    }

    /** Every class name a class refers to. Reduced through {@link Type} so a descriptor,
     *  an array and a method signature all contribute the classes inside them. */
    private static final class ReferenceCollector extends ClassVisitor {
        private final Set<String> into;

        ReferenceCollector(Set<String> into) {
            super(Opcodes.ASM9);
            this.into = into;
        }

        private void type(Type type) {
            switch (type.getSort()) {
                case Type.OBJECT -> into.add(type.getInternalName());
                case Type.ARRAY -> type(type.getElementType());
                case Type.METHOD -> {
                    for (Type argument : type.getArgumentTypes()) type(argument);
                    type(type.getReturnType());
                }
                default -> { }
            }
        }

        private void descriptor(String descriptor) {
            if (descriptor != null) type(Type.getType(descriptor));
        }

        private void internal(String internalName) {
            if (internalName != null) into.add(internalName);
        }

        @Override public void visit(int v, int access, String name, String sig,
                                    String superName, String[] interfaces) {
            internal(superName);
            if (interfaces != null) for (String iface : interfaces) internal(iface);
        }

        @Override public AnnotationVisitor visitAnnotation(String descriptor, boolean visible) {
            descriptor(descriptor);
            return null;
        }

        @Override public FieldVisitor visitField(int access, String name, String descriptor,
                                                 String signature, Object value) {
            descriptor(descriptor);
            return new FieldVisitor(Opcodes.ASM9) {
                @Override public AnnotationVisitor visitAnnotation(String d, boolean visible) {
                    descriptor(d);
                    return null;
                }
            };
        }

        @Override public MethodVisitor visitMethod(int access, String name, String descriptor,
                                                   String signature, String[] exceptions) {
            descriptor(descriptor);
            if (exceptions != null) for (String thrown : exceptions) internal(thrown);
            return new MethodVisitor(Opcodes.ASM9) {
                @Override public AnnotationVisitor visitAnnotation(String d, boolean visible) {
                    descriptor(d);
                    return null;
                }
                @Override public AnnotationVisitor visitParameterAnnotation(int p, String d, boolean v) {
                    descriptor(d);
                    return null;
                }
                @Override public void visitTypeInsn(int opcode, String type) { internal(type); }
                @Override public void visitFieldInsn(int opcode, String owner, String n, String d) {
                    internal(owner);
                    descriptor(d);
                }
                @Override public void visitMethodInsn(int opcode, String owner, String n, String d,
                                                      boolean itf) {
                    internal(owner);
                    descriptor(d);
                }
                @Override public void visitLdcInsn(Object value) {
                    if (value instanceof Type t) type(t);
                    if (value instanceof Handle h) { internal(h.getOwner()); descriptor(h.getDesc()); }
                }
                @Override public void visitInvokeDynamicInsn(String n, String d, Handle bsm, Object... args) {
                    descriptor(d);
                    internal(bsm.getOwner());
                    for (Object arg : args) {
                        if (arg instanceof Type t) type(t);
                        if (arg instanceof Handle h) { internal(h.getOwner()); descriptor(h.getDesc()); }
                    }
                }
                @Override public void visitTryCatchBlock(Label s, Label e, Label h, String type) {
                    internal(type);
                }
                @Override public void visitMultiANewArrayInsn(String d, int dims) { descriptor(d); }
            };
        }
    }
}
