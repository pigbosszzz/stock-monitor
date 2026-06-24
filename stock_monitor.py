"""
A股实时股价监控提醒工具
=========================
功能：
  1. 实时获取 A 股股价（腾讯免费接口，无需 API Key）
  2. 监控多个股票，支持多个目标价
  3. 达到目标价时：桌面通知 + 声音提醒 + 控制台高亮
  4. 记录历史提醒日志

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

            # 打印股价详情（format_stock_row 已包含完整布局）
            print(format_stock_row(data))

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
        description="A 股实时股价监控提醒工具",
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
        )
    except KeyboardInterrupt:
        print("\n\n监控已手动停止。")
        sys.exit(0)


if __name__ == "__main__":
    main()
