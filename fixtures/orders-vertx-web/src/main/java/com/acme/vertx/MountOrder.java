package com.acme.vertx;

import io.vertx.core.Vertx;
import io.vertx.ext.web.Router;
import io.vertx.ext.web.RoutingContext;

/**
 * A mounted router is served from its parent: its routes compete with the parent's own, at the
 * mount route's place among them. One verb and path on the parent and on a router it mounts is
 * one request, answered by whichever of the parent route and the mount route is tried first.
 */
public class MountOrder {

    /** The parent's own route first, then the mount: the parent answers. */
    public void parentFirst(Vertx vertx) {
        Router parent = Router.router(vertx);
        Router sub = Router.router(vertx);
        sub.get("/x").handler(this::subOfParentFirst);
        parent.get("/mount-order/parent-first/x").handler(this::parentFirstOwn);
        parent.route("/mount-order/parent-first/*").subRouter(sub);
    }

    /** The mount first, then the parent's own route: the mounted router answers. */
    public void mountFirst(Vertx vertx) {
        Router parent = Router.router(vertx);
        Router sub = Router.router(vertx);
        sub.get("/x").handler(this::subOfMountFirst);
        parent.route("/mount-order/mount-first/*").subRouter(sub);
        parent.get("/mount-order/mount-first/x").handler(this::mountFirstOwn);
    }

    /** Both given an order, the mount's the lower, registered after the parent's own route. */
    public void mountOrdered(Vertx vertx) {
        Router parent = Router.router(vertx);
        Router sub = Router.router(vertx);
        sub.get("/x").handler(this::subOfOrdered);
        parent.get("/mount-order/ordered/x").order(5).handler(this::orderedOwn);
        parent.route("/mount-order/ordered/*").order(1).subRouter(sub);
    }

    /** Two levels of mount, the parent's own route last: the innermost router answers. */
    public void nested(Vertx vertx) {
        Router parent = Router.router(vertx);
        Router middle = Router.router(vertx);
        Router inner = Router.router(vertx);
        inner.get("/x").handler(this::innerOfNested);
        middle.route("/inner/*").subRouter(inner);
        parent.route("/mount-order/nested/*").subRouter(middle);
        parent.get("/mount-order/nested/inner/x").handler(this::nestedOwn);
    }

    /** The parent's own route and the mount made in two methods: no order the code states. */
    public void twoMethods(Vertx vertx) {
        Router parent = Router.router(vertx);
        own(parent);
        mount(vertx, parent);
    }

    private void own(Router parent) {
        parent.get("/mount-order/two-methods/x").handler(this::twoMethodsOwn);
    }

    private void mount(Vertx vertx, Router parent) {
        Router sub = Router.router(vertx);
        sub.get("/x").handler(this::subOfTwoMethods);
        parent.route("/mount-order/two-methods/*").subRouter(sub);
    }

    /** A route on one router and a mount on another, unrelated: each is its router's answer. */
    public void unrelated(Vertx vertx) {
        Router one = Router.router(vertx);
        Router other = Router.router(vertx);
        Router sub = Router.router(vertx);
        sub.get("/x").handler(this::subOfUnrelated);
        other.route("/mount-order/unrelated/*").subRouter(sub);
        one.get("/mount-order/unrelated/x").handler(this::unrelatedOwn);
    }

    private void subOfParentFirst(RoutingContext ctx) {
        ctx.response().end("sub");
    }

    private void parentFirstOwn(RoutingContext ctx) {
        ctx.response().end("parent");
    }

    private void subOfMountFirst(RoutingContext ctx) {
        ctx.response().end("sub");
    }

    private void mountFirstOwn(RoutingContext ctx) {
        ctx.response().end("parent");
    }

    private void subOfOrdered(RoutingContext ctx) {
        ctx.response().end("sub");
    }

    private void orderedOwn(RoutingContext ctx) {
        ctx.response().end("parent");
    }

    private void innerOfNested(RoutingContext ctx) {
        ctx.response().end("inner");
    }

    private void nestedOwn(RoutingContext ctx) {
        ctx.response().end("parent");
    }

    private void twoMethodsOwn(RoutingContext ctx) {
        ctx.response().end("parent");
    }

    private void subOfTwoMethods(RoutingContext ctx) {
        ctx.response().end("sub");
    }

    private void subOfUnrelated(RoutingContext ctx) {
        ctx.response().end("sub");
    }

    private void unrelatedOwn(RoutingContext ctx) {
        ctx.response().end("parent");
    }
}
