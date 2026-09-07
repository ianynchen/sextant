package dev.sextant.extractor;

import java.util.ArrayList;
import java.util.List;
import java.util.TreeMap;
import java.util.function.Consumer;
import org.objectweb.asm.Type;
import org.objectweb.asm.signature.SignatureReader;
import org.objectweb.asm.signature.SignatureVisitor;

/** Type references: a symbol reference plus optional type arguments, recursively
 *  (D00 §5a). Recorded verbatim — unwrapping envelopes is catalog knowledge. */
public final class TypeRefs {
    private TypeRefs() {}

    /** A type reference built from an erased descriptor — a method parameter, or a return
     *  type whose method carries no {@code Signature} attribute. Fully projected, exactly
     *  like {@link #fieldRef}: a signature-level reference and a field's reference describe
     *  the same thing, and a consumer that has to ask which of the two it is holding before
     *  it can read {@code wire_type} has two grammars where D00 §5a states one. What the
     *  descriptor genuinely lost — the type arguments — stays lost; the projection is not a
     *  claim about arguments that were never there. */
    public static String fromType(Type type) {
        return toJson(nodeFromType(type));
    }

    // Package-private: ClassScanner's field type references share this exact
    // symbol grammar rather than keeping their own copy of it.
    static String descriptorName(Type type) {
        return switch (type.getSort()) {
            case Type.OBJECT -> type.getInternalName() + "#";
            // ONE dimension per step, never `getElementType()` (`A-M10`). ASM's
            // `Type#getElementType` returns an array's INNERMOST element type, not its
            // component type, so `descriptorName(getElementType()) + "[]"` appended exactly
            // one `[]` however many the descriptor carried: `String[][]` and `String[]`
            // produced byte-identical facts. JVMS 4.3.2 and JLS 10.1 make the number of
            // `[` part of the type's identity — `[[Ljava/lang/String;` is an array whose
            // COMPONENT type is `[Ljava/lang/String;` — so a DR-5 contract comparison of a
            // caller sending `String[][]` against a callee expecting `String[]` read equal.
            // Dropping the leading `[` and recursing is that sentence: it is what
            // `NodeCollector.visitArrayType` below already does on the signature path,
            // which is why the two seams disagreed with each other.
            case Type.ARRAY -> descriptorName(componentType(type)) + "[]";
            default -> type.getClassName() + "#";
        };
    }

    /** An array's COMPONENT type — one dimension less, which is what JVMS 4.3.2 means by
     *  a component — as against ASM's own {@code getElementType()}, which strips every
     *  dimension at once. Spelled out here rather than inlined at its two call sites
     *  because getting it wrong is silent in both: the fact is well formed and names a
     *  different type. */
    private static Type componentType(Type array) {
        return Type.getType(array.getDescriptor().substring(1));
    }

    /** Generic return type from the Signature attribute, or null when absent. Walked by the
     *  same {@link NodeCollector} a field's signature is, so a return type and a field of
     *  the same declared type produce the same reference — an envelope such as
     *  {@code ResponseEntity<OrderView>} keeps both its own {@code wire_type} and its
     *  argument's, which is what lets a later pass root the payload and then say whether
     *  what it rooted at is a payload at all. */
    public static String returnFromSignature(String signature) {
        if (signature == null) return null;
        List<Node> collected = new ArrayList<>();
        new SignatureReader(signature).accept(new SignatureVisitor(org.objectweb.asm.Opcodes.ASM9) {
            @Override public SignatureVisitor visitReturnType() {
                return new NodeCollector(collected::add);
            }
        });
        return collected.isEmpty() ? null : toJson(collected.get(0));
    }

    /** The generic superclass reference from a class {@code Signature}, or null when there is
     *  none to capture — D00 §5a's PTR carrier. {@code new ParameterizedTypeReference<List<OrderView>>() {}}
     *  compiles to a class whose own descriptor names nothing and whose signature names
     *  everything, so this is the only place that payload type survives.
     *
     *  <p>Null for a superclass with **no type argument**, not merely for an absent signature.
     *  A class signature is written whenever the class *itself* declares a type parameter, so
     *  {@code class Box<T>} has one and its superclass part reads {@code java/lang/Object} —
     *  emitting that would put a supertype reference on a large fraction of every module and
     *  say nothing with any of them. D00 §5a draws the line in the same place: "an ordinary,
     *  non-generic superclass carries no such field", the relationship itself being already
     *  stated once at {@code relationship_kind: extends}.
     *
     *  <p>Walked by the same {@link NodeCollector} a field and a return type are, so the
     *  argument a consumer roots a payload from is the same recursive shape it reads
     *  everywhere else. */
    public static String genericSuperclassFromSignature(String signature) {
        if (signature == null) return null;
        List<Node> collected = new ArrayList<>();
        new SignatureReader(signature).accept(new SignatureVisitor(org.objectweb.asm.Opcodes.ASM9) {
            @Override public SignatureVisitor visitSuperclass() {
                return new NodeCollector(collected::add);
            }
        });
        if (collected.isEmpty()) return null;
        Node superclass = collected.get(0);
        return superclass.argumentsJson().isEmpty() ? null : toJson(superclass);
    }

