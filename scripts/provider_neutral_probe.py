"""ممیزی فقط‌خواندنی منابع دادهٔ مستقل؛ بدون کلید، حساب یا سفارش معاملاتی."""
from __future__ import annotations

import json
import io
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, parse_qs

ROOT = Path(__file__).resolve().parents[2]
TIMEOUT_SECONDS = 12
MAX_BODY_BYTES = 16 * 1024 * 1024
USER_AGENT = "Trade-Provider-Probe/1.0 (+read-only; no trading)"

def _timestamp_hint(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    candidates = [
        payload.get("last_updated"),
        payload.get("timestamp"),
        payload.get("updated_at"),
        payload.get("time"),
    ]
    data = payload.get("data")
    if isinstance(data, dict):
        candidates.extend([data.get("last_updated"), data.get("timestamp")])
    if isinstance(data, list) and data and isinstance(data[0], dict):
        candidates.extend([data[0].get("last_updated"), data[0].get("timestamp")])
    for value in candidates:
        if value is not None:
            return str(value)
    return None

def _shape_hint(payload: Any) -> str:
    if isinstance(payload, dict):
        return "object:" + ",".join(sorted(str(k) for k in payload.keys())[:20])
    if isinstance(payload, list):
        first = payload[0] if payload else None
        if isinstance(first, dict):
            return f"array[{len(payload)}]:object:" + ",".join(sorted(str(k) for k in first.keys())[:20])
        return f"array[{len(payload)}]"
    return type(payload).__name__

def request_probe(provider: str, category: str, url: str, binary: bool = False) -> dict[str, Any]:
    started = time.monotonic()
    result: dict[str, Any] = {
        "provider": provider,
        "category": category,
        "url": url.split("?")[0],
        "resource_hint": parse_qs(urlparse(url).query).get("file", [None])[0],
        "status_code": None,
        "status": "UNAVAILABLE",
        "latency_ms": None,
        "content_type": None,
        "content_length": None,
        "body_bytes_read": 0,
        "schema_hint": None,
        "provider_timestamp": None,
        "error": None,
    }
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            result["status_code"] = int(response.status)
            result["content_type"] = response.headers.get("Content-Type")
            length = response.headers.get("Content-Length")
            result["content_length"] = int(length) if length and length.isdigit() else None
            if result["content_length"] and result["content_length"] > MAX_BODY_BYTES:
                result["status"] = "BODY_TOO_LARGE"
            else:
                body = response.read(MAX_BODY_BYTES + 1)
                result["body_bytes_read"] = len(body)
                if len(body) > MAX_BODY_BYTES:
                    result["status"] = "BODY_TOO_LARGE"
                elif binary:
                    if not body.startswith(b"PAR1"):
                        result["status"] = "SCHEMA_UNVERIFIED"
                        result["schema_hint"] = "not_parquet_magic"
                    else:
                        try:
                            import pyarrow.parquet as pq
                            parquet = pq.ParquetFile(io.BytesIO(body))
                            result["status"] = "PASS"
                            result["schema_hint"] = "parquet_schema_valid"
                            result["parquet_rows"] = parquet.metadata.num_rows
                            result["parquet_columns"] = parquet.schema_arrow.names
                        except Exception as exc:
                            result["status"] = "PARQUET_PARSE_ERROR"
                            result["schema_hint"] = "parquet_magic_valid_but_metadata_unreadable"
                            result["error"] = type(exc).__name__
                else:
                    try:
                        payload = json.loads(body.decode("utf-8"))
                        result["status"] = "PASS"
                        result["schema_hint"] = _shape_hint(payload)
                        result["provider_timestamp"] = _timestamp_hint(payload)
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        result["status"] = "SCHEMA_UNVERIFIED"
    except urllib.error.HTTPError as exc:
        result["status_code"] = int(exc.code)
        result["content_type"] = exc.headers.get("Content-Type") if exc.headers else None
        result["status"] = f"HTTP_{exc.code}"
        result["error"] = "http_error"
    except Exception as exc:  # گزارش خطای واقعی؛ هیچ endpointی باعث شکست کل ممیزی نمی‌شود
        result["status"] = "NETWORK_ERROR"
        result["error"] = type(exc).__name__
    finally:
        result["latency_ms"] = round((time.monotonic() - started) * 1000, 2)
    return result

def build_probes(now: datetime | None = None) -> list[tuple[str, str, str, bool]]:
    now = now or datetime.now(timezone.utc)
    # دو ساعت تأخیر محافظه‌کارانه برای انتشار فایل ساعتی.
    hour = (now - timedelta(hours=2)).replace(minute=0, second=0, microsecond=0)
    date = hour.strftime("%Y-%m-%d")
    hh = hour.strftime("%H")
    hft_base = f"https://api.cryptohftdata.com/v1/download?file=binance_futures/{date}/{hh}/"
    hft_probes = [
        ("CryptoHFTData", f"{symbol}_mark_price".lower(), hft_base + f"{symbol}_mark_price.parquet", True)
        for symbol in ("BTCUSDT", "ETHUSDT", "SOLUSDT", "FILUSDT")
    ] + [
        ("CryptoHFTData", f"{symbol}_open_interest".lower(), hft_base + f"{symbol}_open_interest.parquet", True)
        for symbol in ("BTCUSDT", "ETHUSDT", "SOLUSDT", "FILUSDT")
    ]
    hft_extra = [
        ("CryptoHFTData", "filusdt_trades", hft_base + "FILUSDT_trades.parquet", True),
        ("CryptoHFTData", "solusdt_trades", hft_base + "SOLUSDT_trades.parquet", True),
        ("CryptoHFTData", "filusdt_liquidations", hft_base + "FILUSDT_liquidations.parquet", True),
    ]
    return hft_probes + hft_extra + [
        ("CoinGecko", "aggregated_market_api", "https://api.coingecko.com/api/v3/ping", False),
        ("CoinMarketCap", "keyless_aggregated_market_api", "https://pro-api.coinmarketcap.com/public-api/v1/cryptocurrency/listings/latest?start=1&limit=5&convert=USD", False),
        ("GeckoTerminal", "onchain_dex_networks", "https://api.geckoterminal.com/api/v2/networks", False),
        ("CoinPaprika", "aggregated_market_ticker", "https://api.coinpaprika.com/v1/tickers/btc-bitcoin", False),
        ("Alternative.me", "sentiment_fear_greed", "https://api.alternative.me/fng/?limit=1", False),
        ("DEXScreener", "onchain_dex_discovery", "https://api.dexscreener.com/latest/dex/search?q=BTC", False),
        ("DefiLlama", "defi_protocol_context", "https://api.llama.fi/v2/chains", False),
        ("DefiLlama", "perpetual_dex_open_interest", "https://api.llama.fi/overview/open-interest?excludeTotalDataChart=true&excludeTotalDataChartBreakdown=true", False),
        ("DefiLlama", "dex_volume_overview", "https://api.llama.fi/overview/dexs?excludeTotalDataChart=true&excludeTotalDataChartBreakdown=true", False),
        ("Coinalyze", "derivatives_auth_requirement", "https://api.coinalyze.net/v1/assets", False),
    ]

def run() -> dict[str, Any]:
    started = datetime.now(timezone.utc)
    probes = [request_probe(*item) for item in build_probes(started)]
    counts: dict[str, int] = {}
    for item in probes:
        counts[item["status"]] = counts.get(item["status"], 0) + 1
    return {
        "schema_version": "1.0",
        "generated_at_utc": started.isoformat(),
        "runtime": "github_actions_or_configured_runner",
        "mode": "READ_ONLY_NO_CREDENTIALS",
        "probe_count": len(probes),
        "status_counts": counts,
        "probes": probes,
        "interpretation": "Reachability probe only; not proof of licence, full coverage, freshness, production suitability or signal quality.",
    }

def main() -> int:
    report = run()
    out = Path("provider-probe-report.json")
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "probe_count": report["probe_count"],
        "status_counts": report["status_counts"],
        "report": str(out),
    }, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
