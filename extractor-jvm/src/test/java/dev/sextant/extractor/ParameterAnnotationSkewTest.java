package dev.sextant.extractor;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.InputStream;
import java.util.List;
import org.junit.jupiter.api.Test;

/**
 * JVMS 4.7.18: the parameter-annotation table may be SHORTER than the
 * descriptor's parameter list, because javac omits synthesised leading
 * parameters — the outer instance on an inner class, and `$enum$name` /
 * `$enum$ordinal` on an enum. Entries align from the END, not from zero.
 *
 * <p>Measured on the fixture: the constructor's descriptor carries four
 * parameters (String, int, String, int) while `RuntimeVisibleParameterAnnotations`
 * declares two, so the annotation at attribute index 0 belongs to descriptor
 * index 2. Indexing from zero put it on `$enum$name`.
 *
 * <p>An ENUM rather than only an inner class, deliberately: the hidden first
 * parameter here is also a `String`, so the misalignment is invisible to every
 * check except one that knows about 4.7.18. On an inner class the hidden
 * parameter is the outer instance and a consumer could notice the type is
 * wrong; that is the easy case, and it is not the one that ships silently.
 */
class ParameterAnnotationSkewTest {

    private List<String> scan(String simpleName) throws Exception {
        try (InputStream in =
                getClass().getResourceAsStream("/dev/sextant/extractor/" + simpleName + ".class")) {
            return new ClassScanner("com.acme/orders", "1.0.0")
                .scan(in.readAllBytes(), "doc-" + simpleName);
        }
    }

    private static String constructorSymbol(List<String> lines) {
        return lines.stream()
            .filter(line -> line.contains("\"construct_kind\":\"constructor\""))
            .findFirst()
            .orElseThrow(() -> new AssertionError("no constructor symbol emitted"));
    }

    @Test
    void an_enum_constructors_annotation_lands_on_the_parameter_that_declares_it()
            throws Exception {
        String constructor = constructorSymbol(scan("EnumConstructorAnnotated"));

        // The descriptor's own four parameters, synthesised ones included: the
        // signature describes the METHOD as the JVM sees it.
        int parameters = constructor.split("\"annotations\":", -1).length - 1;
        assertEquals(4, parameters, "expected the descriptor's four parameters");

        // `@Labelled` belongs to `display`, the THIRD descriptor parameter.
        // Before the fix it sat on the first, which is `$enum$name` — also a
        // String, which is why no downstream type check could catch it.
        int labelled = constructor.indexOf("Labelled");
        assertTrue(labelled > 0, "the annotation was dropped entirely");
        String beforeLabelled = constructor.substring(0, labelled);
        int parameterOfLabelled = beforeLabelled.split("\"annotations\":", -1).length - 2;
        assertEquals(
            2,
            parameterOfLabelled,
            "the annotation is on parameter " + parameterOfLabelled
                + "; `display` is descriptor parameter 2 and parameter 0 is $enum$name");
    }

    /** The index of the parameter carrying the first annotation, counted the way
     *  the emitted signature orders them. */
    private static int annotatedParameter(String constructorSymbol) {
        int labelled = constructorSymbol.indexOf("Labelled");
        assertTrue(labelled > 0, "the annotation was dropped entirely");
        return constructorSymbol.substring(0, labelled).split("\"annotations\":", -1).length - 2;
    }

    @Test
    void a_top_level_constructor_is_unmoved_because_nothing_was_synthesised()
            throws Exception {
        // Shift 0. A fix that aligned from the end UNCONDITIONALLY would break
        // every ordinary constructor, so this is the arm that says it does not.
        assertEquals(
            0, annotatedParameter(constructorSymbol(scan("ConstructorAnnotationShapes$TopLevel"))));
    }

    @Test
    void an_inner_class_constructor_shifts_by_its_hidden_outer_instance() throws Exception {
        // Shift 1. The easy case: the hidden parameter is the outer instance, so
        // its type differs and a consumer could in principle notice. It is here
        // because the shift is not a constant — 0, 1 and 2 all occur, and a fix
        // that hardcoded any one of them would pass one of these three tests.
        assertEquals(
            1, annotatedParameter(constructorSymbol(scan("ConstructorAnnotationShapes$Inner"))));
    }
}
