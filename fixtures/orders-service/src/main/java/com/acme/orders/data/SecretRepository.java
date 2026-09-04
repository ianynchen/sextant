package com.acme.orders.data;

import org.springframework.data.repository.CrudRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;

import com.acme.orders.contracts.OrderRequest;

/** The other half of the same rule: `exported = false` removes the repository
 *  from the API entirely — every route of it answers 404, including the
 *  collection — so nothing here may derive. */
@RepositoryRestResource(exported = false)
public interface SecretRepository extends CrudRepository<OrderRequest, Long> {
}
