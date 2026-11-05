package com.acme.events;

/** An event implementing both markers: published as a `Tracked`, its `Auditable`
 * listener runs too. */
public class Stamped implements Tracked, Auditable {
}
