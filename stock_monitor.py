"""
A股实时股价监控提醒工具
=========================
功能：
  1. 实时获取 A 股股价（腾讯免费接口，无需 API Key）
  2. 监控多个股票，支持多个目标价
  3. 达到目标价时：桌面通知 + 声音提醒 + 控制台高亮
  5. 结合大盘信息的投资建议（目标价/止损价/持有建议）

用法示例：
  python stock_monitor.py 600519 --target 190 195 --interval 10
  python stock_monitor.py 000858 600519 --target 180:below 200:above
"""

from __future__ import annotations

import argparse
import datetime
import json
import logging
import os
import sys
import textwrap
import time
import webbrowser
from pathlib import Path
from typing import Dict, Optional

import requests

# 修复 Windows GBK 编码问题
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# ── 日志 ────────────────────────────────────────────────────────────────
LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "stock_monitor.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("stock_monitor")


# ── 核心工具函数 ─────────────────────────────────────────────────────────

STOCK_NAME_CACHE: dict[str, str] = {}


def stock_code_key(code: str) -> str:
    """将 6 位数字代码转为腾讯 API 用的 '市场+代码' 格式。"""
    code = code.strip()
    if code.startswith(("sh", "sz", "SH", "SZ")):
        return code.lower()
    # 上海: 6 开头, 或 500/550 开头
    if code.startswith(("6", "5")):
        return f"sh{code}"
    # 深圳: 0/3/2 开头
    return f"sz{code}"


def fetch_realtime_price(code: str) -> Optional[dict]:
    """
    从腾讯财经接口获取实时行情。
    返回字段：name, code, price, open, high, low, prev_close, volume, amount, percent
    """
    key = stock_code_key(code)
    url = f"http://qt.gtimg.cn/q={key}"
    try:
        resp = requests.get(url, timeout=5)
        resp.encoding = "gbk"
        text = resp.text.strip()
        # 返回格式：v_sh600519="...";   用引号分割
        if not text or '="' not in text:
            log.warning("接口返回异常: %s", text[:100])
            return None
        data_part = text.split('="', 1)[1].rsplit('"', 1)[0]
        fields = data_part.split("~")
        if len(fields) < 40:
            log.warning("字段不足: %s", data_part[:100])
            return None
        name = fields[1]
        price = float(fields[3]) if fields[3] else 0.0
        prev_close = float(fields[4]) if fields[4] else 0.0
        open_p = float(fields[5]) if fields[5] else 0.0
        volume = int(fields[6]) if fields[6] else 0  # 手
        amount = float(fields[37]) if fields[37] else 0.0  # 万元
        high = float(fields[33]) if fields[33] else 0.0
        low = float(fields[34]) if fields[34] else 0.0

        change = price - prev_close
        percent = (change / prev_close * 100) if prev_close else 0.0

        STOCK_NAME_CACHE[code] = name

        return {
            "name": name,
            "code": code,
            "price": price,
            "open": open_p,
            "high": high,
            "low": low,
            "prev_close": prev_close,
            "change": round(change, 2),
            "percent": round(percent, 2),
            "volume": volume,
            "amount": amount,
            "time": datetime.datetime.now().strftime("%H:%M:%S"),
        }
    except requests.RequestException as e:
        log.error("网络请求失败 [%s]: %s", key, e)
        return None
    except (ValueError, IndexError, TypeError) as e:
        log.error("解析失败 [%s]: %s", key, e)
        return None


def get_stock_name(code: str) -> str:
    """获取股票名称（带缓存）。"""
    if code in STOCK_NAME_CACHE:
        return STOCK_NAME_CACHE[code]
    data = fetch_realtime_price(code)
    if data:
        return data["name"]
    return code


# ── 提醒模块 ─────────────────────────────────────────────────────────────

def notify_desktop(title: str, message: str):
    """发送桌面通知。尝试 plyer -> win10toast -> 回退。"""
    try:
        from plyer import notification

        notification.notify(
            title=title,
            message=message,
            app_name="A股监控",
            timeout=8,
        )
        return
    except ImportError:
        pass
    except Exception as e:
        log.debug("plyer 通知失败: %s", e)

    try:
        from win10toast import ToastNotifier

        toaster = ToastNotifier()
        toaster.show_toast(title, message, duration=8, threaded=True)
        return
    except ImportError:
        pass
    except Exception as e:
        log.debug("win10toast 通知失败: %s", e)

    # 回退：控制台输出
    border = "=" * 50
    log.info("\n" + border)
    log.info("  %s", title)
    log.info("  %s", message)
    log.info(border)


def play_alert_sound(times: int = 3):
    """播放提醒音效。"""
    try:
        import winsound

        for _ in range(times):
            winsound.Beep(880, 300)  # 频率 880Hz, 持续 300ms
            time.sleep(0.15)
    except ImportError:
        # Linux/macOS 用终端 bell
        print("\a", end="", flush=True)


