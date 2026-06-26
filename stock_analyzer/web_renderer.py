"""Web dashboard renderer."""
from datetime import datetime
from pathlib import Path
import webbrowser

def _css():
    p = Path(__file__).parent / "dashboard.css"
    return p.read_text(encoding="utf-8")

def fc(v):
    return f"+{v:.2f}%" if v >= 0 else f"{v:.2f}%"

def cz(v):
    return "up" if v > 0 else ("down" if v < 0 else "")

def sg(s):
    if any(k in s for k in ("买入","加仓")): return "buy"
    if any(k in s for k in ("减仓","回避")): return "sell"
    return "hold"

def render(al, mr=None):
    css = _css()
    n = datetime.now().strftime("%Y-%m-%d %H:%M")
    L = []
    L.append("<html><head><meta charset=UTF-8><style>"+css+"</style></head><body>")
    L.append("<div class=header><h1>股票分析看板</h1><div class=time>"+n+"</div></div>")

    if mr and mr.indices:
        L.append("<div class=market-section><div class=market-grid>")
        for x in mr.indices:
            L.append("<div class=index-card><div class=name>"+x.index_name+"</div>")
            L.append("<div class=\"val "+cz(x.percent)+"\">"+str(int(x.price))+"</div>")
            L.append("<div class=\"change "+cz(x.percent)+"\">"+fc(x.percent)+"</div></div>")
        L.append("</div></div>")

    L.append("<div class=grid>")
    for r in al:
        q = r.quote
        if not q: continue
        a = "uarr;" if q.percent>0 else ("darr;" if q.percent<0 else "mdash;")
        pc, sc = cz(q.percent), sg(r.signal)

        L.append("<div class=card>")
        L.append("<div class=card-title>"+q.name+"<span class=code>"+q.code+"</span></div>")
        L.append("<div class=price-row><span class=price>"+str(q.price)+"</span>")
        L.append("<span class=\"change "+pc+"\">&"+a+"; "+str(q.change)+" ("+fc(q.percent)+")</span></div>")
        L.append("<div class=info-grid>")
        L.append("<div>开盘 <span>"+str(q.open)+"</span></div><div>最高 <span style=color:#3fb950>"+str(q.high)+"</span></div>")
        L.append("<div>昨收 <span>"+str(q.prev_close)+"</span></div><div>最低 <span style=color:#f85149>"+str(q.low)+"</span></div>")
        L.append("<div>成交量 <span>"+str(q.volume)+"手</span></div><div>成交额 <span>"+str(int(q.amount))+"万</span></div>")
        L.append("</div>")

        if r.cost_price and r.shares:
            pc2 = "up" if r.profit_loss>0 else "down"
            L.append("<div class=holding>")
            L.append("<div class=holding-title>持仓明细</div>")
            L.append("<div class=holding-grid>")
            L.append("<div>成本</div><div>"+str(r.cost_price)+"</div>")
            L.append("<div>持仓</div><div>"+str(r.shares)+"股</div>")
            L.append("<div>市值</div><div>"+str(int(r.market_value))+"</div>")
            L.append("<div>盈亏</div><div><span class="+pc2+">"+str(int(r.profit_loss))+" ("+fc(r.profit_loss_pct)+")</span></div>")
            L.append("</div></div>")
        L.append("<div class=target-row><span class=t>目标价 "+str(r.target_price)+"</span>  <span class=s>止损价 "+str(r.stop_loss)+"</span></div>")

        L.append("<div class=\"signal "+sc+"\">"+r.signal+"</div>")
        L.append("<div class=detail>评分: "+str(r.score)+" | "+r.detail+"</div>")

        if r.ma5:
            L.append("<div class=ma-row>MA5:"+str(r.ma5)+"("+fc(r.ma5_pct)+") MA10:"+str(r.ma10)+"("+fc(r.ma10_pct)+") MA20:"+str(r.ma20)+"("+fc(r.ma20_pct)+") | "+r.trend+"</div>")

        ir = getattr(r, "_industry_rank", None)
        if ir and ir.ranked_stocks:
            L.append("<div class=section-title>行业排名 - "+ir.industry_name+"</div>")
            L.append("<div class=rank-list>")
            for i, s in enumerate(ir.ranked_stocks):
                cl = "mine" if s.get("code") == r.code else ""
                p2 = cz(s.get("percent", 0))
                nm = s.get("name", "")
                cd = s.get("code", "")
                pt = s.get("percent", 0)
                L.append("<div class=\"rank-row "+cl+"\"><span class=name>"+str(i+1)+". "+nm+" ("+cd+")</span><span class="+p2+">"+fc(pt)+"</span></div>")
            L.append("</div>")

        for w in r.warnings:
            L.append("<div class=warn>! "+w+"</div>")
        L.append("</div>")

    L.append("</div><div class=footer>以上分析不构成投资建议</div></body></html>")
    return "\n".join(L)

def save_and_open(html, fname="stock_dashboard.html"):
    p = Path(fname)
    p.write_text(html, encoding="utf-8")
    webbrowser.open("file:///" + str(p.absolute()))
    return str(p)