package dev.sextant.extractor;

import java.util.ArrayList;
import java.util.List;
import java.util.TreeMap;
import org.objectweb.asm.Opcodes;
import org.objectweb.asm.Type;
import org.objectweb.asm.tree.AbstractInsnNode;
import org.objectweb.asm.tree.FieldInsnNode;
import org.objectweb.asm.tree.InsnList;
import org.objectweb.asm.tree.IntInsnNode;
import org.objectweb.asm.tree.LdcInsnNode;
import org.objectweb.asm.tree.MethodInsnNode;
import org.objectweb.asm.tree.MethodNode;
import org.objectweb.asm.tree.analysis.Analyzer;
import org.objectweb.asm.tree.analysis.AnalyzerException;
import org.objectweb.asm.tree.analysis.Frame;
import org.objectweb.asm.tree.analysis.SourceInterpreter;
import org.objectweb.asm.tree.analysis.SourceValue;

/** Per-method dataflow: which instruction produced each value an invoke
 *  consumes, emitted as D00 §5's {@code call_site} facts.
 *
 *  <p>Uses ASM's {@code Analyzer} with {@code SourceInterpreter}, because a
 *  {@code SourceValue}'s instruction set holds exactly one element for a
 *  straight-line producer and several after a branch merge — which is precisely
 *  the resolved/unresolved line D00 §5 draws. A merged value is genuinely two
 *  possible producers, and picking one of them would be a fact about code that
 *  may never run.
 *
 *  <p>Value ids are instruction indices: deterministic by construction (NFR-1),
 *  and meaningless across methods on purpose. D00 §5 makes that a property, not
 *  a limitation — chain reconstruction is a within-method join, and a chain that
 *  crosses a method boundary stops honestly rather than being stitched by
 *  proximity. */
public final class MethodFlow {
    private MethodFlow() {}

    /** One JSON line per invoke instruction, in instruction order. */
    public static List<String> callSites(String documentId, String callerSymbol, MethodNode method) {
        Frame<SourceValue>[] frames;
        try {
            frames = new Analyzer<>(new SourceInterpreter()).analyze(ownerOf(callerSymbol), method);
        } catch (AnalyzerException unanalysable) {
            // A body the analyser cannot walk yields no call facts. The method's
            // own symbol was already emitted, so the loss is bounded and visible
            // as "a method with no call sites", never as a missing method.
            return List.of();
        }
        InsnList instructions = method.instructions;
        AbstractInsnNode[] insns = instructions.toArray();
        List<String> lines = new ArrayList<>();
        int ordinal = 0;
        for (int i = 0; i < insns.length; i++) {
            if (!(insns[i] instanceof MethodInsnNode invoke)) continue;
            Frame<SourceValue> frame = frames[i];
            // Unreachable code: no frame ever reached this invoke. It keeps its
            // ordinal — the position is a property of the instruction list, not
            // of what the analyser managed to reach — but has no values to read.
            if (frame == null) {
                ordinal++;
                continue;
            }
            Type[] argumentTypes = Type.getArgumentTypes(invoke.desc);
            // Stack layout at an invoke: ... receiver? arg0 .. argN-1. ASM's
            // frame keeps one stack entry per value, long and double included,
            // so a slot index is an argument index.
            int base = frame.getStackSize() - argumentTypes.length;
            List<String> arguments = new ArrayList<>();
            for (int a = 0; a < argumentTypes.length; a++) {
                arguments.add(argumentJson(frame.getStack(base + a), argumentTypes[a], instructions));
            }
            Integer receiver = invoke.getOpcode() == Opcodes.INVOKESTATIC
                ? null
                : sourceId(frame.getStack(base - 1), instructions);
            Integer result = Type.getReturnType(invoke.desc).getSort() == Type.VOID ? null : i;
            lines.add(callSiteJson(documentId, callerSymbol, invoke, ordinal++, receiver, result,
                                   arguments));
        }
        return lines;
    }

