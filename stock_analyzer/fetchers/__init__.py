"""
数据采集层 — 多源并行股票数据采集。
"""
from stock_analyzer.fetchers.base import StockFetcher
from stock_analyzer.fetchers.tencent import TencentFetcher
from stock_analyzer.fetchers.sina import SinaFetcher
from stock_analyzer.fetchers.eastmoney import EastMoneyFetcher

# 按优先级排列的默认数据源
DEFAULT_FETCHERS = [TencentFetcher, SinaFetcher, EastMoneyFetcher]

__all__ = ["StockFetcher", "TencentFetcher", "SinaFetcher", "EastMoneyFetcher", "DEFAULT_FETCHERS"]