def open_stock_url(code: str):
    """在浏览器打开股票详情页（东方财富）。"""
    url = f"https://quote.eastmoney.com/{stock_code_key(code).upper()}.html"
    webbrowser.open(url)


# ── 目标价格管理 ─────────────────────────────────────────────────────────

class PriceTarget:
    """单个目标价格配置。"""

    def __init__(self, price: float, direction: str = "above"):
        self.price = price
        self.direction = direction  # "above" 或 "below"
        self.tripped = False  # 已触发过

    def check(self, current_price: float) -> bool:
        """检查是否达到目标价。达到返回 True（仅首次触发返回 True）。"""
        if self.tripped:
            return False
        hit = False
        if self.direction == "above" and current_price >= self.price:
            self.tripped = True
            hit = True
        elif self.direction == "below" and current_price <= self.price:
            self.tripped = True
            hit = True
        # 如果价格反向穿越，重置（例如：涨到 200 触发后跌回 190 以下再涨到 200 可再次触发）
        if not hit:
            self._check_reset(current_price)
        return hit

    def _check_reset(self, current_price: float):
        """价格足够远离触发价时重置标记，允许重复提醒。"""
        if self.direction == "above" and current_price < self.price * 0.98:
            self.tripped = False
        elif self.direction == "below" and current_price > self.price * 1.02:
            self.tripped = False

    def __str__(self):
        arrow = "/\\" if self.direction == "above" else "\\/"
        status = "[!]" if self.tripped else "[_]"
        return "%s %.2f %s" % (status, self.price, arrow)


class ChangeTarget:
    """单个涨跌幅目标配置，基于百分比。"""

    def __init__(self, percent: float, direction: str = "above"):
        self.percent = percent          # 目标百分比，如 5.0 表示 5%
        self.direction = direction      # "above" = 涨幅超 X% 提醒; "below" = 跌幅超 X% 提醒
        self.tripped = False

    def check(self, current_percent: float) -> bool:
        """检查当前涨跌幅是否达到目标。首次触发返回 True。"""
        if self.tripped:
            return False
        hit = False
        if self.direction == "above" and current_percent >= self.percent:
            self.tripped = True
            hit = True
        elif self.direction == "below" and current_percent <= self.percent:
            self.tripped = True
            hit = True
        if not hit:
            self._check_reset(current_percent)
        return hit

    def _check_reset(self, current_percent: float):
        """价格回落后重置标记，允许重复提醒。"""
        if self.direction == "above" and current_percent < self.percent - 1.0:
            self.tripped = False
        elif self.direction == "below" and current_percent > self.percent + 1.0:
            self.tripped = False

    def __str__(self):
        arrow = "/\\" if self.direction == "above" else "\\/"
        status = "[!]" if self.tripped else "[_]"
        return "%s %.1f%% %s" % (status, self.percent, arrow)


# ── 大盘指数与投资建议 ────────────────────────────────────────────────

# 历史 K 线缓存（避免重复请求）
HIST_KLINE_CACHE: dict = {}
# 公告缓存
ANNOUNCE_CACHE: dict = {}


def fetch_market_index() -> Optional[dict]:
    """获取大盘指数（上证指数）实时行情。"""
    return fetch_realtime_price("sh000001")


def fetch_historical_kline(code: str, days: int = 30) -> Optional[list]:
    """
    从新浪财经获取日 K 线数据（含 MA5/MA10/MA20）。
    返回列表，每项: {day, open, close, high, low, volume, ma5, ma10, ma20}
    """
    # 缓存
    if code in HIST_KLINE_CACHE:
        return HIST_KLINE_CACHE[code]

    key = stock_code_key(code)
    url = ("http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
           "CN_MarketData.getKLineData?symbol=%s&scale=240&ma=5,10,20&datalen=%d"
           % (key, days))
    try:
        resp = requests.get(url, timeout=8)
        data = resp.json()
        kline = []
        for d in data:
            kline.append({
                "day": d["day"][:10],
                "open": float(d["open"]),
                "close": float(d["close"]),
                "high": float(d["high"]),
                "low": float(d["low"]),
                "volume": int(d["volume"]) if d["volume"] else 0,
                "ma5": float(d.get("ma_price5", 0) or 0),
                "ma10": float(d.get("ma_price10", 0) or 0),
                "ma20": float(d.get("ma_price20", 0) or 0),
            })
        # 按日期排序（旧→新）
        kline.sort(key=lambda x: x["day"])
        HIST_KLINE_CACHE[code] = kline
        return kline
    except Exception as e:
        log.debug("获取历史 K 线失败 [%s]: %s", code, e)
        return None


