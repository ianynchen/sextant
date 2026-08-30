package dev.sextant.extractor;

/** A generic base whose argument is the only statement of the payload type —
 *  the shape {@code ParameterizedTypeReference} and {@code TypeToken} take,
 *  without the framework name (M03 keeps framework knowledge in the catalog).
 *  A subclass that fixes {@code T} declares nothing of its own, so the
 *  superclass reference is where that argument survives. */
class TypeCarrier<T> {
}
