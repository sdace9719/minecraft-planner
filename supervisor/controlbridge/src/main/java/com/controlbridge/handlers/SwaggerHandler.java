package com.controlbridge.handlers;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import com.controlbridge.BridgeHttpServer;
import com.controlbridge.BridgeHttpServer.RouteHandler;

public class SwaggerHandler implements RouteHandler {
    private static String cachedSpec;

    private static final String SWAGGER_UI_HTML = """
        <!DOCTYPE html>
        <html lang="en">
        <head>
          <meta charset="UTF-8">
          <meta name="viewport" content="width=device-width, initial-scale=1.0">
          <title>ControlBridge API Docs</title>
          <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css">
          <style>
            html { box-sizing: border-box; overflow-y: scroll; }
            *, *::before, *::after { box-sizing: inherit; }
            body { margin: 0; background: #fafafa; }
            .swagger-ui .topbar { background-color: #1b1b1b; }
            .swagger-ui .topbar .download-url-wrapper .select-label { display: flex; align-items: center; }
            .swagger-ui .info .title { font-size: 2em; }
          </style>
        </head>
        <body>
          <div id="swagger-ui"></div>
          <script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js" crossorigin></script>
          <script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-standalone-preset.js" crossorigin></script>
          <script>
            SwaggerUIBundle({
              url: "./swagger",
              dom_id: "#swagger-ui",
              deepLinking: true,
              presets: [SwaggerUIBundle.presets.apis, SwaggerUIStandalonePreset],
              plugins: [SwaggerUIBundle.plugins.DownloadUrl],
              layout: "StandaloneLayout"
            });
          </script>
        </body>
        </html>
        """;

    @Override
    public String handle(String method, String path, Map<String, String> headers, String body) {
        // Strip query string to get clean path
        String cleanPath = path.contains("?") ? path.substring(0, path.indexOf('?')) : path;

        // /docs or /docs/ → Swagger UI HTML page
        if (cleanPath.equals("/docs") || cleanPath.equals("/docs/") || cleanPath.startsWith("/docs?")) {
            return htmlResponse(200, SWAGGER_UI_HTML);
        }

        // /swagger — return raw OpenAPI spec
        if (cachedSpec == null) {
            try (InputStream is = getClass().getClassLoader().getResourceAsStream("swagger.json")) {
                if (is != null) cachedSpec = new String(is.readAllBytes(), StandardCharsets.UTF_8);
                else cachedSpec = "{\"error\":\"swagger.json not found\"}";
            } catch (Exception e) {
                cachedSpec = "{\"error\":\"" + e.getMessage() + "\"}";
            }
        }
        return BridgeHttpServer.jsonResponse(200, cachedSpec);
    }

    private static String htmlResponse(int status, String body) {
        String statusText = status == 200 ? "OK" : "Error";
        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        return "HTTP/1.1 " + status + " " + statusText + "\r\n" +
               "Content-Type: text/html; charset=UTF-8\r\n" +
               "Content-Length: " + bytes.length + "\r\n" +
               "Connection: close\r\n" +
               "\r\n" +
               body;
    }
}
