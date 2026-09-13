package dev.sextant.extractor

import java.util.function.Consumer

/** A Kotlin lambda that captures `this` compiles — unlike javac's — to a STATIC
 *  synthetic method whose first parameter is the captured receiver, so the captured
 *  value is a leading parameter and `captures` is 1. `forEach` is inline in the
 *  standard library and would compile to no lambda at all; `Consumer` is a Java
 *  interface, so the conversion goes through the same LambdaMetafactory indy javac
 *  uses. */
class KotlinCaptureSample(private val tag: String) {
    fun note(value: String): String = tag + value

    fun run(values: List<String>) {
        values.stream().forEach(Consumer { note(it) })
    }
}
