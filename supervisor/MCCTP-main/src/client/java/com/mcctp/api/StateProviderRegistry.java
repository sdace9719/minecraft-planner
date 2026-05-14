package com.mcctp.api;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class StateProviderRegistry {
    private static final List<StateProvider> providers = new ArrayList<>();

    public static void register(StateProvider provider) {
        providers.add(provider);
    }

    public static List<StateProvider> getProviders() {
        return Collections.unmodifiableList(providers);
    }
}
