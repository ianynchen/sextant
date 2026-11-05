package com.acme.actors;

import java.time.Duration;
import java.util.Set;
import org.apache.pekko.actor.typed.ActorRef;
import org.apache.pekko.actor.typed.Behavior;
import org.apache.pekko.actor.typed.javadsl.AbstractBehavior;
import org.apache.pekko.actor.typed.javadsl.ActorContext;
import org.apache.pekko.actor.typed.javadsl.Behaviors;
import org.apache.pekko.actor.typed.javadsl.Receive;
import org.apache.pekko.actor.typed.receptionist.Receptionist;

public final class Frontend extends AbstractBehavior<Frontend.Command> {

  public interface Command {}

  public record Workers(Receptionist.Listing listing) implements Command {}

  public record Reserved(Stock.Reply reply) implements Command {}

  public record Failed(Throwable cause) implements Command {}

  public record Start(String sku) implements Command {}

  public record Loaded(String body) implements Command {}

  private ActorRef<Stock.Command> stock;

  public static Behavior<Command> create() {
    return Behaviors.setup(Frontend::new);
  }

  private Frontend(ActorContext<Command> context) {
    super(context);
    ActorRef<Receptionist.Listing> adapter =
        context.messageAdapter(Receptionist.Listing.class, listing -> new Workers(listing));
    context.getSystem().receptionist().tell(Receptionist.subscribe(Stock.KEY, adapter));
  }

  @Override
  public Receive<Command> createReceive() {
    return newReceiveBuilder()
        .onMessage(Workers.class, this::onWorkers)
        .onMessage(Start.class, this::onStart)
        .onMessage(Reserved.class, message -> Behaviors.same())
        .onMessage(Failed.class, message -> Behaviors.same())
        .onMessage(Loaded.class, message -> Behaviors.same())
        .build();
  }

  private Behavior<Command> onWorkers(Workers message) {
    Set<ActorRef<Stock.Command>> found = message.listing().getServiceInstances(Stock.KEY);
    stock = found.isEmpty() ? null : found.iterator().next();
    return this;
  }

  private Behavior<Command> onStart(Start message) {
    getContext()
        .ask(
            Stock.Reply.class,
            stock,
            Duration.ofSeconds(3),
            r -> new Stock.Reserve(message.sku(), r),
            (res, ex) -> res != null ? new Reserved(res) : new Failed(ex));
    getContext().pipeToSelf(load(message.sku()), (body, ex) -> new Loaded(body));
    return this;
  }

  private java.util.concurrent.CompletionStage<String> load(String sku) {
    return java.util.concurrent.CompletableFuture.completedFuture(sku);
  }
}