def fetch_stock_announcements(code: str, limit: int = 5) -> list:
    """从东方财富获取最新公司公告。"""
    if code in ANNOUNCE_CACHE:
        return ANNOUNCE_CACHE[code]

    url = ("https://np-anotice-stock.eastmoney.com/api/security/ann?"
           "sr=-1&page_size=%d&page_index=1&ann_type=A&stock_list=%s&f_node=0&s_node=0"
           % (limit, code))
    try:
        resp = requests.get(url, timeout=8)
        data = resp.json()
        items = data.get("data", {}).get("list", [])
        result = []
        for item in items:
            title = item.get("title", "").strip()
            stime = item.get("display_time", "")[:10]
            if title:
                result.append({"title": title, "time": stime})
        ANNOUNCE_CACHE[code] = result
        return result
    except Exception as e:
        log.debug("获取公告失败 [%s]: %s", code, e)
        return []


def generate_stock_advice(
    stock_data: dict,
    index_data: Optional[dict] = None,
    kline_data: Optional[list] = None,
    announcements: Optional[list] = None,
) -> dict:
    """
    综合投资建议生成器。
    融合：Pivot Point + MA 趋势 + 成交量分析 + 相对大盘 + 公告信息
    """
    price = stock_data["price"]
    high = stock_data["high"]
    low = stock_data["low"]
    prev_close = stock_data["prev_close"]
    stock_pct = stock_data["percent"]
    volume = stock_data["volume"]

    # ── 1. Pivot Point ──
    pivot = (high + low + price) / 3
    r1 = max(2 * pivot - low, price * 0.98)
    s1 = min(2 * pivot - high, price * 1.02)
    if r1 <= price:
        r1 = price * 1.03
    if s1 >= price:
        s1 = price * 0.97

    # ── 2. MA 分析 ──
    ma5 = ma10 = ma20 = 0
    ma5_pct = ma10_pct = ma20_pct = 0.0  # 价格偏离 MA 的百分比
    trend = "震荡"
    trend_score = 0.0

    if kline_data and len(kline_data) >= 3:
        latest = kline_data[-1]
        ma5 = latest["ma5"]
        ma10 = latest["ma10"]
        ma20 = latest["ma20"]
        ma5_pct = (price - ma5) / ma5 * 100 if ma5 else 0
        ma10_pct = (price - ma10) / ma10 * 100 if ma10 else 0
        ma20_pct = (price - ma20) / ma20 * 100 if ma20 else 0

        # MA 多头排列判定：MA5 > MA10 > MA20
        bull_mas = ma5 > ma10 > ma20
        bear_mas = ma5 < ma10 < ma20
        # 价格在 MA 上方/下方
        above_ma5 = price > ma5
        above_ma20 = price > ma20

        if bull_mas and above_ma5 and above_ma20:
            trend = "多头排列"
            trend_score = 1.5
        elif bear_mas and not above_ma5 and not above_ma20:
            trend = "空头排列"
            trend_score = -1.5
        elif above_ma5 and price > ma10:
            trend = "短线偏多"
            trend_score = 0.8
        elif not above_ma5 and price < ma10:
            trend = "短线偏空"
            trend_score = -0.8
        elif ma5 < ma10 < ma20:
            trend = "均线收敛"
            trend_score = -0.3
        else:
            trend = "均线交织"
            trend_score = 0.0

        # 价格偏离 MA 过大时预警
        if abs(ma5_pct) > 8:
            trend += " (偏离MA5 %.1f%%)" % ma5_pct

    # ── 3. 成交量分析 ──
    vol_analysis = ""
    vol_score = 0.0
    vol_ratio = None
    if kline_data and len(kline_data) >= 10:
        # K 线量是股，转成手（1手=100股），与实时量单位统一
        vols = [k["volume"] / 100.0 for k in kline_data[-20:] if k["volume"] > 0]
        if vols:
            avg_vol = sum(vols) / len(vols)
            vol_ratio = volume / avg_vol if avg_vol else 1.0
            if vol_ratio > 2.0:
                vol_analysis = "放量%.1f倍" % vol_ratio
                vol_score = 0.5 if stock_pct > 0 else -0.8
            elif vol_ratio > 1.5:
                vol_analysis = "放量%.1f倍" % vol_ratio
                vol_score = 0.3 if stock_pct > 0 else -0.4
            elif vol_ratio < 0.5:
                vol_analysis = "缩量%.0f%%" % (vol_ratio * 100)
                vol_score = -0.2
            else:
                vol_analysis = "量能正常"

    # ── 4. 日内强弱 ──
    day_range = high - low
    pos_in_range = (price - low) / day_range if day_range > 0 else 0.5
    intraday_score = (pos_in_range - 0.5) * 2

    # ── 5. 相对大盘 ──
    index_pct = index_data["percent"] if index_data else 0
    relative_strength = stock_pct - index_pct
    rel_score = min(max(relative_strength / 2.0, -2.0), 2.0)

    # ── 6. 绝对涨跌幅分 ──
    pct_score = min(max(stock_pct / 3.0, -1.5), 1.5)

    # ── 综合评分 ──
    score = intraday_score + trend_score + vol_score + rel_score + pct_score
    score = max(min(score, 5), -5)

    # ── 生成信号 ──
    if score >= 2.0:
        signal = "买入 / 加仓"
        detail = "强势上涨，可考虑加仓"
        if relative_strength > 1.5:
            detail += "，明显跑赢大盘"
        if vol_ratio > 2.0 if kline_data else False:
            detail += "，量价配合良好"
    elif score >= 0.8:
        signal = "持有"
        detail = "走势稳健，继续持有"
        if trend == "多头排列":
            detail += "，均线多头排列"
        elif relative_strength > 0:
            detail += "，略强于大盘"
    elif score >= -0.5:
        signal = "持有观察"
        detail = "方向不明，观望为主"
        if relative_strength < -1:
            detail += "，注意大盘拖累"
        if vol_ratio < 0.5 if kline_data else False:
            detail += "，缩量整理中"
    elif score >= -2.0:
        signal = "谨慎持有"
        detail = "偏弱运行，注意风险"
        if trend == "空头排列":
            detail += "，均线空头压制"
        elif "放量" in vol_analysis and stock_pct < 0:
            detail += "，放量下跌需警惕"
    else:
        signal = "减仓 / 回避"
        detail = "弱势明显，建议减仓"
        if "放量" in vol_analysis and stock_pct < 0:
            detail += "，放量杀跌"
        if relative_strength < -2:
            detail += "，大幅跑输大盘"

    # ── 风险提示 ──
    warnings = []
    if price < low + day_range * 0.15:
        warnings.append("接近日内最低，关注能否企稳")
    elif price > high - day_range * 0.15:
        warnings.append("接近日内最高，注意回落")
    if stock_pct > 7:
        warnings.append("涨幅过大，警惕回调")
    elif stock_pct < -7:
        warnings.append("跌幅过大，恐慌释放中")
    # MA 偏离预警
    if ma5 and abs(ma5_pct) > 5:
        warnings.append("偏离MA5 %.1f%%" % ma5_pct)
    # 放量下跌预警
    if stock_pct < -2 and "放量" in vol_analysis:
        warnings.append("放量下跌注意风险")

    # ── 公告分析 ──
    announce_highlights = []
    if announcements:
        for ann in announcements[:3]:
            t = ann["title"]
            # 提取公告中的关键词摘要
            tag = ""
            if "分红" in t or "派息" in t or "送转" in t or "分配" in t:
                tag = "分红"
            elif "增减持" in t or "增持" in t or "减持" in t:
                tag = "增减持"
            elif "回购" in t:
                tag = "回购"
            elif "业绩" in t or "预告" in t or "快报" in t:
                tag = "业绩"
            elif "合同" in t or "中标" in t or "订单" in t:
                tag = "订单"
            elif "聘任" in t or "辞职" in t or "人事" in t:
                tag = "人事"
            elif "决" in t and ("议" in t or "案" in t):
                tag = "决议"
            elif "实施" in t:
                tag = "实施"
            else:
                tag = "公告"
            announce_highlights.append("%s (%s)" % (tag, ann["time"]))

    return {
        "signal": signal,
        "detail": detail,
        "target_price": round(r1, 2),
        "stop_loss": round(s1, 2),
        "pivot": round(pivot, 2),
        "score": round(score, 1),
        "warnings": warnings,
        "index_pct": index_pct,
        "relative_strength": round(relative_strength, 2),
        # 新增字段
        "trend": trend,
        "ma5": ma5,
        "ma10": ma10,
        "ma20": ma20,
        "ma5_pct": round(ma5_pct, 1),
        "ma10_pct": round(ma10_pct, 1),
        "ma20_pct": round(ma20_pct, 1),
        "vol_analysis": vol_analysis,
        "vol_ratio": round(vol_ratio, 1) if vol_ratio else None,
        "announce_highlights": announce_highlights,
    }


