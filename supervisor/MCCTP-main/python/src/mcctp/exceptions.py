class MCCTPError(Exception):
    """Base exception for MCCTP."""


class ConnectionError(MCCTPError):
    """Failed to connect to MCCTP WebSocket server."""


class ActionError(MCCTPError):
    """Server returned an error for an action."""
