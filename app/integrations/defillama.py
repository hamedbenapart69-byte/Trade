"""Read-only DeFiLlama protocol fundamentals adapter (public endpoint)."""
from __future__ import annotations

from dataclasses import dataclass
import math
import httpx

PROTOCOLS_URL = "https://api.llama.fi/protocols"
MAX_PROTOCOLS = 10000


class DeFiLlamaError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProtocolSnapshot:
    provider: str
    slug: str
    name: str
    category: str | None
    chains: tuple[str, ...]
    tvl_usd: float | None
    change_1d_pct: float | None
    change_7d_pct: float | None
    market_cap_usd: float | None


def _finite_number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) and number >= 0 else None


def fetch_protocols(*, client: httpx.Client | None = None) -> list[ProtocolSnapshot]:
    """Fetch public protocol directory; no token/secret or exchange account is used."""
    own = client is None
    http = client or httpx.Client(timeout=20.0, follow_redirects=False)
    try:
        response = http.get(PROTOCOLS_URL, headers={"Accept": "application/json", "User-Agent": "Trade-Market-Research/0.1"}, timeout=20.0)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise DeFiLlamaError("provider_response_not_a_list")
        results: list[ProtocolSnapshot] = []
        for item in payload[:MAX_PROTOCOLS]:
            if not isinstance(item, dict):
                continue
            slug, name = item.get("slug"), item.get("name")
            if not isinstance(slug, str) or not slug or not isinstance(name, str) or not name:
                continue
            chains = item.get("chains")
            clean_chains = tuple(x for x in chains if isinstance(x, str)) if isinstance(chains, list) else ()
            results.append(ProtocolSnapshot(
                provider="defillama",
                slug=slug,
                name=name,
                category=item.get("category") if isinstance(item.get("category"), str) else None,
                chains=clean_chains,
                tvl_usd=_finite_number(item.get("tvl")),
                change_1d_pct=(float(item["change_1d"]) if isinstance(item.get("change_1d"), (int, float)) and not isinstance(item.get("change_1d"), bool) and math.isfinite(float(item["change_1d"])) else None),
                change_7d_pct=(float(item["change_7d"]) if isinstance(item.get("change_7d"), (int, float)) and not isinstance(item.get("change_7d"), bool) and math.isfinite(float(item["change_7d"])) else None),
                market_cap_usd=_finite_number(item.get("mcap")),
            ))
        return results
    except httpx.HTTPError as exc:
        raise DeFiLlamaError(f"defillama_transport_or_http_error:{type(exc).__name__}") from exc
    except (ValueError, TypeError) as exc:
        raise DeFiLlamaError("defillama_invalid_json") from exc
    finally:
        if own:
            http.close()