def format_advice_section(advice: dict) -> str:
    """格式化完整的投资建议区块。"""
    parts = []
    parts.append("  " + "-" * 56)

    sig = advice["signal"]
    score = advice["score"]

    # 信号颜色
    if score >= 1:
        score_color = "\033[91m"
    elif score >= -1:
        score_color = "\033[93m"
    else:
        score_color = "\033[92m"
    score_display = "%s%+.1f\033[0m" % (score_color, score)

    if "买入" in sig or "加仓" in sig:
        sig_tag = "\033[91m[ %s ]\033[0m" % sig
    elif "减仓" in sig or "回避" in sig:
        sig_tag = "\033[92m[ %s ]\033[0m" % sig
    elif "持有观察" in sig:
        sig_tag = "\033[93m[ %s ]\033[0m" % sig
    else:
        sig_tag = "\033[93m[ %s ]\033[0m" % sig

    parts.append("  %s  评分: %s" % (sig_tag, score_display))
    parts.append("    \033[90m%s\033[0m" % advice["detail"])

    # ── MA 趋势线 ──
    trend = advice.get("trend", "")
    ma5 = advice.get("ma5", 0)
    ma10 = advice.get("ma10", 0)
    ma20 = advice.get("ma20", 0)
    if ma5:
        # 颜色根据价格相对 MA 的位置
        def ma_color(pct):
            if abs(pct) < 1:
                return "\033[93m"  # 黄=持平
            return "\033[91m" if pct > 0 else "\033[92m"
        parts.append(
            "    MA5: %s%.2f(%+.1f%%)\033[0m  MA10: %s%.2f(%+.1f%%)\033[0m  MA20: %s%.2f(%+.1f%%)\033[0m  %s"
            % (ma_color(advice["ma5_pct"]), ma5, advice["ma5_pct"],
               ma_color(advice["ma10_pct"]), ma10, advice["ma10_pct"],
               ma_color(advice["ma20_pct"]), ma20, advice["ma20_pct"],
               trend)
        )

    # ── 成交量 ──
    vol = advice.get("vol_analysis", "")
    vol_r = advice.get("vol_ratio")
    if vol_r:
        parts.append("    成交量: \033[1m%s\033[0m (近20日均量对比)" % vol)

    # ── 目标/止损/枢轴 ──
    parts.append(
        "    \033[36m目标价\033[0m: \033[1;97m%.2f\033[0m  "
        "\033[35m止损价\033[0m: \033[1;97m%.2f\033[0m  "
        "\033[90m枢轴: %.2f\033[0m"
        % (advice["target_price"], advice["stop_loss"], advice["pivot"])
    )

    # ── 大盘对比 ──
    idx_pct = advice["index_pct"]
    rel = advice["relative_strength"]
    idx_prefix = "+" if idx_pct >= 0 else ""
    rel_prefix = "+" if rel >= 0 else ""
    rel_color = "\033[91m" if rel > 0 else "\033[92m"
    parts.append(
        "    上证: %s%.2f%%  |  相对强度: %s%s%.2f%%\033[0m"
        % (idx_prefix, idx_pct, rel_color, rel_prefix, rel)
    )

    # ── 公告亮点 ──
    anns = advice.get("announce_highlights", [])
    if anns:
        parts.append("    \033[90m近日公告: %s\033[0m" % " | ".join(anns))

    # ── 风险提示 ──
    for w in advice.get("warnings", []):
        parts.append("    \033[93m%s\033[0m" % w)

    return "\n".join(parts)


