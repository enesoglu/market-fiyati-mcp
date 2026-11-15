"""Explicit live smoke: three read-only provider calls, metadata only in output."""

import asyncio
import json

from market_fiyati_mcp.client import MarketClient


async def main():
    client = MarketClient(cache_ttl=0)
    try:
        result = await client.search("süt", limit=1)
        report = {"search": {"matches": result["total_matches_reported"]}}
        if not result["products"]:
            raise RuntimeError("Expected a sample product for the live smoke test.")
        identity = result["products"][0]["id"]
        found = await client.by_identity(identity, limit=1)
        similar = await client.similar(identity, "süt", limit=1)
        report["identity"] = {"matches": found["total_matches_reported"]}
        report["similar"] = {"matches": similar["total_matches_reported"]}
        print(json.dumps(report))
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
