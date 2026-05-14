package com.mcctp.network;

import com.mcctp.action.ActionDispatcher;
import io.netty.channel.ChannelInitializer;
import io.netty.channel.ChannelPipeline;
import io.netty.channel.socket.SocketChannel;
import io.netty.handler.codec.http.HttpObjectAggregator;
import io.netty.handler.codec.http.HttpServerCodec;
import io.netty.handler.codec.http.websocketx.WebSocketServerProtocolHandler;

public class WebSocketServerInitializer extends ChannelInitializer<SocketChannel> {
    private final ConnectionManager connectionManager;
    private final ActionDispatcher actionDispatcher;

    public WebSocketServerInitializer(ConnectionManager connectionManager, ActionDispatcher actionDispatcher) {
        this.connectionManager = connectionManager;
        this.actionDispatcher = actionDispatcher;
    }

    @Override
    protected void initChannel(SocketChannel ch) {
        ChannelPipeline pipeline = ch.pipeline();
        pipeline.addLast(new HttpServerCodec());
        pipeline.addLast(new HttpObjectAggregator(65536));
        pipeline.addLast(new WebSocketServerProtocolHandler("/mcctp"));
        pipeline.addLast(new WebSocketFrameHandler(connectionManager, actionDispatcher));
    }
}
