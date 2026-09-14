"""
Testy API (pytest + httpx via fastapi.testclient).

Źródło (CheapShark) jest mockowane na poziomie httpx.Client.get, więc testy
nie wychodzą do sieci, a mimo to przechodzą przez pełny stack: retry, throttle,
normalizację, cache, sortowanie i paginację.
"""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

import main
from scraper.client import GameDealsClient

# Przykładowa surowa odpowiedź /deals ze źródła (fragment realnego schematu CheapShark).
FAKE_DEALS = [
    {
        "dealID": "d1",
        "title": "Alpha Game",
        "salePrice": "9.99",
        "thumb": "https://img/1.jpg",
        "storeID": "1",
        "releaseDate": 1609459200,
    },
    {
        "dealID": "d2",
        "title": "Bravo Game",
        "salePrice": "4.50",
        "thumb": "https://img/2.jpg",
        "storeID": "1",
        "releaseDate": 1609459200,
    },
    {
        "dealID": "d3",
        "title": "Charlie Game",
        "salePrice": "19.00",
        "thumb": "https://img/3.jpg",
        "storeID": "7",
        "releaseDate": 1609459200,
    },
]

FAKE_STORES = [
    {"storeID": "1", "storeName": "Steam", "isActive": 1},
    {"storeID": "7", "storeName": "GOG", "isActive": 1},
]


def _make_get(deals=FAKE_DEALS, deals_status=200):
    """Buduje fake dla httpx.Client.get zwracający dane zależnie od ścieżki."""

    def _fake_get(url, params=None):
        request = httpx.Request("GET", url)
        if url.endswith("/stores"):
            return httpx.Response(200, json=FAKE_STORES, request=request)
        if url.endswith("/deals"):
            if deals_status != 200:
                return httpx.Response(
                    deals_status, text="upstream boom", request=request
                )
            # Symulacja stronicowania: druga strona i dalej są puste.
            page = (params or {}).get("pageNumber", 0)
            body = deals if page == 0 else []
            return httpx.Response(200, json=body, request=request)
        return httpx.Response(404, json={}, request=request)

    return _fake_get


@pytest.fixture
def client_stub(monkeypatch):
    """Neutralizuje throttling/backoff i czyści cache przed każdym testem."""
    main.client.min_interval_s = 0.0
    main.client.clear_cache()
    monkeypatch.setattr(GameDealsClient, "_sleep_backoff", staticmethod(lambda a: None))
    return main.client


@pytest.fixture
def api(client_stub):
    return TestClient(main.app)


def test_health(api):
    r = api.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["source"] == "cheapshark"
    assert "version" in body


def test_sources(api):
    r = api.get("/sources")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] >= 1
    ids = [s["id"] for s in body["sources"]]
    assert "cheapshark" in ids


def test_listings_happy_path(api, monkeypatch):
    monkeypatch.setattr(main.client._client, "get", _make_get())
    r = api.get("/listings?query=game&limit=10")
    assert r.status_code == 200
    body = r.json()
    # Wsteczna kompatybilność: istniejące pola nadal obecne.
    assert body["query"] == "game"
    assert body["source"] == "cheapshark"
    assert body["count"] == 3
    assert len(body["results"]) == 3
    first = body["results"][0]
    for key in ("title", "price", "currency", "url", "location", "image", "posted_at"):
        assert key in first
    assert first["currency"] == "USD"
    assert first["location"] == "Steam"
    # Nagłówki planu zachowane.
    assert r.headers["X-Plan"] == "FREE"
    assert r.headers["X-Plan-Quota"] == "100"
    assert "X-Response-Time-ms" in r.headers
    assert r.headers["X-Data-Source"].startswith("CheapShark")


def test_listings_empty_query(api, monkeypatch):
    monkeypatch.setattr(main.client._client, "get", _make_get())
    r = api.get("/listings?query=")
    assert r.status_code == 200
    body = r.json()
    assert body["query"] == ""
    assert body["count"] == 3


def test_listings_limit_over_100_returns_422(api):
    r = api.get("/listings?limit=101")
    assert r.status_code == 422


def test_listings_sort_price_asc(api, monkeypatch):
    monkeypatch.setattr(main.client._client, "get", _make_get())
    r = api.get("/listings?sort=price_asc&limit=10")
    assert r.status_code == 200
    prices = [x["price"] for x in r.json()["results"]]
    assert prices == sorted(prices)
    assert r.json()["sort"] == "price_asc"


def test_listings_sort_price_desc(api, monkeypatch):
    monkeypatch.setattr(main.client._client, "get", _make_get())
    r = api.get("/listings?sort=price_desc&limit=10")
    assert r.status_code == 200
    prices = [x["price"] for x in r.json()["results"]]
    assert prices == sorted(prices, reverse=True)


def test_listings_invalid_sort_returns_422(api):
    r = api.get("/listings?sort=banana")
    assert r.status_code == 422


def test_listings_offset_pagination(api, monkeypatch):
    monkeypatch.setattr(main.client._client, "get", _make_get())
    r = api.get("/listings?sort=price_asc&limit=1&offset=1")
    assert r.status_code == 200
    body = r.json()
    assert body["offset"] == 1
    assert body["limit"] == 1
    assert body["count"] == 1
    # price_asc: [4.50, 9.99, 19.00] -> offset 1 -> 9.99
    assert body["results"][0]["price"] == 9.99


def test_listings_source_5xx_returns_502(api, monkeypatch):
    monkeypatch.setattr(main.client._client, "get", _make_get(deals_status=500))
    main.client.max_retries = 2
    r = api.get("/listings?query=x")
    assert r.status_code == 502
    body = r.json()
    assert body["error"] == "source_unavailable"
    assert "detail" in body


def test_listings_source_timeout_returns_502(api, monkeypatch):
    def _timeout_get(url, params=None):
        raise httpx.ConnectTimeout("boom", request=httpx.Request("GET", url))

    monkeypatch.setattr(main.client._client, "get", _timeout_get)
    main.client.max_retries = 2
    r = api.get("/listings?query=x")
    assert r.status_code == 502
    assert r.json()["error"] == "source_unavailable"


def test_cache_avoids_second_source_call(api, monkeypatch):
    calls = {"deals": 0}
    base = _make_get()

    def _counting_get(url, params=None):
        if url.endswith("/deals"):
            calls["deals"] += 1
        return base(url, params)

    monkeypatch.setattr(main.client._client, "get", _counting_get)
    api.get("/listings?query=cachetest&limit=5")
    first = calls["deals"]
    assert first >= 1
    api.get("/listings?query=cachetest&limit=5")
    # Drugie zapytanie serwowane z cache -> brak dodatkowego wywołania /deals.
    assert calls["deals"] == first
