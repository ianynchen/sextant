package dev.sextant.extractor;

/** A superinterface that fixes its own type arguments — capability 9.14's own
 *  fixture. `interfaces` alone erases {@code Keyed<String, Long>} to a bare
 *  symbol, the same loss {@link SupertypeSample} exists to recover for a
 *  superclass, one level over: D00 §5a's PTR-carrier rule, applied to
 *  `implements`. */
public interface GenericInterfaceSample extends Keyed<String, Long> {
}

/** The generic superinterface itself — package-private, since only {@link
 *  GenericInterfaceSample}'s signature needs it to exist. */
interface Keyed<K, V> {
    K key();
    V value();
}
