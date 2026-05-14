package com.mcctp.action.handlers;

import com.google.gson.JsonObject;
import com.mcctp.action.ActionHandler;
import net.minecraft.client.MinecraftClient;

public class CloseScreenHandler implements ActionHandler {
    @Override
    public void handle(JsonObject params) {
        MinecraftClient client = MinecraftClient.getInstance();
        if (client.player == null) return;

        if (client.currentScreen != null) {
            client.currentScreen.close();
        }
    }
}
