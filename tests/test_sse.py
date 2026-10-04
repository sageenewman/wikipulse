import asyncio

import httpx

from ingestion.config import Settings
from ingestion.sse import StreamMessage, stream_events


def sse_body(*events: tuple[str, str]) -> bytes:
    """Encode (id, data) pairs the way an SSE server sends them."""
    return "".join(f"event: message\nid: {id_}\ndata: {data}\n\n" for id_, data in events).encode()


def sse_response(*events: tuple[str, str]) -> httpx.Response:
    return httpx.Response(
        200, headers={"content-type": "text/event-stream"}, content=sse_body(*events)
    )


def collect(
    transport: httpx.MockTransport, count: int, start_event_id: str = ""
) -> list[StreamMessage]:
    settings = Settings.model_construct(reconnect_min_seconds=0.0, reconnect_max_seconds=0.0)

    async def take() -> list[StreamMessage]:
        messages = []
        stream = stream_events(settings, start_event_id=start_event_id, transport=transport)
        async for message in stream:
            messages.append(message)
            if len(messages) == count:
                break
        await stream.aclose()
        return messages

    return asyncio.run(take())


def test_reconnect_resumes_from_the_last_message_seen() -> None:
    """The server closes the stream; the client reconnects and asks to continue."""
    requests: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.headers.get("Last-Event-ID"))
        if len(requests) == 1:
            return sse_response(("pos-1", "a"), ("pos-2", "b"))
        return sse_response(("pos-3", "c"))

    messages = collect(httpx.MockTransport(handler), count=3)

    assert [m.data for m in messages] == ["a", "b", "c"]
    assert requests == [None, "pos-2"]


def test_reconnects_after_a_network_error() -> None:
    requests: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.headers.get("Last-Event-ID"))
        if len(requests) == 2:
            raise httpx.ConnectError("connection refused")
        if len(requests) == 1:
            return sse_response(("pos-1", "a"))
        return sse_response(("pos-2", "b"))

    messages = collect(httpx.MockTransport(handler), count=2)

    assert [m.data for m in messages] == ["a", "b"]
    # The failed attempt and the retry both ask to continue after pos-1.
    assert requests == [None, "pos-1", "pos-1"]


def test_reconnects_after_a_server_error() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(503)
        return sse_response(("pos-1", "a"))

    messages = collect(httpx.MockTransport(handler), count=1)

    assert [m.data for m in messages] == ["a"]
    assert calls == 2


def test_first_connect_uses_the_stored_position() -> None:
    requests: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.headers.get("Last-Event-ID"))
        return sse_response(("pos-8", "a"))

    collect(httpx.MockTransport(handler), count=1, start_event_id="pos-7")

    assert requests == ["pos-7"]


def test_non_message_and_empty_events_are_ignored() -> None:
    body = b"event: ping\ndata: x\n\n:ok\n\n" + sse_body(("pos-1", "a"))

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=body)

    messages = collect(httpx.MockTransport(handler), count=1)

    assert messages == [StreamMessage(event_id="pos-1", data="a")]
