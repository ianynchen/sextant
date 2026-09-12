package com.acme.versioned;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** Class-level media: `produces` declared ONCE on the prefix, inherited by every handler. */
@RestController
@RequestMapping(value = "/v7/reports", produces = "application/xml")
public class ReportController {

    @GetMapping("/daily")
    public String daily() {
        return "<report/>";
    }
}
