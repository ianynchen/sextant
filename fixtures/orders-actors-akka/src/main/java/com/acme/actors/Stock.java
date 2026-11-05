package com.acme.actors;

import java.time.Duration;
import akka.actor.typed.ActorRef;
import akka.actor.typed.Behavior;
import akka.actor.typed.javadsl.ActorContext;
import akka.actor.typed.javadsl.Behaviors;
import akka.actor.typed.receptionist.Receptionist;
import akka.actor.typed.receptionist.ServiceKey;

public final class Stock {

  public interface Command {}

  public record Reserve(String sku, ActorRef<Reply> replyTo) implements Command {}

  public record Release(String sku, boolean urgent) implements Command {}

  public enum Tick implements Command {
    INSTANCE
  }

  public record Reply(String sku, boolean ok) {}

  public static final ServiceKey<Command> KEY = ServiceKey.create(Command.class, "stock");

  private Stock() {}

  public static Behavior<Command> create() {
    return Behaviors.setup(
        context -> {
          context.getSystem().receptionist().tell(Receptionist.register(KEY, context.getSelf()));
          return Behaviors.withTimers(
              timers -> {
                timers.startTimerWithFixedDelay(Tick.INSTANCE, Duration.ofSeconds(30));
                return behavior(context);
              });
        });
  }

  private static Behavior<Command> behavior(ActorContext<Command> context) {
    return Behaviors.receive(Command.class)
        .onMessage(Reserve.class, Stock::onReserve)
        .onMessage(Release.class, p -> p.urgent(), Stock::onUrgentRelease)
        .onMessage(Release.class, Stock::onRelease)
        .onMessageEquals(Tick.INSTANCE, Stock::onTick)
        .build();
  }

  private static Behavior<Command> onReserve(Reserve message) {
    message.replyTo().tell(new Reply(message.sku(), true));
    return Behaviors.same();
  }

  private static Behavior<Command> onUrgentRelease(Release message) {
    return Behaviors.same();
  }

  private static Behavior<Command> onRelease(Release message) {
    return Behaviors.same();
  }

  private static Behavior<Command> onTick() {
    return Behaviors.same();
  }
}
