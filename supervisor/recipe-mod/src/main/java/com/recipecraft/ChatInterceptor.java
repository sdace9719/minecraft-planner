package com.recipecraft;

import net.fabricmc.fabric.api.client.message.v1.ClientSendMessageEvents;
import net.minecraft.client.MinecraftClient;

public class ChatInterceptor {
    private static final String PREFIX = "!";

    public static void register() {
        ClientSendMessageEvents.ALLOW_CHAT.register((message) -> {
            if (message.startsWith(PREFIX)) {
                String command = message.substring(PREFIX.length()).trim();
                handleCommand(command);
                return false;
            }
            return true;
        });
    }

    private static void handleCommand(String command) {
        if (command.isEmpty()) {
            sendFeedback("Usage: !craft <item> [count]  — example: !craft stick 16");
            return;
        }

        String[] parts = command.split("\\s+");
        if (!parts[0].equalsIgnoreCase("craft")) {
            sendFeedback("Unknown command. Usage: !craft <item> [count]");
            return;
        }

        if (parts.length < 2) {
            sendFeedback("Usage: !craft <item> [count]  — example: !craft stick 16");
            return;
        }

        String itemName = parts[1];
        int count = 1;

        if (parts.length >= 3) {
            try {
                count = Integer.parseInt(parts[2]);
            } catch (NumberFormatException e) {
                sendFeedback("Invalid count: " + parts[2] + ". Using 1.");
                count = 1;
            }
        }

        if (count < 1) {
            sendFeedback("Count must be at least 1.");
            return;
        }

        MinecraftClient client = MinecraftClient.getInstance();
        RecipeCrafter.craft(client, itemName, count);
    }

    static void sendFeedback(String message) {
        MinecraftClient client = MinecraftClient.getInstance();
        if (client.player != null) {
            client.player.sendMessage(
                net.minecraft.text.Text.literal("[RecipeCraft] " + message),
                false
            );
        }
    }
}
