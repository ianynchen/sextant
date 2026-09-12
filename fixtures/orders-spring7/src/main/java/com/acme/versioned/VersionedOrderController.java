package com.acme.versioned;

import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** Spring 7's API versioning: two handlers on ONE path, told apart by `version`, which
 *  `RequestMappingInfo` compares exactly as it compares `params` and `headers`. Spring
 *  serves both; a reader that ignores `version` sees a routing conflict that does not
 *  exist — a false question on a legitimately versioned API. */
@RestController
@RequestMapping("/orders")
public class VersionedOrderController {

    @GetMapping(version = "1.0")
    public List<String> listV1() { return List.of(); }

    @GetMapping(version = "2.0")
    public List<String> listV2() { return List.of(); }
}
