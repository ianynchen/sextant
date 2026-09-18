package com.acme.quarkus;

import org.jboss.resteasy.reactive.RestForm;

// A parameter CONTAINER: no annotation on the class, bound fields inside. Quarkus's
// ResteasyReactiveParameterContainerScanner makes any parameter of this type a set of
// form values, never the body.
public class Upload {
    @RestForm public String description;
    @RestForm public String fileName;
}