# ── 显示格式化 ───────────────────────────────────────────────────────────

def colorize(text: str, change: float) -> str:
    """根据涨跌返回带颜色的文本（ANSI）。"""
    if change > 0:
        return "\033[91m%s\033[0m" % text   # 红涨
    elif change < 0:
        return "\033[92m%s\033[0m" % text   # 绿跌
    return text


def format_price_bar(current: float, targets: list, width: int = 40) -> str:
    """简易价格柱状图 — 显示当前价在目标价区间的位置。"""
    if not targets:
        return ""
    prices = [t.price for t in targets] + [current]
    min_p, max_p = min(prices), max(prices)
    span = max_p - min_p or 1
    bar = ["-"] * width
    # 标记目标价位置
    for t in targets:
        pos = min(width - 1, int((t.price - min_p) / span * (width - 1)))
        marker = "v" if t.direction == "above" else "^"
        if 0 <= pos < width:
            bar[pos] = marker if bar[pos] == "-" else "X"
    # 标记当前位置
    cur_pos = min(width - 1, int((current - min_p) / span * (width - 1)))
    if 0 <= cur_pos < width:
        bar[cur_pos] = "@"
    info = "min=%.2f  max=%.2f  @=%.2f" % (min_p, max_p, current)
    return "".join(bar) + "  " + info


def format_stock_row(data: dict) -> str:
    """格式化单条股票行情 — 核心股价突出显示。"""
    name = data["name"]
    code = data["code"]
    price = data["price"]
    change = data["change"]
    percent = data["percent"]
    open_p = data["open"]
    high = data["high"]
    low = data["low"]
    prev_close = data["prev_close"]
    vol = data["volume"]
    amo = data["amount"]

    # 涨跌箭头与颜色
    if change > 0:
        arrow = "↑"
        tag = " 涨"
    elif change < 0:
        arrow = "↓"
        tag = " 跌"
    else:
        arrow = "-"
        tag = " 平"

    prefix = "+" if change >= 0 else ""

    # 第一行：股票名 + 当前股价（大号加粗）
    parts = []
    parts.append("")
    parts.append("  " + "=" * 56)
    parts.append("  %s (%s)" % (name, code))
    parts.append("  " + "-" * 56)
    parts.append(
        "    当前股价: \033[1;97m%s%.2f\033[0m   %s  %s"
        % (colorize(arrow, change), price,
           colorize("%s%.2f" % (prefix, change), change),
           colorize("%s%.2f%%%s" % (prefix, percent, tag), change))
    )
    # 第二行：开盘 / 最高 / 最低 / 昨收
    parts.append(
        "    开盘: \033[1m%.2f\033[0m  |  最高: \033[1;91m%.2f\033[0m  |  最低: \033[1;92m%.2f\033[0m  |  昨收: %.2f"
        % (open_p, high, low, prev_close)
    )
    # 第三行：成交量 / 成交额
    parts.append(
        "    成交量: %.0f万手  |  成交额: %.1f亿"
        % (vol / 10000, amo)
    )
    parts.append("  " + "=" * 56)

    return "\n".join(parts)


