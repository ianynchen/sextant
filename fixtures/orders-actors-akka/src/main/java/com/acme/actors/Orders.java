package com.acme.actors;

import java.util.ArrayList;
import java.util.List;
import akka.actor.typed.ActorRef;
import akka.actor.typed.Behavior;
import akka.persistence.typed.PersistenceId;
import akka.persistence.typed.javadsl.CommandHandler;
import akka.persistence.typed.javadsl.CommandHandlerBuilder;
import akka.persistence.typed.javadsl.CommandHandlerBuilderByState;
import akka.persistence.typed.javadsl.Effect;
import akka.persistence.typed.javadsl.EventHandler;
import akka.persistence.typed.javadsl.EventSourcedBehavior;

public final class Orders extends EventSourcedBehavior<Orders.Command, Orders.Event, Orders.State> {

  public interface Command {}

  public record Place(String item, ActorRef<Placed> replyTo) implements Command {}

  public record Cancel(String item) implements Command {}

  public record Placed(String item) {}

  public interface Event {}

  public record ItemPlaced(String item) implements Event {}

  public record State(List<String> items) {}

  public static Behavior<Command> create(String id) {
    return new Orders(PersistenceId.ofUniqueId(id));
  }

  private Orders(PersistenceId persistenceId) {
    super(persistenceId);
  }

  @Override
  public State emptyState() {
    return new State(new ArrayList<>());
  }

  @Override
  public CommandHandler<Command, Event, State> commandHandler() {
    CommandHandlerBuilder<Command, Event, State> builder = newCommandHandlerBuilder();
    builder.forAnyState().onCommand(Place.class, this::onPlace);
    CommandHandlerBuilderByState<Command, Event, State, State> open = builder.forState(s -> s.items().isEmpty());
    open.onCommand(Cancel.class, this::onCancelEmpty);
    CommandHandlerBuilderByState<Command, Event, State, State> busy = builder.forState(s -> !s.items().isEmpty());
    busy.onCommand(Cancel.class, this::onCancel);
    return builder.build();
  }

  private Effect<Event, State> onPlace(State state, Place command) {
    return Effect().persist(new ItemPlaced(command.item()));
  }

  private Effect<Event, State> onCancelEmpty(State state, Cancel command) {
    return Effect().none();
  }

  private Effect<Event, State> onCancel(State state, Cancel command) {
    return Effect().none();
  }

  @Override
  public EventHandler<State, Event> eventHandler() {
    return newEventHandlerBuilder()
        .forAnyState()
        .onEvent(ItemPlaced.class, (state, event) -> state)
        .build();
  }
}
