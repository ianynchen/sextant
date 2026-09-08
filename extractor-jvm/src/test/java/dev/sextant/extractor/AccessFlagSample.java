package dev.sextant.extractor;

/** W7's fixture for the access flags, one construct per flag that has a payoff. */
public abstract class AccessFlagSample {

    /** `ACC_VARARGS`. The descriptor is `([Ljava/lang/String;)V` — identical to
     *  {@link #array}'s — so without the flag a call passing three strings and one
     *  passing `new String[]{…}` are the same declaration (capability 9.15). */
    public void spread(String... parts) {}

    /** The same descriptor, without the flag. */
    public void array(String[] parts) {}

    /** `ACC_ABSTRACT`. Beside a `default` method on {@link Behaviour}, these two used
     *  to emit identical modifiers. */
    public abstract void declared();

    /** `ACC_SYNCHRONIZED` and `ACC_FINAL` on one declaration. */
    public final synchronized void guarded() {}

    /** `ACC_NATIVE`. */
    public native void foreign();

    /** `ACC_VOLATILE` and `ACC_FINAL` on fields. */
    public volatile int changing = 0;

    public final int fixed = 1;
}

/** `ACC_ANNOTATION`: an annotation TYPE, which carries `ACC_INTERFACE` too — which is
 *  why every one of them read as `construct_kind: "interface"`. */
@interface Marked {}

/** A plain interface with one abstract and one `default` method, so the two can be told
 *  apart by `modifiers.abstract` rather than by nothing at all. */
interface Behaviour {
    void abstractOne();

    default void defaultOne() {}
}
