package com.acme.pp.controller.audit;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** **Served at `/audit-logs/{id}`, with NO prefix.** `PrefixConfig.auditCategories()` builds
 *  a map of exactly the prefix-declaration shape — a package predicate keyed by a string —
 *  and hands it to nobody. A reader that took any such map for a prefix map published this
 *  controller under `/AUDIT`, an address the app does not serve. */
@RestController
@RequestMapping("/audit-logs")
public class AuditController {

    @GetMapping("/{id}")
    public String get(String id) {
        return id;
    }
}
