"""
数据模型 — Pydantic 强类型定义，所有 fetcher 和 analyzer 通用。
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


class StockQuote(BaseModel):
    """单笔实时行情（标准化格式）"""
    code: str                          # 6位代码
    name: str                          # 股票名称
    price: float                       # 现价
    open: float = 0.0                  # 今开
    high: float = 0.0                  # 最高
    low: float = 0.0                   # 最低
    prev_close: float = 0.0            # 昨收
    change: float = 0.0                # 涨跌额
    percent: float = 0.0               # 涨跌幅%
    volume: int = 0                    # 成交量(手)
    amount: float = 0.0                # 成交额(万元)
    time: str = ""                     # 数据时间
    source: str = ""                   # 数据来源 (tencent/sina/eastmoney)


class KLine(BaseModel):
    """单根日 K 线"""
    day: str                           # YYYY-MM-DD
    open: float
    close: float
    high: float
    low: float
    volume: int                        # 成交量(股)
    ma5: float = 0.0
    ma10: float = 0.0
    ma20: float = 0.0


class BoardInfo(BaseModel):
    """概念板块信息"""
    name: str
    code: str = ""                     # 板块代码(东财格式)
    rank: int = 99


class Announcement(BaseModel):
    """公司公告"""
    title: str
    date: str                          # YYYY-MM-DD


class PeerStock(BaseModel):
    """行业对标股"""
    code: str
    name: str


class StockAnalysis(BaseModel):
    """综合投资分析结果"""
    code: str
    name: str
    quote: Optional[StockQuote] = None

    # 分析信号
    signal: str = "未知"               # 买入/加仓 | 持有 | 持有观察 | 谨慎持有 | 减仓/回避
    detail: str = ""                   # 一句话分析
    score: float = 0.0                 # 综合评分 [-5, 5]

    # 价格参考
    target_price: float = 0.0
    stop_loss: float = 0.0
    pivot: float = 0.0

    # MA 分析
    trend: str = "震荡"
    ma5: float = 0.0
    ma10: float = 0.0
    ma20: float = 0.0
    ma5_pct: float = 0.0
    ma10_pct: float = 0.0
    ma20_pct: float = 0.0

    # 成交量
    vol_analysis: str = ""
    vol_ratio: Optional[float] = None

    # 大盘对比
    index_pct: float = 0.0
    relative_strength: float = 0.0

    # 风险提示
    warnings: list[str] = Field(default_factory=list)

    # 公告亮点
    announce_highlights: list[str] = Field(default_factory=list)

    # 板块信息
    boards: list[BoardInfo] = Field(default_factory=list)
    peers: list[PeerStock] = Field(default_factory=list)

    # 数据来源
    data_sources: list[str] = Field(default_factory=list)
