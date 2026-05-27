package com.controlbridge.handlers;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import com.controlbridge.JsonUtil;
import com.recipecraft.BulkCraftListener;
import com.recipecraft.BulkResult;
import com.recipecraft.CraftRequest;
import com.recipecraft.RecipeCrafter;
import net.minecraft.client.MinecraftClient;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class BulkCraftHandler extends CraftHandler {
    private static final Logger LOG = LoggerFactory.getLogger("ControlBridge-BulkCraft");

    @Override
    public String handle(String method, String path, Map<String, String> headers, String body) {
        try {
            List<CraftRequest> requests = parseRequests(body);
            if (requests == null || requests.isEmpty())
                return err(400, "Missing or invalid field: 'requests' (non-empty array required)");

            MinecraftClient client = MinecraftClient.getInstance();
            if (client.player == null)
                return err(503, "Player not in game world");

            BulkResult result = RecipeCrafter.bulkCraft(client, requests, new BulkCraftListener() {
                @Override public void onItemComplete(int idx, String name, int count) {
                    LOG.info("Bulk craft item complete: [{}] {} x{}", idx, name, count);
                }
                @Override public void onAllComplete() {
                    LOG.info("Bulk craft all complete");
                }
                @Override public void onError(String msg) {
                    LOG.error("Bulk craft error: {}", msg);
                }
            }, true); // skipBreak: leave table in world for Baritone collection

            if (result.success()) {
                return ok("Bulk crafting started: " + result.totalBatches() + " total batches");
            } else {
                return err(400, result.error());
            }
        } catch (Exception e) {
            return err(500, "Internal error: " + e.getMessage());
        }
    }

    private List<CraftRequest> parseRequests(String json) {
        // Parse JSON array of {item, count} objects
        List<CraftRequest> list = new ArrayList<>();
        int i = json.indexOf('[');
        if (i < 0) return null;
        int end = json.lastIndexOf(']');
        if (end < 0) return null;
        String arr = json.substring(i + 1, end);

        // Split by "},{" pattern
        String[] entries = arr.split("\\},\\s*\\{");
        for (String entry : entries) {
            entry = entry.trim();
            if (entry.startsWith("{")) entry = entry.substring(1);
            if (entry.endsWith("}")) entry = entry.substring(0, entry.length() - 1);
            String item = JsonUtil.getString("{" + entry + "}", "item");
            Integer count = JsonUtil.getInt("{" + entry + "}", "count");
            if (item != null && count != null && count > 0) {
                list.add(new CraftRequest(item, count));
            }
        }
        return list.isEmpty() ? null : list;
    }
}
