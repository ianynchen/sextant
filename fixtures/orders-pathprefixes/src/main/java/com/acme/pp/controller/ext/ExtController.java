package com.acme.pp.controller.ext;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** **Served at `/ext/{id}`, with NO prefix.** Its prefix IS declared — `PrefixConfig` installs
 *  one for this package — but as `${api.ext-prefix}`, which Spring resolves through its
 *  embedded value resolver before using. Publishing the placeholder verbatim put a path that
 *  is not even path-shaped into the document, so an unresolved prefix is refused instead. */
@RestController
@RequestMapping("/ext")
public class ExtController {

    @GetMapping("/{id}")
    public String get(String id) {
        return id;
    }
}
