package com.acme.actors;

import java.time.Duration;
import java.util.concurrent.CompletionStage;
import akka.actor.typed.ActorSystem;
import akka.cluster.sharding.typed.javadsl.ClusterSharding;
import akka.cluster.sharding.typed.javadsl.Entity;

public final class OrderRoutes {

  private final ClusterSharding sharding;
  private final Duration timeout = Duration.ofSeconds(3);

  public OrderRoutes(ActorSystem<?> system) {
    this.sharding = ClusterSharding.get(system);
    sharding.init(Entity.of(OrderEntity.KEY, entityContext -> OrderEntity.create(entityContext.getEntityId())));
  }

  public CompletionStage<OrderEntity.Summary> summary(String id) {
    return sharding
        .entityRefFor(OrderEntity.KEY, id)
        .ask(replyTo -> new OrderEntity.Get(id, replyTo), timeout);
  }
}
