package com.recipecraft;

import net.fabricmc.api.ClientModInitializer;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class RecipeCraftMod implements ClientModInitializer {
    public static final String MOD_ID = "recipecraft";
    public static final Logger LOGGER = LoggerFactory.getLogger(MOD_ID);

    @Override
    public void onInitializeClient() {
        LOGGER.info("RecipeCraft initializing");
        ChatInterceptor.register();
        RecipeCrafter.register();
        LOGGER.info("RecipeCraft ready — use !craft <item> [count] in chat to craft");
    }
}
