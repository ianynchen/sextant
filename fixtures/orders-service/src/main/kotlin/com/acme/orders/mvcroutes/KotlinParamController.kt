// Spec 2026-09-19 §5b, R1: the two ways a Kotlin parameter is optional to Spring's binder
// without any attribute saying so — `MethodParameter.isOptional()` reaches
// `KotlinDelegate.isOptional`, which is `KType.isMarkedNullable()` or
// `KParameter.isOptional()` (CP-25 row 3). `page: Int = 0` compiles to an `int` slot
// whose `@kotlin.Metadata` flag the extractor publishes as `declares_default: true`
// (D00 §5a); `tag: String?` compiles with kotlinc's `@org.jetbrains.annotations.Nullable`
// on the parameter, one of the shape model's `nullability.nullable` spellings. Neither
// is `required`, and before R1 the first would have been written so.
//
// A controller of its own beside `KotlinMvcRoutes.kt` (a router DSL, where a parameter
// annotation has nowhere to go) under `/ktparams`, so no `/ktmvc` row moves.
package com.acme.orders.mvcroutes

import org.springframework.web.bind.annotation.GetMapping
import org.springframework.web.bind.annotation.RequestMapping
import org.springframework.web.bind.annotation.RequestParam
import org.springframework.web.bind.annotation.RestController

@RestController
@RequestMapping("/ktparams")
class KotlinParamController {

    @GetMapping("/search")
    fun search(@RequestParam page: Int = 0, @RequestParam tag: String?): String = "$page:$tag"
}
