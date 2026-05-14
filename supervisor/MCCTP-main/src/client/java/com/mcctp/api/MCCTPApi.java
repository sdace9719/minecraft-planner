package com.mcctp.api;

import com.mcctp.action.ActionDispatcher;
import com.mcctp.network.ConnectionManager;

import java.util.Collections;
import java.util.LinkedHashSet;
import java.util.Set;

public class MCCTPApi {
    private static ConnectionManager connectionManager;
    private static ActionDispatcher actionDispatcher;
    private static final Set<String> loadedModules = new LinkedHashSet<>();
    private static int tickInterval = 1;

    public static void init(ConnectionManager cm, ActionDispatcher ad) {
        connectionManager = cm;
        actionDispatcher = ad;
    }

    public static ConnectionManager getConnectionManager() {
        return connectionManager;
    }

    public static ActionDispatcher getActionDispatcher() {
        return actionDispatcher;
    }

    public static void registerModule(String name) {
        loadedModules.add(name);
    }

    public static Set<String> getLoadedModules() {
        return Collections.unmodifiableSet(loadedModules);
    }

    public static void setTickInterval(int interval) {
        tickInterval = Math.max(1, interval);
    }

    public static int getTickInterval() {
        return tickInterval;
    }
}
