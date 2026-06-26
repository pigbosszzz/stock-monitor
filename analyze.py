#!/usr/bin/env python3
"""A 股多源投资分析工具 — CLI 入口"""
from __future__ import annotations

import argparse, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from stock_analyzer.analyzer import StockAnalyzer
from stock_analyzer.config import load_config
from stock_analyzer.fetchers.tencent import TencentFetcher
from stock_analyzer.fetchers.sina import SinaFetcher
from stock_analyzer.fetchers.eastmoney import EastMoneyFetcher
from stock_analyzer.formatter import (
    format_analysis, format_market_report, format_market_context, format_board_rankings,
)
from stock_analyzer.market import MarketAnalyzer


def main():
    parser = argparse.ArgumentParser(prog="analyze",
        description="A 股多源投资分析工具",
        epilog="示例:\n  python analyze.py --market    # 自选股 + 大盘")
    parser.add_argument("codes", nargs="*")
    parser.add_argument("--config", "-c", default="config.yaml")
    parser.add_argument("--watchlist", "-w", default="watchlist.yaml")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--source", "-s", type=str)
    parser.add_argument("--no-advice", action="store_true")
    parser.add_argument("--no-boards", action="store_true")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--market", action="store_true",
                        help="显示大盘分析")
    parser.add_argument("--market-only", action="store_true",
                        help="仅显示大盘分析")
    args = parser.parse_args()

    import logging
    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO,
                         format="%(message)s")

    config_dir = Path(__file__).parent
    cfg = load_config(str(config_dir / args.config), str(config_dir / args.watchlist))

    if args.codes:
        codes = args.codes
        entries = {}
    elif cfg.stocks:
        codes = [s.code for s in cfg.stocks]
        entries = {s.code: s for s in cfg.stocks}
    else:
        print("[!] 未指定股票代码。", file=sys.stderr)
        sys.exit(1)

    sources = args.source.split(",") if args.source else cfg.analysis.use_sources

    # ── 共享 Fetcher 实例（避免重复创建连接）──
    tf = TencentFetcher()
    sf = SinaFetcher()
    em = EastMoneyFetcher()

    # ═══ 大盘 ═══
    market_report = None
    ma = None
    if args.market or args.market_only:
        ma = MarketAnalyzer(cfg=cfg, tencent=tf, eastmoney=em)
        market_report = ma.generate_report()
        print(format_market_report(market_report))
        if args.market_only:
            return

    analyzer = StockAnalyzer(cfg=cfg, tencent=tf, sina=sf, eastmoney=em)

    if not args.market_only:
        if not args.market:
            print("╔" + "═" * 58 + "╗")
            print("║  A 股多源投资分析" + " " * 42 + "║")
            print("╚" + "═" * 58 + "╝")

        results = []
        peer_quotes_map = {}
        for code in codes:
                        entry = entries.get(code.strip() if not isinstance(entries, dict) else code.strip())
            cp = entry.cost_price or 0 if entry else 0
            sh = entry.shares or 0 if entry else 0
            r = analyzer.analyze(code.strip(), sources=sources, cost_price=cp, shares=sh)
            results.append(r)
            if r.quote:
                peer_quotes_map[code] = analyzer.fetch_peer_quotes(code)

        # 板块排行
        board_data = {}
        if market_report and ma:
            board_stocks = {}
            for r in results:
                for b in r.boards:
                    bn = b.name if hasattr(b, 'name') else str(b)
                    if bn not in board_stocks:
                        board_stocks[bn] = set()
                    for p in r.peers:
                        board_stocks[bn].add(p.code)
                    board_stocks[bn].add(r.code)
            seen = {}
            deduped = {}
            for bn, codes_set in board_stocks.items():
                key = frozenset(codes_set)
                if key not in seen:
                    seen[key] = bn
                    deduped[bn] = codes_set
            items = list(deduped.items())[1:cfg.market.top_boards + 1]
            board_data = ma.fetch_board_ranking(dict(items), per_board=cfg.market.board_display)

        for r in results:
            if args.once:
                q = r.quote
                if q:
                    a = "↑" if q.change > 0 else ("↓" if q.change < 0 else "─")
                    c = "\033[91m" if q.change > 0 else ("\033[92m" if q.change < 0 else "")
                    print(f"  {q.name} ({q.code})  {c}{q.price:.2f} {a} {q.percent:+.2f}%\033[0m")
                else:
                    print(f"  [!] {r.code}: 获取失败")
            else:
                peer_qs = peer_quotes_map.get(r.code, [])
                print(format_analysis(r, show_detail=not args.no_advice, peer_quotes=peer_qs))
                if market_report and ma:
                    ctxs = ma.analyze_with_market(market_report, [r])
                    ctx = ctxs.get(r.code, {})
                    if ctx:
                        print(format_market_context(ctx, r.name))

        if board_data:
            print(format_board_rankings(board_data))

    print(f"\n{'─' * 60}")
    print("  ℹ 以上分析基于技术指标，不构成投资建议。")
    print()


if __name__ == "__main__":
    main()
