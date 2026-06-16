"""Smoke test for MCPClientManager using a local mock MCP server.

Run from the repository root:

    python server/mcp/test_manager.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

if __package__ is None or __package__ == "":
    sys.path.append(str(Path(__file__).resolve().parents[2]))

from server.mcp.manager import MCPClientManager


async def main() -> None:
    manager = MCPClientManager(operation_timeout=60)
    session_id: str | None = None
    mock_server = Path(__file__).resolve().parents[1] / "tests" / "mock_mcp_server.py"
    try:
        session_id = await manager.connect([sys.executable, str(mock_server)])
        tools = await manager.list_tools(session_id)
        tool_names = {tool.name for tool in tools}
        if "fetch" not in tool_names:
            raise AssertionError(f"fetch tool not found: {sorted(tool_names)}")

        result = await manager.call_tool(
            session_id,
            "fetch",
            {"url": "https://example.com"},
        )
        text = "\n".join(
            getattr(content, "text", "") for content in result.content
        )
        if "Example Domain" not in text:
            raise AssertionError("fetch result did not contain Example Domain")
    finally:
        if session_id is not None:
            await manager.disconnect(session_id)
        await manager.close_all()

    print("OK")


if __name__ == "__main__":
    asyncio.run(main())
