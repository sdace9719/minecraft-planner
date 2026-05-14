package com.mcctp.config;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.mcctp.MCCTPMod;
import net.fabricmc.loader.api.FabricLoader;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public class MCCTPConfig {
    private int port = 8765;
    private int tickInterval = 1;

    private static final Gson GSON = new GsonBuilder().setPrettyPrinting().create();

    public int getPort() {
        return port;
    }

    public int getTickInterval() {
        return tickInterval;
    }

    public static MCCTPConfig load() {
        Path configPath = FabricLoader.getInstance().getConfigDir().resolve("mcctp.json");
        if (Files.exists(configPath)) {
            try {
                String json = Files.readString(configPath);
                MCCTPConfig config = GSON.fromJson(json, MCCTPConfig.class);
                MCCTPMod.LOGGER.info("Loaded MCCTP config: port={}, tickInterval={}", config.port, config.tickInterval);
                return config;
            } catch (IOException e) {
                MCCTPMod.LOGGER.error("Failed to load MCCTP config, using defaults", e);
            }
        }
        MCCTPConfig config = new MCCTPConfig();
        config.save();
        return config;
    }

    public void save() {
        Path configPath = FabricLoader.getInstance().getConfigDir().resolve("mcctp.json");
        try {
            Files.writeString(configPath, GSON.toJson(this));
        } catch (IOException e) {
            MCCTPMod.LOGGER.error("Failed to save MCCTP config", e);
        }
    }
}
