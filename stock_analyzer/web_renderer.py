"""Web dashboard renderer."""
from datetime import datetime
from pathlib import Path
import webbrowser

def _css():
    p = Path(__file__).parent / "dashboard.css"
    return p.read_text(encoding="utf-8")

def fc(v):
    if v >= 0: return f"+{v:.2f}%"
    return f"{v:.2f}%"

def cz(v):
    if v > 0: return "up"
    if v < 0: return "down"
    return ""

def sg(s):
    if any(k in s for k in ("买入","加仓")): return "buy"
    if any(k in s for k in ("减仓","回避")): return "sell"
    return "hold"

def render(al, mr=None):
    css = _css()
    n = datetime.now().strftime("%Y-%m-%d %H:%M")
    L = []
    L.append("<html><head><meta charset=UTF-8><style>"+css+"</style></head><body>")
    L.append(f"<div class=header><h1>Dashboard</h1><div class=time>{n}</div></div>")

    if mr and mr.indices:
        L.append("<div class=market-section><div class=market-grid>")
        for x in mr.indices:
            c = cz(x.percent)
            L.append(f"<div class=index-card><div class=name>{x.index_name}</div>")
            L.append(f"<div class=\"val {c}\">{x.price:,.0f}</div>")
            L.append(f"<div class=\"change {c}\">{fc(x.percent)}</div></div>")
        L.append("</div></div>")

    L.append("<div class=grid>")
    for r in al:
        q = r.quote
        if not q: continue
        a = "uarr;" if q.percent>0 else ("darr;" if q.percent<0 else "mdash;")
        pc, sc = cz(q.percent), sg(r.signal)

        L.append(f"<div class=card><div class=card-title>{q.name}<span class=code>{q.code}</span></div>")
        L.append(f"<div class=price-row><span class=price>{q.price:.2f}</span>")
        L.append(f"<span class=\"change {pc}\">&{a}; {q.change:+.2f} ({fc(q.percent)})</span></div>")
        L.append("<div class=info-grid>")
        L.append(f"<div>Open <span>{q.open:.2f}</span></div><div>High <span style=color:#3fb950>{q.high:.2f}</span></div>")
        L.append(f"<div>Prev <span>{q.prev_close:.2f}</span></div><div>Low <span style=color:#f85149>{q.low:.2f}</span></div>")
        L.append(f"<div>Vol <span>{q.volume:,}</span></div><div>Amt <span>{q.amount:,.0f}</span></div>")
        L.append("</div>")

        if r.cost_price and r.shares:
            pc2 = "up" if r.profit_loss>0 else "down"
            L.append(f"<div class=holding><span class=label>P&amp;L</span> ")
            L.append(f"Cost {r.cost_price:.2f} x {r.shares:,} = {r.market_value:,.0f} | ")
            L.append(f"<span class={pc2}>{r.profit_loss:+,.0f} ({fc(r.profit_loss_pct)})</span></div>")

        L.append(f"<div class=\"signal {sc}\">{r.signal}</div>")
        L.append(f"<div class=detail>Score: {r.score:+.1f} | {r.detail}</div>")

        if r.ma5:
            L.append(f"<div class=ma-row>MA5:{r.ma5:.2f}({fc(r.ma5_pct)}) MA10:{r.ma10:.2f}({fc(r.ma10_pct)}) MA20:{r.ma20:.2f}({fc(r.ma20_pct)})|{r.trend}</div>")

        L.append(f"<div class=target-row><span class=t>Target {r.target_price:.2f}</span><span class=s>Stop {r.stop_loss:.2f}</span></div>")

        ir = getattr(r, "_industry_rank", None)
        if ir and ir.ranked_stocks:
            L.append(f"<div class=section-title>Industry: {ir.industry_name}</div><div class=rank-list>")
            for i, s in enumerate(ir.ranked_stocks):
                cl = "mine" if s.get("code") == r.code else ""
                p2 = cz(s.get("percent", 0))
                nm = s.get("name", "")
                cd = s.get("code", "")
                pt = s.get("percent", 0)
                L.append(f"<div class=\"rank-row {cl}\"><span class=name>{i+1}. {nm} ({cd})</span><span class={p2}>{fc(pt)}</span></div>")
            L.append("</div>")

        for w in r.warnings:
            L.append(f"<div class=warn>! {w}</div>")
        L.append("</div>")

    L.append("</div><div class=footer>Not financial advice</div></body></html>")
    return "".join(L)

def save_and_open(html, fname="stock_dashboard.html"):
    p = Path(fname)
    p.write_text(html, encoding="utf-8")
    webbrowser.open("file:///" + str(p.absolute()))
    return str(p)