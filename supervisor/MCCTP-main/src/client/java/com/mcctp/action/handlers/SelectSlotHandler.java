package com.mcctp.action.handlers;

import com.google.gson.JsonObject;
import com.mcctp.action.ActionHandler;
import com.mcctp.hud.HotbarWheelState;
import net.minecraft.client.MinecraftClient;

public class SelectSlotHandler implements ActionHandler {
    @Override
    public void handle(JsonObject params) {
        MinecraftClient client = MinecraftClient.getInstance();
        if (client.player == null) return;

        int slot = params.has("slot") ? params.get("slot").getAsInt() : 0;
        if (slot < 0 || slot > 8) return;

        client.player.getInventory().setSelectedSlot(slot);
        HotbarWheelState.setSelectedSlot(slot);
    }
}
