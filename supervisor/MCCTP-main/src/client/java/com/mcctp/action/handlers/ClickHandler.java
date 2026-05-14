package com.mcctp.action.handlers;

import com.google.gson.JsonObject;
import com.mcctp.action.ActionHandler;
import net.minecraft.client.MinecraftClient;
import net.minecraft.client.gui.Click;
import net.minecraft.client.gui.screen.Screen;
import net.minecraft.client.input.MouseInput;
import org.lwjgl.glfw.GLFW;

public class ClickHandler implements ActionHandler {

    @Override
    public void handle(JsonObject params) {
        MinecraftClient client = MinecraftClient.getInstance();
        Screen screen = client.currentScreen;
        if (screen == null) return;

        String button = params.has("button") ? params.get("button").getAsString() : "left";
        int glfwButton = button.equals("right") ? GLFW.GLFW_MOUSE_BUTTON_RIGHT : GLFW.GLFW_MOUSE_BUTTON_LEFT;

        long window = client.getWindow().getHandle();
        double[] mx = new double[1], my = new double[1];
        GLFW.glfwGetCursorPos(window, mx, my);
        double scale = client.getWindow().getScaleFactor();
        double scaledX = mx[0] / scale;
        double scaledY = my[0] / scale;

        MouseInput mouseInput = new MouseInput(glfwButton, 0);
        Click click = new Click(scaledX, scaledY, mouseInput);
        screen.mouseClicked(click, false);
        screen.mouseReleased(click);
    }
}
