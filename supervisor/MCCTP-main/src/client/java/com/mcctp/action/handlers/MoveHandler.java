package com.mcctp.action.handlers;

import com.google.gson.JsonObject;
import com.mcctp.action.ActionHandler;
import com.mcctp.mixin.KeyBindingAccessor;
import net.minecraft.client.MinecraftClient;
import net.minecraft.client.option.GameOptions;
import net.minecraft.client.option.KeyBinding;

public class MoveHandler implements ActionHandler {
    @Override
    public void handle(JsonObject params) {
        MinecraftClient client = MinecraftClient.getInstance();
        if (client.player == null) return;

        String direction = params.has("direction") ? params.get("direction").getAsString() : "forward";
        boolean start = !params.has("state") || params.get("state").getAsString().equals("start");

        GameOptions options = client.options;
        KeyBinding key = switch (direction) {
            case "forward" -> options.forwardKey;
            case "backward" -> options.backKey;
            case "left" -> options.leftKey;
            case "right" -> options.rightKey;
            default -> null;
        };

        if (key != null) {
            ((KeyBindingAccessor) key).setPressed(start);
        }
    }
}
