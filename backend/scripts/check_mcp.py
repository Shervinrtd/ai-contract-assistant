"""Smoke-test the MCP server from Python, without the MCP Inspector.

Start the server first (`python -m mcp_server`), then run from the backend folder:
    python -m scripts.check_mcp
"""

from __future__ import annotations

import asyncio
import json
import sys

from app import config
from app.mcp_client import MCPUnavailable, mcp_session, result_payload

CALLS = [
    ("search_contracts", {"query": "Helix"}),
    ("search_contracts", {"status": "Expired"}),
    ("get_upcoming_expirations", {"days": 30}),
    ("get_upcoming_expirations", {"days": 90}),
    ("get_upcoming_expirations", {"days": -5}),  # invalid on purpose: should be rejected
]


async def main() -> int:
    print(f"Connecting to {config.MCP_SERVER_URL}")
    try:
        async with mcp_session() as session:
            tools = (await session.list_tools()).tools
            print(f"\n{len(tools)} tools available:")
            for tool in tools:
                params = ", ".join(tool.inputSchema.get("properties", {}))
                print(f"  - {tool.name}({params}): {tool.description.splitlines()[0]}")

            for name, args in CALLS:
                result = await session.call_tool(name, args)
                print(f"\n> {name}({', '.join(f'{k}={v!r}' for k, v in args.items())})")
                if result.isError:
                    print("  rejected:", " ".join(c.text for c in result.content if hasattr(c, "text"))[:200])
                    continue
                payload = result_payload(result)
                for c in payload.get("contracts", []):
                    print(f"  {c['id']}  {c['title']:<45} {c['expiration_date']}  "
                          f"{c['status']:<8} {c['days_until_expiration']:>4} days")
                if not payload.get("contracts"):
                    print("  (no contracts)", json.dumps(payload)[:120])
    except MCPUnavailable as exc:
        print(exc, "\nIs the server running? Start it with: python -m mcp_server")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