# ── 核心监控逻辑 ─────────────────────────────────────────────────────────

def monitor_loop(
    codes: list[str],
    targets: list[PriceTarget],
    change_targets: list[ChangeTarget] = None,
    interval: int = 60,
    max_checks: Optional[int] = None,
    no_sound: bool = False,
    no_notify: bool = False,
    open_url: bool = False,
    no_advice: bool = False,
):
    """
    主监控循环。
    codes: 股票代码列表
    targets: 目标价格列表
    change_targets: 涨跌幅目标列表
    interval: 轮询间隔（秒）
    max_checks: 最大检查次数（None=无限）
    """
    if change_targets is None:
        change_targets = []
    if not targets and not change_targets:
        log.warning("[-] 未设置任何目标，仅显示行情。用 --target / --change 设置。")

    check_count = 0
    alerts_history: list[dict] = []
    index_cache = None  # 大盘指数缓存，每次循环取一次

    print_header(codes, targets, change_targets, interval)

    while max_checks is None or check_count < max_checks:
        check_count += 1
        now = datetime.datetime.now()
        timestamp = now.strftime("%Y-%m-%d %H:%M:%S")

        # 非交易时间处理：--once 模式照样抓取，连续监控则跳过
        if not is_trading_time(now):
            if max_checks is not None and max_checks <= 1:
                # --once 模式：不跳过，直接抓取（盘后也能看行情）
                pass
            else:
                # 连续监控：跳过，等待开盘
                cached_info = ""
                if STOCK_NAME_CACHE:
                    cached_info = " | ".join(
                        "%s" % c for c in codes if c in STOCK_NAME_CACHE
                    )
                msg = "\r[%s] 非交易时间，等待中...  %s" % (timestamp, cached_info)
                print(msg, end="", flush=True)
                time.sleep(interval)
                continue

        print("\n" + "#" * 60)
        print("#  [%s]  第 %d 次检查" % (timestamp, check_count))
        print("#" * 60)

        for code in codes:
            data = fetch_realtime_price(code)
            if not data:
                print("  [!] %s: 获取失败，跳过" % code)
                continue

            # 打印股价详情
            print(format_stock_row(data))

            # 投资建议（默认开启，--no-advice 关闭）
            if not no_advice:
                try:
                    if index_cache is None:
                        index_cache = fetch_market_index()
                    # 首次取历史 K 线和公告（缓存）
                    if code not in HIST_KLINE_CACHE:
                        HIST_KLINE_CACHE[code] = fetch_historical_kline(code)
                    if code not in ANNOUNCE_CACHE:
                        ANNOUNCE_CACHE[code] = fetch_stock_announcements(code)
                    kline = HIST_KLINE_CACHE.get(code)
                    anns = ANNOUNCE_CACHE.get(code)
                    advice = generate_stock_advice(
                        data, index_cache, kline_data=kline, announcements=anns
                    )
                    print(format_advice_section(advice))
                except Exception as e:
                    log.debug("生成投资建议失败: %s", e)

            # 检查价格目标
            for target in targets:
                if target.check(data["price"]):
                    direction_cn = "上涨突破" if target.direction == "above" else "下跌跌破"
                    msg = (
                        "%s(%s) 当前价 %.2f 已达目标价 %.2f (%s)"
                        % (data["name"], code, data["price"], target.price, direction_cn)
                    )
                    print("\n  " + "!" * 50)
                    print("  >>> " + msg)
                    print("  " + "!" * 50 + "\n")

                    alerts_history.append({
                        "time": timestamp,
                        "code": code,
                        "name": data["name"],
                        "price": data["price"],
                        "target": target.price,
                        "direction": direction_cn,
                        "type": "price",
                    })

                    if not no_notify:
                        notify_desktop("A股价格提醒", msg)
                    if not no_sound:
                        play_alert_sound()
                    if open_url:
                        open_stock_url(code)

            # 检查涨跌幅目标
            for ct in change_targets:
                if ct.check(data["percent"]):
                    direct_cn = "涨幅超过" if ct.direction == "above" else "跌幅超过"
                    target_pct = ct.percent if ct.direction == "above" else -abs(ct.percent)
                    msg = (
                        "%s(%s) 当前涨跌幅 %.2f%% 已达目标 %s %.1f%%"
                        % (data["name"], code, data["percent"], direct_cn, abs(target_pct))
                    )
                    print("\n  " + "!" * 50)
                    print("  >>> " + msg)
                    print("  " + "!" * 50 + "\n")

                    alerts_history.append({
                        "time": timestamp,
                        "code": code,
                        "name": data["name"],
                        "price": data["price"],
                        "percent": data["percent"],
                        "target_pct": target_pct,
                        "direction": direct_cn,
                        "type": "change",
                    })

                    if not no_notify:
                        notify_desktop("A股涨跌幅提醒", msg)
                    if not no_sound:
                        play_alert_sound()
                    if open_url:
                        open_stock_url(code)

        # 显示目标价/涨跌幅状态概览
        if targets or change_targets:
            last = fetch_realtime_price(codes[0])
            if last:
                status_parts = []
                for t in targets:
                    if t.tripped:
                        status_parts.append("\033[93m[价已触发 %.2f]\033[0m" % t.price)
                    else:
                        arrow = "涨" if t.direction == "above" else "跌"
                        status_parts.append("[价目标 %.2f %s]" % (t.price, arrow))
                for ct in change_targets:
                    if ct.tripped:
                        status_parts.append("\033[93m[幅已触发 %.1f%%]\033[0m" % ct.percent)
                    else:
                        pct = ct.percent if ct.direction == "above" else -abs(ct.percent)
                        dire = "涨超" if ct.direction == "above" else "跌超"
                        status_parts.append("[幅目标 %s%.1f%%]" % (dire, abs(pct)))
                print("  [目标] " + " | ".join(status_parts))

                if targets:
                    bar = format_price_bar(last["price"], targets)
                    if bar:
                        print("  [价格带] " + bar)

        # 保存提醒历史
        if alerts_history:
            save_alerts(alerts_history)

        if max_checks is None:
            print("  [*] 休眠 %d 秒..." % interval)
            time.sleep(interval)
        elif check_count < max_checks:
            print("  [*] 休眠 %d 秒... (剩余 %d 次)" % (interval, max_checks - check_count))
            time.sleep(interval)

    # 监控结束
    print("")
    print("=" * 60)
    print("监控结束，本次提醒汇总：")
    if alerts_history:
        for a in alerts_history:
            if a.get("type") == "change":
                print(
                    "  [%s] %s -> 涨跌幅目标 %.1f%% (实际 %.2f%%)"
                    % (a["time"], a["name"], a["target_pct"], a["percent"])
                )
            else:
                print(
                    "  [%s] %s -> 目标价 %.2f (实际 %.2f) %s"
                    % (a["time"], a["name"], a["target"], a["price"], a["direction"])
                )
    else:
        print("  (无触发)")


