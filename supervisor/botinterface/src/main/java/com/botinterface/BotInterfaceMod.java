package com.botinterface;

import net.fabricmc.api.ClientModInitializer;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class BotInterfaceMod implements ClientModInitializer {
    public static final String MOD_ID = "botinterface";
    public static final Logger LOGGER = LoggerFactory.getLogger(MOD_ID);

    @Override
    public void onInitializeClient() {
        LOGGER.info("BotInterface initialized");
    }
}
