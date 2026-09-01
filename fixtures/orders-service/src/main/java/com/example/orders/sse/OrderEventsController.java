package com.example.orders.sse;
import com.acme.orders.contracts.OrderView;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;
import reactor.core.publisher.Flux;

@RestController
public class OrderEventsController {

    @GetMapping("/events/emitter")        // NO produces — return-type rung pin
    public SseEmitter emitterEvents() { return new SseEmitter(); }

    @GetMapping(value = "/events/stream", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<OrderView>> streamEvents() { return Flux.empty(); }
}
