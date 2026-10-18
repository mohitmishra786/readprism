"""MCP server (EC-04): protocol, tools, and scope gating."""

from __future__ import annotations

import json

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.mcp_server import ReadPrismMcpServer


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_initialize_and_tools_list_readonly():
    server = ReadPrismMcpServer("http://test", "rp_ro", client=_client())
    server.write_scope = False  # skip the probe; test the gating directly

    init = await server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert init["result"]["serverInfo"]["name"] == "readprism"

    listed = await server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    names = [t["name"] for t in listed["result"]["tools"]]
    assert "get_digest" in names and "search_archive" in names
    assert "add_source" not in names  # read-only token: write tools not advertised
    assert "record_feedback" not in names


@pytest.mark.asyncio
async def test_write_scope_lists_and_calls_write_tools():
    server = ReadPrismMcpServer("http://test", "rp_rw", client=_client())
    server.write_scope = True

    listed = await server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    names = [t["name"] for t in listed["result"]["tools"]]
    assert "add_source" in names and "record_feedback" in names

    result = await server.handle(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "record_feedback", "arguments": {"content_item_id": "x"}},
        }
    )
    # Tool-level failures surface as isError results (not protocol errors).
    assert result["result"]["isError"] is True


@pytest.mark.asyncio
async def test_notifications_get_no_response_and_unknown_method_errors():
    server = ReadPrismMcpServer("http://test", "rp_x", client=_client())
    assert await server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    err = await server.handle({"jsonrpc": "2.0", "id": 9, "method": "bogus"})
    assert err["error"]["code"] == -32601


@pytest.mark.asyncio
async def test_scope_probe_via_403(client: AsyncClient, test_user_data: dict):
    """detect_scope maps a 403 to read-only using the real API."""
    resp = await client.post("/api/v1/auth/register", json=test_user_data)
    jwt = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    ro = await client.post("/api/v1/tokens", json={"name": "ro", "scopes": ["read"]}, headers=jwt)

    token = ro.json()["token"]
    api_client = AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": f"Bearer {token}"},
    )
    server = ReadPrismMcpServer("http://test", token, client=api_client)
    await server.detect_scope()
    assert server.write_scope is False
    names = [
        t["name"]
        for t in (await server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}))[
            "result"
        ]["tools"]
    ]
    assert "add_source" not in names


@pytest.mark.asyncio
async def test_http_transport_serves_on_localhost():
    """--http used to crash: uvicorn.run() inside the running event loop (#262)."""
    import asyncio
    import contextlib
    import socket
    from unittest.mock import AsyncMock, patch

    import httpx

    from app import mcp_server

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    with patch.object(mcp_server.ReadPrismMcpServer, "detect_scope", AsyncMock()):
        task = asyncio.create_task(mcp_server.serve("http://x", "rp_t", http=True, port=port))
        try:
            for _ in range(50):
                await asyncio.sleep(0.1)
                try:
                    async with httpx.AsyncClient() as client:
                        resp = await client.get(f"http://127.0.0.1:{port}/mcp")
                    break
                except httpx.ConnectError:
                    continue
            else:
                pytest.fail("MCP HTTP server never came up")
            assert resp.status_code < 500
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, SystemExit):
                await task
