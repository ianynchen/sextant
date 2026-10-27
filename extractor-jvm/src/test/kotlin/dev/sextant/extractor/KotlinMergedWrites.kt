package dev.sextant.extractor

// Committed fixture for `field_write`'s same-block rule on kotlinc's own output: an elvis
// `?:` and an `if` expression each join two branches AT the write, so the instruction right
// below it is only the last branch's value. Top-level vals are `putstatic` in this file
// class's `<clinit>`; the class's properties are `putfield` from a call in its `<init>`.

fun mergedMake(s: String): String = s

fun mergedLookup(): String? = System.getenv("SEXTANT_UNSET")

fun mergedFlag(): Boolean = System.getenv("SEXTANT_FLAG") != null

val elvisTop: String = System.getenv("SEXTANT_UNSET") ?: "https://default.example.com/"

val chosenTop: String =
    if (mergedFlag()) mergedMake("https://a.example.com/") else mergedMake("https://b.example.com/")

val singleTop: String = mergedMake("https://single.example.com/")

class KotlinMergedHolder(c: Boolean) {
    val elvis: String = mergedLookup() ?: mergedMake("https://default.example.com/")
    val chosen: String =
        if (c) mergedMake("https://a.example.com/") else mergedMake("https://b.example.com/")
    val single: String = mergedMake("https://single.example.com/")
}
