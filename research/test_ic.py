"""Multi-factor Spearman Rank IC research probe using Binance Vision spot klines.

Universe: BTC, ETH, SOL, BNB, XRP, ADA, DOGE, AVAX, DOT, LINK.
Period: 2024 calendar year; 2023-10..2023-12 are warm-up only.
Features: Volume_Z20, RSI_14, MA_Dist_50, Volatility_ATR.
Target: 3-day forward close-to-close return.

The reported t-stat is a Newey-West HAC t-statistic for the slope in a
regression of standardized average ranks. This avoids the naive IID
standard-error assumption for serially dependent daily observations.
No SciPy, statsmodels, exchange account, or trading API is used.
"""
from __future__ import annotations

from io import BytesIO
import json
from zipfile import ZipFile

import numpy as np
import pandas as pd
import requests


BASE_URL = "https://data.binance.vision/data/spot/monthly/klines"
SYMBOLS = (
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
    "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "DOTUSDT", "LINKUSDT",
)
YEAR = 2024
WARMUP_MONTHS = ("2023-10", "2023-11", "2023-12")
MONTHS = tuple(f"{YEAR}-{month:02d}" for month in range(1, 13))
HAC_MAX_LAG = 5
FEATURES = ("Volume_Z20", "RSI_14", "MA_Dist_50", "Volatility_ATR")

COLUMNS = [
    "open_time", "open", "high", "low", "close", "volume",
    "close_time", "quote_asset_volume", "number_of_trades",
    "taker_buy_base_asset_volume", "taker_buy_quote_asset_volume", "ignore",
]


def download_month(
    session: requests.Session, symbol: str, month: str
) -> pd.DataFrame:
    """Download and parse one Binance Vision monthly daily-kline archive."""
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

    numeric = ("open", "high", "low", "close", "volume")
    for column in numeric:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame["timestamp"] = pd.to_datetime(frame["open_time"], unit="ms", utc=True)
    return frame[["timestamp", *numeric]]


def wilder_smoothing(series: pd.Series, period: int) -> pd.Series:
    """Wilder's recursive moving average."""
    return series.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()


def calculate_features(data: pd.DataFrame) -> pd.DataFrame:
    """Calculate all four features using information available at time t."""
    close = data["close"]
    high = data["high"]
    low = data["low"]
    volume = data["volume"]

    vol_mean = volume.rolling(window=20, min_periods=20).mean()
    vol_std = volume.rolling(window=20, min_periods=20).std(ddof=0)
    data["Volume_Z20"] = (volume - vol_mean) / vol_std.replace(0.0, np.nan)

    delta = close.diff()
    gains = delta.clip(lower=0.0)
    losses = -delta.clip(upper=0.0)
    avg_gain = wilder_smoothing(gains, 14)
    avg_loss = wilder_smoothing(losses, 14)
    relative_strength = avg_gain / avg_loss.replace(0.0, np.nan)
    data["RSI_14"] = 100.0 - (100.0 / (1.0 + relative_strength))
    data.loc[(avg_loss == 0.0) & (avg_gain > 0.0), "RSI_14"] = 100.0
    data.loc[(avg_gain == 0.0) & (avg_loss > 0.0), "RSI_14"] = 0.0

    ma50 = close.rolling(window=50, min_periods=50).mean()
    data["MA_Dist_50"] = close / ma50 - 1.0

    previous_close = close.shift(1)
    true_range = pd.concat(
        [
            high - low,
            (high - previous_close).abs(),
            (low - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr14 = wilder_smoothing(true_range, 14)
    data["Volatility_ATR"] = atr14 / close

    data["Target"] = close.shift(-3) / close - 1.0
    return data


def hac_t_stat(x: np.ndarray, y: np.ndarray, max_lag: int = HAC_MAX_LAG) -> float:
    """OLS slope t-stat with Bartlett-kernel Newey-West HAC covariance.

    x and y are rank-transformed and standardized. The OLS slope therefore
    equals their Pearson correlation, i.e. Spearman Rank IC.
    """
    n = len(x)
    if n < 30:
        return float("nan")

    x_rank = pd.Series(x).rank(method="average").to_numpy(dtype=float)
    y_rank = pd.Series(y).rank(method="average").to_numpy(dtype=float)
    x_std = x_rank.std(ddof=0)
    y_std = y_rank.std(ddof=0)
    if x_std == 0.0 or y_std == 0.0:
        return float("nan")

    xr = (x_rank - x_rank.mean()) / x_std
    yr = (y_rank - y_rank.mean()) / y_std
    design = np.column_stack((np.ones(n, dtype=float), xr))
    xtx_inv = np.linalg.inv(design.T @ design)
    beta = xtx_inv @ design.T @ yr
    residuals = yr - design @ beta

    scores = design * residuals[:, None]
    meat = scores.T @ scores
    lag_limit = min(max_lag, n - 1)
    for lag in range(1, lag_limit + 1):
        weight = 1.0 - lag / (lag_limit + 1.0)
        gamma = scores[lag:].T @ scores[:-lag]
        meat += weight * (gamma + gamma.T)

    covariance = xtx_inv @ meat @ xtx_inv
    covariance *= n / (n - design.shape[1])
    variance = float(covariance[1, 1])
    if not np.isfinite(variance) or variance <= 0.0:
        return float("nan")
    return float(beta[1] / np.sqrt(variance))


def load_symbol(session: requests.Session, symbol: str) -> pd.DataFrame:
    """Load warm-up plus 2024 data and calculate the factor/target panel."""
    months = (*WARMUP_MONTHS, *MONTHS)
    frames = [download_month(session, symbol, month) for month in months]
    data = (
        pd.concat(frames, ignore_index=True)
        .drop_duplicates(subset="timestamp")
        .sort_values("timestamp")
        .reset_index(drop=True)
    )
    data = calculate_features(data)
    year_mask = data["timestamp"].dt.year.eq(YEAR)
    return data.loc[year_mask, ["timestamp", *FEATURES, "Target"]].copy()


def main() -> None:
    results: list[dict[str, object]] = []
    with requests.Session() as session:
        session.headers.update({"User-Agent": "Trade-Research-MultiFactor-IC/1.0"})
        for symbol in SYMBOLS:
            sample = load_symbol(session, symbol)
            for feature in FEATURES:
                pair = sample[[feature, "Target"]].replace(
                    [np.inf, -np.inf], np.nan
                ).dropna()
                n = len(pair)
                if n < 30:
                    raise ValueError(
                        f"Insufficient observations: {symbol}/{feature}: {n}"
                    )
                x_rank = pair[feature].rank(method="average")
                y_rank = pair["Target"].rank(method="average")
                rank_ic = float(x_rank.corr(y_rank, method="pearson"))
                t_stat = hac_t_stat(
                    pair[feature].to_numpy(dtype=float),
                    pair["Target"].to_numpy(dtype=float),
                )
                results.append(
                    {
                        "symbol": symbol,
                        "feature": feature,
                        "rank_ic": round(rank_ic, 8),
                        "t_stat": round(t_stat, 8),
                    }
                )

    print(json.dumps(results, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
