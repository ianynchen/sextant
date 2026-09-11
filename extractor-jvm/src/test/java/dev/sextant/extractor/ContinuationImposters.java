package dev.sextant.extractor;

import kotlin.coroutines.Continuation;

/** Methods that LOOK like suspend functions to a structural test and are not one.
 *
 * <p>Every member here carries a trailing {@code Continuation} in its signature while
 * being an ordinary Java declaration. None appears in any {@code @kotlin.Metadata}, so
 * none may have a parameter dropped or a return type replaced. The scale this stands in
 * for was measured over `kotlinx-coroutines-core-jvm` 1.8.0 and `kotlin-stdlib` 2.2.0:
 * a structural test fires on 683 of 14,895 methods and 228 of those are not suspend
 * functions, most of them the {@code <init>} of generated state-machine classes.
 */
public class ContinuationImposters {

    /** Two declared parameters, an `int` return of its own. */
    public int await(String id, Continuation<? super String> c) {
        return id.length() + c.hashCode();
    }

    /** The whole parameter list is the Continuation, and the return is not Object. */
    public java.util.List<Integer> collect(Continuation<? super String> c) {
        return java.util.List.of(c.hashCode());
    }

    /** An INNER class, so its constructor descriptor carries the enclosing instance that
     *  its signature omits — the case where "the last signature entry" and "the last
     *  descriptor slot" are different slots. Trusting the signature deleted the author's
     *  own parameter and kept the synthetic. */
    public class Inner {
        public Inner(Continuation<? super String> c) {
            c.hashCode();
        }
    }
}