def is_trading_time(now: Optional[datetime.datetime] = None) -> bool:
    """
    判断是否为 A 股交易时间。
    交易时段：
      上午 9:30 - 11:30
      下午 13:00 - 15:00
    周末不交易。
    """
    if now is None:
        now = datetime.datetime.now()
    weekday = now.weekday()
    if weekday >= 5:  # 周六日
        return False
    hour = now.hour
    minute = now.minute
    time_val = hour * 60 + minute
    morning = (9 * 60 + 30) <= time_val <= (11 * 60 + 30)
    afternoon = (13 * 60) <= time_val <= (15 * 60)
    return morning or afternoon


def print_header(codes, targets, change_targets=None, interval=60):
    """打印启动头信息。"""
    if change_targets is None:
        change_targets = []
    names = []
    for c in codes:
        n = get_stock_name(c) or c
        names.append("%s(%s)" % (n, c))
    target_str = ", ".join(
        "%.2f[涨]" % t.price if t.direction == "above" else "%.2f[跌]" % t.price
        for t in targets
    ) if targets else ""
    change_str = ", ".join(
        "%.1f%%[涨超]" % t.percent if t.direction == "above" else "%.1f%%[跌超]" % (-t.percent if t.percent < 0 else t.percent)
        for t in change_targets
    ) if change_targets else ""
    goals = []
    if target_str:
        goals.append("目标价: " + target_str)
    if change_str:
        goals.append("涨跌幅: " + change_str)
    if not goals:
        goals.append("仅显示行情")
    print("")
    print("=" * 60)
    print("  A 股实时监控工具")
    print("=" * 60)
    print("  股票: " + ", ".join(names))
    for g in goals:
        print("  " + g)
    print("  轮询间隔: %d 秒" % interval)
    print("=" * 60)
    print("")


