"""
东方财富数据源 — 概念板块、公司公告、行业对标、板块成分股。
"""
from __future__ import annotations

import logging
import re
from typing import Optional



from stock_analyzer.fetchers.base import StockFetcher
from stock_analyzer.models import BoardInfo, Announcement, PeerStock, StockQuote
from stock_analyzer.utils import em_code

log = logging.getLogger(__name__)

# ── 板块过滤黑名单 ──
_BOARD_BLACKLIST = {
    "Ⅱ", "Ⅲ", "题材股", "趋势股", "大盘股", "小盘股", "小盘成长", "权重股",
    "百元股", "百日新高", "历史新高", "近期新高", "最近多板", "昨日涨停",
    "昨日涨停_含一字", "昨日高振幅", "标准普尔", "富时罗素", "MSCI中国",
    "证金持股", "社保重仓", "深股通", "沪股通", "深证100", "上证180",
    "上证380", "沪深300", "HS300", "上证50", "央视50", "中证500",
    "中证1000", "东方财富热股", "茅指数", "宁组合", "行业龙头",
    "破净", "破发", "低价股", "高市盈率", "低市盈率", "活跃股",
    "融资融券", "预盈预增", "预亏预减", "机构重仓", "基金重仓",
    "QFII重仓", "消费风格", "周期风格", "成长风格",
    "科技风格", "大盘成长", "大盘价值", "小盘价值", "中盘成长", "中盘价值", "周期股",
    "2025年报预增", "2025三季报预增", "2025中报预增", "2025一季报预增",
    "2026年报预增", "2026一季报预增",
    "昨日连板", "昨日首板", "昨日触板", "昨日炸板",
    "AH股", "GDR", "CDR", "创业板综", "科创板做市股",
    "创业板", "科创板", "北交所",
    "深成500", "中证100", "创医药", "创科技",
}
_BOARD_BLACKLIST_SUFFIX = {"板块"}  # 地域板块


class EastMoneyFetcher(StockFetcher):

    def __init__(self):
        super().__init__()
    """东方财富：板块 / 公告 / 行业对标"""

    source_name = "eastmoney"

    def fetch_boards(self, code: str, max_boards: int = 12) -> list[BoardInfo]:
        """从东财 F10 获取股票所属概念板块"""
        em_c = em_code(code)
        url = f"http://emweb.securities.eastmoney.com/PC_HSF10/CoreConception/PageAjax?code={em_c}"
        try:
            resp = self._get(url, timeout=8,
                headers={"User-Agent": "Mozilla/5.0",
                         "Referer": "http://emweb.securities.eastmoney.com/"},
            )
            data = resp.json()
            boards = []
            seen_names = set()
            for item in data.get("ssbk", []):
                name = (item.get("BOARD_NAME") or "").strip()
                board_code = (item.get("BOARD_CODE") or "").strip()
                rank = int(item.get("BOARD_RANK", 99))
                if name and name not in seen_names and not self._is_generic(name):
                    seen_names.add(name)
                    boards.append(BoardInfo(name=name, code=board_code, rank=rank))
            boards.sort(key=lambda x: x.rank)
            return boards[:max_boards]
        except Exception as e:
            log.debug("获取板块失败 [%s]: %s", code, e)
            return []

    def fetch_announcements(self, code: str, limit: int = 5) -> list[Announcement]:
        """从东财获取最新公司公告"""
        url = (
            "https://np-anotice-stock.eastmoney.com/api/security/ann?"
            f"sr=-1&page_size={limit}&page_index=1&ann_type=A&"
            f"stock_list={code}&f_node=0&s_node=0"
        )
        try:
            resp = self._get(url, timeout=8)
            data = resp.json()
            items = data.get("data", {}).get("list", [])
            results = []
            for item in items:
                title = (item.get("title") or "").strip()
                stime = (item.get("display_time") or "")[:10]
                if title:
                    results.append(Announcement(title=title, date=stime))
            return results
        except Exception as e:
            log.debug("获取公告失败 [%s]: %s", code, e)
            return []

    def fetch_peers(self, code: str) -> list[PeerStock]:
        """从东财获取行业对标股"""
        em_c = em_code(code)
        url = f"http://emweb.securities.eastmoney.com/PC_HSF10/IndustryAnalysis/PageAjax?code={em_c}"
        try:
            resp = self._get(url, timeout=8,
                headers={"User-Agent": "Mozilla/5.0",
                         "Referer": "http://emweb.securities.eastmoney.com/"},
            )
            data = resp.json()
            peers = []
            seen = set()
            for item in data.get("czxbj", []):
                p_code = (item.get("CORRE_SECURITY_CODE") or "").strip()
                p_name = (item.get("CORRE_SECURITY_NAME") or "").strip()
                if not p_code or not p_name:
                    continue
                if "行业中值" in p_name or "行业平均" in p_name:
                    continue
                if p_code == code or p_code in seen:
                    continue
                seen.add(p_code)
                peers.append(PeerStock(code=p_code, name=p_name))
            return peers[:5]
        except Exception as e:
            log.debug("获取对标股失败 [%s]: %s", code, e)
            return []

    def fetch_board_constituents(
        self, board_code: str, max_stocks: int = 6
    ) -> list[dict]:
        """
        从东财获取某个概念板块的成分股及实时行情。
        board_code: 如 "BK0589" (东财板块代码)
        """
        url = (
            "http://push2.eastmoney.com/api/qt/clist/get"
            f"?pn=1&pz={max_stocks}&po=1&np=1&fltt=2&invt=2"
            f"&fid=f3&fs=b:{board_code}&fields=f2,f3,f12,f14"
        )
        try:
            resp = self._get(url, timeout=8)
            data = resp.json()
            items = data.get("data", {}).get("diff", [])
            results = []
            for item in items:
                results.append({
                    "code": item.get("f12", ""),
                    "name": item.get("f14", ""),
                    "price": item.get("f2", 0) or 0,
                    "percent": item.get("f3", 0) or 0,
                })
            return results
        except Exception as e:
            log.debug("获取板块成分股失败 [%s]: %s", board_code, e)
            return []

    @staticmethod
    def _is_generic(name: str) -> bool:
        """判断是否泛金融/风格类板块名（应过滤）"""
        name = name.strip()
        if not name:
            return True
        if any(kw in name for kw in _BOARD_BLACKLIST):
            return True
        if any(suf in name for suf in _BOARD_BLACKLIST_SUFFIX):
            return True
        if all(c in "0123456789ⅢⅡⅠ" for c in name):
            return True
        return False