    /** The generic superinterface references from a class {@code Signature} — D00 §5a's
     *  PTR-carrier rule, applied one level over to `implements`: {@code interface
     *  OrderRepository extends CrudRepository<Order, Long>} erases to
     *  {@code interfaces: [".../CrudRepository#"]} with the entity and id types lost, and
     *  Spring Data REST cannot derive a repository's entity type from that alone (2O
     *  design §2a) — this is the only place they survive.
     *
     *  <p>Empty for a class signature with no generic superinterface, not merely for an
     *  absent signature — the same "nothing generic, nothing captured" rule
     *  {@link #genericSuperclassFromSignature} states for a superclass, applied per
     *  interface: an ordinary, non-generic interface is already named once by the erased
     *  `interfaces` list. Where one interface in the list is generic and another is not,
     *  only the generic one is captured — never a positional placeholder for the one with
     *  nothing to say.
     *
     *  <p>In declaration order, walked by the same {@link NodeCollector} every other type
     *  reference is. */
    public static List<String> genericInterfacesFromSignature(String signature) {
        if (signature == null) return List.of();
        List<Node> collected = new ArrayList<>();
        new SignatureReader(signature).accept(new SignatureVisitor(org.objectweb.asm.Opcodes.ASM9) {
            @Override public SignatureVisitor visitInterface() {
                return new NodeCollector(collected::add);
            }
        });
        List<String> generic = new ArrayList<>();
        for (Node node : collected) {
            if (!node.argumentsJson().isEmpty()) generic.add(toJson(node));
        }
        return generic;
    }

    /** The generic PARAMETER types from a method or constructor {@code Signature}, in
     *  declaration order — empty when the method carries no such attribute, which is
     *  exactly when it has nothing generic to say (JVMS 4.7.9.1 writes the attribute only
     *  for a method whose declaration uses a type variable or a parameterization).
     *
     *  <p>The list is not always as long as the descriptor's. JVMS 4.7.9.1 permits a
     *  signature to omit parameters that are IMPLICITLY declared, and javac takes it:
     *  measured on {@code GenericSignatureSample$Inner}, the constructor's descriptor is
     *  {@code (LGenericSignatureSample;Ljava/util/List;)V} and its signature is
     *  {@code (Ljava/util/List<Ljava/lang/String;>;)V} — the enclosing instance is in one
     *  and not the other. Aligning the two positionally would put {@code List<String>} on
     *  the outer instance and leave the real parameter erased.
     *
     *  <p>{@link ClassScanner} does the alignment, and it does NOT do it by counting.
     *  What a signature omits is not always omitted from the front — a local class that
     *  captures gets its captures appended at the END (measured) — so the difference in
     *  length says nothing about which entries are missing. `MethodParameters`
     *  (JVMS 4.7.24) says which, and the same helper answers it for the parameter
     *  ANNOTATION tables too.
     *
     *  <p>Walked by the same {@link NodeCollector} a field and a return type are, so a
     *  parameter's reference is the identical recursive shape — including a bare type
     *  VARIABLE, which {@code returnFromSignature} has already been able to yield since
     *  the collector existed. {@code accept(List<String>, T)} keeps both {@code String}
     *  and the name {@code T}; the descriptor keeps neither, having erased them to
     *  {@code List} and {@code Comparable}. */
    public static List<String> parametersFromSignature(String signature) {
        if (signature == null) return List.of();
        List<String> parameters = new ArrayList<>();
        new SignatureReader(signature).accept(new SignatureVisitor(org.objectweb.asm.Opcodes.ASM9) {
            @Override public SignatureVisitor visitParameterType() {
                return new NodeCollector(node -> parameters.add(toJson(node)));
            }
        });
        return parameters;
    }

