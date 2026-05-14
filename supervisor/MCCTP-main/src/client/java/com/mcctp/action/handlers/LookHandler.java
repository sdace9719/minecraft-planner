package com.mcctp.action.handlers;

import com.google.gson.JsonObject;
import com.mcctp.action.ActionHandler;
import net.minecraft.client.MinecraftClient;
import net.minecraft.client.network.ClientPlayerEntity;

public class LookHandler implements ActionHandler {
    @Override
    public void handle(JsonObject params) {
        MinecraftClient client = MinecraftClient.getInstance();
        ClientPlayerEntity player = client.player;
        if (player == null) return;

        float yaw = params.has("yaw") ? params.get("yaw").getAsFloat() : 0;
        float pitch = params.has("pitch") ? params.get("pitch").getAsFloat() : 0;
        boolean relative = params.has("relative") && params.get("relative").getAsBoolean();

        if (relative) {
            player.setYaw(player.getYaw() + yaw);
            player.setPitch(Math.clamp(player.getPitch() + pitch, -90f, 90f));
        } else {
            player.setYaw(yaw);
            player.setPitch(Math.clamp(pitch, -90f, 90f));
        }
    }
}
