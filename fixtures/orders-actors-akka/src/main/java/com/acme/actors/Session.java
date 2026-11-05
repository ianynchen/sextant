package com.acme.actors;

import java.time.Duration;
import akka.actor.typed.Behavior;
import akka.actor.typed.javadsl.AbstractBehavior;
import akka.actor.typed.javadsl.ActorContext;
import akka.actor.typed.javadsl.Behaviors;
import akka.actor.typed.javadsl.Receive;

/**
 * A receive timeout: the actor tells itself `Timeout.INSTANCE` after a silence (the
 * `akka-sample-cluster-java` `StatsAggregator` shape), so the timeout's case is reached.
 */
public final class Session extends AbstractBehavior<Session.Event> {

  public interface Event {}

  public enum Timeout implements Event {
    INSTANCE
  }

  public record Touched(String by) implements Event {}

  private Session(ActorContext<Event> context) {
    super(context);
    getContext().setReceiveTimeout(Duration.ofSeconds(3), Timeout.INSTANCE);
  }

  public static Behavior<Event> create() {
    return Behaviors.setup(Session::new);
  }

  @Override
  public Receive<Event> createReceive() {
    return newReceiveBuilder()
        .onMessage(Touched.class, this::onTouched)
        .onMessageEquals(Timeout.INSTANCE, this::onTimeout)
        .build();
  }

  private Behavior<Event> onTouched(Touched message) {
    return this;
  }

  private Behavior<Event> onTimeout() {
    return Behaviors.stopped();
  }
}
