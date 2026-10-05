"""US swing-trade scanner: core logic (daily candles, long-only).

Pipeline: liquidity filter -> trend filter -> relative strength vs SPY ->
setup detection (BREAKOUT / PULLBACK) -> not-extended + resistance-room checks
-> 0-100 score -> trade plan (entry, stop, targets, position size).
"""
from __future__ import annotations
from datetime import datetime
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd

DEFAULT_CFG = {
    "min_price": 10.0,
    "min_dollar_vol": 20_000_000,   # 20-day avg traded value in USD
    "min_score": 60,
    "atr_stop_mult": 1.5,
    "rr_target": 2.0,
    "max_extension_atr": 3.0,       # skip if price > 3 ATR above EMA21
    "min_room_r": 1.5,              # pullbacks need >=1.5R room to 52w high
    "capital": 10_000.0,
    "risk_pct": 1.0,                # % of capital risked per trade
    "setups": ["BREAKOUT", "PULLBACK"],
    "block_in_bear": True,          # no new longs when SPY is in a downtrend
}


# ---------- indicators ----------
def _rsi(s: pd.Series, n: int = 14) -> pd.Series:
    d = s.diff()
    up, dn = d.clip(lower=0), -d.clip(upper=0)
    rs = up.ewm(alpha=1 / n, adjust=False).mean() / dn.ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + rs)


