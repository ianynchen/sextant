package com.acme.held;

import org.springframework.kafka.core.KafkaTemplate;

/**
 * A publisher whose destination is a field written from a CONSTANT, not from a parameter.
 *
 * <p>`OrderPublisher` beside this one is the sixth edge's shape — a field assigned from a
 * constructor parameter, which `field_writes` records as `from_parameter: 0`. This one
 * compiles to a different write:
 *
 * <pre>
 *   5: ldc       "orders-dead-letter"   // a constant from the pool, no parameter in sight
 *   7: putfield  topic
 * </pre>
 *
 * <p>and `field_writes` could not express it, so NO fact was emitted and the walk answered
 * `no_writer` about a literal one line up. Measured on `spring-petclinic-microservices`,
 * where the same shape holds an outbound host: `private String hostname =
 * "http://visits-service/"`, read into `hostname + "pets/visits?petId={petId}"`, and the
 * published row carried no address at all.
 *
 * <p>**The field is deliberately NOT `final`.** A `final` String field initialised with a
 * constant expression is a *constant variable* (JLS 4.12.4), and javac resolves reads of one
 * at the use site (JLS 13.1) — so the send would carry a literal argument and no field read
 * would exist to resolve. The real-world shape is non-final for its own reason: petclinic's
 * comment says *"Could be changed for testing purpose"*.
 */
public class DeadLetterPublisher {

    private String topic = "orders-dead-letter";
    private final KafkaTemplate<String, String> kafkaTemplate;

    public DeadLetterPublisher(KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publish(String payload) {
        kafkaTemplate.send(topic, payload);
    }
}
