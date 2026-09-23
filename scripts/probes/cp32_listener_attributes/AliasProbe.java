// CP-32 Q12's input, and the ONLY source file this probe compiles.
//
// `micronaut-kafka.yml` names two `metadata_from` entries onto one `kind`, because
// `@KafkaListener`'s `value()` and `groupId()` are `@AliasFor` one another (Q4a) and javac
// merges nothing. The line's first draft added a sentence saying a declaration writes at
// most one of the two — which nothing had measured. These two classes are the measurement:
// `Both` writes BOTH elements, `OnlyValue` writes one, and Q12 reads back what each class
// file carries. Compiled with `-proc:none` and WITHOUT Micronaut's annotation processor on
// the path, so what lands is javac's own output — which is exactly what a scan reads.
//
// Not a fixture: it lives beside the probe, is compiled into a temporary directory by
// `run.sh`, and no catalog derives anything from it.
import io.micronaut.configuration.kafka.annotation.KafkaListener;

public class AliasProbe {

    /** Both aliased elements written, and deliberately with DIFFERENT values, so a reader
     *  can tell which one any downstream answer came from. */
    @KafkaListener(value = "by-value", groupId = "by-group-id")
    public static class Both {}

    /** The control: the short spelling, which writes `value` alone. */
    @KafkaListener("by-value")
    public static class OnlyValue {}
}
