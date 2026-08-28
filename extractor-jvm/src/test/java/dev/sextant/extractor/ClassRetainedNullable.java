package dev.sextant.extractor;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

/** A {@code CLASS}-retention {@code TYPE_USE} annotation, so the extractor's own
 *  test sources exercise the invisible-type-annotation table without adding a
 *  dependency. JSpecify — the only type-use annotation used elsewhere in this
 *  fixture set — is {@code RUNTIME}, so without this nothing here ever proved
 *  the invisible table is read at all. */
@Retention(RetentionPolicy.CLASS)
@Target(ElementType.TYPE_USE)
@interface ClassRetainedNullable {}
