package dev.sextant.extractor

/** T2 sample. Lives in its own source set (`testLambdaClass`) because it is compiled with
 *  `-Xlambdas=class` and `KotlinCaptureSample` in the ordinary test set needs the default
 *  `invokedynamic` shape: `plain` becomes a `Lambda` subclass with a typed
 *  `invoke(String)` and a synthetic `invoke(Object)` bridge; `suspended` becomes a
 *  `SuspendLambda` subclass whose body is `invokeSuspend(Object)`. */
class KotlinLambdaSample {
    fun plain(): (String) -> Int = { it.length }
    fun suspended(): suspend (String) -> Int = { it.length }
}
