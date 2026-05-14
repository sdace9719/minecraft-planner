package com.mcctp.network;

import com.google.gson.Gson;
import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import com.mcctp.MCCTPMod;
import com.mcctp.action.ActionDispatcher;
import com.mcctp.api.MCCTPApi;
import io.netty.channel.ChannelHandlerContext;
import io.netty.channel.SimpleChannelInboundHandler;
import io.netty.handler.codec.http.websocketx.CloseWebSocketFrame;
import io.netty.handler.codec.http.websocketx.PingWebSocketFrame;
import io.netty.handler.codec.http.websocketx.PongWebSocketFrame;
import io.netty.handler.codec.http.websocketx.TextWebSocketFrame;
import io.netty.handler.codec.http.websocketx.WebSocketFrame;

public class WebSocketFrameHandler extends SimpleChannelInboundHandler<WebSocketFrame> {
    private final ConnectionManager connectionManager;
    private final ActionDispatcher actionDispatcher;

    public WebSocketFrameHandler(ConnectionManager connectionManager, ActionDispatcher actionDispatcher) {
        this.connectionManager = connectionManager;
        this.actionDispatcher = actionDispatcher;
    }

    private static final Gson GSON = new Gson();

    @Override
    public void handlerAdded(ChannelHandlerContext ctx) {
        connectionManager.add(ctx.channel());
        sendHandshake(ctx);
    }

    private void sendHandshake(ChannelHandlerContext ctx) {
        JsonObject handshake = new JsonObject();
        handshake.addProperty("type", "handshake");
        JsonArray modules = new JsonArray();
        for (String m : MCCTPApi.getLoadedModules()) {
            modules.add(m);
        }
        handshake.add("modules", modules);
        handshake.addProperty("version", "1.0");
        ctx.channel().writeAndFlush(new TextWebSocketFrame(GSON.toJson(handshake)));
    }

    @Override
    public void handlerRemoved(ChannelHandlerContext ctx) {
        connectionManager.remove(ctx.channel());
    }

    @Override
    protected void channelRead0(ChannelHandlerContext ctx, WebSocketFrame frame) {
        if (frame instanceof TextWebSocketFrame textFrame) {
            String text = textFrame.text();
            MCCTPMod.LOGGER.debug("Received: {}", text);
            String response = actionDispatcher.dispatch(text);
            if (response != null) {
                ctx.channel().writeAndFlush(new TextWebSocketFrame(response));
            }
        } else if (frame instanceof PingWebSocketFrame) {
            ctx.channel().writeAndFlush(new PongWebSocketFrame(frame.content().retain()));
        } else if (frame instanceof CloseWebSocketFrame) {
            ctx.channel().close();
        }
    }

    @Override
    public void exceptionCaught(ChannelHandlerContext ctx, Throwable cause) {
        MCCTPMod.LOGGER.error("WebSocket error", cause);
        ctx.close();
    }
}
