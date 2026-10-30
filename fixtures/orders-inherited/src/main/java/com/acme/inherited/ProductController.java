package com.acme.inherited;

import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * Overrides `list` with its own mapping, so it serves `GET /products/all` and never
 * `GET /products/list`; `create` is inherited and served at `POST /products`.
 */
@RestController
@RequestMapping("/products")
public class ProductController extends CrudController<Product> {

    @Override
    @GetMapping("/all")
    public List<Product> list() {
        return List.of(new Product("p-1", "Widget"));
    }
}
