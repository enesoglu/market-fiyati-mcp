"""Exercise the real stdio entrypoint and MCP handshake without provider traffic."""

import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def test_stdio_handshake_and_tool_discovery():
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "market_fiyati_mcp"],
        env={"PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")},
    )
    async with stdio_client(parameters) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            initialized = await session.initialize()
            assert initialized.server_info.name == "Market Fiyatı"
            result = await session.list_tools()
            assert {tool.name for tool in result.tools} == {
                "search_products",
                "find_product",
                "find_similar_products",
            }
