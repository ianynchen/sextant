package dev.sextant.extractor;

import java.io.Serializable;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/** W5's fixture: every place a {@code Signature} attribute says something the
 *  erased descriptor cannot.
 *
 *  <p>The class declares a BOUNDED formal type parameter; one method declares
 *  its own; one method takes a parameterized parameter; and {@link Inner}'s
 *  constructor is the skew case — javac writes the outer instance into the
 *  descriptor and leaves it out of the signature, so a positional read of the
 *  two lists disagrees by one. */
public class GenericSignatureSample<T extends Comparable<T>> {

    /** A parameterized parameter type. The descriptor says {@code List}; only
     *  the signature says {@code List<String>}, and only the signature says the
     *  second parameter is the class's own {@code T} rather than its erasure. */
    public void accept(List<String> names, T item) {}

    /** A method that declares a formal type parameter of its OWN, with an
     *  interface bound — the class's parameter is not the only one a generic
     *  substitution has to bind. */
    public <K extends CharSequence> Map<K, T> pair(K key) {
        return null;
    }

    /** No type variable and no parameterization anywhere: javac writes NO
     *  {@code Signature} attribute at all, and the erased descriptor is the
     *  only source there is. */
    public void plain(String value) {}

    /** Two bounds on one parameter, and neither type appears anywhere else in the
     *  method — {@code W} is not the type of anything it declares — so an assertion on
     *  either can only be satisfied by the bound itself. {@code <W extends Number &
     *  Serializable>} is written {@code W:Ljava/lang/Number;:Ljava/io/Serializable;}
     *  (measured): a class bound, then an interface bound. */
    public <W extends Number & Serializable> void bounded(String only) {}

    /** A type parameter bounded by ANOTHER type parameter. This is the shape that walks
     *  a bound which is a bare type VARIABLE, and a variable is handed over the instant
     *  it is seen rather than at an end-of-node callback — so a bound collector keyed on
     *  that callback would drop it silently. */
    public <A, C extends A> void chained(String only) {}

    /** A local class that CAPTURES. javac appends the captured values to the
     *  constructor's descriptor — at the END — while the {@code Signature} attribute
     *  names only what was written in source, so here the two lists disagree in the
     *  opposite direction from {@link Inner}. The count alone cannot tell the two apart;
     *  {@code MethodParameters} can. */
    public void capturingLocal(int limit) {
        final StringBuilder captured = new StringBuilder();
        class Local {
            Local(@Labelled("real") @TypeUsed List<String> tags) {
                captured.append(tags).append(limit);
            }
        }
        new Local(new ArrayList<>());
    }

    /** The same capture, in a STATIC method — where javac writes no
     *  {@code MethodParameters} attribute at all (measured). Nothing then says which
     *  descriptor slots the signature omitted, and the only honest answer is the erased
     *  type for every parameter. */
    public static void capturingStaticLocal(int limit) {
        final StringBuilder captured = new StringBuilder();
        class StaticLocal {
            StaticLocal(@Labelled("real") @TypeUsed List<String> tags) {
                captured.append(tags).append(limit);
            }
        }
        new StaticLocal(new ArrayList<>());
    }

    /** A covariant override and the bridge javac ships beside it. The override declares
     *  {@code T} and carries a {@code Signature}; the bridge carries none, so its
     *  parameters can only ever read erased. Two members of one class, one parameter
     *  list in source, and two different parameter SYMBOLS in the facts. */
    public static class Base<T> {
        public Object get(T item) {
            return null;
        }
    }

    /** @see Base */
    public static class Sub<T> extends Base<T> {
        @Override
        public String get(T item) {
            return null;
        }
    }

    /** An INNER class — deliberately not static. Its constructor's descriptor
     *  carries the enclosing instance as a leading parameter that the
     *  {@code Signature} attribute omits (JVMS 4.7.9.1: implicitly declared
     *  parameters may be left out), which is the skew this fixture exists to
     *  measure rather than assume. */
    public class Inner {
        public Inner(@TypeUsed List<String> tags) {}
    }
}
