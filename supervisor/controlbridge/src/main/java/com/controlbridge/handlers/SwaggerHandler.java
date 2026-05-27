package com.controlbridge.handlers;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import com.controlbridge.BridgeHttpServer;
import com.controlbridge.BridgeHttpServer.RouteHandler;

public class SwaggerHandler implements RouteHandler {
    private static String cached;

    @Override
    public String handle(String method, String path, Map<String, String> headers, String body) {
        if (cached == null) {
            try (InputStream is = getClass().getClassLoader().getResourceAsStream("swagger.json")) {
                if (is != null) cached = new String(is.readAllBytes(), StandardCharsets.UTF_8);
                else cached = "{\"error\":\"swagger.json not found\"}";
            } catch (Exception e) {
                cached = "{\"error\":\"" + e.getMessage() + "\"}";
            }
        }
        return BridgeHttpServer.jsonResponse(200, cached);
    }
}
