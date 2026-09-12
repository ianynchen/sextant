package dev.sextant.extractor;

import java.lang.annotation.Annotation;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.function.Consumer;
import kotlin.Metadata;
import kotlin.metadata.Attributes;
import kotlin.metadata.KmClassifier;
import kotlin.metadata.KmConstructor;
import kotlin.metadata.KmFunction;
import kotlin.metadata.KmProperty;
import kotlin.metadata.KmType;
import kotlin.metadata.KmValueParameter;
import kotlin.metadata.jvm.JvmExtensionsKt;
import kotlin.metadata.jvm.JvmMethodSignature;
import kotlin.metadata.jvm.KotlinClassMetadata;
import org.objectweb.asm.AnnotationVisitor;
import org.objectweb.asm.Opcodes;
import org.objectweb.asm.Type;

/** Kotlin's nullability lives in the type system, not in any annotation a scanner could
 *  read the way JSpecify's {@code @Nullable} is read (D00 §5a) — the compiler states it
 *  once, in the opaque protobuf blob it writes to every Kotlin class's {@code @Metadata}
 *  annotation. This reads that blob and maps each property to the nullability its
 *  declared type carries. */
public final class KotlinNullability {
    private KotlinNullability() {}

    /** The one annotation the Kotlin compiler writes to every class it compiles. */
    public static final String DESCRIPTOR = "Lkotlin/Metadata;";

    /** What every non-Kotlin class decodes to: no properties, no parameters and no
     *  suspend functions, so nothing overrides Java's rule. */
    public static final Decoded NONE =
        new Decoded(Map.of(), Map.of(), Map.of(), Map.of(), Set.of());

    /** The eight Kotlin classifiers that compile to a JVM primitive when declared
     *  non-null, and to the box when declared nullable (`OI-80`). {@code kotlin/Int} is
     *  {@code I} in a descriptor and {@code Ljava/lang/Integer;} wherever the JVM cannot
     *  hold a primitive — a type argument, which is exactly where a {@code suspend fun}'s
     *  declared return survives. Which of the two the source meant is the nullability
     *  beside the classifier, and nothing else. */
    static final Map<String, Type> KOTLIN_PRIMITIVES = Map.of(
        "kotlin/Int", Type.INT_TYPE,
        "kotlin/Long", Type.LONG_TYPE,
        "kotlin/Boolean", Type.BOOLEAN_TYPE,
        "kotlin/Double", Type.DOUBLE_TYPE,
        "kotlin/Float", Type.FLOAT_TYPE,
        "kotlin/Short", Type.SHORT_TYPE,
        "kotlin/Byte", Type.BYTE_TYPE,
        "kotlin/Char", Type.CHAR_TYPE);

