package dev.sextant.extractor

/** `OI-82`'s fixture: the PARAMETER half of Kotlin nullability, functions and constructors.
 *
 * Every reference parameter here erases to the same descriptor whether or not it was
 * written with a `?`, and `List<String?>` and `List<String>?` erase to the same
 * `Signature` too. Only `@kotlin.Metadata` states what the author declared, at every
 * level of the type.
 */
class KotlinParameterSample(val id: String, val note: String?) {
    fun place(sku: String, qty: Int?, tags: List<String?>, meta: Map<String, List<Int>?>?) = sku
    fun copy(id: String = this.id, note: String? = this.note) = KotlinParameterSample(id, note)

    /** A bare type variable's implicit bound is `Any?`, so metadata's "not nullable" on
     *  `x: T` and on the return `T` is a statement about the VARIABLE, not about what a
     *  caller may bind it to. `y: T?` is definitely nullable whatever `T` is. */
    fun <T> ranked(x: T, y: T?): T = x

    fun <T> rankedMaybe(x: T): T? = x
}
