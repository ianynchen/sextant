package dev.sextant.extractor

/** `kotlin-defaultimpls`' fixture: an interface with a default method body, and the
 *  nested `DefaultImpls` class kotlinc emits to hold it.
 *
 * Compiled with no `-jvm-default` flag (see `build.gradle.kts`). Measured on kotlinc
 * 2.2.0, whose default mode is `enable`: `Pricer` itself carries `price()` as a JVM
 * default method AND the compiler still emits `Pricer$DefaultImpls`, a `public final`
 * class — NOT `synthetic` — whose every method is `public static` with the interface
 * at descriptor slot 0 (`price(Ldev/sextant/extractor/KotlinDefaultImplsSample$Pricer;)I`),
 * so that a class compiled under the older mode can still find the body there.
 */
class KotlinDefaultImplsSample {
    interface Pricer {
        /** The body: it is what `Pricer$DefaultImpls.price(Pricer)` stands for. */
        fun price(): Int = 0

        /** A body with a parameter and a default, so the `DefaultImpls` holds a
         *  `$default` bridge too — `OI-81`'s recogniser sees it under the interface
         *  slot. */
        fun discount(basis: Int, rate: Int = 10): Int = basis - rate

        /** The control: no body, so nothing of it lands in `DefaultImpls`. */
        fun label(): String
    }

    /** An implementation that does not override `price`: a call to `price()` on it
     *  has to reach the body in `DefaultImpls`. */
    class FlatPricer : Pricer {
        override fun label(): String = "flat"
    }
}
