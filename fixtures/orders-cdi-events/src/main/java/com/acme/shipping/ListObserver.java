package com.acme.shipping;

import jakarta.enterprise.context.ApplicationScoped;
import jakarta.enterprise.event.Observes;
import java.util.List;

@ApplicationScoped
public class ListObserver {

    /** CDI matches the parameterized type `List<String>`, not its erasure. */
    void on(@Observes List<String> event) {
    }
}
