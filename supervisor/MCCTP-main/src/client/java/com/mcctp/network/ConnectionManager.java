package com.mcctp.network;

import com.mcctp.MCCTPMod;
import io.netty.channel.Channel;
import io.netty.handler.codec.http.websocketx.TextWebSocketFrame;

import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

public class ConnectionManager {
    private final Set<Channel> channels = ConcurrentHashMap.newKeySet();

    public void add(Channel channel) {
        channels.add(channel);
        MCCTPMod.LOGGER.info("MCCTP client connected: {}", channel.remoteAddress());
    }

    public void remove(Channel channel) {
        channels.remove(channel);
        MCCTPMod.LOGGER.info("MCCTP client disconnected: {}", channel.remoteAddress());
    }

    public void broadcast(String message) {
        TextWebSocketFrame frame = new TextWebSocketFrame(message);
        for (Channel ch : channels) {
            if (ch.isActive()) {
                ch.writeAndFlush(frame.retainedDuplicate());
            }
        }
        frame.release();
    }

    public void disconnectAll() {
        for (Channel ch : channels) {
            ch.close();
        }
        channels.clear();
    }

    public int getConnectionCount() {
        return channels.size();
    }
}
