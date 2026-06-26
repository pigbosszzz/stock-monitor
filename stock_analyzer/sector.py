"""Dynamic sector analysis."""
from __future__ import annotations
import logging
from stock_analyzer.fetchers.eastmoney import EastMoneyFetcher
from stock_analyzer.models import BoardInfo

log = logging.getLogger(__name__)


class SectorAnalyzer:
    def __init__(self, eastmoney: EastMoneyFetcher | None = None):
        self._em = eastmoney or EastMoneyFetcher()

    def get_stock_boards(self, code: str) -> list[BoardInfo]:
        return self._em.fetch_boards(code)
