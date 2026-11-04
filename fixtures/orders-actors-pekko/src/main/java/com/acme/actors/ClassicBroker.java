package com.acme.actors;

import org.apache.pekko.actor.AbstractActor;
import org.apache.pekko.cluster.pubsub.DistributedPubSub;
import org.apache.pekko.actor.ActorRef;
import org.apache.pekko.cluster.pubsub.DistributedPubSubMediator;

public class ClassicBroker extends AbstractActor {

  public record Price(String symbol, double value) {}

  public record Ack() {}

  private final ActorRef mediator = DistributedPubSub.get(getContext().getSystem()).mediator();

  @Override
  public void preStart() {
    mediator.tell(new DistributedPubSubMediator.Subscribe("prices", getSelf()), getSelf());
    mediator.tell(new DistributedPubSubMediator.Put(getSelf()), getSelf());
  }

  @Override
  public Receive createReceive() {
    return receiveBuilder().match(Price.class, this::onPrice).build();
  }

  private void onPrice(Price price) {
    getSender().tell(new Ack(), getSelf());
  }

  public void announce(String symbol, double value) {
    mediator.tell(new DistributedPubSubMediator.Publish("prices", new Price(symbol, value)), getSelf());
    mediator.tell(new DistributedPubSubMediator.Send("/user/broker", new Price(symbol, value), false), getSelf());
  }
}
