"""
大盘分析模块 — 指数、热门板块、涨跌榜、结合持仓分析。
数据源：腾讯（指数）、新浪（涨跌排行）、东财 emweb（板块）
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import requests

from stock_analyzer.fetchers.tencent import TencentFetcher
from stock_analyzer.fetchers.eastmoney import EastMoneyFetcher

log = logging.getLogger(__name__)


@dataclass
class MarketSnapshot:
    index_name: str
    index_code: str
    price: float
    change: float
    percent: float
    volume: float = 0  # 成交额(亿)


@dataclass
class HotSector:
    name: str
    percent: float
    leader_stock: str = ""
    leader_pct: float = 0


@dataclass
class MarketReport:
    indices: list[MarketSnapshot] = field(default_factory=list)
    hot_sectors: list[HotSector] = field(default_factory=list)
    top_gainers_day: list[dict] = field(default_factory=list)
    top_losers_day: list[dict] = field(default_factory=list)


MAIN_BOARD_PREFIXES = ("600", "601", "603", "605", "000", "001", "002", "003")

class MarketAnalyzer:
    """大盘分析器"""

    INDEX_CODES = {
        "上证指数": "sh000001",
        "深证成指": "sz399001",
        "沪深300": "sh000300",
    }

    # 代表板块的 ETF 代码（腾讯可查行情）
    SECTOR_ETFS = [
        ("半导体",   "sh512480"),
        ("人工智能", "sz159819"),
        ("新能源车", "sh515030"),
        ("白酒",     "sh512690"),
        ("军工",     "sh512660"),
        ("证券",     "sh512880"),
        ("医药",     "sh512010"),
        ("银行",     "sh512800"),
        ("光伏",     "sh515790"),
        ("软件",     "sh515230"),
        ("消费电子", "sz159732"),
        ("电力",     "sh159611"),
        ("煤炭",     "sh515220"),
        ("游戏",     "sz159869"),
    ]

    def __init__(self, cfg=None, tencent=None, eastmoney=None):
        self.cfg = cfg
        self._ranking_fetch = cfg.market.ranking_fetch if cfg else 120
        self.tf = tencent or TencentFetcher()
        self.em = eastmoney or EastMoneyFetcher()

    # ── 指数 ──

    def fetch_indices(self) -> list[MarketSnapshot]:
        indices = []
        for name, code in self.INDEX_CODES.items():
            q = self.tf.fetch_quote(code)
            if q:
                amount_yi = q.amount / 10000 if q.amount else 0
                indices.append(MarketSnapshot(
                    index_name=name, index_code=q.code,
                    price=q.price, change=q.change, percent=q.percent,
                    volume=amount_yi,
                ))
        return indices

    # ── 热门板块（通过代表ETF的涨跌幅）──

    def fetch_hot_sectors(self, count: int = 10) -> list[HotSector]:
        """通过代表性ETF涨跌幅判断热门板块"""
        codes = [c for _, c in self.SECTOR_ETFS]
        quotes = self.tf.fetch_quote_batch(codes)
        # batch 返回的 code 不含 sh/sz 前缀，去掉前缀匹配
        quote_map = {}
        for q in quotes:
            c = q.code.replace("sh", "").replace("sz", "").replace("SH", "").replace("SZ", "")
            quote_map[c] = q

        sectors = []
        for name, full_code in self.SECTOR_ETFS:
            short_code = full_code.replace("sh", "").replace("sz", "")
            q = quote_map.get(short_code)
            if q:
                sectors.append(HotSector(
                    name=name,
                    percent=round(q.percent, 2),
                ))

        # 按涨跌幅排序
        sectors.sort(key=lambda x: x.percent, reverse=True)
        return sectors[:count]

    # ── 涨跌榜（新浪接口）──

    def _sina_ranking(self, sort: str, count: int = 10) -> list[dict]:
        """新浪行情中心排行（多拉股票再过滤主板）
        sort: 'asc'=涨幅, 'desc'=跌幅
        """
        asc = 1 if sort == "desc" else 0
        # 拉 60 只再过滤，确保主板有足够数量
        fetch_count = self._ranking_fetch
        url = (
            "http://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/"
            "Market_Center.getHQNodeData?"
            f"page=1&num={fetch_count}&sort=changepercent&asc={asc}"
            "&node=hs_a&symbol=&_s_r_a=init"
        )
        try:
            resp = requests.get(url, timeout=10)
            resp.encoding = "gbk"
            data = resp.json()
            if not isinstance(data, list):
                return []
            results = []
            for it in data:
                try:
                    price = float(it.get("trade", 0) or 0)
                except (ValueError, TypeError):
                    price = 0.0
                try:
                    pct = float(it.get("changepercent", 0) or 0)
                except (ValueError, TypeError):
                    pct = 0.0
                code = it.get("code", "")
                # 只保留主板，且排除退市股
                name = it.get("name", "")
                if not code.startswith(MAIN_BOARD_PREFIXES):
                    continue
                if "退" in name:
                    continue
                results.append({
                    "code": code,
                    "name": name,
                    "price": price,
                    "percent": pct,
                })
                if len(results) >= count:
                    break
            return results
        except Exception as e:
            log.debug("新浪排行获取失败: %s", e)
            return []

    def fetch_top_gainers(self, count: int = 10) -> list[dict]:
        return self._sina_ranking("asc", count)

    def fetch_top_losers(self, count: int = 10) -> list[dict]:
        return self._sina_ranking("desc", count)


    def generate_report(self) -> MarketReport:
        report = MarketReport()
        report.indices = self.fetch_indices()
        report.hot_sectors = self.fetch_hot_sectors(10)
        count = self.cfg.market.ranking_display if self.cfg else 30
        report.top_gainers_day = self.fetch_top_gainers(count)
        report.top_losers_day = self.fetch_top_losers(count)
        return report

    # ── 持仓 + 大盘结合 ──


    # ── 按板块的涨跌排行 ──

    def fetch_board_ranking(
        self, board_stocks: dict, per_board: int = 8
    ) -> dict:
        """按板块分组涨跌排行（仅主板）。board_stocks: {板块名: {股票代码, ...}}"""
        if not board_stocks:
            return {}

        all_codes = set()
        for codes in board_stocks.values():
            all_codes.update(codes)

        quotes = self.tf.fetch_quote_batch(list(all_codes))
        quote_map = {}
        for q in quotes:
            quote_map[q.code] = q
            quote_map["sh" + q.code] = q
            quote_map["sz" + q.code] = q

        result = {}
        for bname, codes in board_stocks.items():
            stocks = []
            for code in codes:
                if not code.startswith(MAIN_BOARD_PREFIXES):
                    continue
                q = quote_map.get(code)
                if not q:
                    continue
                stocks.append({"code": q.code, "name": q.name, "price": q.price, "percent": q.percent})
            stocks.sort(key=lambda x: x["percent"], reverse=True)
            if stocks:
                result[bname] = stocks[:per_board]

        return result

    def analyze_with_market(
        self, report: MarketReport, stocks
    ) -> dict:
        if not report.indices:
            return {}
        sh_idx = next((i for i in report.indices if "上证" in i.index_name), None)
        market_trend = "震荡"
        if sh_idx:
            if sh_idx.percent > 1: market_trend = "强势上涨"
            elif sh_idx.percent > 0.3: market_trend = "温和上涨"
            elif sh_idx.percent < -1: market_trend = "明显下跌"
            elif sh_idx.percent < -0.3: market_trend = "小幅走弱"

        hot_names = {s.name for s in report.hot_sectors[:5]}
        results = {}
        for s in stocks:
            stock_boards = {b.name if hasattr(b, 'name') else str(b) for b in s.boards}
            overlap = stock_boards & hot_names
            results[s.code] = {
                "market_trend": market_trend,
                "sh_index_pct": sh_idx.percent if sh_idx else 0,
                "in_hot_sector": len(overlap) > 0,
                "hot_sectors_matched": list(overlap),
            }
        return results
