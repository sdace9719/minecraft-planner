from __future__ import annotations

import asyncio
import threading
from typing import Callable, Optional

from mcctp.client import MCCTPClient


class SyncMCCTPClient:
    """Synchronous wrapper around MCCTPClient for simple scripts."""

    def __init__(self, host: str = "localhost", port: int = 8765):
        self._async_client = MCCTPClient(host, port)
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None

    @property
    def state(self) -> Optional[dict]:
        return self._async_client.state

    @property
    def modules(self) -> list[str]:
        return self._async_client.modules

    def on_state(self, callback: Callable[[dict], None]):
        self._async_client.on_state(callback)

    def on_handshake(self, callback: Callable[[list[str]], None]):
        self._async_client.on_handshake(callback)

    def connect(self):
        self._loop = asyncio.new_event_loop()
        self._loop.run_until_complete(self._async_client.connect())
        self._thread = threading.Thread(
            target=self._loop.run_until_complete,
            args=(self._async_client.listen(),),
            daemon=True,
        )
        self._thread.start()

    def disconnect(self):
        if self._loop and self._async_client._ws:
            try:
                asyncio.run_coroutine_threadsafe(
                    self._async_client.disconnect(), self._loop
                ).result(timeout=2)
            except (TimeoutError, Exception):
                pass

    def send(self, action: dict):
        if not self._loop:
            raise RuntimeError("Not connected")
        future = asyncio.run_coroutine_threadsafe(
            self._async_client.send(action), self._loop
        )
        future.result(timeout=5)

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *args):
        self.disconnect()
