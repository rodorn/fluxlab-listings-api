"""
Listings API — płatne mikro-API (scraper-as-API) gotowe pod RapidAPI.

Źródło danych: publiczne, bezkluczowe API CheapShark (oferty gier).
Zwraca znormalizowane oferty. Plan/tier oraz limity sygnalizowane w nagłówkach.
"""

from __future__ import annotations

import os
import time

from typing import Optional

from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse

from scraper import GameDealsClient, ListingsError
from scraper.models import (
    ListingsResponse,
    SourceInfo,
    SourcesResponse,
)

APP_VERSION = "1.1.0"
SOURCE_NAME = "cheapshark"

# Rejestr dostępnych źródeł danych (na razie jedno; endpoint /sources je eksponuje).
SOURCES = [
    SourceInfo(
        id="cheapshark",
        name="CheapShark",
        url="https://www.cheapshark.com",
        attribution_required=True,
        description="Agregator promocji na gry PC (Steam, GOG, Epic i inne sklepy).",
    ),
]

# Dozwolone wartości sortowania (walidowane przez FastAPI -> błędne dają 422).
ALLOWED_SORT = ("price_asc", "price_desc")

# Placeholder limitów per plan (RapidAPI egzekwuje realne limity po swojej stronie;
# tu tylko deklarujemy tier w nagłówkach dla klienta).
PLAN_LIMITS = {
    "FREE": 100,
    "PRO": 10000,
    "ULTRA": 200000,
}

app = FastAPI(
    title="Listings API — Game Deals",
    version=APP_VERSION,
    description=(
        "Znormalizowane oferty (listings) z publicznego źródła. "
        "Jeden spójny schemat: title, price, currency, url, location, image, posted_at. "
        "Dane pochodzą z CheapShark (https://www.cheapshark.com) — źródło wymagające atrybucji."
    ),
    contact={"name": "Listings API"},
)

client = GameDealsClient()


def _plan_from_request(request: Request) -> str:
    # RapidAPI wstrzykuje nagłówek X-RapidAPI-Subscription z nazwą planu.
    plan = (
        request.headers.get("X-RapidAPI-Subscription")
        or request.headers.get("X-Plan")
        or os.getenv("DEFAULT_PLAN", "FREE")
    ).upper()
    return plan if plan in PLAN_LIMITS else "FREE"


@app.exception_handler(ListingsError)
async def listings_error_handler(request: Request, exc: ListingsError):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": "source_unavailable", "detail": str(exc)},
    )


@app.get("/health", tags=["meta"])
def health():
    """Health check. Zwraca status usługi i wersję. Nie odpytuje źródła."""
    return {"status": "ok", "version": APP_VERSION, "source": SOURCE_NAME}


@app.get("/sources", response_model=SourcesResponse, tags=["meta"])
def sources():
    """Lista dostępnych źródeł danych, z których API buduje listingi."""
    return SourcesResponse(count=len(SOURCES), sources=SOURCES)


def _apply_sort(results: list, sort: Optional[str]) -> list:
    if not sort:
        return results
    reverse = sort == "price_desc"
    # Rekordy bez ceny (None) zawsze na końcu, niezależnie od kierunku.
    with_price = [r for r in results if r.price is not None]
    without_price = [r for r in results if r.price is None]
    with_price.sort(key=lambda r: r.price, reverse=reverse)
    return with_price + without_price


@app.get("/listings", response_model=ListingsResponse, tags=["listings"])
def listings(
    request: Request,
    query: str = Query(
        "", description="Fraza wyszukiwania (np. 'zelda'). Pusta = top deals."
    ),
    limit: int = Query(20, ge=1, le=100, description="Maks. liczba wyników (1-100)."),
    offset: int = Query(
        0, ge=0, le=1000, description="Przesunięcie (paginacja). 0 = od początku."
    ),
    sort: Optional[str] = Query(
        None,
        description="Sortowanie po cenie: 'price_asc' lub 'price_desc'. Brak = kolejność źródła.",
        pattern="^(price_asc|price_desc)$",
    ),
):
    """
    Zwraca znormalizowaną listę ofert dla zapytania.

    Każdy rekord ma pola: **title, price, currency, url, location, image, posted_at**.
    - `price`/`currency` mogą być `null`, gdy źródło nie podaje ceny.
    - `posted_at` w formacie ISO-8601 (UTC).

    Parametry:
    - `query` — fraza (pusta = top deals),
    - `limit` — liczba wyników 1-100,
    - `offset` — przesunięcie do paginacji (0-1000),
    - `sort` — `price_asc` / `price_desc` (opcjonalne).

    Nagłówki odpowiedzi:
    - `X-Plan` — wykryty plan (FREE/PRO/ULTRA),
    - `X-Plan-Quota` — miesięczny limit żądań w planie (placeholder),
    - `X-Response-Time-ms` — czas obsługi żądania.
    """
    started = time.perf_counter()
    plan = _plan_from_request(request)

    # Pobieramy okno offset+limit; zapytania do źródła są cache'owane (TTL) po stronie klienta.
    window = client.search_listings(query=query, want=offset + limit)
    total_available = len(window)
    window = _apply_sort(window, sort)
    results = window[offset : offset + limit]

    payload = ListingsResponse(
        query=query,
        count=len(results),
        source=SOURCE_NAME,
        results=results,
        offset=offset,
        limit=limit,
        sort=sort,
        total_available=total_available,
    )

    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    headers = {
        "X-Plan": plan,
        "X-Plan-Quota": str(PLAN_LIMITS[plan]),
        "X-Response-Time-ms": str(elapsed_ms),
        "X-Data-Source": "CheapShark (https://www.cheapshark.com)",
    }
    return JSONResponse(content=payload.model_dump(), headers=headers)


@app.on_event("shutdown")
def _shutdown():
    client.close()
