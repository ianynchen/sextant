package probe;

import io.micronaut.http.annotation.*;
import io.micronaut.runtime.Micronaut;

public class App {
  public static void main(String[] a) { Micronaut.run(App.class, a); }

  // no @Controller: not a controller itself
  public abstract static class CrudController {
    @Get("/list") public String list() { return "list"; }
    @Post public String create() { return "create"; }
  }

  @Controller("/orders")
  public static class OrderController extends CrudController {}

  @Controller("/products")
  public static class ProductController extends CrudController {
    @Override @Get("/all") public String list() { return "all"; }
  }

  @Controller("/base")
  public static class BaseController {
    @Get("/list") public String list() { return "list"; }
    @Post public String create() { return "create"; }
  }

  @Controller("/sub")
  public static class SubController extends BaseController {}
}
