"""多源分析引擎 — 合并多个数据源，生成综合投资建议。"""
from __future__ import annotations

import re
from typing import Optional

from stock_analyzer.fetchers.tencent import TencentFetcher
from stock_analyzer.fetchers.sina import SinaFetcher
from stock_analyzer.fetchers.eastmoney import EastMoneyFetcher
from stock_analyzer.models import (
    StockQuote, KLine, BoardInfo, Announcement, PeerStock, StockAnalysis,
)
from stock_analyzer.config import AppConfig
from stock_analyzer.sector import SectorAnalyzer


class StockAnalyzer:
    """多源股票分析引擎"""

    def __init__(self, cfg: AppConfig | None = None,
                 tencent: TencentFetcher | None = None,
                 sina: SinaFetcher | None = None,
                 eastmoney: EastMoneyFetcher | None = None):
        self.cfg = cfg or AppConfig()
        self.tencent = tencent or TencentFetcher()
        self.sina = sina or SinaFetcher()
        self.em = eastmoney or EastMoneyFetcher()
        self.sector = SectorAnalyzer(self.em)

    # ── 数据采集 ──

    def fetch_all(self, code: str, sources: list[str] | None = None) -> dict:
        sources = sources or self.cfg.analysis.use_sources
        days = self.cfg.analysis.kline_days
        result: dict = {"quote": None, "kline": None, "boards": [],
                         "announcements": [], "peers": [], "data_sources": []}
        if "tencent" in sources:
            q = self.tencent.fetch_quote(code)
            if q:
                result["quote"] = q
                result["data_sources"].append("tencent")
        if "sina" in sources:
            kline = self.sina.fetch_kline(code, days)
            if kline:
                result["kline"] = kline
                result["data_sources"].append("sina")
            if result["quote"] is None:
                q = self.sina.fetch_quote(code)
                if q:
                    result["quote"] = q
                    result["data_sources"].append("sina(backup)")
        if "eastmoney" in sources:
            for attr, method in [("boards", self.em.fetch_boards),
                                  ("announcements", self.em.fetch_announcements),
                                  ("peers", self.em.fetch_peers)]:
                val = method(code)
                if val:
                    result[attr] = val
            if result["boards"] or result["announcements"] or result["peers"]:
                result["data_sources"].append("eastmoney")
        return result

    def fetch_peer_quotes(self, code: str) -> list[StockQuote]:
        """获取对标股实时行情"""
        peers = self.em.fetch_peers(code)
        codes = [p.code for p in peers[:8]]
        return self.tencent.fetch_quote_batch(codes)

    # ── 单股分析 ──

    def analyze(self, code: str, sources: list[str] | None = None) -> StockAnalysis:
        data = self.fetch_all(code, sources)
        quote = data["quote"]
        kline = data["kline"]
        boards = data.get("boards", []) or []
        announcements = data.get("announcements", []) or []
        peers = data.get("peers", []) or []
        name = quote.name if quote else code

        analysis = StockAnalysis(
            code=code, name=name, quote=quote,
            data_sources=data.get("data_sources", []) or [],
            boards=[BoardInfo(name=b.name, code=b.code, rank=b.rank)
                    if not isinstance(b, BoardInfo) else b for b in boards],
            peers=[PeerStock(code=p.code, name=p.name)
                   if not isinstance(p, PeerStock) else p for p in peers],
        )
        if not quote:
            analysis.signal = "数据获取失败"
            analysis.detail = "无法获取实时行情"
            return analysis

        self._run_analysis(quote, kline, analysis)
        self._announcement_analysis(announcements, analysis)
        return analysis

    # ═══ 技术分析（已拆分） ═══

    def _run_analysis(self, quote: StockQuote, kline, analysis: StockAnalysis):
        price, high, low, stock_pct, volume = (
            quote.price, quote.high, quote.low, quote.percent, quote.volume)
        analysis.pivot = round((high + low + price) / 3, 2)

        ma5, ma10, ma20, trend, trend_score = self._calc_ma(price, kline, analysis)
        atr = self._calc_atr(kline)

        analysis.target_price, analysis.stop_loss = self._fib_atr_target_stop(
            price, high, low, kline, atr, trend, ma5, ma10, ma20)

        vol_analysis, vol_score, vol_ratio = self._calc_volume(volume, stock_pct, kline)
        analysis.vol_analysis = vol_analysis
        analysis.vol_ratio = vol_ratio

        # 评分与信号
        day_range = high - low
        pos = (price - low) / day_range if day_range > 0 else 0.5
        intraday_score = (pos - 0.5) * 2

        index_pct = 0.0
        relative_strength = stock_pct - index_pct
        rel_score = min(max(relative_strength / 2.0, -self.cfg.technical.scoring["relative_max"]),
                        self.cfg.technical.scoring["relative_max"])

        analysis.index_pct = index_pct
        analysis.relative_strength = round(relative_strength, 2)

        pct_score = min(max(stock_pct / 3.0, -self.cfg.technical.scoring["pct_max"]),
                        self.cfg.technical.scoring["pct_max"])

        sc = self.cfg.technical.scoring
        score = intraday_score + trend_score + vol_score + rel_score + pct_score
        score = max(min(score, sc["score_max"]), sc["score_min"])
        analysis.score = round(score, 1)

        analysis.signal, analysis.detail = self._gen_signal(
            score, relative_strength, trend, vol_analysis, stock_pct)

        # 风险
        w = self.cfg.technical.warnings
        warnings = []
        if price < low + day_range * w["price_near_low_ratio"]:
            warnings.append("接近日内最低，关注能否企稳")
        elif price > high - day_range * w["price_near_high_ratio"]:
            warnings.append("接近日内最高，注意回落")
        if stock_pct > w["pct_surge"]:
            warnings.append("涨幅过大，警惕回调")
        elif stock_pct < w["pct_crash"]:
            warnings.append("跌幅过大，恐慌释放中")
        if ma5 and abs(analysis.ma5_pct) > w["ma_deviation"]:
            warnings.append(f"偏离MA5 {analysis.ma5_pct:+.1f}%")
        if stock_pct < -2 and "放量" in vol_analysis:
            warnings.append("放量下跌注意风险")
        analysis.warnings = warnings

    def _calc_ma(self, price, kline, analysis):
        """MA 均线分析"""
        ma5 = ma10 = ma20 = 0.0
        ma5_pct = ma10_pct = ma20_pct = 0.0
        trend = "震荡"
        score = 0.0
        sc = self.cfg.technical.scoring

        if kline and len(kline) >= 3:
            latest = kline[-1]
            ma5, ma10, ma20 = latest.ma5, latest.ma10, latest.ma20
            if ma5: ma5_pct = (price - ma5) / ma5 * 100
            if ma10: ma10_pct = (price - ma10) / ma10 * 100
            if ma20: ma20_pct = (price - ma20) / ma20 * 100

            bull = ma5 > ma10 > ma20
            bear = ma5 < ma10 < ma20
            above_5 = price > ma5 if ma5 else False
            above_20 = price > ma20 if ma20 else False

            if bull and above_5 and above_20:
                trend, score = "多头排列", sc["trend_long"]
            elif bear and not above_5 and not above_20:
                trend, score = "空头排列", sc["trend_short"]
            elif above_5 and price > (ma10 or price):
                trend, score = "短线偏多", sc["trend_weak_long"]
            elif not above_5 and price < (ma10 or price):
                trend, score = "短线偏空", sc["trend_weak_short"]
            elif ma5 < ma10 < ma20:
                trend, score = "均线收敛", -0.3
            else:
                trend, score = "均线交织", 0.0

        analysis.ma5, analysis.ma10, analysis.ma20 = ma5, ma10, ma20
        analysis.ma5_pct = round(ma5_pct, 1)
        analysis.ma10_pct = round(ma10_pct, 1)
        analysis.ma20_pct = round(ma20_pct, 1)
        analysis.trend = trend
        return ma5, ma10, ma20, trend, score

    def _calc_atr(self, kline) -> float:
        """ATR 计算"""
        if not kline or len(kline) < 5:
            return 0.0
        n = min(14, len(kline) - 1)
        trs = []
        for i in range(-1, -n - 1, -1):
            if abs(i) > len(kline): break
            c, p = kline[i], kline[i - 1] if i - 1 >= -len(kline) else kline[i]
            trs.append(max(c.high - c.low, abs(c.high - p.close), abs(c.low - p.close)))
        return sum(trs) / len(trs) if trs else 0.0

    def _calc_volume(self, volume, stock_pct, kline):
        """成交量分析"""
        vol_analysis = ""
        vol_score = 0.0
        vol_ratio = None
        sc = self.cfg.technical.scoring
        if kline and len(kline) >= 10:
            vols = [k.volume / 100.0 for k in kline[-20:] if k.volume > 0]
            if vols:
                avg = sum(vols) / len(vols)
                vol_ratio = volume / avg if avg else 1.0
                if vol_ratio > 2.0:
                    vol_analysis = f"放量{vol_ratio:.1f}倍"
                    vol_score = sc["vol_surge_bull"] if stock_pct > 0 else sc["vol_surge_bear"]
                elif vol_ratio > 1.5:
                    vol_analysis = f"放量{vol_ratio:.1f}倍"
                    vol_score = 0.3 if stock_pct > 0 else -0.4
                elif vol_ratio < 0.5:
                    vol_analysis = f"缩量{vol_ratio * 100:.0f}%"
                    vol_score = sc["vol_drop"]
                else:
                    vol_analysis = "量能正常"
        return vol_analysis, vol_score, round(vol_ratio, 1) if vol_ratio else None

    def _gen_signal(self, score, rel, trend, vol, pct):
        """根据评分生成交易信号"""
        if score >= 2.0:
            s, d = "买入 / 加仓", "强势上涨，可考虑加仓"
            if rel > 1.5: d += "，明显跑赢大盘"
        elif score >= 0.8:
            s, d = "持有", "走势稳健，继续持有"
            if trend == "多头排列": d += "，均线多头排列"
            elif rel > 0: d += "，略强于大盘"
        elif score >= -0.5:
            s, d = "持有观察", "方向不明，观望为主"
            if rel < -1: d += "，注意大盘拖累"
        elif score >= -2.0:
            s, d = "谨慎持有", "偏弱运行，注意风险"
            if trend == "空头排列": d += "，均线空头压制"
            elif "放量" in vol and pct < 0: d += "，放量下跌需警惕"
        else:
            s, d = "减仓 / 回避", "弱势明显，建议减仓"
            if "放量" in vol and pct < 0: d += "，放量杀跌"
            if rel < -2: d += "，大幅跑输大盘"
        return s, d

    # ═══ 斐波那契 + ATR 目标/止损 ═══

    def _fib_atr_target_stop(self, price, high, low, kline, atr, trend, ma5, ma10, ma20):
        tcfg = self.cfg.technical
        mult = tcfg.atr_stop_multiplier

        target = round(price + atr * 2.0, 2) if atr else round(price * 1.05, 2)
        stop = round(price - atr * 2.0, 2) if atr else round(price * 0.95, 2)

        if kline and len(kline) >= 10:
            lookback = min(20, len(kline))
            recent = kline[-lookback:]
            s_high = max(k.high for k in recent)
            s_low = min(k.low for k in recent)
            rng = s_high - s_low
            if rng > 0:
                hi_idx = max(i for i, k in enumerate(recent) if k.high == s_high)
                lo_idx = min(i for i, k in enumerate(recent) if k.low == s_low)
                if hi_idx > lo_idx and price > (s_high + s_low) / 2:
                    fib = s_low + rng * tcfg.fib_target["uptrend"]
                    if fib > price: target = round(fib, 2)
                elif lo_idx > hi_idx and price < (s_high + s_low) / 2:
                    fib = s_high - rng * tcfg.fib_target["downtrend"]
                    if fib > price: target = round(fib, 2)

        if atr > 0:
            if "多头" in trend and kline and len(kline) >= 14:
                r_high = max(k.high for k in kline[-14:])
                stop = round(r_high - atr * mult["bull"], 2)
            elif "空头" in trend:
                stop = round(price - atr * mult["bear"], 2)
            elif "偏空" in trend:
                stop = round(price - atr * mult["bearish"], 2)
            elif trend == "均线收敛":
                stop = round(price - atr * mult["convergence"], 2)
            else:
                stop = round(price - atr * mult["neutral"], 2)

        if target <= price:
            target = round(price * 1.05 if not atr else price + atr * 1.5, 2)
        if stop >= price:
            stop = round(price * 0.95 if not atr else price - atr * 1.0, 2)

        return target, stop

    # ═══ 公告分析 ═══

    def _announcement_analysis(self, announcements, analysis):
        highlights = []
        for ann in announcements[:3]:
            t = ann.title
            s = re.sub(r'^[^:：]+[：:]\s*', '', t)
            s = re.sub(r'公告$', '', s)
            if len(s) > 22: s = s[:20] + ".."
            if "分红" in t or "派息" in t or "送转" in t or "分配" in t:
                tag = "[分红]"
            elif "增减持" in t or "增持" in t or "减持" in t:
                tag = "[增减持]"
            elif "回购" in t: tag = "[回购]"
            elif "业绩" in t or "预告" in t or "快报" in t: tag = "[业绩]"
            elif "合同" in t or "中标" in t or "订单" in t: tag = "[订单]"
            elif "聘任" in t or "辞职" in t or "人事" in t: tag = "[人事]"
            elif "决" in t and ("议" in t or "案" in t): tag = "[决议]"
            else: tag = "[公告]"
            highlights.append(f"{tag} {s} ({ann.date})")
        analysis.announce_highlights = highlights

    # ═══ 批量 ═══

    def analyze_batch(self, codes: list[str],
                      sources: list[str] | None = None) -> list[StockAnalysis]:
        results = []
        for code in codes:
            try:
                results.append(self.analyze(code, sources))
            except Exception as e:
                results.append(StockAnalysis(
                    code=code, name=code, signal="分析失败", detail=str(e)))
        return results
