package com.acme.orders.data;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.repository.MongoRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;

/** A Spring Data REST resource over MongoDB rather than JPA — the same annotation, the
 *  same exposed route table, a different store. Spring Data REST is store-neutral by
 *  design and MongoDB is one of its headline guides. */
@RepositoryRestResource(path = "shipments")
public interface ShipmentRepository extends MongoRepository<ShipmentRepository.Shipment, String> {

    @Document("shipments")
    class Shipment {
        @Id
        public String id;
        public String orderId;
    }
}
