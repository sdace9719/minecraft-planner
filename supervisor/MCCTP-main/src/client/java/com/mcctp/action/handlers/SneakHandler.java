package com.mcctp.action.handlers;

import com.google.gson.JsonObject;
import com.mcctp.action.ActionHandler;
import com.mcctp.mixin.KeyBindingAccessor;
import net.minecraft.client.MinecraftClient;

public class SneakHandler implements ActionHandler {
    @Override
    public void handle(JsonObject params) {
        MinecraftClient client = MinecraftClient.getInstance();
        if (client.player == null) return;

        boolean start = !params.has("state") || params.get("state").getAsString().equals("start");
        ((KeyBindingAccessor) client.options.sneakKey).setPressed(start);
    }
}
