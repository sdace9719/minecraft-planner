package com.mcctp;

import com.google.gson.Gson;
import com.google.gson.JsonObject;
import com.mcctp.action.ActionDispatcher;
import com.mcctp.action.KeyReleaseScheduler;
import com.mcctp.api.MCCTPApi;
import com.mcctp.api.StateProvider;
import com.mcctp.api.StateProviderRegistry;
import com.mcctp.config.MCCTPConfig;
import com.mcctp.hud.HotbarWheelRenderer;
import com.mcctp.hud.HotbarWheelState;
import com.mcctp.network.ConnectionManager;
import com.mcctp.network.WebSocketServer;
import net.fabricmc.api.ClientModInitializer;
import net.fabricmc.fabric.api.client.event.lifecycle.v1.ClientTickEvents;
import net.fabricmc.fabric.api.client.networking.v1.ClientPlayConnectionEvents;
import net.fabricmc.fabric.api.client.keybinding.v1.KeyBindingHelper;
import net.fabricmc.fabric.api.client.rendering.v1.HudRenderCallback;
import net.minecraft.client.option.KeyBinding;
import org.lwjgl.glfw.GLFW;

import java.util.List;

public class MCCTPClient implements ClientModInitializer {
    private WebSocketServer webSocketServer;
    private ActionDispatcher actionDispatcher;
    private ConnectionManager connectionManager;
    private final Gson gson = new Gson();
    private int tickCounter;

    private static final KeyBinding TOGGLE_WHEEL = KeyBindingHelper.registerKeyBinding(
            new KeyBinding("key.mcctp.toggle_wheel", GLFW.GLFW_KEY_V, KeyBinding.Category.MISC)
    );

    @Override
    public void onInitializeClient() {
        MCCTPConfig config = MCCTPConfig.load();
        connectionManager = new ConnectionManager();
        actionDispatcher = new ActionDispatcher();
        webSocketServer = new WebSocketServer(config.getPort(), connectionManager, actionDispatcher);

        // Set API singletons
        MCCTPApi.init(connectionManager, actionDispatcher);
        MCCTPApi.registerModule("mcctp");
        MCCTPApi.setTickInterval(config.getTickInterval());

        ClientPlayConnectionEvents.JOIN.register((handler, sender, client) -> {
            MCCTPMod.LOGGER.info("Joined world, starting MCCTP WebSocket server on port {}", config.getPort());
            webSocketServer.start();
        });

        ClientPlayConnectionEvents.DISCONNECT.register((handler, client) -> {
            MCCTPMod.LOGGER.info("Disconnected, stopping MCCTP WebSocket server");
            webSocketServer.stop();
        });

        ClientTickEvents.END_CLIENT_TICK.register(client -> {
            KeyReleaseScheduler.tick();
            if (client.player == null) return;

            if (TOGGLE_WHEEL.wasPressed()) {
                HotbarWheelState.toggle();
            }

            List<StateProvider> providers = StateProviderRegistry.getProviders();
            if (!providers.isEmpty()) {
                tickCounter++;
                if (tickCounter >= MCCTPApi.getTickInterval()) {
                    tickCounter = 0;
                    JsonObject root = new JsonObject();
                    root.addProperty("type", "game_state");
                    root.addProperty("timestamp", System.currentTimeMillis());
                    for (StateProvider p : providers) {
                        p.collectState(client, root);
                    }
                    connectionManager.broadcast(gson.toJson(root));
                }
            }
        });

        HudRenderCallback.EVENT.register((drawContext, renderTickCounter) -> {
            HotbarWheelRenderer.render(drawContext);
        });

        MCCTPMod.LOGGER.info("MCCTP client initialized");
    }
}
