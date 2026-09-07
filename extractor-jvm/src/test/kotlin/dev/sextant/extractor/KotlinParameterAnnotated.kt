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
