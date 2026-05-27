package com.controlbridge.handlers;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import com.botinterface.HotbarSwapper;
import com.controlbridge.BridgeHttpServer;
import com.controlbridge.BridgeHttpServer.RouteHandler;
import com.controlbridge.JsonUtil;
import net.minecraft.client.MinecraftClient;

public class SwapHotbarHandler extends CraftHandler {
    @Override
    public String handle(String method, String path, Map<String, String> headers, String body) {
        try {
            List<String> itemsToHotbar = parseStringArray(body, "itemsToHotbar");
            if (itemsToHotbar == null || itemsToHotbar.isEmpty())
                return err(400, "Missing required field: 'itemsToHotbar' (non-empty array)");

            List<String> itemsFromHotbar = parseStringArray(body, "itemsFromHotbar");

            int swapped = HotbarSwapper.swapToHotbar(
                MinecraftClient.getInstance(), itemsToHotbar, itemsFromHotbar);
            return BridgeHttpServer.jsonResponse(200,
                JsonUtil.obj("status", JsonUtil.str("ok"), "swapped", JsonUtil.num(swapped)));
        } catch (Exception e) {
            return err(500, "Internal error: " + e.getMessage());
        }
    }

    private static List<String> parseStringArray(String json, String key) {
        String search = "\"" + key + "\"";
        int i = json.indexOf(search);
        if (i < 0) return null;
        i = json.indexOf('[', i + search.length());
        if (i < 0) return null;
        int j = json.indexOf(']', i);
        if (j < 0) return null;
        String inner = json.substring(i + 1, j);
        List<String> result = new ArrayList<>();
        for (String s : inner.split(",")) {
            s = s.trim().replaceAll("^\"|\"$", "");
            if (!s.isEmpty()) result.add(s);
        }
        return result;
    }
}
