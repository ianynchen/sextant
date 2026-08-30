package dev.sextant.extractor;

import java.util.ArrayList;
import java.util.List;
import java.util.TreeMap;
import org.objectweb.asm.Handle;
import org.objectweb.asm.Opcodes;
import org.objectweb.asm.Type;
import org.objectweb.asm.tree.AbstractInsnNode;
import org.objectweb.asm.tree.FieldInsnNode;
import org.objectweb.asm.tree.InsnList;
import org.objectweb.asm.tree.IntInsnNode;
import org.objectweb.asm.tree.InvokeDynamicInsnNode;
import org.objectweb.asm.tree.LdcInsnNode;
import org.objectweb.asm.tree.MethodInsnNode;
import org.objectweb.asm.tree.MethodNode;
import org.objectweb.asm.tree.TypeInsnNode;
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

    /** One JSON line per invoke instruction — {@code invokedynamic} included,
     *  which is why an {@code ordinal} counts positions a reader of the source
     *  cannot always see: a string concatenation is an invoke to the JVM. */
    public static List<String> callSites(String documentId, String callerSymbol, MethodNode method) {
        Frame<SourceValue>[] frames;
        try {
            frames = new Analyzer<>(new CopyTransparentSourceInterpreter())
                .analyze(ownerOf(callerSymbol), method);
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
            Target target = targetOf(insns[i]);
            if (target == null) continue;
            Frame<SourceValue> frame = frames[i];
            // Unreachable code: no frame ever reached this invoke. It keeps its
            // ordinal — the position is a property of the instruction list, not
            // of what the analyser managed to reach — but has no values to read.
            if (frame == null) {
                ordinal++;
                continue;
            }
            Type[] argumentTypes = Type.getArgumentTypes(target.descriptor());
            // Stack layout at an invoke: ... receiver? arg0 .. argN-1. ASM's
            // frame keeps one stack entry per value, long and double included,
            // so a slot index is an argument index.
            int base = frame.getStackSize() - argumentTypes.length;
            List<String> arguments = new ArrayList<>();
            for (int a = 0; a < argumentTypes.length; a++) {
                arguments.add(argumentJson(frame.getStack(base + a), argumentTypes[a], instructions));
            }
            Integer receiver = target.hasReceiver()
                ? sourceId(frame.getStack(base - 1), instructions)
                : null;
            Integer result = Type.getReturnType(target.descriptor()).getSort() == Type.VOID ? null : i;
            lines.add(callSiteJson(documentId, callerSymbol, target, ordinal++, receiver, result,
                                   arguments));
        }
        return lines;
    }

    /** {@code SourceInterpreter}, except that **moving or re-typing a value is
     *  not producing it**. ASM's own {@code copyOperation} mints a fresh
     *  {@code SourceValue} attributed to the copying instruction; this one
     *  hands back the value it was given, so a value's source stays the
     *  instruction that computed it.
     *
     *  <p>{@code copyOperation} is called for exactly seventeen opcodes — the
     *  five loads, the five stores, the six DUPs and {@code SWAP} — and every
     *  one of them only relocates a value between the stack and a local. None
     *  computes anything, so none is an origin, and the rule needs no exception
     *  list.
     *
     *  <p>{@code CHECKCAST} does not arrive at {@code copyOperation} — ASM
     *  routes it through {@code unaryOperation} instead — but it earns the
     *  same treatment for the same reason: a successful cast is still the
     *  identical reference, only re-labelled with a narrower static type, so
     *  {@link #unaryOperation} special-cases it below rather than falling
     *  through to {@code SourceInterpreter}'s default (which would mint a new
     *  value, same as any other unary op that actually computes one).
     *
     *  <p>Three joins depend on this, and none is exotic:
     *
     *  <ul>
     *  <li>{@code NEW T; DUP; INVOKESPECIAL T.<init>} — without transparency the
     *  constructor's receiver names the DUP while the value handed to the
     *  enclosing call names the NEW, so one object carries two ids and D02 §2h's
     *  one-hop body follow has nothing to join on.</li>
     *  <li>{@code Request r = builder.build(); client.newCall(r);} — the shape
     *  every OkHttp caller actually writes. Without transparency the store and
     *  the reload sit between the two halves, {@code newCall}'s argument is an
     *  {@code unresolved} with no {@code source} at all, and a split builder
     *  chain cannot be reconstructed on honest code.</li>
     *  <li>{@code webClient.post().uri(...).bodyValue(...)} — a mid-chain hop
     *  inherited from a generic self-type interface ({@code UriSpec<S extends
     *  RequestHeadersSpec<S>>}) whose erased return type is the bound, not the
     *  caller's own narrower static type, so javac inserts a {@code CHECKCAST}
     *  between {@code uri(...)}'s result and {@code bodyValue(...)}'s receiver.
     *  Without transparency here, every WebClient/RestClient chain that sets a
     *  request body mid-chain stops one hop short of its terminal and derives
     *  nothing — proven live against the Phase 2C fixture's compiled
     *  {@code InventoryWebClient#reserve}/{@code OrdersRestClient#submitMirror}
     *  before this fix, both silently missing.</li>
     *  </ul>
     *
     *  <p>The cost, stated rather than discovered later: a receiver or argument
     *  that arrives as a **method parameter** has no producing instruction in
     *  this method — it existed before the first bytecode ran — so it now reads
     *  as null where it used to report the index of the load. That is the more
     *  honest answer, and nothing consumes the old one: a fluent root matches by
     *  owner and method, and a step join runs call-result to receiver. A local
     *  reassigned on two branches still merges to several producers and stays
     *  {@code unresolved}, which is the same honest silence as before. */
    private static final class CopyTransparentSourceInterpreter extends SourceInterpreter {
        CopyTransparentSourceInterpreter() {
            super(Opcodes.ASM9);
        }

        @Override
        public SourceValue copyOperation(AbstractInsnNode insn, SourceValue value) {
            return value;
        }

        /** {@code CHECKCAST} is the one unary op that re-labels a value's
         *  static type without computing a new one; every other unary op
         *  (`INSTANCEOF`, `ARRAYLENGTH`, `NEWARRAY`/`ANEWARRAY`, the numeric
         *  conversions, `GETFIELD`, …) genuinely produces a fresh value and
         *  keeps {@code SourceInterpreter}'s default behaviour. */
        @Override
        public SourceValue unaryOperation(AbstractInsnNode insn, SourceValue value) {
            return insn.getOpcode() == Opcodes.CHECKCAST ? value : super.unaryOperation(insn, value);
        }
    }

    /** What a call site needs to know about its callee, read from whichever of
     *  the JVM's two invoke shapes this instruction is — or null when it is not
     *  an invoke at all.
     *
     *  <p>An {@code invokedynamic} is a call site (D00 §5's {@code dynamic}
     *  dispatch form) and skipping it would be silent: the value it produces is
     *  already reachable as another argument's {@code source}, so an unemitted
     *  indy leaves that join pointing at nothing — a string concatenation, a
     *  lambda, a record's {@code toString} all dead-end there. */
    private static Target targetOf(AbstractInsnNode insn) {
        if (insn instanceof MethodInsnNode invoke) {
            return new Target(invoke.owner, invoke.name, invoke.desc,
                              invokeKind(invoke.getOpcode()),
                              invoke.getOpcode() != Opcodes.INVOKESTATIC);
        }
        if (insn instanceof InvokeDynamicInsnNode indy) {
            // An indy has no receiver, and therefore no owner in the sense every
            // other call site means it: the name and descriptor on the
            // instruction describe the *call site's* signature, not a method on
            // some type. What does say what the site means is the bootstrap
            // method's owner — `LambdaMetafactory`, `StringConcatFactory`,
            // `ObjectMethods` — so that is what `owner` records, and a consumer
            // reading the target triple learns which of them it is looking at
            // rather than "a method called `apply` on nothing in particular".
            return new Target(indy.bsm.getOwner(), indy.name, indy.desc, "dynamic", false);
        }
        return null;
    }

    /** One invoke's callee, in the two spellings the JVM has for it. */
    private record Target(String owner, String name, String descriptor, String invokeKind,
                          boolean hasReceiver) {}

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
        // `NEW Type; DUP; INVOKESPECIAL <init>` — and the value that reaches an
        // argument slot is the one the NEW pushed, never the constructor's:
        // `<init>` returns void and produces no value at all. So the NEW is the
        // *only* instruction that names the concrete type here, and the concrete
        // type is what D00 §5a's PTR carrier and D02's one-hop body follow both
        // read.
        //
        // The `source` is that same NEW's index, and it is what makes D02 §2h's
        // one-hop follow a join rather than a search: the constructor call site
        // in this method whose `receiver` equals this id is the one that built
        // this value, and its arguments are the payload. That agreement is only
        // true because CopyTransparentSourceInterpreter above keeps the DUP from
        // standing between the two.
        if (producer instanceof TypeInsnNode created && created.getOpcode() == Opcodes.NEW) {
            return argument("instance", null,
                            JsonOut.string(TypeRefs.descriptorName(Type.getObjectType(created.desc))),
                            String.valueOf(instructions.indexOf(producer)));
        }
        if (producer instanceof InvokeDynamicInsnNode indy) {
            // A lambda's code is not here: javac lifted the body into a
            // synthetic method and the call site only names it, in the
            // bootstrap's second argument. A method reference bootstraps
            // identically and names the referenced method itself.
            String implementation = lambdaSymbol(indy);
            // Now that an indy is a call site of its own, the value it produced
            // has a `result` id — so the same join a plain call's result gets
            // applies, whether or not the kind resolved to `lambda`.
            return argument(implementation == null ? "unresolved" : "lambda", null, implementation,
                            String.valueOf(instructions.indexOf(producer)));
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

    /** The symbol of the method a {@code LambdaMetafactory} call site will
     *  invoke, or null when this indy is bootstrapped by something else — a
     *  string concatenation, a record's generated {@code equals}, a framework's
     *  own bootstrap. Those are honest {@code unresolved}s: there is no
     *  implementation method to name.
     *
     *  <p>Both {@code metafactory} and {@code altMetafactory} put the
     *  implementation handle in the same slot, behind the SAM method type.
     *
     *  <p>The **bare descriptor path** — {@code java/lang/String#trim(sig_…).} —
     *  with no coordinates prefix, exactly like the {@code class}, {@code enum}
     *  and {@code instance} kinds beside it. A method reference is very often
     *  into a library, and D00 §1 requires that two modules seeing the same
     *  library type produce the same string: stamping the *caller's* module
     *  coordinates onto {@code java/lang/String} would mint a different symbol
     *  for {@code String::trim} in every module that used it, and none of them
     *  would join to the other. An in-module reference is joined to its own
     *  method fact by the descriptor suffix, which is what every consumer of
     *  these symbols already keys on. */
    private static String lambdaSymbol(InvokeDynamicInsnNode indy) {
        if (!"java/lang/invoke/LambdaMetafactory".equals(indy.bsm.getOwner())) return null;
        if (indy.bsmArgs.length < 2 || !(indy.bsmArgs[1] instanceof Handle implementation)) return null;
        return JsonOut.string(implementation.getOwner() + "#" + implementation.getName()
            + "(" + ClassScanner.disambiguatorOf(implementation.getDesc()) + ").");
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

    private static String callSiteJson(String documentId, String callerSymbol, Target invoke,
                                       int ordinal, Integer receiver, Integer result,
                                       List<String> arguments) {
        TreeMap<String, String> target = new TreeMap<>();
        // The owner goes through the same symbol grammar every type reference
        // uses, so an array receiver reads as `java/lang/String#[]` here too
        // rather than as the raw descriptor ASM hands back.
        target.put("owner", JsonOut.string(TypeRefs.descriptorName(Type.getObjectType(invoke.owner()))));
        target.put("name", JsonOut.string(invoke.name()));
        // D00 §5: the descriptor is what makes the target unambiguous — two
        // methods named `execute` are not the same method.
        target.put("descriptor", JsonOut.string(invoke.descriptor()));

        TreeMap<String, String> fact = new TreeMap<>();
        fact.put("kind", JsonOut.string("call_site"));
        fact.put("document_id", JsonOut.string(documentId));
        fact.put("caller", JsonOut.string(callerSymbol));
        fact.put("target", JsonOut.object(target));
        fact.put("invoke_kind", JsonOut.string(invoke.invokeKind()));
        fact.put("ordinal", String.valueOf(ordinal));
        fact.put("receiver", receiver == null ? "null" : String.valueOf(receiver));
        fact.put("result", result == null ? "null" : String.valueOf(result));
        fact.put("arguments", JsonOut.array(arguments));
        return JsonOut.object(fact);
    }

    /** D00 §5's dispatch forms, named after the JVM's own five —
     *  {@code dynamic} is settled at {@link #targetOf}, where the instruction
     *  shape rather than an opcode decides it. */
    private static String invokeKind(int opcode) {
        return switch (opcode) {
            case Opcodes.INVOKESTATIC -> "static";
            case Opcodes.INVOKEINTERFACE -> "interface";
            case Opcodes.INVOKESPECIAL -> "special";
            default -> "virtual";
        };
    }
}
