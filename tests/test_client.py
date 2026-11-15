import asyncio

import httpx
import pytest

from market_fiyati_mcp.client import MarketClient, MarketError, location

FIXTURE = {
    "numberOfFound": 1,
    "searchResultType": 1,
    "content": [
        {
            "id": "p1",
            "title": "Süt 1 L",
            "brand": "Example",
            "refinedVolumeOrWeight": "1",
            "refinedQuantityUnit": "L",
            "productDepotInfoList": [
                {
                    "depotId": "a",
                    "depotName": "Store A",
                    "marketAdi": "A",
                    "price": 45.9,
                    "unitPrice": "45.90 ₺/L",
                    "latitude": 41,
                    "longitude": 29,
                    "indexTime": "2026-11-15",
                },
                {"depotId": "b", "depotName": "Store B", "marketAdi": "B", "price": 39.5},
            ],
        }
    ],
}


@pytest.fixture
def payload():
    import copy

    return copy.deepcopy(FIXTURE)


@pytest.mark.parametrize(
    "args",
    [
        (0, None, 1000),
        (91, 0, 1000),
        (0, 181, 1000),
        (0, 0, 99),
        (0, 0, 50001),
        (float("nan"), 0, 1000),
    ],
)
def test_invalid_locations(args):
    with pytest.raises(ValueError):
        location(*args)


async def test_cache_provenance_sorting_and_expiry(payload):
    now = [0]
    calls = []

    def upstream(request):
        calls.append(request)
        return httpx.Response(200, json=payload)

    client = MarketClient(transport=httpx.MockTransport(upstream), clock=lambda: now[0])
    try:
        result = await client.search(" süt ")
        assert not result["cached"]
        assert result["products"][0]["offers"][0]["price"] == "39.5"
        again = await client.search("süt")
        assert again["cached"] and again["fetched_at"] == result["fetched_at"]
        assert len(calls) == 1
        now[0] = 121
        assert not (await client.search("süt"))["cached"]
        assert len(calls) == 2
    finally:
        await client.close()


async def test_simultaneous_identical_requests_coalesce(payload):
    calls = []

    async def upstream(request):
        calls.append(request)
        await asyncio.sleep(0.01)
        return httpx.Response(200, json=payload)

    client = MarketClient(transport=httpx.MockTransport(upstream))
    try:
        results = await asyncio.gather(*(client.search("süt") for _ in range(10)))
        assert len(calls) == 1
        assert sum(not r["cached"] for r in results) == 1
    finally:
        await client.close()


@pytest.mark.parametrize("status", [400, 403, 429, 500])
async def test_http_errors_are_errors_not_empty_results(status):
    client = MarketClient(transport=httpx.MockTransport(lambda _: httpx.Response(status)))
    try:
        with pytest.raises(MarketError):
            await client.search("süt")
        assert not client.cache
    finally:
        await client.close()


async def test_transient_failure_retries_once(payload):
    calls = []

    def upstream(request):
        calls.append(request)
        return httpx.Response(503) if len(calls) == 1 else httpx.Response(200, json=payload)

    client = MarketClient(transport=httpx.MockTransport(upstream))
    try:
        assert (await client.search("süt"))["products"]
        assert len(calls) == 2
    finally:
        await client.close()


async def test_network_error_is_bounded():
    calls = []

    def upstream(request):
        calls.append(request)
        raise httpx.ConnectError("sensitive internal details", request=request)

    client = MarketClient(transport=httpx.MockTransport(upstream))
    try:
        with pytest.raises(MarketError, match="could not be reached") as error:
            await client.search("süt")
        assert "sensitive" not in str(error.value)
        assert len(calls) == 2
    finally:
        await client.close()


@pytest.mark.parametrize("body", [b"not json", b"[]", b"{}", b"x" * 1_048_577])
async def test_invalid_or_oversized_response(body):
    client = MarketClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=body))
    )
    try:
        with pytest.raises(MarketError):
            await client.search("süt")
    finally:
        await client.close()


async def test_empty_search_is_distinct_from_provider_failure():
    client = MarketClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json={"content": [], "numberOfFound": 0})
        )
    )
    try:
        result = await client.search("nonexistent")
        assert result["products"] == [] and result["total_matches_reported"] == 0
    finally:
        await client.close()


async def test_location_cache_keys_and_budget(payload):
    client = MarketClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload))
    )
    try:
        assert not (await client.search("süt", 41, 29, 1000))["cached"]
        assert not (await client.search("süt", 42, 29, 1000))["cached"]
        for index in range(28):
            await client.search(f"query-{index}")
        with pytest.raises(MarketError, match="budget"):
            await client.search("one-too-many")
        assert (await client.search("süt", 41, 29, 1000))["cached"]
    finally:
        await client.close()


async def test_endpoint_contract_and_bounded_output(payload):
    import json

    calls = []

    def upstream(request):
        calls.append((request.url.path, json.loads(request.content)))
        return httpx.Response(200, json=payload)

    payload["content"] *= 25
    payload["numberOfFound"] = 100
    client = MarketClient(transport=httpx.MockTransport(upstream))
    try:
        result = await client.by_identity("123", "barcode", limit=1)
        assert calls[-1] == (
            "/api/v2/searchByIdentity",
            {"identity": "123", "identityType": "barcode"},
        )
        assert result["truncated"] and len(result["products"]) == 1
        await client.similar("p1", "süt")
        assert calls[-1][0].endswith("/searchSmilarProduct")
        with pytest.raises(ValueError):
            await client.by_identity("1", "anything")
        with pytest.raises(ValueError):
            await client.search("süt", limit=26)
    finally:
        await client.close()


async def test_invalid_price_fails_explicitly(payload):
    payload["content"][0]["productDepotInfoList"][0]["price"] = "NaN"
    client = MarketClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload))
    )
    try:
        with pytest.raises(MarketError, match="invalid price"):
            await client.search("süt")
    finally:
        await client.close()
