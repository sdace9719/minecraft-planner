package com.mcctp.hud;

public class HotbarWheelState {
    private static boolean visible = false;
    private static int selectedSlot = 0;

    public static boolean isVisible() {
        return visible;
    }

    public static void toggle() {
        visible = !visible;
    }

    public static int getSelectedSlot() {
        return selectedSlot;
    }

    public static void setSelectedSlot(int slot) {
        selectedSlot = Math.clamp(slot, 0, 8);
    }
}