    /** The owner's internal name, which is what {@code Analyzer.analyze} wants,
     *  read back out of the caller's symbol: the method symbol already carries
     *  it (D00 §1's {@code com/x/Y#member(sig_…).}), and a second parameter
     *  saying the same thing is a second place for it to disagree. */
    private static String ownerOf(String callerSymbol) {
        String descriptorPath = callerSymbol.substring(callerSymbol.lastIndexOf(' ') + 1);
        int member = descriptorPath.indexOf('#');
        return member < 0 ? descriptorPath : descriptorPath.substring(0, member);
    }

    /** One argument slot. The slot is always written, whatever the pass could
     *  make of it: an omitted slot silently renumbers every argument after it,
     *  which is why D00 §5 makes {@code unresolved} a first-class answer rather
     *  than an absence.
     *
     *  <p>{@code declaredType} is the descriptor's own argument type, and it is
     *  load-bearing: a boolean and an int both arrive as {@code ICONST_*}, and
     *  only the descriptor tells them apart. Reporting a flag as {@code 1}
     *  throws away the distinction the flag exists for. */
    private static String argumentJson(SourceValue value, Type declaredType, InsnList instructions) {
        AbstractInsnNode producer = singleSource(value);
        if (producer == null) return argument("unresolved", null, null, null);

        if (producer instanceof LdcInsnNode constant) {
            Object literal = constant.cst;
            if (literal instanceof String text) return argument("string", JsonOut.string(text), null, null);
            if (literal instanceof Integer number) {
                return declaredType.getSort() == Type.BOOLEAN
                    ? argument("boolean", String.valueOf(number.intValue() != 0), null, null)
                    : argument("int", String.valueOf(number), null, null);
            }
            if (literal instanceof Long number) return argument("long", String.valueOf(number), null, null);
            // An LDC of a Type is a class constant *only* for the two sorts a
            // class constant can have. ASM models a MethodType constant — legal
            // in any class file since Java 7, and what a method-handle-shaped
            // call site loads — as a Type of sort METHOD, on which
            // `descriptorName`'s fallback calls `getClassName()` and ASM throws
            // an AssertionError. That is an Error, not an Exception, so it
            // escapes Main's catch and takes the whole extraction down: no fact
            // files, no "extractor failed:" line, one class file's constant pool
            // silently costing every other class its facts.
            if (literal instanceof Type type
                    && (type.getSort() == Type.OBJECT || type.getSort() == Type.ARRAY)) {
                return argument("class", null, JsonOut.string(TypeRefs.descriptorName(type)), null);
            }
            // A float, a double, a method type, a method handle, a condy: no kind
            // in D00 §5's table, and inventing one is worse than saying so.
            return argument("unresolved", null, null, null);
        }
        if (producer instanceof IntInsnNode push
                && (push.getOpcode() == Opcodes.BIPUSH || push.getOpcode() == Opcodes.SIPUSH)) {
            return argument("int", String.valueOf(push.operand), null, null);
        }
        // GETSTATIC of a field whose type is its own owner: a **named constant of
        // its own type** — an enum, or something shaped exactly like one. That,
        // not "an enum", is the rule this implements, and the breadth is
        // deliberate rather than a tolerated imprecision. A closed set of named
        // constants declared as plain static finals instead of as a language
        // enum is the same fact to every consumer, libraries migrate between the
        // two spellings without changing what they mean, and an ACC_ENUM test
        // would silently drop half of them. The flag is not available here
        // anyway: it lives on the owning class, which this pass has not read and
        // may never see.
        //
        // The cost is named rather than hidden. A Kotlin `object`'s INSTANCE,
        // `BigDecimal.ZERO`, `Duration.ZERO` — all take this shape, all land
        // here. None of that is a defect to filter at emission: the referenced
        // type's own `construct_kind` settles true enum-ness (D00 §5b) and is
        // already a fact on disk, so the consumer that needs the distinction can
        // join for it. Guessing here, in the one place that cannot know, would
        // only make the answer unavailable to everyone.
        if (producer instanceof FieldInsnNode field && field.getOpcode() == Opcodes.GETSTATIC
                && Type.getType(field.desc).getSort() == Type.OBJECT
                && Type.getType(field.desc).getInternalName().equals(field.owner)) {
            return argument("enum", null, JsonOut.string(field.owner + "#" + field.name + "."), null);
        }
        if (producer instanceof MethodInsnNode) {
            // The value itself is out of reach, and the call that produced it is
            // not: this is the join that makes a chain split across two
            // statements — built here, passed there — reconstructable (D00 §5).
            return argument("unresolved", null, null, String.valueOf(instructions.indexOf(producer)));
        }
        return switch (producer.getOpcode()) {
            case Opcodes.ACONST_NULL -> argument("null", null, null, null);
            case Opcodes.ICONST_M1, Opcodes.ICONST_0, Opcodes.ICONST_1, Opcodes.ICONST_2,
                 Opcodes.ICONST_3, Opcodes.ICONST_4, Opcodes.ICONST_5 -> {
                int number = producer.getOpcode() - Opcodes.ICONST_0;
                yield declaredType.getSort() == Type.BOOLEAN
                    ? argument("boolean", String.valueOf(number != 0), null, null)
                    : argument("int", String.valueOf(number), null, null);
            }
            case Opcodes.LCONST_0, Opcodes.LCONST_1 ->
                argument("long", String.valueOf(producer.getOpcode() - Opcodes.LCONST_0), null, null);
            default -> argument("unresolved", null, null, null);
        };
    }