def _atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    pc = df["Close"].shift()
    tr = pd.concat([df["High"] - df["Low"], (df["High"] - pc).abs(), (df["Low"] - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


# ---------- data ----------
def download(tickers, period: str = "2y") -> dict:
    import yfinance as yf  # lazy import
    tickers = list(dict.fromkeys(tickers))
    raw = yf.download(tickers, period=period, interval="1d", group_by="ticker",
                      auto_adjust=True, threads=True, progress=False)
    out = {}
    for t in tickers:
        try:
            df = raw[t] if isinstance(raw.columns, pd.MultiIndex) else raw
            df = df[["Open", "High", "Low", "Close", "Volume"]].dropna(subset=["Close"])
            if len(df) >= 210:
                out[t] = df
        except KeyError:
            continue
    return out


def drop_partial(df: pd.DataFrame) -> pd.DataFrame:
    """Remove today's bar if the US market hasn't closed yet (use completed candles only)."""
    ny = datetime.now(ZoneInfo("America/New_York"))
    if df.index[-1].date() == ny.date() and (ny.hour < 16 or (ny.hour == 16 and ny.minute < 10)):
        return df.iloc[:-1]
    return df


def market_regime(spy: pd.DataFrame) -> str:
    c = spy["Close"]
    s50, s200 = c.rolling(50).mean().iloc[-1], c.rolling(200).mean().iloc[-1]
    if c.iloc[-1] > s50 > s200:
        return "BULL"
    if c.iloc[-1] > s200:
        return "NEUTRAL"
    return "BEAR"


# ---------- per-stock analysis ----------
def analyze(ticker: str, df: pd.DataFrame, spy_ret63: float, regime: str, cfg: dict):
    c, h, l, o, v = df["Close"], df["High"], df["Low"], df["Open"], df["Volume"]
    sma50, sma200 = c.rolling(50).mean(), c.rolling(200).mean()
    ema21 = c.ewm(span=21, adjust=False).mean()
    atr, rsi = _atr(df), _rsi(c)
    vol20 = v.rolling(20).mean().shift(1)
    dvol = (c * v).rolling(20).mean()

    close, high, low, opn = (float(x.iloc[-1]) for x in (c, h, l, o))
    a = float(atr.iloc[-1])
    vals = [close, a, sma50.iloc[-1], sma200.iloc[-1], vol20.iloc[-1], dvol.iloc[-1], rsi.iloc[-1], sma50.iloc[-11]]
    if any(pd.isna(x) for x in vals) or a <= 0:
        return None

    # 1) liquidity / price
    if close < cfg["min_price"] or dvol.iloc[-1] < cfg["min_dollar_vol"]:
        return None
    # 2) trend
    if not (close > sma50.iloc[-1] > sma200.iloc[-1] and sma50.iloc[-1] > sma50.iloc[-11]):
        return None
    # 3) relative strength vs SPY (63d)
    ret63 = close / float(c.iloc[-64]) - 1
    rs = ret63 - spy_ret63
    if rs <= 0:
        return None
    # 4) not extended
    ext = (close - float(ema21.iloc[-1])) / a
    if ext > cfg["max_extension_atr"]:
        return None

    hi252 = float(h.rolling(252, min_periods=200).max().iloc[-1])
    near_high = close / hi252
    rng = high - low
    close_pos = (close - low) / rng if rng > 0 else 0.5
    vr = float(v.iloc[-1] / vol20.iloc[-1])

    # 5) setups
    setup = None
    prior20 = float(h.shift(1).rolling(20).max().iloc[-1])
    if close > prior20 and vr >= 1.5 and close_pos >= 0.6 and near_high >= 0.90:
        setup = "BREAKOUT"
    else:
        recent_high = float(c.iloc[-11:-1].max())
        pb_low = float(l.iloc[-5:].min())
        depth = (recent_high - pb_low) / a
        if (1.0 <= depth <= 4.0 and 40 <= rsi.iloc[-1] <= 60 and close > opn
                and close > float(h.iloc[-2]) and close > float(ema21.iloc[-1])
                and pb_low >= float(sma50.iloc[-1]) * 0.98 and near_high >= 0.80):
            setup = "PULLBACK"
    if setup is None or setup not in cfg["setups"]:
        return None

    # 6) trade plan
    stop = close - cfg["atr_stop_mult"] * a
    if setup == "PULLBACK":
        stop = min(stop, float(l.iloc[-5:].min()) - 0.1 * a)
    stop = max(stop, close - 3 * a)
    risk = close - stop
    if risk <= 0:
        return None
    if setup == "PULLBACK" and hi252 > close and (hi252 - close) < cfg["min_room_r"] * risk:
        return None  # not enough room to resistance
    t1, t2 = close + cfg["rr_target"] * risk, close + 3 * risk
    shares = int(min(cfg["capital"] * cfg["risk_pct"] / 100 / risk, cfg["capital"] / close))

    # 7) score (0-100)
    sc = 8 + 8 + 4 + (5 if ema21.iloc[-1] > sma50.iloc[-1] else 0)          # trend (25)
    sc += 10 + (5 if rs > 0.05 else 0) + (5 if rs > 0.10 else 0)             # RS (20)
    if setup == "BREAKOUT":
        sc += 10 + min(vr / 2, 1) * 7 + (8 if near_high >= 0.97 else 3)      # setup (25)
    else:
        sc += 10 + (7 if 42 <= rsi.iloc[-1] <= 52 else 3) + min(max(vr, 0.5), 1.5) / 1.5 * 8
    sc += 10 if dvol.iloc[-1] >= 50e6 else 5                                  # liquidity (10)
    sc += 10 if ext <= 2 else 5                                               # not extended (10)
    sc += {"BULL": 10, "NEUTRAL": 5, "BEAR": 0}[regime]                       # market (10)

    return {
        "ticker": ticker, "setup": setup, "score": int(round(min(sc, 100))),
        "close": round(close, 2), "entry": round(close, 2), "stop": round(stop, 2),
        "target1": round(t1, 2), "target2": round(t2, 2), "risk": round(risk, 2),
        "shares": shares, "rs_pct": round(rs * 100, 1), "vol_ratio": round(vr, 2),
        "rsi": round(float(rsi.iloc[-1]), 1), "ext_atr": round(ext, 2),
        "from_52w_high_pct": round((near_high - 1) * 100, 1),
        "dollar_vol_m": round(float(dvol.iloc[-1]) / 1e6, 1),
    }


def run_scan(tickers, cfg: dict | None = None, data: dict | None = None, partial_ok: bool = False):
    """Returns (results_df, regime, meta)."""
    cfg = {**DEFAULT_CFG, **(cfg or {})}
    if data is None:
        data = download(sorted(set(tickers) | {"SPY"}))
    if "SPY" not in data:
        raise RuntimeError("SPY data missing (yfinance download failed?)")
    prep = (lambda d: d) if partial_ok else drop_partial
    spy = prep(data["SPY"])
    regime = market_regime(spy)
    spy_ret63 = float(spy["Close"].iloc[-1] / spy["Close"].iloc[-64] - 1)
    meta = {"asof": str(spy.index[-1].date()), "scanned": 0, "regime": regime}

    rows = []
    if not (regime == "BEAR" and cfg["block_in_bear"]):
        for t in tickers:
            if t not in data or t == "SPY":
                continue
            meta["scanned"] += 1
            try:
                r = analyze(t, prep(data[t]), spy_ret63, regime, cfg)
            except Exception:
                r = None
            if r and r["score"] >= cfg["min_score"]:
                rows.append(r)
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("score", ascending=False).reset_index(drop=True)
    return df, regime, meta
