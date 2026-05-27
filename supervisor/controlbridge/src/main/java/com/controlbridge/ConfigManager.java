package com.controlbridge;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/** Reads/writes controlbridge.json from the Minecraft config folder. */
public class ConfigManager {
    private static final Logger LOG = LoggerFactory.getLogger("ControlBridge-Config");
    private static final String FILE_NAME = "controlbridge.json";
    private static final int DEFAULT_PORT = 8765;

    private final Path configPath;
    private int port = DEFAULT_PORT;

    public ConfigManager() {
        this.configPath = Paths.get("config", FILE_NAME);
    }

    public int getPort() {
        return port;
    }

    public void load() {
        if (Files.exists(configPath)) {
            try {
                String content = Files.readString(configPath);
                int p = JsonUtil.getInt(content, "port");
                if (p >= 1024 && p <= 65535) {
                    port = p;
                    LOG.info("Loaded port {} from config", port);
                } else {
                    LOG.warn("Invalid port in config, using default {}", DEFAULT_PORT);
                    port = DEFAULT_PORT;
                }
            } catch (Exception e) {
                LOG.warn("Failed to read config, using default {}", DEFAULT_PORT, e);
                port = DEFAULT_PORT;
            }
        } else {
            port = DEFAULT_PORT;
            save();
            LOG.info("Created default config with port {}", DEFAULT_PORT);
        }
    }

    public void save() {
        try {
            Files.createDirectories(configPath.getParent());
            String json = JsonUtil.obj(
                "port", JsonUtil.num(port),
                "_comment", JsonUtil.str("ControlBridge HTTP server port (1024-65535)")
            );
            Files.writeString(configPath, json);
        } catch (IOException e) {
            LOG.error("Failed to save config", e);
        }
    }
}
