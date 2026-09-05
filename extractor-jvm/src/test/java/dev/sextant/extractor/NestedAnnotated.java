package dev.sextant.extractor;

import java.lang.annotation.Annotation;
import java.lang.annotation.ElementType;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

/** Mirrors the shapes capability 9.16 exists for: an annotation whose argument is
 *  ANOTHER annotation. ASM reports those through {@code visitAnnotation}, which
 *  {@code ClassScanner.useCollectingVisitor} did not override, so the whole nested
 *  value vanished with no key at all — measured in
 *  {@code scripts/probes/spring-integration-destinations.md} against
 *  {@code @InboundChannelAdapter(poller = @Poller(…))}.
 *
 *  <p>Local stand-ins rather than the real Spring annotations, the same way
 *  {@code EnumAnnotated} stands in for {@code @RequestMapping}: the extractor's
 *  test source set carries no Spring dependency, and the bytecode shape is
 *  identical either way. */
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Poll {
    String fixedDelay() default "";
}

/** The {@code @InboundChannelAdapter(poller = @Poller(…))} shape — one level. */
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Adapter {
    String channel() default "";

    Poll poller() default @Poll;
}

/** The {@code @RabbitListener(bindings = @QueueBinding(value = @Queue(…)))} shape —
 *  an ARRAY of annotations whose elements themselves hold annotations, two levels
 *  down to the queue name. */
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Q {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface QueueBind {
    Q value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Listener {
    QueueBind[] bindings() default {};
}

/** The container javac folds two or more {@code @Sched} onto one method into
 *  (JLS 9.7.5). A method carrying one {@code @Sched} keeps its own annotation; a
 *  method carrying two carries only this, holding both — so before 9.16 the second
 *  schedule did not degrade the first, it erased both. */
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Scheds {
    Sched[] value();
}

@Repeatable(Scheds.class)
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Sched {
    String cron() default "";

    long fixedRate() default -1L;
}

/** The near-miss (GUIDELINES §10): an argument that REFERENCES an annotation type
 *  rather than holding an annotation. ASM reports it through {@code visit} as a
 *  {@code Type}, and D00 §5a's literal model already has a class reference for it. */
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Handled {
    Class<? extends Annotation> handler();
}

// The depth chain. Seven types, one per level, so the outermost sits at depth 0 and
// `Depth6` sits one level past ClassScanner.MAX_NESTED_ANNOTATION_DEPTH. Default
// (CLASS) retention on the inner six is deliberate and harmless: a nested value is
// stored inside its enclosing annotation's attribute, so only the OUTERMOST type's
// retention decides which table it lands in.
@interface Depth6 {
    String value();
}

@interface Depth5 {
    Depth6 value();
}

@interface Depth4 {
    Depth5 value();
}

@interface Depth3 {
    Depth4 value();
}

@interface Depth2 {
    Depth3 value();
}

@interface Depth1 {
    Depth2 value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface DeepRoot {
    Depth1 value();
}

@Adapter(channel = "tickChannel", poller = @Poll(fixedDelay = "1000"))
@Listener(bindings = @QueueBind(@Q("orders.queue")))
@Handled(handler = Poll.class)
@DeepRoot(@Depth1(@Depth2(@Depth3(@Depth4(@Depth5(@Depth6("bottom")))))))
public class NestedAnnotated {

    /** The near-miss's other half: a FIELD whose declared type is an annotation
     *  type. It is a type reference on a symbol fact and must never appear as a
     *  nested-annotation argument. */
    Poll markerTypedField;

    /** javac folds these two into one {@code @Scheds}. */
    @Sched(cron = "0 0 * * * *")
    @Sched(fixedRate = 5000L)
    void twoSchedules() {}

    /** One stays an unwrapped {@code @Sched}, which read correctly before 9.16 —
     *  the contrast is the whole point of the acceptance case. */
    @Sched(cron = "0 15 * * * *")
    void oneSchedule() {}
}
