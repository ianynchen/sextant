package probe;

import jakarta.ws.rs.*;
import org.glassfish.jersey.server.ResourceConfig;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.stereotype.Component;

@SpringBootApplication
public class App {
  public static void main(String[] a) { SpringApplication.run(App.class, a); }

  // no @Path: not a resource itself
  public abstract static class CrudResource {
    @GET @Path("/list") public String list() { return "list"; }
    @POST public String create() { return "create"; }
  }

  @Path("/orders")
  public static class OrderResource extends CrudResource {}

  @Path("/products")
  public static class ProductResource extends CrudResource {
    @Override @GET @Path("/all") public String list() { return "all"; }
  }

  @Path("/base")
  public static class BaseResource {
    @GET @Path("/list") public String list() { return "list"; }
    @POST public String create() { return "create"; }
  }

  @Path("/sub")
  public static class SubResource extends BaseResource {}

  @Component
  public static class Config extends ResourceConfig {
    public Config() {
      register(OrderResource.class); register(ProductResource.class);
      register(BaseResource.class); register(SubResource.class);
    }
  }
}
