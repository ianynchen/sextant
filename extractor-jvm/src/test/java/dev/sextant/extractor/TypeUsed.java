package dev.sextant.extractor;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

/** A TYPE_USE-only annotation, for the JVMS 4.7.20.1 alignment fixtures.
 *
 *  <p>Its own target deliberately: {@link Labelled} is {@code ElementType.PARAMETER}, so
 *  every skew fixture in this package drove {@code visitParameterAnnotation} and NOTHING
 *  drove {@code METHOD_FORMAL_PARAMETER}. Replacing that whole branch with "the index is
 *  the slot" passed the entire suite. The two attributes are indexed the same way and
 *  skew the same way; only this annotation reaches the second one. */
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
public @interface TypeUsed {}
