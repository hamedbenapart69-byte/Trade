"""Read-only CoinGecko public API integration for approved market snapshots."""
from __future__ import annotations
from dataclasses import dataclass
import httpx

BASE_URL = "https://api.coingecko.com/api/v3/simple/price"
ALLOWED_COINS = {"bitcoin", "ethereum", "solana", "ripple", "dogecoin", "binancecoin", "tether"}
ALLOWED_CURRENCIES = {"usd", "eur"}

class MarketDataError(RuntimeError):
    pass

@dataclass(frozen=True)
class MarketSnapshot:
    provider: str
    status_code: int
    coin_id: str
    currency: str
    price: float
    change_24h_pct: float | None

def fetch_market_snapshot(*, payload: dict, client: httpx.Client | None = None) -> MarketSnapshot:
    coin_id = payload.get("coin_id")
    currency = payload.get("currency", "usd")
    if coin_id not in ALLOWED_COINS:
        raise MarketDataError("coin_id_not_allowlisted")
    if currency not in ALLOWED_CURRENCIES:
        raise MarketDataError("currency_not_allowlisted")
    own = client is None
    http = client or httpx.Client(timeout=8.0, follow_redirects=False)
    try:
        response = http.get(
            BASE_URL,
            params={"ids": coin_id, "vs_currencies": currency, "include_24hr_change": "true"},
            headers={"Accept": "application/json", "User-Agent": "Trade-Control-Plane/0.1"},
            timeout=8.0,
        )
        response.raise_for_status()
        data = response.json()
        asset = data.get(coin_id)
        if not isinstance(asset, dict) or not isinstance(asset.get(currency), (int, float)):
            raise MarketDataError("provider_response_missing_price")
        change = asset.get(f"{currency}_24h_change")
        if change is not None and not isinstance(change, (int, float)):
            change = None
        return MarketSnapshot(
            provider="coingecko",
            status_code=response.status_code,
            coin_id=coin_id,
            currency=currency,
            price=float(asset[currency]),
            change_24h_pct=float(change) if change is not None else None,
        )
    except httpx.HTTPError as exc:
        raise MarketDataError(f"coingecko_transport_or_http_error:{type(exc).__name__}") from exc
    except (ValueError, TypeError) as exc:
        raise MarketDataError("coingecko_invalid_json") from exc
    finally:
        if own:
            http.close()
