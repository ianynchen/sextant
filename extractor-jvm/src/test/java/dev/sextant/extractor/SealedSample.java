package dev.sextant.extractor;

import java.io.IOException;

/** W7: a sealed hierarchy, a declared `throws`, and a deprecated declaration. */
public sealed interface SealedSample permits Approved, Rejected {

    /** JVMS 4.7.5 `Exceptions` — two of them, in declaration order. */
    void settle(long id) throws IOException, InterruptedException;

    /** JVMS 4.7.15 `Deprecated`, the ATTRIBUTE, which `@Deprecated` also sets. */
    @Deprecated
    void legacy();
}

record Approved(long id) implements SealedSample {
    public void settle(long id) {}

    @Deprecated
    public void legacy() {}
}

record Rejected(String reason) implements SealedSample {
    public void settle(long id) {}

    @Deprecated
    public void legacy() {}
}
