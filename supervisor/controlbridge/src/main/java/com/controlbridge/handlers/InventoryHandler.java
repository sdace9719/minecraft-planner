package com.controlbridge.handlers;

import java.util.Map;
import com.controlbridge.BridgeHttpServer;
import com.controlbridge.BridgeHttpServer.RouteHandler;
import com.controlbridge.JsonUtil;
import net.minecraft.client.MinecraftClient;
import net.minecraft.item.ItemStack;

public class InventoryHandler implements RouteHandler {
    @Override
    public String handle(String method, String path, Map<String, String> headers, String body) {
        var player = MinecraftClient.getInstance().player;
        if (player == null)
            return BridgeHttpServer.jsonResponse(503,
                JsonUtil.obj("status", JsonUtil.str("error"), "message", JsonUtil.str("Player not in game")));

        StringBuilder sb = new StringBuilder("[");
        var inv = player.getInventory();
        boolean first = true;
        for (int i = 0; i < inv.size(); i++) {
            ItemStack stack = inv.getStack(i);
            if (stack.isEmpty()) continue;
            if (!first) sb.append(',');
            first = false;
            String itemId = net.minecraft.registry.Registries.ITEM.getId(stack.getItem()).toString();
            sb.append(JsonUtil.obj(
                "slot", JsonUtil.num(i),
                "item", JsonUtil.str(itemId),
                "count", JsonUtil.num(stack.getCount())));
        }
        sb.append(']');
        return BridgeHttpServer.jsonResponse(200, sb.toString());
    }
}
