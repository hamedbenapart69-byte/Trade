"""CryptoHFTData public archive adapter.

این آداپتر فقط دادهٔ عمومی بازار را می‌خواند؛ حساب یا کلید معاملاتی ندارد.
دادهٔ خام فقط در حافظه پردازش می‌شود و نباید در مخزن عمومی ذخیره شود.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

BASE_URL = "https://api.cryptohftdata.com/v1"
USER_AGENT = "Trade-Internal-Market-Research/1.0"

ALLOWED_EXCHANGES = frozenset({
    "binance_futures",
    "bybit",
    "kraken_futures",
    "okx_futures",
    "bitget_futures",
    "hyperliquid_futures",
    "aster_futures",
    "lighter",
    "bitmex",
})
REQUIRED_COLUMNS = {
    "mark_price": frozenset({
        "received_time", "symbol", "mark_price", "index_price",
        "funding_rate", "next_funding_time",
    }),
    "open_interest": frozenset({
        "received_time", "symbol", "sum_open_interest",
        "sum_open_interest_value", "timestamp",
    }),
    "trades": frozenset({
        "received_time", "event_time", "symbol", "trade_id",
        "price", "quantity", "trade_time", "is_buyer_maker", "order_type",
    }),
    "liquidations": frozenset({
        "received_time", "event_time", "symbol", "side", "order_type",
        "time_in_force", "quantity", "price", "average_price",
        "order_status", "filled_quantity", "trade_time",
    }),
}


class CryptoHFTDataError(RuntimeError):
    """خطای عمومی دریافت یا اعتبارسنجی داده."""


class ProviderDataUnavailable(CryptoHFTDataError):
    """فایل یا نماد در آرشیو ارائه‌دهنده موجود نیست."""


class ProviderAuthenticationError(CryptoHFTDataError):
    """ارائه‌دهنده برای این درخواست احراز هویت می‌خواهد."""


class ProviderRateLimited(CryptoHFTDataError):
    """محدودیت نرخ درخواست ارائه‌دهنده فعال شده است."""


@dataclass(frozen=True)
class DatasetSnapshot:
    """دادهٔ خام و فراداده؛ table فقط در حافظه نگهداری شود."""
    provider: str
    exchange_id: str
    symbol: str
    data_type: str
    hour_start_utc: datetime
    retrieved_at_utc: datetime
    source_path: str
    table: pa.Table

    @property
    def row_count(self) -> int:
        return self.table.num_rows

    @property
    def columns(self) -> list[str]:
        return list(self.table.schema.names)


def latest_complete_hour(
    now: datetime | None = None,
    publication_delay_minutes: int = 15,
    safety_buffer_minutes: int = 2,
) -> datetime:
    """آخرین ساعت کامل که با تأخیر انتشار و حاشیهٔ ایمنی قابل دریافت است."""
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    current = current.astimezone(timezone.utc)
    safe_time = current - timedelta(
        minutes=publication_delay_minutes + safety_buffer_minutes
    )
    return safe_time.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)


def build_file_path(
    exchange_id: str,
    symbol: str,
    data_type: str,
    hour_start: datetime,
) -> str:
    """مسیر فایل ساعتی؛ مقادیر ورودی قبل از ساخت URL اعتبارسنجی می‌شوند."""
    exchange = str(exchange_id).lower()
    if exchange not in ALLOWED_EXCHANGES:
        raise ValueError(f"unsupported_exchange_id:{exchange}")
    normalized_symbol = str(symbol).upper()
    if not re.fullmatch(r"[A-Z0-9._-]{2,40}", normalized_symbol):
        raise ValueError("invalid_symbol")
    if data_type not in REQUIRED_COLUMNS:
        raise ValueError(f"unsupported_data_type:{data_type}")
    if hour_start.tzinfo is None:
        raise ValueError("hour_start must be timezone-aware")
    hour = hour_start.astimezone(timezone.utc)
    if any((hour.minute, hour.second, hour.microsecond)):
        raise ValueError("hour_start must be aligned to UTC hour")
    return (
        f"{exchange}/{hour:%Y-%m-%d}/{hour:%H}/"
        f"{normalized_symbol}_{data_type}.parquet"
    )


class CryptoHFTDataProvider:
    """دریافت فایل‌های Parquet ساعتی با REST عمومی، بدون نیاز به API key."""

    def __init__(
        self,
        api_key: str | None = None,
        timeout_seconds: float = 20.0,
        max_file_bytes: int = 16 * 1024 * 1024,
        min_request_interval_seconds: float = 1.05,
        opener: Any = None,
    ) -> None:
        self.api_key = api_key or os.getenv("CRYPTOHFTDATA_API_KEY")
        self.timeout_seconds = float(timeout_seconds)
        self.max_file_bytes = int(max_file_bytes)
        self.min_request_interval_seconds = max(0.0, float(min_request_interval_seconds))
        self._opener = opener or urllib.request.urlopen
        self._rate_lock = threading.Lock()
        self._last_download_at = 0.0

    def _build_url(self, endpoint: str, params: dict[str, str]) -> str:
        query = dict(params)
        if self.api_key:
            query["api_key"] = self.api_key
        return f"{BASE_URL}/{endpoint.lstrip('/')}?{urllib.parse.urlencode(query)}"

    def _get(self, url: str, *, is_download: bool = False) -> bytes:
        if is_download and self.min_request_interval_seconds:
            with self._rate_lock:
                elapsed = time.monotonic() - self._last_download_at
                wait = self.min_request_interval_seconds - elapsed
                if wait > 0:
                    time.sleep(wait)
                self._last_download_at = time.monotonic()

        request = urllib.request.Request(
            url,
            headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
            method="GET",
        )
        try:
            with self._opener(request, timeout=self.timeout_seconds) as response:
                status = int(response.status)
                if status >= 400:
                    raise CryptoHFTDataError(f"provider_http_{status}")
                body = response.read(self.max_file_bytes + 1)
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                raise ProviderAuthenticationError("provider_http_401") from exc
            if exc.code == 403:
                raise ProviderAuthenticationError("provider_http_403") from exc
            if exc.code == 404:
                raise ProviderDataUnavailable("provider_file_not_found") from exc
            if exc.code == 429:
                raise ProviderRateLimited("provider_http_429") from exc
            raise CryptoHFTDataError(f"provider_http_{exc.code}") from exc
        except (TimeoutError, urllib.error.URLError) as exc:
            raise CryptoHFTDataError(f"provider_network_error:{type(exc).__name__}") from exc

        if len(body) > self.max_file_bytes:
            raise CryptoHFTDataError("provider_file_exceeds_size_limit")
        return body

    def discover_symbols(self, exchange_id: str, data_type: str) -> list[str]:
        """نمادها را از endpoint رسمی discovery می‌گیرد؛ alias حدس زده نمی‌شود."""
        exchange = str(exchange_id).lower()
        if exchange not in ALLOWED_EXCHANGES:
            raise ValueError(f"unsupported_exchange_id:{exchange}")
        if data_type not in {"mark_price", "open_interest", "trades", "liquidations", "orderbook"}:
            raise ValueError(f"unsupported_discovery_data_type:{data_type}")
        url = self._build_url("symbols", {"exchange": exchange, "data_type": data_type})
        try:
            payload = json.loads(self._get(url).decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise CryptoHFTDataError("provider_symbols_invalid_json") from exc
        symbols = payload.get("symbols") if isinstance(payload, dict) else None
        if not isinstance(symbols, list) or not all(isinstance(item, str) for item in symbols):
            raise CryptoHFTDataError("provider_symbols_invalid_schema")
        return sorted({item.upper() for item in symbols})

    def download_hourly_parquet(
        self,
        exchange_id: str,
        symbol: str,
        data_type: str,
        hour_start: datetime,
    ) -> DatasetSnapshot:
        """فایل را مستقیم در حافظه می‌خواند؛ هیچ فایل خامی روی دیسک نوشته نمی‌شود."""
        source_path = build_file_path(exchange_id, symbol, data_type, hour_start)
        url = self._build_url("download", {"file": source_path})
        body = self._get(url, is_download=True)
        if not body.startswith(b"PAR1"):
            raise CryptoHFTDataError("provider_response_not_parquet")

        try:
            table = pq.ParquetFile(pa.BufferReader(body)).read(use_threads=False)
        except Exception as exc:
            raise CryptoHFTDataError(f"provider_parquet_parse_error:{type(exc).__name__}") from exc

        required = REQUIRED_COLUMNS[data_type]
        missing = sorted(required.difference(table.schema.names))
        if missing:
            raise CryptoHFTDataError(f"provider_schema_missing_columns:{','.join(missing)}")
        if table.num_rows <= 0:
            raise ProviderDataUnavailable("provider_dataset_empty")

        actual_symbols = {str(value).upper() for value in table.column("symbol").to_pylist() if value is not None}
        expected_symbol = str(symbol).upper()
        if actual_symbols and actual_symbols != {expected_symbol}:
            raise CryptoHFTDataError("provider_symbol_mismatch")

        return DatasetSnapshot(
            provider="CRYPTOHFTDATA",
            exchange_id=str(exchange_id).lower(),
            symbol=expected_symbol,
            data_type=data_type,
            hour_start_utc=hour_start.astimezone(timezone.utc),
            retrieved_at_utc=datetime.now(timezone.utc),
            source_path=source_path,
            table=table,
        )

    def download_latest(
        self,
        exchange_id: str,
        symbol: str,
        data_type: str,
        now: datetime | None = None,
    ) -> DatasetSnapshot:
        hour_start = latest_complete_hour(now)
        return self.download_hourly_parquet(exchange_id, symbol, data_type, hour_start)
