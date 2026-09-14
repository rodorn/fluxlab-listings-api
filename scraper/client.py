"""
Klient scrapujący publiczne, bezkluczowe API CheapShark (oferty gier).

Źródło: https://www.cheapshark.com/api/1.0/deals
ToS: publiczne, darmowe, dozwolone użycie komercyjne z linkiem zwrotnym / atrybucją.
Nie wymaga logowania ani klucza. Dane oddajemy w znormalizowanej formie.

Cechy produkcyjne:
- timeouty (connect + read),
- retry z backoffem na błędy sieciowe / 5xx / 429 (respekt Retry-After),
- ostrożny throttling (min. odstęp między żądaniami),
- konfigurowalny User-Agent,
- opcjonalne proxy przez zmienne środowiskowe (działa też bez proxy),
- cache mapy sklepów (storeID -> nazwa) z krótkim TTL.
"""

from __future__ import annotations

import os
import threading
import time
from datetime import datetime, timezone
from typing import Optional

import httpx

from .models import Listing

CHEAPSHARK_BASE = "https://www.cheapshark.com/api/1.0"
DEFAULT_UA = "rapidapi-listings/1.0 (+https://rapidapi.com; contact via RapidAPI)"


class ListingsError(Exception):
    """Błąd pobierania / parsowania danych ze źródła."""

    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


