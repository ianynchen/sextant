package probe;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.*;

@SpringBootApplication
public class App {
  public static void main(String[] a) { SpringApplication.run(App.class, a); }

  // not a bean: abstract, no stereotype
  public abstract static class CrudController {
    @GetMapping("/list") public String list() { return "list"; }
    @PostMapping("") public String create() { return "create"; }
  }

  @RestController @RequestMapping("/orders")
  public static class OrderController extends CrudController {}

  @RestController @RequestMapping("/products")
  public static class ProductController extends CrudController {
    @Override @GetMapping("/all") public String list() { return "all"; }
  }

  @RestController @RequestMapping("/base")
  public static class BaseController {
    @GetMapping("/list") public String list() { return "list"; }
    @PostMapping("") public String create() { return "create"; }
  }

  @RestController @RequestMapping("/sub")
  public static class SubController extends BaseController {}
}
