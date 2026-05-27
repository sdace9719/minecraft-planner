package com.controlbridge.handlers;

import java.util.List;
import java.util.Map;
import com.controlbridge.BridgeHttpServer;
import com.controlbridge.BridgeHttpServer.RouteHandler;
import com.recipecraft.RecipeCrafter;

public class PositionsHandler implements RouteHandler {
    @Override
    public String handle(String method, String path, Map<String, String> headers, String body) {
        List<String> positions = RecipeCrafter.getLastPositions();
        StringBuilder sb = new StringBuilder("{\"positions\":[");
        for (int i = 0; i < positions.size(); i++) {
            if (i > 0) sb.append(',');
            sb.append('"').append(positions.get(i)).append('"');
        }
        sb.append("]}");
        return BridgeHttpServer.jsonResponse(200, sb.toString());
    }
}
