package dev.sextant.extractor

/** T1 sample: one defaulted, one plain, one nullable-without-default parameter. */
class KotlinDefaultParams {
    fun list(page: Int = 0, size: Int, tag: String?): String = "$page$size$tag"
}
