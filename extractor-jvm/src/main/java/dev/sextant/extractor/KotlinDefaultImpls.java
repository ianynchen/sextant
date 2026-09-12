package dev.sextant.extractor;

import org.objectweb.asm.Opcodes;
import org.objectweb.asm.Type;

/** The nested {@code <Iface>$DefaultImpls} class kotlinc emits for an interface with a
 *  default method body, recognised from its shape (`kotlin-defaultimpls`).
 *
 *  <p>MEASURED, not taken from the language reference. For
 *  {@code interface Pricer { fun price(): Int = 0; fun discount(basis: Int, rate: Int = 10): Int }}
 *  kotlinc 2.2.0 (no {@code -jvm-default} flag, so its own {@code enable} mode) emits
 *  {@code Pricer$DefaultImpls}: flags {@code ACC_PUBLIC | ACC_FINAL | ACC_SUPER} — NOT
 *  {@code ACC_SYNTHETIC} — with {@code @kotlin.Metadata k=3} (a synthetic-class kind,
 *  which {@link KotlinNullability} decodes to {@link KotlinNullability#NONE}), no fields,
 *  no constructor, and three methods, every one {@code ACC_STATIC} with the interface
 *  at descriptor slot 0:
 *  <pre>
 *  public static int price(Pricer);                            (LPricer;)I
 *  public static int discount(Pricer, int, int);               (LPricer;II)I
 *  public static synthetic int discount$default(Pricer, int, int, int, Object);
 *  </pre>
 *  and an {@code InnerClasses} entry {@code DefaultImpls = Pricer$DefaultImpls of Pricer}
 *  naming the interface as the outer class. In that mode the interface ALSO carries
 *  {@code price()} as a JVM default method, and the {@code DefaultImpls} body is a
 *  {@code @Deprecated} stub calling back through {@code Pricer.access$price$jd}; under
 *  {@code -jvm-default=disable} (kotlinc 2.4.10, measured) the interface method is
 *  {@code abstract}, the body is in {@code DefaultImpls}, and the {@code DefaultImpls}
 *  class file has the SAME flags, methods and descriptors. Both modes give an
 *  implementing class that does not override its own forwarding {@code price()}. The
 *  shape is what both share, so the shape is the rule.
 *
 *  <p>Three conjuncts, each necessary. The NAME alone is a user's to take — a nested
 *  class called {@code DefaultImpls} is legal Java. The {@code InnerClasses} entry
 *  naming {@code <Iface>} as the outer class rules out a top-level class that merely
 *  spells its name with a {@code $}. And EVERY method being static with the interface at
 *  slot 0 rules out anything a person wrote: javac gives every class a constructor,
 *  which is neither, so a hand-written nested {@code DefaultImpls} fails here at its
 *  {@code <init>}. The one class that could pass vacuously — a nested INTERFACE named
 *  {@code DefaultImpls}, which has no constructor — is excluded by requiring at least
 *  one method.
 *
 *  <p>A method's fact is emitted as the method is visited and the type's fact last, so a
 *  body's {@code bridge_of} states the METHOD's own shape and the type's
 *  {@code implements_default_of} states every method's; a consumer reads the first beside
 *  the second. Neither compiler mode produces a holder where the two disagree. */
final class KotlinDefaultImpls {
    private KotlinDefaultImpls() {}

    static final String SUFFIX = "$DefaultImpls";

    /** The interface {@code internalName} holds the default bodies of, or null: the
     *  class is named {@code <outerName>$DefaultImpls} and the {@code InnerClasses}
     *  entry for it names {@code outerName} as its outer class. Shape of the members is
     *  the scanner's question, asked per method through {@link #isBody}. */
    static String holderOf(String internalName, String outerName) {
        return outerName != null && internalName.equals(outerName + SUFFIX) ? outerName : null;
    }

    /** Whether one method has the shape of a default body in {@code iface}'s holder:
     *  {@code static}, and its first descriptor slot is the interface itself. Holds for
     *  the body and for a {@code $default} bridge inside the holder alike. */
    static boolean isBody(int access, String descriptor, String iface) {
        if ((access & Opcodes.ACC_STATIC) == 0) return false;
        Type[] slots = Type.getArgumentTypes(descriptor);
        return slots.length > 0
            && slots[0].getSort() == Type.OBJECT
            && slots[0].getInternalName().equals(iface);
    }
}
