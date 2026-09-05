package probe;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.actuate.endpoint.annotation.DeleteOperation;
import org.springframework.boot.actuate.endpoint.annotation.Endpoint;
import org.springframework.boot.actuate.endpoint.annotation.ReadOperation;
import org.springframework.boot.actuate.endpoint.annotation.WriteOperation;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.stereotype.Component;

@SpringBootApplication
public class ProbeApplication {

    public static void main(String[] args) {
        SpringApplication.run(ProbeApplication.class, args);
    }

    /** Rows 1-4: id -> path, and one operation annotation per HTTP verb. */
    @Component
    @Endpoint(id = "probe")
    public static class ProbeEndpoint {
        @ReadOperation
        public String read() { return "read"; }

        @WriteOperation
        public String write() { return "write"; }

        @DeleteOperation
        public String delete() { return "delete"; }
    }

    /** Row 6: an @Endpoint class carrying no operation annotation at all. */
    @Component
    @Endpoint(id = "empty")
    public static class EmptyEndpoint {
        public String notAnOperation() { return "not served"; }
    }
}
