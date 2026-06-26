"""动态概念板块分析 — 完全从东财 API 获取，消除硬编码 CONCEPT_STOCKS。"""
from __future__ import annotations

import logging

from stock_analyzer.fetchers.eastmoney import EastMoneyFetcher
from stock_analyzer.models import BoardInfo

log = logging.getLogger(__name__)


class SectorAnalyzer:
    """概念板块动态分析器"""

    def __init__(self, eastmoney: EastMoneyFetcher | None = None):
        self._em = eastmoney or EastMoneyFetcher()

    def get_stock_boards(self, code: str) -> list[BoardInfo]:
        return self._em.fetch_boards(code)

    def get_board_constituents(self, board: BoardInfo, max_stocks: int = 6) -> list[dict]:
        return self._em.fetch_board_constituents(board.code, max_stocks)

    def get_peers(self, code: str) -> list[str]:
        peers = self._em.fetch_peers(code)
        return [p.code for p in peers]
