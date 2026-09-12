package dev.sextant.extractor;

import org.objectweb.asm.Opcodes;
import org.objectweb.asm.Type;

/** The {@code $default} bridge kotlinc emits beside every function with default
 *  arguments, recognised from its shape and joined to the function it stands for
 *  (`OI-81`).
 *
 *  <p>MEASURED on kotlinc 2.2.0, not taken from the language reference. For
 *  {@code fun greet(name: String = "x", loud: Boolean = false): String} the class holds a
 *  second method, {@code greet$default}, flags {@code ACC_PUBLIC | ACC_STATIC |
 *  ACC_SYNTHETIC}, descriptor
 *  <pre>
 *  (Ldev/sextant/extractor/KotlinDefaultsSample;Ljava/lang/String;ZILjava/lang/Object;)Ljava/lang/String;
 *  </pre>
 *  — the RECEIVER, then the function's own slots in order, then one {@code int} mask per
 *  32 parameters (a 33-parameter function carries two, measured), then a trailing
 *  {@code Object} marker. A {@code @JvmStatic} function's bridge has NO receiver slot
 *  ({@code js$default(Ljava/lang/String;ILjava/lang/Object;)}), a {@code suspend fun}'s
 *  carries its {@code Continuation} BEFORE the mask, and a constructor's defaults go
 *  through a synthetic {@code <init>(…, int, DefaultConstructorMarker)} with no
 *  {@code $default} name at all, which this class does not describe.
 *
 *  <p>The bridge has no {@code Signature} attribute and no entry in {@code @kotlin.Metadata}'s
 *  function list, so every slot and the return fell to Java's rule while the sibling read
 *  its declared types: {@code copy} answered {@code nullable: false} and {@code copy$default}
 *  {@code true} for one declared type. The sibling is found by taking the bridge's
 *  descriptor, dropping the receiver and the trailing masks and marker, and looking the
 *  result up by {@code name + descriptor} in what metadata keyed — which is also how the
 *  receiver question is settled: the candidate WITH the receiver dropped is tried first,
 *  the one without second, and whichever metadata keys is the sibling.
 *
 *  <p>The mask count is solved, not counted: the masks are {@code int}s and so may be the
 *  function's own last parameters, so "trailing {@code I}s" over-counts on
 *  {@code fun f(x: Int = 0)}. With {@code n} function slots there are exactly
 *  {@code ceil(n / 32)} masks, and {@code n + ceil(n / 32)} is strictly increasing in
 *  {@code n}, so the slot count determines {@code n} outright and the solved mask slots are
 *  then checked to be {@code I}.
 *
 *  @param function the name of the function the bridge stands for — the bridge's own
 *         name without its {@code $default} suffix
 *  @param receiverSlots 1 where the bridge's first slot is the sibling's receiver, 0 for a
 *         static sibling
 *  @param declaredSlots how many of the bridge's slots, from {@code receiverSlots} on, are
 *         the sibling's own — a {@code suspend} sibling's {@code Continuation} included,
 *         because the descriptor carries it and metadata's key does too
 *  @param siblingKey the sibling's {@code name + descriptor}, in the form
 *         {@link KotlinNullability.Decoded} keys, whether or not metadata keyed it */
record KotlinDefaultBridge(String function, int receiverSlots, int declaredSlots, String siblingKey) {

    private static final String SUFFIX = "$default";

    /** The bridge {@code name}/{@code descriptor}/{@code access} describe, or null where
     *  they describe an ordinary method. {@code metadata} settles the receiver question;
     *  a class whose metadata is unreadable ({@link KotlinNullability#NONE}) still gets
     *  its bridge recognised — the NAME is certain from the shape alone — with the
     *  receiver assumed present wherever the first slot is a reference. */
    static KotlinDefaultBridge recognise(
            int access, String name, String descriptor, KotlinNullability.Decoded metadata) {
        if ((access & Opcodes.ACC_STATIC) == 0 || (access & Opcodes.ACC_SYNTHETIC) == 0) return null;
        if (!name.endsWith(SUFFIX) || name.length() == SUFFIX.length()) return null;
        Type[] slots = Type.getArgumentTypes(descriptor);
        int last = slots.length - 1;
        if (last < 1 || slots[last].getSort() != Type.OBJECT
                || !"java/lang/Object".equals(slots[last].getInternalName())) {
            return null;
        }
        String function = name.substring(0, name.length() - SUFFIX.length());
        String returns = Type.getReturnType(descriptor).getDescriptor();
        KotlinDefaultBridge withReceiver = slots[0].getSort() == Type.OBJECT
            ? solve(function, 1, slots, returns)
            : null;
        KotlinDefaultBridge withoutReceiver = solve(function, 0, slots, returns);
        if (withReceiver != null && metadata.parameterTypes().containsKey(withReceiver.siblingKey())) {
            return withReceiver;
        }
        if (withoutReceiver != null && metadata.parameterTypes().containsKey(withoutReceiver.siblingKey())) {
            return withoutReceiver;
        }
        return withReceiver != null ? withReceiver : withoutReceiver;
    }

    /** The bridge with {@code receiverSlots} leading slots taken as the receiver, or null
     *  where no parameter count produces this many slots with every mask an {@code int}. */
    private static KotlinDefaultBridge solve(
            String function, int receiverSlots, Type[] slots, String returns) {
        int available = slots.length - receiverSlots - 1;
        for (int n = 1; n + masks(n) <= available; n++) {
            if (n + masks(n) != available) continue;
            for (int mask = receiverSlots + n; mask < slots.length - 1; mask++) {
                if (slots[mask].getSort() != Type.INT) return null;
            }
            StringBuilder sibling = new StringBuilder("(");
            for (int slot = receiverSlots; slot < receiverSlots + n; slot++) {
                sibling.append(slots[slot].getDescriptor());
            }
            sibling.append(')').append(returns);
            return new KotlinDefaultBridge(function, receiverSlots, n, function + sibling);
        }
        return null;
    }

    /** One {@code int} mask per 32 parameters: a bit per parameter saying whether the
     *  caller supplied it. */
    private static int masks(int parameters) {
        return (parameters + 31) / 32;
    }
}
