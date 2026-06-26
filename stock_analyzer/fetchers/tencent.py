"""
腾讯财经数据源 — 实时行情（免费、无需 API Key）。
"""
from __future__ import annotations

import logging
from typing import Optional



from stock_analyzer.fetchers.base import StockFetcher
from stock_analyzer.models import StockQuote
from stock_analyzer.utils import stock_code_key

log = logging.getLogger(__name__)


class TencentFetcher(StockFetcher):

    def __init__(self):
        super().__init__()
    """腾讯财经实时行情（qt.gtimg.cn）"""

    source_name = "tencent"

    def fetch_quote(self, code: str) -> Optional[StockQuote]:
        """获取实时行情"""
        key = stock_code_key(code)
        url = f"http://qt.gtimg.cn/q={key}"
        try:
            resp = self._get(url, timeout=5)
            resp.encoding = "gbk"
            text = resp.text.strip()

            # 解析 ~ 分隔的字段
            # 格式: v_sh600183="1~生益科技~600183~178.50~187.20~182.00~... 
            if "~" not in text:
                return None
            parts = text.split("~")
            if len(parts) < 40:
                return None

            # 字段索引（腾讯 qt 接口标准）
            name = parts[1]      # 股票名称
            price = float(parts[3])     # 现价
            prev_close = float(parts[4])  # 昨收
            open_p = float(parts[5])   # 今开
            volume = int(parts[6])     # 成交量(手)
            high = float(parts[33] or parts[35] or 0)  # 最高
            low = float(parts[34] or parts[36] or 0)   # 最低

            # 涨跌额和涨幅
            change = round(price - prev_close, 2)
            percent = round((change / prev_close) * 100, 2) if prev_close else 0.0

            # 成交额
            amount_str = parts[37] or "0"
            try:
                amount = float(amount_str)  # API 已返回万元
            except (ValueError, IndexError):
                amount = 0.0

            return StockQuote(
                code=code.strip(),
                name=name,
                price=price,
                open=open_p,
                high=high,
                low=low,
                prev_close=prev_close,
                change=change,
                percent=percent,
                volume=volume,
                amount=amount,
                time=parts[30] or "",
                source="tencent",
            )
        except Exception as e:
            log.debug("腾讯行情获取失败 [%s]: %s", code, e)
            return None

    def fetch_quote_batch(self, codes: list[str]) -> list[StockQuote]:
        """批量获取多只股票行情（单次请求）"""
        keys = [stock_code_key(c) for c in codes]
        url = f"http://qt.gtimg.cn/q={','.join(keys)}"
        try:
            resp = self._get(url, timeout=8)
            resp.encoding = "gbk"
            text = resp.text.strip()
        except Exception as e:
            log.error("批量获取失败: %s", e)
            return []

        results = []
        for line in text.split(";"):
            line = line.strip()
            if not line or "~" not in line:
                continue
            parts = line.split("~")
            if len(parts) < 40:
                continue
            try:
                original_code = parts[2] if len(parts) > 2 else ""
                name = parts[1]
                price = float(parts[3])
                prev_close = float(parts[4])
                open_p = float(parts[5])
                volume = int(parts[6])
                high = float(parts[33] or parts[35] or 0)
                low = float(parts[34] or parts[36] or 0)
                change = round(price - prev_close, 2)
                percent = round((change / prev_close) * 100, 2) if prev_close else 0.0
                amount_str = parts[37] or "0"
                try:
                    amount = float(amount_str)  # API 已返回万元
                except (ValueError, IndexError):
                    amount = 0.0

                results.append(StockQuote(
                    code=original_code,
                    name=name,
                    price=price, open=open_p, high=high, low=low,
                    prev_close=prev_close, change=change, percent=percent,
                    volume=volume, amount=amount, time=parts[30] or "",
                    source="tencent",
                ))
            except (ValueError, IndexError, KeyError) as e:
                log.debug("解析行情失败 [%s]: %s", line[:50], e)
                continue
        return results
