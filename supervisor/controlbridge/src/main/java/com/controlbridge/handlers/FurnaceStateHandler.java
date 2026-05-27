package com.controlbridge.handlers;

import java.util.Map;
import com.botinterface.FurnaceStateChecker;
import com.controlbridge.BridgeHttpServer;
import com.controlbridge.BridgeHttpServer.RouteHandler;
import com.controlbridge.JsonUtil;
import net.minecraft.client.MinecraftClient;

public class FurnaceStateHandler extends CraftHandler {
    @Override
    public String handle(String method, String path, Map<String, String> headers, String body) {
        try {
            Map<String, String> params = parseQuery(path);
            String xs = params.get("x"), ys = params.get("y"), zs = params.get("z");
            if (xs == null || ys == null || zs == null)
                return err(400, "Missing query params: x, y, z (e.g. /bot/furnace?x=10&y=64&z=10)");

            int x = Integer.parseInt(xs), y = Integer.parseInt(ys), z = Integer.parseInt(zs);
            boolean burning = FurnaceStateChecker.isBurning(MinecraftClient.getInstance(), x, y, z);
            return BridgeHttpServer.jsonResponse(200,
                JsonUtil.obj("status", JsonUtil.str("ok"), "burning", JsonUtil.bool(burning)));
        } catch (NumberFormatException e) {
            return err(400, "x, y, z must be integers");
        } catch (Exception e) {
            return err(500, "Internal error: " + e.getMessage());
        }
    }

    private static Map<String, String> parseQuery(String path) {
        Map<String, String> m = new java.util.HashMap<>();
        int q = path.indexOf('?');
        if (q < 0) return m;
        for (String pair : path.substring(q + 1).split("&")) {
            int eq = pair.indexOf('=');
            if (eq > 0) m.put(pair.substring(0, eq), pair.substring(eq + 1));
        }
        return m;
    }
}
