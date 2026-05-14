package com.mcctp.action;

import com.mcctp.mixin.KeyBindingAccessor;
import net.minecraft.client.option.KeyBinding;

import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;

public class KeyReleaseScheduler {
    private static final List<PendingRelease> pending = new ArrayList<>();

    public static void scheduleRelease(KeyBinding key, int ticks) {
        pending.add(new PendingRelease(key, ticks));
    }

    public static void pressPulse(KeyBinding key, int holdTicks) {
        ((KeyBindingAccessor) key).setPressed(true);
        ((KeyBindingAccessor) key).setTimesPressed(((KeyBindingAccessor) key).getTimesPressed() + 1);
        scheduleRelease(key, holdTicks);
    }

    public static void tick() {
        Iterator<PendingRelease> it = pending.iterator();
        while (it.hasNext()) {
            PendingRelease pr = it.next();
            if (--pr.ticksLeft <= 0) {
                ((KeyBindingAccessor) pr.key).setPressed(false);
                it.remove();
            }
        }
    }

    private static class PendingRelease {
        final KeyBinding key;
        int ticksLeft;

        PendingRelease(KeyBinding key, int ticksLeft) {
            this.key = key;
            this.ticksLeft = ticksLeft;
        }
    }
}
