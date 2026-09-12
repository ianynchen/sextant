package dev.sextant.extractor

/** `OI-81`'s fixture: a function with default arguments, and the `$default` bridge
 *  kotlinc emits beside it.
 *
 * The bridge is `static synthetic`, carries no `Signature` attribute and no entry in
 * `@kotlin.Metadata`'s function list, so every one of its parameters and its return took
 * Java's rule while `greet` itself read its declared types — one declaration, two
 * answers. `greet$default` stands for `greet`, and its fact should say so.
 */
class KotlinDefaultsSample {
    fun greet(name: String = "x", loud: Boolean = false): String = if (loud) name.uppercase() else name

    /** The nullable side, so the bridge is shown to borrow `true` as well as `false`. */
    fun maybe(note: String? = null, tags: List<String?> = emptyList()): String? = note

    /** A `suspend fun` with a default: the bridge's descriptor carries the `Continuation`
     *  BEFORE the mask and marker, and the sibling is keyed with it. */
    suspend fun fetch(id: String = "0"): String = id
}

/** The collision a receiver guess would get wrong. `js$default` has NO receiver slot —
 *  `(Ljava/lang/String;IILjava/lang/Object;)Ljava/lang/String;` — so reading its first
 *  slot as a receiver derives `js(I)Ljava/lang/String;`, which the arity overload beside
 *  it keys. Both candidates key; neither may be taken. The overload's return is declared
 *  non-null so that borrowing it reads `false` where Java's rule reads `true`. */
object KotlinDefaultsObject {
    @JvmStatic fun js(a: String, b: Int = 0): String = a + b
    fun js(b: Int): String = b.toString()
}
