package com.controlbridge.handlers;

import java.util.Map;
import com.botinterface.BlockMiner;
import com.controlbridge.BridgeHttpServer;
import com.controlbridge.BridgeHttpServer.RouteHandler;
import com.controlbridge.JsonUtil;
import net.minecraft.client.MinecraftClient;

public class BlockMineHandler extends CraftHandler {
    @Override
    public String handle(String method, String path, Map<String, String> headers, String body) {
        try {
            String block = JsonUtil.getString(body, "block");
            if (block == null || block.isEmpty())
                return err(400, "Missing required field: 'block'");

            Integer count = JsonUtil.getInt(body, "count");
            if (count == null || count <= 0)
                return err(400, "Missing or invalid field: 'count' (must be > 0)");

            boolean started = BlockMiner.mineByName(MinecraftClient.getInstance(), block, count);
            return started
                ? BridgeHttpServer.jsonResponse(200,
                    JsonUtil.obj(
                        "status", JsonUtil.str("ok"),
                        "message", JsonUtil.str("Mining " + count + "x " + block),
                        "block", JsonUtil.str(block),
                        "count", JsonUtil.num(count)))
                : err(503, "Player not in game or mining failed to start");
        } catch (Exception e) {
            return err(500, "Internal error: " + e.getMessage());
        }
    }
}
