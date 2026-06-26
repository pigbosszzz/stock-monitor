"""
配置加载 — YAML 配置文件 + 自选股持仓管理。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel, Field


class StockEntry(BaseModel):
    """单个自选股/持仓股配置"""
    code: str
    name: str = ""
    cost_price: Optional[float] = None
    shares: Optional[int] = None
    note: str = ""


class TechnicalConfig(BaseModel):
    """技术分析参数"""
    atr_stop_multiplier: dict = Field(default_factory=lambda: {
        "bull": 3.0, "bear": 1.5, "neutral": 2.0,
        "bearish": 1.5, "convergence": 1.8,
    })
    fib_target: dict = Field(default_factory=lambda: {
        "uptrend": 1.272, "downtrend": 0.382,
    })
    scoring: dict = Field(default_factory=lambda: {
        "trend_long": 1.5, "trend_short": -1.5,
        "trend_weak_long": 0.8, "trend_weak_short": -0.8,
        "vol_surge_bull": 0.5, "vol_surge_bear": -0.8, "vol_drop": -0.2,
        "relative_max": 2.0, "pct_max": 1.5,
        "score_max": 5.0, "score_min": -5.0,
    })
    warnings: dict = Field(default_factory=lambda: {
        "price_near_low_ratio": 0.15, "price_near_high_ratio": 0.15,
        "pct_surge": 7.0, "pct_crash": -7.0, "ma_deviation": 5.0,
    })


class MarketConfig(BaseModel):
    """大盘分析参数"""
    ranking_fetch: int = 120
    ranking_display: int = 30
    board_display: int = 8
    top_boards: int = 4


class AnalysisConfig(BaseModel):
    """分析配置"""
    kline_days: int = 30
    use_sources: list[str] = Field(default_factory=lambda: ["tencent", "sina", "eastmoney"])
    show_boards: bool = True
    show_peers: bool = True
    show_announcements: bool = True
    show_advice: bool = True
    max_board_constituents: int = 6


class AppConfig(BaseModel):
    """应用总配置"""
    stocks: list[StockEntry] = Field(default_factory=list)
    analysis: AnalysisConfig = Field(default_factory=AnalysisConfig)
    technical: TechnicalConfig = Field(default_factory=TechnicalConfig)
    market: MarketConfig = Field(default_factory=MarketConfig)
    output: dict = Field(default_factory=dict)


def load_config(
    config_path: str | Path = "config.yaml",
    watchlist_path: str | Path = "watchlist.yaml",
) -> AppConfig:
    """加载配置文件和自选股列表"""
    base = Path(config_path).parent
    cfg = AppConfig()

    if Path(config_path).exists():
        with open(config_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        if "analysis" in raw:
            cfg.analysis = AnalysisConfig(**raw["analysis"])
        if "technical" in raw:
            cfg.technical = TechnicalConfig(**raw["technical"])
        if "market" in raw:
            cfg.market = MarketConfig(**raw["market"])
        if "output" in raw:
            cfg.output = raw["output"]

    wp = Path(watchlist_path)
    if wp.exists():
        with open(wp, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        watchlist = raw.get("stocks", raw) if isinstance(raw, dict) else []
        if isinstance(watchlist, list):
            cfg.stocks = [
                StockEntry(**s) if isinstance(s, dict) else StockEntry(code=str(s))
                for s in watchlist
            ]

    return cfg
