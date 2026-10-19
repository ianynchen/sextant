package com.acme.pp.controller.text;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** Served at `/text-api/text/{id}`, through a declaration that holds its prefix and its
 *  pattern as plain `String` PARAMETERS — so the lambda CAPTURES the pattern, and reaching it
 *  means crossing from the lambda's body into the site that captured it (`OI-150`). */
@RestController
@RequestMapping("/text")
public class TextController {

    @GetMapping("/{id}")
    public String get(String id) {
        return id;
    }
}
