package dev.sextant.extractor;

/** The JVMS 4.7.18 index skew, in the one shape where it cannot be caught
 *  downstream by type.
 *
 *  <p>javac synthesises two leading constructor parameters for an enum —
 *  {@code $enum$name} (a String) and {@code $enum$ordinal} (an int) — and OMITS
 *  them from the parameter-annotation attribute, so `num_parameters` there is
 *  smaller than the descriptor's own count. An extractor that indexes the
 *  attribute from zero puts {@code @Labelled} on {@code $enum$name}.
 *
 *  <p>An inner class skews by one and its hidden parameter is the outer
 *  instance, so a consumer could in principle notice the type is wrong. Here
 *  the hidden first parameter is ALSO a {@code String}, which is why the spec
 *  requires an enum for this test: the misalignment is invisible to every check
 *  except the one that knows about 4.7.18. */
public enum EnumConstructorAnnotated {
    EARTH("earth", 1);

    private final String display;
    private final int rank;

    EnumConstructorAnnotated(@Labelled("display") @TypeUsed String display, int rank) {
        this.display = display;
        this.rank = rank;
    }

    public String display() {
        return display;
    }

    public int rank() {
        return rank;
    }
}