    /** One class's Kotlin-declared facts, as far as the scanner consumes them.
     *
     *  <p>{@code properties} maps a property NAME to the nullability its declared type
     *  carries — the field projection that has shipped since M03. Absent for a property
     *  declared as a bare type variable ({@link #declaredNullable}), so that field keeps
     *  Java's rule and carries no {@code ext.kotlin} block: the same answer its getter and
     *  its constructor parameter give, because one declared type must not read three ways.
     *
     *  <p>{@code returnNullable} maps a method's JVM {@code name + descriptor} to the
     *  nullability of the type it DECLARES it returns — every Kotlin function, plus every
     *  property's generated GETTER. Keyed by the full JVM signature rather than by the
     *  Kotlin name because overloads share a name and, for a suspend function, share an
     *  erased descriptor return as well: {@code fetch(String): Order} and
     *  {@code maybe(String): Order?} both compile to
     *  {@code (Ljava/lang/String;Lkotlin/coroutines/Continuation;)Ljava/lang/Object;},
     *  so nothing shorter than the signature tells two of them apart.
     *
     *  <p>This is {@code G-63}'s RETURN half. Before it, a Kotlin function's return
     *  carried {@code nullable: true, nullable_resolution: "resolved"} — a certainty
     *  marker on a value the same fact contradicts, since kotlinc writes {@code @NotNull}
     *  on the method beside it. Absent for a return declared as a bare type variable
     *  ({@link #declaredNullable}), so that return keeps Java's rule.
     *
     *  <p>{@code returnClassifier} maps the same key to the NAME of the class the declared
     *  return names ({@code kotlin/Int}, {@code dev/acme/Order}), absent where the
     *  classifier is a type variable. Read for one purpose (`OI-80`): a {@code suspend
     *  fun}'s return is recovered from a type argument, where {@code Int} can only be
     *  spelled {@code Integer}, and only the classifier beside {@code returnNullable} says
     *  whether the source wrote the primitive — {@link Decoded#primitiveReturn}.
     *
     *  <p>{@code parameterTypes} is the PARAMETER half (`OI-82`): the same key maps to
     *  the declared type of each value parameter, in declaration order — every Kotlin
     *  function, plus every constructor. The declared {@code KmType} is kept whole rather
     *  than flattened to a boolean, because nullability is stated at EVERY level of the
     *  type: {@code List<String?>} and {@code List<String>?} erase to one descriptor and
     *  one {@code Signature}, and only this tree tells them apart. {@link TypeRefs} walks
     *  it beside the reference it built from the signature. Metadata lists what the
     *  SOURCE declared while the descriptor may carry synthetics, so aligning an index
     *  here to a descriptor slot is the scanner's decision, not this class's.
     *
     *  <p>{@code suspendMethods} holds the JVM {@code name + descriptor} of every function
     *  metadata marks {@code suspend}. It is the ONLY admissible answer to "is this a
     *  suspending function", and it exists because the structural answer — "the last
     *  parameter is a {@code Continuation}" — is wrong on a large scale. MEASURED over
     *  `kotlinx-coroutines-core-jvm` 1.8.0 plus `kotlin-stdlib` 2.2.0 (14,895 methods):
     *  the structural test fires on 683 and **228 of those are not suspend functions**,
     *  dominated by the {@code <init>} of generated state-machine classes — whose facts
     *  would stop reporting {@code returns: void#}. A Java method declaring a
     *  {@code Continuation} parameter, and a Kotlin {@code fun} that merely takes one,
     *  are the same error one step further out. Metadata cannot make either mistake:
     *  neither appears in {@code getFunctions()} as suspend. */
    public record Decoded(
            Map<String, Boolean> properties,
            Map<String, Boolean> returnNullable,
            Map<String, String> returnClassifier,
            Map<String, List<KmType>> parameterTypes,
            Set<String> suspendMethods) {

        /** The JVM primitive the method keyed {@code key} declares it returns, or null
         *  where it declares none: a Java method, a reference, or a NULLABLE
         *  {@code Int?} — which genuinely boxes, so the {@code Integer} a type argument
         *  spells is then the right answer. */
        public Type primitiveReturn(String key) {
            if (!Boolean.FALSE.equals(returnNullable.get(key))) return null;
            String classifier = returnClassifier.get(key);
            return classifier == null ? null : KOTLIN_PRIMITIVES.get(classifier);
        }
    }

