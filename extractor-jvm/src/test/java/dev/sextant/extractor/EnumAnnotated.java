package dev.sextant.extractor;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

/** Mirrors the shape that matters in the wild: an annotation whose argument is
 *  an array of enum constants, as Spring's {@code @RequestMapping(method = ...)}
 *  is. ASM reports those through {@code visitEnum}, not {@code visit}. */
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Mapped {
    Verb[] verb() default {};

    Verb single() default Verb.GET;
}

enum Verb {
    GET,
    POST
}

@Mapped(verb = {Verb.GET, Verb.POST}, single = Verb.POST)
public class EnumAnnotated {}
