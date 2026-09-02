package dev.sextant.extractor;

/** Committed alongside {@code FieldSample.java}, for the same reason: the
 *  method-modifier assertions must be about what javac actually emits, and a
 *  source fixture Gradle compiles gives that without reaching into another
 *  module's build output.
 *
 *  <p>Every method here exists for one flag combination a consumer enumerating
 *  a class's exposed members has to tell apart (D00 §5a, D02's
 *  {@code mapping.members}).
 */
public class MethodModifierSample implements MethodModifierBase<String> {

    /** The control: an ordinary public instance method, both flags false. */
    public String plain(String value) {
        return value;
    }

    /** THE TRAP. {@code ACC_VARARGS} is {@code 0x0080} on a method — the very
     *  bit that means {@code ACC_TRANSIENT} on a field — so a scanner reusing
     *  the FIELD modifier pair would report this method as "declared not
     *  serialized". It is nothing of the kind: it is an ordinary exposed
     *  member, and both of its real flags are false. */
    public String varargs(String... parts) {
        return parts.length == 0 ? "" : parts[0];
    }

    /** Bound to the type rather than to an instance, so not a member of the
     *  exposed object at all. */
    public static String helper() {
        return "helper";
    }

    /** Not callable from outside the type, so not exposed. */
    private String hidden() {
        return "hidden";
    }

    /** The real override. javac ALSO emits {@code echo(Object)} beside it,
     *  flagged {@code ACC_BRIDGE | ACC_SYNTHETIC}, because
     *  {@link MethodModifierBase}'s own descriptor erases to {@code Object} —
     *  compiler machinery nobody wrote, and the case the {@code synthetic}
     *  flag exists to name. Unlike a synthetic FIELD, it is still emitted as a
     *  fact on purpose (the inheritance walk's bridge rule has to see it), so
     *  the flag rather than omission is what tells the two apart. */
    @Override
    public String echo(String value) {
        return hidden() + value;
    }
}
