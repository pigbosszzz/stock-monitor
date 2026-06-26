"""Backtesting & multi-timeframe K-line analysis."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import requests

from stock_analyzer.utils import stock_code_key

log = logging.getLogger(__name__)


@dataclass
class TFResult:
    """Single timeframe result"""
    name: str          # "日线"/"周线"/"月线"
    trend: str         # "多头排列" etc
    ma5: float = 0
    ma10: float = 0
    ma20: float = 0
    close: float = 0
    bars: int = 0


@dataclass
class BacktestResult:
    """Backtest results"""
    total_return: float = 0       # total return %
    max_drawdown: float = 0       # max drawdown %
    win_rate: float = 0           # trade win rate %
    trade_count: int = 0          # number of trades
    buy_hold_return: float = 0    # buy-and-hold return %
    timeframe: list[TFResult] = field(default_factory=list)


class BacktestEngine:

    SCALES = {"日线": 240, "周线": 1200, "月线": 7200}

    def _fetch(self, code, scale, count):
        key = stock_code_key(code)
        url = (
            "http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
            f"CN_MarketData.getKLineData?symbol={key}&scale={scale}&ma=5,10,20&datalen={count}"
        )
        try:
            resp = requests.get(url, timeout=10,
                headers={"User-Agent": "Mozilla/5.0"})
            data = resp.json()
            if not isinstance(data, list):
                return []
            bars = []
            for d in data:
                bars.append({
                    "day": d["day"][:10],
                    "open": float(d["open"]), "close": float(d["close"]),
                    "high": float(d["high"]), "low": float(d["low"]),
                    "volume": int(d["volume"]) if d.get("volume") else 0,
                    "ma5": float(d.get("ma_price5", 0) or 0),
                    "ma10": float(d.get("ma_price10", 0) or 0),
                    "ma20": float(d.get("ma_price20", 0) or 0),
                })
            bars.sort(key=lambda x: x["day"])
            return bars
        except Exception as e:
            log.warning("K-line fetch failed [%s scale=%s]: %s", code, scale, e)
            return []

    # ═══ Multi-timeframe ═══

    def analyze_timeframes(self, code: str) -> list[TFResult]:
        results = []
        for name, scale in self.SCALES.items():
            count = {"日线": 30, "周线": 20, "月线": 12}[name]
            bars = self._fetch(code, scale, count)
            if not bars or len(bars) < 3:
                continue

            latest = bars[-1]
            ma5, ma10, ma20 = latest["ma5"], latest["ma10"], latest["ma20"]
            close = latest["close"]

            # Trend detection (same logic as analyzer)
            if ma5 and ma10 and ma20:
                if ma5 > ma10 > ma20 and close > ma5:
                    trend = "多头排列"
                elif ma5 < ma10 < ma20 and close < ma5:
                    trend = "空头排列"
                elif close > ma5 and close > ma10:
                    trend = "短线偏多"
                elif close < ma5 and close < ma10:
                    trend = "短线偏空"
                else:
                    trend = "震荡"
            else:
                trend = "数据不足"

            results.append(TFResult(
                name=name, trend=trend,
                ma5=ma5, ma10=ma10, ma20=ma20,
                close=close, bars=len(bars),
            ))
        return results

    def tf_summary(self, code: str) -> str:
        """One-line multi-timeframe summary"""
        tfs = self.analyze_timeframes(code)
        parts = []
        for t in tfs:
            emoji = {"多头排列": "🔴", "空头排列": "🟢", "短线偏多": "🟠", "短线偏空": "🔵"}.get(t.trend, "⚪")
            parts.append(f"{t.name}:{emoji}{t.trend}")
        return " | ".join(parts)

    # ═══ Backtesting ═══

    def backtest(self, code: str, days: int = 90) -> BacktestResult:
        """Simple backtest using the scoring system."""
        bars = self._fetch(code, 240, days)
        if len(bars) < 30:
            return BacktestResult()

        result = BacktestResult()
        lookback = 20  # need 20 bars for MA warmup
        capital = 10000
        shares = 0
        start_price = bars[lookback]["close"]
        trades = []
        peak = capital

        for i in range(lookback, len(bars)):
            window = bars[max(0, i - 30):i + 1]
            current = window[-1]
            price = current["close"]

            # Simple score: MA trend + momentum
            score = self._quick_score(window)

            # Trading logic
            if score >= 2.0 and shares == 0:
                shares = capital / price
                capital = 0
                trades.append(("buy", price))
            elif score <= -2.0 and shares > 0:
                capital = shares * price
                shares = 0
                trades.append(("sell", price))

            # Track peak
            total = capital + shares * price
            if total > peak:
                peak = total

        # Close any open position
        final_price = bars[-1]["close"]
        final_value = capital + shares * final_price

        result.total_return = round((final_value - 10000) / 10000 * 100, 2)
        result.buy_hold_return = round((final_price - start_price) / start_price * 100, 2)
        result.trade_count = len(trades)

        # Win rate
        if trades:
            wins = 0
            for j in range(0, len(trades) - 1, 2):
                if j + 1 < len(trades):
                    if trades[j + 1][1] > trades[j][1]:
                        wins += 1
            pairs = len(trades) // 2
            result.win_rate = round(wins / pairs * 100, 1) if pairs else 0

        # Max drawdown
        if peak > 0:
            result.max_drawdown = round((peak - final_value) / peak * 100, 2)

        # Multi-timeframe
        result.timeframe = self.analyze_timeframes(code)

        return result

    def _quick_score(self, window):
        """Fast score approximation for backtesting."""
        if len(window) < 5:
            return 0.0
        latest = window[-1]
        ma5 = latest.get("ma5", 0)
        ma10 = latest.get("ma10", 0)
        ma20 = latest.get("ma20", 0)
        price = latest["close"]
        score = 0.0

        if ma5 and ma10 and ma20:
            if ma5 > ma10 > ma20 and price > ma5:
                score += 2.0
            elif ma5 < ma10 < ma20:
                score -= 2.0
            elif price > ma5:
                score += 0.8
            elif price < ma5:
                score -= 0.8

        # Momentum (5-day)
        if len(window) >= 5:
            chg = (price - window[-5]["close"]) / window[-5]["close"] * 100
            score += min(max(chg / 2, -1.5), 1.5)

        return round(score, 1)
