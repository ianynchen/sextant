package dev.sextant.extractor;

/** A plain, non-generic class hierarchy — capability 9.13's own fixture.
 *  Nothing here is generic, so the class file carries no {@code Signature}
 *  attribute at all: the class file's own {@code super_class} constant-pool
 *  entry — read directly by ASM's {@code visit}, never through a signature —
 *  is the only place {@code PlainSubclassSample} names {@code
 *  PlainSuperclass} as what it extends. */
public class PlainSubclassSample extends PlainSuperclass {
}

/** The plain superclass {@link PlainSubclassSample} extends. */
class PlainSuperclass {
}
