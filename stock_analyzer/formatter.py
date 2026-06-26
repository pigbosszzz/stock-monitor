"""
输出格式化 — 将分析结果渲染为彩色终端输出（纯格式化，不获取数据）。
"""
from __future__ import annotations


class Color:
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    CYAN = "\033[36m"
    MAGENTA = "\033[35m"
    GRAY = "\033[90m"
    BOLD = "\033[1m"
    BRIGHT = "\033[1;97m"
    RESET = "\033[0m"


def _price_color(change: float) -> str:
    if change > 0: return Color.RED
    if change < 0: return Color.GREEN
    return Color.YELLOW


def _signal_color(signal: str) -> str:
    if "买入" in signal or "加仓" in signal: return Color.RED
    if "减仓" in signal or "回避" in signal: return Color.GREEN
    return Color.YELLOW


def _ma_line(ma: float, pct: float) -> str:
    if abs(pct) < 1: color = Color.YELLOW
    else: color = Color.RED if pct > 0 else Color.GREEN
    return f"{color}{ma:.2f}({pct:+.1f}%){Color.RESET}"


def _fmt_amount(amount: float) -> str:
    if amount >= 10000: return f"{amount / 10000:.2f}亿"
    return f"{amount:,.0f}万"


def _format_peers(peer_quotes: list, max_stocks: int = 5) -> list[str]:
    MAIN = ("600", "601", "603", "605", "000", "001", "002", "003")
    lines = []
    count = 0
    for q in peer_quotes:
        if not q.code.startswith(MAIN): continue
        if count >= max_stocks: break
        count += 1
        arrow = "↑" if q.percent > 0 else ("↓" if q.percent < 0 else "─")
        color = _price_color(q.percent)
        prefix = "+" if q.percent >= 0 else ""
        lines.append(
            f"{q.name}({q.code})  {Color.BRIGHT}{q.price:.2f}{Color.RESET}"
            f"  {color}{arrow} {prefix}{q.percent:.2f}%{Color.RESET}"
        )
    if not lines and peer_quotes:
        f_count = len([p for p in peer_quotes if not p.code.startswith(MAIN)])
        if f_count:
            lines.append(f"{Color.GRAY}(已跳过{f_count}只科创板/创业板票){Color.RESET}")
    return lines


