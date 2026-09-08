package dev.sextant.extractor

/**
 * W6's SMAP fixture. ITS LINE NUMBERS ARE THE FIXTURE — `SourceLocationTest` pins
 * them, so editing above or inside these functions moves them.
 *
 * `let` and `forEach` are `inline` in the Kotlin standard library, so kotlinc
 * splices their bodies in here and remaps the spliced lines into a synthetic
 * range past the end of this file, recording the truth in `SourceDebugExtension`.
 * Read naively, these functions report line numbers belonging to
 * `_Collections.kt` — a different file, in a different artifact.
 *
 * Keep additions at the BOTTOM.
 */
class KotlinInlined {

    /** Body on line 18, and `let` splices a line past the end of this file. */
    fun useLet(a: String): Int {
        return a.let { it.length }
    }

    /** Body on lines 23 to 25, and `forEach` splices two more. */
    fun useForEach(items: List<String>): Int {
        var total = 0
        items.forEach { total += it.length }
        return total
    }
}
