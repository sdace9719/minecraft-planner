package com.controlbridge.handlers;

import java.util.Map;
import com.controlbridge.JsonUtil;
import com.recipecraft.RecipeCrafter;
import net.minecraft.client.MinecraftClient;

public class SmeltHandler extends CraftHandler {
    @Override
    public String handle(String method, String path, Map<String, String> headers, String body) {
        try {
            String item = JsonUtil.getString(body, "item");
            Integer quantity = JsonUtil.getInt(body, "quantity");
            String fuel = JsonUtil.getString(body, "fuel");

            if (item == null || item.isEmpty())
                return err(400, "Missing required field: 'item'");
            if (quantity == null || quantity < 1)
                return err(400, "Missing or invalid field: 'quantity' (must be >= 1)");

            if (fuel == null) fuel = "oak_planks";

            MinecraftClient client = MinecraftClient.getInstance();
            if (client.player == null)
                return err(503, "Player not in game world");

            RecipeCrafter.smelt(client, item, quantity, fuel);

            return ok("Smelting started for " + quantity + "x " + item + " with " + fuel);
        } catch (Exception e) {
            return err(500, "Internal error: " + e.getMessage());
        }
    }
}
