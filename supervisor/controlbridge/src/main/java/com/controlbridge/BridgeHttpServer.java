package com.controlbridge;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import com.controlbridge.handlers.*;

public class BridgeHttpServer {
    private static final Logger LOG = LoggerFactory.getLogger("ControlBridge-HTTP");
    private final int port;
    private final Map<String, RouteHandler> routes = new HashMap<>();
    private volatile boolean running;

    public BridgeHttpServer(int port) {
        this.port = port;
    }

    public void start() {
        // Register routes
        routes.put("GET /health", new HealthHandler());
        routes.put("GET /swagger", new SwaggerHandler());
        routes.put("POST /craft", new CraftHandler());
        routes.put("POST /smelt", new SmeltHandler());
        routes.put("POST /bulk/craft", new BulkCraftHandler());
        routes.put("POST /bulk/smelt", new BulkSmeltHandler());
        routes.put("POST /bot/pickup", new ItemPickupHandler());
        routes.put("GET /bot/furnace", new FurnaceStateHandler());
        routes.put("POST /bot/swap-hotbar", new SwapHotbarHandler());
        routes.put("GET /inventory", new InventoryHandler());
        routes.put("GET /bot/positions", new PositionsHandler());
        routes.put("POST /bot/pickup_placed_block", new PickupPlacedBlockHandler());

        running = true;
        Thread serverThread = new Thread(this::run, "ControlBridge-HTTP");
        serverThread.setDaemon(true);
        serverThread.start();
    }

    private void run() {
        try (ServerSocket serverSocket = new ServerSocket(port)) {
            LOG.info("HTTP server listening on port {}", port);
            while (running) {
                try {
                    Socket client = serverSocket.accept();
                    new Thread(() -> handleClient(client), "Bridge-Worker").start();
                } catch (Exception e) {
                    if (running) LOG.error("Accept error", e);
                }
            }
        } catch (Exception e) {
            LOG.error("Failed to start HTTP server on port {}", port, e);
        }
    }

    private void handleClient(Socket client) {
        try (client) {
            BufferedReader reader = new BufferedReader(new InputStreamReader(client.getInputStream(), StandardCharsets.UTF_8));
            OutputStream out = client.getOutputStream();

            // Parse request line
            String requestLine = reader.readLine();
            if (requestLine == null) return;
            String[] parts = requestLine.split(" ", 3);
            if (parts.length < 2) return;
            String method = parts[0];
            String fullPath = parts[1];
            String path = fullPath.contains("?") ? fullPath.substring(0, fullPath.indexOf('?')) : fullPath;

            // Parse headers
            Map<String, String> headers = new HashMap<>();
            String headerLine;
            int contentLength = 0;
            while ((headerLine = reader.readLine()) != null && !headerLine.isEmpty()) {
                int colon = headerLine.indexOf(':');
                if (colon > 0) {
                    String key = headerLine.substring(0, colon).trim().toLowerCase();
                    String val = headerLine.substring(colon + 1).trim();
                    headers.put(key, val);
                    if (key.equals("content-length")) {
                        contentLength = Integer.parseInt(val);
                    }
                }
            }

            // Read body
            String body = "";
            if (contentLength > 0) {
                char[] buf = new char[contentLength];
                int read = reader.read(buf, 0, contentLength);
                if (read > 0) body = new String(buf, 0, read);
            }

            // Route
            String routeKey = method + " " + path;
            RouteHandler handler = routes.get(routeKey);

            String response;
            if (handler != null) {
                response = handler.handle(method, fullPath, headers, body);
            } else {
                response = jsonResponse(404, "{\"status\":\"error\",\"message\":\"Not found: " + routeKey + "\"}");
            }

            out.write(response.getBytes(StandardCharsets.UTF_8));
            out.flush();
        } catch (Exception e) {
            LOG.error("Error handling client", e);
        }
    }

    public static String jsonResponse(int status, String body) {
        String statusText = switch (status) {
            case 200 -> "OK";
            case 400 -> "Bad Request";
            case 404 -> "Not Found";
            case 500 -> "Internal Server Error";
            default -> "Unknown";
        };
        return "HTTP/1.1 " + status + " " + statusText + "\r\n" +
               "Content-Type: application/json\r\n" +
               "Content-Length: " + body.getBytes(StandardCharsets.UTF_8).length + "\r\n" +
               "Connection: close\r\n" +
               "\r\n" +
               body;
    }

    @FunctionalInterface
    public interface RouteHandler {
        String handle(String method, String path, Map<String, String> headers, String body);
    }
}
