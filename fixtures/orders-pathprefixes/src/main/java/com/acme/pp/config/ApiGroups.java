package com.acme.pp.config;

/**
 * `ruoyi`'s `WebProperties` reduced to its shape: two API groups, each holding a prefix and
 * the controller packages it covers, both constructed in field initialisers.
 *
 * <p>The walk reaches a group's two strings through the sixth edge — a getter returns a field
 * read, the field read follows the constructor that wrote it, and the constructor's parameter
 * follows its callers to the two `new Api(…)` sites here. It has no instance identity, so it
 * answers BOTH prefixes and BOTH patterns for one site; what keeps `/internal-api` away from
 * the ops pattern is that the two answers must come down the same path.
 */
public class ApiGroups {

    public static final class Api {

        private final String prefix;
        private final String controller;

        Api(String prefix, String controller) {
            this.prefix = prefix;
            this.controller = controller;
        }

        public String getPrefix() {
            return prefix;
        }

        public String getController() {
            return controller;
        }
    }

    private final Api internalApi = new Api("/internal-api", "**.controller.internal.**");
    private final Api opsApi = new Api("/ops-api", "**.controller.ops.**");

    public Api getInternalApi() {
        return internalApi;
    }

    public Api getOpsApi() {
        return opsApi;
    }
}
