package dev.sextant.extractor

/** W2's alignment, measured against KOTLIN rather than assumed from javac.
 *
 * The rule "synthesised parameters are always LEADING" is javac's, not the
 * class-file format's, and Kotlin appends its synthetics at the END — a
 * `Continuation` on a `suspend fun`, a mask and marker on a `$default` bridge.
 * If kotlinc emitted a SHORT annotation table for these, aligning from the end
 * would move an annotation that indexing-from-zero had right.
 *
 * Measured: it does not. kotlinc writes one table entry per DESCRIPTOR
 * parameter — empty for the synthetic ones — so the table is full length, the
 * shift computes to 0, and the annotation stays where it was written.
 */
@Target(AnnotationTarget.VALUE_PARAMETER)
annotation class Tagged(val v: String)

class KotlinParameterAnnotated {
    /** Descriptor gains a trailing `Continuation`; the annotation is on arg 0. */
    suspend fun suspending(@Tagged("topic") topic: String) {
        topic.length
    }

    /** A defaulted parameter, which also generates a `$default` bridge. */
    fun defaulted(@Tagged("name") name: String, size: Int = 3) {
        name.length + size
    }
}

/** W5's alignment, measured against KOTLIN rather than assumed from javac.
 *
 * The javac rule W5 replaced ("what a signature drops, it drops from the front")
 * was replaced because it is not the format's rule. Kotlin is the other producer
 * this scanner reads, and it appends its synthetics at the END — a `Continuation`
 * on a `suspend fun`, a mask and marker on a `$default` bridge — so it is the
 * producer that would break a count-based alignment first. It is also the producer
 * that writes no `MethodParameters` attribute, which is what W5 aligns BY.
 *
 * Measured rather than assumed, and the reason nothing here needs aligning at all.
 */
class KotlinGenericSignature {
    /** A parameterized parameter and a type variable, in a function that declares
     *  its own formal type parameter. */
    fun <T : Comparable<T>> ranked(names: List<String>, item: T) {
        names.size + item.hashCode()
    }

    /** Descriptor gains a trailing `Continuation`. */
    suspend fun batched(names: List<String>) {
        names.size
    }

    /** A defaulted parameter, which generates a `$default` bridge carrying two
     *  extra trailing parameters. */
    fun defaulted(names: List<String>, size: Int = 3) {
        names.size + size
    }
}