def format_analysis(result, show_detail: bool = True,
                    peer_quotes: list | None = None) -> str:
    lines = []
    q = result.quote
    if q:
        change = q.change
        color = _price_color(change)
        arrow = "↑" if change > 0 else ("↓" if change < 0 else "─")
        tag = "涨" if change > 0 else ("跌" if change < 0 else "平")
        prefix = "+" if change >= 0 else ""

        lines.append("")
        lines.append("  " + "=" * 60)
        lines.append(f"  {q.name} ({q.code})")
        lines.append("  " + "-" * 60)
        lines.append(
            f"    当前股价: {Color.BRIGHT}{q.price:.2f}{Color.RESET}"
            f"   {color}{arrow} {prefix}{change:.2f}  {prefix}{q.percent:.2f}%{tag}{Color.RESET}"
        )
        lines.append(
            f"    开盘: {Color.BOLD}{q.open:.2f}{Color.RESET}"
            f"  |  最高: {Color.RED}{q.high:.2f}{Color.RESET}"
            f"  |  最低: {Color.GREEN}{q.low:.2f}{Color.RESET}"
            f"  |  昨收: {q.prev_close:.2f}"
        )
        lines.append(
            f"    成交量: {q.volume:,}手  |  成交额: {_fmt_amount(q.amount)}"
        )
        if result.data_sources:
            lines.append(f"    {Color.GRAY}数据来源: {', '.join(result.data_sources)}{Color.RESET}")
    else:
        return f"\n  [!] {result.name} ({result.code}): 数据获取失败"

    if not show_detail:
        return "\n".join(lines)

    # 信号
    sig_color = _signal_color(result.signal)
    sc = result.score
    if sc >= 1: sd = f"{Color.RED}+{sc}{Color.RESET}"
    elif sc <= -1: sd = f"{Color.GREEN}{sc}{Color.RESET}"
    else: sd = f"{Color.YELLOW}{sc}{Color.RESET}"
    lines.append(f"    {sig_color}[ {result.signal} ]{Color.RESET}  评分: {sd}")
    lines.append(f"    {Color.GRAY}{result.detail}{Color.RESET}")

    # MA
    if result.ma5:
        t = result.trend
        lines.append(
            f"    MA5: {_ma_line(result.ma5, result.ma5_pct)}  "
            f"MA10: {_ma_line(result.ma10, result.ma10_pct)}  "
            f"MA20: {_ma_line(result.ma20, result.ma20_pct)}  "
            f"{'多头排列' if '多头' in t else ('空头排列' if '空头' in t else t)}"
        )

    # 成交量
    if result.vol_ratio:
        lines.append(f"    成交量: {Color.BOLD}{result.vol_analysis}{Color.RESET} (近20日均量对比)")

    # 目标/止损/枢轴
    lines.append(
        f"    {Color.CYAN}目标价{Color.RESET}: {Color.BRIGHT}{result.target_price:.2f}{Color.RESET}"
        f"  {Color.MAGENTA}止损价{Color.RESET}: {Color.BRIGHT}{result.stop_loss:.2f}{Color.RESET}"
        f"  {Color.GRAY}枢轴: {result.pivot:.2f}{Color.RESET}"
    )

    # 相对强度
    rs = result.relative_strength
    lines.append(f"    相对强度: {Color.RED if rs > 0 else Color.GREEN}{rs:+.2f}%{Color.RESET}")

    # 板块
    if result.boards:
        industry = result.boards[0].name if result.boards else ""
        concepts = [b.name for b in result.boards[1:]]
        if concepts:
            lines.append(f"    {Color.CYAN}行业{Color.RESET}: {industry}    {Color.CYAN}概念{Color.RESET}: {' | '.join(concepts[:8])}")
        elif industry:
            lines.append(f"    {Color.CYAN}行业{Color.RESET}: {industry}")

    # 公告
    if result.announce_highlights:
        lines.append(f"    {Color.GRAY}近日公告: {' | '.join(result.announce_highlights)}{Color.RESET}")

    # 对标股（数据已由调用方预取）
    if peer_quotes:
        peer_lines = _format_peers(peer_quotes)
        if peer_lines:
            lines.append(f"    {Color.MAGENTA}行业对标{Color.RESET}:")
            for pl in peer_lines:
                lines.append(f"      {pl}")

    # 风险
    for w in result.warnings:
        lines.append(f"    {Color.YELLOW}⚠ {w}{Color.RESET}")

    return "\n".join(lines)


def format_batch(results: list) -> str:
    lines = ["", "=" * 60, f"  📊 股票分析报告  ({len(results)} 只)", "=" * 60]
    for r in results:
        lines.append(format_analysis(r))
    lines.extend(["", "─" * 60, "  ℹ 以上分析基于技术指标，不构成投资建议。", ""])
    return "\n".join(lines)


# ═══ 大盘格式化 ═══

