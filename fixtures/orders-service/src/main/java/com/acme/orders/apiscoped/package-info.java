// `@NonNullApi` ALONE, which is the half `com.acme.orders.springscoped` cannot
// exercise because it declares both. Spring scopes the two separately and means
// different things by them: `@NonNullApi` covers parameters and return values,
// `@NonNullFields` covers fields. Measured over 1,672 cached jars, 197 packages
// declare this one on its own — spring-data-mongodb (28), spring-data-repository
// (14), the MongoDB driver (10), spring-hateoas (9) — and while it was listed as
// a field scope every field in all of them read `nullable: false` at
// `resolution: resolved` on the strength of an annotation about parameters.
@org.springframework.lang.NonNullApi
package com.acme.orders.apiscoped;