    /** The FORMAL type parameters a class or method declares, in declaration order, each
     *  as {@code {name, bounds}} — empty when the declaration has none.
     *
     *  <p>The name and the order are the load-bearing half: a generic substitution binds
     *  {@code T} by the position it was declared at, and until now nothing in a fact said
     *  what {@code T} even was. {@code parametersFromSignature} above can now emit a
     *  reference whose symbol is {@code T}, so this is what stops that from being an
     *  unattached string.
     *
     *  <p>Bounds are recorded exactly as the signature states them, {@code java/lang/Object}
     *  included. javac writes {@code T:Ljava/lang/Object;} for a parameter declared
     *  {@code <T>} (measured) — the bytes for {@code <T>} and {@code <T extends Object>} are
     *  identical, so there is no distinction here to flatten and nothing is gained by
     *  dropping it. Dropping it would cost something instead: a bounds list that is empty
     *  for one parameter and populated for the next leaves a reader unable to tell an
     *  unbounded declaration from a bound the scanner declined to read, which is the
     *  absence ambiguity GUIDELINES §8 exists to refuse. Multiple bounds stay multiple —
     *  {@code <U extends Number & Serializable>} is written {@code U:Ljava/lang/Number;:Ljava/io/Serializable;}
     *  and yields two entries, in that order.
     *
     *  <p>A bound is walked by the same {@link NodeCollector} every other reference is, so
     *  {@code T extends Comparable<T>} keeps the {@code T} inside {@code Comparable} too. */
    public static List<String> typeParametersFromSignature(String signature) {
        if (signature == null) return List.of();
        List<String> declared = new ArrayList<>();
        FormalTypeParameters collector = new FormalTypeParameters(declared);
        new SignatureReader(signature).accept(collector);
        // The reader has no "the formal parameter section ended" callback, so the last
        // one is still pending here. `accept` is synchronous and every NodeCollector
        // hands its node over during the walk, so nothing is still in flight.
        collector.flush();
        return declared;
    }

    /** Accumulates one formal type parameter at a time: a name arrives, then zero or more
     *  bounds, then either the next name or the end of the section. */
    private static final class FormalTypeParameters extends SignatureVisitor {
        private final List<String> declared;
        private String name;
        private final List<String> bounds = new ArrayList<>();

        FormalTypeParameters(List<String> declared) {
            super(org.objectweb.asm.Opcodes.ASM9);
            this.declared = declared;
        }

        @Override public void visitFormalTypeParameter(String parameterName) {
            flush();
            name = parameterName;
        }

        @Override public SignatureVisitor visitClassBound() {
            return new NodeCollector(bound -> bounds.add(toJson(bound)));
        }

        @Override public SignatureVisitor visitInterfaceBound() {
            return new NodeCollector(bound -> bounds.add(toJson(bound)));
        }

        void flush() {
            if (name == null) return;
            TreeMap<String, String> parameter = new TreeMap<>();
            parameter.put("name", JsonOut.string(name));
            parameter.put("bounds", JsonOut.array(bounds));
            declared.add(JsonOut.object(parameter));
            name = null;
            bounds.clear();
        }
    }

    /** A field's fully augmented type reference: the {symbol, arguments} envelope every
     *  type reference carries (D00 §5a), plus D1's wire-type projection and D3's
     *  nullability at **every** level of the chain — a parameterized type keeps each of
     *  its arguments as a full reference of its own, never a bare string.
     *  `List&lt;CustomerRef&gt;` must keep `CustomerRef`, not erase to plain `List`.
     *
     *  <p>Reads the field's generic {@code Signature} attribute when present — the erased
     *  descriptor alone has already lost every type argument by the time it reaches this
     *  method — and falls back to the descriptor when absent, which is exactly when the
     *  JVM spec omits the attribute: a field typed with no type variable and no
     *  parameterization (a plain {@code String} or {@code long}) gets no {@code Signature}
     *  attribute at all.
     *
     *  <p>{@code nullableOverride}, when non-null, replaces the computed top-level
     *  nullability with a value another source already resolved — Kotlin's type system,
     *  D3's Kotlin half — without touching any nested type argument, which that source
     *  says nothing about. */
    public static String fieldRef(Type erasedType, String genericSignature, Boolean nullableOverride) {
        Node node = genericSignature == null ? null : fromSignature(genericSignature);
        if (node == null) node = nodeFromType(erasedType);
        return toJson(nullableOverride == null ? node : node.withNullable(nullableOverride));
    }

    private static Node fromSignature(String genericSignature) {
        List<Node> collected = new ArrayList<>();
        new SignatureReader(genericSignature).acceptType(new NodeCollector(collected::add));
        // A malformed or unrecognised FieldTypeSignature has no honest reference to
        // build; the caller falls back to the descriptor, which is never wrong, only
        // less specific.
        return collected.isEmpty() ? null : collected.get(0);
    }

    private static Node nodeFromType(Type type) {
        boolean nullable = type.getSort() == Type.OBJECT || type.getSort() == Type.ARRAY;
        return new Node(descriptorName(type), elementArguments(type), nullable,
            WireTypes.of(type), WireTypes.format(type));
    }

