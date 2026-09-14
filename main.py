"""
Listings API — płatne mikro-API (scraper-as-API) gotowe pod RapidAPI.

Źródło danych: publiczne, bezkluczowe API CheapShark (oferty gier).
Zwraca znormalizowane oferty. Plan/tier oraz limity sygnalizowane w nagłówkach.
"""

from __future__ import annotations

import os
import time

from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse

from scraper import GameDealsClient, ListingsError
from scraper.models import ListingsResponse

APP_VERSION = "1.0.0"
SOURCE_NAME = "cheapshark"

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


@app.get("/listings", response_model=ListingsResponse, tags=["listings"])
def listings(
    request: Request,
    query: str = Query(
        "", description="Fraza wyszukiwania (np. 'zelda'). Pusta = top deals."
    ),
    limit: int = Query(20, ge=1, le=60, description="Maks. liczba wyników (1-60)."),
):
    """
    Zwraca znormalizowaną listę ofert dla zapytania.

    Każdy rekord ma pola: **title, price, currency, url, location, image, posted_at**.
    - `price`/`currency` mogą być `null`, gdy źródło nie podaje ceny.
    - `posted_at` w formacie ISO-8601 (UTC).

    Nagłówki odpowiedzi:
    - `X-Plan` — wykryty plan (FREE/PRO/ULTRA),
    - `X-Plan-Quota` — miesięczny limit żądań w planie (placeholder),
    - `X-Response-Time-ms` — czas obsługi żądania.
    """
    started = time.perf_counter()
    plan = _plan_from_request(request)

    results = client.search_listings(query=query, limit=limit)
    payload = ListingsResponse(
        query=query, count=len(results), source=SOURCE_NAME, results=results
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