class GameDealsClient:
    def __init__(
        self,
        base_url: str = CHEAPSHARK_BASE,
        user_agent: Optional[str] = None,
        timeout_connect: float = 5.0,
        timeout_read: float = 12.0,
        max_retries: int = 3,
        min_interval_s: float = 0.34,  # ~3 req/s max, ostrożny throttle
        stores_ttl_s: int = 3600,
        deals_ttl_s: int = 60,
    ):
        self.base_url = base_url.rstrip("/")
        self.user_agent = user_agent or os.getenv("SCRAPER_USER_AGENT") or DEFAULT_UA
        self.timeout = httpx.Timeout(
            connect=timeout_connect,
            read=timeout_read,
            write=timeout_read,
            pool=timeout_connect,
        )
        self.max_retries = max_retries
        self.min_interval_s = min_interval_s
        self.stores_ttl_s = stores_ttl_s
        self.deals_ttl_s = deals_ttl_s
        # CheapShark akceptuje pageSize maksymalnie 60 rekordów na stronę.
        self.source_page_size = 60

        # Proxy opcjonalnie: HTTP_PROXY / HTTPS_PROXY / SCRAPER_PROXY_URL.
        proxy = os.getenv("SCRAPER_PROXY_URL") or None
        client_kwargs: dict = {
            "timeout": self.timeout,
            "headers": {"User-Agent": self.user_agent},
        }
        if proxy:
            client_kwargs["proxy"] = proxy
        # trust_env=True -> honoruje HTTP(S)_PROXY z env, gdy SCRAPER_PROXY_URL nie ustawiono.
        client_kwargs["trust_env"] = True
        self._client = httpx.Client(**client_kwargs)

        self._lock = threading.Lock()
        self._last_request_ts = 0.0
        self._stores_cache: dict[str, str] = {}
        self._stores_cache_ts = 0.0
        # Cache surowych stron ze źródła: klucz -> (timestamp, dane).
        self._deals_cache: dict[tuple, tuple[float, list]] = {}

    def clear_cache(self) -> None:
        """Czyści cache stron ofert (pomocne w testach / przy ręcznym odświeżeniu)."""
        with self._lock:
            self._deals_cache.clear()

    # ---- infrastruktura ----------------------------------------------------

    def _throttle(self) -> None:
        with self._lock:
            elapsed = time.monotonic() - self._last_request_ts
            wait = self.min_interval_s - elapsed
            if wait > 0:
                time.sleep(wait)
            self._last_request_ts = time.monotonic()

    def _get(self, path: str, params: Optional[dict] = None) -> httpx.Response:
        url = f"{self.base_url}/{path.lstrip('/')}"
        last_exc: Optional[Exception] = None
        for attempt in range(self.max_retries):
            self._throttle()
            try:
                resp = self._client.get(url, params=params)
            except httpx.RequestError as exc:
                last_exc = exc
                self._sleep_backoff(attempt)
                continue

            if resp.status_code == 429 or resp.status_code >= 500:
                retry_after = resp.headers.get("Retry-After")
                if retry_after and retry_after.isdigit():
                    time.sleep(min(int(retry_after), 10))
                else:
                    self._sleep_backoff(attempt)
                last_exc = ListingsError(f"upstream {resp.status_code}", 502)
                continue

            if resp.status_code >= 400:
                raise ListingsError(f"upstream client error {resp.status_code}", 502)

            return resp

        if isinstance(last_exc, ListingsError):
            raise last_exc
        raise ListingsError(f"źródło niedostępne (timeout/sieć): {last_exc}", 502)

    @staticmethod
    def _sleep_backoff(attempt: int) -> None:
        # 0.5s, 1s, 2s ...
        time.sleep(0.5 * (2**attempt))

    # ---- mapowanie sklepów --------------------------------------------------

    def _store_name(self, store_id: Optional[str]) -> Optional[str]:
        if store_id is None:
            return None
        now = time.monotonic()
        if not self._stores_cache or (now - self._stores_cache_ts) > self.stores_ttl_s:
            try:
                resp = self._get("stores")
                data = resp.json()
                self._stores_cache = {
                    str(s["storeID"]): s["storeName"]
                    for s in data
                    if s.get("isActive", 1)
                }
                self._stores_cache_ts = now
            except (ListingsError, ValueError, KeyError):
                # brak mapy sklepów nie jest krytyczny
                pass
        return self._stores_cache.get(str(store_id))

    # ---- normalizacja -------------------------------------------------------

    @staticmethod
    def _to_iso(epoch: Optional[int]) -> Optional[str]:
        if not epoch:
            return None
        try:
            return datetime.fromtimestamp(int(epoch), tz=timezone.utc).isoformat()
        except (ValueError, OSError, TypeError):
            return None

    @staticmethod
    def _to_float(value) -> Optional[float]:
        try:
            f = float(value)
            return f
        except (TypeError, ValueError):
            return None

    def _normalize(self, raw: dict) -> Listing:
        deal_id = raw.get("dealID")
        url = (
            f"https://www.cheapshark.com/redirect?dealID={deal_id}"
            if deal_id
            else "https://www.cheapshark.com/"
        )
        posted_at = self._to_iso(raw.get("releaseDate")) or self._to_iso(
            raw.get("lastChange")
        )
        return Listing(
            title=raw.get("title") or "(bez tytułu)",
            price=self._to_float(raw.get("salePrice")),
            currency="USD" if raw.get("salePrice") is not None else None,
            url=url,
            location=self._store_name(raw.get("storeID")),
            image=raw.get("thumb"),
            posted_at=posted_at,
        )

    # ---- API publiczne ------------------------------------------------------

    def _deals_page(self, query: str, page_number: int) -> list:
        """Pobiera pojedynczą stronę ofert ze źródła (z cache TTL).

        Zwraca surową listę słowników z CheapShark dla danej strony.
        """
        q = (query or "").strip()
        key = (q, page_number)
        now = time.monotonic()
        cached = self._deals_cache.get(key)
        if cached and (now - cached[0]) <= self.deals_ttl_s:
            return cached[1]

        params: dict = {
            "pageSize": self.source_page_size,
            "pageNumber": page_number,
            "sortBy": "Deal Rating",
        }
        if q:
            params["title"] = q

        resp = self._get("deals", params=params)
        try:
            data = resp.json()
        except ValueError as exc:
            raise ListingsError(f"niepoprawny JSON ze źródła: {exc}", 502)

        if not isinstance(data, list):
            raise ListingsError("nieoczekiwany format odpowiedzi źródła", 502)

        self._deals_cache[key] = (now, data)
        return data

    def search_listings(self, query: str, want: int = 20) -> list[Listing]:
        """Zwraca znormalizowane oferty pasujące do zapytania.

        query pusty -> najświeższe/najlepsze deals bez filtra tytułu.
        `want` to liczba rekordów potrzebnych warstwie API (offset+limit);
        źródło stronicowane jest po 60 rekordów, wyniki cache'owane per strona.
        """
        want = max(1, want)
        collected: list = []
        page_number = 0
        # Zabezpieczenie przed nieskończoną pętlą (CheapShark ma skończoną liczbę stron).
        max_pages = 50
        while len(collected) < want and page_number < max_pages:
            page = self._deals_page(query, page_number)
            if not page:
                break
            collected.extend(page)
            if len(page) < self.source_page_size:
                break  # ostatnia strona
            page_number += 1

        return [self._normalize(item) for item in collected[:want]]

    def close(self) -> None:
        self._client.close()
