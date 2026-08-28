package dev.sextant.extractor;

import java.util.ArrayList;
import java.util.List;
import java.util.TreeMap;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassVisitor;
import org.objectweb.asm.MethodVisitor;
import org.objectweb.asm.Opcodes;
import org.objectweb.asm.Type;

/** Reads one class file and emits symbol facts as JSONL lines. */
public final class ClassScanner {
    private final String coordinates;
    private final String version;

    public ClassScanner(String coordinates, String version) {
        this.coordinates = coordinates;
        this.version = version;
    }

    public List<String> scan(byte[] classBytes, String documentId) {
        List<String> lines = new ArrayList<>();
        new ClassReader(classBytes).accept(new Visitor(lines, documentId), ClassReader.SKIP_FRAMES);
        return lines;
    }

    String symbolOf(String descriptorPath) {
        return "sextant-jvm maven " + coordinates + " " + version + " " + descriptorPath;
    }

    private final class Visitor extends ClassVisitor {
        private final List<String> lines;
        private final String documentId;
        private String typeSymbol;

        Visitor(List<String> lines, String documentId) {
            super(Opcodes.ASM9);
            this.lines = lines;
            this.documentId = documentId;
        }

        @Override
        public void visit(int v, int access, String name, String sig, String superName, String[] ifaces) {
            typeSymbol = symbolOf(name + "#");
            boolean isInterface = (access & Opcodes.ACC_INTERFACE) != 0;
            emit(typeSymbol, isInterface ? "interface" : "class", null, null, access);
        }

        @Override
        public MethodVisitor visitMethod(int access, String name, String descriptor, String sig, String[] ex) {
            String owner = typeSymbol.substring(typeSymbol.lastIndexOf(' ') + 1);
            String methodSymbol = symbolOf(owner + name + "().");
            emit(methodSymbol, "<init>".equals(name) ? "constructor" : "method",
                 typeSymbol, signatureJson(descriptor, sig), access);
            return null;
        }

        private String signatureJson(String descriptor, String genericSignature) {
            List<String> parameters = new ArrayList<>();
            for (Type argument : Type.getArgumentTypes(descriptor)) {
                TreeMap<String, String> parameter = new TreeMap<>();
                parameter.put("annotations", "[]");
                parameter.put("name", "null");
                parameter.put("type", TypeRefs.fromType(argument));
                parameters.add(JsonOut.object(parameter));
            }
            String generic = TypeRefs.returnFromSignature(genericSignature);
            String returns = generic != null ? generic : TypeRefs.fromType(Type.getReturnType(descriptor));
            TreeMap<String, String> signature = new TreeMap<>();
            signature.put("parameters", JsonOut.array(parameters));
            signature.put("returns", returns);
            return JsonOut.object(signature);
        }

        private void emit(String symbol, String constructKind, String enclosing, String signature, int access) {
            TreeMap<String, String> fact = new TreeMap<>();
            fact.put("kind", JsonOut.string("symbol"));
            fact.put("document_id", JsonOut.string(documentId));
            fact.put("symbol", JsonOut.string(symbol));
            fact.put("construct_kind", JsonOut.string(constructKind));
            fact.put("enclosing", enclosing == null ? "null" : JsonOut.string(enclosing));
            fact.put("signature", signature == null ? "null" : signature);
            fact.put("visibility", JsonOut.string((access & Opcodes.ACC_PUBLIC) != 0 ? "public" : "other"));
            fact.put("line_start", "0");
            fact.put("line_end", "0");
            lines.add(JsonOut.object(fact));
        }
    }
}
