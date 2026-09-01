package com.acme.orders;

import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * The other half of the same seam: a `"/"` class prefix, where BOTH halves
 * spell the separator. Spring still joins them with exactly one — this is
 * served at `/chat`, since a `"/"` prefix contributes nothing but the leading
 * slash.
 *
 * <p>Ordinary Spring, and it derived `//chat` — a second address nobody serves.
 * Found live against spring-petclinic-microservices, whose genai-service writes
 * exactly this (`@RequestMapping("/")` + `@PostMapping("/chatclient")`).
 */
@RestController
@RequestMapping("/")
public class RootSeamController {

    private final OrderService service = new OrderService();

    @PostMapping("/chat")
    public OrderResult chat(@RequestBody OrderCommand command) {
        return service.place(command);
    }
}
