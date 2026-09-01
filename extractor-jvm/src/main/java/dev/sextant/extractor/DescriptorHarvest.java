package dev.sextant.extractor;

import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Base64;
import java.util.List;
import java.util.TreeMap;
import org.objectweb.asm.Opcodes;
import org.objectweb.asm.tree.AbstractInsnNode;
import org.objectweb.asm.tree.LdcInsnNode;
import org.objectweb.asm.tree.MethodInsnNode;
import org.objectweb.asm.tree.MethodNode;
import org.objectweb.asm.tree.TypeInsnNode;

/** D00 §5's {@code embedded_descriptor}: the schema payload a generated class
 *  carries verbatim, read out of its {@code <clinit>} as string constants and
 *  handed on **unparsed**.
 *
 *  <p>That is the whole layering rule (2G design §1): no extractor in any
 *  language links a schema runtime, because one interpreter in the Python core
 *  understands schema formats and nothing else does. This class therefore knows
 *  which constants to pick up and which charset they were mangled with — never
 *  what a descriptor means.
 *
 *  <p>Both formats compile to the **same bytecode shape**, which is why one
 *  harvest reads both: an {@code ANEWARRAY java/lang/String} filled by
 *  {@code LDC}s, handed to a static assembly call. protoc emits
 *  {@code Descriptors.FileDescriptor.internalBuildGeneratedFileFrom(descriptorData,
 *  dependencies)}; Avro's compiler emits
 *  {@code JsonSchemaParser.parseInternal(chunks)} into {@code SCHEMA$}.
 *
 *  <p>The array is what is read, never "the LDC": a Java string constant caps
 *  at 64KB, so a large descriptor arrives split across several elements and the
 *  payload is their concatenation in emission order. The array is also what
 *  bounds the read — a generated {@code <clinit>} is full of other string
 *  constants (the gencode version argument, and one {@code String[]} of
 *  camel-cased field names per {@code FieldAccessorTable}), so a harvest that
 *  collected the method's constants would emit field names glued to a
 *  descriptor. */
public final class DescriptorHarvest {
    private DescriptorHarvest() {}

    private static final String STRING_ARRAY_ARGUMENT = "([Ljava/lang/String;";

    /** protobuf's own loader for the constants below. Anchoring on the call
     *  rather than on the array is what tells the descriptor apart from every
     *  other {@code String[]} the same method builds. */
    private static final String PROTOBUF_OWNER = "com/google/protobuf/Descriptors$FileDescriptor";
    private static final String PROTOBUF_ASSEMBLY = "internalBuildGeneratedFileFrom";

    /** Avro 1.12's generated {@code SCHEMA$} initializer. Older generators wrote
     *  {@code new Schema.Parser().parse(<one string>)}, which builds no array at
     *  all and is therefore not harvested — a module on that version records no
     *  schema rather than a wrong one. */
    private static final String AVRO_OWNER = "org/apache/avro/JsonSchemaParser";
    private static final String AVRO_ASSEMBLY = "parseInternal";

    /** The Avro supertype a generated record extends (2G design §1). Checked at
     *  one hop because that is all a single class file offers — a class names
     *  its own direct supertype and nothing further — and generated code always
     *  extends it directly. It is what keeps the record's own schema apart from
     *  a hand-written class that happens to parse schemas at startup: there the
     *  class is not the record, so the fact would name a holder that holds
     *  nothing. */
    private static final String AVRO_RECORD_SUPERTYPE = "org/apache/avro/specific/SpecificRecordBase";

