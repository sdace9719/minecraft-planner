package com.controlbridge;

import net.fabricmc.api.ClientModInitializer;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class ControlBridgeMod implements ClientModInitializer {
    public static final String MOD_ID = "controlbridge";
    public static final Logger LOGGER = LoggerFactory.getLogger(MOD_ID);
    private BridgeHttpServer server;

    @Override
    public void onInitializeClient() {
        LOGGER.info("ControlBridge initializing");
        ConfigManager config = new ConfigManager();
        config.load();
        int port = config.getPort();
        server = new BridgeHttpServer(port);
        server.start();
        LOGGER.info("ControlBridge HTTP server started on port {}", port);
    }
}
