package com.controlbridge.handlers;

import java.util.Map;
import com.botinterface.ItemPickup;
import com.controlbridge.BridgeHttpServer;
import com.controlbridge.BridgeHttpServer.RouteHandler;
import com.controlbridge.JsonUtil;
import net.minecraft.client.MinecraftClient;

public class ItemPickupHandler extends CraftHandler {
    @Override
    public String handle(String method, String path, Map<String, String> headers, String body) {
        try {
            String item = JsonUtil.getString(body, "item");
            if (item == null || item.isEmpty())
                return err(400, "Missing required field: 'item'");

            boolean picked = ItemPickup.pickupDroppedItem(MinecraftClient.getInstance(), item);
            return BridgeHttpServer.jsonResponse(200,
                JsonUtil.obj("status", JsonUtil.str("ok"),
                    "pickedUp", JsonUtil.bool(picked)));
        } catch (Exception e) {
            return err(500, "Internal error: " + e.getMessage());
        }
    }
}
