package com.probe;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerResponse;

@SpringBootApplication
public class App {
    public static void main(String[] args) { SpringApplication.run(App.class, args); }

    @RestController
    public static class Flux {
        @GetMapping("/flux") public String flux() { return "flux"; }
    }

    @Bean
    RouterFunction<ServerResponse> routes() {
        return RouterFunctions.route().GET("/fnflux", r -> ServerResponse.ok().bodyValue("fnflux")).build();
    }
}
