package com.acme.app;

import com.acme.network.CoreNetworkModule;
import com.acme.network.NetworkEdgeModule;
import dagger.Component;

/** Two components: each takes the core recipe from the sibling and one of the two edge recipes. */
final class Components {
    private Components() {}

    @Component(modules = {CoreNetworkModule.class, LocalEdgeModule.class, ApiModule.class})
    interface LocalComponent {
        CoreApi core();

        EdgeApi edge();
    }

    @Component(modules = {CoreNetworkModule.class, NetworkEdgeModule.class, ApiModule.class})
    interface NetworkComponent {
        CoreApi core();

        EdgeApi edge();
    }
}
