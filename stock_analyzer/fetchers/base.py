"""
抽象基类 — 所有数据源的统一接口，内置 HTTP Session 复用。
"""
from __future__ import annotations

from abc import ABC
from typing import Optional

import requests

from stock_analyzer.models import StockQuote, KLine, BoardInfo, Announcement, PeerStock


class StockFetcher(ABC):
    """股票数据源抽象基类"""

    source_name: str = "base"

    def __init__(self):
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        })

    def _get(self, url: str, timeout: int = 8, **kwargs) -> requests.Response:
        """统一 GET 请求（复用 Session）"""
        return self._session.get(url, timeout=timeout, **kwargs)

    def fetch_quote(self, code: str) -> Optional[StockQuote]:
        return None

    def fetch_kline(self, code: str, days: int = 30) -> Optional[list[KLine]]:
        return None

    def fetch_boards(self, code: str) -> list[BoardInfo]:
        return []

    def fetch_announcements(self, code: str, limit: int = 5) -> list[Announcement]:
        return []

    def fetch_peers(self, code: str) -> list[PeerStock]:
        return []
