package com.mcctp.api;

import com.google.gson.JsonObject;
import net.minecraft.client.MinecraftClient;

public interface StateProvider {
    void collectState(MinecraftClient client, JsonObject root);
}
