package dev.sextant.extractor

/** T2 sample. Lives in its own source set (`testLambdaClass`) because it is compiled with
 *  `-Xlambdas=class` and `KotlinCaptureSample` in the ordinary test set needs the default
 *  `invokedynamic` shape: `plain` becomes a `Lambda` subclass with a typed
 *  `invoke(String)` and a synthetic `invoke(Object)` bridge; `suspended` becomes a
 *  `SuspendLambda` subclass whose body is `invokeSuspend(Object)`. `reference` and
 *  `sreference` are function REFERENCES, which compile to a `FunctionReferenceImpl`
 *  subclass with a typed `invoke` whose body calls the referenced function — a suspend
 *  one takes a `Continuation` and implements `SuspendFunction`, but has no
 *  `invokeSuspend`. */
class KotlinLambdaSample {
    fun plain(): (String) -> Int = { it.length }
    fun suspended(): suspend (String) -> Int = { it.length }
    fun referenced(s: String): Int = s.length
    fun reference(): (String) -> Int = ::referenced
    suspend fun sref(s: String): Int = s.length
    fun sreference(): suspend (String) -> Int = ::sref
}
