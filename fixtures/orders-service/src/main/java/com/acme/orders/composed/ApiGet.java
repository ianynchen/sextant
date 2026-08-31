// A module-local HTTP composition: meta-annotated with `@RequestMapping`, so
// the composed-annotation pre-pass (Tasks 5-9) can widen `annotation_driven`'s
// catalog set to cover it. `@GetMapping` itself cannot fill this meta-
// annotation role -- its own `@Target` is `METHOD` only, and javac rejects
// any meta-annotation whose `@Target` excludes annotation-type declarations
// (verified against the real spring-web 6.1.6 jar at the checkpoint).
// `@RequestMapping`'s `@Target` includes `TYPE` (which covers annotation
// types), so this composes the same way `@GetMapping` itself is defined --
// `@RequestMapping(method = GET)`. RUNTIME retention is required -- Spring
// reads mapping annotations reflectively, and the checkpoint verifies javac
// actually emits it (spec §6.2).
package com.acme.orders.composed;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestMethod;

@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
@RequestMapping(method = RequestMethod.GET, path = "/composed")
public @interface ApiGet {
}
