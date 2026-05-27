package com.controlbridge.handlers;

import java.util.Map;
import com.botinterface.BlockCollector;
import com.controlbridge.BridgeHttpServer;
import com.controlbridge.BridgeHttpServer.RouteHandler;
import com.controlbridge.JsonUtil;
import net.minecraft.client.MinecraftClient;

public class PickupPlacedBlockHandler extends CraftHandler {
    @Override
    public String handle(String method, String path, Map<String, String> headers, String body) {
        try {
            Integer x = JsonUtil.getInt(body, "x");
            Integer y = JsonUtil.getInt(body, "y");
            Integer z = JsonUtil.getInt(body, "z");
            if (x == null || y == null || z == null)
                return err(400, "Missing required fields: x, y, z");

            boolean broken = BlockCollector.gotoAndBreak(MinecraftClient.getInstance(), x, y, z);
            return BridgeHttpServer.jsonResponse(200,
                JsonUtil.obj("status", JsonUtil.str("ok"),
                    "broken", JsonUtil.bool(broken),
                    "x", JsonUtil.num(x), "y", JsonUtil.num(y), "z", JsonUtil.num(z)));
        } catch (Exception e) {
            return err(500, "Internal error: " + e.getMessage());
        }
    }
}
