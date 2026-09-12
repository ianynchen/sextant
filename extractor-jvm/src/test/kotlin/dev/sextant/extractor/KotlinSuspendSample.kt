package dev.sextant.extractor

/** G-63's method half and Q2's `suspend fun` obligation, in one fixture.
 *
 * Every function here compiles to a descriptor that has LOST what the author
 * declared. `fetch` and `maybe` are byte-identical at the descriptor level —
 * `(Ljava/lang/String;Lkotlin/coroutines/Continuation;)Ljava/lang/Object;` —
 * so the return type AND its nullability are both gone, and `@kotlin.Metadata`
 * is the only place either is still written down. The `Signature` attribute
 * does carry `Continuation<? super KotlinSample>`, but it spells the nullable
 * and the non-nullable return identically, so it can close half of this at most.
 */
class KotlinSuspendSample {
    suspend fun fetch(id: String): KotlinSample = KotlinSample(id, null)

    suspend fun maybe(id: String): KotlinSample? = null

    /** The control: an ordinary function whose descriptor already states it. */
    fun plain(id: String): KotlinSample = KotlinSample(id, null)

    /** `OI-80`: a type argument cannot be a primitive, so the `Continuation` names
     *  `Integer` where the author wrote `Int`. Only `@kotlin.Metadata`'s classifier says
     *  which one was declared, and only its nullability says whether it boxes. */
    suspend fun suspCount(): Int = 1

    suspend fun suspFlag(): Boolean = true

    suspend fun suspTotal(): Long = 1L

    /** `Int?` genuinely boxes — this one must STAY `java/lang/Integer`. */
    suspend fun suspMaybeCount(): Int? = null

    /** The control: the descriptor itself says `I`. */
    fun plainCount(): Int = 1
}

/** Kotlin declarations that are NOT suspend but mention `Continuation`. Metadata says so;
 *  a structural test cannot. */
class KotlinContinuationImposters {
    fun resumeIt(c: kotlin.coroutines.Continuation<String>): Int = c.hashCode()

    fun arrayParam(cs: Array<kotlin.coroutines.Continuation<String>>): Int = cs.size
}
