package com.controlbridge.handlers;

import java.util.Map;
import com.controlbridge.BridgeHttpServer;
import com.controlbridge.BridgeHttpServer.RouteHandler;
import com.controlbridge.JsonUtil;
import com.recipecraft.RecipeCrafter;

public class HealthHandler implements RouteHandler {
    private final long startTime = System.currentTimeMillis();

    @Override
    public String handle(String method, String path, Map<String, String> headers, String body) {
        long uptime = (System.currentTimeMillis() - startTime) / 1000;
        boolean busy = RecipeCrafter.isBusy();
        String resp = JsonUtil.obj(
            "status", JsonUtil.str(busy ? "busy" : "ok"),
            "uptime", JsonUtil.num((int) uptime),
            "active", JsonUtil.bool(busy)
        );
        return BridgeHttpServer.jsonResponse(200, resp);
    }
}
