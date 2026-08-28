package dev.sextant.extractor;

import java.lang.annotation.Annotation;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.function.Consumer;
import kotlin.Metadata;
import kotlin.metadata.Attributes;
import kotlin.metadata.KmProperty;
import kotlin.metadata.jvm.KotlinClassMetadata;
import org.objectweb.asm.AnnotationVisitor;
import org.objectweb.asm.Opcodes;

/** Kotlin's nullability lives in the type system, not in any annotation a scanner could
 *  read the way JSpecify's {@code @Nullable} is read (D00 §5a) — the compiler states it
 *  once, in the opaque protobuf blob it writes to every Kotlin class's {@code @Metadata}
 *  annotation. This reads that blob and maps each property to the nullability its
 *  declared type carries. */
public final class KotlinNullability {
    private KotlinNullability() {}

    /** The one annotation the Kotlin compiler writes to every class it compiles. */
    public static final String DESCRIPTOR = "Lkotlin/Metadata;";

    /** What every non-Kotlin class decodes to: no properties, so nothing overrides
     *  Java's rule. */
    public static final Map<String, Boolean> NONE = Map.of();

    /** Collects {@code @Metadata}'s elements as ASM visits them, then decodes property
     *  nullability once the annotation is fully read and hands the result to
     *  {@code onDecoded}. Per {@link AnnotationVisitor#visit}'s own contract, `mv` — an
     *  {@code int[]} — arrives as one array object through {@code visit}; only the
     *  {@code String[]} elements (`d1`, `d2`) are itemized through {@code visitArray}. */
    public static AnnotationVisitor collector(Consumer<Map<String, Boolean>> onDecoded) {
        int[] k = {0};
        int[][] mv = {new int[0]};
        List<String> d1 = new ArrayList<>();
        List<String> d2 = new ArrayList<>();
        String[] xs = {""};
        String[] pn = {""};
        int[] xi = {0};
        return new AnnotationVisitor(Opcodes.ASM9) {
            @Override
            public void visit(String name, Object value) {
                switch (name) {
                    case "k" -> k[0] = (int) value;
                    case "mv" -> mv[0] = (int[]) value;
                    case "xs" -> xs[0] = (String) value;
                    case "pn" -> pn[0] = (String) value;
                    case "xi" -> xi[0] = (int) value;
                    default -> {}
                }
            }

            @Override
            public AnnotationVisitor visitArray(String name) {
                return switch (name) {
                    case "d1" -> stringCollector(d1);
                    case "d2" -> stringCollector(d2);
                    default -> null;
                };
            }

            @Override
            public void visitEnd() {
                onDecoded.accept(propertyNullability(new MetadataValues(
                    k[0], mv[0], d1.toArray(new String[0]), d2.toArray(new String[0]),
                    xs[0], pn[0], xi[0])));
            }
        };
    }

    private static AnnotationVisitor stringCollector(List<String> sink) {
        return new AnnotationVisitor(Opcodes.ASM9) {
            @Override
            public void visit(String ignored, Object value) {
                sink.add((String) value);
            }
        };
    }

    /** Decodes one class's already-collected {@code @Metadata} elements into
     *  {@code property name -> nullable}. Anything other than a class facade (a file
     *  facade, a synthetic lambda class, ...) has no properties and decodes to the
     *  empty map — the Kotlin compiler writes {@code @Metadata} to those too. */
    private static Map<String, Boolean> propertyNullability(Metadata metadata) {
        KotlinClassMetadata parsed = KotlinClassMetadata.readStrict(metadata);
        if (!(parsed instanceof KotlinClassMetadata.Class classMetadata)) return NONE;
        Map<String, Boolean> result = new HashMap<>();
        for (KmProperty property : classMetadata.getKmClass().getProperties()) {
            result.put(property.getName(), Attributes.isNullable(property.getReturnType()));
        }
        return result;
    }

    /** A plain implementation of the annotation interface {@code kotlin-metadata-jvm}
     *  expects, standing in for the runtime instance reflection would have supplied —
     *  ASM only ever hands back element values, never an {@code Annotation} object.
     *  {@code bv} is excluded: it is {@link Metadata#bv() deprecated} and unused by
     *  {@code kotlin-metadata-jvm}'s reader, so nothing ASM hands back is collected
     *  for it either. */
    private record MetadataValues(
            int k, int[] mv, String[] d1, String[] d2, String xs, String pn, int xi)
            implements Metadata {
        @Override
        public Class<? extends Annotation> annotationType() {
            return Metadata.class;
        }

        @Override
        @SuppressWarnings("deprecation")
        public int[] bv() {
            return new int[0];
        }
    }
}
