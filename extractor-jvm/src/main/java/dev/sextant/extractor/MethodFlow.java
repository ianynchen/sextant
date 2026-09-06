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
                arguments.add(argumentJson(frame.getStack(base + a), argumentTypes[a], instructions,
                                           parameterSlots, frames, i));
            }
            Integer receiver = target.hasReceiver()
                ? sourceId(frame.getStack(base - 1), instructions)
                : null;
            Integer result = Type.getReturnType(target.descriptor()).getSort() == Type.VOID ? null : i;
            lines.add(callSiteJson(documentId, callerSymbol, target, ordinal++, receiver, result,
                                   implementationOf(insns[i]), arguments));
        }
        return lines;
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
    public static List<String> fieldWrites(String documentId, MethodNode method) {
        if (!"<init>".equals(method.name)) return List.of();
        int[] parameterSlots = parameterSlotsOf(method.desc, 1);
        List<AbstractInsnNode> real = new ArrayList<>();
        for (AbstractInsnNode insn : method.instructions) {
            if (insn.getOpcode() >= 0) real.add(insn);
        }
        List<String> lines = new ArrayList<>();
        for (int i = 0; i + 2 < real.size(); i++) {
            if (!(real.get(i) instanceof VarInsnNode receiverLoad)
                    || receiverLoad.getOpcode() != Opcodes.ALOAD || receiverLoad.var != 0) {
                continue;
            }
            if (!(real.get(i + 1) instanceof VarInsnNode valueLoad) || !isLoad(valueLoad.getOpcode())) {
                continue;
            }
            if (!(real.get(i + 2) instanceof FieldInsnNode put) || put.getOpcode() != Opcodes.PUTFIELD) {
                continue;
            }
            int parameterIndex = indexOfSlot(parameterSlots, valueLoad.var);
            if (parameterIndex < 0) continue;
            lines.add(fieldWriteJson(documentId, put, parameterIndex));
        }
        return lines;
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

    private static String fieldWriteJson(String documentId, FieldInsnNode field, int fromParameter) {
        TreeMap<String, String> fact = new TreeMap<>();
        fact.put("kind", JsonOut.string("field_write"));
        fact.put("document_id", JsonOut.string(documentId));
        fact.put("field", JsonOut.string(field.owner + "#" + field.name + "."));
        fact.put("from_parameter", String.valueOf(fromParameter));
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
     *  that does not exist. {@link #lambdaSymbol} is the gate: null for every
     *  bootstrap but {@code LambdaMetafactory}'s two. */
    private static String implementationOf(AbstractInsnNode insn) {
        return insn instanceof InvokeDynamicInsnNode indy ? lambdaSymbol(indy) : null;
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

    /** The symbol of the method a {@code LambdaMetafactory} call site will
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
     *  body was then named nowhere.
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
                                       int ordinal, Integer receiver, Integer result,
                                       String implementation, List<String> arguments) {
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
