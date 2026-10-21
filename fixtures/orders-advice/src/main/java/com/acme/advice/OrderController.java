package com.acme.advice;

import com.example.billing.ConflictingOrderException;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrderController {

    @GetMapping("/orders")
    public String orders() {
        throw new ConflictingOrderException("placed twice");
    }
}
