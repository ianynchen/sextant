package dev.sextant.extractor;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

/** A parameter annotation with a readable argument, for the JVMS 4.7.18
 *  alignment fixtures. Its own file rather than an auxiliary class beside one
 *  of them, because both {@link EnumConstructorAnnotated} and
 *  {@link ConstructorAnnotationShapes} use it and this build runs -Werror. */
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.PARAMETER)
public @interface Labelled {
    String value();
}
