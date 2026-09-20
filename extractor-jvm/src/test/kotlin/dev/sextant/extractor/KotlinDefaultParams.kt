package dev.sextant.extractor

/** T1 sample: one defaulted, one plain, one nullable-without-default parameter. */
class KotlinDefaultParams {
    fun list(page: Int = 0, size: Int, tag: String?): String = "$page$size$tag"

    /** The smallest MISALIGNED declaration: an `inner` class's constructor takes the
     *  enclosing instance as its FIRST descriptor slot (`(LKotlinDefaultParams;I)V`),
     *  and metadata lists only `size` — one value parameter against two slots. */
    inner class Page(val size: Int = 20)
}
