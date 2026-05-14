package com.mcctp.action.handlers;

import com.google.gson.JsonObject;
import com.mcctp.action.ActionHandler;
import net.minecraft.client.MinecraftClient;

public class DropItemHandler implements ActionHandler {
    @Override
    public void handle(JsonObject params) {
        MinecraftClient client = MinecraftClient.getInstance();
        if (client.player == null) return;

        boolean fullStack = params.has("full_stack") && params.get("full_stack").getAsBoolean();
        client.player.dropSelectedItem(fullStack);
    }
}
