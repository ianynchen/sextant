package dev.sextant.extractor;

/** Implements two interfaces, in this declaration order — exercises `interfaces`
 *  on a class symbol fact (D00 §5a's `implemented_interfaces` capability). */
public class InterfaceSample implements AutoCloseable, Runnable {
    @Override public void close() {}
    @Override public void run() {}
}
