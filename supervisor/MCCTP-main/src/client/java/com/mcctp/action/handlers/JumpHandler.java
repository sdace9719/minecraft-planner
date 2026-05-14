package com.mcctp.action.handlers;

import com.google.gson.JsonObject;
import com.mcctp.action.ActionHandler;
import com.mcctp.action.KeyReleaseScheduler;
import net.minecraft.client.MinecraftClient;

public class JumpHandler implements ActionHandler {
    @Override
    public void handle(JsonObject params) {
        MinecraftClient client = MinecraftClient.getInstance();
        if (client.player == null) return;

        KeyReleaseScheduler.pressPulse(client.options.jumpKey, 3);
    }
}
