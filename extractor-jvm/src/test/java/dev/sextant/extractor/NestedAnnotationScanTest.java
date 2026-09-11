package dev.sextant.extractor;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.InputStream;
import java.util.List;
import org.junit.jupiter.api.Test;

/** Capability 9.16. One missing {@code visitAnnotation} override dropped every
 *  annotation-valued annotation argument, with no key at all rather than an
 *  {@code unresolved} — measured in
 *  {@code scripts/probes/spring-integration-destinations.md}. */
class NestedAnnotationScanTest {

    private List<String> scanNestedAnnotated() throws Exception {
        try (InputStream in =
                getClass().getResourceAsStream("/dev/sextant/extractor/NestedAnnotated.class")) {
            return new ClassScanner("com.acme/orders", "1.0.0")
                .scan(in.readAllBytes(), "doc-nested-annotated");
        }
    }

    /** The shape the probe measured: {@code @InboundChannelAdapter(poller = @Poller(…))}.
     *  The nested value carries its OWN fqn and its OWN args, in the same
     *  {@code {"annotation":…,"args":{…}}} shape the outer use has — D00 §5a's
     *  vocabulary extended, not a second one invented beside it. */
    @Test
    void records_a_nested_annotation_argument_with_its_own_fqn_and_arguments() throws Exception {
        assertTrue(scanNestedAnnotated().stream().anyMatch(line ->
            line.contains(
                "\"annotation\":\"dev/sextant/extractor/Adapter#\","
                    + "\"args\":{\"channel\":\"tickChannel\","
                    + "\"poller\":{\"annotation\":\"dev/sextant/extractor/Poll#\","
                    + "\"args\":{\"fixedDelay\":\"1000\"}}}")));
    }

    /** {@code @RabbitListener(bindings = @QueueBinding(value = @Queue("orders")))} —
     *  an array of annotations holding annotations, so capability 9.15's array
     *  handling and this must compose, and the queue name sits two levels down. */
    @Test
    void records_a_nested_annotation_two_levels_deep_inside_an_array() throws Exception {
        assertTrue(scanNestedAnnotated().stream().anyMatch(line ->
            line.contains(
                "\"bindings\":[{\"annotation\":\"dev/sextant/extractor/QueueBind#\","
                    + "\"args\":{\"value\":{\"annotation\":\"dev/sextant/extractor/Q#\","
                    + "\"args\":{\"value\":\"orders.queue\"}}}}]")));
    }

    /** The acceptance case. {@code @Sched} is {@code @Repeatable}, so javac folds
     *  two onto one method into a single {@code @Scheds} container (JLS 9.7.5,
     *  confirmed against {@code javap -v} on javac 26.0.2.1 {@code --release 21}).
     *  A method with ONE schedule was readable before 9.16; a method with TWO was
     *  completely invisible. Both triggers must now be present. */
    @Test
    void records_both_triggers_of_a_method_carrying_two_repeatable_annotations()
            throws Exception {
        List<String> lines = scanNestedAnnotated();
        assertTrue(lines.stream().anyMatch(line ->
            line.contains("twoSchedules")
                && line.contains(
                    "\"annotation\":\"dev/sextant/extractor/Scheds#\",\"args\":{\"value\":["
                        + "{\"annotation\":\"dev/sextant/extractor/Sched#\","
                        + "\"args\":{\"cron\":\"0 0 * * * *\"}},"
                        + "{\"annotation\":\"dev/sextant/extractor/Sched#\","
                        + "\"args\":{\"fixedRate\":5000}}]}")));
        // The single-schedule method is untouched: still an unwrapped `@Sched`,
        // never folded into a container. The contrast is what makes the loss
        // above a defect rather than a uniform limitation.
        assertTrue(lines.stream().anyMatch(line ->
            line.contains("oneSchedule")
                && line.contains(
                    "\"annotation\":\"dev/sextant/extractor/Sched#\","
                        + "\"args\":{\"cron\":\"0 15 * * * *\"}")));
    }

    /** GUIDELINES §8 at the recursion bound: the annotation TYPE is real evidence
     *  read off the descriptor and is kept, the arguments were never read and get
     *  no key. An empty `args` would be indistinguishable from an annotation
     *  genuinely written with none. */
    @Test
    void marks_a_nesting_deeper_than_the_bound_unresolved_rather_than_truncating()
            throws Exception {
        List<String> lines = scanNestedAnnotated();
        assertTrue(lines.stream().anyMatch(line ->
            line.contains(
                "\"value\":{\"annotation\":\"dev/sextant/extractor/Depth6#\","
                    + "\"unresolved\":\"depth_limit\"}")));
        // Depth 5 is still collected in full — the bound is where it is stated
        // to be, not one level earlier.
        assertTrue(lines.stream().anyMatch(line ->
            line.contains("\"annotation\":\"dev/sextant/extractor/Depth5#\",\"args\":{")));
        // And nothing past the bound is reconstructed.
        assertFalse(lines.stream().anyMatch(line -> line.contains("bottom")));
    }

    /** Near-miss (GUIDELINES §10), both halves: an argument that REFERENCES an
     *  annotation type is a class reference and stays one, and a FIELD whose
     *  declared type is an annotation type is a type reference on a symbol fact.
     *  Neither is a nested annotation, and neither may grow an `args` of its own. */
    @Test
    void does_not_treat_a_class_reference_or_a_field_of_annotation_type_as_nesting()
            throws Exception {
        List<String> lines = scanNestedAnnotated();
        assertTrue(lines.stream().anyMatch(line ->
            line.contains("\"annotation\":\"dev/sextant/extractor/Handled#\","
                + "\"args\":{\"handler\":\"dev/sextant/extractor/Poll#\"}")));
        assertFalse(lines.stream().anyMatch(line ->
            line.contains("\"handler\":{\"annotation\"")));
        // The field is a symbol fact naming `Poll` as its TYPE. It carries no
        // annotation of its own, so no `annotation` fact may name it either.
        assertTrue(lines.stream().anyMatch(line ->
            line.contains("\"kind\":\"symbol\"")
                && line.contains("markerTypedField")
                && line.contains("dev/sextant/extractor/Poll#")));
        assertFalse(lines.stream().anyMatch(line ->
            line.contains("\"kind\":\"annotation\"") && line.contains("markerTypedField")));
    }
}
