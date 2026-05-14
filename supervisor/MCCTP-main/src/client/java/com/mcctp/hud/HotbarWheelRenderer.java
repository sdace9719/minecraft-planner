package com.mcctp.hud;

import net.minecraft.client.MinecraftClient;
import net.minecraft.client.gui.DrawContext;
import net.minecraft.client.network.ClientPlayerEntity;
import net.minecraft.item.ItemStack;

public class HotbarWheelRenderer {
    private static final int RADIUS = 60;
    private static final int SLOT_SIZE = 20;
    private static final float START_ANGLE = 180f;   // π radians (left side)
    private static final float TOTAL_ARC = 270f;     // 3/4 circle (π to -π/2)
    private static final float ANGLE_STEP = TOTAL_ARC / 8f; // 33.75° for 9 slots
    private static final int SELECTED_COLOR = 0xFFFFD700;
    private static final int NORMAL_COLOR = 0xAA333333;
    private static final int BORDER_COLOR = 0xAA888888;

    public static void render(DrawContext context) {
        if (!HotbarWheelState.isVisible()) return;

        MinecraftClient client = MinecraftClient.getInstance();
        ClientPlayerEntity player = client.player;
        if (player == null) return;

        int centerX = client.getWindow().getScaledWidth() / 2;
        int centerY = client.getWindow().getScaledHeight() / 2;
        int selected = HotbarWheelState.getSelectedSlot();

        for (int i = 0; i < 9; i++) {
            double angle = Math.toRadians(START_ANGLE + i * ANGLE_STEP);
            int slotX = centerX + (int) (RADIUS * Math.cos(angle)) - SLOT_SIZE / 2;
            int slotY = centerY + (int) (RADIUS * Math.sin(angle)) - SLOT_SIZE / 2;

            // Background
            int bgColor = (i == selected) ? SELECTED_COLOR : NORMAL_COLOR;
            context.fill(slotX - 1, slotY - 1, slotX + SLOT_SIZE + 1, slotY + SLOT_SIZE + 1,
                    (i == selected) ? SELECTED_COLOR : BORDER_COLOR);
            context.fill(slotX, slotY, slotX + SLOT_SIZE, slotY + SLOT_SIZE, NORMAL_COLOR);

            // Item icon
            ItemStack stack = player.getInventory().getStack(i);
            if (!stack.isEmpty()) {
                context.drawItem(stack, slotX + 2, slotY + 2);
                if (stack.getCount() > 1) {
                    String count = String.valueOf(stack.getCount());
                    context.drawText(client.textRenderer, count, slotX + SLOT_SIZE - 4, slotY + SLOT_SIZE - 8, 0xFFFFFFFF, true);
                }
            }

            // Slot number
            String label = String.valueOf(i + 1);
            context.drawText(client.textRenderer, label, slotX + SLOT_SIZE / 2 - 2, slotY - 10, 0xFFFFFFFF, true);
        }
    }
}
