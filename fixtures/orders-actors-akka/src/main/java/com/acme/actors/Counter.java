package com.acme.actors;

import java.time.Duration;
import java.util.concurrent.CompletionStage;
import akka.actor.typed.ActorRef;
import akka.actor.typed.Behavior;
import akka.actor.typed.Scheduler;
import akka.actor.typed.javadsl.AbstractBehavior;
import akka.actor.typed.javadsl.ActorContext;
import akka.actor.typed.javadsl.AskPattern;
import akka.actor.typed.javadsl.Receive;

/** Constructor references where a function is expected: an adapter and an ask's request. */
public final class Counter extends AbstractBehavior<Counter.Command> {

  public interface Command {}

  public record Counted(Stock.Reply reply) implements Command {}

  public record Report(ActorRef<Integer> replyTo) implements Command {}

  private int count;

  private Counter(ActorContext<Command> context) {
    super(context);
    ActorRef<Stock.Reply> adapter = context.messageAdapter(Stock.Reply.class, Counted::new);
  }

  public static CompletionStage<Integer> report(ActorRef<Command> counter, Scheduler scheduler) {
    return AskPattern.ask(counter, Report::new, Duration.ofSeconds(1), scheduler);
  }

  @Override
  public Receive<Command> createReceive() {
    return newReceiveBuilder()
        .onMessage(Counted.class, this::onCounted)
        .onMessage(Report.class, this::onReport)
        .build();
  }

  private Behavior<Command> onCounted(Counted message) {
    count++;
    return this;
  }

  private Behavior<Command> onReport(Report message) {
    message.replyTo().tell(count);
    return this;
  }
}
