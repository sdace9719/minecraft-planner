from __future__ import annotations

import asyncio
import json
from typing import Callable, Optional

import websockets
from websockets.asyncio.client import ClientConnection

from mcctp.exceptions import ConnectionError, ActionError


class MCCTPClient:
    """Async WebSocket client for MCCTP."""

    def __init__(self, host: str = "localhost", port: int = 8765):
        self.uri = f"ws://{host}:{port}/mcctp"
        self._ws: Optional[ClientConnection] = None
        self._state: Optional[dict] = None
        self._state_callback: Optional[Callable[[dict], None]] = None
        self._modules: list[str] = []
        self._handshake_callback: Optional[Callable[[list[str]], None]] = None
        self._running = False

    @property
    def state(self) -> Optional[dict]:
        return self._state

    @property
    def modules(self) -> list[str]:
        return self._modules

    def on_state(self, callback: Callable[[dict], None]):
        self._state_callback = callback

    def on_handshake(self, callback: Callable[[list[str]], None]):
        self._handshake_callback = callback

    async def connect(self):
        try:
            self._ws = await websockets.connect(self.uri)
        except Exception as e:
            raise ConnectionError(f"Failed to connect to {self.uri}: {e}") from e
        self._running = True

    async def disconnect(self):
        self._running = False
        if self._ws:
            await self._ws.close()
            self._ws = None

    async def send(self, action: dict):
        if not self._ws:
            raise ConnectionError("Not connected")
        await self._ws.send(json.dumps(action))

    async def recv(self) -> dict:
        if not self._ws:
            raise ConnectionError("Not connected")
        data = await self._ws.recv()
        return json.loads(data)

    async def listen(self):
        """Listen for messages. Blocks until disconnected."""
        if not self._ws:
            raise ConnectionError("Not connected")

        try:
            async for message in self._ws:
                data = json.loads(message)
                msg_type = data.get("type")
                if msg_type == "handshake":
                    self._modules = data.get("modules", [])
                    if self._handshake_callback:
                        self._handshake_callback(self._modules)
                elif msg_type == "game_state":
                    self._state = data
                    if self._state_callback:
                        self._state_callback(self._state)
                elif msg_type == "error":
                    raise ActionError(data.get("message", "Unknown error"))
        except websockets.ConnectionClosed:
            pass
        finally:
            self._running = False

    async def send_and_listen(self, action: dict):
        """Send an action and continue listening."""
        await self.send(action)

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, *args):
        await self.disconnect()
