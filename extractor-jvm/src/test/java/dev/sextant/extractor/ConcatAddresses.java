package dev.sextant.extractor;

/** W4 fixture: the two shapes an assembled address takes. */
public final class ConcatAddresses {

    /** Runtime value spliced in — javac cannot fold this, so it emits a recipe. */
    public String built(String version) {
        return "/api/" + version + "/orders";
    }

    /** Both halves are compile-time constants, so javac folds them and no
     *  concat site exists at all. */
    public String folded() {
        return "/api/" + "v2" + "/folded";
    }
}
