# Gotowy tekst listingu RapidAPI

## Nazwa API

**Game Deals, Listings API**

## Krótki opis (tagline, ~1 zdanie)

Real-time, normalized game deal listings from major PC stores, one clean JSON schema, no scraping headaches.

## Opis pełny (Description / Overview)

Game Deals Listings API delivers **normalized game-deal listings** aggregated from major PC game stores (Steam, Humble, GreenManGaming, Epic and more). You get a single, consistent JSON schema for every result, no per-store parsing, no HTML scraping, no auth juggling.

Every listing returns: `title`, `price`, `currency`, `url`, `location` (store), `image`, `posted_at` (ISO-8601 UTC).

Perfect for: price-comparison sites, deal bots (Discord/Telegram), browser extensions, budget trackers, gaming dashboards and affiliate content.

**Highlights**

- One normalized schema across all stores.
- Full-text search (`query`) or top-rated deals (empty query).
- Fast responses, sane rate limiting, robust error handling.
- Simple: two endpoints, zero setup.

**Endpoints**

- `GET /health`, service status.
- `GET /listings?query={text}&limit={1-60}`, normalized listings.

**Attribution:** deal data is sourced from CheapShark. Please keep the returned `url` links and the `X-Data-Source` reference when displaying results.

## Endpoint, dokumentacja skrócona

### GET /listings

| Param | Type | Required | Default | Notes |
| ----- | ------ | -------- | ------- | ---------------------------------------------------- |
| query | string | no | "" | Search text (e.g. `zelda`). Empty = top-rated deals. |
| limit | int | no | 20 | 1–60. |

Response 200:

```json
{
 "query": "zelda",
 "count": 3,
 "source": "cheapshark",
 "results": [
 {
 "title": "The Legend of Zelda: Links Awakening",
 "price": 59.99,
 "currency": "USD",
 "url": "https://www.cheapshark.com/redirect?dealID=...",
 "location": "Humble Store",
 "image": "https://cdn.humblebundle.com/misc/files/hashed/....jpg",
 "posted_at": "2026-09-14T13:15:15+00:00"
 }
 ]
}
```

## Plany / Pricing (tiers)

| Plan | Cena (USD/mies.) | Limit żądań | Rate limit | Uwagi |
| --------- | ---------------- | ----------------- | ---------- | --------------------------------- |
| **Free** | 0 | 100 / miesiąc | 1 req/s | Do testów i hobby. Hard limit. |
| **Pro** | 9.99 | 10 000 / miesiąc | 5 req/s | Dla botów i małych aplikacji. |
| **Ultra** | 49.99 | 200 000 / miesiąc | 20 req/s | Produkcja, dashboardy, duży ruch. |

> Overage (opcjonalnie do włączenia w RapidAPI): Pro +0.002 USD/req, Ultra +0.001 USD/req.

## Tagi

`games`, `gaming`, `deals`, `price-comparison`, `ecommerce`, `listings`, `steam`, `discounts`, `data`, `scraper`

## Kategoria

Data / Gaming

## Uwagi dla właściciela (nie publikować)

- Limity per plan egzekwuje RapidAPI (Rate Limits w edytorze planu). Nagłówek `X-Plan-Quota` w API to tylko sygnalizacja.
- Do wypłat: PayPal w Provider Dashboard → Payout.
- Źródło CheapShark wymaga atrybucji, zostawione w opisie i w nagłówku `X-Data-Source`.
