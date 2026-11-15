"""MCP adapters; the client owns all price and upstream behavior."""

from mcp.types import ToolAnnotations

from .client import MarketClient

READ = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=True,
)


def register_tools(mcp, client: MarketClient):
    @mcp.tool(annotations=READ)
    async def search_products(
        keywords: str,
        latitude: float | None = None,
        longitude: float | None = None,
        distance: int | None = None,
        limit: int = 10,
    ) -> dict:
        """Search Turkish grocery products. Optional location requires all three fields;
        distance is in meters (100–50000). Returns up to 25 products and 20 cheapest
        returned offers per product, TRY prices, provenance and truncation flags.
        Results are provider snapshots, not guaranteed checkout prices. Do not invent a location."""
        return await client.search(keywords, latitude, longitude, distance, limit)

    @mcp.tool(annotations=READ)
    async def find_product(
        identity: str,
        identity_type: str = "id",
        latitude: float | None = None,
        longitude: float | None = None,
        distance: int | None = None,
        limit: int = 10,
    ) -> dict:
        """Find by provider product ID or barcode. Set identity_type to id or barcode.
        A barcode match is distinct from fuzzy name similarity. Optional distance is
        in meters and requires latitude and longitude. Upstream errors are not empty results."""
        return await client.by_identity(
            identity, identity_type, latitude, longitude, distance, limit
        )

    @mcp.tool(annotations=READ)
    async def find_similar_products(
        product_id: str,
        keywords: str,
        latitude: float | None = None,
        longitude: float | None = None,
        distance: int | None = None,
        limit: int = 10,
    ) -> dict:
        """Find provider-suggested alternatives to a provider product ID.
        Alternatives are not exact product matches. Compare quantities and units before
        comparing prices. Optional distance is in meters and requires both coordinates."""
        return await client.similar(product_id, keywords, latitude, longitude, distance, limit)
