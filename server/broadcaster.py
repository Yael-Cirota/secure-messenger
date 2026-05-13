"""
broadcaster.py — Real-time fan-out broadcaster for SSE clients.

DESIGN PATTERNS USED:
  - Pub-Sub / Observer   : publish() notifies all subscribed queues
  - Singleton            : module-level `broadcaster` instance shared app-wide
  - RAII / Async Context Manager : subscribe() registers and auto-cleans up queues
  - Bounded Buffer (Backpressure) : Queue(maxsize=32) — slow clients are skipped,
                                    not allowed to stall the publisher
  - Value Object / Typed Event    : accepts BroadcastEvent, not raw dicts
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from .schemas import BroadcastEvent

log = logging.getLogger(__name__)

_QUEUE_MAX = 32  # max buffered events per subscriber before backpressure kicks in


class Broadcaster:
    """
    Maintains a registry of per-subscriber asyncio queues.
    publish() fans out a typed event to evercted client.
    Clients that are too slow (full queue) are skipped, not stalled.
    """

    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue[BroadcastEvent]] = []

    @asynccontextmanager
    async def subscribe(self):
        """
        Async context manager — yields a bounded queue for one SSE client.
        The queue is registered on enter and removed on exit, even if the
        client disconnects abruptly (RAII guarantee).

        Usage:
            async with broadcaster.subscribe() as queue:
                event = await queue.get()
        """
        queue: asyncio.Queue[BroadcastEvent] = asyncio.Queue(maxsize=_QUEUE_MAX)
        self._subscribers.append(queue)
        log.info("SSE client connected  (total: %d)", len(self._subscribers))
        try:
            yield queue
        finally:
            self._subscribers.remove(queue)
            log.info("SSE client disconnected (total: %d)", len(self._subscribers))

    async def publish(self, event: BroadcastEvent) -> None:
        """
        Push a typed event to all connected subscriber queues.
        If a subscriber's queue is full (slow client), that client is skipped —
        the publisher never blocks (Backpressure / Bounded Buffer pattern).
        """
        dropped = 0
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                dropped += 1

        if dropped:
            log.warning("Dropped event for %d slow subscriber(s)", dropped)


# ---------------------------------------------------------------------------
# Singleton — one broadcaster shared across the entire application lifetime
# ---------------------------------------------------------------------------
broadcaster = Broadcaster()
