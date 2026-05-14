package com.mcctp.action.handlers;

import com.google.gson.JsonObject;
import com.mcctp.MCCTPMod;
import com.mcctp.action.ActionHandler;
import net.minecraft.client.MinecraftClient;

public class SendChatHandler implements ActionHandler {
    @Override
    public void handle(JsonObject params) {
        MinecraftClient client = MinecraftClient.getInstance();
        if (client.player == null || client.player.networkHandler == null) return;

        if (!params.has("message")) {
            MCCTPMod.LOGGER.warn("send_chat requires a 'message' parameter");
            return;
        }

        String message = params.get("message").getAsString();
        if (message.isEmpty()) return;

        if (message.startsWith("/")) {
            client.player.networkHandler.sendChatCommand(message.substring(1));
        } else {
            client.player.networkHandler.sendChatMessage(message);
        }
    }
}
