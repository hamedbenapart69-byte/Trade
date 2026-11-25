"""Simple volume/forward-return Rank IC probe using Binance Vision public klines.

Downloads BTCUSDT and ETHUSDT daily spot klines for calendar year 2023.
December 2022 is included only as rolling-window warm-up; statistics are
reported only for 2023 observations. No strategy, execution, or trading API.
"""
from __future__ import annotations

from io import BytesIO
from zipfile import ZipFile

import numpy as np
import pandas as pd
import requests


BASE_URL = "https://data.binance.vision/data/spot/monthly/klines"
SYMBOLS = ("BTCUSDT", "ETHUSDT")
YEAR = 2023
MONTHS = [f"{YEAR}-{month:02d}" for month in range(1, 13)]
WARMUP_MONTH = "2022-12"

COLUMNS = [
    "open_time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "close_time",
    "quote_asset_volume",
    "number_of_trades",
    "taker_buy_base_asset_volume",
    "taker_buy_quote_asset_volume",
    "ignore",
]


def download_month(session: requests.Session, symbol: str, month: str) -> pd.DataFrame:
    """Download and parse one Binance Vision monthly kline archive."""
    filename = f"{symbol}-1d-{month}.zip"
    url = f"{BASE_URL}/{symbol}/1d/{filename}"
    response = session.get(url, timeout=45)
    response.raise_for_status()

    with ZipFile(BytesIO(response.content)) as archive:
        csv_files = [name for name in archive.namelist() if name.endswith(".csv")]
        if len(csv_files) != 1:
            raise ValueError(f"Expected one CSV in {filename}; found {csv_files}")
        with archive.open(csv_files[0]) as csv_file:
            frame = pd.read_csv(csv_file, header=None, names=COLUMNS)

    frame["timestamp"] = pd.to_datetime(frame["open_time"], unit="ms", utc=True)
    frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
    frame["volume"] = pd.to_numeric(frame["volume"], errors="coerce")
    return frame[["timestamp", "close", "volume"]]


def load_symbol(session: requests.Session, symbol: str) -> pd.DataFrame:
    """Load warm-up plus 2023 data, then calculate feature and target."""
    frames = [download_month(session, symbol, WARMUP_MONTH)]
    frames.extend(download_month(session, symbol, month) for month in MONTHS)

    data = (
        pd.concat(frames, ignore_index=True)
        .drop_duplicates(subset="timestamp")
        .sort_values("timestamp")
        .reset_index(drop=True)
    )

    rolling_mean = data["volume"].rolling(window=20, min_periods=20).mean()
    rolling_std = data["volume"].rolling(window=20, min_periods=20).std(ddof=0)
    data["Volume_Z20"] = (data["volume"] - rolling_mean) / rolling_std.replace(0, np.nan)
    data["Target"] = data["close"].shift(-3) / data["close"] - 1.0

    year_mask = data["timestamp"].dt.year.eq(YEAR)
    sample = data.loc[year_mask, ["timestamp", "Volume_Z20", "Target"]].copy()
    sample = sample.replace([np.inf, -np.inf], np.nan).dropna()
    return sample


def main() -> None:
    total_rows = 0
    print("TEST=Volume_Z20_vs_3d_forward_return")
    print("SOURCE=Binance Vision public spot daily klines")
    print("PERIOD=2023-01-01..2023-12-31")
    print("METHOD=pandas average-ranks + Pearson correlation of ranks (Spearman-equivalent; scipy-free)")

    with requests.Session() as session:
        session.headers.update({"User-Agent": "Trade-Research-IC-Test/1.0"})
        for symbol in SYMBOLS:
            sample = load_symbol(session, symbol)
            rows = len(sample)
            total_rows += rows
            # pandas corr(method="spearman") imports scipy internally in current pandas.
            # To honor the no-SciPy constraint, compute the mathematically
            # equivalent Spearman coefficient as Pearson correlation of ranks.
            rank_ic = sample["Volume_Z20"].rank(method="average").corr(
                sample["Target"].rank(method="average"), method="pearson"
            )
            print(
                f"SYMBOL={symbol} "
                f"RANK_IC={rank_ic:.10f} "
                f"ROWS_PROCESSED={rows}"
            )

    print(f"TOTAL_ROWS_PROCESSED={total_rows}")


if __name__ == "__main__":
    main()
