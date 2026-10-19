package dev.sextant.extractor;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.TreeMap;
import org.objectweb.asm.Handle;
import org.objectweb.asm.Opcodes;
import org.objectweb.asm.Type;
import org.objectweb.asm.tree.AbstractInsnNode;
import org.objectweb.asm.tree.FieldInsnNode;
import org.objectweb.asm.tree.InsnList;
import org.objectweb.asm.tree.IntInsnNode;
import org.objectweb.asm.tree.InvokeDynamicInsnNode;
import org.objectweb.asm.tree.JumpInsnNode;
import org.objectweb.asm.tree.LabelNode;
import org.objectweb.asm.tree.LdcInsnNode;
import org.objectweb.asm.tree.LookupSwitchInsnNode;
import org.objectweb.asm.tree.MethodInsnNode;
import org.objectweb.asm.tree.MethodNode;
import org.objectweb.asm.tree.TableSwitchInsnNode;
import org.objectweb.asm.tree.TryCatchBlockNode;
import org.objectweb.asm.tree.TypeInsnNode;
import org.objectweb.asm.tree.VarInsnNode;
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
        // A static method's parameter 0 lives in slot 0; an instance method's
        // slot 0 is `this`, which is a parameter of neither the descriptor nor
        // D00 §5's numbering.
        int[] parameterSlots = parameterSlotsOf(
            method.desc, (method.access & Opcodes.ACC_STATIC) != 0 ? 0 : 1);
        // A body the analyser cannot walk yields no call facts. The method's
        // own symbol was already emitted, so the loss is bounded and visible
        // as "a method with no call sites", never as a missing method.
        Frame<SourceValue>[] frames = analyze(callerSymbol, method);
        if (frames == null) return List.of();
        InsnList instructions = method.instructions;
        AbstractInsnNode[] insns = instructions.toArray();
        List<String> lines = new ArrayList<>();
        int ordinal = 0;
        for (int i = 0; i < insns.length; i++) {
            // `G-52`. An `ATHROW` leaves the method, and dropping it dropped half of
            // every exit path: MEASURED before this, a method whose only exit is a
            // throw published NO exit at all — a `call_site` for the exception's
            // CONSTRUCTOR and nothing saying the method then left through it. Building
            // an exception and throwing it are different acts, and code that builds one
            // to hand somewhere else read identically.
            //
            // It is still not a `method_return` — `methodReturns` refuses it for the
            // reason stated there, that an exception in the position a caller reads as a
            // returned value is a lie. D00 §5 reserves the other half and this produces
            // it: "the invoke-kind set includes `throw`: a throw site is a call-site-
            // shaped observation whose target is the thrown exception type".
            //
            // It shares the ORDINAL sequence, which renumbers the call sites that follow
            // a throw in the same method — measured on the fixture, 13 methods of 750.
            // That is forced rather than chosen: `ordinal` is D00's "index within its
            // method, assigned in instruction order", `call_edges` carries `(caller,
            // ordinal)` as its position, and a second sequence would put two rows there
            // meaning different things.
            if (insns[i].getOpcode() == Opcodes.ATHROW) {
                Frame<SourceValue> throwFrame = frames[i];
                // Unreachable, exactly as an unreachable invoke is: the ordinal is a
                // property of the instruction list, not of what the analyser reached.
                if (throwFrame == null) {
                    ordinal++;
                    continue;
                }
                lines.add(throwSiteJson(documentId, callerSymbol, ordinal++,
                    thrownType(throwFrame)));
                continue;
            }
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
                arguments.add(argumentJson(frame.getStack(base + a), argumentTypes[a], instructions,
                                           parameterSlots, frames, i));
            }
            Integer receiver = target.hasReceiver()
                ? sourceId(frame.getStack(base - 1), instructions)
                : null;
            // The other half of what `sourceId` cannot say. A receiver that arrives as a
            // parameter has no producing instruction, so `receiver` is null — the same
            // null a field receiver and an unreadable one get. The parameter marker the
            // interpreter mints is right there, and the argument grammar has read it as
            // `{"kind":"parameter"}` since 9.8; this reads it for the receiver slot and
            // names the index, so a walk can tell "the lambda's own parameter" from
            // "something I cannot see". Written only where there is an index to write.
            Integer receiverParameter = target.hasReceiver()
                ? parameterIndex(frame.getStack(base - 1), parameterSlots)
                : null;
            Integer result = Type.getReturnType(target.descriptor()).getSort() == Type.VOID ? null : i;
            lines.add(callSiteJson(documentId, callerSymbol, target, ordinal++, receiver,
                                   receiverParameter, result, implementationOf(insns[i]), arguments));
        }
        return lines;
    }

    /** The per-method dataflow pass both fact kinds read, or **null** where the
     *  analyser could not walk the body. Shared rather than duplicated, so
     *  {@link #callSites} and {@link #methodReturns} can never disagree about
     *  which value a given instruction popped. */
    private static Frame<SourceValue>[] analyze(String callerSymbol, MethodNode method) {
        try {
            return new Analyzer<>(new CopyTransparentSourceInterpreter())
                .analyze(ownerOf(callerSymbol), method);
        } catch (AnalyzerException unanalysable) {
            return null;
        }
    }

    /** D00 §5's {@code method_return} (capability 9.18): one line per return
     *  instruction, naming the value the method hands back.
     *
     *  <p>The value chain that makes a round trip readable is already extracted
     *  — an argument carries the {@code source} id of the call that produced it,
     *  and 993 of `mall-admin`'s 1,817 argument slots carry one — so
     *  {@code CommonPage#restPage}'s result flowing into {@code
     *  CommonResult#success} is a fact today. What was missing is the last link:
     *  nothing said that {@code success}'s result is what the METHOD returns.
     *  This is that link, and it is the same machinery one instruction further.
     *
     *  <p>**Every return form, not only {@code ARETURN}**, and the bytecode is
     *  modelled rather than collapsed:
     *
     *  <ul>
     *  <li>A primitive return reads through the same argument grammar an
     *  argument slot does, against the method's own declared return type — which
     *  is load-bearing for exactly the reason it is at a call site: a boolean
     *  and an int both arrive as {@code ICONST_*}.</li>
     *  <li>A {@code void} return pops nothing, and that is an ANSWER rather than
     *  a failure to read one: {@code value} is written as {@code null}, which no
     *  value-returning form can produce, so "returns nothing" is distinguishable
     *  from "returns something this pass could not name" ({@code
     *  {"kind":"unresolved"}}). The distinction is the whole reason the value is
     *  an argument entry and not a bare id.</li>
     *  <li>Several returns in one method are several facts, each with its own
     *  {@code ordinal}. A method with two {@code return} statements has two
     *  possible answers and no single one; picking either would be a fact about
     *  code that may never run, which is the same rule {@link #singleSource}
     *  applies to a merged value.</li>
     *  </ul>
     *
     *  <p>{@code ATHROW} is deliberately not a return. It leaves the method
     *  without handing a value back, and D00 §5 already reserves a separate
     *  {@code throw} observation for it; recording one here would put an
     *  exception in the position a caller reads as a returned value.
     *
     *  <p>An unreachable return keeps its ordinal and emits nothing, exactly as
     *  an unreachable invoke does in {@link #callSites}: the position is a
     *  property of the instruction list, not of what the analyser reached. */
    public static List<String> methodReturns(String documentId, String methodSymbol,
                                             MethodNode method) {
        Frame<SourceValue>[] frames = analyze(methodSymbol, method);
        if (frames == null) return List.of();
        Type returnType = Type.getReturnType(method.desc);
        int[] parameterSlots = parameterSlotsOf(
            method.desc, (method.access & Opcodes.ACC_STATIC) != 0 ? 0 : 1);
        InsnList instructions = method.instructions;
        AbstractInsnNode[] insns = instructions.toArray();
        List<String> lines = new ArrayList<>();
        int ordinal = 0;
        for (int i = 0; i < insns.length; i++) {
            if (!isReturn(insns[i].getOpcode())) continue;
            Frame<SourceValue> frame = frames[i];
            if (frame == null) {
                ordinal++;
                continue;
            }
            String value = insns[i].getOpcode() == Opcodes.RETURN
                ? null
                : argumentJson(frame.getStack(frame.getStackSize() - 1), returnType, instructions,
                               parameterSlots, frames, i);
            lines.add(methodReturnJson(documentId, methodSymbol, ordinal++, value));
        }
        return lines;
    }

    /** The six return opcodes, contiguous in the JVM's own numbering from
     *  {@code IRETURN} to {@code RETURN} — the five typed ones plus the void
     *  one, which is the last of them. */
    private static boolean isReturn(int opcode) {
        return opcode >= Opcodes.IRETURN && opcode <= Opcodes.RETURN;
    }

    private static String methodReturnJson(String documentId, String methodSymbol, int ordinal,
                                           String value) {
        TreeMap<String, String> fact = new TreeMap<>();
        fact.put("kind", JsonOut.string("method_return"));
        fact.put("document_id", JsonOut.string(documentId));
        fact.put("method", JsonOut.string(methodSymbol));
        fact.put("ordinal", String.valueOf(ordinal));
        // Written even when null, unlike an argument's own optional keys: here
        // the null IS the fact — a void return hands nothing back — and an
        // absent key would be indistinguishable from an extractor that does
        // not produce this at all.
        fact.put("value", value == null ? "null" : value);
        return JsonOut.object(fact);
    }

    /** D00 §5's {@code field_write}: constructors only, direct traces only. A
     *  {@code <init>} body's {@code ALOAD 0; xLOAD k; PUTFIELD} — with nothing
     *  in between — assigns parameter N straight to a field, and that triple
     *  is the whole rule. No dataflow pass is needed for it, unlike {@link
     *  #callSites}: the shape is syntactic, and a computed assignment
     *  (concatenation, a default expression, anything but the bare load)
     *  simply never presents the triple, so it emits nothing and the
     *  resolution that would have followed it degrades honestly rather than
     *  guessing a source.
     *
     *  <p>Scanned against the instruction list with label/line-number/frame
     *  pseudo-instructions filtered out first — they carry no opcode and are
     *  not computation, so their presence between the three real instructions
     *  must not count as "something intervened". */
    public static List<String> fieldWrites(
            String documentId, String methodSymbol, MethodNode method) {
        // **ANY INSTANCE METHOD, not constructors only** (spec
        // 2026-10-18-the-sixth-edge-design.md §0). The `<init>` guard that stood here was
        // never a soundness rule: a setter's assignment is the same instruction sequence as
        // a constructor's, which CP-33 row 1 measured — `aload_0; aload_1; putfield`,
        // "the triple, unchanged". Lifting it was measured too, by building this change and
        // re-scanning: `spring-petclinic-rest` 86 field writes becomes 237 and
        // `apollo-portal` 553 becomes 1,638, so the guard was hiding about two thirds of the
        // writes on real code. `OI-136` had always described capability 9.19 as exactly
        // this: "a write OUTSIDE an initialiser and a method-filter change".
        //
        // **Static methods stay out, and that is a soundness rule rather than a filter.**
        // Slot 0 holds `this` for an instance method, which is what `ALOAD 0` below reads
        // and what `parameterSlotsOf(desc, 1)` counts from; in a static method slot 0 is the
        // FIRST PARAMETER, so the same instructions mean something else and `PUTSTATIC` is a
        // different opcode anyway (CP-33 row 6, still unreported).
        if ((method.access & Opcodes.ACC_STATIC) != 0) return List.of();
        int[] parameterSlots = parameterSlotsOf(method.desc, 1);
        List<AbstractInsnNode> real = new ArrayList<>();
        for (AbstractInsnNode insn : method.instructions) {
            if (insn.getOpcode() >= 0) real.add(insn);
        }
        int[] block = basicBlocks(method, real);
        List<String> lines = new ArrayList<>();
        for (int i = 0; i + 2 < real.size(); i++) {
            if (!(real.get(i) instanceof VarInsnNode receiverLoad)
                    || receiverLoad.getOpcode() != Opcodes.ALOAD || receiverLoad.var != 0) {
                continue;
            }
            if (!(real.get(i + 2) instanceof FieldInsnNode put) || put.getOpcode() != Opcodes.PUTFIELD) {
                continue;
            }
            // **A write the SAME BASIC BLOCK overwrites never happens, and reporting it
            // publishes a value nothing can read.** `private String topic = "default";`
            // plus `this.topic = topic;` in the one constructor puts both writes in one
            // straight line — `ldc; putfield; aload_1; putfield`, measured — and the
            // initialiser is dead on every path. Found by review before this shipped, where
            // the dead literal was published as a `resolved` destination.
            //
            // **Only within one block, which is sound in the under-reporting direction.**
            // A later write behind a branch (`if (p) this.f = "b";`) leaves the earlier one
            // live when the branch is not taken, so it is kept. The case this therefore
            // still over-reports is an initialiser overwritten on EVERY branch of an
            // if/else, which needs post-dominance rather than a block comparison; the
            // register carries it rather than this comment pretending otherwise.
            if (overwrittenInBlock(real, block, i, put)) continue;
            AbstractInsnNode written = real.get(i + 1);
            // **Two kinds of write, and the second was invisible until 2026-10-18**
            // (`OI-138` cause 2). `this.f = parameter` loads the value from a local slot;
            // `private String f = "literal"` loads it from the CONSTANT POOL, which javac
            // compiles into the constructor as `ALOAD 0; LDC; PUTFIELD`. The fact could only
            // say "from parameter N", so a constant write had nothing to point at and no
            // fact was emitted — the walk then answered `no_writer` about a literal one line
            // above the read. Measured on `spring-petclinic-microservices`, where an outbound
            // HOST is held that way and the published row carried no address at all.
            if (written instanceof VarInsnNode valueLoad && isLoad(valueLoad.getOpcode())) {
                int parameterIndex = indexOfSlot(parameterSlots, valueLoad.var);
                if (parameterIndex < 0) continue;
                lines.add(fieldWriteJson(documentId, methodSymbol, put, parameterIndex, null));
            } else if (written instanceof LdcInsnNode constant) {
                // The declared type is handed over for the shared mapping's sake; for a
                // FIELD write it never decides anything, because javac has no `LDC` for an
                // int small enough to be a boolean. It is the call-site caller that needs
                // it.
                String value = literalEntry(constant.cst, Type.getType(put.desc));
                // A constant with no kind in D00 §5's table emits NOTHING rather than a
                // write whose value nobody can read.
                //
                // **The small-integer opcodes (`ICONST_*`, `BIPUSH`, `SIPUSH`) are not read
                // here, and the honest reason is not frequency.** A census over every
                // compiled module under `examples/` (3,568 classes, 56 modules) counts 7
                // `LDC` writes against 6 small-constant ones (`denyAll:Z`, `callCount:I`,
                // `accumulatedCallTime:J`), so "no measured input" would be false — what is
                // true is that none of the six is an ADDRESS or a destination, which is what
                // a consumer of this fact reads it for. An int arm would be a mechanism with
                // measured input and no measured consumer.
                if (value != null) {
                    lines.add(fieldWriteJson(documentId, methodSymbol, put, -1, value));
                }
            }
        }
        return lines;
    }

    /** Whether a LATER write to the same field sits in the same basic block as the write at
     *  {@code i}, which makes that write dead.
     *
     *  <p>Same field means same owner and name: a write to another object's field of the
     *  same name is a different field, and the {@code ALOAD 0} check above has already
     *  established that both of these write {@code this}.
     */
    private static boolean overwrittenInBlock(
            List<AbstractInsnNode> real, int[] block, int i, FieldInsnNode put) {
        for (int j = i + 3; j < real.size(); j++) {
            if (block[j] != block[i + 2]) return false;
            if (real.get(j) instanceof FieldInsnNode later
                    && later.getOpcode() == Opcodes.PUTFIELD
                    && later.owner.equals(put.owner)
                    && later.name.equals(put.name)) {
                return true;
            }
        }
        return false;
    }

    /** A block number per REAL instruction: two instructions share one when control cannot
     *  enter or leave between them.
     *
     *  <p>A boundary is a jump or switch (control leaves), a {@code return}/{@code throw}
     *  (likewise), or a label something jumps to or a handler covers (control enters). A
     *  label javac emits only to anchor a line number is NOT a boundary — treating it as one
     *  would put every statement in its own block, which is how a first attempt at this left
     *  the dead-write case unfixed.
     */
    private static int[] basicBlocks(MethodNode method, List<AbstractInsnNode> real) {
        Set<LabelNode> entered = new HashSet<>();
        for (AbstractInsnNode insn : method.instructions) {
            if (insn instanceof JumpInsnNode jump) {
                entered.add(jump.label);
            } else if (insn instanceof TableSwitchInsnNode table) {
                entered.add(table.dflt);
                entered.addAll(table.labels);
            } else if (insn instanceof LookupSwitchInsnNode lookup) {
                entered.add(lookup.dflt);
                entered.addAll(lookup.labels);
            }
        }
        if (method.tryCatchBlocks != null) {
            for (TryCatchBlockNode handler : method.tryCatchBlocks) {
                entered.add(handler.handler);
                entered.add(handler.start);
                entered.add(handler.end);
            }
        }
        int[] block = new int[real.size()];
        int current = 0;
        int at = 0;
        for (AbstractInsnNode insn : method.instructions) {
            if (insn instanceof LabelNode label && entered.contains(label)) current++;
            if (insn.getOpcode() < 0) continue;
            block[at++] = current;
            int opcode = insn.getOpcode();
            boolean leaves = insn instanceof JumpInsnNode
                    || insn instanceof TableSwitchInsnNode
                    || insn instanceof LookupSwitchInsnNode
                    || (opcode >= Opcodes.IRETURN && opcode <= Opcodes.RETURN)
                    || opcode == Opcodes.ATHROW;
            if (leaves) current++;
        }
        return block;
    }

    /** One of the five {@code xLOAD} opcodes — {@code ILOAD} through {@code
     *  ALOAD} are contiguous in the JVM's own numbering. */
    private static boolean isLoad(int opcode) {
        return opcode >= Opcodes.ILOAD && opcode <= Opcodes.ALOAD;
    }

    /** The local slot each declared parameter starts at, counting from {@code
     *  firstSlot} — 1 where slot 0 holds {@code this} (a constructor is never
     *  static), 0 for a static method, which is the only difference between
     *  the two callers. {@code long}/{@code double} occupy two slots, so a
     *  parameter's own index and its starting slot agree only up to the first
     *  wide one — the mapping the two-slot fixture case pins. */
    private static int[] parameterSlotsOf(String descriptor, int firstSlot) {
        Type[] parameterTypes = Type.getArgumentTypes(descriptor);
        int[] slots = new int[parameterTypes.length];
        int slot = firstSlot;
        for (int i = 0; i < parameterTypes.length; i++) {
            slots[i] = slot;
            slot += parameterTypes[i].getSize();
        }
        return slots;
    }

    /** The parameter index whose slot this is, or -1 when the loaded slot is
     *  not a parameter's own starting slot at all — {@code this} itself, a
     *  local declared inside the constructor body, or the second slot of a
     *  wide parameter loaded on its own (which no real bytecode does, since a
     *  {@code long}/{@code double} load always names the first slot). */
    private static int indexOfSlot(int[] parameterSlots, int slot) {
        for (int i = 0; i < parameterSlots.length; i++) {
            if (parameterSlots[i] == slot) return i;
        }
        return -1;
    }

    private static String fieldWriteJson(
            String documentId, String methodSymbol, FieldInsnNode field, int fromParameter,
            String value) {
        TreeMap<String, String> fact = new TreeMap<>();
        fact.put("kind", JsonOut.string("field_write"));
        fact.put("document_id", JsonOut.string(documentId));
        fact.put("field", JsonOut.string(field.owner + "#" + field.name + "."));
        // **WHICH method wrote it**, as the caller's own symbol form — the same string
        // `callSites` puts in `caller`, built by `ClassScanner` once per method. Without it
        // the fact says "some method's parameter N" and a reader has to guess among the
        // owner's methods: with the guard lifted a field commonly has several writers (a
        // constructor AND a setter, both assigning parameter 0), and guessing would cross to
        // the wrong method's callers and publish a value the field never held.
        //
        // The symbol rather than `name + desc`: the walk keys methods the way `call_edges`
        // names them, so carrying that form makes the edge a direct read instead of a
        // reconstruction nobody can check.
        fact.put("written_by", JsonOut.string(methodSymbol));
        // **Exactly one of the two**, and which one says what kind of write it was: a
        // parameter index, or the constant itself as an argument-grammar entry. `value` is
        // additive and absent by default, so every fact written before it reads unchanged
        // and `FACT_SCHEMA_VERSION` does not move — the property `written_by` and
        // `receiver_parameter` established, proved per release by
        // `scripts/probes/fact_additivity/run.py`.
        if (fromParameter >= 0) fact.put("from_parameter", String.valueOf(fromParameter));
        if (value != null) fact.put("value", value);
        return JsonOut.object(fact);
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
     *  {@code unresolved}, which is the same honest silence as before.
     *
     *  <p>Second exception, and the reason the first one's cost is bounded:
     *  **a parameter's initial value names the slot it arrived in**. That
     *  emptiness above made an argument fed straight from a parameter
     *  indistinguishable from one the pass genuinely could not read — both a
     *  bare {@code unresolved}, which D00 §5's `parameter` kind now separates.
     *  It cannot be fixed by making the {@code xLOAD} a producer (that is the
     *  very thing the three joins above forbid), so the *initial* value carries
     *  a marker instead: a {@code VarInsnNode} naming the slot, deliberately
     *  **not in the instruction list**.
     *
     *  <p>Everything else then keeps working untouched, which is why the marker
     *  lives here rather than in a second scan of its own: copy transparency
     *  propagates it through a store and a reload, so a parameter parked in a
     *  local still reads as that parameter; a slot reassigned from a call
     *  carries the call's value and reports that; and two parameters merged on
     *  a branch are two producers, so they stay {@code unresolved} exactly as
     *  two merged literals do. Because the marker indexes nothing, it is never
     *  a value **id** — {@link #sourceId} refuses it, which is what keeps the
     *  receiver contract above true. */
    private static final class CopyTransparentSourceInterpreter extends SourceInterpreter {
        CopyTransparentSourceInterpreter() {
            super(Opcodes.ASM9);
        }

        @Override
        public SourceValue copyOperation(AbstractInsnNode insn, SourceValue value) {
            return value;
        }

        /** The marker described above. {@code this} is tagged the same way and
         *  costs nothing: slot 0 is no parameter of the descriptor, so it maps
         *  to no index and reads {@code unresolved}, exactly as it did before. */
        @Override
        public SourceValue newParameterValue(boolean isInstanceMethod, int local, Type type) {
            return new SourceValue(
                type.getSize(), new VarInsnNode(type.getOpcode(Opcodes.ILOAD), local));
        }

        /** {@code CHECKCAST} is the one unary op that re-labels a value's
         *  static type without computing a new one; every other unary op
         *  ({@code INSTANCEOF}, {@code ARRAYLENGTH}, {@code NEWARRAY}/
         *  {@code ANEWARRAY}, the numeric conversions, {@code GETFIELD}, …)
         *  genuinely produces a fresh value and keeps {@code
         *  SourceInterpreter}'s default behaviour. */
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

    /** Capability 9.17: the method a call site's DISPATCH will land in, where
     *  the instruction's own target does not name it — or null wherever the
     *  target already is the answer.
     *
     *  <p>Only an {@code invokedynamic} has the gap, and only some of those.
     *  {@link #targetOf} records the bootstrap method's owner, which is what
     *  says what the site MEANS; the body the site will actually run is a
     *  different thing and until now was recorded nowhere at all. A lambda's
     *  code is lifted into a synthetic method of the enclosing class — a method
     *  whose own symbol and call sites are already facts, and which nothing
     *  could reach, because no fact named it from the site that creates it. So
     *  {@code list.forEach(x -> mapper.insert(x))} loses its {@code insert} to
     *  a traversal that follows targets: the body is extracted and orphaned.
     *
     *  <p>**Not every {@code invokedynamic} is a lambda**, and this records what
     *  the bootstrap actually names rather than assuming. A {@code
     *  StringConcatFactory} site's bootstrap arguments are a format recipe and
     *  a set of constants — there is no implementation method, so there is no
     *  symbol, and writing the recipe's owner here would claim a call to code
     *  that does not exist. {@link #lambdaHandle} is the gate: null for every
     *  bootstrap but {@code LambdaMetafactory}'s two. */
    private static String implementationOf(AbstractInsnNode insn) {
        if (!(insn instanceof InvokeDynamicInsnNode indy)) return null;
        Handle implementation = lambdaHandle(indy);
        return implementation == null ? null : lambdaSymbol(implementation);
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
     *  throws away the distinction the flag exists for.
     *
     *  <p>{@code frames} and {@code invokeIndex} exist only for capability
     *  9.15's array branch, which needs the whole method's frames to find the
     *  stores into an array and the consuming invoke's own position to bound
     *  them. **A null {@code frames} means "do not expand an array here"**, and
     *  the one caller that passes null is that branch itself, reading an
     *  array's elements: an element that is itself a constructed array reads
     *  {@code unresolved}. That is what makes the recursion terminate on
     *  {@code Object[] a = new Object[1]; a[0] = a;} — legal Java, whose
     *  element's producer is the very array being expanded — rather than
     *  needing a cycle check for a shape nothing useful is spelled in. */
    private static String argumentJson(SourceValue value, Type declaredType, InsnList instructions,
                                       int[] parameterSlots, Frame<SourceValue>[] frames,
                                       int invokeIndex) {
        AbstractInsnNode producer = singleSource(value);
        if (producer == null) return argument("unresolved", null, null, null);

        // The only VarInsnNode that can ever be a producer is the parameter
        // marker CopyTransparentSourceInterpreter.newParameterValue mints: a
        // real load moves a value without producing it. The slot it names is a
        // parameter's own starting slot, or `this` / the second half of a wide
        // parameter — neither of which is a parameter D00 §5 numbers, so those
        // stay the honest `unresolved`.
        if (producer instanceof VarInsnNode parameter) {
            int index = indexOfSlot(parameterSlots, parameter.var);
            return index < 0
                ? argument("unresolved", null, null, null)
                : argument("parameter", String.valueOf(index), null, null);
        }
        if (producer instanceof LdcInsnNode constant) {
            String entry = literalEntry(constant.cst, declaredType);
            // A float, a double, a method type, a method handle, a condy: no kind
            // in D00 §5's table, and inventing one is worse than saying so.
            return entry != null ? entry : argument("unresolved", null, null, null);
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
        // Any remaining GETFIELD/GETSTATIC producer — the enum-constant shape
        // above always wins first, so this is everything that shape rejected:
        // an instance field read, or a static field whose type is not its own
        // owner. D00 §5's `field` kind, the cross-language "this argument
        // reads a declared field" contract; the JVM mapping is a symbol
        // reference to the field itself, the same bare-descriptor grammar the
        // `enum` branch above already uses.
        if (producer instanceof FieldInsnNode field) {
            return argument("field", null, JsonOut.string(field.owner + "#" + field.name + "."), null);
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
        // Capability 9.15: the array a varargs call site builds at an argument
        // slot. `foo("a", "b")` against `foo(String...)` compiles to `ICONST_2;
        // ANEWARRAY String; DUP; ICONST_0; LDC "a"; AASTORE; DUP; ICONST_1;
        // LDC "b"; AASTORE; INVOKE…` — the value reaching the slot is the one
        // ANEWARRAY produced, never the LDCs, so without this branch every
        // element falls out of the fact stream entirely and eight different
        // ways of spelling a destination collapse to one byte-identical
        // `unresolved` (measured: scripts/probes/spring-integration-destinations.md).
        //
        // **An explicitly written `new String[]{"a", "b"}` is the same
        // bytecode** — javac erases the varargs sugar at the call site and the
        // callee's ACC_VARARGS flag lives on a class this pass has not read.
        // The two are therefore reported identically, and that is correct
        // rather than tolerated: they *are* the same call, and `elements`
        // states what the callee receives, which is one array either way.
        //
        // The shape is self-describing for exactly that reason. A consumer
        // reading `{"kind":"array","elements":[…]}` sees one argument that
        // happens to be an array, with its own contents beside it, and can
        // never mistake it for N arguments — an unpacked element list would
        // have renumbered every slot after it and made arity unreadable, the
        // same reason D00 §5 makes `unresolved` an answer rather than an
        // absence.
        //
        // Only a one-dimensional array is expanded: `Type#getElementType`
        // returns an array type's INNERMOST element type, so a
        // `String[]...` parameter's own elements are arrays and reporting
        // them against `java/lang/String` would mis-type every one. Higher
        // dimensions, and MULTIANEWARRAY with them, stay `unresolved`.
        if (frames != null && isArrayCreation(producer) && declaredType.getSort() == Type.ARRAY
                && declaredType.getDimensions() == 1) {
            String elements = arrayElementsJson(producer, declaredType.getElementType(),
                                                instructions, parameterSlots, frames, invokeIndex);
            // Null means the construction was not readable end to end — and
            // the slot then reads `unresolved` with no `source`, exactly as it
            // did before 9.15. The ANEWARRAY's own index would be an id that
            // joins to nothing (no fact is emitted for it, unlike the NEW an
            // `instance` argument points at, whose `<init>` call site names it
            // as a receiver), so writing one would be a dangling join.
            if (elements != null) return argument("array", null, null, null, elements);
        }
        if (producer instanceof InvokeDynamicInsnNode indy) {
            // A string built by joining pieces. javac does not assemble it in the
            // bytecode: it emits one `invokedynamic` plus a RECIPE holding the
            // literal parts, with a marker where each runtime value goes. The
            // literals are right there in the class file and were being thrown
            // away, so `"/api/" + version + "/orders"` reached a catalog as
            // `unresolved` — an outbound call naming nothing at all.
            //
            // What is recorded is the template: `/api/{}/orders`. The hole is
            // left unnamed on purpose. The class file carries a parameter's name
            // only when the build asked for it (`-parameters`), and the filler is
            // often not a parameter at all — `"/api/" + getVersion() + "/orders"`
            // has no name anywhere — so naming it would be invented half the
            // time. A template with a visible hole is the whole truth the class
            // file states.
            String template = concatTemplate(indy);
            if (template != null) {
                // JSON-encoded, like every other `value` in this grammar: the
                // helper writes what it is handed verbatim.
                return argument("concat", JsonOut.string(template), null,
                                String.valueOf(instructions.indexOf(producer)));
            }
            // A lambda's code is not here: the compiler lifted the body into a
            // method of its own and the call site only names it, in the bootstrap's
            // second argument. A method reference bootstraps identically and names
            // the referenced method itself.
            Handle implementation = lambdaHandle(indy);
            // Now that an indy is a call site of its own, the value it produced
            // has a `result` id — so the same join a plain call's result gets
            // applies, whether or not the kind resolved to `lambda`.
            if (implementation == null) {
                return argument("unresolved", null, null, String.valueOf(instructions.indexOf(producer)));
            }
            // How many of the body's LEADING parameters are captured values. The
            // metafactory lays the body's parameters out as captured values first, then
            // the interface's, so the interface's parameter k is the body's parameter
            // `captures + k` — a walk into the body needs this number, and it is written
            // here, on the indy, where it is known exactly. The indy's own descriptor
            // lists the captured values; when the handle is an instance kind the first of
            // them becomes the body's receiver rather than a parameter, so it is not
            // counted. An unbound instance reference (no captured value, instance handle)
            // reads -1: the interface's FIRST parameter is the receiver, and parameter k
            // is the body's parameter k-1.
            int captured = Type.getArgumentTypes(indy.desc).length;
            int captures = isInstanceHandle(implementation) ? captured - 1 : captured;
            return lambdaArgument(lambdaSymbol(implementation),
                                  String.valueOf(instructions.indexOf(producer)), captures);
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

    /** The two single-dimension array-creation opcodes: {@code ANEWARRAY} for a
     *  reference element type ({@code String...}, {@code Queue...}) and {@code
     *  NEWARRAY} for a primitive one ({@code int...}, {@code boolean...}).
     *  {@code MULTIANEWARRAY} is deliberately absent — it builds more than one
     *  dimension, which the caller already refuses. */
    private static boolean isArrayCreation(AbstractInsnNode producer) {
        return producer.getOpcode() == Opcodes.ANEWARRAY || producer.getOpcode() == Opcodes.NEWARRAY;
    }

    /** The eight {@code xASTORE} opcodes, contiguous in the JVM's own numbering
     *  from {@code IASTORE} to {@code SASTORE}. All eight take the same three
     *  operands — array reference, index, value — and ASM's {@code Frame} keeps
     *  one stack entry per value, {@code long} and {@code double} included, so
     *  the three read at fixed depths whatever the element type is. */
    private static boolean isArrayStore(int opcode) {
        return opcode >= Opcodes.IASTORE && opcode <= Opcodes.SASTORE;
    }

    /** The constant {@code int} this instruction pushes, or null when it pushes
     *  something computed. An array's length and each store's index must both
     *  be constants for the construction to be a readable element list: a
     *  length or an index the pass cannot name is a loop counter or a branch
     *  result, and there is no element list to report for either. */
    private static Integer constantInt(AbstractInsnNode producer) {
        if (producer == null) return null;
        if (producer instanceof LdcInsnNode constant && constant.cst instanceof Integer number) {
            return number;
        }
        if (producer instanceof IntInsnNode push
                && (push.getOpcode() == Opcodes.BIPUSH || push.getOpcode() == Opcodes.SIPUSH)) {
            return push.operand;
        }
        int opcode = producer.getOpcode();
        if (opcode >= Opcodes.ICONST_0 && opcode <= Opcodes.ICONST_5) {
            return opcode - Opcodes.ICONST_0;
        }
        return null;
    }

    /** Capability 9.15's whole rule, as the JSON array of element arguments —
     *  or **null**, meaning the construction is not a readable element list and
     *  the slot stays {@code unresolved}. GUIDELINES §8: ambiguous evidence
     *  produces nothing, and a partial element list is an invention, because a
     *  consumer cannot tell one from a complete one.
     *
     *  <p>Every one of these must hold, and each rejects a shape that looks
     *  like varargs construction and is not:
     *
     *  <ul>
     *  <li>The length is a constant — a length computed at runtime has no
     *  element count to report.</li>
     *  <li>Every store into this array anywhere in the method sits strictly
     *  between the creation and this invoke. A store after the invoke is a
     *  mutation of the array the callee was handed, and the elements this slot
     *  would claim are then not what the callee sees for the rest of its
     *  life.</li>
     *  <li>Every store's index is a constant, and no two stores name the same
     *  one. A loop's {@code arr[i] = …} has a non-constant index; a
     *  conditionally populated {@code if (…) arr[0] = a; else arr[0] = b;} has
     *  two stores at index 0 and no single answer for it — the same merge rule
     *  {@link #singleSource} applies one level down.</li>
     *  <li>Every index in {@code 0..length-1} is written. A partially populated
     *  array is a real shape ({@code new String[2]} with one store, the other
     *  element left null) and reporting the written half as the whole would
     *  assert an arity the call does not have.</li>
     *  <li>The array reference reaches no invoke other than this one — see
     *  {@link #consumedByInvoke}.</li>
     *  </ul>
     *
     *  <p>Not on the list, and deliberately: an array that arrives from
     *  somewhere else — a parameter, a field, another call's result — never
     *  gets here at all, because its producer is not an array creation. Those
     *  keep the ordinary {@code parameter}/{@code field}/{@code unresolved}
     *  answers they already had.
     *
     *  <p>A zero-length array — what {@code foo()} compiles to against {@code
     *  foo(String...)} — satisfies every clause vacuously and emits {@code
     *  {"kind":"array","elements":[]}}. The empty list is the fact: the callee
     *  is called with no varargs values, which is a different statement from
     *  "the array could not be read", and `unresolved` is what says the
     *  latter. */
    private static String arrayElementsJson(AbstractInsnNode creation, Type elementType,
                                            InsnList instructions, int[] parameterSlots,
                                            Frame<SourceValue>[] frames, int invokeIndex) {
        int creationIndex = instructions.indexOf(creation);
        Frame<SourceValue> creationFrame = frames[creationIndex];
        if (creationFrame == null || creationFrame.getStackSize() < 1) return null;
        Integer length =
            constantInt(singleSource(creationFrame.getStack(creationFrame.getStackSize() - 1)));
        if (length == null || length < 0) return null;
        String[] elements = new String[length];
        AbstractInsnNode[] insns = instructions.toArray();
        for (int j = 0; j < insns.length; j++) {
            Frame<SourceValue> frame = frames[j];
            if (frame == null || j == invokeIndex) continue;
            int top = frame.getStackSize();
            if (isArrayStore(insns[j].getOpcode())) {
                if (top < 3 || singleSource(frame.getStack(top - 3)) != creation) continue;
                if (j < creationIndex || j > invokeIndex) return null;
                Integer at = constantInt(singleSource(frame.getStack(top - 2)));
                if (at == null || at < 0 || at >= length || elements[at] != null) return null;
                elements[at] = argumentJson(frame.getStack(top - 1), elementType, instructions,
                                            parameterSlots, null, -1);
            } else if (consumedByInvoke(insns[j], frame, creation)) {
                return null;
            }
        }
        for (String element : elements) {
            if (element == null) return null;
        }
        return JsonOut.array(List.of(elements));
    }

    /** Whether this instruction is an invoke that consumes the array as a
     *  receiver or an argument. Any such call may mutate the array — {@code
     *  System.arraycopy}, {@code Arrays.fill}, or any method at all that keeps
     *  the reference — so an element list read at a later call site would be a
     *  claim about the array before that call rather than at it. A within-method
     *  pass cannot see what the callee does, so it declines rather than
     *  guesses; the invoke this slot belongs to is excluded by its caller.
     *
     *  <p>Only invokes are checked. Every other consumer of an array reference
     *  reads it or stores it ({@code ARRAYLENGTH}, {@code AALOAD}, {@code
     *  PUTFIELD}, {@code ARETURN}) and none of them changes an element. */
    private static boolean consumedByInvoke(AbstractInsnNode insn, Frame<SourceValue> frame,
                                            AbstractInsnNode creation) {
        Target target = targetOf(insn);
        if (target == null) return false;
        int consumed = Type.getArgumentTypes(target.descriptor()).length
            + (target.hasReceiver() ? 1 : 0);
        int top = frame.getStackSize();
        for (int k = 1; k <= consumed && k <= top; k++) {
            if (singleSource(frame.getStack(top - k)) == creation) return true;
        }
        return false;
    }

    /** The template a {@code StringConcatFactory} site composes, or null for any
     *  other bootstrap.
     *
     *  <p>The recipe is the first bootstrap argument: literal text with
     *  {@code \u0001} where a runtime value is spliced in and {@code \u0002}
     *  where one of the bootstrap's own constants is. The second marker is
     *  substituted — that constant IS known — while the first becomes {@code {}},
     *  a hole this analysis can see and cannot fill. */
    private static String concatTemplate(InvokeDynamicInsnNode indy) {
        if (indy.bsm == null
                || !"java/lang/invoke/StringConcatFactory".equals(indy.bsm.getOwner())
                || !"makeConcatWithConstants".equals(indy.bsm.getName())
                || indy.bsmArgs == null
                || indy.bsmArgs.length == 0
                || !(indy.bsmArgs[0] instanceof String recipe)) {
            return null;
        }
        StringBuilder out = new StringBuilder();
        int constant = 1;
        for (int i = 0; i < recipe.length(); i++) {
            char c = recipe.charAt(i);
            if (c == '\u0001') {
                out.append("{}");
            } else if (c == '\u0002') {
                out.append(constant < indy.bsmArgs.length
                    ? String.valueOf(indy.bsmArgs[constant++])
                    : "{}");
            } else {
                out.append(c);
            }
        }
        return out.toString();
    }

    /** The handle of the method a {@code LambdaMetafactory} call site will
     *  invoke, or null when this indy is bootstrapped by something else — a
     *  string concatenation, a record's generated {@code equals}, a framework's
     *  own bootstrap. Those are honest {@code unresolved}s: there is no
     *  implementation method to name.
     *
     *  <p>Both {@code metafactory} and {@code altMetafactory} put the
     *  implementation handle in the same slot, behind the SAM method type. The
     *  gate is the bootstrap's OWNER for that reason, never its name.
     *
     *  <p>Two readers, asking the same question at different sites: the {@code
     *  lambda} argument kind, where a lambda is HANDED to another call, and
     *  {@link #implementationOf} (capability 9.17), where the indy is the call
     *  site itself. The second exists because the first only fires where the
     *  lambda fills an argument slot — a lambda that is returned, stored in a
     *  field, or invoked through its own interface reaches no slot, and its
     *  body was then named nowhere. The first also reads the handle's KIND, to
     *  count captured values, which is why the handle and not its symbol is
     *  what this returns. */
    private static Handle lambdaHandle(InvokeDynamicInsnNode indy) {
        if (!"java/lang/invoke/LambdaMetafactory".equals(indy.bsm.getOwner())) return null;
        if (indy.bsmArgs.length < 2 || !(indy.bsmArgs[1] instanceof Handle implementation)) return null;
        return implementation;
    }

    /** The symbol of the method a {@link #lambdaHandle} names, spelled as the
     *  **bare descriptor path** — {@code java/lang/String#trim(sig_…).} —
     *  with no coordinates prefix, exactly like the {@code class}, {@code enum}
     *  and {@code instance} kinds beside it. A method reference is very often
     *  into a library, and D00 §1 requires that two modules seeing the same
     *  library type produce the same string: stamping the *caller's* module
     *  coordinates onto {@code java/lang/String} would mint a different symbol
     *  for {@code String::trim} in every module that used it, and none of them
     *  would join to the other. An in-module reference is joined to its own
     *  method fact by the descriptor suffix, which is what every consumer of
     *  these symbols already keys on. */
    private static String lambdaSymbol(Handle implementation) {
        return JsonOut.string(implementation.getOwner() + "#" + implementation.getName()
            + "(" + ClassScanner.disambiguatorOf(implementation.getDesc()) + ").");
    }

    private static boolean isInstanceHandle(Handle handle) {
        return handle.getTag() == Opcodes.H_INVOKEVIRTUAL
            || handle.getTag() == Opcodes.H_INVOKESPECIAL
            || handle.getTag() == Opcodes.H_INVOKEINTERFACE;
    }

    /** The `lambda` kind's own writer: three of the four keys every argument may
     *  carry (a lambda has no `value`), plus `captures`, which only a lambda has. */
    private static String lambdaArgument(String symbol, String source, int captures) {
        TreeMap<String, String> entry = new TreeMap<>();
        entry.put("kind", JsonOut.string("lambda"));
        entry.put("symbol", symbol);
        entry.put("source", source);
        entry.put("captures", String.valueOf(captures));
        return JsonOut.object(entry);
    }

    /** One {@code LDC} constant as an argument-grammar entry, or {@code null} for a
     *  constant D00 §5's table has no kind for.
     *
     *  <p>Two callers read the same mapping — a call site's argument and a FIELD WRITE from
     *  a constant ({@code fieldWrites}) — so it lives here once. Returning {@code null}
     *  rather than an {@code unresolved} entry is what lets them differ where they must: an
     *  argument slot must be filled whatever was found, because an absent slot renumbers its
     *  neighbours, while a field write with no readable value is better not emitted at all.
     *
     *  <p>{@code declaredType} is the type the CONSUMER declares, and it decides one case:
     *  the JVM has no boolean constant, so {@code LDC 1} is a {@code boolean} where the
     *  field or parameter is one and an {@code int} otherwise.
     */
    private static String literalEntry(Object literal, Type declaredType) {
        if (literal instanceof String text) return argument("string", JsonOut.string(text), null, null);
        if (literal instanceof Integer number) {
            return declaredType != null && declaredType.getSort() == Type.BOOLEAN
                ? argument("boolean", String.valueOf(number.intValue() != 0), null, null)
                : argument("int", String.valueOf(number), null, null);
        }
        if (literal instanceof Long number) return argument("long", String.valueOf(number), null, null);
        // An LDC of a Type is a class constant *only* for the two sorts a class constant can
        // have. ASM models a MethodType constant — legal in any class file since Java 7, and
        // what a method-handle-shaped call site loads — as a Type of sort METHOD, on which
        // `descriptorName`'s fallback calls `getClassName()` and ASM throws an AssertionError.
        // That is an Error, not an Exception, so it escapes Main's catch and takes the whole
        // extraction down: no fact files, no "extractor failed:" line, one class file's
        // constant pool silently costing every other class its facts.
        if (literal instanceof Type type
                && (type.getSort() == Type.OBJECT || type.getSort() == Type.ARRAY)) {
            return argument("class", null, JsonOut.string(TypeRefs.descriptorName(type)), null);
        }
        return null;
    }

    private static String argument(String kind, String value, String symbol, String source) {
        return argument(kind, value, symbol, source, null);
    }

    /** {@code elements} is capability 9.15's own key and belongs to the {@code
     *  array} kind alone. It is written **whenever the array was read**, empty
     *  list included — the one place in this grammar where an empty value says
     *  something an absent key would not, since a zero-length varargs call is a
     *  real call and not a failure to read one. */
    private static String argument(String kind, String value, String symbol, String source,
                                   String elements) {
        TreeMap<String, String> entry = new TreeMap<>();
        entry.put("kind", JsonOut.string(kind));
        // Written only when they say something. Unlike an argument slot, whose
        // absence would renumber its neighbours, an absent key here is
        // unambiguous: D00 §5's grammar makes all three optional.
        if (value != null) entry.put("value", value);
        if (symbol != null) entry.put("symbol", symbol);
        if (source != null) entry.put("source", source);
        if (elements != null) entry.put("elements", elements);
        return JsonOut.object(entry);
    }

    /** The value id of a value with exactly one producer, or null. Several
     *  producers means a branch merged two of them, and D00 §5's answer to that
     *  is silence rather than a guess. */
    private static Integer sourceId(SourceValue value, InsnList instructions) {
        AbstractInsnNode producer = singleSource(value);
        // A parameter marker is not in this method's instruction list, so it
        // has no index to report: a receiver that arrives as a parameter or as
        // `this` stays null, the answer it has given since copy transparency
        // landed. Reporting the marker would emit an id that joins to nothing.
        if (producer == null || producer instanceof VarInsnNode) return null;
        return instructions.indexOf(producer);
    }

    /** The parameter index a value arrives as, or null: the same test `argumentJson`
     *  makes for a `parameter`-kind argument — a `VarInsnNode` producer is the
     *  interpreter's parameter marker and nothing else — applied to the receiver slot.
     *  `this` and the second half of a wide parameter are no numbered parameter and
     *  stay null, exactly as they do for an argument. */
    private static Integer parameterIndex(SourceValue value, int[] parameterSlots) {
        AbstractInsnNode producer = singleSource(value);
        if (!(producer instanceof VarInsnNode parameter)) return null;
        int index = indexOfSlot(parameterSlots, parameter.var);
        return index < 0 ? null : index;
    }

    private static AbstractInsnNode singleSource(SourceValue value) {
        // Exactly one producer, or nothing. A parameter counts as one of them
        // — it carries the marker CopyTransparentSourceInterpreter gave its
        // initial value — so a slot merged from a parameter and a literal is
        // two producers and reads as none, exactly as two literals do. That
        // costs recall against the empty set a parameter used to contribute,
        // and it is the point: reporting the literal there asserted one
        // branch's value as the whole argument.
        if (value == null || value.insns.size() != 1) return null;
        return value.insns.iterator().next();
    }

    private static String callSiteJson(String documentId, String callerSymbol, Target invoke,
                                       int ordinal, Integer receiver, Integer receiverParameter,
                                       Integer result, String implementation, List<String> arguments) {
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
        // Capability 9.17, written only where a dispatch names a body its
        // target does not — which today is a `LambdaMetafactory` indy and
        // nothing else. Absent rather than null on every other site, for the
        // reason an argument's own optional keys are absent: a key on every
        // call site would rewrite every fact file to say "not applicable"
        // 2,500 times, and D00 §5 already makes an absent optional key
        // unambiguous.
        if (implementation != null) fact.put("implementation", implementation);
        fact.put("ordinal", String.valueOf(ordinal));
        fact.put("receiver", receiver == null ? "null" : String.valueOf(receiver));
        // Absent rather than null on every site whose receiver is not a parameter — the
        // rule `implementation` follows two lines up, for the same reason.
        if (receiverParameter != null) fact.put("receiver_parameter", String.valueOf(receiverParameter));
        fact.put("result", result == null ? "null" : String.valueOf(result));
        fact.put("arguments", JsonOut.array(arguments));
        return JsonOut.object(fact);
    }

    /** The type an {@code ATHROW} leaves with, or null where the stack value names
     *  none. The exception object is the top of stack; its producing instruction is a
     *  {@code NEW} for the overwhelmingly common `throw new Foo(...)`, an invoke for a
     *  helper-built one ({@link #typeOf} reads its declared return type as a bound), and
     *  anything else — a caught exception rethrown, a field read — does not name a type
     *  here without a resolution pass this one is not.
     *
     *  <p>Null rather than a guess. A throw whose type could not be read still emits its
     *  site, because the EXIT is the fact and the type is the detail: silence about the
     *  exit is the defect being fixed, and replacing it with silence about unreadable
     *  exits would fix half of it. */
    private static String thrownType(Frame<SourceValue> frame) {
        SourceValue thrown = frame.getStack(frame.getStackSize() - 1);
        // EVERY producer, then exactly one distinct answer or none — never the first one
        // iteration happens to reach. Two reasons, and either alone would be enough.
        //
        // Determinism (NFR-1). `SourceValue.insns` is ASM's `SmallSet` while it holds at
        // most two producers and a `java.util.HashSet` beyond that, and
        // `AbstractInsnNode` overrides neither `hashCode` nor `equals` — so past two
        // branches the iteration order is IDENTITY-HASH order, which varies between runs
        // of the same JVM on the same bytes. Measured: one class file, six runs under
        // different `-XX:hashCode=` strategies, four different answers. Fact files are
        // byte-compared across runs.
        //
        // And the rule this file already applies twice. `singleSource` refuses a value
        // merged from two producers, and `methodReturns` refuses to pick between two
        // `return` statements — "two possible answers and no single one; picking either
        // would be a fact about code that may never run". A `throw` merged from two
        // branches is the same shape and gets the same answer.
        String only = null;
        for (AbstractInsnNode source : thrown.insns) {
            String candidate = typeOf(source);
            if (candidate == null) return null;
            if (only == null) {
                only = candidate;
            } else if (!only.equals(candidate)) {
                return null;
            }
        }
        return only;
    }

    /** The type one producer of a thrown value names, or null where it names none.
     *
     *  <p>{@code NEW} is the exact runtime type. An invoke's DECLARED RETURN type is a
     *  BOUND — a subclass may be what actually flies — and it is recorded anyway because
     *  the class file states it, which is the difference between a bound and a guess.
     *  MEASURED on the fixture: the {@code NEW} walk alone read 14 of 39 sites and this
     *  takes it to 34, because a helper-built exception is how Kotlin's {@code Intrinsics}
     *  and most factory methods throw. The five that still read none are rethrows, whose
     *  type lives in the try-catch table this pass does not read. */
    private static String typeOf(AbstractInsnNode source) {
        if (source.getOpcode() == Opcodes.NEW) {
            return ((TypeInsnNode) source).desc;
        }
        if (source instanceof MethodInsnNode call) {
            Type returned = Type.getReturnType(call.desc);
            return returned.getSort() == Type.OBJECT ? returned.getInternalName() : null;
        }
        return null;
    }

    /** D00 §5's throw site: a call-site-shaped fact whose target is the thrown type.
     *
     *  <p>{@code name} and {@code descriptor} are ABSENT rather than empty. There is no
     *  method here, and an empty string would be a name that matches nothing while
     *  looking like one — the same reason {@code implementation} is absent on every site
     *  that is not a lambda. Consumers joining `target` to method symbols therefore find
     *  nothing, which is correct: a throw dispatches to no body.
     *
     *  <p>{@code receiver} and {@code result} are null for the same reason. A throw
     *  returns nothing to anybody. */
    private static String throwSiteJson(String documentId, String callerSymbol, int ordinal,
                                         String thrownOwner) {
        TreeMap<String, String> target = new TreeMap<>();
        target.put("owner", thrownOwner == null ? "null" : JsonOut.string(thrownOwner + "#"));

        TreeMap<String, String> fact = new TreeMap<>();
        fact.put("kind", JsonOut.string("call_site"));
        fact.put("document_id", JsonOut.string(documentId));
        fact.put("caller", JsonOut.string(callerSymbol));
        fact.put("target", JsonOut.object(target));
        fact.put("invoke_kind", JsonOut.string("throw"));
        fact.put("ordinal", String.valueOf(ordinal));
        fact.put("receiver", "null");
        fact.put("result", "null");
        fact.put("arguments", JsonOut.array(List.of()));
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
