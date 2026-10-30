package com.acme.inherited;

import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;

/**
 * The shared base. Abstract and carrying no stereotype or prefix, so it serves nothing of
 * its own: each mapping here is served once per concrete controller that inherits it.
 */
public abstract class CrudController<T> {

    @GetMapping("/list")
    public List<T> list() {
        return List.of();
    }

    @PostMapping
    public T create(@RequestBody T body) {
        return body;
    }
}