    /** Collects {@code @Metadata}'s elements as ASM visits them, then decodes property
     *  nullability once the annotation is fully read and hands the result to
     *  {@code onDecoded}. Per {@link AnnotationVisitor#visit}'s own contract, `mv` — an
     *  {@code int[]} — arrives as one array object through {@code visit}; only the
     *  {@code String[]} elements (`d1`, `d2`) are itemized through {@code visitArray}.
     *
     *  <p>{@code kotlin-metadata-jvm}'s supported metadata version always trails the
     *  compiler's own — a class compiled by a newer Kotlin than this library understands
     *  is not a bug in the class, and must not take the rest of the module's scan down
     *  with it (M03, FR-17). {@code onUnsupported} receives the library's own explanation
     *  (it already names both the class's version and the maximum supported) instead of
     *  the read failing loudly; {@code onDecoded} still receives {@link #NONE} for that
     *  class, so every field falls back to Java's own rule — an honest fallback,
     *  not a guess dressed up as one. */
    public static AnnotationVisitor collector(
            Consumer<Decoded> onDecoded, Consumer<String> onUnsupported) {
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
                Metadata metadata = new MetadataValues(
                    k[0], mv[0], d1.toArray(new String[0]), d2.toArray(new String[0]),
                    xs[0], pn[0], xi[0]);
                try {
                    onDecoded.accept(decode(metadata));
                } catch (IllegalArgumentException unreadable) {
                    // kotlin-metadata-jvm throws this for metadata it cannot make sense
                    // of — most commonly a compiler version newer than the library
                    // supports, which its message already names alongside the maximum
                    // it does support.
                    onUnsupported.accept(unreadable.getMessage());
                    onDecoded.accept(NONE);
                }
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
    private static Decoded decode(Metadata metadata) {
        KotlinClassMetadata parsed = KotlinClassMetadata.readStrict(metadata);
        if (!(parsed instanceof KotlinClassMetadata.Class classMetadata)) return NONE;
        Map<String, Boolean> properties = new HashMap<>();
        for (KmProperty property : classMetadata.getKmClass().getProperties()) {
            Boolean nullable = declaredNullable(property.getReturnType());
            if (nullable != null) properties.put(property.getName(), nullable);
        }
        Map<String, Boolean> returns = new HashMap<>();
        Map<String, String> returnClassifier = new HashMap<>();
        Map<String, List<KmType>> parameterTypes = new HashMap<>();
        Set<String> suspend = new HashSet<>();
        for (KmFunction function : classMetadata.getKmClass().getFunctions()) {
            // A function metadata describes but whose JVM signature it does not state
            // cannot be joined to the method being visited. Skipped rather than keyed on
            // the Kotlin name, which overloads share.
            JvmMethodSignature signature = JvmExtensionsKt.getSignature(function);
            if (signature == null) continue;
            String key = signature.getName() + signature.getDescriptor();
            Boolean returnNullable = declaredNullable(function.getReturnType());
            if (returnNullable != null) returns.put(key, returnNullable);
            if (function.getReturnType().getClassifier() instanceof KmClassifier.Class named) {
                returnClassifier.put(key, named.getName());
            }
            parameterTypes.put(key, declaredTypes(function.getValueParameters()));
            if (Attributes.isSuspend(function)) suspend.add(key);
        }
        // Constructors too: a data class's primary constructor is where a payload's
        // contract is declared, so a constructor parameter reading `nullable: true` for
        // a `val id: String` was the wrong answer at exactly the place a wire contract
        // is read from. Same key form — the signature's name is `<init>`.
        for (KmConstructor constructor : classMetadata.getKmClass().getConstructors()) {
            JvmMethodSignature signature = JvmExtensionsKt.getSignature(constructor);
            if (signature == null) continue;
            parameterTypes.put(
                signature.getName() + signature.getDescriptor(),
                declaredTypes(constructor.getValueParameters()));
        }
        for (KmProperty property : classMetadata.getKmClass().getProperties()) {
            // The GETTER, not the field: `KotlinOrder#id` the field already reads
            // correctly through `properties` above, while `getId()` is a method and took
            // Java's rule. Same declared type, two facts, and only one of them was right.
            JvmMethodSignature getter = JvmExtensionsKt.getGetterSignature(property);
            if (getter == null) continue;
            Boolean getterNullable = declaredNullable(property.getReturnType());
            if (getterNullable != null) {
                returns.put(getter.getName() + getter.getDescriptor(), getterNullable);
            }
        }
        return new Decoded(properties, returns, returnClassifier, parameterTypes, suspend);
    }

    /** The nullability a declared type states, or null where it states none.
     *
     *  <p>A bare type variable {@code T} is implicitly bounded by {@code Any?}, so
     *  metadata's "not nullable" on it describes the VARIABLE and not what a caller binds
     *  it to — {@code ranked<String?>(null)} is legal against {@code fun <T> ranked(x: T):
     *  T}. Java's rule (a type variable is a reference, and every reference permits null)
     *  is the right answer there and a caller receiving null leaves it standing — on all
     *  three projections, the field, the getter and the parameter, so that one declared
     *  type does not read differently depending on which of them a consumer looks at.
     *  {@code T?} is nullable whatever {@code T} is, and a class is what it says. A bound
     *  that would settle it ({@code T : Any}) is not read: Java's rule is less specific
     *  and never wrong, and no fixture declares one. */
    static Boolean declaredNullable(KmType type) {
        boolean nullable = Attributes.isNullable(type);
        if (!nullable && type.getClassifier() instanceof KmClassifier.TypeParameter) return null;
        return nullable;
    }

    /** One declaration's value parameters' declared types, in declaration order. */
    private static List<KmType> declaredTypes(List<KmValueParameter> parameters) {
        List<KmType> types = new ArrayList<>();
        for (KmValueParameter parameter : parameters) types.add(parameter.getType());
        return List.copyOf(types);
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
