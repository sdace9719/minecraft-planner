package com.mcctp.network;

import com.mcctp.MCCTPMod;
import com.mcctp.action.ActionDispatcher;
import io.netty.bootstrap.ServerBootstrap;
import io.netty.channel.Channel;
import io.netty.channel.EventLoopGroup;
import io.netty.channel.nio.NioEventLoopGroup;
import io.netty.channel.socket.nio.NioServerSocketChannel;

public class WebSocketServer {
    private final int port;
    private final ConnectionManager connectionManager;
    private final ActionDispatcher actionDispatcher;

    private EventLoopGroup bossGroup;
    private EventLoopGroup workerGroup;
    private Channel serverChannel;

    public WebSocketServer(int port, ConnectionManager connectionManager, ActionDispatcher actionDispatcher) {
        this.port = port;
        this.connectionManager = connectionManager;
        this.actionDispatcher = actionDispatcher;
    }

    public void start() {
        if (serverChannel != null && serverChannel.isActive()) {
            MCCTPMod.LOGGER.warn("MCCTP WebSocket server is already running");
            return;
        }

        bossGroup = new NioEventLoopGroup(1);
        workerGroup = new NioEventLoopGroup(2);

        new Thread(() -> {
            try {
                ServerBootstrap bootstrap = new ServerBootstrap();
                bootstrap.group(bossGroup, workerGroup)
                        .channel(NioServerSocketChannel.class)
                        .childHandler(new WebSocketServerInitializer(connectionManager, actionDispatcher));

                serverChannel = bootstrap.bind(port).sync().channel();
                MCCTPMod.LOGGER.info("MCCTP WebSocket server started on port {}", port);
                serverChannel.closeFuture().sync();
            } catch (InterruptedException e) {
                MCCTPMod.LOGGER.error("MCCTP WebSocket server interrupted", e);
                Thread.currentThread().interrupt();
            } catch (Exception e) {
                MCCTPMod.LOGGER.error("MCCTP WebSocket server failed to start", e);
            } finally {
                shutdown();
            }
        }, "MCCTP-WebSocket").start();
    }

    public void stop() {
        connectionManager.disconnectAll();
        if (serverChannel != null) {
            serverChannel.close();
            serverChannel = null;
        }
        shutdown();
    }

    private void shutdown() {
        if (bossGroup != null) {
            bossGroup.shutdownGracefully();
            bossGroup = null;
        }
        if (workerGroup != null) {
            workerGroup.shutdownGracefully();
            workerGroup = null;
        }
    }
}
