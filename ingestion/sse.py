"""Client for the Wikimedia Server-Sent Events stream, with automatic reconnect."""

import asyncio
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass

import httpx
from httpx_sse import SSEError, aconnect_sse

from ingestion.config import Settings

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class StreamMessage:
    event_id: str
    """Position in the upstream stream. Sent back as `Last-Event-ID` to resume."""
    data: str
    """The event payload, exactly as received."""


async def stream_events(settings: Settings) -> AsyncIterator[StreamMessage]:
    """Yield stream messages forever, reconnecting when the connection drops.

    After a reconnect the stream resumes from the last message seen, so messages
    can repeat around a reconnect but are not skipped (at-least-once). The resume
    position lives in memory only: a process restart starts from "now".
    """
    last_event_id = ""
    delay = settings.reconnect_min_seconds
    timeout = httpx.Timeout(10.0, read=settings.stream_read_timeout_seconds)
    headers = {"User-Agent": settings.user_agent, "Accept": "text/event-stream"}

    async with httpx.AsyncClient(timeout=timeout, headers=headers) as client:
        while True:
            resume = {"Last-Event-ID": last_event_id} if last_event_id else {}
            try:
                async with aconnect_sse(
                    client, "GET", settings.stream_url, headers=resume
                ) as source:
                    source.response.raise_for_status()
                    log.info("stream connected", extra={"resumed": bool(last_event_id)})
                    async for sse in source.aiter_sse():
                        if sse.event != "message" or not sse.data:
                            continue
                        if sse.id:
                            last_event_id = sse.id
                        delay = settings.reconnect_min_seconds
                        yield StreamMessage(event_id=sse.id, data=sse.data)
                log.info("stream closed by server")
            except (httpx.HTTPError, SSEError) as exc:
                log.warning(
                    "stream connection failed",
                    extra={"error": repr(exc), "retry_in_seconds": delay},
                )

            await asyncio.sleep(delay)
            delay = min(delay * 2, settings.reconnect_max_seconds)
