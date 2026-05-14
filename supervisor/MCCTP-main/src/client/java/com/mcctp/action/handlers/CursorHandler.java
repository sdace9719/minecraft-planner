package com.mcctp.action.handlers;

import com.google.gson.JsonObject;
import com.mcctp.action.ActionHandler;
import net.minecraft.client.MinecraftClient;
import org.lwjgl.glfw.GLFW;

public class CursorHandler implements ActionHandler {

    @Override
    public void handle(JsonObject params) {
        MinecraftClient client = MinecraftClient.getInstance();
        if (client.currentScreen == null) return;

        double x = params.has("x") ? params.get("x").getAsDouble() : 0.5;
        double y = params.has("y") ? params.get("y").getAsDouble() : 0.5;

        // Convert normalized coords (0-1) to screen pixel coords
        long window = client.getWindow().getHandle();
        double scale = client.getWindow().getScaleFactor();
        double pixelX = x * client.getWindow().getScaledWidth() * scale;
        double pixelY = y * client.getWindow().getScaledHeight() * scale;

        GLFW.glfwSetCursorPos(window, pixelX, pixelY);
    }
}
