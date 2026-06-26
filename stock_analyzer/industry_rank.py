"""
行业排名 — 同行业股票排名（基本面 + 价格表现）。
"""
from __future__ import annotations

from dataclasses import dataclass, field

import requests
from stock_analyzer.fetchers.tencent import TencentFetcher
from stock_analyzer.utils import em_code


@dataclass
class IndustryRank:
    """行业排名结果"""
    industry_name: str = ""
    total_peers: int = 0
    # 基本面排名
    cap_rank: int = 0         # 总市值排名
    revenue_rank: int = 0     # 营收排名
    profit_rank: int = 0      # 净利润排名
    # 今日价格排名
    price_rank: int = 0       # 今日涨跌排名
    price_rank_total: int = 0 # 参与排名总数
    avg_change: float = 0     # 行业平均涨跌幅
    stock_change: float = 0   # 本股涨跌幅
    peer_count: int = 0       # 同行数量
    ranked_stocks: list = field(default_factory=list)  # 所有排名股票


class IndustryRanker:
    """行业排名分析器"""

    def __init__(self, tencent=None):
        self.tf = tencent or TencentFetcher()

    def get_rank(self, code: str, boards: list) -> IndustryRank:
        """获取某股票在同行业的排名"""
        rank = IndustryRank()
        if not boards:
            return rank
        rank.industry_name = boards[0].name if hasattr(boards[0], 'name') else str(boards[0])

        # 1. 基本面排名（从东财 emweb）
        em_c = em_code(code)
        try:
            url = f"http://emweb.securities.eastmoney.com/PC_HSF10/IndustryAnalysis/PageAjax?code={em_c}"
            resp = requests.get(url, timeout=8,
                headers={"User-Agent": "Mozilla/5.0", "Referer": "http://emweb.securities.eastmoney.com/"})
            data = resp.json()

            gsgm = (data.get("gsgm") or [{}])[0]
            rank.cap_rank = gsgm.get("TOTAL_CAP_RANK", 0)
            rank.revenue_rank = gsgm.get("TOTAL_OPERATEINCOME_RANK", 0)
            rank.profit_rank = gsgm.get("NETPROFIT_RANK", 0)

            # 收集所有同行代码
            peer_codes = set()
            peer_codes.add(code)
            for cat in ["czxbj", "gsgm_zsz", "gsgm_yysr", "gsgm_jlr"]:
                for item in data.get(cat, []):
                    c = item.get("CORRE_SECURITY_CODE", "")
                    if c and c != "行业平均" and c != "行业中值":
                        peer_codes.add(c)
            rank.peer_count = len(peer_codes)

            # 2. 价格排名（批量查行情）
            all_quotes = self.tf.fetch_quote_batch(list(peer_codes))
            quote_map = {}
            for q in all_quotes:
                quote_map[q.code] = q

            # 过滤新股（名称以 N 开头）
            filtered = [q for q in all_quotes if not q.name.startswith("N")]
            # 按涨跌幅排序
            sorted_peers = sorted(
                [q for q in filtered if q.code == code or True],
                key=lambda x: x.percent, reverse=True
            )

            # 计算行业平均
            if sorted_peers:
                rank.avg_change = round(
                    sum(q.percent for q in sorted_peers) / len(sorted_peers), 2
                )

            # 找到本股位置
            rank.ranked_stocks = [
                {"code": q.code, "name": q.name, "percent": q.percent}
                for q in sorted_peers
            ]
            for i, q in enumerate(sorted_peers):
                if q.code == code:
                    rank.price_rank = i + 1
                    rank.stock_change = q.percent
                    break
            rank.price_rank_total = len(sorted_peers)

        except Exception as e:
            pass

        return rank
