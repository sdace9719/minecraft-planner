package com.mcctp.action;

import com.google.gson.Gson;
import com.google.gson.JsonObject;
import com.mcctp.MCCTPMod;
import com.mcctp.action.handlers.*;
import net.minecraft.client.MinecraftClient;

import java.util.HashMap;
import java.util.Map;

public class ActionDispatcher {
    private final Gson gson = new Gson();
    private final Map<String, ActionHandler> handlers = new HashMap<>();

    public ActionDispatcher() {
        handlers.put("move", new MoveHandler());
        handlers.put("look", new LookHandler());
        handlers.put("jump", new JumpHandler());
        handlers.put("sneak", new SneakHandler());
        handlers.put("sprint", new SprintHandler());
        handlers.put("attack", new AttackHandler());
        handlers.put("use_item", new UseItemHandler());
        handlers.put("throw_item", new ThrowItemHandler());
        handlers.put("drop_item", new DropItemHandler());
        handlers.put("select_slot", new SelectSlotHandler());
        handlers.put("swap_hands", new SwapHandsHandler());
        handlers.put("open_inventory", new OpenInventoryHandler());
        handlers.put("close_screen", new CloseScreenHandler());
        handlers.put("toggle_wheel", new ToggleWheelHandler());
        handlers.put("hover_slot", new HoverSlotHandler());
        handlers.put("inventory_click", new InventoryClickHandler());
        handlers.put("send_chat", new SendChatHandler());
        handlers.put("cursor", new CursorHandler());
        handlers.put("click", new ClickHandler());
    }

    public void registerHandler(String action, ActionHandler handler) {
        handlers.put(action, handler);
    }

    public String dispatch(String json) {
        try {
            ActionMessage message = gson.fromJson(json, ActionMessage.class);
            if (message.action == null) {
                return errorResponse("Missing 'action' field");
            }

            ActionHandler handler = handlers.get(message.action);
            if (handler == null) {
                return errorResponse("Unknown action: " + message.action);
            }

            JsonObject params = message.params != null ? message.params : new JsonObject();
            MinecraftClient.getInstance().execute(() -> handler.handle(params));
            return null;
        } catch (Exception e) {
            MCCTPMod.LOGGER.error("Failed to dispatch action", e);
            return errorResponse(e.getMessage());
        }
    }

    private String errorResponse(String message) {
        JsonObject response = new JsonObject();
        response.addProperty("type", "error");
        response.addProperty("message", message);
        return gson.toJson(response);
    }
}