def save_alerts(alerts: list[dict]):
    """保存提醒记录到 JSON 文件。"""
    path = LOG_DIR / "alerts.json"
    try:
        existing = []
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                existing = json.load(f)
        existing.extend(alerts)
        # 只保留最近 500 条
        existing = existing[-500:]
        with open(path, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.warning("保存提醒记录失败: %s", e)


# ── 命令行入口 ───────────────────────────────────────────────────────────

def parse_target_arg(arg: str) -> Optional[PriceTarget]:
    """解析单个目标价参数，格式：'190'、'200:above'、'180:below'。"""
    arg = arg.strip()
    if ":" in arg:
        price_str, direction = arg.rsplit(":", 1)
        direction = direction.strip().lower()
        if direction not in ("above", "below", "上", "下", "突破", "跌破"):
            print("  [-] 无效方向 '%s'，使用默认 'above'" % direction, file=sys.stderr)
            direction = "above"
        elif direction in ("上", "突破"):
            direction = "above"
        elif direction in ("下", "跌破"):
            direction = "below"
        return PriceTarget(float(price_str), direction)
    return PriceTarget(float(arg), "above")


def parse_change_arg(arg: str) -> Optional[ChangeTarget]:
    """
    解析涨跌幅目标参数。
    格式: '5' = 涨超 5%  |  '-3' = 跌超 3%
          '5:above'      |  '3:below'
          '5:涨'         |  '3:跌'
    """
    arg = arg.strip()
    if ":" in arg:
        val_str, direction = arg.rsplit(":", 1)
        val = float(val_str)
        direction = direction.strip().lower()
        if direction in ("above", "涨", "上"):
            return ChangeTarget(abs(val), "above")
        elif direction in ("below", "跌", "下"):
            return ChangeTarget(-abs(val), "below")
        else:
            print("  [-] 无效方向 '%s'，使用默认 'above'" % direction, file=sys.stderr)
            return ChangeTarget(abs(val), "above")
    # 不带方向：正数=涨，负数=跌
    val = float(arg)
    if val >= 0:
        return ChangeTarget(val, "above")
    else:
        return ChangeTarget(val, "below")


def main():
    parser = argparse.ArgumentParser(
        prog="stock_monitor",
        description="A 股实时股价监控提醒工具（含大盘分析+投资建议）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            示例：
              %(prog)s 600519 --target 190 195
              %(prog)s 000858 600519 --target 180:below 200:above -i 15
              %(prog)s 600519 --target 200:突破 --no-sound
              %(prog)s 002415 --target 45:跌破 --once --open-url
              %(prog)s 600519 --change 5         涨超 5%% 时提醒
              %(prog)s 600519 --change -3         跌超 3%% 时提醒
              %(prog)s 600519 --change 3:below    跌超 3%% 时提醒
              %(prog)s 600519 -t 1220 -c 5        同时监控价格和涨跌幅
              %(prog)s 600519 --once              查行情 + 自动出投资建议
              %(prog)s 600519 --once --no-advice  只看行情，不要建议
        """),
    )
    parser.add_argument(
        "codes", nargs="+",
        help="股票代码（多个用空格分隔），如 600519 000858"
    )
    parser.add_argument(
        "-t", "--target", action="append", default=[],
        help="目标价，格式: 190  或  200:above  或  180:below  或 200:突破",
    )
    parser.add_argument(
        "-c", "--change", action="append", default=[],
        help="涨跌幅目标(百分比)，格式: 5 或 -3 或 5:above 或 3:below",
    )
    parser.add_argument(
        "-i", "--interval", type=int, default=60,
        help="轮询间隔（秒），默认 60 秒"
    )
    parser.add_argument(
        "--once", action="store_true",
        help="仅执行一次检查后退出"
    )
    parser.add_argument(
        "-n", "--checks", type=int, default=None,
        help="检查 N 次后退出（默认持续监控）"
    )
    parser.add_argument(
        "--no-sound", action="store_true",
        help="关闭声音提醒"
    )
    parser.add_argument(
        "--no-notify", action="store_true",
        help="关闭桌面通知"
    )
    parser.add_argument(
        "--open-url", action="store_true",
        help="触发提醒时自动在浏览器打开股票详情页"
    )
    parser.add_argument(
        "--watch-only", action="store_true",
        help="仅显示行情，不设目标价"
    )
    parser.add_argument(
        "--debug", action="store_true",
        help="开启调试日志"
    )
    parser.add_argument(
        "--no-advice", action="store_true",
        help="关闭投资建议功能"
    )

    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        log.setLevel(logging.DEBUG)

    if args.watch_only and (args.target or args.change):
        print("  [!] --watch-only 与 --target/--change 冲突，忽略所有目标设置")
        args.target = []
        args.change = []

    # 解析目标价
    targets = []
    for t in args.target:
        try:
            pt = parse_target_arg(t)
            targets.append(pt)
        except ValueError as e:
            print("  [!] 目标价格式错误 '%s': %s" % (t, e), file=sys.stderr)
            sys.exit(1)

    # 解析涨跌幅目标
    change_targets = []
    for c in args.change:
        try:
            ct = parse_change_arg(c)
            change_targets.append(ct)
        except ValueError as e:
            print("  [!] 涨跌幅参数错误 '%s': %s" % (c, e), file=sys.stderr)
            sys.exit(1)

    max_checks = 1 if args.once else args.checks

    print("正在初始化，获取股票信息...")
    time.sleep(0.5)

    try:
        monitor_loop(
            codes=args.codes,
            targets=targets,
            change_targets=change_targets,
            interval=args.interval,
            max_checks=max_checks,
            no_sound=args.no_sound,
            no_notify=args.no_notify,
            open_url=args.open_url,
            no_advice=args.no_advice,
        )
    except KeyboardInterrupt:
        print("\n\n监控已手动停止。")
        sys.exit(0)


if __name__ == "__main__":
    main()
