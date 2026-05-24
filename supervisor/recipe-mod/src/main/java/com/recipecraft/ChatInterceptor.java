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
            sendFeedback("Usage: !craft <item> [count]  or  !smelt <item> <qty> [fuel_qty] [fuel]");
            return;
        }

        String[] parts = command.split("\\s+");
        String sub = parts[0].toLowerCase();

        if (sub.equals("craft")) {
            handleCraft(parts);
        } else if (sub.equals("smelt")) {
            handleSmelt(parts);
        } else {
            sendFeedback("Unknown command. Use !craft or !smelt.");
        }
    }

    // ── !craft <item> [count] ──
    private static void handleCraft(String[] parts) {
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
            }
        }
        if (count < 1) {
            sendFeedback("Count must be at least 1.");
            return;
        }

        MinecraftClient client = MinecraftClient.getInstance();
        RecipeCrafter.craft(client, itemName, count);
    }

    // ── !smelt <item> <quantity> [fuel_item] ──
    private static void handleSmelt(String[] parts) {
        if (parts.length < 3) {
            sendFeedback("Usage: !smelt <item> <quantity> [fuel_item]  — example: !smelt raw_iron 6 coal");
            return;
        }

        String itemName = parts[1];
        int smeltQty;
        try {
            smeltQty = Integer.parseInt(parts[2]);
        } catch (NumberFormatException e) {
            sendFeedback("Invalid quantity: " + parts[2]);
            return;
        }
        if (smeltQty < 1) {
            sendFeedback("Quantity must be at least 1.");
            return;
        }

        String fuelName = "oak_planks"; // default fuel
        if (parts.length >= 4) {
            fuelName = parts[3];
        }

        MinecraftClient client = MinecraftClient.getInstance();
        RecipeCrafter.smelt(client, itemName, smeltQty, fuelName);
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
