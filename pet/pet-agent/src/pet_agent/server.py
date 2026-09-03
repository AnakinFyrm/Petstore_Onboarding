"""MCP server for pet-agent.

Tools are plain typed functions: the docstring and signature are what the client
model sees, so both are part of the interface. Keep them small, pure and
individually testable, and put anything that talks to the outside world behind a
function you can substitute in tests.
"""

import hashlib

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("pet-agent")


@mcp.tool()
def word_count(text: str) -> dict[str, int]:
    """Count the characters, words and lines in a piece of text."""
    return {
        "characters": len(text),
        "words": len(text.split()),
        "lines": len(text.splitlines()) or (1 if text else 0),
    }


@mcp.tool()
def sha256_checksum(text: str) -> str:
    """Return the hex SHA-256 checksum of ``text`` encoded as UTF-8."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def main() -> None:
    """Run the MCP server over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
