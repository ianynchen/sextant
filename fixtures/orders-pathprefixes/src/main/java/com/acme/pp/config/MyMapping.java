package com.acme.pp.config;

import org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerMapping;

/** A SUBCLASS of the framework's mapping — ordinary Spring customisation. javac emits
 *  `invokevirtual MyMapping.setPathPrefixes`, so a gate matching the framework class exactly
 *  reads a module that installs prefixes this way as installing none. */
public class MyMapping extends RequestMappingHandlerMapping {
}
