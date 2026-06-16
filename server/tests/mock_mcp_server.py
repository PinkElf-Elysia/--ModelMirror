"""Local stdio MCP server used by integration tests."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

app = FastMCP("modelmirror-test-mcp")


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


if __name__ == "__main__":
    app.run()
