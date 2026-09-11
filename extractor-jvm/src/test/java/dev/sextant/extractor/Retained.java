package dev.sextant.extractor;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

/** CLASS retention, so it lands in `RuntimeInvisibleParameterAnnotations` — the
 *  attribute every other fixture leaves empty. */
@Retention(RetentionPolicy.CLASS)
@Target(ElementType.PARAMETER)
public @interface Retained {
    String value();
}
