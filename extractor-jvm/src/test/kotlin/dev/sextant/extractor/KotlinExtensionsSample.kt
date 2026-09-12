package dev.sextant.extractor

/** `kotlin-extension-functions`' fixture: an extension function's receiver is a
 *  parameter to the JVM and a receiver to the author.
 *
 * A top-level extension lives in this file's facade, `KotlinExtensionsSampleKt`, as a
 * static method whose FIRST descriptor slot is the receiver — measured on kotlinc 2.2.0:
 * `shout` is `public static final String shout(String)`, and `@kotlin.Metadata` lists it
 * with NO value parameters and a receiver parameter type, so nothing but that receiver
 * type says slot 0 was never written as a parameter.
 */
fun String.shout(): String = uppercase()

/** The receiver beside a real parameter: slot 0 is the receiver, slot 1 is `suffix` —
 *  declared non-null, which Java's rule would misread if the declared types were laid
 *  from slot 0. */
fun String.repeatShout(suffix: String): String = uppercase() + suffix

/** An extension with a default: its `$default` bridge is
 *  `decorate$default(Ljava/lang/String;Ljava/lang/String;ILjava/lang/Object;)` — no
 *  owner, the receiver first, then `prefix`, the mask and the marker. */
fun String.decorate(prefix: String = "*"): String = prefix + this

/** A suspending extension: the receiver stays FIRST and the `Continuation` stays LAST. */
suspend fun String.fetchShout(): String = uppercase()

/** The control: a top-level function with no receiver, in the same facade. */
fun plain(name: String): String = name

class KotlinExtensionsHolder {
    /** A member extension: an instance method whose first descriptor slot is the receiver. */
    fun List<Int>.total(): Int = sum()

    /** The control: a member with no receiver, beside the extension. */
    fun count(items: List<Int>): Int = items.size
}