def format_market_report(report) -> str:
    lines = ["", "╔" + "═" * 58 + "╗",
             "║  📈 今日大盘全景" + " " * 45 + "║",
             "╚" + "═" * 58 + "╝", ""]

    if report.indices:
        lines.append(f"  {Color.CYAN}主要指数{Color.RESET}")
        lines.append("  " + "─" * 32)
        for idx in report.indices:
            arrow = "↑" if idx.percent > 0 else ("↓" if idx.percent < 0 else "─")
            color = Color.RED if idx.percent > 0 else Color.GREEN
            prefix = "+" if idx.percent >= 0 else ""
            lines.append(
                f"    {idx.index_name:<6s}  {Color.BRIGHT}{idx.price:>10.2f}{Color.RESET}"
                f"  {color}{arrow} {prefix}{idx.percent:+.2f}%{Color.RESET}"
                f"  {Color.GRAY}成交 {idx.volume:.0f}亿{Color.RESET}"
            )
        lines.append("")

    if report.hot_sectors:
        lines.append(f"  {Color.RED}🔥 板块强弱排行（ETF）{Color.RESET}")
        lines.append("  " + "─" * 42)
        for s in report.hot_sectors[:10]:
            color = Color.RED if s.percent > 0 else Color.GREEN
            prefix = "+" if s.percent >= 0 else ""
            lines.append(f"    {s.name:<16s}  {color}{prefix}{s.percent:>+.2f}%{Color.RESET}")
        lines.append("")

    if report.top_gainers_day:
        lines.append(f"  {Color.RED}🚀 今日主板涨幅榜{Color.RESET}")
        lines.append("  " + "─" * 58)
        show = report.top_gainers_day[:30]
        for i in range(0, len(show), 3):
            row = show[i:i+3]
            parts = []
            for s in row:
                parts.append(
                    f"{s['name']:<6s}({s['code']}) "
                    f"{Color.RED}↑{s['percent']:+.1f}%{Color.RESET}"
                )
            lines.append("    " + "  │  ".join(parts))
        if len(report.top_gainers_day) > 30:
            lines.append(f"    {Color.GRAY}...共 {len(report.top_gainers_day)} 只{Color.RESET}")
        lines.append("")

    if report.top_losers_day:
        lines.append(f"  {Color.GREEN}📉 今日主板跌幅榜{Color.RESET}")
        lines.append("  " + "─" * 58)
        show = report.top_losers_day[:30]
        for i in range(0, len(show), 3):
            row = show[i:i+3]
            parts = []
            for s in row:
                parts.append(
                    f"{s['name']:<6s}({s['code']}) "
                    f"{Color.GREEN}↓{s['percent']:+.1f}%{Color.RESET}"
                )
            lines.append("    " + "  │  ".join(parts))
        if len(report.top_losers_day) > 30:
            lines.append(f"    {Color.GRAY}...共 {len(report.top_losers_day)} 只{Color.RESET}")
        lines.append("")

    return "\n".join(lines)


def format_board_rankings(board_data: dict) -> str:
    if not board_data: return ""
    lines = [f"  {Color.CYAN}📋 板块涨跌排行{Color.RESET}", "  " + "─" * 50]
    for board_name, stocks in board_data.items():
        if not stocks: continue
        avg = sum(s["percent"] for s in stocks) / len(stocks)
        color = Color.RED if avg > 0 else Color.GREEN
        prefix = "+" if avg >= 0 else ""
        lines.append(f"    {Color.BOLD}{board_name}{Color.RESET}  ({color}均{prefix}{avg:+.1f}%{Color.RESET})")
        for s in stocks:
            sc = Color.RED if s["percent"] > 0 else Color.GREEN
            sp = "+" if s["percent"] >= 0 else ""
            arrow = "↑" if s["percent"] > 0 else ("↓" if s["percent"] < 0 else "─")
            lines.append(
                f"      {s['name']:<8s}({s['code']})  "
                f"{Color.BRIGHT}{s['price']:.2f}{Color.RESET}"
                f"  {sc}{arrow} {sp}{s['percent']:.2f}%{Color.RESET}"
            )
        lines.append("")
    return "\n".join(lines)


def format_market_context(context: dict, stock_name: str) -> str:
    if not context: return ""
    idx_pct = context.get("sh_index_pct", 0)
    color = Color.RED if idx_pct > 0 else Color.GREEN
    prefix = "+" if idx_pct >= 0 else ""
    trend = context.get("market_trend", "未知")
    lines = [
        f"    {Color.GRAY}大盘环境: {trend} "
        f"(上证 {color}{prefix}{idx_pct:.2f}%{Color.RESET}{Color.GRAY}){Color.RESET}"
    ]
    if context.get("in_hot_sector"):
        m = context.get("hot_sectors_matched", [])
        lines.append(f"    {Color.RED}🔥 {stock_name} 处于今日热门板块: {', '.join(m)}{Color.RESET}")
    return "\n".join(lines)
