# Listings API, Game Deals (scraper-as-API)

Płatne mikro-API zwracające **znormalizowane oferty** z publicznego, bezkluczowego
źródła [CheapShark](https://www.cheapshark.com) (promocje na gry). Gotowe do publikacji na RapidAPI.

Jeden spójny schemat rekordu:

```
title, price, currency, url, location, image, posted_at
```

## Endpointy

| Metoda | Ścieżka         | Opis                                                              |
| ------ | --------------- | ----------------------------------------------------------------- |
| GET    | `/health`       | Health check (nie odpytuje źródła).                               |
| GET    | `/listings`     | Znormalizowane oferty. Parametry poniżej.                         |
| GET    | `/sources`      | Lista dostępnych źródeł danych (id, nazwa, url, wymóg atrybucji). |
| GET    | `/docs`         | Swagger UI (OpenAPI generowany automatycznie).                    |
| GET    | `/openapi.json` | Schemat OpenAPI.                                                  |

### Parametry `/listings`

| Parametr | Typ    | Domyślnie | Opis                                                                      |
| -------- | ------ | --------- | ------------------------------------------------------------------------- |
| `query`  | string | `""`      | Fraza wyszukiwania (pusta = top deals).                                   |
| `limit`  | int    | `20`      | Liczba wyników, zakres 1-100. Poza zakresem => `422`.                     |
| `offset` | int    | `0`       | Przesunięcie (paginacja), zakres 0-1000.                                  |
| `sort`   | string | brak      | Sortowanie po cenie: `price_asc` lub `price_desc`. Inna wartość => `422`. |

Rekordy bez ceny (`price = null`) przy sortowaniu trafiają zawsze na koniec listy.

Pola odpowiedzi (wstecznie kompatybilne): `query`, `count`, `source`, `results`
oraz dodatkowo `offset`, `limit`, `sort`, `total_available`.

Nagłówki odpowiedzi `/listings`: `X-Plan`, `X-Plan-Quota`, `X-Response-Time-ms`, `X-Data-Source`.

## Uruchomienie, jedną komendą

```bash
# w katalogu projektu
python -m venv .venv && ./.venv/bin/pip install -r requirements.txt && ./.venv/bin/uvicorn main:app --reload
```

Potem: <http://127.0.0.1:8000/docs>

> Uwaga: `requirements.txt` przypina wersje pod Python 3.12 (obraz Dockera).
> Na Pythonie 3.13/3.14 zainstaluj najnowsze: `pip install -U fastapi "uvicorn[standard]" httpx pydantic`.

### Docker

```bash
docker build -t listings-api .
docker run -p 8000:8000 listings-api
```

### Szybki test

```bash
curl "http://127.0.0.1:8000/health"
curl "http://127.0.0.1:8000/sources"
curl "http://127.0.0.1:8000/listings?query=zelda&limit=3"
curl "http://127.0.0.1:8000/listings?limit=5&offset=5&sort=price_asc"
```

## Running tests

```bash
# w katalogu projektu, na aktywnym venv
./.venv/bin/pip install -r requirements-dev.txt
./.venv/bin/pytest -q
```

Testy mockują źródło (CheapShark) na poziomie `httpx`, więc nie wychodzą do sieci.
Pokrywają `/health`, `/sources`, happy path `/listings`, walidację (`limit > 100` i błędny
`sort` => `422`), paginację, sortowanie, cache oraz błędy źródła (5xx/timeout => `502`).
CI (GitHub Actions, `.github/workflows/ci.yml`) uruchamia je na Pythonie 3.12 przy każdym push/PR.

## Konfiguracja (opcjonalna)

Skopiuj `.env.example` → `.env`. Wszystko opcjonalne, usługa działa bez pliku:

- `SCRAPER_USER_AGENT`, opisowy UA (CheapShark wymaga niegenerycznego UA).
- `SCRAPER_PROXY_URL`, proxy (opcjonalne; obsługiwane też `HTTP_PROXY`/`HTTPS_PROXY`).
- `DEFAULT_PLAN`, domyślny plan przy braku nagłówka RapidAPI.

## Cechy produkcyjne

- Timeouty (connect/read), retry z wykładniczym backoffem, respekt `Retry-After` na 429.
- Ostrożny throttling (~3 req/s do źródła).
- Cache mapy sklepów (storeID -> nazwa) oraz cache stron ofert z TTL (domyślnie 60 s),
  dzięki czemu paginacja i sortowanie nie generują dodatkowych żądań do źródła.
- Obsługa błędów źródła (5xx/timeout) => czyste `502` z JSON `{"error": ..., "detail": ...}`.
- Walidacja parametrów (`limit` 1-100, `offset` 0-1000, `sort` price_asc/price_desc) => `422`.

## Atrybucja (WYMAGANA przez źródło)

Dane pochodzą z CheapShark. Zgodnie z ich zasadami należy linkować do CheapShark
i wskazywać je jako źródło. Nagłówek `X-Data-Source` oraz opis listingu to realizują.

## Publikacja na RapidAPI, krok po kroku

1. **Załóż konto** na <https://rapidapi.com> (provider/hub) i **PayPal** (do wypłat payout w RapidAPI → Provider Dashboard → Payout).
2. **Wystaw API publicznie**, najprościej wdrożyć kontener na dowolnym hostingu z publicznym URL:
   - np. `docker build` + deploy na Render / Railway / Fly.io / VPS. Zapisz publiczny bazowy URL (np. `https://twoje-api.onrender.com`).
3. W RapidAPI: **My APIs → Add New API** → nazwa „Game Deals, Listings API", kategoria _Data_ / _Gaming_.
4. **Import definicji**: wskaż `https://twoje-api.onrender.com/openapi.json` (RapidAPI zaimportuje `/health` i `/listings`).
5. **Base URL / Routing**: ustaw base URL na publiczny adres. RapidAPI wstawi nagłówki
   `X-RapidAPI-Proxy-Secret` (zweryfikuj po stronie serwera, jeśli chcesz blokować bezpośredni ruch)
   oraz `X-RapidAPI-Subscription` (nazwa planu, usługa czyta ją do `X-Plan`).
6. **Plany (Pricing)**, utwórz zgodnie z `rapidapi-listing.md`:
   - Free: 100 req/mies., hard limit.
   - Pro: 9.99 USD/mies.
   - Ultra: 49.99 USD/mies.
7. **Opis, tagi, obrazek**, wklej treść z `rapidapi-listing.md`.
8. **Test w Playground** RapidAPI, potem **Make Public**.
9. **Payout**: Provider Dashboard → podłącz PayPal → ustaw próg wypłaty.

Do zrobienia ręcznie zostaje **tylko**: założenie konta RapidAPI + PayPal oraz jednorazowy deploy kontenera pod publiczny URL. Cała technika (API, normalizacja, docs, plany w nagłówkach) jest gotowa.

---

## O autorze / About

Zbudowane przez Pawła Iwanka, **FluxLab**, automatyzacja procesów biznesowych i wdrożenia AI dla małych firm.

Strona: https://fluxlab.pl

Potrzebujesz podobnej automatyzacji na zamówienie? Napisz przez https://fluxlab.pl
