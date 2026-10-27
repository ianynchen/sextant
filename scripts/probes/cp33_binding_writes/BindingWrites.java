package probe;

import jakarta.annotation.PostConstruct;

/** CP-33: every shape capability 9.19 would have to read, and the ones it must refuse. */
public class BindingWrites {

    private String viaSetter;
    private String viaPostConstruct;
    private String viaComputed;
    private String readAfterWrite;
    private String viaCallResult;
    private String viaFieldInit = "field-init-value";
    private static String viaStaticInit;
    private static String viaMerged;

    static { viaStaticInit = "static-init-value"; }

    /** 1. The setter — the shape `field_write` already reads, outside `<init>`. */
    public void setViaSetter(String value) { this.viaSetter = value; }

    /** 2. @PostConstruct assigning a LITERAL, not a parameter. */
    @PostConstruct
    public void init() { this.viaPostConstruct = "post-construct-literal"; }

    /** 3. A computed assignment — must emit nothing. */
    public void setComputed(String a, String b) { this.viaComputed = a + b; }

    /** 4. A method that writes the field and then reads it back. */
    public void writeThenRead(String value) {
        this.readAfterWrite = value;
        System.out.println(this.readAfterWrite);
    }

    /** 5. Two parameters, the SECOND assigned — does the slot mapping hold outside `<init>`? */
    public void setSecond(long wide, String value) { this.viaSetter = value; }

    /** 7. A field assigned another CALL'S RESULT, not a parameter and not a constant.
     *  This is the `ActorRef ref = system.actorOf(props, "worker")` shape, and it is
     *  what decides whether capability 9.19 would reach `akka-pekko-actors` at all. */
    public void setFromCall(java.util.List<String> source) { this.viaCallResult = source.get(0); }

    /** 9. A value two branches MERGE at the write: each branch ends with its own constant, and
     *  the instruction right below the write is only the last branch's. */
    public static void setMerged(boolean prod) { viaMerged = prod ? "prod-value" : "staging-value"; }
}
