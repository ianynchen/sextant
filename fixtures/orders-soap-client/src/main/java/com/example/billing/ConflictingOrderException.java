package com.example.billing;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ResponseStatus;

/**
 * A library exception whose HTTP status is declared ON THE CLASS. Spring's own exceptions do not
 * do this (measured off `spring-web` 6.1.6: none of the four most-handled carry `@ResponseStatus`),
 * so a class in a dependency jar is the only way the shape exists in a corpus — and this stub is
 * a dependency of `orders-advice`, which does not opt it into `extract_libraries`.
 */
@ResponseStatus(HttpStatus.CONFLICT)
public class ConflictingOrderException extends RuntimeException {

    public ConflictingOrderException(String message) {
        super(message);
    }
}
