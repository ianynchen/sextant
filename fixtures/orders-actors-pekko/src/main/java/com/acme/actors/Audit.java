package com.acme.actors;

import org.apache.pekko.actor.typed.ActorRef;
import org.apache.pekko.actor.typed.javadsl.ActorContext;
import org.apache.pekko.actor.typed.receptionist.Receptionist;
import org.apache.pekko.actor.typed.receptionist.ServiceKey;

/**
 * A key whose message class no behavior in this module handles: the actor registered under it
 * is built where nothing here reads its cases. The key is still served here, so looking it up
 * is a hop and no outbound row.
 */
public final class Audit {

  public record Entry(String text) {}

  public static final ServiceKey<Entry> KEY = ServiceKey.create(Entry.class, "audit");

  private Audit() {}

  public static void register(ActorContext<?> context, ActorRef<Entry> self) {
    context.getSystem().receptionist().tell(Receptionist.register(KEY, self));
  }

  public static void lookup(ActorContext<?> context, ActorRef<Receptionist.Listing> replyTo) {
    context.getSystem().receptionist().tell(Receptionist.find(KEY, replyTo));
  }
}
