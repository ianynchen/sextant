package com.acme.actors;

import org.apache.pekko.actor.typed.ActorRef;
import org.apache.pekko.actor.typed.Behavior;
import org.apache.pekko.actor.typed.javadsl.Behaviors;
import org.apache.pekko.cluster.sharding.typed.javadsl.EntityTypeKey;

public final class OrderEntity {

  public interface Command {}

  public record Get(String orderId, ActorRef<Summary> replyTo) implements Command {}

  public record Summary(String orderId, int lines) {}

  public static final EntityTypeKey<Command> KEY = EntityTypeKey.create(Command.class, "order");

  private OrderEntity() {}

  public static Behavior<Command> create(String orderId) {
    return Behaviors.receive(Command.class)
        .onMessage(Get.class, message -> onGet(orderId, message))
        .build();
  }

  private static Behavior<Command> onGet(String orderId, Get message) {
    message.replyTo().tell(new Summary(orderId, 0));
    return Behaviors.same();
  }
}