    /** An array's element as its single type argument. The array's own symbol already ends
     *  in {@code []}, but that suffix is descriptor grammar — language knowledge (D1) that
     *  the language-blind half must not have to parse. Without the element as a real
     *  reference, {@code CustomerRef[]} and {@code String[]} are the same {@code array}
     *  with nothing held: an expansion pass cannot tell them apart, cannot report the type
     *  it failed to expand, and DR-5 matches a caller sending strings against a callee
     *  expecting records. A collection expressed as {@code List<E>} has carried its element
     *  since D00 §5a; an array is the same claim in different syntax. */
    private static List<String> elementArguments(Type type) {
        // `componentType`, not `getElementType()` (`A-M10`): a `String[][]` holds ONE
        // `String[]`, and reporting it as holding a `String` is the same lost dimension
        // `descriptorName` had — reached through the argument list instead of the symbol,
        // and read by `shapes/expansion.py::_described`, which hashes what it finds.
        return type.getSort() == Type.ARRAY
            ? List.of(toJson(nodeFromType(componentType(type))))
            : List.of();
    }

    private static String toJson(Node node) {
        TreeMap<String, String> fields = new TreeMap<>();
        fields.put("symbol", JsonOut.string(node.symbol()));
        fields.put("arguments", JsonOut.array(node.argumentsJson()));
        fields.put("wire_type", JsonOut.string(node.wireType()));
        fields.put("wire_format", JsonOut.string(node.wireFormat()));
        fields.put("nullable", String.valueOf(node.nullable()));
        // D3 (corrected): `resolution` is candidate-set semantics (CONTEXT.md) — how
        // certain a fact's *target* is — and a boolean has no candidate set. Java's type
        // system settles nullability outright: every reference permits null and every
        // primitive forbids it. Never partial, never anything but resolved on the JVM.
        fields.put("nullable_resolution", JsonOut.string("resolved"));
        return JsonOut.object(fields);
    }

    /** One level of an augmented type reference, pre-serialization — {@link #toJson}
     *  turns exactly one of these into the JSON object a caller keeps. */
    private record Node(String symbol, List<String> argumentsJson, boolean nullable,
                         String wireType, String wireFormat) {
        Node withNullable(boolean value) {
            return new Node(symbol, argumentsJson, value, wireType, wireFormat);
        }
    }

    /** Walks a {@code FieldTypeSignature} (JVMS 4.7.9.1) — a class type, an array type, a
     *  type variable, or a base type — recursively, handing one {@link Node} to
     *  {@code onDone} once that level is fully parsed. The one collector: a field's
     *  signature and a method's return-type signature are the same grammar, and a second
     *  one that walked it without the wire projection would emit references a consumer
     *  could not read the same way. */
    private static final class NodeCollector extends SignatureVisitor {
        private final Consumer<Node> onDone;
        private String owner;
        private final List<String> arguments = new ArrayList<>();

        NodeCollector(Consumer<Node> onDone) {
            super(org.objectweb.asm.Opcodes.ASM9);
            this.onDone = onDone;
        }

        @Override public void visitBaseType(char descriptor) {
            Type type = Type.getType(String.valueOf(descriptor));
            onDone.accept(new Node(descriptorName(type), List.of(), false,
                WireTypes.of(type), WireTypes.format(type)));
        }

        // Not a real class — recorded by the name the signature itself gives it, never
        // resolved to its bound (resolution is not this task's job). Any instantiation of
        // a type variable is still a reference in Java, so the nullability rule holds.
        @Override public void visitTypeVariable(String name) {
            onDone.accept(new Node(name, List.of(), true, "object", ""));
        }

        // The signature half of {@link #elementArguments}: the element is already a fully
        // built node here, so it is kept as the array's single argument rather than
        // surviving only as the `[]` suffix on the symbol.
        @Override public SignatureVisitor visitArrayType() {
            return new NodeCollector(element -> onDone.accept(
                new Node(element.symbol() + "[]", List.of(toJson(element)), true, "array", "")));
        }

        @Override public void visitClassType(String name) {
            if (owner == null) owner = name;
        }

        @Override public void visitInnerClassType(String name) {
            if (owner != null) owner = owner + "$" + name;
        }

        // The wildcard kind (`+`/`-`/`=`) has no field on D00 §5a's type reference — only
        // the bound is recorded, exactly as the signature states it. Resolving variance is
        // not this task's job any more than resolving a type variable's bound is.
        @Override public SignatureVisitor visitTypeArgument(char wildcard) {
            return new NodeCollector(node -> arguments.add(toJson(node)));
        }

        // An unbounded wildcard (`?`) has no bound to recurse into — recorded rather than
        // silently dropped from the argument list.
        @Override public void visitTypeArgument() {
            arguments.add(toJson(new Node("?", List.of(), true, "object", "")));
        }

        @Override public void visitEnd() {
            if (owner == null) return;
            Type type = Type.getObjectType(owner);
            onDone.accept(new Node(owner + "#", arguments, true, WireTypes.of(type), WireTypes.format(type)));
        }
    }
}
