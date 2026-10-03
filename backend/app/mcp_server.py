"""Minimal MCP server over stdio (EC-04).

Run:
    python -m app.mcp_server --api-base http://localhost:8000 --token rp_...

Speaks JSON-RPC 2.0 (newline-delimited) on stdin/stdout and exposes the
ReadPrism API as MCP tools. The token's scopes decide what is possible:
a read-only token disables the write tools (`add_source`,
`record_feedback`) — they are not even advertised in tools/list.

No third-party SDK: the MCP wire format needed here is initialize /
tools/list / tools/call, which this implements directly.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any

import httpx

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "readprism", "version": "1.0.0"}


def tool_definitions(write_scope: bool) -> list[dict]:
    tools = [
        {
            "name": "get_digest",
            "description": "Return the user's latest digest with sections and item summaries.",
            "inputSchema": {"type": "object", "properties": {}, "required": []},
        },
        {
            "name": "search_archive",
            "description": "Hybrid full-text + semantic search over the user's archive.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "default": 10},
                },
                "required": ["query"],
            },
        },
        {
            "name": "list_sources",
            "description": "List the user's active sources with health status.",
            "inputSchema": {"type": "object", "properties": {}, "required": []},
        },
        {
            "name": "explain_item",
            "description": "Explain why an item ranked the way it did (signal contributions).",
            "inputSchema": {
                "type": "object",
                "properties": {"content_item_id": {"type": "string"}},
                "required": ["content_item_id"],
            },
        },
    ]
    if write_scope:
        tools += [
            {
                "name": "add_source",
                "description": "Subscribe the user to a feed/site URL (write scope).",
                "inputSchema": {
                    "type": "object",
                    "properties": {"url": {"type": "string"}},
                    "required": ["url"],
                },
            },
            {
                "name": "record_feedback",
                "description": "Rate or save a content item: strong learning signal (write scope).",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "content_item_id": {"type": "string"},
                        "rating": {"type": "integer", "enum": [1, -1]},
                        "saved": {"type": "boolean"},
                    },
                    "required": ["content_item_id"],
                },
            },
        ]
    return tools


class ReadPrismMcpServer:
    def __init__(self, api_base: str, token: str, client: httpx.AsyncClient | None = None):
        self.api_base = api_base.rstrip("/")
        self.token = token
        self._client = client
        self.write_scope = True  # corrected after the first API call

    async def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.api_base,
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=30,
            )
        return self._client

    async def _api(self, method: str, path: str, json_body: dict | None = None) -> Any:
        client = await self._http()
        resp = await client.request(method, path, json=json_body)
        if resp.status_code == 403:
            raise PermissionError("token lacks the write scope")
        resp.raise_for_status()
        return resp.json() if resp.content else None

    async def detect_scope(self) -> None:
        """Probe once whether the token can write: a mutation with an invalid
        body returns 422 for write tokens but 403 for read-only tokens."""
        try:
            await self._api("POST", "/api/v1/sources", {"url": ""})
        except PermissionError:
            self.write_scope = False
        except httpx.HTTPStatusError:
            self.write_scope = True  # 422 reached validation => write allowed
        except Exception:
            self.write_scope = True

    async def call_tool(self, name: str, arguments: dict) -> Any:
        from urllib.parse import quote

        if name == "get_digest":
            return await self._api("GET", "/api/v1/digest/latest")
        if name == "search_archive":
            query = quote(arguments.get("query", ""), safe="")
            limit = int(arguments.get("limit", 10))
            return await self._api("GET", f"/api/v1/search?q={query}&limit={limit}")
        if name == "list_sources":
            return await self._api("GET", "/api/v1/sources")
        if name == "explain_item":
            item_id = quote(str(arguments.get("content_item_id", "")), safe="")
            return await self._api("GET", f"/api/v1/content/{item_id}")
        if name == "add_source":
            if not self.write_scope:
                raise PermissionError("add_source requires a write-scoped token")
            return await self._api("POST", "/api/v1/sources", {"url": arguments.get("url", "")})
        if name == "record_feedback":
            if not self.write_scope:
                raise PermissionError("record_feedback requires a write-scoped token")
            body: dict = {"content_item_id": arguments.get("content_item_id", "")}
            if "rating" in arguments:
                body["explicit_rating"] = arguments["rating"]
            if "saved" in arguments:
                body["saved"] = arguments["saved"]
            return await self._api("POST", "/api/v1/feedback/interaction", body)
        raise ValueError(f"unknown tool: {name}")

    async def handle(self, request: dict) -> dict | None:
        method = request.get("method")
        req_id = request.get("id")
        params = request.get("params") or {}

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {"tools": {}},
                    "serverInfo": SERVER_INFO,
                },
            }
        if method == "notifications/initialized":
            return None  # notification: no response
        if method == "ping":
            return {"jsonrpc": "2.0", "id": req_id, "result": {}}
        if method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"tools": tool_definitions(self.write_scope)},
            }
        if method == "tools/call":
            name = params.get("name", "")
            try:
                result = await self.call_tool(name, params.get("arguments") or {})
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [
                            {"type": "text", "text": json.dumps(result, default=str)[:60000]}
                        ]
                    },
                }
            except Exception as e:  # tool errors are results, not protocol errors
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "isError": True,
                        "content": [{"type": "text", "text": str(e)}],
                    },
                }
        if req_id is not None:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": "method not found"},
            }
        return None


async def serve(api_base: str, token: str) -> None:
    server = ReadPrismMcpServer(api_base, token)
    await server.detect_scope()
    loop = asyncio.get_running_loop()
    while True:
        line = await loop.run_in_executor(None, sys.stdin.readline)
        if not line:
            break
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            continue
        response = await server.handle(request)
        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()


def main() -> None:
    parser = argparse.ArgumentParser(description="ReadPrism MCP server (stdio)")
    parser.add_argument("--api-base", default="http://localhost:8000")
    parser.add_argument("--token", required=True, help="ReadPrism API token (rp_...)")
    args = parser.parse_args()
    asyncio.run(serve(args.api_base, args.token))


if __name__ == "__main__":
    main()
