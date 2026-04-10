"""Mailbox message system for multi-agent communication.

Implements the Mailbox pattern from Claude Code for async message passing
between agents, supporting poll, receive (blocking), and send with
waiter matching.
"""

import asyncio
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class MailboxMessage:
    """A single message in the mailbox."""
    source: str  # Agent ID that sent this
    content: str
    metadata: dict = field(default_factory=dict)


@dataclass
class Waiter:
    """A pending receive request."""
    filter_fn: Callable[[MailboxMessage], bool]
    resolve: Callable[[MailboxMessage], None]
    reject: Callable[[Exception], None]


class Mailbox:
    """Async mailbox for agent-to-agent messaging.

    Messages can be sent without waiting (fire-and-forget).
    Receivers can poll or block waiting for matching messages.
    """

    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self._queue: list[MailboxMessage] = []
        self._waiters: list[Waiter] = []
        self._lock = asyncio.Lock()

    def send(self, msg: MailboxMessage) -> None:
        """Send a message. Matches any waiting receivers first."""
        # Check if any waiter matches
        for i, waiter in enumerate(self._waiters):
            if waiter.filter_fn(msg):
                self._waiters.pop(i)
                waiter.resolve(msg)
                return
        # No matching waiter, queue it
        self._queue.append(msg)

    def poll(self, filter_fn: Callable[[MailboxMessage], bool] | None = None) -> MailboxMessage | None:
        """Poll for a matching message. Returns None if no match."""
        if filter_fn is None:
            filter_fn = lambda m: True

        for i, msg in enumerate(self._queue):
            if filter_fn(msg):
                return self._queue.pop(i)
        return None

    async def receive(self, filter_fn: Callable[[MailboxMessage], bool] | None = None) -> MailboxMessage:
        """Wait for a matching message. Blocks until received."""
        if filter_fn is None:
            filter_fn = lambda m: True

        # Check queue first
        for i, msg in enumerate(self._queue):
            if filter_fn(msg):
                return self._queue.pop(i)

        # Wait for matching send
        loop = asyncio.get_running_loop()
        waiter = Waiter(
            filter_fn=filter_fn,
            resolve=lambda m: None,  # Will be replaced
            reject=lambda e: None,
        )
        fut = loop.create_future()
        waiter.resolve = lambda m: fut.set_result(m)
        waiter.reject = lambda e: fut.set_exception(e)
        self._waiters.append(waiter)

        try:
            return await fut
        finally:
            # Clean up waiter if not resolved
            if waiter in self._waiters:
                self._waiters.remove(waiter)

    def receive_nowait(self, filter_fn: Callable[[MailboxMessage], bool] | None = None) -> MailboxMessage | None:
        """Non-blocking receive. Returns None if no match available."""
        return self.poll(filter_fn)

    @property
    def queue_size(self) -> int:
        return len(self._queue)

    @property
    def has_waiters(self) -> bool:
        return len(self._waiters) > 0


class TeammateMailbox(Mailbox):
    """Extended mailbox with teammate-specific features."""

    def __init__(self, agent_id: str, team_name: str):
        super().__init__(agent_id)
        self.team_name = team_name
        self._done = asyncio.Event()

    def mark_done(self) -> None:
        """Signal this teammate has completed its task."""
        self._done.set()

    async def wait_done(self, timeout: float | None = None) -> bool:
        """Wait for this teammate to signal completion."""
        try:
            await asyncio.wait_for(self._done.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False

    def send_to_team(
        self,
        content: str,
        target_agent_id: str | None = None,
        team_broadcast: bool = False,
    ) -> None:
        """Send a message to a teammate or entire team."""
        msg = MailboxMessage(
            source=self.agent_id,
            content=content,
            metadata={
                "team": self.team_name,
                "target": target_agent_id,
                "broadcast": team_broadcast,
            },
        )
        self.send(msg)
