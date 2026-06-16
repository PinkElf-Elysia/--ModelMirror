"""Local stdio MCP server used by integration tests."""

from __future__ import annotations

import sys

from mcp.server.fastmcp import FastMCP

LABEL = sys.argv[1] if len(sys.argv) > 1 else "default"
app = FastMCP(f"modelmirror-test-mcp-{LABEL}")


@app.tool()
def echo(text: str) -> str:
    """Return the provided text with an echo prefix."""

    return f"echo: {text}"


@app.tool()
def fetch(url: str) -> str:
    """Return deterministic content for smoke testing."""

    if url == "https://example.com":
        return "<html><title>Example Domain</title><body>Example Domain</body></html>"
    return f"Mock fetch response for {url}"


@app.tool(name=f"marker_{LABEL}")
def marker() -> str:
    """Return this mock server label."""

    return LABEL


if __name__ == "__main__":
    app.run()