    /** One fact per **schema holder**, emitted from the holder's own document.
     *
     *  <p>For protobuf that is the outer class, never the message classes: a
     *  generated message extends {@code GeneratedMessage} /
     *  {@code GeneratedMessageV3} / {@code GeneratedMessageLite} and holds no
     *  descriptor bytes of its own — it calls the holder's
     *  {@code getDescriptor()} — so the supertype identifies a class the payload
     *  is *not* in, and a fact per message would be one payload copied once per
     *  type. (A lite-runtime message has no {@code FileDescriptor} anywhere in
     *  its generated code, so a lite-only artifact harvests nothing, which is a
     *  gap and never a guess.) For Avro the record class is itself the holder.
     *
     *  <p>Gated on {@code <clinit>} here, the way {@link MethodFlow#fieldWrites}
     *  gates on {@code <init>}, so the caller can call it for every method.
     *
     *  @param typeSymbol the holder's bare type descriptor
     *      ({@code com/example/orders/proto/OrderProtos#}) — the grammar every
     *      cross-document reference uses (D00 §1), and the one the interpreter's
     *      own shape symbols are keyed on
     *  @param superName the class's direct supertype, ASM's internal name
     */
    public static List<String> embeddedDescriptors(String documentId, String typeSymbol,
                                                   String superName, MethodNode method) {
        if (!"<clinit>".equals(method.name)) return List.of();
        List<String> lines = new ArrayList<>();
        List<String> chunks = null;
        for (AbstractInsnNode insn : method.instructions) {
            if (insn instanceof TypeInsnNode created && created.getOpcode() == Opcodes.ANEWARRAY
                    && "java/lang/String".equals(created.desc)) {
                // A new array supersedes the last one: the descriptor array is
                // the String[] opened most recently before the assembly call,
                // and the arrays built afterwards belong to something else.
                chunks = new ArrayList<>();
            } else if (insn instanceof LdcInsnNode constant && chunks != null
                    && constant.cst instanceof String text) {
                chunks.add(text);
            } else if (insn instanceof MethodInsnNode invoke && chunks != null && !chunks.isEmpty()) {
                String format = formatOf(invoke, superName);
                if (format != null) {
                    lines.add(factJson(documentId, typeSymbol, format, payloadOf(format, chunks)));
                    chunks = null;
                }
            }
        }
        return lines;
    }

    /** The schema format this call assembles, or null when it is not one of the
     *  two assembly calls at all.
     *
     *  <p>The descriptor test is not decoration: both calls take the constants
     *  as their **first** argument, and a same-named overload taking anything
     *  else would consume a different array than the one just read. */
    private static String formatOf(MethodInsnNode invoke, String superName) {
        if (!invoke.desc.startsWith(STRING_ARRAY_ARGUMENT)) return null;
        if (PROTOBUF_OWNER.equals(invoke.owner) && PROTOBUF_ASSEMBLY.equals(invoke.name)) {
            return "protobuf";
        }
        if (AVRO_OWNER.equals(invoke.owner) && AVRO_ASSEMBLY.equals(invoke.name)
                && AVRO_RECORD_SUPERTYPE.equals(superName)) {
            return "avro";
        }
        return null;
    }

    /** Protobuf embeds **binary** in a string: protoc writes each descriptor
     *  byte as one char, and protobuf-java's own loader reads them back with
     *  {@code latin1Cat} — {@code String.getBytes(ISO_8859_1)} per element,
     *  concatenated (verified against {@code protobuf-java} bytecode, not
     *  assumed). Re-encoding those chars as UTF-8 would silently double every
     *  byte above 0x7F, so the harvest states the charset rather than taking
     *  the platform's, and base64 is what carries the bytes through a JSON
     *  string intact.
     *
     *  <p>An Avro schema is JSON text that was always text: it travels verbatim,
     *  because encoding readable text would cost a reader the ability to read
     *  the fact stream and buy nothing. */
    private static String payloadOf(String format, List<String> chunks) {
        String joined = String.join("", chunks);
        return "protobuf".equals(format)
            ? Base64.getEncoder().encodeToString(joined.getBytes(StandardCharsets.ISO_8859_1))
            : joined;
    }

    /** {@code origin} is deliberately absent: the schema defaults it to
     *  {@code compiled}, and a class file is the only origin an extractor can
     *  ever report — a source-file reader is what says otherwise (2G design §2). */
    private static String factJson(String documentId, String typeSymbol, String format,
                                   String payload) {
        TreeMap<String, String> fact = new TreeMap<>();
        fact.put("kind", JsonOut.string("embedded_descriptor"));
        fact.put("document_id", JsonOut.string(documentId));
        fact.put("symbol", JsonOut.string(typeSymbol));
        fact.put("schema_format", JsonOut.string(format));
        fact.put("payload", JsonOut.string(payload));
        return JsonOut.object(fact);
    }
}
