package com.controlbridge.handlers;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import com.controlbridge.JsonUtil;
import com.recipecraft.BulkResult;
import com.recipecraft.BulkSmeltListener;
import com.recipecraft.RecipeCrafter;
import com.recipecraft.SmeltRequest;
import net.minecraft.client.MinecraftClient;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class BulkSmeltHandler extends CraftHandler {
    private static final Logger LOG = LoggerFactory.getLogger("ControlBridge-BulkSmelt");

    @Override
    public String handle(String method, String path, Map<String, String> headers, String body) {
        try {
            List<SmeltRequest> requests = parseRequests(body);
            if (requests == null || requests.isEmpty())
                return err(400, "Missing or invalid field: 'requests' (non-empty array required)");

            MinecraftClient client = MinecraftClient.getInstance();
            if (client.player == null)
                return err(503, "Player not in game world");

            BulkResult result = RecipeCrafter.bulkSmelt(client, requests, new BulkSmeltListener() {
                @Override public void onItemComplete(int idx, String name, int count) {
                    LOG.info("Bulk smelt item complete: [{}] {} x{}", idx, name, count);
                }
                @Override public void onAllComplete() {
                    LOG.info("Bulk smelt all complete");
                }
                @Override public void onError(String msg) {
                    LOG.error("Bulk smelt error: {}", msg);
                }
            });

            if (result.success()) {
                return ok("Bulk smelting started: " + result.totalBatches() + " total batches");
            } else {
                return err(400, result.error());
            }
        } catch (Exception e) {
            return err(500, "Internal error: " + e.getMessage());
        }
    }

    private List<SmeltRequest> parseRequests(String json) {
        List<SmeltRequest> list = new ArrayList<>();
        int i = json.indexOf('[');
        if (i < 0) return null;
        int end = json.lastIndexOf(']');
        if (end < 0) return null;
        String arr = json.substring(i + 1, end);

        String[] entries = arr.split("\\},\\s*\\{");
        for (String entry : entries) {
            entry = entry.trim();
            if (entry.startsWith("{")) entry = entry.substring(1);
            if (entry.endsWith("}")) entry = entry.substring(0, entry.length() - 1);
            entry = "{" + entry + "}";
            String item = JsonUtil.getString(entry, "item");
            Integer count = JsonUtil.getInt(entry, "count");
            String fuel = JsonUtil.getString(entry, "fuel");
            if (item != null && count != null && count > 0) {
                if (fuel != null) {
                    list.add(new SmeltRequest(item, count, fuel));
                } else {
                    list.add(new SmeltRequest(item, count));
                }
            }
        }
        return list.isEmpty() ? null : list;
    }
}
