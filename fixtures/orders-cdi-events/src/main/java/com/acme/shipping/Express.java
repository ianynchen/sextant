package com.acme.shipping;

import static java.lang.annotation.ElementType.FIELD;
import static java.lang.annotation.ElementType.PARAMETER;
import static java.lang.annotation.RetentionPolicy.RUNTIME;

import jakarta.inject.Qualifier;
import java.lang.annotation.Retention;
import java.lang.annotation.Target;

/** An application event qualifier: only events fired with it reach its observers. */
@Qualifier
@Retention(RUNTIME)
@Target({FIELD, PARAMETER})
public @interface Express {
}
