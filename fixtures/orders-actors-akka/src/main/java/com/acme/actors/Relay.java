package com.acme.actors;

import akka.actor.typed.ActorRef;

public final class Relay {

  private Relay() {}

  public static void forward(Object msg, ActorRef<Object> to) {
    to.tell(msg);
  }
}
