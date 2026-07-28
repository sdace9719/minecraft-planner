package com.botinterface;

import net.fabricmc.api.ClientModInitializer;
import net.fabricmc.fabric.api.client.event.lifecycle.v1.ClientTickEvents;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class BotInterfaceMod implements ClientModInitializer {
    public static final String MOD_ID = "botinterface";
    public static final Logger LOGGER = LoggerFactory.getLogger(MOD_ID);

    @Override
    public void onInitializeClient() {
        LOGGER.info("BotInterface initialized");
        ClientTickEvents.END_CLIENT_TICK.register(BackgroundSwapHandler::processTick);
        LOGGER.info("BotInterface: registered tick-based swap handler");
    }
}
