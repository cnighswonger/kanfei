"""Bot adapter protocol for messaging platform integrations.

Defines the contract that all bot adapters (Telegram, Discord, Slack)
implement. Uses typing.Protocol for structural subtyping — adapters
don't need to inherit from this class, they just need matching methods.
"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class BotAdapter(Protocol):
    """Protocol for messaging bot adapters."""

    async def send_notification(self, text: str) -> None:
        """Send a notification message to all configured channels/chats."""
        ...

    async def handle_event(self, message: dict) -> None:
        """Process an IPC or emitter event and send notifications if applicable."""
        ...

    async def start(self) -> None:
        """Start the bot connection (polling, WebSocket, etc.)."""
        ...

    async def stop(self) -> None:
        """Stop the bot gracefully."""
        ...
