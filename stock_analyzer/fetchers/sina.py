"""
新浪财经数据源 — 历史K线、备用行情。
"""
from __future__ import annotations

import logging
from typing import Optional



from stock_analyzer.fetchers.base import StockFetcher
from stock_analyzer.models import KLine, StockQuote
from stock_analyzer.utils import retry, stock_code_key

log = logging.getLogger(__name__)


class SinaFetcher(StockFetcher):

    def __init__(self):
        super().__init__()
    """新浪财经 K 线 + 备用行情"""

    source_name = "sina"

    def fetch_kline(self, code: str, days: int = 30) -> Optional[list[KLine]]:
        """从新浪获取日K线（含MA5/MA10/MA20）"""
        key = stock_code_key(code)
        url = (
            "http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
            "CN_MarketData.getKLineData?symbol=%s&scale=240&ma=5,10,20&datalen=%d"
            % (key, days)
        )
        try:
            resp = self._get(url, timeout=8)
            data = resp.json()
            if not isinstance(data, list):
                return None

            klines = []
            for d in data:
                klines.append(KLine(
                    day=d["day"][:10],
                    open=float(d["open"]),
                    close=float(d["close"]),
                    high=float(d["high"]),
                    low=float(d["low"]),
                    volume=int(d["volume"]) if d.get("volume") else 0,
                    ma5=float(d.get("ma_price5", 0) or 0),
                    ma10=float(d.get("ma_price10", 0) or 0),
                    ma20=float(d.get("ma_price20", 0) or 0),
                ))
            klines.sort(key=lambda x: x.day)
            return klines
        except Exception as e:
            log.warning("新浪K线获取失败 [%s]: %s", code, e)
            return None

    def fetch_quote(self, code: str) -> Optional[StockQuote]:
        """从新浪备用获取行情"""
        key = stock_code_key(code)
        url = f"http://hq.sinajs.cn/list={key}"
        try:
            resp = self._get(url, timeout=5, headers={"Referer": "https://finance.sina.com.cn"})
            resp.encoding = "gbk"
            text = resp.text.strip()
            if "var " not in text and "=" not in text:
                return None

            # 解析: var hq_str_sh600183="生益科技,178.50,187.20,..."
            payload = text.split('"')[1] if '"' in text else ""
            if not payload:
                return None
            parts = payload.split(",")
            if len(parts) < 33:
                return None

            name = parts[0]
            open_p = float(parts[1])
            prev_close = float(parts[2])
            price = float(parts[3])
            high = float(parts[4])
            low = float(parts[5])
            volume = int(float(parts[8]))
            amount = float(parts[9]) / 10000  # 元→万元
            change = round(price - prev_close, 2)
            percent = round((change / prev_close) * 100, 2) if prev_close else 0.0

            return StockQuote(
                code=code.strip(), name=name,
                price=price, open=open_p, high=high, low=low,
                prev_close=prev_close, change=change, percent=percent,
                volume=volume, amount=amount,
                time=parts[31] if len(parts) > 31 else "",
                source="sina",
            )
        except Exception as e:
            log.warning("新浪行情获取失败 [%s]: %s", code, e)
            return None
