package com.example.orders.graphql;

import com.acme.orders.contracts.OrderView;
import org.springframework.graphql.data.method.annotation.SchemaMapping;
import org.springframework.stereotype.Controller;

// The class-level-typeName resolver shape (2H design §1): every method here
// resolves a field of `Customer`, and the type is stated once on the class
// rather than repeated on each method.
@Controller
@SchemaMapping(typeName = "Customer")
public class CustomerGraphqlController {

    // Neither half spelled on the method: the scope comes from the class-level
    // annotation, the field name from the method — `Customer.nickname`.
    @SchemaMapping
    public String nickname(OrderView order) { return null; }

    // The method's own typeName WINS over the class-level one, which is
    // Spring's own precedence — the nearer declaration is the more specific.
    @SchemaMapping(typeName = "Order", field = "shipTo")
    public String shipTo(OrderView order) { return null; }
}
