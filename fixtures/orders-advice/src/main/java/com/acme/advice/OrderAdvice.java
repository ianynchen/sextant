package com.acme.advice;

import com.example.billing.ConflictingOrderException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

/**
 * Two bare handlers — `@ExceptionHandler` naming NO class — so the exception type comes from the
 * PARAMETER, which is the framework's rule and the first ◐ row: the parameter is an exception iff
 * it is assignable to `Throwable`. Both parameters are classes this module never compiled:
 *
 *   ConflictingOrderException   stub jar, NOT opted in  →  chain `RuntimeException`, and the class
 *                                                          carries `@ResponseStatus(CONFLICT)` (row 2)
 *   MethodArgumentNotValidException   spring-web        →  chain `BindException → Exception`
 *
 * Before the header read, neither parameter could be proven a throwable and both handlers derived
 * nothing from it; the first's status was NULL because its annotation sat in an unscanned jar.
 */
@RestControllerAdvice
public class OrderAdvice {

    @ExceptionHandler
    public String conflict(ConflictingOrderException e) {
        return "conflict";
    }

    @ExceptionHandler
    public String invalid(MethodArgumentNotValidException e) {
        return "invalid";
    }
}
