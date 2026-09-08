// The SAME rule as `com.acme.orders.scoped`, in Spring's own spelling — which is
// what a Spring codebase actually writes, and what `shape-models/json.yml` did not
// declare until OI-48. Measured on spring-web 6.1.6: 58 package-info classes, every
// one carrying both of these.
@org.springframework.lang.NonNullApi
@org.springframework.lang.NonNullFields
package com.acme.orders.springscoped;