    private static String argument(String kind, String value, String symbol, String source) {
        TreeMap<String, String> entry = new TreeMap<>();
        entry.put("kind", JsonOut.string(kind));
        // Written only when they say something. Unlike an argument slot, whose
        // absence would renumber its neighbours, an absent key here is
        // unambiguous: D00 §5's grammar makes all three optional.
        if (value != null) entry.put("value", value);
        if (symbol != null) entry.put("symbol", symbol);
        if (source != null) entry.put("source", source);
        return JsonOut.object(entry);
    }

    /** The value id of a value with exactly one producer, or null. Several
     *  producers means a branch merged two of them, and D00 §5's answer to that
     *  is silence rather than a guess. */
    private static Integer sourceId(SourceValue value, InsnList instructions) {
        AbstractInsnNode producer = singleSource(value);
        return producer == null ? null : instructions.indexOf(producer);
    }

    private static AbstractInsnNode singleSource(SourceValue value) {
        // A method parameter's initial value has no producing instruction at
        // all, which reads as an empty set here.
        if (value == null || value.insns.size() != 1) return null;
        return value.insns.iterator().next();
    }

    private static String callSiteJson(String documentId, String callerSymbol, MethodInsnNode invoke,
                                       int ordinal, Integer receiver, Integer result,
                                       List<String> arguments) {
        TreeMap<String, String> target = new TreeMap<>();
        // The owner goes through the same symbol grammar every type reference
        // uses, so an array receiver reads as `java/lang/String#[]` here too
        // rather than as the raw descriptor ASM hands back.
        target.put("owner", JsonOut.string(TypeRefs.descriptorName(Type.getObjectType(invoke.owner))));
        target.put("name", JsonOut.string(invoke.name));
        // D00 §5: the descriptor is what makes the target unambiguous — two
        // methods named `execute` are not the same method.
        target.put("descriptor", JsonOut.string(invoke.desc));

        TreeMap<String, String> fact = new TreeMap<>();
        fact.put("kind", JsonOut.string("call_site"));
        fact.put("document_id", JsonOut.string(documentId));
        fact.put("caller", JsonOut.string(callerSymbol));
        fact.put("target", JsonOut.object(target));
        fact.put("invoke_kind", JsonOut.string(invokeKind(invoke.getOpcode())));
        fact.put("ordinal", String.valueOf(ordinal));
        fact.put("receiver", receiver == null ? "null" : String.valueOf(receiver));
        fact.put("result", result == null ? "null" : String.valueOf(result));
        fact.put("arguments", JsonOut.array(arguments));
        return JsonOut.object(fact);
    }

    /** D00 §5's dispatch forms, named after the JVM's own five. */
    private static String invokeKind(int opcode) {
        return switch (opcode) {
            case Opcodes.INVOKESTATIC -> "static";
            case Opcodes.INVOKEINTERFACE -> "interface";
            case Opcodes.INVOKESPECIAL -> "special";
            default -> "virtual";
        };
    }
}
