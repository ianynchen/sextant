package com.acme.pp.config;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.function.Predicate;
import org.springframework.util.AntPathMatcher;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerMapping;

/**
 * `ruoyi`'s wiring, reduced to what the mechanism needs: a prefix per controller package,
 * installed through Spring's own API.
 *
 * <p>It declares four prefixes TWO ways, because the two differ in what the reader has to
 * get right:
 *
 * <ul>
 *   <li>`/admin-api` and `/app-api` inline, one `put` site each, from string constants. This
 *       is the declaration at its plainest — the reading is all that is tested.
 *   <li>`/internal-api` and `/ops-api` through `putPathPrefix`, which is `ruoyi`'s own shape:
 *       ONE `put` site, called once per group, with the prefix and the pattern both read off
 *       an `ApiGroups.Api` object. The walk answers both prefixes and both patterns there, so
 *       a reader that paired them by SITE would cross them.
 * </ul>
 *
 * <p>Beside them are the three shapes a reader must NOT publish a prefix for, each with its
 * own controller asserting the path it keeps: a map of the same shape that is never installed
 * (`auditCategories`), a prefix that is an unresolved placeholder (`${api.ext-prefix}`), and
 * a class in a prefixed package that is not a `@RestController` at all
 * (`controller/admin/RouterConfig`).
 */
public class PrefixConfig {

    private static final String ADMIN_PREFIX = "/admin-api";
    private static final String APP_PREFIX = "/app-api";
    private static final String EXT_PREFIX = "${api.ext-prefix}";
    private static final String ADMIN_PACKAGES = "**.controller.admin.**";
    private static final String APP_PACKAGES = "**.controller.app.**";
    private static final String EXT_PACKAGES = "**.controller.ext.**";
    private static final String AUDIT_PACKAGES = "**.controller.audit.**";

    public RequestMappingHandlerMapping mapping() {
        RequestMappingHandlerMapping mapping = new RequestMappingHandlerMapping();
        // A `LinkedHashMap`-TYPED variable, deliberately: javac then emits
        // `invokevirtual java/util/LinkedHashMap.put`, and a reader requiring `Map#put`
        // reads this module as declaring nothing. What identifies an entry is the MAP it
        // writes into, never the static type the author happened to declare.
        LinkedHashMap<String, Predicate<Class<?>>> prefixes = new LinkedHashMap<>();
        AntPathMatcher matcher = new AntPathMatcher(".");
        prefixes.put(ADMIN_PREFIX, clazz -> clazz.isAnnotationPresent(RestController.class)
                && matcher.match(ADMIN_PACKAGES, clazz.getPackage().getName()));
        prefixes.put(APP_PREFIX, clazz -> clazz.isAnnotationPresent(RestController.class)
                && matcher.match(APP_PACKAGES, clazz.getPackage().getName()));
        // A prefix nobody has resolved. Spring passes the key through its embedded value
        // resolver first; `…controller.ext` must therefore publish NO prefix rather than a
        // literal `${api.ext-prefix}`.
        prefixes.put(EXT_PREFIX, clazz -> clazz.isAnnotationPresent(RestController.class)
                && matcher.match(EXT_PACKAGES, clazz.getPackage().getName()));
        mapping.setPathPrefixes(prefixes);
        return mapping;
    }

    /**
     * The same declaration on a SUBCLASS of the mapping, which is ordinary Spring
     * customisation — and `ruoyi`'s one-`put`-site shape, so the two prefixes here are the
     * ones whose pairing is a real question.
     */
    public MyMapping customMapping() {
        MyMapping mapping = new MyMapping();
        Map<String, Predicate<Class<?>>> prefixes = new LinkedHashMap<>();
        AntPathMatcher matcher = new AntPathMatcher(".");
        ApiGroups groups = new ApiGroups();
        putPathPrefix(prefixes, groups.getInternalApi(), matcher);
        putPathPrefix(prefixes, groups.getOpsApi(), matcher);
        mapping.setPathPrefixes(prefixes);
        return mapping;
    }

    /**
     * **A map of exactly the prefix-declaration shape that is handed to nobody.** Every
     * test a prefix entry passes, this passes too — a string key, a lambda, a package match
     * — except the one that matters: the map never reaches `setPathPrefixes`. A reader
     * gated only on "the module installs prefixes somewhere" published
     * `/AUDIT/audit-logs/{id}`.
     */
    public Map<String, Predicate<Class<?>>> auditCategories() {
        Map<String, Predicate<Class<?>>> categories = new LinkedHashMap<>();
        AntPathMatcher matcher = new AntPathMatcher(".");
        categories.put("AUDIT", clazz -> clazz.isAnnotationPresent(RestController.class)
                && matcher.match(AUDIT_PACKAGES, clazz.getPackage().getName()));
        return categories;
    }

    /** One `put` site for every group — `ruoyi`'s `YudaoWebAutoConfiguration.putPathPrefix`,
     *  line for line except for the null check it does first. */
    private void putPathPrefix(
            Map<String, Predicate<Class<?>>> prefixes, ApiGroups.Api api, AntPathMatcher matcher) {
        prefixes.put(api.getPrefix(), clazz -> clazz.isAnnotationPresent(RestController.class)
                && matcher.match(api.getController(), clazz.getPackage().getName()));
    }
}
