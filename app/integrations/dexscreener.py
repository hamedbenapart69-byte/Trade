"""Read-only DEX discovery via the public DexScreener search endpoint.

This adapter discovers pools; it does not treat search ranking as investment advice.
All returned records retain provider, retrieval time and raw liquidity/volume fields.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import math
import httpx

BASE_URL = "https://api.dexscreener.com/latest/dex/search"
MAX_QUERY_LENGTH = 120
MAX_RESULTS = 30


class DexScreenerError(RuntimeError):
    """Provider transport, HTTP or schema failure."""


@dataclass(frozen=True)
class DiscoveredPool:
    provider: str
    retrieved_at: str
    chain_id: str
    dex_id: str
    pair_address: str
    base_symbol: str
    base_name: str
    base_address: str
    quote_symbol: str
    price_usd: float | None
    liquidity_usd: float | None
    fdv_usd: float | None
    market_cap_usd: float | None
    volume_24h_usd: float | None
    price_change_24h_pct: float | None
    buys_24h: int | None
    sells_24h: int | None
    pair_created_at_ms: int | None


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) and result >= 0 else None


def _integer(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def search_dex_pools(*, query: str, client: httpx.Client | None = None) -> list[DiscoveredPool]:
    """Search public DEX pools. Missing provider fields remain None, never fabricated."""
    if not isinstance(query, str) or not query.strip() or len(query.strip()) > MAX_QUERY_LENGTH:
        raise DexScreenerError("invalid_search_query")
    own = client is None
    http = client or httpx.Client(timeout=12.0, follow_redirects=False)
    try:
        response = http.get(
            BASE_URL,
            params={"q": query.strip()},
            headers={"Accept": "application/json", "User-Agent": "Trade-Market-Research/0.1"},
            timeout=12.0,
        )
        response.raise_for_status()
        payload = response.json()
        pairs = payload.get("pairs") if isinstance(payload, dict) else None
        if not isinstance(pairs, list):
            raise DexScreenerError("provider_response_missing_pairs")
        retrieved = datetime.now(timezone.utc).isoformat()
        results: list[DiscoveredPool] = []
        for item in pairs[:MAX_RESULTS]:
            if not isinstance(item, dict):
                continue
            base = item.get("baseToken") if isinstance(item.get("baseToken"), dict) else {}
            quote = item.get("quoteToken") if isinstance(item.get("quoteToken"), dict) else {}
            liquidity = item.get("liquidity") if isinstance(item.get("liquidity"), dict) else {}
            volume = item.get("volume") if isinstance(item.get("volume"), dict) else {}
            change = item.get("priceChange") if isinstance(item.get("priceChange"), dict) else {}
            txns = item.get("txns") if isinstance(item.get("txns"), dict) else {}
            h24 = txns.get("h24") if isinstance(txns.get("h24"), dict) else {}
            chain, dex, address = item.get("chainId"), item.get("dexId"), item.get("pairAddress")
            if not all(isinstance(v, str) and v.strip() for v in (chain, dex, address)):
                continue
            results.append(DiscoveredPool(
                provider="dexscreener",
                retrieved_at=retrieved,
                chain_id=chain,
                dex_id=dex,
                pair_address=address,
                base_symbol=str(base.get("symbol") or ""),
                base_name=str(base.get("name") or ""),
                base_address=str(base.get("address") or ""),
                quote_symbol=str(quote.get("symbol") or ""),
                price_usd=_number(item.get("priceUsd")),
                liquidity_usd=_number(liquidity.get("usd")),
                fdv_usd=_number(item.get("fdv")),
                market_cap_usd=_number(item.get("marketCap")),
                volume_24h_usd=_number(volume.get("h24")),
                price_change_24h_pct=(float(change["h24"]) if isinstance(change.get("h24"), (int, float)) and not isinstance(change.get("h24"), bool) and math.isfinite(float(change["h24"])) else None),
                buys_24h=_integer(h24.get("buys")),
                sells_24h=_integer(h24.get("sells")),
                pair_created_at_ms=_integer(item.get("pairCreatedAt")),
            ))
        return results
    except httpx.HTTPError as exc:
        raise DexScreenerError(f"dexscreener_transport_or_http_error:{type(exc).__name__}") from exc
    except (ValueError, TypeError) as exc:
        raise DexScreenerError("dexscreener_invalid_json") from exc
    finally:
        if own:
            http.close()
