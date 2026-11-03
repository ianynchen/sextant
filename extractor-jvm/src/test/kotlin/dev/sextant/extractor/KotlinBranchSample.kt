package dev.sextant.extractor

/** Kotlin's `?.` compiles to a null test and a jump around the call, so the call sits on
 *  one branch: it is not on every path to the return, and the call after it is dominated
 *  by no call (spec 2026-11-02-per-path-truth rule 9). */
class KotlinBranchSample {
    fun go() {}

    fun after() {}

    fun safeCall(other: KotlinBranchSample?) {
        other?.go()
        after()
    }
}
