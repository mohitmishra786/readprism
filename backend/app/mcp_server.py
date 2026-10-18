"""ReadPrism MCP server (EC-04), on the official MCP SDK.

Run (stdio, the default):
    python -m app.mcp_server --api-base http://localhost:8000 --token rp_...

Run (streamable HTTP):
    python -m app.mcp_server --http --port 8001 --token rp_...

Tools call the ReadPrism API with the given token; the token's scopes decide
what is possible: a read-only token disables the write tools (`add_source`,
`record_feedback`) — they are not even advertised in tools/list.

The wire protocol (JSON-RPC framing, initialize handshake, stdio and HTTP
transports) is owned by the official `mcp` SDK (#262); this module keeps the
API mapping and the scope rules, plus a legacy `handle()` dict shim so the
existing tests and embedders keep working.
"""

from __future__ import annotations

import argparse
import asyncio
from typing import Any

import httpx
from mcp.server.mcpserver import MCPServer

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "readprism"
SERVER_VERSION = "1.0.0"

READ_TOOLS = ("get_digest", "search_archive", "list_sources", "explain_item")
WRITE_TOOLS = ("add_source", "record_feedback")


class ReadPrismMcpServer:
    """Tool implementations against the ReadPrism API, plus a legacy shim."""

    def __init__(self, api_base: str, token: str, client: httpx.AsyncClient | None = None):
        self.api_base = api_base.rstrip("/")
        self.token = token
        self._client = client
        self.write_scope = True  # corrected after the first API call
        self._sdk: MCPServer | None = None

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

    # ------------------------------------------------------------------
    # Official SDK wiring (#262).
    # ------------------------------------------------------------------

    def _register_tools(self, sdk: MCPServer) -> None:
        server = self

        async def get_digest() -> Any:
            return await server.call_tool("get_digest", {})

        async def search_archive(query: str, limit: int = 10) -> Any:
            return await server.call_tool("search_archive", {"query": query, "limit": limit})

        async def list_sources() -> Any:
            return await server.call_tool("list_sources", {})

        async def explain_item(content_item_id: str) -> Any:
            return await server.call_tool("explain_item", {"content_item_id": content_item_id})

        for name, fn, description in (
            (
                "get_digest",
                get_digest,
                "Return the user's latest digest with sections and item summaries.",
            ),
            (
                "search_archive",
                search_archive,
                "Hybrid full-text + semantic search over the user's archive.",
            ),
            ("list_sources", list_sources, "List the user's active sources with health status."),
            (
                "explain_item",
                explain_item,
                "Explain why an item ranked the way it did (signal contributions).",
            ),
        ):
            sdk.add_tool(fn, name=name, description=description)

        if self.write_scope:

            async def add_source(url: str) -> Any:
                return await server.call_tool("add_source", {"url": url})

            async def record_feedback(
                content_item_id: str, rating: int | None = None, saved: bool | None = None
            ) -> Any:
                arguments: dict = {"content_item_id": content_item_id}
                if rating is not None:
                    arguments["rating"] = rating
                if saved is not None:
                    arguments["saved"] = saved
                return await server.call_tool("record_feedback", arguments)

            sdk.add_tool(
                add_source,
                name="add_source",
                description="Subscribe the user to a feed/site URL (write scope).",
            )
            sdk.add_tool(
                record_feedback,
                name="record_feedback",
                description="Rate or save a content item: strong learning signal (write scope).",
            )

    def sdk_server(self) -> MCPServer:
        """The official-SDK server for this token (cached; scope fixed)."""
        if self._sdk is None:
            sdk = MCPServer(name=SERVER_NAME, version=SERVER_VERSION)
            self._register_tools(sdk)
            self._sdk = sdk
        return self._sdk

    # ------------------------------------------------------------------
    # Legacy dict shim: kept so existing tests and embedders that pass raw
    # JSON-RPC dicts keep working. Production transports (stdio + HTTP) use
    # the SDK's protocol engine below.
    # ------------------------------------------------------------------

    async def _sdk_tools(self) -> list[dict]:
        tools = await self.sdk_server().list_tools()
        return [tool.model_dump(by_alias=True, exclude_none=True) for tool in tools]

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
                    "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                },
            }
        if method == "notifications/initialized":
            return None  # notification: no response
        if method == "ping":
            return {"jsonrpc": "2.0", "id": req_id, "result": {}}
        if method == "tools/list":
            return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": await self._sdk_tools()}}
        if method == "tools/call":
            name = params.get("name", "")
            try:
                result = await self.sdk_server().call_tool(name, params.get("arguments") or {})
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": result.model_dump(by_alias=True, exclude_none=True),
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


async def serve(api_base: str, token: str, http: bool = False, port: int = 8001) -> None:
    server = ReadPrismMcpServer(api_base, token)
    await server.detect_scope()
    if http:
        import uvicorn

        app = server.sdk_server().streamable_http_app()
        uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
        return
    # stdio: the official SDK owns the JSON-RPC session on stdin/stdout.
    await server.sdk_server().run_stdio_async()


def main() -> None:
    parser = argparse.ArgumentParser(description="ReadPrism MCP server (official SDK)")
    parser.add_argument("--api-base", default="http://localhost:8000")
    parser.add_argument("--token", required=True, help="ReadPrism API token (rp_...)")
    parser.add_argument(
        "--http", action="store_true", help="serve the streamable-HTTP transport instead of stdio"
    )
    parser.add_argument("--port", type=int, default=8001, help="port for --http mode")
    args = parser.parse_args()
    asyncio.run(serve(args.api_base, args.token, http=args.http, port=args.port))


if __name__ == "__main__":
    main()
