package com.controlbridge.handlers;

import java.util.Map;
import com.controlbridge.BridgeHttpServer;
import com.controlbridge.BridgeHttpServer.RouteHandler;
import com.controlbridge.JsonUtil;
import com.recipecraft.RecipeCrafter;
import net.minecraft.client.MinecraftClient;

public class CraftHandler implements RouteHandler {
    @Override
    public String handle(String method, String path, Map<String, String> headers, String body) {
        try {
            String item = JsonUtil.getString(body, "item");
            Integer count = JsonUtil.getInt(body, "count");

            if (item == null || item.isEmpty())
                return err(400, "Missing required field: 'item'");
            if (count == null || count < 1)
                return err(400, "Missing or invalid field: 'count' (must be >= 1)");

            MinecraftClient client = MinecraftClient.getInstance();
            if (client.player == null)
                return err(503, "Player not in game world");

            // craft() is fire-and-forget — it validates internally and sends chat errors
            RecipeCrafter.craft(client, item, count);

            return ok("Crafting started for " + count + "x " + item);
        } catch (Exception e) {
            return err(500, "Internal error: " + e.getMessage());
        }
    }

    static String ok(String msg) {
        return BridgeHttpServer.jsonResponse(200,
            JsonUtil.obj("status", JsonUtil.str("ok"), "message", JsonUtil.str(msg)));
    }

    static String err(int code, String msg) {
        return BridgeHttpServer.jsonResponse(code,
            JsonUtil.obj("status", JsonUtil.str("error"), "message", JsonUtil.str(msg)));
    }
}
