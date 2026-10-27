package com.acme.dc;

import org.springframework.web.client.RestTemplate;

/**
 * A host held in a static field whose value is a TERNARY: two constants, one per branch, and
 * the two branches join at the write.
 *
 * <p>javac compiles the initialiser to {@code getstatic; ifeq; ldc prod; goto; ldc staging;
 * putstatic}, so the instruction right below the write is the staging constant alone. Measured
 * before the extractor's same-block rule: {@code GET staging.example.com /inventory resolved},
 * for a field that holds the production host whenever the flag is set. Neither constant is the
 * field's one value, so the row states no address.
 */
public class MergedHostClient {

    static final boolean PROD = Boolean.getBoolean("prod");
    static String BASE =
        PROD ? "https://prod.example.com/inventory" : "https://staging.example.com/inventory";

    private final RestTemplate restTemplate = new RestTemplate();

    public String inventory() {
        return restTemplate.getForObject(BASE, String.class);
    }
}
