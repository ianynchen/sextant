package probe;

import jakarta.ws.rs.*;

public class Resources {
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
}
