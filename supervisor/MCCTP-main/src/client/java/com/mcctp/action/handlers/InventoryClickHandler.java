package com.mcctp.action.handlers;

import com.google.gson.JsonObject;
import com.mcctp.MCCTPMod;
import com.mcctp.action.ActionHandler;
import net.minecraft.client.MinecraftClient;
import net.minecraft.client.gui.screen.ingame.HandledScreen;
import net.minecraft.screen.slot.SlotActionType;

public class InventoryClickHandler implements ActionHandler {
    @Override
    public void handle(JsonObject params) {
        MinecraftClient client = MinecraftClient.getInstance();
        if (client.player == null || client.interactionManager == null) return;

        if (!(client.currentScreen instanceof HandledScreen<?> handledScreen)) {
            MCCTPMod.LOGGER.warn("inventory_click requires an open HandledScreen");
            return;
        }

        int slot = params.has("slot") ? params.get("slot").getAsInt() : 0;
        int button = params.has("button") ? params.get("button").getAsInt() : 0;
        String action = params.has("action") ? params.get("action").getAsString() : "pickup";

        SlotActionType actionType = switch (action) {
            case "quick_move" -> SlotActionType.QUICK_MOVE;
            case "swap" -> SlotActionType.SWAP;
            case "throw" -> SlotActionType.THROW;
            case "quick_craft" -> SlotActionType.QUICK_CRAFT;
            case "pickup_all" -> SlotActionType.PICKUP_ALL;
            default -> SlotActionType.PICKUP;
        };

        int syncId = handledScreen.getScreenHandler().syncId;
        client.interactionManager.clickSlot(syncId, slot, button, actionType, client.player);
    }
}
