package probe;

import io.vertx.core.Future;
import io.vertx.core.Vertx;
import io.vertx.core.buffer.Buffer;
import io.vertx.core.http.HttpMethod;
import io.vertx.ext.web.Route;
import io.vertx.ext.web.Router;
import io.vertx.ext.web.RoutingContext;
import io.vertx.ext.web.client.HttpRequest;
import io.vertx.ext.web.client.WebClient;
import io.vertx.ext.web.client.WebClientOptions;
import io.vertx.ext.web.codec.BodyCodec;
import io.vertx.ext.web.impl.RouterImpl;

/** Call shapes whose compiled form CP-56 reads. One method per shape, so a probe can read one body. */
public class Shapes {

  void handle(RoutingContext ctx) {
    ctx.response().end("h");
  }

  void routeMethodReference(Router router) {
    router.get("/x").handler(this::handle);
  }

  void routeLambda(Router router) {
    router.get("/x").handler(ctx -> ctx.response().end("a"));
  }

  void routeRespond(Router router) {
    router.get("/x").respond(ctx -> Future.succeededFuture("a"));
  }

  void routeStatementStyle(Router router) {
    Route route = router.route("/orders/:id");
    route.method(HttpMethod.GET);
    route.handler(this::handle);
  }

  void routeVerbArgument(Router router) {
    router.route(HttpMethod.POST, "/orders").handler(this::handle);
  }

  void routeNoVerbNoPath(Router router) {
    router.route().handler(ctx -> ctx.next());
  }

  void routeRegex(Router router) {
    router.getWithRegex("/r/.+").handler(this::handle);
  }

  Router directRouter(Vertx vertx) {
    return new RouterImpl(vertx);
  }

  Router factoryRouter(Vertx vertx) {
    return Router.router(vertx);
  }

  void subRouterMount(Router router, Router sub) {
    router.route("/api/*").subRouter(sub);
  }

  void clientExplicitAddress(WebClient client) {
    client.get(8080, "h", "/p").send();
  }

  void clientHostAndUri(WebClient client) {
    client.get("h", "/p").send();
  }

  void clientUriOnly(WebClient client) {
    client.get("/p").send();
  }

  void clientAbsolute(WebClient client) {
    client.getAbs("http://h:8080/p").send();
  }

  void clientChain(WebClient client) {
    client
        .post("/q")
        .addQueryParam("a", "b")
        .timeout(1000)
        .basicAuthentication("u", "p")
        .as(BodyCodec.jsonObject())
        .send();
  }

  void clientStatementStyle(WebClient client) {
    HttpRequest<Buffer> request = client.post("/q");
    request.addQueryParam("a", "b");
    request.timeout(1000);
    request.send();
  }

  WebClient clientWithDefaults(Vertx vertx) {
    return WebClient.create(vertx, new WebClientOptions().setDefaultHost("h").setDefaultPort(9));
  }
}
