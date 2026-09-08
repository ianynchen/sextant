package dev.sextant.extractor;

/** W7's shapes where a FLAG or a CALLBACK COUNT says one thing and the class file
 *  states another. Each is a case the first version of `constructKindOf` got wrong. */
final class ConstructKindSample {
    private ConstructKindSample() {}
}

/** A record with NO components. `visitRecordComponent` fires once per component, so
 *  it never fires here — while the `Record` attribute is present and
 *  `Class.isRecord()` returns true. Measured: 16 such classes in the local dependency
 *  cache, in Hibernate and Spring Boot, and a marker record is the shape a sealed
 *  hierarchy uses most. */
record EmptyRecord() {}

/** An enum whose constants have BODIES. javac compiles each into an anonymous class
 *  carrying `ACC_ENUM`, whose superclass is the enum rather than `java/lang/Enum` —
 *  and `Class.isEnum()` refuses to call those enums for that reason. Measured: 5,895
 *  such classes against 16,563 real enum types across the cached jars. */
enum ConstantsWithBodies {
    FIRST {
        @Override
        String label() {
            return "first";
        }
    },
    SECOND {
        @Override
        String label() {
            return "second";
        }
    };

    abstract String label();
}

/** `@Deprecated` on a TYPE and on a FIELD, neither of which was asserted anywhere —
 *  deleting both writers left the whole suite green. */
@Deprecated
class DeprecatedType {
    @Deprecated int obsolete = 1;

    int current = 2;
}
