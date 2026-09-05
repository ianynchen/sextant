package com.example.siprobe;

import org.springframework.amqp.rabbit.annotation.Argument;
import org.springframework.amqp.rabbit.annotation.Exchange;
import org.springframework.amqp.rabbit.annotation.Queue;
import org.springframework.amqp.rabbit.annotation.QueueBinding;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.Scheduled;

/** The nested-annotation shapes capability 9.16 exists for, kept in the probe
 *  harness so the finding stays re-runnable against real Spring bytecode rather
 *  than against the extractor's own stand-ins.
 *
 *  <p>Q2 of {@code scripts/probes/spring-integration-destinations.md} found in
 *  passing that {@code @InboundChannelAdapter(poller = @Poller(…))} produced no
 *  {@code poller} key at all — {@code ClassScanner.useCollectingVisitor}
 *  overrode {@code visit}, {@code visitEnum} and {@code visitArray} but not
 *  {@code visitAnnotation}. That one omission lost three separate things, and
 *  this class carries the two the harness did not already have (the polled
 *  adapter itself is on {@code Shape3PolledAndOtherBrokers#tick}). */
@Configuration
public class NestedAnnotationShapes {

    /** Two levels down to the queue name, plus a third to a binding argument:
     *  {@code @RabbitListener} → {@code @QueueBinding} → {@code @Queue} →
     *  {@code @Argument}. This is the deepest nesting the estate produces, and
     *  it is the ONLY place an AMQP queue name is written for this listener —
     *  there is no {@code setQueueNames} call site to fall back to. */
    @RabbitListener(bindings = @QueueBinding(
        value = @Queue(name = "nested.orders.queue", durable = "true",
                       arguments = @Argument(name = "x-dead-letter-exchange",
                                             value = "nested.orders.dlx")),
        exchange = @Exchange(name = "nested.orders.exchange", type = "topic"),
        key = "nested.orders.rk"))
    public void onNestedBoundOrder(String payload) {}

    /** The sharpest case. {@code @Scheduled} is {@code @Repeatable}, so javac
     *  folds these two into a single {@code @Schedules({…, …})} (JLS 9.7.5) and
     *  the method's own annotations become one array of nested annotations.
     *  Before 9.16 this method carried NO trigger at all, while
     *  {@link #singleTrigger()} below carried its own — one schedule was
     *  readable, two were invisible. */
    @Scheduled(cron = "0 0 * * * *")
    @Scheduled(fixedRate = 5000L)
    public void twoTriggers() {}

    /** The control arm: one {@code @Scheduled} is never wrapped, and read
     *  correctly before 9.16. The contrast is what makes the loss above a
     *  defect rather than a uniform limitation. */
    @Scheduled(cron = "0 15 * * * *")
    public void singleTrigger() {}
}
